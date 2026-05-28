---
phase: 02-weather-layer
verified: 2026-05-28T20:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 2: Weather Layer Verification Report

**Phase Goal:** The top line gains live NWS weather that never blocks rendering
**Verified:** 2026-05-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Top line shows `<condition icon> <temp>` sourced from NWS, with `\|🌧️<precip>` appended when precipitation is present | VERIFIED | `_weather_segment` assembles `conditions_chunk` (`icon temp°F`) from `weather_section` and `precip_chunk` (`🌧️pop%`) only when PoP >= `pop_min`; live output `[☁️ 82°F \| 🌇 8:37pm]` confirmed |
| 2 | Top line ends with the next sun event (🌅/🌇) computed locally from lat/lon — no network call | VERIFIED | `_sun_segment` uses `astral.sun()` + `LocationInfo` from configured lat/lon; no network call in `_sun_segment`; UTC-to-local tz fix in c4b2b00 ensures correct event selection |
| 3 | When an active NWS alert exists for the location, it replaces the sun-event detail | VERIFIED | `_weather_segment` trailing-detail branch: `section_within_ceiling` → `select_alert` → severity-colored `⚠ event +N`; `dedup_alerts` confirmed to drop superseded/cancelled/expired; `_alert_color` returns RED for Extreme/Severe |
| 4 | Weather (~10 min) and alerts (~5 min) cached; subsequent renders read cache and return instantly | VERIFIED | `_weather_segment` calls `read_cache(_CACHE_PATH)` then `maybe_spawn_refresh`; `maybe_spawn_refresh` uses `subprocess.Popen(..., start_new_session=True)` with no `.wait()` or `.communicate()` — fire-and-forget confirmed; `run_refresh` uses `O_CREAT\|O_EXCL` lockfile preventing stampede |
| 5 | When network unavailable or cache cold, bar still renders — weather block omitted or shows stale data gracefully | VERIFIED | `HOME=/tmp python3 claude-statusline.py` with no venv renders Phase-1 bar exactly (`[demo] [Opus 4.8]` + bottom line), exit 0, no Traceback on stderr; `_WEATHER_OK = _ASTRAL_OK and _REQUESTS_OK` guard at module level; `_reexec_into_venv()` only called from `main()`, not at import time (post-checkpoint fix) |

**Score:** 5/5 truths verified

---

### Requirements Coverage

| Requirement | Plan | Description | Status | Evidence |
|-------------|------|-------------|--------|----------|
| WX-01 | 02-02 | `<condition icon> <temp>` from NWS observation | SATISFIED | `fetch_weather` points→stations→observations/latest; `_icon_to_emoji` maps textDescription/icon-URL; `c_to_unit` converts Celsius; `conditions_chunk` in `_weather_segment` |
| WX-02 | 02-02 | Precip chunk `\|🌧️<precip>` when precipitation present | SATISFIED | `precip_chunk` built only when `pop is not None and float(pop) >= pop_min`; zero/null PoP omitted; configurable `pop_min` default 30 |
| WX-03 | 02-01 | Next sun event computed locally from lat/lon | SATISFIED | `_sun_segment` uses `astral`; three-branch selection (before sunrise/before sunset/after sunset); time formatted `%-I:%M%p`.lower() matching `fmt_reset` |
| WX-04 | 02-03 | Active NWS alert replaces sun-event detail | SATISFIED | `fetch_alerts` with CAP dedup; `select_alert` highest-severity; `_alert_color` RED/YELLOW; `CLAUDE_STATUSLINE_FAKE_ALERTS` env hook for UAT; meteorologist approved at checkpoint |
| WX-05 | 02-02 | Cache with TTLs; render reads cache never blocks | SATISFIED | `_CACHE_PATH` sectioned cache.json; `section_is_fresh`/`section_within_ceiling` staleness; `maybe_spawn_refresh` Popen fire-and-forget; `run_refresh` O_CREAT\|O_EXCL lockfile |
| WX-06 | 02-01 | Bar still renders when weather unavailable | SATISFIED | Degradation verified: missing venv → `_WEATHER_OK=False` → `_weather_segment` returns `None` → Phase-1 bar unchanged; subprocess test confirms no Traceback |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-statusline.py` | Venv re-exec, guarded imports, `_sun_segment`, `_weather_segment`, cache/fetch/alerts layer, `--refresh` entry mode | VERIFIED | 1252 lines; all named functions present; `_reexec_into_venv()` function-guarded; `_WEATHER_OK`, `_ASTRAL_OK`, `_REQUESTS_OK` defined |
| `install.py` | Subfolder + venv + pip install + settings.json wiring, no `shell=True` | VERIFIED | `INSTALL_DIR = ~/.claude/claude-statusline`, `VENV_DIR`, `SCRIPT_PATH`, `CONFIG_PATH`; `subprocess.run` with fixed argv lists; `shell=True` absent; config not clobbered if exists |
| `pyproject.toml` | `dependencies = ["requests", "astral"]` | VERIFIED | Line 5: `dependencies = ["requests", "astral"]` |
| `tests/test_weather_sun.py` | Sun-event selection + degradation unit tests | VERIFIED | Exists; 3 branches + None-on-failure tested; skipped in system python3 (no astral), runs in venv |
| `tests/test_bootstrap_degradation.py` | `_weather_segment` None when `_WEATHER_OK=False`, subprocess bar-renders-no-Traceback | VERIFIED | 15 tests; `TestSubprocessDegradation.test_no_traceback_in_stderr` confirmed passing |
| `tests/test_weather_cache.py` | Cache read/staleness/atomic-write tests | VERIFIED | 31 tests; cold/fresh/stale/beyond-ceiling/malformed/round-trip all covered; all pass |
| `tests/test_weather_fetch.py` | NWS parse + temp-conversion + render-from-fixture tests, no real network | VERIFIED | Fixture-driven via `_nws_get` monkeypatch; `TestNwsSourceRequirements.test_no_wait_communicate` passes; render tests skip in system python3 (astral absent), run in venv |
| `tests/test_weather_alerts.py` | Dedup + severity-selection + override-render + degradation tests | VERIFIED | Exists; dedup/select/color/override tests pass; render tests skip in system python3, run in venv |
| `tests/fixtures/nws_*.json` | NWS fixture files | VERIFIED | 6 fixture files present: nws_alerts_active.json, nws_alerts_superseded.json, nws_hourly_forecast.json, nws_observation_latest.json, nws_points.json, nws_stations.json |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `render_top_line` | `_weather_segment` | `segments` list, None-filtered | WIRED | L1175: `_weather_segment(data, cfg)` appended to segments; None-filter at L1177 |
| `_weather_segment` render path | `cache.json` | `read_cache(_CACHE_PATH)` | WIRED | L1063: `cache = read_cache(_CACHE_PATH)` — no inline fetch; confirmed `_nws_get` never called from `_weather_segment` |
| `_weather_segment` stale trigger | detached child | `maybe_spawn_refresh(cfg, cache)` | WIRED | L1068; Popen with `start_new_session=True`; `--refresh` in argv |
| `maybe_spawn_refresh` | `run_refresh` via `--refresh` | `subprocess.Popen([sys.executable, __file__, "--refresh"])` | WIRED | L786-792; no `.wait()` / `.communicate()` on L793 comment confirmed; no such calls in file |
| `run_refresh` | `fetch_weather` + `fetch_alerts` | under O_CREAT\|O_EXCL lockfile | WIRED | L742-743: both called sequentially under single lock (D2-16) |
| `fetch_alerts` (--refresh) | `api.weather.gov/alerts/active` | `_nws_get` with `Accept: application/ld+json` | WIRED | L695-699; ld+json Accept header set; FAKE_ALERTS env hook tested |
| `_weather_segment` trailing detail | alert override / `_sun_segment` | `section_within_ceiling` → `select_alert` → `_alert_color`, else `_sun_segment` | WIRED | L1096-1119; correct fallback to sun when no alert/stale/cold |
| `_reexec_into_venv` | `os.execv` | only called from `main()` | WIRED | L1230: first call in `main()`; NOT at module top level (post-checkpoint critical fix) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `_weather_segment` conditions_chunk | `weather_section` from `cache.json` | `fetch_weather` → `write_cache_section` (in detached child) | Yes — NWS observation + hourly fetch | FLOWING |
| `_weather_segment` trailing_detail | `alerts_section.active` from `cache.json` | `fetch_alerts` → `dedup_alerts` → `write_cache_section` (in detached child) | Yes — NWS alerts/active with dedup | FLOWING |
| `_sun_segment` | `astral.sun()` | local computation from lat/lon, no network | Yes — astral library | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase-1 bar renders intact with no venv | `HOME=/tmp python3 claude-statusline.py <<json` | `[demo] [Opus 4.8]` + bottom line, exit 0, no stderr | PASS |
| Script exits 0 with live install | `echo json \| python3 claude-statusline.py > /dev/null 2>&1; echo $?` | `0` | PASS |
| `dedup_alerts` drops superseded+cancelled+expired | python3 inline test with `nws_alerts_superseded.json` | 4 alerts → 1 survivor (`Tornado Warning`) | PASS |
| `select_alert` returns Extreme first with +2 | python3 inline test with `nws_alerts_active.json` | `Tornado Warning` Extreme, remaining=2, color=RED (`\033[31m`) | PASS |
| `_sun_segment` returns None for 0.0/0.0 | python3 inline module load | `None` for both 0.0/0.0 and empty cfg | PASS |
| No `.wait()` or `.communicate()` in codebase | `grep` | Only a comment on L793, no actual call | PASS |
| `os.execv` only in function, not at module level | `grep -n os.execv` | L38 inside `_reexec_into_venv()` def; L1230 call from `main()` only | PASS |
| contact_email never printed to stdout | `grep print.*contact_email` | Only in docstring/comment, not in any `print()` call | PASS |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `claude-statusline.py` | 969, 1048 | "placeholder" in comment | Info | Comments explain 0.0/0.0 null-island semantic — intentional design documentation, not a stub |

No TBD, FIXME, or XXX markers found in any phase-modified file. No unreferenced debt. No `return null`/`return {}` stubs in production paths. The two "placeholder" matches are inline code comments documenting the 0.0/0.0 unconfigured-location convention — they do not indicate unimplemented behavior; the code path correctly returns `None` (omits segment) for the default lat/lon.

---

### Human Verification (Completed at Checkpoint)

The phase plan included a `checkpoint:human-verify` task (Plan 02-03, Task 3). The developer — a degreed meteorologist — performed the following live verification against real NWS data and approved:

- Live render confirmed: `[☁️ 82°F | 🌇 8:37pm]` (Mostly Cloudy, KOKC, PoP 13% hidden below pop_min=30, sunset as next event)
- Alert override confirmed via FAKE_ALERTS fixture: `[☁️ 82°F | ⚠ Tornado Warning +2]` (red, correct severity coloring)
- Degradation confirmed: renamed .venv → weather segment vanished, Phase-1 bar intact

Post-checkpoint fixes applied and regression-tested before approval:
- Sun times UTC→local (c4b2b00) — correct event selection for western time zones
- PoP threshold `pop_min` (c4b2b00) — sub-threshold precip hidden
- Venv re-exec moved to `main()` only (c4b2b00) — prevents pytest import hijack
- Icon map ordering: partly/mostly-sunny before broad cloudy/sunny (a253511)
- Day/night: clear at night → 🌙 (0e890be)

Human verification status: SATISFIED (approved at checkpoint 2026-05-28)

---

### Test Suite Summary

| Run mode | Passed | Skipped | Failed |
|----------|--------|---------|--------|
| System python3 (no astral/requests) | 224 | 32 | 0 |
| Installed venv (all deps) | 256 | 0 | 0 |

Skips in system python3 are expected: all 32 are astral-dependent sun/render tests that require the venv's `astral` and `requests` packages. The venv run (256 passed) is the complete suite.

---

### Gaps Summary

No gaps found. All 5 ROADMAP success criteria are verified against the codebase. All 6 WX requirements (WX-01 through WX-06) are implemented and tested. The render path provably never performs an inline network call. The detached child architecture is correctly wired with a fire-and-forget Popen, an O_CREAT|O_EXCL lockfile, and no blocking wait. Degradation is confirmed behaviorally.

Note: `REQUIREMENTS.md` traceability checkboxes and table still show WX-01..06 as "Pending" — this is a tracking-file update that was not applied after phase completion. It is a documentation gap, not an implementation gap, and does not affect the passing verdict.

---

_Verified: 2026-05-28_
_Verifier: Claude (gsd-verifier)_
