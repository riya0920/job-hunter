"""SQLite state for the outreach pipeline — reuses job-hunter's jobs.db.

Two tables:
  * outreach_meta   — small key/value store (e.g. last-seen Gmail timestamp)
  * outreach_items  — one row per queued item, for cross-path dedup

Dedup: same company + fuzzy role title within DEDUP_WINDOW_DAYS is a duplicate;
the earliest row wins and the newer sighting just appends a note.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from storage.db import get_connection  # reuse the existing DB + path

from . import config, do_not_apply


def init() -> None:
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outreach_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS outreach_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            company_norm  TEXT,
            role_norm     TEXT,
            company       TEXT,
            role          TEXT,
            source        TEXT,
            url           TEXT,
            first_date    TEXT,
            status        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outreach_company ON outreach_items(company_norm);
        """
    )
    conn.commit()
    conn.close()


# ── meta kv ─────────────────────────────────────────────────────────────────
def get_meta(key: str) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT value FROM outreach_meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO outreach_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_last_gmail_ts() -> Optional[float]:
    v = get_meta("last_gmail_ts")
    return float(v) if v else None


def set_last_gmail_ts(ts: float) -> None:
    set_meta("last_gmail_ts", str(ts))


# ── dedup ───────────────────────────────────────────────────────────────────
def _role_norm(role: str) -> str:
    return do_not_apply.normalize(role or "")


def find_duplicate(company: str, role: str, within_days: int = None) -> Optional[dict]:
    """Return an existing row for the same company + fuzzy role within the window."""
    within_days = within_days or config.DEDUP_WINDOW_DAYS
    cutoff = (datetime.utcnow() - timedelta(days=within_days)).isoformat()
    cnorm = do_not_apply.normalize(company)
    rnorm = _role_norm(role)
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM outreach_items WHERE company_norm = ? AND first_date >= ?",
        (cnorm, cutoff),
    ).fetchall()
    conn.close()
    for r in rows:
        other = r["role_norm"] or ""
        if other == rnorm:
            return dict(r)
        # fuzzy: token subset either direction (e.g. "ml engineer" vs "ml engineer ii")
        a, b = set(rnorm.split()), set(other.split())
        if a and b and (a <= b or b <= a):
            return dict(r)
    return None


def record_item(company: str, role: str, source: str, url: str, status: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO outreach_items "
        "(company_norm, role_norm, company, role, source, url, first_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            do_not_apply.normalize(company),
            _role_norm(role),
            company,
            role,
            source,
            url,
            datetime.utcnow().isoformat(),
            status,
        ),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id
