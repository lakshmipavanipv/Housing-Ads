"""
setup_sheets.py
───────────────
One-time script to create and initialise the Google Spreadsheet.
Run this first, before doing anything else.

Usage:
    python setup_sheets.py --credentials credentials/google_credentials.json
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils.sheets_manager import (
    get_client,
    create_or_open_spreadsheet,
    setup_sites_sheet,
    setup_property_sheet,
    setup_contacts_sheet,
    setup_dashboard_sheet,
    get_spreadsheet_url,
    COLOR,
)
from config import SPREADSHEET_TITLE, SHEET_NAMES

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Set up the Housing Ads Google Spreadsheet")
    parser.add_argument(
        "--credentials",
        default="credentials/google_credentials.json",
        help="Path to Google service-account JSON credentials file",
    )
    parser.add_argument(
        "--prop1-title",
        default="Property 1 – Hyderabad",
        help="Display title for Property 1",
    )
    parser.add_argument(
        "--prop2-title",
        default="Property 2 – Hyderabad",
        help="Display title for Property 2",
    )
    args = parser.parse_args()

    creds_path = Path(args.credentials)
    if not creds_path.exists():
        console.print(
            Panel(
                f"[red]Credentials file not found:[/red] {creds_path}\n\n"
                "Please follow SETUP.md to create a Google Service Account and download the JSON key.\n"
                "Save it to: [bold]credentials/google_credentials.json[/bold]",
                title="Setup Error",
                border_style="red",
            )
        )
        sys.exit(1)

    console.print(Panel(f"Setting up: [bold cyan]{SPREADSHEET_TITLE}[/bold cyan]", border_style="cyan"))

    try:
        client = get_client(str(creds_path))
        console.print("  [green]✓[/green] Connected to Google Sheets API")

        sh = create_or_open_spreadsheet(client)

        console.print("  Creating [bold]Sites & Credentials[/bold] sheet…")
        setup_sites_sheet(sh)
        console.print("  [green]✓[/green] Sites & Credentials sheet ready")

        console.print(f"  Creating [bold]{SHEET_NAMES['property1']}[/bold] sheet…")
        setup_property_sheet(sh, "property1", args.prop1_title, COLOR["header_green"])
        console.print(f"  [green]✓[/green] {SHEET_NAMES['property1']} ready")

        console.print(f"  Creating [bold]{SHEET_NAMES['property2']}[/bold] sheet…")
        setup_property_sheet(sh, "property2", args.prop2_title, COLOR["header_blue"])
        console.print(f"  [green]✓[/green] {SHEET_NAMES['property2']} ready")

        console.print("  Creating [bold]Contacts[/bold] sheet…")
        setup_contacts_sheet(sh)
        console.print("  [green]✓[/green] Contacts sheet ready")

        console.print("  Creating [bold]Dashboard[/bold] sheet…")
        setup_dashboard_sheet(sh)
        console.print("  [green]✓[/green] Dashboard sheet ready")

        url = get_spreadsheet_url(client)

        # Print next-steps table
        table = Table(title="✅  Spreadsheet Created Successfully", show_header=True)
        table.add_column("Step", style="bold cyan", width=6)
        table.add_column("What to do", style="white")
        table.add_row("1", f"Open the spreadsheet:\n[link={url}]{url}[/link]")
        table.add_row("2", "Go to the [bold]Sites & Credentials[/bold] sheet")
        table.add_row("3", "Fill in your Username / Email and Password for each site")
        table.add_row("4", "Update [bold]ads/property1.html[/bold] and [bold]ads/property2.html[/bold]\n"
                           "with your real property details")
        table.add_row("5", "Run:  [bold green]python post_ads.py[/bold green]")
        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise


if __name__ == "__main__":
    main()
