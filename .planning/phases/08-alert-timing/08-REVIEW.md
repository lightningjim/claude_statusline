---
phase: 08-alert-timing
reviewed: 2026-06-20T20:04:10Z
depth: deep
files_reviewed: 2
files_reviewed_list:
  - claude-statusline.py
  - tests/test_weather_alerts.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 8: Alert Timing — Code Review Report (Re-review)

**Reviewed:** 2026-06-20T20:04:10Z
**Depth:** deep
**Files Reviewed:** 2 (`git diff 5e7f15f..HEAD`)
**Status:** issues_found (0 critical, 1 warning, 2 info)

## Summary

This is the adversarial re-review of the Phase 8 implementation after the
earlier CR-01 fix was applied. Scope is `_fmt_alert_time` and
`_fmt_alert_timing` (~L2562–2655), the timing splice in `_weather_segment`
Step 3c (~L3781–3791), and the two new test classes
(`TestAlertTimingFormatter`, `TestWeatherSegmentAlertTiming`).

**CR-01 is confirmed resolved.** Both guards are present and correct:

- `_fmt_alert_time` L2582: `if delta_days < 0: return None` — guards against
  past calendar dates returning a misleading weekday string.
- `_fmt_alert_timing` active branch L2648: `if end is None or end <= now_local: return None`
  — omits timing when the hazard end has already passed.
- `_fmt_alert_timing` upcoming D-03a L2636: `if end is None or end <= now_local: return None`
  — anomaly guard for contradictory stale records.

All three comparisons are tz-aware (`now_local = now.astimezone()`, both `start`
and `end` are `_parse()`-returned tz-aware datetimes). No path exists that emits
a past time. The runtime contract is preserved — no I/O, no blocking, pure
computation only.

One warning (redundant variable) and two info items (test import style,
missing docstring precondition) were found. After the adversarial refutation
pass, none of the three rise to BLOCKER.

---

## Warnings

### WR-01: Redundant `props_timing` variable re-fetches `props` already in scope

**File:** `claude-statusline.py:3783`

**Issue:** Line 3783 computes `props_timing = best.get("properties") or best`
inside the timing try-block. An identical expression was already computed four
lines earlier as `props = best.get("properties") or best` (L3759), and `props`
is in scope at L3783. Both variables reference the same dict object (Python
returns the same reference; no copy is made). The redundant re-fetch is not a
correctness bug but it carries two maintenance costs:

1. If the `"properties"` extraction idiom changes (e.g., a helper is introduced),
   there are now two call sites in the same function that must be updated in tandem.
2. A reviewer reading L3785–3786 sees `props_timing.get("onset")` and must
   backtrack to L3783 to confirm it is the same dict as `props` — unnecessary
   cognitive overhead.

The inner `try/except` at L3782 also adds an extra exception layer around code
that is already protected by the outer `try/except` at L3752/3798. The inner
layer is not harmful, but it obscures that `props.get()` on a known-good dict
(guarded by L3759's outer block) cannot raise.

**Fix:** Remove `props_timing`; use `props` directly:

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
                            pass  # timing parse failed → omit silently (D-10)
```

---

## Info

### IN-01: `__import__("datetime").timedelta` anti-pattern repeated 13 times in integration tests

**File:** `tests/test_weather_alerts.py:1777` (and L1778, 1797, 1798, 1817,
1818, 1836, 1837, 1883, 1885, 1905, 1906, 1940, 1941 — 13 total occurrences)

**Issue:** `TestWeatherSegmentAlertTiming` computes relative timestamps via
`__import__("datetime").timedelta(hours=N)`. The idiom is correct — `__import__`
returns the `datetime` module and `.timedelta` retrieves the class — but it is
unusual. `__import__` is the primitive underlying `import` statements; its
conventional use is for dynamic/conditional imports and plugin loading, not as a
substitute for a forgotten top-level import. Readers will pause to verify no
side-effect is intended.

The `from datetime import datetime, timezone` import on L29 does not include
`timedelta`. Rather than adding it, the author worked around the omission with
`__import__`. The one counter-example in the same file (`from datetime import
timedelta` as a local import inside `test_fmt_alert_time_past_date_returns_none`
at L1659) shows the clean pattern was available.

**Fix:** Add `timedelta` to the existing module-level import at L29:

```python
# Before:
from datetime import datetime, timezone

# After:
from datetime import datetime, timedelta, timezone
```

Then replace all 13 `__import__("datetime").timedelta(hours=N)` occurrences
with `timedelta(hours=N)`.

---

### IN-02: `_fmt_alert_time` has no docstring precondition stating `dt` must be `>= now`

**File:** `claude-statusline.py:2562`

**Issue:** `_fmt_alert_time` guards against past calendar dates via
`if delta_days < 0: return None`. However, it does not guard against a datetime
that falls on today's calendar date but earlier than `now` (e.g., `now = 3:00 PM`,
`dt = 1:00 PM` same day → `delta_days == 0` → returns `"1:00 PM"`, a past time).

In the current codebase this cannot surface in production: both call sites in
`_fmt_alert_timing` are gated by `end > now_local` or `start > now_local` before
the call, so `_fmt_alert_time` never receives a same-day-past datetime. But the
function's docstring documents only the four output forms and the "returns None on
error" behavior — it does not state the `dt >= now` precondition that callers must
satisfy to avoid a same-day-past-time string.

An independent future caller reading only the docstring could pass a past same-day
datetime and receive a misleading time string with no warning.

**Fix:** Add a precondition note to the docstring:

```python
def _fmt_alert_time(dt, now) -> str | None:
    """Format a tz-aware datetime as a WX-10 relative-day time string.

    Returns one of four forms:
      - Same calendar day   → '3:00 PM'         (bare 12-hour time, uppercase AM/PM)
      - Next calendar day   → 'Tmrw. at 3:00 PM'
      - 2–6 days ahead      → 'Wed at 3:00 PM'   (abbreviated weekday, no period)
      - 7+ days ahead       → 'Jul 3 at 3:00 PM' (dated form, no leading zero on day)

    Precondition: `dt` must be >= `now` (in the future or at least today-future).
    Past calendar dates return None; same-day-past times are the caller's responsibility
    to exclude — this function does not guard against them.

    Day arithmetic is by calendar-date delta (not 24h windows), per D-05.
    Returns None on any error / non-datetime input — omit-not-fake (D-10, T-08-01).
    """
```

---

## CR-01 Resolution Verification (Required by Review Brief)

All three CR-01 guards confirmed present and correct in the committed code:

| Guard | Location | Code | Correct? |
|---|---|---|---|
| Past date in `_fmt_alert_time` | L2582 | `if delta_days < 0: return None` | Yes |
| Active branch past-end | L2648 | `if end is None or end <= now_local: return None` | Yes |
| Upcoming D-03a past-end | L2636 | `if end is None or end <= now_local: return None` | Yes |

Regression tests `test_active_past_end_same_day_returns_none` (L1636) and
`test_active_past_end_prior_day_returns_none` (L1648) in `TestAlertTimingFormatter`
cover both same-day and cross-day past-end scenarios for the active branch.
`test_d03a_future_start_past_end_returns_none` (L1608) covers the upcoming D-03a
guard. The `delta_days < 0` guard in `_fmt_alert_time` is covered by
`test_fmt_alert_time_past_date_returns_none` (L1658). CR-01 is fully resolved.

---

_Reviewed: 2026-06-20T20:04:10Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
