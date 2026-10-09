# One-command desktop setup for the job-hunt agent (Windows PowerShell).
#   irm https://raw.githubusercontent.com/lakshmipavanipv/Housing-Ads/claude/awesome-cannon-7zgrea/job-hunt/setup_desktop.ps1 | iex
# Safe to re-run: it updates the code and never touches job-hunt\private\ data.
$ErrorActionPreference = "Stop"

$Repo   = "https://github.com/lakshmipavanipv/Housing-Ads.git"
$Branch = "claude/awesome-cannon-7zgrea"
$Dir    = if ($env:JOB_HUNT_DIR) { $env:JOB_HUNT_DIR } else { Join-Path $HOME "Housing-Ads" }

function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Say "Getting the code into $Dir"
if (Test-Path (Join-Path $Dir ".git")) {
  git -C $Dir fetch origin $Branch
  git -C $Dir checkout -B $Branch "origin/$Branch"
} else {
  git clone --branch $Branch $Repo $Dir
}
Set-Location $Dir

Say "Installing Python packages"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q python-docx openpyxl pyyaml

Say "Checking LibreOffice (turns resumes into PDFs)"
if ((Get-Command soffice -ErrorAction SilentlyContinue) -or
    (Test-Path "C:\Program Files\LibreOffice\program\soffice.exe")) {
  Write-Host "LibreOffice found."
} else {
  winget install --id TheDocumentFoundation.LibreOffice -e --accept-source-agreements --accept-package-agreements
}

Say "Creating private folders (git-ignored, never uploaded)"
New-Item -ItemType Directory -Force job-hunt\private\resume\tailored, job-hunt\private\edits | Out-Null
if (-not (Test-Path job-hunt\private\applicant-profile.yaml)) {
  Copy-Item job-hunt\applicant-profile.example.yaml job-hunt\private\applicant-profile.yaml
}
if (-not (Test-Path job-hunt\private\Job-Tracker.xlsx)) {
  & .\.venv\Scripts\python.exe job-hunt\tracker.py init
}
if (Test-Path job-hunt\private\resume\original.docx) {
  Say "Building the Hyderabad base resume"
  & .\.venv\Scripts\python.exe job-hunt\tailor_resume.py base
}

Say "Done. Remaining one-time steps:"
Write-Host @"
  1. Copy your resume to:  $Dir\job-hunt\private\resume\original.docx
     then run:             .venv\Scripts\python job-hunt\tailor_resume.py base
  2. Fill in:              $Dir\job-hunt\private\applicant-profile.yaml
  3. In Chrome (with the Claude in Chrome extension): log in to LinkedIn and Gmail.
  4. Claude desktop app -> Scheduled -> New task, daily 09:00, folder: $Dir
     Prompt: Run the daily job-hunt agent: follow job-hunt/AGENT_DAILY.md exactly, using Claude in Chrome and the Gmail connector.
"@
