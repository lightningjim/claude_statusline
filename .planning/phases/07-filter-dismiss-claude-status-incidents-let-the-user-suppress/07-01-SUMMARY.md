---
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
plan: "01"
subsystem: claude-status-filter
tags: [dismissal-store, config, cache-payload, tdd]
dependency_graph:
  requires: [06-02]
  provides: [dismissal-store-helpers, claude_status-config-table, tracked-incident-cache-payload]
  affects: [fetch_claude_status, claude_status-cache-section, DEFAULTS]
tech_stack:
  added: []
  patterns: [atomic-temp-os.replace-write, read-with-silent-fallback, tdd-red-green]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_claude_status.py
decisions:
  - DEFAULTS["claude_status"] added as top-level table (not nested under display) per D-06
  - _DISMISSALS_PATH in same cache dir as _CACHE_PATH; store is a flat dict (id → {impact_at_dismiss, dismissed_at})
  - _collect_tracked_incidents helper extracts tracked incidents; titles stored RAW per T-06-01/T-07-03 contract
  - tracked_incidents included in BOTH noteworthy and healthy payload branches for stable shape
  - _prune_dismissals is pure (no side effects) so derivation path can call it cheaply
metrics:
  duration_minutes: 5
  completed_date: "2026-06-17"
  tasks_completed: 2
  files_modified: 2
---

# Phase 7 Plan 01: [claude_status] Config Table + Dismissal Store + Widened Payload Summary

**One-liner:** Tool-owned dismissal store helpers (read/write/dismiss/undismiss/prune) + `[claude_status]` TOML config table + widened `fetch_claude_status` payload carrying the raw tracked-incident list for offline `--status-incidents` display.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | [claude_status] config + store tests (failing) | d9497e9 | tests/test_claude_status.py |
| 1 (GREEN) | [claude_status] config + store implementation | a230868 | claude-statusline.py |
| 2 (RED) | Widened payload tests (failing) | 4c642c8 | tests/test_claude_status.py |
| 2 (GREEN) | Widened payload implementation | daeed9c | claude-statusline.py |

## What Was Built

### Task 1: [claude_status] config table + dismissal-store helpers

**Config table (DEFAULTS["claude_status"]):**
- `filter_enabled: True` — master toggle for the suppression filter (D-06)
- `ignore_title_patterns: []` — list of title patterns for keyword suppression (D-06)
- Added as a top-level sibling of `"display"` per CONTEXT D-06 and PATTERNS.md Pattern 4
- Hand-edited TOML only — tool NEVER rewrites this table (D-05); existing `_deep_merge` handles absent-key defaults automatically

**Dismissal store helpers (new, near `_CACHE_PATH` at line 260):**
- `_DISMISSALS_PATH` — `~/.claude/claude-statusline/status_dismissals.json` (same dir as cache)
- `read_dismissals(path=None) -> dict` — copied from `read_cache` pattern; corrupt/missing → `{}` → no suppression (T-07-01)
- `write_dismissals(store, path=None) -> None` — atomic temp+`os.replace` write of the whole flat dict; swallows all errors (T-07-02)
- `_dismiss_id(inc_id, impact_at_dismiss, path=None) -> None` — read→set→write; no-op on empty id; records `impact_at_dismiss` + `dismissed_at` epoch (D-03/D-04)
- `_undismiss_id(inc_id, path=None) -> None` — read→pop→write; no-op if absent
- `_prune_dismissals(store, live_ids) -> dict` — pure fn (no side effects); returns only entries with id in live_ids (D-04 auto-prune enabler)

### Task 2: Widened claude_status cache payload

**New helper:**
- `_collect_tracked_incidents(summary) -> list` — mirrors `_derive_claude_status` tracked-component filter; returns compact dicts `{id, impact, status, title, component}` where `component` is the first matching tracked component name; per-item `try/except` guard; titles stored RAW per Phase 6 cache contract (T-07-03); empty list on any error

**fetch_claude_status payload:**
- `tracked_incidents` key added to BOTH the noteworthy and healthy payload branches (stable shape — Plan 03 reads from cache without a network fetch per D-02)
- All existing Phase 6 keys (`noteworthy`, `severity`, `label`, `kind`) unchanged — zero regression to Plan 06 render path

## Tests Added

**25 new tests (Task 1):**
- `TestClaudeStatusConfigDefaults` (4 tests): DEFAULTS table present, filter_enabled=True, ignore_title_patterns=[], deep-merge with partial TOML override
- `TestDismissalStoreHelpers` (21 tests): _DISMISSALS_PATH constant, read_dismissals (missing/garbage/non-dict/valid), write_dismissals round-trip + unwritable-path swallow, _dismiss_id (adds entry + empty-id noop), _undismiss_id (removes entry + missing-id noop), _prune_dismissals (removes stale/pure/empty-live-ids/empty-store)

**14 new tests (Task 2):**
- `TestFetchClaudeStatusWidenedPayload` (14 tests): tracked_incidents key present in both branches, operational fixture has [], incident fixture entry has id/impact/status/title/component, regression guard for noteworthy/severity/label/kind

**Baseline: 85 → Final: 123 tests passing (38 new tests added)**

## Verification Results

```
python -m pytest tests/test_claude_status.py -q
123 passed, 15 subtests passed in 0.29s
```

```
grep -c "def read_dismissals|def write_dismissals|def _dismiss_id|def _undismiss_id|def _prune_dismissals" claude-statusline.py
5
```

```
grep -c "tomllib.dump|toml.*write|.write_text.*toml" claude-statusline.py
0  (no TOML writer introduced)
```

## Deviations from Plan

None — plan executed exactly as written. TDD RED/GREEN cycle followed for both tasks. No architectural changes required.

## Threat Flags

None. All STRIDE threats addressed by the implementation:
- T-07-01 (Tampering/corrupt store): `read_dismissals` wraps `json.load` in `try/except`, rejects non-dict → `{}` ✓
- T-07-02 (DoS/concurrent writes): `write_dismissals` copies atomic temp+`os.replace` pattern ✓
- T-07-03 (Injection/RAW titles): titles stored RAW in cache per contract; sanitization flagged forward to Plan 03 ✓
- T-07-SC (no new deps): stdlib `json`/`os`/`time` only ✓

## Self-Check: PASSED

- `claude-statusline.py` modified: FOUND (5 new functions + config table + payload widening)
- `tests/test_claude_status.py` modified: FOUND (38 new tests)
- Commits: d9497e9, a230868, 4c642c8, daeed9c — all present in git log
- `python -m pytest tests/test_claude_status.py -q` → 123 passed (≥85 baseline) ✓
