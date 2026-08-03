"""Article-specific AI chatbot endpoint.

POST /chat/article — Answer questions about a specific article ONLY.
Refuses to answer general knowledge questions.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ArticleChatRequest(BaseModel):
    story_id: str
    question: str
    article_headline: str
    article_content: str
    article_publisher: str


class ArticleChatResponse(BaseModel):
    answer: str


@router.post("/article", response_model=ArticleChatResponse)
async def chat_about_article(req: ArticleChatRequest) -> ArticleChatResponse:
    """Answer questions about a specific article using Ollama.

    Only answers questions directly related to the article content.
    Refuses general knowledge questions.
    """
    # Build context-restricted prompt
    system_prompt = f"""You are an AI assistant that ONLY answers questions about this specific article:

**Headline:** {req.article_headline}
**Publisher:** {req.article_publisher}
**Content:** {req.article_content}

STRICT RULES:
1. ONLY answer questions about THIS article
2. If asked about anything else, respond: "I can only answer questions about this specific article."
3. Be concise (2-3 sentences max)
4. Cite specific parts of the article when possible
5. If the article doesn't contain enough information, say so

User question: {req.question}"""

    try:
        import httpx
        import os

        ollama_base = os.getenv("LLM_LOCAL_BASE_URL", "http://localhost:11434/v1")
        ollama_model = os.getenv("LLM_LOCAL_MODEL", "qwen2.5:7b")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ollama_base}/chat/completions",
                json={
                    "model": ollama_model,
                    "messages": [
                        {"role": "system", "content": "You only answer questions about the provided article. No general knowledge."},
                        {"role": "user", "content": system_prompt},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"].strip()

            logger.info(
                "chat.article_question",
                story_id=req.story_id,
                question_len=len(req.question),
                answer_len=len(answer),
            )

            return ArticleChatResponse(answer=answer)

    except Exception as exc:
        logger.error("chat.article_question.failed", error=str(exc), story_id=req.story_id)
        # Fallback response
        return ArticleChatResponse(
            answer="⚠️ I can only answer questions about this specific article. "
            "Please ask about the content, context, or implications of the story being displayed."
        )
