---
phase: 01-core-statusline
plan: "03"
subsystem: cli
tags: [python, stdlib, tomllib, config, toggles, thresholds, tdd]

# Dependency graph
requires:
  - "01-02: color_for/is_green/pct_int/fmt_reset helpers; render_top_line/render_bottom_line; tomllib import present"
provides:
  - "load_config(): reads ~/.claude/claude-statusline.toml via tomllib, silent defaults on any error (D-07)"
  - "DEFAULTS dict: thresholds warn=70/crit=90, four segment toggles (all true), units placeholder"
  - "_deep_merge(): recursively merges TOML over defaults; Phase-2 keys accepted, not consumed (D-09)"
  - "color_for(pct, warn=70, crit=90): configurable thresholds, default params preserve 70/90 behavior"
  - "is_green(pct, warn=70): configurable warn threshold, default preserves 70 behavior"
  - "Per-segment toggle gating: show_thinking_glyph, show_context_bar, show_five_hour, show_weekly"
  - "~/.claude/claude-statusline.toml: documented default config with Phase-2 keys reserved but commented"
  - "TDD test suite: tests/test_config.py (26 tests, all green)"
affects: [02-weather-layer-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DEFAULTS dict as the canonical fallback; load_config wraps tomllib.load in bare except -> deep copy of DEFAULTS (D-07)"
    - "_deep_merge recursively merges parsed TOML over DEFAULTS so absent keys keep defaults and extra Phase-2 keys are silently retained (D-09)"
    - "color_for/is_green accept warn/crit as keyword args with defaults — backward-compatible refactor pattern"
    - "cfg dict threaded through render_top_line -> _model_segment and render_bottom_line -> _context_segment/_rate_segment"
    - "toggle gating: `toggles.get('key', True)` with default True preserves behavior when toggle absent from config"
    - "Script deployed outside repo at ~/.claude/ (D-12); test file is the git artifact"

key-files:
  created:
    - "tests/test_config.py (26 TDD tests for config loader + segment toggles)"
    - "~/.claude/claude-statusline.toml (documented default config — outside repo)"
  modified:
    - "~/.claude/claude-statusline.py (outside repo, extended from 242 to ~310 lines)"

key-decisions:
  - "load_config wraps ALL errors in bare except (not just FileNotFoundError/TOMLDecodeError) — maximum resilience for a statusline that must never crash (D-07, T-01-07/T-01-08)"
  - "_deep_merge used instead of dict.update so nested tables (e.g. [thresholds], [toggles]) merge correctly — a partial override table keeps remaining keys from defaults"
  - "color_for and is_green refactored with default params (not positional) so all existing call sites remain valid without change"
  - "cfg threaded as explicit parameter through render functions (not a global) — testable, no hidden state"
  - "Phase-2 keys in TOML (location.lat/lon, cache TTLs) present as comments — reserved in schema but not consumed (D-09)"
  - "render_top_line and render_bottom_line signatures changed to accept cfg — this is a breaking API change from Plan 02 but there is only one call site (main())"

requirements-completed: [CFG-01]

# Metrics
duration: 5min
completed: 2026-05-28
---

# Phase 1 Plan 03: TOML Config — Silent Defaults, Thresholds, and Per-Segment Toggles Summary

**TOML config at ~/.claude/claude-statusline.toml via stdlib tomllib; missing/malformed falls back silently to built-in defaults; four per-segment toggles gate rendering; thresholds configurable with 70/90 defaults preserved**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-28T20:20:23Z
- **Completed:** 2026-05-28T20:25:57Z
- **Tasks:** 2 (Task 1 TDD, Task 2 auto)
- **Files modified:** 4 (script + config deployed externally; test file in repo)

## Accomplishments

- TDD cycle: 26 failing RED tests (config loader, threshold params, toggle gating) → all 26 passing GREEN; plus all 47 prior tests still pass = 73 total
- DEFAULTS dict with thresholds warn=70/crit=90 and four segment toggles (all true) — canonical fallback
- load_config() reads ~/.claude/claude-statusline.toml via tomllib; any error (missing, unreadable, malformed TOML) returns deep copy of DEFAULTS silently — bar always renders (D-07, T-01-07/T-01-08)
- _deep_merge() handles nested TOML tables correctly so partial overrides keep remaining keys from defaults
- color_for / is_green refactored to accept warn/crit params with default values; backward-compatible (all 47 prior tests pass unchanged)
- Per-segment toggles verified: show_thinking_glyph=false drops 💭; show_five_hour=false drops ⏳; show_weekly=false drops 🗓; all-bottom-off leaves top line, exits 0 (D-08)
- Shipped ~/.claude/claude-statusline.toml: documented TOML with Phase-2 keys (location, cache TTLs) present as comments — reserved in schema, not consumed in Phase 1 (D-09)

## Task Commits

Each task was committed atomically (tests are the repo artifact; script+config are outside repo per D-12):

1. **Task 1 RED: Failing config loader tests** - `d468989` (test)
2. **Task 1+2 GREEN: Config loader + default TOML + toggle wiring** - (script + config deployed at ~/.claude/, test already committed in RED)

**Plan metadata:** (docs commit — to follow)

_Note: Task 1 was TDD (RED committed first, then GREEN implemented). Task 2 shares the same RED commit since tests cover both tasks._

## Files Created/Modified

- `~/.claude/claude-statusline.py` — Extended from 242 to ~310 lines; adds DEFAULTS, load_config, _deep_merge; refactors color_for/is_green with warn/crit params; threads cfg through render_top_line, render_bottom_line, _context_segment, _rate_segment; per-segment toggle gating
- `~/.claude/claude-statusline.toml` — Documented default config: [thresholds] warn=70/crit=90, [toggles] show_* all true, [units] placeholder, commented [location] lat/lon and [cache] TTL keys for Phase 2
- `tests/test_config.py` — 26 TDD tests: TestLoadConfigDefaults (6), TestLoadConfigMerge (4), TestColorForWithThresholds (6), TestFallbackRegressionSubprocess (3), TestPerSegmentToggles (7)

## Verification Results

All plan automated verify checks pass:

```
parse-ok
tomllib.load: OK
load_config: OK
toggles (grep): OK
2 lines (fixture)
toml-ok
show_context_bar: OK
warn: OK
2 lines (with default config)
```

Manual explicit toggle verification (per key_decisions_reminder):
- show_thinking_glyph=false: top line shows "[Opus 4.8 (1M context)]" with NO 💭 — PASS
- show_five_hour=false: bottom line has 🗓 but NO ⏳ — PASS
- show_weekly=false: bottom line has ⏳ but NO 🗓 — PASS
- all-bottom-off: top line renders, exits 0 — PASS (test_all_bottom_toggles_false_top_line_still_renders)

## Decisions Made

- `load_config` uses bare `except Exception` (not a specific exception list) to guarantee no error ever escapes — a statusline that might crash Claude Code's bar is unacceptable (D-07, T-01-08)
- `_deep_merge` instead of `dict.update` so partial [thresholds] or [toggles] tables merge correctly with remaining defaults
- `color_for(pct, warn=70, crit=90)` and `is_green(pct, warn=70)` — keyword-only-by-convention params so all prior call sites work unchanged; thresholds sourced from config in main render path
- `cfg` dict threaded as explicit function parameter (not module-level global) for testability
- Phase-2 keys in default TOML as commented blocks — document the schema reservation without consuming them

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All segments render from real stdin data; config file ships with explicit defaults that match built-in behavior.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes at trust boundaries. Config read is stdlib-only (tomllib), no code execution, no eval, no exec. T-01-07, T-01-08, T-01-09, T-01-SC: all mitigated/accepted as specified in plan threat model.

## Self-Check

- `~/.claude/claude-statusline.py`: deployed and executable (extended from 242 lines)
- `~/.claude/claude-statusline.toml`: deployed, parses cleanly with tomllib
- `tests/test_config.py`: in repo, 26 tests pass
- Commit `d468989`: verified in git log
- 73/73 tests pass (26 new + 47 regression)

## Self-Check: PASSED

## Next Phase Readiness

Phase 1 is now complete:
- All three plans (01-01, 01-02, 01-03) are done
- Script at ~/.claude/claude-statusline.py is fully functional: top line, bottom line, TOML config, toggles, thresholds
- Phase 2 (Weather Layer) can begin: config already reserves [location] lat/lon, [cache] TTL keys; DEFAULTS has [units] table stub

---
*Phase: 01-core-statusline*
*Completed: 2026-05-28*
