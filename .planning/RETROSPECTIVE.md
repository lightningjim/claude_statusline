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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 12 | 28 | First milestone; established per-segment omit-don't-fake architecture and decimal-phase insertion for urgent fixes |

### Cumulative Quality

| Milestone | Tests (latest run) | Coverage | Zero-Dep Additions |
|-----------|--------------------|----------|--------------------|
| v1.0 | 727 passed, 60 skipped, 0 failed | not measured | TOML (tomllib), git (subprocess), GSD state (hand-parsed) — only `requests`+`astral` added |

### Top Lessons (Verified Across Milestones)

1. *(established v1.0)* Omit-don't-fake degradation keeps a frequently-run status tool honest and crash-proof.
2. *(established v1.0)* Close milestone boundaries before starting new scope.
