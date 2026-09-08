"""Outreach digest — a morning section for the existing Gmail digest.

Renders "N drafts ready for review" with company/role lines, a link to the
sheet, and any Path B radar warnings. Sending reuses the same Gmail SMTP app
password the notifier already uses. This is a separate, low-frequency email so
it never disturbs the 5-minute discovery loop.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config


def _sheet_url() -> str:
    sid = os.getenv("GOOGLE_SHEETS_ID", "")
    return f"https://docs.google.com/spreadsheets/d/{sid}" if sid else ""


def build_html(items: list[dict], warnings: list[str] | None = None,
               dropped: list[dict] | None = None) -> str:
    warnings = warnings or []
    dropped = dropped or []
    url = _sheet_url()
    link = f'<a href="{url}#gid=0">Open the Outreach tab →</a>' if url else "(set GOOGLE_SHEETS_ID)"

    parts = [
        "<div style=\"font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:680px\">",
        f"<h2 style=\"margin-bottom:4px\">✍️ {len(items)} draft"
        f"{'s' if len(items) != 1 else ''} ready for review</h2>",
        f"<div style=\"color:#666;font-size:13px;margin-bottom:14px\">Every item is "
        f"NEEDS_REVIEW. Nothing was sent. {link}</div>",
    ]

    if warnings:
        parts.append('<div style="background:#fff3cd;border:1px solid #ffe08a;border-radius:8px;'
                     'padding:10px 14px;margin-bottom:14px">')
        for w in warnings:
            parts.append(f'<div style="font-size:13px;color:#856404">{w}</div>')
        parts.append("</div>")

    for it in items:
        parts.append(
            '<div style="border:1px solid #e0e0e0;border-left:4px solid #4a90d9;'
            'border-radius:8px;padding:12px 14px;margin-bottom:10px">'
            f'<div style="font-weight:600">{it.get("company","?")} — {it.get("role","?")}</div>'
            f'<div style="color:#666;font-size:12px">{it.get("source","")} · '
            f'{it.get("industry","")} · {it.get("matched_repo","")}</div>'
            f'<div style="font-size:13px;margin-top:6px">{it.get("draft_message","")}</div>'
            + (f'<div style="font-size:12px;color:#a15;margin-top:4px">{it.get("notes","")}</div>'
               if it.get("notes") else "")
            + "</div>"
        )

    if dropped:
        parts.append(f'<h3 style="margin-top:18px;font-size:14px">Filtered out this run ({len(dropped)})</h3>')
        parts.append('<div style="font-size:12px;color:#666">')
        for d in dropped[:25]:
            parts.append(f'• {d.get("company","?")} — {d.get("role","?")}: {d.get("reason","")}<br>')
        parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)


def build_text(items: list[dict], warnings: list[str] | None = None) -> str:
    lines = [f"{len(items)} drafts ready for review (all NEEDS_REVIEW; nothing sent)."]
    for w in (warnings or []):
        lines.append(w)
    for it in items:
        lines.append(f"- {it.get('company','?')} — {it.get('role','?')} "
                     f"[{it.get('source','')}/{it.get('industry','')}]")
    u = _sheet_url()
    if u:
        lines.append(f"Sheet: {u}")
    return "\n".join(lines)


def send_digest(items: list[dict], warnings: list[str] | None = None,
                dropped: list[dict] | None = None) -> bool:
    """Send the outreach digest email. No-op (returns False) if nothing to say."""
    warnings = warnings or []
    if not items and not warnings:
        print("[OUTREACH DIGEST] Nothing to report")
        return False

    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    app_password = os.getenv("EMAIL_APP_PASSWORD")
    if not all([email_from, email_to, app_password]):
        print("[OUTREACH DIGEST] Missing email credentials, skipping")
        return False

    html = build_html(items, warnings, dropped)
    msg = MIMEMultipart("alternative")
    n = len(items)
    warn = " · ⚠️ radar" if warnings else ""
    msg["Subject"] = f"✍️ {n} outreach draft{'s' if n != 1 else ''} to review{warn}"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(build_text(items, warnings), "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_from, app_password)
            server.send_message(msg)
        print(f"[OUTREACH DIGEST] Sent — {n} drafts, {len(warnings)} warnings")
        return True
    except Exception as e:
        print(f"[OUTREACH DIGEST] Failed: {e}")
        return False
