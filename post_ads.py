"""
post_ads.py
───────────
Read credentials from the local .xlsx, parse HTML ads, open a browser
for each site, assist with form filling, then update the tracker.

Usage:
    python post_ads.py                              # interactive menu
    python post_ads.py --property 1 --sites all
    python post_ads.py --property 2 --sites magicbricks,99acres,olx,nobroker
    python post_ads.py --property 1 --sites magicbricks --headless
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from config import HOUSING_SITES, TRACKER_FILE
from utils.html_parser import parse_property_html, validate_property_data
from utils.sheets_manager import get_credentials, update_ad_status
from utils.browser import get_driver
from utils.github_pusher import sync_all

console = Console()

# Map site_id → (module, class)
SITE_HANDLERS = {
    "magicbricks":  ("sites.magicbricks",    "MagicBricks"),
    "99acres":      ("sites.ninetynineacres", "NinetyNineAcres"),
    "housing":      ("sites.housing_com",     "HousingCom"),
    "nobroker":     ("sites.nobroker",        "NoBroker"),
    "olx":          ("sites.olx",             "OLX"),
    "quikr":        ("sites.quikr",           "Quikr"),
    "commonfloor":  ("sites.commonfloor",     "CommonFloor"),
    "sulekha":      ("sites.sulekha",         "Sulekha"),
    "proptiger":    ("sites.proptiger",       "PropTiger"),
    "makaan":       ("sites.makaan",          "Makaan"),
    "squareyards":  ("sites.squareyards",     "SquareYards"),
    "facebook":     ("sites.facebook",        "FacebookMarketplace"),
}

MANUAL_SITES = {"indiaproperty", "nestoria", "propertywala", "homeonline", "instagram", "jll", "anarock"}


def import_handler(site_id: str):
    if site_id not in SITE_HANDLERS:
        return None
    import importlib
    mod_path, cls = SITE_HANDLERS[site_id]
    return getattr(importlib.import_module(mod_path), cls)


def select_sites_interactively() -> list[str]:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#",       width=4)
    table.add_column("Site",    width=20)
    table.add_column("Tier",    width=10)
    table.add_column("Auto?",   width=8)
    for i, s in enumerate(HOUSING_SITES, 1):
        auto = "✓" if s["id"] in SITE_HANDLERS else "Manual"
        table.add_row(str(i), s["name"], s["tier"], auto)
    console.print(table)
    choice = Prompt.ask("Enter site numbers (comma-separated) or [bold]all[/bold]", default="all")
    if choice.strip().lower() == "all":
        return [s["id"] for s in HOUSING_SITES]
    selected = []
    for token in choice.split(","):
        t = token.strip()
        if t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(HOUSING_SITES):
                selected.append(HOUSING_SITES[idx]["id"])
        else:
            selected.append(t)
    return selected


def print_results(results: list):
    table = Table(title="Posting Results", show_header=True)
    table.add_column("Site",    width=22)
    table.add_column("Status",  width=18)
    table.add_column("URL / Notes", width=52)
    for r in results:
        sc = {"Active":"green","Failed":"red","Manual Required":"yellow","Pending":"cyan"}.get(r.status,"white")
        table.add_row(r.site_name, f"[{sc}]{r.status}[/{sc}]", r.ad_url or r.notes)
    console.print(table)


def post_to_sites(property_key, prop_data, site_ids, credentials, headless=False):
    results = []
    driver = None

    for site_id in site_ids:
        site_info = next((s for s in HOUSING_SITES if s["id"] == site_id), None)
        if not site_info:
            continue

        site_creds = credentials.get(site_id, {})

        # Manual-only sites: open browser, let user post
        if site_id in MANUAL_SITES:
            console.print(f"\n  [cyan]{site_info['name']}[/cyan] – browser-assisted manual posting")
            if driver is None:
                driver = get_driver(headless=headless)
            driver.get(site_info["post_url"])
            input(f"\n  >>> Complete the ad on {site_info['name']}, then press Enter.")
            ad_url = input("  Paste the ad URL (or press Enter to skip): ").strip()
            from sites.base_site import PostResult
            r = PostResult(
                success=bool(ad_url),
                site_id=site_id,
                site_name=site_info["name"],
                ad_url=ad_url,
                ad_title=prop_data.get("title", ""),
                status="Active" if ad_url else "Manual Required",
                notes="Manual posting",
            )
            results.append(r)
            update_ad_status(property_key, site_id, r.to_dict())
            continue

        HandlerClass = import_handler(site_id)
        if HandlerClass is None:
            continue

        console.print(f"\n  [bold cyan]→ Posting on {site_info['name']}…[/bold cyan]")
        if driver is None:
            driver = get_driver(headless=headless)

        try:
            handler = HandlerClass(driver, site_creds, prop_data)
            result = handler.post_ad()
        except Exception as exc:
            from sites.base_site import PostResult
            result = PostResult(False, site_id, site_info["name"], status="Failed", notes=str(exc))

        results.append(result)
        console.print(f"  {result}")
        update_ad_status(property_key, site_id, result.to_dict())

    if driver:
        if Confirm.ask("\n  Close browser?", default=True):
            driver.quit()

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--property",  choices=["1","2"])
    parser.add_argument("--sites",     default="")
    parser.add_argument("--headless",  action="store_true")
    parser.add_argument("--skip-sync", action="store_true", help="Skip GitHub/Drive sync after posting")
    args = parser.parse_args()

    console.print(Panel("[bold cyan]Housing Ads – Auto Poster[/bold cyan]", border_style="cyan"))

    if not TRACKER_FILE.exists():
        console.print(f"[red]Tracker not found:[/red] {TRACKER_FILE}")
        console.print("Run [bold]python setup_sheets.py[/bold] first.")
        sys.exit(1)

    prop_num = args.property or Prompt.ask("Which property to post?", choices=["1","2"])
    property_key = f"property{prop_num}"
    html_path = f"ads/property{prop_num}.html"

    if not Path(html_path).exists():
        console.print(f"[red]HTML file not found:[/red] {html_path}")
        sys.exit(1)

    console.print(f"\n  Parsing [bold]{html_path}[/bold]…")
    prop_data = parse_property_html(html_path)
    missing = validate_property_data(prop_data)
    if missing:
        console.print(f"  [yellow]⚠ Missing fields:[/yellow] {', '.join(missing)}")
        if not Confirm.ask("  Continue anyway?", default=False):
            sys.exit(0)

    console.print(f"  [bold]{prop_data['title']}[/bold]")
    console.print(f"  ₹{prop_data['price']}  |  {prop_data['area']} {prop_data['area_unit']}  |  {prop_data['full_address']}")

    if args.sites:
        site_ids = [s.strip() for s in args.sites.split(",")]
        if "all" in site_ids:
            site_ids = [s["id"] for s in HOUSING_SITES]
    else:
        site_ids = select_sites_interactively()

    credentials = get_credentials()
    filled = sum(1 for s in site_ids if s in credentials)
    console.print(f"\n  Credentials loaded: {filled}/{len(site_ids)} sites")

    if not Confirm.ask(f"\n  Start posting to {len(site_ids)} sites?", default=True):
        sys.exit(0)

    results = post_to_sites(property_key, prop_data, site_ids, credentials, args.headless)
    print_results(results)

    success = sum(1 for r in results if r.success)
    console.print(f"\n  [green]✓[/green] {success}/{len(results)} ads posted")
    console.print(f"  Tracker saved: [bold]{TRACKER_FILE}[/bold]")

    if not args.skip_sync:
        if Confirm.ask("\n  Sync tracker to GitHub & Google Drive?", default=True):
            sync_all(f"Post ads – Property {prop_num} – {success}/{len(results)} sites")
            console.print("  [green]✓[/green] Synced")


if __name__ == "__main__":
    main()
