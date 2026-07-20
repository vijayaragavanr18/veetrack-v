"use client";

import { useMemo } from "react";
import { GitBranch, Clock, Layers } from "lucide-react";
import type { MockStory, MockArticle } from "@/types";
import TimelineEntry from "@/components/ui/TimelineEntry";
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

/** Deduplicate publishers for the source summary pill row. */
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

function SingleArticleState({ article }: { article: MockArticle }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 h-full px-8 text-center">
      <Layers className="h-10 w-10 text-muted-foreground/30" aria-hidden />
      <div className="space-y-1.5">
        <p className="text-sm font-semibold text-foreground">Single source so far</p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Only one article is in this story cluster. More coverage will appear here as the
          pipeline finds related articles.
        </p>
      </div>
      <div className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-left space-y-1">
        <p className="text-sm font-medium leading-snug">{article.headline}</p>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="font-medium">{article.publisher}</span>
          <span aria-hidden>·</span>
          <PublishedTime iso={article.published_at} />
        </div>
      </div>
    </div>
  );
}

export default function Page3Cluster({ story }: Props) {
  const sorted = useMemo(
    () => sortedChronologically(story.cluster_articles),
    [story.cluster_articles],
  );

  const publishers = useMemo(() => uniquePublishers(sorted), [sorted]);

  const isSingleArticle = sorted.length <= 1;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-border/50 shrink-0">
        <GitBranch className="h-4 w-4 text-primary shrink-0" aria-hidden />
        <h2 className="text-lg font-semibold leading-none">Story Cluster</h2>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {story.article_count} article{story.article_count === 1 ? "" : "s"}
        </span>
      </header>

      {isSingleArticle ? (
        <SingleArticleState article={story.primary_article} />
      ) : (
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {/* Source breadth pills */}
          {publishers.length > 1 && (
            <section aria-label="Sources in this cluster">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-2">
                Sources
              </p>
              <div className="flex flex-wrap gap-1.5">
                {publishers.map((p) => (
                  <span
                    key={p}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground border border-border"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Key timeline milestones (editorial — from story.timeline_events) */}
          {story.timeline_events.length > 0 && (
            <section aria-labelledby="milestones-heading">
              <p
                id="milestones-heading"
                className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3"
              >
                Key Milestones
              </p>
              <ol className="space-y-3" aria-label="Story milestones">
                {story.timeline_events.map((event, i) => (
                  <li key={i} className="flex gap-3 text-xs">
                    <div className="flex flex-col items-center shrink-0 w-4">
                      <div className={`w-px ${i === 0 ? "h-2 invisible" : "h-2 bg-border"}`} />
                      <div className="h-2 w-2 rounded-full bg-primary shrink-0" aria-hidden />
                      <div
                        className={`w-px flex-1 ${i === story.timeline_events.length - 1 ? "invisible" : "bg-border"}`}
                      />
                    </div>
                    <div className="pb-3">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="font-semibold text-foreground">{event.label}</span>
                        <span className="text-muted-foreground/50" aria-hidden>·</span>
                        <span className="flex items-center gap-1 text-muted-foreground/70">
                          <Clock className="h-3 w-3" aria-hidden />
                          <PublishedTime iso={event.at} className="text-[11px]" />
                        </span>
                      </div>
                      <p className="text-muted-foreground leading-relaxed">{event.description}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Article timeline — sorted chronologically */}
          <section aria-labelledby="coverage-heading">
            <p
              id="coverage-heading"
              className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3"
            >
              Coverage Timeline
            </p>
            {/* overflow-anchor prevents scroll jump when entries above expand */}
            <ol
              className="list-none"
              aria-label={`${sorted.length} articles in chronological order`}
            >
              {sorted.map((article, i) => (
                <li key={article.id}>
                  <TimelineEntry
                    article={article}
                    isFirst={i === 0}
                    isLast={i === sorted.length - 1}
                  />
                </li>
              ))}
            </ol>
          </section>

        </div>
      )}
    </div>
  );
}
