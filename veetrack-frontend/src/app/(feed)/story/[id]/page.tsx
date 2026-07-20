"use client";

import { use } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { MOCK_STORIES } from "@/lib/mock-data";
import FlipStoryViewer from "@/components/flip/FlipStoryViewer";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function StoryPage({ params }: PageProps) {
  const { id } = use(params);
  const story = MOCK_STORIES.find((s) => s.id === id);
  if (!story) notFound();

  return (
    <div className="max-w-2xl mx-auto">
      {/* Back nav */}
      <div className="flex items-center justify-between mb-4">
        <Link
          href="/feed"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to feed
        </Link>
      </div>

      {/* Full-story flip page view */}
      <FlipStoryViewer stories={MOCK_STORIES} />
    </div>
  );
}
