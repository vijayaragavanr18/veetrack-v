"use client";

import { useMemo } from "react";
import { Layers, ExternalLink } from "lucide-react";
import type { MockStory, MockArticle } from "@/types";
import PublishedTime from "@/components/ui/PublishedTime";

interface Props {
  story: MockStory;
}

/** Sort a copy of articles chronologically (oldest first). */
function sortedChronologically(articles: MockArticle[]): MockArticle[] {
  return [...articles].sort(
    (a, b) => new Date(a.published_at).getTime() - new Date(b.published_at).getTime(),
  );
}

/** Deduplicate publishers from article list. */
function uniquePublishers(articles: MockArticle[]): string[] {
  const seen = new Set<string>();
  return articles.reduce<string[]>((acc, a) => {
    if (a.publisher && !seen.has(a.publisher)) {
      seen.add(a.publisher);
      acc.push(a.publisher);
    }
    return acc;
  }, []);
}

const ANALYSIS_PENDING = "Analysis pending…";

export default function Page3Cluster({ story }: Props) {
  const sorted = useMemo(
    () => sortedChronologically(story.cluster_articles),
    [story.cluster_articles],
  );

  const publishers = useMemo(() => uniquePublishers(sorted), [sorted]);

  const pullQuote =
    story.insight.what_happened && story.insight.what_happened !== ANALYSIS_PENDING
      ? story.insight.what_happened.slice(0, 120)
      : null;

  const pullQuoteTruncated =
    pullQuote !== null && story.insight.what_happened.length > 120;

  return (
    <div className="flex flex-col h-full">

      {/* 1. AI Narrative header */}
      <header className="shrink-0 bg-gradient-to-b from-primary/10 to-transparent px-5 pt-4 pb-3">
        <span className="text-[10px] font-semibold tracking-widest uppercase text-muted-foreground">
          Story Cluster
        </span>
        <h2 className="text-base font-bold leading-snug line-clamp-2 mt-0.5">
          {story.title}
        </h2>
        <p className="text-xs text-muted-foreground mt-1">
          {story.article_count} article{story.article_count === 1 ? "" : "s"}
          {" · "}
          {publishers.length} source{publishers.length === 1 ? "" : "s"}
        </p>
        {pullQuote !== null && (
          <blockquote className="mt-2 border-l-2 border-primary pl-3 text-xs italic text-muted-foreground leading-relaxed">
            {pullQuote}
            {pullQuoteTruncated ? "…" : ""}
          </blockquote>
        )}
      </header>

      {/* 2. Source pills row — skip if no publishers */}
      {publishers.length > 0 && (
        <div
          className="shrink-0 flex gap-2 px-5 py-2 overflow-x-auto"
          aria-label="Sources in this cluster"
        >
          {publishers.map((p) => (
            <span
              key={p}
              className="bg-secondary rounded-full text-[11px] px-2 py-0.5 whitespace-nowrap text-secondary-foreground shrink-0"
            >
              {p}
            </span>
          ))}
        </div>
      )}

      {/* 3. Coverage timeline */}
      <section
        className="flex-1 overflow-y-auto px-5 pb-2 min-h-0"
        aria-labelledby="coverage-heading"
      >
        <p
          id="coverage-heading"
          className="text-[10px] font-semibold tracking-widest uppercase text-muted-foreground pt-3 pb-2"
        >
          Coverage Timeline
        </p>

        {sorted.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
            <Layers className="h-8 w-8 text-muted-foreground/30" aria-hidden />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-foreground">Building cluster…</p>
              <p className="text-xs text-muted-foreground max-w-xs">
                Articles are being grouped as the pipeline runs. Check back shortly.
              </p>
            </div>
          </div>
        ) : (
          <ol
            className="list-none"
            aria-label={`${sorted.length} article${sorted.length === 1 ? "" : "s"} in chronological order`}
          >
            {sorted.map((article, i) => {
              const isLast = i === sorted.length - 1;
              return (
                <li key={article.id} className="flex gap-3">

                  {/* Git-log vertical connector + dot */}
                  <div className="flex flex-col items-center shrink-0 w-4">
                    <div
                      className={`w-px ${i === 0 ? "h-2 invisible" : "h-2 bg-border"}`}
                    />
                    <div
                      className="h-2.5 w-2.5 rounded-full border-2 border-primary/60 bg-background shrink-0 z-10"
                      aria-hidden
                    />
                    <div
                      className={`w-px flex-1 ${isLast ? "invisible" : "bg-border"}`}
                    />
                  </div>

                  {/* Article content */}
                  <div className="flex-1 min-w-0 pb-4">
                    {article.url ? (
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-start gap-1 group font-semibold text-sm leading-snug hover:text-primary transition-colors text-foreground"
                        aria-label={`${article.headline} — opens in new tab`}
                      >
                        <span className="line-clamp-2">{article.headline}</span>
                        <ExternalLink
                          className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground/60 group-hover:text-primary transition-colors"
                          aria-hidden
                        />
                      </a>
                    ) : (
                      <p className="font-semibold text-sm leading-snug line-clamp-2 text-foreground">
                        {article.headline}
                      </p>
                    )}
                    {article.content_preview && (
                      <p className="text-xs text-muted-foreground/90 line-clamp-2 mt-1 leading-relaxed bg-secondary/20 p-2 rounded border border-border/40">
                        "{article.content_preview}"
                      </p>
                    )}
                    <div className="flex items-center gap-1.5 mt-1.5 text-[11px] text-muted-foreground">
                      <span className="font-semibold text-primary/80">{article.publisher}</span>
                      <span aria-hidden>·</span>
                      <PublishedTime iso={article.published_at} />
                    </div>
                  </div>

                </li>
              );
            })}
          </ol>
        )}
      </section>

    </div>
  );
}
