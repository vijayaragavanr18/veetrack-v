"use client";

/**
 * FlipStoryViewer — top-level orchestrator for the half-bend flip UI.
 *
 * Wires together:
 *   - useFlipGesture: single pointer handler locking to vertical OR horizontal
 *   - VerticalFlipCard: story-to-story flip (rotateX around horizontal crease)
 *   - HorizontalFlipCard: page-to-page flip (rotateY around vertical edge)
 *   - feedStore: single source of truth for navigation state
 *
 * prefers-reduced-motion: falls back to instant swap (no 3D transforms).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useReducedMotion, useMotionValue } from "framer-motion";
import type { MockStory } from "@/types";
import { useFeedStore } from "@/store/feedStore";
import { useFlipGesture } from "./useFlipGesture";
import VerticalFlipCard from "./VerticalFlipCard";
import HorizontalFlipCard from "./HorizontalFlipCard";
import Page1Original from "@/components/pages/Page1Original";
import Page2Insight from "@/components/pages/Page2Insight";
import Page3Cluster from "@/components/pages/Page3Cluster";
import Page4Recommendations from "@/components/pages/Page4Recommendations";
import ArticleChatbot from "@/components/ai/ArticleChatbot";

interface FlipStoryViewerProps {
  stories: MockStory[];
  isLoading?: boolean;
  fetchNextPage?: () => void;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
}

function PageContent({ story, page }: { story: MockStory; page: 1 | 2 | 3 | 4 }) {
  if (page === 1) return <Page1Original story={story} />;
  if (page === 2) return <Page2Insight story={story} />;
  if (page === 3) return <Page3Cluster story={story} />;
  return <Page4Recommendations story={story} />;
}

function PageDots({
  currentPage,
  onPageClick,
}: {
  currentPage: 1 | 2 | 3 | 4;
  onPageClick: (p: 1 | 2 | 3 | 4) => void;
}) {
  const labels = ["Original", "Insight", "Cluster", "Actions"] as const;
  return (
    <div className="flex justify-center gap-2 py-2 shrink-0" role="tablist" aria-label="Story pages">
      {([1, 2, 3, 4] as const).map((p) => (
        <button
          key={p}
          role="tab"
          aria-selected={currentPage === p}
          aria-label={labels[p - 1]}
          onClick={() => onPageClick(p)}
          className={`h-2 rounded-full transition-all duration-200 ${
            currentPage === p
              ? "w-6 bg-primary"
              : "w-2 bg-muted-foreground/40 hover:bg-muted-foreground/70"
          }`}
        />
      ))}
    </div>
  );
}

export default function FlipStoryViewer({ 
  stories, 
  isLoading = false,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage
}: FlipStoryViewerProps) {
  const {
    currentStoryIndex, currentPage,
    nextStory, prevStory, nextPage, prevPage, goToPage,
  } = useFeedStore();

  const reduced = useReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  const [cardSize, setCardSize] = useState({ width: 600, height: 640 });

  // Idle MotionValue — always zero, used when no gesture is active
  const idleProgress = useMotionValue(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const e = entries[0];
      if (e) setCardSize({ width: e.contentRect.width, height: e.contentRect.height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Fetch next page when we are 3 stories away from the end
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && fetchNextPage) {
      if (stories.length - currentStoryIndex <= 3) {
        fetchNextPage();
      }
    }
  }, [currentStoryIndex, stories.length, hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Prefetch hero images for the next 3 stories
  useEffect(() => {
    if (typeof window === "undefined") return;
    const nextStories = stories.slice(currentStoryIndex + 1, currentStoryIndex + 4);
    nextStories.forEach(story => {
      const url = story.primary_article?.hero_image_url;
      if (url) {
        const img = new window.Image();
        img.src = url;
      }
    });
  }, [currentStoryIndex, stories]);

  const onStoryChange = useCallback(
    (delta: -1 | 1) => { if (delta === 1) nextStory(stories.length); else prevStory(); },
    [nextStory, prevStory, stories.length],
  );
  const onPageChange = useCallback(
    (delta: -1 | 1) => { if (delta === 1) nextPage(); else prevPage(); },
    [nextPage, prevPage],
  );

  const gesture = useFlipGesture({
    totalStories: stories.length,
    currentStoryIndex,
    totalPages: 4,
    currentPage,
    cardHeight: cardSize.height,
    cardWidth: cardSize.width,
    onStoryChange,
    onPageChange,
  });

  // ── Reduced motion check: 3D flip physics active ─────────────────────────────

  if (isLoading) {
    return <div className="flex-1 bg-card animate-pulse" />;
  }

  const story = stories[currentStoryIndex];
  if (!story) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 px-8 text-center">
        <p className="text-2xl">🔍</p>
        <p className="text-base font-medium text-foreground">No stories found</p>
        <p className="text-sm text-muted-foreground">Try searching for a different topic, company, or person.</p>
      </div>
    );
  }

  const dir = gesture.direction.current;
  const lockedAxis = gesture.axis.current;

  // Adjacent story (for vertical flip)
  const targetStory = stories[currentStoryIndex + dir] ?? null;

  // Adjacent page (for horizontal flip)
  const targetPageNum = (currentPage + dir) as 1 | 2 | 3 | 4;
  const targetPageValid = targetPageNum >= 1 && targetPageNum <= 4;

  // ── Page views ─────────────────────────────────────────────────────────────
  const currentPageContent = (
    <div className="absolute inset-0 overflow-y-auto bg-card" style={{ touchAction: "none" }}>
      <PageContent story={story} page={currentPage} />
    </div>
  );
  const targetPageContent = targetPageValid ? (
    <div className="absolute inset-0 overflow-y-auto bg-card" style={{ touchAction: "none" }}>
      <PageContent story={story} page={targetPageNum} />
    </div>
  ) : null;

  // ── Story slots ────────────────────────────────────────────────────────────
  // The "current" slot in the vertical flip contains the horizontal page flip
  const currentStorySlot = (
    <div className="absolute inset-0 bg-card">
      <div className="absolute inset-0 overflow-hidden">
        {lockedAxis === "horizontal" ? (
          <HorizontalFlipCard
            currentContent={currentPageContent}
            targetContent={targetPageContent}
            direction={dir}
            progress={gesture.progress}
          />
        ) : (
          currentPageContent
        )}
      </div>
      <div className="absolute top-0 inset-x-0 z-50 pointer-events-none">
        <div className="pointer-events-auto">
          <PageDots currentPage={currentPage} onPageClick={goToPage} />
        </div>
      </div>
    </div>
  );

  const targetStorySlot = targetStory ? (
    <div className="absolute inset-0 bg-card">
      <div className="absolute inset-0 overflow-y-auto">
        <PageContent story={targetStory} page={1} />
      </div>
      <div className="absolute top-0 inset-x-0 z-50 pointer-events-none">
        <div className="pointer-events-auto">
          <PageDots currentPage={1} onPageClick={goToPage} />
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="flex-1 relative min-h-0 overflow-hidden">
      <div
        ref={containerRef}
        className="absolute inset-0 select-none cursor-grab active:cursor-grabbing bg-card"
        style={{ touchAction: "none" }}
        data-testid="story-viewport"
        {...gesture.pointerHandlers}
      >
        {lockedAxis === "vertical" ? (
          <VerticalFlipCard
            currentContent={currentStorySlot}
            targetContent={targetStorySlot}
            direction={dir}
            progress={gesture.progress}
            cardHeight={cardSize.height}
          />
        ) : (
          currentStorySlot
        )}
      </div>
      <ArticleChatbot story={story} />
    </div>
  );
}
