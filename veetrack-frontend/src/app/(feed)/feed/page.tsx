"use client";

import { useFeedStore } from "@/store/feedStore";
import { useKeyboardNav } from "@/hooks/useKeyboardNav";
import { useFeedQuery } from "@/features/feed/hooks/useFeedQuery";
import StoryCard from "@/components/story-card/StoryCard";
import StoryCardSkeleton from "@/components/story-card/StoryCardSkeleton";
import FlipStoryViewer from "@/components/flip/FlipStoryViewer";
import ExportBriefButton from "@/components/ui/ExportBriefButton";

// Default entity shown until the user searches for something else.
const DEFAULT_ENTITY = "Tesla";

export default function FeedPage() {
  const { currentStoryIndex, goToStory } = useFeedStore();
  const { stories, isLoading, usingMockData } = useFeedQuery(DEFAULT_ENTITY);
  useKeyboardNav(stories.length);

  return (
    <div className="flex gap-6">
      {/* Left: story list — sidebar navigation */}
      <aside className="hidden md:flex flex-col gap-3 w-64 shrink-0">
        <div className="flex items-center justify-between px-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Stories
            {!isLoading && (
              <>
                {" · "}
                {stories.length}
                {usingMockData && (
                  <span className="ml-1 text-[10px] opacity-60">(demo)</span>
                )}
              </>
            )}
          </p>
          <ExportBriefButton entity={DEFAULT_ENTITY} windowDays={7} />
        </div>
        <div className="space-y-3 overflow-y-auto max-h-[calc(100vh-8rem)]">
          {isLoading
            ? Array.from({ length: 4 }).map((_, i) => (
                <StoryCardSkeleton key={i} />
              ))
            : stories.map((story, i) => (
                <StoryCard
                  key={story.id}
                  story={story}
                  isActive={i === currentStoryIndex}
                  onClick={() => goToStory(i)}
                />
              ))}
        </div>
      </aside>

      {/* Right: half-bend flip story viewer */}
      <div className="flex-1 min-w-0">
        <FlipStoryViewer stories={stories} isLoading={isLoading} />

        {/* Accessibility hint */}
        <p className="mt-3 text-xs text-muted-foreground text-center" aria-live="polite">
          Swipe up/down for stories · left/right for pages · ↑↓←→ keyboard shortcuts
        </p>
      </div>
    </div>
  );
}
