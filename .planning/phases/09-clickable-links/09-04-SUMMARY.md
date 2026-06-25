---
phase: 09-clickable-links
plan: "04"
subsystem: weather-links
tags: [osc8, weather, alerts, nws, vte, link-target, gap-closure]
one_liner: "showsigwx link target + FIPS county derivation + VTE>=5000 gate close UAT gaps GAP-09-A and GAP-09-B"
requirements_completed: [LINK-02]

dependency_graph:
  requires:
    - 09-01-SUMMARY.md   # osc8(), _osc8_enabled(), _valid_ugc() foundation
    - 09-02-SUMMARY.md   # _weather_segment OSC 8 integration
  provides:
    - showsigwx link target for weather alerts (warnzone + warncounty)
    - _same_to_county_ugc + _FIPS_STATE_POSTAL helpers
    - VTE_VERSION >= 5000 capability gate
  affects:
    - claude-statusline.py (_osc8_enabled auto branch, _weather_segment Step 3c)
    - tests/test_weather_links.py
    - tests/test_weather_link_target.py (new)
    - tests/test_osc8_links.py

tech_stack:
  added: []
  patterns:
    - FIPS-to-USPS lookup table (Census ANSI FIPS-5-2, stdlib-only)
    - SAME code parsing (P|SS|CCC format, ^[0-9]{6}$ fullmatch)
    - int() version gate with try/except bias-to-False (T-09-05)

key_files:
  created:
    - tests/test_weather_link_target.py  # unit tests for _same_to_county_ugc + _FIPS_STATE_POSTAL
  modified:
    - claude-statusline.py               # _FIPS_STATE_POSTAL, _same_to_county_ugc, _weather_segment, _osc8_enabled
    - tests/test_weather_links.py        # retargeted to showsigwx + no-SAME omit tests

decisions:
  - warncounty required for showsigwx to list alerts; zone-only URL omitted per D-10 (LINK-02)
  - _same_to_county_ugc validates through existing _valid_ugc allowlist — no second regex
  - VTE_VERSION gate threshold 5000 == VTE 0.50 when OSC 8 support landed
  - JetBrains kept in auto allowlist; WR-02 comment documents indistinguishability

metrics:
  duration_minutes: 7
  completed_date: "2026-06-25"
  tasks_completed: 3
  files_modified: 4
---

# Phase 09 Plan 04: Gap Closure — showsigwx Link Target + VTE Gate Summary

showsigwx link target with FIPS county derivation and VTE>=5000 gate closes UAT gaps GAP-09-A (LINK-02) and GAP-09-B (WR-01).

## What Was Built

### Task 1: `_FIPS_STATE_POSTAL` table + `_same_to_county_ugc` helper

Added a 56-entry module-level constant `_FIPS_STATE_POSTAL: dict[str, str]` mapping 2-digit zero-padded state/territory FIPS codes to 2-letter USPS postal codes (50 states + DC + PR/GU/VI/AS/MP). Placed alongside the other OSC 8 / validator constants after `_valid_incident_id`.

Added `def _same_to_county_ugc(same) -> str | None` — a pure, never-raises helper that:
1. Validates SAME to `^[0-9]{6}$` (P|SS|CCC format) — fullmatch before slicing (T-09-04)
2. Extracts state FIPS `SS = same[1:3]`, looks up postal in `_FIPS_STATE_POSTAL`
3. Builds `candidate = f"{postal}C{county}"`
4. Re-validates through the existing `_valid_ugc` allowlist — no second regex

Returns `None` on any bad input (D-10 omit-not-fake): None, empty, non-6-digit, non-numeric, unknown-state FIPS.

New test file `tests/test_weather_link_target.py` covers 21 cases including all success/rejection cases and `_FIPS_STATE_POSTAL` spot-checks.

### Task 2: Weather alert link retargeted to `showsigwx.php` (GAP-09-A / LINK-02)

In `_weather_segment` Step 3c, added county derivation from `geocode.SAME` via `_same_to_county_ugc` (first non-None result from the SAME list). The `_wx_url` is now built **only when both warnzone and warncounty are valid**:

```python
_wx_url = (
    f"https://forecast.weather.gov/showsigwx.php?warnzone={_ugc}&warncounty={_county}"
    if (_ugc and _county) else None
)
```

D-10 (omit-not-fake): if SAME is missing, malformed, or has an unknown state FIPS, `_county` is `None` and `_wx_url` is `None` → `osc8()` returns plain text → zero `\x1b]8` bytes. No zone-only or half URL is ever emitted.

`tests/test_weather_links.py` updated: `_make_alert_with_ugc` extended with `same_list` kwarg; all link-present assertions retargeted to `showsigwx.php`; `test_no_same_no_link`, `test_invalid_same_no_link`, `test_unknown_state_same_no_link` added; `links=off` tests now supply SAME to prove off suppresses a buildable link.

### Task 3: VTE version gate (GAP-09-B / WR-01) + WR-02 comment

In `_osc8_enabled` auto branch, replaced the bare VTE presence check with a version-gated check:

```python
_vte = os.environ.get("VTE_VERSION", "")
try:
    if int(_vte) >= 5000:
        return True
except (TypeError, ValueError):
    pass
```

OSC 8 landed in VTE 0.50 (`VTE_VERSION == 5000`). Pre-5000 (`4604`, `4999`), empty, and non-numeric values bias to `False` and never raise (T-09-05).

Added WR-02 comment on the JetBrains branch explaining that legacy and reworked JediTerm both export `TERMINAL_EMULATOR=JetBrains-JediTerm` and cannot be distinguished via env; kept in allowlist per UAT Test 3.

8 new VTE gate tests added to `tests/test_osc8_links.py` covering `TestOsc8EnabledVteGate`.

## Commits

| Task | Phase | Hash | Message |
|------|-------|------|---------|
| 1 RED | test | 1ea9d81 | test(09-04): add failing tests for _same_to_county_ugc + _FIPS_STATE_POSTAL |
| 1 GREEN | feat | 4d76c4f | feat(09-04): add _FIPS_STATE_POSTAL table + _same_to_county_ugc helper |
| 2 RED | test | 5370de3 | test(09-04): update weather link tests to assert showsigwx target + no-SAME omit |
| 2 GREEN | feat | 4883241 | feat(09-04): re-target weather alert link to showsigwx (GAP-09-A / LINK-02) |
| 3 RED | test | da9946a | test(09-04): add failing VTE>=5000 gate tests + WR-02 JetBrains test |
| 3 GREEN | feat | 01e86a1 | feat(09-04): gate VTE auto-detect on VTE_VERSION>=5000 + WR-02 comment (WR-01) |
| fix | fix | ffe2a2b | fix(09-04): consolidate showsigwx URL onto single line for grep verifiability |

## Verification Results

All three plan test modules pass:

```
tests/test_weather_link_target.py  21 passed
tests/test_weather_links.py        15 passed
tests/test_osc8_links.py           34 passed
```

Full suite: 841 passed, 68 skipped, 284 subtests passed, 2 pre-existing failures (E2E tests that fail inside git worktrees regardless of this plan's changes — confirmed by running against base commit).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test class attribute binding for module function**
- **Found during:** Task 1 GREEN run
- **Issue:** `cls.fn = cls.mod._same_to_county_ugc` caused `self.fn(arg)` to pass `self` as the first argument — Python's descriptor protocol binds `self` to module-level functions assigned as class attributes.
- **Fix:** Wrapped with `staticmethod(cls.mod._same_to_county_ugc)` to prevent binding.
- **Files modified:** `tests/test_weather_link_target.py`
- **Commit:** 4d76c4f

**2. [Rule 1 - Bug] showsigwx URL split across two f-string lines**
- **Found during:** Final verification grep check
- **Issue:** The URL `f"https://forecast.weather.gov/showsigwx.php"\nf"?warnzone=..."` split across two lines meant `grep -c 'showsigwx.php?warnzone='` returned 0.
- **Fix:** Consolidated onto a single f-string line (no behavior change).
- **Files modified:** `claude-statusline.py`
- **Commit:** ffe2a2b

### Plan Verification Discrepancy

The plan's grep check `grep -c 'api.weather.gov/alerts/active' claude-statusline.py` expects 0. However, the NWS data-fetch function (`fetch_active_alerts` at L2382-2387) legitimately uses `https://api.weather.gov/alerts/active?point=lat,lon` to retrieve alert data via GET. This is the data source, not a link target.

The old *link target* (`api.weather.gov/alerts/active?zone=...`) has been fully removed from the link-building code. The functional requirement is satisfied: `test_old_api_target_absent` passes (rendered segments never contain the old URL). The grep check cannot be satisfied at 0 without removing the fetch endpoint, which would break alert retrieval.

## Known Stubs

None.

## Threat Flags

No new security-relevant surface introduced beyond what was already in the plan's threat model.

## Self-Check: PASSED

- `tests/test_weather_link_target.py`: FOUND
- `tests/test_weather_links.py`: FOUND (modified)
- `tests/test_osc8_links.py`: FOUND (modified)
- `claude-statusline.py`: FOUND (contains `_FIPS_STATE_POSTAL`, `_same_to_county_ugc`, `showsigwx.php?warnzone=`, VTE gate)
- Commits 1ea9d81/4d76c4f/5370de3/4883241/da9946a/01e86a1/ffe2a2b: all present in git log
