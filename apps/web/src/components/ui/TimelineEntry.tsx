"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { MockArticle } from "@/types";
import SourceIcon from "@/components/ui/SourceIcon";
import SentimentBadge from "@/components/ui/SentimentBadge";
import PublishedTime from "@/components/ui/PublishedTime";

interface TimelineEntryProps {
  article: MockArticle;
  isFirst: boolean;
  isLast: boolean;
}

/** Sentiment score normalised to 0–100 for the mini bar. */
function scoreToPercent(score: number): number {
  return Math.round(((score + 1) / 2) * 100);
}

function MiniSentimentBar({ score }: { score: number }) {
  const pct = scoreToPercent(score);
  const color =
    score > 0.3
      ? "bg-risk-low"
      : score < -0.3
        ? "bg-risk-critical"
        : "bg-risk-medium";
  return (
    <div className="flex items-center gap-2" aria-label={`Sentiment score ${score.toFixed(2)}`}>
      <div className="relative flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground/70 shrink-0">
        {score > 0 ? "+" : ""}
        {score.toFixed(2)}
      </span>
    </div>
  );
}

/**
 * TimelineEntry — one row in the story-cluster timeline.
 *
 * Tap/click to expand a sentiment detail row.
 * The vertical connector line is drawn using CSS pseudo-elements on
 * the wrapper so adjacent entries form an unbroken line.
 */
export default function TimelineEntry({
  article,
  isFirst,
  isLast,
}: TimelineEntryProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="flex gap-3 group"
      style={{ contentVisibility: "auto", containIntrinsicSize: "0 76px" }}
    >
      {/* Timeline gutter: line + dot */}
      <div className="flex flex-col items-center shrink-0 w-4">
        {/* Top connector — hidden for first item */}
        <div
          className={cn(
            "w-px flex-none",
            isFirst ? "h-2 invisible" : "h-2 bg-border",
          )}
        />
        {/* Dot */}
        <div
          className={cn(
            "h-2.5 w-2.5 rounded-full border-2 shrink-0 z-10",
            isLast
              ? "border-primary bg-primary"
              : "border-primary/60 bg-background",
          )}
          aria-hidden
        />
        {/* Bottom connector — hidden for last item */}
        <div
          className={cn(
            "w-px flex-1",
            isLast ? "invisible" : "bg-border",
          )}
        />
      </div>

      {/* Content */}
      <button
        className={cn(
          "flex-1 min-w-0 text-left rounded-lg border border-border bg-card px-3 py-2.5 mb-2",
          "hover:border-primary/30 hover:bg-card/80 transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        )}
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        aria-label={`${article.headline} — tap to ${expanded ? "collapse" : "expand"} details`}
      >
        {/* Row 1: headline + sentiment badge */}
        <div className="flex items-start gap-2">
          <p className="text-sm font-medium leading-snug flex-1 line-clamp-2">
            {article.headline}
          </p>
          <SentimentBadge
            label={article.sentiment_label}
            className="text-[10px] shrink-0 mt-0.5"
          />
        </div>

        {/* Row 2: source icon + publisher + time + external link */}
        <div className="flex items-center gap-1.5 mt-1.5">
          <SourceIcon
            publisher={article.publisher}
            url=""
            className="h-5 w-5"
          />
          <span className="text-xs text-muted-foreground font-medium truncate">
            {article.publisher}
          </span>
          <span className="text-muted-foreground/40 text-xs" aria-hidden>·</span>
          <PublishedTime
            iso={article.published_at}
            className="text-xs text-muted-foreground/70 shrink-0"
          />
          {article.url && (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="ml-auto shrink-0 text-primary/60 hover:text-primary transition-colors"
              aria-label={`Open ${article.publisher} article in new tab`}
            >
              <svg
                className="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          )}
        </div>

        {/* Expanded: sentiment score bar */}
        {expanded && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <MiniSentimentBar score={article.sentiment_score} />
          </div>
        )}
      </button>
    </div>
  );
}
