"use client";

import { useEffect, useRef } from "react";
import { Bell, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AlertPayload } from "@/features/watchlists/hooks/useAlertSocket";
import type { RiskLevel } from "@/types";

interface AlertToastProps {
  alert: AlertPayload;
  onDismiss: () => void;
  /** Auto-dismiss after this many ms. Default 8000. */
  autoDismissMs?: number;
}

const RISK_COLORS: Record<string, string> = {
  low: "border-risk-low/40 bg-risk-low/10 text-risk-low",
  medium: "border-risk-medium/40 bg-risk-medium/10 text-risk-medium",
  high: "border-risk-high/40 bg-risk-high/10 text-risk-high",
  critical: "border-risk-critical/40 bg-risk-critical/10 text-risk-critical",
};

export default function AlertToast({
  alert,
  onDismiss,
  autoDismissMs = 8000,
}: AlertToastProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    timerRef.current = setTimeout(onDismiss, autoDismissMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [onDismiss, autoDismissMs]);

  const riskKey = (alert.risk_level as RiskLevel) ?? "medium";
  const colorClass = RISK_COLORS[riskKey] ?? RISK_COLORS.medium;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg",
        "max-w-sm w-full pointer-events-auto",
        colorClass,
      )}
    >
      <Bell className="h-4 w-4 mt-0.5 shrink-0" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide">
          {riskKey} risk alert
        </p>
        <p className="text-sm mt-0.5 leading-snug line-clamp-2">
          {alert.story_title}
        </p>
      </div>
      <button
        onClick={onDismiss}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
        aria-label="Dismiss alert"
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
