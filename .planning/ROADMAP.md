# Roadmap: claude-statusline

## Overview

Two vertical slices deliver a complete working statusline. Phase 1 wires up everything available from stdin — project, model, thinking state, context bar, rate limits, colors, config — producing a fully functional bar with no network dependency. Phase 2 layers in NWS weather with caching, local sun events, and alert override, completing the feature set. Each phase produces a bar the user can install and see.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Core Statusline** - Colored two-line bar from stdin — project, model+thinking, context bar, rate limits with reset times, TOML config, graceful degradation
- [ ] **Phase 2: Weather Layer** - NWS conditions/temp/precip, cached alerts, local sunrise/sunset via astral, weather degradation

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
**Plans**: TBD

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
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Statusline | 0/TBD | Not started | - |
| 2. Weather Layer | 0/TBD | Not started | - |
