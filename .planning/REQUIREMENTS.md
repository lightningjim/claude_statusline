# Requirements: claude-statusline

**Defined:** 2026-06-20
**Milestone:** v1.1 QOL and fixes
**Core Value:** At a glance, the bottom of the terminal tells the truth about the current session — context and rate-limit headroom (and when limits reset) — without slowing Claude Code down.

## v1.1 Requirements

Requirements for the QOL-and-fixes milestone. Each maps to a roadmap phase.

### Weather Alert Timing

Extends the v1.0 weather/alert segment (WX-01..06). Continues the WX numbering.

- [ ] **WX-07**: The alert segment distinguishes an issued-but-not-yet-active alert (onset in the future) from an active alert (in effect now), and labels each accordingly.
- [ ] **WX-08**: A not-yet-active alert shows its start as `from <time>`, using the NWS `onset` timestamp and falling back to `effective` when `onset` is null.
- [ ] **WX-09**: An active alert shows its end as `until <time>`, using the NWS `ends` timestamp and falling back to `expires` when `ends` is null.
- [ ] **WX-10**: Alert times render in 12-hour am/pm form: same-day as the bare time (`3:00 PM`), next calendar day as `Tmrw. at 3:00 PM`, and further out as `<Wkdy> at 3:00 PM` (abbreviated weekday).

### Clickable Links

- [ ] **LINK-01**: Claude Status events on the usage line render as OSC 8 hyperlinks to the relevant status.claude.com page/incident.
- [ ] **LINK-02**: Weather alerts render as OSC 8 hyperlinks to the NWS alert detail URL.
- [ ] **LINK-03**: Hyperlinks degrade to plain text where the terminal does not support OSC 8 (capability gate / config toggle), never emitting raw escape sequences as visible noise.

### Tech-Debt Cleanup

Aggregates the v1.0 milestone-audit `tech_debt` block (`.planning/milestones/v1.0-MILESTONE-AUDIT.md`).

- [ ] **DEBT-01**: `pyproject.toml` version is bumped to match `_APP_VERSION` (0.2.0) in `claude-statusline.py`.
- [ ] **DEBT-02**: SUMMARY `requirements-completed` frontmatter is backfilled for the 15/19 requirements missing it, or the field is formally retired as redundant with VERIFICATION/traceability.
- [ ] **DEBT-03**: The stale `REQUIREMENTS.md` footer is refreshed and the traceability table reconciled (this milestone's file supersedes the v1.0 artifact).
- [ ] **DEBT-04**: The astral/requests weather tests are runnable (or explicitly gated) under system `python3`, so WX-01..06 isn't only covered via the venv interpreter.
- [ ] **DEBT-05**: The WX-05 cache-TTL text/code drift is resolved — requirement text ("~15min") and the code default (10 min, `claude-statusline.py`) are aligned so they agree.

## Future Requirements

Deferred to a later milestone. Tracked but not in this roadmap.

### Enhancements (from v1.0 init deferrals)

- **ENH-01**: Show session cost on the bar.
- **ENH-02**: Show effort / fast-mode indicator.
- **ENH-03**: Multi-location / auto-geolocation weather.

### QOL (discovered through use)

- Further QOL improvements surfaced during daily use are captured via `/gsd:insert-phase` as they arise, rather than pre-enumerated here.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Right-aligning weather to the terminal edge | Claude Code's stdin JSON has no terminal width; inline layout chosen in v1.0 |
| Non-NWS weather providers | NWS chosen for official alerts; no provider abstraction planned |
| Multi-user / general distribution | Personal tooling, configured for one location/user |
| Relative countdowns for alerts (e.g. "in 2h") | Absolute clock times chosen for unambiguous reading; matches forecaster convention |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WX-07 | Phase TBD | Pending |
| WX-08 | Phase TBD | Pending |
| WX-09 | Phase TBD | Pending |
| WX-10 | Phase TBD | Pending |
| LINK-01 | Phase TBD | Pending |
| LINK-02 | Phase TBD | Pending |
| LINK-03 | Phase TBD | Pending |
| DEBT-01 | Phase TBD | Pending |
| DEBT-02 | Phase TBD | Pending |
| DEBT-03 | Phase TBD | Pending |
| DEBT-04 | Phase TBD | Pending |
| DEBT-05 | Phase TBD | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 0 (set during roadmap creation)
- Unmapped: 12 ⚠️ (resolved by roadmapper)

---
*Requirements defined: 2026-06-20*
*Last updated: 2026-06-20 after v1.1 definition*
