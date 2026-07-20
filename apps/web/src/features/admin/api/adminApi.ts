/**
 * Admin API client — /api/v1/admin/dashboard + review queue.
 */

import { apiFetch } from "@/features/auth/api/authApi";

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface SourceSnapshot {
  id: string;
  type: string;
  is_active: boolean;
  calls_made_this_window: number;
  quota_limit: number;
  circuit_open: boolean;
  usage_pct: number;
}

export interface QueueDepths {
  ingestion: number;
  nlp: number;
  llm: number;
  alerts: number;
}

export interface DashboardData {
  generated_at: string;
  sources: SourceSnapshot[];
  queue_depths: QueueDepths;
  pending_review_count: number;
  errors_last_hour: number;
}

export async function apiGetDashboard(
  accessToken: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<DashboardData> {
  return apiFetch<DashboardData>(
    "/api/v1/admin/dashboard",
    accessToken,
    {},
    onTokenRefreshed,
  );
}

// ---------------------------------------------------------------------------
// Review queue
// ---------------------------------------------------------------------------

export interface PendingRecommendation {
  id: string;
  story_id: string;
  audience: string;
  recommendation_text: string;
  risk_level: string;
  confidence_score: number;
  generated_at: string;
}

export interface ReviewActionResponse {
  id: string;
  action: string;
  audit_log_id: string;
}

export async function apiListPendingReview(
  accessToken: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<PendingRecommendation[]> {
  return apiFetch<PendingRecommendation[]>(
    "/api/v1/admin/recommendations/pending-review",
    accessToken,
    {},
    onTokenRefreshed,
  );
}

export async function apiApproveRecommendation(
  accessToken: string,
  recId: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<ReviewActionResponse> {
  return apiFetch<ReviewActionResponse>(
    `/api/v1/admin/recommendations/${recId}/approve`,
    accessToken,
    { method: "POST" },
    onTokenRefreshed,
  );
}

export async function apiRejectRecommendation(
  accessToken: string,
  recId: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<ReviewActionResponse> {
  return apiFetch<ReviewActionResponse>(
    `/api/v1/admin/recommendations/${recId}/reject`,
    accessToken,
    { method: "POST" },
    onTokenRefreshed,
  );
}
