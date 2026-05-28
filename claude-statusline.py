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
import fcntl
import json
import math
import subprocess
import tomllib
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# ANSI color constants
# ---------------------------------------------------------------------------

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"    # dim/neutral — used for reset times (D-04)
RESET  = "\033[0m"

# Bar fill characters (▓ = filled block, ░ = light shade / empty)
_FILLED = "▓"
_EMPTY  = "░"
_BAR_WIDTH = 20


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
    },
    # Phase-2 weather settings (D2-12)
    "weather": {
        "contact_email": "your-email@example.com",  # required by NWS ToS for User-Agent
        "show_weather":  True,
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
#     "weather": { "fetched_at": <epoch>, "icon": ..., "temp": ..., "pop": ... },
#     "alerts":  { "fetched_at": <epoch>, "active": [...] }
#   }
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

# NWS textDescription / icon-path → emoji mapping (Claude's discretion per CONTEXT).
# The icon URL path encodes the condition code (e.g. /icons/land/day/skc).
# We match against textDescription first (case-insensitive) then fall back to
# scanning the icon URL path segment.
_NWS_ICON_MAP: list[tuple[tuple[str, ...], str]] = [
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
    # Cloudy
    (("overcast", "cloudy"), "☁️"),
    # Mostly / partly cloudy
    (("mostly cloudy", "bkn", "broken", "few", "scattered", "partly cloudy",
      "mostly clear", "partly sunny"), "⛅"),
    # Clear / sunny
    (("clear", "fair", "sunny", "skc", "hot"), "☀️"),
    # Cold / frost
    (("cold", "frost"), "🥶"),
]


def _icon_to_emoji(text_description: str, icon_url: str) -> str:
    """Map NWS textDescription and/or icon URL to an emoji condition icon.

    Tries text_description first (lowercase contains-match), then icon URL path.
    Falls back to "🌡️" if no match found.
    """
    desc = (text_description or "").lower()
    icon_path = (icon_url or "").lower()

    for keywords, emoji in _NWS_ICON_MAP:
        for kw in keywords:
            if kw in desc or kw in icon_path:
                return emoji
    return "🌡️"  # fallback: thermometer


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
        icon_url = obs_props.get("icon", "")
        icon_emoji = _icon_to_emoji(text_desc, icon_url)
        temp_converted = c_to_unit(temp_c, temp_unit)

        # Step 4: /gridpoints/{cwa}/{x},{y}/forecast/hourly — PoP for current period
        hourly_url = f"https://api.weather.gov/gridpoints/{cwa}/{grid_x},{grid_y}/forecast/hourly"
        hourly_data = _nws_get(hourly_url, ua)
        periods = hourly_data.get("properties", {}).get("periods", [])
        pop = None
        if periods:
            pop_field = periods[0].get("probabilityOfPrecipitation", {})
            pop = pop_field.get("value")  # percent, may be null

        # Step 5: write weather section atomically
        weather_payload = {
            "icon": icon_emoji,
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


def run_refresh(cfg: dict) -> None:
    """Entry point for the detached background fetch child (--refresh mode).

    Acquires an exclusive lockfile using O_CREAT|O_EXCL (atomic create — fails
    if the file already exists).  If the lock is already held by another fetch,
    exits immediately (no stampede — T-02-09, D2-05).

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
        # Lock acquired — run the fetch
        fetch_weather(cfg)
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
    """Spawn a detached background child to refresh the weather cache if stale.

    Checks whether the weather section needs refreshing (past its TTL or absent).
    If so, spawns a new process under the current interpreter with --refresh,
    detached (start_new_session=True, stdio=DEVNULL) so it never blocks the render.

    This is a fire-and-forget call on the RENDER PATH — it must return instantly.
    The parent render continues with the current (possibly stale) cached value.
    (D2-05 / T-02-08)
    """
    try:
        cache_cfg = cfg.get("cache", {})
        weather_ttl = float(cache_cfg.get("weather_ttl", 600))
        import time as _time
        now = _time.time()
        weather_section = cache.get("weather", {})
        # Trigger refresh when: weather section is absent OR stale past its TTL
        needs_refresh = not section_is_fresh(weather_section, ttl=weather_ttl, now=now)
        if not needs_refresh:
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
# Segment builders (each returns a string or None to omit)
# Each builder accepts thresholds forwarded from loaded config.
# ---------------------------------------------------------------------------

def _project_segment(data: dict) -> str | None:
    """[<basename of workspace.project_dir>] or None if absent/empty."""
    try:
        project_dir = data.get("workspace", {}).get("project_dir", "")
        if not project_dir:
            return None
        basename = os.path.basename(project_dir.rstrip("/"))
        if not basename:
            return None
        return f"[{basename}]"
    except Exception:
        return None


def _model_segment(data: dict, show_thinking_glyph: bool = True) -> str | None:
    """[<model.display_name> 💭?] or None if display_name absent/empty.

    When show_thinking_glyph is False the thinking glyph is suppressed (D-08).
    """
    try:
        display_name = data.get("model", {}).get("display_name", "")
        if not display_name:
            return None
        thinking_enabled = data.get("thinking", {}).get("enabled", False)
        suffix = " 💭" if (thinking_enabled and show_thinking_glyph) else ""
        return f"[{display_name}{suffix}]"
    except Exception:
        return None


def _context_segment(
    data: dict,
    warn: int | float = 70,
    crit: int | float = 90,
) -> str | None:
    """[<20-wide bar>] <pct>% colored by threshold, or None if missing (CTX-01, CTX-02, D-05)."""
    try:
        ctx = data.get("context_window", {})
        pct = pct_int(ctx.get("used_percentage"))
        if pct is None:
            return None
        # Clamp to [0, _BAR_WIDTH] so out-of-range pct (e.g. >104, or negative)
        # can never overflow/underflow the 20-char bar (CR-01).
        filled = max(0, min(_BAR_WIDTH, math.floor(pct * _BAR_WIDTH / 100)))
        empty = _BAR_WIDTH - filled
        bar_chars = _FILLED * filled + _EMPTY * empty
        color = color_for(pct, warn, crit)
        bar = f"[{color}{bar_chars}{RESET}]"
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

        if now is None:
            now = datetime.now()

        # astral LocationInfo: name/region unused; timezone="" triggers local-time computation
        loc = LocationInfo(name="", region="", timezone="UTC", latitude=lat, longitude=lon)

        # Compute sun times for today in UTC, then convert to local naive time
        today_utc = now.date()
        s_today = sun(loc.observer, date=today_utc)
        # astral returns timezone-aware datetimes; strip tz for local comparison
        sunrise_today = s_today["sunrise"].replace(tzinfo=None)
        sunset_today  = s_today["sunset"].replace(tzinfo=None)

        if now < sunrise_today:
            event_time = sunrise_today
            glyph = "\U0001f305"  # 🌅
        elif now < sunset_today:
            event_time = sunset_today
            glyph = "\U0001f307"  # 🌇
        else:
            # Past today's sunset — next event is tomorrow's sunrise
            tomorrow_utc = today_utc + timedelta(days=1)
            s_tomorrow = sun(loc.observer, date=tomorrow_utc)
            event_time = s_tomorrow["sunrise"].replace(tzinfo=None)
            glyph = "\U0001f305"  # 🌅

        # Format: "6:14am" — matches fmt_reset() format (LIM-04 / D2-10)
        time_str = event_time.strftime("%-I:%M%p").lower()
        return f"{glyph} {time_str}"
    except Exception:
        return None


def _weather_segment(data: dict | None, cfg: dict | None) -> str | None:
    """Return the bracketed weather segment or None to omit (D2-10, D2-12).

    Format (D2-10):  [<icon> <temp> | 🌧️<pop>% | <sun-or-alert>]
    For this plan (Plan 02-01), only the trailing sun detail is implemented
    (the first two chunks require NWS network fetch added in Plan 02-02).

    Returns None immediately when:
      - _WEATHER_OK is False (astral or requests import failed, D2-12)
      - cfg weather.show_weather is False
      - _sun_segment returns None and there is no other data

    Wraps entire body in try/except — never raises to caller (D-10).
    """
    try:
        if not _WEATHER_OK:
            return None
        cfg = cfg or {}
        weather_cfg = cfg.get("weather", {})
        if not weather_cfg.get("show_weather", True):
            return None

        # For Plan 02-01: build internals from sun detail only.
        # (Conditions + PoP chunks will be added in Plan 02-02 from cache.json.)
        sun_detail = _sun_segment(cfg)
        if sun_detail is None:
            # No sun detail (missing lat/lon or astral failure): omit entire segment.
            return None

        # Internals are pipe-delimited (D2-10); only one chunk for now.
        internals = sun_detail
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
# Line renderers (accept config dict forwarded from main)
# ---------------------------------------------------------------------------

def render_top_line(data: dict, cfg: dict) -> str:
    """Assemble the top line from present segments, joined by a single space.

    Phase 1: [project] [model 💭]
    Phase 2: [project] [model 💭] [<weather segment>]  (weather omitted when deps unavailable)
    """
    toggles = cfg.get("toggles", {})
    show_thinking_glyph = toggles.get("show_thinking_glyph", True)
    segments = [
        _project_segment(data),
        _model_segment(data, show_thinking_glyph=show_thinking_glyph),
        _weather_segment(data, cfg),   # None-filtered by the existing space-join (D2-10)
    ]
    present = [s for s in segments if s is not None]
    return " ".join(present)


def render_bottom_line(data: dict, cfg: dict) -> str | None:
    """Assemble the bottom line; return None if no segments are present.

    Layout (D-03): [bar] pct%   ⏳ 5h%[ reset]   🗓 wk%[ reset]
    Three spaces separate the context block, the 5h block, and the weekly block.
    Per-segment toggles from cfg suppress individual segments (D-08).
    """
    try:
        toggles    = cfg.get("toggles", {})
        thresholds = cfg.get("thresholds", {})
        warn = thresholds.get("warn", 70)
        crit = thresholds.get("crit", 90)

        ctx_seg = (
            _context_segment(data, warn=warn, crit=crit)
            if toggles.get("show_context_bar", True)
            else None
        )

        rate_limits = data.get("rate_limits", {})
        five_hour_block = rate_limits.get("five_hour", {}) if isinstance(rate_limits, dict) else {}
        seven_day_block = rate_limits.get("seven_day", {}) if isinstance(rate_limits, dict) else {}

        five_hour_seg = (
            _rate_segment(five_hour_block, "⏳", warn=warn, crit=crit)
            if (toggles.get("show_five_hour", True) and isinstance(five_hour_block, dict))
            else None
        )
        weekly_seg = (
            _rate_segment(seven_day_block, "🗓", warn=warn, crit=crit)
            if (toggles.get("show_weekly", True) and isinstance(seven_day_block, dict))
            else None
        )

        parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg] if s is not None]
        if not parts:
            return None
        return "   ".join(parts)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
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
