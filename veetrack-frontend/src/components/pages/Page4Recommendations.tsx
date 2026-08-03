"use client";

import { useState } from "react";
import { Lightbulb, Layers, AlertCircle, Eye } from "lucide-react";
import type { MockStory, MockRecommendation, RecommendationAudience } from "@/types";
import type { UserRole } from "@/types/shared";
import { useAuthStore } from "@/store/authStore";
import RiskBadge from "@/components/ui/RiskBadge";
import ConfidenceIndicator from "@/components/ui/ConfidenceIndicator";

interface Props {
  story: MockStory;
}

const AUDIENCE_LABEL: Record<RecommendationAudience, string> = {
  pr: "PR Team",
  exec: "Executive",
  marketing: "Marketing",
};

/** Roles that may toggle pending-review items into view. */
const ELEVATED_ROLES = new Set<UserRole>(["owner", "admin", "analyst"]);

/**
 * Viewer role sees only confident recommendations, no toggle.
 * All other roles (including unauthenticated — can't reach this page without
 * auth in production; JWT auth is Phase 6) can see the review toggle.
 */
function canSeeReviewToggle(role: string | undefined): boolean {
  if (role === "viewer") return false;
  // unauthenticated (null/undefined) defaults to elevated so the UI keeps
  // working during local development without a running auth service.
  return role === undefined || ELEVATED_ROLES.has(role as UserRole);
}

function EmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center h-full gap-4 px-8 text-center"
      data-testid="empty-state"
    >
      <Layers className="h-10 w-10 text-muted-foreground/30" aria-hidden />
      <div className="space-y-1.5">
        <p className="text-sm font-semibold text-foreground">
          No recommendations generated yet
        </p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Suggested actions will appear here once the analysis pipeline completes for this story.
        </p>
      </div>
    </div>
  );
}

interface RecCardProps {
  rec: MockRecommendation;
  isPendingReview: boolean;
}

function RecCard({ rec, isPendingReview }: RecCardProps) {
  const audience = AUDIENCE_LABEL[rec.audience as RecommendationAudience] ?? rec.audience;

  return (
    <article
      className={
        isPendingReview
          ? "rounded-lg border border-dashed border-risk-medium/30 bg-risk-medium/5 p-4 space-y-3"
          : "rounded-lg border border-border bg-card p-4 space-y-3"
      }
      aria-label={`${audience} recommendation${isPendingReview ? " (needs review)" : ""}`}
    >
      {/* Header row: audience + risk + review badge */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground border border-border">
          {audience}
        </span>
        <RiskBadge level={rec.risk_level} />
        {isPendingReview && (
          <span
            className="ml-auto inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full text-risk-medium bg-risk-medium/15 border border-risk-medium/30"
            aria-label="Needs human review before acting"
          >
            <AlertCircle className="h-3 w-3 shrink-0" aria-hidden />
            Needs Review
          </span>
        )}
      </div>

      {/* Recommendation text — framed as advisory */}
      <p
        className={
          isPendingReview
            ? "text-sm leading-relaxed text-muted-foreground"
            : "text-sm leading-relaxed text-foreground"
        }
      >
        {rec.recommendation_text}
      </p>

      {/* Confidence meter */}
      <ConfidenceIndicator score={rec.confidence_score} muted={isPendingReview} />

      {/* Review warning */}
      {isPendingReview && (
        <p className="text-xs text-risk-medium/80 flex items-start gap-1.5">
          <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span>
            Below confidence threshold — human review required before acting on this suggestion.
          </span>
        </p>
      )}
    </article>
  );
}

export default function Page4Recommendations({ story }: Props) {
  const user = useAuthStore((s) => s.user);
  const userRole = user?.role;
  const showToggle = canSeeReviewToggle(userRole);

  // Default open when unauthenticated (dev/local) so the UI isn't empty.
  // Authenticated elevated roles start with it closed — they click to expand.
  const [showPendingReview, setShowPendingReview] = useState(!userRole);

  const confident = story.recommendations.filter((r) => !r.needs_human_review);
  const pendingReview = story.recommendations.filter((r) => r.needs_human_review);

  const visiblePending = showToggle && showPendingReview ? pendingReview : [];

  if (story.recommendations.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <header className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-border/50 shrink-0">
          <Lightbulb className="h-4 w-4 text-primary shrink-0" aria-hidden />
          <h2 className="text-lg font-semibold leading-none">Recommendations</h2>
        </header>
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-border/50 shrink-0">
        <Lightbulb className="h-4 w-4 text-primary shrink-0" aria-hidden />
        <h2 className="text-lg font-semibold leading-none">Recommendations</h2>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {confident.length} suggested
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-3 space-y-4 min-h-0">
        {/* Confident recommendations */}
        {confident.map((rec) => (
          <RecCard key={rec.id} rec={rec} isPendingReview={false} />
        ))}

        {/* Pending-review section — elevated roles only */}
        {showToggle && pendingReview.length > 0 && (
          <div className="space-y-3">
            <button
              onClick={() => setShowPendingReview((v) => !v)}
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
              aria-expanded={showPendingReview}
              aria-controls="pending-review-list"
            >
              <Eye className="h-3.5 w-3.5" aria-hidden />
              <span>
                {showPendingReview ? "Hide" : "Show"} {pendingReview.length} pending-review
                suggestion{pendingReview.length === 1 ? "" : "s"}
              </span>
              <span className="ml-auto text-muted-foreground/50" aria-hidden>
                {showPendingReview ? "↑" : "↓"}
              </span>
            </button>

            <div id="pending-review-list" aria-live="polite">
              {visiblePending.map((rec) => (
                <div key={rec.id} className="mb-3">
                  <RecCard rec={rec} isPendingReview />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Advisory disclaimer */}
        <p className="text-xs text-muted-foreground/60 text-center pt-1 pb-0">
          AI-generated suggestions — advisory only. Verify before acting.
        </p>
      </div>
    </div>
  );
}
