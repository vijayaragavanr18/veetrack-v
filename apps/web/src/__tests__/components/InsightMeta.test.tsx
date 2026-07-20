/**
 * Component tests for InsightMeta — AI attribution line with model name +
 * relative timestamp.
 */

import { render, screen } from "@testing-library/react";
import InsightMeta from "@/components/ui/InsightMeta";

const ISO_1H_AGO = new Date(Date.now() - 3_600_000).toISOString();

describe("InsightMeta", () => {
  it("renders 'AI-generated' label", () => {
    render(<InsightMeta modelUsed="claude-sonnet-3-5" generatedAt={ISO_1H_AGO} />);
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
  });

  it("shortens 'claude-sonnet-3-5-20241022' to 'claude-sonnet'", () => {
    render(<InsightMeta modelUsed="claude-sonnet-3-5-20241022" generatedAt={ISO_1H_AGO} />);
    expect(screen.getByText("claude-sonnet")).toBeInTheDocument();
  });

  it("shortens 'claude-haiku-4-5-20251001' to 'claude-haiku'", () => {
    render(<InsightMeta modelUsed="claude-haiku-4-5-20251001" generatedAt={ISO_1H_AGO} />);
    expect(screen.getByText("claude-haiku")).toBeInTheDocument();
  });

  it("renders a shortened 'claude-sonnet-3-5' without date stripping", () => {
    render(<InsightMeta modelUsed="claude-sonnet-3-5" generatedAt={ISO_1H_AGO} />);
    // No date suffix — still shortens numeric suffix
    expect(screen.getByText("claude-sonnet")).toBeInTheDocument();
  });

  it("does not render model text when model_used is sentinel '—'", () => {
    const { container } = render(<InsightMeta modelUsed="—" generatedAt={ISO_1H_AGO} />);
    // The sentinel '—' should not appear as visible model text (only in aria-label)
    const monoEl = container.querySelector(".font-mono");
    expect(monoEl).not.toBeInTheDocument();
  });

  it("renders a relative time element when generatedAt is non-empty", () => {
    render(<InsightMeta modelUsed="claude-opus" generatedAt={ISO_1H_AGO} />);
    expect(screen.getByRole("time")).toBeInTheDocument();
  });

  it("does not render a time element when generatedAt is empty", () => {
    render(<InsightMeta modelUsed="claude-opus" generatedAt="" />);
    expect(screen.queryByRole("time")).not.toBeInTheDocument();
  });

  it("has accessible aria-label mentioning AI-generated", () => {
    render(<InsightMeta modelUsed="claude-haiku" generatedAt={ISO_1H_AGO} />);
    const el = screen.getByLabelText(/AI-generated analysis/i);
    expect(el).toBeInTheDocument();
  });

  it("accepts a custom className", () => {
    const { container } = render(
      <InsightMeta modelUsed="claude-opus" generatedAt={ISO_1H_AGO} className="mt-4" />,
    );
    expect(container.firstChild).toHaveClass("mt-4");
  });
});
