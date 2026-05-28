---
phase: 02-weather-layer
plan: "03"
subsystem: weather-layer
tags: [weather, alerts, nws, dedup, severity, override, tdd, cap]
dependency_graph:
  requires: [02-02]
  provides: [alert-dedup, alert-severity-selection, alert-override-render, fetch-alerts]
  affects: [claude-statusline.py, tests/test_weather_alerts.py, tests/fixtures/nws_alerts_active.json, tests/fixtures/nws_alerts_superseded.json]
tech_stack:
  added: [CLAUDE_STATUSLINE_FAKE_ALERTS env var (UAT/offline fixture override)]
  patterns: [cap-references-chain-dedup, severity-rank-selection, alert-override-trailing-detail, fake-file-env-trigger]
key_files:
  created:
    - tests/test_weather_alerts.py
    - tests/fixtures/nws_alerts_active.json
    - tests/fixtures/nws_alerts_superseded.json
  modified:
    - claude-statusline.py
    - tests/test_weather_fetch.py
decisions:
  - "dedup_alerts operates on raw NWS feature dicts (not Alert dataclass) — no WxDesktopPy domain model imported"
  - "References in NWS payload may be objects with 'identifier' key or plain strings — code handles both shapes"
  - "alerts with missing 'expires' field are skipped (cannot verify they are not expired)"
  - "Unknown severity maps to YELLOW — visible but not alarming (plan discretion)"
  - "maybe_spawn_refresh checks BOTH weather and alerts TTLs — single spawn covers both; single lock in run_refresh (D2-16)"
  - "fetch_alerts honors CLAUDE_STATUSLINE_FAKE_ALERTS env var (mirrors WxDesktopPy WXD_FAKE_ALERTS_FILE)"
  - "Warning glyph is U+26A0 ⚠ (plain, no variation selector) for consistent terminal width"
  - "Trailing detail in _weather_segment: alert override attempted first, sun event is unconditional fallback"
metrics:
  duration: "~30 min"
  completed: "2026-05-28 (autonomous tasks; checkpoint pending human-verify)"
  tasks_completed: 2
  files_modified: 4
---

# Phase 2 Plan 03: Active-Alert Override Summary

**One-liner:** CAP references-chain dedup + highest-severity selection + severity-colored alert override replaces the sun-event trailing detail in _weather_segment, fetched in the lock-guarded background child with FAKE_ALERTS offline testing support.

**Status: AWAITING HUMAN-VERIFY CHECKPOINT** — autonomous tasks 1 and 2 complete; task 3 (checkpoint:human-verify) pending user sign-off.

## Tasks Completed (Autonomous)

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Port references-chain dedup + severity selection + _alert_color | 555ad52 | claude-statusline.py, tests/test_weather_alerts.py, fixtures/*.json |
| 2 | fetch_alerts in background child + alert-override trailing detail | 14005a8 | claude-statusline.py, tests/test_weather_fetch.py |

TDD commits (RED before GREEN):
- 26753d2 — test(02-03): failing tests for all Tasks 1+2 (RED)
- 555ad52 — feat(02-03): Task 1 dedup + select_alert + _alert_color (GREEN)
- 14005a8 — feat(02-03): Task 2 fetch_alerts + run_refresh + alert override (GREEN)

## What Was Built

### claude-statusline.py additions (plan 02-03)

**Alert dedup (Task 1):**
- `_TERMINAL_MSG_TYPES`: frozenset `{"Cancel", "Ack", "Error"}`
- `_SEVERITY_RANK`: dict Extreme=4, Severe=3, Moderate=2, Minor=1, Unknown=0
- `dedup_alerts(alerts, now=None)`: CAP references-chain algorithm ported from WxDesktopPy dedup.py (L70-88); builds superseded set from references + Cancel/Ack/Error messageTypes; drops expired (expires ≤ now); returns survivors sorted by sent descending; tolerates missing/malformed fields per T-02-12
- `select_alert(survivors)`: returns (best_alert, remaining_count) using _SEVERITY_RANK; returns (None, 0) on empty input
- `_alert_color(severity)`: RED for Extreme/Severe, YELLOW for Moderate/Minor/Unknown

**Alert fetch (Task 2):**
- `fetch_alerts(cfg)`: GETs `/alerts/active?point={lat:.4f},{lon:.4f}` with `Accept: application/ld+json` and NWS User-Agent; handles both `@graph` (JSON-LD) and `features` (GeoJSON) keys; runs dedup_alerts; writes `alerts` cache section `{fetched_at, active: [survivor_dicts]}` atomically; honors `CLAUDE_STATUSLINE_FAKE_ALERTS` env var for offline UAT; fully wrapped in try/except
- `run_refresh(cfg)`: extended to call `fetch_alerts` after `fetch_weather` under the single lock (D2-16)
- `maybe_spawn_refresh(cfg, cache)`: extended to check BOTH weather_ttl AND alerts_ttl; spawns when either section is stale; single detached child covers both refreshes

**_weather_segment trailing detail (Task 2):**
- Alert override branch: reads alerts section; if `section_within_ceiling(alerts_section, alerts_max_stale)` and `active` list is non-empty → `select_alert` → renders `⚠ <event>` wrapped in `_alert_color(severity) + RESET`, plus ` +N` when remaining > 0
- Fallback: `_sun_segment(cfg)` when alerts absent/cold/beyond ceiling (D2-12 — sun always renders offline)
- precip chunk and conditions chunk logic unchanged from Plan 02-02

### Tests

**tests/test_weather_alerts.py** (52 tests, 37 passed + 15 skipped for render tests in dev env):
- `TestDedupAlerts` (12 tests): referenced drop, Cancel/Ack/Error drop, expired drop, survivor sort, superseded fixture, tolerates missing fields
- `TestSelectAlert` (9 tests): Extreme beats Severe, severity rank ordering, remaining count, empty survivors, fixture-driven
- `TestAlertColor` (7 tests): RED for Extreme/Severe, YELLOW for Moderate/Minor, Unknown non-red
- `TestFetchAlerts` (6 tests): endpoint in source, ld+json in source, fake-fixture writes cache, superseded-fixture dedup, swallows errors, no real network when fake set
- `TestRunRefreshAlerts` (1 test): run_refresh calls fetch_alerts
- `TestMaybeSpawnRefreshAlerts` (2 tests): spawns when alerts stale, no spawn when both fresh
- `TestWeatherSegmentAlertOverride` (15 tests, all skip in dev env): alert replaces sun, RED for Extreme/Severe, YELLOW for Moderate, +N suffix, conditions still present, stale fallback to sun, cold fallback, warning glyph present

**tests/fixtures:**
- `nws_alerts_active.json`: 3 active alerts — Extreme (Tornado Warning), Severe (Severe Thunderstorm Warning), Moderate (Flash Flood Watch)
- `nws_alerts_superseded.json`: Update (references old Alert), Cancel, expired Alert — exercises full dedup

**tests/test_weather_fetch.py** (update):
- `test_does_not_spawn_on_fresh_cache`: updated to include fresh `alerts` section (maybe_spawn_refresh now checks both)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_does_not_spawn_on_fresh_cache broke when maybe_spawn_refresh extended to check alerts staleness**
- **Found during:** Task 2 full-suite run
- **Issue:** Pre-existing test passed a weather-only cache (no `alerts` key); with alerts staleness check, absent alerts = stale → spawned unexpectedly
- **Fix:** Updated test to include fresh `alerts: {fetched_at: now-60, active: []}` section — aligns with the intended D2-16 behavior (single spawn covers both)
- **Files modified:** tests/test_weather_fetch.py
- **Commit:** 14005a8 (bundled with GREEN Task 2)

## TDD Gate Compliance

- Task 1: RED commit 26753d2 → GREEN commit 555ad52 — compliant
- Task 2: RED commit 26753d2 → GREEN commit 14005a8 — compliant
  (Task 1 and Task 2 RED tests were committed together; GREEN commits are separate)

## Known Stubs

None. All alert override functionality is wired end-to-end; the fake-alerts env var enables offline UAT at the checkpoint.

## Threat Surface Scan

All threats from the plan's threat model have been addressed:
- T-02-12: dedup_alerts drops referenced + Cancel/Ack/Error + expired alerts before selection
- T-02-13: fetch_alerts + dedup wrapped in try/except; per-alert date parse failures skip that alert; requests 10s timeout in _nws_get; runs only in the detached child
- T-02-14: contact_email flows only into make_user_agent return value (User-Agent header); no print() call references it (inherited T-02-06 coverage from Plan 02-02)
- T-02-15: CLAUDE_STATUSLINE_FAKE_ALERTS is env-var-gated, off by default; reads local file in try/except
- T-02-16: fetch_alerts runs inside the SAME lockfile as fetch_weather in run_refresh (single O_CREAT|O_EXCL lock)

No new network endpoints, auth paths, or schema changes beyond the plan's threat model.

## Self-Check: PASSED

Files created/exist:
- claude-statusline.py: FOUND (modified, extended with dedup + fetch_alerts + alert override)
- tests/test_weather_alerts.py: FOUND (52 tests)
- tests/fixtures/nws_alerts_active.json: FOUND
- tests/fixtures/nws_alerts_superseded.json: FOUND

Commits verified in git log:
- 26753d2: FOUND (test RED)
- 555ad52: FOUND (feat Task 1 GREEN)
- 14005a8: FOUND (feat Task 2 GREEN)

Test suite: 211 passed, 29 skipped (all expected dev-env skips — astral/requests not in system Python)
