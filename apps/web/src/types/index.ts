import type {
  RiskLevel,
  SentimentLabel,
  StoryStatus,
  RecommendationAudience,
  EntityType,
} from "@veetrack/shared-types";

export type { RiskLevel, SentimentLabel, StoryStatus, RecommendationAudience, EntityType };

export interface MockArticle {
  id: string;
  headline: string;
  hero_image_url: string | null;
  publisher: string;
  published_at: string;
  url: string;
  sentiment_label: SentimentLabel;
  sentiment_score: number;
  language: string;
}

export interface MockEntity {
  id: string;
  canonical_name: string;
  type: EntityType;
}

export interface MockTimelineEvent {
  at: string;
  label: string;
  description: string;
}

export interface MockRecommendation {
  id: string;
  recommendation_text: string;
  audience: RecommendationAudience;
  risk_level: RiskLevel;
  confidence_score: number;
  needs_human_review: boolean;
}

/** Full 4-page story payload — field names match DB schema from docs/01_ARCHITECTURE.md §6. */
export interface MockStory {
  // Core (stories table)
  id: string;
  title: string;
  status: StoryStatus;
  risk_level: RiskLevel;
  created_at: string;
  updated_at: string;

  // Page 1 — lead article view
  primary_article: MockArticle;
  entities: MockEntity[];
  article_count: number;

  // Page 2 — AI insight (story_insights table)
  insight: {
    id: string;
    what_happened: string;
    why_happened: string;
    generated_at: string;
    model_used: string;
  };
  sentiment_label: SentimentLabel;
  sentiment_score: number;

  // Page 3 — cluster (story_articles table)
  cluster_articles: MockArticle[];
  timeline_events: MockTimelineEvent[];

  // Page 4 — recommendations (story_recommendations table)
  recommendations: MockRecommendation[];
}
