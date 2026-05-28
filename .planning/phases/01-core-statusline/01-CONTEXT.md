# Phase 1: Core Statusline - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a complete, colored **two-line** status bar driven **entirely from stdin** — no network. Covers:
- Top line: project name + model (with thinking glyph)
- Bottom line: 20-wide `▓░` context bar with explicit %, plus 5-hour and weekly rate-limit usage with reset times for non-green indicators
- Threshold coloring (green/yellow/red) across context, 5h, weekly
- A single TOML config file
- Graceful degradation on missing/malformed stdin

**Out of this phase:** Weather, NWS, alerts, sunrise/sunset, caching, and any third-party dependency (`requests`, `astral`) — all belong to Phase 2 (Weather Layer).

</domain>

<decisions>
## Implementation Decisions

### Line layout & separators
- **D-01:** Two-line, **bracketed-segments** layout. Each top-line segment is wrapped in its own brackets.
- **D-02:** Top line: `[<project>] [<model> 💭]`
  - `<project>` = basename of `workspace.project_dir`
  - `<model>` = `model.display_name` (full string, e.g. `Opus 4.8 (1M context)`)
  - 💭 appended inside the model brackets only when `thinking.enabled` is true
- **D-03:** Bottom line: `[<20-wide ▓░ bar>] <pct>%   ⏳ <5h%>[ <reset>]   🗓 <wk%>[ <reset>]`
  - Context bar is bracketed; explicit percentage follows the bar.
  - Rate-limit indicators use **glyph-only** labels — ⏳ for 5-hour, 🗓 for weekly. No "5h"/"wk" text labels.
- **D-04:** Reset time (`5:15pm` same-day / `Mon 5:15pm` otherwise) is appended **only** to a rate-limit indicator that is **not green** (≥70%), and is rendered **dim/neutral** (not the indicator's color) so the percentage stays the focal point.
- **D-05:** Threshold coloring (green <70 / yellow 70–90 / red >90) applies to: the context bar fill, the context percentage number, the 5-hour %, and the weekly %. (Reset times excepted — dim per D-04.)

### Config location & defaults
- **D-06:** Config file lives at `~/.claude/claude-statusline.toml` (flat, alongside the installed script in `~/.claude/`).
- **D-07:** If the config file is missing or unreadable, fall back **silently to built-in defaults** (thresholds 70/90, units, toggles). The bar always renders out-of-the-box — no error, no prompt.
- **D-08:** Config supports **per-segment toggles** (booleans, e.g. `show_context_bar`, `show_five_hour`, `show_weekly`, `show_thinking_glyph`) in addition to thresholds and units. A toggled-off segment is not rendered.
- **D-09:** Config holds the keys needed across the project (location lat/lon, color thresholds, units, feature toggles, cache TTLs per CFG-01) — but lat/lon/TTLs are consumed in Phase 2; Phase 1 only reads/uses thresholds, units, and toggles.
- TOML is read with stdlib `tomllib` (Python 3.14) — **no third-party dependency** for config.

### Per-segment degradation
- **D-10:** When an individual stdin field is missing or malformed (e.g., no `rate_limits` block, absent `context_window`), **omit just that segment** silently and render everything else. A missing-but-enabled segment simply does not appear. (No placeholders, no assumed-zero.)
- **D-11:** When stdin is empty or not valid JSON, print a **minimal safe line** and exit 0. Never emit a Python traceback or break Claude Code's bar.

### Install & invocation
- **D-12:** Ship as an **executable script at `~/.claude/claude-statusline.py`** with a `#!/usr/bin/env python3` shebang, run directly by system `python3` (≥3.14). No venv/pip required for Phase 1 (zero third-party deps).
- **D-13:** Remove the unused `import requests` from `main.py` for Phase 1 (it's a Phase 2 concern). Phase 1 uses only stdlib (`sys`, `json`, `datetime`, `tomllib`).
- **D-14:** Provide an **install helper** that copies the script to `~/.claude/` and wires the `statusLine` entry in Claude Code's `settings.json` — one step to set up.

### Claude's Discretion
- Exact source-file/module structure (single script vs. internal helpers). Note: the deliverable is a self-contained `~/.claude/claude-statusline.py`, so any structure must collapse into a runnable single file (or the install helper assembles it).
- Percentage rounding strategy (the bash predecessor truncated via `cut -d.`); pick floor or round consistently across all three indicators.
- Exact content of the "minimal safe line" for bad/empty stdin (e.g., empty line vs. bare empty bar) — must be valid and exit 0.
- Whether to honor `NO_COLOR` / a `color` config toggle (ANSI is otherwise always emitted; Claude Code renders it).
- The bar fill math (`filled = pct * 20 / 100`) and rounding of partial cells.

</decisions>

<specifics>
## Specific Ideas

- The selected layout, concretely (5h non-green example):
  ```
  [claude_statusline] [Opus 4.8 (1M context) 💭]
  [▓▓▓▓▓▓▓▓▓░░░░░░░░░░░] 47%   ⏳ 78% 5:15pm   🗓 3%
  ```
  (where `5:15pm` is dim, and 78% is yellow.)
- Carry forward the bash predecessor's feel: `perc_color` thresholds (70/90), the `▓░` 20-wide bar, and ⏳/🗓 rate glyphs — but in cleaner Python with bracketed segments.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & decisions
- `.planning/REQUIREMENTS.md` — RUN-01/02, TOP-01/02/03, CTX-01/02, LIM-01/02/03/04, FMT-01, CFG-01 (the Phase 1 requirement set)
- `.planning/PROJECT.md` — Core value, Key Decisions table, stdin schema notes, constraints
- `.planning/ROADMAP.md` §"Phase 1: Core Statusline" — goal and 5 success criteria

### Reuse / reference sources
- `.examples/statusline-command.sh` — bash predecessor: `perc_color` (70/90), 20-wide `▓░` bar math, ⏳/🗓 glyphs, two-line `printf` layout, reset-time formatting
- `.examples/claude_stdin.json` — real sample stdin payload (use as the primary test fixture)
- `main.py` — current stub to replace (`json.load(sys.stdin)`; drop the `requests` import)
- `pyproject.toml` — `name = "claude-statusline"`, `requires-python = ">=3.14"`, empty deps (keep empty for Phase 1)

No external ADRs or design specs exist — requirements are fully captured in the docs above plus the decisions in this file.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.examples/statusline-command.sh`: directly portable logic — threshold color bands (70/90), the `▓░` fill/empty bar (`FILLED = PCT*20/100`), ⏳/🗓 rate-limit glyphs, two-line composition, epoch→local reset-time formatting.
- `.examples/claude_stdin.json`: canonical input shape — `model.display_name`, `thinking.enabled`, `workspace.project_dir`, `context_window.used_percentage`, `rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}` (resets are unix epoch seconds).
- Python 3.14 stdlib `tomllib` for config reading — no dependency.

### Established Patterns
- Runtime contract: read one JSON object from stdin → write line(s) to stdout → exit fast. Must never hang or error in a way that breaks the bar (RUN-01/02).
- Color is ANSI escapes; no guaranteed terminal width (inline layout, no right-alignment).

### Integration Points
- Output consumed by Claude Code's `statusLine` (configured in `settings.json`) — stdout only; stderr is not displayed.
- Install target is `~/.claude/` (script + `claude-statusline.toml` config), wired via the install helper (D-14).

</code_context>

<deferred>
## Deferred Ideas

- **Phase 2 (Weather Layer):** NWS conditions/temp/precip, active-alert override, local sunrise/sunset via `astral`, temp-file caching, graceful weather degradation. Adds `requests` + `astral` deps — which must then be made available to the system `python3` that runs `~/.claude/claude-statusline.py` (a consequence of D-12; resolve in Phase 2, e.g. install deps for that interpreter or revisit packaging).
- **Phase 2 reuse source:** `/home/kcreasey/Documents/Projects/WxDesktopPy` — NWS HTTP client + `User-Agent`, station lookup, active-alert fetch/dedup.
- **v2 (REQUIREMENTS.md):** ENH-01 session cost, ENH-02 effort/fast-mode indicator, ENH-03 multi-location/auto-geolocation.

</deferred>

---

*Phase: 01-core-statusline*
*Context gathered: 2026-05-28*
