# Job Hunt Agent: Hyderabad, Senior Manager and above, Data & Analytics

Every morning on your laptop, Claude:
1. finds new Hyderabad roles at Senior Manager level or above, **GCCs first**;
2. tailors your resume to each job description;
3. applies in your Chrome: LinkedIn → Apply → company site → sign in or create the account → fill the form → upload → submit (up to 30 a day);
4. checks Gmail for interviews and sends you a summary on your phone.

Full instructions for the agent: [`AGENT_DAILY.md`](AGENT_DAILY.md).

## Privacy
This repo is **public**. Your resume, tracker and form answers live in `job-hunt/private/`, which git ignores, so they never get uploaded. Passwords are only ever kept in Chrome's password manager.

## One-time setup (about 20 minutes)
1. **On your laptop:**
   1. Install the **Claude desktop app** and the **Claude in Chrome** extension.
   2. In that Chrome, log in to **LinkedIn** and **Gmail**.
   3. Turn on Chrome → Settings → Passwords → "Offer to save passwords".
2. In claude.ai → Settings → **Connectors**, connect **Gmail**.
3. Run the installer on the laptop. It downloads the code to `~/Housing-Ads`, installs Python packages and LibreOffice, and creates the private folders and tracker:
   - **Mac:** open Terminal and paste
     ```
     curl -fsSL https://raw.githubusercontent.com/lakshmipavanipv/Housing-Ads/claude/awesome-cannon-7zgrea/job-hunt/setup_desktop.sh | bash
     ```
   - **Windows:** open PowerShell and paste
     ```
     irm https://raw.githubusercontent.com/lakshmipavanipv/Housing-Ads/claude/awesome-cannon-7zgrea/job-hunt/setup_desktop.ps1 | iex
     ```
   Re-running it later updates the code and leaves your private files alone.
4. Copy your original resume to `job-hunt/private/resume/original.docx` and run `.venv/bin/python job-hunt/tailor_resume.py base` (Windows: `.venv\Scripts\python job-hunt\tailor_resume.py base`). Then fill in the empty fields in `job-hunt/private/applicant-profile.yaml`: phone, city, notice period, CTC, PIN code and so on.
5. In the Claude desktop app, create a **Scheduled task** that runs daily at 09:00, with the repo folder as its working folder and this prompt:
   > Run the daily job-hunt agent: follow job-hunt/AGENT_DAILY.md exactly, using Claude in Chrome and the Gmail connector.
6. **First run:** watch it once with `daily_apply_cap: 2` in `profile.yaml`. When it looks right, set the cap back to 30.

## Day to day
- Keep the laptop on and awake around 09:00.
- Read the summary on your phone.
- Finish any "needs you" items (a CAPTCHA, an OTP, or an unusual question); each takes about a minute.
- Reply to interview emails yourself.

## Files
| File | What it is |
|---|---|
| `profile.yaml` | Search criteria: levels, domains, GCC list, scoring, daily cap |
| `tailor_resume.py` | Makes the base resume and per-job tailored resumes; blocks invented skills or numbers |
| `tracker.py` | Excel tracker of every job (Queued / Applied / Skipped / Interview / Rejected / Offer) |
| `applicant-profile.example.yaml` | Template for the answers used on application forms |
| `AGENT_DAILY.md` | Step-by-step instructions the daily agent follows |
| `setup_desktop.sh` / `setup_desktop.ps1` | One-command laptop installer (Mac / Windows) |
