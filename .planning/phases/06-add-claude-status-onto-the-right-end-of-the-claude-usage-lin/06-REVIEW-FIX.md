---
phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
fixed_at: 2026-06-16T00:00:00Z
review_path: .planning/phases/06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin/06-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-06-16
**Source review:** .planning/phases/06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 3
- Fixed: 3
- Skipped: 0

In-scope = Critical + Warning. The review reported 0 Critical and 3 Warning
findings; all 3 were fixed. The 4 Info findings (IN-01..IN-04) are out of scope
for `--fix` (critical_warning) and were left untouched.

## Fixed Issues

### WR-01: `under_maintenance` component status renders the INCIDENT glyph (D-04 violation)

**Files modified:** `claude-statusline.py`, `tests/test_claude_status.py`, `tests/fixtures/status_component_under_maintenance_no_event.json`
**Commit:** 53b29b7
**Applied fix:** In `_claude_status_segment` step 5, the glyph/color branch now
keys on the maintenance SIGNAL, not `kind` alone:
`if kind == "maintenance" or severity == "maintenance":`. A tracked component in
`under_maintenance` with no matching `scheduled_maintenances` entry falls through
`_derive_claude_status` Rule 3 with `severity == "maintenance"` but
`kind == "degraded"`; previously this rendered `_NF_CLAUDE_INCIDENT` (exclamation)
with DIM color and a "maintenance" label — conflating maintenance with an outage.
It now renders the distinct `_NF_CLAUDE_MAINT` (wrench) glyph + neutral color,
consistent with the DIM color and label already produced (D-04 honored). Added:
a new fixture (`status_component_under_maintenance_no_event.json`), two derivation
tests asserting Rule 3 yields `severity == "maintenance"` for this path, and two
segment-render tests asserting the wrench glyph (not the incident glyph) and the
neutral color. No prior test exercised Rule 3 with `under_maintenance`, which is
why the defect was invisible to the suite.

### WR-02: Render-path `maybe_spawn_refresh` triggers blind `fetch_weather` against an unconfigured location

**Files modified:** `claude-statusline.py`, `tests/test_claude_status.py`, `tests/test_weather_alerts.py`, `tests/test_weather_fetch.py`
**Commits:** cdb863e (fix + new gating tests), 6faf158 (companion: update two pre-existing run_refresh tests)
**Applied fix:** In `run_refresh`, gated the `fetch_weather`/`fetch_alerts` calls
on the same conditions the render-path weather segment uses
(`_weather_segment` :2773-2787): `_WEATHER_OK` AND `weather.show_weather` AND a
configured (non-0.0/0.0) location. `fetch_claude_status` remains unconditional, so
status refresh stays independent (the T-06-06 / D-05 intent) while weather fetches
no longer fire for users who have weather disabled or never set a location. The
`float(lat)` placeholder check runs inside `run_refresh`'s outer `try/except`,
matching the render-path pattern, so a non-numeric location degrades silently.
Added three new tests (show_weather=False, unconfigured 0.0/0.0 location,
`_WEATHER_OK` False) each asserting weather/alerts are skipped while
`fetch_claude_status` still runs. The gating change altered `run_refresh`'s
behavior, so three pre-existing tests that assumed unconditional weather fetches
(`TestRunRefreshStatus`, `TestRunRefreshAlerts`, `TestRunRefresh`) were updated to
patch `_WEATHER_OK` True to assert the intended "weather configured" path.

### WR-03: `fetch_claude_status` issues a live network request with no `_REQUESTS_OK` guard

**Files modified:** `claude-statusline.py`, `tests/test_claude_status.py`
**Commit:** fe26490
**Applied fix:** Added an early `if not _REQUESTS_OK: return` bail at the top of
the live-fetch branch in `fetch_claude_status`, mirroring the `_WEATHER_OK` guards
used by the weather/alerts fetch path. When `requests` failed to import, `_nws_get`
previously raised a `NameError` (swallowed by the outer `try/except`) only after
constructing the UA and taking the network branch; it now degrades cleanly,
leaving the cache section unchanged. The fake-status path is unaffected. Added a
test asserting `_nws_get` is not called and the cache is untouched when
`_REQUESTS_OK` is False.

## Verification

- Per-fix: Tier 1 (re-read) + Tier 2 (`python3 -c ast.parse` syntax check) passed
  for every modified `.py` and JSON file.
- Full suite: `python3 -m pytest tests/ -q` (system `python3`; the project `.venv`
  lacks pytest, and `astral` is not installed in this environment, so
  `_WEATHER_OK` is False here).
  - Result inside the fixer's isolated worktree:
    **564 passed, 60 skipped, 269 subtests passed, 2 failed.**
  - The 2 failures were **pre-existing and unrelated** to these fixes:
    - `tests/test_git_segment.py::TestGitSegmentE2E::test_e2e_repo_dir_shows_git_segment_between_project_and_model`
    - `tests/test_gsd_segment.py::TestGsdSegmentE2E::test_e2e_repo_dir_shows_gsd_segment_between_git_and_model`
  - Both were confirmed FAILING on the pre-fix base commit (6851708) and depend
    purely on the working-directory name: they hardcode the project marker
    `[claude_statusline]`, but the fixer ran inside an isolated git worktree
    (`/tmp/sv-06-reviewfix-XXXXXX`), so the rendered marker did not match.
  - **Both pass when run from the real `claude_statusline` checkout** (verified
    after cleanup: `2 passed`). No code change of mine affects the git/gsd
    segments — net effect in the project directory is a fully green suite.
  - All Phase-06 status tests pass, including the 7 new tests added for
    WR-01/WR-02/WR-03.

## Notes

- WR-01 is a logic/UX correctness fix (glyph selection). It is fully covered by
  the new render-path tests asserting the exact wrench-vs-exclamation glyph and
  neutral-vs-severity color, so it does not require additional human verification
  beyond the human-visual gate already standard for this project.
- IN-01..IN-04 (Info) were intentionally not addressed (out of scope for
  `critical_warning` fix mode).

---

_Fixed: 2026-06-16_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
