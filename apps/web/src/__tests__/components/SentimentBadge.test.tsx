/**
 * Component tests for SentimentBadge — correct variant per sentiment value,
 * icon presence, accessible aria-label.
 */

import { render, screen } from "@testing-library/react";
import SentimentBadge from "@/components/ui/SentimentBadge";

describe("SentimentBadge", () => {
  it("renders 'Positive' text for positive sentiment", () => {
    render(<SentimentBadge label="positive" />);
    expect(screen.getByText("Positive")).toBeInTheDocument();
  });

  it("renders 'Negative' text for negative sentiment", () => {
    render(<SentimentBadge label="negative" />);
    expect(screen.getByText("Negative")).toBeInTheDocument();
  });

  it("renders 'Neutral' text for neutral sentiment", () => {
    render(<SentimentBadge label="neutral" />);
    expect(screen.getByText("Neutral")).toBeInTheDocument();
  });

  it("renders 'Mixed' text for mixed sentiment", () => {
    render(<SentimentBadge label="mixed" />);
    expect(screen.getByText("Mixed")).toBeInTheDocument();
  });

  it("has accessible aria-label that names the sentiment", () => {
    render(<SentimentBadge label="negative" />);
    const badge = screen.getByLabelText(/Sentiment: Negative/i);
    expect(badge).toBeInTheDocument();
  });

  it("renders a span (not a div) for inline composability", () => {
    const { container } = render(<SentimentBadge label="positive" />);
    expect(container.querySelector("span")).toBeInTheDocument();
  });

  it("renders an icon element inside the badge (aria-hidden)", () => {
    const { container } = render(<SentimentBadge label="positive" />);
    // Lucide icons render as SVG; there should be one SVG in the badge
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("aria-hidden");
  });

  it("accepts a custom className", () => {
    const { container } = render(
      <SentimentBadge label="neutral" className="test-class" />,
    );
    expect(container.firstChild).toHaveClass("test-class");
  });
});
