import { render, screen } from "@testing-library/react";
import Page1Original from "@/components/pages/Page1Original";
import Page2Insight from "@/components/pages/Page2Insight";
import Page3Cluster from "@/components/pages/Page3Cluster";
import Page4Recommendations from "@/components/pages/Page4Recommendations";
import { MOCK_STORIES } from "@/lib/mock-data";
import type { MockStory } from "@/types";

const story = MOCK_STORIES[0]; // Tesla — fully populated, critical risk

const storyWithoutRecs: MockStory = {
  ...MOCK_STORIES[0],
  recommendations: [],
};

describe("Page1Original", () => {
  it("renders the article headline", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByRole("heading")).toHaveTextContent(story.primary_article.headline);
  });

  it("renders the publisher name", () => {
    render(<Page1Original story={story} />);
    expect(screen.getAllByText(story.primary_article.publisher).length).toBeGreaterThan(0);
  });

  it("renders entity badges", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByText("Tesla, Inc.")).toBeInTheDocument();
  });

  it("renders risk badge", () => {
    render(<Page1Original story={story} />);
    expect(screen.getByText(/CRITICAL RISK/i)).toBeInTheDocument();
  });
});

describe("Page2Insight", () => {
  it("renders the What Happened section", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(/What Happened/i)).toBeInTheDocument();
  });

  it("renders the Why It Happened section", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(/Why It Happened/i)).toBeInTheDocument();
  });

  it("renders the insight text", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(story.insight.what_happened)).toBeInTheDocument();
  });

  it("renders aggregate sentiment badge", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getAllByText(/negative/i).length).toBeGreaterThan(0);
  });
});

describe("Page3Cluster", () => {
  it("renders the cluster header", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByText("Story Cluster")).toBeInTheDocument();
  });

  it.skip("renders timeline events", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByText("Investigation Opens")).toBeInTheDocument();
  });

  it("renders cluster articles", () => {
    render(<Page3Cluster story={story} />);
    expect(screen.getByText(story.cluster_articles[0].headline)).toBeInTheDocument();
  });
});

describe("Page4Recommendations", () => {
  it("renders recommendation text", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText(story.recommendations[0].recommendation_text)).toBeInTheDocument();
  });

  it("renders audience badge", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText("PR Team")).toBeInTheDocument();
  });

  it("renders the human review warning when needed", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
  });

  it("renders empty state when no recommendations", () => {
    render(<Page4Recommendations story={storyWithoutRecs} />);
    expect(screen.getByText(/No recommendations generated yet/i)).toBeInTheDocument();
  });
});
