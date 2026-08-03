"use client";

import { Suspense, useEffect, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useFeedStore } from "@/store/feedStore";
import { useKeyboardNav } from "@/hooks/useKeyboardNav";
import { useFeedQuery } from "@/features/feed/hooks/useFeedQuery";
import FlipStoryViewer from "@/components/flip/FlipStoryViewer";

function EmptyPrompt() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center gap-4 px-8 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
        <Search className="h-7 w-7 text-primary" aria-hidden />
      </div>
      <div className="space-y-1.5">
        <p className="text-base font-semibold text-foreground">Search to get started</p>
        <p className="text-sm text-muted-foreground max-w-[240px]">
          Tap the search button below and enter a company, person, or topic to see PR intelligence.
        </p>
      </div>
    </div>
  );
}

function FeedContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = searchParams.get("q")?.trim() ?? "";
  const time = searchParams.get("time")?.trim() ?? "all";

  const { resetFeed, lastQuery, setLastQuery, lastTime, setLastTime } = useFeedStore();

  const prevQuery = useRef(query);
  const prevTime = useRef(time);
  useEffect(() => {
    if (query && query !== lastQuery) {
      setLastQuery(query);
    }
    if (time && time !== lastTime) {
      setLastTime(time);
    }
    
    if (prevQuery.current !== query || prevTime.current !== time) {
      prevQuery.current = query;
      prevTime.current = time;
      resetFeed();
    }
  }, [query, time, lastQuery, lastTime, setLastQuery, setLastTime, resetFeed]);

  // If there's no query in URL but we have a lastQuery in store, redirect to it
  useEffect(() => {
    if (!query && lastQuery) {
      router.replace(`/feed?q=${encodeURIComponent(lastQuery)}&time=${lastTime}`);
    }
  }, [query, lastQuery, lastTime, router]);

  const { stories, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useFeedQuery(query, time);
  useKeyboardNav(stories.length);

  // No search query yet — show prompt instead of fetching
  if (!query) {
    return <EmptyPrompt />;
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <FlipStoryViewer 
        stories={stories} 
        isLoading={isLoading}
        fetchNextPage={fetchNextPage}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
      />
    </div>
  );
}

export default function FeedPage() {
  return (
    <div className="flex flex-col flex-1 min-h-0 h-full">
      <Suspense fallback={<div className="flex-1 bg-muted animate-pulse" />}>
        <FeedContent />
      </Suspense>
    </div>
  );
}
