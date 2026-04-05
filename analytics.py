"""
analytics.py
────────────
Build/refresh the analytics trend charts in Google Sheets.
Reads all stats from property sheets and writes a trends table
so Sheets can render bar/line charts.

Usage:
    python analytics.py
    python analytics.py --credentials credentials/google_credentials.json
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config import HOUSING_SITES, SPREADSHEET_TITLE, SHEET_NAMES
from utils.sheets_manager import get_client, get_spreadsheet_url, COLOR

console = Console()

# We'll write trends data into a dedicated range in the Dashboard sheet
# below the contact pipeline section.

TREND_START_ROW = 25   # row in Dashboard where trend table begins


def collect_stats(client) -> dict:
    """
    Read all stats from Property 1 and Property 2 sheets.
    Returns { site_id: {name, p1_views, p1_clicks, p1_inq, p2_views, ...} }
    """
    sh = client.open(SPREADSHEET_TITLE)
    stats = {s["id"]: {"name": s["name"], "p1_views": 0, "p1_clicks": 0, "p1_inq": 0,
                        "p2_views": 0, "p2_clicks": 0, "p2_inq": 0} for s in HOUSING_SITES}

    for prop_key, prefix in [("property1", "p1"), ("property2", "p2")]:
        ws = sh.worksheet(SHEET_NAMES[prop_key])
        rows = ws.get_all_values()
        for row in rows[2:]:
            if len(row) < 9 or not row[0]:
                continue
            sid = row[0]
            if sid not in stats:
                continue
            try:
                stats[sid][f"{prefix}_views"] = int(row[6]) if row[6] else 0
                stats[sid][f"{prefix}_clicks"] = int(row[7]) if row[7] else 0
                stats[sid][f"{prefix}_inq"] = int(row[8]) if row[8] else 0
            except ValueError:
                pass

    return stats


def write_trends_to_dashboard(client, stats: dict):
    """Write a trends table into the Dashboard sheet."""
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["dashboard"])

    # Sort sites by total views (p1+p2)
    sorted_sites = sorted(
        stats.items(),
        key=lambda kv: kv[1]["p1_views"] + kv[1]["p2_views"],
        reverse=True,
    )

    rows = [
        ["TRENDS BY SITE", "", "", "", "", "", "", ""],
        [f"Updated: {datetime.now().strftime('%d-%m-%Y %H:%M')}", "", "", "", "", "", "", ""],
        ["Site", "P1 Views", "P1 Clicks", "P1 Inquiries", "P2 Views", "P2 Clicks", "P2 Inquiries",
         "Total Views"],
    ]
    for sid, s in sorted_sites:
        total = s["p1_views"] + s["p2_views"]
        rows.append([
            s["name"],
            s["p1_views"], s["p1_clicks"], s["p1_inq"],
            s["p2_views"], s["p2_clicks"], s["p2_inq"],
            total,
        ])

    start_cell = f"A{TREND_START_ROW}"
    ws.update(start_cell, rows)

    # Format header row of trends table
    sheet_id = ws.id
    header_row_idx = TREND_START_ROW + 2 - 1   # 0-indexed
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row_idx,
                    "endRowIndex": header_row_idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR["header_dash"],
                        "textFormat": {"foregroundColor": COLOR["white"], "bold": True},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        }
    ]
    sh.batch_update({"requests": requests})

    console.print(f"  [green]✓[/green] Trends table written to Dashboard (row {TREND_START_ROW})")


def print_trends_console(stats: dict):
    sorted_sites = sorted(
        stats.items(),
        key=lambda kv: kv[1]["p1_views"] + kv[1]["p2_views"],
        reverse=True,
    )

    table = Table(title="Trends by Site", show_header=True, header_style="bold")
    table.add_column("Site", width=18)
    table.add_column("P1 Views", justify="right", width=10)
    table.add_column("P1 Clicks", justify="right", width=10)
    table.add_column("P1 Inq.", justify="right", width=8)
    table.add_column("P2 Views", justify="right", width=10)
    table.add_column("P2 Clicks", justify="right", width=10)
    table.add_column("P2 Inq.", justify="right", width=8)
    table.add_column("Total Views", justify="right", width=12)

    for sid, s in sorted_sites:
        total = s["p1_views"] + s["p2_views"]
        if total == 0:
            continue
        table.add_row(
            s["name"],
            str(s["p1_views"]), str(s["p1_clicks"]), str(s["p1_inq"]),
            str(s["p2_views"]), str(s["p2_clicks"]), str(s["p2_inq"]),
            f"[bold]{total}[/bold]",
        )
    if table.row_count:
        console.print(table)
    else:
        console.print("  [yellow]No stats yet. Run update_status.py to populate stats.[/yellow]")


def add_sparkline_charts(client):
    """
    Add Google Sheets SPARKLINE formulas next to each site row
    in the Dashboard trends table, showing a mini trend bar.
    Note: Sheets sparklines need historical data columns to be meaningful.
    Here we just use the 8 metrics as the data range.
    """
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["dashboard"])

    data = ws.get_all_values()
    # Find the trends header row
    for i, row in enumerate(data):
        if row and row[0] == "Site":
            header_row = i + 1   # 1-indexed
            break
    else:
        return

    # Write sparkline in column I for each data row after header
    updates = []
    for row_num in range(header_row + 1, header_row + len(HOUSING_SITES) + 1):
        cell = f"I{row_num}"
        formula = f'=SPARKLINE(B{row_num}:H{row_num},{{"charttype","bar";"color1","#1a6e3e";"color2","#0d3d86"}})'
        updates.append({"range": cell, "values": [[formula]]})

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
        console.print("  [green]✓[/green] Sparkline charts added to Dashboard")


def main():
    parser = argparse.ArgumentParser(description="Refresh analytics in Google Sheet")
    parser.add_argument("--credentials", default="credentials/google_credentials.json")
    parser.add_argument("--no-sparklines", action="store_true")
    args = parser.parse_args()

    if not Path(args.credentials).exists():
        console.print(f"[red]Credentials file not found:[/red] {args.credentials}")
        sys.exit(1)

    client = get_client(args.credentials)
    url = get_spreadsheet_url(client)
    console.print(f"  Sheet: [link={url}]{url}[/link]")

    console.print("  Collecting stats…")
    stats = collect_stats(client)
    print_trends_console(stats)

    console.print("  Writing trends to Dashboard…")
    write_trends_to_dashboard(client, stats)

    if not args.no_sparklines:
        console.print("  Adding sparkline charts…")
        add_sparkline_charts(client)

    console.print(f"\n  [green]✓[/green] Analytics refreshed: [link={url}]{url}[/link]")


if __name__ == "__main__":
    main()
