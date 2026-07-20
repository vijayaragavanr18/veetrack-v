/**
 * Component tests for SourceIcon — correct URL, new tab, rel, touch target,
 * fallback when URL is empty, aria-label.
 */

import { render, screen } from "@testing-library/react";
import SourceIcon from "@/components/ui/SourceIcon";

describe("SourceIcon — with URL", () => {
  it("renders an anchor element", () => {
    render(
      <SourceIcon
        publisher="Reuters"
        url="https://reuters.com/article/123"
      />,
    );
    expect(screen.getByRole("link")).toBeInTheDocument();
  });

  it("href points to the correct URL", () => {
    render(
      <SourceIcon
        publisher="Reuters"
        url="https://reuters.com/article/123"
      />,
    );
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://reuters.com/article/123",
    );
  });

  it("opens in a new tab with target=_blank", () => {
    render(<SourceIcon publisher="BBC" url="https://bbc.com/story" />);
    expect(screen.getByRole("link")).toHaveAttribute("target", "_blank");
  });

  it("has rel=noopener noreferrer for security", () => {
    render(<SourceIcon publisher="Bloomberg" url="https://bloomberg.com/story" />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("includes the publisher name in the aria-label", () => {
    render(<SourceIcon publisher="Reuters" url="https://reuters.com/x" />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Reuters"),
    );
  });

  it("aria-label mentions new tab", () => {
    render(<SourceIcon publisher="Reuters" url="https://reuters.com/x" />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("new tab"),
    );
  });

  it("renders an SVG icon inside the link", () => {
    const { container } = render(
      <SourceIcon publisher="Reuters" url="https://reuters.com/x" />,
    );
    const link = container.querySelector("a");
    expect(link?.querySelector("svg")).toBeInTheDocument();
  });

  it("has minimum 44px touch target (h-11 = 44px)", () => {
    const { container } = render(
      <SourceIcon publisher="Reuters" url="https://reuters.com/x" />,
    );
    const link = container.querySelector("a");
    expect(link?.className).toMatch(/h-11/);
    expect(link?.className).toMatch(/w-11/);
  });
});

describe("SourceIcon — no URL", () => {
  it("renders a span (not a link) when url is empty", () => {
    render(<SourceIcon publisher="Unknown" url="" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("still renders an icon SVG as non-interactive element", () => {
    const { container } = render(
      <SourceIcon publisher="Unknown" url="" />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

describe("SourceIcon — publisher-specific icons", () => {
  // All of these just verify they render without error and still give a link
  const publishers = [
    "Reuters",
    "Bloomberg",
    "BBC",
    "CNN",
    "Financial Times",
    "YouTube",
    "Twitter",
    "RSS Feed",
    "Unknown Source",
  ];

  publishers.forEach((publisher) => {
    it(`renders without error for publisher: ${publisher}`, () => {
      expect(() =>
        render(
          <SourceIcon publisher={publisher} url="https://example.com" />,
        ),
      ).not.toThrow();
    });
  });
});
