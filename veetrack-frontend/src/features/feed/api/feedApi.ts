/**
 * Feed API client — calls GET /api/v1/feed (Phase 18).
 *
 * The backend returns a flat "4-page payload" shape (StoryPayload).
 * adaptApiStory() maps it to the MockStory shape used by all existing page
 * components so we don't need to touch Page1–4 components in this phase.
 */

import { apiFetch, getApiBaseUrl } from "@/features/auth/api/authApi";
import type { MockStory, MockArticle, MockRecommendation } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── API response types (matches apps/api/app/api/v1/feed.py) ─────────────────

export interface ApiArticleItem {
  id: string;
  headline: string;
  publisher: string;
  published_at: string;
  sentiment_label: string;
  hero_image_url?: string | null;
  url?: string;
  content_preview?: string;
}

export interface ApiInsight {
  what_happened: string;
  why_happened: string;
  model_used: string;
}

export interface ApiRecommendation {
  id: string;
  audience: string;
  recommendation_text: string;
  risk_level: string;
  confidence_score: number;
  needs_human_review: boolean;
}

export interface ApiStory {
  id: string;
  title: string;
  status: string;
  risk_level: string;
  primary_entity_id: string;
  entity_name: string;
  article_count: number;
  articles: ApiArticleItem[];
  insight: ApiInsight | null;
  cluster_member_ids: string[];
  recommendations: ApiRecommendation[];
  updated_at: string;
}

export interface FeedResponse {
  stories: ApiStory[];
  next_cursor: string | null;
  entity_id: string;
  entity_name: string;
  path: "fast" | "cold";
}

// ── Adapter: ApiStory → MockStory ────────────────────────────────────────────

function adaptArticle(a: ApiArticleItem): MockArticle {
  return {
    id: a.id,
    headline: a.headline,
    hero_image_url: a.hero_image_url ?? null,
    publisher: a.publisher,
    published_at: a.published_at,
    url: a.url ?? "",
    content_preview: a.content_preview ?? "",
    sentiment_label: (a.sentiment_label as MockArticle["sentiment_label"]) ?? "neutral",
    sentiment_score: 0,
    language: "en",
  };
}

export function adaptApiStory(s: ApiStory): MockStory {
  const primaryArticle: MockArticle =
    s.articles.length > 0
      ? adaptArticle(s.articles[0])
      : {
          id: `${s.id}-placeholder`,
          headline: s.title,
          hero_image_url: null,
          publisher: s.entity_name,
          published_at: s.updated_at,
          url: "",
          sentiment_label: "neutral",
          sentiment_score: 0,
          language: "en",
        };

  return {
    id: s.id,
    title: s.title,
    status: (s.status as MockStory["status"]) ?? "active",
    risk_level: (s.risk_level as MockStory["risk_level"]) ?? "low",
    created_at: s.updated_at,
    updated_at: s.updated_at,

    primary_article: primaryArticle,
    entities: [
      {
        id: s.primary_entity_id,
        canonical_name: s.entity_name,
        type: "company" as const,
      },
    ],
    article_count: s.article_count,

    insight: s.insight
      ? {
          id: `${s.id}-insight`,
          what_happened: s.insight.what_happened,
          why_happened: s.insight.why_happened,
          generated_at: s.updated_at,
          model_used: s.insight.model_used,
        }
      : {
          id: `${s.id}-insight`,
          what_happened: "Analysis pending…",
          why_happened: "Analysis pending…",
          generated_at: s.updated_at,
          model_used: "—",
        },
    sentiment_label: "neutral",
    sentiment_score: 0,

    cluster_articles: s.articles.map(adaptArticle),
    timeline_events: [],

    recommendations: s.recommendations.map(
      (r): MockRecommendation => ({
        id: r.id,
        recommendation_text: r.recommendation_text,
        audience: r.audience as MockRecommendation["audience"],
        risk_level: r.risk_level as MockRecommendation["risk_level"],
        confidence_score: r.confidence_score,
        needs_human_review: r.needs_human_review,
      }),
    ),
  };
}

// ── API functions ────────────────────────────────────────────────────────────

export interface FeedParams {
  entity: string;
  cursor?: string | null;
  time?: string;
  limit?: number;
  accessToken: string;
}

export async function fetchFeed({
  entity,
  cursor,
  time,
  limit = 25,
  accessToken,
}: FeedParams): Promise<FeedResponse> {
  const params = new URLSearchParams({ entity });
  if (cursor) params.set("cursor", cursor);
  if (time && time !== "all") params.set("time", time);
  if (limit !== 25) params.set("limit", String(limit));
  return apiFetch<FeedResponse>(
    `/api/v1/feed?${params.toString()}`,
    accessToken,
  );
}

/** Direct (no auth) fetch — used when API is not yet deployed and we fall back to mock data. */
export async function fetchFeedDirect(
  entity: string,
  cursor?: string | null,
  time?: string,
): Promise<FeedResponse> {
  const params = new URLSearchParams({ entity: entity });
  if (cursor) params.set("cursor", cursor);
  if (time && time !== "all") params.set("time", time);
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/api/v1/feed?${params.toString()}`, {
    credentials: "include",
    headers: {
      "Bypass-Tunnel-Reminder": "true",
      "ngrok-skip-browser-warning": "true",
    },
  });
  if (!res.ok) throw new Error(`Feed fetch failed: ${res.status}`);
  return res.json() as Promise<FeedResponse>;
}
