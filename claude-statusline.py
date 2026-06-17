#!/usr/bin/env python3
"""
claude-statusline — Plan 02-02 (weather layer: NWS cache + fetch)

Reads one JSON object from stdin (Claude Code's session data), renders a
two-line status bar to stdout, and exits 0.  Never emits a Python traceback.

Top line   (Plan 01):  [project] [model 💭]
Top line   (Plan 02):  [project] [model 💭] [<icon> <temp> | 🌧️<pop>% | <sun-or-alert>]
Bottom line (Plan 02): [<20-wide ▓░ bar>] <pct>%   ⏳ <5h%>[ <reset>]   🗓 <wk%>[ <reset>]
Plan 03:   Reads TOML config at ~/.claude/claude-statusline/claude-statusline.toml;
           silent defaults on any error; per-segment toggles; configurable thresholds.
"""

# ---------------------------------------------------------------------------
# Venv self-re-exec bootstrap (D2-03)
# Must appear before heavy imports so the re-exec is cheap.
# Guard with os.path.exists() so a missing venv NEVER hard-fails the bar.
# The sys.executable comparison prevents infinite loops if already in the venv.
# ---------------------------------------------------------------------------

import os
import sys

_VENV_PY = os.path.expanduser("~/.claude/claude-statusline/.venv/bin/python")


def _reexec_into_venv() -> None:
    """Re-exec under the install's venv interpreter so requests/astral import (D2-03).

    MUST be called only from the __main__ entrypoint — NEVER at module top level.
    Running it on import would let any `import` of this module (e.g. pytest collecting
    the test suite) trigger a process-replacing exec and silently hijack the importing
    process once the venv exists. Guard: skip when already under the venv, or when the
    venv is absent (then weather degrades but the bar still renders).
    """
    if sys.executable != _VENV_PY and os.path.exists(_VENV_PY):
        os.execv(_VENV_PY, [_VENV_PY, __file__, *sys.argv[1:]])

# ---------------------------------------------------------------------------
# Third-party dep guards (D2-12 layered degradation)
# If astral or requests are unavailable, the weather segment is omitted;
# the Phase-1 bar (project, model, bottom line) renders completely untouched.
# ---------------------------------------------------------------------------

try:
    import astral  # noqa: F401
    from astral import LocationInfo
    from astral.sun import sun
    from astral.moon import phase as _moon_phase  # D-04: live moon phase (0–27.99)
    _ASTRAL_OK = True
except Exception:
    _ASTRAL_OK = False

try:
    import requests  # noqa: F401
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

# _WEATHER_OK: True only when BOTH astral AND requests are importable.
_WEATHER_OK = _ASTRAL_OK and _REQUESTS_OK

import copy
import json
import math
import re
import subprocess
import tomllib
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# ANSI color constants
# ---------------------------------------------------------------------------

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"    # dim/neutral — used for reset times (D-04)
BOLD   = "\033[1m"    # bold/bright — used for Immediate+Observed alert intensity (D-06)
RESET  = "\033[0m"
DEFAULT_FG = "\033[39m"  # default foreground only — neutral hue that preserves BOLD/DIM
                         # (unlike RESET, which cancels intensity); see _alert_color (WR-01/D-06)

# Semantic weather colors (Phase 02.1, D-08) — TOP-LINE ONLY.
# Do NOT use these on the bottom line; GREEN/YELLOW/RED there carry
# usage-threshold semantics and must not be mixed with weather coloring.
BLUE    = "\033[34m"   # rain
CYAN    = "\033[36m"   # snow / freezing rain
MAGENTA = "\033[35m"   # thunderstorm
GRAY    = "\033[90m"   # fog / haze (bright black)

# Bar fill characters — Phase 3 preset table (D-01, D-03, D-08/D-09).
# _BAR_PRESETS maps bar_style name → (filled_glyph, empty_glyph).
# Closed at exactly four entries per D-03: shade, solid, solid-dim, gradient.
# ascii, dots, braille, and powerline fills are explicitly excluded.
# gradient math (sub-cell boundary cell) is implemented in Plan 03-02.
_BAR_PRESETS: dict[str, tuple[str, str]] = {
    "shade":     ("▓", "░"),   # default — current look (D-09)
    "solid":     ("█", "░"),   # full block + light shade
    "solid-dim": ("█", "▒"),   # full block + medium shade
    "gradient":  ("█", " "),   # Plan 03-02: sub-cell boundary cell + blank track
}
# Backward-compat references kept for any code that still uses the bare names.
_FILLED = _BAR_PRESETS["shade"][0]   # "▓"
_EMPTY  = _BAR_PRESETS["shade"][1]   # "░"
_BAR_WIDTH = 20
# Partial-block glyphs for the gradient preset (D-02): left-aligned, 1/8 → 7/8 precision.
# Index i corresponds to remainder == i+1 (1/8 through 7/8 of a cell).
_GRADIENT_PARTIAL = ("▏", "▎", "▍", "▌", "▋", "▊", "▉")   # 7 glyphs, 1/8..7/8


def _bar_preset(style: object) -> tuple[str, str]:
    """Return (filled_glyph, empty_glyph) for *style*, falling back to shade (RUN-02).

    Never raises — an unknown/missing bar_style silently returns the shade pair.
    A non-string value (e.g. a TOML array/table/number) is treated as unknown
    and also falls back to shade, so dict.get() is never handed a non-hashable
    key (RUN-02: malformed config must degrade, not drop the bar).
    """
    if not isinstance(style, str):
        return _BAR_PRESETS["shade"]
    return _BAR_PRESETS.get(style, _BAR_PRESETS["shade"])


# ---------------------------------------------------------------------------
# Built-in defaults (D-07) — guaranteed even with no config file
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "thresholds": {
        "warn": 70,
        "crit": 90,
    },
    "toggles": {
        "show_context_bar":    True,
        "show_five_hour":      True,
        "show_weekly":         True,
        "show_thinking_glyph": True,
    },
    "units": {
        "temp_unit": "F",  # or "C"
    },
    # Phase-2 location — set lat/lon in claude-statusline.toml for weather/sun (D-09)
    "location": {
        "lat": 0.0,
        "lon": 0.0,
    },
    # Phase-2 cache — TTL (seconds) for weather and alert caching (D2-07)
    "cache": {
        "weather_ttl":        600,    # 10 min
        "alerts_ttl":         300,    # 5 min
        "weather_max_stale":  3600,   # 1 hour ceiling before dropping stale obs
        "alerts_max_stale":   900,    # 15 min ceiling before dropping stale alerts
        # Phase 06: Claude status cache TTL (D-05 — same cadence as alerts)
        "status_ttl":         300,    # 5 min
        "status_max_stale":   900,    # 15 min ceiling before dropping stale status
    },
    # Phase-2 weather settings (D2-12)
    "weather": {
        "contact_email": "your-email@example.com",  # required by NWS ToS for User-Agent
        "show_weather":  True,
        "pop_min":       30,    # hide precip chunk below this PoP% (sub-threshold = noise)
    },
    # Phase 02.1: glyph set selection (D-06, D-07)
    # "nerd" (default) uses Weather Icons / Nerd Font PUA codepoints.
    # "emoji" falls back to the Phase 2 emoji tables (retained, not deleted).
    # A single global switch — one key flips all four converted segments (D-07).
    "display": {
        "icon_set": "nerd",     # "nerd" (default) or "emoji"
        # Phase 03: context-bar fill style (D-08/D-09).
        # "shade" (default) keeps the existing ▓/░ look — zero change for existing installs.
        # Other values: "solid", "solid-dim", "gradient".  Independent of icon_set (D-10).
        "bar_style": "shade",   # "shade" | "solid" | "solid-dim" | "gradient"
        # Phase 04: git segment toggle (D-08 discretion: display.show_git).
        # True (default) renders the git segment on the top line when in a git repo.
        # Set to false in [display] to suppress the segment (e.g. in test configs).
        "show_git": True,
        # Phase 05: GSD segment toggle (D-08 discretion: display.show_gsd).
        # True (default) renders the GSD segment when .planning/ exists under project_dir.
        # Set to false in [display] to suppress the segment (e.g. in test configs).
        "show_gsd": True,
        # Phase 06: Claude service-health segment toggle (D-08 discretion: display.show_claude_status).
        # True (default) renders the Claude status segment when a noteworthy event is detected.
        # Quiet when all tracked components are healthy (D-01). Set to false to suppress.
        "show_claude_status": True,
    },
    # Phase 07: Claude-status incident filter (D-06). Hand-edited TOML only —
    # the tool NEVER rewrites this table (id-dismissals live in the tool-owned
    # store, D-05). A bad regex degrades to no-match, never crashes (D-10).
    "claude_status": {
        "filter_enabled": True,            # master toggle for the suppression filter
        "ignore_title_patterns": [],       # title patterns (e.g. "Mythos", "Fable")
    },
}


# ---------------------------------------------------------------------------
# Config loader (D-06, D-07, D-09)
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a deep copy of *base*.

    Keys present in *base* but absent in *override* keep their base value.
    Keys present in *override* but absent in *base* are added (D-09: Phase-2
    keys are accepted without error).
    Nested dicts are merged recursively; non-dict values are replaced.
    """
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(path: str | None = None) -> dict:
    """Load TOML config at *path* (default: ~/.claude/claude-statusline/claude-statusline.toml).

    On ANY error (file missing, unreadable, malformed TOML) the function
    returns a deep copy of DEFAULTS silently — no exception, no traceback
    (D-07, T-01-07, T-01-08, security_context: no code execution).

    On success, the parsed values are deep-merged over DEFAULTS so absent
    keys keep their defaults and extra Phase-2 keys (location.lat/lon, cache
    TTLs) are silently retained/ignored in Phase 1 (D-09).

    Config path supersedes Phase 1 D-06: now inside the subfolder (D2-02).
    """
    if path is None:
        path = os.path.expanduser("~/.claude/claude-statusline/claude-statusline.toml")
    try:
        with open(path, "rb") as fh:
            parsed = tomllib.load(fh)
        return _deep_merge(DEFAULTS, parsed)
    except Exception:
        # FileNotFoundError, tomllib.TOMLDecodeError, OSError, PermissionError,
        # or any other error — always fall back silently to built-in defaults.
        return copy.deepcopy(DEFAULTS)


# ---------------------------------------------------------------------------
# Sectioned cache.json helpers (D2-05, D2-06, D2-07, D2-12)
#
# Cache path: ~/.claude/claude-statusline/cache.json
# Structure (three independently-timestamped sections — D2-06):
#   {
#     "geo":     { "fetched_at": <epoch>, "cwa": ..., "gridX": ..., "gridY": ..., "station_id": ... },
#     "weather": { "fetched_at": <epoch>, "text_desc": str, "icon_url": str,
#                  "temp": int|null, "pop": int|null },
#     "alerts":  { "fetched_at": <epoch>, "active": [...] }
#   }
#
# Phase 02.1 change (D-04/D-07): the weather section now stores the raw NWS
# tokens (textDescription + icon URL) instead of a pre-resolved glyph in "icon".
# Glyph resolution happens at render time in _weather_segment via _icon_to_glyph.
# This allows the icon_set toggle to take effect immediately (D-07) and the
# clear-night moon phase to reflect the live current phase (D-04).
#
# All helpers return safe defaults / swallow errors so a corrupt cache can never
# crash the render (D-10 never-crash discipline).
# ---------------------------------------------------------------------------

_CACHE_PATH = os.path.expanduser("~/.claude/claude-statusline/cache.json")


def read_cache(path: str | None = None) -> dict:
    """Load cache.json; return {} on any error (cold cache, malformed JSON, etc.).

    Mirrors load_config's read-with-silent-fallback discipline (D-07).
    """
    if path is None:
        path = _CACHE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def write_cache_section(path: str | None, section_name: str, payload: dict, now: float) -> None:
    """Atomically write one section of cache.json (temp file then os.replace — D2-10/T-02-10).

    Reads the existing cache (or {} on any read error), sets cache[section_name]
    to a dict of { "fetched_at": now, **payload }, then writes the WHOLE cache.json
    atomically via a temp file in the same directory followed by os.replace.

    The temp-then-replace approach ensures the render path never reads a half-written
    file (mirrors install.py write_settings shape).

    Any error during write is swallowed so a failing cache write can never crash the render.
    """
    if path is None:
        path = _CACHE_PATH
    try:
        # Load existing cache (or start fresh)
        cache = read_cache(path)
        # Merge section
        section_data = {"fetched_at": now}
        section_data.update(payload)
        cache[section_name] = section_data
        # Atomic write: temp file in same dir, then os.replace
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        # Any OS/JSON error is swallowed — cache miss on next render, not a crash
        pass


# ---------------------------------------------------------------------------
# Phase 07: Tool-owned dismissal store (D-05)
#
# Modeled VERBATIM on read_cache / write_cache_section above:
#  - same cache dir (~/.claude/claude-statusline/)
#  - same atomic temp-then-os.replace write pattern
#  - same corrupt/missing → safe-default discipline (corrupt → {} → no suppression)
#
# The store maps incident id → {"impact_at_dismiss": str, "dismissed_at": float}.
# The tool fully owns this file; it NEVER writes the user's TOML (D-05).
# ---------------------------------------------------------------------------

_DISMISSALS_PATH = os.path.expanduser("~/.claude/claude-statusline/status_dismissals.json")


def read_dismissals(path: str | None = None) -> dict:
    """Load the dismissal store; return {} on any error (missing, corrupt, non-dict).

    Mirrors read_cache's read-with-silent-fallback discipline:
    corrupt / missing → {} → no suppression (D-05, T-07-01).
    """
    if path is None:
        path = _DISMISSALS_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def write_dismissals(store: dict, path: str | None = None) -> None:
    """Atomically write the whole dismissal store (temp file then os.replace — T-07-02).

    Writes the flat dict as a single JSON object — no per-section merge (unlike
    write_cache_section, which merges sections; here we own the whole file).

    Any error during write is swallowed so a failing store write never crashes the bar.
    """
    if path is None:
        path = _DISMISSALS_PATH
    try:
        # Atomic write: temp file in same dir, then os.replace
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        # Any OS/JSON error is swallowed — store miss on next render, not a crash
        pass


def _dismiss_id(inc_id: str, impact_at_dismiss: str, path: str | None = None) -> None:
    """Add an id-dismiss entry to the store.

    Records impact_at_dismiss (used for escalation re-surface, D-03) and dismissed_at
    (epoch float).  No-op on empty inc_id (guard against caller passing "" or None).
    Swallows all errors — never raises.
    """
    if not inc_id:
        return
    try:
        import time as _time
        store = read_dismissals(path)
        store[inc_id] = {
            "impact_at_dismiss": impact_at_dismiss,
            "dismissed_at": _time.time(),
        }
        write_dismissals(store, path)
    except Exception:
        pass


def _undismiss_id(inc_id: str, path: str | None = None) -> None:
    """Remove an id-dismiss entry from the store.

    No-op if inc_id is not in the store.  Swallows all errors — never raises.
    """
    try:
        store = read_dismissals(path)
        store.pop(inc_id, None)
        write_dismissals(store, path)
    except Exception:
        pass


def _prune_dismissals(store: dict, live_ids: object) -> dict:
    """Return a new dict containing only entries whose id is in live_ids.

    Pure / side-effect-free: the input store is never modified (caller persists
    the result via write_dismissals if desired — D-04 auto-prune).  Safe on any
    input type for live_ids (non-sets/non-iterables degrade to returning {}).
    """
    try:
        return {k: v for k, v in store.items() if k in live_ids}
    except Exception:
        return {}


def section_is_fresh(section: dict, ttl: float, now: float) -> bool:
    """Return True when the section's fetched_at is within the given TTL.

    False when fetched_at is missing, non-numeric, or older than ttl seconds
    from now.  A False result triggers a background refresh (D2-05).
    """
    try:
        fetched_at = float(section["fetched_at"])
        return (now - fetched_at) < ttl
    except Exception:
        return False


def section_within_ceiling(section: dict, max_stale: float, now: float) -> bool:
    """Return True when the section's fetched_at is within the max-stale ceiling.

    False when fetched_at is missing, non-numeric, or older than max_stale seconds
    from now.  A False result means the data is too stale to display — drop to
    the degraded (sun-only) fallback (D2-12).
    """
    try:
        fetched_at = float(section["fetched_at"])
        return (now - fetched_at) <= max_stale
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NWS fetch layer (D2-05, D2-08, D2-09)
#
# ALL network I/O runs ONLY in the detached background child (--refresh mode).
# The render path reads cache.json and returns instantly — it never calls
# any function in this section directly (D2-05 / critical reminder).
#
# NWS User-Agent is required by api.weather.gov ToS; a 403 is returned
# without it.  contact_email is read from cfg and placed ONLY in the
# User-Agent header — never printed to stdout (T-02-06).
# ---------------------------------------------------------------------------

# Version constant — embedded in the User-Agent.
# Keep in sync with pyproject.toml.
_APP_VERSION = "0.2.0"

# Lockfile path — created with exclusive mode to prevent concurrent fetches (T-02-09).
_LOCK_PATH = os.path.expanduser("~/.claude/claude-statusline/refresh.lock")


# ---------------------------------------------------------------------------
# Nerd Font / Weather Icons glyph constants (Phase 02.1, D-03, D-04)
#
# All codepoints are from the Weather Icons range bundled in Nerd Fonts
# (nf-weather-* alias, PUA block starting at U+E300).
# Each constant is named _WI_<CONDITION> or _NF_<CONDITION> and holds the
# single Unicode character. Trailing comments name the wi-*/nf-* identifier
# and hex codepoint for traceability.
#
# These constants are consumed by Plans 02 and 03.  This plan defines them
# all here so downstream plans never re-derive codepoints.
# ---------------------------------------------------------------------------

# --- Condition icons: day variants ---
_WI_DAY_CLEAR        = ""   # wi-day-sunny           U+E30D
_WI_DAY_PARTLY       = ""   # wi-day-cloudy          U+E302

# --- Condition icons: night variants ---
_WI_NIGHT_CLEAR      = ""   # wi-night-clear         U+E32B
_WI_NIGHT_PARTLY     = ""   # wi-night-alt-cloudy    U+E379

# --- Cloud / overcast (day/night neutral) ---
_WI_CLOUDY           = ""   # wi-cloudy              U+E312

# --- Precipitation ---
_WI_RAIN             = ""   # wi-rain                U+E318
_WI_RAIN_SHOWERS     = ""   # wi-showers             U+E319
_WI_SNOW             = ""   # wi-snow                U+E31A
_WI_SLEET            = ""   # wi-sleet               U+E3AD
_WI_FREEZING_RAIN    = ""   # wi-rain-mix            U+E316
_WI_RAIN_SNOW        = ""   # wi-rain-mix (rain-snow U+E316 — same glyph)

# --- Severe / thunderstorm ---
_WI_THUNDERSTORM      = ""  # wi-thunderstorm        U+E31D
_WI_THUNDERSTORM_RAIN = ""  # wi-storm-showers       U+E31C

# --- Low visibility ---
_WI_FOG              = ""   # wi-fog                 U+E313

# --- Wind ---
_WI_WINDY            = ""   # wi-windy               U+E31E

# --- Sun events (used by _sun_segment in Plan 03) ---
_WI_SUNRISE          = ""   # wi-sunrise             U+E34C
_WI_SUNSET           = ""   # wi-sunset              U+E34D

# --- Precipitation probability indicator (used by precip chunk in _weather_segment) ---
_WI_RAINDROPS        = ""   # weather-raindrops      U+E34A

# --- Thinking indicator (Plan 03: model segment; Claude's Discretion) ---
_NF_THINKING         = ""   # nf-fa-lightbulb        U+F0EB

# --- Rate-limit glyphs (Plan 03: rate segment; Claude's Discretion) ---
_NF_HOURGLASS        = ""   # nf-fa-hourglass        U+F254  (5h window)
_NF_CALENDAR         = ""   # nf-fa-calendar         U+F073  (weekly window)

# --- Fallback (single-cell thermometer) ---
_WI_FALLBACK         = ""   # wi-thermometer         U+E33D

# ---------------------------------------------------------------------------
# Git segment glyph constants (Phase 04, Plan 02)
#
# Nerd Font codepoints chosen from the powerline / font-awesome ranges and
# validated against the installed JetBrains Nerd Font cmap (test_nerd_icons.py).
# ---------------------------------------------------------------------------

# Branch glyph (powerline branch symbol — the universally recognized git branch icon)
_NF_GIT_BRANCH   = ""   # nf-pl-branch        U+E0A0

# Worktree glyph (code fork — visually suggests a branch diverging from main)
_NF_GIT_WORKTREE = ""   # nf-fa-code_fork     U+F126

# Dirty-state marker (asterisk — concise single-cell flag for uncommitted changes)
_NF_GIT_DIRTY    = ""   # nf-fa-asterisk      U+F069

# Ahead-of-upstream marker (arrow up — "you are ahead")
_NF_GIT_AHEAD    = ""   # nf-fa-arrow_up      U+F062

# Behind-upstream marker (arrow down — "you are behind")
_NF_GIT_BEHIND   = ""   # nf-fa-arrow_down    U+F063

# ---------------------------------------------------------------------------
# GSD segment glyphs — Phase 05 lifecycle / plan indicators
#
# Codepoints validated against the installed JetBrains Nerd Font cmap
# (test_nerd_icons.py installed-font cmap guard).
# ---------------------------------------------------------------------------

# Executing glyph (play button — actively running a plan right now)
_NF_GSD_EXECUTING = ""   # nf-fa-play          U+F04B  (green: actively running)

# Verifying glyph (checkbox square — verification step in progress)
_NF_GSD_VERIFYING = ""   # nf-fa-check_square  U+F046  (yellow: verification step)

# Blocked glyph (ban circle — blocked, cannot proceed)
_NF_GSD_BLOCKED   = ""   # nf-fa-ban           U+F05E  (red: blocked)

# Done glyph (check circle — milestone fully complete)
_NF_GSD_DONE      = ""   # nf-fa-check_circle  U+F058  (green: milestone complete)

# Idle glyph (pause button — parked / next-up, not actively executing)
_NF_GSD_IDLE      = ""   # nf-fa-pause         U+F04C  (dim: parked / next-up)

# Plan slot glyph (map — the plan/roadmap label icon)
_NF_GSD_PLAN      = ""   # nf-fa-map           U+F278  (neutral: plan slot label)

# ---------------------------------------------------------------------------
# Claude service-health glyph constants (Phase 06, D-03/D-04)
#
# Two codepoints — incident severity and maintenance — following the same
# literal-codepoint-per-state + intent-comment pattern as _NF_GSD_* above.
# Codepoints from the nf-fa-* (U+F0xx) range for consistency.
#
# Semantic rationale:
#   Incident  -> fa-exclamation-circle  (U+F06A): urgent problem -- act now
#   Maint     -> fa-wrench              (U+F0AD): maintenance/repair -- planned work
#
# DISTINCT glyphs for incident vs. maintenance (D-04): maintenance uses a neutral
# wrench glyph rather than a severity exclamation; this prevents conflating
# scheduled maintenance with an unplanned outage.
# ---------------------------------------------------------------------------

# Incident glyph (exclamation circle -- unresolved incident on a tracked component)
_NF_CLAUDE_INCIDENT = ""   # nf-fa-exclamation_circle  U+F06A  (severity: problem active)

# Maintenance glyph (wrench -- scheduled or in-progress maintenance window)
_NF_CLAUDE_MAINT    = ""   # nf-fa-wrench               U+F0AD  (neutral: planned work)

# ---------------------------------------------------------------------------
# Alert-class glyph constants (Phase 02.2, D-04)
#
# One nerd codepoint per hazard class — replaces the single ⚠ hardcode.
# Codepoints chosen from the nf-fa-* (U+F0xx) range, all validated against
# the installed JetBrains Nerd Font cmap (test_nerd_icons.py cmap guard).
#
# Semantic rationale:
#   Warning    → fa-warning     (U+F071): glyph name literally "fa-warning" — act now
#   Watch      → fa-eye         (U+F06E): watching/observing — be prepared
#   Advisory   → fa-info_circle (U+F05A): information/advisory — be aware
#   Statement  → fa-bell        (U+F0F3): general notification — neutral
# ---------------------------------------------------------------------------

_WI_ALERT_WARNING   = ""   # nf-fa-warning       U+F071  (Warning: act now)
_WI_ALERT_WATCH     = ""   # nf-fa-eye           U+F06E  (Watch: be prepared)
_WI_ALERT_ADVISORY  = ""   # nf-fa-info_circle   U+F05A  (Advisory: be aware)
_WI_ALERT_STATEMENT = ""   # nf-fa-bell          U+F0F3  (Statement/Other: neutral)

# Nerd Font glyph per alert class — resolved at render time via icon_set (D-04).
_ALERT_CLASS_GLYPHS_NERD: dict = {
    "Warning":         _WI_ALERT_WARNING,
    "Watch":           _WI_ALERT_WATCH,
    "Advisory":        _WI_ALERT_ADVISORY,
    "Statement/Other": _WI_ALERT_STATEMENT,
}

# Emoji fallback glyph per alert class — used when icon_set != "nerd" (D-04).
_ALERT_CLASS_GLYPHS_EMOJI: dict = {
    "Warning":         "🔴",
    "Watch":           "🟡",
    "Advisory":        "🔵",
    "Statement/Other": "ℹ️",
}


# ---------------------------------------------------------------------------
# Moon-phase glyph table (D-04)
#
# 28 slots mapping astral.moon.phase() output (0–27.99) to wi-moon-* glyphs.
# Slot 0 = new moon, slot 14 = full moon.
# Phase sequence: new → waxing-crescent ×6 → first-quarter → waxing-gibbous ×6
#                → full → waning-gibbous ×6 → third-quarter → waning-crescent ×6
# ---------------------------------------------------------------------------

_MOON_PHASE_GLYPHS: list[str] = [
    "",   # 0  wi-moon-new                U+E38D
    "",   # 1  wi-moon-waxing-crescent-1  U+E38E
    "",   # 2  wi-moon-waxing-crescent-2  U+E38F
    "",   # 3  wi-moon-waxing-crescent-3  U+E390
    "",   # 4  wi-moon-waxing-crescent-4  U+E391
    "",   # 5  wi-moon-waxing-crescent-5  U+E392
    "",   # 6  wi-moon-waxing-crescent-6  U+E393
    "",   # 7  wi-moon-first-quarter      U+E394
    "",   # 8  wi-moon-waxing-gibbous-1   U+E395
    "",   # 9  wi-moon-waxing-gibbous-2   U+E396
    "",   # 10 wi-moon-waxing-gibbous-3   U+E397
    "",   # 11 wi-moon-waxing-gibbous-4   U+E398
    "",   # 12 wi-moon-waxing-gibbous-5   U+E399
    "",   # 13 wi-moon-waxing-gibbous-6   U+E39A
    "",   # 14 wi-moon-full               U+E39B
    "",   # 15 wi-moon-waning-gibbous-1   U+E39C
    "",   # 16 wi-moon-waning-gibbous-2   U+E39D
    "",   # 17 wi-moon-waning-gibbous-3   U+E39E
    "",   # 18 wi-moon-waning-gibbous-4   U+E39F
    "",   # 19 wi-moon-waning-gibbous-5   U+E3A0
    "",   # 20 wi-moon-waning-gibbous-6   U+E3A1
    "",   # 21 wi-moon-third-quarter      U+E3A2
    "",   # 22 wi-moon-waning-crescent-1  U+E3A3
    "",   # 23 wi-moon-waning-crescent-2  U+E3A4
    "",   # 24 wi-moon-waning-crescent-3  U+E3A5
    "",   # 25 wi-moon-waning-crescent-4  U+E3A6
    "",   # 26 wi-moon-waning-crescent-5  U+E3A7
    "",   # 27 wi-moon-waning-crescent-6  U+E3A8
]


def _moon_phase_index(phase: float) -> int:
    """Map an astral moon phase value (0–27.99) to a _MOON_PHASE_GLYPHS index.

    astral.moon.phase() returns a float in [0, 28).  This helper converts it
    to an integer index in [0, 27].  Out-of-range values are clamped so a bad
    phase value degrades to a valid glyph rather than raising IndexError
    (never-crash, RUN-01/02).

    Does NOT call astral — Plan 02 wires the astral call under the _ASTRAL_OK
    guard; this helper performs only the index arithmetic.
    """
    try:
        idx = int(phase)
        return max(0, min(27, idx))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# NWS condition icon tables (D-03, D-05, D-06)
#
# Two parallel tables — same list[tuple[tuple[str,...], str]] shape:
#   _NWS_ICON_MAP_EMOJI : Phase 2 emoji glyphs (retained as icon_set="emoji" fallback)
#   _NWS_ICON_MAP_NERD  : Weather Icons / Nerd Font _WI_* glyphs (default, D-03)
#
# Both tables use the same first-match ordering discipline (D-05):
#   specific sky states (partly/mostly/few/scattered) MUST precede the broad
#   cloudy/sunny/clear entries — "Partly Cloudy" contains "cloudy", so if the
#   broad entry came first it would match incorrectly (first-match wins).
#
# Token vocabulary for the nerd table (D-03): NWS icon-URL tokens (skc, few,
# sct, bkn, ovc, ra, rain_showers, rasn, sn, fzra, tsra, tstm, fg, wind, ip)
# plus textDescription synonyms.  The URL check (icon_path) uses lowercase
# substring matching on the icon URL path segment.
#
# Defined AFTER the _WI_* constants and _MOON_PHASE_GLYPHS they reference.
# ---------------------------------------------------------------------------

# Phase 2 emoji table — retained exactly as-is for icon_set="emoji" fallback (D-06).
# DO NOT alter its glyphs or ordering.
_NWS_ICON_MAP_EMOJI: list[tuple[tuple[str, ...], str]] = [
    # Thunderstorm conditions
    (("thunderstorm", "tstm", "thunder"), "⛈️"),
    # Rain / shower conditions
    (("rain_showers", "rain shower", "showers", "drizzle", "rain", "sleet"), "🌧️"),
    # Snow conditions
    (("snow", "blizzard", "wintry mix", "winter mix", "freezing rain"), "🌨️"),
    # Fog / low visibility
    (("fog", "haze", "smoke", "dust", "sand", "ash"), "🌫️"),
    # Windy / blustery
    (("wind", "breezy", "blustery"), "💨"),
    # Partly/mostly sunny (sun-dominant). MUST precede the broad "cloudy"/"sunny"
    # rules below — "Partly Cloudy" contains "cloudy" and "Mostly Sunny" contains
    # "sunny", so the specific sky states have to match first (first-match wins).
    (("partly cloudy", "partly sunny", "mostly sunny", "mostly clear",
      "few", "scattered"), "⛅"),
    # Cloudy / overcast / mostly cloudy / broken (cloud-dominant)
    (("mostly cloudy", "broken", "bkn", "overcast", "cloudy"), "☁️"),
    # Clear / sunny
    (("clear", "fair", "sunny", "skc", "hot"), "☀️"),
    # Cold / frost
    (("cold", "frost"), "🥶"),
]

# Nerd Font / Weather Icons table — full D-03 granularity.
# Maps each condition category to a _WI_* constant.
# Ordering discipline: specific entries MUST precede broad ones (D-05).
#
# Shape: list[tuple[tuple[str,...], str, str]]
#   (keywords_tuple, glyph_constant, category_string)
# The category_string is used by _weather_segment to select _wx_color() (D-08).
# Categories: "storm", "rain", "snow", "fog", "wind", "cloud", "sun"
_NWS_ICON_MAP_NERD: list[tuple[tuple[str, ...], str, str]] = [
    # --- Severe / thunderstorm (most specific — precede plain rain) ---
    # tsra = thunderstorm with rain; tstm = thunderstorm without precipitation
    (("thunderstorm", "tstm", "thunder", "tsra"), _WI_THUNDERSTORM, "storm"),

    # --- Freezing precipitation (specific — precede generic snow/rain) ---
    # fzra = freezing rain (NWS token); "freezing rain/drizzle" via textDescription
    (("fzra", "freezing rain", "freezing drizzle"), _WI_FREEZING_RAIN, "snow"),

    # --- Rain-snow mix (specific — precede snow and rain individually) ---
    # rasn = rain-snow mix (NWS token); "wintry mix", "rain snow" via textDescription
    (("rasn", "wintry mix", "winter mix", "rain snow", "rain/snow"), _WI_RAIN_SNOW, "snow"),

    # --- Sleet (specific — precede generic rain) ---
    # ip = ice pellets (NWS token for sleet); "sleet" via textDescription
    (("ip", "sleet", "ice pellet"), _WI_SLEET, "snow"),

    # --- Snow (specific — precede generic cloud/rain) ---
    # sn = snow (NWS token); "blizzard" via textDescription
    (("sn", "snow", "blizzard"), _WI_SNOW, "snow"),

    # --- Rain / showers (specific — precede broad cloud) ---
    # ra = rain (NWS token); rain_showers / showers / drizzle via text or URL
    (("rain_showers", "rain shower", "showers", "drizzle", "/ra", "rain"), _WI_RAIN, "rain"),

    # --- Fog / low visibility ---
    # fg = fog (NWS token); smoke/haze/dust/sand/ash collapse to fog glyph
    (("fg", "fog", "haze", "smoke", "dust", "sand", "ash"), _WI_FOG, "fog"),

    # --- Wind ---
    # wind_skc, wind_few, wind_bkn, etc. in NWS URL; "windy", "breezy", "blustery" via text
    (("wind", "breezy", "blustery"), _WI_WINDY, "wind"),

    # --- Partly / mostly cloudy/sunny (specific — MUST precede broad cloudy/clear) ---
    # few = FEW clouds; sct = SCaTtered; "partly", "mostly clear", "mostly sunny"
    (("partly cloudy", "partly sunny", "mostly sunny", "mostly clear",
      "few", "sct", "scattered"), _WI_DAY_PARTLY, "sun"),

    # --- Mostly cloudy / broken / overcast (cloud-dominant; precede clear) ---
    # bkn = BroKeN cloud cover; ovc = OVerCast
    (("mostly cloudy", "broken", "bkn", "ovc", "overcast", "cloudy"), _WI_CLOUDY, "cloud"),

    # --- Clear / sunny (broad — must follow all more-specific sun entries above) ---
    # skc = SKy Clear; "fair", "hot" collapse to clear
    (("clear", "fair", "sunny", "skc", "hot"), _WI_DAY_CLEAR, "sun"),

    # --- Cold / frost (low priority) ---
    (("cold", "frost"), _WI_DAY_CLEAR, "sun"),
]


# _NERD_SUN_GLYPHS: frozenset of glyphs that trigger live moon-phase substitution on
# clear nights (D-04).  Only FULLY CLEAR day glyphs belong here; _WI_DAY_PARTLY must
# NOT be included — partly-cloudy nights must return _WI_NIGHT_PARTLY, not a moon phase
# (CR-01 fix).
_NERD_SUN_GLYPHS: frozenset = frozenset({_WI_DAY_CLEAR})


def _icon_to_glyph(text_description: str, icon_url: str, icon_set: str = "nerd",
                   is_night_override: bool | None = None) -> str:
    """Map NWS textDescription and/or icon URL to a condition glyph.

    When icon_set == "nerd" (default): iterates _NWS_ICON_MAP_NERD and returns the
    matching _WI_* glyph constant.  For a matched clear/sun glyph on a night URL,
    branches to the live moon-phase path (D-04): guards on _ASTRAL_OK, calls
    _moon_phase() today, maps via _moon_phase_index() into the 28-slot table.
    If _ASTRAL_OK is False, returns _WI_NIGHT_CLEAR as a generic fallback.

    When icon_set != "nerd": iterates _NWS_ICON_MAP_EMOJI and reproduces the Phase 2
    emoji behavior exactly, including "🌙" for clear nights (D-06).

    is_night_override: when not None, overrides the URL-derived is_night flag.
    Use this to supply locally-computed astral day/night so the condition icon
    stays consistent with the sun-segment near sunset/sunrise.

    Tries text_description first (lowercase contains-match), then icon URL path.
    Falls back to _WI_FALLBACK (nerd) or "🌡️" (emoji) when no token matches.

    Never raises to the caller (RUN-01/02, T-02.1-05).
    """
    try:
        desc = (text_description or "").lower()
        icon_path = (icon_url or "").lower()
        # D-05: preserve the is_night flag and text-then-URL dispatch order.
        # is_night_override (when not None) wins over the NWS URL-derived flag so
        # the condition icon stays consistent with the astral sun segment near sunset.
        is_night = is_night_override if is_night_override is not None else ("/night/" in icon_path)

        if icon_set == "nerd":
            for keywords, glyph, _category in _NWS_ICON_MAP_NERD:
                for kw in keywords:
                    if kw in desc or kw in icon_path:
                        # CR-01: partly-cloudy night → dedicated moon-behind-cloud glyph,
                        # NOT a live moon phase.  Must come before the sun-glyph check.
                        if is_night and glyph == _WI_DAY_PARTLY:
                            return _WI_NIGHT_PARTLY
                        # D-04: fully-clear glyph at night → live moon phase
                        if is_night and glyph in _NERD_SUN_GLYPHS:
                            if _ASTRAL_OK:
                                try:
                                    from datetime import date as _date
                                    phase = _moon_phase(_date.today())
                                    return _MOON_PHASE_GLYPHS[_moon_phase_index(phase)]
                                except Exception:
                                    return _WI_NIGHT_CLEAR
                            return _WI_NIGHT_CLEAR  # _ASTRAL_OK False — degrade
                        return glyph
            return _WI_FALLBACK  # no match: fallback thermometer glyph
        else:
            # emoji path: reproduce Phase 2 behavior exactly (D-06)
            for keywords, emoji in _NWS_ICON_MAP_EMOJI:
                for kw in keywords:
                    if kw in desc or kw in icon_path:
                        if is_night and emoji == "☀️":
                            return "🌙"
                        return emoji
            return "🌡️"  # fallback: thermometer emoji
    except Exception:
        # Never-crash (RUN-01/02): return the safest fallback for the requested set.
        try:
            return _WI_FALLBACK if icon_set == "nerd" else "🌡️"
        except Exception:
            return "🌡️"


def _icon_to_emoji(text_description: str, icon_url: str) -> str:
    """Backward-compat alias — delegates to _icon_to_glyph with icon_set='emoji'.

    MUST delegate explicitly with icon_set='emoji' — NOT the 'nerd' default —
    so existing callers (test_weather_fetch.py TestIconMapping) continue to
    receive Phase 2 emoji glyphs (D-06).
    """
    return _icon_to_glyph(text_description, icon_url, "emoji")


def _condition_category(text_description: str, icon_url: str,
                        is_night_override: bool | None = None) -> str:
    """Return the semantic condition category string for a NWS token pair.

    Used by _weather_segment to select the _wx_color() argument (D-08).
    Returns one of: "storm", "rain", "snow", "fog", "wind", "cloud", "sun", "moon".
    Falls back to "sun" (RESET-adjacent / yellow) on any error or unknown token.

    The category is derived from the nerd table regardless of icon_set — it
    represents the meteorological nature of the condition.

    is_night_override: when not None, overrides the URL-derived is_night flag.
    """
    try:
        desc = (text_description or "").lower()
        icon_path = (icon_url or "").lower()
        is_night = is_night_override if is_night_override is not None else ("/night/" in icon_path)

        for keywords, glyph, category in _NWS_ICON_MAP_NERD:
            for kw in keywords:
                if kw in desc or kw in icon_path:
                    # CR-01: partly-cloudy night keeps its day color category (e.g. 'sun')
                    # so it renders with YELLOW, not the dim moon color.  Only fully-clear
                    # nights return 'moon' (RESET / dim white).
                    if is_night and glyph == _WI_DAY_PARTLY:
                        return category  # 'sun' — same as its day counterpart
                    # Clear/sun glyph at night → moon (dim/white, not yellow)
                    if is_night and glyph in _NERD_SUN_GLYPHS:
                        return "moon"
                    return category
        return "sun"
    except Exception:
        return "sun"


def make_user_agent(version: str, contact_email: str) -> str:
    """Return the NWS-ToS-compliant User-Agent string.

    Format: 'claude-statusline/<version> (<contact_email>)'
    contact_email is placed ONLY in this header — never logged or printed (T-02-06).
    """
    return f"claude-statusline/{version} ({contact_email})"


def c_to_unit(celsius, unit: str) -> int | None:
    """Convert NWS Celsius temperature to the configured unit, rounded to a whole number.

    Returns None when celsius is None (sensor value missing).
    unit: "F" → Fahrenheit (default); "C" → Celsius; anything else → Fahrenheit.
    """
    if celsius is None:
        return None
    try:
        c = float(celsius)
        if unit == "C":
            return round(c)
        # Default: convert to Fahrenheit
        return round(c * 9 / 5 + 32)
    except Exception:
        return None


def _nws_get(url: str, ua: str, accept: str | None = None) -> dict:
    """Perform a single synchronous NWS GET request.

    Sends the mandatory User-Agent header (NWS ToS / T-02-11).
    Raises on any non-2xx or parse error — caller is responsible for try/except.

    Runs ONLY in the detached background child — never on the render path (D2-05).
    """
    headers = {"User-Agent": ua}
    if accept:
        headers["Accept"] = accept
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_weather(cfg: dict) -> None:
    """Fetch NWS conditions + PoP and write geo + weather cache sections.

    Flow (D2-08):
      1. Resolve gridpoint via /points/{lat:.4f},{lon:.4f} (cache geo permanently).
      2. Resolve nearest observation station via observationStations URL.
      3. Fetch latest observation (icon + temperature).
      4. Fetch hourly forecast first period (PoP).
      5. Write geo and weather sections atomically.

    All network/parse errors are swallowed — the cache is simply left unchanged
    and the render falls back to its current cached state (T-02-07).

    RUNS ONLY IN THE DETACHED CHILD (--refresh mode). Never called on the render path.
    """
    try:
        location = cfg.get("location", {})
        lat = float(location.get("lat", 0.0))
        lon = float(location.get("lon", 0.0))
        weather_cfg = cfg.get("weather", {})
        contact_email = weather_cfg.get("contact_email", "")
        units_cfg = cfg.get("units", {})
        temp_unit = units_cfg.get("temp_unit", "F")

        ua = make_user_agent(_APP_VERSION, contact_email)
        import time as _time
        now = _time.time()

        # Step 1: /points — resolve gridpoint + observationStations URL
        points_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        points_data = _nws_get(points_url, ua)
        props = points_data["properties"]
        cwa = props["gridId"]          # NWS office code, e.g. "OUN"
        grid_x = props["gridX"]
        grid_y = props["gridY"]
        stations_url = props["observationStations"]

        # Step 2: observationStations — get nearest station identifier
        stations_data = _nws_get(stations_url, ua)
        features = stations_data.get("features") or []
        if not features:
            return  # no stations found — leave cache unchanged
        station_id = features[0]["properties"]["stationIdentifier"]

        # Write geo section (near-permanent — only re-fetched when absent, D2-06)
        write_cache_section(_CACHE_PATH, "geo", {
            "cwa": cwa,
            "gridX": grid_x,
            "gridY": grid_y,
            "station_id": station_id,
        }, now)

        # Step 3: /stations/{id}/observations/latest — current conditions
        obs_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        obs_data = _nws_get(obs_url, ua)
        obs_props = obs_data["properties"]
        temp_c = obs_props.get("temperature", {}).get("value")  # Celsius, may be null
        text_desc = obs_props.get("textDescription", "")
        icon_url_raw = obs_props.get("icon", "")
        # D-04/D-07: store raw NWS tokens, NOT a pre-resolved glyph.
        # The render path (_weather_segment) resolves the glyph at render time via
        # _icon_to_glyph, allowing the icon_set toggle to take effect immediately
        # and the clear-night moon phase to reflect the live time (not a baked phase).
        temp_converted = c_to_unit(temp_c, temp_unit)

        # Step 4: /gridpoints/{cwa}/{x},{y}/forecast/hourly — PoP for current period
        hourly_url = f"https://api.weather.gov/gridpoints/{cwa}/{grid_x},{grid_y}/forecast/hourly"
        hourly_data = _nws_get(hourly_url, ua)
        periods = hourly_data.get("properties", {}).get("periods", [])
        pop = None
        if periods:
            pop_field = periods[0].get("probabilityOfPrecipitation", {})
            pop = pop_field.get("value")  # percent, may be null

        # Step 5: write weather section atomically — raw tokens, not a resolved glyph.
        # Schema: { "fetched_at": <epoch>, "text_desc": str, "icon_url": str,
        #           "temp": int|None, "pop": int|None }
        weather_payload = {
            "text_desc": text_desc,
            "icon_url":  icon_url_raw,
        }
        if temp_converted is not None:
            weather_payload["temp"] = temp_converted
        if pop is not None:
            weather_payload["pop"] = pop

        write_cache_section(_CACHE_PATH, "weather", weather_payload, now)

    except Exception:
        # Any network / parse / OS error is swallowed (T-02-07 / D-10).
        # The cache is simply left as-is; the render will use the last good value.
        pass


# ---------------------------------------------------------------------------
# Alert dedup + severity selection (D2-11, T-02-12)
#
# Port of WxDesktopPy dedup.py algorithm to plain NWS feature.properties dicts.
# No Alert dataclass, no pint, no logging framework — pure dict operations.
#
# ALL functions tolerate missing/malformed fields without raising (Rule 2 safety).
# ---------------------------------------------------------------------------

# CAP messageType values that indicate an alert is superseded / terminal.
_TERMINAL_MSG_TYPES: frozenset = frozenset({"Cancel", "Ack", "Error"})

# Severity rank: Extreme > Severe > Moderate > Minor > Unknown (D2-11).
_SEVERITY_RANK: dict = {
    "Extreme":  4,
    "Severe":   3,
    "Moderate": 2,
    "Minor":    1,
    "Unknown":  0,
}

# VTEC significance letter → hazard class (D-01).
# W = Warning, A = Watch, Y = Advisory, S/F/O/N = Statement/Other.
_VTEC_SIG_TO_CLASS: dict = {
    "W": "Warning",
    "A": "Watch",
    "Y": "Advisory",
    "S": "Statement/Other",
    "F": "Statement/Other",
    "O": "Statement/Other",
    "N": "Statement/Other",
}

# Hazard class rank for class-first selection (D-07).
_ALERT_CLASS_RANK: dict = {
    "Warning":         3,
    "Watch":           2,
    "Advisory":        1,
    "Statement/Other": 0,
}


def _classify_alert_class(alert: dict) -> str:
    """Classify a CAP alert dict as Warning/Watch/Advisory/Statement/Other.

    Primary: VTEC significance letter from properties.parameters.VTEC (D-01).
      The significance letter is the 5th dot-delimited field of the VTEC string,
      after stripping leading/trailing "/".  W→Warning, A→Watch, Y→Advisory,
      S/F/O/N→Statement/Other.
    Fallback: trailing word of properties.event (D-02).
      "Tornado Warning" → Warning, "Flash Flood Watch" → Watch, etc.
    Default: "Statement/Other" (D-03, omit-not-fake — never raises, never None).
    """
    try:
        props = alert.get("properties") or alert
        # D-01: VTEC significance letter (5th dot-delimited field of each VTEC string)
        vtec_list = (props.get("parameters") or {}).get("VTEC") or []
        if isinstance(vtec_list, str):
            vtec_list = [vtec_list]
        for vtec_str in vtec_list:
            try:
                fields = vtec_str.strip("/").split(".")
                if len(fields) >= 5:
                    sig = fields[4].upper()
                    cls = _VTEC_SIG_TO_CLASS.get(sig)
                    if cls:
                        return cls
            except Exception:
                pass
        # D-02: event-name trailing word fallback
        event = (props.get("event") or "").strip()
        for word in ("Warning", "Watch", "Advisory"):
            if event.endswith(word):
                return word
    except Exception:
        pass
    return "Statement/Other"   # D-03: unclassifiable or any error → Statement/Other


def _alert_intensity(alert: dict) -> str:
    """Return ANSI intensity modifier for an alert's urgency+certainty (D-06).

    Three bands (locked):
      Immediate + Observed  → BOLD   (act now, high confidence)
      Expected  / Likely    → ""     (normal, no modifier)
      Future    / Possible  → DIM    (lower immediacy or confidence)

    Never raises — returns "" (normal) on any parse failure.
    """
    try:
        props = alert.get("properties") or alert
        urgency   = (props.get("urgency")   or "").strip()
        certainty = (props.get("certainty") or "").strip()
        # Immediate + Observed → bold/bright (highest immediacy, confirmed)
        if urgency == "Immediate" and certainty == "Observed":
            return BOLD
        # Future urgency or Possible/Unlikely certainty → dim (lower signal)
        if urgency in ("Future",) or certainty in ("Possible", "Unlikely"):
            return DIM
        # Expected / Likely (or anything else) → normal (no modifier)
    except Exception:
        pass
    return ""


def dedup_alerts(alerts: list, now=None) -> list:
    """Dedup a CAP alert list via the references-chain algorithm.

    Algorithm (ported from WxDesktopPy dedup.py L70-88, simplified):
      1. Build a superseded set:
         a. Every identifier appearing in any alert's 'references' list.
         b. Every alert whose messageType is in {Cancel, Ack, Error}.
      2. Drop alerts whose 'expires' < now.
      3. Return survivors sorted by 'sent' descending (newest first).

    Parameters
    ----------
    alerts : list of NWS feature dicts (each has a 'properties' sub-dict).
    now    : datetime (tz-aware or naive) for the expires comparison.
             Defaults to datetime.now(tz=timezone.utc) when None.

    Tolerates missing/malformed fields by skipping that alert (never raises).
    (T-02-12 / STRIDE T-02-12 load-bearing safety logic.)
    """
    from datetime import timezone as _tz
    if not alerts:
        return []

    if now is None:
        now = datetime.now(tz=_tz.utc)

    # Helper: parse an ISO-8601 string, tolerating trailing 'Z'
    def _parse_dt(s):
        if not s:
            return None
        try:
            # Python ≥3.11: fromisoformat handles 'Z'; older: replace manually
            s2 = s
            if s2.endswith("Z"):
                s2 = s2[:-1] + "+00:00"
            return datetime.fromisoformat(s2)
        except Exception:
            return None

    # Step 1: Build the superseded identifier set.
    superseded: set = set()
    for alert in alerts:
        try:
            props = alert.get("properties") or alert
            # 1a. Each identifier in this alert's references list is superseded.
            for ref in (props.get("references") or []):
                try:
                    ref_id = ref.get("identifier") or ref.get("id") or str(ref)
                    if ref_id:
                        superseded.add(ref_id)
                except Exception:
                    pass
            # 1b. Cancel/Ack/Error alerts are themselves superseded.
            msg_type = props.get("messageType", "")
            if msg_type in _TERMINAL_MSG_TYPES:
                alert_id = props.get("id") or alert.get("id")
                if alert_id:
                    superseded.add(alert_id)
        except Exception:
            pass

    # Step 2 + 3: Filter out superseded + expired; sort by sent descending.
    survivors = []
    for alert in alerts:
        try:
            props = alert.get("properties") or alert
            alert_id = props.get("id") or alert.get("id")
            if alert_id in superseded:
                continue

            # Parse expires — skip alerts with missing/unparseable expires
            expires_str = props.get("expires")
            if not expires_str:
                continue  # missing expires: skip (cannot verify it's still active)
            expires_dt = _parse_dt(expires_str)
            if expires_dt is None:
                continue  # unparseable: skip

            # Make both now and expires comparable (strip tz if mixed)
            try:
                if expires_dt.tzinfo is not None and now.tzinfo is None:
                    expires_cmp = expires_dt.replace(tzinfo=None)
                elif expires_dt.tzinfo is None and now.tzinfo is not None:
                    expires_cmp = expires_dt.replace(tzinfo=_tz.utc)
                else:
                    expires_cmp = expires_dt
                if expires_cmp <= now:
                    continue  # expired
            except Exception:
                continue

            survivors.append(alert)
        except Exception:
            pass  # skip malformed alerts

    # Sort by sent descending (newest first)
    def _sent_key(alert):
        try:
            props = alert.get("properties") or alert
            dt = _parse_dt(props.get("sent"))
            if dt is None:
                return datetime.min.replace(tzinfo=_tz.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=_tz.utc)
            return dt
        except Exception:
            return datetime.min.replace(tzinfo=_tz.utc)

    try:
        survivors.sort(key=_sent_key, reverse=True)
    except Exception:
        pass

    return survivors


def select_alert(survivors: list) -> tuple:
    """Select the primary alert using class-first composite ranking (D-07).

    Rank: Warning > Watch > Advisory > Statement/Other,
    ties broken by severity → urgency → certainty.

    Returns
    -------
    (best_alert, remaining_alerts) where:
      - best_alert: highest-ranked alert dict (or None if empty).
      - remaining_alerts: list of the other survivors (for per-class tally, D-08).

    Tolerates missing/malformed fields (no raise).
    """
    if not survivors:
        return (None, [])
    try:
        def _composite_key(alert):
            try:
                cls   = _classify_alert_class(alert)
                props = alert.get("properties") or alert
                sev   = _SEVERITY_RANK.get(props.get("severity", "Unknown"), 0)
                urg   = {"Immediate": 2, "Expected": 1, "Future": 0}.get(
                            props.get("urgency", "Unknown"), 0)
                cert  = {"Observed": 2, "Likely": 1, "Possible": 0}.get(
                            props.get("certainty", "Unknown"), 0)
                return (_ALERT_CLASS_RANK.get(cls, 0), sev, urg, cert)
            except Exception:
                return (0, 0, 0, 0)

        best = max(survivors, key=_composite_key)
        remaining = [a for a in survivors if a is not best]
        return (best, remaining)
    except Exception:
        return (None, [])


def _alert_color(alert: dict) -> str:
    """Return the ANSI color+intensity for a CAP alert dict (D-05, D-06).

    Hue from alert class (D-05):
      Warning         → RED
      Watch           → YELLOW
      Advisory        → CYAN
      Statement/Other → DEFAULT_FG (neutral default foreground; preserves intensity)

    Intensity from urgency+certainty (D-06) — prepended before hue:
      Immediate + Observed → BOLD + hue
      Future / Possible    → DIM + hue
      Expected / Likely    → hue (no modifier)

    Never raises — falls back to YELLOW on any parse error.
    """
    try:
        cls       = _classify_alert_class(alert)
        intensity = _alert_intensity(alert)
        hue_map   = {
            "Warning":         RED,
            "Watch":           YELLOW,
            "Advisory":        CYAN,
            # Neutral default-foreground hue so the prepended BOLD/DIM intensity band
            # survives (WR-01/D-06). RESET here (\x1b[0m) would cancel the intensity,
            # flattening the entire Statement/Other class; DEFAULT_FG (\x1b[39m) only
            # sets foreground, leaving bold/dim intact, and avoids upstream color bleed.
            "Statement/Other": DEFAULT_FG,
        }
        hue = hue_map.get(cls, YELLOW)
        return f"{intensity}{hue}"
    except Exception:
        return YELLOW


def _claude_status_color(severity: object) -> str:
    """Return the ANSI color+intensity for a Statuspage.io severity token (Phase 06, D-03/D-04).

    Maps status severity tokens from summary.json to band hues:
      minor       -> YELLOW             (minor disruption — be aware)
      major       -> RED                (major outage — significant impact)
      critical    -> BOLD + RED         (critical outage — service down)
      maintenance -> DIM                (planned maintenance — neutral, NOT a severity hue, D-04)
      <other>     -> YELLOW             (safe default on unknown/None/garbage input)

    The function is intentionally symmetric with _alert_color: whole body in
    try/except, returning YELLOW on any parse error (D-10 never-raises contract).

    Do NOT route through color_for() — that is the usage-threshold band function
    and is not applicable to status severity (see PATTERNS.md).
    """
    try:
        hue_map = {
            "minor":       YELLOW,
            "major":       RED,
            "critical":    f"{BOLD}{RED}",
            # Neutral hue for maintenance: DIM, not a severity color (D-04).
            # Using DIM (not DEFAULT_FG) so scheduled maintenance reads as low-key/informational.
            "maintenance": DIM,
        }
        if not isinstance(severity, str):
            return YELLOW
        return hue_map.get(severity, YELLOW)
    except Exception:
        return YELLOW


# ---------------------------------------------------------------------------
# Claude service-health derivation (Phase 06, D-01/D-02/D-03/D-04)
# ---------------------------------------------------------------------------

# Tracked components: only these trigger the status indicator (D-02).
# Must match the component names verbatim as they appear in the status.claude.com feed.
_CLAUDE_TRACKED_COMPONENTS: frozenset = frozenset({
    "Claude Code",
    "claude.ai",
    "Claude Cowork",
})

# Human-readable state labels for degraded component statuses (D-03 fallback)
_CLAUDE_STATUS_LABELS: dict = {
    "degraded_performance": "degraded",
    "partial_outage":       "partial outage",
    "major_outage":         "major outage",
    "under_maintenance":    "maintenance",
}

# Impact → severity mapping for incidents (D-03)
_CLAUDE_IMPACT_SEVERITY: dict = {
    "critical": "critical",
    "major":    "major",
    "minor":    "minor",
    # "none" impact on an unresolved incident → fall back to "minor"
    "none":     "minor",
}


def _derive_claude_status(summary: object) -> dict | None:
    """Derive a status trigger result from a Statuspage.io summary.json dict.

    Returns None (quiet-when-healthy, D-01) when all tracked components
    (Claude Code, claude.ai, Claude Cowork) are operational and there is no
    relevant incident or maintenance window.

    Returns a dict with the shape:
        {"severity": str, "label": str, "kind": str}
    when something noteworthy is found.  The label is stored RAW (unsanitized)
    so the cache is a faithful record — sanitization is the render path's job (Plan 02).

    Derivation priority (first match wins):
      1. Unresolved incident whose components[] intersect the tracked set → kind="incident"
      2. Scheduled/in-progress maintenance touching a tracked component → kind="maintenance"
      3. Tracked component with a non-operational status and no incident → kind="degraded"
      4. All healthy → None

    Do NOT use the top-level status.indicator rollup as the trigger (confirmed
    D-02 hazard: indicator fires on any component, including untracked ones).

    Whole body in try/except returning None — never raises (D-10 / T-06-02).
    """
    try:
        if not isinstance(summary, dict):
            return None

        # Build a name→status map for all components in the feed
        components_raw = summary.get("components", [])
        if not isinstance(components_raw, list):
            components_raw = []
        comp_status: dict = {}
        for comp in components_raw:
            if not isinstance(comp, dict):
                continue
            name = comp.get("name", "")
            status = comp.get("status", "operational")
            if isinstance(name, str) and name:
                comp_status[name] = status

        def _tracked_component_names(component_refs: object) -> set:
            """Return the subset of tracked component names from a component refs list."""
            if not isinstance(component_refs, list):
                return set()
            result = set()
            for ref in component_refs:
                if not isinstance(ref, dict):
                    continue
                name = ref.get("name", "")
                if isinstance(name, str) and name in _CLAUDE_TRACKED_COMPONENTS:
                    result.add(name)
            return result

        # --- Rule 1: Unresolved incidents touching tracked components (D-03) ---
        incidents_raw = summary.get("incidents", [])
        if not isinstance(incidents_raw, list):
            incidents_raw = []

        triggered_incidents = []
        for inc in incidents_raw:
            if not isinstance(inc, dict):
                continue
            # An incident is "unresolved" if its status is investigating/identified/monitoring
            inc_status = inc.get("status", "")
            if not isinstance(inc_status, str):
                continue
            if inc_status not in ("investigating", "identified", "monitoring"):
                continue
            tracked = _tracked_component_names(inc.get("components", []))
            if not tracked:
                continue
            triggered_incidents.append(inc)

        if triggered_incidents:
            # Pick the highest-impact incident
            impact_rank = {"critical": 3, "major": 2, "minor": 1, "none": 0}
            best = max(
                triggered_incidents,
                key=lambda i: impact_rank.get(i.get("impact", "none"), 0),
            )
            impact = best.get("impact", "none")
            severity = _CLAUDE_IMPACT_SEVERITY.get(impact, "minor")
            label = best.get("name", "")
            if not isinstance(label, str):
                label = ""
            return {"severity": severity, "label": label, "kind": "incident"}

        # --- Rule 2: Scheduled/in-progress maintenance touching tracked components (D-04) ---
        maintenances_raw = summary.get("scheduled_maintenances", [])
        if not isinstance(maintenances_raw, list):
            maintenances_raw = []

        for maint in maintenances_raw:
            if not isinstance(maint, dict):
                continue
            maint_status = maint.get("status", "")
            if not isinstance(maint_status, str):
                continue
            if maint_status not in ("scheduled", "in_progress"):
                continue
            tracked = _tracked_component_names(maint.get("components", []))
            if not tracked:
                continue
            label = maint.get("name", "")
            if not isinstance(label, str):
                label = ""
            return {"severity": "maintenance", "label": label, "kind": "maintenance"}

        # --- Rule 3: Tracked component degraded with no associated incident (D-03 fallback) ---
        non_operational = (
            "degraded_performance",
            "partial_outage",
            "major_outage",
            "under_maintenance",
        )
        for comp_name in sorted(_CLAUDE_TRACKED_COMPONENTS):  # deterministic order
            status = comp_status.get(comp_name, "operational")
            if status in non_operational:
                human_state = _CLAUDE_STATUS_LABELS.get(status, status.replace("_", " "))
                label = f"{comp_name}: {human_state}"
                # Map component status to severity tier
                severity_map = {
                    "degraded_performance": "minor",
                    "partial_outage":       "major",
                    "major_outage":         "critical",
                    "under_maintenance":    "maintenance",
                }
                severity = severity_map.get(status, "minor")
                return {"severity": severity, "label": label, "kind": "degraded"}

        # --- Rule 4: All healthy (D-01) ---
        return None

    except Exception:
        return None


def _build_alert_tally(remaining: list, icon_set: str) -> str:
    """Build a per-class tally string for the non-primary alerts (D-08).

    Groups remaining alerts by class and returns a compact string like:
      "<warn-glyph>1 <adv-glyph>2"
    Classes with zero remaining are omitted. Order: Warning > Watch > Advisory > Statement/Other.
    Never raises — returns "" on any failure.
    """
    try:
        counts: dict = {}
        for a in remaining:
            try:
                cls = _classify_alert_class(a)
            except Exception:
                cls = "Statement/Other"
            counts[cls] = counts.get(cls, 0) + 1
        parts = []
        for cls in ("Warning", "Watch", "Advisory", "Statement/Other"):
            n = counts.get(cls, 0)
            if n == 0:
                continue
            if icon_set == "nerd":
                g = _ALERT_CLASS_GLYPHS_NERD.get(cls, _WI_ALERT_STATEMENT)
            else:
                g = _ALERT_CLASS_GLYPHS_EMOJI.get(cls, "ℹ️")
            parts.append(f"{g}{n}")
        return " ".join(parts)
    except Exception:
        return ""


def _wx_color(condition_type: str) -> str:
    """Return semantic ANSI color for a weather condition category (D-08).

    Maps the condition category string to a top-line color constant.
    TOP-LINE ONLY — do not apply to the bottom line (D-08).

    Categories:
      storm  → MAGENTA (thunderstorm)
      rain   → BLUE
      snow   → CYAN (snow / freezing rain)
      fog    → GRAY (fog / haze)
      sun    → YELLOW
      other  → RESET (clear-moon, wind, cold: uncolored / white)

    Never raises — unknown/None/non-str input returns RESET.
    """
    try:
        if condition_type == "storm":
            return MAGENTA
        if condition_type == "rain":
            return BLUE
        if condition_type == "snow":
            return CYAN
        if condition_type == "fog":
            return GRAY
        if condition_type == "sun":
            return YELLOW
    except Exception:
        pass
    return RESET


def fetch_alerts(cfg: dict) -> None:
    """Fetch NWS active alerts and write the alerts cache section.

    Endpoint: GET /alerts/active?point={lat:.4f},{lon:.4f}
    Accept: application/ld+json  (NWS CAP payload in JSON-LD format)

    Flow:
      1. If CLAUDE_STATUSLINE_FAKE_ALERTS env var is set, load the named JSON file
         as the alerts payload instead of issuing an HTTP request (UAT/offline testing —
         mirrors WxDesktopPy's WXD_FAKE_ALERTS_FILE; T-02-15).
      2. Otherwise: GET the NWS alerts/active endpoint (with User-Agent + Accept header).
      3. Pull the feature @graph list, run dedup_alerts on the raw feature dicts.
      4. Write the alerts cache section ({fetched_at, active: [survivor_dicts]}) atomically.

    Wrapped in try/except — never raises (D-10). A failed fetch leaves the alerts
    section unchanged; the render falls back to the last good cached value.

    RUNS ONLY IN THE DETACHED CHILD (--refresh mode). Never called on the render path.
    """
    try:
        location = cfg.get("location", {})
        lat = float(location.get("lat", 0.0))
        lon = float(location.get("lon", 0.0))
        weather_cfg = cfg.get("weather", {})
        contact_email = weather_cfg.get("contact_email", "")

        ua = make_user_agent(_APP_VERSION, contact_email)
        import time as _time
        now = _time.time()

        # UAT/offline fixture override: honor CLAUDE_STATUSLINE_FAKE_ALERTS env var
        # (mirrors WxDesktopPy active_alerts.py WXD_FAKE_ALERTS_FILE pattern — T-02-15)
        fake_path = os.environ.get("CLAUDE_STATUSLINE_FAKE_ALERTS")
        if fake_path:
            try:
                with open(fake_path, encoding="utf-8") as fh:
                    payload = json.load(fh)
            except Exception:
                return  # bad fake file: leave cache unchanged
            graph = payload.get("@graph", payload.get("features", []))
        else:
            # Live fetch: GET /alerts/active?point=lat,lon with ld+json Accept header
            url = (
                f"https://api.weather.gov/alerts/active"
                f"?point={lat:.4f},{lon:.4f}"
            )
            payload = _nws_get(url, ua, accept="application/ld+json")
            # NWS CAP JSON-LD uses "@graph"; GeoJSON uses "features"
            graph = payload.get("@graph", payload.get("features", []))

        # Dedup via references-chain algorithm (T-02-12)
        from datetime import timezone as _tz
        now_dt = datetime.now(tz=_tz.utc)
        survivors = dedup_alerts(graph, now=now_dt)

        # Write the alerts cache section atomically
        write_cache_section(_CACHE_PATH, "alerts", {"active": survivors}, now)

    except Exception:
        # Any network / parse / OS error is swallowed (D-10).
        pass


def fetch_claude_status(cfg: dict) -> None:
    """Fetch Anthropic/Claude service health and write the claude_status cache section.

    Endpoint: GET https://status.claude.com/api/v2/summary.json
    Accept: None (plain JSON — no ld+json header needed for Statuspage.io v2)

    Flow:
      1. If CLAUDE_STATUSLINE_FAKE_STATUS env var is set, load the named JSON file
         as the summary payload instead of issuing an HTTP request (UAT/offline testing —
         mirrors CLAUDE_STATUSLINE_FAKE_ALERTS pattern; T-06-02).
      2. Otherwise: GET summary.json via _nws_get (reused as-is; generic despite NWS name).
      3. Pass the parsed payload to _derive_claude_status to compute the trigger result.
      4. Write the claude_status cache section atomically — even when derivation is None
         (healthy state), to timestamp the fetch and prevent a hot respawn loop.

    Stores the RAW (unsanitized) label from _derive_claude_status; sanitization happens
    on the render path (Plan 02) so the cache is a faithful record (truth-telling, T-06-01).

    Wrapped in try/except — never raises (D-10 / T-06-02). A failed fetch leaves the
    claude_status section unchanged; the render falls back gracefully (cold-cache → None).

    RUNS ONLY IN THE DETACHED CHILD (--refresh mode). Never called on the render path.
    """
    try:
        weather_cfg = cfg.get("weather", {})
        contact_email = weather_cfg.get("contact_email", "")

        ua = make_user_agent(_APP_VERSION, contact_email)
        import time as _time
        now = _time.time()

        # UAT/offline fixture override: honor CLAUDE_STATUSLINE_FAKE_STATUS env var
        # (mirrors CLAUDE_STATUSLINE_FAKE_ALERTS pattern — T-06-02)
        fake_path = os.environ.get("CLAUDE_STATUSLINE_FAKE_STATUS")
        if fake_path:
            try:
                with open(fake_path, encoding="utf-8") as fh:
                    summary = json.load(fh)
            except Exception:
                return  # bad fake file: leave cache unchanged
        else:
            # WR-03: mirror the _WEATHER_OK guards used by the weather/alerts fetch
            # path. _nws_get references the module-level `requests`; when it failed
            # to import (_REQUESTS_OK False) the network branch would raise NameError
            # (swallowed by the outer try/except) after doing pointless work. Bail
            # early instead, leaving the cache section unchanged.
            if not _REQUESTS_OK:
                return  # requests unavailable — leave cache unchanged
            # Live fetch: GET status.claude.com/api/v2/summary.json (plain JSON)
            # URL is a hardcoded constant — no user/config interpolation (T-06-04)
            url = "https://status.claude.com/api/v2/summary.json"
            summary = _nws_get(url, ua, accept=None)

        # Derive the trigger result from the parsed payload
        derived = _derive_claude_status(summary)

        # Build the cache payload — always include the derived result (or an explicit
        # "noteworthy=False" marker) so even a healthy refresh timestamps the section,
        # preventing the maybe_spawn_refresh loop from respawning every render.
        if derived is not None:
            payload = {
                "noteworthy": True,
                "severity":   derived.get("severity"),
                "label":      derived.get("label"),
                "kind":       derived.get("kind"),
            }
        else:
            payload = {"noteworthy": False}

        # Write the claude_status cache section atomically
        write_cache_section(_CACHE_PATH, "claude_status", payload, now)

    except Exception:
        # Any network / parse / OS error is swallowed (D-10).
        pass


def run_refresh(cfg: dict) -> None:
    """Entry point for the detached background fetch child (--refresh mode).

    Acquires an exclusive lockfile using O_CREAT|O_EXCL (atomic create — fails
    if the file already exists).  If the lock is already held by another fetch,
    exits immediately (no stampede — T-02-09, D2-05).

    Refreshes weather, alerts, and Claude service status under the single lock
    (D2-16 + Phase-06 D-05 — all three fetches run in the same detached child).

    On any error: swallows and exits cleanly (never crashes the render bar via stderr).
    The lock file is always removed in the finally block so a crashed child
    doesn't leave a stale lock.
    """
    lock_path = _LOCK_PATH
    lock_fd = None
    try:
        # Ensure the lock directory exists
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        # O_CREAT|O_EXCL: atomic exclusive create — raises FileExistsError if held
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, OSError):
            # Lock already held by another fetch — exit immediately (no stampede)
            return
        # Lock acquired — run the fetches under the single lock (D2-16 + Phase 06).
        # WR-02: gate weather/alerts on the SAME conditions the render-path weather
        # segment uses (_weather_segment :2773-2787) so a user with weather disabled
        # or an unconfigured (0.0,0.0) location does not spawn pointless HTTP requests
        # against api.weather.gov every status_ttl. The status fetch is independent
        # of weather config and always runs (the T-06-06 / D-05 intent).
        weather_cfg = cfg.get("weather", {}) if isinstance(cfg, dict) else {}
        location = cfg.get("location", {}) if isinstance(cfg, dict) else {}
        _lat, _lon = location.get("lat"), location.get("lon")
        has_location = not (
            _lat is None or _lon is None or (float(_lat) == 0.0 and float(_lon) == 0.0)
        )
        if _WEATHER_OK and weather_cfg.get("show_weather", True) and has_location:
            fetch_weather(cfg)
            fetch_alerts(cfg)
        fetch_claude_status(cfg)  # Phase 06: Claude service-health status (D-05)
    except Exception:
        pass
    finally:
        # Release: close the fd and remove the lock file
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception:
                pass
        try:
            os.unlink(lock_path)
        except Exception:
            pass


def maybe_spawn_refresh(cfg: dict, cache: dict) -> None:
    """Spawn a detached background child to refresh weather, alerts, or status cache if stale.

    Checks whether the weather, alerts, OR claude_status section needs refreshing
    (past its TTL or absent). If any is stale, spawns a new process with --refresh,
    detached (start_new_session=True, stdio=DEVNULL) so it never blocks the render.

    The detached child refreshes all three sections under the single lock (D2-16 + Phase-06).

    This is a fire-and-forget call on the RENDER PATH — it must return instantly.
    The parent render continues with the current (possibly stale) cached value.
    (D2-05 / T-02-08 / D-05)
    """
    try:
        cache_cfg = cfg.get("cache", {})
        weather_ttl = float(cache_cfg.get("weather_ttl", 600))
        alerts_ttl = float(cache_cfg.get("alerts_ttl", 300))
        status_ttl = float(cache_cfg.get("status_ttl", 300))  # Phase 06 (D-05)
        import time as _time
        now = _time.time()
        weather_section = cache.get("weather", {})
        alerts_section = cache.get("alerts", {})
        status_section = cache.get("claude_status", {})  # Phase 06 (D-05)
        # Trigger refresh when: weather OR alerts OR claude_status is absent/stale
        weather_stale = not section_is_fresh(weather_section, ttl=weather_ttl, now=now)
        alerts_stale = not section_is_fresh(alerts_section, ttl=alerts_ttl, now=now)
        status_stale = not section_is_fresh(status_section, ttl=status_ttl, now=now)  # Phase 06 (D-05)
        if not (weather_stale or alerts_stale or status_stale):
            return
        # Spawn detached child — fixed argv, no shell interpolation (T-02-08)
        subprocess.Popen(
            [sys.executable, __file__, "--refresh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Never .wait() or .communicate() — the render path returns immediately.
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Threshold helpers (FMT-01, D-04, D-05)
# Now accept configurable warn/crit thresholds (Plan 03); defaults 70/90 preserved.
# ---------------------------------------------------------------------------

def color_for(pct: int | float, warn: int | float = 70, crit: int | float = 90) -> str:
    """Return the ANSI color code for a given usage percentage.

    Bands (FMT-01 / D-05):
      pct > crit  → RED    (strictly greater than crit)
      pct >= warn → YELLOW
      otherwise  → GREEN

    Default parameters (warn=70, crit=90) preserve pre-Plan-03 behavior.
    Thresholds are sourced from the loaded config in Plan 03.
    """
    if pct > crit:
        return RED
    if pct >= warn:
        return YELLOW
    return GREEN


def is_green(pct: int | float, warn: int | float = 70) -> bool:
    """Return True iff the percentage is below the warn threshold.

    Gates whether a reset time is shown for a rate-limit indicator (D-04):
    reset is only displayed when is_green() returns False (i.e., pct >= warn).

    Default parameter (warn=70) preserves pre-Plan-03 behavior.
    """
    return pct < warn


def pct_int(value) -> int | None:
    """Floor a percentage value to an int, tolerating missing/non-numeric input.

    Matches the bash predecessor's `cut -d.` truncation (floor, not round).
    Returns None on any invalid input so the caller can omit the segment (D-10).
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):  # reject NaN / ±inf (e.g. JSON 1e309) — WR-01
        return None
    return math.floor(f)


def fmt_reset(epoch) -> str | None:
    """Format a unix-epoch reset time to LOCAL shorthand (LIM-04).

    Same calendar day → '5:15pm'  (no leading zero on hour, lowercase am/pm)
    Different day     → 'Mon 5:15pm'  (abbreviated weekday prefix)

    Returns None on any error so the caller can silently omit the suffix (D-10,
    T-01-05).
    """
    if epoch is None:
        return None
    try:
        reset_dt = datetime.fromtimestamp(float(epoch))
        today = datetime.now().date()
        # Format: %-I strips leading zero on 12h hour (Linux); %p gives AM/PM
        time_str = reset_dt.strftime("%-I:%M%p").lower()  # e.g. "5:15pm"
        if reset_dt.date() == today:
            return time_str
        # Different day: prepend abbreviated weekday
        weekday = reset_dt.strftime("%a")  # e.g. "Mon"
        return f"{weekday} {time_str}"
    except (OSError, OverflowError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Safe stdin parse
# ---------------------------------------------------------------------------

def _load_stdin() -> dict:
    """Read all of stdin and parse as JSON.  On any error, return {}."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Git helper layer (Phase 04, Plan 01)
# Three pure / IO-isolated helpers consumed by _git_segment (Plan 02).
# subprocess and os are already imported above — no new imports.
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str, timeout: float = 0.15) -> str | None:
    """Run ``git -C cwd <args>`` and return stdout text, or None on any failure.

    Never raises (RUN-01/RUN-02).  On TimeoutExpired the subprocess is killed
    by subprocess.run before the exception propagates, so the render path is
    freed within *timeout* seconds.

    Design notes (D-05/D-06, T-04-01/T-04-02/T-04-03):
    - Fixed argv list — cwd is only ever an argument to ``-C``, NEVER shell-
      interpolated.  ``shell=True`` is intentionally absent (V5 injection
      control).
    - Uses ``-C cwd`` rather than the ``cwd=`` kwarg so a non-existent
      directory degrades through git's own rc!=0 (avoids os.chdir side-effects
      on the parent process).
    - Blanket ``except Exception`` catches TimeoutExpired, FileNotFoundError
      (git absent), OSError, and anything else — segment omits silently.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None          # non-repo (rc=128), empty-repo HEAD failures, etc.
        return proc.stdout
    except Exception:
        return None              # TimeoutExpired, FileNotFoundError (no git), OSError, …


# ---------------------------------------------------------------------------
# GSD state helper layer (Phase 05, Plan 01)
# Two pure / IO-isolated helpers consumed by _gsd_segment (Plan 02).
# json, os, and datetime are already imported above — no new imports.
# ---------------------------------------------------------------------------

# Maximum bytes to read from any single .planning/ file (T-05-01: denial-of-service guard).
# 64 KiB is generous for HANDOFF.json (~2 KiB), STATE.md (~3 KiB), ROADMAP.md (~8 KiB)
# while bounding memory usage on a pathologically large file.
_GSD_MAX_BYTES = 65_536

# Staleness window for HANDOFF.json (D-05 Claude's discretion).
# A HANDOFF is treated as "live" only when its plan field is non-null AND its
# timestamp is within this many seconds of now (UTC).  Beyond the window we fall
# back to the ROADMAP checkbox position.  1 hour is generous — the executor always
# writes a new HANDOFF on each checkpoint; a 1 h-old HANDOFF almost certainly means
# the session ended and the project is now parked (idle).
_GSD_HANDOFF_STALE_SECONDS = 3600   # 1 hour; D-05 discretion

# Roadmap-fallback parsing patterns (IN-01: hoisted to module scope, compiled once).
# Two incomplete-marker shapes are recognised, checked in this order:
#   1. _GSD_PLAN_CHECKBOX  — unchecked plan rows ("- [ ] 05-01-PLAN.md"), the
#      planned-but-unexecuted plan path (kept for synthetic + real roadmaps).
#   2. _GSD_PHASE_HEADER   — unchecked phase headers ("- [ ] **Phase 03.1: ...**"),
#      the real-roadmap shape for a phase with no broken-out plan rows yet.
# Anything else (incl. "- [ ] TBD (run ...)" placeholders) yields no identifier;
# combined with the STATE-progress completeness check this resolves to idle, never
# a false "done" (CR-01 / WR-02).
_GSD_PLAN_CHECKBOX = re.compile(r"-\s\[\s\]\s+(\d+(?:\.\d+)?-\d+-PLAN\.md)")
_GSD_PHASE_HEADER  = re.compile(r"-\s\[\s\]\s+\*\*Phase\s+(\d+(?:\.\d+)?)\s*:")

# Max rendered width for untrusted free-text labels (plan, milestone) — WR-01.
_GSD_LABEL_MAXLEN = 24


def _sanitize_label(s, maxlen=_GSD_LABEL_MAXLEN):
    """Strip control chars (esp. ESC \\x1b) from untrusted file text and clamp width.

    WR-01: ``plan`` (HANDOFF.json) and ``milestone`` (STATE.md) are untrusted
    on-disk text rendered verbatim into the bar.  Keep only printable chars plus
    ASCII space, drop ESC/control sequences (prevents ANSI injection), and truncate
    to ``maxlen`` (prevents unbounded segment width).  Never raises.
    """
    try:
        cleaned = "".join(
            ch for ch in str(s)
            if ch == " " or (ch.isprintable() and ch != "\x1b")
        )
        return cleaned[:maxlen]
    except Exception:
        return ""


def _read_gsd_state(planning_dir: str) -> dict | None:
    """Read HANDOFF.json, STATE.md frontmatter, and ROADMAP.md from planning_dir.

    Returns a dict::

        {
            "handoff": dict,   # parsed HANDOFF.json
            "state":   dict,   # parsed STATE.md YAML frontmatter (incl. nested "progress")
            "roadmap": str,    # raw ROADMAP.md text
        }

    Returns None on any missing file, parse error, oversized read, or OS error.
    Never raises (RUN-01/RUN-02).

    Security (T-05-01, T-05-02):
    - Each file is read with an explicit byte cap (_GSD_MAX_BYTES) — no unbounded
      reads that could stall the bar.
    - All paths are constructed with os.path.join(planning_dir, "<fixed-name>") — no
      attacker-controlled path components beyond the three fixed filenames; no writes
      anywhere; no symlink following added.
    - Whole body is wrapped in try/except Exception so a parse blow-up degrades to
      omission rather than a traceback.
    """
    try:
        handoff_path = os.path.join(planning_dir, "HANDOFF.json")
        state_path   = os.path.join(planning_dir, "STATE.md")
        roadmap_path = os.path.join(planning_dir, "ROADMAP.md")

        # --- HANDOFF.json ---
        with open(handoff_path, encoding="utf-8") as fh:
            handoff = json.loads(fh.read(_GSD_MAX_BYTES))
        if not isinstance(handoff, dict):
            return None

        # --- STATE.md frontmatter ---
        with open(state_path, encoding="utf-8") as fh:
            state_text = fh.read(_GSD_MAX_BYTES)
        state_fm = _parse_gsd_frontmatter(state_text)
        if state_fm is None:
            return None

        # --- ROADMAP.md ---
        with open(roadmap_path, encoding="utf-8") as fh:
            roadmap_text = fh.read(_GSD_MAX_BYTES)

        return {
            "handoff": handoff,
            "state":   state_fm,
            "roadmap": roadmap_text,
        }
    except Exception:
        return None   # file missing, JSON/YAML parse error, OS error — omit silently


def _parse_gsd_frontmatter(text: str) -> dict | None:
    """Parse the YAML frontmatter between the first two ``---`` delimiters in text.

    Handles one level of nesting (the ``progress:`` block in STATE.md) whose
    children are indented with two spaces.  Coerces digit-only values to int;
    strips surrounding quotes from string values.  Returns an empty dict if the
    frontmatter block is present but empty.  Returns None if no delimiters found.
    Never raises.

    This is intentionally minimal — just enough to extract the handful of keys
    the GSD segment needs from STATE.md.  No new dependency added (project uses
    stdlib tomllib for config; YAML here is hand-parsed per the same convention).
    """
    try:
        # Split on '---' lines.  We need lines that are exactly '---' (optional
        # trailing whitespace).  Use splitlines() to handle \r\n safely.
        lines = text.splitlines()
        delimiters = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
        if len(delimiters) < 2:
            return None  # no frontmatter block — caller returns None or empty dict

        fm_lines = lines[delimiters[0] + 1 : delimiters[1]]
        result: dict = {}
        current_mapping: dict | None = None  # active nested dict (e.g. progress)
        current_key: str | None = None

        for line in fm_lines:
            if not line.strip() or line.strip().startswith("#"):
                continue

            # Two-space-indented child → belongs to current_mapping
            if line.startswith("  ") and current_mapping is not None:
                child = line.strip()
                if ":" in child:
                    k, _, v = child.partition(":")
                    v = v.strip().strip('"').strip("'")
                    current_mapping[k.strip()] = int(v) if v.isdigit() else v
                continue

            # Top-level key
            if ":" in line:
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                # IN-02: only an empty value starts a nested mapping; nesting is
                # confirmed by the following two-space-indented child lines.  The
                # old `v.endswith(":")` heuristic misread a scalar value that
                # happens to end in a colon (e.g. "stopped_at: see step 2:").
                if v == "":
                    # Mapping key — start nested dict
                    current_key = k
                    current_mapping = {}
                    result[k] = current_mapping
                else:
                    current_mapping = None
                    current_key = None
                    v = v.strip('"').strip("'")
                    result[k] = int(v) if v.isdigit() else v

        return result
    except Exception:
        return None


def _infer_gsd_lifecycle(state: dict | None) -> dict | None:
    """Infer the active GSD plan id, task progress, plan-of-total, and lifecycle state.

    Input is the dict returned by ``_read_gsd_state``::

        {
            "handoff": dict,
            "state":   dict,   # parsed STATE.md frontmatter
            "roadmap": str,
        }

    Returns a dict::

        {
            "plan_id":     str | None,   # e.g. "05-02", or None when done
            "tasks_done":  int | None,   # len(completed_tasks) clamped ≤ total_tasks
            "total_tasks": int | None,
            "plans_done":  int | None,   # from STATE progress.completed_plans
            "plans_total": int | None,   # from STATE progress.total_plans
            "state":       str,          # "executing"|"verifying"|"blocked"|"idle"|"done"
            "milestone":   str | None,   # e.g. "v1.0" — only set when state=="done"
        }

    Precedence (D-05): HANDOFF is live when its ``plan`` field is a non-null string AND
    its ``timestamp`` is within ``_GSD_HANDOFF_STALE_SECONDS`` seconds of now (UTC).
    When live, HANDOFF is authoritative.  Otherwise fall back to the first incomplete
    plan checkbox in ROADMAP (state → "idle") or "done" when all complete (D-06/D-07).

    Lifecycle priorities (D-03):
    1. blockers non-empty → "blocked"  (highest priority, even over live HANDOFF)
    2. live HANDOFF with status containing "verif" → "verifying"
    3. live HANDOFF → "executing"
    4. stale/null HANDOFF + incomplete ROADMAP plan found → "idle"
    5. stale/null HANDOFF + no incomplete plan → "done"

    Never raises.  Returns None only when state is None.
    """
    if state is None:
        return None

    try:
        handoff  = state.get("handoff") or {}
        state_fm = state.get("state") or {}
        roadmap  = state.get("roadmap") or ""

        # --- plan-of-total from STATE frontmatter ---
        progress    = state_fm.get("progress") or {}
        plans_done  = progress.get("completed_plans")
        plans_total = progress.get("total_plans")
        # Coerce to int in case they arrived as strings (defensive)
        try:
            plans_done  = int(plans_done)  if plans_done  is not None else None
        except (TypeError, ValueError):
            plans_done = None
        try:
            plans_total = int(plans_total) if plans_total is not None else None
        except (TypeError, ValueError):
            plans_total = None

        # WR-01: milestone is untrusted STATE.md text — sanitize before it can
        # ever reach the rendered segment (strip ESC/control chars, clamp width).
        milestone_raw = state_fm.get("milestone")
        milestone_label = _sanitize_label(milestone_raw) if milestone_raw is not None else None

        # --- Determine milestone completeness from STATE progress (D-07) ---
        # D-07 must be POSITIVELY confirmed, never a fall-through default.  Treat
        # the milestone as complete only when STATE.md progress confirms every
        # phase (and, when known, every plan) is done.  This is the authoritative
        # signal; the roadmap is only consulted for the next-incomplete identifier.
        phases_done  = progress.get("completed_phases")
        phases_total = progress.get("total_phases")
        try:
            phases_done  = int(phases_done)  if phases_done  is not None else None
        except (TypeError, ValueError):
            phases_done = None
        try:
            phases_total = int(phases_total) if phases_total is not None else None
        except (TypeError, ValueError):
            phases_total = None

        milestone_complete = (
            phases_total is not None and phases_total > 0
            and phases_done is not None and phases_done >= phases_total
        )
        # When plan-level counts are also present, require plan completion too.
        if milestone_complete and plans_total is not None and plans_done is not None:
            milestone_complete = plans_total > 0 and plans_done >= plans_total

        # --- Check HANDOFF liveness (D-05) ---
        handoff_plan = handoff.get("plan")
        handoff_live = False
        if isinstance(handoff_plan, str) and handoff_plan:
            ts_raw = handoff.get("timestamp") or ""
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                handoff_live = age <= _GSD_HANDOFF_STALE_SECONDS
            except Exception:
                handoff_live = False  # bad timestamp → treat as stale

        # --- Lifecycle state ---
        blockers = handoff.get("blockers") or []
        if handoff_live:
            # Blockers highest priority (D-03 rule 1)
            if blockers:
                lifecycle = "blocked"
            elif "verif" in str(handoff.get("status") or "").lower():
                lifecycle = "verifying"
            else:
                lifecycle = "executing"

            completed_tasks = handoff.get("completed_tasks") or []
            total_tasks_raw = handoff.get("total_tasks")
            try:
                total_tasks = int(total_tasks_raw) if total_tasks_raw is not None else None
            except (TypeError, ValueError):
                total_tasks = None
            # WR-03: a non-positive total_tasks (e.g. 0 or negative from a
            # malformed HANDOFF) is meaningless — treat as "no task count" so the
            # render drops the N/M fragment rather than showing garbage like -1/-1.
            if total_tasks is not None and total_tasks <= 0:
                total_tasks = None
            tasks_done = max(0, len(completed_tasks))
            if total_tasks is not None:
                tasks_done = min(tasks_done, total_tasks)

            return {
                # WR-01: handoff_plan is untrusted HANDOFF.json text — sanitize.
                "plan_id":     _sanitize_label(handoff_plan),
                "phase_id":    None,
                "tasks_done":  tasks_done,
                "total_tasks": total_tasks,
                "plans_done":  plans_done,
                "plans_total": plans_total,
                "state":       lifecycle,
                "milestone":   None,
            }

        # --- HANDOFF stale or null: roadmap fallback (D-05/D-06/D-07) ---
        # D-07 is only emitted when STATE progress POSITIVELY confirms completion
        # (computed above).  This is the fix for CR-01/WR-02: "done" is never a
        # fall-through for an unrecognised/empty roadmap — that resolves to idle.
        if milestone_complete:
            return {
                "plan_id":     None,
                "phase_id":    None,
                "tasks_done":  None,
                "total_tasks": None,
                "plans_done":  plans_done,
                "plans_total": plans_total,
                "state":       "done",
                "milestone":   milestone_label,
            }

        # Not milestone-complete (D-06): find the next incomplete identifier in
        # ROADMAP.md.  Recognise two shapes and PREFER a plan row over a phase
        # header (a plan row is the more specific "next plan" pointer):
        #   1. first unchecked plan row  ("- [ ] 05-01-PLAN.md")        → plan_id
        #   2. else first unchecked phase head ("- [ ] **Phase 03.1: ...**") → phase_id
        # "- [ ] TBD (...)" placeholders match neither and are skipped — yielding
        # an idle state with no identifier rather than a false "done".
        next_plan_id = None
        next_phase_id = None
        for line in roadmap.splitlines():
            m = _GSD_PLAN_CHECKBOX.search(line)
            if m:
                # Strip the -PLAN.md suffix to get the bare plan id (e.g. "05-01").
                next_plan_id = m.group(1)[: -len("-PLAN.md")]
                break
        if next_plan_id is None:
            for line in roadmap.splitlines():
                mp = _GSD_PHASE_HEADER.search(line)
                if mp:
                    # No plan row anywhere — surface the first incomplete phase number.
                    next_phase_id = mp.group(1)
                    break

        # Idle (D-06): show whatever identifier we found (plan id preferred), or
        # none.  Never "done" here.  next_plan_id is regex-constrained (safe);
        # next_phase_id is regex-constrained too.
        return {
            "plan_id":     next_plan_id,
            "phase_id":    next_phase_id,
            "tasks_done":  None,
            "total_tasks": None,
            "plans_done":  plans_done,
            "plans_total": plans_total,
            "state":       "idle",
            "milestone":   None,
        }

    except Exception:
        return None   # RUN-01/RUN-02: never raise on partial dicts


def _gsd_segment(data: dict, cfg: dict) -> str | None:
    """[<plan_id> <task_progress> <status_glyph>] or None.

    Reads live GSD planning state from .planning/ under workspace.project_dir and
    renders a bracketed top-line segment showing the active plan id, task progress,
    and a colored lifecycle status glyph.

    Decision mapping:
    - D-01/D-02: headline is plan_id + task progress (e.g. "05-02 2/3"), no phase prefix
    - D-03/D-09: lifecycle glyph colored (executing/done→GREEN, verifying→YELLOW,
                  blocked→RED, idle→DIM); plan-id/task label stays neutral (no color wrap)
    - D-07: milestone-complete shows explicit done state (milestone + green done glyph)
    - D-08: scoped to workspace.project_dir/.planning; omit silently if absent (non-GSD)
    - D-10: inserted after _git_segment and before _model_segment in render_top_line
    - RUN-01/RUN-02: never raises; entire body wrapped in try/except

    Glyph selection follows icon_set ('nerd' → _NF_GSD_* constants;
    anything else → emoji/ascii fallbacks).
    """
    try:
        # (1) Config toggle (D-08 discretion: display.show_gsd, default True)
        if not cfg.get("display", {}).get("show_gsd", True):
            return None

        # (2) Resolve project_dir: workspace.project_dir ONLY (D-08, NOT current_dir)
        ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
        project_dir = ws.get("project_dir", "")
        if not project_dir:
            return None
        planning_dir = os.path.join(project_dir, ".planning")
        if not os.path.isdir(planning_dir):
            return None   # non-GSD project — omit silently (D-08)

        # (3) Read GSD state files
        state = _read_gsd_state(planning_dir)
        if state is None:
            return None

        # (4) Infer lifecycle state
        info = _infer_gsd_lifecycle(state)
        if info is None:
            return None

        # (6) Resolve glyphs from icon_set
        icon_set = cfg.get("display", {}).get("icon_set", "nerd")
        if icon_set == "nerd":
            exec_glyph   = _NF_GSD_EXECUTING
            verif_glyph  = _NF_GSD_VERIFYING
            block_glyph  = _NF_GSD_BLOCKED
            done_glyph   = _NF_GSD_DONE
            idle_glyph   = _NF_GSD_IDLE
        else:
            # emoji/ascii fallbacks — distinct from nerd codepoints
            exec_glyph   = "\u25b6"    # ▶
            verif_glyph  = "\u2611"    # ☑
            block_glyph  = "\u2298"    # ⊘
            done_glyph   = "\u2713"    # ✓
            idle_glyph   = "\u23f8"    # ⏸

        # Map lifecycle state to its glyph and color (D-09)
        lifecycle = info.get("state", "idle")
        if lifecycle == "executing":
            glyph = exec_glyph
            color = GREEN
        elif lifecycle == "verifying":
            glyph = verif_glyph
            color = YELLOW
        elif lifecycle == "blocked":
            glyph = block_glyph
            color = RED
        elif lifecycle == "done":
            glyph = done_glyph
            color = GREEN
        else:  # idle
            glyph = idle_glyph
            color = DIM

        # (8) Colored lifecycle glyph ONLY (D-09)
        status_glyph = f"{color}{glyph}{RESET}"

        # (7) Neutral label (D-09: no color wrap on plan id or task count)
        plan_id     = info.get("plan_id")
        phase_id    = info.get("phase_id")
        tasks_done  = info.get("tasks_done")
        total_tasks = info.get("total_tasks")
        milestone   = info.get("milestone")
        plans_done  = info.get("plans_done")
        plans_total = info.get("plans_total")

        if lifecycle == "done":
            # D-07: explicit done state — show milestone label, not "None".
            # WR-01: milestone is already sanitized in _infer_gsd_lifecycle;
            # sanitize again here as a defensive render-boundary guard.
            milestone_label = _sanitize_label(milestone) if milestone else "done"
            interior = f"{milestone_label} {status_glyph}"
        else:
            # Active / idle: plan id + task progress (neutral) + colored glyph.
            # CR-01/D-06: when the roadmap fallback found no plan id but did find
            # the next incomplete phase header, surface the phase id instead so
            # the segment still tells you where you'll resume (idle granularity).
            label_id = plan_id if plan_id is not None else phase_id
            if label_id is None:
                return None   # no identifier in non-done state — omit silently
            if plan_id is not None and tasks_done is not None and total_tasks is not None:
                task_label = f"{label_id} {tasks_done}/{total_tasks}"
            else:
                task_label = label_id

            # (9) Optional plan-of-total fragment (D-04) — neutral, no color.
            # Omit when the source STATE.md is internally inconsistent
            # (completed_plans > total_plans, or non-positive total): a
            # logically impossible "(51/47)" would mislead, so per D-10 we
            # drop the fragment silently rather than show or clamp a false ratio.
            if (
                plans_done is not None
                and plans_total is not None
                and plans_total > 0
                and plans_done <= plans_total
            ):
                wave_part = f" ({plans_done}/{plans_total})"
            else:
                wave_part = ""

            interior = f"{task_label}{wave_part} {status_glyph}"

        return f"[{interior}]"
    except Exception:
        return None   # RUN-01/RUN-02: never raise, never traceback

def _parse_git_status_v2(stdout: str) -> dict | None:
    """Parse ``status --porcelain=v2 --branch`` stdout → state dict, or None.

    Returns::

        {
            "branch":   str | None,   # branch name, or None when detached
            "detached": bool,         # True when ``# branch.head (detached)``
            "oid":      str | None,   # full OID, or None for unborn repos
            "dirty":    bool,         # any modified/untracked/staged line present
            "ahead":    int | None,   # commits ahead of upstream; None = no upstream
            "behind":   int | None,   # commits behind upstream; None = no upstream
        }

    Never raises.  ahead/behind default to ``None`` (not 0) when the
    ``# branch.ab`` line is absent (Pitfall 3: no upstream configured).

    Edge cases handled (all VERIFIED against git 2.53.0):
    - ``# branch.head (detached)``  → detached=True, branch=None (Pitfall 4)
    - ``# branch.oid (initial)``    → oid=None without crashing (Pitfall 2)
    - Missing ``# branch.ab``       → ahead=None, behind=None (Pitfall 3)
    - Any "1 "/"2 "/"u " or "? " line → dirty=True (D-02)
    """
    try:
        branch: str | None = None
        oid: str | None = None
        detached = False
        ahead: int | None = None
        behind: int | None = None
        dirty = False

        for line in stdout.splitlines():
            if line.startswith("# branch.head "):
                head = line[len("# branch.head "):].strip()
                if head == "(detached)":
                    detached = True
                else:
                    branch = head
            elif line.startswith("# branch.oid "):
                val = line[len("# branch.oid "):].strip()
                oid = None if val == "(initial)" else val
            elif line.startswith("# branch.ab "):
                # format: "+N -M"
                parts = line[len("# branch.ab "):].split()
                for p in parts:
                    if p.startswith("+"):
                        ahead = int(p[1:])
                    elif p.startswith("-"):
                        behind = int(p[1:])
            elif line[:2] in ("1 ", "2 ", "u ") or line.startswith("? "):
                dirty = True

        return {
            "branch": branch,
            "detached": detached,
            "oid": oid,
            "dirty": dirty,
            "ahead": ahead,
            "behind": behind,
        }
    except Exception:
        return None


def _detect_linked_worktree(rev_parse_stdout: str) -> tuple[bool, str | None]:
    """Return ``(is_linked, worktree_basename)`` from ``rev-parse`` output.

    *rev_parse_stdout* must be the stdout of::

        git rev-parse --absolute-git-dir --git-common-dir --show-toplevel

    Detection logic (D-03, D-04, Pitfall 6):
    - Compare ``os.path.realpath`` of line 0 (``--absolute-git-dir``) with
      line 1 (``--git-common-dir``).  They resolve EQUAL in the main checkout
      and DIVERGE inside a linked worktree (git-dir = ``…/.git/worktrees/<n>``
      while common-dir = ``…/.git``).
    - ``--git-common-dir`` may be returned as a RELATIVE path (e.g. ``.git``
      in the main checkout) or contain ``/../..`` segments (VERIFIED: real
      worktree probe).  Relative paths are resolved against ``--show-toplevel``
      (line 2) before applying ``os.path.realpath``, ensuring the comparison
      is always between two absolute normalised paths.
    - basename = ``os.path.basename(toplevel)`` gives the worktree dir name,
      which is what the user thinks in (D-04).

    Returns ``(False, None)`` on any malformed / insufficient input.
    Never raises.
    """
    try:
        lines = rev_parse_stdout.splitlines()
        if len(lines) < 3:
            return (False, None)
        abs_git_dir_raw = lines[0].strip()
        common_raw      = lines[1].strip()
        toplevel        = lines[2].strip()

        git_dir = os.path.realpath(abs_git_dir_raw)

        # ``--git-common-dir`` may be relative (e.g. ".git" in the main checkout).
        # Resolve it relative to the toplevel so realpath normalises correctly.
        if not os.path.isabs(common_raw) and toplevel:
            common = os.path.realpath(os.path.join(toplevel, common_raw))
        else:
            common = os.path.realpath(common_raw)

        is_linked = git_dir != common
        name = os.path.basename(toplevel.rstrip("/")) if toplevel else None
        return (is_linked, name)
    except Exception:
        return (False, None)


# ---------------------------------------------------------------------------
# Segment builders (each returns a string or None to omit)
# Each builder accepts thresholds forwarded from loaded config.
# ---------------------------------------------------------------------------

def _project_segment(data: dict) -> str | None:
    """[<basename of workspace.project_dir>] or None if absent/empty."""
    try:
        # IN-03: standardize on the isinstance-guarded workspace access used by
        # _gsd_segment / _git_segment (handles workspace being a non-dict cleanly).
        ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
        project_dir = ws.get("project_dir", "")
        if not project_dir:
            return None
        basename = os.path.basename(project_dir.rstrip("/"))
        if not basename:
            return None
        return f"[{basename}]"
    except Exception:
        return None


def _git_segment(data: dict, cfg: dict) -> str | None:
    """[<wt-marker?><branch-glyph><branch|sha> <dirty?><ahead/behind?>] or None.

    Reads live git state for the session's working directory (D-08) and renders
    a bracketed top-line segment mirroring the _project_segment shape.

    Decision mapping:
    - D-01: shows branch, dirty, ahead/behind — no standalone SHA or stash count
    - D-02: single dirty marker only (no per-type counts)
    - D-03/D-04: worktree glyph+basename prepended ONLY when in a linked worktree
    - D-05/D-06: two timeout-guarded git subprocess calls via _run_git
    - D-07: no caching — runs every render
    - D-08: dir from workspace.current_dir → cwd → os.getcwd() (NOT project_dir)
    - D-10: branch/worktree label NEUTRAL; dirty/ahead/behind markers COLORED
    - RUN-01/RUN-02: never raises, entire body wrapped in try/except

    Glyph selection follows icon_set ('nerd' → _NF_GIT_* constants;
    anything else → emoji/ascii fallbacks: '⑂' worktree, '✚' dirty, '↑'/'↓' ab).
    """
    try:
        # (1) Config toggle (D-08 discretion: display.show_git, default True)
        if not cfg.get("display", {}).get("show_git", True):
            return None

        # (2) Resolve repo dir: workspace.current_dir → cwd → os.getcwd() (D-08)
        ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
        repo_dir = ws.get("current_dir") or data.get("cwd") or os.getcwd()

        # (3) Fetch git status (D-05/D-06: one call, timeout-guarded)
        status_out = _run_git(["status", "--porcelain=v2", "--branch"], repo_dir)
        if status_out is None:
            return None   # non-repo / timeout / git absent → omit silently (RUN-01)

        # (4) Parse the porcelain-v2 output
        st = _parse_git_status_v2(status_out)
        if st is None:
            return None

        # (5) Worktree detection: second git call (D-04)
        rp_out = _run_git(
            ["rev-parse", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"],
            repo_dir,
        )
        is_linked, wt_name = _detect_linked_worktree(rp_out or "")

        # (6) Resolve glyphs from icon_set (Pattern 4)
        icon_set = cfg.get("display", {}).get("icon_set", "nerd")
        if icon_set == "nerd":
            branch_glyph = _NF_GIT_BRANCH
            wt_glyph     = _NF_GIT_WORKTREE
            dirty_glyph  = _NF_GIT_DIRTY
            ahead_glyph  = _NF_GIT_AHEAD
            behind_glyph = _NF_GIT_BEHIND
        else:
            branch_glyph = ""      # no branch glyph in plain emoji/ascii mode
            wt_glyph     = "⑂"
            dirty_glyph  = "✚"
            ahead_glyph  = "↑"
            behind_glyph = "↓"

        # (7) Branch text: name or 7-char short SHA for detached HEAD (D-01, Pitfall 4)
        if st["detached"]:
            oid = st.get("oid") or ""
            branch_text = oid[:7] if oid else "HEAD"
        elif st["branch"]:
            branch_text = st["branch"]
        else:
            # Unborn branch with no oid — show empty string; the UNBORN name is in branch
            branch_text = "HEAD"

        # Build the neutral branch label (D-10: no color wrap for the branch itself).
        # branch_glyph precedes the name; both rendered without color.
        label = f"{branch_glyph}{branch_text}" if branch_glyph else branch_text

        # (8) Dirty marker: YELLOW-colored single glyph, only when dirty (D-02/D-10)
        dirty_part = f"{YELLOW}{dirty_glyph}{RESET}" if st["dirty"] else ""

        # (9) Ahead/behind markers: colored, only when non-None AND > 0 (Open Q1)
        ab_parts = []
        ahead = st.get("ahead")
        behind = st.get("behind")
        if ahead is not None and ahead > 0:
            ab_parts.append(f"{GREEN}{ahead_glyph}{ahead}{RESET}")
        if behind is not None and behind > 0:
            ab_parts.append(f"{YELLOW}{behind_glyph}{behind}{RESET}")
        ab_part = " ".join(ab_parts)

        # Assemble the interior: label + optional state markers
        state_parts = [p for p in [dirty_part, ab_part] if p]
        if state_parts:
            interior = f"{label} {''.join(state_parts)}"
        else:
            interior = label

        # (10) Prepend worktree marker ONLY when inside a linked worktree (D-03/D-04)
        if is_linked and wt_name:
            interior = f"{wt_glyph} {wt_name} {interior}"

        return f"[{interior}]"
    except Exception:
        return None   # RUN-01/RUN-02: never raise, never traceback


def _model_segment(
    data: dict,
    show_thinking_glyph: bool = True,
    icon_set: str = "nerd",
) -> str | None:
    """[<model.display_name> <thinking-glyph>?] or None if display_name absent/empty.

    When show_thinking_glyph is False the thinking glyph is suppressed (D-08).
    icon_set selects the thinking glyph: "nerd" uses _NF_THINKING, "emoji" uses 💭 (D-01/D-07).
    """
    try:
        display_name = data.get("model", {}).get("display_name", "")
        if not display_name:
            return None
        thinking_enabled = data.get("thinking", {}).get("enabled", False)
        if thinking_enabled and show_thinking_glyph:
            try:
                thinking_glyph = _NF_THINKING if icon_set == "nerd" else "💭"
            except Exception:
                thinking_glyph = "💭"  # fallback to emoji on any glyph-selection failure
            suffix = f" {thinking_glyph}"
        else:
            suffix = ""
        return f"[{display_name}{suffix}]"
    except Exception:
        return None


def _context_segment(
    data: dict,
    warn: int | float = 70,
    crit: int | float = 90,
    bar_style: str = "shade",
) -> str | None:
    """[<20-wide bar>] <pct>% colored by threshold, or None if missing (CTX-01, CTX-02, D-05).

    Phase 3: bar_style selects the filled/empty glyph pair from _BAR_PRESETS (D-01/D-08).
    Per-cell color (D-06/D-07): filled cells are wrapped in the threshold color; empty cells
    are wrapped in GRAY — sharpening the filled/empty contrast for all block presets.
    Unknown bar_style silently falls back to "shade" via _bar_preset (RUN-02).

    gradient preset (D-02/D-04/D-07): eighth-block sub-cell precision — full █ cells + one
    left-aligned partial-block boundary cell (▏▎▍▌▋▊▉) + blank empty track. The blank
    track is uncolored per D-07 (gray treatment is moot when there is nothing to color).
    Sub-cell precision is gradient-only; shade/solid/solid-dim stay whole-cell (D-04).
    """
    try:
        ctx = data.get("context_window", {})
        pct = pct_int(ctx.get("used_percentage"))
        if pct is None:
            return None
        color = color_for(pct, warn, crit)

        if bar_style == "gradient":
            # D-02/D-04: eighth-block sub-cell rendering for gradient only.
            # total_eighths clamped to [0, _BAR_WIDTH*8] so out-of-range pct never
            # overflows/underflows the bar or indexes _GRADIENT_PARTIAL out of range (T-03-03).
            total_eighths = round(pct / 100 * _BAR_WIDTH * 8)
            total_eighths = max(0, min(_BAR_WIDTH * 8, total_eighths))
            full_cells = total_eighths // 8
            remainder  = total_eighths % 8   # 0 means exact whole-cell boundary
            # Build the visible cell content (always exactly _BAR_WIDTH cells wide).
            filled_part = "█" * full_cells
            if remainder > 0:
                boundary_glyph = _GRADIENT_PARTIAL[remainder - 1]
                blank_count    = _BAR_WIDTH - full_cells - 1
            else:
                boundary_glyph = ""
                blank_count    = _BAR_WIDTH - full_cells
            # D-07: filled run + boundary glyph get the threshold color; blank track is
            # uncolored (no GRAY wrap) because there is nothing to color there.
            colored_filled = f"{color}{filled_part}{boundary_glyph}{RESET}" if (filled_part or boundary_glyph) else ""
            blank_track = " " * blank_count
            bar = f"[{colored_filled}{blank_track}]"
        else:
            # Whole-cell rendering for shade / solid / solid-dim (D-04 — do not touch).
            # Clamp to [0, _BAR_WIDTH] so out-of-range pct never overflows (CR-01).
            filled = max(0, min(_BAR_WIDTH, math.floor(pct * _BAR_WIDTH / 100)))
            empty = _BAR_WIDTH - filled
            fill_glyph, empty_glyph = _bar_preset(bar_style)
            # D-06: filled run in threshold color, empty run in dim GRAY — per-cell color split.
            filled_str = f"{color}{fill_glyph * filled}{RESET}" if filled else ""
            empty_str  = f"{GRAY}{empty_glyph * empty}{RESET}"  if empty  else ""
            bar = f"[{filled_str}{empty_str}]"

        pct_str = f"{color}{pct}%{RESET}"
        return f"{bar} {pct_str}"
    except Exception:
        return None


def _sun_segment(cfg: dict | None, now: datetime | None = None) -> str | None:
    """Return the next sun event as a glyph + local time string, or None on failure.

    Selection logic (matches bash predecessor's sunriseset(), D2-10):
      - now < today's sunrise  → "🌅 <sunrise>"  (sunrise glyph + sunrise time)
      - now < today's sunset   → "🌇 <sunset>"   (sunset glyph + sunset time)
      - otherwise              → "🌅 <tomorrow's sunrise>"  (next day wraps)

    Time formatted with strftime("%-I:%M%p").lower() — matches fmt_reset() e.g. "6:14am".
    Returns None immediately when _ASTRAL_OK is False (import-level guard, D2-12).
    Returns None on any error (missing lat/lon, astral failure, bad cfg) — silent omit.
    Never raises to the caller.
    """
    if not _ASTRAL_OK:
        return None
    try:
        location = (cfg or {}).get("location", {})
        lat = location.get("lat")
        lon = location.get("lon")
        if lat is None or lon is None:
            return None
        # 0.0/0.0 is the unconfigured placeholder (null island) — treat as not set.
        if float(lat) == 0.0 and float(lon) == 0.0:
            return None

        if now is None:
            now = datetime.now()
        # Treat `now` as local wall-clock time, made timezone-aware in the system
        # local zone. CRITICAL: pass that same local tzinfo to astral's sun() so it
        # computes events for the LOCAL calendar date. With the default (UTC) tzinfo,
        # sun(date=D) returns the events occurring on UTC-date D — for a western
        # (UTC-offset-negative) location that puts "today's sunset" on the *previous*
        # local evening, so both today's events read as past and selection breaks.
        now = now.astimezone()
        local_tz = now.tzinfo

        loc = LocationInfo(name="", region="", timezone="UTC", latitude=lat, longitude=lon)

        # Events come back tz-aware in local_tz — no further conversion needed.
        today = now.date()
        s_today = sun(loc.observer, date=today, tzinfo=local_tz)
        sunrise_today = s_today["sunrise"]
        sunset_today  = s_today["sunset"]

        # Resolve icon_set from cfg (D-06/D-07); default "nerd" matches the config default.
        _display = (cfg or {}).get("display", {})
        _icon_set = _display.get("icon_set", "nerd")

        if now < sunrise_today:
            event_time = sunrise_today
            is_sunrise = True
        elif now < sunset_today:
            event_time = sunset_today
            is_sunrise = False
        else:
            # Past today's sunset — next event is tomorrow's sunrise
            s_tomorrow = sun(loc.observer, date=today + timedelta(days=1), tzinfo=local_tz)
            event_time = s_tomorrow["sunrise"]
            is_sunrise = True

        # Select glyph based on icon_set with emoji fallback on any failure (D-10)
        try:
            if _icon_set == "nerd":
                glyph = _WI_SUNRISE if is_sunrise else _WI_SUNSET
            else:
                glyph = "\U0001f305" if is_sunrise else "\U0001f307"  # 🌅 / 🌇
        except Exception:
            glyph = "\U0001f305" if is_sunrise else "\U0001f307"  # emoji fallback

        # Format in LOCAL time: "6:14am" — matches fmt_reset() format (LIM-04 / D2-10)
        time_str = event_time.strftime("%-I:%M%p").lower()
        return f"{glyph} {time_str}"
    except Exception:
        return None


def _weather_segment(data: dict | None, cfg: dict | None) -> str | None:
    """Return the bracketed weather segment or None to omit (D2-10, D2-12).

    Format (D2-10):  [<icon> <temp>°F | 🌧️<pop>% | <sun-or-alert>]

    Render path (D2-05):
      1. Read cache.json (instant, no network).
      2. If weather OR alerts section is stale (past TTL), fire-and-forget spawn.
      3. Build internals from cached values + local sun/alert computation:
         - conditions chunk: icon + temp — only when section_within_ceiling passes
         - precip chunk: 🌧️<pop>% — only when PoP is present and non-zero (WX-02, D2-09)
         - trailing detail: alert override when within-ceiling active alert exists (D2-11),
           else the sun event (always computed offline, D2-12)
      4. Pipe-delimit present chunks and return bracketed string.

    Alert override (D2-11, WX-04, D-04/D-05/D-06/D-08):
      - Read alerts cache section; if within alerts_max_stale and non-empty survivors:
        run select_alert → render per-class glyph + sanitized event, class-hue colored
        via _alert_color(best), + per-class tally (_build_alert_tally) for remainder.
      - Otherwise: fall back to _sun_segment(cfg).

    Degradation (D2-12):
      - Weather section beyond max-stale ceiling → conditions dropped, sun-only
      - Alerts beyond alerts_max_stale or absent → sun event detail (no marker)
      - Sun segment absent (no lat/lon) → omit entire segment (return None)
      - _WEATHER_OK False or show_weather False → return None immediately

    Wraps entire body in try/except — never raises to caller (D-10).
    """
    try:
        if not _WEATHER_OK:
            return None
        cfg = cfg or {}
        weather_cfg = cfg.get("weather", {})
        if not weather_cfg.get("show_weather", True):
            return None

        # No configured location → weather isn't set up; omit the whole segment.
        # lat/lon both 0.0 is the install placeholder meaning "unconfigured" (null
        # island, no inhabitants), so out-of-the-box the bar matches Phase 1 until
        # the user sets a real [location] in claude-statusline.toml.
        _loc = cfg.get("location", {})
        _lat, _lon = _loc.get("lat"), _loc.get("lon")
        if _lat is None or _lon is None or (float(_lat) == 0.0 and float(_lon) == 0.0):
            return None

        import time as _time
        now = _time.time()
        cache_cfg = cfg.get("cache", {})
        weather_max_stale = float(cache_cfg.get("weather_max_stale", 3600))
        alerts_max_stale = float(cache_cfg.get("alerts_max_stale", 900))

        # Step 1: Read cache (render path — instant, never fetches inline)
        cache = read_cache(_CACHE_PATH)
        weather_section = cache.get("weather", {})
        alerts_section = cache.get("alerts", {})

        # Step 2: Trigger background refresh if weather OR alerts is stale (D2-05)
        maybe_spawn_refresh(cfg, cache)

        # Resolve icon_set from config (D-06/D-07): read at render time so toggling
        # takes effect on the next render without waiting for a cache refresh.
        display = cfg.get("display", {})
        icon_set = display.get("icon_set", "nerd")

        # Compute astral is_night override so the condition icon agrees with the
        # sun segment near sunset.  NWS flips its /night/ URL path before the true
        # local sunset; without the override a moon glyph appears while the sun
        # segment still shows the upcoming sunset time.
        # Fails silently (None) when _ASTRAL_OK is False or location is unset.
        _astral_is_night: bool | None = None
        if _ASTRAL_OK:
            try:
                _loc = cfg.get("location", {})
                _lat, _lon = _loc.get("lat"), _loc.get("lon")
                if (_lat is not None and _lon is not None
                        and not (float(_lat) == 0.0 and float(_lon) == 0.0)):
                    _now_dt = datetime.now().astimezone()
                    _local_tz = _now_dt.tzinfo
                    _loc_info = LocationInfo(name="", region="", timezone="UTC",
                                            latitude=_lat, longitude=_lon)
                    _s_today = sun(_loc_info.observer, date=_now_dt.date(), tzinfo=_local_tz)
                    _astral_is_night = not (_s_today["sunrise"] <= _now_dt <= _s_today["sunset"])
            except Exception:
                pass  # Fall through: _astral_is_night remains None (use NWS URL flag)

        # Step 3a: Conditions chunk — only when within the max-stale ceiling (D2-12)
        conditions_chunk = None
        if section_within_ceiling(weather_section, max_stale=weather_max_stale, now=now):
            # Read raw NWS tokens stored by fetch_weather (D-04/D-07).
            # Backward-compat: also check the old "icon" key for existing caches
            # that pre-date the token migration (old caches may store a glyph in "icon").
            text_desc = weather_section.get("text_desc", "")
            cached_icon_url = weather_section.get("icon_url", "")
            # Fallback to old "icon" key for backward-compat with pre-migration caches
            legacy_icon = weather_section.get("icon")
            temp = weather_section.get("temp")

            if temp is not None and (text_desc or cached_icon_url or legacy_icon):
                temp_unit = cfg.get("units", {}).get("temp_unit", "F")
                unit_symbol = "°C" if temp_unit == "C" else "°F"

                if text_desc or cached_icon_url:
                    # New token format: resolve glyph at render time
                    try:
                        glyph = _icon_to_glyph(text_desc, cached_icon_url, icon_set,
                                               is_night_override=_astral_is_night)
                        if icon_set == "nerd":
                            # D-08: wrap nerd glyph in semantic ANSI color (top-line only)
                            category = _condition_category(text_desc, cached_icon_url,
                                                           is_night_override=_astral_is_night)
                            color = _wx_color(category)
                            colored_glyph = f"{color}{glyph}{RESET}"
                        else:
                            # emoji path: emoji carry their own color — no ANSI wrapping
                            colored_glyph = glyph
                    except Exception:
                        colored_glyph = legacy_icon or _WI_FALLBACK
                    conditions_chunk = f"{colored_glyph} {temp}{unit_symbol}"
                elif legacy_icon:
                    # Old cache format (pre-migration) — use stored glyph as-is
                    conditions_chunk = f"{legacy_icon} {temp}{unit_symbol}"

        # Step 3b: Precip chunk — only when PoP meets the minimum threshold (WX-02, D2-09).
        # Sub-threshold PoP is noise to a forecaster; hide it. Default floor 30%,
        # configurable via [weather] pop_min.
        precip_chunk = None
        if section_within_ceiling(weather_section, max_stale=weather_max_stale, now=now):
            pop = weather_section.get("pop")
            try:
                pop_min = float(weather_cfg.get("pop_min", 30))
            except (TypeError, ValueError):
                pop_min = 30.0
            if pop is not None and float(pop) >= pop_min:
                # D-07 / IN-02: respect icon_set toggle so the precip chunk stays
                # visually consistent with the rest of the weather block.
                if icon_set == "nerd":
                    precip_chunk = f"{_WI_RAINDROPS}{int(pop)}%"
                else:
                    precip_chunk = f"\U0001f327️{int(pop)}%"  # 🌧️

        # Step 3c: Trailing detail — alert override or sun event (D2-11, D2-12, WX-04)
        trailing_detail = None
        # Attempt alert override: only when alerts section is within ceiling + non-empty
        try:
            if section_within_ceiling(alerts_section, max_stale=alerts_max_stale, now=now):
                active = alerts_section.get("active") or []
                if active:
                    best, remaining_alerts = select_alert(active)
                    if best is not None:
                        try:
                            props = best.get("properties") or best
                            event = props.get("event", "Unknown Alert")
                        except Exception:
                            event = "Unknown Alert"
                        # D-05/D-06: class-driven hue + urgency/certainty intensity
                        color = _alert_color(best)
                        # D-04: class glyph resolved via icon_set toggle
                        best_class = _classify_alert_class(best)
                        if icon_set == "nerd":
                            class_glyph = _ALERT_CLASS_GLYPHS_NERD.get(best_class, _WI_ALERT_STATEMENT)
                        else:
                            class_glyph = _ALERT_CLASS_GLYPHS_EMOJI.get(best_class, "ℹ️")
                        # Sanitize event text — strip ESC/control seqs, truncate to 64 (T-02.2-04)
                        safe_event = "".join(
                            ch for ch in str(event)
                            if ch == " " or (ch.isprintable() and ch != "\x1b")
                        )[:64].strip()
                        # D-10: never emit a hollow glyph — if sanitization left nothing
                        # (e.g. an all-control-char event), fall back to the class name (WR-02).
                        if not safe_event:
                            safe_event = best_class
                        detail = f"{class_glyph} {safe_event}"
                        # D-08: per-class tally of remaining alerts (not flat +N)
                        if remaining_alerts:
                            tally = _build_alert_tally(remaining_alerts, icon_set)
                            if tally:
                                detail += f"  {tally}"
                        trailing_detail = f"{color}{detail}{RESET}"
        except Exception:
            pass  # alert override failed: fall through to sun event

        # Fall back to sun event if no valid alert override
        if trailing_detail is None:
            trailing_detail = _sun_segment(cfg)

        # Assemble pipe-delimited internals (omit None pieces)
        pieces = [p for p in [conditions_chunk, precip_chunk, trailing_detail] if p is not None]

        if not pieces:
            # No trailing detail and no conditions: omit the whole segment
            return None

        internals = " | ".join(pieces)
        return f"[{internals}]"
    except Exception:
        return None


def _rate_segment(
    block: dict,
    glyph: str,
    warn: int | float = 70,
    crit: int | float = 90,
) -> str | None:
    """<glyph> <pct>%[ <dim reset>] colored by threshold, or None if missing (LIM-01/02/03/04)."""
    try:
        pct = pct_int(block.get("used_percentage"))
        if pct is None:
            return None
        color = color_for(pct, warn, crit)
        pct_str = f"{color}{pct}%{RESET}"
        result = f"{glyph} {pct_str}"
        # Append reset time only when not green (D-04, LIM-03)
        if not is_green(pct, warn):
            resets_at = block.get("resets_at")
            if resets_at is not None:
                reset_str = fmt_reset(resets_at)
                if reset_str:
                    result += f" {DIM}{reset_str}{RESET}"
        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Claude status segment — Phase 06, Plan 02 (render path)
# ---------------------------------------------------------------------------

# Maximum visible characters for a sanitized incident/maintenance label.
# Narrower than the alert-override bound (64) since status titles are short
# and the segment appears at the trailing end of an already-busy bottom line.
_CLAUDE_STATUS_LABEL_MAXLEN: int = 50


def _claude_status_segment(data: object, cfg: object) -> str | None:
    """Return a severity-colored glyph + sanitized incident/maintenance title, or None.

    Reads the "claude_status" cache section written by fetch_claude_status (Plan 01).
    Never blocks on the network — all I/O is a single cache read.

    Return rules (first match):
      - show_claude_status=False → None
      - cache absent / section stale past status_max_stale → None  (cold-cache silent, D-01)
      - noteworthy=False (healthy) → None  (quiet-when-healthy, D-01)
      - kind=="maintenance" → neutral glyph (_NF_CLAUDE_MAINT) + DIM color (D-04)
      - kind=="incident" or "degraded" → severity glyph + _claude_status_color(severity)
      - Sanitization (T-06-04): ANSI-strip + width-bound + hollow-glyph fallback (WR-02)
      - Any exception → return None (D-10 never-crash)

    Shape identical to _rate_segment / _gsd_segment: body wrapped in try/except.
    """
    try:
        # Step 1: toggle guard (mirrors show_gsd / show_weather pattern)
        _cfg = cfg if isinstance(cfg, dict) else {}
        if not _cfg.get("display", {}).get("show_claude_status", True):
            return None

        # Step 2: read cache section + freshness gate
        import time as _time
        now = _time.time()
        cache_cfg = _cfg.get("cache", {})
        status_max_stale = float(cache_cfg.get("status_max_stale", 900))

        cache = read_cache(_CACHE_PATH)
        sec = cache.get("claude_status", {})
        if not isinstance(sec, dict):
            return None
        if not section_within_ceiling(sec, max_stale=status_max_stale, now=now):
            return None  # cold / too-stale → silent omit (D-01)

        # Step 3: healthy check — noteworthy=False means all-clear (D-01)
        noteworthy = sec.get("noteworthy")
        if not noteworthy:
            return None

        # Step 4: resolve severity, label, kind from section
        severity = sec.get("severity", "minor")
        label    = sec.get("label", "")
        kind     = sec.get("kind", "incident")

        # Step 5: resolve icon_set and glyph (D-04 distinct glyphs for incident vs maintenance)
        icon_set = _cfg.get("display", {}).get("icon_set", "nerd")
        # WR-01 / D-04: key the maintenance glyph off the maintenance SIGNAL, not only
        # `kind`. A tracked component in `under_maintenance` with no scheduled_maintenances
        # entry falls through _derive_claude_status Rule 3 with severity=="maintenance" but
        # kind=="degraded"; branching on `kind` alone wrongly emitted the INCIDENT glyph,
        # conflating maintenance with an outage. Branch on severity=="maintenance" too so
        # the wrench glyph stays consistent with the DIM color and "maintenance" label.
        if kind == "maintenance" or severity == "maintenance":
            # Neutral maintenance path (D-04): wrench glyph + DIM color
            if icon_set == "nerd":
                glyph = _NF_CLAUDE_MAINT
            else:
                glyph = "\U0001f527"   # 🔧 emoji fallback (wrench)
            color = _claude_status_color("maintenance")  # DIM (neutral, not severity)
        else:
            # Incident / degraded path: exclamation glyph + severity color (D-03)
            if icon_set == "nerd":
                glyph = _NF_CLAUDE_INCIDENT
            else:
                glyph = "\U0001f534"   # 🔴 emoji fallback
            color = _claude_status_color(severity)

        # Step 6: sanitize label — strip ESC / non-printable, width-bound, hollow-glyph guard
        # VERBATIM from _weather_segment alert-override sanitizer (:2906-2913, T-02.2-04/T-06-04)
        safe_label = "".join(
            ch for ch in str(label)
            if ch == " " or (ch.isprintable() and ch != "\x1b")
        )[:_CLAUDE_STATUS_LABEL_MAXLEN].strip()
        # WR-02 / D-03 fallback: never emit a bare glyph when label is empty after sanitization
        if not safe_label:
            safe_label = kind or "incident"  # kind is already a safe string

        # Step 7: assemble and return (matches alert-override assembly, :2915-2921)
        detail = f"{glyph} {safe_label}"
        return f"{color}{detail}{RESET}"

    except Exception:
        return None  # D-10 never-crash — render path must not blow up


# ---------------------------------------------------------------------------
# Line renderers (accept config dict forwarded from main)
# ---------------------------------------------------------------------------

def render_top_line(data: dict, cfg: dict) -> str:
    """Assemble the top line from present segments, joined by a single space.

    Phase 1:    [project] [model 💭]
    Phase 2:    [project] [model 💭] [<weather segment>]
    Phase 02.1: glyph set controlled by icon_set (D-01/D-07).
    Phase 04:   [project] [git] [model 💭] [<weather>]  (D-09 ordering)
                git segment inserted between project and model (D-09).
                Omitted when show_git=false, non-repo, timeout, or git absent.
    Phase 05:   [project] [git] [gsd] [model 💭] [<weather>]  (D-10 ordering)
                gsd segment inserted after git and before model (D-10).
                Omitted when show_gsd=false, .planning/ absent, or any read error.
    """
    toggles = cfg.get("toggles", {})
    show_thinking_glyph = toggles.get("show_thinking_glyph", True)
    display = cfg.get("display", {})
    icon_set = display.get("icon_set", "nerd")
    segments = [
        _project_segment(data),
        _git_segment(data, cfg),        # D-09: immediately after project, before model
        _gsd_segment(data, cfg),        # D-10: immediately after git, before model
        _model_segment(data, show_thinking_glyph=show_thinking_glyph, icon_set=icon_set),
        _weather_segment(data, cfg),    # None-filtered by the existing space-join (D2-10)
    ]
    present = [s for s in segments if s is not None]
    return " ".join(present)


def render_bottom_line(data: dict, cfg: dict) -> str | None:
    """Assemble the bottom line; return None if no segments are present.

    Layout (D-03): [bar] pct%   ⏳ 5h%[ reset]   🗓 wk%[ reset]   <status>
    Three spaces separate each block (D-06).
    Per-segment toggles from cfg suppress individual segments (D-08).

    Phase 06: Claude service-health status segment appended after weekly_seg (D-06).
    The status segment is built by _claude_status_segment, which reads the
    "claude_status" cache section silently (no network I/O on render path).

    Render-path refresh trigger (Phase 06): maybe_spawn_refresh is called here so
    the status cache stays fresh even when weather is disabled / no location is
    configured — the weather segment's own maybe_spawn_refresh call is unreachable
    when _WEATHER_OK is False or location is unconfigured (T-06-06 / D-05).
    The single O_CREAT|O_EXCL lock prevents a double-spawn if weather also triggers.
    """
    try:
        toggles    = cfg.get("toggles", {})
        thresholds = cfg.get("thresholds", {})
        warn = thresholds.get("warn", 70)
        crit = thresholds.get("crit", 90)

        # Phase 03: resolve bar_style from config (D-08/D-10); mirrors icon_set resolution below.
        _display = cfg.get("display", {})
        _bar_style = _display.get("bar_style", "shade")

        ctx_seg = (
            _context_segment(data, warn=warn, crit=crit, bar_style=_bar_style)
            if toggles.get("show_context_bar", True)
            else None
        )

        rate_limits = data.get("rate_limits", {})
        five_hour_block = rate_limits.get("five_hour", {}) if isinstance(rate_limits, dict) else {}
        seven_day_block = rate_limits.get("seven_day", {}) if isinstance(rate_limits, dict) else {}

        # Resolve rate-limit glyphs from icon_set (D-01/D-07).
        # _rate_segment signature is UNCHANGED — glyph swap happens at the call site only.
        # Note: _display already resolved above for bar_style; reuse it here.
        _icon_set = _display.get("icon_set", "nerd")
        if _icon_set == "nerd":
            _glyph_5h = _NF_HOURGLASS
            _glyph_wk = _NF_CALENDAR
        else:
            _glyph_5h = "⏳"
            _glyph_wk = "🗓"

        five_hour_seg = (
            _rate_segment(five_hour_block, _glyph_5h, warn=warn, crit=crit)
            if (toggles.get("show_five_hour", True) and isinstance(five_hour_block, dict))
            else None
        )
        weekly_seg = (
            _rate_segment(seven_day_block, _glyph_wk, warn=warn, crit=crit)
            if (toggles.get("show_weekly", True) and isinstance(seven_day_block, dict))
            else None
        )

        # Phase 06: Claude service-health segment, appended AFTER weekly_seg (D-06).
        # Build + trigger the render-path refresh here so status stays fresh even when
        # weather is disabled (weather segment's spawn call is unreachable in that case).
        # The fire-and-forget spawn is idempotent: the existing O_CREAT|O_EXCL lock
        # prevents a double-refresh if the weather segment also spawns one.
        try:
            _render_cache = read_cache(_CACHE_PATH)
            maybe_spawn_refresh(cfg, _render_cache)
        except Exception:
            pass  # never-crash: spawn failure must not block render
        status_seg = _claude_status_segment(data, cfg)

        parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]
        if not parts:
            return None
        return "   ".join(parts)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # FIRST: switch to the venv interpreter (D2-03). Done here (not at import) so
    # importing this module never hijacks the importer via os.execv.
    _reexec_into_venv()

    # --refresh mode: invoked by the detached background child (D2-05).
    # Loads config, runs the NWS fetch, writes cache, exits.
    # Never reads stdin; never writes to stdout (only the render path does that).
    if "--refresh" in sys.argv:
        cfg = load_config()
        run_refresh(cfg)
        sys.exit(0)

    cfg = load_config()
    data = _load_stdin()
    top = render_top_line(data, cfg)
    print(top)
    bottom = render_bottom_line(data, cfg)
    if bottom is not None:
        print(bottom)
    sys.exit(0)


if __name__ == "__main__":
    main()
