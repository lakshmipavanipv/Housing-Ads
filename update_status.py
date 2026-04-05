"""
update_status.py
────────────────
Scrape/refresh view counts and stats for all active ads,
then update the Google Sheet.

Usage:
    python update_status.py                         # update all active ads
    python update_status.py --property 1
    python update_status.py --property 2
    python update_status.py --manual                # enter stats manually
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm

from config import HOUSING_SITES, SHEET_NAMES
from utils.sheets_manager import get_client, update_ad_status, get_spreadsheet_url
from utils.browser import get_driver

console = Console()


def scrape_site_stats(client, driver, property_key: str, site_id: str, ad_url: str) -> dict | None:
    """Try to scrape stats from the live ad page. Return dict or None."""
    # Import the handler if it has a scrape_stats override
    from post_ads import import_handler
    HandlerClass = import_handler(site_id)
    if HandlerClass is None:
        return None

    # Use empty creds / prop data for scrape-only
    handler = HandlerClass(driver, {}, {})
    try:
        stats = handler.scrape_stats(ad_url)
        return stats if any(v > 0 for v in stats.values()) else None
    except Exception:
        return None


def get_active_ads(client, property_key: str) -> list[dict]:
    """Return rows from the property sheet that have an Ad URL and are Active."""
    import gspread
    sh = client.open_by_key(_get_sheet_id(client))
    ws = sh.worksheet(SHEET_NAMES[property_key])
    rows = ws.get_all_values()

    active = []
    for row in rows[2:]:   # skip title + header rows
        if len(row) < 6:
            continue
        site_id, site_name, posted_date, ad_url, ad_title, status = row[:6]
        if ad_url and status in ("Active", "active"):
            active.append({
                "site_id": site_id,
                "site_name": site_name,
                "ad_url": ad_url,
                "status": status,
            })
    return active


def _get_sheet_id(client) -> str:
    from config import SPREADSHEET_TITLE
    return client.open(SPREADSHEET_TITLE).id


def manual_update(client, property_key: str):
    """Prompt user to enter stats manually for each site."""
    console.print(f"\n[bold]Manual Stats Update – {SHEET_NAMES[property_key]}[/bold]")
    console.print("Enter stats for each site (press Enter to skip a site):\n")

    for site in HOUSING_SITES:
        sid = site["id"]
        site_name = site["name"]
        update = Confirm.ask(f"  Update stats for [bold]{site_name}[/bold]?", default=False)
        if not update:
            continue

        ad_url = Prompt.ask(f"    Ad URL for {site_name}", default="")
        views = IntPrompt.ask("    Views", default=0)
        clicks = IntPrompt.ask("    Clicks", default=0)
        inquiries = IntPrompt.ask("    Inquiries", default=0)
        status = Prompt.ask(
            "    Status",
            choices=["Active", "Pending", "Expired", "Failed"],
            default="Active",
        )
        notes = Prompt.ask("    Notes", default="")

        update_ad_status(client, property_key, sid, {
            "ad_url": ad_url,
            "views": views,
            "clicks": clicks,
            "inquiries": inquiries,
            "status": status,
            "last_scraped": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "notes": notes,
        })
        console.print(f"    [green]✓[/green] {site_name} updated")


def auto_update(client, property_key: str):
    """Scrape stats automatically for active ads."""
    active = get_active_ads(client, property_key)
    if not active:
        console.print(f"  No active ads found in {SHEET_NAMES[property_key]}.")
        return

    console.print(f"  Found {len(active)} active ads to scrape…")
    driver = get_driver(headless=True)

    for ad in active:
        sid = ad["site_id"]
        url = ad["ad_url"]
        console.print(f"  Scraping [cyan]{ad['site_name']}[/cyan] – {url[:60]}…", end=" ")
        stats = scrape_site_stats(client, driver, property_key, sid, url)
        if stats:
            update_ad_status(client, property_key, sid, {
                "views": stats["views"],
                "clicks": stats["clicks"],
                "inquiries": stats["inquiries"],
                "last_scraped": datetime.now().strftime("%d-%m-%Y %H:%M"),
            })
            console.print(f"[green]views={stats['views']}[/green]")
        else:
            console.print("[yellow]no data[/yellow]")

    driver.quit()


def print_stats_table(client, property_key: str):
    """Print current stats from the sheet."""
    from config import SPREADSHEET_TITLE
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES[property_key])
    rows = ws.get_all_values()

    table = Table(title=f"Stats – {SHEET_NAMES[property_key]}", show_header=True)
    table.add_column("Site", width=18)
    table.add_column("Status", width=14)
    table.add_column("Views", justify="right", width=8)
    table.add_column("Clicks", justify="right", width=8)
    table.add_column("Inquiries", justify="right", width=10)
    table.add_column("Last Scraped", width=16)

    for row in rows[2:]:
        if len(row) < 10:
            continue
        sid, name, _, url, _, status, views, clicks, inq, scraped = row[:10]
        if not name:
            continue
        sc = {"Active": "green", "Failed": "red", "Pending": "yellow",
              "Manual Required": "yellow"}.get(status, "white")
        table.add_row(name, f"[{sc}]{status}[/{sc}]",
                      str(views), str(clicks), str(inq), scraped)
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Update ad stats in Google Sheet")
    parser.add_argument("--credentials", default="credentials/google_credentials.json")
    parser.add_argument("--property", choices=["1", "2", "both"], default="both")
    parser.add_argument("--manual", action="store_true", help="Enter stats manually")
    args = parser.parse_args()

    if not Path(args.credentials).exists():
        console.print(f"[red]Credentials file not found:[/red] {args.credentials}")
        sys.exit(1)

    client = get_client(args.credentials)
    keys = ["property1", "property2"] if args.property == "both" else [f"property{args.property}"]

    for key in keys:
        console.print(f"\n[bold cyan]Updating {SHEET_NAMES[key]}…[/bold cyan]")
        if args.manual:
            manual_update(client, key)
        else:
            auto_update(client, key)
        print_stats_table(client, key)

    url = get_spreadsheet_url(client)
    console.print(f"\n  Sheet: [link={url}]{url}[/link]")


if __name__ == "__main__":
    main()
