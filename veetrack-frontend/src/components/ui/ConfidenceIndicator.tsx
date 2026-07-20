import { cn } from "@/lib/utils";

interface ConfidenceIndicatorProps {
  score: number;
  /** When true, renders in muted/pending style regardless of score. */
  muted?: boolean;
  className?: string;
}

const SEGMENTS = 5;
const HIGH_THRESHOLD = 0.8;
const REVIEW_THRESHOLD = 0.6;

function segmentColor(score: number, muted: boolean): string {
  if (muted) return "bg-muted-foreground/20";
  if (score >= HIGH_THRESHOLD) return "bg-risk-low";
  if (score >= REVIEW_THRESHOLD) return "bg-risk-medium";
  return "bg-risk-critical";
}

function confidenceLabel(score: number, muted: boolean): string {
  if (muted) return "Pending review";
  const pct = Math.round(score * 100);
  if (score >= HIGH_THRESHOLD) return `High confidence · ${pct}%`;
  if (score >= REVIEW_THRESHOLD) return `Moderate confidence · ${pct}%`;
  return `Low confidence · ${pct}%`;
}

/**
 * ConfidenceIndicator — 5-segment confidence meter.
 *
 * Below-threshold items render in a clearly muted style when `muted` is true,
 * so they are visually distinct from confident recommendations.
 */
export default function ConfidenceIndicator({
  score,
  muted = false,
  className,
}: ConfidenceIndicatorProps) {
  const filled = Math.round(score * SEGMENTS);
  const color = segmentColor(score, muted);
  const label = confidenceLabel(score, muted);
  const pct = Math.round(score * 100);

  return (
    <div
      className={cn("space-y-1", className)}
      aria-label={`Confidence: ${label}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Confidence</span>
        <span
          className={cn(
            "text-xs tabular-nums font-medium",
            muted ? "text-muted-foreground/50" : "text-foreground",
          )}
        >
          {pct}%
        </span>
      </div>
      <div
        className="flex gap-1"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <div
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              i < filled ? color : "bg-muted",
            )}
          />
        ))}
      </div>
    </div>
  );
}
