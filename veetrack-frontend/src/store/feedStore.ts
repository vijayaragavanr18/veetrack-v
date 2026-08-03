"use client";

import { create } from "zustand";
import { devtools } from "zustand/middleware";

interface FeedState {
  currentStoryIndex: number;
  currentPage: 1 | 2 | 3 | 4;
  lastQuery: string;
  lastTime: string;
}

interface FeedActions {
  nextStory: (totalStories: number) => void;
  prevStory: () => void;
  nextPage: () => void;
  prevPage: () => void;
  goToPage: (page: 1 | 2 | 3 | 4) => void;
  goToStory: (index: number) => void;
  resetFeed: () => void;
  setLastQuery: (q: string) => void;
  setLastTime: (t: string) => void;
}

export const useFeedStore = create<FeedState & FeedActions>()(
  devtools(
    (set) => ({
      currentStoryIndex: 0,
      currentPage: 1,
      lastQuery: "",
      lastTime: "all",

      setLastQuery: (q: string) => set({ lastQuery: q }, false, "setLastQuery"),
      setLastTime: (t: string) => set({ lastTime: t }, false, "setLastTime"),

      nextStory: (total: number) =>
        set(
          (s) => ({
            currentStoryIndex: Math.min(s.currentStoryIndex + 1, total - 1),
            currentPage: 1,
          }),
          false,
          "nextStory"
        ),

      prevStory: () =>
        set(
          (s) => ({
            currentStoryIndex: Math.max(s.currentStoryIndex - 1, 0),
            currentPage: 1,
          }),
          false,
          "prevStory"
        ),

      nextPage: () =>
        set(
          (s) => ({
            currentPage: (Math.min(s.currentPage + 1, 4) as 1 | 2 | 3 | 4),
          }),
          false,
          "nextPage"
        ),

      prevPage: () =>
        set(
          (s) => ({
            currentPage: (Math.max(s.currentPage - 1, 1) as 1 | 2 | 3 | 4),
          }),
          false,
          "prevPage"
        ),

      goToPage: (page: 1 | 2 | 3 | 4) => set({ currentPage: page }, false, "goToPage"),

      goToStory: (index: number) =>
        set({ currentStoryIndex: index, currentPage: 1 }, false, "goToStory"),

      resetFeed: () =>
        set({ currentStoryIndex: 0, currentPage: 1 }, false, "resetFeed"),
    }),
    { name: "FeedStore" }
  )
);
