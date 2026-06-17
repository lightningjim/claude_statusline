---
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
plan: "03"
subsystem: claude-status-filter
tags: [cli-flags, dismiss, status-incidents, ansi-sanitization, tdd]
dependency_graph:
  requires: [07-01, 07-02]
  provides: [--dismiss-flag, --undismiss-flag, --status-incidents-flag]
  affects: [main, claude-statusline.py]
tech_stack:
  added: []
  patterns: [tdd-red-green, hand-rolled-sys-argv, ansi-sanitize-verbatim, never-crash-try-except]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_claude_status.py
decisions:
  - Handler functions (_handle_dismiss_flag, _handle_undismiss_flag, _print_status_incidents) factored out of main() so they are unit-testable without subprocess
  - _DISMISS_REFRESH_NOTE shared constant ensures symmetric phrasing for both --dismiss and --undismiss confirmations
  - --status-incidents shows stale store entries (dismissed ids no longer in live feed) in the same table using '?' placeholders for unknown fields
  - ANSI sanitizer applied verbatim from _claude_status_segment (same expression, same _CLAUDE_STATUS_LABEL_MAXLEN) — single sanitization point, no drift
  - Empty id to _handle_dismiss_flag/_handle_undismiss_flag prints usage hint and returns cleanly (no _dismiss_id call, store unchanged)
metrics:
  duration_minutes: 10
  completed_date: "2026-06-17"
  tasks_completed: 2
  files_modified: 2
---

# Phase 7 Plan 03: --dismiss / --undismiss / --status-incidents CLI Flags Summary

**One-liner:** Three management CLI flags (--dismiss, --undismiss, --status-incidents) wired into main() before stdin read — the user-facing surface for discovering incident ids, muting perpetual noise, and lifting mutes, with ANSI-sanitized table output and a next-refresh latency note.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for --dismiss/--undismiss flags | b1069fc | tests/test_claude_status.py |
| 1 (GREEN) | --dismiss/--undismiss handler implementation | 2cdc22b | claude-statusline.py |
| 2 (RED) | Failing tests for --status-incidents table | b9e6731 | tests/test_claude_status.py |
| 2 (GREEN) | --status-incidents table + main() branch | 84f78d1 | claude-statusline.py |

## What Was Built

### Task 1: --dismiss / --undismiss store-mutation flags

**New module constant:**
- `_DISMISS_REFRESH_NOTE` — shared one-liner note appended to both --dismiss and --undismiss confirmations: "change takes effect on the bar at the next status refresh (cache TTL ~5 min); run --refresh to apply it immediately."

**New handler functions (unit-testable, no subprocess required):**
- `_handle_dismiss_flag(inc_id, cache_path=None, dismissals_path=None)`: reads the cached `tracked_incidents` list to find the live impact for the given id (D-03 baseline); calls `_dismiss_id(id, impact_at_dismiss)`; prints a one-line confirmation + `_DISMISS_REFRESH_NOTE`. Empty/missing id → usage hint, no store write (graceful).
- `_handle_undismiss_flag(inc_id, dismissals_path=None)`: calls `_undismiss_id(id)`; prints confirmation + same `_DISMISS_REFRESH_NOTE`. Empty id → usage hint.

**Updated `main()`:**
- `--dismiss <id>` branch: after `--refresh`, before `_load_stdin()`. Extracts `sys.argv[idx+1]` with idx+1 bounds guard (no IndexError if missing arg). Calls `_handle_dismiss_flag`, then `sys.exit(0)`.
- `--undismiss <id>` branch: same shape. Calls `_handle_undismiss_flag`, then `sys.exit(0)`.

### Task 2: --status-incidents table (sanitized, cache + store only)

**New helper `_print_status_incidents(cache, dismissals) -> None`:**
- Reads `tracked_incidents` from `cache["claude_status"]` + dismissal store dict (both already loaded by caller — no network, no fetch).
- Builds aligned text table with columns: ID, IMPACT, STATUS, STATE, COMPONENT, TITLE.
- STATE values: `dismissed` (id in store + in live list), `active` (in live, not dismissed), `stale` (in store, absent from live list — will be auto-pruned by next `--refresh`). Stale entries shown with `?` placeholders for fields only known from the live feed.
- Titles ANSI-sanitized using the VERBATIM expression from `_claude_status_segment` (T-07-08): `"".join(ch for ch in str(s) if ch == " " or (ch.isprintable() and ch != "\x1b"))[:_CLAUDE_STATUS_LABEL_MAXLEN].strip()` — no raw `\x1b` escapes reach the terminal.
- Empty list → prints `"No tracked incidents."` (friendly, non-silent).
- Entire body in `try/except → print error message` — never raises.

**Updated `main()`:**
- `--status-incidents` branch: after `--undismiss`, before `_load_stdin()`. Calls `read_cache(_CACHE_PATH)` + `read_dismissals(_DISMISSALS_PATH)`, then `_print_status_incidents(cache, dismissals)`. No `load_config()` needed (no cfg dependency), no fetch. `sys.exit(0)`.

## Tests Added

**Task 1 RED → GREEN (10 new tests in `TestDismissUndismissFlags`):**
- Store mutation: dismiss adds id with live impact baseline; undismiss removes it
- Next-refresh note: confirmation output contains "refresh" and "--refresh"
- Unknown id: recorded with `impact_at_dismiss="none"` (D-03 baseline default)
- Missing arg: no IndexError, clean return, store unchanged (both flags)
- No stdin: `_handle_dismiss_flag` does not call `_load_stdin`

**Task 2 RED → GREEN (14 new tests in `TestStatusIncidentsFlag`):**
- Helper exists: `_print_status_incidents` is callable
- Table content: output contains id, title, component, impact, status
- State markers: undismissed → "active"; dismissed → "dismissed"; stale store entry → "stale"
- No fetch: `_print_status_incidents` does not call `fetch_claude_status`
- ANSI sanitization: malicious title with raw `\x1b` escapes → none in output (two variants)
- Empty list: non-empty friendly message mentioning "no"/"none"/"empty"
- main() branch: `inspect.getsource(main)` contains `--status-incidents`

**Baseline: 166 → Final: 190 tests passing (24 new tests added)**

## Verification Results

```
python -m pytest tests/test_claude_status.py -q
190 passed, 15 subtests passed in 0.49s
```

```
grep -n '"--dismiss" in sys.argv\|"--undismiss" in sys.argv\|"--status-incidents" in sys.argv' claude-statusline.py
3737:    if "--dismiss" in sys.argv:
3745:    if "--undismiss" in sys.argv:
3753:    if "--status-incidents" in sys.argv:
```

```
grep -c "_dismiss_id\|_undismiss_id" claude-statusline.py
5  (definition sites + call sites in handlers)
```

```
grep "import argparse" claude-statusline.py | wc -l
0  (no argparse introduced)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] `_handle_dismiss_flag` accepts optional `cache_path`/`dismissals_path` parameters**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests need to redirect store/cache paths to temp directories, but the handler calls `_CACHE_PATH`/`_DISMISSALS_PATH` directly. Without injectable paths, tests would require `patch.object` on every single constant, making the test helper fragile.
- **Fix:** Added `cache_path=None` and `dismissals_path=None` optional params to `_handle_dismiss_flag`; `None` defaults to the module constants. Same pattern used throughout the codebase (e.g. `_dismiss_id(path=None)`). `_handle_undismiss_flag` likewise accepts `dismissals_path=None`.
- **Files modified:** `claude-statusline.py`
- **Commit:** included in 2cdc22b

## Threat Flags

None. All STRIDE threats from the plan's threat register addressed:
- T-07-08 (Injection/title printing): `_print_status_incidents` ANSI-strips + width-bounds titles using the verbatim expression from `_claude_status_segment`; tested with malicious-title fixture ✓
- T-07-09 (DoS/missing id): `idx+1 < len(sys.argv)` guard in both main() branches; `not inc_id` guard in handlers; tested ✓
- T-07-10 (Tampering/arbitrary id): accepted — auto-prune removes phantom ids; no TOML/real-incident impact ✓
- T-07-SC (no new deps): stdlib only (`sys`, `json`, `os`) ✓

## Self-Check: PASSED

- `claude-statusline.py` modified: FOUND (_handle_dismiss_flag, _handle_undismiss_flag, _DISMISS_REFRESH_NOTE, _print_status_incidents, main() branches)
- `tests/test_claude_status.py` modified: FOUND (24 new tests in 2 new classes)
- Commits: b1069fc, 2cdc22b, b9e6731, 84f78d1 — verified present in git log
- `python -m pytest tests/test_claude_status.py -q` → 190 passed (≥166 baseline) ✓
