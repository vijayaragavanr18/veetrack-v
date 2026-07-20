/**
 * Component tests for Page2Insight — full insight data, pending state,
 * long-text overflow guard, and pending→populated transition.
 */

import { render, screen, act } from "@testing-library/react";
import Page2Insight from "@/components/pages/Page2Insight";
import { MOCK_STORIES } from "@/lib/mock-data";
import type { MockStory } from "@/types";

// Mock useQueryClient used by PendingInsightState (only rendered on cold-path stories).
const mockInvalidateQueries = jest.fn();
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

const story = MOCK_STORIES[0]; // Tesla — fully populated, negative sentiment

/** A story whose insight has the "pending" sentinel values set by adaptApiStory. */
const pendingStory: MockStory = {
  ...story,
  insight: {
    ...story.insight,
    what_happened: "Analysis pending…",
    model_used: "—",
  },
};

/** Story with very long insight text (overflow guard). */
const longTextStory: MockStory = {
  ...story,
  insight: {
    ...story.insight,
    what_happened: "A".repeat(2000),
    why_happened: "B".repeat(2000),
  },
};

beforeEach(() => {
  mockInvalidateQueries.mockClear();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

// ── Full insight ──────────────────────────────────────────────────────────────

describe("Page2Insight — full insight", () => {
  it("renders the What Happened section heading", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(/what happened/i)).toBeInTheDocument();
  });

  it("renders the Why It Happened section heading", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(/why it happened/i)).toBeInTheDocument();
  });

  it("renders the insight what_happened text", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(story.insight.what_happened)).toBeInTheDocument();
  });

  it("renders the insight why_happened text", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByText(story.insight.why_happened)).toBeInTheDocument();
  });

  it("renders the sentiment badge with the correct label", () => {
    render(<Page2Insight story={story} />);
    // SentimentBadge renders 'Negative' for negative sentiment
    expect(screen.getAllByText(/negative/i).length).toBeGreaterThan(0);
  });

  it("renders the aggregate sentiment bar", () => {
    render(<Page2Insight story={story} />);
    expect(screen.getByLabelText(/aggregate sentiment/i)).toBeInTheDocument();
  });

  it("renders InsightMeta with model attribution", () => {
    render(<Page2Insight story={story} />);
    // InsightMeta renders the model name (shortened) in .font-mono
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
  });

  it("does NOT show the pending state", () => {
    render(<Page2Insight story={story} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

// ── Pending state ─────────────────────────────────────────────────────────────

describe("Page2Insight — pending state (cold-path story)", () => {
  it("renders the pending status region", () => {
    render(<Page2Insight story={pendingStory} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("says 'Analysis in progress'", () => {
    render(<Page2Insight story={pendingStory} />);
    expect(screen.getByText("Analysis in progress")).toBeInTheDocument();
  });

  it("does NOT render the What Happened heading", () => {
    render(<Page2Insight story={pendingStory} />);
    expect(screen.queryByText(/what happened/i)).not.toBeInTheDocument();
  });

  it("does NOT render the why_happened text", () => {
    render(<Page2Insight story={pendingStory} />);
    expect(screen.queryByText(story.insight.why_happened)).not.toBeInTheDocument();
  });

  it("invalidates the feed query after the poll interval fires", () => {
    render(<Page2Insight story={pendingStory} />);

    act(() => {
      jest.advanceTimersByTime(20_000);
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["feed"] }),
    );
  });

  it("stops polling after unmount", () => {
    const { unmount } = render(<Page2Insight story={pendingStory} />);
    unmount();

    act(() => {
      jest.advanceTimersByTime(60_000);
    });

    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });
});

// ── Long-text overflow ────────────────────────────────────────────────────────

describe("Page2Insight — long text", () => {
  it("renders long what_happened text without truncation", () => {
    render(<Page2Insight story={longTextStory} />);
    const el = screen.getByText((text) => text.startsWith("A") && text.length > 100);
    expect(el).toBeInTheDocument();
  });

  it("renders long why_happened text without truncation", () => {
    render(<Page2Insight story={longTextStory} />);
    const el = screen.getByText((text) => text.startsWith("B") && text.length > 100);
    expect(el).toBeInTheDocument();
  });
});

// ── Pending → populated transition ───────────────────────────────────────────

describe("Page2Insight — pending to populated transition", () => {
  it("switches from pending UI to real content on rerender with populated story", () => {
    const { rerender } = render(<Page2Insight story={pendingStory} />);
    expect(screen.getByRole("status")).toBeInTheDocument();

    // Simulate the query resolving with real data
    rerender(<Page2Insight story={story} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText(story.insight.what_happened)).toBeInTheDocument();
  });

  it("header sentiment badge is shown in both pending and populated states", () => {
    const { rerender } = render(<Page2Insight story={pendingStory} />);
    // Header is always present
    expect(screen.getAllByText(/negative/i).length).toBeGreaterThan(0);

    rerender(<Page2Insight story={story} />);
    expect(screen.getAllByText(/negative/i).length).toBeGreaterThan(0);
  });
});
