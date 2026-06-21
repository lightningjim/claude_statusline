# Roadmap: claude-statusline

## Milestones

- ✅ **v1.0 MVP** — 12 phases (8 integer + 4 inserted decimals) — shipped 2026-06-20
- 🚧 **v1.1 QOL and fixes** — in progress (Phases 8–10)

## Phases

<details>
<summary>✅ v1.0 MVP (12 phases) — SHIPPED 2026-06-20</summary>

- [x] Phase 1: Core Statusline (3/3 plans) — completed 2026-05-28
- [x] Phase 2: Weather Layer (3/3 plans) — completed 2026-05-29
- [x] Phase 02.1: Nerd Font icon set (INSERTED) (3/3 plans) — completed 2026-05-29
- [x] Phase 02.2: Watch/Warning/Advisory differentiation (INSERTED) (2/2 plans) — completed 2026-06-07
- [x] Phase 3: Context-bar fill presets (2/2 plans) — completed 2026-05-29
- [x] Phase 03.1: Default bar gradient vs shade test drift (INSERTED) (1/1 plan) — completed 2026-05-29
- [x] Phase 4: git info including active worktree (2/2 plans) — completed 2026-05-29
- [x] Phase 5: GSD status info (2/2 plans) — completed 2026-05-29
- [x] Phase 05.1: Fix TestGsdSegmentBuilder env-leak tests (INSERTED) (1/1 plan) — completed 2026-05-30
- [x] Phase 6: Add Claude Status to the usage line (2/2 plans) — completed 2026-06-16
- [x] Phase 7: Filter/dismiss Claude-status incidents (4/4 plans) — completed 2026-06-17
- [x] Phase 07.1: Distinguish resolved from unresolved incidents (INSERTED) (3/3 plans) — completed 2026-06-18

Full phase details archived: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### 🚧 v1.1 QOL and fixes

- [x] **Phase 8: Alert Timing** - Display alert onset and expiry times in 12hr relative-day format (completed 2026-06-20)
- [ ] **Phase 9: Clickable Links** - OSC 8 hyperlinks for status events and weather alerts with plain-text fallback (gap closure in progress — 09-04)
- [ ] **Phase 10: Tech-Debt Cleanup** - Clear the v1.0 audit's five-item tech-debt bundle

## Phase Details

### Phase 8: Alert Timing
**Goal**: Alert segments tell the user whether a weather alert is upcoming or currently active, and when it starts or ends, in plain readable time
**Depends on**: Nothing (can run first; produces alert-rendering changes Phase 9 builds on)
**Requirements**: WX-07, WX-08, WX-09, WX-10
**Success Criteria** (what must be TRUE):
  1. An alert that has not yet started shows `from <time>` using NWS `onset` (or `effective` when `onset` is null), making clear it is not yet in effect
  2. An alert that is currently active shows `until <time>` using NWS `ends` (or `expires` when `ends` is null), making clear when it ends
  3. Alert times on the same calendar day render as bare 12hr times (`3:00 PM`), the next calendar day as `Tmrw. at 3:00 PM`, and further out as `<Wkdy> at 3:00 PM`
  4. A null or missing `onset`/`ends`/`effective`/`expires` causes the time portion to be omitted rather than faked or errored
**Plans**: 2 plans
- [x] 08-01-PLAN.md — Pure _fmt_alert_time relative-day formatter + _fmt_alert_timing upcoming/active decision (TDD)
- [x] 08-02-PLAN.md — Splice timing fragment into _weather_segment Step 3c + integration render tests

### Phase 9: Clickable Links
**Goal**: Status events and weather alerts are clickable hyperlinks in terminals that support OSC 8, with no visible escape-sequence noise in terminals that do not
**Depends on**: Phase 8 (both phases touch alert rendering; clickable links wrap the alert text that Phase 8 finalizes)
**Requirements**: LINK-01, LINK-02, LINK-03
**Success Criteria** (what must be TRUE):
  1. In a supporting terminal, Claude Status incident text is a clickable link opening the relevant status.claude.com page
  2. In a supporting terminal, weather alert text is a clickable link opening the NWS alert detail URL for that alert
  3. In a terminal that does not support OSC 8 (or when the config toggle is off), the same text renders as plain text with no stray escape sequences
**Plans**: 4 plans (3 shipped + 1 gap closure)
- [x] 09-01-PLAN.md — OSC 8 foundation: osc8() helper, links tri-state config + auto-detect, allowlist URL validators (LINK-03)
- [x] 09-02-PLAN.md — Weather alert site: OSC 8-wrap glyph+event+timing to NWS zone URL, UGC extraction, tally outside span (LINK-02)
- [x] 09-03-PLAN.md — Claude Status site: OSC 8-wrap whole segment to incident page, id binding, no-homepage fallback (LINK-01)
- [ ] 09-04-PLAN.md — Gap closure: re-target weather link to human-readable showsigwx page (warnzone+warncounty from SAME, omit-not-fake) + VTE>=5000 auto gate + WR-02 doc (LINK-02)

### Phase 10: Tech-Debt Cleanup
**Goal**: All five items from the v1.0 audit tech-debt block are resolved; version metadata, planning artifacts, and test coverage are consistent and accurate
**Depends on**: Nothing (independent housekeeping; can run in parallel with or after Phases 8-9)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04, DEBT-05
**Success Criteria** (what must be TRUE):
  1. `pyproject.toml` version matches `_APP_VERSION` in `claude-statusline.py` (both read 0.2.0 or whatever the current canonical value is)
  2. SUMMARY `requirements-completed` frontmatter is either backfilled for all requirements or formally retired with a clear note, leaving no silent gaps in the audit trail
  3. The REQUIREMENTS.md traceability table and footer are current for this milestone and reconciled with what shipped
  4. The 60 astral/requests weather tests are runnable (pass or are explicitly skipped with a reason) under system `python3`, not only under the venv interpreter
  5. The WX-05 cache-TTL text and code default agree — the requirement text and `claude-statusline.py` default use the same number
**Plans**: TBD

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Core Statusline | v1.0 | 3/3 | Complete | 2026-05-28 |
| 2. Weather Layer | v1.0 | 3/3 | Complete | 2026-05-29 |
| 02.1. Nerd Font icon set | v1.0 | 3/3 | Complete | 2026-05-29 |
| 02.2. W/W/A differentiation | v1.0 | 2/2 | Complete | 2026-06-07 |
| 3. Context-bar fill presets | v1.0 | 2/2 | Complete | 2026-05-29 |
| 03.1. Default bar gradient vs shade | v1.0 | 1/1 | Complete | 2026-05-29 |
| 4. git info incl. worktree | v1.0 | 2/2 | Complete | 2026-05-29 |
| 5. GSD status info | v1.0 | 2/2 | Complete | 2026-05-29 |
| 05.1. Fix TestGsdSegmentBuilder | v1.0 | 1/1 | Complete | 2026-05-30 |
| 6. Claude Status indicator | v1.0 | 2/2 | Complete | 2026-06-16 |
| 7. Filter/dismiss incidents | v1.0 | 4/4 | Complete | 2026-06-17 |
| 07.1. Resolved vs unresolved | v1.0 | 3/3 | Complete | 2026-06-18 |
| 8. Alert Timing | v1.1 | 2/2 | Complete    | 2026-06-20 |
| 9. Clickable Links | v1.1 | 3/4 | Gap closure | - |
| 10. Tech-Debt Cleanup | v1.1 | 0/? | Not started | - |
