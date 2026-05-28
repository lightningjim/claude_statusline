# Phase 2: Weather Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 02-weather-layer
**Areas discussed:** Dependency strategy, Cache & refresh model, Weather format & placement, Weather degradation

---

## Dependency strategy

### Deps approach
| Option | Description | Selected |
|--------|-------------|----------|
| Zero new deps | stdlib urllib + inline NOAA solar calc; drop requests & astral; keep zero-dep delivery | |
| Keep astral, drop requests | urllib for HTTP, pip install --user astral | |
| Full deps + venv | Keep requests + astral, install.py builds a venv and points at it | ✓ |

**User's choice:** Full deps + venv (revisits Phase 1 D-12 zero-dep/system-python).

### Folder layout (user-initiated clarification)
The user redirected the venv-location question: move the script, config, and `.venv` into a dedicated subfolder `~/.claude/claude-statusline/`, with the script "calling the venv directly."

**User's choice:** Subfolder layout — supersedes flat Phase 1 paths (D-06 config, D-12 script).
**Notes:** Resolved the ambiguity of "calls the venv directly" → see next.

### Launch mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Self re-exec into venv | settings.json calls script via any python3; script os.execv's into its .venv if not already under it (exists-guarded) | ✓ |
| settings.json points at venv python | install.py wires settings.json directly to .venv/bin/python | |

**User's choice:** Self re-exec into venv.

---

## Cache & refresh model

### Refresh approach
| Option | Description | Selected |
|--------|-------------|----------|
| Fire-and-forget background fetch | Render reads cache instantly; spawns detached child to refresh when stale; lockfile prevents stampede | ✓ |
| Synchronous fetch with hard timeout | Render fetches on stale/cold with ~1–1.5s timeout, else stale/omit | |
| Separate scheduled refresh | cron/systemd --refresh keeps cache warm; render is pure cache-read | |

**User's choice:** Fire-and-forget background fetch.

### Cache file location & structure
| Option | Description | Selected |
|--------|-------------|----------|
| One JSON in subfolder, sectioned | cache.json with geo/weather/alerts timestamped sections; persists across reboots | ✓ |
| System temp dir | /tmp cache, cleared on reboot | |
| Separate files per concern | Distinct geo/weather/alerts files | |

**User's choice:** Single sectioned cache.json in the subfolder.

---

## Weather format & placement

### Top-line appearance
| Option | Description | Selected |
|--------|-------------|----------|
| Bracketed segment, pipes inside | Third bracketed segment `[<icon> <temp> | 🌧️<precip> | <detail>]` | ✓ |
| Unbracketed trailing block | Pipe-style block trailing the line, no brackets (bash-predecessor style) | |
| Separate spaced segments, no pipes | Each part its own bracketed segment | |

**User's choice:** Bracketed segment with pipe-delimited internals (harmonizes D-01 with WX spec).

### Active-alert rendering
| Option | Description | Selected |
|--------|-------------|----------|
| Glyph + full event, severity-colored | ⚠️ + full NWS event name, red Severe/Extreme, yellow Moderate/Minor, highest + "+N" | ✓ |
| Glyph + abbreviated event | Short code, severity-colored | |
| Severity glyph only | Colored dot, no text | |

**User's choice:** Glyph + full event name, severity-colored, highest-severity with +N (reuse WxDesktopPy dedup).

### Data source / endpoints
| Option | Description | Selected |
|--------|-------------|----------|
| Current observation + PoP from forecast | Icon+temp from latest observation; precip = PoP from hourly forecast | ✓ |
| All from hourly forecast | Icon/temp/PoP from forecast current period | |
| Observation with measured precip | Icon/temp/precip-amount from observation (precipitationLastHour often null) | |

**User's choice:** Current observation for icon+temp; probability-of-precipitation from hourly forecast.

---

## Weather degradation

### Failure-mode behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Layered: sun always, conditions stale-ok, omit only if absent | Sun renders locally always; stale obs shown; whole WX seg omitted on import/venv failure | ✓ |
| Same, but mark stale data | Identical + a dim staleness marker | |
| Strict silent-omit (Phase 1 parity) | Drop conditions the moment stale/unavailable | |

**User's choice:** Layered degradation, no staleness marker.

### Max-stale ceiling
| Option | Description | Selected |
|--------|-------------|----------|
| Configurable max-stale cap | Drop obs past weather_max_stale (~1h) / alerts past alerts_max_stale (~15m) → sun-only | ✓ |
| No cap | Always show last good ob regardless of age | |

**User's choice:** Configurable max-stale ceilings per data type.

---

## Claude's Discretion

- NWS `textDescription`/icon-code → emoji mapping table.
- Temperature rounding strategy.
- Lockfile mechanism and detached-spawn implementation.
- Atomic cache writes (temp-then-rename).
- Depth of WxDesktopPy reuse (thin extraction vs. framework).
- Lazy vs. install-time `geo` resolution.

## Deferred Ideas

- Alert classification fidelity (Watch/Warning/Advisory + urgency/certainty, not just severity) — user (meteorologist) flagged interest; refine in planning if it doesn't expand scope.
- Extra weather variables (dewpoint, wind, apparent temperature) — v2.
- Multi-location / auto-geolocation (ENH-03) — v2.
- Scheduled/daemon refresh — considered, rejected in favor of fire-and-forget.

---

*Mid-discussion the user clarified they are a degreed meteorologist (not just a storm-spotter) — recorded to user memory; weather fidelity choices favor correct terminology and authoritative NWS data.*
