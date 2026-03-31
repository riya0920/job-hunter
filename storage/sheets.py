"""
Google Sheets integration — writes job data and manages formatting.
"""
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Column headers
HEADERS = [
    "Date Found", "Score", "Title", "Company", "Location",
    "Job Type", "Apply Link", "H1B Status", "Experience Level",
    "Key Skills Match", "Source", "Description Preview"
]


def get_client():
    """Authenticate and return gspread client."""
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    return gspread.authorize(creds)


def ensure_headers(sheet):
    """Add headers if the sheet is empty."""
    try:
        first_row = sheet.row_values(1)
        if not first_row or first_row[0] != HEADERS[0]:
            sheet.insert_row(HEADERS, 1)
            # Bold the header row
            sheet.format("1:1", {
                "textFormat": {"bold": True, "fontSize": 11},
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.7},
                "horizontalAlignment": "CENTER",
                "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
            })
    except Exception:
        sheet.insert_row(HEADERS, 1)


def write_jobs(jobs: list[dict]):
    """
    Write a batch of jobs to Google Sheets.
    Each job dict should have: title, company, location, url, score, 
    h1b_status, experience_level, skills_match, source, description_preview, job_type
    """
    if not jobs:
        return 0

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheet_id:
        print("[SHEETS] No GOOGLE_SHEETS_ID set, skipping sheets write")
        return 0

    try:
        gc = get_client()
        spreadsheet = gc.open_by_key(sheet_id)

        # Use or create the "Job Matches" worksheet
        try:
            sheet = spreadsheet.worksheet("Job Matches")
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet("Job Matches", rows=1000, cols=len(HEADERS))

        ensure_headers(sheet)

        # Build rows — sorted by score (highest first)
        rows = []
        for job in sorted(jobs, key=lambda j: j.get("score", 0), reverse=True):
            url = job.get("url", "")
            title = job.get("title", "Unknown")
            
            # Create clickable hyperlink
            apply_link = f'=HYPERLINK("{url}", "Apply →")' if url else ""
            
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                round(job.get("score", 0), 1),
                title,
                job.get("company", "Unknown"),
                job.get("location", "US"),
                job.get("job_type", "Full-time"),
                apply_link,
                job.get("h1b_status", "Unknown"),
                job.get("experience_level", "Entry"),
                job.get("skills_match", ""),
                job.get("source", ""),
                (job.get("description_preview", "") or "")[:200]
            ]
            rows.append(row)

        # Batch append (one API call)
        sheet.append_rows(rows, value_input_option="USER_ENTERED")

        # Color-code score column (column B) for newly added rows
        total_rows = len(sheet.get_all_values())
        start_row = total_rows - len(rows) + 1
        
        for i, job in enumerate(sorted(jobs, key=lambda j: j.get("score", 0), reverse=True)):
            row_num = start_row + i
            score = job.get("score", 0)
            if score >= 75:
                color = {"red": 0.56, "green": 0.93, "blue": 0.56}  # green
            elif score >= 50:
                color = {"red": 1.0, "green": 0.95, "blue": 0.6}    # yellow
            else:
                color = {"red": 1.0, "green": 0.8, "blue": 0.8}     # light red

            sheet.format(f"B{row_num}", {"backgroundColor": color})

        print(f"[SHEETS] Wrote {len(rows)} jobs to Google Sheets")
        return len(rows)

    except Exception as e:
        print(f"[SHEETS] Error writing to sheets: {e}")
        return 0
