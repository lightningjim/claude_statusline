# Walking Skeleton — claude-statusline

**Phase:** 1
**Generated:** 2026-05-28

## Capability Proven End-to-End

A user installs the command and sees a real top line — `[claude_statusline] [Opus 4.8 (1M context) 💭]` — driven entirely from the JSON Claude Code pipes to the script's stdin, with no network, no crash, and exit 0.

This exercises the tool's full "stack": **stdin → JSON parse → segment render → stdout → installed into settings.json**. There is no DB, no HTTP routing, and no browser UI — this is a single-file Python CLI, so the skeleton's end-to-end path is the read/parse/render/print/install pipeline.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python ≥3.14, run by system `python3` via `#!/usr/bin/env python3` shebang | D-12; pyproject `requires-python = ">=3.14"`; no venv/pip needed |
| Dependencies | Zero third-party in Phase 1 — stdlib only (`sys`, `json`, `datetime`, `tomllib`) | D-13; `requests`/`astral` deferred to Phase 2; `tomllib` is stdlib in 3.14 |
| Deliverable shape | Single self-contained executable script at `~/.claude/claude-statusline.py` | D-12; Claude's-discretion structure must collapse to one runnable file |
| Input contract | Read one JSON object from stdin with `json.load`; never `eval` | RUN-01; security_context — only `json.load`, parse failures degrade safely |
| Config | Single TOML at `~/.claude/claude-statusline.toml`, read with stdlib `tomllib`, silent defaults | D-06, D-07, D-09 (lat/lon + TTL keys reserved for Phase 2) |
| Install / deployment | `install.py` copies the script to `~/.claude/`, sets it executable, and parse-merge-backup wires the `statusLine` entry into `~/.claude/settings.json` (idempotent) | D-14; security_context — never clobber existing keys, back up first |
| Degradation model | Per-field omission for missing/malformed segments (D-10); minimal safe line + exit 0 for empty/invalid stdin (D-11) | RUN-02; the bar must never break Claude Code's statusline |
| Layout | Two-line bracketed-segments; top line uncolored, bottom line threshold-colored | D-01..D-05; no terminal width assumed (inline, no right-align) |
| Output styling | ANSI escapes always emitted (Claude Code renders them); NO_COLOR/color toggle is Claude's discretion | code_context: stdout only, stderr not displayed |

## Stack Touched in Phase 1 (CLI-adapted)

- [x] Project scaffold — executable script + shebang + dep-free `pyproject.toml`; `main.py` stub cleaned (drop `import requests`)
- [x] "Routing" equivalent — the stdin → parse → render → stdout pipeline (single entry point)
- [x] "Persistence" equivalent — config read from `~/.claude/claude-statusline.toml` (read), settings.json wired (write via installer)
- [x] "UI" equivalent — the rendered two-line ANSI bar the user actually sees in Claude Code
- [x] Deployment — `install.py` installs into `~/.claude/` and wires `statusLine`; user sees it live (documented one-step run: `python3 install.py`)

## Out of Scope (Deferred to Later Slices)

Explicit, to prevent later phases from re-litigating Phase 1's minimalism:

- All weather: NWS conditions/temp/precip, active-alert override (Phase 2, WX-01/02/04)
- Local sunrise/sunset via `astral` (Phase 2, WX-03)
- Temp-file caching with TTLs for weather/alerts (Phase 2, WX-05)
- Network resilience / cold-cache graceful weather degradation (Phase 2, WX-06)
- Third-party dependencies `requests` + `astral`, and making them available to the system `python3` that runs the installed script (Phase 2 packaging consequence of D-12)
- v2 enhancements: session cost (ENH-01), effort/fast-mode indicator (ENH-02), multi-location/auto-geolocation (ENH-03)

## Subsequent Slice Plan

Each later phase adds a vertical slice on top of this skeleton without altering its architectural decisions (single stdlib-run executable, stdin contract, TOML config, installer):

- Phase 2 (Weather Layer): the top line gains live NWS weather (`<icon> <temp>[|🌧️<precip>]`), the next sun event computed locally from configured lat/lon, an active-alert override, and a temp-file cache so rendering never blocks on the network. This is where `requests` + `astral` enter and the deferred `location.lat/lon` + cache-TTL config keys become consumed.
