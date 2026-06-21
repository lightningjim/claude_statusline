---
phase: 09-clickable-links
plan: "02"
subsystem: weather-alert-osc8
tags: [osc8, hyperlinks, weather, alerts, ugc, security]
dependency_graph:
  requires:
    - osc8() helper (Plan 09-01)
    - _osc8_enabled() resolver (Plan 09-01)
    - _valid_ugc() validator (Plan 09-01)
    - _weather_segment Step 3c alert-override block (Phase 8)
  provides:
    - OSC 8 clickable link for weather alert glyph+event+timing fragment
    - UGC extraction with Z-preferred / C-fallback chain
    - LINK-02 delivery: weather alerts link to NWS per-zone active-alerts endpoint
    - LINK-03 at this site: zero \x1b]8 bytes when links=off or no valid UGC
  affects:
    - claude-statusline.py (_weather_segment Step 3c, ~L3885-3960)
    - tests/test_weather_links.py (new test module)
tech_stack:
  added: []
  patterns:
    - "UGC extraction: props.get('geocode') or {} → .get('UGC') or [] → Z-first loop"
    - "OSC 8 composition: osc8(color+text+RESET, url, enabled=bool) — SGR inside span"
    - "Tally outside span: concatenated to osc8() result, never to detail before wrapping"
    - "_osc8_enabled() resolved once per render, patched True in tests via patch.object"
key_files:
  created:
    - tests/test_weather_links.py
  modified:
    - claude-statusline.py
decisions:
  - "SGR color wrap goes INSIDE the OSC 8 span (D-06): osc8(f'{color}{detail}{RESET}', url, enabled=...) — terminals accept SGR inside OSC 8"
  - "Tally appended to osc8() result as a string suffix, not to detail before osc8() — enforces D-06 tally-outside-span boundary in source order"
  - "UGC loop: two separate passes (Z first, then C) rather than a single pass with conditional, for clarity matching D-05 fallback chain description"
  - "_ugc extraction wrapped in try/except → _ugc=None so any unexpected geocode shape degrades to no link (omit-not-fake, D-10)"
  - "Tests patch _WEATHER_OK=True + _ASTRAL_OK=False so they run without astral installed; _ASTRAL_OK=False suppresses sun-segment calls and leaves trailing_detail as the alert"
metrics:
  duration: "8 min"
  completed: "2026-06-21"
  tasks: 2
  files: 2
  commits: 2
requirements_completed:
  - LINK-02
  - LINK-03
---

# Phase 09 Plan 02: Weather Alert OSC 8 Links

Wire the Plan 09-01 OSC 8 helpers into the weather alert render site: the `_weather_segment` Step 3c alert-override block now wraps the glyph+event+timing fragment in an OSC 8 hyperlink to `https://api.weather.gov/alerts/active?zone={UGC}`, with the trailing per-class tally outside the span.

## What Was Built

### `_weather_segment` Step 3c modifications

Three logical additions inside the existing alert-override block:

**1. Link toggle resolve** — `_links_enabled = _osc8_enabled(cfg)` called once per render near the top of Step 3c, matching the `icon_set` resolve pattern (D-01 render-time toggle).

**2. UGC extraction + validation** — Defensive read:

```python
_geocode  = props.get("geocode") or {}
_ugc_list = _geocode.get("UGC") or []
```

Then two sequential passes through `_ugc_list`: first pass picks the first code where `_valid_ugc(code)` succeeds and `code[2] == "Z"` (forecast-zone, D-05 preferred); second pass falls back to `code[2] == "C"` (county); if neither yields → `_ugc = None` → `_wx_url = None` → `osc8()` returns plain text (T-09-03 mitigated).

**3. OSC 8 wrap + tally-outside assembly** — After timing is appended and before the tally:

```python
linkable = osc8(f"{color}{detail}{RESET}", _wx_url, enabled=_links_enabled)
tally = f"  {_tally}" if remaining_alerts and _tally else ""
trailing_detail = linkable + tally
```

The SGR color wrap (`{color}…{RESET}`) goes inside the OSC 8 span. The tally is concatenated to the `osc8()` result, not to `detail` before wrapping — D-06 boundary enforced in source order.

### `tests/test_weather_links.py`

Two test classes, 11 tests total:

**TestWeatherLinkEnabled** (6 tests):
- `test_zone_ugc_link_present` — OKZ034 → URL present with OSC 8 open bytes
- `test_county_fallback_ugc_link_present` — OKC109 (no Z) → county code used
- `test_zone_preferred_over_county` — [OKC109, OKZ034] → zone wins
- `test_osc8_bytes_present_when_enabled` — OSC8_OPEN and OSC8_CLOSE in output
- `test_no_valid_ugc_no_link` — XX9999 → no `\x1b]8` bytes
- `test_tally_outside_link_span` — with extra_alerts=2, content appears after OSC8_CLOSE

**TestWeatherLinkDisabled** (5 tests):
- `test_links_off_no_osc8_bytes` — LINK-03: no `\x1b]8` bytes with links=off
- `test_links_off_byte_identical_to_plain` — links=off == no-links-key output
- `test_no_ugc_key_no_osc8_bytes` — alert with no geocode key → no escape bytes
- `test_invalid_ugc_no_osc8_bytes` — invalid XX9999 → no escape bytes even with links=on
- `test_tally_appears_after_osc8_close` — tally index > OSC8_CLOSE index

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Failing tests for weather OSC 8 links | 888fd8f | tests/test_weather_links.py (+295 lines) |
| GREEN | OSC 8 wrap implementation in _weather_segment | 08ab9e8 | claude-statusline.py (+38/-5 lines) |

## Test Coverage

`tests/test_weather_links.py` — 11 tests:

- Zone URL confirmed in rendered output (byte-level OSC 8 open+URL check)
- County fallback UGC when no Z code present
- Zone-over-county preference when both present
- No `\x1b]8` bytes when links=off (LINK-03 at this site)
- No `\x1b]8` bytes with invalid UGC
- No `\x1b]8` bytes with missing geocode key
- links=off output byte-identical to no-links-key output
- Tally-outside-span: content after OSC8_CLOSE confirmed (D-06 boundary)

Existing tests unchanged: `tests/test_weather_alerts.py` (95 passed, 30 skipped) and `tests/test_osc8_links.py` (26 passed).

## Deviations from Plan

None — plan executed exactly as written. TDD RED/GREEN cycle followed.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes. T-09-03 (Tampering via UGC → URL injection) mitigated: `_valid_ugc()` allowlist rejects any non-matching string (including ESC/ST bytes) before the URL is built. Non-match → `_ugc = None` → `_wx_url = None` → `osc8()` returns plain text, zero `\x1b]8` bytes.

## Known Stubs

None.

## Self-Check: PASSED

- [x] `tests/test_weather_links.py` exists (11 tests, all pass)
- [x] `claude-statusline.py` Step 3c contains `alerts/active?zone=` (grep count: 1)
- [x] `claude-statusline.py` Step 3c contains `osc8(` call (grep count: 1 at render site)
- [x] Tally append is after the osc8 call in source order (source verified)
- [x] RED commit (888fd8f) exists before GREEN commit (08ab9e8)
- [x] `python -m pytest tests/test_weather_links.py -q` exits 0 (11 passed)
- [x] `python -m pytest tests/test_weather_alerts.py -q` exits 0 (95 passed, 30 skipped)
- [x] `grep -c 'alerts/active?zone=' claude-statusline.py` returns 1
