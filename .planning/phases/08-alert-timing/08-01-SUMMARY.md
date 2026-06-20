---
phase: 08-alert-timing
plan: "01"
subsystem: weather-alerts
tags: [tdd, formatter, datetime, alert-timing]
requires: []
provides: [_fmt_alert_time, _fmt_alert_timing]
affects: [claude-statusline.py, tests/test_weather_alerts.py]
tech_stack:
  added: []
  patterns: [tdd-red-green, naive-datetime-for-portable-tests, omit-not-fake-try-except]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_weather_alerts.py
decisions:
  - Use naive datetimes in _fmt_alert_time tests so display output is system-timezone-portable
  - malformed start in _fmt_alert_timing falls to active branch per D-03 (start None → active)
metrics:
  duration_seconds: 303
  completed: "2026-06-20"
  tasks_completed: 2
  files_modified: 2
requirements_completed: [WX-07, WX-08, WX-09, WX-10]
---

# Phase 8 Plan 1: Alert Timing Formatter Layer Summary

Pure stdlib timing layer for Phase 8: `_fmt_alert_time` (four relative-day arms per WX-10) and `_fmt_alert_timing` (upcoming/active decision with D-03a anomaly guard), both fully tested under system `python3` with no venv.

## Objective

Create the testable core of alert timing: a relative-day time formatter and an upcoming-vs-active decision builder. Plan 02 only splices the resulting fragment into the render site.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| RED | Add failing TestAlertTimingFormatter (22 tests) | 2d05e5c | tests/test_weather_alerts.py |
| GREEN | Implement _fmt_alert_time + _fmt_alert_timing | a76e5a1 | claude-statusline.py, tests/test_weather_alerts.py |

## What Was Built

### `_fmt_alert_time(dt, now)` (claude-statusline.py, after `fmt_reset`)

Pure formatter taking two datetimes; returns a WX-10 string or None:
- Same calendar day → `3:00 PM` (bare 12-hour, uppercase AM/PM, space before AM/PM)
- Next calendar day → `Tmrw. at 3:00 PM`
- 2–6 calendar days → `Tue at 3:00 PM` (abbreviated weekday, no period)
- 7+ calendar days → `Jun 27 at 3:00 PM` (dated form, no leading zero on day)

Uses `%-I:%M %p` (Linux strftime), mirrors `fmt_reset` idioms but diverges on style (uppercase, space before `%p`). Date arithmetic via `(dt_local.date() - now_local.date()).days`. Full body in `try/except Exception: return None` per D-10, T-08-01, T-08-03.

### `_fmt_alert_timing(start_raw, end_raw, now=None)` (claude-statusline.py, below `_fmt_alert_time`)

Takes two raw NWS ISO-8601 strings; returns fragment text without leading separator or None:
- `start > now` → upcoming → `"from " + _fmt_alert_time(start, now)`
  - D-03a guard: if end is None/unparseable/past → None (omit, don't show `from`)
- `start <= now` (or start None) → active → `"until " + _fmt_alert_time(end, now)`
  - If end None/unparseable → None (D-10)
- `now` defaults to `datetime.now().astimezone()` when not passed
- Inner `_parse` helper handles Z-suffix (`replace("Z", "+00:00")`) and malformed strings

### Test class `TestAlertTimingFormatter` (tests/test_weather_alerts.py)

22 tests, no `_WEATHER_OK` guard (pure stdlib functions). Covers:
- All four relative-day arms with exact string assertions
- +6/+7 boundary (6 days → weekday, 7 days → dated)
- None/garbage/int inputs → None for `_fmt_alert_time`
- Upcoming branch, Z-suffix ISO, active branch, equality-to-now
- D-03a: future start + None end, past end, unparseable end → all None
- Active with missing/bad end → None
- Both None, malformed start (falls to active per D-03)

## Verification

```
python3 -m unittest tests.test_weather_alerts.TestAlertTimingFormatter
Ran 22 tests in 0.069s — OK

python3 -m unittest tests.test_weather_alerts
Ran 114 tests in 0.232s — OK (skipped=22, all pre-existing _WEATHER_OK skips)

python3 -c "... print(callable(m._fmt_alert_time), callable(m._fmt_alert_timing))"
True True
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertions used UTC datetimes for `_fmt_alert_time` producing local-time output mismatch**

- **Found during:** GREEN verification (RED committed correctly, test design flaw exposed by run)
- **Issue:** Tests used `datetime(..., tzinfo=timezone.utc)` for `dt` and `now`, but `_fmt_alert_time` calls `.astimezone()` to convert to local time. On CDT (UTC-5) system, `15:00 UTC` displays as `10:00 AM CDT`, not `3:00 PM`. Six tests failed.
- **Fix:** Changed `_fmt_alert_time` tests to use **naive datetimes** (no tzinfo). Python's `.astimezone()` on naive datetimes treats them as local, so `datetime(2026, 6, 20, 15, 0, 0)` always displays as `3:00 PM` regardless of system timezone — making the tests portable. `_fmt_alert_timing` tests retain tz-aware UTC anchors since NWS data always carries explicit offsets.
- **Files modified:** tests/test_weather_alerts.py
- **Commit:** a76e5a1 (combined with GREEN implementation)

**2. [Rule 2 - Spec clarification] `test_malformed_start_returns_none` expectation was incorrect**

- **Found during:** GREEN verification
- **Issue:** Test expected `_fmt_alert_timing("not-a-date", valid_end, ...)` to return `None`. But per D-03: "start None or start <= now → active". A malformed start parses to None → active branch → `until <end>` when end is valid. The test had the wrong expectation.
- **Fix:** Renamed test to `test_malformed_start_falls_to_active_branch`, updated assertion to `startswith("until ")` with a docstring explaining the D-03 active-branch fallthrough. This is correct behavior — a malformed start means we can't determine if it's upcoming, so active branch is safe.
- **Files modified:** tests/test_weather_alerts.py
- **Commit:** a76e5a1

## Known Stubs

None. Both functions are fully implemented with real logic.

## Threat Flags

None. New functions produce only machine-formatted output from parsed `datetime` objects via fixed `strftime` patterns — no raw NWS strings reach output. T-08-01, T-08-02, T-08-03 all mitigated as planned.

## TDD Gate Compliance

- RED gate: `test(08-01)` commit `2d05e5c` — 22 tests, all ERROR (functions absent)
- GREEN gate: `feat(08-01)` commit `a76e5a1` — 22 tests, all pass

## Self-Check: PASSED

- `claude-statusline.py` contains `def _fmt_alert_time(` — FOUND
- `claude-statusline.py` contains `def _fmt_alert_timing(` — FOUND
- `tests/test_weather_alerts.py` contains `class TestAlertTimingFormatter` — FOUND
- RED commit `2d05e5c` — FOUND
- GREEN commit `a76e5a1` — FOUND
- 22 tests pass, 0 fail, 0 error
- Full suite: 114 run, 22 skipped (pre-existing), 0 fail
