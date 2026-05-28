#!/usr/bin/env python3
"""
install.py — Idempotent installer for claude-statusline.

Usage:
    python3 install.py

Steps:
  1. Copies the repo's canonical claude-statusline.py to ~/.claude/claude-statusline.py
     and marks it executable (mode 0o755). The repo is the source of truth; the
     installed copy at ~/.claude/ is what Claude Code runs (D-12, D-14).
  2. Parse-merge-backup ~/.claude/settings.json:
     - Read existing settings (treats missing/empty as {})
     - Back up to ~/.claude/settings.json.bak BEFORE writing
     - Merge/overwrite the "statusLine" key only
     - Preserve all other existing keys
     - Write back with json.dump(indent=2)
     - Idempotent: running twice leaves a single correct statusLine entry
  3. On malformed existing settings.json: print a clear message and exit 1
     WITHOUT overwriting (the backup step is skipped to avoid corrupting).

Security: parse-merge-backup approach (T-01-03).  Never blind-append.
          Only stdlib: os, json, shutil, stat, sys.
"""

import json
import os
import shutil
import stat
import sys


SCRIPT_NAME = "claude-statusline.py"
SETTINGS_NAME = "settings.json"
BACKUP_SUFFIX = ".bak"

CLAUDE_DIR = os.path.expanduser("~/.claude")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_SCRIPT_PATH = os.path.join(REPO_DIR, SCRIPT_NAME)
SCRIPT_PATH = os.path.join(CLAUDE_DIR, SCRIPT_NAME)
SETTINGS_PATH = os.path.join(CLAUDE_DIR, SETTINGS_NAME)
BACKUP_PATH = SETTINGS_PATH + BACKUP_SUFFIX


def ensure_executable(path: str) -> None:
    """Set executable bit (0o755) on the given file."""
    current = os.stat(path).st_mode
    desired = current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if current != desired:
        os.chmod(path, 0o755)
        print(f"  Set executable: {path}")
    else:
        print(f"  Already executable: {path}")


def load_settings(path: str) -> dict:
    """Load settings.json; return {} if missing or empty."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return {}
    return json.loads(content)  # raises json.JSONDecodeError on malformed input


def write_settings(path: str, data: dict) -> None:
    """Write settings dict to path as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def build_status_line_entry(script_path: str) -> dict:
    """Build the statusLine entry pointing at the installed script."""
    return {
        "type": "command",
        "command": f"python3 {script_path}",
    }


def main() -> int:
    print("claude-statusline installer")
    print("=" * 40)

    # ---- Step 1: Copy the repo's canonical script into ~/.claude and chmod ----
    if not os.path.exists(REPO_SCRIPT_PATH):
        print(f"ERROR: Canonical script not found at {REPO_SCRIPT_PATH}")
        print("  Run install.py from the claude-statusline repo (it ships claude-statusline.py).")
        return 1

    os.makedirs(CLAUDE_DIR, exist_ok=True)
    shutil.copy2(REPO_SCRIPT_PATH, SCRIPT_PATH)
    print(f"  Installed script: {REPO_SCRIPT_PATH} -> {SCRIPT_PATH}")
    ensure_executable(SCRIPT_PATH)

    # ---- Step 2: Parse existing settings.json ----
    print(f"\nReading {SETTINGS_PATH} ...")
    try:
        settings = load_settings(SETTINGS_PATH)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {SETTINGS_PATH} contains malformed JSON: {exc}")
        print("  Refusing to overwrite.  Fix or remove the file and re-run.")
        return 1

    # ---- Step 3: Back up BEFORE any write ----
    if os.path.exists(SETTINGS_PATH):
        shutil.copy2(SETTINGS_PATH, BACKUP_PATH)
        print(f"  Backup written: {BACKUP_PATH}")
    else:
        print(f"  No existing {SETTINGS_PATH} — creating fresh.")

    # ---- Step 4: Merge statusLine, preserve all other keys ----
    new_entry = build_status_line_entry(SCRIPT_PATH)
    existing_entry = settings.get("statusLine")

    if existing_entry == new_entry:
        print(f"\nstatusLine already correct — no changes needed.")
    else:
        settings["statusLine"] = new_entry
        write_settings(SETTINGS_PATH, settings)
        print(f"\nMerged statusLine entry into {SETTINGS_PATH}")
        print(f"  command: {new_entry['command']}")

    # ---- Step 5: Confirm ----
    print("\nInstall complete.")
    print(f"  Script   : {SCRIPT_PATH}")
    print(f"  Settings : {SETTINGS_PATH}")
    print(f"  Backup   : {BACKUP_PATH}")
    print("\nRestart Claude Code to pick up the new statusLine command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
