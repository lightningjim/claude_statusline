---
phase: 08-alert-timing
reviewed: 2026-06-20T00:00:00Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - claude-statusline.py
  - tests/test_weather_alerts.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 8: Alert Timing — Code Review Report

**Reviewed:** 2026-06-20
**Depth:** deep (cross-function tracing)
**Files Reviewed:** 2 (diff range `5e7f15f..HEAD`)
**Status:** issues_found

## Summary

Phase 8 adds `_fmt_alert_time` and `_fmt_alert_timing` in `claude-statusline.py` (~L2562–2646)
and splices them into `_weather_segment` Step 3c (~L3772–3782). The implementation is
well-structured: pure functions, inner `try/except` guards, `_parse` inner function for
ISO-8601 handling, and D-03a anomaly guard. Test coverage is broad for the formatter
(15 unit tests) and integration (8 tests for `_weather_segment`).

One correctness bug (BLOCKER) was found that violates the omit-not-fake principle: the
active branch of `_fmt_alert_timing` emits `"until <past time>"` for an alert whose `end`
timestamp has already passed — factually incorrect output that can occur within the
`alerts_max_stale` window. Two gaps in test coverage (WARNING) let this bug through and
leave the negative-delta behavior of `_fmt_alert_time` entirely untested. One redundant
`props` re-fetch is noted (WARNING, code quality). One test import style issue is noted
(INFO).

---

## Critical Issues

### CR-01: Active branch emits `"until <past time>"` for expired-but-cached alerts

**File:** `claude-statusline.py:2637–2644`

**Issue:** `_fmt_alert_timing`'s active branch (`else:`) checks only `end is None` before
calling `_fmt_alert_time`. It does NOT check `end <= now_local`. An alert that has already
expired but is still present in the cache (within the 900-second `alerts_max_stale` ceiling)
will produce output like `"until 6:30 AM"` when it is already noon — a factually false
claim that the alert is still active until a past time.

The bug is directly reproducible:
- `start = "2026-06-20T06:00:00Z"` (in past), `end = "2026-06-20T11:30:00Z"` (30 min ago)
- Active branch fires (start <= now). `end` is not None.
- `_fmt_alert_time(end, now_local)` with `delta_days = 0` → returns `"6:30 AM"`.
- Output: `"until 6:30 AM"` at 12:00 — factually wrong.

Compounding issue: `_fmt_alert_time` itself has no guard against negative `delta_days`.
For dates in the past, `delta_days` is negative, and the condition `elif delta_days <= 6`
is True for ALL negative values, so past dates in different calendar days produce
`"<Weekday> at <time>"` (e.g. `"Mon at 3:00 PM"`) rather than `None`. This means:
- Same-day past → `"until 6:30 AM"` (confusingly past)
- Yesterday/last-week past → `"until Mon at 3:00 PM"` (wrong weekday, looks like a future date)

The D-03a anomaly guard in the **upcoming** branch correctly rejects a past `end`. The same
guard is missing from the **active** branch.

This violates the omit-not-fake principle (D-10): an already-expired `end` timestamp is
incoherent for display and must be omitted.

**Fix — `_fmt_alert_timing`, active branch (~L2637):**
```python
        else:
            # Active branch (start is None, or start <= now)
            if end is None or end <= now_local:   # ← add guard: omit if already expired
                return None
            frag = _fmt_alert_time(end, now_local)
            if frag is None:
                return None
            return f"until {frag}"
```

**Fix — `_fmt_alert_time`, branch ladder (~L2581):**

Add a guard for negative `delta_days` so that a past datetime passed by mistake returns
`None` rather than a misleading weekday string:

```python
        if delta_days < 0:
            return None          # past date — caller should not reach here; omit safely
        elif delta_days == 0:
            return time_str
        elif delta_days == 1:
            return f"Tmrw. at {time_str}"
        elif delta_days <= 6:
            weekday = dt_local.strftime("%a")
            return f"{weekday} at {time_str}"
        else:  # >= 7
            month = dt_local.strftime("%b")
            day = dt_local.strftime("%-d")
            return f"{month} {day} at {time_str}"
```

With the `_fmt_alert_timing` fix in place, `_fmt_alert_time` would never be called with a
past `end`; the `_fmt_alert_time` guard is a defense-in-depth safeguard for future callers.

---

## Warnings

### WR-01: No test for active branch with past `end` timestamp (gap that hid CR-01)

**File:** `tests/test_weather_alerts.py` — `TestAlertTimingFormatter`

**Issue:** The test suite covers D-03a (future start, past end → None in the upcoming
branch) but has no test for the symmetric active-branch case: `start` in the past AND
`end` also in the past (stale-cached record). This is the scenario described in CR-01.

The test `test_active_past_start_valid_end_returns_until` always uses a `end` 9 hours in
the future. No test exercises `start` past + `end` past.

**Fix:** Add a unit test to `TestAlertTimingFormatter`:
```python
def test_active_past_start_past_end_returns_none(self):
    """Active alert where end has already passed → None (omit stale expired alert, D-10)."""
    # start 6h ago, end 30min ago — alert is over but still in cache window
    start_raw = "2026-06-20T06:00:00+00:00"
    end_raw   = "2026-06-20T11:30:00+00:00"   # 30 min before noon anchor
    result = self.mod._fmt_alert_timing(start_raw, end_raw, now=self._now_utc)
    self.assertIsNone(result, "Expired-end active alert must omit timing (D-10)")
```

Also add a cross-day past-end variant to cover the negative-delta weekday-arm bug in
`_fmt_alert_time`:
```python
def test_past_dt_in_fmt_alert_time_returns_none(self):
    """_fmt_alert_time with dt in the past returns None (defense-in-depth, not a weekday)."""
    dt = datetime(2026, 6, 17, 15, 0, 0)   # 3 days before now_naive anchor
    result = self.mod._fmt_alert_time(dt, self._now_naive)
    self.assertIsNone(result)
```


### WR-02: `test_all_timestamps_null_omits_middot_fragment` tests an unreachable production state

**File:** `tests/test_weather_alerts.py:1826–1845`

**Issue:** The test builds an alert, then removes its `expires` field
(`alert["properties"].pop("expires", None)`), so all four timing fields are absent. It then
injects this alert directly into the cache `active` list.

In the production pipeline, `dedup_alerts` calls `continue` (skips) on any alert with a
missing or unparseable `expires` field (see `claude-statusline.py:1396–1397`). An alert
with no `expires` would never survive dedup and never appear in the `active` cache.

The test therefore validates render robustness against data that cannot arrive via the real
data path. This is not wrong per se (it's a useful defense-in-depth check), but the test
docstring claims it models a real scenario ("all four timing fields absent") without
acknowledging that `expires`-absent records are pre-filtered. A reader may incorrectly
believe this is a realistic production case.

**Fix:** Clarify the docstring to explain this is a defense-in-depth test against
corrupted/hand-injected cache data, not a scenario producible through the normal NWS fetch
path. Alternatively, restructure to leave `expires` present (far future) and only omit
`onset`/`effective`/`ends` — which is the realistic production scenario for alerts that
lack precise onset/ends data.

```python
def test_onset_effective_ends_all_null_omits_middot_fragment(self):
    """When onset, effective, and ends are all absent but expires is present (realistic
    production state — dedup requires expires), active branch has no end (None), so the
    timing fragment is omitted per D-10."""
    ...
    # Leave expires in place (its presence is required for the alert to survive dedup)
    # Only pop onset/effective/ends
    for field in ("onset", "effective", "ends"):
        alert["properties"].pop(field, None)
```


### WR-03: Redundant `best.get("properties") or best` re-fetch in `_weather_segment` Step 3c

**File:** `claude-statusline.py:3774`

**Issue:** At line 3774, `props_timing = best.get("properties") or best` duplicates the
identical expression already computed at line 3750 as `props`. The variable `props` is in
scope and holds the same value; `props_timing` is unnecessary.

This is not a correctness bug — the result is identical — but the duplication is a
maintenance hazard: if the `properties` extraction idiom ever changes, it must be changed
in two places in the same try block.

**Fix:** Remove `props_timing` and use the already-bound `props`:
```python
                        detail = f"{class_glyph} {safe_event}"
                        # D-01/D-02/D-03: Build and splice timing fragment
                        try:
                            # D-03: start = onset → effective fallback; end = ends → expires fallback
                            start_raw = props.get("onset") or props.get("effective")
                            end_raw   = props.get("ends")  or props.get("expires")
                            timing_fragment = _fmt_alert_timing(start_raw, end_raw)
                            if timing_fragment:
                                detail += f" · {timing_fragment}"
                        except Exception:
                            pass
```

---

## Info

### IN-01: `timedelta` accessed via `__import__("datetime")` in integration tests instead of top-level import

**File:** `tests/test_weather_alerts.py:1750, 1751, 1770, 1771, 1790, 1791, 1809, 1810, 1856, 1858, 1878, 1879, 1913, 1914` (14 occurrences)

**Issue:** The integration tests in `TestWeatherSegmentAlertTiming` compute relative
timestamps using `__import__("datetime").timedelta(hours=N)`. This is an unusual pattern
that works but avoids a standard top-level import. `timedelta` is not in the file's
existing `from datetime import datetime, timezone` import statement, so each use reaches
for `__import__` as a workaround.

This is verbose, visually noisy, and deviates from standard Python idiom.

**Fix:** Add `timedelta` to the existing import at line 29:
```python
from datetime import datetime, timedelta, timezone
```
Then replace all 14 occurrences of `__import__("datetime").timedelta(hours=N)` with
`timedelta(hours=N)`.

---

_Reviewed: 2026-06-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
