"""
contact_manager.py
──────────────────
Manage buyer contacts and follow-up status.
Prompts the user to update status for each contact,
and logs everything back to the Google Sheet.

Usage:
    python contact_manager.py              # show contacts + update follow-ups
    python contact_manager.py --add        # add a new contact manually
    python contact_manager.py --stats      # show contact pipeline summary
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from config import FOLLOW_UP_STATUS, SHEET_NAMES, SPREADSHEET_TITLE
from utils.sheets_manager import get_client, add_contact, get_spreadsheet_url

console = Console()


def load_contacts(client) -> list[dict]:
    """Load all contacts from the Contacts sheet."""
    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["contacts"])
    rows = ws.get_all_values()

    contacts = []
    for i, row in enumerate(rows[2:], start=3):   # row index (1-based), skip title+header
        if len(row) < 9 or not row[4]:            # need at least a name
            continue
        contacts.append({
            "row": i,
            "date": row[0],
            "time": row[1],
            "property": row[2],
            "site": row[3],
            "name": row[4],
            "phone": row[5],
            "email": row[6],
            "message": row[7],
            "follow_up_status": row[8],
            "last_follow_up": row[9] if len(row) > 9 else "",
            "next_follow_up": row[10] if len(row) > 10 else "",
            "asking_price": row[11] if len(row) > 11 else "",
            "offered_price": row[12] if len(row) > 12 else "",
            "notes": row[13] if len(row) > 13 else "",
        })
    return contacts


def print_contacts_table(contacts: list[dict], filter_status: str = None):
    filtered = contacts if not filter_status else [
        c for c in contacts if c["follow_up_status"] == filter_status
    ]
    if not filtered:
        console.print("  [yellow]No contacts found.[/yellow]")
        return

    table = Table(title=f"Contacts ({len(filtered)} total)", show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Date", width=12)
    table.add_column("Property", width=12)
    table.add_column("Site", width=16)
    table.add_column("Name", width=18)
    table.add_column("Phone", width=14)
    table.add_column("Follow-up Status", width=18)
    table.add_column("Notes", width=30)

    for i, c in enumerate(filtered, 1):
        status = c["follow_up_status"]
        sc = {
            "New": "cyan",
            "Interested": "yellow",
            "Very Interested": "green",
            "Negotiating": "bold green",
            "Closed / Sold": "bold cyan",
            "Not Interested": "red",
            "No Response": "dim",
        }.get(status, "white")
        table.add_row(
            str(i),
            c["date"],
            c["property"],
            c["site"],
            c["name"],
            c["phone"],
            f"[{sc}]{status}[/{sc}]",
            c["notes"][:28],
        )
    console.print(table)


def update_follow_up(client, contact: dict):
    """Prompt user to update a contact's follow-up status."""
    console.print(
        Panel(
            f"[bold]{contact['name']}[/bold] | {contact['phone']} | {contact['email']}\n"
            f"Property: {contact['property']} | Site: {contact['site']}\n"
            f"Message: {contact['message']}\n"
            f"Current Status: [cyan]{contact['follow_up_status']}[/cyan]",
            title="Update Contact",
            border_style="cyan",
        )
    )

    new_status = Prompt.ask(
        "  New follow-up status",
        choices=FOLLOW_UP_STATUS,
        default=contact["follow_up_status"],
    )
    asking_price = Prompt.ask("  Buyer's asking price", default=contact["asking_price"] or "")
    offered_price = Prompt.ask("  Offered price (your counter)", default=contact["offered_price"] or "")
    next_fu = Prompt.ask("  Next follow-up date (DD-MM-YYYY)", default="")
    notes = Prompt.ask("  Notes", default=contact["notes"] or "")

    sh = client.open(SPREADSHEET_TITLE)
    ws = sh.worksheet(SHEET_NAMES["contacts"])
    row = contact["row"]

    ws.update_cell(row, 9, new_status)
    ws.update_cell(row, 10, datetime.today().strftime("%d-%m-%Y"))
    ws.update_cell(row, 11, next_fu)
    ws.update_cell(row, 12, asking_price)
    ws.update_cell(row, 13, offered_price)
    ws.update_cell(row, 14, notes)

    console.print(f"  [green]✓[/green] {contact['name']} updated → {new_status}")


def add_contact_interactive(client):
    """Manually add a new contact."""
    console.print("\n[bold]Add New Contact[/bold]")
    contact = {
        "property": Prompt.ask("  Property", choices=["Property 1", "Property 2"]),
        "site": Prompt.ask("  Site where contact came from"),
        "name": Prompt.ask("  Contact Name"),
        "phone": Prompt.ask("  Phone"),
        "email": Prompt.ask("  Email", default=""),
        "message": Prompt.ask("  Message / Query", default=""),
        "notes": Prompt.ask("  Notes", default=""),
    }
    add_contact(client, contact)
    console.print(f"  [green]✓[/green] Contact added: {contact['name']}")


def pipeline_summary(contacts: list[dict]):
    """Print pipeline summary."""
    from collections import Counter
    status_counts = Counter(c["follow_up_status"] for c in contacts)

    table = Table(title="Contact Pipeline Summary", show_header=True)
    table.add_column("Status", width=22)
    table.add_column("Count", justify="right", width=8)

    for status in FOLLOW_UP_STATUS:
        count = status_counts.get(status, 0)
        sc = {
            "New": "cyan",
            "Interested": "yellow",
            "Very Interested": "green",
            "Negotiating": "bold green",
            "Closed / Sold": "bold cyan",
            "Not Interested": "red",
            "No Response": "dim",
        }.get(status, "white")
        table.add_row(f"[{sc}]{status}[/{sc}]", str(count))

    table.add_row("[bold]TOTAL[/bold]", f"[bold]{len(contacts)}[/bold]")
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Manage buyer contacts")
    parser.add_argument("--credentials", default="credentials/google_credentials.json")
    parser.add_argument("--add", action="store_true", help="Add a new contact")
    parser.add_argument("--stats", action="store_true", help="Show pipeline stats only")
    parser.add_argument("--update-all", action="store_true", help="Update follow-up for all contacts")
    args = parser.parse_args()

    if not Path(args.credentials).exists():
        console.print(f"[red]Credentials file not found:[/red] {args.credentials}")
        sys.exit(1)

    client = get_client(args.credentials)
    url = get_spreadsheet_url(client)

    if args.add:
        add_contact_interactive(client)
        return

    contacts = load_contacts(client)
    console.print(f"\n  Sheet: [link={url}]{url}[/link]")
    console.print(f"  Total contacts: {len(contacts)}\n")

    if args.stats:
        pipeline_summary(contacts)
        return

    pipeline_summary(contacts)
    print_contacts_table(contacts)

    if not contacts:
        console.print("\n  No contacts yet. Contacts will appear here when buyers reach out.")
        return

    if args.update_all:
        for c in contacts:
            if c["follow_up_status"] not in ("Closed / Sold",):
                update_follow_up(client, c)
        return

    # Interactive: pick a contact to update
    while True:
        choice = Prompt.ask(
            "\n  Enter contact # to update, or 'q' to quit",
            default="q",
        )
        if choice.lower() == "q":
            break
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(contacts):
                update_follow_up(client, contacts[idx])
                contacts = load_contacts(client)   # refresh
                print_contacts_table(contacts)
            else:
                console.print("  [red]Invalid number[/red]")


if __name__ == "__main__":
    main()
