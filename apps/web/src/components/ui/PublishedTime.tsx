import { cn } from "@/lib/utils";

interface PublishedTimeProps {
  iso: string;
  className?: string;
}

function formatRelative(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 0) return "Just now";
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(diff / 86_400_000);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatAbsolute(iso: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * PublishedTime — shows relative time ("2h ago") with absolute time in the
 * title tooltip (visible on hover on desktop; accessible via aria-label).
 *
 * Uses a native <time> element for semantic correctness.
 */
export default function PublishedTime({ iso, className }: PublishedTimeProps) {
  if (!iso) return null;

  const relative = formatRelative(iso);
  const absolute = formatAbsolute(iso);

  return (
    <time
      dateTime={iso}
      title={absolute}
      aria-label={`Published ${absolute}`}
      className={cn(
        "tabular-nums cursor-default select-none",
        className,
      )}
    >
      {relative}
    </time>
  );
}
