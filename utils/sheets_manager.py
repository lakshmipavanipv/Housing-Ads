"""
Google Sheets manager.
Handles all read/write operations against the Housing Ads Tracker spreadsheet.
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from pathlib import Path
from config import (
    SPREADSHEET_TITLE,
    SHEET_NAMES,
    HOUSING_SITES,
    SITES_SHEET_HEADERS,
    PROPERTY_SHEET_HEADERS,
    CONTACTS_SHEET_HEADERS,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Colour palette (RGB hex without #) ──────────────────────────────────────
COLOR = {
    "header_dark":  {"red": 0.13, "green": 0.13, "blue": 0.38},   # dark navy
    "header_green": {"red": 0.07, "green": 0.39, "blue": 0.22},   # dark green
    "header_blue":  {"red": 0.07, "green": 0.30, "blue": 0.55},   # dark blue
    "header_purple":{"red": 0.36, "green": 0.11, "blue": 0.55},   # purple
    "header_dash":  {"red": 0.53, "green": 0.12, "blue": 0.05},   # dark red
    "white":        {"red": 1.00, "green": 1.00, "blue": 1.00},
    "light_yellow": {"red": 1.00, "green": 0.97, "blue": 0.80},
    "light_green":  {"red": 0.85, "green": 0.95, "blue": 0.85},
    "light_blue":   {"red": 0.83, "green": 0.91, "blue": 0.98},
    "active":       {"red": 0.20, "green": 0.80, "blue": 0.20},
    "failed":       {"red": 0.90, "green": 0.20, "blue": 0.20},
    "pending":      {"red": 1.00, "green": 0.80, "blue": 0.20},
}


def get_client(credentials_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _fmt_header_request(sheet_id: int, num_cols: int, color: dict) -> dict:
    """Build a batchUpdate request to format the header row."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": color,
                    "horizontalAlignment": "CENTER",
                    "textFormat": {"foregroundColor": COLOR["white"], "bold": True, "fontSize": 10},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    }


def _freeze_request(sheet_id: int, rows: int = 1) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": rows}},
            "fields": "gridProperties.frozenRowCount",
        }
    }


def _col_width_request(sheet_id: int, col_index: int, width_px: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_index,
                "endIndex": col_index + 1,
            },
            "properties": {"pixelSize": width_px},
            "fields": "pixelSize",
        }
    }


# ── Sheet initialisation ────────────────────────────────────────────────────

def create_or_open_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """Open existing spreadsheet or create a new one."""
    try:
        sh = client.open(SPREADSHEET_TITLE)
        print(f"  Opened existing spreadsheet: {sh.url}")
    except gspread.SpreadsheetNotFound:
        sh = client.create(SPREADSHEET_TITLE)
        sh.share(None, perm_type="anyone", role="writer")
        print(f"  Created new spreadsheet: {sh.url}")
    return sh


def _ensure_sheet(sh: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    """Get or create a worksheet by title."""
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=200, cols=20)


def setup_sites_sheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """Create/populate the Sites & Credentials sheet."""
    ws = _ensure_sheet(sh, SHEET_NAMES["sites"])
    ws.clear()

    rows = [SITES_SHEET_HEADERS]
    for site in HOUSING_SITES:
        rows.append([
            site["id"],
            site["name"],
            site["url"],
            site["post_url"],
            site["tier"],
            "Yes" if site["free_listing"] else "No",
            "",  # Username
            "",  # Password
            "",  # Phone
            "",  # API Key
            "Not Set",
            "",  # Notes
        ])

    ws.update("A1", rows)

    # Formatting via batchUpdate
    sid = ws.id
    requests = [
        _fmt_header_request(sid, len(SITES_SHEET_HEADERS), COLOR["header_dark"]),
        _freeze_request(sid, 1),
        _col_width_request(sid, 0, 100),   # Site ID
        _col_width_request(sid, 1, 160),   # Site Name
        _col_width_request(sid, 2, 220),   # URL
        _col_width_request(sid, 3, 250),   # Post URL
        _col_width_request(sid, 6, 200),   # Username
        _col_width_request(sid, 7, 160),   # Password
        _col_width_request(sid, 10, 120),  # Account Status
        _col_width_request(sid, 11, 220),  # Notes
    ]
    sh.batch_update({"requests": requests})

    # Protect password column with a note
    ws.update("H1", [["Password ⚠ (stored locally – handle with care)"]])
    return ws


def setup_property_sheet(
    sh: gspread.Spreadsheet,
    sheet_key: str,        # "property1" or "property2"
    prop_title: str,
    color: dict,
) -> gspread.Worksheet:
    ws = _ensure_sheet(sh, SHEET_NAMES[sheet_key])
    ws.clear()

    # Title row
    ws.merge_cells("A1:M1")
    ws.update("A1", [[f"Ad Status Tracker – {prop_title}"]])

    # Headers in row 2
    ws.update("A2", [PROPERTY_SHEET_HEADERS])

    # Seed one row per site (empty stats)
    today = datetime.today().strftime("%d-%m-%Y")
    data_rows = []
    for site in HOUSING_SITES:
        data_rows.append([
            site["id"],
            site["name"],
            "",        # Ad Posted Date
            "",        # Ad URL
            "",        # Ad Title
            "Pending", # Status
            0,         # Views
            0,         # Clicks
            0,         # Inquiries
            "",        # Last Scraped
            "",        # Expiry
            "",        # Renewal
            "",        # Notes
        ])
    ws.update("A3", data_rows)

    sid = ws.id
    requests = [
        _fmt_header_request(sid, len(PROPERTY_SHEET_HEADERS), color),
        _freeze_request(sid, 2),
        _col_width_request(sid, 0, 110),
        _col_width_request(sid, 1, 160),
        _col_width_request(sid, 3, 260),  # Ad URL
        _col_width_request(sid, 4, 280),  # Ad Title
        _col_width_request(sid, 5, 110),  # Status
        _col_width_request(sid, 12, 200), # Notes
    ]
    sh.batch_update({"requests": requests})
    return ws


def setup_contacts_sheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    ws = _ensure_sheet(sh, SHEET_NAMES["contacts"])
    ws.clear()

    ws.merge_cells("A1:N1")
    ws.update("A1", [["Contact Tracker – Update Follow-up Status regularly"]])
    ws.update("A2", [CONTACTS_SHEET_HEADERS])

    sid = ws.id
    requests = [
        _fmt_header_request(sid, len(CONTACTS_SHEET_HEADERS), COLOR["header_purple"]),
        _freeze_request(sid, 2),
        _col_width_request(sid, 0, 100),
        _col_width_request(sid, 1, 80),
        _col_width_request(sid, 4, 160),  # Name
        _col_width_request(sid, 5, 130),  # Phone
        _col_width_request(sid, 6, 200),  # Email
        _col_width_request(sid, 7, 280),  # Message
        _col_width_request(sid, 8, 140),  # Follow-up
        _col_width_request(sid, 13, 200), # Notes
    ]
    sh.batch_update({"requests": requests})
    return ws


def setup_dashboard_sheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """Create a summary dashboard with formulas referencing other sheets."""
    ws = _ensure_sheet(sh, SHEET_NAMES["dashboard"])
    ws.clear()

    p1 = SHEET_NAMES["property1"]
    p2 = SHEET_NAMES["property2"]
    con = SHEET_NAMES["contacts"]

    rows = [
        ["HOUSING ADS DASHBOARD", "", "", "", "", ""],
        ["Last Refreshed:", "=TEXT(NOW(),\"DD-MM-YYYY HH:MM\")", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["METRIC", "PROPERTY 1", "PROPERTY 2", "TOTAL", "", ""],
        # COUNTIF on Status column (col F = col 6, index 5) in property sheets
        ["Ads Active",
            f"=COUNTIF('{p1}'!F3:F100,\"Active\")",
            f"=COUNTIF('{p2}'!F3:F100,\"Active\")",
            "=B5+C5", "", ""],
        ["Ads Pending",
            f"=COUNTIF('{p1}'!F3:F100,\"Pending\")",
            f"=COUNTIF('{p2}'!F3:F100,\"Pending\")",
            "=B6+C6", "", ""],
        ["Ads Failed",
            f"=COUNTIF('{p1}'!F3:F100,\"Failed\")",
            f"=COUNTIF('{p2}'!F3:F100,\"Failed\")",
            "=B7+C7", "", ""],
        ["", "", "", "", "", ""],
        ["Total Views",
            f"=SUM('{p1}'!G3:G100)",
            f"=SUM('{p2}'!G3:G100)",
            "=B9+C9", "", ""],
        ["Total Clicks",
            f"=SUM('{p1}'!H3:H100)",
            f"=SUM('{p2}'!H3:H100)",
            "=B10+C10", "", ""],
        ["Total Inquiries",
            f"=SUM('{p1}'!I3:I100)",
            f"=SUM('{p2}'!I3:I100)",
            "=B11+C11", "", ""],
        ["", "", "", "", "", ""],
        ["CONTACT PIPELINE", "", "", "", "", ""],
        ["New Contacts",
            f"=COUNTIF('{con}'!I3:I200,\"New\")", "", "", "", ""],
        ["Interested",
            f"=COUNTIF('{con}'!I3:I200,\"Interested\")", "", "", "", ""],
        ["Very Interested",
            f"=COUNTIF('{con}'!I3:I200,\"Very Interested\")", "", "", "", ""],
        ["Negotiating",
            f"=COUNTIF('{con}'!I3:I200,\"Negotiating\")", "", "", "", ""],
        ["Closed / Sold",
            f"=COUNTIF('{con}'!I3:I200,\"Closed / Sold\")", "", "", "", ""],
        ["Not Interested",
            f"=COUNTIF('{con}'!I3:I200,\"Not Interested\")", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["TOP SITES BY VIEWS", "", "", "", "", ""],
        ["(Refresh stats via: python update_status.py)", "", "", "", "", ""],
    ]

    ws.update("A1", rows)

    sid = ws.id
    requests = [
        _fmt_header_request(sid, 6, COLOR["header_dash"]),
        _freeze_request(sid, 1),
        _col_width_request(sid, 0, 200),
        _col_width_request(sid, 1, 130),
        _col_width_request(sid, 2, 130),
        _col_width_request(sid, 3, 100),
    ]
    sh.batch_update({"requests": requests})
    return ws


# ── Runtime helpers ─────────────────────────────────────────────────────────

def get_credentials(client: gspread.Client) -> dict[str, dict]:
    """
    Return {site_id: {username, password, phone, api_key}} from Sites sheet.
    Skips rows with empty username.
    """
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["sites"])
    records = ws.get_all_values()  # row 0 = headers

    creds = {}
    for row in records[1:]:
        if len(row) < 10:
            continue
        site_id, _, _, _, _, _, username, password, phone, api_key = row[:10]
        if username:
            creds[site_id] = {
                "username": username,
                "password": password,
                "phone": phone,
                "api_key": api_key,
            }
    return creds


def update_ad_status(
    client: gspread.Client,
    property_key: str,   # "property1" or "property2"
    site_id: str,
    updates: dict,       # keys match PROPERTY_SHEET_HEADERS
):
    """Update a single row in a property status sheet."""
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES[property_key])
    data = ws.get_all_values()

    # Find row with matching site_id (col A = index 0), data starts at row 3 (index 2)
    for i, row in enumerate(data):
        if row and row[0] == site_id:
            row_num = i + 1  # 1-indexed
            if "ad_url" in updates:
                ws.update_cell(row_num, 4, updates["ad_url"])
            if "ad_title" in updates:
                ws.update_cell(row_num, 5, updates["ad_title"])
            if "status" in updates:
                ws.update_cell(row_num, 6, updates["status"])
            if "views" in updates:
                ws.update_cell(row_num, 7, updates["views"])
            if "clicks" in updates:
                ws.update_cell(row_num, 8, updates["clicks"])
            if "inquiries" in updates:
                ws.update_cell(row_num, 9, updates["inquiries"])
            if "posted_date" in updates:
                ws.update_cell(row_num, 3, updates["posted_date"])
            if "last_scraped" in updates:
                ws.update_cell(row_num, 10, updates["last_scraped"])
            if "expiry_date" in updates:
                ws.update_cell(row_num, 11, updates["expiry_date"])
            if "notes" in updates:
                ws.update_cell(row_num, 13, updates["notes"])
            return
    print(f"  [WARN] site_id '{site_id}' not found in {SHEET_NAMES[property_key]}")


def add_contact(client: gspread.Client, contact: dict):
    """Append a new contact row to the Contacts sheet."""
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["contacts"])
    now = datetime.now()
    row = [
        now.strftime("%d-%m-%Y"),
        now.strftime("%H:%M"),
        contact.get("property", ""),
        contact.get("site", ""),
        contact.get("name", ""),
        contact.get("phone", ""),
        contact.get("email", ""),
        contact.get("message", ""),
        "New",
        "",  # Last follow-up
        "",  # Next follow-up
        "",  # Asking price
        "",  # Offered price
        contact.get("notes", ""),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


def get_spreadsheet_url(client: gspread.Client) -> str:
    sh = client.open(SPREADSHEET_TITLE)
    return sh.url
