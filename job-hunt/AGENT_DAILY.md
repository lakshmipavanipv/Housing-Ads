# Daily Job-Hunt Agent: instructions

This file is for Claude. It runs every day as a scheduled task in the Claude desktop app on Lakshmi's laptop. Claude in Chrome must be on, she must be logged in to LinkedIn in that Chrome, and the Gmail connector must be connected.

Working folder: the local clone of this repo. All personal files live in `job-hunt/private/`, which is git-ignored. **Never commit or push anything from `private/`.** The repo is public.

Python: the installer makes a virtualenv. Wherever this file says `python`, use `.venv/bin/python` (Windows: `.venv\Scripts\python`) when that exists.

## Inputs
- `job-hunt/profile.yaml`: what to search for (levels, domains, GCC list, scoring, daily cap).
- `job-hunt/private/applicant-profile.yaml`: her answers for application forms.
- `job-hunt/private/resume/Lakshmi_Pavani_Base_Hyderabad.docx`: the base resume.
- `job-hunt/tracker.py`: tracker commands (`add`, `seen`, `set`, `list`, `today`).
- `job-hunt/tailor_resume.py`: makes a tailored resume per job, with a guardrail.

## Hard rules
1. **Only apply.** Never edit her LinkedIn profile. Never message, connect, follow, post, like or endorse. Never send, delete or archive emails. Never change account settings on any site.
2. **Answer truthfully** from `applicant-profile.yaml` and the resume only. If a required question can't be answered from them, do not guess. Mark the job `Skipped` with the question as the note, then move on.
3. **CAPTCHA, "verify you are human", or a phone/SMS OTP:** stop on that job and mark it `Skipped` ("needs human: CAPTCHA/OTP"). Never try to get around them.
4. **Passwords:**
   - When a site needs a new account, sign up with her email and accept Chrome's suggested strong password, so Chrome saves it.
   - When signing in, use Chrome's saved password autofill.
   - Never type, print, log or store a password anywhere else.
   - If no saved password exists for an existing account, mark the job `Skipped` ("needs login").
5. **Daily cap:** stop when `python job-hunt/tracker.py today` reaches `daily_apply_cap` (30). Wait 1–3 minutes between applications.
6. **Salary:** if the form demands a number, use `expected_ctc_inr_lpa`. If a posting's stated maximum is below `min_acceptable_ctc_inr_lpa`, skip it.
7. **Declarations:** accept standard privacy and data-processing consents. Decline marketing and talent-community opt-ins. Skip the job if it asks for anything unusual, such as a non-compete or a background-check fee.

## Step 1: Find jobs (GCCs first)
1. For each company in `gcc_priority` (start with `new_gccs_first`), open its careers site in Chrome. Search for Data / Analytics / BI / AI roles in Hyderabad and open postings from the last 7 days.
2. Search LinkedIn Jobs in Chrome with:
   - Location: Hyderabad
   - Date posted: past 24 hours (past week on Mondays)
   - Experience level: Director and Executive, plus Mid-Senior filtered by title
   - Queries, one at a time:
     - "Senior Manager Data Analytics"
     - "Director Data Analytics"
     - "Associate Director Business Intelligence"
     - "Head of Data"
     - "Data Governance Director"
     - "AI Analytics Director"
3. Then run the same searches on Naukri, iimjobs, Instahyre and Foundit.
4. For each posting:
   - **Drop it** if:
     - its level isn't in `levels_include`;
     - its title matches `levels_exclude` without a senior qualifier;
     - it isn't in Hyderabad or India-remote;
     - `python job-hunt/tracker.py seen "<link>"` exits 0 (already seen).
   - **Score it** 0–100 with the `scoring` weights. For skill overlap, read the JD's must-haves and count how many her resume covers, including close equivalents.
   - **Mark it GCC** if the company is in the list or is clearly a global in-house centre.
5. Keep postings with score ≥ `min_score`. Sort GCC first, then by score.

## Step 2: Tailor a resume per job
For each kept job, up to (cap − applied today), write `job-hunt/private/edits/<company>_<role>.json`:
```json
{"company": "...", "role": "...",
 "headline": "<JD title> | <2-3 of her strongest matching themes>",
 "keywords": ["10-14 JD keywords she genuinely has, in the JD's own wording"],
 "summary": "3-4 sentence executive profile in the JD's language, from her real experience",
 "priority_terms": ["8-12 lowercase JD terms used to move matching bullets to the top"]}
```
- **"In and around" rule:** use the JD's wording for skills she has and their close equivalents. Examples:
  - "Azure data platform" → her Azure / Fabric / Databricks work
  - "BI tools" → Power BI / Tableau / Cognos
  - "data mesh / data products" → governed certified datasets and semantic models
- Do not add tools, employers, certifications or numbers she doesn't have; the guardrail will reject them.

Run `python job-hunt/tailor_resume.py tailor <edits.json>`.
- If the guardrail blocks it, remove the flagged items and run it again.
- The output PDF path goes in the tracker's resume column.

Then add the job with `python job-hunt/tracker.py add '{"company":..,"title":..,"link":..,"gcc":..,"level":..,"source":..,"score":..,"resume":"<pdf path>"}'`.

## Step 3: Apply
For each `Queued` job (`python job-hunt/tracker.py list Queued`, which comes out GCC first), until the cap is reached:

1. Open the apply link in a new Chrome tab.
2. **LinkedIn Easy Apply:**
   - Choose "Upload resume" and pick the tailored PDF.
   - Fill the contact, experience and screening questions from the applicant profile.
   - Review the summary, then Submit.
3. **LinkedIn "Apply" to an external site,** or a direct careers link:
   - **Workday:**
     - Sign in, or "Create Account" with her email and Chrome's suggested password. If verification is needed, open the verification email in Gmail and click its link.
     - Choose "Autofill with Resume" and upload the PDF.
     - Correct any parsed fields against the resume, especially dates, titles and current employer.
     - Answer the questions from the profile, complete voluntary disclosures, then Review and Submit.
   - **Greenhouse / Lever / SmartRecruiters:**
     - Fill name, email and phone, upload the resume and add the LinkedIn URL.
     - Answer questions from the profile. Add a cover letter only if it's required.
     - Submit.
   - **SuccessFactors / Taleo / iCIMS / Oracle:** same pattern. Create the account if needed, upload the resume, fill fields, submit.
   - **Naukri / iimjobs / Instahyre:** use their Apply button. Update the resume on the site only if it asks for one for this application.
4. Confirm success by looking for a confirmation page or a "thank you / application received" message. Then run `python job-hunt/tracker.py set "<link>" Applied "<confirmation text or ID>"`.
5. **On any blocker:** run `tracker.py set "<link>" Skipped "<reason>"` and continue with the next job.

## Step 4: Check Gmail (last 24h, read-only)
1. Search Gmail for:
   ```
   newer_than:1d (interview OR "schedule a call" OR "availability" OR "next steps" OR assessment OR "shortlisted" OR "application" OR recruiter)
   ```
2. Classify each message as one of:
   - **Interview scheduled:** capture company, role, date/time (IST), meeting link, interviewer.
   - **Interview request:** asks her for availability.
   - **Assessment / test link**
   - **Recruiter outreach**
   - **Rejection**
   - **Application confirmation**
3. Update the matching tracker rows to `Interview` or `Rejected` with a note.
4. Do not reply to anything; she replies herself.

## Step 5: Daily summary
End the run with a short message (it shows on her phone in the Claude app) in this format:
```
Job hunt – <date>
Applied today: N  (GCC: x)
  • Company – Title (source)
Skipped – needs you (1 min each):
  • Company – Title – reason – <link>
Interviews / recruiter emails:
  • Company – Role – <date time IST> – <meeting link> – action needed?
Tracker totals: Applied A | Interview I | Rejected R
```
