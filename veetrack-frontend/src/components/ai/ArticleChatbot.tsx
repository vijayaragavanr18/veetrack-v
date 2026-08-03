'use client';

import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2, AlertTriangle } from 'lucide-react';
import type { MockStory } from '@/types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ArticleChatbotProps {
  story: MockStory;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function ArticleChatbot({ story }: ArticleChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const article = story.primary_article;

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  // Reset chat when story changes
  useEffect(() => {
    setMessages([]);
    setInput('');
  }, [story.id]);

  async function handleSend() {
    const question = input.trim();
    if (!question || isLoading) return;

    // Add user message
    const userMessage: Message = { role: 'user', content: question };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // Call backend chatbot endpoint
      const response = await fetch(`${API_BASE}/api/v1/chat/article`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          story_id: story.id,
          question: question,
          article_headline: article.headline,
          article_content: article.content_preview || '',
          article_publisher: article.publisher,
        }),
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.status}`);
      }

      const data = await response.json();
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.answer || 'Sorry, I could not generate a response.',
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      const errorMessage: Message = {
        role: 'assistant',
        content: '⚠️ I can only answer questions about this specific article. Please ask about the content, context, or implications of the story being displayed.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="absolute bottom-20 right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:scale-110 active:scale-95 transition-transform"
        aria-label="Open AI assistant"
      >
        <MessageCircle className="h-5 w-5" aria-hidden />
      </button>
    );
  }

  return (
    <div className="absolute bottom-20 right-4 z-40 flex flex-col w-[calc(100%-2rem)] max-w-[380px] h-[500px] rounded-2xl border border-border bg-background shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-2xl border-b border-border bg-primary/5 backdrop-blur-sm px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20">
            <MessageCircle className="h-4 w-4 text-primary" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">Article Assistant</p>
            <p className="text-[10px] text-muted-foreground">Ask about this article</p>
          </div>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          aria-label="Close chat"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {/* Article context banner */}
      <div className="shrink-0 border-b border-border/50 bg-muted/30 backdrop-blur-sm px-3 py-2">
        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">
          Current Article
        </p>
        <p className="text-xs font-semibold text-foreground line-clamp-2 leading-snug">
          {article.headline}
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          {article.publisher} • {new Date(article.published_at).toLocaleDateString()}
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <MessageCircle className="h-6 w-6 text-primary" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground mb-1">
                Ask me about this article
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                I can explain the content, provide context, analyze sentiment, or answer questions about this specific story.
              </p>
            </div>
            <div className="w-full rounded-lg border border-orange-500/20 bg-orange-500/5 px-3 py-2 mt-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-3.5 w-3.5 text-orange-500 shrink-0 mt-0.5" aria-hidden />
                <p className="text-[10px] text-orange-600/90 dark:text-orange-400/90 leading-relaxed">
                  I only answer questions about the article currently displayed. I cannot discuss other topics or general knowledge.
                </p>
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted border border-border text-foreground'
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-muted border border-border px-3 py-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />
              <span className="text-xs text-muted-foreground">Thinking...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border bg-background/95 backdrop-blur-sm px-3 py-3">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this article..."
            disabled={isLoading}
            className="flex-1 rounded-full border border-input bg-muted/50 px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground hover:bg-primary/90 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            aria-label="Send message"
          >
            <Send className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
