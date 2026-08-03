"""Tool: get_cluster_candidate_articles.

Returns the full content of articles from two candidate clusters (stories) for a potential merge decision.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

async def get_cluster_candidate_articles(args: dict[str, Any], db_query: DbQuery) -> str:
    cluster_a = str(args.get("cluster_id_a", ""))
    cluster_b = str(args.get("cluster_id_b", ""))
    
    async def fetch_articles(cluster_id: str) -> list[dict[str, Any]]:
        if not cluster_id:
            return []
        return await db_query(
            """
            SELECT a.id, a.headline, a.clean_content, a.published_at
            FROM articles a
            JOIN story_articles sa ON a.id = sa.article_id
            WHERE sa.story_id = :sid
            ORDER BY a.published_at ASC
            LIMIT 5
            """,
            {"sid": cluster_id},
        )

    rows_a = await fetch_articles(cluster_a)
    rows_b = await fetch_articles(cluster_b)
    
    lines = [f"Cluster A (story_id={cluster_a!r}) articles:"]
    if not rows_a:
        lines.append("  (No articles found)")
    else:
        for r in rows_a:
            lines.append(f"  - [{r['id']}] {r['headline']} ({r['published_at']})")
            lines.append(f"    Preview: {str(r.get('clean_content', ''))[:400]}...")
            
    lines.append(f"\nCluster B (story_id={cluster_b!r}) articles:")
    if not rows_b:
        lines.append("  (No articles found)")
    else:
        for r in rows_b:
            lines.append(f"  - [{r['id']}] {r['headline']} ({r['published_at']})")
            lines.append(f"    Preview: {str(r.get('clean_content', ''))[:400]}...")
            
    return "\n".join(lines)
