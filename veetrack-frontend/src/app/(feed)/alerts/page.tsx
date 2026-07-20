'use client';

import { Bell } from 'lucide-react';

export default function AlertsPage() {
  return (
    <div className="flex flex-col flex-1 min-h-0 items-center justify-center px-6 py-10">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <Bell className="h-8 w-8 text-muted-foreground/50" aria-hidden />
        </div>
        <div className="space-y-1.5">
          <h1 className="text-base font-semibold text-foreground">No alerts yet</h1>
          <p className="text-sm text-muted-foreground max-w-[240px] leading-relaxed">
            Track a story to get notified when new articles match your watchlist.
          </p>
        </div>
        <p className="text-[11px] text-muted-foreground/60 mt-2">
          Alert delivery: in-app · email · Slack (Phase 26)
        </p>
      </div>
    </div>
  );
}
