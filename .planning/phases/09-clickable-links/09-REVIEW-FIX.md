---
phase: 09-clickable-links
fixed_at: 2026-06-25T00:00:00Z
review_path: .planning/phases/09-clickable-links/09-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-06-25
**Source review:** `.planning/phases/09-clickable-links/09-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `test_vte_unset_returns_false` — redundant `patch.dict` + `os.environ.pop` idiom

**Files modified:** `tests/test_osc8_links.py`
**Commit:** ce6484f
**Applied fix:** Replaced the 9-line `patch.dict` / `os.environ.pop` body with the
4-line `_run_auto({})` idiom already used by every sibling VTE test. Added a comment
explaining that omitting `VTE_VERSION` from `env_patch` causes `os.environ.get` to
return `""`, which makes `int("")` raise `ValueError`, giving the same `False` result
as `VTE_VERSION=""`. Test name, assertion, and semantic coverage are unchanged.

---

### IN-01: `_FIPS_STATE_POSTAL` comment overstated NWS territory coverage

**Files modified:** `claude-statusline.py`
**Commit:** f364313
**Applied fix:** Replaced the single-line comment
`# Territories: PR(72), GU(66), VI(78), AS(60), MP(69) — all issued by NWS for alerts.`
with a three-line comment (Option 1 / COMMENT-CORRECTION) that names the five
territories with their own NWS Forecast Offices, then explicitly notes that PGUM
also serves FSM(64), Marshall Islands(68), and Palau(70) but those FIPS codes are
absent from the table — alerts from those areas get no link per the D-10 omit-not-fake
rule. Table contents and all behavior are unchanged.

---

### IN-02: `_make_alert_with_ugc` docstring misrepresented `same_list` default condition

**Files modified:** `tests/test_weather_links.py`
**Commit:** 3f5e21e
**Applied fix:** Replaced the docstring lines that falsely implied `["040109"]` is
the default only when `ugc_list` contains `OKZ034`, with text that accurately states
the default applies to any call that omits `same_list`. The explicit
`Pass same_list=[] explicitly…` guidance is preserved. Function signature and
behavior are unchanged.

---

_Test run (post-fix):_ `/usr/bin/pytest -q tests/test_osc8_links.py tests/test_weather_links.py tests/test_weather_link_target.py` — **70 passed, 0 failed**

_Fixed: 2026-06-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
