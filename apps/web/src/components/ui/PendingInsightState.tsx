"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";

interface PendingInsightStateProps {
  /** Poll interval in ms — defaults to 20 000 (20 s). */
  pollInterval?: number;
}

const DEFAULT_INTERVAL = 20_000;

/**
 * PendingInsightState — shown while the AI executive brief is being generated.
 *
 * Polls the feed query at a reasonable interval so the view auto-updates once
 * the insight arrives, without hammering the API.
 *
 * Design rule: the copy is honest about AI processing time. No fake progress
 * bars or indefinite spinners — the spinner stops and the real content replaces
 * this component as soon as the parent re-renders with real data.
 */
export default function PendingInsightState({
  pollInterval = DEFAULT_INTERVAL,
}: PendingInsightStateProps) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const id = setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["feed"] });
    }, pollInterval);
    return () => clearInterval(id);
  }, [queryClient, pollInterval]);

  return (
    <div
      className="flex flex-col items-center justify-center gap-5 h-full px-8 text-center"
      role="status"
      aria-live="polite"
      aria-label="AI analysis in progress"
    >
      <div className="relative">
        <Sparkles
          className="h-10 w-10 text-primary/40"
          aria-hidden
        />
        <Loader2
          className="absolute -bottom-1 -right-1 h-4 w-4 text-primary animate-spin"
          aria-hidden
        />
      </div>

      <div className="space-y-2">
        <p className="text-base font-semibold text-foreground">
          Analysis in progress
        </p>
        <p className="text-sm text-muted-foreground max-w-xs">
          The AI executive brief is being generated. This usually takes a few
          seconds for new stories — the page will update automatically.
        </p>
      </div>
    </div>
  );
}
