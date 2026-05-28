#!/usr/bin/env python3
"""
install.py — Idempotent installer for claude-statusline (Phase 2).

Usage:
    python3 install.py

Steps:
  1. Create install dir: ~/.claude/claude-statusline/
  2. Build a .venv inside the install dir (python -m venv)
  3. pip install requests astral into the venv
  4. Copy the repo's canonical claude-statusline.py into the install dir and mark executable
  5. Copy a default claude-statusline.toml config ONLY if one doesn't already exist
     (never clobber an existing user config — T-02-04)
  6. Parse-merge-backup ~/.claude/settings.json:
     - Read existing settings (treats missing/empty as {})
     - Back up to ~/.claude/settings.json.bak BEFORE writing
     - Merge/overwrite the "statusLine" key only (points at new SCRIPT_PATH, uses python3
       — the script self-re-execs into its venv, settings.json needs no venv path, D2-03)
     - Preserve all other existing keys
     - Write back with json.dump(indent=2)
     - Idempotent: running twice leaves a single correct statusLine entry
  7. On malformed existing settings.json: print a clear message and exit 1
     WITHOUT overwriting (the backup step is skipped to avoid corrupting).

Security:
  - subprocess.run invoked with FIXED argument-vector lists, never shell=True (T-02-02)
  - Default config copied only when config does not exist (T-02-04)
  - parse-merge-backup approach for settings.json (T-01-03); never blind-append
  - Only stdlib: os, json, shutil, stat, subprocess, sys
"""

import json
import os
import shutil
import stat
import subprocess
import sys


SCRIPT_NAME   = "claude-statusline.py"
CONFIG_NAME   = "claude-statusline.toml"
SETTINGS_NAME = "settings.json"
BACKUP_SUFFIX = ".bak"

# Install root: self-contained subfolder under ~/.claude (D2-02)
INSTALL_DIR  = os.path.expanduser("~/.claude/claude-statusline")
VENV_DIR     = os.path.join(INSTALL_DIR, ".venv")
SCRIPT_PATH  = os.path.join(INSTALL_DIR, SCRIPT_NAME)
CONFIG_PATH  = os.path.join(INSTALL_DIR, CONFIG_NAME)

# Settings.json lives in the parent ~/.claude dir
CLAUDE_DIR    = os.path.expanduser("~/.claude")
SETTINGS_PATH = os.path.join(CLAUDE_DIR, SETTINGS_NAME)
BACKUP_PATH   = SETTINGS_PATH + BACKUP_SUFFIX

# Repo paths
REPO_DIR         = os.path.dirname(os.path.abspath(__file__))
REPO_SCRIPT_PATH = os.path.join(REPO_DIR, SCRIPT_NAME)
REPO_CONFIG_PATH = os.path.join(REPO_DIR, CONFIG_NAME)

# Default config content (written when no user config exists)
DEFAULT_CONFIG_CONTENT = """\
# claude-statusline configuration
# Edit this file to enable weather: set [location] lat/lon and [weather] contact_email.
# All values have built-in defaults; this file only needs the keys you want to override.

# [location]
# lat = 39.7392     # your latitude  (decimal degrees, positive = North)
# lon = -104.9903   # your longitude (decimal degrees, negative = West)

# [weather]
# contact_email = "your-email@example.com"  # required by NWS ToS (never emitted to stdout)
# show_weather = true

# [units]
# temp_unit = "F"   # or "C"

# [cache]
# weather_ttl = 600        # seconds to cache conditions (default 10 min)
# alerts_ttl = 300         # seconds to cache alerts (default 5 min)
# weather_max_stale = 3600 # max age (seconds) before dropping stale conditions (default 1 h)
# alerts_max_stale = 900   # max age (seconds) before dropping stale alerts (default 15 min)

# [thresholds]
# warn = 70
# crit = 90

# [toggles]
# show_context_bar = true
# show_five_hour = true
# show_weekly = true
# show_thinking_glyph = true
"""


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
    """Write settings dict to path as pretty-printed JSON, atomically (WR-02).

    Write to a temp file in the same directory, then os.replace() so a crash
    mid-write can never leave a truncated/corrupt settings.json.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def build_status_line_entry(script_path: str) -> dict:
    """Build the statusLine entry pointing at the installed script.

    Command uses python3 (not the venv python) — the script self-re-execs
    into its own venv at startup (D2-03), so settings.json needs no venv path.
    """
    return {
        "type": "command",
        "command": f"python3 {script_path}",
    }


def main() -> int:
    print("claude-statusline installer (Phase 2)")
    print("=" * 40)

    # ---- Step 1: Create install directory ----
    os.makedirs(INSTALL_DIR, exist_ok=True)
    print(f"  Install dir: {INSTALL_DIR}")

    # ---- Step 2: Build .venv (fixed argv list — T-02-02: no shell=True) ----
    print(f"\nBuilding virtual environment at {VENV_DIR} ...")
    subprocess.run(
        [sys.executable, "-m", "venv", VENV_DIR],
        check=True,
    )
    venv_python = os.path.join(VENV_DIR, "bin", "python")
    venv_pip    = os.path.join(VENV_DIR, "bin", "pip")
    print(f"  venv python: {venv_python}")

    # ---- Step 3: pip install requests astral (fixed argv list — T-02-02) ----
    print("\nInstalling dependencies (requests, astral) ...")
    subprocess.run(
        [venv_pip, "install", "requests", "astral"],
        check=True,
    )

    # ---- Step 4: Copy the repo's canonical script and chmod ----
    if not os.path.exists(REPO_SCRIPT_PATH):
        print(f"ERROR: Canonical script not found at {REPO_SCRIPT_PATH}")
        print("  Run install.py from the claude-statusline repo directory.")
        return 1

    shutil.copy2(REPO_SCRIPT_PATH, SCRIPT_PATH)
    print(f"\n  Installed script: {REPO_SCRIPT_PATH} -> {SCRIPT_PATH}")
    ensure_executable(SCRIPT_PATH)

    # ---- Step 5: Copy default config ONLY if none exists (T-02-04) ----
    if os.path.exists(CONFIG_PATH):
        print(f"  Config already exists — NOT overwriting: {CONFIG_PATH}")
    else:
        # Try to copy from repo if it exists; otherwise write the built-in default.
        if os.path.exists(REPO_CONFIG_PATH):
            shutil.copy2(REPO_CONFIG_PATH, CONFIG_PATH)
            print(f"  Installed config: {REPO_CONFIG_PATH} -> {CONFIG_PATH}")
        else:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(DEFAULT_CONFIG_CONTENT)
            print(f"  Created default config: {CONFIG_PATH}")

    # ---- Step 6: Parse existing settings.json ----
    print(f"\nReading {SETTINGS_PATH} ...")
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    try:
        settings = load_settings(SETTINGS_PATH)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {SETTINGS_PATH} contains malformed JSON: {exc}")
        print("  Refusing to overwrite.  Fix or remove the file and re-run.")
        return 1

    # ---- Step 7: Back up BEFORE any write ----
    if os.path.exists(SETTINGS_PATH):
        shutil.copy2(SETTINGS_PATH, BACKUP_PATH)
        print(f"  Backup written: {BACKUP_PATH}")
    else:
        print(f"  No existing {SETTINGS_PATH} — creating fresh.")

    # ---- Step 8: Merge statusLine, preserve all other keys ----
    new_entry = build_status_line_entry(SCRIPT_PATH)
    existing_entry = settings.get("statusLine")

    if existing_entry == new_entry:
        print("\nstatusLine already correct — no changes needed.")
    else:
        settings["statusLine"] = new_entry
        write_settings(SETTINGS_PATH, settings)
        print(f"\nMerged statusLine entry into {SETTINGS_PATH}")
        print(f"  command: {new_entry['command']}")

    # ---- Confirm ----
    print("\nInstall complete.")
    print(f"  Script   : {SCRIPT_PATH}")
    print(f"  Venv     : {venv_python}")
    print(f"  Config   : {CONFIG_PATH}")
    print(f"    -> Edit [location] lat/lon and [weather] contact_email to enable weather.")
    print(f"  Settings : {SETTINGS_PATH}")
    print(f"  Backup   : {BACKUP_PATH}")
    print("\nRestart Claude Code to pick up the new statusLine command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
