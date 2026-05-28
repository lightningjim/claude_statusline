# Phase 2: Weather Layer - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 7 (3 modified, 4 new conceptual modules — all may land inside the single script)
**Analogs found:** 7 / 7

## Orientation

The deliverable is a **single self-contained script** `claude-statusline.py` (currently 362 lines). The "files" below are logically-distinct modules that the planner may keep inside the one script (preferred, matching the existing structure) or split out. Either way, each maps to a concrete analog.

The single strongest analog for everything render-side is **`claude-statusline.py` itself** — its segment-builder + silent-omit + config-merge discipline is the template. The NWS network code has no in-repo analog; the closest analogs live in **`/home/kcreasey/Documents/Projects/WxDesktopPy`**, but they are **async/httpx/clean-architecture** and must be reduced to **synchronous stdlib `urllib`/`requests`** thin extractions (NOT copied wholesale).

## File Classification

| New/Modified File (or module) | Role | Data Flow | Closest Analog | Match Quality |
|-------------------------------|------|-----------|----------------|---------------|
| `_weather_segment()` in `claude-statusline.py` | segment-builder | transform / render | `_rate_segment()` + `_context_segment()` in same file (L261-285, L237-258) | exact |
| `render_top_line()` change in `claude-statusline.py` | renderer | transform | existing `render_top_line` (L291-300) | exact |
| `DEFAULTS` + `load_config` path change | config | n/a | existing `DEFAULTS` (L43-64) + `load_config` (L88-108) | exact |
| Venv self-re-exec bootstrap (top of script) | bootstrap | process-control | no in-repo analog | none (RESEARCH/discretion) |
| Sectioned JSON cache read + atomic write | utility / store | file-I/O | `install.py` `write_settings` atomic temp+`os.replace` (L67-77) | role-match |
| Detached background fetch + lockfile | service | event-driven / process-control | no in-repo analog | none (discretion D2-05) |
| NWS HTTP fetch (points→grid→station→obs/forecast) | service / source | request-response | WxDesktopPy `current_observation.py`, `hourly_forecast.py`, `stations_list.py`, `source.py` | role-match (async→sync rewrite) |
| User-Agent factory | utility | n/a | WxDesktopPy `user_agent.py` (L17-38) | exact (verbatim-ish) |
| Alert dedup + severity selection | utility | transform | WxDesktopPy `dedup.py` (L35-88) | role-match (simplify) |
| Sun-event computation (`astral`) | utility | transform | `.examples/statusline-command.sh` `sunriseset()` (L31-42) | partial (logic, not API) |
| `install.py` rewrite (subfolder + venv + pip) | config / installer | file-I/O | existing `install.py` (whole file) | role-match |
| `pyproject.toml` deps | config | n/a | existing `pyproject.toml` (L5) | exact |
| Tests for weather | test | n/a | `tests/test_config.py` (L23-46, monkeypatch+subprocess) | exact |

## Shared Patterns

### Never-crash / silent-omit discipline (apply to ALL weather code)
**Source:** `claude-statusline.py` every `_*_segment` (e.g. L217-218, L257-258, L283-284)
```python
def _project_segment(data: dict) -> str | None:
    try:
        ...
        return f"[{basename}]"
    except Exception:
        return None
```
Every weather function returns `None` (omit) on any failure. `render_top_line` already filters `None`. D2-12 layered degradation = each data type (sun / conditions / alerts) is computed independently inside its own `try/except`, so one failure never drops the others.

### ANSI color constants (apply to alert severity coloring — D2-11)
**Source:** `claude-statusline.py` L27-31
```python
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"
RESET  = "\033[0m"
```
Severity → color: Extreme/Severe → `RED`, Moderate/Minor → `YELLOW`. Wrap exactly like existing segments: `f"{color}⚠️ {event}{RESET}"`. There is already a threshold-color helper shape (`color_for`, L116-131) to mirror for a `_alert_color(severity)` helper.

### Config-driven values via deep-merge over DEFAULTS
**Source:** `claude-statusline.py` `_deep_merge` (L71-85) + `load_config` (L88-108)
```python
def load_config(path: str | None = None) -> dict:
    if path is None:
        path = os.path.expanduser("~/.claude/claude-statusline.toml")  # ← change to subfolder
    try:
        with open(path, "rb") as fh:
            parsed = tomllib.load(fh)
        return _deep_merge(DEFAULTS, parsed)
    except Exception:
        return copy.deepcopy(DEFAULTS)
```
Phase-2 keys already reserved as comments in `DEFAULTS` (L54-63) — promote them to real entries. Extra/absent keys already tolerated (proven by `test_config.py::test_phase2_lat_lon_ignored`, L135-146).

### Atomic file write (apply to cache.json — discretion in D2-12)
**Source:** `install.py` `write_settings` (L67-77)
```python
def write_settings(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)   # ← atomic; render never reads a half-written cache
```
Copy this temp-then-`os.replace` shape verbatim for `cache.json` writes in the background fetcher.

## Pattern Assignments

### `_weather_segment(data, cfg)` (segment-builder, transform)

**Analog:** `_rate_segment` (L261-285) for the colored-suffix shape; `_context_segment` (L237-258) for the config-threaded shape.

**Segment shape to copy** (L261-285):
```python
def _rate_segment(block, glyph, warn=70, crit=90) -> str | None:
    try:
        pct = pct_int(block.get("used_percentage"))
        if pct is None:
            return None
        color = color_for(pct, warn, crit)
        result = f"{glyph} {color}{pct}%{RESET}"
        if not is_green(pct, warn):
            ...
            result += f" {DIM}{reset_str}{RESET}"
        return result
    except Exception:
        return None
```
`_weather_segment` mirrors this: read cached values (NOT `data` from stdin — weather is external), assemble pipe-delimited internals `[<icon> <temp> | 🌧️<pop>% | <sun-or-alert>]`, return `None` if no data and no sun event. Precip chunk omitted when PoP absent/zero (D-09 / WX-02) — same `if x is None: skip` pattern.

**Wire into render_top_line** (L291-300) — append one entry to the `segments` list:
```python
segments = [
    _project_segment(data),
    _model_segment(data, show_thinking_glyph=show_thinking_glyph),
    _weather_segment(data, cfg),   # ← add; join logic unchanged
]
present = [s for s in segments if s is not None]
return " ".join(present)
```

**Bracketing:** the segment must return its own `[...]` wrapper (D2-10), matching `_project_segment`/`_model_segment` which return `[...]`. Internals are `|`-delimited per the bash predecessor (`.examples/statusline-command.sh` L65-67: `WX="${CC} ${TEMP#+}"; WX="${WX}|🌧️..."; WX="${WX}|$(sunriseset ...)"`).

---

### Sun-event helper (utility, transform)

**Analog:** `.examples/statusline-command.sh` `sunriseset()` (L31-42) for the selection logic; `fmt_reset` in `claude-statusline.py` (L162-184) for the local-time formatting + `%-I:%M%p` lowercase shape.

**Selection logic to port** (bash L37-39):
```bash
if   [ "$NOW" -lt "$SUNRISE" ]; then SUNBLOCK="🌅$(date --date=$1 '+%I:%M%P')"
elif [ "$NOW" -lt "$SUNSET"  ]; then SUNBLOCK="🌇$(date --date=$2 '+%I:%M%P')"
```
Reimplement with `astral` (sun times from config `[location] lat/lon`): before sunrise → `🌅 <sunrise>`, before sunset → `🌇 <sunset>`, else next day's sunrise. **No network** → always renders (D2-12 "sun event always renders").

**Time formatting to reuse** (`claude-statusline.py` L177):
```python
time_str = reset_dt.strftime("%-I:%M%p").lower()  # "6:14am"
```

---

### Cache read + atomic write (utility/store, file-I/O)

**Analog:** `install.py` `write_settings` (L67-77, see Shared Patterns) for writes; `load_config` (L101-108) for the read-with-silent-fallback shape.

**Read shape** (mirror `load_config` L101-108):
```python
try:
    with open(cache_path) as fh:
        cache = json.load(fh)
except Exception:
    cache = {}   # cold cache → sun-only render
```
Single sectioned file `cache.json` with `geo` / `weather` / `alerts`, each independently timestamped (D2-06). Staleness: compare section timestamp to `now`; show stale-OK up to `*_max_stale` ceiling, then drop to sun-only (D2-12). This is the same "floor/compare numeric, omit on None" discipline as `pct_int`/`fmt_reset`.

---

### NWS HTTP fetch (service/source, request-response)

**Analog:** WxDesktopPy `current_observation.py` (L58-71), `hourly_forecast.py` (L55-69), `stations_list.py` (L66-81), and `source.py` (points→grid at L128). **These are async/httpx — extract the URL shapes and JSON-pluck logic ONLY; rewrite synchronous.**

**Endpoint flow (the load-bearing knowledge to extract):**
- Resolve geo (cache permanently): `GET /points/{lat:.4f},{lon:.4f}` → gridpoint (`cwa`,`x`,`y`) + `observationStations` URL. (`source.py` L128.)
- Stations: `GET {observationStations URL}` → `features[*].properties.stationIdentifier`, nearest first. (`stations_list.py` L70-75.)
- Conditions (D2-08): `GET /stations/{id}/observations/latest`. (`current_observation.py` L60-65.)
- PoP (D2-08): `GET /gridpoints/{cwa}/{x},{y}/forecast/hourly`, current period. (`hourly_forecast.py` L57-60.)
- Alerts: `GET /alerts/active?point={lat:.4f},{lon:.4f}` with `Accept: application/ld+json`. (`active_alerts.py` L88-94.)

**4-decimal lat/lon discipline** (consistent across endpoints): `f"{lat:.4f},{lon:.4f}"`.

**Sync rewrite shape** (replace `await self._http.get(url)` with stdlib/`requests`, e.g.):
```python
req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/ld+json"})
with urllib.request.urlopen(req, timeout=10) as r:
    payload = json.load(r)
```
Runs ONLY in the detached background child, never the render path (D2-05).

---

### User-Agent factory (utility)

**Analog:** WxDesktopPy `user_agent.py` (L17-38) — extract near-verbatim.
```python
def make_user_agent(version: str, contact_email: str) -> str:
    return f"claude-statusline/{version} ({contact_email})"
```
**Load-bearing ToS requirement:** `api.weather.gov` returns **403 without a User-Agent** identifying the app + a contact email. This header is mandatory on every NWS request.

---

### Alert dedup + severity selection (utility, transform)

**Analog:** WxDesktopPy `dedup.py` (L35-88). Extract the algorithm, simplify (no `Alert` dataclass / pint / logging framework needed).

**Algorithm to port** (dedup.py L70-88):
1. Build `superseded` set: every identifier in any alert's `references`, PLUS any alert whose `msg_type` ∈ `{"Cancel","Ack","Error"}` (L32, L74-78).
2. Drop expired (`expires < now`).
3. Sort remaining by `sent` descending.

**Severity fields** (from `parsers.py` L484-490): `properties.event`, `properties.severity` (`"Extreme"/"Severe"/"Moderate"/"Minor"/"Unknown"`), `properties.messageType`, `properties.references`, `properties.expires`, `properties.sent`.

**D2-11 selection:** after dedup, pick highest-severity alert → render `⚠️ <event>` severity-colored, with `+N` suffix for remaining count. Severity rank: Extreme > Severe > Moderate > Minor > Unknown.

---

### Venv self-re-exec bootstrap (bootstrap, process-control)

**Analog:** none in repo. Pattern per D2-03 (discretion). Shape:
```python
# top of script, before heavy imports
import os, sys
_VENV_PY = os.path.expanduser("~/.claude/claude-statusline/.venv/bin/python")
if sys.executable != _VENV_PY and os.path.exists(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY, __file__, *sys.argv[1:]])
```
Guard with `os.path.exists` (D2-03/D2-12) so a missing venv never hard-fails the bar — falls through to whatever `python3` invoked it; weather imports then guarded so segment omits cleanly.

**Import guard for deps** (extends silent-omit to whole segment, D2-12):
```python
try:
    import requests   # or astral
    _WEATHER_OK = True
except Exception:
    _WEATHER_OK = False
```
`_weather_segment` returns `None` immediately when `_WEATHER_OK` is False — Phase-1 bar renders untouched.

---

### `install.py` rewrite (installer, file-I/O)

**Analog:** existing `install.py` (whole file). Keep: parse-merge-backup of `settings.json` (L103-129), atomic `write_settings` (L67-77), idempotent statusLine entry (L80-85, L123-128), `os.makedirs(..., exist_ok=True)` (L98).

**Changes (D2-02/D2-04):**
- New install root `~/.claude/claude-statusline/` (subfolder) instead of flat `~/.claude/` (current L37-42 constants).
- Add: build `.venv` (`python -m venv`), `pip install requests astral` into it, copy script + default `.toml` config into the subfolder.
- `build_status_line_entry` command stays `python3 <script>` (D2-03 — script re-execs itself into venv; settings.json needs no venv path). Update path to the subfolder script.

---

### `pyproject.toml` (config)

**Analog:** existing `pyproject.toml` L5 (`dependencies = []`). Change to:
```toml
dependencies = ["requests", "astral"]
```

---

### Weather tests (test)

**Analog:** `tests/test_config.py` — `_load_script_module` (L23-28, importlib import without running main), `run_script` (L31-40, subprocess + env override), temp-TOML + backup-real-config harness (L276-294).

**Reuse:**
- Import-as-module to unit-test pure helpers (`_alert_color`, sun selection, dedup) without spawning.
- Subprocess + fixture to assert the bar still renders 2 lines under cold cache / missing venv / import failure (mirror `test_fixture_renders_two_lines_no_config` L220-228 and `assertNotIn("Traceback", ...)` L256).
- Provide a cache.json fixture (and a fake-alerts fixture, cf. WxDesktopPy `WXD_FAKE_ALERTS_FILE` env trigger, `active_alerts.py` L71-86) to drive deterministic weather render tests offline.

## No Analog Found

| Module | Role | Data Flow | Reason / Source to use instead |
|--------|------|-----------|-------------------------------|
| Detached fire-and-forget spawn + lockfile | service | process-control | No in-repo analog. D2-05 (discretion): `subprocess.Popen` detached stdio or double-fork; lockfile via `O_CREAT|O_EXCL` or `flock`. Parent must return immediately. |
| Venv self-re-exec | bootstrap | process-control | No in-repo analog. D2-03 `os.execv` pattern above. |
| `astral` sun computation | utility | transform | Library is new; only the bash `sunriseset` selection *logic* is an analog, not the API. |

## Metadata

**Analog search scope:**
- In-repo: `claude-statusline.py`, `install.py`, `.examples/statusline-command.sh`, `pyproject.toml`, `tests/`
- Reference: `/home/kcreasey/Documents/Projects/WxDesktopPy/src/wx_desktop_py/infrastructure/http/` and `.../sources/nws/`, `.../application/alerts/dedup.py`
**Files scanned:** ~14
**Pattern extraction date:** 2026-05-28
