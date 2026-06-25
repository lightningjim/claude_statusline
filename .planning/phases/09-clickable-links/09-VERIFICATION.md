---
phase: 09-clickable-links
verified: 2026-06-25T00:00:00Z
status: passed
human_resolution: skip-accepted
status_history: [human_needed (2026-06-25), passed (2026-06-25, human item skip-accepted via /gsd:verify-work)]
score: 6/6 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 3/3
  gaps_closed:
    - "GAP-09-A (LINK-02): weather alert link now opens forecast.weather.gov/showsigwx.php?warnzone={zone}&warncounty={county} instead of raw CAP JSON at api.weather.gov/alerts/active?zone="
    - "GAP-09-B (WR-01): _osc8_enabled auto branch now gates VTE on int(VTE_VERSION) >= 5000 with defensive try/except; pre-5000, empty, and non-numeric values bias to False and never raise"
    - "WR-02 (doc-only): JetBrains branch in _osc8_enabled now carries an explanatory comment distinguishing legacy vs reworked JediTerm indistinguishability"
  gaps_remaining: []
  regressions: []
human_verification_resolution:
  resolved_via: "/gsd:verify-work 09 (2026-06-25)"
  outcome: skipped-with-reason — risk accepted by user
  rationale:
    - "No active NWS weather alert available to click during testing."
    - "showsigwx page rendering already verified live during GAP-09-A diagnosis (CAZ373 + CAC037 → populated WWA page)."
    - "OSC 8 click mechanism confirmed live in original UAT Test 3 (LINK-03) in the PyCharm terminal."
    - "URL construction (warnzone + SAME-derived warncounty) and omit-not-fake fully covered by automated tests (70 passing)."
    - "User assessment: 'links were working before this so most likely [fine]'."
human_verification:
  - test: "With an active NWS weather alert in a supporting terminal (links='on' or links='auto' + known terminal), click the alert text (glyph + event + timing)."
    expected: "The NWS 'WWA Summary by Location' page at https://forecast.weather.gov/showsigwx.php?warnzone={zone}&warncounty={county} opens in a browser and lists the active alert(s) for that location. The page must be human-readable — not an error page, 404, or empty alert list."
    why_human: "Automated tests verify that the URL string is correctly formed with both warnzone and warncounty; they cannot verify that the live NWS showsigwx.php endpoint actually serves a populated, readable page. The warncounty derivation from geocode.SAME has been unit-tested against known-good FIPS codes (LA, OK, TX), but NWS zone/county data combinations in the real feed are the only true end-to-end proof."
---

# Phase 09: Clickable Links Verification Report (Re-verification)

**Phase Goal:** Status events and weather alerts are clickable hyperlinks in terminals that support OSC 8, with no visible escape-sequence noise in terminals that do not.
**Verified:** 2026-06-25T00:00:00Z
**Status:** passed (human item skip-accepted — see Human Verification Resolution below)
**Re-verification:** Yes — after Plan 09-04 gap closure (GAP-09-A, GAP-09-B, WR-02)

## Gap Closure Summary

Plan 09-04 targeted three items from the Human UAT (`09-HUMAN-UAT.md`):

| Gap | Severity | Closed? | Evidence |
|-----|----------|---------|---------|
| GAP-09-A (LINK-02): alert link opened raw CAP JSON | minor | YES | `showsigwx.php?warnzone=` at L4081; old `?zone=` target absent from link-building code; 15 tests pass |
| GAP-09-B (WR-01): VTE gate not versioned | minor | YES | `int(_vte) >= 5000` with `try/except` at L294-299; 8 new VTE gate tests pass |
| WR-02 (doc-only): JetBrains comment | won't-fix | YES | WR-02 comment present at L300-304; behavior unchanged |

## Goal Achievement

### Observable Truths (09-04 must-haves)

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Clicking a weather alert opens `forecast.weather.gov/showsigwx.php` (human-readable NWS WWA page), not raw CAP JSON | VERIFIED | `_wx_url = f"https://forecast.weather.gov/showsigwx.php?warnzone={_ugc}&warncounty={_county}"` at L4080-4082. `grep -c 'showsigwx.php?warnzone=' claude-statusline.py` = 1. Old `api.weather.gov/alerts/active?zone=` pattern: 0 occurrences in link-building code. |
| 2 | Weather link contains BOTH warnzone (zone UGC) AND warncounty (county derived from geocode.SAME); URL only built when both are valid | VERIFIED | `if (_ugc and _county) else None` at L4082 gates the URL on both. `_same_to_county_ugc` called in a loop over `_geocode.get("SAME")` at L4068-4073. |
| 3 | `_same_to_county_ugc("006037") == "CAC037"` and `_same_to_county_ugc("040109") == "OKC109"` | VERIFIED | `tests/test_weather_link_target.py::TestSameToCountyUgc::test_ca_los_angeles` and `::test_ok_oklahoma_county` pass. TX Harris County (`048201` → `TXC201`) also confirmed. 21 tests in `TestSameToCountyUgc` all pass. |
| 4 | When alert has no usable SAME (missing, empty, bad FIPS, unknown state, or derived county fails `_valid_ugc`), alert renders as plain text with zero `\x1b]8` bytes (D-10 omit-not-fake) | VERIFIED | `_same_to_county_ugc` returns `None` on all bad input paths; `_wx_url = None`; `osc8(…, None, …)` returns plain text. `test_no_same_no_link`, `test_invalid_same_no_link`, and `test_unknown_state_same_no_link` all pass. |
| 5 | Under `links="auto"`, VTE gets OSC 8 only when `VTE_VERSION >= 5000`; pre-5000, empty, and non-numeric values yield False and never crash | VERIFIED | `_vte = os.environ.get("VTE_VERSION", "")` → `try: if int(_vte) >= 5000: return True except (TypeError, ValueError): pass` at L294-299. `TestOsc8EnabledVteGate` (8 tests): 5000 → True, 6800 → True, 4604 → False, 4999 → False, "" → False, unset → False, "garbage" → False (no exception). All 8 pass. |
| 6 | The per-class tally (`+N`) remains outside the OSC 8 link span (D-06); `links="off"` with full UGC+SAME emits zero `\x1b]8` bytes (LINK-03 preserved) | VERIFIED | `linkable = osc8(f"{color}{detail}{RESET}", _wx_url, enabled=_links_enabled)` at L4088; tally appended after (`_trailing_detail = linkable + tally`). `test_tally_outside_link_span`, `test_links_off_no_osc8_bytes`, `test_links_off_byte_identical_to_plain` all pass. |

**Score:** 6/6 must-haves verified

### Phase-Level Requirement Truths (regression check)

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| LINK-01 | Claude Status incidents render as OSC 8 hyperlinks to the relevant status.claude.com incident page | VERIFIED (no regression) | `test_status_links.py` 21 tests still pass; plan 09-04 did not touch `_claude_status_segment`. |
| LINK-02 | Weather alerts render as OSC 8 hyperlinks to the NWS human-readable alert page | VERIFIED (gap closed) | `showsigwx.php?warnzone={zone}&warncounty={county}` is now the link target. Old raw-JSON target gone. |
| LINK-03 | Hyperlinks degrade to plain text where OSC 8 is unsupported/config-off; no stray escape bytes | VERIFIED (no regression) | `osc8()` contract unchanged; `test_links_off_no_osc8_bytes` passes in both weather and status test modules. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-statusline.py` | `_FIPS_STATE_POSTAL` table, `_same_to_county_ugc`, `showsigwx.php` URL template, VTE>=5000 gate, WR-02 comment | VERIFIED | `_FIPS_STATE_POSTAL` at L369 (56 entries). `_same_to_county_ugc` at L430. `showsigwx.php?warnzone=` at L4081 (1 occurrence). VTE gate at L294-299. WR-02 comment at L300-304. |
| `tests/test_weather_link_target.py` | Unit tests for `_same_to_county_ugc` and `_FIPS_STATE_POSTAL` table coverage | VERIFIED | Exists. `TestSameToCountyUgc`: 21 tests (all success/rejection cases + table spot-checks for CA/OK/TX/DC/PR/GU/VI/AS/MP). All 21 pass. |
| `tests/test_weather_links.py` | Integration tests asserting showsigwx URL + omit-not-fake on missing/bad SAME | VERIFIED | Updated. 15 tests pass. Includes `test_no_same_no_link`, `test_invalid_same_no_link`, `test_unknown_state_same_no_link`. All link-present assertions target `showsigwx.php`. `test_old_api_target_absent` confirms rendered output never contains `api.weather.gov/alerts/active`. |
| `tests/test_osc8_links.py` | VTE>=5000 gate tests added (`TestOsc8EnabledVteGate`) | VERIFIED | 34 tests total (original 26 + 8 new). `TestOsc8EnabledVteGate` present with 8 cases. All 34 pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_weather_segment` Step 3c | `_same_to_county_ugc` | county derivation from `_geocode.get("SAME")` list, L4068-4073 | WIRED | Loop at L4070-4073 calls `_same_to_county_ugc(_same)`, takes first non-None result. |
| `_weather_segment` Step 3c | `forecast.weather.gov/showsigwx.php` | `_wx_url` built when `_ugc and _county` both non-None, L4080-4082 | WIRED | Single f-string with both `warnzone={_ugc}` and `warncounty={_county}`. D-10: `else None` when either is missing. |
| `_osc8_enabled` auto branch | `VTE_VERSION >= 5000` gate | `try: if int(_vte) >= 5000: return True except (TypeError, ValueError): pass`, L294-299 | WIRED | `except` catches both bad-type and non-numeric string. Never raises. |
| `_same_to_county_ugc` | `_FIPS_STATE_POSTAL` lookup | `postal = _FIPS_STATE_POSTAL.get(state)`, L458 | WIRED | Returns `None` (not raises) on unknown key per D-10. |
| `_same_to_county_ugc` | `_valid_ugc` re-validation | `return _valid_ugc(candidate)`, L464 | WIRED | No second regex — derived county code routed through the same allowlist used everywhere. |

### D-10 Omit-Not-Fake Verification (Gap-Closure Specific)

| Input Condition | `_same_to_county_ugc` | `_wx_url` | `osc8()` output | Test |
|----------------|----------------------|-----------|-----------------|------|
| `same=None` | None | None | plain text | `test_none_returns_none` |
| `same=""` | None | None | plain text | `test_empty_string_returns_none` |
| `same="12345"` (5 digits) | None | None | plain text | `test_five_digit_returns_none` |
| `same="0xx037"` (non-numeric state) | None | None | plain text | `test_non_numeric_state_returns_none` |
| `same="099037"` (FIPS 99 not in table) | None | None | plain text | `test_unknown_state_fips_returns_none` |
| `same=[]` (no SAME in geocode) | not called | None | plain text | `test_no_same_no_link` (weather links) |
| `same=["BAD"]` (invalid SAME) | None | None | plain text | `test_invalid_same_no_link` |
| `same=["099037"]` (unknown state) | None | None | plain text | `test_unknown_state_same_no_link` |

All 8 conditions confirmed to produce zero `\x1b]8` bytes by passing tests.

### `api.weather.gov/alerts/active` Disambiguation

The production code contains exactly one occurrence of `api.weather.gov/alerts/active` (L2384). This is the **data-fetch** endpoint:

```python
url = (
    f"https://api.weather.gov/alerts/active"
    f"?point={lat:.4f},{lon:.4f}"
)
```

This is the HTTP GET call that retrieves NWS alert data. It is correct and must not be removed. The old **link target** (`api.weather.gov/alerts/active?zone={_ugc}`) is gone from the link-building code. `test_old_api_target_absent` confirms rendered output never contains `api.weather.gov/alerts/active`.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All three phase-09 test files | `/usr/bin/pytest -q tests/test_weather_link_target.py tests/test_weather_links.py tests/test_osc8_links.py` | 70 passed in 0.13s | PASS |
| `showsigwx.php?warnzone=` appears once in production code | `grep -c 'showsigwx.php?warnzone=' claude-statusline.py` | 1 | PASS |
| `_same_to_county_ugc` defined once | `grep -c 'def _same_to_county_ugc' claude-statusline.py` | 1 | PASS |
| Old `?zone=` link target absent from link-building code | `grep -c 'alerts/active?zone=' claude-statusline.py` | 0 | PASS |
| Status links regression | `/usr/bin/pytest -q tests/test_status_links.py` | 21 passed | PASS |
| VTE gate present | `grep -n 'int(_vte) >= 5000' claude-statusline.py` | L296 match | PASS |
| WR-02 comment present | `grep -n 'WR-02' claude-statusline.py` | L301 match | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| LINK-01 | 09-03-PLAN.md | Claude Status events render as OSC 8 hyperlinks to status.claude.com incident page | SATISFIED | `_claude_status_segment` wraps segment via `osc8()` to `https://status.claude.com/incidents/{_validated_id}`; 21 status link tests pass. |
| LINK-02 | 09-02-PLAN.md (original) + 09-04-PLAN.md (gap closure) | Weather alerts render as OSC 8 hyperlinks to the NWS alert detail URL | SATISFIED (gap closed) | `showsigwx.php?warnzone={zone}&warncounty={county}` is the link target; 15 weather link tests pass; 3 omit-not-fake tests confirm no link on missing/bad SAME. |
| LINK-03 | 09-01-PLAN.md, 09-02-PLAN.md, 09-03-PLAN.md | Hyperlinks degrade to plain text where OSC 8 is unsupported or config is off | SATISFIED | `osc8()` returns `text` unchanged when `not enabled or not url`; disabled-path tests in all three test modules assert zero `\x1b]8` bytes. |

All three phase-9 requirements (LINK-01, LINK-02, LINK-03) are SATISFIED. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `claude-statusline.py` | 4056-4062 | `_valid_ugc(_code)` called twice per candidate in Z/C loop (IN-01, pre-existing) | Info | Redundant regex call; correct behavior; unchanged from original plan 09-02. |
| `claude-statusline.py` | 664-668, 3911-3914, 4206-4209 | ANSI-sanitizer logic duplicated in three places (IN-02, pre-existing) | Info | DRY violation only; all copies functionally correct; unchanged. |

No `TBD`, `FIXME`, or `XXX` markers in files modified by plan 09-04. No new debt markers.

The two pre-existing IN-* findings from the code review are info-only and not introduced by this plan.

### Human Verification — RESOLVED (skip-accepted 2026-06-25 via /gsd:verify-work)

The item below was presented to the user during `/gsd:verify-work 09`. The user **skipped** it
(no active NWS alert available to click) and **accepted the residual risk**, on the basis that:
(1) the showsigwx page was already verified live during GAP-09-A diagnosis (CAZ373 + CAC037 →
populated WWA page); (2) the OSC 8 click mechanism passed live in original UAT Test 3 (LINK-03);
(3) URL construction + omit-not-fake are fully covered by 70 passing automated tests. It is recorded
here for audit completeness, not as an open gate.

#### 1. LINK-02 Live Browser Rendering — showsigwx.php Populates with Alerts

**Test:** With an active NWS weather alert and a terminal with OSC 8 support (set `links = "on"` in TOML, or use `links = "auto"` with a known-good terminal), view the statusline and click the weather alert text.
**Expected:** The browser opens `https://forecast.weather.gov/showsigwx.php?warnzone={zone}&warncounty={county}` and the NWS "WWA Summary by Location" page loads with at least one active watch/warning/advisory listed for that location. The page is human-readable (not a 404, a raw JSON dump, or an empty alert list).
**Why human:** Automated tests verify that the URL string is correctly formed with both `warnzone` and `warncounty` parameters. They cannot verify that the live NWS endpoint actually serves a populated, readable page for a given zone/county combination in production. The GAP-09-A fix was verified manually against a specific live zone (CAZ373 + CAC037) before the plan was written; this test confirms the pattern holds for the user's actual location zone.

---

## Gaps Summary

No blocking gaps. All six 09-04 must-have truths are machine-verified. All three phase-level requirements (LINK-01, LINK-02, LINK-03) are satisfied in code.

The lone human item (LINK-02 live-browser rendering) was an inherently human test. It was presented during `/gsd:verify-work 09` and **skip-accepted** by the user (no active alert; live page + click mechanism separately confirmed; automated coverage complete). No open gates remain.

---

_Verified: 2026-06-25T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
