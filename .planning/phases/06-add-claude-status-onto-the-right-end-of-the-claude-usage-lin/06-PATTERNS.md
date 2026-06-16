# Phase 6: Add Claude Status onto the right end of the Claude usage line - Pattern Map

**Mapped:** 2026-06-16
**Files analyzed:** 1 source file (`claude-statusline.py`) + 1 test file (`tests/test_claude_status.py`, new)
**Analogs found:** 10 / 10 code units (single-file project — every analog lives in `claude-statusline.py`)

> This is a single-file Python project. There is NO `src/` tree. All new code is
> added to `/home/kcreasey/Documents/Projects/claude_statusline/claude-statusline.py`
> and one new test file under `tests/`. "File" below means a **code unit** (function /
> constant block / config block) inside that one module.

## File Classification

| New / Modified Code Unit | Role | Data Flow | Closest Analog (file:line) | Match Quality |
|--------------------------|------|-----------|----------------------------|---------------|
| `_claude_status_segment(data, cfg)` (NEW) | segment-builder (render-path) | request-response / read-cache | `_rate_segment` (`claude-statusline.py:2640`); structure/cache-read from `_weather_segment` alert override (`:2582-2620`) | role-match + flow-match |
| `fetch_claude_status(cfg)` (NEW) | service / fetch (detached) | file-I/O write + HTTP GET | `fetch_alerts` (`claude-statusline.py:1270`) | exact |
| `run_refresh(cfg)` (MODIFY — add status fetch) | service orchestrator (detached) | event-driven (lock + batch fetch) | `run_refresh` (`claude-statusline.py:1333`) | self (extend) |
| `maybe_spawn_refresh(cfg, cache)` (MODIFY — add status staleness check) | spawn / fire-and-forget | event-driven | `maybe_spawn_refresh` (`claude-statusline.py:1376`) | self (extend) |
| `render_bottom_line(data, cfg)` (MODIFY — append segment) | line-renderer | transform / assembly | `render_bottom_line` (`claude-statusline.py:2698`) | self (extend) |
| `DEFAULTS["cache"]` status TTL key (MODIFY) | config | n/a | `DEFAULTS["cache"]` (`claude-statusline.py:151`) | self (extend) |
| `DEFAULTS["display"].show_claude_status` toggle (MODIFY) | config | n/a | `DEFAULTS["display"].show_gsd` (`claude-statusline.py:180`) | exact |
| `_claude_status_color(...)` / severity→ANSI (NEW) | utility | transform | `_alert_color` (`claude-statusline.py:1172`) + `color_for` (`:1420`) | role-match |
| status glyph constants `_NF_CLAUDE_*` (NEW) | config / constants | n/a | `_NF_GSD_*` (`claude-statusline.py:441-456`) | exact |
| incident-title sanitization (NEW, inline) | security / utility | transform | inline sanitizer in `_weather_segment` (`:2604-2612`) + `_sanitize_label` (`:1578`) | exact |
| `tests/test_claude_status.py` (NEW) | test | n/a | `tests/test_weather_alerts.py` | exact |

---

## Pattern Assignments

### `fetch_claude_status(cfg)` — NEW service fetch (detached child only)

**Analog:** `fetch_alerts` (`claude-statusline.py:1270-1330`)

Copy the exact shape: whole body in `try/except: pass` (D-10 never-crash), optional
env-var fake-fixture override for offline tests, live HTTP GET via the shared client,
then `write_cache_section(...)` for a **new `"claude_status"` section**.

**HTTP GET helper to reuse** (`claude-statusline.py:804-817`) — same single-GET pattern, raise-on-error, caller wraps:
```python
def _nws_get(url: str, ua: str, accept: str | None = None) -> dict:
    headers = {"User-Agent": ua}
    if accept:
        headers["Accept"] = accept
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
```
> NOTE for planner: `status.claude.com/api/v2/summary.json` is plain JSON (no
> `application/ld+json`). Reuse `_nws_get` as-is with `accept=None` (it is generic
> despite the NWS name), OR add a tiny `_http_get_json` alias — planner discretion.
> `requests` is already imported (used by the weather layer). User-Agent comes from
> `make_user_agent(_APP_VERSION, contact_email)` (`:777`) — the descriptive-UA pattern.

**Fake-fixture override pattern to copy** (`claude-statusline.py:1300-1318`):
```python
fake_path = os.environ.get("CLAUDE_STATUSLINE_FAKE_ALERTS")
if fake_path:
    try:
        with open(fake_path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return  # bad fake file: leave cache unchanged
    graph = payload.get("@graph", payload.get("features", []))
else:
    url = (...)
    payload = _nws_get(url, ua, accept="application/ld+json")
```
> Mirror this with `CLAUDE_STATUSLINE_FAKE_STATUS` for the status fixture (UAT/offline).

**Cache-write pattern to copy** (`claude-statusline.py:1326`):
```python
write_cache_section(_CACHE_PATH, "alerts", {"active": survivors}, now)
```
> New call: `write_cache_section(_CACHE_PATH, "claude_status", {<derived fields>}, now)`.
> Store the **derived trigger result** (chosen glyph-class/severity + sanitized label +
> maintenance flag) OR the raw filtered components/incidents — planner discretion per
> D-03/CONTEXT discretion. Prefer storing minimal derived fields so the render path
> stays cheap, matching how `weather` stores raw tokens and `alerts` stores survivors.

---

### `run_refresh(cfg)` — MODIFY: add the status fetch under the existing lock

**Analog / target:** `run_refresh` (`claude-statusline.py:1333-1373`)

Add `fetch_claude_status(cfg)` alongside the existing two fetches, under the same
single exclusive lock (no new lock / no new process — D-05, D2-16):
```python
        # Lock acquired — run both fetches under the single lock (D2-16)
        fetch_weather(cfg)
        fetch_alerts(cfg)
        # <-- ADD: fetch_claude_status(cfg)   (same lock, swallow-on-error)
```
The lock acquire (`os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`,
`:1354`) and `finally`-unlink (`:1363-1373`) are unchanged.

---

### `maybe_spawn_refresh(cfg, cache)` — MODIFY: add status staleness to the trigger

**Analog / target:** `maybe_spawn_refresh` (`claude-statusline.py:1376-1412`)

Add a third staleness check (`status_stale`) using a new `status_ttl` (~300s, D-05),
OR'd into the existing spawn condition. Detached-spawn block stays identical:
```python
        weather_stale = not section_is_fresh(weather_section, ttl=weather_ttl, now=now)
        alerts_stale = not section_is_fresh(alerts_section, ttl=alerts_ttl, now=now)
        # <-- ADD: status_section = cache.get("claude_status", {})
        # <-- ADD: status_stale = not section_is_fresh(status_section, ttl=status_ttl, now=now)
        if not (weather_stale or alerts_stale):   # <-- ADD `or status_stale`
            return
        subprocess.Popen(
            [sys.executable, __file__, "--refresh"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
```
> `--refresh` branch in `main()` (`:2767-2770`) already calls `run_refresh(cfg)` — no
> change needed there; the new fetch rides the existing detached child.

**Cache read on render path** (already wired in `_weather_segment`, `:2493-2499`):
```python
cache = read_cache(_CACHE_PATH)
...
maybe_spawn_refresh(cfg, cache)
```
> The status segment can read the same cache: `read_cache(_CACHE_PATH)` then
> `cache.get("claude_status", {})`, gated by `section_within_ceiling(...)` (`:318`) /
> `section_is_fresh(...)` (`:305`) exactly like weather/alerts.

---

### `_claude_status_segment(data, cfg)` — NEW render-path segment builder

**Analog (shape):** `_rate_segment` (`claude-statusline.py:2640-2663`) — minimal builder, `str | None`, body in `try/except: return None`:
```python
def _rate_segment(block, glyph, warn=70, crit=90) -> str | None:
    try:
        pct = pct_int(block.get("used_percentage"))
        if pct is None:
            return None
        color = color_for(pct, warn, crit)
        pct_str = f"{color}{pct}%{RESET}"
        result = f"{glyph} {pct_str}"
        ...
        return result
    except Exception:
        return None
```

**Analog (toggle + project gating + cache read):** `_gsd_segment` (`claude-statusline.py:1928-1953`):
```python
    try:
        if not cfg.get("display", {}).get("show_gsd", True):   # toggle → mirror with show_claude_status
            return None
        ...
        state = _read_gsd_state(planning_dir)
        if state is None:
            return None
        icon_set = cfg.get("display", {}).get("icon_set", "nerd")
        if icon_set == "nerd":
            exec_glyph = _NF_GSD_EXECUTING
            ...
```

**Analog (severity-coloring + sanitized untrusted label — the D-03 core):**
`_weather_segment` alert-override block (`claude-statusline.py:2582-2619`). Copy verbatim:
```python
        color = _alert_color(best)                       # → _claude_status_color(...)
        best_class = _classify_alert_class(best)         # → derive severity class from feed
        if icon_set == "nerd":
            class_glyph = _ALERT_CLASS_GLYPHS_NERD.get(best_class, _WI_ALERT_STATEMENT)
        else:
            class_glyph = _ALERT_CLASS_GLYPHS_EMOJI.get(best_class, "ℹ️")
        # Sanitize event text — strip ESC/control seqs, truncate, trim (T-02.2-04)
        safe_event = "".join(
            ch for ch in str(event)
            if ch == " " or (ch.isprintable() and ch != "\x1b")
        )[:64].strip()
        # D-10: never emit a hollow glyph — fall back to class name when empty (WR-02)
        if not safe_event:
            safe_event = best_class
        detail = f"{class_glyph} {safe_event}"
        trailing_detail = f"{color}{detail}{RESET}"
```
> Map: `event` → incident **title**; `safe_event` → sanitized incident title (D-03,
> T-02.2-04/05/06). The hollow-glyph fallback maps directly to D-03's "component +
> state" fallback (`Claude Code: degraded`) when there is no incident title.
> The truncation width `[:64]` is the established bound (or reuse `_sanitize_label`
> with its own `maxlen` — `:1578`); pick the width budget per CONTEXT discretion.

**Builder logic to implement (derivation — planner discretion per D-02/D-04):**
1. `if not cfg.get("display", {}).get("show_claude_status", True): return None`
2. `cache = read_cache(_CACHE_PATH)`; `sec = cache.get("claude_status", {})`;
   `if not section_within_ceiling(sec, max_stale=..., now=...): return None` (cold cache → silent, D-01).
3. Derive trigger from **tracked components only** (Claude Code / claude.ai / Claude
   Cowork — D-02). All operational AND no relevant incident AND no relevant
   maintenance → `return None` (quiet-when-healthy, D-01).
4. Incident present → severity-colored glyph + sanitized incident title (D-03).
   Degraded-no-title → `component + state` fallback. Maintenance → distinct neutral
   glyph, no severity color (D-04).

---

### `_claude_status_color(...)` — NEW severity → ANSI

**Analog:** `_alert_color` (`claude-statusline.py:1172-1204`) — hue-map + `try/except → safe default`:
```python
    try:
        cls = _classify_alert_class(alert)
        hue_map = {"Warning": RED, "Watch": YELLOW, "Advisory": CYAN,
                   "Statement/Other": DEFAULT_FG}
        hue = hue_map.get(cls, YELLOW)
        return f"{intensity}{hue}"
    except Exception:
        return YELLOW
```
**Band constants** (`claude-statusline.py:77-92`): `GREEN`/`YELLOW`/`RED`/`RESET`/`DIM`/`DEFAULT_FG`,
plus semantic hues `CYAN`/`MAGENTA`/`GRAY`. Map status `indicator`:
`none`→(silent), `minor`→YELLOW, `major`→RED (or an "orange" tier — discretion; note
the file has no 256-color orange constant yet, so planner adds one or uses RED),
`critical`→RED+BOLD. Maintenance → neutral (`DIM`/`DEFAULT_FG`, D-04).
> `color_for(pct, warn, crit)` (`:1420`) is the usage-threshold band fn — NOT applicable
> to status severity; do not route status through `color_for`. Build a small status
> hue-map like `_alert_color` instead.

---

### Status glyph constants `_NF_CLAUDE_*` — NEW

**Analog:** `_NF_GSD_*` block (`claude-statusline.py:441-456`) — one constant per state, with NF codepoint + intent comment:
```python
_NF_GSD_EXECUTING = ""   # nf-fa-play          U+F04B  (green: actively running)
_NF_GSD_VERIFYING = ""   # nf-fa-check_square  U+F046  (yellow: verification step)
_NF_GSD_BLOCKED   = ""   # nf-fa-ban           U+F05E  (red: blocked)
...
```
> Add `_NF_CLAUDE_INCIDENT` (severity glyph) + `_NF_CLAUDE_MAINT` (neutral/info glyph).
> Resolve via the standard `icon_set == "nerd"` branch with emoji/ascii fallbacks
> (see `_gsd_segment` `:1953`). Reuse existing `_ALERT_CLASS_GLYPHS_NERD/EMOJI`
> machinery as the pattern reference if a severity-keyed glyph map is wanted.

---

### `DEFAULTS` config — MODIFY

**Toggle analog** (`claude-statusline.py:173-181`):
```python
        "show_git": True,
        "show_gsd": True,
        # <-- ADD: "show_claude_status": True,  # Phase 06: Claude service-health segment
```
**TTL analog** (`claude-statusline.py:150-156`):
```python
    "cache": {
        "weather_ttl":        600,
        "alerts_ttl":         300,
        "weather_max_stale":  3600,
        "alerts_max_stale":   900,
        # <-- ADD: "status_ttl": 300, "status_max_stale": 900,   # Phase 06 (D-05)
    },
```
**`_deep_merge`** (`claude-statusline.py:189-203`) is unchanged — it already accepts/merges
new keys recursively, so the new toggle/TTL keys flow through with zero loader changes.

---

### `render_bottom_line(data, cfg)` — MODIFY: append after weekly

**Target:** `claude-statusline.py:2698-2752`. Current assembly (`:2741-2750`):
```python
        weekly_seg = (
            _rate_segment(seven_day_block, _glyph_wk, warn=warn, crit=crit)
            if (toggles.get("show_weekly", True) and isinstance(seven_day_block, dict))
            else None
        )

        parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg] if s is not None]
        if not parts:
            return None
        return "   ".join(parts)
```
**Change:** build `status_seg = _claude_status_segment(data, cfg)` and append it to the
`parts` list **after `weekly_seg`** (D-06):
```python
        status_seg = _claude_status_segment(data, cfg)
        parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]
```
The `"   ".join(parts)` (3-space separator, D-06) and the `None`-filter handle the
silent-omit case automatically — no extra guarding needed.

---

## Shared Patterns

### Never-crash discipline (D-10)
**Source:** every builder/fetch — `_rate_segment` (`:2647`), `fetch_alerts` (`:1289/1328`), `render_bottom_line` (`:2705/2751`).
**Apply to:** all new code units.
```python
    try:
        ...
    except Exception:
        return None   # (or `pass` for fetch/refresh writers)
```

### Sectioned temp-file cache (atomic write, silent read)
**Source:** `write_cache_section` (`:273-302`), `read_cache` (`:256-270`), `section_is_fresh` (`:305-315`), `section_within_ceiling` (`:318-329`).
**Apply to:** `fetch_claude_status` (write `"claude_status"` section), `_claude_status_segment` (read + freshness gate).
```python
write_cache_section(_CACHE_PATH, "claude_status", {<payload>}, now)   # atomic temp+os.replace
...
if not section_within_ceiling(sec, max_stale=status_max_stale, now=now):
    return None
```

### Untrusted-text sanitization (ANSI-strip + width-bound) — T-02.2-04/05/06
**Source:** inline sanitizer `_weather_segment` (`:2604-2612`); standalone `_sanitize_label` (`:1578-1593`).
**Apply to:** incident-title label (D-03).
```python
safe = "".join(ch for ch in str(text) if ch == " " or (ch.isprintable() and ch != "\x1b"))[:maxlen].strip()
if not safe:
    safe = <fallback label>   # never emit a hollow glyph (WR-02 / D-03 fallback)
```

### icon_set glyph resolution (nerd default, emoji/ascii fallback) — D-07
**Source:** `_gsd_segment` (`:1953`), `_git_segment` (`:2217`), `render_bottom_line` (`:2728`).
**Apply to:** status glyph selection.
```python
icon_set = cfg.get("display", {}).get("icon_set", "nerd")
if icon_set == "nerd":
    glyph = _NF_CLAUDE_INCIDENT
else:
    glyph = "🔴"   # emoji fallback
```

### Detached-refresh contract (render never blocks on network)
**Source:** `run_refresh` (`:1333`) + `maybe_spawn_refresh` (`:1376`) + `main` `--refresh` branch (`:2767`).
**Apply to:** status fetch rides the existing single detached child + single lock; render only reads cache.

### Descriptive User-Agent for HTTP
**Source:** `make_user_agent` (`:777-783`) — `claude-statusline/<version> (<email>)`; `_APP_VERSION = "0.2.0"` (`:346`).
**Apply to:** `fetch_claude_status` GET. (Statuspage.io has no UA mandate, but reuse for
consistency / good-citizen requests. The WxDesktopPy `infrastructure/http` UA pattern
in CONTEXT is the same idea already realized here — prefer the in-repo `make_user_agent`.)

### Test structure
**Source:** `tests/test_weather_alerts.py` — `importlib`-loads `claude-statusline.py` as a
module (`_load_script_module`, lines ~38-42), `_load_fixture(name)` from `tests/fixtures/`,
`unittest.TestCase`, `unittest.mock.patch` for the fetch.
**Apply to:** new `tests/test_claude_status.py`. Add a `tests/fixtures/status_*.json`
Statuspage `summary.json` fixture set and drive `fetch_claude_status` via
`CLAUDE_STATUSLINE_FAKE_STATUS` (mirrors `CLAUDE_STATUSLINE_FAKE_ALERTS`). Cases
(from CONTEXT integration notes): operational→silent, tracked-component incident→glyph+title,
untracked-component incident→silent, degraded-no-title→component+state fallback,
active/upcoming maintenance→neutral glyph, cold-cache/no-network→silent.

---

## No Analog Found

| Code Unit | Role | Data Flow | Reason |
|-----------|------|-----------|--------|
| (none) | — | — | Every new unit has a direct in-repo analog; the weather/alert layer is a near-exact mechanical template. |

> Two minor gaps the planner must close (no blocker — extend existing patterns):
> 1. **No "orange"/256-color constant** exists for a distinct `major` tier (`:77-92` has
>    only 8/16-color + bright-black GRAY). Planner adds one or folds `major` into RED.
> 2. **No generic JSON GET name** — `_nws_get` (`:804`) is NWS-named but generic; reuse
>    as-is or add a thin `_http_get_json` alias (discretion).

---

## Metadata

**Analog search scope:** `/home/kcreasey/Documents/Projects/claude_statusline/claude-statusline.py` (2783 lines), `tests/`.
**Files scanned:** 1 source module + test directory listing + 1 test file head.
**Key regions read:** constants/`DEFAULTS`/`_deep_merge`/cache helpers (77-329), fetch layer
+ UA (777-817, 820, 1270-1330), alert color/select/sanitize (1135-1204, 1578-1593),
refresh/spawn (1333-1412), `color_for` (1420-1435), glyph constants (346-456),
`_gsd_segment` (1909-1958), `_rate_segment`/render lines (2640-2752, 2759-2779),
weather-segment alert override (2490-2619).
**Pattern extraction date:** 2026-06-16
