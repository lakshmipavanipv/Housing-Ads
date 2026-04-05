# Housing Ads Automation – Setup Guide

## What this system does

Automatically posts your 2 Hyderabad flats across **19 property websites**, then tracks
views, clicks, inquiries, and buyer follow-ups in a **single Google Spreadsheet**.

---

## Step 1 – Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 2 – Set up Google Sheets API

You need a **Google Service Account** (free) to create and edit the spreadsheet automatically.

### 2a. Create a Google Cloud project
1. Go to https://console.cloud.google.com
2. Create a new project (e.g. `housing-ads`)
3. In the left menu → **APIs & Services → Library**
4. Enable **Google Sheets API** and **Google Drive API**

### 2b. Create a Service Account
1. **APIs & Services → Credentials → Create Credentials → Service Account**
2. Give it any name (e.g. `housing-ads-bot`)
3. Click **Done**

### 2c. Download the JSON key
1. Click the service account you just created
2. **Keys** tab → **Add Key → Create new key → JSON**
3. Download the JSON file
4. Save it as:  `credentials/google_credentials.json`

> ⚠ Never commit this file to git (it's already in `.gitignore`).

---

## Step 3 – Fill in your property details

Edit the two HTML template files with your real property information:

| File | Property |
|------|----------|
| `ads/property1.html` | Flat 1 |
| `ads/property2.html` | Flat 2 |

**Replace all the `<meta>` tag values** (title, price, area, location, contact details, etc.)
and replace the body HTML with your actual ad content.

---

## Step 4 – Create the Google Spreadsheet

```bash
python setup_sheets.py
```

This creates a spreadsheet named **"Housing Ads Tracker – Hyderabad"** in your Google Drive
with 5 sheets:

| Sheet | Purpose |
|-------|---------|
| **Sites & Credentials** | List of all 19 sites. Fill in your username/password for each. |
| **Property 1 Status** | Ad status, views, clicks, inquiries per site for Flat 1 |
| **Property 2 Status** | Same for Flat 2 |
| **Contacts** | Buyer contact log with follow-up status |
| **Dashboard** | Live summary + trends (auto-calculated from other sheets) |

---

## Step 5 – Add your credentials to the Sheet

1. Open the spreadsheet URL (printed by setup_sheets.py)
2. Go to the **Sites & Credentials** tab
3. Fill in **Username/Email** and **Password** for each site you have an account on
4. Leave blank for sites you don't use (the script will open a browser for those)

---

## Step 6 – Post your ads

```bash
python main.py        # interactive menu (recommended)
# or directly:
python post_ads.py --property 1 --sites all
python post_ads.py --property 2 --sites magicbricks,99acres,olx,nobroker,housing
```

The browser will open for each site. The script:
- Logs in with your saved credentials
- Pre-fills the form fields from your HTML ad
- Pauses for you to complete captchas, OTPs, or image uploads
- Records the ad URL back to the Google Sheet automatically

---

## Step 7 – Daily / Weekly maintenance

### Update stats
```bash
python update_status.py          # auto-scrape where possible
python update_status.py --manual # enter stats manually
```

### Manage buyer contacts
```bash
python contact_manager.py              # view + update follow-ups
python contact_manager.py --add        # add a contact from WhatsApp/call
python contact_manager.py --stats      # pipeline summary only
```

### Refresh analytics dashboard
```bash
python analytics.py
```

---

## Sites covered (19 total)

| Tier | Sites |
|------|-------|
| Tier-1 (highest traffic) | MagicBricks, 99acres, Housing.com, NoBroker, OLX |
| Tier-2 | Quikr, CommonFloor, Sulekha, PropTiger, Makaan, Square Yards |
| Tier-3 | India Property, Nestoria, PropertyWala, HomeOnline |
| Social | Facebook Marketplace, Instagram |
| Premium | JLL India, Anarock |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `gspread.exceptions.APIError` | Check that Sheets API and Drive API are enabled in GCP |
| Browser doesn't open | Install Chrome: `sudo apt-get install chromium-browser` |
| ChromeDriver error | The script auto-downloads the right driver via `webdriver-manager` |
| CAPTCHA stuck | Complete it manually in the browser window; press Enter to continue |
| OTP required | Some sites (NoBroker) use phone OTP – complete manually, then press Enter |

---

## Running everything with one command

```bash
python main.py
```

Use the numbered menu to run each step.
