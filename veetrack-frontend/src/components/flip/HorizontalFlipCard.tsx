"use client";

/**
 * HorizontalFlipCard — page-to-page flip around a central vertical spine.
 *
 * Matches the reference VerticalFlipCard mechanics exactly, but rotated 90 degrees.
 * Folds the screen perfectly in half (left 50% and right 50%) for a book-like feel.
 */

import { useEffect, useState } from "react";
import { useMotionValue } from "framer-motion";
import FlipPanel from "./FlipPanel";
import HalfClip from "./HalfClip";

interface HorizontalFlipCardProps {
  currentContent: React.ReactNode;
  targetContent: React.ReactNode | null;
  direction: 1 | -1;
  progress: ReturnType<typeof useMotionValue<number>>;
}

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

  // If no target (edge), just bounce the current content slightly without breaking
  if (!targetContent) {
    return (
      <div style={{ position: "absolute", inset: 0, zIndex: 1 }}>
        <div style={{ 
          position: "absolute", inset: 0,
          transform: `translateX(${direction > 0 ? -p * 20 : p * 20}px)`,
          opacity: 1 - p * 0.5
        }}>
          {currentContent}
        </div>
      </div>
    );
  }

  let leftAngle = 0;
  let rightAngle = 0;
  let leftBackContent: React.ReactNode = null;
  let rightBackContent: React.ReactNode = null;
  let leftFlapContent: React.ReactNode = null;
  let rightFlapContent: React.ReactNode = null;

  if (direction === 1) {
    // Flip FORWARD (Right page folds over to the left)
    // Left half is static (current), right flap is current folding left, revealing target underneath
    leftBackContent = currentContent;
    rightBackContent = targetContent;
    
    // Right flap: current content folding from 0 to 180 (towards left)
    rightFlapContent = currentContent;
    rightAngle = 180 * p;

    // Left flap: reveals target content as it folds from -180 (hidden behind right flap) to 0
    leftFlapContent = targetContent;
    leftAngle = -180 * (1 - p);
  } else {
    // Flip BACKWARD (Left page folds over to the right)
    leftBackContent = targetContent;
    rightBackContent = currentContent;
    
    // Left flap: current content folding from 0 to -180 (towards right)
    leftFlapContent = currentContent;
    leftAngle = -180 * p;

    // Right flap: reveals target content as it folds from 180 (hidden) to 0
    rightFlapContent = targetContent;
    rightAngle = 180 * (1 - p);
  }

  return (
    <div style={{ position: "absolute", inset: 0, perspective: "2500px" }}>
      {/* ── Static back layers ─────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: "50%", overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: "200%" }}>
          {leftBackContent}
        </div>
      </div>
      <div style={{ position: "absolute", top: 0, left: "50%", bottom: 0, width: "50%", overflow: "hidden", zIndex: 0 }}>
        <div style={{ position: "absolute", top: 0, left: "-100%", bottom: 0, width: "200%" }}>
          {rightBackContent}
        </div>
      </div>

      {/* ── Left flap ───────────────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: 0, bottom: 0, width: "50%", zIndex: 2 }}>
        <FlipPanel angleDeg={leftAngle} axis="y" origin="right">
          <HalfClip half="left">
            {leftFlapContent}
          </HalfClip>
        </FlipPanel>
      </div>

      {/* ── Right flap ────────────────────────────────────── */}
      <div style={{ position: "absolute", top: 0, left: "50%", bottom: 0, width: "50%", zIndex: 2 }}>
        <FlipPanel angleDeg={rightAngle} axis="y" origin="left">
          <HalfClip half="right">
            {rightFlapContent}
          </HalfClip>
        </FlipPanel>
      </div>
    </div>
  );
}
