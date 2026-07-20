"use client";

/**
 * PageSwiper — horizontal swipe between the four story pages.
 *
 * Uses framer-motion drag="x" for gesture detection and AnimatePresence for
 * spring-physics enter/exit. The actual page content is rendered by the
 * Page1–4 components and passed in as children.
 *
 * respects `prefers-reduced-motion`: replaces spring transitions with
 * an instant fade so users who opt out aren't affected.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRef } from "react";
import type { MockStory } from "@/types";
import { useFeedStore } from "@/store/feedStore";
import { useSwipeNav } from "@/hooks/useSwipeNav";
import Page1Original from "@/components/pages/Page1Original";
import Page2Insight from "@/components/pages/Page2Insight";
import Page3Cluster from "@/components/pages/Page3Cluster";
import Page4Recommendations from "@/components/pages/Page4Recommendations";

interface PageSwiperProps {
  story: MockStory;
  totalStories: number;
}

const PAGE_LABELS: Record<number, string> = {
  1: "Original",
  2: "Insight",
  3: "Cluster",
  4: "Actions",
};

export default function PageSwiper({ story, totalStories }: PageSwiperProps) {
  const { currentPage, goToPage } = useFeedStore();
  const { onHorizontalDragEnd } = useSwipeNav(totalStories);
  const reduced = useReducedMotion();
  const isFirstMount = useRef(true);

  // Direction: +1 if moving to a higher page (slides in from right), -1 from left.
  // We encode direction in the key using a sentinel — positive page numbers already
  // provide left→right ordering, so framer-motion can infer from key changes.
  const variants = {
    enter: (dir: number) => ({
      x: reduced ? 0 : dir > 0 ? "100%" : "-100%",
      opacity: reduced ? 0 : 1,
    }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({
      x: reduced ? 0 : dir > 0 ? "-100%" : "100%",
      opacity: reduced ? 0 : 1,
    }),
  };

  const transition = reduced
    ? { duration: 0.15 }
    : { type: "spring" as const, stiffness: 300, damping: 30 };

  return (
    <div className="flex flex-col h-full">
      {/* Page indicator dots */}
      <div
        className="flex justify-center gap-2 py-2"
        role="tablist"
        aria-label="Story pages"
      >
        {([1, 2, 3, 4] as const).map((page) => (
          <button
            key={page}
            role="tab"
            aria-selected={currentPage === page}
            aria-label={PAGE_LABELS[page]}
            onClick={() => goToPage(page)}
            className={`h-2 rounded-full transition-all duration-200 ${
              currentPage === page
                ? "w-6 bg-primary"
                : "w-2 bg-muted-foreground/40 hover:bg-muted-foreground/70"
            }`}
          />
        ))}
      </div>

      {/* Swipeable page content */}
      <div className="flex-1 overflow-hidden relative">
        <AnimatePresence mode="wait" custom={currentPage}>
          <motion.div
            key={`${story.id}-page-${currentPage}`}
            custom={currentPage}
            variants={variants}
            initial={isFirstMount.current ? false : "enter"}
            animate="center"
            exit="exit"
            transition={transition}
            onAnimationStart={() => { isFirstMount.current = false; }}
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.15}
            onDragEnd={onHorizontalDragEnd}
            className="absolute inset-0 overflow-y-auto"
            style={{ willChange: "transform" }}
          >
            {currentPage === 1 && <Page1Original story={story} />}
            {currentPage === 2 && <Page2Insight story={story} />}
            {currentPage === 3 && <Page3Cluster story={story} />}
            {currentPage === 4 && <Page4Recommendations story={story} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
