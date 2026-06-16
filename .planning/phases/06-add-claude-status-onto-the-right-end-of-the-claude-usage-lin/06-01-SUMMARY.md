---
phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
plan: "01"
subsystem: claude-status-data-layer
tags: [fetch, cache, derivation, tdd, statuspage]
dependency_graph:
  requires: []
  provides:
    - fetch_claude_status
    - _derive_claude_status
    - _claude_status_color
    - _NF_CLAUDE_INCIDENT
    - _NF_CLAUDE_MAINT
    - cache.claude_status section (shape: {fetched_at, noteworthy, severity?, label?, kind?})
    - DEFAULTS.display.show_claude_status
    - DEFAULTS.cache.status_ttl
    - DEFAULTS.cache.status_max_stale
  affects:
    - run_refresh (added fetch_claude_status call)
    - maybe_spawn_refresh (added status_stale trigger)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN per task (3 tasks, 3 RED commits, 3 GREEN commits)
    - Statuspage.io v2 summary.json parsing via _nws_get (reused as-is)
    - CLAUDE_STATUSLINE_FAKE_STATUS env var fixture override (mirrors FAKE_ALERTS pattern)
    - try/except never-crash discipline (D-10) on all new functions
key_files:
  created:
    - tests/test_claude_status.py (43 tests)
    - tests/fixtures/status_operational.json
    - tests/fixtures/status_incident_tracked.json
    - tests/fixtures/status_incident_untracked.json
    - tests/fixtures/status_degraded_no_title.json
    - tests/fixtures/status_maintenance.json
    - tests/fixtures/status_malicious_title.json (ESC-encoded ANSI in title for Plan 02)
  modified:
    - claude-statusline.py (config keys, glyph constants, color helper, derivation, fetch, wiring)
decisions:
  - "Cache section name locked as 'claude_status'"
  - "_derive_claude_status return dict contract: {severity, label, kind} or None"
  - "RAW (unsanitized) label stored in cache; sanitization deferred to Plan 02 render path"
  - "major severity maps to RED (no separate orange tier added — file has no 256-color constant)"
  - "Healthy refresh (derivation=None) still writes claude_status section with noteworthy=False to timestamp fetch and prevent hot-respawn loop"
  - "Pre-existing E2E worktree failures (test_git_segment, test_gsd_segment) are out-of-scope — they fail because E2E tests run in a git worktree where project dir name is agent-id, not claude_statusline"
metrics:
  duration_minutes: 35
  completed_date: "2026-06-16T20:39:21Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 8
  files_modified: 3
---

# Phase 06 Plan 01: Claude Status Data Layer Summary

Claude service-health data layer: detached background fetch of `status.claude.com/api/v2/summary.json`, trigger derivation enforcing D-01/D-02/D-03/D-04, severity-color helper, status glyph constants, cache TTL config keys, and wiring into the existing refresh machinery.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for config keys, color, glyphs | 24b1cfb | tests/test_claude_status.py |
| 1 (GREEN) | Config keys, glyph constants, severity-color helper | c88b4c1 | claude-statusline.py |
| 2 (GREEN) | Derivation helper + fixtures | 1e46906 | claude-statusline.py, 6 fixtures |
| 3 (GREEN) | fetch_claude_status + run_refresh/maybe_spawn_refresh wiring | 43a0cc3 | claude-statusline.py, 2 test fixes |

## Locked Data Contract (Plan 02 depends on this)

**Cache section name:** `"claude_status"`

**Cache section shape:**
```json
{
  "fetched_at": <float epoch>,
  "noteworthy": <bool>,
  "severity":   "<minor|major|critical|maintenance>",  // present when noteworthy=True
  "label":      "<raw incident title or 'Component: state'>",  // present when noteworthy=True
  "kind":       "<incident|maintenance|degraded>"  // present when noteworthy=True
}
```

When all tracked components are healthy and no relevant incident/maintenance exists, the section is written with `{"noteworthy": False}` (timestamps the fetch to prevent hot-respawn loop).

**`_derive_claude_status` return contract:**
- `None` — quiet when healthy (D-01)
- `{"severity": str, "label": str, "kind": str}` — something noteworthy

**Severity tokens:** `"minor"`, `"major"`, `"critical"`, `"maintenance"`

**Kind tokens:** `"incident"`, `"maintenance"`, `"degraded"`

**Tracked component names (D-02):** `"Claude Code"`, `"claude.ai"`, `"Claude Cowork"` — verbatim.

**Label:** RAW (unsanitized) — Plan 02 render path must ANSI-sanitize + width-bound before display.

## Derivation Rules (Priority Order)

1. **Unresolved incident touching tracked component** → `kind="incident"`, severity from impact field, label = incident `name` (title). (D-03)
2. **Scheduled/in-progress maintenance touching tracked component** → `kind="maintenance"`, `severity="maintenance"`, label = maintenance `name`. (D-04)
3. **Tracked component non-operational, no incident** → `kind="degraded"`, severity from component status, label = `"<name>: <human state>"`. (D-03 fallback)
4. **All healthy** → `None`. (D-01)

**D-02 enforced:** page-wide `status.indicator` rollup is NEVER consulted — trigger is derived only from tracked components' own statuses + incidents/maintenances scoped to those components.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed existing no-spawn tests broken by status_stale extension**
- **Found during:** Task 3 full-suite run
- **Issue:** Two existing tests (`TestMaybeSpawnRefreshAlerts::test_no_spawn_when_both_fresh` in `test_weather_alerts.py` and `TestMaybeSpawnRefresh::test_does_not_spawn_on_fresh_cache` in `test_weather_fetch.py`) expected no Popen call when weather + alerts were fresh, but now that `status_stale` is a third trigger, absent `claude_status` section caused spurious spawn.
- **Fix:** Added `"claude_status": {"fetched_at": now - 60, "noteworthy": False}` to both test cache dicts to simulate a fresh status section.
- **Files modified:** `tests/test_weather_alerts.py`, `tests/test_weather_fetch.py`
- **Commit:** 43a0cc3

### Design Decisions Made During Execution

**No orange/256-color constant added for `major` severity:**
- Plan noted this as discretion: "if you add one, add a single ANSI 256-color constant near :92 with a comment, otherwise fold major into RED and note it"
- Decision: `major` folds into `RED`. The file's existing band vocabulary is 8/16-color only (GREEN/YELLOW/RED/DIM/BOLD/RESET/DEFAULT_FG/CYAN/GRAY). Adding a 256-color constant would be the first departure from this palette and is unnecessary — RED is the correct signal for a major outage.

## Out-of-Scope Pre-existing Failures

Two E2E tests fail in the worktree environment (pre-existing before this plan's changes):
- `tests/test_git_segment.py::TestGitSegmentE2E::test_e2e_repo_dir_shows_git_segment_between_project_and_model`
- `tests/test_gsd_segment.py::TestGsdSegmentE2E::test_e2e_repo_dir_shows_gsd_segment_between_git_and_model`

These fail because the tests run the script with `_REPO_DIR` as the project dir, which resolves to the worktree root (`agent-a17ffc262906a97c5`) rather than the main repo root (`claude_statusline`). The `[claude_statusline]` project marker is not found. Verified pre-existing: same failure occurred on the base commit before any changes.

## Known Stubs

None. This plan is pure data-layer work; no UI rendering stubs. The label field stores the RAW unsanitized title intentionally — that is by design (Plan 02 handles sanitization), not a stub.

## Threat Surface Scan

No new threat surface beyond what the plan's `<threat_model>` anticipated:
- T-06-01: RAW label stored; sanitization deferred to Plan 02 render path (by design).
- T-06-02: `_derive_claude_status` and `fetch_claude_status` both wrapped in try/except.
- T-06-03: `_nws_get` timeout=10 reused; fetch only in detached child.
- T-06-04: URL is a hardcoded constant — no user/config interpolation.
- T-06-05: Cache read errors degrade gracefully; `read_cache` returns {} on error.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| claude-statusline.py | FOUND |
| tests/test_claude_status.py | FOUND |
| tests/fixtures/status_operational.json | FOUND |
| tests/fixtures/status_incident_tracked.json | FOUND |
| tests/fixtures/status_incident_untracked.json | FOUND |
| tests/fixtures/status_degraded_no_title.json | FOUND |
| tests/fixtures/status_maintenance.json | FOUND |
| tests/fixtures/status_malicious_title.json | FOUND |
| Commit 24b1cfb (RED tests) | FOUND |
| Commit c88b4c1 (Task 1 GREEN) | FOUND |
| Commit 1e46906 (Task 2 GREEN) | FOUND |
| Commit 43a0cc3 (Task 3 GREEN) | FOUND |
| tests/test_claude_status.py (43 tests) | 43 passed |
