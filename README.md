# 🎯 Job Hunter — Automated AI/ML Job Discovery & Alert System

Finds freshly posted AI/ML jobs across 30+ sources, scores them against your resume, writes to Google Sheets, and notifies you within minutes — all running serverlessly for **$0/month**.

## What It Does

Every 5–15 minutes, Job Hunter:

1. **Scrapes 30+ job sources** — Greenhouse, Lever, Ashby ATS APIs (direct JSON, no auth needed) + LinkedIn, Indeed, Glassdoor, Google Jobs, ZipRecruiter via JobSpy
2. **Filters intelligently** — only AI/ML roles, entry-level/new grad (0–3 years), US-based
3. **Scores against your resume** — TF-IDF keyword matching + AI/ML relevance scoring
4. **Detects H1B sponsorship** — keyword analysis on job descriptions
5. **Deduplicates** — SQLite-backed URL + title/company hashing (never see the same job twice)
6. **Writes to Google Sheets** — color-coded by match score, with clickable Apply links
7. **Emails you a digest** — beautifully formatted HTML with scores, H1B status, and skills match
8. **Push notifications** — instant alerts via ntfy.sh for high-match jobs (optional)

## Quick Start (5 minutes)

### 1. Clone & Install

```bash
git clone <your-repo-url> job-hunter
cd job-hunter
pip install -r requirements.txt
```

### 2. Set Up Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project → Enable **Google Sheets API** + **Google Drive API**
3. Go to **Credentials** → Create **Service Account** → Download JSON key
4. Save it as `credentials.json` in the project root
5. Create a new Google Sheet → copy its ID from the URL (`https://docs.google.com/spreadsheets/d/THIS_PART/edit`)
6. **Share the sheet** with your service account email (found in credentials.json as `client_email`)

### 3. Set Up Gmail Notifications

1. Enable 2FA on your Gmail: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to **App Passwords** → Generate one for "Mail"
3. Copy the 16-character password

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values:
#   GOOGLE_SHEETS_ID=your_sheet_id
#   EMAIL_FROM=riyassoni@gmail.com
#   EMAIL_TO=riyassoni@gmail.com
#   EMAIL_APP_PASSWORD=your_app_password
```

### 5. Add Your Resume

Replace `resume.txt` with your actual resume text. This is used for scoring.

### 6. Run It

```bash
# Full run (scrapes everything, writes to sheets, sends email)
python main.py

# Quick test (ATS APIs only — fast, always works)
python main.py --ats-only

# Dry run (scrape & score, no notifications)
python main.py --dry-run

# Check stats
python main.py --stats
```

## Deploy Free (Run Every 5–10 Min Without Your Laptop)

### Option A: GitHub Actions (Easiest — 15 min interval)

1. Push this repo to a **private** GitHub repo
2. Go to **Settings → Secrets → Actions** and add these secrets:
   - `GOOGLE_SHEETS_ID`
   - `GOOGLE_CREDENTIALS_JSON` (base64-encode your credentials.json: `base64 -w0 credentials.json`)
   - `EMAIL_FROM`, `EMAIL_TO`, `EMAIL_APP_PASSWORD`
   - `NTFY_TOPIC` (optional)
3. The workflow at `.github/workflows/job_hunter.yml` runs every 15 minutes automatically

### Option B: Google Cloud Functions (Best — 5 min interval, free tier)

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

Free tier: 2M invocations/month + 400K GB-seconds. This uses ~8,640 invocations/month = well within limits.

### Option C: Oracle Cloud Always Free VM (Most Powerful — any interval)

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (Always Free tier)
2. Create an ARM VM (4 OCPU, 24 GB RAM — free forever)
3. SSH in, clone repo, install deps
4. Add to crontab: `*/5 * * * * cd /home/ubuntu/job-hunter && python main.py >> /var/log/job-hunter.log 2>&1`

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

- `min_score`: Minimum score to include in Google Sheets (default: 30)
- `notify_score`: Minimum score to trigger email (default: 50)
- Modify `relevance_keywords` to match your specific skills

### Search Queries

Add/remove queries in `search_queries` to target different roles.

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
|-----------|------|
| Infrastructure (GCF / GitHub Actions / Oracle) | $0/month |
| Google Sheets API | Free |
| Gmail SMTP | Free (500 emails/day) |
| ntfy.sh push notifications | Free |
| ATS APIs (Greenhouse/Lever/Ashby) | Free, no auth |
| JobSpy (LinkedIn/Indeed) | Free, open source |
| **Total** | **$0/month** |

Optional: Anthropic API for LLM-powered scoring (~$3–10/month at 100 jobs/day) — not required, the TF-IDF + relevance scoring works well without it.
