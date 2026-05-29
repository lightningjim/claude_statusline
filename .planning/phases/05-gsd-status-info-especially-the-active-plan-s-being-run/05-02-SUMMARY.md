---
phase: 05-gsd-status-info-especially-the-active-plan-s-being-run
plan: 02
subsystem: gsd-segment
tags: [segment, top-line, gsd, lifecycle, glyphs, config-toggle]
dependency_graph:
  requires: [_read_gsd_state, _infer_gsd_lifecycle (05-01), _NF_GIT_* pattern (04-02), render_top_line]
  provides: [_NF_GSD_* constants, display.show_gsd default, _gsd_segment builder, render_top_line Phase-05 wiring]
  affects: [claude-statusline.py, tests/test_gsd_segment.py, tests/test_nerd_icons.py, tests/test_skeleton_render.py, tests/test_bootstrap_degradation.py]
tech_stack:
  added: []
  patterns: [_NF_GSD_* PUA codepoint constants, config-toggle gate, project_dir/.planning scoped read, colored-glyph + neutral-label composition, icon_set nerd/emoji fallback, try/except-Exception-return-None outer guard]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_gsd_segment.py
    - tests/test_nerd_icons.py
    - tests/test_skeleton_render.py
    - tests/test_bootstrap_degradation.py
decisions:
  - Used Python chr() to embed actual Unicode codepoints in GSD glyph constants (same approach as existing NF_GIT_* constants)
  - emoji/ascii fallback glyphs use Python unicode escape sequences in double-quoted string literals which Python interprets at runtime
  - E2E test counts brackets between [project] and [model] to verify both [git] and [gsd] are present (bracket_count >= 2)
  - plan-of-total wave_part included in non-done states when plans_done/plans_total are available from STATE.md progress block
metrics:
  duration: "20 min"
  completed: "2026-05-29"
  tasks: 3
  files: 5
---

# Phase 05 Plan 02: _gsd_segment Builder + Top-Line Wiring Summary

**One-liner:** `_gsd_segment` renders active plan id + neutral task progress with a single colored lifecycle glyph (executing/done→GREEN, verifying→YELLOW, blocked→RED, idle→DIM) scoped to `project_dir/.planning`, wired into `render_top_line` after `_git_segment` per D-10, with 20 new tests and all existing tests green.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | _NF_GSD_* glyph constants + display.show_gsd default + cmap guard | 69dc510 | claude-statusline.py, tests/test_nerd_icons.py |
| 2 | _gsd_segment builder + render_top_line wiring + builder/E2E tests | 1b72d0c | claude-statusline.py, tests/test_gsd_segment.py |
| 3 | Update exact-string top-line test fixtures for default-True GSD segment | 43f29af | tests/test_skeleton_render.py, tests/test_bootstrap_degradation.py |

## What Was Built

### `_NF_GSD_*` glyph constants (6 new)

Added after the `_NF_GIT_*` block with the same `_NF_GSD_<ROLE> = "<glyph>"  # nf-<family>-<name>  U+XXXX` comment format. All codepoints are from the planning-validated JetBrains Nerd Font cmap:

- `_NF_GSD_EXECUTING` = U+F04B (fa-play, green)
- `_NF_GSD_VERIFYING` = U+F046 (fa-check_square, yellow)
- `_NF_GSD_BLOCKED` = U+F05E (fa-ban, red)
- `_NF_GSD_DONE` = U+F058 (fa-check_circle, green)
- `_NF_GSD_IDLE` = U+F04C (fa-pause, dim)
- `_NF_GSD_PLAN` = U+F278 (fa-map, neutral)

### `display.show_gsd` default (DEFAULTS)

Added `"show_gsd": True` after `"show_git": True` in the DEFAULTS display block with a Phase-05 comment (D-08 discretion).

### `_gsd_segment(data, cfg)` builder

Mirrors `_git_segment` step-for-step:
1. Config-toggle gate: `show_gsd=False` → None
2. Resolve `project_dir` from `workspace.project_dir` ONLY (D-08, not `current_dir`)
3. Check `os.path.isdir(project_dir/.planning)` → None if absent (silent omit, non-GSD project)
4. `_read_gsd_state(planning_dir)` → None on failure
5. `_infer_gsd_lifecycle(state)` → None on failure
6. Glyph resolution: nerd → `_NF_GSD_*` constants; emoji → ascii/emoji fallbacks (▶/☑/⊘/✓/⏸)
7. Neutral label: `plan_id tasks_done/total_tasks` (no color wrap, D-09)
8. Colored status glyph: lifecycle state maps to ANSI color (D-09)
9. Assembly: `[{label} {wave_part} {status_glyph}]`; done state: `[{milestone} {done_glyph}]` (D-07)
- Outer `try/except Exception: return None` (RUN-01/RUN-02)
- Renders ONLY structured fields — no raw file text (T-05-05 ANSI-injection guard)

### `render_top_line` wiring

`_gsd_segment(data, cfg)` inserted as third segment after `_git_segment` and before `_model_segment` (D-10). Docstring updated to document Phase-05 ordering `[project] [git] [gsd] [model] [weather]`.

### Test updates

- `tests/test_nerd_icons.py`: 6 `_NF_GSD_*` names appended to `GLYPH_CONSTANTS` cmap guard list
- `tests/test_gsd_segment.py`: 20 new tests added (`TestGsdSegmentBuilder` × 18 + `TestGsdSegmentE2E` × 2)
- `tests/test_skeleton_render.py`: `_NO_GIT_HOME` config extended with `show_gsd = false` to preserve exact-string assertion
- `tests/test_bootstrap_degradation.py`: `cfg["display"]` extended with `"show_gsd": False` to preserve ≤2-segment guard

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- `grep -c "^_NF_GSD_" claude-statusline.py` → 6
- `grep -n '"show_gsd": True' claude-statusline.py` → 1 match inside DEFAULTS display block
- `grep -c "_gsd_segment" claude-statusline.py` → 3 (def + render_top_line call + docstring)
- `python -m pytest tests/test_gsd_segment.py -q` → 48 passed (28 Wave-1 + 20 new)
- `python -m pytest tests/test_nerd_icons.py -q` → 94 passed, 20 skipped (cmap guard passes or skips cleanly)
- `python -m pytest tests/test_skeleton_render.py tests/test_bootstrap_degradation.py -q` → 26 passed
- Full suite: 422 passed, 52 skipped — 2 pre-existing Phase 03.1 failures in test_bottom_line.py unchanged; no regressions
- Smoke test: top line output (ANSI stripped) = `[claude_statusline] [main ] [05-02 (14/15) ⏸] [Sonnet 4.5]` — GSD segment appears between git and model as designed

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns outside the designed `.planning/` subtree, or schema changes at trust boundaries introduced.

- T-05-04 (path traversal): `_gsd_segment` delegates all file reads to `_read_gsd_state` (implemented in Plan 01 with fixed-name joins); no additional path construction beyond `os.path.join(project_dir, ".planning")`
- T-05-05 (ANSI injection): builder renders only `plan_id`, integer counts, `milestone`, and fixed `_NF_GSD_*` glyph constants — never raw file text
- T-05-06 (DoS): whole-body `try/except Exception: return None`; no network, no subprocess, no caching

## Self-Check: PASSED

- claude-statusline.py modified: FOUND
- tests/test_gsd_segment.py modified: FOUND
- tests/test_nerd_icons.py modified: FOUND
- tests/test_skeleton_render.py modified: FOUND
- tests/test_bootstrap_degradation.py modified: FOUND
- Commit 69dc510 exists: FOUND (Task 1)
- Commit 1b72d0c exists: FOUND (Task 2)
- Commit 43f29af exists: FOUND (Task 3)
- 48 tests pass in test_gsd_segment.py: VERIFIED
- Full suite: 422 passed, 2 pre-existing failures, no new failures: VERIFIED
