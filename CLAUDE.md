<!-- GSD:project-start source:PROJECT.md -->
## Project

**claude-statusline**

A Python statusline command for Claude Code. It reads the session JSON that Claude Code pipes to stdin and prints a two-line, color-coded status bar showing the active project, model (with a thinking indicator), local weather + alerts, context-window usage, and rolling rate-limit usage. It replaces an earlier bash implementation (`.examples/statusline-command.sh`) with cleaner data handling and better formatting. Built for the author's personal use.

**Core Value:** At a glance, the bottom of the terminal tells the truth about the current session — how much context and rate-limit headroom remains (and when limits reset) — without slowing Claude Code down.

### Constraints

- **Tech stack**: Python ≥3.14 (per `pyproject.toml`); dependencies `requests` (HTTP) and `astral` (local sun times). `requests` is currently imported in `main.py` but not declared — must be added.
- **Runtime contract**: Reads one JSON object from stdin, writes the status line(s) to stdout, exits fast. Must never hang or error out in a way that breaks Claude Code's bar.
- **Weather provider**: NWS (`api.weather.gov`) — free, no key, official alerts, but provides no sunrise/sunset (computed locally).
- **Performance**: Rendering must not block on the network; weather/alert fetches are cached with TTLs.
- **Terminal output**: ANSI color escapes; no guaranteed terminal width available.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
