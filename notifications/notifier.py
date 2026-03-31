"""
Notification system — Email (Gmail SMTP) + Push (ntfy.sh).
"""
import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def send_email(jobs: list[dict]) -> bool:
    """
    Send an HTML email digest of new job matches.
    Uses Gmail SMTP with App Password.
    """
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    app_password = os.getenv("EMAIL_APP_PASSWORD")
    
    if not all([email_from, email_to, app_password]):
        print("[EMAIL] Missing email credentials, skipping notification")
        return False
    
    # Separate high-priority (score >= 70) from others
    high = [j for j in jobs if j.get("score", 0) >= 70]
    medium = [j for j in jobs if 50 <= j.get("score", 0) < 70]
    low = [j for j in jobs if j.get("score", 0) < 50]
    
    # Build HTML email
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 700px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a1a2e; font-size: 22px; margin-bottom: 4px; }}
            .subtitle {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
            .job {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 12px; transition: all 0.2s; }}
            .job:hover {{ border-color: #4a90d9; }}
            .job-high {{ border-left: 4px solid #27ae60; }}
            .job-medium {{ border-left: 4px solid #f39c12; }}
            .job-low {{ border-left: 4px solid #95a5a6; }}
            .job-title {{ font-size: 16px; font-weight: 600; color: #1a1a2e; margin: 0; }}
            .job-company {{ color: #4a90d9; font-size: 14px; margin: 4px 0; }}
            .job-meta {{ color: #666; font-size: 12px; }}
            .score {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 13px; }}
            .score-high {{ background: #d4edda; color: #155724; }}
            .score-medium {{ background: #fff3cd; color: #856404; }}
            .score-low {{ background: #f0f0f0; color: #666; }}
            .apply-btn {{ display: inline-block; padding: 6px 16px; background: #4a90d9; color: white !important; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 500; margin-top: 8px; }}
            .section-title {{ font-size: 15px; font-weight: 600; color: #333; margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #eee; }}
            .h1b-badge {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
            .h1b-yes {{ background: #d4edda; color: #155724; }}
            .h1b-no {{ background: #f8d7da; color: #721c24; }}
            .h1b-unknown {{ background: #e2e3e5; color: #383d41; }}
            .skills {{ color: #666; font-size: 12px; margin-top: 4px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 {len(jobs)} New AI/ML Job Match{'es' if len(jobs) != 1 else ''}</h1>
            <div class="subtitle">{datetime.now().strftime('%B %d, %Y at %I:%M %p')} • Job Hunter Alert</div>
    """
    
    def render_job(j, tier):
        score = j.get('score', 0)
        score_class = 'high' if score >= 70 else ('medium' if score >= 50 else 'low')
        h1b = j.get('h1b_status', 'Unknown')
        h1b_class = 'yes' if 'Sponsor' in h1b else ('no' if 'No' in h1b else 'unknown')
        
        return f"""
            <div class="job job-{tier}">
                <p class="job-title">{j.get('title', 'Unknown')}</p>
                <p class="job-company">{j.get('company', 'Unknown')} • {j.get('location', 'US')}</p>
                <div class="job-meta">
                    <span class="score score-{score_class}">{score}% match</span>
                    <span class="h1b-badge h1b-{h1b_class}">H1B: {h1b}</span>
                    • {j.get('experience_level', '')} • {j.get('source', '')}
                </div>
                <div class="skills">Skills: {j.get('skills_match', 'N/A')}</div>
                <a href="{j.get('url', '#')}" class="apply-btn">Apply Now →</a>
            </div>
        """
    
    if high:
        html += f'<div class="section-title">🔥 High Match ({len(high)})</div>'
        for j in high:
            html += render_job(j, "high")
    
    if medium:
        html += f'<div class="section-title">⭐ Good Match ({len(medium)})</div>'
        for j in medium:
            html += render_job(j, "medium")
    
    if low:
        html += f'<div class="section-title">📋 Worth a Look ({len(low)})</div>'
        for j in low[:10]:  # Cap low-priority at 10
            html += render_job(j, "low")
        if len(low) > 10:
            html += f'<p class="job-meta">...and {len(low) - 10} more in your Google Sheet</p>'
    
    html += """
        </div>
    </body>
    </html>
    """
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎯 {len(jobs)} New AI/ML Jobs • {'🔥 ' + str(len(high)) + ' High Match' if high else 'New matches found'}"
        msg["From"] = email_from
        msg["To"] = email_to
        msg.attach(MIMEText(html, "html"))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_from, app_password)
            server.send_message(msg)
        
        print(f"[EMAIL] Sent digest with {len(jobs)} jobs to {email_to}")
        return True
        
    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")
        return False


def send_push(jobs: list[dict]) -> bool:
    """
    Send push notification via ntfy.sh (free, instant, mobile app available).
    Includes clickable links: tap notification → top job's apply page,
    plus an action button to open the full Google Sheet.
    """
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return False
    
    high = [j for j in jobs if j.get("score", 0) >= 70]
    
    if not high:
        # Only push for high-priority matches
        return False
    
    try:
        title = f"{len(high)} High-Match AI/ML Jobs!"
        body_lines = []
        for j in high[:5]:
            body_lines.append(
                f"- {j['title']} @ {j['company']} ({j['score']}%)"
            )
        body = "\n".join(body_lines)
        if len(high) > 5:
            body += f"\n...and {len(high) - 5} more"
        
        # Top job's apply URL — tapping the notification opens this
        top_url = high[0].get("url", "")
        
        # Google Sheet link for the "View All" action button
        sheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""
        
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": "high",
            "Tags": "fire,briefcase",
            "Content-Type": "text/plain; charset=utf-8",
        }
        
        # Tap notification → open top job's apply link
        if top_url:
            headers["Click"] = top_url
        
        # Add action buttons for each top job (up to 3) + Google Sheet
        actions = []
        for j in high[:3]:
            url = j.get("url", "")
            if url:
                label = f"Apply: {j['company']}"[:40]
                actions.append(f"view, {label}, {url}")
        if sheet_url:
            actions.append(f"view, Open Google Sheet, {sheet_url}")
        
        if actions:
            headers["Actions"] = "; ".join(actions)
        
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        print(f"[NTFY] Push sent for {len(high)} high-match jobs")
        return True
        
    except Exception as e:
        print(f"[NTFY] Failed: {e}")
        return False


def notify(jobs: list[dict]) -> dict:
    """Send all notifications for a batch of new jobs."""
    if not jobs:
        print("[NOTIFY] No new jobs to notify about")
        return {"email": False, "push": False}
    
    min_score = float(os.getenv("NOTIFY_MIN_SCORE", 30))
    notify_jobs = [j for j in jobs if j.get("score", 0) >= min_score]
    
    if not notify_jobs:
        print(f"[NOTIFY] No jobs above score threshold ({min_score})")
        return {"email": False, "push": False}
    
    email_sent = send_email(notify_jobs)
    push_sent = send_push(notify_jobs)
    
    return {"email": email_sent, "push": push_sent}