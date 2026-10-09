#!/usr/bin/env bash
# One-command desktop setup for the job-hunt agent (macOS / Linux).
#   curl -fsSL https://raw.githubusercontent.com/lakshmipavanipv/Housing-Ads/claude/awesome-cannon-7zgrea/job-hunt/setup_desktop.sh | bash
# Safe to re-run: it updates the code and never touches job-hunt/private/ data.
set -euo pipefail

REPO=https://github.com/lakshmipavanipv/Housing-Ads.git
BRANCH=claude/awesome-cannon-7zgrea
DIR="${JOB_HUNT_DIR:-$HOME/Housing-Ads}"

say() { printf '\n==> %s\n' "$*"; }

say "Getting the code into $DIR"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch origin "$BRANCH"
  git -C "$DIR" checkout -B "$BRANCH" "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

say "Installing Python packages"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q python-docx openpyxl pyyaml

say "Checking LibreOffice (turns resumes into PDFs)"
if command -v soffice >/dev/null || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
  echo "LibreOffice found."
elif command -v brew >/dev/null; then
  brew install --cask libreoffice
else
  echo "!! Install LibreOffice from https://www.libreoffice.org/download/ then re-run this script."
fi

say "Creating private folders (git-ignored, never uploaded)"
mkdir -p job-hunt/private/resume/tailored job-hunt/private/edits
[ -f job-hunt/private/applicant-profile.yaml ] || \
  cp job-hunt/applicant-profile.example.yaml job-hunt/private/applicant-profile.yaml
[ -f job-hunt/private/Job-Tracker.xlsx ] || .venv/bin/python job-hunt/tracker.py init

if [ -f job-hunt/private/resume/original.docx ]; then
  say "Building the Hyderabad base resume"
  .venv/bin/python job-hunt/tailor_resume.py base
fi

say "Done. Remaining one-time steps:"
cat <<EOF
  1. Copy your resume to:  $DIR/job-hunt/private/resume/original.docx
     then run:             cd "$DIR" && .venv/bin/python job-hunt/tailor_resume.py base
  2. Fill in:              $DIR/job-hunt/private/applicant-profile.yaml
  3. In Chrome (with the Claude in Chrome extension): log in to LinkedIn and Gmail.
  4. Claude desktop app -> Scheduled -> New task, daily 09:00, folder: $DIR
     Prompt: Run the daily job-hunt agent: follow job-hunt/AGENT_DAILY.md exactly, using Claude in Chrome and the Gmail connector.
EOF
