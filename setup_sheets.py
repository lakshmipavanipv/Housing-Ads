"""
setup_sheets.py
───────────────
One-time setup: creates the Housing-Ads-Tracker.xlsx file,
saves it locally, pushes to GitHub, and optionally uploads to Google Drive.

Usage:
    python setup_sheets.py
    python setup_sheets.py --prop1 "3BHK Banjara Hills" --prop2 "2BHK Madhapur"
    python setup_sheets.py --skip-drive      # skip Google Drive upload
    python setup_sheets.py --local-path "C:/Projects/Housing Ad"
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import TRACKER_FILE, SHEET_NAMES, HOUSING_SITES
from utils.sheets_manager import create_tracker
from utils.github_pusher import sync_all

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Set up the Housing Ads tracker .xlsx")
    parser.add_argument("--prop1",       default="Property 1 – Hyderabad", help="Display name for Property 1")
    parser.add_argument("--prop2",       default="Property 2 – Hyderabad", help="Display name for Property 2")
    parser.add_argument("--local-path",  default="",  help="Override local save folder (e.g. C:/Projects/Housing Ad)")
    parser.add_argument("--skip-drive",  action="store_true", help="Skip Google Drive upload")
    parser.add_argument("--skip-github", action="store_true", help="Skip GitHub push")
    args = parser.parse_args()

    # Override save path if provided
    if args.local_path:
        import os
        os.environ["LOCAL_SAVE_PATH"] = args.local_path
        # Re-import config values after env change
        import importlib, config, utils.sheets_manager as sm
        importlib.reload(config)
        importlib.reload(sm)
        from config import TRACKER_FILE as TF
        file_path = TF
    else:
        file_path = TRACKER_FILE

    console.print(Panel(
        f"[bold cyan]Housing Ads Tracker Setup[/bold cyan]\n"
        f"Saving to: [green]{file_path}[/green]",
        border_style="cyan"
    ))

    # ── Step 1: Create .xlsx ─────────────────────────────────────────────
    console.print("\n  [1/3] Creating tracker spreadsheet…")
    try:
        saved_path = create_tracker(args.prop1, args.prop2)
        console.print(f"  [green]✓[/green] Saved: [bold]{saved_path}[/bold]")
    except Exception as exc:
        console.print(f"  [red]✗ Failed to create tracker:[/red] {exc}")
        raise

    # ── Step 2: Push to GitHub ───────────────────────────────────────────
    if not args.skip_github:
        console.print("\n  [2/3] Pushing to GitHub…")
        ok = sync_all("Initial tracker setup – Housing Ads Tracker.xlsx")
        if ok:
            console.print("  [green]✓[/green] Pushed to GitHub")
        else:
            console.print("  [yellow]⚠[/yellow] GitHub push failed – file saved locally, push manually if needed")
    else:
        console.print("\n  [2/3] GitHub push skipped")

    # ── Step 3: Upload to Google Drive ───────────────────────────────────
    if not args.skip_drive:
        console.print("\n  [3/3] Uploading to Google Drive via browser…")
        try:
            from utils.drive_uploader import upload_to_drive
            drive_url = upload_to_drive(headless=False)
            if drive_url:
                console.print(f"  [green]✓[/green] Uploaded to Google Drive")
            else:
                console.print("  [yellow]⚠[/yellow] Drive upload incomplete")
        except Exception as exc:
            console.print(f"  [yellow]⚠ Drive upload error:[/yellow] {exc}")
            console.print(f"    You can manually upload the file from: [bold]{saved_path}[/bold]")
            console.print("    → Go to drive.google.com → drag-and-drop the .xlsx file")
    else:
        console.print("\n  [3/3] Google Drive upload skipped")

    # ── Next steps ───────────────────────────────────────────────────────
    table = Table(title="Next Steps", show_header=True, header_style="bold cyan")
    table.add_column("#", width=4)
    table.add_column("Action", width=55)

    table.add_row("1", f"Open the file:\n[bold]{saved_path}[/bold]")
    table.add_row("2", f"Go to sheet: [bold]{SHEET_NAMES['sites']}[/bold]\n"
                       "Fill in Username/Email and Password for each site")
    table.add_row("3", "Update [bold]ads/property1.html[/bold] and [bold]ads/property2.html[/bold]\n"
                       "with your real property details (edit the <meta> tags and body)")
    table.add_row("4", "Run:  [bold green]python post_ads.py[/bold green]")
    table.add_row("5", "Track progress:  [bold green]python main.py[/bold green]")
    console.print(table)


if __name__ == "__main__":
    main()
