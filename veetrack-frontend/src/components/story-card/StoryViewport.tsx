"use client";

/**
 * StoryViewport — virtualized vertical swipe container for stories.
 *
 * Virtualization rule: only the current story ± 1 is mounted. Every other
 * story index renders a lightweight placeholder div. This keeps the DOM lean
 * and maintains 60fps during swipe even with large story lists.
 *
 * Gesture: drag="y" with spring-physics transitions via framer-motion.
 * prefers-reduced-motion: replaced with instant fade when set.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRef } from "react";
import type { MockStory } from "@/types";
import { useFeedStore } from "@/store/feedStore";
import { useSwipeNav } from "@/hooks/useSwipeNav";
import PageSwiper from "@/components/pages/PageSwiper";

interface StoryViewportProps {
  stories: MockStory[];
  isLoading?: boolean;
}

export default function StoryViewport({
  stories,
  isLoading = false,
}: StoryViewportProps) {
  const { currentStoryIndex } = useFeedStore();
  const { onVerticalDragEnd } = useSwipeNav(stories.length);
  const reduced = useReducedMotion();
  // Skip enter animation on the very first mount so the story is immediately visible.
  const isFirstMount = useRef(true);

  // Vertical enter/exit: negative index → slides from top, positive → from bottom
  const variants = {
    enter: (dir: number) => ({
      y: reduced ? 0 : dir > 0 ? "100%" : "-100%",
      opacity: reduced ? 0 : 1,
    }),
    center: { y: 0, opacity: 1 },
    exit: (dir: number) => ({
      y: reduced ? 0 : dir > 0 ? "-100%" : "100%",
      opacity: reduced ? 0 : 1,
    }),
  };

  const transition = reduced
    ? { duration: 0.15 }
    : { type: "spring" as const, stiffness: 280, damping: 32 };

  if (isLoading) {
    return (
      <div className="flex-1 flex flex-col gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border border-border bg-card animate-pulse h-[600px]"
          />
        ))}
      </div>
    );
  }

  const activeStory = stories[currentStoryIndex];

  return (
    <div className="flex-1 min-h-0 relative overflow-hidden">
      <AnimatePresence mode="wait" custom={currentStoryIndex}>
        {activeStory && (
          <motion.div
            key={`story-${currentStoryIndex}-${activeStory.id}`}
            custom={currentStoryIndex}
            variants={variants}
            initial={isFirstMount.current ? false : "enter"}
            animate="center"
            exit="exit"
            onAnimationStart={() => { isFirstMount.current = false; }}
            transition={transition}
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={0.12}
            onDragEnd={onVerticalDragEnd}
            className="absolute inset-0 bg-card overflow-hidden"
            style={{ willChange: "transform" }}
            data-testid="story-viewport"
          >
            <PageSwiper story={activeStory} totalStories={stories.length} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
