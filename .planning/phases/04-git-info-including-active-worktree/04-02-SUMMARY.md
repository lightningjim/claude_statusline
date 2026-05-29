---
phase: 04-git-info-including-active-worktree
plan: "02"
subsystem: git-segment
tags: [git, segment, nerd-fonts, worktree, tdd]
dependency_graph:
  requires: [04-01]
  provides: [_git_segment, display.show_git, nerd-git-glyphs]
  affects: [render_top_line, tests/test_git_segment.py, tests/test_nerd_icons.py, tests/test_skeleton_render.py]
tech_stack:
  added: []
  patterns: [per-segment-builder, icon_set-glyph-resolution, monkeypatch-testing, subprocess-e2e]
key_files:
  created: []
  modified:
    - claude-statusline.py
    - tests/test_git_segment.py
    - tests/test_nerd_icons.py
    - tests/test_skeleton_render.py
    - tests/test_bootstrap_degradation.py
decisions:
  - "show_git placed in DEFAULTS['display'] next to icon_set/bar_style (not in weather table)"
  - "Git nerd glyphs: U+E0A0 branch, U+F126 worktree, U+F069 dirty, U+F062 ahead, U+F063 behind"
  - "Dirty marker colored YELLOW; ahead colored GREEN; behind colored YELLOW (D-10)"
  - "Detached HEAD shows oid[:7] (7 chars) in branch slot"
  - "Worktree marker prepended only when is_linked and wt_name truthy (D-03/D-04)"
  - "test_fixture_top_line_exact now runs under NO_GIT_HOME config (show_git=false) to keep exact-equality guard"
  - "test_bootstrap_degradation show_git=false in Phase-1-format guard (Rule 1 auto-fix)"
metrics:
  duration_minutes: 10
  completed: "2026-05-29"
  tasks_completed: 3
  files_modified: 5
---

# Phase 04 Plan 02: Git Segment Builder and Wiring Summary

**One-liner:** Live git segment (branch + dirty + ahead/behind + linked-worktree marker) wired into `render_top_line` between project and model using nerd font glyphs validated against the installed font cmap.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Add show_git default + git glyph constants (nerd + fallback) | `9b89434` | claude-statusline.py, tests/test_nerd_icons.py |
| 2 | Implement _git_segment builder (TDD RED + GREEN) | `47b3e9a`, `2ce84d6` | claude-statusline.py, tests/test_git_segment.py |
| 3 | Wire _git_segment into render_top_line + e2e tests | `30ff023` | claude-statusline.py, tests/test_git_segment.py, tests/test_skeleton_render.py, tests/test_bootstrap_degradation.py |

## What Was Built

### Task 1: show_git default + git glyph constants

Added `"show_git": True` to `DEFAULTS["display"]` (next to `icon_set`/`bar_style`, NOT in the weather table as specified). Added five nerd glyph constants for git state:

- `_NF_GIT_BRANCH = ""` (U+E0A0, `nf-pl-branch` - powerline branch symbol)
- `_NF_GIT_WORKTREE = ""` (U+F126, `nf-fa-code_fork` - fork shape for linked worktrees)
- `_NF_GIT_DIRTY = ""` (U+F069, `nf-fa-asterisk` - single-cell dirty flag)
- `_NF_GIT_AHEAD = ""` (U+F062, `nf-fa-arrow_up` - ahead of upstream)
- `_NF_GIT_BEHIND = ""` (U+F063, `nf-fa-arrow_down` - behind upstream)

All 5 codepoints verified present in the installed JetBrains Nerd Font cmap via `tests/test_nerd_icons.py` (no tofu). Extended `TestAllNerdGlyphConstantsInInstalledFont.GLYPH_CONSTANTS` with all 5 new constants.

### Task 2: _git_segment builder

Implemented `def _git_segment(data: dict, cfg: dict) -> str | None` following the `_project_segment` shape:

1. Checks `cfg.get("display", {}).get("show_git", True)` - returns None if toggled off
2. Resolves `repo_dir = workspace.current_dir or cwd or os.getcwd()` (D-08)
3. Calls `_run_git(["status", "--porcelain=v2", "--branch"], repo_dir)` - timeout-guarded
4. Parses via `_parse_git_status_v2()` - pure function from Plan 01
5. Calls `_run_git(["rev-parse", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"], repo_dir)`
6. Detects linked worktree via `_detect_linked_worktree()` - realpath-divergence from Plan 01
7. Resolves glyphs from `icon_set`: nerd (`_NF_GIT_*`) or emoji/ascii fallbacks (`⑂`/`✚`/`↑`/`↓`)
8. Builds neutral branch label (no color); detached HEAD uses `oid[:7]` (7 chars exactly)
9. Dirty marker: `YELLOW + _NF_GIT_DIRTY + RESET` only when `st["dirty"]`
10. Ahead/behind: `GREEN/YELLOW + glyph + count + RESET` only when `> 0`; omitted entirely when no upstream (None)
11. Worktree prefix: `<wt_glyph> <wt_name> ` prepended ONLY when `is_linked and wt_name`
12. Returns `f"[{interior}]"` or None on any error (full try/except wrapper)

TDD: RED commit (`47b3e9a`) with 17 failing builder tests, GREEN commit (`2ce84d6`) passing all 44 tests in `test_git_segment.py`.

### Task 3: render_top_line wiring + end-to-end tests

Inserted `_git_segment(data, cfg)` into `render_top_line`'s `segments` list between `_project_segment(data)` and `_model_segment(...)` (D-09 ordering).

Updated `tests/test_skeleton_render.py`:
- `test_fixture_top_line_exact` now runs under `_NO_GIT_HOME` (a temp home with `[display]\nshow_git = false`) to keep the exact-equality contract `[claude_statusline] [Opus 4.8 (1M context) ]` valid.
- Added `test_d09_git_segment_between_project_and_model`: asserts a `[` bracket appears between `[claude_statusline]` and `[Opus 4.8 (1M context)` in the actual fixture render.

Added `TestGitSegmentE2E` in `tests/test_git_segment.py`:
- `test_e2e_repo_dir_shows_git_segment_between_project_and_model`: pipes the project repo as `workspace.current_dir` and asserts D-09 ordering (project < git bracket < model)
- `test_e2e_non_repo_dir_omits_git_segment_exits_zero`: non-repo temp dir omits git segment, exits 0, no traceback
- `test_e2e_empty_stdin_exits_zero`: never-crash contract

## Verification Results

### Scoped gate (phase-owned suites)

```
python3 -m pytest tests/test_git_segment.py tests/test_nerd_icons.py tests/test_skeleton_render.py
  150 passed, 20 skipped, 214 subtests passed
```

Exit 0. No failures.

### Full suite

```
python3 -m pytest tests/
  374 passed, 52 skipped, 2 failed
```

The 2 failures are the pre-existing Phase-3 gradient/shade-default regression (out of scope):
- `tests/test_bottom_line.py::TestBottomLineFixture::test_bottom_line_bar_fill_cells`
- `tests/test_bottom_line.py::TestBarStylePresets::test_default_no_config_shade_unchanged`

No NEW failures introduced.

### Security check

```
grep -v '^#' claude-statusline.py | grep -c 'shell=True'
  1  (a docstring line in _run_git, not actual code)
```

No actual `shell=True` subprocess calls. Fixed-argv list discipline preserved.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_bootstrap_degradation.py breaking on git segment wiring**
- **Found during:** Task 3 (full suite run after wiring git into render_top_line)
- **Issue:** `test_top_line_no_weather_equals_phase1_format` asserted `len(parts) <= 2` (at most 2 segments). After Phase-4 wiring, the real fixture produces 3 segments: `[project] [git] [model]`, breaking the pre-wiring assumption.
- **Fix:** Added `"display": {"show_git": False, "icon_set": "nerd", "bar_style": "shade"}` to that test's cfg so it truly tests "Phase-1 format with no git and no weather" as intended.
- **Files modified:** `tests/test_bootstrap_degradation.py`
- **Commit:** `30ff023`

## Known Stubs

None. All data flows live: git state read from the real subprocess on every render (D-07 no cache).

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers (T-04-05 through T-04-08). The git segment uses fixed-argv subprocess exclusively.

## TDD Gate Compliance

- RED gate commit: `47b3e9a` (`test(04-02): add failing tests for _git_segment builder`)
- GREEN gate commit: `2ce84d6` (`feat(04-02): implement _git_segment builder`)

Both gates present in git log in correct order.

## Self-Check: PASSED

Files created/modified:
- `claude-statusline.py` - FOUND (contains `def _git_segment` and `"show_git": True`)
- `tests/test_git_segment.py` - FOUND (contains `TestGitSegmentBuilder` and `TestGitSegmentE2E`)
- `tests/test_nerd_icons.py` - FOUND (contains `_NF_GIT_BRANCH` in GLYPH_CONSTANTS)
- `tests/test_skeleton_render.py` - FOUND (contains `test_d09_git_segment_between_project_and_model`)
- `tests/test_bootstrap_degradation.py` - FOUND (contains `show_git=False` fix)

Commits verified:
- `9b89434` - Task 1 constants + show_git default
- `47b3e9a` - TDD RED tests
- `2ce84d6` - TDD GREEN implementation
- `30ff023` - Wiring + e2e tests

Scoped test gate: `pytest tests/test_git_segment.py tests/test_nerd_icons.py tests/test_skeleton_render.py` => 150 passed, 0 failed.
