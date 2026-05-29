# Phase 5: GSD status info especially the active Plan(s) being run - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 05-gsd-status-info-especially-the-active-plan-s-being-run
**Areas discussed:** Segment content, "Active" meaning & idle state, Visibility & color, Placement / which line

---

## Segment content — Headline

| Option | Description | Selected |
|--------|-------------|----------|
| Active plan + task progress | Lead with the plan currently running + its task burn-down, e.g. `05-02 ·2/3`. Literal "especially the active plan" reading. | ✓ |
| Phase + plan together | Lead with phase position AND active plan, e.g. `P5 ·05-02 2/3`. | |
| Milestone progress % | Lead with high-level burn-down, e.g. `5/7 ·71%`. | |

**User's choice:** Active plan + task progress
**Notes:** Segment is about what's executing right now, not an overall progress meter. → D-01.

## Segment content — Supporting fields

| Option | Description | Selected |
|--------|-------------|----------|
| Phase anchor | Short phase prefix, e.g. `P5 · 05-02 2/3`. | |
| Status verb/glyph | Indicator of what GSD is doing (executing/planning/verifying/blocked). | ✓ |
| Wave / plan-of-total | Position within phase's plan set, e.g. `plan 2/2`. | ✓ |
| Nothing else — keep it tight | Just plan id + task progress. | |

**User's choice:** Status verb/glyph + Wave/plan-of-total
**Notes:** User explicitly rejected the phase anchor — "05-02 already delineates it's phase 5 so no need to duplicate info." → D-02, D-03, D-04.

## Segment content — Status states

| Option | Description | Selected |
|--------|-------------|----------|
| Executing / blocked only | Two live states; everything else shows no verb. | |
| Plan lifecycle | planning → executing → verifying → done, + blocked. | ✓ |
| Executing / idle / blocked | Three states. | |
| You decide | Pick during planning by what files reliably signal. | |

**User's choice:** Plan lifecycle
**Notes:** → D-03.

---

## "Active" meaning & idle state — Source of truth

| Option | Description | Selected |
|--------|-------------|----------|
| HANDOFF, fall back to roadmap | Prefer HANDOFF.json live pointer; derive from ROADMAP+SUMMARY when null/stale. | ✓ |
| HANDOFF only | Trust only the live pointer; blank otherwise. | |
| Roadmap position only | Always derive from checkboxes/SUMMARY; never stale but can't tell running from next-up. | |

**User's choice:** HANDOFF, fall back to roadmap
**Notes:** HANDOFF.json currently null (partial auto-checkpoint after Phase 4). → D-05.

## "Active" meaning & idle state — Idle display

| Option | Description | Selected |
|--------|-------------|----------|
| Next-up plan, marked idle | First incomplete plan id + non-executing lifecycle glyph. | ✓ |
| Phase position only | Drop to phase granularity when nothing's running. | |
| Omit entirely when idle | Segment appears only during live execution. | |

**User's choice:** Next-up plan, marked idle
**Notes:** Stays at plan granularity; status glyph distinguishes idle from executing. → D-06.

## "Active" meaning & idle state — Milestone complete

| Option | Description | Selected |
|--------|-------------|----------|
| Show 'milestone complete' | Done/celebratory state, e.g. `v1.0 ✓` green check. | ✓ |
| Omit when nothing's left | Segment disappears. | |
| Show last completed + done glyph | Keep last plan id with a done glyph, e.g. `05-02 ✓`. | |

**User's choice:** Show 'milestone complete'
**Notes:** Confirms a clean stopping point rather than looking broken. → D-07.

---

## Visibility & color — Where to look for .planning/

| Option | Description | Selected |
|--------|-------------|----------|
| Walk up from current_dir | Start at current_dir, walk parents to find `.planning/`. | |
| project_dir only | Look under workspace.project_dir; omit if absent. | ✓ |
| current_dir only (git-style) | Mirror git's D-08. | |

**User's choice:** project_dir only
**Notes:** GSD planning is project-root-scoped; project_dir is the right anchor for this user's setup. → D-08.

## Visibility & color — Coloring

| Option | Description | Selected |
|--------|-------------|----------|
| Neutral label, colored status | Plan id/tasks neutral; only lifecycle status glyph colored. Mirrors git D-10. | ✓ |
| Whole-segment by status | Color the entire segment by state. | |
| Task progress by threshold | Color the 2/3 by completion via the threshold colorer. | |

**User's choice:** Neutral label, colored status
**Notes:** executing→green, verifying→yellow, blocked→red, done→green, idle→dim. → D-09.

---

## Placement / which line

| Option | Description | Selected |
|--------|-------------|----------|
| Top line, after git | `[project] [git] [gsd] [model] [weather]` — identity cluster. | ✓ |
| Bottom line, leading | Before the context bar on the session-truth line. | |
| Bottom line, trailing | After rate limits. | |

**User's choice:** Top line, after git
**Notes:** "What am I working on" lives with project/branch/model identity. → D-10.

---

## Claude's Discretion

- HANDOFF staleness window (live only when non-null plan + recent timestamp).
- Data-access mechanic: direct file reads (favored) vs. timeout-guarded `gsd-sdk query progress` subprocess. (`gsd-sdk query plan-status` verified invalid.)
- Specific nerd/emoji lifecycle/plan/blocked glyphs under the `icon_set` toggle.
- Status-inference rules from HANDOFF.status / artifact presence / blockers.
- `display.show_gsd`-style toggle name; separator/spacing; STATE.md YAML parse approach (hand-parse vs dep).

## Deferred Ideas

- Whole-roadmap / plan-list rendering, velocity/metrics, multi-project aggregation.
- GSD actions from the bar (advance plan, resolve blocker) — display-only.
- Threshold-% coloring of GSD progress — rejected for neutral-label + colored-status.
- Bottom-line placement — rejected for the top-line identity cluster.
