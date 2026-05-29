---
phase: 04-git-info-including-active-worktree
plan: "01"
subsystem: git-helpers
tags: [git, subprocess, parser, worktree, tdd]
dependency_graph:
  requires: []
  provides: [_run_git, _parse_git_status_v2, _detect_linked_worktree]
  affects: [claude-statusline.py, tests/test_git_segment.py]
tech_stack:
  added: []
  patterns:
    - blanket-except-returns-None (RUN-01/RUN-02)
    - fixed-argv-subprocess-no-shell (T-04-01 V5 injection control)
    - porcelain-v2-pure-parser (pure function, unit-testable)
    - realpath-divergence-worktree-test (Pitfall 6 relative-path fix)
key_files:
  created:
    - tests/test_git_segment.py
  modified:
    - claude-statusline.py
decisions:
  - "_run_git uses git -C <cwd> (not cwd= kwarg) so a non-existent dir degrades through git rc!=0"
  - "_detect_linked_worktree resolves relative --git-common-dir against --show-toplevel before realpath comparison (Pitfall 6 fix)"
  - "Test shell=True check uses AST-based approach to avoid false positive from docstring mention"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-29"
  tasks: 3
  files: 2
---

# Phase 04 Plan 01: Git Helper Layer Summary

**One-liner:** Three timeout-guarded git subprocess helpers (_run_git, _parse_git_status_v2, _detect_linked_worktree) with full porcelain-v2 parsing and realpath-divergence worktree detection.

## What Was Built

Three leaf functions added to `claude-statusline.py` between the cache/weather helpers and the segment builders. These are consumed by the `_git_segment` builder in Plan 02.

### `_run_git(args, cwd, timeout=0.15) -> str | None`
Subprocess wrapper that runs `git -C cwd <args>` with a hard 150ms timeout. Returns stdout on rc=0, None on any non-zero rc or any exception (TimeoutExpired, FileNotFoundError, OSError). Uses fixed argv list — `cwd` is passed to `-C`, never shell-interpolated (`shell=True` is absent, satisfying T-04-01). `subprocess` and `os` were already imported — no new imports.

### `_parse_git_status_v2(stdout: str) -> dict | None`
Pure parser for `git status --porcelain=v2 --branch` output. Extracts: branch, detached, oid, dirty, ahead, behind. Key edge cases:
- `(detached)` → `detached=True`, `branch=None`
- `(initial)` → `oid=None` (unborn/empty repo)
- Missing `# branch.ab` → `ahead=None`, `behind=None` (NOT 0) — no upstream configured
- Any `1 `/`2 `/`u `/`? ` line → `dirty=True`

### `_detect_linked_worktree(rev_parse_stdout: str) -> tuple[bool, str | None]`
Pure detector using realpath-divergence test on `rev-parse --absolute-git-dir --git-common-dir --show-toplevel` output. Main checkout: git-dir == common-dir (after realpath). Linked worktree: git-dir != common-dir.

**Key deviation discovered and fixed during implementation:** git returns `--git-common-dir` as a RELATIVE path (`.git`) in the main checkout. Simple `os.path.realpath('.git')` resolves relative to the Python process's cwd, causing false detection. Fix: detect relative paths and resolve against `--show-toplevel` (line 2) before comparing.

### `tests/test_git_segment.py`
27 tests covering all three helpers:
- `TestRunGit` (6 tests): non-existent dir, non-repo dir, timeout, valid repo, AST-based shell=True check
- `TestParseGitStatusV2` (13 tests): all fixture combinations from RESEARCH.md
- `TestDetectLinkedWorktree` (8 tests): empty input, <3 lines, main/linked via temp dirs, integration end-to-end with real `git worktree add`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed relative --git-common-dir path in _detect_linked_worktree**
- **Found during:** Task 3 integration test failure
- **Issue:** git returns `--git-common-dir` as `.git` (relative) in the main checkout. `os.path.realpath('.git')` resolves against the test process's cwd, not the repo's toplevel, making main and common diverge incorrectly — falsely classifying the main checkout as a linked worktree.
- **Fix:** Added an `os.path.isabs()` check; if `common_raw` is relative and `toplevel` is available, join them before calling `realpath`. This is exactly the issue described as Pitfall 6 in RESEARCH.md.
- **Files modified:** `claude-statusline.py` (_detect_linked_worktree implementation)
- **Commit:** 88db4c9

**2. [Rule 1 - Bug] Fixed test_run_git_never_uses_shell false positive**
- **Found during:** Task 1 test run
- **Issue:** The original test stripped `#`-comment lines and then searched for `shell=True` in the remaining text, but docstrings are not stripped. The `_run_git` docstring contains "``shell=True`` is intentionally absent" (explaining why it's absent), triggering a false positive.
- **Fix:** Replaced the grep-style test with an AST-based check (`ast.walk` looking for `subprocess.run` calls with `shell=True` keyword arguments). This tests the actual security requirement rather than string presence.
- **Files modified:** `tests/test_git_segment.py`
- **Commit:** 88db4c9

## Verification Results

```
python3 -m pytest tests/test_git_segment.py -x
27 passed in 0.15s

python3 -m pytest tests/ --tb=short -q
2 failed, 353 passed, 52 skipped, 209 subtests passed
  (2 failures are pre-existing Phase-3 drift in test_bottom_line.py — OUT OF SCOPE)
```

Security check — no subprocess.run with shell=True:
```
python3 -m pytest tests/test_git_segment.py -k "never_uses_shell"
1 passed
```

All acceptance criteria met:
- `claude-statusline.py` contains `def _run_git(`, `def _parse_git_status_v2(`, `def _detect_linked_worktree(`
- Non-existent directory test: passes (returns None, no exception)
- Timeout test: passes (timeout=0.0001, returns None)
- No-upstream test: ahead is None, behind is None (not 0)
- Detached HEAD test: detached=True, branch=None
- Unborn repo test: oid=None without raising
- Untracked file test: dirty=True
- Integration test: real repo + worktree add → (False, ...) and (True, "wt-feature")
- <3 lines input: (False, None), no raise

## Known Stubs

None. All three functions are fully implemented.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. The only security-relevant surface (subprocess argv construction) was verified: fixed argv list, no shell=True (T-04-01 disposition: mitigate — implemented).

## Self-Check: PASSED

- `claude-statusline.py` exists and contains all three function definitions: FOUND
- `tests/test_git_segment.py` exists with 27 tests: FOUND
- Commits exist: 2d7d289 (RED), 88db4c9 (GREEN+fix)
- No regressions: 2 pre-existing failures only (same as baseline)
