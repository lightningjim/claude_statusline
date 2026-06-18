### Phase 07.1: Distinguish resolved from unresolved Claude status incidents — keep showing important resolved-but-not-cleared incidents marked as resolved (INSERTED)

**Goal:** Make the Phase 6/7 Claude service-health segment tell the truth about a recently-resolved incident: while a resolved incident's tracked component is still degraded, render it GREEN with a check-circle glyph and a `resolved:` prefix instead of an alarming red outage (D-01/D-03/D-05); keep an unexplained degraded component red (D-05); keep active incidents and maintenance outranking it (D-04); keep a muted incident fully quiet through its resolved phase — no green and no red fallback (D-06, both the store-prune and render layers); and add a `resolved` STATE to `--status-incidents` (D-07). In-place edits to `claude-statusline.py` + tests only; never blocks the render path, never crashes, never fakes (D-10).
**Requirements**: none mapped (CONTEXT-driven refinement of Phase 6/7; scope tracked against D-01..D-07)
**Depends on:** Phase 7
**Plans:** 1/3 plans executed

Plans:

**Wave 1**

- [x] 07.1-01-PLAN.md — Resolved derivation + cache contract: GREEN `resolved` hue in `_claude_status_color`, resolved-vs-red branch in `_derive_claude_status` Rule 3 (reusing `_is_suppressed`), widen `_collect_tracked_incidents` to carry resolved incidents + fixture/tests (D-01,D-02,D-03,D-04,D-05,D-06)

**Wave 2** *(blocked on Wave 1)*

- [ ] 07.1-02-PLAN.md — Auto-prune Risk #1 fix: `fetch_claude_status` `live_ids` retains resolved-but-still-degraded tracked incident ids so a dismissed incident stays muted through resolution; truly-stale dismissals still prune (D-06)

**Wave 3** *(blocked on Wave 2)*

- [ ] 07.1-03-PLAN.md — Render + CLI: GREEN check-circle `resolved:` branch in `_claude_status_segment`, D-06 fall-through guard Risk #2 (muted degraded/resolved → None, not red/green), `resolved` STATE in `--status-incidents` + full behavior test matrix (D-03,D-04,D-05,D-06,D-07)
