---
phase: 08-alert-timing
asvs_level: 1
block_on: high
audited_at: 2026-06-20
auditor: claude-sonnet-4-6
verdict: SECURED
threats_open: 0
threats_total: 6
---

# Phase 8 — Alert Timing: Security Audit

## Result: SECURED

**Threats Closed:** 6/6
**Threats Open:** 0/6
**ASVS Level:** 1
**Block On:** high

---

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-08-01 | Denial of Service | mitigate | `_fmt_alert_time` body wrapped in `try/except Exception: return None` at `claude-statusline.py:2601`. `_fmt_alert_timing` outer guard at `claude-statusline.py:2658`. Both confirmed. Unit tests `test_none_input_returns_none`, `test_garbage_string_returns_none`, `test_int_returns_none` in `TestAlertTimingFormatter` assert None-on-garbage with no exception. |
| T-08-02 | Tampering | accept | Accepted. Timing fragment is assembled only from parsed `datetime` objects via fixed strftime patterns (`%-I:%M %p`, `%a`, `%b`, `%-d`). No raw NWS timestamp string is concatenated into `detail`. Event text is independently sanitized at `claude-statusline.py:3776-3779` (control-char strip + ESC filter + 64-char truncation) before being stored in `safe_event`. The timing splice at L3784-3792 appends only `_fmt_alert_timing` output, which is pure strftime output. Rationale holds. |
| T-08-03 | Denial of Service | mitigate | `.astimezone()` calls on both `dt` and `now` occur at `claude-statusline.py:2580-2581` inside the `try/except Exception: return None` guard that covers the entire `_fmt_alert_time` body. Similarly, `now.astimezone()` and `_parse()` internals in `_fmt_alert_timing` at L2634 and L2630 are covered by the outer `try/except Exception: return None` at L2658. Timezone edge cases that raise `OverflowError`, `OSError`, or `ValueError` are silently suppressed and return None. |
| T-08-04 | Denial of Service | mitigate | Step 3c timing splice at `claude-statusline.py:3786-3794` is wrapped in `try/except Exception: pass` (inner guard, L3786/3793). That block is itself inside the outer alert-override `try/except Exception: pass` at L3756/3801, which nests inside the whole-segment `try/except` at L3641. Three guard layers confirmed. A malformed timestamp causes `_fmt_alert_timing` to return None (inner guard in the function itself) and `if timing_fragment:` prevents any append; the outer `except Exception: pass` catches any unexpected raise from the splice block. Integration tests `test_all_timestamps_null_omits_middot_fragment` and `test_d03a_future_onset_past_ends_omits_fragment` in `TestWeatherSegmentAlertTiming` assert the event renders with no middot fragment on bad/contradictory data. |
| T-08-05 | Tampering | accept | Accepted. The timing fragment (`f" · {timing_fragment}"` at L3792) is the output of `_fmt_alert_timing`, which returns only strftime-produced strings or None. No raw NWS string is placed in `detail` via the timing path. Event text injection vector is separately guarded by the pre-existing sanitization at L3776-3779 (unchanged this phase). No new injection surface introduced. |
| T-08-06 | Information disclosure | accept | Accepted. The only data placed into `detail` from the timing path is the formatted `"from <time>"` / `"until <time>"` string built from `datetime.strftime`. Raw NWS ISO timestamp strings (`onset`, `ends`, `effective`, `expires`) are consumed by `_fmt_alert_timing`'s inner `_parse()` helper and discarded; they never appear in the returned fragment or in `detail`. Oversized or garbage payloads are silently dropped at the `_parse` boundary (`claude-statusline.py:2627-2632`). |

---

## CR-01 Fix Verification

The constraint note flags a CR-01 fix: `_fmt_alert_time` returns None on negative `delta_days`, and `_fmt_alert_timing` omits timing when `end <= now_local` in both branches (active: L2652; upcoming D-03a guard: L2640).

**Raise-path check:** The CR-01 additions introduce no new raise paths.
- `delta_days < 0: return None` at L2586 is a pure integer comparison inside the existing `try/except` — cannot raise.
- `end <= now_local` at L2640 and L2652 compares two tz-aware datetimes; if either is None the enclosing `try/except Exception: return None` at L2658 catches the `TypeError`. No new raise path.

Tests added for CR-01: `test_active_past_end_same_day_returns_none` (L1636), `test_active_past_end_prior_day_returns_none` (L1647), `test_fmt_alert_time_past_date_returns_none` (L1657) — all in `TestAlertTimingFormatter`, no `_WEATHER_OK` guard.

---

## Unregistered Flags

**08-01-SUMMARY.md Threat Flags:** None declared.
**08-02-SUMMARY.md Threat Flags:** None declared.

No unregistered attack surface identified.

---

## Accepted Risk Log

| Threat ID | Rationale |
|-----------|-----------|
| T-08-02 | Timing output is strftime-only; no raw NWS string reaches terminal via this path. Event text has independent sanitization at L3776-3779. |
| T-08-05 | Same rationale as T-08-02. No new injection surface in the timing splice. |
| T-08-06 | Raw timestamp strings are discarded at the `_parse()` boundary inside `_fmt_alert_timing`; only formatted clock text is emitted. |
