---
phase: 04-git-info-including-active-worktree
verified: 2026-05-29T00:00:00Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 4: git info including active worktree — Verification Report

**Phase Goal:** A read-only git-info segment on the top line (immediately after the project name) surfaces the session repo's branch (or detached short-SHA), a single colored dirty marker, ahead/behind upstream, and — only when the session is inside a linked worktree — a worktree glyph + worktree-dir basename, all timeout-guarded so the bar never hangs and silently omitted on any non-repo/error (CONTEXT D-01..D-10).
**Verified:** 2026-05-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Step 0: Previous Verification

No previous VERIFICATION.md exists. Proceeding in initial mode.

---

## Step 1-2: Must-Haves Established

Must-haves derived from ROADMAP Phase 4 goal + CONTEXT.md locked decisions D-01..D-10 + RUN-01/RUN-02 (no mapped REQ-IDs per both plan frontmatters).

---

## Goal Achievement

### Observable Truths (D-01..D-10 + RUN-01/RUN-02)

| #   | Decision | Truth | Status | Evidence |
| --- | -------- | ----- | ------ | -------- |
| 1   | D-01     | Segment shows branch + dirty + ahead/behind; no standalone SHA field, no stash count | VERIFIED | `_git_segment` builds from `st["branch"]`, `st["dirty"]`, `st["ahead"]`/`st["behind"]`; short SHA appears only as detached-HEAD fallback |
| 2   | D-02     | Dirty state renders as a single marker (any change type → one glyph; clean → nothing) | VERIFIED | `dirty_part = f"{YELLOW}{dirty_glyph}{RESET}" if st["dirty"] else ""`; `_parse_git_status_v2` sets `dirty=True` on any `1 `/`2 `/`u `/`? ` line |
| 3   | D-03     | Worktree marker shown ONLY when inside a linked worktree; main checkout stays quiet | VERIFIED | `if is_linked and wt_name:` guard at line 1551; `test_main_checkout_no_worktree_marker` and integration test both pass |
| 4   | D-04     | Linked worktree labeled with worktree directory basename (+ glyph) | VERIFIED | `interior = f"{wt_glyph} {wt_name} {interior}"`; `wt_name` = `os.path.basename(toplevel)`; `test_linked_worktree_shows_worktree_basename` passes |
| 5   | D-05/D-06 | Git state read via subprocess with hard timeout (~150ms); segment omitted on timeout or error | VERIFIED | `_run_git` uses `subprocess.run(timeout=0.15)`; blanket `except Exception: return None`; no shell=True (AST-verified); test with `timeout=0.0001` confirms None return, no hang |
| 6   | D-07     | Run every render, no caching | VERIFIED | `_git_segment` contains zero cache calls (AST-confirmed); no read_cache/write_cache_section in function body; data flows live from subprocess every call |
| 7   | D-08     | Repo dir from `workspace.current_dir` → `cwd` fallback (NOT `project_dir`) | VERIFIED | Line 1482: `repo_dir = ws.get("current_dir") or data.get("cwd") or os.getcwd()`; `project_dir` is explicitly NOT used |
| 8   | D-09     | Git segment on top line immediately after project, before model | VERIFIED | `render_top_line` segments list: `[_project_segment(data), _git_segment(data, cfg), _model_segment(...), _weather_segment(...)]`; smoke test confirms `[project] [git] [model] [weather]` ordering; `test_d09_git_segment_between_project_and_model` passes |
| 9   | D-10     | Branch/worktree label neutral color; dirty and ahead/behind markers colored | VERIFIED | Branch: no color wrap (line 1528: `label = f"{branch_glyph}{branch_text}"`); dirty: YELLOW; ahead: GREEN; behind: YELLOW; `test_branch_label_is_neutral_no_green_red` passes |
| 10  | RUN-01/02 | Never crash or hang regardless of input | VERIFIED | Entire `_git_segment` body wrapped in `try/except Exception: return None`; `_run_git` and `_detect_linked_worktree` both have identical blanket-except wrappers; `test_never_raises_on_any_input` passes; non-repo smoke test exits 0 |

**Score: 10/10 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `claude-statusline.py` | `_run_git`, `_parse_git_status_v2`, `_detect_linked_worktree`, `_git_segment`, `display.show_git`, nerd git glyph constants | VERIFIED | All present at lines 1295, 1326, 1390, 1456, 172, 411-423 |
| `tests/test_git_segment.py` | Helper unit tests + builder monkeypatch tests + E2E subprocess tests | VERIFIED | 44+ tests in TestRunGit, TestParseGitStatusV2, TestDetectLinkedWorktree, TestGitSegmentBuilder, TestGitSegmentE2E |
| `tests/test_nerd_icons.py` | Cmap guard extended with 5 new git glyph constants | VERIFIED | `_NF_GIT_BRANCH`, `_NF_GIT_WORKTREE`, `_NF_GIT_DIRTY`, `_NF_GIT_AHEAD`, `_NF_GIT_BEHIND` in `GLYPH_CONSTANTS` at lines 1312-1316; `test_all_glyph_constants_exist_in_installed_font` passes |
| `tests/test_skeleton_render.py` | `test_d09_git_segment_between_project_and_model` + `test_fixture_top_line_exact` (show_git=false guard) | VERIFIED | Both tests present and passing; `_NO_GIT_HOME` config with `show_git = false` keeps the exact-equality guard valid |

---

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `render_top_line` | `_git_segment` | Second entry in `segments` list (line 1930) | VERIFIED | `_git_segment(data, cfg)` positioned after `_project_segment(data)` and before `_model_segment(...)` |
| `_git_segment` | `_run_git` / `_parse_git_status_v2` / `_detect_linked_worktree` | Two sequential git calls + parse + worktree detect (lines 1485-1499) | VERIFIED | status call → `_parse_git_status_v2(status_out)` → rev-parse call → `_detect_linked_worktree(rp_out or "")` |
| `_git_segment` | `DEFAULTS["display"]["show_git"]` | `cfg.get("display", {}).get("show_git", True)` (line 1477) | VERIFIED | `show_git: True` in `DEFAULTS["display"]` at line 172, next to `icon_set` and `bar_style` (NOT in the weather table) |
| `_git_segment` | `icon_set` glyph resolution | `cfg.get("display", {}).get("icon_set", "nerd")` with branch on "nerd" vs fallback (lines 1502-1514) | VERIFIED | Nerd path uses `_NF_GIT_*`; else path uses `"⑂"`, `"✚"`, `"↑"`, `"↓"` |
| `_run_git` | `subprocess.run` | Fixed argv `["git", "-C", cwd, *args]`, no `shell=True` | VERIFIED | AST check confirms zero `subprocess.run(shell=True)` calls in entire file |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `_git_segment` | `st` (parsed status dict) | `_run_git(["status","--porcelain=v2","--branch"], repo_dir)` → `_parse_git_status_v2()` | Yes — live subprocess every render (D-07 confirmed, no cache) | FLOWING |
| `_git_segment` | `is_linked, wt_name` | `_run_git(["rev-parse","--absolute-git-dir","--git-common-dir","--show-toplevel"], repo_dir)` → `_detect_linked_worktree()` | Yes — live subprocess every render | FLOWING |
| `render_top_line` | git segment string | `_git_segment(data, cfg)` return value, None-filtered by `[s for s in segments if s is not None]` | Yes — rendered on every top-line call | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Git segment appears between project and model (D-09) | Pipe repo JSON → check bracket between `[claude_statusline]` and `[Opus 4.8]` | 4 segments: `[claude_statusline]` at pos 0, git at pos 20, `[Opus...]` at pos 33 | PASS |
| Non-repo dir omits git segment, exits 0 | Pipe `/tmp/nonrepo_test` JSON | No git bracket in output; exit code 0 | PASS |
| Dirty repo shows colored marker | `test_dirty_repo_shows_yellow_dirty_marker` (monkeypatched) | YELLOW ANSI code present; `_NF_GIT_DIRTY` present | PASS |
| Detached HEAD shows 7-char oid (not literal `(detached)`) | `test_detached_head_shows_7char_oid` | `"0123456"` present; `"01234567"` absent; `"(detached)"` absent | PASS |
| No-upstream → no ahead/behind | `test_no_upstream_no_ahead_behind` | Neither `_NF_GIT_AHEAD` nor `_NF_GIT_BEHIND` present | PASS |
| shell=True absent | AST walk of all `subprocess.run` calls | Zero calls with `shell=True` keyword | PASS |

---

### Probe Execution

No `probe-*.sh` scripts declared or present for this phase. Step skipped.

---

### Requirements Coverage

No REQ-IDs mapped to Phase 4 (both plan frontmatters declare `requirements: []`; scope is fully CONTEXT-driven against D-01..D-10). All 10 locked decisions verified above.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `claude-statusline.py` | 1304 | `shell=True` string in docstring | INFO | Not code; docstring explains the intentional absence of `shell=True`. AST-verified: zero actual `shell=True` subprocess calls. No impact. |

No `TBD`, `FIXME`, or `XXX` markers found in files modified by this phase (confirmed via codebase scan).

---

### Pre-existing Failures (Out of Scope — Flagged for User)

The following 2 test failures exist in `tests/test_bottom_line.py` on the `main` branch and predate Phase 4. They are a Phase-3 gradient/shade-default regression, explicitly declared out of scope in both 04-01 and 04-02 plan files. Phase 4 introduces ZERO new failures.

- `tests/test_bottom_line.py::TestBottomLineFixture::test_bottom_line_bar_fill_cells`
- `tests/test_bottom_line.py::TestBarStylePresets::test_default_no_config_shade_unchanged`

Full suite: **374 passed, 52 skipped, 2 failed** (same 2 pre-existing failures; no regression from Phase 4 work).
Scoped suite: **150 passed, 20 skipped, 0 failed**.

These should be addressed in a follow-up to Phase 3 before Phase 5 begins.

---

### Human Verification Required

None. All phase behaviors are programmatically verifiable. The visual appearance of the git segment in a real Nerd Font terminal (glyph rendering, color appearance) was handled by the cmap guard in `tests/test_nerd_icons.py` — all 5 new git glyph codepoints (`_NF_GIT_BRANCH` U+E0A0, `_NF_GIT_WORKTREE` U+F126, `_NF_GIT_DIRTY` U+F069, `_NF_GIT_AHEAD` U+F062, `_NF_GIT_BEHIND` U+F063) are confirmed present in the installed JetBrains Nerd Font cmap.

---

## Gaps Summary

No gaps. All 10 CONTEXT decisions verified as implemented, tested, and functioning. The phase goal is fully achieved.

---

_Verified: 2026-05-29_
_Verifier: Claude (gsd-verifier)_
