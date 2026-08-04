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
    <div className="flex flex-col h-full bg-card">
      {/* Header — Executive Brief Title */}
      <header className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/50 shrink-0 bg-secondary/20">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
          <h2 className="text-sm font-bold tracking-wider uppercase text-foreground">
            Executive AI Brief
          </h2>
        </div>
        <SentimentBadge label={story.sentiment_label} className="text-xs" />
      </header>

      {/* Body — Rich scrollable executive layout */}
      {pending ? (
        <PendingInsightState />
      ) : (
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-0">
          {/* Key Facts / What Happened Card */}
          <section className="rounded-xl border border-primary/20 bg-gradient-to-br from-primary/5 via-card to-card p-4 space-y-2 shadow-sm">
            <div className="flex items-center gap-2 text-primary">
              <span className="text-xs font-bold uppercase tracking-widest">
                What Happened
              </span>
            </div>
            <p className="text-sm leading-relaxed text-foreground font-medium">
              {insight.what_happened}
            </p>
          </section>

          {/* Strategic Context / Why It Happened Card */}
          <section className="rounded-xl border border-border bg-card p-4 space-y-2 shadow-sm">
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="text-xs font-bold uppercase tracking-widest text-primary">
                Why It Matters & Strategic Impact
              </span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {insight.why_happened}
            </p>
          </section>

          {/* Key Takeaways Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-border/80 bg-secondary/30 p-3 space-y-1">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                Risk Level
              </span>
              <p className="text-xs font-bold capitalize text-foreground flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${story.risk_level === 'high' || story.risk_level === 'critical' ? 'bg-destructive' : 'bg-emerald-500'}`} />
                {story.risk_level} Priority
              </p>
            </div>
            <div className="rounded-lg border border-border/80 bg-secondary/30 p-3 space-y-1">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                Media Coverage
              </span>
              <p className="text-xs font-bold text-foreground">
                {story.article_count} Major Outlets
              </p>
            </div>
          </div>

          {/* Aggregate Sentiment Meter Card */}
          <section className="rounded-xl border border-border bg-card px-4 py-3 space-y-2 shadow-sm">
            <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
              Public & Press Sentiment Spectrum
            </p>
            <SentimentBar score={story.sentiment_score} />
          </section>

          {/* Attribution Footer */}
          <div className="pt-2 pb-1">
            <InsightMeta
              modelUsed={insight.model_used}
              generatedAt={insight.generated_at}
              className="justify-center"
            />
          </div>
        </div>
      )}
    </div>
  );
}
