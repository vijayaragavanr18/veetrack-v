"use client";

/**
 * HalfClip — renders the top or bottom half of its children.
 *
 * Technique: the outer div is half the card height with overflow:hidden;
 * the inner div is the full card height, offset negatively so only the
 * desired half is visible. Matches the reference HTML's `clip()` helper.
 */

interface HalfClipProps {
  /** Which half to show. */
  half: "top" | "bottom";
  /** Full height of the card (px). */
  cardHeight: number;
  children: React.ReactNode;
  className?: string;
}

export default function HalfClip({
  half,
  cardHeight,
  children,
  className,
}: HalfClipProps) {
  const halfH = cardHeight / 2;
  const offsetY = half === "bottom" ? -halfH : 0;

  return (
    <div
      style={{ height: halfH, overflow: "hidden", position: "relative" }}
      className={className}
    >
      {/* Full-height inner pushes content into view through the clip window */}
      <div style={{ position: "absolute", top: offsetY, left: 0, right: 0, height: cardHeight }}>
        {children}
      </div>
    </div>
  );
}
