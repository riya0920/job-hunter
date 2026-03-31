"""
Google Cloud Function entry point.
Deploy with: gcloud functions deploy job_hunter --runtime python312 --trigger-topic job-scan --memory 512MB

Then create a Cloud Scheduler:
gcloud scheduler jobs create pubsub job-scan-schedule \
    --schedule="*/10 * * * *" \
    --topic=job-scan \
    --message-body="run" \
    --location=us-central1
"""
import functions_framework
import base64
from main import run


@functions_framework.cloud_event
def job_hunter(cloud_event):
    """Cloud Function entry point — triggered by Pub/Sub."""
    print("Job Hunter triggered by Cloud Scheduler")
    run(dry_run=False, ats_only=False)
    return "OK"
