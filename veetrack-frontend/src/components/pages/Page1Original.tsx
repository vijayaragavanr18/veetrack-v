"use client";

import { useState } from "react";
import Image from "next/image";
import { ExternalLink } from "lucide-react";
import type { MockStory } from "@/types";
import { Badge } from "@/components/ui/badge";
import PublishedTime from "@/components/ui/PublishedTime";
import WatchlistToggle from "@/components/ui/WatchlistToggle";
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
      {/* ── Hero image — Exactly 50% of the screen height if it exists ─────────────────────── */}
      {showImage && (
        <div 
          className="relative w-full h-[50%] shrink-0" 
          style={{ transform: "translateZ(0)", WebkitTransform: "translateZ(0)", willChange: "transform" }}
        >
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
          {/* Scrim gradient over image */}
          <div
            className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-card via-card/50 to-transparent"
            aria-hidden
          />
        </div>
      )}

      {/* ── Absolute Tags (Always Visible at Top) ─────────────────────── */}
      {article.url && (
        <div className="absolute top-10 left-3 z-10">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 bg-background/80 backdrop-blur-sm rounded-full px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-background/95 transition-colors border border-border/30 shadow-sm"
            aria-label={`Read full article on ${article.publisher || "source"}`}
          >
            <ExternalLink className="h-2.5 w-2.5 shrink-0" aria-hidden />
            {article.publisher || "Source"}
          </a>
        </div>
      )}

      {/* Category tag — bottom left of hero if image */}
      <div className={`absolute ${showImage ? "top-[calc(50%-14px)]" : "top-20"} left-0 z-10`}>
        <div className="bg-red-600 text-white text-[11px] font-bold uppercase tracking-widest px-3 py-1.5 flex items-center gap-1 shadow-md">
           <span className="opacity-70">#</span> {entityLabel}
        </div>
      </div>

      {/* Risk badge — top-right */}
      <div className="absolute top-10 right-3 z-10">
        <Badge variant={riskVariant[story.risk_level] ?? "low"} className="text-[10px] font-semibold shadow-sm">
          {story.risk_level.toUpperCase()} RISK
        </Badge>
      </div>

      {/* ── Content area ──────────────────────────────────────────────── */}
      <div className={`flex flex-col flex-1 px-4 ${showImage ? "pt-4" : "pt-32"} pb-2 min-h-0`}>
        {/* Text fills space from top */}
        <div className="flex-1 flex flex-col gap-3 overflow-y-auto min-h-0">
          {/* Headline */}
          <h1 className="text-[28px] sm:text-[32px] font-extrabold leading-[1.15] text-foreground tracking-tight font-serif mt-1" style={{ fontFamily: "'Playfair Display', 'Merriweather', Georgia, serif" }}>
            {article.headline}
          </h1>

          {/* Source row */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground/80 flex-wrap shrink-0 mt-1 uppercase tracking-wider">
            {article.publisher && (
              <span className="font-semibold truncate max-w-[140px]">
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

          {/* Article body preview */}
          <p className="text-[17px] text-muted-foreground/90 leading-[1.65] mt-2 font-serif" style={{ fontFamily: "'Merriweather', Georgia, serif" }}>
            {bodyText}
          </p>


        </div>

        {/* Engagement row — pinned to absolute bottom */}
        <div className="shrink-0 border-t border-border/40 pt-3 mt-auto">
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
