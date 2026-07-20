/**
 * Component tests for AlertToast and AlertToastContainer.
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import AlertToast from "@/components/ui/AlertToast";
import type { AlertPayload } from "@/features/watchlists/hooks/useAlertSocket";

const makeAlert = (overrides?: Partial<AlertPayload>): AlertPayload => ({
  type: "alert",
  watchlist_id: "wl1",
  story_id: "s1",
  story_title: "Tesla faces SEC probe",
  risk_level: "high",
  channel: "websocket",
  ...overrides,
});

describe("AlertToast — rendering", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("renders the story title", () => {
    render(<AlertToast alert={makeAlert()} onDismiss={jest.fn()} />);
    expect(screen.getByText("Tesla faces SEC probe")).toBeInTheDocument();
  });

  it("renders the risk level label", () => {
    render(<AlertToast alert={makeAlert()} onDismiss={jest.fn()} />);
    expect(screen.getByText(/high risk alert/i)).toBeInTheDocument();
  });

  it("has role='alert' for screen readers", () => {
    render(<AlertToast alert={makeAlert()} onDismiss={jest.fn()} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders dismiss button", () => {
    render(<AlertToast alert={makeAlert()} onDismiss={jest.fn()} />);
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeInTheDocument();
  });

  it("clicking dismiss calls onDismiss", () => {
    const onDismiss = jest.fn();
    render(<AlertToast alert={makeAlert()} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

describe("AlertToast — auto-dismiss", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("calls onDismiss after autoDismissMs", () => {
    const onDismiss = jest.fn();
    render(<AlertToast alert={makeAlert()} onDismiss={onDismiss} autoDismissMs={5000} />);
    expect(onDismiss).not.toHaveBeenCalled();
    act(() => jest.advanceTimersByTime(5001));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("does NOT auto-dismiss before the timer fires", () => {
    const onDismiss = jest.fn();
    render(<AlertToast alert={makeAlert()} onDismiss={onDismiss} autoDismissMs={8000} />);
    act(() => jest.advanceTimersByTime(4000));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("clears timer on unmount (no stale callback)", () => {
    const onDismiss = jest.fn();
    const { unmount } = render(
      <AlertToast alert={makeAlert()} onDismiss={onDismiss} autoDismissMs={5000} />,
    );
    unmount();
    act(() => jest.advanceTimersByTime(6000));
    expect(onDismiss).not.toHaveBeenCalled();
  });
});

describe("AlertToast — risk level styling", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("renders critical risk label for a critical alert", () => {
    render(
      <AlertToast
        alert={makeAlert({ risk_level: "critical" })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText(/critical risk alert/i)).toBeInTheDocument();
  });

  it("renders low risk label for a low alert", () => {
    render(
      <AlertToast
        alert={makeAlert({ risk_level: "low" })}
        onDismiss={jest.fn()}
      />,
    );
    expect(screen.getByText(/low risk alert/i)).toBeInTheDocument();
  });
});
