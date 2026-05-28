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
  - "POST-CHECKPOINT: sun times computed with local tzinfo passed to astral.sun() (UTC default put western sunset on prior local day)"
  - "POST-CHECKPOINT: precip chunk hidden below configurable [weather] pop_min (default 30) — sub-threshold PoP is noise"
  - "POST-CHECKPOINT: venv self-re-exec moved out of module scope into _reexec_into_venv() (import-time execv hijacked pytest)"
  - "POST-CHECKPOINT: unconfigured location (lat/lon absent or 0.0/0.0) omits the whole weather segment"
  - "POST-CHECKPOINT: icon map reordered — partly/mostly-sunny before broad cloudy/sunny; clear-at-night → 🌙"
metrics:
  duration: "~30 min autonomous + verification-round fixes"
  completed: "2026-05-28 (checkpoint approved by user)"
  tasks_completed: 3
  files_modified: 5
---

# Phase 2 Plan 03: Active-Alert Override Summary

**One-liner:** CAP references-chain dedup + highest-severity selection + severity-colored alert override replaces the sun-event trailing detail in _weather_segment, fetched in the lock-guarded background child with FAKE_ALERTS offline testing support.

**Status: COMPLETE** — autonomous tasks 1 & 2 implemented; task 3 (human-verify checkpoint) approved by the user (degreed meteorologist) after a verification round that surfaced and fixed several bugs (see "Checkpoint Resolution" below).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Port references-chain dedup + severity selection + _alert_color | 555ad52 | claude-statusline.py, tests/test_weather_alerts.py, fixtures/*.json |
| 2 | fetch_alerts in background child + alert-override trailing detail | 14005a8 | claude-statusline.py, tests/test_weather_fetch.py |
| 3 | Meteorologist data-fidelity sign-off (human-verify) | approved | — (see Checkpoint Resolution) |

TDD commits (RED before GREEN): 26753d2 (RED) → 555ad52 (Task 1 GREEN) → 14005a8 (Task 2 GREEN).

## What Was Built

### claude-statusline.py additions (plan 02-03)

**Alert dedup (Task 1):** `_TERMINAL_MSG_TYPES` {Cancel,Ack,Error}; `_SEVERITY_RANK` (Extreme=4…Unknown=0); `dedup_alerts()` CAP references-chain (drops referenced/Cancel/Ack/Error/expired, sorts by sent desc, tolerates malformed input); `select_alert()` → (best, remaining_count); `_alert_color()` RED Extreme/Severe, YELLOW Moderate/Minor/Unknown.

**Alert fetch (Task 2):** `fetch_alerts(cfg)` GETs `/alerts/active?point={lat:.4f},{lon:.4f}` (ld+json, NWS UA), handles `@graph`/`features`, dedups, atomic `alerts` cache write, `CLAUDE_STATUSLINE_FAKE_ALERTS` offline hook; `run_refresh` extended to fetch alerts after weather under the single lock (D2-16); `maybe_spawn_refresh` checks both TTLs.

**_weather_segment trailing detail:** alert override (`⚠ <event>` severity-colored + `+N`) when alerts within ceiling & non-empty, else `_sun_segment` fallback (D2-12).

### Tests
`tests/test_weather_alerts.py` (dedup/select/color/fetch/spawn/override); fixtures `nws_alerts_active.json` (Extreme/Severe/Moderate) + `nws_alerts_superseded.json` (Update/Cancel/expired).

## Checkpoint Resolution (Human-Verify) & Post-Verification Fixes

The meteorologist checkpoint caught real bugs against live NWS data. Fixed and committed before approval:

| Commit | Fix |
|--------|-----|
| c4b2b00 | **Sun times UTC→local + event selection:** pass local `tzinfo` to `astral.sun()` (UTC-date default put a western sunset on the prior local evening → wrong event); format in local-aware time. **PoP threshold:** configurable `[weather] pop_min` (default 30) hides sub-threshold noise. **Venv re-exec import hijack:** moved top-level `os.execv` into `_reexec_into_venv()` called only from `main()` (importing the module had hijacked pytest once the venv existed). **Config template footgun:** `install.py` ships table headers uncommented so uncommenting a key nests correctly. **Unconfigured location (0,0) omits weather.** **Test isolation:** skeleton subprocess tests run under an isolated HOME. |
| a253511 | **Icon map ordering:** partly/mostly-sunny rule before broad cloudy/sunny so `Partly Cloudy`→⛅, `Mostly Sunny`→⛅ (were swallowed by `cloudy`/`sunny`). |
| 0e890be | **Day/night:** clear skies at night → 🌙 via the NWS icon-URL day/night token. |
| e1e1344 | Captured ENH-04 (Weather Icons / Nerd Font icon set) as a v2 enhancement. |

Verified live @ KOKC: `[☁️ 82°F | 🌇 8:37pm]` (Mostly Cloudy per the observation's `bkn`/textDescription; PoP 13% hidden; sunset as next event) and `[☁️ 82°F | ⚠ Tornado Warning +2]` (red, fixture).

## TDD Gate Compliance
Task 1: RED 26753d2 → GREEN 555ad52. Task 2: RED 26753d2 → GREEN 14005a8. Post-checkpoint fixes carry their own regression tests (pop_min boundary + configurability, no top-level os.execv, _reexec_into_venv is a function, icon mapping day/night).

## Threat Surface Scan
All plan threats addressed (T-02-12…16): dedup drops superseded/terminal/expired; fetch+dedup in try/except with 10s timeout in the detached child only; contact_email only in the User-Agent header; FAKE_ALERTS env-gated/off by default; single O_CREAT|O_EXCL lock covers both fetches. No new endpoints/auth/schema.

## Self-Check: PASSED
All files present; commits in git log. Test suite: **system python3 224 passed / 32 skipped; venv 256 passed** (the venv run executes the astral-dependent sun + render tests that dev-python skips — the gap that originally hid the tz bug).
