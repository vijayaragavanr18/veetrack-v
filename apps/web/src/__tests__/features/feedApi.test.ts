/**
 * Unit tests for adaptApiStory — the adapter that maps the Phase 18 API
 * response shape to the MockStory shape used by page components.
 */

import { adaptApiStory } from "@/features/feed/api/feedApi";
import type { ApiStory } from "@/features/feed/api/feedApi";

const baseStory: ApiStory = {
  id: "s1",
  title: "Test Story",
  status: "active",
  risk_level: "medium",
  primary_entity_id: "eid-1",
  entity_name: "Tesla",
  article_count: 3,
  articles: [
    {
      id: "a1",
      headline: "Tesla recall announced",
      publisher: "Reuters",
      published_at: "2026-07-16T00:00:00",
      sentiment_label: "negative",
    },
    {
      id: "a2",
      headline: "Safety regulators respond",
      publisher: "AP",
      published_at: "2026-07-15T00:00:00",
      sentiment_label: "neutral",
    },
  ],
  insight: {
    what_happened: "Recall of 100k vehicles",
    why_happened: "Brake software defect",
    model_used: "claude-haiku",
  },
  cluster_member_ids: ["a1", "a2"],
  recommendations: [
    {
      id: "r1",
      audience: "pr",
      recommendation_text: "Issue a public statement",
      risk_level: "high",
      confidence_score: 0.85,
      needs_human_review: false,
    },
  ],
  updated_at: "2026-07-16T10:00:00",
};

describe("adaptApiStory", () => {
  it("maps id, title, status, risk_level correctly", () => {
    const story = adaptApiStory(baseStory);
    expect(story.id).toBe("s1");
    expect(story.title).toBe("Test Story");
    expect(story.status).toBe("active");
    expect(story.risk_level).toBe("medium");
  });

  it("uses first article as primary_article", () => {
    const story = adaptApiStory(baseStory);
    expect(story.primary_article.headline).toBe("Tesla recall announced");
    expect(story.primary_article.publisher).toBe("Reuters");
    expect(story.primary_article.sentiment_label).toBe("negative");
  });

  it("creates an entity from entity_name and primary_entity_id", () => {
    const story = adaptApiStory(baseStory);
    expect(story.entities).toHaveLength(1);
    expect(story.entities[0].canonical_name).toBe("Tesla");
    expect(story.entities[0].id).toBe("eid-1");
  });

  it("maps article_count", () => {
    const story = adaptApiStory(baseStory);
    expect(story.article_count).toBe(3);
  });

  it("maps insight fields", () => {
    const story = adaptApiStory(baseStory);
    expect(story.insight.what_happened).toBe("Recall of 100k vehicles");
    expect(story.insight.why_happened).toBe("Brake software defect");
    expect(story.insight.model_used).toBe("claude-haiku");
  });

  it("maps all articles to cluster_articles", () => {
    const story = adaptApiStory(baseStory);
    expect(story.cluster_articles).toHaveLength(2);
    expect(story.cluster_articles[1].headline).toBe("Safety regulators respond");
  });

  it("maps recommendations correctly", () => {
    const story = adaptApiStory(baseStory);
    expect(story.recommendations).toHaveLength(1);
    const rec = story.recommendations[0];
    expect(rec.id).toBe("r1");
    expect(rec.audience).toBe("pr");
    expect(rec.confidence_score).toBe(0.85);
    expect(rec.needs_human_review).toBe(false);
  });

  it("uses title as placeholder headline when articles are empty", () => {
    const noArticles = { ...baseStory, articles: [] };
    const story = adaptApiStory(noArticles);
    expect(story.primary_article.headline).toBe("Test Story");
    expect(story.cluster_articles).toHaveLength(0);
  });

  it("uses fallback insight text when insight is null", () => {
    const noInsight = { ...baseStory, insight: null };
    const story = adaptApiStory(noInsight);
    expect(story.insight.what_happened).toBe("Analysis pending…");
  });
});
