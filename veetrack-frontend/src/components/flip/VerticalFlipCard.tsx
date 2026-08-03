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

  // For dir > 0 (forward / drag up): bottom is the leader (peels up first), top is the follower.
  // For dir < 0 (backward / drag down): top is the leader (peels down first), bottom follows.
  const isLeaderTop = direction < 0;

  const topAngle = isLeaderTop
    ? leaderAngle(p, direction, true)
    : followerAngle(p, direction, true);

  const bottomAngle = isLeaderTop
    ? followerAngle(p, direction, false)
    : leaderAngle(p, direction, false);

  // Static back layers — always rendered, always flat
  // Forward (bottom leads): top back is current, bottom back is target
  // Backward (top leads): top back is target, bottom back is current
  const topBackContent = direction > 0 ? currentContent : targetContent;
  const bottomBackContent = direction > 0 ? targetContent : currentContent;

  // Top flap content:
  // Forward (top follows): targetContent
  // Backward (top leads): currentContent
  const topFlapContent = direction > 0 ? targetContent : currentContent;

  // Bottom flap content:
  // Forward (bottom leads): currentContent
  // Backward (bottom follows): targetContent
  const bottomFlapContent = direction > 0 ? currentContent : targetContent;

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
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "50%", overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "200%" }}>
          {topBackContent}
        </div>
      </div>
      <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: "50%", overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: "-100%", left: 0, right: 0, height: "200%" }}>
          {bottomBackContent}
        </div>
      </div>

      {/* ── Top flap ───────────────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "50%", zIndex: 2 }}>
        <FlipPanel angleDeg={topAngle} axis="x" origin="bottom">
          <HalfClip half="top">
            {topFlapContent}
          </HalfClip>
        </FlipPanel>
      </div>

      {/* ── Bottom flap ────────────────────────────────────── */}
      <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: "50%", zIndex: 2 }}>
        <FlipPanel angleDeg={bottomAngle} axis="x" origin="top">
          <HalfClip half="bottom">
            {bottomFlapContent}
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
