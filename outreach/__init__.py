"""Outreach Assistant — human-in-the-loop outreach pipeline for job-hunter.

The bot researches, filters, matches, and drafts. Riya is the ONLY sender.

Hard rules (enforced in code):
  1. Zero LinkedIn access. LinkedIn appears only as pre-built search URLs.
  2. Nothing is ever sent by the system. Every item lands in the review queue
     with status NEEDS_REVIEW. Only Riya moves items to SENT, by hand.
  3. Gmail access is read-only (gmail.readonly scope only).
  4. This is an extension. It reuses job-hunter's Google auth, Sheets, and the
     job-tracker read-only Gmail OAuth pattern.
"""

__all__ = ["config"]
