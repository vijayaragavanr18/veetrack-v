'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { useTheme } from 'next-themes';
import { LogOut, Moon, Sun, Bell, ChevronRight, Bookmark, ExternalLink, Trash2, X } from 'lucide-react';
import { useSavedStore } from '@/store/savedStore';
import { useAuthStore } from '@/store/authStore';
import type { MockStory } from '@/types';
import PublishedTime from '@/components/ui/PublishedTime';

// ── Saved stories sheet ───────────────────────────────────────────────────────

function SavedStoryCard({ story, onRemove }: { story: MockStory; onRemove: () => void }) {
  const article = story.primary_article;

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3.5">
      <div className="flex items-start gap-2">
        <p className="flex-1 text-sm font-semibold text-foreground leading-snug line-clamp-2">
          {article.headline}
        </p>
        <button
          onClick={onRemove}
          aria-label="Remove from saved"
          className="shrink-0 p-1 text-muted-foreground hover:text-destructive transition-colors rounded"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>

      <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap">
        {article.publisher && (
          <span className="font-medium text-foreground/70 truncate max-w-[120px]">
            {article.publisher}
          </span>
        )}
        <span aria-hidden>·</span>
        <PublishedTime iso={article.published_at} />
        <span aria-hidden>·</span>
        <span>{story.article_count} article{story.article_count === 1 ? '' : 's'}</span>
      </div>

      {article.content_preview && (
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
          {article.content_preview}
        </p>
      )}

      {article.url && (
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:text-primary/80 transition-colors w-fit"
        >
          <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
          Read on {article.publisher || 'source'}
        </a>
      )}
    </article>
  );
}

function SavedStoriesSheet({ onClose }: { onClose: () => void }) {
  const { savedStories, unsaveStory } = useSavedStore();

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border bg-background/95 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <Bookmark className="h-4 w-4 text-primary fill-primary" aria-hidden />
          <h2 className="text-sm font-semibold text-foreground">Saved</h2>
          {savedStories.length > 0 && (
            <span className="text-xs text-muted-foreground">({savedStories.length})</span>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close saved stories"
          className="p-1.5 text-muted-foreground hover:text-foreground transition-colors rounded-lg"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {savedStories.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Bookmark className="h-10 w-10 text-muted-foreground/25" aria-hidden />
            <p className="text-sm font-semibold text-foreground">No saved stories yet</p>
            <p className="text-xs text-muted-foreground max-w-[220px]">
              Tap the bookmark icon on any story to save it here.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {savedStories.map((story) => (
              <SavedStoryCard
                key={story.id}
                story={story}
                onRemove={() => unsaveStory(story.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Profile page ──────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const isDark = theme === 'dark';
  const [notificationsOn, setNotificationsOn] = useState(true);
  const [savedOpen, setSavedOpen] = useState(false);
  const savedCount = useSavedStore((s) => s.savedStories.length);
  const { user, clearAuth } = useAuthStore();

  function handleSignOut() {
    clearAuth();
    router.push('/login');
  }

  return (
    <>
      <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">
        {/* Avatar + identity */}
        <div className="flex flex-col items-center gap-3 px-6 pt-8 pb-6 border-b border-border">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/20 text-primary text-xl font-bold select-none">
            {user?.email?.[0]?.toUpperCase() ?? 'U'}
          </div>
          <div className="text-center space-y-0.5">
            <p className="text-base font-semibold text-foreground">{user?.email ?? '—'}</p>
            <span className="inline-block text-[11px] font-medium bg-primary/10 text-primary rounded-full px-2.5 py-0.5 mt-1">
              {user?.role ?? 'user'}
            </span>
          </div>
        </div>

        {/* Library section */}
        <div className="flex flex-col gap-px px-4 pt-5">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-2 mb-2">
            Library
          </p>
          <button
            onClick={() => setSavedOpen(true)}
            className="flex items-center justify-between rounded-xl bg-card border border-border px-4 py-3.5 hover:bg-muted/50 transition-colors text-left group"
          >
            <div className="flex items-center gap-3">
              <Bookmark
                className={`h-4 w-4 ${savedCount > 0 ? 'text-primary fill-primary' : 'text-muted-foreground'}`}
                aria-hidden
              />
              <span className="text-sm font-medium text-foreground">Saved Stories</span>
            </div>
            <div className="flex items-center gap-2">
              {savedCount > 0 && (
                <span className="text-xs font-semibold text-primary bg-primary/10 rounded-full px-2 py-0.5">
                  {savedCount}
                </span>
              )}
              <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors" aria-hidden />
            </div>
          </button>
        </div>

        {/* Preferences */}
        <div className="flex flex-col gap-px px-4 pt-5">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-2 mb-2">
            Preferences
          </p>

          <div className="flex items-center justify-between rounded-xl bg-card border border-border px-4 py-3.5">
            <div className="flex items-center gap-3">
              <Bell className="h-4 w-4 text-muted-foreground" aria-hidden />
              <span className="text-sm font-medium text-foreground">Notifications</span>
            </div>
            <button
              role="switch"
              aria-checked={notificationsOn}
              onClick={() => setNotificationsOn((v) => !v)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                notificationsOn ? 'bg-primary' : 'bg-muted'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${
                  notificationsOn ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between rounded-xl bg-card border border-border px-4 py-3.5 mt-2">
            <div className="flex items-center gap-3">
              {isDark
                ? <Moon className="h-4 w-4 text-primary" aria-hidden />
                : <Sun className="h-4 w-4 text-yellow-500" aria-hidden />
              }
              <span className="text-sm font-medium text-foreground">
                {isDark ? 'Dark mode' : 'Light mode'}
              </span>
            </div>
            <button
              role="switch"
              aria-checked={isDark}
              aria-label="Toggle dark mode"
              onClick={() => setTheme(isDark ? 'light' : 'dark')}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                isDark ? 'bg-primary' : 'bg-muted'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${
                  isDark ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Account */}
        <div className="flex flex-col gap-px px-4 pt-5">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-2 mb-2">
            Account
          </p>
          <button
            onClick={handleSignOut}
            className="flex items-center gap-3 rounded-xl bg-card border border-border px-4 py-3.5 text-left hover:bg-destructive/5 hover:border-destructive/30 transition-colors group"
          >
            <LogOut className="h-4 w-4 text-muted-foreground group-hover:text-destructive transition-colors" aria-hidden />
            <span className="text-sm font-medium text-foreground group-hover:text-destructive transition-colors">
              Sign Out
            </span>
          </button>
        </div>

        <p className="text-[11px] text-muted-foreground/50 text-center px-6 mt-8 mb-4">
          VeeTrack v0.1 · Phase 19
        </p>
      </div>

      {savedOpen && <SavedStoriesSheet onClose={() => setSavedOpen(false)} />}
    </>
  );
}
