import Image from "next/image";
import { BookOpen, AlertTriangle } from "lucide-react";
import type { MockStory } from "@/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  story: MockStory;
  isActive: boolean;
  onClick: () => void;
}

const riskVariant: Record<string, "low" | "medium" | "high" | "critical"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

export default function StoryCard({ story, isActive, onClick }: Props) {
  const { primary_article: article } = story;

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-lg border transition-colors overflow-hidden group",
        isActive
          ? "border-primary bg-card shadow-lg shadow-primary/10"
          : "border-border bg-card hover:border-primary/50"
      )}
      aria-current={isActive ? "true" : undefined}
    >
      {/* Hero image — fixed height */}
      <div className="relative h-40 w-full bg-muted overflow-hidden">
        {article.hero_image_url ? (
          <Image
            src={article.hero_image_url}
            alt={article.headline}
            fill
            className="object-cover group-hover:scale-[1.02] transition-transform duration-300"
            sizes="(max-width: 768px) 100vw, 400px"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <BookOpen className="h-8 w-8 text-muted-foreground" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-background/70 to-transparent" />
        <div className="absolute top-2 right-2">
          <Badge variant={riskVariant[story.risk_level]} className="text-xs">
            <AlertTriangle className="h-3 w-3 mr-1" />
            {story.risk_level.toUpperCase()}
          </Badge>
        </div>
      </div>

      {/* Text content */}
      <div className="p-4 space-y-2">
        <p className="text-sm font-semibold leading-snug line-clamp-2">{article.headline}</p>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/70">{article.publisher}</span>
          <Badge
            variant={story.sentiment_label as "positive" | "negative" | "neutral" | "mixed"}
            className="capitalize"
          >
            {story.sentiment_label}
          </Badge>
          <span className="ml-auto">{story.article_count} articles</span>
        </div>
        {story.entities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {story.entities.slice(0, 3).map((e) => (
              <Badge key={e.id} variant="secondary" className="text-xs">
                {e.canonical_name}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}
