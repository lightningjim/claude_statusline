---
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
plan: "04"
subsystem: claude-status-render
tags: [render-time-suppression, dismiss, filter, uat-gap-closure, tdd, never-crash]
gap_closure: true

dependency_graph:
  requires: [07-01, 07-02, 07-03]
  provides:
    - "Render-time suppression in _claude_status_segment reusing _is_suppressed over cached tracked_incidents + live dismissal store + cfg patterns"
    - "Corrected _DISMISS_REFRESH_NOTE (no longer claims --refresh required)"
    - "TestClaudeStatusRenderSuppression unit tests proving instant suppression, escalation re-surface, and never-crash"
  affects:
    - "claude-statusline.py:_claude_status_segment"

tech_stack:
  added: []
  patterns:
    - "Render-time re-application of existing suppression function (REUSE not fork)"
    - "Dismissal store read at render: local JSON, fail-safe, wrapped in try/except"
    - "Override variables (_severity_override / _label_override / _kind_override) to cleanly separate baked vs. surviving-incident paths"

key_files:
  created: []
  modified:
    - "claude-statusline.py"
    - "tests/test_claude_status.py"

decisions:
  - "RENDER-TIME SUPPRESSION (user-decided 2026-06-17): re-apply _is_suppressed at render time in _claude_status_segment; REUSE the single suppression ordering — no fork"
  - "_DISMISS_REFRESH_NOTE: replaced stale --refresh claim with truthful 'very next render, no --refresh required' message"
  - "No other user-facing help text repeated the stale --refresh claim"

metrics:
  duration: "15 min"
  completed: "2026-06-17"
  tasks_completed: 3
  files_modified: 2
  tests_added: 9
  test_count_before: 190
  test_count_after: 199
---

# Phase 07 Plan 04: Render-Time Suppression (UAT Gap Closure) Summary

**One-liner:** Render-time suppression layered on `_claude_status_segment` reusing `_is_suppressed` so `--dismiss` and `ignore_title_patterns` take effect on the very next bar render — zero network, lock-independent, instant.

## Objective

Close the single UAT gap on Phase 07: `--dismiss <id>` (and `ignore_title_patterns`) were only effective at FETCH time (baked into the cache by `_derive_claude_status`), not RENDER time. The render path `_claude_status_segment` read the baked `noteworthy`/`label` values and never re-applied the filter, so local-only actions could not take effect until a fresh NETWORK fetch. Manual `--refresh` was unreliable under the stampede lock. The misleading help text claimed `--refresh` was the fix.

## What Was Done

### Task 1 — Render-time suppression in `_claude_status_segment`

Added Step 3b in `_claude_status_segment` (after the noteworthy gate, before Step 4):

1. **Reads live dismissal store**: `read_dismissals(_DISMISSALS_PATH)` — cheap local JSON read, fail-safe (exception → `{}`).
2. **Reads `sec["tracked_incidents"]`** — non-list treated as empty.
3. **Re-runs `_is_suppressed`** over each cached incident in list order (same order `_collect_tracked_incidents` produced). First non-suppressed incident drives the segment.
4. **Decides render outcome**:
   - All suppressed → `return None` (instant mute, D-01)
   - Surviving incident found → recompute severity/label/kind from its live cached fields
   - Empty `tracked_incidents` (maintenance/degraded) → fall through to baked values unchanged

The implementation strictly REUSES `_is_suppressed` — the single suppression ordering (see `:1556`). D-03 escalation re-surface is honored automatically because `_is_suppressed` compares the live impact (from cached incident) against `impact_at_dismiss`. The entire block is inside the existing function `try/except → None`, so any failure degrades to baked behavior or `None` without raising (D-10). No network I/O, no new locks.

**Commit:** `7ab3cf5`

### Task 2 — Correct `_DISMISS_REFRESH_NOTE`

Replaced the stale confirmation text:
- Before: `"Note: change takes effect on the bar at the next status refresh (cache TTL ~5 min); run --refresh to apply it immediately."`
- After: `"Note: change takes effect on the bar at the very next render (no --refresh required)."`

Scanned for other occurrences of the stale claim in the file — none found beyond `_DISMISS_REFRESH_NOTE`.

**Commit:** `8b26eda`

### Task 3 — Unit tests: `TestClaudeStatusRenderSuppression`

Added 9 tests to `tests/test_claude_status.py` (class `TestClaudeStatusRenderSuppression`). Both `_CACHE_PATH` and `_DISMISSALS_PATH` are patched to temp paths; no real `~/.claude` paths touched; no network I/O.

| Test | Behavior Proven |
|------|----------------|
| `test_dismiss_by_id_suppresses_at_render` | Dismissed id at matching impact → `None` (instant mute, D-01) |
| `test_keyword_suppresses_at_render` | `ignore_title_patterns` match → `None` at render |
| `test_escalation_resurfaces_at_render` | Dismissed at minor, live major → D-03 re-surface (non-None) |
| `test_unrelated_incident_still_lights` | Un-dismissed incident always surfaces |
| `test_healthy_still_omits` | `noteworthy=False` → `None` regardless of dismissal store (D-01) |
| `test_cold_cache_still_omits` | Absent/stale cache → `None` (D-01) |
| `test_render_never_raises_on_malformed` | Bad `tracked_incidents` + corrupt store → never raises (D-10) |
| `test_maintenance_baked_behavior_unchanged` | Maintenance baked section renders unchanged (not suppressed) |
| `test_second_incident_surfaces_when_first_dismissed` | Fall-through to next incident works correctly |

**Commit:** `6a23d87`

## Verification

```
python -m unittest tests.test_claude_status -v
Ran 199 tests in 0.240s
OK

python -m unittest discover -s tests -v
Ran 740 tests in 12.468s
OK (skipped=60)

grep -n "_is_suppressed\|read_dismissals" claude-statusline.py | grep "3[56789][0-9][0-9]\|36[0-9][0-9]"
3576:            dismissals = read_dismissals(_DISMISSALS_PATH)
3602:                if not _is_suppressed(inc_id_rt, inc_impact, inc_title, dismissals, _cfg):

grep -q "run --refresh to apply it immediately" claude-statusline.py || echo "OK: stale claim removed"
OK: stale claim removed
```

## Deviations from Plan

None — plan executed exactly as written. The implementation logic (Step 3b with `_severity_override`/`_label_override`/`_kind_override` variables) is a clean factoring that avoids any repeated `sec.get(...)` calls and makes the baked-vs-surviving-incident paths explicit.

An additional test (`test_second_incident_surfaces_when_first_dismissed`) was added beyond the 8 specified in the plan — this tests the fall-through behavior (two tracked incidents, first dismissed, second surfaces) which is implied by the plan's spec but not explicitly listed as its own test. This is a Rule 2 addition for completeness.

## Known Stubs

None — all logic is fully wired. The render-time suppression uses the live dismissal store and live cached `tracked_incidents` from the real cache path.

## Threat Flags

No new trust boundaries introduced. The dismissal store was already read on the `--dismiss`/`--status-incidents` CLI paths; reading it on the render path adds no new attack surface. Trust boundaries audited:

| Boundary | Mitigated by |
|----------|-------------|
| Corrupt dismissal store on render | `read_dismissals()` returns `{}` on any error; render block wraps in try/except (T-07-04-02) |
| Malformed `tracked_incidents` in cache | Non-list → empty; per-item `.get()` null-safe; function try/except → None (T-07-04-03) |
| ReDoS via user patterns | Reuses `_is_suppressed` which applies the 500-char cap before any match (T-07-04-01) |
| Escalation hidden by mute | D-03: `_is_suppressed` uses live impact vs `impact_at_dismiss`; escalations always re-surface (T-07-04-04) |

## Self-Check: PASSED

- `claude-statusline.py` modified with render-time suppression: FOUND
- `tests/test_claude_status.py` modified with TestClaudeStatusRenderSuppression: FOUND
- Commit `7ab3cf5` (Task 1): EXISTS
- Commit `8b26eda` (Task 2): EXISTS
- Commit `6a23d87` (Task 3): EXISTS
- 199 claude_status tests pass: VERIFIED
- 740 total tests pass (60 skipped): VERIFIED
- `_is_suppressed(` and `read_dismissals(` inside `_claude_status_segment`: VERIFIED (lines 3576, 3602)
- Stale `--refresh` claim removed: VERIFIED
