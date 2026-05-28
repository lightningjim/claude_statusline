# Requirements: claude-statusline

**Defined:** 2026-05-28
**Core Value:** At a glance, the bottom of the terminal tells the truth about the current session — context and rate-limit headroom (and when limits reset) — without slowing Claude Code down.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Runtime

- [ ] **RUN-01**: Statusline reads one JSON object from stdin, writes the status line(s) to stdout, and exits fast
- [ ] **RUN-02**: Missing or malformed stdin fields never crash the command or corrupt the bar (graceful degradation)

### Top Line

- [ ] **TOP-01**: Top line shows the running project (basename of `workspace.project_dir`)
- [ ] **TOP-02**: Top line shows the model (`model.display_name`)
- [ ] **TOP-03**: A thinking glyph (🧠) is appended to the model when `thinking.enabled` is true

### Weather

- [ ] **WX-01**: Weather shows `<condition icon> <temperature>` for the configured location, sourced from NWS
- [ ] **WX-02**: When precipitation is present, append `|🌧️<precip>` to the weather block
- [ ] **WX-03**: Weather details show the next sun event — 🌅 sunrise or 🌇 sunset, whichever comes next — computed locally from configured lat/lon
- [ ] **WX-04**: When an active NWS alert exists for the location, it replaces the sun-event detail
- [ ] **WX-05**: Weather (~10min) and alerts (~5min) are cached to a temp file; rendering reads cache and never blocks on the network
- [ ] **WX-06**: When weather/alerts are unavailable (no network, cold cache), the line still renders (omit or show stale gracefully)

### Context Usage

- [ ] **CTX-01**: Context usage renders as a 20-wide filled/empty bar (`▓░`), colored by threshold
- [ ] **CTX-02**: Context usage also shows an explicit percentage number alongside the bar

### Rate Limits

- [ ] **LIM-01**: Show 5-hour rate-limit usage percentage (`rate_limits.five_hour`), colored by threshold
- [ ] **LIM-02**: Show weekly rate-limit usage percentage (`rate_limits.seven_day`), colored by threshold
- [ ] **LIM-03**: For whichever rate-limit indicator is not green (≥70%), append its reset time
- [ ] **LIM-04**: Reset time uses shorthand — same-day → `5:15pm`; otherwise `Mon 5:15pm` (abbreviated weekday)

### Formatting & Config

- [ ] **FMT-01**: Color bands are green <70%, yellow 70–90%, red >90%, applied consistently to context, 5h, and weekly indicators
- [ ] **CFG-01**: A single TOML config file holds location (lat/lon), color thresholds, units, feature toggles, and cache TTLs

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhancements

- **ENH-01**: Show session cost (`cost.total_cost_usd`)
- **ENH-02**: Show effort level / fast-mode indicator
- **ENH-03**: Multi-location or auto-geolocation for weather

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Right-aligning weather to terminal edge | No terminal width in stdin JSON; inline layout chosen to avoid fragile padding |
| `user@host:cwd` PS1 prefix | Replaced by project name; full path was noise |
| Non-NWS weather providers (wttr.in, OpenWeatherMap) | NWS chosen for official alerts; no provider abstraction in v1 |
| Multi-user / general distribution | Personal tooling, single configured location/user |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| RUN-01 | — | Pending |
| RUN-02 | — | Pending |
| TOP-01 | — | Pending |
| TOP-02 | — | Pending |
| TOP-03 | — | Pending |
| WX-01 | — | Pending |
| WX-02 | — | Pending |
| WX-03 | — | Pending |
| WX-04 | — | Pending |
| WX-05 | — | Pending |
| WX-06 | — | Pending |
| CTX-01 | — | Pending |
| CTX-02 | — | Pending |
| LIM-01 | — | Pending |
| LIM-02 | — | Pending |
| LIM-03 | — | Pending |
| LIM-04 | — | Pending |
| FMT-01 | — | Pending |
| CFG-01 | — | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 0 (roadmap pending)
- Unmapped: 19 ⚠️

---
*Requirements defined: 2026-05-28*
*Last updated: 2026-05-28 after initial definition*
