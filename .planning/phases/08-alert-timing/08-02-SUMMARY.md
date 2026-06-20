---
phase: 08-alert-timing
plan: "02"
subsystem: weather-alerts
tags: [render, alert-timing, integration-test, splice]
requires: [_fmt_alert_time, _fmt_alert_timing]
provides: [timing-splice-in-_weather_segment, TestWeatherSegmentAlertTiming]
affects: [claude-statusline.py, tests/test_weather_alerts.py]
tech_stack:
  added: []
  patterns: [try-except-omit-not-fake, props-guard-idiom, relative-timestamp-tests]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_weather_alerts.py
decisions:
  - Pass no `now` argument to _fmt_alert_timing at the call site (now in _weather_segment is a float unix timestamp; _fmt_alert_timing defaults to datetime.now().astimezone() when now=None)
  - Re-read props from best as props_timing to be explicit rather than reusing the outer props variable (avoids coupling to surrounding scope order)
metrics:
  duration_seconds: 900
  completed: "2026-06-20"
  tasks_completed: 2
  files_modified: 2
requirements_completed: [WX-07, WX-08, WX-09, WX-10]
---

# Phase 8 Plan 2: Alert Timing Render Splice Summary

Spliced the Plan 01 timing formatter into the `_weather_segment` Step 3c render path: the primary weather alert now shows `{glyph} {event} · from <time>` or `{glyph} {event} · until <time>` in the class color, with the tally trailing, and all fallback/omit-not-fake guards in place.

## Objective

Wire the `_fmt_alert_timing` function (built in Plan 01) into the live render path so the timing fragment is visible on the statusline. Add integration tests that call `_weather_segment` end-to-end to prove all branches work.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Splice _fmt_alert_timing into _weather_segment Step 3c | ab24630 | claude-statusline.py |
| 2 | Integration render tests for alert timing | a8ee49a | tests/test_weather_alerts.py |

## What Was Built

### Timing splice in `_weather_segment` Step 3c (claude-statusline.py, L3772-3782)

Inserted between `detail = f"{class_glyph} {safe_event}"` and the tally append:

```python
# D-01/D-02/D-03: Build and splice timing fragment
try:
    props_timing = best.get("properties") or best
    # D-03: start = onset -> effective fallback; end = ends -> expires fallback
    start_raw = props_timing.get("onset") or props_timing.get("effective")
    end_raw   = props_timing.get("ends")  or props_timing.get("expires")
    timing_fragment = _fmt_alert_timing(start_raw, end_raw)
    if timing_fragment:
        detail += f" · {timing_fragment}"
except Exception:
    pass  # timing parse failed -> omit silently (D-10)
```

The `trailing_detail = f"{color}{detail}{RESET}"` line at L3788 is unchanged — timing inherits the class color (D-01). The middot U+00B7 ` · ` is the separator between event and timing (D-02). Render order: `{glyph} {event} · {from|until <time>}  {tally}` (D-02). Timing on primary only (D-04).

**Call site note:** `_fmt_alert_timing` is called without `now=` because `now` in `_weather_segment` is a float Unix timestamp (`_time.time()`), not a datetime. The function defaults `now=None` to `datetime.now().astimezone()` internally, which is correct.

### `TestWeatherSegmentAlertTiming` class (tests/test_weather_alerts.py, appended after TestAlertTimingFormatter)

8 integration tests calling `_weather_segment` end-to-end via `_run_segment` helper:

| Test | What it proves |
|------|----------------|
| `test_upcoming_alert_renders_from_fragment` | onset 2h future -> `· from ` present, `until` absent |
| `test_active_alert_renders_until_fragment` | onset 1h past, ends 2h future -> `· until ` present, `from` absent |
| `test_fallback_effective_used_when_onset_null` | onset absent, effective 2h future -> `· from ` renders (WX-08) |
| `test_fallback_expires_used_when_ends_null` | ends absent, expires 3h future -> `· until ` renders (WX-09) |
| `test_all_timestamps_null_omits_middot_fragment` | all four timing fields absent -> event renders, no `· ` (D-10) |
| `test_d03a_future_onset_past_ends_omits_fragment` | onset future + ends past -> no `· ` (D-03a anomaly guard) |
| `test_d04_timing_only_on_primary_alert` | 2 alerts -> `· ` appears at most once; Watch tally glyph present (D-04) |
| `test_timing_falls_between_event_and_tally` | middot position < tally position in plain output (D-02 order) |

All 8 skip cleanly under system python3 with the `_WEATHER_OK` guard.

## Verification

```
python3 -c "...import ok..." -> import ok
grep -c "_fmt_alert_timing(" claude-statusline.py -> 2
python3 -m unittest tests.test_weather_alerts -> Ran 122 tests in 0.205s -- OK (skipped=30)
python3 -m unittest tests.test_weather_alerts.TestWeatherSegmentAlertTiming -v -> Ran 8 tests -- OK (skipped=8)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `now` variable in `_weather_segment` is a float, not a datetime**

- **Found during:** Task 1 implementation
- **Issue:** The plan instructs calling `_fmt_alert_timing(start_raw, end_raw, now=now)` and notes that "now is already in scope". However, the `now` variable at L3646 in `_weather_segment` is `_time.time()` — a Unix float. `_fmt_alert_timing` calls `now.astimezone()` at L3625, which would raise `AttributeError: 'float' object has no attribute 'astimezone'`.
- **Fix:** Omit the `now=` argument. `_fmt_alert_timing` defaults `now=None` to `datetime.now().astimezone()` internally, which is the correct behavior. The result is functionally identical since both evaluate the current local time at render.
- **Files modified:** claude-statusline.py (the call site uses `_fmt_alert_timing(start_raw, end_raw)`)
- **Commit:** ab24630

## Known Stubs

None. The timing splice calls `_fmt_alert_timing` with real NWS CAP properties; no placeholder values.

## Threat Flags

None. The splice passes raw NWS ISO-8601 strings into `_fmt_alert_timing`, which parses them internally and produces only machine-formatted strftime output. No raw NWS strings reach the terminal. T-08-04 (DoS) mitigated: the splice is in `try/except Exception: pass`. T-08-05 (injection) mitigated: event text already sanitized at L3762-3766; timing fragment is strftime output only.

## Self-Check: PASSED

- `claude-statusline.py` contains `_fmt_alert_timing(start_raw, end_raw)` call at L3778 -- FOUND
- `tests/test_weather_alerts.py` contains `class TestWeatherSegmentAlertTiming` -- FOUND
- Task 1 commit `ab24630` -- FOUND
- Task 2 commit `a8ee49a` -- FOUND
- `import ok` -- PASSED
- `grep -c "_fmt_alert_timing("` = 2 -- PASSED
- Full suite: 122 tests run, 30 skipped, 0 failures -- PASSED
