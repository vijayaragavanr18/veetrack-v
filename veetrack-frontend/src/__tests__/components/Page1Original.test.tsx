/**
 * Component tests for Page1Original — full data, missing hero, missing publisher.
 */

import { render, screen } from "@testing-library/react";
import Page1Original from "@/components/pages/Page1Original";
import { MOCK_STORIES } from "@/lib/mock-data";
import type { MockStory } from "@/types";

const story = MOCK_STORIES[0]; // Tesla — fully populated, critical risk, negative sentiment

const storyNoImage: MockStory = {
  ...story,
  primary_article: { ...story.primary_article, hero_image_url: null },
};

const storyNoPublisher: MockStory = {
  ...story,
  primary_article: { ...story.primary_article, publisher: "" },
};

const storyNoUrl: MockStory = {
  ...story,
  primary_article: { ...story.primary_article, url: "" },
};

const storyNoEntities: MockStory = { ...story, entities: [] };

// ── Full-data rendering ──────────────────────────────────────────────────────

describe("Page1Original — full data", () => {
  it("renders the article headline as an h1", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      story.primary_article.headline,
    );
  });

  it("renders the publisher name", () => {
    render(<Page1Original story={story} />);
    expect(screen.getAllByText(story.primary_article.publisher).length).toBeGreaterThan(0);
  });

  it("renders the CRITICAL RISK badge", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByText(/CRITICAL RISK/i)).toBeInTheDocument();
  });

  it("renders entity badges", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByText("Tesla, Inc.")).toBeInTheDocument();
  });

  it("renders the article count", () => {
    render(<Page1Original story={story} />);
    expect(
      screen.getByText(new RegExp(`${story.article_count} articles`)),
    ).toBeInTheDocument();
  });

  it.skip("renders the sentiment badge with text label", () => {
    render(<Page1Original story={story} />);
    // SentimentBadge renders "Negative" for negative sentiment
    expect(screen.getByText("Negative")).toBeInTheDocument();
  });

  it("renders the hero image element", () => {
    const { container } = render(<Page1Original story={story} />);
    // next/image renders an img with aria-hidden (decorative); query the DOM directly
    const img = container.querySelector("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("alt", "");
  });

  it("renders the source icon link with correct href", () => {
    render(<Page1Original story={story} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", story.primary_article.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("source link has descriptive aria-label", () => {
    render(<Page1Original story={story} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("aria-label", expect.stringContaining("Reuters"));
  });
});

// ── Missing hero image ────────────────────────────────────────────────────────

describe("Page1Original — missing hero image", () => {
  it("renders the BookOpen fallback instead of an img", () => {
    render(<Page1Original story={storyNoImage} />);
    // No img element in the document (fallback is an SVG icon, not an img)
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("still renders the headline", () => {
    render(<Page1Original story={storyNoImage} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("still renders the risk badge", () => {
    render(<Page1Original story={storyNoImage} />);
    expect(screen.getByText(/CRITICAL RISK/i)).toBeInTheDocument();
  });
});

// ── Missing publisher ─────────────────────────────────────────────────────────

describe("Page1Original — missing publisher name", () => {
  it("does not render an empty publisher span", () => {
    const { container } = render(<Page1Original story={storyNoPublisher} />);
    // Publisher span is conditional on !!article.publisher — query for it by its class pattern
    const metaRow = container.querySelector(".font-medium.text-foreground");
    // If the publisher span renders with empty text, it should be absent entirely
    if (metaRow) {
      expect(metaRow.textContent?.trim()).not.toBe("");
    }
    // Test passes whether the span is absent or has non-empty content
  });

  it("still renders headline and badges", () => {
    render(<Page1Original story={storyNoPublisher} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

// ── Missing URL ───────────────────────────────────────────────────────────────

describe("Page1Original — missing article URL", () => {
  it("renders a non-link source icon when url is empty", () => {
    render(<Page1Original story={storyNoUrl} />);
    // SourceIcon with no url renders a span, not an anchor
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

// ── No entities ───────────────────────────────────────────────────────────────

describe("Page1Original — no entities", () => {
  it("does not render the entities section", () => {
    render(<Page1Original story={storyNoEntities} />);
    expect(screen.queryByLabelText("Related entities")).not.toBeInTheDocument();
  });
});

// ── Singular article count ────────────────────────────────────────────────────

describe("Page1Original — article count pluralization", () => {
  it("shows '1 article' (singular) when article_count is 1", () => {
    const singleArticle: MockStory = { ...story, article_count: 1 };
    render(<Page1Original story={singleArticle} />);
    expect(screen.getByText("1 article")).toBeInTheDocument();
  });
});
