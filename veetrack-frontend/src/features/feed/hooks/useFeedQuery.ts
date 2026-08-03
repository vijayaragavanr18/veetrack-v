"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { fetchFeed, fetchFeedDirect, adaptApiStory } from "@/features/feed/api/feedApi";
import type { MockStory } from "@/types";
import type { FeedResponse } from "@/features/feed/api/feedApi";

export interface UseFeedQueryResult {
  stories: MockStory[];
  isLoading: boolean;
  isError: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  path: "fast" | "cold" | null;
  usingMockData: boolean;
}

export function useFeedQuery(entity: string, time: string = "all"): UseFeedQueryResult {
  const accessToken = useAuthStore((s) => s.accessToken);

  // Try authed fetch; fall back to direct (no-auth) fetch for dev convenience
  const query = useInfiniteQuery<FeedResponse, Error>({
    queryKey: ["feed", entity, time],
    queryFn: async ({ pageParam }) => {
      const cursor = (pageParam as string | null) ?? null;
      if (accessToken) {
        return fetchFeed({ entity, cursor, time, accessToken });
      }
      return fetchFeedDirect(entity, cursor, time);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 30_000,
    retry: 1,
    enabled: entity.length > 0,
  });

  if (query.isError) {
    return {
      stories: [],
      isLoading: false,
      isError: true,
      isFetchingNextPage: false,
      hasNextPage: false,
      fetchNextPage: () => {},
      path: null,
      usingMockData: false,
    };
  }

  const pages = query.data?.pages ?? [];
  const stories = pages.flatMap((p) => p.stories.map(adaptApiStory));
  const lastPage = pages[pages.length - 1];

  return {
    stories,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: () => void query.fetchNextPage(),
    path: lastPage?.path ?? null,
    usingMockData: false,
  };
}
