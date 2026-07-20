"use client";

/**
 * HorizontalFlipCard — page-to-page flip around a vertical crease.
 *
 * Matches the reference HTML's horizontal tilt: the whole card rotates
 * around its right or left edge (not split into halves). This produces a
 * "page turn" effect — the target content is revealed beneath.
 *
 * Layer order:
 *   1. Static back layer (target page content) — always flat beneath
 *   2. Front card — rotates around its hinge edge, darkens with fold shadow
 */

import { useEffect, useState } from "react";
import { useMotionValue } from "framer-motion";
import { foldBrightness, EDGE_DAMP } from "./flipMath";

interface HorizontalFlipCardProps {
  /** Content of the currently visible page. */
  currentContent: React.ReactNode;
  /** Content of the target page. Null at edges. */
  targetContent: React.ReactNode | null;
  /** +1 = flip forward (right-to-left page turn), -1 = backward. */
  direction: 1 | -1;
  /** 0..1 progress MotionValue from useFlipGesture. */
  progress: ReturnType<typeof useMotionValue<number>>;
}

/** Max rotation angle for the horizontal tilt (matches reference: 130°). */
const H_MAX_ANGLE = 130;

export default function HorizontalFlipCard({
  currentContent,
  targetContent,
  direction,
  progress,
}: HorizontalFlipCardProps) {
  const [p, setP] = useState(0);

  useEffect(() => {
    return progress.on("change", (v) => setP(v));
  }, [progress]);

  const hasTarget = targetContent !== null;
  const damp = hasTarget ? 1 : EDGE_DAMP;
  const angle = (direction > 0 ? -1 : 1) * p * H_MAX_ANGLE * damp;
  const origin = direction > 0 ? "right center" : "left center";
  const brightness = foldBrightness(angle);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {/* Static back layer — target page */}
      {hasTarget && (
        <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
          {targetContent}
        </div>
      )}

      {/* Front card — rotates around its hinge */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 2,
          perspective: "1700px",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            transformOrigin: origin,
            transform: `rotateY(${angle}deg)`,
            filter: `brightness(${brightness.toFixed(3)})`,
            willChange: "transform, filter",
            backfaceVisibility: "hidden",
            WebkitBackfaceVisibility: "hidden",
          }}
        >
          {currentContent}
        </div>
      </div>
    </div>
  );
}
