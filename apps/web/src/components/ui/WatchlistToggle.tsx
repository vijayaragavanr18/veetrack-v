"use client";

import { useState } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import { useWatchlistStore } from "@/features/watchlists/store/useWatchlistStore";
import {
  apiCreateWatchlist,
  apiDeleteWatchlist,
} from "@/features/watchlists/api/watchlistsApi";

interface WatchlistToggleProps {
  entityId: string;
  entityName: string;
  className?: string;
}

/**
 * WatchlistToggle — bell icon button that adds/removes an entity from the
 * user's watchlist. Only renders for authenticated users with analyst+ role.
 */
export default function WatchlistToggle({
  entityId,
  entityName,
  className,
}: WatchlistToggleProps) {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const setToken = useAuthStore((s) => s.setToken);
  const { watchlists, isWatched, addWatchlist, removeWatchlist } =
    useWatchlistStore();

  const [loading, setLoading] = useState(false);

  // Only analyst+ can watch entities
  const canWatch =
    user &&
    accessToken &&
    ["analyst", "admin", "owner"].includes(user.role);

  if (!canWatch) return null;

  const watched = isWatched(entityId);
  const watchlistEntry = watchlists.find((w) => w.entity_id === entityId);

  async function handleToggle() {
    if (!accessToken) return;
    setLoading(true);
    try {
      if (watched && watchlistEntry) {
        await apiDeleteWatchlist(accessToken, watchlistEntry.id, setToken);
        removeWatchlist(watchlistEntry.id);
      } else {
        const created = await apiCreateWatchlist(
          accessToken,
          { entity_id: entityId, alert_channels: { websocket: true } },
          setToken,
        );
        addWatchlist(created);
      }
    } catch {
      // errors are surfaced via the API error pattern; no extra toast needed here
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleToggle}
      disabled={loading}
      aria-label={
        watched
          ? `Unwatch ${entityName}`
          : `Watch ${entityName} for alerts`
      }
      aria-pressed={watched}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
        watched
          ? "bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25"
          : "bg-muted text-muted-foreground border border-border hover:bg-muted/80",
        loading && "opacity-50 cursor-wait",
        className,
      )}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      ) : watched ? (
        <Bell className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <BellOff className="h-3.5 w-3.5" aria-hidden />
      )}
      {watched ? "Watching" : "Watch"}
    </button>
  );
}
