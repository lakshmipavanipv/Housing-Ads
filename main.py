"""
main.py  –  Master interactive menu for Housing Ads Automation.

Usage:  python main.py
"""

import subprocess, sys, os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from config import TRACKER_FILE

console = Console()

MENU = [
    ("1", "Setup Tracker Spreadsheet",
     "python setup_sheets.py",
     "Creates Housing-Ads-Tracker.xlsx locally + pushes to GitHub + uploads to Drive"),
    ("2", "Post Ads – Property 1",
     "python post_ads.py --property 1",
     "Open browser, auto-fill forms, post to selected sites"),
    ("3", "Post Ads – Property 2",
     "python post_ads.py --property 2",
     "Open browser, auto-fill forms, post to selected sites"),
    ("4", "Update Ad Stats",
     "python update_status.py",
     "Scrape or manually enter views / clicks / inquiries"),
    ("5", "Manage Contacts",
     "python contact_manager.py",
     "View buyer contacts, update follow-up status"),
    ("6", "Add New Contact",
     "python contact_manager.py --add",
     "Record a buyer from phone / WhatsApp / site message"),
    ("7", "Refresh Analytics Dashboard",
     "python analytics.py",
     "Update trends table in the tracker spreadsheet"),
    ("8", "Contact Pipeline Summary",
     "python contact_manager.py --stats",
     "Quick pipeline view without editing"),
    ("9", "Sync to GitHub & Google Drive",
     "python -c \"from utils.github_pusher import sync_all; sync_all('Manual sync')\"",
     "Push tracker + data JSON to GitHub; upload to Google Drive"),
    ("q", "Quit", None, ""),
]


def print_banner():
    tracker_status = (
        f"[green]✓ {TRACKER_FILE}[/green]"
        if TRACKER_FILE.exists()
        else "[yellow]⚠ Not created yet – run option 1[/yellow]"
    )
    console.print(Panel(
        f"[bold cyan]Housing Ads Automation  –  Hyderabad[/bold cyan]\n"
        f"Post 2 flats across 19 sites · Track views, inquiries & contacts\n\n"
        f"Tracker: {tracker_status}",
        border_style="cyan",
        padding=(0, 2),
    ))


def print_menu():
    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("#",       width=4,  style="bold cyan")
    table.add_column("Action",  width=34)
    table.add_column("What it does", width=54)
    for num, action, _, desc in MENU:
        table.add_row(num, action, desc)
    console.print(table)


def run(cmd: str):
    console.print(f"\n  [dim]$ {cmd}[/dim]\n")
    subprocess.run(cmd, shell=True)
    input("\n  Press Enter to return to menu…")


def main():
    while True:
        os.system("clear" if os.name != "nt" else "cls")
        print_banner()
        print_menu()
        choice = Prompt.ask("\n  Choose", default="q")

        if choice.lower() == "q":
            console.print("  Goodbye!")
            break

        item = next((m for m in MENU if m[0] == choice), None)
        if not item:
            console.print("  [red]Invalid choice[/red]")
            input("  Press Enter…")
            continue

        _, action, cmd, _ = item
        if cmd is None:
            break

        # Remind user to set up if tracker missing and not running setup
        if choice != "1" and not TRACKER_FILE.exists():
            console.print(f"\n  [yellow]⚠ Tracker not found.[/yellow] Run option [bold]1[/bold] first.")
            input("  Press Enter…")
            continue

        run(cmd)


if __name__ == "__main__":
    main()
