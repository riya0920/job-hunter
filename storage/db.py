"""
SQLite-backed storage for job deduplication and history tracking.
"""
import sqlite3
import hashlib
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jobs.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            url_hash TEXT PRIMARY KEY,
            title_company_hash TEXT,
            title TEXT,
            company TEXT,
            url TEXT,
            first_seen TEXT,
            score REAL DEFAULT 0,
            notified INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_title_company ON seen_jobs(title_company_hash);
        CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_jobs(first_seen);

        CREATE TABLE IF NOT EXISTS h1b_sponsors (
            company_name TEXT PRIMARY KEY,
            approvals INTEGER DEFAULT 0,
            last_updated TEXT
        );
    """)
    conn.commit()
    conn.close()


def _hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


def is_duplicate(url: str, title: str, company: str) -> bool:
    """Check if we've already seen this job (by URL or title+company)."""
    conn = get_connection()
    url_hash = _hash(url)
    tc_hash = _hash(f"{title}|{company}")

    row = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE url_hash = ? OR title_company_hash = ?",
        (url_hash, tc_hash)
    ).fetchone()
    conn.close()
    return row is not None


def mark_seen(url: str, title: str, company: str, score: float = 0):
    """Record a job as seen."""
    conn = get_connection()
    url_hash = _hash(url)
    tc_hash = _hash(f"{title}|{company}")

    conn.execute("""
        INSERT OR IGNORE INTO seen_jobs 
        (url_hash, title_company_hash, title, company, url, first_seen, score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url_hash, tc_hash, title, company, url,
          datetime.utcnow().isoformat(), score))
    conn.commit()
    conn.close()


def mark_notified(url: str):
    """Mark job as having been included in a notification."""
    conn = get_connection()
    url_hash = _hash(url)
    conn.execute("UPDATE seen_jobs SET notified = 1 WHERE url_hash = ?", (url_hash,))
    conn.commit()
    conn.close()


def cleanup_old(days: int = 60):
    """Remove entries older than N days."""
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM seen_jobs WHERE first_seen < ?", (cutoff,))
    conn.commit()
    conn.close()


def get_stats():
    """Return basic stats about the database."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM seen_jobs WHERE first_seen >= ?",
        (datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat(),)
    ).fetchone()[0]
    conn.close()
    return {"total_jobs_tracked": total, "new_today": today}


# Initialize on import
init_db()
