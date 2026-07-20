"""PDF renderer — converts a BriefDocument to PDF bytes via WeasyPrint.

Keeps all HTML/CSS template logic here; the application layer only sees
`render_pdf(brief) -> bytes`.
"""

from __future__ import annotations

from app.domain.entities.brief import BriefDocument, BriefStoryItem

_RISK_COLOR = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#22c55e",
}
_RISK_BG = {
    "critical": "#fef2f2",
    "high": "#fff7ed",
    "medium": "#fefce8",
    "low": "#f0fdf4",
}


def render_pdf(brief: BriefDocument) -> bytes:
    """Render *brief* to PDF bytes.  Raises ImportError if WeasyPrint is absent."""
    from weasyprint import HTML  # deferred — keep startup fast if not installed

    html = _build_html(brief)
    return HTML(string=html).write_pdf()


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------


def _story_html(s: BriefStoryItem, idx: int) -> str:
    risk_color = _RISK_COLOR.get(s.risk_level, "#6b7280")
    risk_bg = _RISK_BG.get(s.risk_level, "#f9fafb")
    rec_html = (
        f"<p class='rec'><strong>Recommended action:</strong> {_esc(s.top_recommendation)}</p>"
        if s.top_recommendation
        else ""
    )
    return f"""
    <div class="story" style="border-left:4px solid {risk_color};background:{risk_bg}">
      <div class="story-header">
        <span class="story-num">{idx}</span>
        <span class="risk-badge" style="background:{risk_color};color:#fff">{s.risk_level.upper()}</span>
        <span class="entity-tag">{_esc(s.entity_name)}</span>
        <span class="articles">{s.article_count} article{"s" if s.article_count != 1 else ""}</span>
      </div>
      <h2 class="story-title">{_esc(s.title)}</h2>
      <h3 class="section-head">What Happened</h3>
      <p>{_esc(s.what_happened) or "<em>Analysis pending.</em>"}</p>
      <h3 class="section-head">Why It Happened</h3>
      <p>{_esc(s.why_happened) or "<em>Analysis pending.</em>"}</p>
      {rec_html}
    </div>
    """


def _build_html(brief: BriefDocument) -> str:
    stories_html = "\n".join(_story_html(s, i + 1) for i, s in enumerate(brief.stories))
    date_str = brief.generated_at.strftime("%B %d, %Y %H:%M UTC")
    window_label = f"Last {brief.window_days} day{'s' if brief.window_days != 1 else ''}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  body {{font-family: "Helvetica Neue", Arial, sans-serif; color:#1a1a1a; margin:0; padding:0;}}
  .cover {{background:#0f172a; color:#f8fafc; padding:48px 40px 40px; min-height:140px;}}
  .cover h1 {{margin:0 0 8px; font-size:28px; font-weight:700; letter-spacing:-0.5px;}}
  .cover .subtitle {{font-size:14px; color:#94a3b8; margin:0;}}
  .cover .meta {{font-size:12px; color:#64748b; margin-top:16px;}}
  .content {{padding:32px 40px;}}
  .story {{border-radius:8px; padding:20px 24px; margin-bottom:24px; page-break-inside:avoid;}}
  .story-header {{display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;}}
  .story-num {{width:24px; height:24px; border-radius:50%; background:#0f172a; color:#fff;
               font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center;}}
  .risk-badge {{font-size:10px; font-weight:700; padding:2px 8px; border-radius:12px; letter-spacing:0.5px;}}
  .entity-tag {{font-size:12px; color:#475569; font-weight:600;}}
  .articles {{font-size:12px; color:#94a3b8; margin-left:auto;}}
  .story-title {{margin:0 0 12px; font-size:17px; font-weight:700; line-height:1.3;}}
  .section-head {{font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;
                  color:#64748b; margin:14px 0 4px;}}
  p {{margin:0 0 10px; font-size:13px; line-height:1.6;}}
  .rec {{background:rgba(255,255,255,0.6); border:1px solid rgba(0,0,0,0.08);
         border-radius:4px; padding:10px 12px; font-size:13px;}}
  .footer {{text-align:center; font-size:11px; color:#94a3b8; padding:24px 40px;
            border-top:1px solid #e2e8f0;}}
</style>
</head>
<body>
  <div class="cover">
    <h1>VeeTrack Executive Brief</h1>
    <p class="subtitle">{_esc(brief.entity_keyword)} — {_esc(brief.subtitle)}</p>
    <p class="meta">{window_label} &nbsp;·&nbsp; Generated {date_str}</p>
  </div>
  <div class="content">
    {stories_html if stories_html else "<p>No stories found for the selected time window.</p>"}
  </div>
  <div class="footer">
    AI-generated suggestions are advisory only. Verify before acting. &nbsp;·&nbsp; VeeTrack
  </div>
</body>
</html>"""


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
