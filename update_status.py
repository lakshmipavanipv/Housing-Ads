"""
update_status.py
────────────────
Update views/clicks/inquiries for active ads in the tracker.
Runs auto-scrape where possible, falls back to manual entry.

Usage:
    python update_status.py              # auto scrape both properties
    python update_status.py --manual     # enter stats manually
    python update_status.py --property 1
"""

import argparse, sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm

from config import HOUSING_SITES, SHEET_NAMES, TRACKER_FILE
from utils.sheets_manager import (
    load_property_stats, update_ad_status, write_trends_table
)
from utils.github_pusher import sync_all

console = Console()


def manual_update(property_key: str):
    console.print(f"\n[bold]Manual Stats Entry – {SHEET_NAMES[property_key]}[/bold]")
    stats = load_property_stats(property_key)

    for s in stats:
        if not Confirm.ask(f"  Update [bold]{s['site_name']}[/bold]?", default=False):
            continue

        ad_url    = Prompt.ask(f"    Ad URL", default=s.get("ad_url",""))
        views     = IntPrompt.ask("    Views",     default=int(s.get("views",0) or 0))
        clicks    = IntPrompt.ask("    Clicks",    default=int(s.get("clicks",0) or 0))
        inquiries = IntPrompt.ask("    Inquiries", default=int(s.get("inquiries",0) or 0))
        status    = Prompt.ask("    Status",
                               choices=["Active","Pending","Expired","Failed","Manual Required"],
                               default=s.get("status","Active"))
        notes     = Prompt.ask("    Notes", default=s.get("notes",""))

        update_ad_status(property_key, s["site_id"], {
            "ad_url":       ad_url,
            "views":        views,
            "clicks":       clicks,
            "inquiries":    inquiries,
            "status":       status,
            "last_scraped": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "notes":        notes,
        })
        console.print(f"    [green]✓[/green] {s['site_name']} updated")


def auto_update(property_key: str):
    from utils.browser import get_driver
    from post_ads import import_handler

    stats = load_property_stats(property_key)
    active = [s for s in stats if s.get("ad_url") and s.get("status") == "Active"]

    if not active:
        console.print(f"  No active ads with URLs in {SHEET_NAMES[property_key]}.")
        return

    console.print(f"  Scraping {len(active)} active ads…")
    driver = get_driver(headless=True)

    for s in active:
        HandlerClass = import_handler(s["site_id"])
        if HandlerClass is None:
            continue

        console.print(f"  Scraping [cyan]{s['site_name']}[/cyan]…", end=" ")
        try:
            handler = HandlerClass(driver, {}, {})
            scraped = handler.scrape_stats(s["ad_url"])
            if any(v > 0 for v in scraped.values()):
                update_ad_status(property_key, s["site_id"], {
                    "views":        scraped["views"],
                    "clicks":       scraped["clicks"],
                    "inquiries":    scraped["inquiries"],
                    "last_scraped": datetime.now().strftime("%d-%m-%Y %H:%M"),
                })
                console.print(f"[green]views={scraped['views']} clicks={scraped['clicks']}[/green]")
            else:
                console.print("[yellow]no data[/yellow]")
        except Exception as exc:
            console.print(f"[red]error: {exc}[/red]")

    driver.quit()


def print_stats(property_key: str):
    stats = load_property_stats(property_key)
    table = Table(title=f"Stats – {SHEET_NAMES[property_key]}", show_header=True, header_style="bold")
    table.add_column("Site",       width=18)
    table.add_column("Status",     width=16)
    table.add_column("Views",      justify="right", width=8)
    table.add_column("Clicks",     justify="right", width=8)
    table.add_column("Inquiries",  justify="right", width=10)
    table.add_column("Last Updated", width=16)
    for s in stats:
        if not s["site_name"]:
            continue
        sc = {"Active":"green","Failed":"red","Pending":"yellow","Manual Required":"yellow"}.get(s["status"],"white")
        table.add_row(s["site_name"], f"[{sc}]{s['status']}[/{sc}]",
                      str(s["views"]), str(s["clicks"]), str(s["inquiries"]), s["last_scraped"])
    console.print(table)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--property", choices=["1","2","both"], default="both")
    parser.add_argument("--manual",   action="store_true")
    parser.add_argument("--skip-sync",action="store_true")
    args = parser.parse_args()

    if not TRACKER_FILE.exists():
        console.print(f"[red]Tracker not found:[/red] {TRACKER_FILE}. Run setup_sheets.py first.")
        sys.exit(1)

    keys = ["property1","property2"] if args.property == "both" else [f"property{args.property}"]

    for key in keys:
        console.print(f"\n[bold cyan]Updating {SHEET_NAMES[key]}…[/bold cyan]")
        if args.manual:
            manual_update(key)
        else:
            auto_update(key)
        print_stats(key)

    console.print(f"\n  Tracker saved: [bold]{TRACKER_FILE}[/bold]")

    if not args.skip_sync:
        if Confirm.ask("\n  Sync to GitHub & Google Drive?", default=True):
            sync_all("Update ad stats")
            console.print("  [green]✓[/green] Synced")


if __name__ == "__main__":
    main()
