/**
 * Unit tests for useWatchlistStore Zustand actions.
 */

import { useWatchlistStore } from "@/features/watchlists/store/useWatchlistStore";
import type { WatchlistItem } from "@/features/watchlists/api/watchlistsApi";

const item = (id: string, entityId: string): WatchlistItem => ({
  id,
  workspace_id: "ws1",
  user_id: "u1",
  entity_id: entityId,
  alert_channels: { websocket: true },
});

beforeEach(() => {
  useWatchlistStore.setState({ watchlists: [], watchedEntityIds: new Set() });
});

describe("useWatchlistStore — setWatchlists", () => {
  it("replaces all watchlists", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1"), item("w2", "e2")]);
    expect(useWatchlistStore.getState().watchlists).toHaveLength(2);
  });

  it("derives watchedEntityIds from the new list", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1"), item("w2", "e2")]);
    expect(useWatchlistStore.getState().watchedEntityIds.has("e1")).toBe(true);
    expect(useWatchlistStore.getState().watchedEntityIds.has("e2")).toBe(true);
  });

  it("clears watchedEntityIds when set to empty", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1")]);
    useWatchlistStore.getState().setWatchlists([]);
    expect(useWatchlistStore.getState().watchedEntityIds.size).toBe(0);
  });
});

describe("useWatchlistStore — addWatchlist", () => {
  it("appends the new item", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1")]);
    useWatchlistStore.getState().addWatchlist(item("w2", "e2"));
    expect(useWatchlistStore.getState().watchlists).toHaveLength(2);
  });

  it("adds entity_id to watchedEntityIds", () => {
    useWatchlistStore.getState().addWatchlist(item("w1", "e1"));
    expect(useWatchlistStore.getState().isWatched("e1")).toBe(true);
  });
});

describe("useWatchlistStore — removeWatchlist", () => {
  it("removes by id", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1"), item("w2", "e2")]);
    useWatchlistStore.getState().removeWatchlist("w1");
    expect(useWatchlistStore.getState().watchlists).toHaveLength(1);
    expect(useWatchlistStore.getState().watchlists[0].id).toBe("w2");
  });

  it("removes entity from watchedEntityIds", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1")]);
    useWatchlistStore.getState().removeWatchlist("w1");
    expect(useWatchlistStore.getState().isWatched("e1")).toBe(false);
  });

  it("no-op when id not found", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1")]);
    useWatchlistStore.getState().removeWatchlist("nonexistent");
    expect(useWatchlistStore.getState().watchlists).toHaveLength(1);
  });
});

describe("useWatchlistStore — isWatched", () => {
  it("returns true for a watched entity", () => {
    useWatchlistStore.getState().setWatchlists([item("w1", "e1")]);
    expect(useWatchlistStore.getState().isWatched("e1")).toBe(true);
  });

  it("returns false for an unwatched entity", () => {
    expect(useWatchlistStore.getState().isWatched("e-unknown")).toBe(false);
  });
});
