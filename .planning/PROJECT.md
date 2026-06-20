# claude-statusline

## What This Is

A Python statusline command for Claude Code. It reads the session JSON that Claude Code pipes to stdin and prints a two-line, color-coded status bar showing the active project, git branch/worktree, GSD planning status, model (with a thinking indicator), local weather + alerts, context-window usage, rolling rate-limit usage, and a quiet-when-healthy Claude service-health indicator. It replaces an earlier bash implementation (`.examples/statusline-command.sh`) with cleaner data handling and better formatting. Built for the author's personal use.

## Core Value

At a glance, the bottom of the terminal tells the truth about the current session — how much context and rate-limit headroom remains (and when limits reset) — without slowing Claude Code down.

## Current Milestone: v1.1 QOL and fixes

**Goal:** Harden and polish the shipped statusline through daily use — fix issues surfaced in real usage and clear carried-over tech debt.

**Target features:**
- OSC 8 clickable links for Claude Status events and weather alerts, degrading to plain text where unsupported
- Alert timing display — distinguish issued-but-not-yet-active from active alerts (`from <start>` vs `until <end>`), 12hr am/pm with same-day / `Tmrw. at` / `Wed at` formatting
- v1.0 tech-debt cleanup — the 5-item audit bundle (version sync, `requirements-completed` backfill, REQUIREMENTS footer/traceability, system-python weather tests, WX-05 TTL drift)

## Current State

**Shipped:** v1.0 MVP — 2026-06-20 (12 phases, 28 plans; milestone audit PASSED, 19/19 requirements). See `.planning/MILESTONES.md` and `.planning/milestones/v1.0-*`.

Single-file `claude-statusline.py` + a stdlib-only test suite (727 passing, 60 venv-gated skips). Installed at `~/.claude/claude-statusline/` (script + `.venv` + TOML config); `main()` re-execs into the venv so `requests`/`astral` resolve at runtime.

## Requirements

### Validated (v1.0)

- ✓ Two-line bar from stdin — `[project] [model 💭]` top line — v1.0 (RUN-01/02, TOP-01/02/03)
- ✓ NWS weather — condition icon + temp + precip, local sun events, active-alert override — v1.0 (WX-01..06)
- ✓ 20-wide `▓░` context bar + explicit % — v1.0 (CTX-01/02)
- ✓ 5h + weekly rate limits, threshold-colored, reset time shown for non-green — v1.0 (LIM-01..04, FMT-01)
- ✓ Single TOML config: lat/lon, thresholds, units, toggles, cache TTLs — v1.0 (CFG-01)
- ✓ Non-blocking cached weather/alerts + graceful degradation (exit 0 on any bad input) — v1.0 (WX-05/06, RUN-02)

**Enhancements shipped beyond the v1 requirement set** (CONTEXT-driven, no v1 REQ-IDs): Nerd Font icon set with live moon phases (Ph 02.1) · Watch/Warning/Advisory classification (Ph 02.2) · context-bar fill presets (Ph 3) · git segment (Ph 4) · GSD-status segment (Ph 5) · Claude service-health indicator + incident filter/dismiss + resolved-vs-unresolved (Ph 6/7/07.1).

### Active (v1.1 "QOL and fixes")

- [ ] Clickable links (OSC 8) for Claude Status events and weather alerts, degrading to plain text where unsupported
- [ ] Alert timing display — distinguish issued-but-not-yet-active alerts (`from <onset>`) from active alerts (`until <ends>`), with `effective`/`expires` fallbacks and 12hr am/pm same-day / `Tmrw. at` / `Wed at` time formatting
- [ ] Tech-debt cleanup phase: pyproject/`_APP_VERSION` sync, SUMMARY `requirements-completed` backfill, REQUIREMENTS footer, system-python weather-test coverage, WX-05 TTL text/code drift (full list in `milestones/v1.0-MILESTONE-AUDIT.md`)
- [ ] Further QOL improvements discovered through daily use (insert-phase as they surface)

### Out of Scope

- Right-aligning the weather to the terminal edge — Claude Code's stdin JSON has no terminal width; chosen inline layout instead (avoids fragile padding math)
- `user@host:cwd` PS1 prefix from the bash version — replaced by project name; the full path was noise
- Non-NWS weather providers (OpenWeatherMap, wttr.in) — NWS chosen for official alerts; not building provider abstraction for v1
- Multi-user / general distribution — this is personal tooling, configured for one location/user

## Context

**Replaces a bash script.** `.examples/statusline-command.sh` is the working predecessor. It already establishes: ANSI color helper (`perc_color`, same 70/90 thresholds), the `▓░` context bar, the `⏳`/`🗓️` rate-limit glyphs, and a sunrise/sunset block. It sourced weather from `wttr.in`; this project pivots to NWS for real alerts.

**stdin schema is rich** (`.examples/claude_stdin.json`). Everything except weather is already provided on stdin — no external lookups needed for model, project, context, cost, thinking state, or rate limits:
- `model.display_name`, `model.id`, `effort.level`, `fast_mode`
- `thinking.enabled`
- `context_window.{used_percentage, remaining_percentage, context_window_size, total_input_tokens, ...}`
- `rate_limits.five_hour.{used_percentage, resets_at}`, `rate_limits.seven_day.{used_percentage, resets_at}` (resets are unix epoch seconds)
- `workspace.{project_dir, current_dir}`, `cwd`, `cost.*`, `session_id`, `version`

**NWS reuse source — `/home/kcreasey/Documents/Projects/WxDesktopPy`.** An existing Python project that already pulls from NWS. Reusable pieces:
- `src/wx_desktop_py/infrastructure/http/client.py` and `infrastructure/http/user_agent.py` — NWS requires a descriptive `User-Agent`; this is already solved
- `src/wx_desktop_py/infrastructure/sources/nws/` — station lookup and NWS endpoints
- `src/wx_desktop_py/application/fetch_active_alerts.py` and `application/alerts/dedup.py` — active-alert fetching and dedup
- Its `.planning/research/STACK.md` may inform NWS specifics

**Performance matters.** The statusline command runs frequently. Network calls on every render (as the bash `curl wttr.in` did) add latency and risk NWS rate limits — hence the caching requirement.

## Constraints

- **Tech stack**: Python ≥3.14 (per `pyproject.toml`); dependencies `requests` (HTTP) and `astral` (local sun times). `requests` is currently imported in `main.py` but not declared — must be added.
- **Runtime contract**: Reads one JSON object from stdin, writes the status line(s) to stdout, exits fast. Must never hang or error out in a way that breaks Claude Code's bar.
- **Weather provider**: NWS (`api.weather.gov`) — free, no key, official alerts, but provides no sunrise/sunset (computed locally).
- **Performance**: Rendering must not block on the network; weather/alert fetches are cached with TTLs.
- **Terminal output**: ANSI color escapes; no guaranteed terminal width available.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| All session data from stdin, not external tools | The stdin payload already includes context, rate limits, thinking state | ✅ v1.0 |
| NWS + local `astral` sun times (not wttr.in) | Need official weather alerts; NWS lacks sun times so compute them locally | ✅ v1.0 |
| Cache weather (~10min) / alerts (~5min) to a temp file | Statusline runs often; never block rendering on network | ✅ v1.0 |
| Inline weather, no right-alignment | No terminal width in stdin; avoids fragile padding | ✅ v1.0 |
| Project name replaces user@host:cwd prefix | "Project being run" is the useful signal; path was noise | ✅ v1.0 |
| Single TOML config file | Centralize lat/lon, thresholds, units, toggles, TTLs | ✅ v1.0 |
| Color bands green<70 / yellow 70–90 / red>90 | Matches the bash predecessor's `perc_color` | ✅ v1.0 |
| Nerd Font icon set with `icon_set` toggle (default nerd, emoji fallback) | Installed Nerd Fonts unlock granular day/night + live moon-phase glyphs with semantic color; cmap-guarded | ✅ Phase 02.1 |
| Context-bar fill presets via `display.bar_style` (shade default / solid / solid-dim / gradient) | Selectable fill styles incl. a sub-cell eighth-block gradient; filled=threshold color, empty=dim gray; independent of `icon_set`; unknown values degrade to shade | ✅ Phase 3 |
| Read-only git segment via `display.show_git` (branch/dirty/ahead-behind + linked-worktree marker) | Timeout-guarded, runs every render (no cache), neutral label + colored state, scoped to `current_dir`; omits silently off-repo | ✅ Phase 4 |
| Read-only GSD-status segment via `display.show_gsd` (active plan + task progress + lifecycle glyph) | Reads `.planning/` under `project_dir`; HANDOFF-first/roadmap-fallback with staleness window; milestone-complete confirmed from STATE `progress` (not a fall-through); untrusted labels sanitized; never blocks/crashes; omits silently off-GSD | ✅ Phase 5 |
| Default `bar_style` stays `shade`; full-run tests must isolate `$HOME` | Two "default bar" tests were failing because `run_script` spawns the real script, which reads the developer's live config (`bar_style="gradient"`) — a test-isolation leak, not a code drift. Default kept at `shade` (Phase-3 D-09 preserved, production code untouched); the tests now run under an empty `_NO_CONFIG_HOME` so they assert the true no-config fallback. Any full-run test asserting baseline render must override `$HOME` | ✅ Phase 03.1 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-20 after starting milestone v1.1 QOL and fixes*
