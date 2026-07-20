import { TrendingUp, TrendingDown, Minus, ArrowLeftRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SentimentLabel } from "@/types";

interface SentimentBadgeProps {
  label: SentimentLabel;
  className?: string;
}

const CONFIG: Record<
  SentimentLabel,
  {
    Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
    colorClass: string;
    text: string;
  }
> = {
  positive: {
    Icon: TrendingUp,
    colorClass:
      "text-risk-low bg-risk-low/15 border border-risk-low/30",
    text: "Positive",
  },
  negative: {
    Icon: TrendingDown,
    colorClass:
      "text-risk-critical bg-risk-critical/15 border border-risk-critical/30",
    text: "Negative",
  },
  neutral: {
    Icon: Minus,
    colorClass:
      "text-muted-foreground bg-secondary border border-border",
    text: "Neutral",
  },
  mixed: {
    Icon: ArrowLeftRight,
    colorClass:
      "text-risk-medium bg-risk-medium/15 border border-risk-medium/30",
    text: "Mixed",
  },
};

/**
 * SentimentBadge — color-coded AND icon-coded badge for sentiment values.
 *
 * Non-color-only: each sentiment has a distinct icon so the meaning is
 * accessible to users with color vision deficiency.
 */
export default function SentimentBadge({
  label,
  className,
}: SentimentBadgeProps) {
  const { Icon, colorClass, text } = CONFIG[label] ?? CONFIG.neutral;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        colorClass,
        className,
      )}
      aria-label={`Sentiment: ${text}`}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      <span>{text}</span>
    </span>
  );
}
