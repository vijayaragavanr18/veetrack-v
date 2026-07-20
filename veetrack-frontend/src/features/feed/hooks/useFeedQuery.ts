"use client";

/**
 * TanStack Query infinite-query hook for the feed.
 *
 * Falls back to MOCK_STORIES when the API is unavailable (no access token or
 * network error), so the UI keeps working during local development without a
 * running backend.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { MOCK_STORIES } from "@/lib/mock-data";
import { fetchFeed, adaptApiStory } from "@/features/feed/api/feedApi";
import type { MockStory } from "@/types";
import type { FeedResponse } from "@/features/feed/api/feedApi";

export interface UseFeedQueryResult {
  stories: MockStory[];
  isLoading: boolean;
  isError: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  /** "fast" | "cold" — from the last successful page response */
  path: "fast" | "cold" | null;
  usingMockData: boolean;
}

export function useFeedQuery(entity: string): UseFeedQueryResult {
  const accessToken = useAuthStore((s) => s.accessToken);

  const query = useInfiniteQuery<FeedResponse, Error>({
    queryKey: ["feed", entity],
    queryFn: async ({ pageParam }) => {
      if (!accessToken) throw new Error("no_token");
      return fetchFeed({
        entity,
        cursor: (pageParam as string | null) ?? null,
        accessToken,
      });
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    // Keep stale data visible while refetching
    staleTime: 60_000,
    retry: 1,
    enabled: !!accessToken,
  });

  const noToken = !accessToken;
  const apiError = query.isError || noToken;

  if (apiError) {
    return {
      stories: MOCK_STORIES,
      isLoading: false,
      isError: false,
      isFetchingNextPage: false,
      hasNextPage: false,
      fetchNextPage: () => {},
      path: null,
      usingMockData: true,
    };
  }

  const pages = query.data?.pages ?? [];
  const stories = pages.flatMap((p) => p.stories.map(adaptApiStory));
  const lastPage = pages[pages.length - 1];

  return {
    stories: stories.length > 0 ? stories : MOCK_STORIES,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: () => void query.fetchNextPage(),
    path: lastPage?.path ?? null,
    usingMockData: stories.length === 0,
  };
}
