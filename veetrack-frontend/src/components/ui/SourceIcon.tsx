import {
  Rss,
  Youtube,
  Twitter,
  Newspaper,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SourceIconProps {
  publisher: string;
  url: string;
  className?: string;
}

type SourceKey =
  | "reuters"
  | "bloomberg"
  | "ap"
  | "financial times"
  | "ft"
  | "bbc"
  | "cnn"
  | "the guardian"
  | "guardian"
  | "twitter"
  | "x"
  | "youtube"
  | "rss";

const SOURCE_ICONS: Record<
  SourceKey,
  React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>
> = {
  reuters: Newspaper,
  bloomberg: Newspaper,
  ap: Newspaper,
  "financial times": Newspaper,
  ft: Newspaper,
  bbc: Newspaper,
  cnn: Newspaper,
  "the guardian": Newspaper,
  guardian: Newspaper,
  twitter: Twitter,
  x: Twitter,
  youtube: Youtube,
  rss: Rss,
};

function resolveIcon(
  publisher: string,
): React.ComponentType<{ className?: string; "aria-hidden"?: boolean }> {
  if (!publisher) return ExternalLink;
  const key = publisher.toLowerCase() as SourceKey;
  for (const [pattern, Icon] of Object.entries(SOURCE_ICONS)) {
    if (key.includes(pattern)) return Icon;
  }
  return ExternalLink;
}

/**
 * SourceIcon — tappable icon that opens the original article URL.
 *
 * Touch target is at least 44×44 px (spec requirement).
 * Opens in a new tab with rel="noopener noreferrer" for security.
 */
export default function SourceIcon({
  publisher,
  url,
  className,
}: SourceIconProps) {
  const Icon = resolveIcon(publisher);
  const hasUrl = url && url.length > 0;

  if (!hasUrl) {
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center h-11 w-11 rounded-full",
          "text-muted-foreground cursor-default",
          className,
        )}
        aria-label={publisher || "Unknown source"}
        title={publisher || "Unknown source"}
      >
        <Icon className="h-5 w-5" aria-hidden />
      </span>
    );
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Open original article on ${publisher || "source"} (opens in new tab)`}
      title={`Read on ${publisher || "source"}`}
      className={cn(
        // Minimum 44×44 px touch target
        "inline-flex items-center justify-center h-11 w-11 rounded-full",
        "text-muted-foreground transition-colors",
        "hover:text-primary hover:bg-primary/10",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <Icon className="h-5 w-5" aria-hidden />
    </a>
  );
}
