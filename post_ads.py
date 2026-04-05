"""
post_ads.py
───────────
Main ad-posting script.
Reads credentials from Google Sheet, parses HTML ads, opens a browser for
each site, assists with form filling, and updates the Sheet with results.

Usage:
    python post_ads.py                              # interactive menu
    python post_ads.py --property 1 --sites all    # post property 1 to all sites
    python post_ads.py --property 2 --sites magicbricks,99acres,olx
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

from config import HOUSING_SITES
from utils.html_parser import parse_property_html, validate_property_data
from utils.sheets_manager import get_client, get_credentials, update_ad_status, get_spreadsheet_url
from utils.browser import get_driver

console = Console()

# Map site_id → module class
SITE_HANDLERS = {
    "magicbricks":  ("sites.magicbricks",     "MagicBricks"),
    "99acres":      ("sites.ninetynineacres",  "NinetyNineAcres"),
    "housing":      ("sites.housing_com",      "HousingCom"),
    "nobroker":     ("sites.nobroker",         "NoBroker"),
    "olx":          ("sites.olx",              "OLX"),
    "quikr":        ("sites.quikr",            "Quikr"),
    "commonfloor":  ("sites.commonfloor",      "CommonFloor"),
    "sulekha":      ("sites.sulekha",          "Sulekha"),
    "proptiger":    ("sites.proptiger",        "PropTiger"),
    "makaan":       ("sites.makaan",           "Makaan"),
    "squareyards":  ("sites.squareyards",      "SquareYards"),
    "facebook":     ("sites.facebook",         "FacebookMarketplace"),
    # Sites without automation yet → guided-browser fallback
}

MANUAL_SITES = {"indiaproperty", "nestoria", "propertywala", "homeonline", "instagram",
                "jll", "anarock"}


def import_handler(site_id: str):
    if site_id not in SITE_HANDLERS:
        return None
    module_path, class_name = SITE_HANDLERS[site_id]
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def select_sites_interactively() -> list[str]:
    """Show a numbered menu of sites and let user pick."""
    console.print("\n[bold]Available Sites:[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Site ID", width=15)
    table.add_column("Name", width=20)
    table.add_column("Tier", width=10)
    for i, s in enumerate(HOUSING_SITES, 1):
        table.add_row(str(i), s["id"], s["name"], s["tier"])
    console.print(table)

    choice = Prompt.ask(
        "Enter site numbers (comma-separated) or 'all'",
        default="all",
    )
    if choice.strip().lower() == "all":
        return [s["id"] for s in HOUSING_SITES]

    selected = []
    for token in choice.split(","):
        token = token.strip()
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(HOUSING_SITES):
                selected.append(HOUSING_SITES[idx]["id"])
        else:
            selected.append(token)
    return selected


def print_results_table(results: list):
    table = Table(title="Posting Results", show_header=True, header_style="bold")
    table.add_column("Site", width=20)
    table.add_column("Status", width=16)
    table.add_column("Ad URL / Notes", width=50)
    for r in results:
        status_color = {"Active": "green", "Failed": "red", "Manual Required": "yellow",
                        "Pending": "cyan"}.get(r.status, "white")
        table.add_row(
            r.site_name,
            f"[{status_color}]{r.status}[/{status_color}]",
            r.ad_url or r.notes,
        )
    console.print(table)


def post_to_sites(
    client,
    property_key: str,       # "property1" or "property2"
    prop_data: dict,
    site_ids: list[str],
    credentials: dict,
    headless: bool = False,
):
    results = []
    driver = None

    for site_id in site_ids:
        site_info = next((s for s in HOUSING_SITES if s["id"] == site_id), None)
        if not site_info:
            console.print(f"  [yellow]Unknown site ID:[/yellow] {site_id} – skipping")
            continue

        site_creds = credentials.get(site_id, {})
        if not site_creds:
            console.print(f"  [yellow]No credentials for {site_info['name']}[/yellow] – open browser for manual posting")
            site_creds = {}

        # Manual-only sites
        if site_id in MANUAL_SITES:
            console.print(f"\n  [cyan]{site_info['name']}[/cyan] – opening browser for manual posting")
            if driver is None:
                driver = get_driver(headless=headless)
            driver.get(site_info["post_url"])
            input(f"  >>> Post on {site_info['name']}, then press Enter and paste the ad URL: ")
            ad_url = input("  Ad URL (press Enter to skip): ").strip()
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
            update_ad_status(client, property_key, site_id, r.to_dict())
            continue

        HandlerClass = import_handler(site_id)
        if HandlerClass is None:
            console.print(f"  [yellow]No handler for {site_info['name']}[/yellow] – skipping")
            continue

        console.print(f"\n  [bold cyan]Posting on {site_info['name']}…[/bold cyan]")

        if driver is None:
            driver = get_driver(headless=headless)

        try:
            handler = HandlerClass(driver, site_creds, prop_data)
            result = handler.post_ad()
        except Exception as exc:
            from sites.base_site import PostResult
            result = PostResult(False, site_id, site_info["name"],
                                status="Failed", notes=str(exc))

        results.append(result)
        console.print(f"  {result}")

        # Update Google Sheet immediately
        update_ad_status(client, property_key, site_id, result.to_dict())

    if driver:
        if Confirm.ask("\n  Close browser?", default=True):
            driver.quit()

    return results


def main():
    parser = argparse.ArgumentParser(description="Post housing ads to multiple sites")
    parser.add_argument("--credentials", default="credentials/google_credentials.json")
    parser.add_argument("--property", choices=["1", "2"], help="Which property to post (1 or 2)")
    parser.add_argument("--sites", default="", help="Comma-separated site IDs or 'all'")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    console.print(Panel("[bold cyan]Housing Ads – Auto Poster[/bold cyan]", border_style="cyan"))

    # Check credentials file
    if not Path(args.credentials).exists():
        console.print(f"[red]Credentials file not found:[/red] {args.credentials}")
        console.print("Run [bold]python setup_sheets.py[/bold] first.")
        sys.exit(1)

    client = get_client(args.credentials)
    sheet_url = get_spreadsheet_url(client)
    console.print(f"  Sheet: [link={sheet_url}]{sheet_url}[/link]")

    # Select property
    if args.property:
        prop_num = args.property
    else:
        prop_num = Prompt.ask("Which property to post?", choices=["1", "2"])

    property_key = f"property{prop_num}"
    html_path = f"ads/property{prop_num}.html"

    if not Path(html_path).exists():
        console.print(f"[red]HTML file not found:[/red] {html_path}")
        sys.exit(1)

    # Parse HTML ad
    console.print(f"\n  Parsing [bold]{html_path}[/bold]…")
    prop_data = parse_property_html(html_path)
    missing = validate_property_data(prop_data)
    if missing:
        console.print(f"  [yellow]⚠ Missing/placeholder fields in HTML:[/yellow] {', '.join(missing)}")
        if not Confirm.ask("  Continue anyway?", default=False):
            sys.exit(0)

    console.print(f"  Property: [bold]{prop_data['title']}[/bold]")
    console.print(f"  Price: ₹{prop_data['price']} | Area: {prop_data['area']} {prop_data['area_unit']}")
    console.print(f"  Location: {prop_data['full_address']}")

    # Select sites
    if args.sites:
        site_ids = [s.strip() for s in args.sites.split(",")]
        if "all" in site_ids:
            site_ids = [s["id"] for s in HOUSING_SITES]
    else:
        site_ids = select_sites_interactively()

    console.print(f"\n  Sites to post: [bold]{len(site_ids)}[/bold]")

    # Load credentials from sheet
    console.print("  Loading credentials from Google Sheet…")
    credentials = get_credentials(client)
    filled = len([s for s in site_ids if s in credentials])
    console.print(f"  Credentials found for {filled}/{len(site_ids)} selected sites")

    if not Confirm.ask(f"\n  Start posting to {len(site_ids)} sites?", default=True):
        sys.exit(0)

    # Post ads
    results = post_to_sites(client, property_key, prop_data, site_ids, credentials, args.headless)

    # Summary
    print_results_table(results)
    success = sum(1 for r in results if r.success)
    console.print(f"\n  [green]✓[/green] {success}/{len(results)} ads posted successfully")
    console.print(f"  Results updated in Google Sheet: [link={sheet_url}]{sheet_url}[/link]")


if __name__ == "__main__":
    main()
