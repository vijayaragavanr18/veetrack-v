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
  half: "top" | "bottom" | "left" | "right";
  children: React.ReactNode;
  className?: string;
}

export default function HalfClip({
  half,
  children,
  className,
}: HalfClipProps) {
  const isHorizontal = half === "left" || half === "right";
  
  const offsetY = half === "bottom" ? "-100%" : "0";
  const offsetX = half === "right" ? "-100%" : "0";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        overflow: "hidden",
        position: "relative"
      }}
      className={className}
    >
      {/* Full inner pushes content into view through the clip window */}
      <div 
        style={{ 
          position: "absolute", 
          top: offsetY, 
          left: offsetX, 
          width: isHorizontal ? "200%" : "100%",
          height: isHorizontal ? "100%" : "200%" 
        }}
      >
        {children}
      </div>
    </div>
  );
}
