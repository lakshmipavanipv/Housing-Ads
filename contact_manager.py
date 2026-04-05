"""
contact_manager.py
──────────────────
Manage buyer contacts and follow-up status in the local .xlsx tracker.

Usage:
    python contact_manager.py           # view + update follow-ups
    python contact_manager.py --add     # add a new contact
    python contact_manager.py --stats   # pipeline summary only
"""

import argparse, sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from config import FOLLOW_UP_STATUS, TRACKER_FILE
from utils.sheets_manager import load_contacts, add_contact, update_contact_row
from utils.github_pusher import sync_all

console = Console()

PIPELINE_COLORS = {
    "New":            "cyan",
    "Interested":     "yellow",
    "Very Interested":"green",
    "Negotiating":    "bold green",
    "Closed / Sold":  "bold cyan",
    "Not Interested": "red",
    "No Response":    "dim",
}


def print_contacts_table(contacts: list[dict]):
    if not contacts:
        console.print("  [yellow]No contacts yet.[/yellow]")
        return
    table = Table(title=f"Contacts ({len(contacts)})", show_header=True, header_style="bold")
    table.add_column("#",       width=4)
    table.add_column("Date",    width=12)
    table.add_column("Property",width=12)
    table.add_column("Site",    width=16)
    table.add_column("Name",    width=18)
    table.add_column("Phone",   width=14)
    table.add_column("Status",  width=18)
    table.add_column("Notes",   width=28)
    for i, c in enumerate(contacts, 1):
        status = c["follow_up_status"]
        sc = PIPELINE_COLORS.get(status, "white")
        table.add_row(str(i), c["date"], c["property"], c["site"],
                      c["name"], c["phone"],
                      f"[{sc}]{status}[/{sc}]", c["notes"][:26])
    console.print(table)


def pipeline_summary(contacts: list[dict]):
    from collections import Counter
    counts = Counter(c["follow_up_status"] for c in contacts)
    table = Table(title="Contact Pipeline", show_header=True)
    table.add_column("Status",  width=20)
    table.add_column("Count",   justify="right", width=8)
    for status in FOLLOW_UP_STATUS:
        sc = PIPELINE_COLORS.get(status, "white")
        table.add_row(f"[{sc}]{status}[/{sc}]", str(counts.get(status, 0)))
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{len(contacts)}[/bold]")
    console.print(table)


def update_contact(contacts: list[dict], idx: int):
    c = contacts[idx]
    console.print(Panel(
        f"[bold]{c['name']}[/bold]  |  {c['phone']}  |  {c['email']}\n"
        f"Property: {c['property']}  |  Site: {c['site']}\n"
        f"Message: {c['message']}\n"
        f"Current Status: [{PIPELINE_COLORS.get(c['follow_up_status'],'white')}]{c['follow_up_status']}[/]",
        title="Update Contact", border_style="cyan",
    ))
    new_status   = Prompt.ask("  Status", choices=FOLLOW_UP_STATUS, default=c["follow_up_status"])
    asking_price = Prompt.ask("  Buyer asking price",  default=c["asking_price"] or "")
    offered_price= Prompt.ask("  Your offered price",  default=c["offered_price"] or "")
    next_fu      = Prompt.ask("  Next follow-up date (DD-MM-YYYY)", default="")
    notes        = Prompt.ask("  Notes", default=c["notes"] or "")

    update_contact_row(c["row"], {
        "follow_up_status": new_status,
        "last_follow_up":   datetime.today().strftime("%d-%m-%Y"),
        "next_follow_up":   next_fu,
        "asking_price":     asking_price,
        "offered_price":    offered_price,
        "notes":            notes,
    })
    console.print(f"  [green]✓[/green] Updated: {c['name']} → {new_status}")


def add_contact_interactive():
    console.print("\n[bold]Add New Contact[/bold]")
    contact = {
        "property": Prompt.ask("  Property", choices=["Property 1","Property 2"]),
        "site":     Prompt.ask("  Site (where did they contact from?)"),
        "name":     Prompt.ask("  Name"),
        "phone":    Prompt.ask("  Phone"),
        "email":    Prompt.ask("  Email", default=""),
        "message":  Prompt.ask("  Message / Query", default=""),
        "notes":    Prompt.ask("  Notes", default=""),
    }
    add_contact(contact)
    console.print(f"  [green]✓[/green] Contact added: {contact['name']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--add",        action="store_true")
    parser.add_argument("--stats",      action="store_true")
    parser.add_argument("--update-all", action="store_true")
    parser.add_argument("--skip-sync",  action="store_true")
    args = parser.parse_args()

    if not TRACKER_FILE.exists():
        console.print(f"[red]Tracker not found:[/red] {TRACKER_FILE}. Run setup_sheets.py first.")
        sys.exit(1)

    if args.add:
        add_contact_interactive()
        if not args.skip_sync:
            sync_all("Add new buyer contact")
        return

    contacts = load_contacts()

    if args.stats:
        pipeline_summary(contacts)
        return

    pipeline_summary(contacts)
    print_contacts_table(contacts)

    if not contacts:
        console.print("\n  No contacts yet. Add one with: [bold]python contact_manager.py --add[/bold]")
        return

    if args.update_all:
        for i, c in enumerate(contacts):
            if c["follow_up_status"] != "Closed / Sold":
                update_contact(contacts, i)
        contacts = load_contacts()
    else:
        while True:
            choice = Prompt.ask("\n  Contact # to update (or [bold]q[/bold] to quit)", default="q")
            if choice.lower() == "q":
                break
            if choice.isdigit():
                i = int(choice) - 1
                if 0 <= i < len(contacts):
                    update_contact(contacts, i)
                    contacts = load_contacts()
                    print_contacts_table(contacts)

    console.print(f"\n  Tracker saved: [bold]{TRACKER_FILE}[/bold]")
    if not args.skip_sync:
        if Confirm.ask("\n  Sync to GitHub & Google Drive?", default=True):
            sync_all("Update contact follow-ups")
            console.print("  [green]✓[/green] Synced")


if __name__ == "__main__":
    main()
