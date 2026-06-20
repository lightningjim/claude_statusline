---
phase: 08-alert-timing
fixed_at: 2026-06-20T20:30:00Z
review_path: .planning/phases/08-alert-timing/08-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-06-20T20:30:00Z
**Source review:** .planning/phases/08-alert-timing/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: Redundant `props_timing` variable re-fetches `props` already in scope

**Files modified:** `claude-statusline.py`
**Commit:** 719f09d
**Applied fix:** Removed the `props_timing = best.get("properties") or best` line at
the top of the timing try-block (was L3783). Both `.get("onset")`, `.get("effective")`,
`.get("ends")`, and `.get("expires")` calls in the block now reference `props` directly,
which was already computed at L3759 in the same enclosing try scope. Pure refactor —
no behavior change. `props` was verified to be in scope at the splice point (same
try/except level, assigned at L3759, used at L3784–3785 after fix).

### IN-01: `__import__("datetime").timedelta` anti-pattern repeated in integration tests

**Files modified:** `tests/test_weather_alerts.py`
**Commit:** c4ac3c2
**Applied fix:** Added `timedelta` to the existing module-level import at L29:
`from datetime import datetime, timedelta, timezone`. Replaced all 14 occurrences of
`__import__("datetime").timedelta` in `TestWeatherSegmentAlertTiming` with plain
`timedelta`. (The review listed 13 occurrences but diff shows 14 — the review's count
was off by one; all `__import__` uses are eliminated.) Pure refactor — no behavior
change. The pre-existing local `from datetime import timedelta` inside
`test_fmt_alert_time_past_date_returns_none` at L1659 was left in place (harmless,
not in scope of this finding).

### IN-02: `_fmt_alert_time` has no docstring precondition stating `dt` must be `>= now`

**Files modified:** `claude-statusline.py`
**Commit:** 2711f6f
**Applied fix:** Added a three-line precondition block to the `_fmt_alert_time`
docstring between the output-forms list and the day-arithmetic note. The precondition
states that `dt` must be >= `now`, that past calendar dates return None, and that
same-day-past times are the caller's responsibility to exclude. Docs-only change —
no behavior change.

## Test Results

```
HOME=/tmp/fixverify python3 -m unittest tests.test_weather_alerts
Ran 125 tests in 0.414s
OK (skipped=30)

python3 -m unittest tests.test_weather_alerts.TestAlertTimingFormatter
Ran 25 tests in 0.065s
OK
```

Zero failures, zero regressions.

---

_Fixed: 2026-06-20T20:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
