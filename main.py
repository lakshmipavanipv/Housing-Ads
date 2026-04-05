"""
main.py
───────
Master menu for the Housing Ads Automation system.

Usage:
    python main.py
"""

import subprocess
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

console = Console()

MENU = [
    ("1", "Setup Google Spreadsheet",
     "python setup_sheets.py",
     "One-time setup. Creates all sheets with headers."),
    ("2", "Post Ads – Property 1",
     "python post_ads.py --property 1",
     "Open browser, fill forms, post to selected sites."),
    ("3", "Post Ads – Property 2",
     "python post_ads.py --property 2",
     "Open browser, fill forms, post to selected sites."),
    ("4", "Update Ad Stats",
     "python update_status.py",
     "Scrape or manually enter views/clicks/inquiries."),
    ("5", "Manage Contacts",
     "python contact_manager.py",
     "View contacts, update follow-up status."),
    ("6", "Add New Contact Manually",
     "python contact_manager.py --add",
     "Record a buyer contact from phone/WhatsApp."),
    ("7", "Refresh Analytics Dashboard",
     "python analytics.py",
     "Update trends and sparkline charts in Sheet."),
    ("8", "Contact Pipeline Summary",
     "python contact_manager.py --stats",
     "Quick view of pipeline without editing."),
    ("q", "Quit", None, ""),
]


def print_menu():
    table = Table(
        title="[bold cyan]🏠  Housing Ads Automation – Hyderabad[/bold cyan]",
        show_header=True,
        header_style="bold",
        border_style="cyan",
    )
    table.add_column("#", width=4, style="bold cyan")
    table.add_column("Action", width=32)
    table.add_column("Description", width=48)
    for num, action, _, desc in MENU:
        table.add_row(num, action, desc)
    console.print(table)


def run_command(cmd: str):
    """Run a CLI command as a subprocess with inherited I/O."""
    console.print(f"\n  [dim]Running: {cmd}[/dim]\n")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        console.print(f"  [yellow]Command exited with code {result.returncode}[/yellow]")


def check_credentials_file():
    from pathlib import Path
    creds = Path("credentials/google_credentials.json")
    if not creds.exists():
        console.print(Panel(
            "[yellow]credentials/google_credentials.json not found![/yellow]\n\n"
            "You need a Google Service Account to use this tool.\n"
            "See [bold]SETUP.md[/bold] for step-by-step instructions.",
            title="⚠  First-time Setup Required",
            border_style="yellow",
        ))
        return False
    return True


def main():
    console.print(Panel(
        "[bold]Housing Ads Automation System[/bold]\n"
        "Automatically post your 2 Hyderabad flats across 19 property sites\n"
        "and track views, inquiries and contacts in Google Sheets.",
        border_style="cyan",
    ))

    while True:
        print_menu()
        choice = Prompt.ask("\n  Choose an option", default="q")

        if choice.lower() == "q":
            console.print("  Goodbye!")
            break

        item = next((m for m in MENU if m[0] == choice), None)
        if not item:
            console.print("  [red]Invalid choice[/red]")
            continue

        _, action, cmd, _ = item
        if cmd is None:
            break

        # Warn if creds missing (except for setup)
        if choice != "1" and not check_credentials_file():
            console.print("  Run option [bold]1[/bold] (Setup) first.")
            continue

        run_command(cmd)
        input("\n  Press Enter to return to menu…")


if __name__ == "__main__":
    main()
