import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const MOCK_SOURCES = [
  { id: "src-1", type: "newsdata", name: "NewsData.io", is_active: true, calls_today: 847, quota: 1000 },
  { id: "src-2", type: "twitter", name: "TwitterAPI.io", is_active: true, calls_today: 324, quota: 500 },
  { id: "src-3", type: "rss", name: "RSS Feeds (42 feeds)", is_active: true, calls_today: 2341, quota: 10000 },
  { id: "src-4", type: "youtube", name: "YouTube Transcripts", is_active: false, calls_today: 0, quota: 200 },
];

export default function SourcesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Source Management</h1>
        <p className="text-muted-foreground mt-1">API quota usage and connector health</p>
      </div>

      <div className="grid gap-4">
        {MOCK_SOURCES.map((source) => {
          const usagePct = Math.round((source.calls_today / source.quota) * 100);
          return (
            <Card key={source.id}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{source.name}</CardTitle>
                  <Badge variant={source.is_active ? "default" : "secondary"}>
                    {source.is_active ? "Active" : "Paused"}
                  </Badge>
                </div>
                <CardDescription>
                  {source.calls_today.toLocaleString()} / {source.quota.toLocaleString()} calls today
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-2 rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full transition-all ${
                      usagePct > 90
                        ? "bg-risk-critical"
                        : usagePct > 70
                          ? "bg-risk-high"
                          : "bg-primary"
                    }`}
                    style={{ width: `${Math.min(usagePct, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">{usagePct}% of daily quota used</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground">
        Phase 26 will add live Prometheus metrics and per-source circuit breaker status.
      </p>
    </div>
  );
}
