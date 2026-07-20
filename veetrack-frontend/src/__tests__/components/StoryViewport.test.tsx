/**
 * Tests for StoryViewport — virtualization and story rendering.
 *
 * Verifies that only the active story is in the document, and that the
 * loading state renders skeletons.
 *
 * framer-motion mocked to plain divs; PageSwiper mocked to a minimal stub.
 */

import { render, screen } from "@testing-library/react";
import { useFeedStore } from "@/store/feedStore";
import { MOCK_STORIES } from "@/lib/mock-data";
import StoryViewport from "@/components/story-card/StoryViewport";

const FM_PROPS = new Set([
  "drag", "dragConstraints", "dragElastic", "dragDirectionLock",
  "onDragEnd", "onDrag", "onDragStart",
  "initial", "animate", "exit", "variants", "transition", "custom",
  "whileDrag", "whileHover", "whileTap", "whileInView",
  "layout", "layoutId", "style",
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

jest.mock("@/components/pages/PageSwiper", () => ({
  __esModule: true,
  default: ({ story }: { story: { id: string; title: string } }) => (
    <div data-testid={`page-swiper-${story.id}`}>{story.title}</div>
  ),
}));

beforeEach(() => {
  useFeedStore.setState({ currentStoryIndex: 0, currentPage: 1 });
});

describe("StoryViewport — virtualization", () => {
  it("renders only the active story", () => {
    render(<StoryViewport stories={MOCK_STORIES} />);
    expect(
      screen.getByTestId(`page-swiper-${MOCK_STORIES[0].id}`),
    ).toBeInTheDocument();
    // Non-active stories should NOT be rendered (virtualization)
    expect(
      screen.queryByTestId(`page-swiper-${MOCK_STORIES[2].id}`),
    ).not.toBeInTheDocument();
  });

  it("switches to the story at the new index", () => {
    useFeedStore.setState({ currentStoryIndex: 3 });
    render(<StoryViewport stories={MOCK_STORIES} />);
    expect(
      screen.getByTestId(`page-swiper-${MOCK_STORIES[3].id}`),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(`page-swiper-${MOCK_STORIES[0].id}`),
    ).not.toBeInTheDocument();
  });

  it("renders loading skeletons when isLoading=true", () => {
    render(<StoryViewport stories={[]} isLoading={true} />);
    const pulseEls = document.querySelectorAll(".animate-pulse");
    expect(pulseEls.length).toBeGreaterThanOrEqual(1);
  });

  it("renders nothing when stories list is empty and not loading", () => {
    render(<StoryViewport stories={[]} isLoading={false} />);
    expect(screen.queryByTestId(/page-swiper/)).not.toBeInTheDocument();
  });
});
