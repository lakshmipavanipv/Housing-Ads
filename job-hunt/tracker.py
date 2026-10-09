"""
tracker.py
──────────
Local job-application tracker (job-hunt/private/Job-Tracker.xlsx).
Kept out of git because the repo is public.

Usage (the daily agent calls these):
    python job-hunt/tracker.py init
    python job-hunt/tracker.py add  '{"company":..,"title":..,"link":..,"gcc":true,...}'
    python job-hunt/tracker.py seen  <link-or-"company|title">     # exit 0 if already tracked
    python job-hunt/tracker.py set   <link> <status> [note]
    python job-hunt/tracker.py list  [status]
    python job-hunt/tracker.py today                               # count applied today
"""

import json, sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

FILE = Path(__file__).resolve().parent / "private" / "Job-Tracker.xlsx"
COLS = ["Date Found", "Company", "GCC", "Title", "Level", "Location", "Source",
        "Apply Link", "Score", "Resume File", "Status", "Applied At", "Notes"]
STATUSES = ["Queued", "Applied", "Skipped", "Interview", "Rejected", "Offer"]
REAPPLY_DAYS = 60


def _wb():
    if not FILE.exists():
        init()
    return load_workbook(FILE)


def init():
    FILE.parent.mkdir(parents=True, exist_ok=True)
    if FILE.exists():
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(COLS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
    for col, w in zip("ABCDEFGHIJKLM", [12, 24, 6, 40, 18, 16, 12, 50, 7, 40, 11, 17, 40]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    wb.save(FILE)


def _rows(ws):
    return [dict(zip(COLS, [c.value for c in r]), _row=r[0].row)
            for r in ws.iter_rows(min_row=2) if r[0].value]


def _key(company, title):
    return f"{(company or '').strip().lower()}|{(title or '').strip().lower()}"


def seen(ref):
    ws = _wb()["Jobs"]
    cutoff = datetime.now() - timedelta(days=REAPPLY_DAYS)
    for r in _rows(ws):
        if ref in (r["Apply Link"], _key(r["Company"], r["Title"])):
            found = datetime.strptime(str(r["Date Found"])[:10], "%Y-%m-%d")
            return found >= cutoff or r["Status"] in ("Applied", "Interview", "Offer")
    return False


def add(job):
    if seen(job["link"]) or seen(_key(job["company"], job["title"])):
        return False
    wb = _wb(); ws = wb["Jobs"]
    ws.append([datetime.now().strftime("%Y-%m-%d"), job["company"],
               "Yes" if job.get("gcc") else "", job["title"], job.get("level", ""),
               job.get("location", "Hyderabad"), job.get("source", ""), job["link"],
               job.get("score", ""), job.get("resume", ""), job.get("status", "Queued"),
               "", job.get("notes", "")])
    wb.save(FILE)
    return True


def set_status(ref, status, note=""):
    assert status in STATUSES, f"status must be one of {STATUSES}"
    wb = _wb(); ws = wb["Jobs"]
    for r in _rows(ws):
        if ref in (r["Apply Link"], _key(r["Company"], r["Title"])):
            ws.cell(r["_row"], COLS.index("Status") + 1, status)
            if status == "Applied":
                ws.cell(r["_row"], COLS.index("Applied At") + 1,
                        datetime.now().strftime("%Y-%m-%d %H:%M"))
            if note:
                old = r["Notes"] or ""
                ws.cell(r["_row"], COLS.index("Notes") + 1, (old + " | " if old else "") + note)
            wb.save(FILE)
            return True
    return False


def listing(status=None):
    rows = _rows(_wb()["Jobs"])
    rows = [r for r in rows if not status or r["Status"] == status]
    rows.sort(key=lambda r: (r["GCC"] != "Yes", -(float(r["Score"] or 0))))
    return [{k: v for k, v in r.items() if k != "_row"} for r in rows]


def applied_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return sum(1 for r in _rows(_wb()["Jobs"]) if str(r["Applied At"] or "").startswith(today))


if __name__ == "__main__":
    a = sys.argv[1:] or ["list"]
    if a[0] == "init":
        init(); print(FILE)
    elif a[0] == "add":
        print("added" if add(json.loads(a[1])) else "duplicate")
    elif a[0] == "seen":
        sys.exit(0 if seen(a[1]) else 1)
    elif a[0] == "set":
        print("ok" if set_status(a[1], a[2], a[3] if len(a) > 3 else "") else "not found")
    elif a[0] == "list":
        print(json.dumps(listing(a[1] if len(a) > 1 else None), indent=1, default=str))
    elif a[0] == "today":
        print(applied_today())
    else:
        print(__doc__)
