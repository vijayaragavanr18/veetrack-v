"""
Seed script: pull live data from NewsData.io + RSS feeds, create stories in DB,
build feed cache in Redis — bypassing Celery workers so the frontend sees real data immediately.

Usage:
    PYTHONPATH=src python seed_live_data.py [entity]

Example:
    PYTHONPATH=src python seed_live_data.py "Artificial Intelligence"
    PYTHONPATH=src python seed_live_data.py Technology
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import structlog

log = structlog.get_logger()

DATABASE_URL = "postgresql+asyncpg://veetrack:devpassword@localhost:5432/veetrack"
REDIS_URL = "redis://localhost:6379/0"
NEWSDATA_API_KEY = "pub_4b70425554be4b0a8c0e740c5be2f9f1"

LOOKBACK_HOURS = 48

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://feeds.feedburner.com/TechCrunch",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
]

_FEED_KEY_PREFIX = "vt:feed:"
_TRACKED_KEY_PREFIX = "vt:tracked:"
_ALIAS_KEY_PREFIX = "vt:alias:"


def _dedup_hash(url: str, source_id: str) -> str:
    return hashlib.sha256(f"{source_id}:{url}".encode()).hexdigest()


async def fetch_newsdata(query: str, since: datetime) -> list[dict]:
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    params = {
        "apikey": NEWSDATA_API_KEY,
        "q": query,
        "language": "en",
        "size": 10,
        "timeframe": 48,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get("https://newsdata.io/api/1/latest", params=params)
            r.raise_for_status()
            data = r.json()
            articles = []
            for item in data.get("results", []):
                pub_date = item.get("pubDate") or item.get("publishedAt", "")
                try:
                    if pub_date:
                        dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        if dt < since:
                            continue
                    articles.append({
                        "external_id": item.get("article_id") or item.get("link", ""),
                        "url": item.get("link", ""),
                        "headline": item.get("title", ""),
                        "publisher": item.get("source_name") or item.get("source_id", ""),
                        "published_at": pub_date,
                        "raw_content": item.get("description") or item.get("content") or "",
                        "hero_image_url": item.get("image_url"),
                        "language": item.get("language", "en"),
                        "source": "newsdata",
                    })
                except Exception:
                    continue
            print(f"  NewsData: fetched {len(articles)} articles for '{query}'")
            return articles
        except Exception as e:
            print(f"  NewsData error: {e}")
            return []


async def fetch_rss(feed_urls: list[str], since: datetime) -> list[dict]:
    import feedparser  # type: ignore
    articles = []
    for url in feed_urls:
        try:
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, lambda u=url: feedparser.parse(u))
            for entry in feed.entries:
                # Parse published date
                pub = None
                for attr in ("published_parsed", "updated_parsed"):
                    val = getattr(entry, attr, None)
                    if val:
                        import time
                        pub = datetime.fromtimestamp(time.mktime(val), tz=UTC)
                        break
                if pub and pub < since:
                    continue
                articles.append({
                    "external_id": getattr(entry, "id", "") or getattr(entry, "link", ""),
                    "url": getattr(entry, "link", ""),
                    "headline": getattr(entry, "title", ""),
                    "publisher": feed.feed.get("title", url),
                    "published_at": pub.isoformat() if pub else datetime.now(UTC).isoformat(),
                    "raw_content": getattr(entry, "summary", "") or getattr(entry, "description", ""),
                    "hero_image_url": None,
                    "language": "en",
                    "source": "rss",
                })
        except Exception as e:
            print(f"  RSS error {url}: {e}")
    print(f"  RSS: fetched {len(articles)} articles from {len(feed_urls)} feeds")
    return articles


async def seed(entity_name: str) -> None:
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    redis: Redis = Redis.from_url(REDIS_URL, decode_responses=False)

    since = datetime.now(UTC) - timedelta(hours=LOOKBACK_HOURS)
    now = datetime.now(UTC)

    print(f"\n=== Seeding live data for: '{entity_name}' ===")
    print(f"    Lookback: {since.strftime('%Y-%m-%d %H:%M UTC')} → now\n")

    # Fetch from APIs
    newsdata_articles = await fetch_newsdata(entity_name, since)
    rss_articles = await fetch_rss(RSS_FEEDS, since)
    all_articles = newsdata_articles + rss_articles

    if not all_articles:
        print("No articles fetched. Check API keys and network.")
        return

    print(f"\n  Total articles: {len(all_articles)}")

    async with factory() as session, session.begin():
        # 1. Upsert entity
        entity_row = await session.execute(
            text("SELECT id FROM entities WHERE lower(canonical_name) = lower(:name)"),
            {"name": entity_name},
        )
        row = entity_row.first()
        if row:
            entity_id = str(row[0])
            print(f"  Entity exists: {entity_id}")
        else:
            entity_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO entities (id, canonical_name, entity_type, created_at, updated_at)
                    VALUES (:id, :name, 'topic', :now, :now)
                """),
                {"id": entity_id, "name": entity_name, "now": now},
            )
            # Also add alias
            await session.execute(
                text("""
                    INSERT INTO entity_aliases (id, entity_id, alias_text, created_at)
                    VALUES (:id, :eid, :alias, :now)
                    ON CONFLICT DO NOTHING
                """),
                {"id": str(uuid.uuid4()), "eid": entity_id, "alias": entity_name.lower(), "now": now},
            )
            print(f"  Created entity: {entity_id}")

        # 2. Upsert one umbrella story for this entity (reuse today's story if it exists)
        story_title = f"{entity_name} — Latest News ({now.strftime('%b %d, %Y')})"
        existing_story = await session.execute(
            text("""
                SELECT id FROM stories
                WHERE primary_entity_id = :eid AND title = :title
                LIMIT 1
            """),
            {"eid": entity_id, "title": story_title},
        )
        story_row = existing_story.first()
        if story_row:
            story_id = str(story_row[0])
            print(f"  Reusing story: {story_id}")
        else:
            story_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO stories
                        (id, title, status, risk_level, primary_entity_id, created_at, updated_at)
                    VALUES
                        (:id, :title, 'active', 'medium', :eid, :now, :now)
                """),
                {"id": story_id, "title": story_title, "eid": entity_id, "now": now},
            )
            print(f"  Created story: {story_id}")

        # 3. Ensure sources row exists (articles has FK → sources)
        source_id = f"seed-{entity_name.lower().replace(' ', '-')[:40]}"
        src_exists = await session.execute(
            text("SELECT id FROM sources WHERE id = :id"),
            {"id": source_id},
        )
        if not src_exists.first():
            await session.execute(
                text("""
                    INSERT INTO sources (id, type, config_json, is_active)
                    VALUES (:id, 'rss', '{}', true)
                """),
                {"id": source_id},
            )

        # 4. Insert articles and link to story
        saved = skipped = 0
        for art in all_articles:
            if not art.get("url") or not art.get("headline"):
                continue
            dhash = _dedup_hash(art["external_id"] or art["url"], source_id)

            existing = await session.execute(
                text("SELECT id FROM articles WHERE dedup_hash = :h"),
                {"h": dhash},
            )
            if existing.first():
                skipped += 1
                continue

            # Parse published_at
            pub_at = now
            try:
                if art["published_at"]:
                    pub_at = datetime.fromisoformat(art["published_at"].replace("Z", "+00:00"))
                    if pub_at.tzinfo is None:
                        pub_at = pub_at.replace(tzinfo=UTC)
            except Exception:
                pass

            article_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO articles
                        (id, source_id, external_id, url, headline, hero_image_url,
                         publisher, published_at, raw_content, clean_content,
                         language, sentiment_label, sentiment_score, dedup_hash, ingested_at)
                    VALUES
                        (:id, :source_id, :ext_id, :url, :headline, :img,
                         :publisher, :pub_at, :raw, '',
                         :lang, 'neutral', 0.0, :dhash, :now)
                """),
                {
                    "id": article_id,
                    "source_id": source_id,
                    "ext_id": (art["external_id"] or art["url"])[:255],
                    "url": art["url"][:2048],
                    "headline": art["headline"][:500],
                    "img": art.get("hero_image_url"),
                    "publisher": (art.get("publisher") or "")[:200],
                    "pub_at": pub_at,
                    "raw": (art.get("raw_content") or "")[:10000],
                    "lang": art.get("language", "en")[:10],
                    "dhash": dhash,
                    "now": now,
                },
            )
            # Link article to story
            await session.execute(
                text("""
                    INSERT INTO story_articles (story_id, article_id)
                    VALUES (:sid, :aid)
                    ON CONFLICT DO NOTHING
                """),
                {"sid": story_id, "aid": article_id},
            )
            saved += 1

        print(f"  Articles: saved={saved}, skipped(dedup)={skipped}")

        if saved == 0:
            print("  No new articles inserted — data may already exist.")

    # 4. Build feed cache in Redis
    async with factory() as session:
        art_rows = await session.execute(
            text("""
                SELECT a.id, a.headline, a.publisher, a.published_at,
                       a.sentiment_label, a.hero_image_url, a.url
                FROM articles a
                JOIN story_articles sa ON sa.article_id = a.id
                WHERE sa.story_id = :sid
                ORDER BY a.published_at DESC
                LIMIT 10
            """),
            {"sid": story_id},
        )
        articles_list = []
        primary_article = None
        for ar in art_rows:
            item = {
                "id": str(ar.id),
                "headline": ar.headline or "",
                "publisher": ar.publisher or "",
                "published_at": ar.published_at.isoformat() if ar.published_at else "",
                "sentiment_label": ar.sentiment_label or "neutral",
                "hero_image_url": ar.hero_image_url,
                "url": ar.url or "",
            }
            articles_list.append(item)
            if primary_article is None:
                primary_article = item

        total_count = await session.execute(
            text("SELECT COUNT(*) FROM story_articles WHERE story_id = :sid"),
            {"sid": story_id},
        )
        article_count = total_count.scalar() or 0

    if not primary_article:
        print("  No articles linked to story — skipping cache build")
        return

    # Build a proper feed payload matching StoryPayload schema
    payload = [{
        "id": story_id,
        "title": story_title,
        "status": "active",
        "risk_level": "medium",
        "primary_entity_id": entity_id,
        "entity_name": entity_name,
        "article_count": article_count,
        "articles": articles_list[:5],
        "insight": None,
        "cluster_member_ids": [a["id"] for a in articles_list],
        "recommendations": [],
        "updated_at": now.isoformat(),
    }]

    feed_key = f"{_FEED_KEY_PREFIX}{entity_id}".encode()
    tracked_key = f"{_TRACKED_KEY_PREFIX}{entity_id}".encode()
    alias_key = f"{_ALIAS_KEY_PREFIX}{entity_name.lower()}".encode()

    payload_bytes = json.dumps(payload, default=str).encode()
    await redis.set(feed_key, payload_bytes, ex=86400)   # 24 hours
    await redis.set(tracked_key, b"1", ex=86400)
    # Cache alias so Fast Path resolves entity_name → entity_id
    await redis.set(alias_key, f"{entity_id}\x00{entity_name}".encode(), ex=86400)

    print(f"  Feed cache written: {len(payload_bytes)} bytes")
    print(f"\n✓ Done! Feed ready at: GET /api/v1/feed?entity={entity_name.replace(' ', '%20')}")

    await redis.aclose()
    await engine.dispose()


if __name__ == "__main__":
    entity = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Technology"
    asyncio.run(seed(entity))
