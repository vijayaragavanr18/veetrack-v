"use client";

/**
 * FlipPanel — a single rotating half of the card.
 *
 * The parent supplies perspective. This element applies:
 *   - rotateX (vertical axis) or rotateY (horizontal axis)
 *   - transform-origin at the hinge edge
 *   - backface-visibility: hidden (browser handles >90° automatically)
 *   - a brightness filter to simulate fold shadow
 *
 * Returns null once |angle| >= 90° to avoid any back-face bleed on
 * browsers that ignore backface-visibility (matches reference behaviour).
 */

import { foldBrightness } from "./flipMath";

interface FlipPanelProps {
  /** Rotation angle in degrees around the hinge. */
  angleDeg: number;
  /** Which axis this panel rotates around. */
  axis: "x" | "y";
  /** Which edge is the hinge (the stationary crease). */
  origin: "top" | "bottom" | "left" | "right";
  /** Content to display inside the panel (a HalfClip). */
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export default function FlipPanel({
  angleDeg,
  axis,
  origin,
  children,
  style,
}: FlipPanelProps) {
  // Hide the panel completely once it has passed 90° — prevents back-face bleed.
  if (Math.abs(angleDeg) >= 90) return null;

  const brightness = foldBrightness(angleDeg);
  const rotate = axis === "x"
    ? `rotateX(${angleDeg}deg)`
    : `rotateY(${angleDeg}deg)`;

  const originStr =
    origin === "top"
      ? "center top"
      : origin === "bottom"
      ? "center bottom"
      : origin === "left"
      ? "left center"
      : "right center";

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        transformOrigin: originStr,
        WebkitTransformOrigin: originStr,
        transform: rotate,
        WebkitTransform: rotate,
        transformStyle: "preserve-3d",
        WebkitTransformStyle: "preserve-3d",
        backfaceVisibility: "hidden",
        WebkitBackfaceVisibility: "hidden",
        filter: `brightness(${brightness.toFixed(3)})`,
        willChange: "transform, filter",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
