# 🎯 Job Hunter

**Automated AI/ML job discovery and alerting system. Finds freshly posted AI/ML jobs across 30+ sources, scores them against your resume, writes to Google Sheets, and notifies you within minutes. Runs serverlessly for $0/month.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/riya0920/job-hunter/blob/main/LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## What It Does

Every 5 minutes, Job Hunter:

1. **Scrapes job boards at the SOURCE, concurrently**: Greenhouse, Lever, Ashby, **SmartRecruiters, and Workday** ATS APIs (direct JSON, no auth) — ~100 boards swept in seconds. This is where jobs appear FIRST, before LinkedIn/Indeed syndication. (LinkedIn/Indeed via JobSpy are still available as an opt-in backup, `--with-aggregators`, run only a few times a day.)
2. **Filters intelligently**: AI/ML **and** software-engineering roles, entry-level/new grad (0 to 3 years), US-based. ML/AI roles score a notch above general SWE so they float to the top.
3. **Scores against your resume**: TF-IDF keyword matching plus AI/ML relevance scoring
4. **Flags freshness**: shows "posted X min ago" and marks anything posted within 15 min as **🔥 URGENT**, floated to the top so you hit the truly-fresh ones first
5. **Cold-start guard**: the first time it polls a company, it silently seeds that board's existing jobs — so adding a company never floods you. Only jobs posted *after* that first poll alert you.
6. **Detects H1B sponsorship**: keyword analysis on job descriptions
7. **Deduplicates**: SQLite-backed URL + title/company hashing (never see the same job twice)
8. **Instant-apply assist**: for strong matches, drafts a one-line résumé-grounded pitch via Gemini and drops it into the alert — so you apply within minutes, not hours
9. **Writes to Google Sheets**, **emails an HTML digest**, and **pushes ntfy alerts on every match** (with a daily heartbeat so silence never means "broken")

## Quick Start (5 minutes)

### 1. Clone & Install

```bash
git clone https://github.com/riya0920/job-hunter.git
cd job-hunter
pip install -r requirements.txt
```

### 2. Set Up Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project, then enable **Google Sheets API** and **Google Drive API**
3. Go to **Credentials** → Create **Service Account** → Download JSON key
4. Save it as `credentials.json` in the project root
5. Create a new Google Sheet, then copy its ID from the URL (`https://docs.google.com/spreadsheets/d/THIS_PART/edit`)
6. **Share the sheet** with your service account email (found in `credentials.json` as `client_email`)

### 3. Set Up Gmail Notifications

1. Enable 2FA on your Gmail: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to **App Passwords** and generate one for "Mail"
3. Copy the 16-character password

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values:
#   GOOGLE_SHEETS_ID=your_sheet_id
#   EMAIL_FROM=your.email@gmail.com
#   EMAIL_TO=your.email@gmail.com
#   EMAIL_APP_PASSWORD=your_app_password
```

### 5. Add Your Resume

Replace `resume.txt` with your actual resume text. This is used for scoring.

### 6. Run It

```bash
# Full run (scrapes everything, writes to sheets, sends email)
python main.py

# Quick test (ATS APIs only, fast, always works)
python main.py --ats-only

# Dry run (scrape and score, no notifications)
python main.py --dry-run

# Check stats
python main.py --stats
```

## Deploy Free (Run Every 5 to 10 Min Without Your Laptop)

### Option A: GitHub Actions (Easiest, 15 min interval)

1. Fork or clone this repo into your own GitHub account
2. Go to **Settings → Secrets → Actions** and add these secrets:
   * `GOOGLE_SHEETS_ID`
   * `GOOGLE_CREDENTIALS_JSON` (base64-encode your credentials.json: `base64 -w0 credentials.json`)
   * `EMAIL_FROM`, `EMAIL_TO`, `EMAIL_APP_PASSWORD`
   * `NTFY_TOPIC` (optional)
3. The workflow at `.github/workflows/job_hunter.yml` runs every 15 minutes automatically

### Option B: Google Cloud Functions (Best, 5 min interval, free tier)

```bash
# Install gcloud CLI, then:
gcloud projects create job-hunter-project
gcloud config set project job-hunter-project

# Enable APIs
gcloud services enable cloudfunctions.googleapis.com cloudscheduler.googleapis.com pubsub.googleapis.com

# Create Pub/Sub topic
gcloud pubsub topics create job-scan

# Deploy
gcloud functions deploy job_hunter \
    --gen2 \
    --runtime python312 \
    --trigger-topic job-scan \
    --memory 512MB \
    --timeout 120 \
    --set-env-vars GOOGLE_SHEETS_ID=xxx,EMAIL_FROM=xxx,EMAIL_TO=xxx,EMAIL_APP_PASSWORD=xxx

# Schedule every 10 minutes
gcloud scheduler jobs create pubsub job-scan-schedule \
    --schedule="*/10 * * * *" \
    --topic=job-scan \
    --message-body="run" \
    --location=us-central1
```

Free tier: 2M invocations per month plus 400K GB-seconds. This uses approximately 8,640 invocations per month, well within limits.

### Option C: Oracle Cloud Always-Free VM ⭐ RECOMMENDED (true 5-min interval)

GitHub Actions cron is frequently **late or skipped** — which defeats the whole
point of being early. An always-on VM with systemd timers fires *on time*, every
time. Everything is scripted in [`deploy/`](deploy/).

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (Always Free tier) and
   create an **ARM VM** (Ubuntu 22.04/24.04, 4 OCPU / 24 GB, free forever).
2. SSH in and clone:
   ```bash
   git clone https://github.com/riya0920/job-hunter.git /home/ubuntu/job-hunter
   cd /home/ubuntu/job-hunter
   ```
3. Create three files in the repo root:
   * `.env` — copy from [`deploy/jobhunter.env.example`](deploy/jobhunter.env.example) and fill in secrets
   * `credentials.json` — your Google service-account key
   * `resume.txt` — your résumé text
4. Run the installer (creates the venv, installs deps, installs + enables the timers):
   ```bash
   bash deploy/setup.sh
   ```

That's it. Three systemd timers are now running:

| Timer | What | When |
|-------|------|------|
| `jobhunter.timer` | Fast ATS-direct scan | **every 5 min** |
| `jobhunter-aggregators.timer` | LinkedIn/Indeed backup (JobSpy) | 3×/day |
| `jobhunter-heartbeat.timer` | "still alive" ping | daily |

Handy commands:
```bash
systemctl list-timers | grep jobhunter    # next run times
sudo systemctl start jobhunter.service     # run a scan right now
journalctl -u jobhunter.service -f         # live logs
```
The **first run seeds the DB silently** (cold-start guard) — real alerts begin on
the second run. Because the DB lives on the VM, dedup persists naturally across
runs (no cache juggling like GitHub Actions needs).

## Customization

### Add More Companies

Edit `config/search_config.yaml`:

```yaml
greenhouse_companies:
  - anthropic
  - your-company-slug    # Find slug from boards.greenhouse.io/{slug}

lever_companies:
  - openai
  - another-company      # Find slug from jobs.lever.co/{slug}
```

### Adjust Scoring

* `min_score`: Minimum score to include in Google Sheets (default: 30)
* `notify_score`: Minimum score to trigger email (default: 50)
* Modify `relevance_keywords` to match your specific skills

### Search Queries

Add or remove queries in `search_queries` to target different roles.

## Architecture

```
main.py                    ← Orchestrator
├── scrapers/
│   ├── ats_scraper.py     ← Greenhouse/Lever/Ashby JSON APIs
│   └── jobspy_scraper.py  ← LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter
├── processors/
│   └── scorer.py          ← Experience filter, H1B detection, resume scoring
├── storage/
│   ├── db.py              ← SQLite deduplication
│   └── sheets.py          ← Google Sheets writer
├── notifications/
│   └── notifier.py        ← Email (Gmail) + Push (ntfy.sh)
└── config/
    └── search_config.yaml ← All search params, company lists, keywords
```

## Cost Breakdown

| Component | Cost |
| --- | --- |
| Infrastructure (GCF / GitHub Actions / Oracle) | $0/month |
| Google Sheets API | Free |
| Gmail SMTP | Free (500 emails/day) |
| ntfy.sh push notifications | Free |
| ATS APIs (Greenhouse/Lever/Ashby) | Free, no auth |
| JobSpy (LinkedIn/Indeed) | Free, open source |
| **Total** | **$0/month** |

Optional: Anthropic API for LLM-powered scoring (approximately $3 to $10/month at 100 jobs/day). Not required. The TF-IDF plus relevance scoring works well without it.

## License

MIT

## Author

**Riya Soni** · MS Computer Science, Stevens Institute of Technology  
[GitHub](https://github.com/riya0920) · [LinkedIn](https://linkedin.com/in/riya-soni-ml-engineer)
