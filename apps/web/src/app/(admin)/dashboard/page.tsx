"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ShieldAlert,
  Layers,
  ThumbsDown,
  ThumbsUp,
  Inbox,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/store/authStore";
import {
  apiGetDashboard,
  apiListPendingReview,
  apiApproveRecommendation,
  apiRejectRecommendation,
} from "@/features/admin/api/adminApi";
import type {
  DashboardData,
  PendingRecommendation,
  SourceSnapshot,
} from "@/features/admin/api/adminApi";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function usageColor(pct: number): string {
  if (pct >= 90) return "#ef4444"; // risk-critical
  if (pct >= 70) return "#f97316"; // risk-high
  return "#22c55e";                // risk-low
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.round(diff / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  title,
  value,
  sub,
  icon: Icon,
  urgent,
}: {
  title: string;
  value: string | number;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  urgent?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon
          className={`h-4 w-4 ${urgent ? "text-risk-critical" : "text-muted-foreground"}`}
        />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${urgent ? "text-risk-critical" : ""}`}>
          {value}
        </div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function SourceCard({ source }: { source: SourceSnapshot }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm capitalize">{source.type}</CardTitle>
          <div className="flex items-center gap-2">
            {source.circuit_open && (
              <Badge variant="destructive" className="text-xs">Circuit Open</Badge>
            )}
            <Badge variant={source.is_active ? "default" : "secondary"} className="text-xs">
              {source.is_active ? "Active" : "Paused"}
            </Badge>
          </div>
        </div>
        <CardDescription className="text-xs">
          {source.calls_made_this_window.toLocaleString()} / {source.quota_limit.toLocaleString()} calls this minute
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.min(source.usage_pct, 100)}%`,
              backgroundColor: usageColor(source.usage_pct),
            }}
          />
        </div>
        <p className="text-xs text-muted-foreground mt-1">{source.usage_pct}% of quota</p>
      </CardContent>
    </Card>
  );
}

function QueueDepthChart({ depths }: { depths: DashboardData["queue_depths"] }) {
  const data = [
    { queue: "ingestion", depth: depths.ingestion },
    { queue: "nlp", depth: depths.nlp },
    { queue: "llm", depth: depths.llm },
    { queue: "alerts", depth: depths.alerts },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Queue Depths</CardTitle>
        <CardDescription>Pending tasks per Celery queue</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="queue" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            <Bar dataKey="depth" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.depth > 100 ? "#ef4444" : entry.depth > 20 ? "#f97316" : "#22c55e"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function ReviewQueuePanel({
  items,
  onApprove,
  onReject,
  loading,
}: {
  items: PendingRecommendation[];
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Inbox className="h-4 w-4" aria-hidden />
          Review Queue
          {items.length > 0 && (
            <Badge variant="secondary" className="ml-1">{items.length}</Badge>
          )}
        </CardTitle>
        <CardDescription>
          AI recommendations below confidence threshold — approve or reject before surfacing to users.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && (
          <p className="text-sm text-muted-foreground py-4 text-center">Loading…</p>
        )}
        {!loading && items.length === 0 && (
          <div className="flex flex-col items-center py-8 gap-2 text-muted-foreground">
            <CheckCircle2 className="h-8 w-8 opacity-30" aria-hidden />
            <p className="text-sm">Queue is clear</p>
          </div>
        )}
        <div className="space-y-3">
          {items.map((rec) => (
            <div
              key={rec.id}
              className="rounded-lg border border-dashed border-border p-3 space-y-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="secondary" className="text-xs capitalize">{rec.audience}</Badge>
                  <Badge variant="secondary" className="text-xs capitalize">{rec.risk_level}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {Math.round(rec.confidence_score * 100)}% confidence
                  </span>
                </div>
                <span className="text-xs text-muted-foreground shrink-0">
                  {relativeTime(rec.generated_at)}
                </span>
              </div>
              <p className="text-sm leading-snug">{rec.recommendation_text}</p>
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => onApprove(rec.id)}
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-risk-low/15 text-risk-low border border-risk-low/30 hover:bg-risk-low/25 transition-colors"
                  aria-label={`Approve recommendation ${rec.id}`}
                >
                  <ThumbsUp className="h-3 w-3" aria-hidden /> Approve
                </button>
                <button
                  onClick={() => onReject(rec.id)}
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-risk-critical/10 text-risk-critical border border-risk-critical/30 hover:bg-risk-critical/20 transition-colors"
                  aria-label={`Reject recommendation ${rec.id}`}
                >
                  <ThumbsDown className="h-3 w-3" aria-hidden /> Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminDashboardPage() {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const setToken = useAuthStore((s) => s.setToken);

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [pendingRecs, setPendingRecs] = useState<PendingRecommendation[]>([]);
  const [loadingDash, setLoadingDash] = useState(true);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const isAdmin = user?.role === "admin" || user?.role === "owner";

  const fetchDashboard = useCallback(async () => {
    if (!accessToken) return;
    setLoadingDash(true);
    try {
      const data = await apiGetDashboard(accessToken, setToken);
      setDashboard(data);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoadingDash(false);
    }
  }, [accessToken, setToken]);

  const fetchQueue = useCallback(async () => {
    if (!accessToken) return;
    setLoadingQueue(true);
    try {
      const items = await apiListPendingReview(accessToken, setToken);
      setPendingRecs(items);
    } catch {
      /* non-fatal */
    } finally {
      setLoadingQueue(false);
    }
  }, [accessToken, setToken]);

  useEffect(() => {
    void fetchDashboard();
    void fetchQueue();
    const interval = setInterval(() => { void fetchDashboard(); }, 30_000);
    return () => clearInterval(interval);
  }, [fetchDashboard, fetchQueue]);

  async function handleApprove(id: string) {
    if (!accessToken) return;
    await apiApproveRecommendation(accessToken, id, setToken);
    setPendingRecs((prev) => prev.filter((r) => r.id !== id));
    setDashboard((d) =>
      d ? { ...d, pending_review_count: Math.max(0, d.pending_review_count - 1) } : d,
    );
  }

  async function handleReject(id: string) {
    if (!accessToken) return;
    await apiRejectRecommendation(accessToken, id, setToken);
    setPendingRecs((prev) => prev.filter((r) => r.id !== id));
    setDashboard((d) =>
      d ? { ...d, pending_review_count: Math.max(0, d.pending_review_count - 1) } : d,
    );
  }

  if (!user) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-muted-foreground">Sign in to access the admin console.</p>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center h-48 gap-2 text-risk-critical">
        <ShieldAlert className="h-5 w-5" aria-hidden />
        <p>Admin or owner role required.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Operations Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Source quotas · Queue depths · Review queue
            {lastRefresh && (
              <span className="ml-2 opacity-60">· Updated {relativeTime(lastRefresh.toISOString())}</span>
            )}
          </p>
        </div>
        <button
          onClick={() => { void fetchDashboard(); void fetchQueue(); }}
          disabled={loadingDash}
          className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border hover:bg-muted transition-colors disabled:opacity-50"
          aria-label="Refresh dashboard"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loadingDash ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-risk-critical bg-risk-critical/10 border border-risk-critical/30 rounded-lg px-4 py-3">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
        </div>
      )}

      {/* Top stats */}
      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            title="Sources Online"
            value={`${dashboard.sources.filter((s) => s.is_active).length}/${dashboard.sources.length}`}
            icon={CheckCircle2}
          />
          <StatCard
            title="Pending Review"
            value={dashboard.pending_review_count}
            sub="recommendations"
            icon={Clock}
            urgent={dashboard.pending_review_count > 0}
          />
          <StatCard
            title="Errors (1h)"
            value={dashboard.errors_last_hour}
            sub="unhandled exceptions"
            icon={AlertTriangle}
            urgent={dashboard.errors_last_hour > 0}
          />
          <StatCard
            title="Total Queue"
            value={Object.values(dashboard.queue_depths).reduce((a, b) => a + b, 0)}
            sub="pending tasks"
            icon={Layers}
          />
        </div>
      )}

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Queue depth chart */}
        {dashboard ? (
          <QueueDepthChart depths={dashboard.queue_depths} />
        ) : (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground text-sm">
              {loadingDash ? "Loading queue depths…" : "No data"}
            </CardContent>
          </Card>
        )}

        {/* Review queue */}
        <ReviewQueuePanel
          items={pendingRecs}
          onApprove={handleApprove}
          onReject={handleReject}
          loading={loadingQueue}
        />
      </div>

      {/* Source cards */}
      {dashboard && dashboard.sources.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-3">Source Quota Usage</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {dashboard.sources.map((src) => (
              <SourceCard key={src.id} source={src} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
