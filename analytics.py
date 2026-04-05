"""
analytics.py
────────────
Refresh the trends table in the Dashboard sheet of the local .xlsx.
Reads stats from both property sheets and writes a ranked table.

Usage:
    python analytics.py
"""

import argparse, sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

from config import HOUSING_SITES, TRACKER_FILE
from utils.sheets_manager import load_property_stats, write_trends_table
from utils.github_pusher import sync_all

console = Console()


def collect_trends() -> list[dict]:
    p1 = {s["site_id"]: s for s in load_property_stats("property1")}
    p2 = {s["site_id"]: s for s in load_property_stats("property2")}

    trends = []
    for site in HOUSING_SITES:
        sid = site["id"]
        s1 = p1.get(sid, {})
        s2 = p2.get(sid, {})
        trends.append({
            "id":        sid,
            "name":      site["name"],
            "p1_views":  int(s1.get("views",0)     or 0),
            "p1_clicks": int(s1.get("clicks",0)    or 0),
            "p1_inq":    int(s1.get("inquiries",0) or 0),
            "p2_views":  int(s2.get("views",0)     or 0),
            "p2_clicks": int(s2.get("clicks",0)    or 0),
            "p2_inq":    int(s2.get("inquiries",0) or 0),
        })

    # Sort by total views
    trends.sort(key=lambda t: t["p1_views"] + t["p2_views"], reverse=True)
    return trends


def print_trends(trends: list[dict]):
    table = Table(title="Trends by Site", show_header=True, header_style="bold")
    table.add_column("Site",        width=18)
    table.add_column("P1 Views",    justify="right", width=10)
    table.add_column("P1 Clicks",   justify="right", width=10)
    table.add_column("P1 Inq.",     justify="right", width=8)
    table.add_column("P2 Views",    justify="right", width=10)
    table.add_column("P2 Clicks",   justify="right", width=10)
    table.add_column("P2 Inq.",     justify="right", width=8)
    table.add_column("Total Views", justify="right", width=12)

    has_data = False
    for t in trends:
        total = t["p1_views"] + t["p2_views"]
        if total == 0:
            continue
        has_data = True
        table.add_row(t["name"],
                      str(t["p1_views"]), str(t["p1_clicks"]), str(t["p1_inq"]),
                      str(t["p2_views"]), str(t["p2_clicks"]), str(t["p2_inq"]),
                      f"[bold]{total}[/bold]")
    if has_data:
        console.print(table)
    else:
        console.print("  [yellow]No stats yet. Run update_status.py to populate data.[/yellow]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sync", action="store_true")
    args = parser.parse_args()

    if not TRACKER_FILE.exists():
        console.print(f"[red]Tracker not found:[/red] {TRACKER_FILE}. Run setup_sheets.py first.")
        sys.exit(1)

    console.print("\n  Collecting stats from all property sheets…")
    trends = collect_trends()
    print_trends(trends)

    console.print("\n  Writing trends table to Dashboard sheet…")
    write_trends_table(trends)
    console.print(f"  [green]✓[/green] Dashboard updated: [bold]{TRACKER_FILE}[/bold]")

    if not args.skip_sync:
        from rich.prompt import Confirm
        if Confirm.ask("\n  Sync to GitHub & Google Drive?", default=True):
            sync_all("Refresh analytics dashboard")
            console.print("  [green]✓[/green] Synced")


if __name__ == "__main__":
    main()
