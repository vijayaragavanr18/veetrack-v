"use client";

/**
 * useFlipGesture — shared pan-tracking hook for both vertical and horizontal flips.
 *
 * Returns imperative handlers suitable for attaching to a DOM element via
 * React pointer events. Framer Motion's onPan is NOT used here because this
 * hook needs to work at the VerticalFlipCard level, wrapping both axes, and
 * framer-motion pan would require nesting two motion elements.
 *
 * Progress is a MotionValue so it updates outside React's render cycle,
 * keeping drag at 60fps without re-renders.
 */

import { useCallback, useRef } from "react";
import { useMotionValue, animate } from "framer-motion";
import {
  V_COMPLETE_THRESHOLD,
  H_COMPLETE_THRESHOLD,
  EDGE_DAMP,
} from "./flipMath";

export type FlipAxis = "vertical" | "horizontal" | null;

interface FlipGestureOptions {
  /** Total number of stories — used to determine edge damping on vertical axis. */
  totalStories: number;
  /** Current story index. */
  currentStoryIndex: number;
  /** Total pages (always 4). */
  totalPages: number;
  /** Current page (1-based). */
  currentPage: number;
  /** Full height of the card in px — used to compute vertical progress. */
  cardHeight: number;
  /** Full width of the card in px — used to compute horizontal progress. */
  cardWidth: number;
  /** Called when a full vertical flip completes. +1 = next story, -1 = prev. */
  onStoryChange: (delta: -1 | 1) => void;
  /** Called when a full horizontal flip completes. +1 = next page, -1 = prev. */
  onPageChange: (delta: -1 | 1) => void;
}

export interface FlipGestureState {
  /** 0..1 current progress (MotionValue — reads in FlipCard components). */
  progress: ReturnType<typeof useMotionValue<number>>;
  /** Locked axis for current gesture (null between gestures). */
  axis: React.MutableRefObject<FlipAxis>;
  /** Direction of current gesture: +1 = forward, -1 = backward. */
  direction: React.MutableRefObject<1 | -1>;
  /** Pointer event handlers to spread onto the card container. */
  pointerHandlers: {
    onPointerDown: (e: React.PointerEvent) => void;
    onPointerMove: (e: React.PointerEvent) => void;
    onPointerUp: (e: React.PointerEvent) => void;
    onPointerCancel: (e: React.PointerEvent) => void;
    onTouchStart?: (e: React.TouchEvent) => void;
    onTouchMove?: (e: React.TouchEvent) => void;
    onTouchEnd?: () => void;
  };
}

/** Drag distance (px) required to travel from progress 0 → 1 on vertical axis. */
const V_DISTANCE_FACTOR = 0.75;
/** Drag distance (px) required to travel from progress 0 → 1 on horizontal axis. */
const H_DISTANCE_FACTOR = 0.70;
/** Minimum movement (px) before axis is locked. */
const AXIS_LOCK_DISTANCE = 8;

export function useFlipGesture(opts: FlipGestureOptions): FlipGestureState {
  const {
    totalStories, currentStoryIndex,
    totalPages, currentPage,
    cardHeight, cardWidth,
    onStoryChange, onPageChange,
  } = opts;

  const progress = useMotionValue(0);
  const axis = useRef<FlipAxis>(null);
  const direction = useRef<1 | -1>(1);
  const startX = useRef(0);
  const startY = useRef(0);
  const dragging = useRef(false);
  const animating = useRef(false);

  /** Compute drag progress from raw offset, clamped, with edge rubber-banding. */
  const computeProgress = useCallback(
    (rawOffset: number, isVertical: boolean, dir: 1 | -1): number => {
      const distance = isVertical
        ? cardHeight * V_DISTANCE_FACTOR
        : cardWidth * H_DISTANCE_FACTOR;

      const hasTarget = isVertical
        ? dir === 1
          ? currentStoryIndex < totalStories - 1
          : currentStoryIndex > 0
        : dir === 1
          ? currentPage < totalPages
          : currentPage > 1;

      // dir=1 means we expected a negative offset (drag UP/LEFT)
      // dir=-1 means we expected a positive offset (drag DOWN/RIGHT)
      const expectedMovement = dir === 1 ? -rawOffset : rawOffset;
      
      // If they dragged in the opposite direction, clamp at 0
      const raw = Math.max(0, expectedMovement / distance);
      
      return hasTarget ? Math.min(raw, 1) : Math.min(raw, 1) * EDGE_DAMP;
    },
    [cardHeight, cardWidth, currentStoryIndex, totalStories, currentPage, totalPages],
  );

  const cancelAnimation = useRef<ReturnType<typeof animate> | null>(null);

  const finishGesture = useCallback(
    (lockedAxis: FlipAxis, dir: 1 | -1, currentProgress: number) => {
      if (!lockedAxis) return;

      const isVertical = lockedAxis === "vertical";
      const threshold = isVertical ? V_COMPLETE_THRESHOLD : H_COMPLETE_THRESHOLD;

      const hasTarget = isVertical
        ? dir === 1
          ? currentStoryIndex < totalStories - 1
          : currentStoryIndex > 0
        : dir === 1
          ? currentPage < totalPages
          : currentPage > 1;

      const shouldComplete = currentProgress >= threshold && hasTarget;

      animating.current = true;
      cancelAnimation.current?.stop();

      cancelAnimation.current = animate(progress, shouldComplete ? 1 : 0, {
        duration: shouldComplete ? 0.14 : 0.20,
        ease: shouldComplete ? "easeOut" : "easeInOut",
        onComplete: () => {
          animating.current = false;
          if (shouldComplete) {
            // HAPTIC FEEDBACK: Subtle tick on page flip completion
            if (typeof navigator !== "undefined" && navigator.vibrate) {
              try { navigator.vibrate(15); } catch { /* ignore */ }
            }
            if (isVertical) onStoryChange(dir);
            else onPageChange(dir);
          }
          // Reset for next gesture — slight delay to let parent re-render first
          requestAnimationFrame(() => {
            progress.set(0);
            axis.current = null;
          });
        },
      });
    },
    [currentStoryIndex, totalStories, currentPage, totalPages, progress, onStoryChange, onPageChange],
  );

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (animating.current) return;
    dragging.current = true;
    axis.current = null;
    startX.current = e.clientX;
    startY.current = e.clientY;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current || animating.current) return;

    const dx = e.clientX - startX.current;
    const dy = e.clientY - startY.current;
    const dist = Math.hypot(dx, dy);

    // Lock axis once movement exceeds threshold
    if (axis.current === null) {
      if (dist < AXIS_LOCK_DISTANCE) return;
      axis.current = Math.abs(dx) > Math.abs(dy) ? "horizontal" : "vertical";
      direction.current = axis.current === "vertical"
        ? (dy < 0 ? 1 : -1)
        : (dx < 0 ? 1 : -1);
    }

    e.preventDefault();

    const isVertical = axis.current === "vertical";
    const rawOffset = isVertical ? dy : dx;
    const p = computeProgress(rawOffset, isVertical, direction.current);
    progress.set(p);
  }, [computeProgress, progress]);

  const onPointerUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    if (axis.current) {
      finishGesture(axis.current, direction.current, progress.get());
    }
  }, [finishGesture, progress]);

  const onPointerCancel = useCallback(() => {
    onPointerUp();
  }, [onPointerUp]);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (animating.current || e.touches.length > 1) return;
    dragging.current = true;
    axis.current = null;
    const touch = e.touches[0];
    startX.current = touch.clientX;
    startY.current = touch.clientY;
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!dragging.current || animating.current || e.touches.length > 1) return;
    const touch = e.touches[0];
    const dx = touch.clientX - startX.current;
    const dy = touch.clientY - startY.current;
    const dist = Math.hypot(dx, dy);

    if (axis.current === null) {
      if (dist < AXIS_LOCK_DISTANCE) return;
      axis.current = Math.abs(dx) > Math.abs(dy) ? "horizontal" : "vertical";
      direction.current = axis.current === "vertical"
        ? (dy < 0 ? 1 : -1)
        : (dx < 0 ? 1 : -1);
    }

    const isVertical = axis.current === "vertical";
    const rawOffset = isVertical ? dy : dx;
    const p = computeProgress(rawOffset, isVertical, direction.current);
    progress.set(p);
  }, [computeProgress, progress]);

  const onTouchEnd = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    if (axis.current) {
      finishGesture(axis.current, direction.current, progress.get());
    }
  }, [finishGesture, progress]);

  return {
    progress,
    axis,
    direction,
    pointerHandlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
      onTouchStart,
      onTouchMove,
      onTouchEnd,
    },
  };
}

