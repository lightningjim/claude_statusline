---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Phase 6 context gathered
last_updated: "2026-06-16T20:09:42.435Z"
last_activity: 2026-06-07
progress:
  total_phases: 10
  completed_phases: 9
  total_plans: 19
  completed_plans: 19
  percent: 90
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-28)

**Core value:** At a glance, the bottom of the terminal tells the truth about the current session — context and rate-limit headroom (and when limits reset) — without slowing Claude Code down.
**Current focus:** Phase 03 — presets for the type of block fill for the progress bar incl

## Current Position

Phase: 03
Plan: Not started
Status: Ready to plan
Last activity: 2026-06-07

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 18
- Average duration: 14 min
- Total execution time: 0.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-core-statusline | 3/3 | 32 min | 10.7 min |
| 02-weather-layer | 2/3 | 60 min | 30 min |
| 2 | 3 | - | - |
| 02.1 | 3 | - | - |
| 03 | 2 | - | - |
| 05 | 2 | - | - |
| 03.1 | 1 | - | - |
| 05.1 | 1 | - | - |
| 02.2 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (12 min), 01-02 (15 min), 01-03 (5 min), 02-01 (25 min), 02-02 (35 min)
- Trend: On track

*Updated after each plan completion*
| Phase 02.1 P01 | 3 min | 2 tasks | 2 files |
| Phase 02.1 P02 | 35 min | 2 tasks | 3 files |
| Phase 02.1-nerd-font-icon-set P03 | 30 | 3 tasks | 2 files |
| Phase 03 P01 | 4 | 2 tasks | 4 files |
| Phase 03 P02 | 7 | 3 tasks | 2 files |
| Phase 04 P01 | 15m | 3 tasks | 2 files |
| Phase 05 P02 | 20 min | 3 tasks | 5 files |
| Phase 03.1 P01 | 10 | 2 tasks | 1 files |
| Phase 02.2-differentiate-between-watches-warnings-and-advisories P01 | 25 | 3 tasks | 3 files |
| Phase 02.2 P02 | 20 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- All session data from stdin — no external lookups needed for model, context, rate limits
- Single TOML config file for all settings
- NWS + local astral sun times (not wttr.in)
- Cache weather (~10min) / alerts (~5min) to temp file
- Reuse NWS HTTP client from WxDesktopPy at `/home/kcreasey/Documents/Projects/WxDesktopPy`
- Script delivered directly to ~/.claude/claude-statusline.py (D-12) — superseded in Phase 2 by D2-02 subfolder install
- Phase 2 install root: ~/.claude/claude-statusline/ (script + .venv + config) (D2-02)
- Script self-re-execs into .venv/bin/python at startup; settings.json uses python3 (D2-03)
- _WEATHER_OK = _ASTRAL_OK and _REQUESTS_OK — both must import for weather; missing venv/deps omit only weather segment (D2-12)
- tomllib imported in skeleton so import surface is final for Phase 1 before Plan 03 consumes it
- Per-segment builders return None to omit silently, no placeholders (D-10)
- Minimal safe line for bad/empty stdin is blank line — exits 0, no misleading content (D-11)
- color_for uses strictly >90 for red (90 is yellow); is_green uses <70 (exactly mirrors D-04 >=70)
- fmt_reset wraps fromtimestamp in try/except — out-of-range epoch omits reset suffix (T-01-05)
- Three spaces between bottom-line segments per D-03 layout
- load_config wraps ALL errors in bare except so no config failure ever crashes the bar (D-07, T-01-07/T-01-08)
- _deep_merge for nested TOML tables — partial overrides keep remaining defaults
- color_for/is_green refactored with warn/crit default params; backward-compatible with all prior call sites
- cfg threaded as explicit parameter through render functions (not a global) for testability
- Lockfile uses O_CREAT|O_EXCL (atomic create) — fails immediately if file exists; removed in finally to prevent stale lock after crash (T-02-09)
- c_to_unit uses round() not floor for temperatures — rounding reads better at human-scale
- _icon_to_emoji: textDescription match first, then NWS icon URL path; falls back to thermometer glyph
- section_within_ceiling uses <= at max-stale boundary; section_is_fresh uses < at TTL boundary
- maybe_spawn_refresh: fixed argv [sys.executable, __file__, "--refresh"], start_new_session=True; never .wait()/.communicate() (T-02-08)
- fetch_weather stores raw NWS tokens (text_desc + icon_url) not a baked glyph; glyph resolved at render by _icon_to_glyph (D-04/D-07)
- _condition_category() is a separate helper from _icon_to_glyph so the resolver stays pure and testable
- fzra and rasn share wi-rain-mix glyph (U+E311) per Weather Icons spec — no distinct codepoint; test relaxed accordingly
- _NWS_ICON_MAP_NERD uses 3-tuple (keywords, glyph, category) extending the 2-tuple emoji shape for semantic color lookup
- _GSD_MAX_BYTES=65536 byte cap per .planning/ file — generous for all three files while bounding DoS risk (T-05-01)
- _GSD_HANDOFF_STALE_SECONDS=3600 (1 h) — D-05 documented staleness window; executor always writes on checkpoint
- STATE.md frontmatter hand-parsed (split on --- delimiters) — no new dep, matches project stdlib-only convention
- lifecycle priority for GSD segment: blocked > verifying > executing > idle > done (D-03); roadmap regex fallback for first [ ] plan
- _NF_GSD_* PUA codepoints embedded as literal Unicode characters (chr() approach) — same pattern as existing _NF_GIT_* constants
- emoji/ascii fallback glyphs for GSD segment: ▶/☑/⊘/✓/⏸ — consistent with plan-spec and distinct from nerd codepoints
- plan-of-total wave_part included neutrally in GSD segment when plans_done/plans_total available from STATE.md progress block (D-04)

### Roadmap Evolution

- Phase 3 added: Presets for the type of block fill for the progress bar (including the one in place but I'm sure there's other visually interesting variations)
- Phase 4 added: git info including active worktree
- Phase 5 added: GSD status info especially the active Plan(s) being run
- Phase 02.1 inserted after Phase 2: Nerd Font icon set — weather glyphs + other segment glyphs, pulled forward from v2 ENH-04 (URGENT)
- Phase 03.1 inserted after Phase 3: Resolve default bar gradient vs shade test drift (URGENT)
- Phase 05.1 inserted after Phase 05: Fix TestGsdSegmentBuilder environment-leak test failures (URGENT)
- Phase 02.2 inserted after Phase 2: Differentiate between watches, warnings, and advisories (URGENT)
- Phase 6 added: Add Claude Status onto the right end of the Claude usage line

### Pending Todos

None yet.

### Blockers/Concerns

None. (The `import requests` in main.py was removed in Plan 01-01 per D-13.)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260606-kpt | Commit the D-10 GSD-fragment omit-not-fake fix | 2026-06-06 | c5e394e | [260606-kpt-commit-the-d-10-gsd-fragment-omit-not-fa](./quick/260606-kpt-commit-the-d-10-gsd-fragment-omit-not-fa/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | ENH-01: Show session cost | Deferred | Init |
| v2 | ENH-02: Show effort/fast-mode indicator | Deferred | Init |
| v2 | ENH-03: Multi-location / auto-geolocation | Deferred | Init |

## Session Continuity

Last session: 2026-06-16T20:09:42.425Z
Stopped at: Phase 6 context gathered
Resume file: .planning/phases/06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin/06-CONTEXT.md
