"""Path B — poll Gmail (READ-ONLY) for application-confirmation emails.

Reuses the job-tracker OAuth pattern exactly: a stored refresh token and the
gmail.readonly scope and nothing else. In production only three env vars are
needed (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN); no browser
flow ever runs on the server. Obtain the token once with
job-tracker/backend/scripts/get_gmail_token.py.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from . import config

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class Confirmation:
    gmail_id: str
    sender: str
    subject: str
    body: str
    ts: float  # unix seconds


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def credentials_present() -> bool:
    return all(os.getenv(k) for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"))


def _header(headers: list[dict], name: str) -> str:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def _b64(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> str:
    def walk(part) -> Optional[str]:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if mime == "text/plain" and data:
            return _b64(data)
        for sub in part.get("parts", []) or []:
            got = walk(sub)
            if got:
                return got
        if mime == "text/html" and data:
            return re.sub(r"<[^>]+>", " ", _b64(data))
        return None

    return (walk(payload) or "").strip()


def fetch_confirmations(after_ts: Optional[float], max_results: int = 50,
                        lookback_days: int = 7) -> Iterable[Confirmation]:
    """Yield confirmation emails newer than after_ts (unix seconds).

    after_ts=None → first run: look back `lookback_days`.
    """
    service = _service()
    query = config.CONFIRMATION_QUERY
    query += f" after:{int(after_ts)}" if after_ts else f" newer_than:{lookback_days}d"
    query += " -in:chats"

    ids: list[str] = []
    page_token = None
    while len(ids) < max_results:
        resp = (
            service.users().messages()
            .list(userId="me", q=query, maxResults=min(100, max_results - len(ids)), pageToken=page_token)
            .execute()
        )
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    for gid in ids[:max_results]:
        msg = service.users().messages().get(userId="me", id=gid, format="full").execute()
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        yield Confirmation(
            gmail_id=gid,
            sender=_header(headers, "From"),
            subject=_header(headers, "Subject"),
            body=_extract_body(payload) or msg.get("snippet", ""),
            ts=int(msg.get("internalDate", "0")) / 1000.0,
        )
