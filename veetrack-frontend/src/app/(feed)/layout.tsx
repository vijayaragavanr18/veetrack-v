"use client";

import Link from "next/link";
import { Settings } from "lucide-react";

export default function FeedLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-background">
      {/* Top bar */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-sm px-4 py-3">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          <Link href="/feed" className="text-lg font-bold text-primary shrink-0">
            VeeTrack
          </Link>
          <input
            type="search"
            placeholder="Search entities, topics…"
            className="flex-1 max-w-sm rounded-md border border-input bg-muted px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Link
            href="/admin/sources"
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Admin"
          >
            <Settings className="h-5 w-5" />
          </Link>
        </div>
      </header>
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">{children}</main>
    </div>
  );
}
