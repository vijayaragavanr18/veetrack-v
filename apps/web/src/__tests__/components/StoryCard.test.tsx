import { render, screen, fireEvent } from "@testing-library/react";
import StoryCard from "@/components/story-card/StoryCard";
import { MOCK_STORIES } from "@/lib/mock-data";

const story = MOCK_STORIES[0];

describe("StoryCard", () => {
  it("renders the article headline", () => {
    render(<StoryCard story={story} isActive={false} onClick={() => {}} />);
    expect(screen.getByText(story.primary_article.headline)).toBeInTheDocument();
  });

  it("renders the publisher name", () => {
    render(<StoryCard story={story} isActive={false} onClick={() => {}} />);
    expect(screen.getByText(story.primary_article.publisher)).toBeInTheDocument();
  });

  it("renders the risk level badge", () => {
    render(<StoryCard story={story} isActive={false} onClick={() => {}} />);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("renders the first entity name", () => {
    render(<StoryCard story={story} isActive={false} onClick={() => {}} />);
    expect(screen.getByText(story.entities[0].canonical_name)).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    const onClick = jest.fn();
    render(<StoryCard story={story} isActive={false} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("marks the button as current when isActive", () => {
    render(<StoryCard story={story} isActive={true} onClick={() => {}} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-current", "true");
  });
});
