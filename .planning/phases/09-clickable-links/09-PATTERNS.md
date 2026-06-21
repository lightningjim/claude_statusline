# Phase 9: Clickable Links (OSC 8 hyperlinks) - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 7 code units (all in the single file `claude-statusline.py`)
**Analogs found:** 7 / 7 (all in-file; this is a single-file project)

> Single-file project. Every "file" below is a code unit (constant block / helper / dict
> entry / render site) inside `claude-statusline.py`. No new files are created. All line
> numbers are from the current `claude-statusline.py` (4224 lines) and supersede the
> approximate numbers in `09-CONTEXT.md` (which had drifted).

## File Classification

| Code unit (new/modified) | Role | Data Flow | Closest Analog | Match Quality |
|--------------------------|------|-----------|----------------|---------------|
| `osc8(text, url, *, enabled)` helper (NEW) | utility (pure string fmt) | transform | ANSI constant block L77-84 + `_bar_preset` L114-124 / `fmt_reset` L2537-2559 | role-match (pure fmt) |
| OSC 8 byte constants (NEW, optional) | config (module constants) | n/a | ANSI constant block L77-84 | exact |
| `auto`-mode terminal capability detection (NEW) | utility (env detection) | transform | `os.environ.get(...)` reads L2126, L2249; `icon_set` resolve L3675/L4003 | role-match |
| `links` tri-state config key (MODIFY `DEFAULTS`) | config | n/a | `DEFAULTS` dict L131-196 + `claude_status` hand-edit block L189-195 + `_deep_merge` L203-217 | exact |
| URL-component validation (`{id}`, `{UGC}`) (NEW) | utility (sanitize/validate) | transform | `_sanitize` L532-536; event sanitizer L3776-3779; label sanitizer L4036-4039 | exact |
| Weather render-site OSC 8 wrap (MODIFY `_weather_segment` Step 3c) | render site | request-response | self: alert-override block L3753-3800 (color wrap L3800) | exact (in-place) |
| Status render-site OSC 8 wrap (MODIFY `_claude_status_segment`) | render site | request-response | self: assembly + return L4044-4052 | exact (in-place) |
| Read `geocode.UGC` + incident `id` at render time | data read | transform | `props = best.get("properties") or best` L3763; `incident_id`/`tracked_incidents` reads L3937/L3918/L3974 | exact |

## Pattern Assignments

### 1. `osc8(text, url, *, enabled) -> str` — NEW pure helper (utility, transform)

**Analog A — ANSI constant block** (`claude-statusline.py` L77-84): the project defines escape
sequences as raw `"\033[..."` string literals. **There is NO existing `ESC` / `BOLD` / `RESET`
*object* named `ESC` — those are the literals below.** Define OSC 8 byte constants in the same
place, the same way:

```python
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"    # dim/neutral — used for reset times (D-04)
BOLD   = "\033[1m"    # bold/bright — used for Immediate+Observed alert intensity (D-06)
RESET  = "\033[0m"
DEFAULT_FG = "\033[39m"  # default foreground only ...
```

New constants to add alongside (use `\033` to match the file's existing escape idiom — do
NOT introduce a new `ESC`/`\x1b` spelling; the file uses octal `\033` everywhere):

```python
# OSC 8 hyperlink (Phase 9) — ESC ] 8 ; ; <url> ST ... ESC ] 8 ; ; ST  (ST = ESC \)
_OSC8_OPEN_PRE  = "\033]8;;"   # before the URL
_OSC8_ST        = "\033\\"     # ST terminator (ESC backslash)
_OSC8_CLOSE     = "\033]8;;\033\\"  # empty-URL close
```

**Analog B — pure, never-raises formatting helper** `_bar_preset` (L114-124) and `fmt_reset`
(L2537-2559). Both are the model for "small pure function, total, returns a safe default on
bad input." `osc8()` follows the same shape: pure, takes its inputs, returns plain `text`
unchanged on the disabled/bad path (the omit-not-fake guarantee lives here):

```python
def _bar_preset(style: object) -> tuple[str, str]:
    if not isinstance(style, str):
        return _BAR_PRESETS["shade"]
    return _BAR_PRESETS.get(style, _BAR_PRESETS["shade"])
```

```python
def fmt_reset(epoch) -> str | None:
    if epoch is None:
        return None
    try:
        ...
    except (OSError, OverflowError, ValueError, TypeError):
        return None
```

**Pattern for `osc8`:** when `enabled` is falsy OR `url` is empty/None → `return text` (byte-for-byte
unchanged, the LINK-03 bar). Otherwise wrap: `f"{_OSC8_OPEN_PRE}{url}{_OSC8_ST}{text}{_OSC8_CLOSE}"`.
The SGR `{color}{detail}{RESET}` wrap (L3800/L4052) composes *inside* the OSC 8 span per D-06.

---

### 2. `auto`-mode terminal capability detection — NEW (utility, env transform)

**Analog A — env-var reads** (`claude-statusline.py` L2126, L2249). The codebase's established
idiom for reading the environment is `os.environ.get(NAME)` with a falsy-guard:

```python
# L2126 (fetch_alerts)
fake_path = os.environ.get("CLAUDE_STATUSLINE_FAKE_ALERTS")
if fake_path:
    ...
```
```python
# L2249 (fetch_claude_status)
fake_path = os.environ.get("CLAUDE_STATUSLINE_FAKE_STATUS")
```

`os` is already imported at module top. New detection reads `TERM_PROGRAM`, `WT_SESSION`,
`TERMINAL_EMULATOR`, `KITTY_WINDOW_ID`, `VTE_VERSION`, etc. via the same `os.environ.get` calls.

**Analog B — render-time config resolution** `icon_set` (L3675, L4003): the convention for
"resolve a display option at render time so a toggle takes effect on the next render" —

```python
# L3674-3675 (_weather_segment)
display = cfg.get("display", {})
icon_set = display.get("icon_set", "nerd")
```
```python
# L4003 (_claude_status_segment)
icon_set = _cfg.get("display", {}).get("icon_set", "nerd")
```

**Pattern:** a pure `_osc8_enabled(cfg) -> bool` that reads the `links` config value (off/auto/on),
and for `auto` consults a conservative allowlist against `os.environ.get(...)` markers. Bias to
False on unknown (D-02). Resolve once per render call, pass the bool as `enabled=` into `osc8()`.

---

### 3. `links` tri-state config key — MODIFY `DEFAULTS` (config)

**Analog — `DEFAULTS` dict + Phase-07 hand-edit block** (`claude-statusline.py` L131-196). The
`claude_status` sub-table (L189-195) is the exact precedent for a hand-edited-TOML-only key with
a doc comment; it merges via `_deep_merge` (L203-217). Add a `display.links` (or a top-level
`links`) string key with default `"off"` in the same dict:

```python
# L189-195 — the Phase-07 precedent: hand-edited-only table, default-bearing, merged via _deep_merge
    "claude_status": {
        "filter_enabled": True,            # master toggle for the suppression filter
        "ignore_title_patterns": [],       # title patterns (e.g. "Mythos", "Fable")
    },
```

```python
# _deep_merge (L211-217) — a hand-edited TOML value overrides the default key
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
```

**Pattern:** add `"links": "off"` (default off, opt-in posture per D-01). Place it in `display`
to match `icon_set`/`bar_style`/`show_*` siblings (L170-187), or as a new top-level table. Read
it the same way `icon_set` is read (L3675). Validate the value to the {off,auto,on} set at read
time and fall back to `"off"` on anything unexpected (mirror `_bar_preset`'s unknown→default).

---

### 4. URL-component validation (`{id}`, `{UGC}`) — NEW (utility, sanitize/validate)

**Analog A — `_sanitize` (the canonical strip helper)** (`claude-statusline.py` L532-536):

```python
def _sanitize(s: str, maxlen: int = _CLAUDE_STATUS_LABEL_MAXLEN) -> str:
    return "".join(
        ch for ch in str(s)
        if ch == " " or (ch.isprintable() and ch != "\x1b")
    )[:maxlen].strip()
```

**Analog B — the inline event sanitizer in the weather alert block** (L3776-3779), and the
**identical label sanitizer** in the status segment (L4036-4039). This char-filter is the
established defensive posture for network-sourced strings:

```python
# L3776-3779 (weather event)
safe_event = "".join(
    ch for ch in str(event)
    if ch == " " or (ch.isprintable() and ch != "\x1b")
)[:64].strip()
```
```python
# L4036-4039 (status label) — VERBATIM copy of the same idiom (see its own L4035 comment)
safe_label = "".join(
    ch for ch in str(label)
    if ch == " " or (ch.isprintable() and ch != "\x1b")
)[:_CLAUDE_STATUS_LABEL_MAXLEN].strip()
```

**Pattern (security, D-04 specifics):** the URL component validators are *stricter* than the
display sanitizers above — they must allowlist-match, not just strip. Per CONTEXT security note:
- incident `id` → Statuspage hex/alnum allowlist (e.g. `^[0-9a-z]+$`); reject otherwise.
- `UGC` → `^[A-Z]{2}[CZ][0-9]{3}$` (forecast-zone `Z` preferred per D-05, county `C` fallback).
- On non-match → return None / signal "no link" so the call site falls back to plain text
  (omit-not-fake, D-10) — same return-None-on-bad-data contract as `fmt_reset` (L2547/L2558).
Note the display sanitizers exclude only `\x1b`; the URL validators must additionally reject the
ST byte and all control chars (the OSC 8 breakout vector) — hence allowlist, not denylist.

---

### 5. Weather render-site OSC 8 wrap — MODIFY `_weather_segment` Step 3c (render, request-response)

**Analog = the block itself** (`claude-statusline.py` L3753-3800). `_weather_segment(data, cfg)`
signature at L3612 — `cfg` is in scope, so resolve the toggle here. Key lines:

```python
# L3763 — raw NWS feature is already in scope; geocode.UGC lives under props (see unit 7)
props = best.get("properties") or best
...
# L3784 — detail starts: glyph + event
detail = f"{class_glyph} {safe_event}"
...
# L3790-3792 — timing fragment appended → this is the END of the clickable span (D-06)
timing_fragment = _fmt_alert_timing(start_raw, end_raw)
if timing_fragment:
    detail += f" · {timing_fragment}"
# L3796-3799 — tally appended AFTER → MUST stay OUTSIDE the link (D-06)
if remaining_alerts:
    tally = _build_alert_tally(remaining_alerts, icon_set)
    if tally:
        detail += f"  {tally}"
# L3800 — single canonical color wrap (Phase-8 D-01)
trailing_detail = f"{color}{detail}{RESET}"
```

**Pattern (D-06):** after L3792 (timing appended) and BEFORE L3796 (tally appended), wrap the
glyph+event+timing portion. The OSC 8 wrap must compose with the SGR color wrap (SGR is legal
inside an OSC 8 span). Suggested shape:
```
linkable = osc8(f"{color}{glyph_event_timing}{RESET}", url, enabled=...)
trailing_detail = linkable + (f"  {tally}" if tally else "")
```
where `url = f"https://api.weather.gov/alerts/active?zone={ugc}"` only if `ugc` validated
(unit 4 + unit 7); on no-url, `osc8` returns the text unchanged → plain, no escapes. The whole
block is inside `try/except → pass` (L3801-3802) falling back to `_sun_segment`, so any failure
degrades to plain/sun (omit-not-fake).

---

### 6. Status render-site OSC 8 wrap — MODIFY `_claude_status_segment` (render, request-response)

**Analog = the assembly + return** (`claude-statusline.py` L4044-4052). `_claude_status_segment(data, cfg)`
at L3857 — `_cfg` (the dict-guarded cfg) is in scope:

```python
# L4048-4052 — final assembly + the single return
if kind == "resolved" or severity == "resolved":
    detail = f"{glyph} resolved: {safe_label}"
else:
    detail = f"{glyph} {safe_label}"
return f"{color}{detail}{RESET}"
```

**Pattern (D-07):** wrap the WHOLE returned segment. Compute `url =
f"https://status.claude.com/incidents/{inc_id}"` only when a validated incident id is available
(unit 4 + unit 7), then:
```python
return osc8(f"{color}{detail}{RESET}", url, enabled=...)
```
On missing/invalid id → no url → `osc8` returns the colored text unchanged (D-03a omit-not-fake;
do NOT substitute the homepage). Entire function is inside `try/except → return None` (L4054-4055).

---

### 7. Read `geocode.UGC` + incident `id` at render time — NEW reads (data read, transform)

**Weather `geocode.UGC` analog** (`claude-statusline.py` L3763): the raw NWS feature is already
cached and `props` already exposes CAP fields at render time — no fetch change needed (D-05 note):

```python
props = best.get("properties") or best   # L3763
# UGC lives at props["geocode"]["UGC"] — a list of zone/county codes
```
**Pattern:** `geocode = props.get("geocode") or {}; ugc_list = geocode.get("UGC") or []`, then
pick the first code matching `^[A-Z]{2}Z[0-9]{3}$`, else first `^[A-Z]{2}C[0-9]{3}$`, else None
(D-05 fallback chain). Guard with the same defensive `.get(...) or default` idiom used throughout.

**Status incident `id` analogs** — the id is read in three existing spots; reuse whichever the
plan binds to:
```python
# L3918-3919 — the cached list of incidents
raw_tracked = sec.get("tracked_incidents")
tracked_incs = raw_tracked if isinstance(raw_tracked, list) else []
# L3937 — the explaining-incident id for resolved/degraded verdicts
explaining_id = sec.get("incident_id")
# L3974 — the surviving incident's id on the active-incident path
inc_id_rt  = inc.get("id")
```
And the id is stored at fetch time by `_collect_tracked_incidents` (L2202-2208):
```python
result.append({
    "id":        inc.get("id", ""),     # L2203 — Statuspage id == incident page slug (D-03)
    ...
})
```
**Pattern:** at the status render site, bind the id from the SAME incident the segment is about
(`surviving_inc.get("id")` on the active path L3978; `explaining_inc.get("id")` on the
resolved/degraded path L3945-3953), then validate via unit 4 before building the URL.

---

## Shared Patterns

### Omit-not-fake / never-raise (D-10) — applies to ALL units above
**Source:** `fmt_reset` (L2547/L2558 return None), `_bar_preset` (L122-124 default fallback),
both render functions' outer `try/except` (L3817-3818, L4054-4055), and the alert-override
inner `try/except → pass` (L3801-3802).
**Apply to:** `osc8()` returns plain `text` (never a partial escape) on disabled/bad-url; the
URL validators return None on non-match; both render sites pass a None/empty url straight through.
The guarantee "no stray escape bytes when off/unsupported" lives entirely in `osc8()`.

### Network-string sanitization posture
**Source:** `_sanitize` (L532-536); inline filters L3776-3779 and L4036-4039.
**Apply to:** unit 4 — but URL components need *allowlist* validation (stricter than the
display-string denylist), because `{id}`/`{UGC}` are interpolated into the OSC 8 URI field where
an ST/control byte is a terminal-injection breakout (security note, CONTEXT L101-106).

### Render-time config resolution
**Source:** `icon_set` reads (L3674-3675, L4003); `DEFAULTS` + `_deep_merge` (L131-217).
**Apply to:** unit 2 + unit 3 — resolve `links` (and `auto` env detection) once per render call
from `cfg`, exactly as `icon_set` is resolved, so toggling takes effect on the next render.

### Escape-literal idiom
**Source:** ANSI constants L77-84 use octal `"\033[..."`.
**Apply to:** unit 1 constants — spell OSC 8 bytes as `\033` (not `\x1b`) to match the file. Note:
the SANITIZERS reject the char written `"\x1b"` (L535/L3778/L4038) — same byte, different spelling;
keep that in mind when writing the URL-validator reject set.

## No Analog Found

None. Every code unit has a concrete in-file analog. (This is a deliberately self-similar,
single-file codebase; OSC 8 wrapping is a new mechanism but every supporting pattern —
escape constants, pure total helpers, env reads, config defaults+merge, network-string
sanitization, render-site SGR wrapping, omit-not-fake — already exists.)

## Metadata

**Analog search scope:** `claude-statusline.py` (single file, 4224 lines), `09-CONTEXT.md`.
**Files scanned:** 1 source file + 1 context doc.
**Pattern extraction date:** 2026-06-20
**Note:** CONTEXT.md line numbers had drifted; the references above are re-verified against the
current file. Notably there is NO bare `ESC` constant (CONTEXT's "ESC ~L81-84" is the `BOLD`
literal); escapes are raw `"\033..."` strings.

## PATTERN MAPPING COMPLETE
