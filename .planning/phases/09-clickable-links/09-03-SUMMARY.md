---
phase: 09-clickable-links
plan: "03"
subsystem: claude-status-osc8
tags: [osc8, hyperlinks, status, incidents, security]
dependency_graph:
  requires:
    - osc8() helper (Plan 09-01)
    - _osc8_enabled() resolver (Plan 09-01)
    - _valid_incident_id() validator (Plan 09-01)
    - _claude_status_segment render site (Phase 06)
  provides:
    - OSC 8 clickable link for the whole Claude Status segment
    - Incident id binding from surviving/explaining incident at render time
    - LINK-01 delivery: status events link to specific status.claude.com incident page
    - LINK-03 at this site: zero \x1b]8 bytes when links=off or no valid id
    - D-03a: no homepage substitution on missing/invalid/hyphenated id
  affects:
    - claude-statusline.py (_claude_status_segment Steps 4-7)
    - tests/test_status_links.py (new test module)
    - tests/fixtures/status_incident_valid_id.json (new fixture)
tech_stack:
  added: []
  patterns:
    - "Incident id binding: _inc_id = surviving_inc.get('id') / explaining_inc.get('id') at two paths"
    - "_osc8_enabled() resolved once per render at Step 5 (matches icon_set resolve pattern)"
    - "Allowlist validation: _valid_incident_id(_inc_id) before building URL — rejects hyphens, ESC, uppercase"
    - "url = None when id invalid/missing — osc8() returns text unchanged (D-03a omit-not-fake)"
    - "return osc8(f'{color}{detail}{RESET}', _status_url, enabled=_links_enabled)"
key_files:
  created:
    - tests/test_status_links.py
    - tests/fixtures/status_incident_valid_id.json
  modified:
    - claude-statusline.py
decisions:
  - "_inc_id declared alongside _severity/_label/_kind_override vars for consistent override-var pattern"
  - "Active path binds id BEFORE the baked_kind branch so maintenance+surviving_inc also captures the id"
  - "No url variable when id is missing/invalid (url stays None) — osc8() passthrough, never homepage (D-03a)"
  - "Fixture status_incident_valid_id.json uses id 'abc123def456' — real Statuspage ids are pure lowercase alnum; no hyphen"
  - "status_incident_tracked.json (id 'inc-001', hyphenated) used as the D-03a invalid-id negative fixture"
  - "TestStatusLinkEnabledViaFixture runs fetch_claude_status(FAKE_STATUS) → tests full pipeline not just the render function"
metrics:
  duration: "8 min"
  completed: "2026-06-20"
  tasks: 2
  files: 3
  commits: 3
requirements_completed:
  - LINK-01
  - LINK-03
---

# Phase 09 Plan 03: Status Segment OSC 8 Links

Wire the Plan 09-01 OSC 8 helpers into the Claude Status render site: `_claude_status_segment` now wraps its entire returned segment in an OSC 8 hyperlink to `https://status.claude.com/incidents/{id}`, with the id bound from the exact incident the segment is describing and validated via the `_valid_incident_id` allowlist.

## What Was Built

### `_claude_status_segment` modifications

Four logical additions inside the existing function body:

**1. `_inc_id = None` declaration** — Added alongside the existing `_severity_override`, `_label_override`, `_kind_override` variables at the top of the render-time override block. Default None means "no link" unless an id is successfully bound.

**2. Id binding on the resolved/degraded path** — After `explaining_inc` survives the suppression check (L4125), bind:
```python
_inc_id = explaining_inc.get("id")  # Phase 9: bind for OSC 8 URL (D-03)
```
This is the same incident the segment is describing (not "any incident").

**3. Id binding on the active-incident path** — After `surviving_inc` is found, bind:
```python
_inc_id = surviving_inc.get("id")  # Phase 9: bind for OSC 8 URL (D-03/D-07)
```
Placed before the `baked_kind == "incident"` branch so maintenance items with a surviving incident also capture the id.

**4. `_links_enabled` resolve at Step 5** — Added alongside `icon_set`:
```python
_links_enabled = _osc8_enabled(_cfg)  # Phase 9: resolve toggle once per render (D-01)
```

**5. Return rewritten at Step 7** — The single return is now:
```python
_validated_id = _valid_incident_id(_inc_id)
_status_url   = (f"https://status.claude.com/incidents/{_validated_id}"
                 if _validated_id else None)
return osc8(f"{color}{detail}{RESET}", _status_url, enabled=_links_enabled)
```
`_valid_incident_id` uses `re.fullmatch(r"[0-9a-z]+", ...)` — rejects hyphens, ESC bytes, uppercase, empty strings. When id is None/invalid/hyphenated: `_status_url = None` → `osc8()` returns colored text unchanged. The status homepage is never substituted (D-03a).

### `tests/fixtures/status_incident_valid_id.json`

Clone of `status_incident_tracked.json` shape with `incidents[0].id` changed from `"inc-001"` to `"abc123def456"` — a pure lowercase-alnum id that passes the `^[0-9a-z]+$` allowlist. This is the only fixture valid for the link-present assertion; `status_incident_tracked.json`'s hyphenated `"inc-001"` correctly fails the allowlist and is used for the D-03a negative case.

### `tests/test_status_links.py`

Three test classes, 21 tests total:

**TestStatusLinkEnabled** (8 tests):
- `test_link_present_with_valid_id` — id "abc123def456" → incident URL in output
- `test_osc8_open_present_with_valid_id` — OSC 8 open bytes present
- `test_osc8_close_present_with_valid_id` — OSC 8 close bytes present
- `test_full_osc8_open_with_url` — full `\x1b]8;;https://status.claude.com/incidents/abc123def456` sequence
- `test_hyphenated_id_no_link` — "inc-001" → no `\x1b]8` bytes (D-03a)
- `test_hyphenated_id_no_homepage_fallback` — no homepage as OSC 8 target
- `test_missing_id_no_link` — None id → no `\x1b]8` bytes
- `test_missing_id_no_homepage_fallback` — no homepage substitution

**TestStatusLinkDisabled** (7 tests):
- `test_links_off_no_osc8_bytes` — LINK-03: no `\x1b]8` bytes with links=off
- `test_links_off_byte_identical_to_no_links_key` — links=off == no-key output
- `test_injection_id_no_osc8_bytes` — ESC-byte id rejected by allowlist
- `test_injection_id_no_homepage_fallback` — no homepage for injection id
- `test_empty_id_no_osc8_bytes` — empty string id → no link
- `test_empty_id_no_homepage_fallback` — empty id → no homepage
- `test_no_incidents_slug_with_empty_id_no_link` — no `incidents//` or `incidents/\x1b` in output

**TestStatusLinkEnabledViaFixture** (6 tests — fixture-driven, end-to-end pipeline):
- `test_valid_id_fixture_contains_incident_key` — JSON structure check
- `test_valid_id_matches_allowlist` — `re.fullmatch` on fixture id
- `test_valid_id_fixture_produces_link` — fetch_claude_status(FAKE_STATUS) + segment → OSC 8 present
- `test_hyphenated_id_fixture_no_link` — status_incident_tracked.json → no OSC 8 (D-03a)
- `test_hyphenated_id_no_homepage_fallback_via_fixture` — no homepage via fixture path
- `test_valid_id_fixture_links_off_no_osc8` — valid fixture + links=off → no OSC 8 (LINK-03)

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Failing tests for status OSC 8 links | f61eff2 | tests/test_status_links.py (+274 lines) |
| GREEN | Bind incident id + OSC 8-wrap status segment | b231f4a | claude-statusline.py (+14/-2 lines) |
| Task 2 | Valid-id fixture + fixture-driven link tests | 19d30f2 | tests/fixtures/status_incident_valid_id.json, tests/test_status_links.py (+140 lines) |

## Test Coverage

`tests/test_status_links.py` — 21 tests, 3 classes.

Security cases explicitly asserted:
- Hyphenated id `"inc-001"` (Statuspage-style slug) → no link (D-03a)
- ESC-byte injection `"abc\x1bdef"` → rejected by allowlist → no link
- Empty string id → no link
- Missing id (no `id` key in tracked incident) → no link
- Homepage never substituted on any bad/invalid id path

Existing tests unchanged:
- `tests/test_claude_status.py` — 246 passed, 30 subtests passed
- `tests/test_osc8_links.py` — 26 passed
- `tests/test_weather_links.py` — 11 passed

## Deviations from Plan

None — plan executed exactly as written. TDD RED/GREEN cycle followed for Task 1; Task 2 added the fixture and extended tests.

## Known Stubs

None. All data is wired: the id is bound from the live `tracked_incidents` field in the cache section, validated, and interpolated into the URL. No placeholders.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes. Threat mitigations in the plan's `<threat_model>` are fully implemented:

- T-09-05 (Tampering via incident id → URL injection): mitigated by `_valid_incident_id` allowlist (`re.fullmatch(r"[0-9a-z]+", ...)`) rejecting hyphens, ESC/ST bytes, uppercase, path traversal, and empty strings. Non-match → `_status_url = None` → `osc8()` returns plain text, zero `\x1b]8` bytes.
- T-09-06 (Spoofing via homepage-as-stand-in link): mitigated by D-03a: on missing/invalid id `_status_url` stays `None` (never set to the homepage), so `osc8()` returns the colored text unchanged. Verified by 5 explicit no-homepage-fallback tests.

## Self-Check: PASSED

- [x] `tests/test_status_links.py` exists and passes (21/21)
- [x] `tests/fixtures/status_incident_valid_id.json` exists with id `"abc123def456"` matching `^[0-9a-z]+$`
- [x] `claude-statusline.py` contains `https://status.claude.com/incidents/` (grep count: 1)
- [x] `claude-statusline.py` contains no bare homepage link target `"https://status.claude.com"` (grep count: 0)
- [x] `claude-statusline.py` contains `osc8(` at the status render return
- [x] `claude-statusline.py` contains `_valid_incident_id` at the status render site
- [x] `_links_enabled = _osc8_enabled(_cfg)` present in `_claude_status_segment`
- [x] `_inc_id` bound from `explaining_inc.get("id")` and `surviving_inc.get("id")`
- [x] RED commit (f61eff2) exists before GREEN commit (b231f4a)
- [x] All 3 commits exist in git log
- [x] `python -m pytest tests/test_status_links.py -q` exits 0 (21 passed)
- [x] `python -m pytest tests/test_claude_status.py -q` exits 0 (246 passed, no regression)
