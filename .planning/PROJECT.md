# claude-statusline

## What This Is

A Python statusline command for Claude Code. It reads the session JSON that Claude Code pipes to stdin and prints a two-line, color-coded status bar showing the active project, model (with a thinking indicator), local weather + alerts, context-window usage, and rolling rate-limit usage. It replaces an earlier bash implementation (`.examples/statusline-command.sh`) with cleaner data handling and better formatting. Built for the author's personal use.

## Core Value

At a glance, the bottom of the terminal tells the truth about the current session — how much context and rate-limit headroom remains (and when limits reset) — without slowing Claude Code down.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Top line — `[project] [model 💭] [weather]`**

- [ ] Show the running project (basename of `workspace.project_dir`)
- [ ] Show the model (`model.display_name`)
- [ ] Append a thinking glyph (💭) when `thinking.enabled` is true
- [ ] Show weather as `<icon> <temp>[|🌧️<precip>]|<details>`
- [ ] `<details>` = the next sun event: 🌅 sunrise or 🌇 sunset, whichever comes next
- [ ] Replace `<details>` with an active NWS weather alert when one exists for the configured location

**Second line — context + rate limits**

- [ ] Show context usage as a 20-wide filled/empty bar (`▓░`), colored by threshold
- [ ] Show context usage as an explicit percentage number alongside the bar
- [ ] Show 5-hour rate-limit usage (`rate_limits.five_hour.used_percentage`), colored
- [ ] Show weekly rate-limit usage (`rate_limits.seven_day.used_percentage`), colored
- [ ] For whichever rate-limit indicator is **not green** (≥70%), append its reset time
- [ ] Reset time shorthand: same-day → `5:15pm`; otherwise `Mon 5:15pm`

**Behavior / quality**

- [ ] Color bands: green <70%, yellow 70–90%, red >90% (applied to context, 5h, weekly)
- [ ] Weather and alerts are cached (weather ~10min, alerts ~5min) so rendering never blocks on the network
- [ ] Sunrise/sunset computed locally (no network) from configured lat/lon
- [ ] All settings (lat/lon, thresholds, units, feature toggles, cache TTLs) live in a single config file (TOML)
- [ ] Degrades gracefully: missing stdin fields, no network, or stale cache still produce a valid line

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
| All session data from stdin, not external tools | The stdin payload already includes context, rate limits, thinking state | — Pending |
| NWS + local `astral` sun times (not wttr.in) | Need official weather alerts; NWS lacks sun times so compute them locally | — Pending |
| Cache weather (~10min) / alerts (~5min) to a temp file | Statusline runs often; never block rendering on network | — Pending |
| Inline weather, no right-alignment | No terminal width in stdin; avoids fragile padding | — Pending |
| Project name replaces user@host:cwd prefix | "Project being run" is the useful signal; path was noise | — Pending |
| Single TOML config file | Centralize lat/lon, thresholds, units, toggles, TTLs | — Pending |
| Color bands green<70 / yellow 70–90 / red>90 | Matches the bash predecessor's `perc_color` | — Pending |
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
*Last updated: 2026-05-29 after Phase 03.1 (default-bar test-drift resolution) completion*
