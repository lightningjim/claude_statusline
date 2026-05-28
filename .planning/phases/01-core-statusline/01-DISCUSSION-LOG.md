# Phase 1: Core Statusline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 1-Core Statusline
**Areas discussed:** Line layout & separators, Config location & defaults, Per-segment degradation, Install & invocation

---

## Line layout & separators

### Overall two-line layout

| Option | Description | Selected |
|--------|-------------|----------|
| Predecessor style | Bare project on top, model in brackets; bottom brackets the bar, rate glyphs joined with a pipe | |
| Bracketed segments | Every segment wrapped in its own brackets; bottom line spaces out indicators with labels | ✓ |
| Minimal / no brackets | No brackets, segments separated by spacing | |

**User's choice:** Bracketed segments.

### Rate-limit labels

| Option | Description | Selected |
|--------|-------------|----------|
| Keep label + glyph | `5h ⏳ 78%` / `wk 🗓 3%` | |
| Glyph only | `⏳ 78%` / `🗓 3%` | ✓ |
| Label only | `5h 78%` / `wk 3%` | |

**User's choice:** Glyph only.

### Reset-time color

| Option | Description | Selected |
|--------|-------------|----------|
| Same as indicator | Reset inherits yellow/red of its indicator | |
| Dim / neutral | Reset dim/gray so % stays focal | ✓ |

**User's choice:** Dim / neutral.

**Notes:** Final layout — `[project] [model 💭]` on top; `[‹20-wide ▓░ bar›] <pct>%   ⏳ <5h%>[ <reset>]   🗓 <wk%>[ <reset>]` on bottom. Reset shown only for non-green indicators.

---

## Config location & defaults

### Config path

| Option | Description | Selected |
|--------|-------------|----------|
| XDG ~/.config | `~/.config/claude-statusline/config.toml` | |
| Next to the script | `config.toml` beside main.py | |
| Env-var override | XDG default + `$CLAUDE_STATUSLINE_CONFIG` | |
| Other (free text) | "In the .claude folder itself where the script also should be" | ✓ |

**User's choice:** `~/.claude/` — config lives alongside the script.

### Missing-config behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Silent built-in defaults | Use code defaults if no file; always works out of box | ✓ |
| Defaults + write a starter file | Use defaults AND write a commented config on first run | |
| Require config, error if absent | Refuse to run without config | |

**User's choice:** Silent built-in defaults.

### Config filename (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| claude-statusline.toml | `~/.claude/claude-statusline.toml` (flat) | ✓ |
| statusline/config.toml | `~/.claude/statusline/config.toml` (subdir) | |

**User's choice:** `~/.claude/claude-statusline.toml`.

### Segment toggles (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Per-segment toggles | Booleans like show_context_bar, show_five_hour, etc. | ✓ |
| No toggles in v1 | Always render every segment | |

**User's choice:** Per-segment toggles.

---

## Per-segment degradation

### Missing/malformed individual field

| Option | Description | Selected |
|--------|-------------|----------|
| Omit the segment | Silently drop just that segment, render the rest | ✓ |
| Show a placeholder | Render `—`/`?` marker | |
| Assume zero/empty | Treat missing numerics as 0 (bash `// 0` style) | |

**User's choice:** Omit the segment.

### Empty / invalid stdin

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal safe line | Print harmless fallback, exit 0; never a traceback | ✓ |
| Nothing, exit 0 | Print empty line, exit clean | |
| Diagnostic to stderr | Empty/minimal stdout + parse error to stderr | |

**User's choice:** Minimal safe line.

---

## Install & invocation

### Packaging

| Option | Description | Selected |
|--------|-------------|----------|
| Executable script in ~/.claude | Self-contained `~/.claude/claude-statusline.py`, shebang, system python3.14 | ✓ |
| pip console entry point | [project.scripts] installed into a venv | |
| Script in ~/.claude + venv python | Script in ~/.claude run by a dedicated venv python | |

**User's choice:** Executable script in ~/.claude.

### Claude Code wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Document it | Provide settings.json snippet for the user to paste | |
| Install helper / script | Ship a step that wires settings.json + copies the script | ✓ |
| You decide | Let planning pick the lightest approach | |

**User's choice:** Install helper / script.

**Notes:** Consequence captured for Phase 2 — system-python invocation means Phase 2's `requests`/`astral` deps must be made available to that interpreter (or packaging revisited).

---

## Claude's Discretion

- Source-file/module structure (must collapse to a runnable single `~/.claude/claude-statusline.py`).
- Percentage rounding (floor vs round), applied consistently.
- Exact content of the minimal safe line.
- `NO_COLOR` / color-toggle handling.
- Bar fill math and partial-cell rounding.

## Deferred Ideas

- Phase 2 Weather Layer (NWS, alerts, sunrise/sunset, caching, `requests`+`astral`).
- Phase 2 reuse from `/home/kcreasey/Documents/Projects/WxDesktopPy`.
- v2: session cost (ENH-01), effort/fast-mode indicator (ENH-02), multi-location/geolocation (ENH-03).
