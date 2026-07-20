/**
 * Exports API client — POST /api/v1/exports/brief
 *
 * Returns a Blob (PDF or PPTX); caller is responsible for triggering a
 * browser download via URL.createObjectURL.
 */

import { useAuthStore } from "@/store/authStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ExportFormat = "pdf" | "pptx";

export interface ExportBriefOptions {
  entity: string;
  format?: ExportFormat;
  windowDays?: number;
  maxStories?: number;
}

/**
 * Download an executive brief as a Blob.
 * Throws if the server returns a non-2xx response.
 */
export async function apiExportBrief(
  accessToken: string,
  opts: ExportBriefOptions,
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams({
    entity: opts.entity,
    format: opts.format ?? "pdf",
    window_days: String(opts.windowDays ?? 7),
    max_stories: String(opts.maxStories ?? 10),
  });

  const res = await fetch(`${API_BASE}/api/v1/exports/brief?${params.toString()}`, {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const match = cd.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `veetrack_brief.${opts.format ?? "pdf"}`;

  return { blob, filename };
}

/** Trigger a browser download from a Blob. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
