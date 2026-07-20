// Shared TypeScript types — field names mirror Postgres schema in docs/01_ARCHITECTURE.md §6.

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type StoryStatus = "active" | "resolved" | "archived";

export type UserRole = "owner" | "admin" | "analyst" | "viewer";

export type SourceType = "newsdata" | "twitter" | "rss" | "youtube";

export type EntityType = "company" | "person" | "topic";

export type SentimentLabel = "positive" | "negative" | "neutral" | "mixed";

export type RecommendationAudience = "pr" | "exec" | "marketing";

export interface HealthResponse {
  status: "ok";
}

export interface Workspace {
  id: string;
  name: string;
  plan: string;
  created_at: string;
}

export interface User {
  id: string;
  workspace_id: string;
  email: string;
  role: UserRole;
  created_at: string;
}

export interface Source {
  id: string;
  type: SourceType;
  config_json: Record<string, unknown>;
  is_active: boolean;
  rate_limit_budget: number;
}

export interface Entity {
  id: string;
  canonical_name: string;
  type: EntityType;
  metadata_json: Record<string, unknown>;
}

export interface EntityAlias {
  id: string;
  entity_id: string;
  alias_text: string;
  alias_type: "name" | "ticker" | "handle";
}

export interface Article {
  id: string;
  source_id: string;
  external_id: string;
  url: string;
  headline: string;
  hero_image_url: string | null;
  publisher: string;
  published_at: string;
  raw_content: string;
  clean_content: string;
  language: string;
  sentiment_label: SentimentLabel;
  sentiment_score: number;
  dedup_hash: string;
  ingested_at: string;
}

export interface ArticleEntity {
  article_id: string;
  entity_id: string;
  relevance_score: number;
}

export interface Story {
  id: string;
  primary_entity_id: string;
  title: string;
  status: StoryStatus;
  risk_level: RiskLevel;
  created_at: string;
  updated_at: string;
}

export interface StoryArticle {
  story_id: string;
  article_id: string;
  added_at: string;
}

export interface StoryInsight {
  id: string;
  story_id: string;
  what_happened: string;
  why_happened: string;
  generated_at: string;
  model_used: string;
  token_cost: number;
}

export interface StoryRecommendation {
  id: string;
  story_id: string;
  recommendation_text: string;
  audience: RecommendationAudience;
  risk_level: RiskLevel;
  confidence_score: number;
  needs_human_review: boolean;
  generated_at: string;
}

export interface Watchlist {
  id: string;
  workspace_id: string;
  user_id: string;
  entity_id: string;
  alert_channels_json: Record<string, unknown>;
}

export interface Alert {
  id: string;
  watchlist_id: string;
  story_id: string;
  sent_at: string;
  channel: string;
  status: string;
}
