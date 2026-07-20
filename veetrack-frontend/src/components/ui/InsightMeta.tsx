import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import PublishedTime from "@/components/ui/PublishedTime";

interface InsightMetaProps {
  modelUsed: string;
  generatedAt: string;
  className?: string;
}

/** Shorten a full model ID to a display name: "claude-haiku-4-5-20251001" → "claude-haiku" */
function shortenModel(model: string): string {
  if (!model || model === "—") return model;
  // Strip trailing date stamp and version suffix, keep vendor + family
  return model
    .replace(/-\d{8,}$/, "")     // drop trailing date stamp: "20251001"
    .replace(/-\d+(-\d+)?$/, ""); // drop trailing version numbers: "-3-5", "-4-8"
}

/**
 * InsightMeta — small, unobtrusive AI attribution + timestamp footer.
 *
 * Intentionally subdued — doesn't compete with the insight prose.
 */
export default function InsightMeta({
  modelUsed,
  generatedAt,
  className,
}: InsightMetaProps) {
  const displayModel = shortenModel(modelUsed);

  return (
    <div
      className={cn(
        "flex items-center gap-2 text-xs text-muted-foreground/70 select-none",
        className,
      )}
      aria-label={`AI-generated analysis by ${displayModel}`}
    >
      <Sparkles className="h-3 w-3 shrink-0 text-primary/50" aria-hidden />
      <span>AI-generated</span>
      {displayModel && displayModel !== "—" && (
        <>
          <span aria-hidden>·</span>
          <span className="font-mono">{displayModel}</span>
        </>
      )}
      {generatedAt && (
        <>
          <span aria-hidden>·</span>
          <PublishedTime iso={generatedAt} />
        </>
      )}
    </div>
  );
}
