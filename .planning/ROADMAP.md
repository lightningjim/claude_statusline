# Roadmap: claude-statusline

## Overview

Two vertical slices deliver a complete working statusline. Phase 1 wires up everything available from stdin — project, model, thinking state, context bar, rate limits, colors, config — producing a fully functional bar with no network dependency. Phase 2 layers in NWS weather with caching, local sun events, and alert override, completing the feature set. Each phase produces a bar the user can install and see.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Core Statusline** - Colored two-line bar from stdin — project, model+thinking, context bar, rate limits with reset times, TOML config, graceful degradation — DONE 2026-05-28
- [x] **Phase 2: Weather Layer** - NWS conditions/temp/precip, cached alerts, local sunrise/sunset via astral, weather degradation (completed 2026-05-28)
- [x] **Phase 02.1: Nerd Font icon set (INSERTED)** - Nerd Font glyphs across four segments (weather conditions/alerts, sun events, thinking, rate-limit) behind a single icon_set toggle; emoji retained as fallback (completed 2026-05-29)
- [x] **Phase 3: Presets for the type of block fill for the progress bar (including the one in place but I'm sure there's other visually interesting variations)** (completed 2026-05-29)
- [x] **Phase 03.1: Resolve default bar gradient vs shade test drift (INSERTED)** - Decide whether the default progress bar should render gradient or ▓ shade, then realign the two failing test_bottom_line.py tests with that decision (completed 2026-05-29)
- [x] **Phase 4: git info including active worktree** (completed 2026-05-29)
- [x] **Phase 5: GSD status info especially the active Plan(s) being run** (completed 2026-05-29)
- [x] **Phase 05.1: Fix TestGsdSegmentBuilder environment-leak test failures (INSERTED)** - Make the 9 failing TestGsdSegmentBuilder tests hermetic by refreshing the handoff timestamp to now at call time (mirroring _make_live_state) + add a wall-clock-independence guard test; test-only, source unchanged (completed 2026-05-30)

## Phase Details

### Phase 1: Core Statusline

**Goal**: Users can install the command and see a complete, colored two-line status bar driven entirely from stdin
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: RUN-01, RUN-02, TOP-01, TOP-02, TOP-03, CTX-01, CTX-02, LIM-01, LIM-02, LIM-03, LIM-04, FMT-01, CFG-01
**Success Criteria** (what must be TRUE):

  1. Running `echo '<json>' | claude-statusline` prints a two-line bar to stdout and exits without error
  2. Top line shows `[project] [model]` and appends the thinking glyph when `thinking.enabled` is true
  3. Second line shows a 20-wide `▓░` context bar with percentage, plus 5h and weekly usage — each colored green/yellow/red by threshold — and the reset time for any non-green indicator in `5:15pm` or `Mon 5:15pm` shorthand
  4. All settings (lat/lon, thresholds, units, feature toggles) live in a single TOML config file and the command reads it on startup
  5. Missing or malformed stdin fields produce a valid (possibly partial) bar — the command never crashes or hangs

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Walking Skeleton: executable script reads stdin, renders top line `[project] [model 💭]`, graceful degradation, install helper wires settings.json (RUN-01/02, TOP-01/02/03) — DONE 2026-05-28

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Bottom line: 20-wide context bar + %, 5h/weekly with threshold colors and non-green reset times (CTX-01/02, LIM-01/02/03/04, FMT-01) — DONE 2026-05-28

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — TOML config at ~/.claude/claude-statusline.toml via tomllib: silent defaults, per-segment toggles, thresholds, units (CFG-01) — DONE 2026-05-28

### Phase 2: Weather Layer

**Goal**: The top line gains live NWS weather that never blocks rendering
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: WX-01, WX-02, WX-03, WX-04, WX-05, WX-06
**Success Criteria** (what must be TRUE):

  1. Top line shows `<condition icon> <temp>` sourced from NWS, with `|🌧️<precip>` appended when precipitation is present
  2. Top line ends with the next sun event (🌅 sunrise or 🌇 sunset) computed locally from configured lat/lon — no network call required
  3. When an active NWS alert exists for the location, it replaces the sun-event detail in the top line
  4. Weather (~10 min) and alerts (~5 min) are written to a temp-file cache; subsequent renders read the cache and return instantly
  5. When the network is unavailable or the cache is cold, the bar still renders — weather block is omitted or shows stale data gracefully

**Plans**: 3 plans
Plans:

**Wave 1**

- [x] 02-01-PLAN.md — Packaging (subfolder + venv + self-re-exec) + extended config + sun-only weather segment with degradation (WX-03, WX-06) — DONE 2026-05-28

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — Sectioned cache + fire-and-forget detached NWS fetch + condition icon/temp/precip (WX-01, WX-02, WX-05) — DONE 2026-05-28

**Wave 3** *(blocked on Wave 2)*

- [x] 02-03-PLAN.md — Active-alert override: references-chain dedup, severity color, highest-severity +N, sun fallback (WX-04)

### Phase 02.2: Differentiate between watches, warnings, and advisories (INSERTED)

**Goal:** The top-line alert override distinguishes the three NWS hazard classes (Warning/Watch/Advisory, plus a Statement/Other bucket) as a dimension distinct from CAP severity — classifying each active alert by VTEC significance with an event-name fallback (never raising), giving each class a distinct cmap-guarded glyph and hue (Warning=red, Watch=yellow, Advisory=cyan, Statement=neutral), folding urgency+certainty into a bold/normal/dim intensity axis, selecting the primary alert class-first (Warning>Watch>Advisory) with a severity->urgency->certainty tie-break, and rendering the remainder as a per-class tally — all width-conscious, with NWS event text ANSI-sanitized and the bar never crashing (extends D2-11/WX-04; CONTEXT D-01..D-08).
**Requirements**: WX-04 (refined; phase scope tracked against CONTEXT D-01..D-08)
**Depends on:** Phase 2
**Plans:** 2/2 plans complete

Plans:

**Wave 1**

- [x] 02.2-01-PLAN.md — Classification + color + selection layer: BOLD constant, cmap-guarded `_WI_ALERT_*` class glyphs + paired class-glyph tables, `_classify_alert_class` (VTEC-significance primary + event-name fallback + Statement/Other default), `_alert_intensity` (bold/normal/dim), reshaped `_alert_color(alert)` (class hue + intensity) and `select_alert` (class-first composite, `(best, remaining_list)` contract) + unit tests (D-01,D-02,D-03,D-04,D-05,D-06,D-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02.2-02-PLAN.md — Render wiring: `_build_alert_tally` per-class remainder helper + reshaped `_weather_segment` alert-override block (class glyph via icon_set toggle, `_alert_color(best)` call site, inline ANSI-sanitized + 64-char-bounded event text, per-class tally) + updated override/E2E tests (D-04,D-08; security T-02.2-04/05/06)

### Phase 02.1: Nerd Font icon set (INSERTED)

**Goal:** Adopt Nerd Font glyphs across the statusline now that JetBrains + DejaVu Nerd Fonts are installed — starting with weather conditions/alerts (supersedes the emoji set from Phase 2) and extending to the other segment glyphs (model/thinking indicator, context, rate-limit, sun events) where a Nerd Font glyph reads better than the current emoji/ASCII.
**Requirements**: ENH-04 (pulled forward from REQUIREMENTS.md v2)
**Depends on:** Phase 2
**Plans:** 3/3 plans complete

Plans:

**Wave 1**

- [x] 02.1-01-PLAN.md — Scaffolding: `icon_set` config toggle (default nerd), semantic weather color constants + `_wx_color`, `astral.moon.phase` import, `wi-*`/PUA glyph constants + 28-slot moon table (ENH-04)

**Wave 2** *(blocked on Wave 1)*

- [x] 02.1-02-PLAN.md — Weather conditions/alerts: dual emoji/nerd condition tables, `_icon_to_glyph` render-time resolver (day/night + live moon + semantic color), cache stores raw NWS tokens; alert coloring preserved (ENH-04)

**Wave 3** *(blocked on Wave 2)*

- [x] 02.1-03-PLAN.md — Sun/thinking/rate glyph swaps under the single `icon_set` switch + propagation, then a blocking human-verify checkpoint in a real Nerd Font terminal (ENH-04)

### Phase 3: Presets for the type of block fill for the progress bar (including the one in place but I'm sure there's other visually interesting variations)

**Goal:** A config-selectable `bar_style` lets the user pick the context bar's fill look from four presets — `shade` (default, unchanged), `solid`, `solid-dim`, and `gradient` (1/8 sub-cell precision) — with filled cells in threshold color and empty cells dim gray, all degrading gracefully on unknown values.
**Requirements**: None mapped (enhancement built on ENH-04; scope driven by CONTEXT.md D-01..D-10)
**Depends on:** Phase 2
**Plans:** 2/2 plans complete

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — `bar_style` config key + whole-cell presets (shade/solid/solid-dim), per-cell filled-color/empty-gray rule, silent fallback to shade (D-01,D-06,D-07,D-08,D-09,D-10)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Gradient preset: 1/8 sub-cell boundary-block render (left blocks) + blank empty track, with 0%/100% edge cases (D-02,D-04,D-05)

### Phase 03.1: Resolve default bar gradient vs shade test drift (INSERTED)

**Goal:** Resolve the test/code drift in the Phase-3 default progress bar. Two tests fail on `main` (pre-existing, surfaced during Phase 4) because they assert the default bar contains a `▓` shade cell, while the default now renders a gradient (`█▍…`) bar. Decide the intended default (gradient vs shade), then make the default and the tests agree — either fix the default to emit a shade cell or update the tests to expect the gradient.
**Affected tests:**
- `tests/test_bottom_line.py::TestBottomLineFixture::test_bottom_line_bar_fill_cells`
- `tests/test_bottom_line.py::TestBarStylePresets::test_default_no_config_shade_unchanged`
**Requirements**: None mapped (CONTEXT-driven test-isolation fix; scope tracked against D-01..D-04).
**Depends on:** Phase 3
**Plans:** 1/1 plans complete

Plans:
- [x] 03.1-01-PLAN.md — Isolate the two default-asserting tests from the user's live config (no-config HOME → DEFAULTS shade fallback) + audit/harden sibling full-run tests; production code unchanged (D-01,D-02,D-03,D-04)

### Phase 4: git info including active worktree

**Goal:** A read-only git-info segment on the top line (immediately after the project name) surfaces the session repo's branch (or detached short-SHA), a single colored dirty marker, ahead/behind upstream, and — only when the session is inside a linked worktree — a worktree glyph + worktree-dir basename, all timeout-guarded so the bar never hangs and silently omitted on any non-repo/error (CONTEXT D-01..D-10).
**Requirements**: None mapped (CONTEXT-driven enhancement; scope tracked against D-01..D-10. RUN-01/RUN-02 honored.)
**Depends on:** Phase 3
**Plans:** 2/2 plans complete

Plans:

**Wave 1**

- [x] 04-01-PLAN.md — Git helper layer: `_run_git` (timeout-guarded, never-raises subprocess), `_parse_git_status_v2` (pure porcelain-v2 parser), `_detect_linked_worktree` (realpath divergence) + unit/integration tests (D-01,D-02,D-03,D-04,D-05,D-06,D-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — `_git_segment` builder + `display.show_git` default + nerd/emoji git glyphs (cmap-guarded) + wiring into `render_top_line` between project and model, neutral branch / colored state (D-01,D-02,D-03,D-04,D-08,D-09,D-10)

### Phase 5: GSD status info especially the active Plan(s) being run

**Goal:** A read-only GSD-status segment on the top line (immediately after the git segment) surfaces the project's GSD planning state — emphasizing the active plan being run — as a neutral plan id + task progress (e.g. `05-02 2/3`, no duplicate phase prefix) plus a single colored lifecycle glyph (executing/done→green, verifying→yellow, blocked→red, idle→dim), sourced HANDOFF-first with a ROADMAP-checkbox fallback (idle next-up + explicit milestone-complete done state), scoped to `.planning/` under `project_dir`, never blocking/crashing the bar and silently omitted off-GSD (CONTEXT D-01..D-10).
**Requirements**: None mapped (CONTEXT-driven enhancement; scope tracked against D-01..D-10. RUN-01/RUN-02 honored.)
**Depends on:** Phase 4
**Plans:** 2/2 plans complete

Plans:

**Wave 1**

- [x] 05-01-PLAN.md — GSD data-access + lifecycle-inference layer: `_read_gsd_state` (bounded never-raising HANDOFF.json + STATE.md frontmatter + ROADMAP.md reader) + `_infer_gsd_lifecycle` (pure HANDOFF-first/roadmap-fallback resolver: plan id, task progress, plan-of-total, lifecycle state, milestone) + unit tests (D-01..D-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02-PLAN.md — `_NF_GSD_*` glyph constants (cmap-guarded) + `display.show_gsd` default + `_gsd_segment` builder (neutral label / colored lifecycle glyph) wired into `render_top_line` after `_git_segment`, plus existing exact-string top-line test fixture updates + builder/E2E tests (D-08,D-09,D-10)

### Phase 05.1: Fix TestGsdSegmentBuilder environment-leak test failures (INSERTED)

**Goal:** Make the 9 failing `TestGsdSegmentBuilder` tests in `tests/test_gsd_segment.py` hermetic. The failures are not a product bug — `_gsd_segment` is correct. The shared fixtures carry a hardcoded timestamp (`2026-05-29T20:00:00.000Z`) that ages past the 1-hour staleness window (`_GSD_HANDOFF_STALE_SECONDS = 3600`); once the suite runs >1 hour later, handoffs read as stale → roadmap fallback → empty roadmap → `None` → 9 `assertIsNotNone` failures. Refresh the handoff timestamp to `now` at call time inside `_call` (mirroring `TestInferGsdLifecycle._make_live_state`), keeping the real staleness path exercised, and add a wall-clock-independence guard test. Test-only; source unchanged.
**Requirements**: None mapped (phase_req_ids null; scope tracked against CONTEXT D-01..D-03).
**Depends on:** Phase 05
**Plans:** 1/1 plans complete

Plans:

**Wave 1**

- [x] 05.1-01-PLAN.md — Refresh handoff timestamp to `now` inside `TestGsdSegmentBuilder._call.fake_read_gsd_state` (copy-before-mutate, mirrors `_make_live_state`) + add D-03 `test_builder_live_at_any_walltime` guard asserting live executing GREEN resolution; test-only, source untouched (D-01,D-02,D-03)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 02.1 → 02.2 → 3 → 4 → 5 → 05.1

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Statusline | 3/3 | DONE | 2026-05-28 |
| 2. Weather Layer | 3/3 | Complete   | 2026-05-29 |
| 02.2. Watch/Warning/Advisory differentiation | 2/2 | Complete    | 2026-06-07 |
| 02.1. Nerd Font icon set | 3/3 | Complete    | 2026-05-29 |
| 3. Presets for block fill | 2/2 | Complete   | 2026-05-29 |
| 03.1. Default bar gradient vs shade | 1/1 | Complete | 2026-05-29 |
| 4. git info incl. active worktree | 2/2 | Complete   | 2026-05-29 |
| 5. GSD status info | 2/2 | Complete   | 2026-05-29 |
| 05.1. Fix TestGsdSegmentBuilder test failures | 1/1 | Complete    | 2026-05-30 |
