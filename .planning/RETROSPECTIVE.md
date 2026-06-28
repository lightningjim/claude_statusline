# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-06-20
**Phases:** 12 (8 integer + 4 inserted decimals) | **Plans:** 28 | **Commits:** 273 | **Span:** 23 days

### What Was Built
- A two-line, color-coded Claude Code statusline driven from stdin: project, model+thinking, context bar, 5h/weekly rate limits with reset times, TOML config, graceful degradation.
- A non-blocking NWS weather layer (condition/temp/precip, local sun events, active-alert override) on a sectioned temp-file cache with a detached refresh.
- Richer surfaces layered on top: Nerd Font icon set with live moon phases, meteorologist-grade Watch/Warning/Advisory classification, context-bar fill presets, git + GSD top-line segments, and a quiet-when-healthy Claude service-health indicator with incident filter/dismiss.

### What Worked
- **Per-segment builders that return `None` to omit (D-10 "omit, don't fake").** Made graceful degradation uniform and let new segments slot into the render path via None-filtered joins without touching siblings — the integration audit found 0 orphaned / 0 missing wires across 9 segments.
- **Detached fire-and-forget cache refresh.** The render path provably never makes an inline network call; weather/alerts/status all read cache and the bar never blocks.
- **cmap-guarded glyph constants.** A fontTools test validating every glyph against the installed Nerd Font caught font/codepoint drift before it reached the terminal.
- **Decimal-phase insertions** absorbed urgent fixes (02.1, 02.2, 03.1, 05.1) without derailing the main roadmap order.

### What Was Inefficient
- **Milestone boundary drift.** v1.0 was audited at 8 phases (2026-05-29) but kept growing to 12 (Phases 6/7/07.1 shipped in June) and was never formally closed — forcing a full re-audit at close and a late cleanup of a stray Phase 8 that had been added to an already-"done" milestone.
- **Empty `requirements-completed` SUMMARY frontmatter (15/19).** Two independent sources (VERIFICATION + traceability) had to manually backstop coverage at audit time because the tracking field was left blank by most plans.
- **Environment-split test coverage.** 60 astral/requests weather tests self-skip under system `python3`; WX-01..06 is exercised only via the venv interpreter `main()` re-execs into, so there's no system-python CI signal for the weather path.

### Patterns Established
- **"Omit, don't fake" (D-10)** as a truth-telling invariant for every segment and fragment — never clamp or fabricate a value on bad/impossible data.
- **`icon_set` toggle** (nerd default / emoji fallback) with render-time glyph resolution and cmap-guarded constants.
- **Never-raise external access** — timeout-guarded subprocess (git), bounded never-raising file reads (GSD `.planning/`), atomic `O_CREAT|O_EXCL` lockfile for the cache refresh.

### Key Lessons
1. **Close milestones promptly.** Letting post-audit enhancement phases pile onto a shipped milestone blurs the boundary and forces re-auditing. Insert post-ship enhancements into the *next* milestone instead.
2. **Populate `requirements-completed` at plan time, or retire the field.** A tracking field that two other sources must backstop is worse than no field.
3. **Venv-only dependencies need an explicit test story.** Otherwise the affected suite silently self-skips and the coverage looks green when it isn't running.

### Cost Observations
- Model mix: not tracked this milestone (no per-session model accounting captured).
- Sessions: not tracked.
- Notable: GSD velocity metrics in STATE.md are partial/inconsistent (mixed units, missing rows) — a candidate to either fix or stop maintaining in v1.1.

---

## Milestone: v1.1 — QOL and fixes

**Shipped:** 2026-06-28
**Phases:** 4 (8–11) | **Plans:** 9 | **Commits:** 105 | **Span:** ~7 days (2026-06-20 → 2026-06-27)

### What Was Built
- **Alert timing** on the weather segment — upcoming (`from <onset>`) vs active (`until <ends>`) with `effective`/`expires` fallbacks, 12hr am/pm and same-day / `Tmrw. at` / `<Wkdy> at` relative-day formatting (Phase 8).
- **OSC 8 clickable links** for Claude Status incidents and weather alerts, with `VTE_VERSION>=5000` auto-gate, tri-state `links` config, allowlist URL validators, and clean plain-text fallback; the weather link re-targeted to the human-readable NWS showsigwx page via FIPS-derived warnzone/warncounty (Phase 9).
- **v1.0 tech-debt bundle cleared** — version sync, WX-05 TTL text↔code alignment, REQUIREMENTS reconciliation, `requirements-completed` retired-with-note, and system-`python3` weather-test runnability (Phase 10).
- **Version-display fragment** — dimmed trailing Claude+GSD version fragment from stdin `version` and the `installed_plugins.json` ledger, with an injection-rejecting sanitizer, NF/text glyphs, and omit-not-fake everywhere (Phase 11).

### What Worked
- **The v1.0 "close milestones promptly" lesson held.** v1.1 was scoped to 4 phases, audited, and closed without boundary drift — the exact failure mode from v1.0 did not recur.
- **A dedicated tech-debt phase (Phase 10) cleared the prior milestone's audit debt** instead of letting it carry forward indefinitely, including resolving the v1.0 "venv-only test coverage" inefficiency (DEBT-04 → system-python weather tests now run).
- **D-10 "omit, don't fake" extended cleanly to two new surfaces** (alert-timing fragments and the version fragment) — the established per-fragment None-to-omit pattern absorbed both without special-casing.
- **The human-verify checkpoint (Phase 11-02) was honored as a real gate** — Kyle visually approved the NF glyph rendering rather than it being auto-passed.

### What Was Inefficient
- **The Phase 9 weather link shipped wrong the first time and needed a gap-closure plan (09-04).** The initial link target (raw alert URL) wasn't what a human wants; GAP-09-A/B re-targeted it to showsigwx and added the FIPS county derivation. Earlier validation against "what does clicking actually open" would have caught it in 09-02.
- **Phase 9 UAT left 3 items skipped** (LINK-01/02 click-through and the JediTerm advisory) because no live weather alert was available to click during testing — residual risk documented but not directly exercised.
- **`milestone.complete` auto-extracted garbage accomplishments again** (bug-list fragments instead of deliverables) — the MILESTONES.md and retrospective blocks had to be hand-written, same as v1.0.

### Patterns Established
- **Dedicated tech-debt phase per milestone** to drain the previous milestone's audit `tech_debt` block, rather than ad-hoc carry-forward.
- **Gap-closure plan appended to a phase** (NN-04 after NN-01..03) as the unit for fixing a UAT-surfaced defect without reopening the whole phase.
- **Capability auto-gating via environment probes** (`VTE_VERSION>=5000`) for terminal features, defaulting conservative to avoid escape-sequence noise.

### Key Lessons
1. **Validate links/outputs against the real destination, not just the format.** A well-formed URL that opens the wrong page (raw JSON vs human page) passes format tests but fails the user; check "what does this actually open/show" during the plan, not at UAT.
2. **UAT items that need live external conditions (an active alert) should have a synthetic/fixture path** so they're not perpetually skipped.
3. **Don't trust `milestone.complete`'s auto-accomplishments** — always hand-write the MILESTONES + retrospective deliverable list from the SUMMARY/PROJECT content.

### Cost Observations
- Model mix: balanced profile (planner=opus, executor=sonnet); per-session model accounting still not captured.
- Sessions: not tracked.
- Notable: 105 commits across 9 plans (~12/plan) — consistent with the doc-heavy GSD commit cadence (feat + docs per task).

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 12 | 28 | First milestone; established per-segment omit-don't-fake architecture and decimal-phase insertion for urgent fixes |
| v1.1 | 4 | 9 | Clean milestone boundary (v1.0 lesson applied); dedicated tech-debt phase; gap-closure plan as the defect-fix unit |

### Cumulative Quality

| Milestone | Tests (latest run) | Coverage | Zero-Dep Additions |
|-----------|--------------------|----------|--------------------|
| v1.0 | 727 passed, 60 skipped, 0 failed | not measured | TOML (tomllib), git (subprocess), GSD state (hand-parsed) — only `requests`+`astral` added |
| v1.1 | 885 passed, 68 skipped, 0 failed (+296 subtests) | not measured | OSC 8 (raw escapes), FIPS-state table, version-ledger reader — all stdlib, no new deps |

### Top Lessons (Verified Across Milestones)

1. *(established v1.0, **confirmed v1.1**)* Omit-don't-fake degradation keeps a frequently-run status tool honest and crash-proof.
2. *(established v1.0, **applied v1.1**)* Close milestone boundaries before starting new scope — v1.1 shipped clean at 4 phases.
3. *(established v1.1)* Validate outputs against the real destination/effect, not just the format — a well-formed link can still open the wrong page.
