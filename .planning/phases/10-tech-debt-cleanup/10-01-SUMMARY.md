---
phase: 10-tech-debt-cleanup
plan: "01"
subsystem: metadata-and-planning-docs
tags: [tech-debt, version-sync, requirements, test-verification, documentation]
one_liner: "Closed all five v1.0 audit debt items: pyproject 0.2.0 sync, WX-05 TTL prose fixed, REQUIREMENTS.md reconciled, DEBT-02 retired with note, weather tests verified 228/47/0 under system pytest"
requirements_completed: [DEBT-01, DEBT-02, DEBT-03, DEBT-04, DEBT-05]

dependency_graph:
  requires:
    - 09-04-SUMMARY.md   # LINK-01..03 complete (Phase 9)
  provides:
    - pyproject.toml version aligned to _APP_VERSION (0.2.0)
    - v1.0-REQUIREMENTS.md WX-05 TTL text corrected to 10 min
    - REQUIREMENTS.md traceability table reconciled (all v1.1 reqs complete)
    - v1.0-MILESTONE-AUDIT.md Tech-Debt Resolution section with per-item notes
  affects:
    - pyproject.toml
    - .planning/milestones/v1.0-REQUIREMENTS.md
    - .planning/REQUIREMENTS.md
    - .planning/milestones/v1.0-MILESTONE-AUDIT.md

tech_stack:
  added: []
  patterns:
    - Retirement-with-note pattern for tracking fields cleared at milestone close

key_files:
  created: []
  modified:
    - pyproject.toml                                  # version 0.1.0 → 0.2.0
    - .planning/milestones/v1.0-REQUIREMENTS.md       # WX-05 ~15min → ~10min
    - .planning/REQUIREMENTS.md                       # LINK-01..03 + DEBT-01..05 → Complete; footer updated
    - .planning/milestones/v1.0-MILESTONE-AUDIT.md    # Tech-Debt Resolution (Phase 10) section added

decisions:
  - "DEBT-05 canonical value is the code (10 min / weather_ttl=600); prose corrected to match"
  - "DEBT-02 RETIRED not backfilled — v1.0 SUMMARYs cleared at milestone close (a413558); coverage confirmed by VERIFICATION + traceability; v1.1 SUMMARYs populate requirements_completed going forward"

metrics:
  duration_minutes: 2
  tasks_completed: 3
  files_modified: 4
  completed_date: "2026-06-25"
---

# Phase 10 Plan 01: Tech-Debt Cleanup Summary

## What Was Done

Closed all five items from the v1.0 milestone-audit `tech_debt` block (DEBT-01..05). Every change is metadata, planning markdown, or test verification — no runtime code paths were altered.

**Task 1 (DEBT-01 + DEBT-05, commit cf19e9d):**
- `pyproject.toml`: bumped `version` from `0.1.0` to `0.2.0`, now byte-equal to `_APP_VERSION = "0.2.0"` in `claude-statusline.py:878`.
- `v1.0-REQUIREMENTS.md` WX-05: corrected "Weather (~15min)" to "Weather (~10min)" to match the canonical `weather_ttl=600` default. Code value (10 min) was canonical; prose was the outlier.

**Task 2 (DEBT-03, commit 5202469):**
- `.planning/REQUIREMENTS.md` traceability table: flipped LINK-01..03 (Phase 9 verified complete) and DEBT-01..05 (this plan) from `Pending` to `Complete`.
- Flipped corresponding `[ ]` checkboxes to `[x]` in the requirement list body.
- Updated footer: `Last updated: 2026-06-25 after Phase 10 tech-debt cleanup (LINK-01..03 + DEBT-01..05 reconciled to shipped)`.

**Task 3 (DEBT-02 + DEBT-04, commit 5a533e4):**
- Ran `/usr/bin/pytest tests/test_weather_sun.py tests/test_weather_fetch.py tests/test_weather_cache.py tests/test_weather_alerts.py tests/test_weather_links.py tests/test_weather_link_target.py -q` — result: **228 passed, 47 skipped, 0 errors, exit 0**. The 47 skips all carry stated reasons (`_ASTRAL_OK`/`_WEATHER_OK` guards; system python3 has `requests` but not `astral`). No empty `skipTest("")` calls exist. No fix was needed — DEBT-04 is verified runnable.
- Added "## Tech-Debt Resolution (Phase 10)" section to `v1.0-MILESTONE-AUDIT.md` with one explicit resolution line per DEBT item; DEBT-02 formally RETIRED with citation of clearing commit a413558.

## Deviations from Plan

None — plan executed exactly as written. Both pre-approved ASSUMPTIONs were followed:
- DEBT-05: code value (10 min) taken as canonical; WX-05 prose corrected to match.
- DEBT-02: RETIRED with documented note, not backfilled.

## Known Stubs

None. This plan is metadata/documentation only; no render paths involved.

## Self-Check

- [x] `grep '^version = "0.2.0"$' pyproject.toml` matches
- [x] `grep '_APP_VERSION = "0.2.0"' claude-statusline.py` matches
- [x] `grep 'WX-05.*~10min' .planning/milestones/v1.0-REQUIREMENTS.md` matches
- [x] All LINK-01..03 and DEBT-01..05 rows read "Complete" in REQUIREMENTS.md
- [x] Footer contains `2026-06-25` and phase-10 reconciliation note
- [x] `v1.0-MILESTONE-AUDIT.md` contains "Tech-Debt Resolution (Phase 10)" section with all 5 DEBT items
- [x] Weather suite: 228 passed, 47 skipped, 0 errors under `/usr/bin/pytest`
- [x] DEBT-02 cites commit a413558; DEBT-04 cites exact `/usr/bin/pytest ...` command
- [x] All 3 commits exist: cf19e9d, 5202469, 5a533e4

## Self-Check: PASSED
