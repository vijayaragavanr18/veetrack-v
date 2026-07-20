"use client";

import { useEffect } from "react";
import { useFeedStore } from "@/store/feedStore";

export function useKeyboardNav(totalStories: number) {
  const { nextStory, prevStory, nextPage, prevPage } = useFeedStore();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          nextStory(totalStories);
          break;
        case "ArrowUp":
          e.preventDefault();
          prevStory();
          break;
        case "ArrowRight":
          e.preventDefault();
          nextPage();
          break;
        case "ArrowLeft":
          e.preventDefault();
          prevPage();
          break;
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [nextStory, prevStory, nextPage, prevPage, totalStories]);
}
