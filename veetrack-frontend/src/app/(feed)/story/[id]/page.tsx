"use client";

import { use } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { adaptApiStory } from "@/features/feed/api/feedApi";
import FlipStoryViewer from "@/components/flip/FlipStoryViewer";
import type { MockStory } from "@/types";
import type { ApiStory } from "@/features/feed/api/feedApi";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function StoryPage({ params }: PageProps) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const entity = searchParams.get("q") ?? "";
  const accessToken = useAuthStore((s) => s.accessToken);

  const [story, setStory] = useState<MockStory | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const headers: Record<string, string> = {};
        if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
        const res = await fetch(`${API_BASE}/api/v1/stories/${id}`, {
          credentials: "include",
          headers,
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = (await res.json()) as ApiStory;
        if (!cancelled) setStory(adaptApiStory(data));
      } catch {
        if (!cancelled) setError(true);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [id, accessToken]);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Back nav */}
      <div className="shrink-0 flex items-center px-4 py-2 border-b border-border/40">
        <Link
          href={entity ? `/feed?q=${encodeURIComponent(entity)}` : "/feed"}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>
      </div>

      {error && (
        <div className="flex flex-col flex-1 items-center justify-center gap-3 text-center px-8">
          <p className="text-sm font-semibold text-foreground">Story not found</p>
          <p className="text-xs text-muted-foreground">This story may have been removed or is unavailable.</p>
          <Link href="/feed" className="text-xs text-primary font-medium hover:underline">
            Go to feed
          </Link>
        </div>
      )}

      {!error && !story && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {story && (
        <div className="flex flex-col flex-1 min-h-0">
          <FlipStoryViewer stories={[story]} />
        </div>
      )}
    </div>
  );
}
