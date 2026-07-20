"""Phase 27 — hot-path performance indexes.

Background / justification
---------------------------
EXPLAIN ANALYZE on the Fast Path entity-alias lookup and Cold Path full-text
query at 50 000-article scale identified three missing composite indexes:

1. ``entity_aliases(lower(alias_text))`` — The Fast Path resolve step does
   ``WHERE lower(a.alias_text) = lower(:q)``.  The existing B-tree index on
   ``alias_text`` is case-sensitive, so Postgres falls back to a sequential
   scan for case-folded lookups once the table grows beyond ~10k rows.
   A functional index on ``lower(alias_text)`` makes this O(log n).

2. ``stories(primary_entity_id, status, updated_at DESC)`` — the Cold Path
   entity-known branch sorts by ``updated_at DESC`` *after* filtering on
   ``primary_entity_id = :eid AND status = 'active'``.  The existing separate
   indexes on ``primary_entity_id`` and ``status`` force a bitmap AND + sort;
   a composite covering index eliminates the sort entirely.

3. ``story_articles(story_id, article_id)`` covering — the article-preview
   subquery ``WHERE sa.story_id = ANY(:sids)`` scans the full join table.
   The primary key is (story_id, article_id) but only as individual columns;
   an explicit composite index makes the ANY-array lookup index-only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Note: CREATE INDEX CONCURRENTLY requires running outside a transaction
    # (production: use `alembic upgrade head` via a dedicated script that
    # sets isolation_level=AUTOCOMMIT per connection). For dev/CI on a
    # fresh database we use regular CREATE INDEX (safe — no live traffic).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entity_aliases_lower_alias "
        "ON entity_aliases (lower(alias_text))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stories_entity_status_updated "
        "ON stories (primary_entity_id, status, updated_at DESC) "
        "WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_story_articles_story_article "
        "ON story_articles (story_id, article_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stories_status_updated_partial "
        "ON stories (updated_at DESC) "
        "WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_content_tsv "
        "ON articles USING gin (to_tsvector('english', coalesce(clean_content,'')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_aliases_lower_alias")
    op.execute("DROP INDEX IF EXISTS ix_stories_entity_status_updated")
    op.execute("DROP INDEX IF EXISTS ix_story_articles_story_article")
    op.execute("DROP INDEX IF EXISTS ix_stories_status_updated_partial")
    op.execute("DROP INDEX IF EXISTS ix_articles_content_tsv")
