"use client";

import type { MockStory } from "@/types";
import SentimentBadge from "@/components/ui/SentimentBadge";
import InsightMeta from "@/components/ui/InsightMeta";
import PendingInsightState from "@/components/ui/PendingInsightState";

interface Props {
  story: MockStory;
}

/** Sentinel set by adaptApiStory when the API returns insight: null. */
const PENDING_SENTINEL = "—";

function isPending(story: MockStory): boolean {
  return story.insight.model_used === PENDING_SENTINEL;
}

/** Normalised score → CSS width percentage. Score is -1..+1. */
function scoreToPercent(score: number): number {
  return Math.round(((score + 1) / 2) * 100);
}

function SentimentBar({ score }: { score: number }) {
  const pct = scoreToPercent(score);
  const color =
    score > 0.3
      ? "bg-risk-low"
      : score < -0.3
        ? "bg-risk-critical"
        : "bg-risk-medium";

  return (
    <div className="space-y-1" aria-label={`Sentiment score: ${score.toFixed(2)}`}>
      <div className="flex justify-between text-xs text-muted-foreground/70" aria-hidden>
        <span>Negative</span>
        <span>Positive</span>
      </div>
      <div className="relative h-2 rounded-full bg-muted overflow-hidden">
        <div className="absolute h-full w-px bg-border left-1/2 -translate-x-1/2" aria-hidden />
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-center text-muted-foreground/70">
        {score > 0 ? "+" : ""}
        {score.toFixed(2)}
      </p>
    </div>
  );
}

export default function Page2Insight({ story }: Props) {
  const { insight } = story;
  const pending = isPending(story);

  return (
    <div className="flex flex-col h-full">
      {/* Header — always visible even during pending */}
      <header className="flex items-center gap-2 px-5 pt-5 pb-4 border-b border-border/50 shrink-0">
        <h2 className="text-lg font-semibold leading-none">AI Insight</h2>
        <span className="ml-auto">
          <SentimentBadge label={story.sentiment_label} className="text-xs" />
        </span>
      </header>

      {/* Body — pending or real content */}
      {pending ? (
        <PendingInsightState />
      ) : (
        <div className="flex flex-col gap-5 px-5 py-3 overflow-y-auto flex-1 min-h-0">
          {/* What Happened */}
          <section aria-labelledby="what-heading">
            <h3
              id="what-heading"
              className="text-xs font-semibold text-primary uppercase tracking-widest mb-2"
            >
              What Happened
            </h3>
            <p className="text-sm leading-relaxed text-foreground">
              {insight.what_happened}
            </p>
          </section>

          {/* Why It Happened */}
          <section aria-labelledby="why-heading">
            <h3
              id="why-heading"
              className="text-xs font-semibold text-primary uppercase tracking-widest mb-2"
            >
              Why It Happened
            </h3>
            <p className="text-sm leading-relaxed text-foreground">
              {insight.why_happened}
            </p>
          </section>

          {/* Aggregate Sentiment card */}
          <section
            className="rounded-lg border border-border bg-card px-4 py-3 space-y-3"
            aria-label="Aggregate sentiment"
          >
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
              Aggregate Sentiment
            </p>
            <SentimentBar score={story.sentiment_score} />
          </section>

          {/* Attribution footer */}
          <InsightMeta
            modelUsed={insight.model_used}
            generatedAt={insight.generated_at}
            className="mt-auto pt-1 pb-0 justify-center"
          />
        </div>
      )}
    </div>
  );
}
