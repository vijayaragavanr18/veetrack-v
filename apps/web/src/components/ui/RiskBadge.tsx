import { CheckCircle2, AlertTriangle, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RiskLevel } from "@/types";

interface RiskBadgeProps {
  level: RiskLevel;
  className?: string;
}

const CONFIG: Record<
  RiskLevel,
  {
    Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
    colorClass: string;
    text: string;
  }
> = {
  low: {
    Icon: CheckCircle2,
    colorClass: "text-risk-low bg-risk-low/15 border border-risk-low/30",
    text: "LOW",
  },
  medium: {
    Icon: AlertTriangle,
    colorClass: "text-risk-medium bg-risk-medium/15 border border-risk-medium/30",
    text: "MEDIUM",
  },
  high: {
    Icon: AlertTriangle,
    colorClass: "text-risk-high bg-risk-high/15 border border-risk-high/30",
    text: "HIGH",
  },
  critical: {
    Icon: ShieldAlert,
    colorClass: "text-risk-critical bg-risk-critical/15 border border-risk-critical/30",
    text: "CRITICAL",
  },
};

/**
 * RiskBadge — color-coded AND icon-coded badge for risk levels.
 * Mirrors the SentimentBadge pattern: non-color-only signaling.
 */
export default function RiskBadge({ level, className }: RiskBadgeProps) {
  const { Icon, colorClass, text } = CONFIG[level] ?? CONFIG.medium;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        colorClass,
        className,
      )}
      aria-label={`Risk level: ${text}`}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      <span>{text}</span>
    </span>
  );
}
