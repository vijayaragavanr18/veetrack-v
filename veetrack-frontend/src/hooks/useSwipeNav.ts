"use client";

/**
 * Derives swipe gesture handlers that drive the feed store.
 *
 * Returns onDragEnd callbacks suitable for framer-motion `motion` elements:
 *   - vertical drag (story axis): swipe up → nextStory, swipe down → prevStory
 *   - horizontal drag (page axis): swipe left → nextPage, swipe right → prevPage
 *
 * The velocity threshold avoids accidental nav on slow deliberate scrolls.
 */

import type { PanInfo } from "framer-motion";
import { useFeedStore } from "@/store/feedStore";

const VELOCITY_THRESHOLD = 300;  // px/s — minimum swipe speed
const OFFSET_THRESHOLD  = 50;    // px — minimum drag distance (guards against taps)

export interface SwipeNavHandlers {
  /** For a vertical `drag="y"` motion element (story axis). */
  onVerticalDragEnd: (_e: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => void;
  /** For a horizontal `drag="x"` motion element (page axis). */
  onHorizontalDragEnd: (_e: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => void;
}

export function useSwipeNav(totalStories: number): SwipeNavHandlers {
  const { nextStory, prevStory, nextPage, prevPage } = useFeedStore();

  function onVerticalDragEnd(
    _e: MouseEvent | TouchEvent | PointerEvent,
    info: PanInfo,
  ) {
    const { offset, velocity } = info;
    const fast = Math.abs(velocity.y) > VELOCITY_THRESHOLD;
    const far  = Math.abs(offset.y)  > OFFSET_THRESHOLD;
    if (!fast && !far) return;

    if (offset.y < 0) {
      // Dragged up → go to next story
      nextStory(totalStories);
    } else {
      // Dragged down → go to previous story
      prevStory();
    }
  }

  function onHorizontalDragEnd(
    _e: MouseEvent | TouchEvent | PointerEvent,
    info: PanInfo,
  ) {
    const { offset, velocity } = info;
    const fast = Math.abs(velocity.x) > VELOCITY_THRESHOLD;
    const far  = Math.abs(offset.x)  > OFFSET_THRESHOLD;
    if (!fast && !far) return;

    if (offset.x < 0) {
      // Dragged left → go to next page
      nextPage();
    } else {
      // Dragged right → go to previous page
      prevPage();
    }
  }

  return { onVerticalDragEnd, onHorizontalDragEnd };
}
