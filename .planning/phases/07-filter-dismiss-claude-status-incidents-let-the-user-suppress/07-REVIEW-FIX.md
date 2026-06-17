---
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
fixed_at: 2026-06-17T00:00:00Z
review_path: .planning/phases/07-filter-dismiss-claude-status-incidents-let-the-user-suppress/07-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-06-17
**Source review:** .planning/phases/07-filter-dismiss-claude-status-incidents-let-the-user-suppress/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (Critical + Warning; 2 Info findings out of scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: Dead-code branch in `_is_suppressed` — redundant `isinstance` after guard

**Files modified:** `claude-statusline.py`
**Commit:** 8a4614d
**Applied fix:** Removed the permanently-dead `if isinstance(cfg, dict) else {}` conditional expression at line 1632. After the preceding guard (`if not isinstance(cfg, dict): cfg = {}`), `cfg` is always a dict, so the call is now an unconditional `cfg.get("claude_status")` with a clarifying comment. The existing `if not isinstance(claude_status_cfg, dict)` normalization below it is preserved, so the bad-`claude_status` case is still handled.

### WR-02: Escalation integration test does not distinguish incident re-surface from Rule 3 fallback

**Files modified:** `tests/test_claude_status.py`
**Commit:** bd9efbc
**Applied fix:** Strengthened `TestDeriveClaudeStatusFilterIntegration.test_escalation_resurfaces_id_dismissed_incident`. Added `assertEqual(result.get("kind"), "incident", ...)` to prove the re-surfaced result is the incident itself and not a Rule 3 `kind="degraded"` fallback on the `partial_outage` component, plus `assertEqual(result.get("severity"), "major", ...)` to confirm the escalated impact is carried. Verified against `claude-statusline.py`: `_CLAUDE_IMPACT_SEVERITY["major"] == "major"`, so the severity assertion is correct for the `inc-001` fixture (impact `major`). Ran the single test — passes.

### WR-03: Prune uses all-incidents list; `--status-incidents` shows dismissed-resolved incidents as "stale"

**Files modified:** `claude-statusline.py`
**Commit:** 1e0379d
**Applied fix:** In `fetch_claude_status`, the `live_ids` build loop now skips any incident whose `status` is not in `("investigating", "identified", "monitoring")`, matching the filter used by `_collect_tracked_incidents`. This makes the auto-prune fire as soon as a dismissed incident resolves (rather than waiting days for Statuspage.io to drop it from the feed), so the dismissal store no longer retains entries that `--status-incidents` already reports as stale. Followed the existing inline-tuple convention used in three other call sites rather than introducing a new module-level constant. The full 199-test module passes.

**Note (requires human verification):** WR-03 changes prune/retention behavior (a logic change). Syntax and the full unit-test suite pass, but a developer should confirm the new prune timing matches the intended UX before the phase advances to verification.

---

_Fixed: 2026-06-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
