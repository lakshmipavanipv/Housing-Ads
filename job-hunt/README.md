# Job Hunt Agent: Hyderabad, Senior Manager and above, Data & Analytics

Every morning on your laptop, Claude:
1. finds new Hyderabad roles at Senior Manager level or above, **GCCs first**;
2. tailors your resume to each job description;
3. applies in your Chrome: LinkedIn → Apply → company site → sign in or create the account → fill the form → upload → submit (up to 15 a day);
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
3. Clone this repo and set it up:
   ```
   git clone https://github.com/lakshmipavanipv/Housing-Ads.git
   cd Housing-Ads && git checkout ccr-2da7b747-rbef94
   pip install python-docx openpyxl pyyaml
   ```
   You also need LibreOffice (free), which turns resumes into PDFs.
4. Create your private files:
   ```
   mkdir -p job-hunt/private/resume
   copy your original resume .docx to  job-hunt/private/resume/original.docx
   copy job-hunt/applicant-profile.example.yaml  job-hunt/private/applicant-profile.yaml   (fill phone/city first)
   python job-hunt/tailor_resume.py base       # makes the Hyderabad base resume
   python job-hunt/tracker.py init
   ```
   Fill in the empty fields in `applicant-profile.yaml`: notice period, CTC, PIN code and so on. Claude can also give you the pre-filled copy it made.
5. In the Claude desktop app, create a **Scheduled task** that runs daily at 09:00, with the repo folder as its working folder and this prompt:
   > Run the daily job-hunt agent: follow job-hunt/AGENT_DAILY.md exactly, using Claude in Chrome and the Gmail connector.
6. **First run:** watch it once with `daily_apply_cap: 2` in `profile.yaml`. When it looks right, set the cap back to 15.

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
