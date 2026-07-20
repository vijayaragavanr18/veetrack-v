/**
 * Tests for useSwipeNav — verifies that drag gestures trigger the correct
 * store actions. We use the store directly rather than rendering a component
 * so the test stays fast and doesn't depend on framer-motion.
 */

import { act, renderHook } from "@testing-library/react";
import { useFeedStore } from "@/store/feedStore";
import { useSwipeNav } from "@/hooks/useSwipeNav";
import type { PanInfo } from "framer-motion";

const TOTAL = 8;

// Enough velocity and offset to clear both thresholds.
const fastSwipe = (x: number, y: number): PanInfo => ({
  offset: { x, y },
  velocity: {
    x: x !== 0 ? Math.sign(x) * 500 : 0,
    y: y !== 0 ? Math.sign(y) * 500 : 0,
  },
  delta: { x: 0, y: 0 },
  point: { x: 0, y: 0 },
});

// Below threshold — should NOT trigger navigation.
const tinySwipe = (x: number, y: number): PanInfo => ({
  offset: { x, y },
  velocity: { x: 0, y: 0 },
  delta: { x: 0, y: 0 },
  point: { x: 0, y: 0 },
});

const noopEvent = {} as MouseEvent;

beforeEach(() => {
  useFeedStore.setState({ currentStoryIndex: 2, currentPage: 2 });
});

// ── Vertical (story axis) ─────────────────────────────────────────────────────

describe("useSwipeNav — vertical drag (story axis)", () => {
  it("swipe up (negative y) → nextStory", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onVerticalDragEnd(noopEvent, fastSwipe(0, -100)); });
    expect(useFeedStore.getState().currentStoryIndex).toBe(3);
  });

  it("swipe down (positive y) → prevStory", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onVerticalDragEnd(noopEvent, fastSwipe(0, 100)); });
    expect(useFeedStore.getState().currentStoryIndex).toBe(1);
  });

  it("tiny drag below threshold → no navigation", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onVerticalDragEnd(noopEvent, tinySwipe(0, -10)); });
    expect(useFeedStore.getState().currentStoryIndex).toBe(2);
  });

  it("clamps at last story index", () => {
    useFeedStore.setState({ currentStoryIndex: TOTAL - 1, currentPage: 1 });
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onVerticalDragEnd(noopEvent, fastSwipe(0, -100)); });
    expect(useFeedStore.getState().currentStoryIndex).toBe(TOTAL - 1);
  });

  it("clamps at first story index (swipe down at 0)", () => {
    useFeedStore.setState({ currentStoryIndex: 0, currentPage: 1 });
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onVerticalDragEnd(noopEvent, fastSwipe(0, 100)); });
    expect(useFeedStore.getState().currentStoryIndex).toBe(0);
  });
});

// ── Horizontal (page axis) ────────────────────────────────────────────────────

describe("useSwipeNav — horizontal drag (page axis)", () => {
  it("swipe left (negative x) → nextPage", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onHorizontalDragEnd(noopEvent, fastSwipe(-100, 0)); });
    expect(useFeedStore.getState().currentPage).toBe(3);
  });

  it("swipe right (positive x) → prevPage", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onHorizontalDragEnd(noopEvent, fastSwipe(100, 0)); });
    expect(useFeedStore.getState().currentPage).toBe(1);
  });

  it("tiny horizontal drag below threshold → no navigation", () => {
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onHorizontalDragEnd(noopEvent, tinySwipe(-10, 0)); });
    expect(useFeedStore.getState().currentPage).toBe(2);
  });

  it("clamps at page 4 (swipe left)", () => {
    useFeedStore.setState({ currentStoryIndex: 0, currentPage: 4 });
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onHorizontalDragEnd(noopEvent, fastSwipe(-100, 0)); });
    expect(useFeedStore.getState().currentPage).toBe(4);
  });

  it("clamps at page 1 (swipe right)", () => {
    useFeedStore.setState({ currentStoryIndex: 0, currentPage: 1 });
    const { result } = renderHook(() => useSwipeNav(TOTAL));
    act(() => { result.current.onHorizontalDragEnd(noopEvent, fastSwipe(100, 0)); });
    expect(useFeedStore.getState().currentPage).toBe(1);
  });
});
