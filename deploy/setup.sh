#!/usr/bin/env bash
# ============================================================
# Job Hunter — one-time setup on an Oracle Cloud Always-Free ARM VM
# (Ubuntu 22.04/24.04). Run as the 'ubuntu' user.
#
#   bash deploy/setup.sh
#
# Before running, make sure these files exist in the repo root:
#   .env              (copy from deploy/jobhunter.env.example, fill in secrets)
#   credentials.json  (Google service-account key for Sheets)
#   resume.txt        (your resume text — used for scoring + tailored pitches)
# ============================================================
set -euo pipefail

APP_DIR="/home/ubuntu/job-hunter"
cd "$APP_DIR"

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

echo "==> Creating virtualenv + installing deps"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "==> Checking required files"
for f in .env credentials.json resume.txt; do
  if [[ ! -f "$APP_DIR/$f" ]]; then
    echo "!! Missing $APP_DIR/$f — create it before starting the timers."
  fi
done

echo "==> Installing systemd units"
sudo cp deploy/jobhunter.service            /etc/systemd/system/
sudo cp deploy/jobhunter.timer              /etc/systemd/system/
sudo cp deploy/jobhunter-aggregators.service /etc/systemd/system/
sudo cp deploy/jobhunter-aggregators.timer   /etc/systemd/system/
sudo cp deploy/jobhunter-heartbeat.service   /etc/systemd/system/
sudo cp deploy/jobhunter-heartbeat.timer     /etc/systemd/system/

echo "==> Enabling timers"
sudo systemctl daemon-reload
sudo systemctl enable --now jobhunter.timer
sudo systemctl enable --now jobhunter-aggregators.timer
sudo systemctl enable --now jobhunter-heartbeat.timer

echo ""
echo "==> Done. Useful commands:"
echo "   systemctl list-timers | grep jobhunter     # see next run times"
echo "   sudo systemctl start jobhunter.service     # run one scan right now"
echo "   journalctl -u jobhunter.service -f         # live logs"
echo ""
echo "   First run seeds the DB SILENTLY (cold-start guard) — you won't get a"
echo "   flood. Real alerts begin from the second run onward."
