"use client";

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import type { MockStory } from "@/types";

interface SavedState {
  savedStories: MockStory[];
}

interface SavedActions {
  saveStory: (story: MockStory) => void;
  unsaveStory: (storyId: string) => void;
  isSaved: (storyId: string) => boolean;
}

export const useSavedStore = create<SavedState & SavedActions>()(
  devtools(
    persist(
      (set, get) => ({
        savedStories: [],

        saveStory: (story) =>
          set(
            (s) => {
              if (s.savedStories.some((x) => x.id === story.id)) return s;
              return { savedStories: [story, ...s.savedStories] };
            },
            false,
            "saveStory",
          ),

        unsaveStory: (storyId) =>
          set(
            (s) => ({ savedStories: s.savedStories.filter((x) => x.id !== storyId) }),
            false,
            "unsaveStory",
          ),

        isSaved: (storyId) => get().savedStories.some((x) => x.id === storyId),
      }),
      { name: "veetrack-saved-stories" },
    ),
    { name: "SavedStore" },
  ),
);
