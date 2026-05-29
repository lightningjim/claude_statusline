# Phase 4: git info including active worktree - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a read-only **git-info segment** to the statusline that displays the
repository state for the session's working directory, with emphasis on
surfacing the **active worktree**. The segment shows branch, working-tree
dirty state, ahead/behind-upstream, and a worktree marker when the session is
inside a linked worktree.

Display-only. Reuses the established per-segment-builder + TOML-toggle +
`icon_set` + `color_for` patterns. Out of scope: any git *actions*
(commit/fetch/switch), commit-log/history rendering, multi-repo aggregation,
or stash/diff detail beyond a dirty marker — those are separate capabilities.

</domain>

<decisions>
## Implementation Decisions

### Git fields shown
- **D-01:** The segment shows three fields: **branch name**, a **dirty/clean
  indicator**, and **ahead/behind upstream**. Short SHA and stash count are
  NOT shown as standalone fields in v1.
- **D-02:** Dirty state renders as a **single marker** (one glyph when the
  working tree has uncommitted changes — modified/staged/untracked combined —
  nothing when clean). No per-type file counts.

### Active worktree representation
- **D-03:** The worktree marker is surfaced **only when the session is inside
  a linked worktree** (a `git worktree add` checkout). The main checkout shows
  just branch + state — no worktree noise in the common case.
- **D-04:** When in a linked worktree, label it with the **worktree directory
  basename** (with a worktree glyph), e.g. `⑂ feature-x` — distinct from and
  in addition to the branch name, since the worktree dir is what answers
  "which worktree am I in."

### Data source & performance
- **D-05:** Read git state by **shelling out to `git`** (subprocess) — e.g.
  `rev-parse`, `status --porcelain`, worktree introspection. This adds a
  `subprocess` import (not currently used) and is accepted because git's own
  logic is authoritative for dirty/ahead-behind/worktree edge cases.
- **D-06:** Wrap git calls in a **hard timeout** (target ~150ms). On timeout
  or any error, the segment **omits silently** (returns `None`, per existing
  D-10 builder convention). The bar must never hang on git.
- **D-07:** **Run git every render, timeout-guarded — no caching.** Branch and
  dirty state change constantly; a cache would lag reality right after a
  commit or branch switch. (Contrast with weather, which IS cached.)
- **D-08:** Resolve "the repo" from **`workspace.current_dir`**, falling back
  to `cwd` when absent. NOT `project_dir` — a linked worktree lives outside the
  project root, so `project_dir` would defeat the worktree feature.

### Layout & color
- **D-09:** Place the git segment on the **top line, immediately after the
  project name**: `[project]  [git]  [model 💭]  [weather]`. Git is
  project-identity context, so it sits next to the project name.
- **D-10:** **Color the state, keep the branch neutral.** Branch/worktree
  label in a neutral color; dirty marker and ahead/behind markers colored
  (reuse `color_for` / existing color conventions — e.g. dirty → yellow). Not
  a whole-segment green/dirty wash.

### Claude's Discretion
- **Glyphs follow `icon_set`** (nerd primary, emoji fallback) — same single
  toggle that governs every other segment; choose specific git/branch/worktree
  glyphs during planning consistent with the existing nerd set.
- **Detached HEAD:** show the short SHA in the branch slot (since no branch
  name exists) — the "branch field" gracefully degrades to a SHA.
- **Ahead/behind rendering:** exact form (`↑N↓M`, spacing, hide-when-zero,
  behavior with no upstream) is a planning detail; omit cleanly when there's
  no tracked upstream.
- **Separator / spacing** follows the existing top-line segment style.
- **Exact timeout value** (~150ms) is tunable; pick a safe default and
  consider a config knob only if it falls out naturally.
- **Config toggle** for the segment should follow the `display.*` pattern
  (e.g. a `show_git` toggle alongside `show_weather`); naming at planning time.

</decisions>

<specifics>
## Specific Ideas

- The worktree emphasis is the *point* of the phase — Kyle works across
  multiple git worktrees and wants the bar to make unmistakable which worktree
  the session is in. The "only when linked" rule (D-03) plus the dir basename
  (D-04) is precisely so a linked worktree never goes unnoticed while the
  ordinary single-checkout case stays quiet.
- Mental model parity with the rest of the bar: git is "always fresh, never
  blocks" (D-06/D-07), the same contract every segment honors.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs, ADRs, or design docs exist for this project — requirements
are fully captured in the decisions above and the project planning files. The
in-repo touchpoints that constrain this phase are listed under Existing Code
Insights below (they are source/patterns, not requirement docs).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `claude-statusline.py` `build_top_line(...)` — assembles the top line
  (`[project] [model 💭] [weather]`); the git segment is inserted here, right
  after the project name (D-09).
- Per-segment builder pattern: builders **return `None` to omit silently**
  (D-10 from prior phases) — the git builder uses this for non-repo / timeout
  / error (D-06).
- `color_for(value, warn, crit)` and `is_green(...)` — the green/yellow/red
  threshold colorers; reuse for the dirty/ahead-behind markers (D-10 this
  phase).
- `_icon_to_glyph` / nerd-glyph constants + `icon_set` resolution — the
  established nerd/emoji glyph mechanism the git glyphs plug into.
- `DEFAULTS` config dict with `display.*` toggles (`icon_set`, `bar_style`,
  `bar_width`, `show_weather`) + `_deep_merge` for TOML overrides — add the git
  toggle here.

### Established Patterns
- `cfg` is threaded as an explicit parameter through render functions (not a
  global) for testability — the git builder takes `cfg` the same way.
- Network/slow work never blocks the bar: weather uses cache + detached
  fetch; git uses a timeout guard instead (local, so no detach needed) (D-06).
- stdin carries `gitBranch`, `workspace.current_dir`, `workspace.project_dir`,
  `cwd`. `gitBranch` may be empty and gives branch only (no worktree/dirty),
  so git introspection is required for the headline feature.

### Integration Points
- **New:** `subprocess` import (none today — confirmed only `json, os, sys,
  datetime, tomllib, fcntl` are imported).
- `main()` reads stdin JSON and calls the builders — pass
  `workspace.current_dir` (fallback `cwd`) into the git builder (D-08).
- A new `display.show_git`-style toggle in `DEFAULTS` (D-12 discretion).
- Tests live under `tests/` (e.g. `test_skeleton_render.py`,
  `test_bottom_line.py`) — a `test_git_segment.py` would follow suit; git
  calls will need mocking/isolation given the subprocess + timeout behavior.

</code_context>

<deferred>
## Deferred Ideas

- Standalone short-SHA and stash-count fields — considered, left out of v1
  (D-01). Could return as enhancements.
- Per-type dirty counts (`+3 ~2`) — deferred in favor of the single marker
  (D-02).
- Git *actions* / commit-log / history / multi-repo views — out of scope;
  separate phases if ever wanted.

</deferred>

---

*Phase: 04-git-info-including-active-worktree*
*Context gathered: 2026-05-29*
