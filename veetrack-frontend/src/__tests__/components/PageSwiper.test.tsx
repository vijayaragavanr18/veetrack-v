/**
 * Tests for PageSwiper — page-axis swipe gestures and indicator dots.
 *
 * framer-motion is mocked to plain divs so tests run fast without needing
 * a real animation engine or requestAnimationFrame.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { useFeedStore } from "@/store/feedStore";
import { MOCK_STORIES } from "@/lib/mock-data";
import PageSwiper from "@/components/pages/PageSwiper";

// Filter out framer-motion-specific props that are invalid on real DOM elements.
const FM_PROPS = new Set([
  "drag", "dragConstraints", "dragElastic", "dragDirectionLock",
  "onDragEnd", "onDrag", "onDragStart",
  "initial", "animate", "exit", "variants", "transition", "custom",
  "whileDrag", "whileHover", "whileTap", "whileInView",
  "layout", "layoutId",
]);

function MotionDiv({
  children,
  ...props
}: React.ComponentProps<"div"> & Record<string, unknown>) {
  const domProps = Object.fromEntries(
    Object.entries(props).filter(([k]) => !FM_PROPS.has(k)),
  );
  return <div {...domProps}>{children}</div>;
}

jest.mock("framer-motion", () => ({
  motion: { div: MotionDiv },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useReducedMotion: () => false,
}));

const story = MOCK_STORIES[0];
const TOTAL = MOCK_STORIES.length;

beforeEach(() => {
  useFeedStore.setState({ currentStoryIndex: 0, currentPage: 1 });
});

describe("PageSwiper", () => {
  it("renders Page 1 (Original) by default", () => {
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    expect(
      screen.getByText(story.primary_article.headline),
    ).toBeInTheDocument();
  });

  it("renders Page 2 (Insight) when currentPage is 2", () => {
    useFeedStore.setState({ currentPage: 2 });
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    expect(screen.getByText(/what happened/i)).toBeInTheDocument();
  });

  it("renders Page 3 (Cluster) when currentPage is 3", () => {
    useFeedStore.setState({ currentPage: 3 });
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    expect(screen.getByText(/story cluster/i)).toBeInTheDocument();
  });

  it("renders Page 4 (Recommendations) when currentPage is 4", () => {
    useFeedStore.setState({ currentPage: 4 });
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    expect(screen.getAllByText(/recommendations/i).length).toBeGreaterThan(0);
  });

  it("renders 4 indicator dots", () => {
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
  });

  it("clicking dot 3 navigates to page 3", () => {
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[2]); // index 2 = page 3
    expect(useFeedStore.getState().currentPage).toBe(3);
  });

  it("active dot has aria-selected=true", () => {
    useFeedStore.setState({ currentPage: 2 });
    render(<PageSwiper story={story} totalStories={TOTAL} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("aria-selected", "false");
  });
});
