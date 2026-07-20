/**
 * Component tests for Page3Cluster — multi-source cluster, single-article
 * cluster, chronological ordering, large clusters, and tap-to-open URLs.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import Page3Cluster from "@/components/pages/Page3Cluster";
import { MOCK_STORIES } from "@/lib/mock-data";
import type { MockStory, MockArticle } from "@/types";

const story = MOCK_STORIES[0]; // Tesla — 3 cluster articles, 3 timeline events

// ── helpers ────────────────────────────────────────────────────────────────

function makeArticle(overrides: Partial<MockArticle> & { id: string }): MockArticle {
  return {
    id: overrides.id,
    headline: overrides.headline ?? `Headline ${overrides.id}`,
    publisher: overrides.publisher ?? "Reuters",
    published_at: overrides.published_at ?? "2024-01-01T00:00:00Z",
    url: overrides.url ?? `https://reuters.com/${overrides.id}`,
    sentiment_label: overrides.sentiment_label ?? "neutral",
    sentiment_score: overrides.sentiment_score ?? 0,
    hero_image_url: null,
    language: "en",
  };
}

const singleArticleStory: MockStory = {
  ...story,
  cluster_articles: [],
  article_count: 1,
};

// Out-of-order articles — oldest is the third in array
const outOfOrderArticles: MockArticle[] = [
  makeArticle({ id: "a3", headline: "Latest Article", published_at: "2024-03-01T00:00:00Z", publisher: "BBC" }),
  makeArticle({ id: "a1", headline: "Oldest Article", published_at: "2024-01-01T00:00:00Z", publisher: "Reuters" }),
  makeArticle({ id: "a2", headline: "Middle Article", published_at: "2024-02-01T00:00:00Z", publisher: "Bloomberg" }),
];

const outOfOrderStory: MockStory = {
  ...story,
  cluster_articles: outOfOrderArticles,
  article_count: 3,
};

// 25 articles for large cluster test
const largeClusterArticles: MockArticle[] = Array.from({ length: 25 }, (_, i) =>
  makeArticle({
    id: `large-${i}`,
    headline: `Article number ${i + 1} about the story`,
    published_at: new Date(2024, 0, i + 1).toISOString(),
    publisher: ["Reuters", "Bloomberg", "BBC", "CNN", "FT"][i % 5],
  }),
);

const largeClusterStory: MockStory = {
  ...story,
  cluster_articles: largeClusterArticles,
  article_count: 25,
  timeline_events: [],
};

// ── Multi-source cluster ───────────────────────────────────────────────────

describe("Page3Cluster — multi-source cluster", () => {
  it("renders the 'Story Cluster' heading", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByText("Story Cluster")).toBeInTheDocument();
  });

  it("renders the article count", () => {
    render(<Page3Cluster story={story} />);
    const elements = screen.getAllByText((content, element) => {
      return element?.textContent?.includes(`${story.article_count} article`) ?? false;
    });
    expect(elements.length).toBeGreaterThan(0);
  });

  it("renders all cluster article headlines", () => {
    render(<Page3Cluster story={story} />);
    story.cluster_articles.forEach((a) => {
      expect(screen.getByText(a.headline)).toBeInTheDocument();
    });
  });

  it("renders publisher names", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getAllByText("Bloomberg").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Financial Times").length).toBeGreaterThan(0);
  });

  it("renders the Sources section with publisher pills", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByLabelText("Sources in this cluster")).toBeInTheDocument();
  });

  it("renders the Key Milestones section", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByText("Investigation Opens")).toBeInTheDocument();
    expect(screen.getByText("Recall Announced")).toBeInTheDocument();
  });

  it("renders the Coverage Timeline section", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByLabelText(/articles in chronological order/i)).toBeInTheDocument();
  });

  it("each article has a link to its original URL", () => {
    render(<Page3Cluster story={story} />);
    const links = screen.getAllByRole("link");
    story.cluster_articles.forEach((a) => {
      expect(links.some((l) => l.getAttribute("href") === a.url)).toBe(true);
    });
  });

  it("links open in a new tab with noopener noreferrer", () => {
    render(<Page3Cluster story={story} />);
    const links = screen.getAllByRole("link");
    links.forEach((l) => {
      expect(l).toHaveAttribute("target", "_blank");
      expect(l).toHaveAttribute("rel", "noopener noreferrer");
    });
  });

  it("does NOT show the single-article empty state", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.queryByText(/Single source so far/i)).not.toBeInTheDocument();
  });
});

// ── Single-article cluster ────────────────────────────────────────────────

describe("Page3Cluster — single-article cluster", () => {
  it("renders the 'Single source so far' state", () => {
    render(<Page3Cluster story={singleArticleStory} />);
    expect(screen.getByText("Single source so far")).toBeInTheDocument();
  });

  it("shows the primary article headline in the single state", () => {
    render(<Page3Cluster story={singleArticleStory} />);
    expect(
      screen.getByText(singleArticleStory.primary_article.headline),
    ).toBeInTheDocument();
  });

  it("does NOT render the Coverage Timeline section", () => {
    render(<Page3Cluster story={singleArticleStory} />);
    expect(
      screen.queryByLabelText(/articles in chronological order/i),
    ).not.toBeInTheDocument();
  });

  it("still renders the heading", () => {
    render(<Page3Cluster story={singleArticleStory} />);
    expect(screen.getByText("Story Cluster")).toBeInTheDocument();
  });

  it("shows singular '1 article' count", () => {
    render(<Page3Cluster story={singleArticleStory} />);
    expect(screen.getByText("1 article")).toBeInTheDocument();
  });
});

// ── Chronological ordering ────────────────────────────────────────────────

describe("Page3Cluster — chronological ordering", () => {
  it("renders articles sorted oldest-first regardless of input order", () => {
    render(<Page3Cluster story={outOfOrderStory} />);
    const entries = screen.getAllByRole("button", { name: /tap to/ });
    // First rendered button should be the oldest article
    expect(entries[0]).toHaveAccessibleName(expect.stringContaining("Oldest Article"));
  });

  it("renders the latest article last", () => {
    render(<Page3Cluster story={outOfOrderStory} />);
    const entries = screen.getAllByRole("button", { name: /tap to/ });
    expect(entries[entries.length - 1]).toHaveAccessibleName(
      expect.stringContaining("Latest Article"),
    );
  });
});

// ── Tap-to-expand ──────────────────────────────────────────────────────────

describe("Page3Cluster — tap to expand", () => {
  it("clicking a timeline entry expands its sentiment detail", () => {
    render(<Page3Cluster story={story} />);
    const entry = screen.getAllByRole("button", { name: /tap to expand/i })[0];
    fireEvent.click(entry);
    // After expand, aria-expanded is true
    expect(entry).toHaveAttribute("aria-expanded", "true");
  });

  it("clicking an expanded entry collapses it", () => {
    render(<Page3Cluster story={story} />);
    const entry = screen.getAllByRole("button", { name: /tap to/i })[0];
    fireEvent.click(entry);
    fireEvent.click(entry);
    expect(entry).toHaveAttribute("aria-expanded", "false");
  });
});

// ── Large cluster ──────────────────────────────────────────────────────────

describe("Page3Cluster — large cluster (25 articles)", () => {
  it("renders all 25 articles without error", () => {
    render(<Page3Cluster story={largeClusterStory} />);
    const entries = screen.getAllByRole("button", { name: /tap to/ });
    expect(entries).toHaveLength(25);
  });

  it("shows all 5 unique publishers in the Sources section", () => {
    render(<Page3Cluster story={largeClusterStory} />);
    ["Reuters", "Bloomberg", "BBC", "CNN", "FT"].forEach((p) => {
      // Publisher pill in Sources section + in each entry row
      expect(screen.getAllByText(p).length).toBeGreaterThan(0);
    });
  });

  it("renders the article count as '25 articles'", () => {
    render(<Page3Cluster story={largeClusterStory} />);
    const elements = screen.getAllByText((content, element) => {
      return element?.textContent?.includes("25 articles") ?? false;
    });
    expect(elements.length).toBeGreaterThan(0);
  });
});
