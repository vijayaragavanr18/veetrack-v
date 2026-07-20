"""Celery task: scheduled_digest — generates and emails an executive brief.

Runs on the 'llm' queue (already handles LLM-heavy work; export rendering is
comparable overhead).

Per-workspace schedule is configured in the Beat schedule entry in celery_app.py.
Email delivery is handled by Phase 24's email channel.  If SMTP credentials are
absent the task logs a warning and marks itself as completed — this ensures the
Beat schedule does not crash the worker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="exports.scheduled_digest",
    queue="llm",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def scheduled_digest(
    self: Any,
    workspace_id: str,
    entity_keyword: str,
    recipient_emails: list[str],
    window_days: int = 7,
    format: str = "pdf",
) -> dict[str, Any]:
    """Generate an executive brief and email it to workspace recipients.

    Returns {"status": "sent"|"skipped", "story_count": int, "recipients": int}.
    """
    try:
        return asyncio.run(
            _run(workspace_id, entity_keyword, recipient_emails, window_days, format)
        )
    except Exception as exc:
        logger.exception(
            "scheduled_digest.failed",
            extra={
                "workspace_id": workspace_id,
                "entity_keyword": entity_keyword,
            },
        )
        raise self.retry(exc=exc) from exc


async def _run(
    workspace_id: str,
    entity_keyword: str,
    recipient_emails: list[str],
    window_days: int,
    format: str,
) -> dict[str, Any]:
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.application.use_cases.exports.build_brief import BuildBrief, BuildBriefInput

    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:

        async def _db_query(sql: str, params: dict) -> list[dict]:
            result = await session.execute(text(sql), params)
            cols = result.keys()
            return [dict(zip(cols, row, strict=True)) for row in result]

        brief = await BuildBrief(db_query=_db_query).execute(
            BuildBriefInput(
                workspace_id=workspace_id,
                entity_keyword=entity_keyword,
                window_days=window_days,
                max_stories=15,
            )
        )

    await engine.dispose()

    if not brief.stories:
        logger.info(
            "scheduled_digest.no_stories",
            extra={"workspace_id": workspace_id, "entity_keyword": entity_keyword},
        )
        return {"status": "skipped", "story_count": 0, "recipients": 0}

    # Render
    if format == "pptx":
        from app.infrastructure.exports.pptx_renderer import render_pptx

        payload = render_pptx(brief)
        filename = f"veetrack_brief_{entity_keyword[:20]}.pptx"
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        from app.infrastructure.exports.pdf_renderer import render_pdf

        payload = render_pdf(brief)
        filename = f"veetrack_brief_{entity_keyword[:20]}.pdf"
        mime = "application/pdf"

    # Email delivery
    sent = _send_digest_emails(
        recipients=recipient_emails,
        subject=f"VeeTrack Digest: {entity_keyword}",
        brief=brief,
        attachment_bytes=payload,
        attachment_filename=filename,
        attachment_mime=mime,
    )

    logger.info(
        "scheduled_digest.done",
        extra={
            "workspace_id": workspace_id,
            "story_count": len(brief.stories),
            "recipients": sent,
        },
    )
    return {"status": "sent", "story_count": len(brief.stories), "recipients": sent}


def _send_digest_emails(
    recipients: list[str],
    subject: str,
    brief: Any,
    attachment_bytes: bytes,
    attachment_filename: str,
    attachment_mime: str,
) -> int:
    """Send the digest PDF/PPTX via SMTP.

    Returns number of recipients successfully delivered to.
    If SMTP credentials (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) are absent,
    logs a warning and returns 0 — the task still completes successfully.
    """
    import os
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user or "noreply@veetrack.ai")

    if not (smtp_host and smtp_user and smtp_password):
        logger.warning(
            "scheduled_digest.smtp_not_configured",
            extra={
                "missing": [
                    k
                    for k, v in {
                        "SMTP_HOST": smtp_host,
                        "SMTP_USER": smtp_user,
                        "SMTP_PASSWORD": smtp_password,
                    }.items()
                    if not v
                ]
            },
        )
        return 0

    body = _build_email_body(brief)
    sent = 0

    for recipient in recipients:
        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = recipient
            msg.attach(MIMEText(body, "plain"))

            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment_filename}"',
            )
            part.add_header("Content-Type", attachment_mime)
            msg.attach(part)

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, recipient, msg.as_string())
            sent += 1
        except Exception:
            logger.exception(
                "scheduled_digest.email_failed",
                extra={"recipient": recipient},
            )

    return sent


def _build_email_body(brief: Any) -> str:
    lines = [
        f"VeeTrack Executive Digest — {brief.entity_keyword}",
        f"Period: last {brief.window_days} days  ·  {len(brief.stories)} stories",
        "",
    ]
    for i, s in enumerate(brief.stories, 1):
        lines.append(f"{i}. [{s.risk_level.upper()}] {s.title}")
        if s.what_happened:
            lines.append(
                f"   {s.what_happened[:200]}…"
                if len(s.what_happened) > 200
                else f"   {s.what_happened}"
            )
    lines += ["", "See attached for full brief.", "", "— VeeTrack (advisory only)"]
    return "\n".join(lines)
