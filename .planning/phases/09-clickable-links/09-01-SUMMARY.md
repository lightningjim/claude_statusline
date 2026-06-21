---
phase: 09-clickable-links
plan: "01"
subsystem: osc8-foundation
tags: [osc8, hyperlinks, security, validators, config]
dependency_graph:
  requires: []
  provides:
    - osc8() helper
    - _OSC8_OPEN_PRE / _OSC8_ST / _OSC8_CLOSE constants
    - _osc8_enabled() resolver
    - DEFAULTS["display"]["links"] tri-state key
    - _valid_ugc() allowlist validator
    - _valid_incident_id() allowlist validator
  affects:
    - claude-statusline.py (new constants, helpers, DEFAULTS entry)
    - tests/test_osc8_links.py (new test module)
tech_stack:
  added: []
  patterns:
    - "osc8() pure helper: total, never-raises, returns text unchanged on falsy enabled/url"
    - "_osc8_enabled(): tri-state cfg resolver with conservative env allowlist (D-02)"
    - "re.fullmatch allowlist validators: reject on any non-match (no strip, no partial pass-through)"
key_files:
  created:
    - tests/test_osc8_links.py
  modified:
    - claude-statusline.py
decisions:
  - "OSC 8 constants spelled with octal \\033 to match file's ANSI escape idiom"
  - "osc8() returns text unchanged (not empty string) on disabled/no-url — byte-for-byte LINK-03 guarantee"
  - "auto-mode uses frozenset _OSC8_TERM_PROGRAM_ALLOW for easy extension; checks TERM_PROGRAM, WT_SESSION, KITTY_WINDOW_ID, VTE_VERSION, TERMINAL_EMULATOR"
  - "Validators use re.fullmatch (not search), return None on non-match — allowlist not denylist"
  - "_valid_incident_id rejects uppercase per strict ^[0-9a-z]+$ charset"
  - "No render sites touched in this plan — only constants/helpers/DEFAULTS region modified"
metrics:
  duration: "4 min"
  completed: "2026-06-21"
  tasks: 3
  files: 2
  commits: 2
requirements_completed:
  - LINK-03
---

# Phase 09 Plan 01: OSC 8 Foundation — Constants, Helper, Config Key, and URL Validators

Pure, testable building blocks for OSC 8 hyperlinks: `osc8()` emission helper with ESC/ST constants, the tri-state `links` config key, `auto`-mode terminal capability resolver, and allowlist URL-component validators for the two network-sourced URL fields.

## What Was Built

### OSC 8 constants (in ANSI block)

Three constants added alongside the existing `GREEN`/`RESET`/etc. block, spelled with the file's octal `\033` idiom:

- `_OSC8_OPEN_PRE = "\033]8;;"` — ESC ] 8 ; ; before the URL
- `_OSC8_ST = "\033\\"` — ST terminator (ESC backslash)
- `_OSC8_CLOSE = "\033]8;;\033\\"` — empty-URL close terminator

### `osc8(text, url, *, enabled) -> str`

Pure emission helper modeled on `_bar_preset`'s total/never-raises shape. When `not enabled` or `not url`: returns `text` byte-for-byte unchanged — no `\x1b]8` bytes anywhere (LINK-03 guarantee in one place). When enabled and url present: wraps as `_OSC8_OPEN_PRE + url + _OSC8_ST + text + _OSC8_CLOSE`. SGR codes inside text pass through inside the span.

### `DEFAULTS["display"]["links"] = "off"`

Tri-state config key added alongside `icon_set`, `bar_style`, `show_git`, etc. with doc comment noting off/auto/on semantics and opt-in default per D-01.

### `_osc8_enabled(cfg) -> bool`

Pure resolver reading `cfg["display"]["links"]`:
- `"off"` (default) → `False`
- `"on"` → `True` (env not consulted)
- `"auto"` → checks `_OSC8_TERM_PROGRAM_ALLOW` frozenset (`iTerm.app`, `WezTerm`, `vscode`, `ghostty`), plus `WT_SESSION` (Windows Terminal), `KITTY_WINDOW_ID` (kitty), `VTE_VERSION` (GNOME/VTE), `TERMINAL_EMULATOR` containing "JetBrains"; returns `True` on first match, `False` if none (bias to False, D-02)
- Any other value → `False` (mirror `_bar_preset` unknown→default)

### `_valid_ugc(value) -> str | None`

Allowlist validator using `re.fullmatch(r"[A-Z]{2}[CZ][0-9]{3}", s)`. Returns the validated string or `None` on any non-match — including values carrying ESC/ST/control bytes (security T-09-01). Does not strip; rejects the whole string.

### `_valid_incident_id(value) -> str | None`

Allowlist validator using `re.fullmatch(r"[0-9a-z]+", s)`. Validates Statuspage id format (lowercase hex/alnum). Rejects uppercase, path traversal, ESC bytes, empty/None. Returns string or `None`.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Failing tests for all three tasks | d0e6aa0 | tests/test_osc8_links.py (+211 lines) |
| GREEN | Implementation of all helpers and config | 9cc634c | claude-statusline.py (+132 lines) |

## Test Coverage

`tests/test_osc8_links.py` — 26 tests, 3 classes:

- **TestOsc8Helper** (7 tests): enabled wrap, disabled passthrough, no-`\x1b]8`-when-disabled assertion, empty-url, None-url, SGR-preserved-in-span, constants-exist-and-start-with-ESC
- **TestOsc8Enabled** (6 tests): off→False, on→True, auto+known-terminal→True, auto+no-markers→False (clears all env markers, prevents developer terminal leak), empty-cfg→False, garbage→False
- **TestUrlValidators** (13 tests): UGC zone/county accepted, lowercase/wrong-digits/ST-byte/None/empty rejected; incident-id alnum accepted, uppercase/path-traversal/ESC-byte/empty/None rejected

Security cases (ST-byte `\033\` and ESC-byte `\x1b` rejection) explicitly asserted.

## Deviations from Plan

None — plan executed exactly as written. All three TDD tasks (constants+helper, config+resolver, validators) implemented in a single GREEN commit after RED test file.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The threat mitigations in the plan's `<threat_model>` (T-09-01, T-09-02) are fully implemented:
- T-09-01 (Tampering via URL component injection): mitigated by `_valid_ugc` and `_valid_incident_id` allowlist validators that reject any string containing control/ST/ESC bytes
- T-09-02 (Tampering via osc8 emission with rejected component): mitigated by `osc8()` returning text unchanged on falsy url, closing the breakout path

## Self-Check: PASSED

- [x] `tests/test_osc8_links.py` exists and passes (26/26)
- [x] `claude-statusline.py` contains `def osc8(`, `def _osc8_enabled(`, `def _valid_ugc(`, `def _valid_incident_id(` (grep count: 4)
- [x] `re.fullmatch` used in ≥ 2 places (grep count: 2)
- [x] `_OSC8_OPEN_PRE`, `_OSC8_ST`, `_OSC8_CLOSE` constants present
- [x] `DEFAULTS["display"]["links"]` = `"off"` present
- [x] No render sites changed (only constants/helpers/DEFAULTS region)
- [x] RED commit (d0e6aa0) exists before GREEN commit (9cc634c)
- [x] Both commits exist in git log
