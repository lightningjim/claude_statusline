# Phase 5: GSD status info especially the active Plan(s) being run - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a read-only **GSD-status segment** to the statusline that surfaces the
project's GSD planning state — with emphasis on **which plan is currently being
run**. Source data lives under the project's `.planning/` directory:
`HANDOFF.json` (the live execution pointer — phase / plan / task /
completed-tasks, written by the auto-checkpoint hook), `STATE.md` frontmatter
(milestone, status, progress, phases/plans complete), and `ROADMAP.md` (phase
position + plan checkboxes).

Display-only. Reuses the established per-segment-builder + `display.*` TOML
toggle + `icon_set` + `color_for`/neutral-label patterns from prior phases
(directly analogous to the Phase 4 git segment).

**Out of scope:** any GSD *actions* (no running plans, advancing phases,
resolving blockers from the bar); full roadmap/plan-list rendering; multi-project
aggregation; velocity/metrics dashboards; commit-history of planning docs. Those
are separate capabilities.

</domain>

<decisions>
## Implementation Decisions

### Segment content
- **D-01:** The **headline** is the active plan id + its task progress, e.g.
  `05-02 2/3` (plan currently being run + tasks-complete / total-tasks). This is
  the literal "especially the active plan being run" reading — the segment is
  about what's executing right now, not a high-level progress meter.
- **D-02:** **No separate phase anchor.** The plan id (`05-02`) already encodes
  the phase number, so a duplicate `P5`/phase-slug prefix is NOT shown — it would
  repeat information already in the id.
- **D-03:** A **lifecycle status verb/glyph** rides along, distinguishing the
  full GSD plan lifecycle: **planning → executing → verifying → done**, plus a
  **blocked** state. (The bar infers the state from `HANDOFF.json` `status`,
  presence of PLAN vs SUMMARY vs VERIFICATION artifacts, and recorded blockers.)
- **D-04:** **Wave / plan-of-total** position rides along too — how far through
  the phase's plan set you are (e.g. plan 2/2, or wave number), distinct from the
  task-within-plan progress in D-01.

### "Active plan" definition, idle, and terminal states
- **D-05:** **Source of truth = HANDOFF.json first, roadmap fallback.** When
  `HANDOFF.json` names a live plan/task, show it (true execution pointer). When
  it is null/stale, derive the current position from `ROADMAP.md` checkboxes +
  SUMMARY presence (the first incomplete plan).
- **D-06:** **Idle display = next-up plan, marked idle.** When nothing is
  actively running (HANDOFF null/stale → roadmap fallback), show the first
  incomplete plan id with a **non-executing lifecycle glyph** (planning/idle), so
  it stays at plan granularity and tells you exactly where you'll resume —
  distinct from "executing right now" via the status glyph (D-03).
- **D-07:** **Milestone-complete = explicit done state.** When every phase/plan
  is complete (no next-up plan exists), show a **"milestone complete"** state
  (e.g. `v1.0 ✓` with a green check) rather than omitting — so a clean stopping
  point is confirmed, not mistaken for a broken/off segment.

### Visibility & color
- **D-08:** **Scope `.planning/` to `workspace.project_dir`.** Look for a
  `.planning/` directory under `project_dir`; **omit the segment silently** if
  absent (non-GSD project). (Deliberately NOT the git segment's `current_dir`
  rule — GSD planning is project-root-scoped, and `project_dir` is the right
  anchor for this user's setup.)
- **D-09:** **Color the state, keep the label neutral** (mirrors git D-10). The
  plan id + task progress render neutral; only the **lifecycle status glyph**
  carries color: executing → green, verifying → yellow, **blocked → red**, done →
  green, planning/idle → dim. Not a whole-segment color wash, not threshold-%
  coloring of the task count.

### Layout
- **D-10:** **Top line, immediately after the git segment:**
  `[project] [git] [gsd] [model 💭] [weather]`. The active plan is
  "what am I working on" context, so it sits with the project/branch/model
  identity cluster rather than on the session-truth (context/rate-limit) line.

### Claude's Discretion
- **HANDOFF staleness window:** treat HANDOFF as "live" only when it names a
  non-null plan AND its timestamp is recent; pick a sensible window at planning
  time (HANDOFF carries an ISO `timestamp`; right now it is null/partial). Beyond
  the window, fall back to roadmap (D-05).
- **Data-access mechanic:** parse the `.planning/` files directly vs. shell out
  to `gsd-sdk query progress`. Lean toward **direct file reads** (fast, no
  subprocess, honors the never-block contract); if a subprocess is used it MUST
  be timeout-guarded like git (D-06 Phase 4). `gsd-sdk query progress` returns
  structured phase/plan/status JSON and `gsd-sdk query plan-status` is NOT a
  valid command (verified — errors out).
- **Glyphs follow `icon_set`** (nerd primary, emoji/ascii fallback) — same single
  global toggle every other segment uses; choose specific lifecycle/plan/blocked
  glyphs during planning consistent with the existing nerd set.
- **Status inference rules:** the precise mapping from
  HANDOFF.status/artifacts/blockers → lifecycle state (D-03) is a planning detail;
  keep it to what the files can reliably signal without fragile inference.
- **Config toggle** follows the `display.*` pattern (e.g. a `show_gsd` key
  alongside `show_git`); exact name at planning time.
- **Separator/spacing** follows the existing top-line segment style.
- **Builder returns `None` to omit silently** on any missing-file / parse-error /
  timeout — the universal segment convention (RUN-01/RUN-02).

</decisions>

<specifics>
## Specific Ideas

- The phrase "**especially the active Plan(s) being run**" is the point of the
  phase: the headline (D-01) is the live execution pointer, not a burn-down
  meter. The lifecycle glyph (D-03) is what lets a glance distinguish "executing
  05-02 right now" from "parked, 05-01 is next" (D-06) from "done" (D-07).
- Mental-model parity with the rest of the bar: this segment is "always fresh,
  never blocks, omit when not applicable" — the same contract every segment
  honors (esp. the git segment, its closest analog).
- The plan id is treated as a self-describing token (`05-02` ⇒ phase 5, plan 2),
  which is why D-02 rejects a duplicate phase prefix.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs, ADRs, or design docs exist for this project — requirements
are fully captured in the decisions above plus the GSD planning-file shapes
listed under Existing Code Insights below. The relevant in-repo data sources
(read at planning time to confirm field shapes) are:

- `.planning/HANDOFF.json` — live execution pointer fields: `phase`,
  `phase_name`, `phase_dir`, `plan`, `task`, `total_tasks`, `status`,
  `completed_tasks[]`, `remaining_tasks[]`, `blockers[]`, `timestamp`, `partial`.
- `.planning/STATE.md` — YAML frontmatter: `milestone`, `status`, `stopped_at`,
  `progress.{total_phases, completed_phases, total_plans, completed_plans,
  percent}`.
- `.planning/ROADMAP.md` — phase list with `[x]`/`[ ]` checkboxes and per-phase
  plan checkboxes (drives the roadmap-fallback position, D-05).
- `.planning/phases/<phase>/<plan>-PLAN.md` / `-SUMMARY.md` / `-VERIFICATION.md`
  — artifact presence signals lifecycle state (D-03) and plan-of-total (D-04).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `claude-statusline.py` `render_top_line(data, cfg)` (≈ line 1914) — assembles
  the top line; the GSD segment is inserted here, **right after `_git_segment`
  and before `_model_segment`** (D-10).
- `_git_segment(data, cfg)` (≈ line 1456) — the **direct structural template**:
  config-toggle gate → resolve dir → read state (timeout-guarded) → `None` on any
  miss → resolve glyphs by `icon_set` → neutral label + colored state markers.
  The GSD builder mirrors this shape.
- `_project_segment(data)` (≈ line 1442) — minimal `[...]`/`None` segment shape.
- `color_for(value, warn, crit)` / `is_green(...)` (≈ line 1203) — threshold
  colorers; reuse the GREEN/YELLOW/RED + RESET constants for the lifecycle status
  glyph coloring (D-09). `blocked → red`.
- `_run_git(args, cwd, timeout=0.15)` (≈ line 1295) — the timeout-guarded,
  never-raises subprocess wrapper; the pattern to copy IF a `gsd-sdk` subprocess
  is ever used (discretion favors plain file reads instead).
- `DEFAULTS` dict `display.*` block (≈ line 127) with `icon_set`, `bar_style`,
  `show_git` + `_deep_merge` for TOML overrides — add the GSD toggle (`show_gsd`)
  here.

### Established Patterns
- `cfg` is threaded as an explicit parameter through render functions (not a
  global) for testability — the GSD builder takes `(data, cfg)` the same way.
- Per-segment builders **return `None` to omit silently** — no placeholders
  (D-10 from prior phases). The GSD builder uses this for no-`.planning/`,
  parse error, or timeout.
- Local/fast work runs every render with a timeout guard rather than caching
  (git's D-07); planning files are small local reads — no cache needed.
- nerd/emoji glyphs resolved at the call site via `icon_set` (e.g. the
  `_NF_GIT_*` constants); add `_NF_GSD_*`-style lifecycle/plan glyph constants.

### Integration Points
- `main()` (≈ line 1999) reads stdin JSON and calls the renderers — `data`
  already carries `workspace.project_dir` (used for the `.planning/` lookup,
  D-08).
- New `display.show_gsd`-style toggle in `DEFAULTS`.
- Tests live under `tests/` (e.g. `test_git_segment.py` is the closest model);
  a `test_gsd_segment.py` would follow suit — fixtures for HANDOFF.json /
  STATE.md / a roadmap snapshot, covering executing / idle / blocked /
  milestone-complete / no-`.planning/` cases.
- New imports likely needed: none for JSON (`json` already imported); STATE.md
  frontmatter is YAML — confirm whether to parse minimally by hand or add a dep
  (planning decision; the project currently avoids non-stdlib parsing for config
  via `tomllib`).

</code_context>

<deferred>
## Deferred Ideas

- Whole-roadmap / plan-list rendering, velocity & metrics, multi-project
  aggregation — out of scope; separate phases if ever wanted.
- GSD *actions* from the bar (advance plan, resolve blocker) — explicitly out of
  scope (display-only segment).
- Threshold-% coloring of GSD progress (tying it into the context/rate-limit
  color language) — considered for placement/color and rejected in favor of
  neutral-label + colored-status (D-09).
- Bottom-line placement (with the session-truth meters) — considered and
  rejected in favor of the top-line identity cluster (D-10).

</deferred>

---

*Phase: 05-gsd-status-info-especially-the-active-plan-s-being-run*
*Context gathered: 2026-05-29*
