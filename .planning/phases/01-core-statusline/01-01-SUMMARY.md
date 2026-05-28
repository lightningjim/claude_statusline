---
phase: 01-core-statusline
plan: "01"
subsystem: cli
tags: [python, stdlib, json, tomllib, statusline, install]

# Dependency graph
requires: []
provides:
  - "Executable ~/.claude/claude-statusline.py: reads stdin JSON, renders top line [project] [model 💭], exits 0"
  - "install.py: idempotent parse-merge-backup installer that wires statusLine in ~/.claude/settings.json"
  - "Cleaned main.py: no import requests, stdlib-only stub"
  - "Confirmed dep-free pyproject.toml: dependencies = []"
  - "TDD test suite: tests/test_skeleton_render.py (8 tests, all green)"
affects: [01-02-PLAN, 01-03-PLAN, 02-weather-layer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "stdlib-only Python 3.14 with shebang #!/usr/bin/env python3"
    - "json.loads wrapped in try/except for safe stdin degradation"
    - "Per-segment builders returning str | None; omit-on-None rendering"
    - "parse-merge-backup pattern for settings.json: load → backup → merge → write"

key-files:
  created:
    - "~/.claude/claude-statusline.py (outside repo, executable, min 40 lines)"
    - "install.py"
    - "tests/test_skeleton_render.py"
    - ".examples/claude_stdin.json"
    - ".examples/statusline-command.sh"
  modified:
    - "main.py (removed import requests)"

key-decisions:
  - "Script delivered directly to ~/.claude/claude-statusline.py (D-12) — not tracked by git, intentional"
  - "tomllib imported now so import surface is final for Phase 1; not consumed until Plan 03"
  - "Per-segment builders return None to omit silently, no placeholder text (D-10)"
  - "Minimal safe line for bad/empty stdin is an empty string — prints a blank line, exits 0 (D-11)"

patterns-established:
  - "render_top_line(data): builds segment list, filters None, joins with space"
  - "install.py: stdlib-only, idempotent, backs up before any write, exits non-zero on malformed JSON"

requirements-completed: [RUN-01, RUN-02, TOP-01, TOP-02, TOP-03]

# Metrics
duration: 12min
completed: 2026-05-28
---

# Phase 1 Plan 01: Walking Skeleton Summary

**Executable ~/.claude/claude-statusline.py renders `[project] [model 💭]` from Claude Code's stdin JSON, installed via a parse-merge-backup settings.json helper, with full TDD coverage and graceful degradation to exit 0 on any bad input**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-28T20:05:05Z
- **Completed:** 2026-05-28T20:17:00Z
- **Tasks:** 2 (Task 3 is checkpoint:human-verify, awaiting auto-approval)
- **Files modified:** 6

## Accomplishments

- Walking Skeleton proven end-to-end: stdin JSON → parse → render → stdout → installed into settings.json
- TDD cycle: 8 failing tests (RED), then implementation passing all 8 (GREEN)
- install.py wired the real ~/.claude/settings.json, preserving all 7 existing keys, with backup
- install.py confirmed idempotent: second run prints "statusLine already correct" and changes nothing
- main.py cleaned: removed undeclared `import requests` (D-13)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Skeleton render tests** - `8b8121e` (test)
2. **Task 1 (GREEN): Skeleton render implementation** - `534d2f9` (feat)
3. **Task 2: Install helper + clean main.py** - `623fab8` (feat)

_Note: Task 3 is checkpoint:human-verify — awaiting visual confirmation in a live Claude Code session._

## Files Created/Modified

- `~/.claude/claude-statusline.py` — Executable statusline script (outside repo, D-12); shebang `#!/usr/bin/env python3`; imports: sys json os tomllib datetime; renders `[project] [model 💭]` top line; graceful degradation on any bad input
- `install.py` — Idempotent installer: sets chmod 0o755 on script, parse-merge-backup of ~/.claude/settings.json, preserves all existing keys, stdlib-only
- `main.py` — Stub cleaned: removed `import requests` (D-13), now stdlib-only
- `pyproject.toml` — Confirmed dep-free: `dependencies = []` (no changes)
- `tests/test_skeleton_render.py` — 8 TDD tests covering: fixture exact output, thinking glyph true/false/absent, missing model block, empty/non-JSON stdin, shebang, imports
- `.examples/claude_stdin.json` — Canonical test fixture (project=claude_statusline, model=Opus 4.8 (1M context), thinking.enabled=true)
- `.examples/statusline-command.sh` — Bash predecessor for reference (perc_color, 20-wide bar, glyphs)

## Decisions Made

- `tomllib` imported now even though Plan 03 is when config is consumed — keeps the import surface final and avoids a future diff touching this structural boundary (plan directive)
- Minimal safe line on empty/invalid stdin is an empty string (prints blank line) — meets "valid line, exit 0" requirement with zero risk of emitting misleading content (D-11, Claude's discretion)
- Script lives outside repo at `~/.claude/claude-statusline.py` as intended (D-12) — not tracked by git; install.py is the delivery mechanism

## Deviations from Plan

None — plan executed exactly as written. The threat model mitigations (T-01-01 through T-01-SC) were all applied as specified: `json.loads` only (never eval), parse-merge-backup, dep-free.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Running `python3 install.py` is the one-step setup.

## Checkpoint Pending

**Task 3: Verify the Walking Skeleton renders live in the statusline** — `checkpoint:human-verify`

The automation is complete:
- `~/.claude/claude-statusline.py` installed and executable
- `~/.claude/settings.json` updated (backup at `~/.claude/settings.json.bak`)
- install.py run twice, confirmed idempotent

Awaiting human visual confirmation that the top line `[claude_statusline] [Opus 4.8 (1M context) 💭]` appears in a live Claude Code session.

## Next Phase Readiness

- Plan 02 (Bottom line: context bar + rate limits) can begin immediately — the render pipeline is wired
- `render_top_line()` and `main()` structure is designed for Plan 02 to append a second `print()` call
- Plan 03 (TOML config) — `tomllib` import is already present; `_load_stdin()` and `render_top_line()` accept a `config` parameter slot when Plan 03 is ready

---
*Phase: 01-core-statusline*
*Completed: 2026-05-28*
