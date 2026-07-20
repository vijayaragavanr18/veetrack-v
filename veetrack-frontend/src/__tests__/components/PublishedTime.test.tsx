/**
 * Component tests for PublishedTime — relative formatting, absolute title
 * tooltip, semantic time element, edge cases.
 */

import { render, screen } from "@testing-library/react";
import PublishedTime from "@/components/ui/PublishedTime";

/** Return an ISO string that is `ms` milliseconds in the past from now. */
function pastISO(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

describe("PublishedTime", () => {
  it("renders a <time> element", () => {
    render(<PublishedTime iso={pastISO(3_600_000)} />);
    expect(screen.getByRole("time")).toBeInTheDocument();
  });

  it("sets dateTime attribute to the ISO string", () => {
    const iso = pastISO(3_600_000);
    render(<PublishedTime iso={iso} />);
    expect(screen.getByRole("time")).toHaveAttribute("dateTime", iso);
  });

  it("renders 'Just now' for very recent times", () => {
    render(<PublishedTime iso={pastISO(30_000)} />);
    expect(screen.getByRole("time")).toHaveTextContent("Just now");
  });

  it("renders minutes ago for times < 1 hour", () => {
    render(<PublishedTime iso={pastISO(25 * 60_000)} />);
    expect(screen.getByRole("time")).toHaveTextContent("25m ago");
  });

  it("renders hours ago for times < 24 hours", () => {
    render(<PublishedTime iso={pastISO(5 * 3_600_000)} />);
    expect(screen.getByRole("time")).toHaveTextContent("5h ago");
  });

  it("renders days ago for times < 7 days", () => {
    render(<PublishedTime iso={pastISO(3 * 86_400_000)} />);
    expect(screen.getByRole("time")).toHaveTextContent("3d ago");
  });

  it("renders weeks ago for times < 5 weeks", () => {
    render(<PublishedTime iso={pastISO(2 * 7 * 86_400_000)} />);
    expect(screen.getByRole("time")).toHaveTextContent("2w ago");
  });

  it("renders an absolute date string for old content (> 5 weeks)", () => {
    // 6 weeks ago
    render(<PublishedTime iso={pastISO(42 * 86_400_000)} />);
    const el = screen.getByRole("time");
    // Should be a localized date string, not a relative time
    expect(el.textContent).not.toMatch(/ago/);
    expect(el.textContent!.length).toBeGreaterThan(4); // something like "Jan 1, 2026"
  });

  it("has a title attribute with the absolute date", () => {
    const iso = pastISO(5 * 3_600_000);
    render(<PublishedTime iso={iso} />);
    const el = screen.getByRole("time");
    expect(el).toHaveAttribute("title");
    expect(el.getAttribute("title")!.length).toBeGreaterThan(0);
  });

  it("has an aria-label with the absolute date", () => {
    const iso = pastISO(5 * 3_600_000);
    render(<PublishedTime iso={iso} />);
    const el = screen.getByRole("time");
    expect(el).toHaveAttribute("aria-label", expect.stringContaining("Published"));
  });

  it("renders nothing for an empty iso string", () => {
    const { container } = render(<PublishedTime iso="" />);
    expect(container.firstChild).toBeNull();
  });

  it("accepts a custom className", () => {
    render(<PublishedTime iso={pastISO(3_600_000)} className="custom" />);
    expect(screen.getByRole("time")).toHaveClass("custom");
  });
});
