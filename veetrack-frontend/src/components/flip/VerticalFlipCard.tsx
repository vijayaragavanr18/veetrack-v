"use client";

/**
 * VerticalFlipCard — story-to-story flip around a horizontal crease.
 *
 * Layer order (bottom → top):
 *   1. Static back layers: target content (top half) + current content (bottom half)
 *      — always visible, hidden behind the flaps
 *   2. FlipPanel for top half (leader when dir > 0) — rotates away first
 *   3. FlipPanel for bottom half (follower when dir > 0) — folds in second
 *   4. Crease line overlay
 *
 * Mirrors the reference HTML's zone/flap/flapFront/flapBack structure exactly.
 */

import { useEffect, useState } from "react";
import { useMotionValue } from "framer-motion";
import HalfClip from "./HalfClip";
import FlipPanel from "./FlipPanel";
import { leaderAngle, followerAngle } from "./flipMath";

interface VerticalFlipCardProps {
  /** Content for the currently-visible story (current index). */
  currentContent: React.ReactNode;
  /** Content for the story being flipped to (target index). Null at edges. */
  targetContent: React.ReactNode | null;
  /** +1 = flipping forward (to next story), -1 = backward. */
  direction: 1 | -1;
  /** 0..1 progress MotionValue from useFlipGesture. */
  progress: ReturnType<typeof useMotionValue<number>>;
  /** Card height in px. */
  cardHeight: number;
}

export default function VerticalFlipCard({
  currentContent,
  targetContent,
  direction,
  progress,
  cardHeight,
}: VerticalFlipCardProps) {
  const halfH = cardHeight / 2;
  const [p, setP] = useState(0);

  // Subscribe to the MotionValue outside React's render cycle, then batch-update
  // state only when the component needs to re-render the FlipPanels.
  useEffect(() => {
    return progress.on("change", (v) => setP(v));
  }, [progress]);

  // For dir > 0: top is the leader (peels away first), bottom is the follower.
  // For dir < 0: bottom leads, top follows.
  const isLeaderTop = direction > 0;

  const topAngle = isLeaderTop
    ? leaderAngle(p, direction, true)
    : followerAngle(p, direction, true);

  const bottomAngle = isLeaderTop
    ? followerAngle(p, direction, false)
    : leaderAngle(p, direction, false);

  // Static back layers — always rendered, always flat
  // When dragging forward: top back shows target top, bottom back shows current bottom
  // When dragging backward: reversed
  const topBackContent = direction > 0 ? targetContent : currentContent;
  const bottomBackContent = direction > 0 ? currentContent : targetContent;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        perspective: "1700px",
        touchAction: "none",
      }}
    >
      {/* ── Static back layers ─────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: halfH, overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: cardHeight }}>
          {topBackContent ?? currentContent}
        </div>
      </div>
      <div style={{ position: "absolute", top: halfH, left: 0, right: 0, height: halfH, overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: -halfH, left: 0, right: 0, height: cardHeight }}>
          {bottomBackContent ?? currentContent}
        </div>
      </div>

      {/* ── Top flap ───────────────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: halfH, zIndex: 2 }}>
        <FlipPanel angleDeg={topAngle} axis="x" origin="bottom">
          <HalfClip half="top" cardHeight={cardHeight}>
            {currentContent}
          </HalfClip>
        </FlipPanel>
      </div>

      {/* ── Bottom flap ────────────────────────────────────── */}
      <div style={{ position: "absolute", top: halfH, left: 0, right: 0, height: halfH, zIndex: 2 }}>
        <FlipPanel angleDeg={bottomAngle} axis="x" origin="top">
          <HalfClip half="bottom" cardHeight={cardHeight}>
            {direction > 0 ? (targetContent ?? currentContent) : currentContent}
          </HalfClip>
        </FlipPanel>
      </div>

      {/* ── Crease ─────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          top: halfH - 1,
          left: 0,
          right: 0,
          height: 2,
          background: "rgba(0,0,0,0.18)",
          zIndex: 6,
          pointerEvents: "none",
          opacity: p > 0 ? 1 : 0,
          transition: "opacity 0.1s",
        }}
        aria-hidden
      />
    </div>
  );
}
