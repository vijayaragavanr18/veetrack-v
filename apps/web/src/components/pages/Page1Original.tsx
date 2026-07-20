"use client";

/**
 * Page 1 — Original story view.
 *
 * Layout: fixed-aspect hero image (no layout shift) → headline → metadata row
 * → entity tags → story context paragraph.
 *
 * Hero image notes:
 *   - aspect-[16/7] container always reserves space → zero CLS
 *   - `onError` swaps to the BookOpen fallback without a flash
 *   - blur placeholder via blurDataURL (inline 1×1 muted-tone LQIP)
 */

import { useState } from "react";
import Image from "next/image";
import { BookOpen, AlertTriangle, BookMarked } from "lucide-react";
import type { MockStory } from "@/types";
import { Badge } from "@/components/ui/badge";
import SentimentBadge from "@/components/ui/SentimentBadge";
import SourceIcon from "@/components/ui/SourceIcon";
import PublishedTime from "@/components/ui/PublishedTime";
import WatchlistToggle from "@/components/ui/WatchlistToggle";

interface Props {
  story: MockStory;
}

// 1×1 dark-grey PNG as a tiny base64 blur placeholder — prevents the
// white-flash that appears before next/image loads the real image.
const LQIP =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

const riskVariant: Record<string, "low" | "medium" | "high" | "critical"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

export default function Page1Original({ story }: Props) {
  const { primary_article: article } = story;
  const [imgError, setImgError] = useState(false);

  const showImage = !!article.hero_image_url && !imgError;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* ── Hero image ────────────────────────────────────────────────────── */}
      {/*
        aspect-[16/7] is set on the container, not the image, so the space is
        always reserved regardless of whether the image has loaded — zero CLS.
      */}
      <div className="relative w-full aspect-[16/7] shrink-0 bg-muted overflow-hidden rounded-t-lg">
        {showImage ? (
          <Image
            src={article.hero_image_url!}
            alt=""
            aria-hidden
            fill
            className="object-cover"
            sizes="(max-width: 768px) 100vw, 800px"
            priority
            placeholder="blur"
            blurDataURL={LQIP}
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex items-center justify-center h-full bg-muted" aria-hidden>
            <BookOpen className="h-12 w-12 text-muted-foreground opacity-40" />
          </div>
        )}

        {/* Gradient overlay — only when image is visible */}
        {showImage && (
          <div
            className="absolute inset-0 bg-gradient-to-t from-background/80 via-background/20 to-transparent"
            aria-hidden
          />
        )}

        {/* Risk badge — top right */}
        <div className="absolute top-3 right-3">
          <Badge variant={riskVariant[story.risk_level] ?? "low"}>
            <AlertTriangle className="h-3 w-3 mr-1" aria-hidden />
            <span>{story.risk_level.toUpperCase()} RISK</span>
          </Badge>
        </div>
      </div>

      {/* ── Content ───────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 p-5">
        {/* Headline */}
        <h1 className="text-xl font-bold leading-snug">{article.headline}</h1>

        {/* Metadata row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          {/* Publisher name */}
          {article.publisher && (
            <span className="font-medium text-foreground shrink-0">
              {article.publisher}
            </span>
          )}

          {/* Published time with absolute on hover */}
          <PublishedTime iso={article.published_at} />

          {/* Article count */}
          <span className="flex items-center gap-1 shrink-0">
            <BookMarked className="h-3.5 w-3.5" aria-hidden />
            {story.article_count} article{story.article_count === 1 ? "" : "s"}
          </span>

          {/* Sentiment — icon + text, not color-only */}
          <SentimentBadge label={article.sentiment_label} />

          {/* Source icon — 44px touch target, opens URL in new tab */}
          <span className="ml-auto -my-2">
            <SourceIcon
              publisher={article.publisher}
              url={article.url}
            />
          </span>
        </div>

        {/* Entity tags + watchlist toggle */}
        {story.entities.length > 0 && (
          <div className="flex flex-wrap items-center gap-2" aria-label="Related entities">
            {story.entities.map((entity) => (
              <Badge key={entity.id} variant="secondary" className="text-xs">
                {entity.canonical_name}
                <span className="ml-1 opacity-50 font-normal capitalize">
                  {entity.type}
                </span>
              </Badge>
            ))}
            {story.entities[0] && (
              <WatchlistToggle
                entityId={story.entities[0].id}
                entityName={story.entities[0].canonical_name}
                className="ml-auto"
              />
            )}
          </div>
        )}

        {/* Story context — the story title gives broader context than the article headline */}
        {story.title !== article.headline && (
          <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-border pl-3">
            {story.title}
          </p>
        )}
      </div>
    </div>
  );
}
