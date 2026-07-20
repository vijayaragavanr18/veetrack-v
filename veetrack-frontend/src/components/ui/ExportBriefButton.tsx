"use client";

import { useState } from "react";
import { Download, Loader2, FileText, Presentation } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import { apiExportBrief, downloadBlob } from "@/features/feed/api/exportsApi";
import type { ExportFormat } from "@/features/feed/api/exportsApi";

interface ExportBriefButtonProps {
  /** The entity keyword the brief is built around. */
  entity: string;
  /** Default window (days). */
  windowDays?: number;
  className?: string;
}

const FORMAT_OPTIONS: { value: ExportFormat; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { value: "pdf", label: "Export PDF", Icon: FileText },
  { value: "pptx", label: "Export PPT", Icon: Presentation },
];

export default function ExportBriefButton({
  entity,
  windowDays = 7,
  className,
}: ExportBriefButtonProps) {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [loading, setLoading] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  if (!user || !accessToken) return null;

  async function handleExport(format: ExportFormat) {
    if (!accessToken || loading) return;
    setLoading(format);
    setError(null);
    setOpen(false);
    try {
      const { blob, filename } = await apiExportBrief(accessToken, {
        entity,
        format,
        windowDays,
      });
      downloadBlob(blob, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className={cn("relative inline-flex", className)}>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={!!loading}
        aria-label="Export executive brief"
        aria-expanded={open}
        aria-haspopup="menu"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
          "bg-muted text-muted-foreground border border-border hover:bg-muted/80",
          loading && "opacity-50 cursor-wait",
        )}
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        ) : (
          <Download className="h-3.5 w-3.5" aria-hidden />
        )}
        {loading ? `Exporting ${loading.toUpperCase()}…` : "Export Brief"}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 z-20 min-w-[10rem] rounded-md border border-border bg-card shadow-lg py-1"
        >
          {FORMAT_OPTIONS.map(({ value, label, Icon }) => (
            <button
              key={value}
              role="menuitem"
              onClick={() => handleExport(value)}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-muted transition-colors"
            >
              <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p className="absolute right-0 top-full mt-1 text-xs text-destructive bg-destructive/10 rounded px-2 py-1 whitespace-nowrap z-20">
          {error}
        </p>
      )}
    </div>
  );
}
