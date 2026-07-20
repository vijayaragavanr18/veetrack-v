"use client";

import { Suspense, useState, useTransition, useEffect } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { Loader2, Search, X } from "lucide-react";
import TopBar from "@/components/navigation/TopBar";
import BottomNav from "@/components/navigation/BottomNav";

// ── Search overlay ─────────────────────────────────────────────────────────────

function SearchOverlay({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    startTransition(() => {
      router.push(`/feed?q=${encodeURIComponent(q)}`);
      onClose();
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-background/98 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Search"
    >
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
        <form onSubmit={handleSubmit} className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" aria-hidden />
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search any topic, company, or person…"
            className="w-full rounded-full border border-input bg-muted/50 pl-9 pr-4 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-colors"
          />
          {isPending && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
          )}
        </form>
        <button
          onClick={onClose}
          className="p-2 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Close search"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pt-5 pb-6">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">
          Quick picks
        </p>
        <div className="grid grid-cols-2 gap-2">
          {["Tesla", "Apple", "OpenAI", "Meta", "NVIDIA", "SpaceX", "Amazon", "Microsoft"].map((kw) => (
            <button
              key={kw}
              onClick={() => {
                setQuery(kw);
                router.push(`/feed?q=${encodeURIComponent(kw)}`);
                onClose();
              }}
              className="flex items-center gap-2 rounded-xl bg-muted/60 border border-border px-3 py-2.5 text-sm font-medium text-foreground hover:bg-muted hover:border-primary/40 active:scale-95 transition-all text-left"
            >
              {kw}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground/60 text-center mt-5">
          Search any company, person, or topic for PR intelligence.
        </p>
      </div>
    </div>
  );
}

// ── Top bar title derives from ?q param ──────────────────────────────────────

function FeedTopBar() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const query = searchParams.get("q")?.trim();

  let title = "For You";
  if (query) title = query;
  else if (pathname.startsWith("/discover")) title = "Discover";
  else if (pathname.startsWith("/alerts")) title = "Alerts";
  else if (pathname.startsWith("/profile")) title = "Profile";

  return <TopBar title={title} />;
}

// ── Root feed shell ───────────────────────────────────────────────────────────

export default function FeedLayout({ children }: { children: React.ReactNode }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const pathname = usePathname();

  // Only show bottom nav on these routes
  const showNav =
    pathname.startsWith("/feed") ||
    pathname.startsWith("/discover") ||
    pathname.startsWith("/alerts") ||
    pathname.startsWith("/profile");

  return (
    <div className="flex flex-col h-dvh bg-background">
      {/* Desktop wrapper — simulates phone frame on wide screens */}
      <div className="flex-1 min-h-0 w-full flex justify-center bg-muted/30">
        <div className="w-full max-w-[430px] flex-1 min-h-0 flex flex-col sm:shadow-2xl sm:border-x sm:border-border bg-background overflow-hidden">

          {/* Minimal top bar with entity/section label */}
          <Suspense fallback={<div className="h-11 shrink-0 border-b border-border/40 bg-background" />}>
            <FeedTopBar />
          </Suspense>

          {/* Page content — flex-1 so it fills between top and bottom bars */}
          <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {children}
          </main>

          {/* Persistent bottom navigation */}
          {showNav && (
            <Suspense fallback={<div className="h-16 shrink-0 border-t border-border bg-background" />}>
              <BottomNav onSearchOpen={() => setSearchOpen(true)} />
            </Suspense>
          )}
        </div>
      </div>

      {/* Search overlay — rendered outside the phone frame so it fills the full viewport */}
      <Suspense fallback={null}>
        <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
      </Suspense>
    </div>
  );
}
