/**
 * Watchlists API client — /api/v1/watchlists
 */

import { apiFetch } from "@/features/auth/api/authApi";

export interface WatchlistItem {
  id: string;
  workspace_id: string;
  user_id: string;
  entity_id: string;
  alert_channels: Record<string, boolean>;
}

export interface CreateWatchlistRequest {
  entity_id: string;
  alert_channels?: Record<string, boolean>;
}

export async function apiCreateWatchlist(
  accessToken: string,
  body: CreateWatchlistRequest,
  onTokenRefreshed?: (t: string) => void,
): Promise<WatchlistItem> {
  return apiFetch<WatchlistItem>(
    "/api/v1/watchlists",
    accessToken,
    { method: "POST", body: JSON.stringify(body) },
    onTokenRefreshed,
  );
}

export async function apiListWatchlists(
  accessToken: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<WatchlistItem[]> {
  return apiFetch<WatchlistItem[]>(
    "/api/v1/watchlists",
    accessToken,
    {},
    onTokenRefreshed,
  );
}

export async function apiDeleteWatchlist(
  accessToken: string,
  watchlistId: string,
  onTokenRefreshed?: (t: string) => void,
): Promise<void> {
  return apiFetch<void>(
    `/api/v1/watchlists/${watchlistId}`,
    accessToken,
    { method: "DELETE" },
    onTokenRefreshed,
  );
}
