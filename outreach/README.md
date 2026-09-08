# Outreach Assistant

A human-in-the-loop outreach pipeline layered on top of `job-hunter`. The bot
**researches, filters, matches, and drafts. Riya is the only sender.**

## Hard rules (enforced in code)
1. **Zero LinkedIn access.** LinkedIn appears only as pre-built people-search
   URLs (`outreach/queue.py::linkedin_urls`) that Riya clicks in her own browser.
2. **Nothing is ever sent by the system.** Every item lands in the review queue
   with status `NEEDS_REVIEW`. Only Riya moves items to `SENT`, by hand.
3. **Gmail is read-only** (`gmail.readonly` scope only — `gmail_confirmations.py`).
4. It **reuses** job-hunter's Sheets service account, the job-tracker read-only
   Gmail OAuth pattern, and the existing digest/SMTP machinery.

## Two intake paths
- **Path A — discovered** (`pipeline.process_discovered`): job-hunter's scored
  matches → Filter → Classify → Match → Draft → Queue. Off by default; enable in
  the discovery loop with `OUTREACH_DISCOVERED=1`, or run standalone:
  `python -m outreach.cli poll --source discovered --dry-run`.
- **Path B — applied** (`pipeline.process_applied`): a 4-hourly Gmail scan for
  application-confirmation emails → Claude extraction → Classify → Match → Draft
  → Queue (`source: applied`). This is the default poller and covers 100% of
  applications regardless of where she applied.

## Pipeline stages
`filter.py` (Path A kill-words / level / experience / age / do_not_apply / mega-pool)
→ `classify.py` (keyword rules first, then one Claude call) → `match.py`
(bucket → repo) → `draft.py` (Claude, with a grounded template fallback) →
`queue.py` (the Sheet's **Outreach** tab). Every Claude call degrades gracefully
to a deterministic path when `ANTHROPIC_API_KEY` is absent, so `--dry-run` and
the tests run fully offline.

## One-time setup
1. **Gmail read-only token** (same as job-tracker). Run once locally:
   ```bash
   python ../job-tracker/backend/scripts/get_gmail_token.py --client-secrets-file client.json
   ```
   Copy the printed refresh token into the repo's GitHub secrets.
2. **GitHub secrets** the `Outreach Assistant` workflow needs (most already
   exist for job-hunter/job-tracker):
   - `GOOGLE_SHEETS_ID`, `GOOGLE_CREDENTIALS_JSON` (Sheets service account)
   - `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` (read-only)
   - `ANTHROPIC_API_KEY`
   - `EMAIL_FROM`, `EMAIL_TO`, `EMAIL_APP_PASSWORD` (digest to Riya herself)

## Commands
```bash
# Path B poller (what the 4h cron runs)
python -m outreach.cli poll --source applied
python -m outreach.cli poll --source applied --dry-run   # print, write nothing

# Path A off a fresh scrape
python -m outreach.cli poll --source discovered --dry-run

# Manage the do_not_apply radar as new rejections arrive
python -m outreach.do_not_apply list
python -m outreach.do_not_apply add "Company Name" --rejections 2
python -m outreach.do_not_apply remove "Company Name"
```

## Sheet: the `Outreach` tab
Columns: `date | source | company | role | posting_url | industry | matched_repo
| draft_message | draft_short | linkedin_search_url | linkedin_alumni_url |
status | notes`. The system only ever writes `status = NEEDS_REVIEW`. Dedup:
same company + fuzzy role within 14 days is merged (earliest row kept).

## Tests
`pytest tests/` — filter kill-words + fuzzy company matching, and golden-file
extraction across Workday / Greenhouse / Lever / iCIMS / SuccessFactors. All
offline (no key, no network).
