"""
github_pusher.py
────────────────
Auto-commit and push the updated tracker .xlsx to GitHub
after every significant change.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

from config import TRACKER_FILE, TRACKER_FILE_GIT, GIT_BRANCH, PROJECT_DIR


def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        check=check,
    )


def push_tracker(message: str = "") -> bool:
    """
    Stage the tracker .xlsx, commit, and push to the remote branch.
    Returns True on success.
    """
    # Use the git-trackable copy (always inside the project dir)
    git_copy = TRACKER_FILE_GIT if TRACKER_FILE_GIT.exists() else TRACKER_FILE

    if not git_copy.exists():
        print(f"  [GitHub Push] Tracker file not found: {git_copy}")
        return False

    try:
        # Stage the git copy (relative path inside the repo)
        rel_path = git_copy.relative_to(PROJECT_DIR)
        _git(["add", str(rel_path)])

        # Also stage any JSON data exports if present
        for json_file in PROJECT_DIR.glob("data/*.json"):
            try:
                _git(["add", str(json_file.relative_to(PROJECT_DIR))])
            except Exception:
                pass

        # Check if there's anything to commit
        status = _git(["status", "--porcelain"])
        if not status.stdout.strip():
            print("  [GitHub Push] Nothing to commit – tracker unchanged.")
            return True

        commit_msg = message or f"Update Housing Ads Tracker – {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        _git(["commit", "-m", commit_msg])

        result = _git(["push", "-u", "origin", GIT_BRANCH], check=False)
        if result.returncode == 0:
            print(f"  [GitHub] Pushed to {GIT_BRANCH}")
            return True
        else:
            print(f"  [GitHub Push Error] {result.stderr.strip()}")
            return False

    except subprocess.CalledProcessError as exc:
        print(f"  [GitHub Push Error] {exc.stderr}")
        return False
    except Exception as exc:
        print(f"  [GitHub Push Error] {exc}")
        return False


def export_to_json():
    """
    Export property stats and contacts to JSON files in data/ folder
    for easier viewing on GitHub.
    """
    from utils.sheets_manager import load_property_stats, load_contacts
    import json

    data_dir = PROJECT_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    try:
        p1 = load_property_stats("property1")
        p2 = load_property_stats("property2")
        contacts = load_contacts()

        (data_dir / "property1_status.json").write_text(
            json.dumps(p1, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (data_dir / "property2_status.json").write_text(
            json.dumps(p2, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Contacts – mask phone/email for privacy on GitHub
        contacts_safe = []
        for c in contacts:
            safe = dict(c)
            if safe.get("phone"):
                safe["phone"] = safe["phone"][:4] + "XXXXXX"
            if safe.get("email"):
                safe["email"] = safe["email"][:3] + "***"
            contacts_safe.append(safe)
        (data_dir / "contacts.json").write_text(
            json.dumps(contacts_safe, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  [Data] JSON exports saved to {data_dir}/")

    except Exception as exc:
        print(f"  [Data Export Warning] {exc}")


def sync_all(message: str = "") -> bool:
    """Export JSON data + push tracker + JSON to GitHub."""
    export_to_json()
    return push_tracker(message)
