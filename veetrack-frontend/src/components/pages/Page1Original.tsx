"use client";

import { useState } from "react";
import Image from "next/image";
import { BookOpen, ExternalLink } from "lucide-react";
import type { MockStory } from "@/types";
import { Badge } from "@/components/ui/badge";
import PublishedTime from "@/components/ui/PublishedTime";
import WatchlistToggle from "@/components/ui/WatchlistToggle";
import CategoryTag from "@/components/ui/CategoryTag";
import EngagementRow from "@/components/ui/EngagementRow";
import { useSavedStore } from "@/store/savedStore";

const LQIP =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

const riskVariant: Record<string, "low" | "medium" | "high" | "critical"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

interface Props {
  story: MockStory;
}

export default function Page1Original({ story }: Props) {
  const { primary_article: article } = story;
  const [imgError, setImgError] = useState(false);
  const { saveStory, unsaveStory, isSaved } = useSavedStore();
  const saved = isSaved(story.id);

  const showImage = !!article.hero_image_url && !imgError;
  const entityLabel = story.entities[0]?.canonical_name ?? story.title.split(" ")[0];
  const primaryEntity = story.entities[0];

  // Body: real content preview > story title fallback
  const bodyText =
    article.content_preview?.trim() ||
    (story.title !== article.headline ? story.title : null) ||
    `${story.article_count} article${story.article_count === 1 ? "" : "s"} tracked. Swipe right for the full AI analysis.`;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-card">
      {/* ── Hero image — full-bleed, 42% of card ─────────────────────── */}
      <div className="relative w-full flex-none" style={{ height: "42%" }}>
        {showImage ? (
          <Image
            src={article.hero_image_url!}
            alt=""
            aria-hidden
            fill
            className="object-cover"
            sizes="430px"
            priority
            placeholder="blur"
            blurDataURL={LQIP}
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex items-center justify-center w-full h-full bg-muted" aria-hidden>
            <BookOpen className="h-14 w-14 text-muted-foreground opacity-25" />
          </div>
        )}

        {/* Scrim gradient over image */}
        {showImage && (
          <div
            className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-card via-card/50 to-transparent"
            aria-hidden
          />
        )}

        {/* Source pill — top-left of hero */}
        {article.url && (
          <div className="absolute top-3 left-3 z-10">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 bg-background/80 backdrop-blur-sm rounded-full px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-background/95 transition-colors border border-border/30"
              aria-label={`Read full article on ${article.publisher || "source"}`}
            >
              <ExternalLink className="h-2.5 w-2.5 shrink-0" aria-hidden />
              {article.publisher || "Source"}
            </a>
          </div>
        )}

        {/* Category tag — bottom-left */}
        <div className="absolute bottom-3 left-3">
          <CategoryTag label={entityLabel} />
        </div>

        {/* Risk badge — top-right */}
        <div className="absolute top-3 right-3">
          <Badge variant={riskVariant[story.risk_level] ?? "low"} className="text-[10px] font-semibold">
            {story.risk_level.toUpperCase()} RISK
          </Badge>
        </div>
      </div>

      {/* ── Content area ──────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-h-0 px-4 pt-3 pb-0 gap-2">

        {/* Headline */}
        <h1 className="text-[17px] font-bold leading-tight line-clamp-3 text-foreground">
          {article.headline}
        </h1>

        {/* Source row: publisher · time · article count · watchlist */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap shrink-0">
          {article.publisher && (
            <span className="font-semibold text-foreground/80 truncate max-w-[120px]">
              {article.publisher}
            </span>
          )}
          <span aria-hidden>·</span>
          <PublishedTime iso={article.published_at} />
          <span aria-hidden>·</span>
          <span>{story.article_count} article{story.article_count === 1 ? "" : "s"}</span>
          {primaryEntity && (
            <span className="ml-auto shrink-0">
              <WatchlistToggle
                entityId={primaryEntity.id}
                entityName={primaryEntity.canonical_name}
              />
            </span>
          )}
        </div>

        {/* Article body preview — natural height, scrolls if long */}
        <div className="overflow-y-auto max-h-[8rem]">
          <p className="text-sm text-muted-foreground leading-relaxed">
            {bodyText}
          </p>
        </div>

        {/* Engagement row — pinned to bottom */}
        <div className="mt-auto shrink-0 border-t border-border/40 pt-1.5 pb-3">
          <EngagementRow
            onSave={() => saved ? unsaveStory(story.id) : saveStory(story)}
            isSaved={saved}
            articleUrl={article.url}
            headline={article.headline}
          />
        </div>
      </div>
    </div>
  );
}
