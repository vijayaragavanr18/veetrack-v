"use client";

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { WatchlistItem } from "../api/watchlistsApi";

interface WatchlistState {
  watchlists: WatchlistItem[];
  /** entity_ids that are actively watched (derived from watchlists) */
  watchedEntityIds: Set<string>;
}

interface WatchlistActions {
  setWatchlists: (items: WatchlistItem[]) => void;
  addWatchlist: (item: WatchlistItem) => void;
  removeWatchlist: (id: string) => void;
  isWatched: (entityId: string) => boolean;
}

export const useWatchlistStore = create<WatchlistState & WatchlistActions>()(
  devtools(
    (set, get) => ({
      watchlists: [],
      watchedEntityIds: new Set(),

      setWatchlists: (items) =>
        set(
          {
            watchlists: items,
            watchedEntityIds: new Set(items.map((w) => w.entity_id)),
          },
          false,
          "setWatchlists",
        ),

      addWatchlist: (item) =>
        set(
          (s) => {
            const next = [...s.watchlists, item];
            return {
              watchlists: next,
              watchedEntityIds: new Set(next.map((w) => w.entity_id)),
            };
          },
          false,
          "addWatchlist",
        ),

      removeWatchlist: (id) =>
        set(
          (s) => {
            const next = s.watchlists.filter((w) => w.id !== id);
            return {
              watchlists: next,
              watchedEntityIds: new Set(next.map((w) => w.entity_id)),
            };
          },
          false,
          "removeWatchlist",
        ),

      isWatched: (entityId) => get().watchedEntityIds.has(entityId),
    }),
    { name: "WatchlistStore" },
  ),
);
