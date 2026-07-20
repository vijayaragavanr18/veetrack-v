/**
 * Component tests for PendingInsightState — honest pending UI with auto-poll.
 */

import { render, screen, act } from "@testing-library/react";
import PendingInsightState from "@/components/ui/PendingInsightState";

const mockInvalidateQueries = jest.fn();
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

beforeEach(() => {
  mockInvalidateQueries.mockClear();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("PendingInsightState", () => {
  it("renders an accessible status region", () => {
    render(<PendingInsightState />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("says 'Analysis in progress'", () => {
    render(<PendingInsightState />);
    expect(screen.getByText("Analysis in progress")).toBeInTheDocument();
  });

  it("has honest descriptive copy (mentions 'AI' and 'automatically')", () => {
    render(<PendingInsightState />);
    const body = screen.getByText(/automatically/i);
    expect(body.textContent).toMatch(/AI/i);
  });

  it("calls invalidateQueries after one default interval (20 s)", () => {
    render(<PendingInsightState />);

    act(() => {
      jest.advanceTimersByTime(20_000);
    });

    expect(mockInvalidateQueries).toHaveBeenCalledTimes(1);
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["feed"] }),
    );
  });

  it("calls invalidateQueries multiple times at the default interval", () => {
    render(<PendingInsightState />);

    act(() => {
      jest.advanceTimersByTime(60_000); // 3 × 20 s
    });

    expect(mockInvalidateQueries).toHaveBeenCalledTimes(3);
  });

  it("respects a custom pollInterval", () => {
    render(<PendingInsightState pollInterval={5_000} />);

    act(() => {
      jest.advanceTimersByTime(15_000); // 3 × 5 s
    });

    expect(mockInvalidateQueries).toHaveBeenCalledTimes(3);
  });

  it("does NOT call invalidateQueries before the first interval", () => {
    render(<PendingInsightState />);

    act(() => {
      jest.advanceTimersByTime(19_999); // just under 20 s
    });

    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it("clears the interval on unmount", () => {
    const { unmount } = render(<PendingInsightState />);
    unmount();

    act(() => {
      jest.advanceTimersByTime(60_000);
    });

    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });
});
