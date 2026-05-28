# Phase 2: Weather Layer - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add live NWS weather to the **top line**: a condition icon + temperature, an optional precipitation chunk, and a trailing detail that is normally the next sun event (🌅/🌇) but is replaced by an active NWS alert when one exists. A temp-file cache (weather ~10 min, alerts ~5 min) ensures every render reads cached data and **never blocks on the network**; the bar still renders when offline or on a cold cache.

Covers requirements **WX-01 … WX-06**.

**Out of this phase:** the bottom line and everything from Phase 1 (unchanged); block-fill presets (Phase 3); git info (Phase 4); GSD status (Phase 5); and v2 enhancements ENH-01/02/03. Apparent-temperature / dewpoint / wind extras are **not** in scope (candidate v2).

</domain>

<decisions>
## Implementation Decisions

### Dependencies, packaging & invocation (supersedes Phase 1 D-06, D-12)
- **D2-01:** Phase 2 adds real third-party deps (`requests` for NWS HTTP, `astral` for sun times) installed into a dedicated **virtual environment** — revisiting Phase 1's zero-dep, system-`python3` delivery (D-12).
- **D2-02:** The install is restructured into a **self-contained subfolder** `~/.claude/claude-statusline/` containing the script, the TOML config, and the `.venv`. This **supersedes** the flat Phase 1 paths:
  - Config moves: `~/.claude/claude-statusline.toml` → `~/.claude/claude-statusline/claude-statusline.toml` (default config path in `load_config` updates accordingly).
  - Script moves: `~/.claude/claude-statusline.py` → `~/.claude/claude-statusline/claude-statusline.py`.
- **D2-03:** **Self re-exec** launch model. `settings.json` invokes the script with any `python3`. At startup the script checks whether it is already running under its own venv interpreter; if not (and `.venv/bin/python` exists), it `os.execv`'s into `~/.claude/claude-statusline/.venv/bin/python` and re-runs itself. The script guarantees its own interpreter — `settings.json` needs no venv path.
  - `settings.json` command: `python3 ~/.claude/claude-statusline/claude-statusline.py`
  - Guard with an `exists()` check so a missing venv can never hard-fail the bar (see D2-12).
- **D2-04:** `install.py` is updated to: create the subfolder, build the `.venv`, `pip install requests astral` into it, copy the script + config, and wire the `statusLine` command in `settings.json`. `pyproject.toml` declares `requests` and `astral` as dependencies.

### Caching & refresh
- **D2-05:** **Fire-and-forget background refresh.** Every render reads the cache and returns **instantly** — it never fetches inline. When a cache section is past its TTL, the render spawns a **detached child process** (under the venv) that performs the NWS fetch and rewrites the cache, then the render returns immediately using whatever data is currently cached. A **lockfile** prevents multiple concurrent fetches (the statusline runs frequently). The refreshed data appears on a subsequent render.
- **D2-06:** **Single sectioned cache file** `~/.claude/claude-statusline/cache.json` with three independently-timestamped sections:
  - `geo` — lat/lon → NWS gridpoint + observation station; effectively permanent (re-resolve only if missing or lat/lon changes).
  - `weather` — condition icon, temperature, precip; TTL `weather_ttl`.
  - `alerts` — active alerts list; TTL `alerts_ttl`.
  - Persists across reboots (fewer cold fetches) and keeps the long-lived `geo` lookup out of the per-refresh request path.
- **D2-07:** TTLs are **config-driven** from the `[cache]` table already reserved in Phase 1 (`weather_ttl` default 600s, `alerts_ttl` default 300s). Add **max-stale ceilings** (see D2-11).

### Weather data source & values
- **D2-08:** **Condition icon + temperature** come from the **latest NWS station observation** (`stations/{id}/observations/latest`) — the actual current conditions. **Precipitation** is rendered as **probability-of-precipitation** (`🌧️<pop>%`) pulled from the **hourly forecast** (`gridpoints/.../forecast/hourly`, current period) — forward-looking and reliably populated. Two endpoints, both cached under `weather`.
- **D2-09:** Temperature unit is **config-driven** (`units.temp_unit`, default `°F`); NWS reports SI/°C, so convert. Precip chunk is **omitted** when PoP is absent/zero (WX-02).

### Top-line format & alert override
- **D2-10:** Weather is a **third bracketed top-line segment**, consistent with Phase 1's bracketed segments (D-01), with **pipe-delimited internals** from the WX spec:
  ```
  [<project>] [<model> 💭] [<icon> <temp> | 🌧️<pop>% | <sun-or-alert>]
  ```
  Implemented as a new `_weather_segment()` that returns `None` to omit (per D-10 pattern), joined by `render_top_line`'s existing space-join.
- **D2-11:** **Active-alert override** (WX-04): when an alert is active, the trailing detail becomes `⚠️ <full NWS event name>`, **severity-colored** — red for Extreme/Severe, yellow for Moderate/Minor. With multiple active alerts, show the **highest-severity** one with a `+N` suffix for the rest. Reuse WxDesktopPy's alert **dedup** logic. (See deferred note on Watch/Warning/Advisory + urgency/certainty fidelity.)

### Graceful degradation
- **D2-12:** **Layered degradation** (extends D-10 silent-omit, applied per data type):
  - **Sun event always renders** — computed locally from lat/lon, no network. Even a cold/empty weather cache still shows `[… | 🌅 6:14am]`.
  - **Conditions/alerts render stale-OK** — show the last good cached value even past its refresh TTL (a slightly-aged ob beats nothing); omit only when no data has ever been fetched.
  - **Max-stale ceiling** — drop conditions once older than `weather_max_stale` (default ~1h) and alerts older than `alerts_max_stale` (default ~15m), falling back to sun-only rather than displaying misleadingly old data. (Stale data shown **without** a staleness marker — clean look — but capped by these ceilings.)
  - **Import/venv failure** — if `requests`/`astral`/the venv are unavailable, the **entire weather segment is omitted** and the Phase 1 bar (project, model, bottom line) renders completely untouched. Weather can never break the bar.

### Claude's Discretion
- NWS `textDescription`/`icon`-code → emoji mapping table.
- Temperature rounding strategy (consistent with Phase 1's floor convention unless rounding reads better for temps).
- Exact lockfile mechanism and detached-spawn approach (e.g. `subprocess.Popen` with detached stdio, or double-fork) — must guarantee the parent render returns immediately.
- Atomic cache writes (write-temp-then-rename) so a render never reads a half-written cache.
- How much of WxDesktopPy to reuse verbatim vs. reimplement minimally — it is a heavy clean-architecture app (HTTP decorators, domain models); the statusline wants a thin extraction (User-Agent factory, NWS endpoint flow, alert dedup), not the framework.
- Whether the background fetch resolves `geo` lazily on first run vs. at install time.

</decisions>

<specifics>
## Specific Ideas

- Target rendering (fresh, no alert):
  ```
  [claude_statusline] [Opus 4.8 (1M context) 💭] [☀️ 72°F | 🌧️40% | 🌅 6:14am]
  ```
- Active alert (Severe — red event text):
  ```
  [claude_statusline] [Opus 4.8 (1M context) 💭] [☀️ 72°F | ⚠️ Tornado Warning +2]
  ```
- Cold cache (sun-only until first background fetch lands):
  ```
  [claude_statusline] [Opus 4.8 (1M context) 💭] [🌇 8:02pm]
  ```
- **User is a degreed meteorologist** — favor correct terminology and high NWS data fidelity (real event names, severity, observation-vs-forecast distinction, PoP). Don't dumb down the weather signal.
- Carry forward the bash predecessor's sun-event feel (🌅 before sunrise, 🌇 before sunset) — now via `astral`, location from config.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & decisions
- `.planning/REQUIREMENTS.md` — WX-01…WX-06 (Phase 2 requirement set), `[cache]` TTL intent, out-of-scope provider note.
- `.planning/ROADMAP.md` §"Phase 2: Weather Layer" — goal and 5 success criteria.
- `.planning/PROJECT.md` — Core value, Key Decisions table, NWS provider constraint, performance/caching rationale, WxDesktopPy reuse note.
- `.planning/phases/01-core-statusline/01-CONTEXT.md` — Phase 1 decisions this phase **supersedes/extends** (D-01 bracketed segments kept; D-06 config path & D-12 zero-dep/system-python delivery superseded by D2-02/D2-03; D-09 reserved `[location]`/`[cache]` keys now consumed; D-10 silent-omit extended).

### Current implementation (to extend)
- `claude-statusline.py` — segment-builder architecture; add `_weather_segment()` + cache/fetch/sun modules; update `load_config` default path (D2-02) and `DEFAULTS` (`[location]`, `[cache]` incl. new `*_max_stale`).
- `install.py` — rewrite for subfolder + venv + pip install + settings.json wiring (D2-04).
- `pyproject.toml` — add `requests`, `astral` to `dependencies`.
- `.examples/statusline-command.sh` — predecessor sun-event block (🌅/🌇 selection logic) and `|`-delimited weather composition.
- `.examples/claude_stdin.json` — primary test fixture (no weather fields; weather is external).

### NWS reuse source — `/home/kcreasey/Documents/Projects/WxDesktopPy`
- `src/wx_desktop_py/infrastructure/http/user_agent.py` — NWS-compliant `User-Agent` factory (required; 403 without it). **MUST read** — encodes the ToS requirement.
- `src/wx_desktop_py/infrastructure/http/client.py` — NWS HTTP client patterns (headers, error handling). Extract minimally; the statusline does not need the full decorator stack (retry/breaker/cache/rate_limit).
- `src/wx_desktop_py/infrastructure/sources/nws/` — endpoint flow: `stations_list.py`, `current_observation.py`, `hourly_forecast.py`, `parsers.py`, `active_alerts.py`.
- `src/wx_desktop_py/application/fetch_active_alerts.py` + `application/alerts/dedup.py` — active-alert fetch and **dedup** (reused for D2-11 highest-severity selection).
- Its `.planning/research/STACK.md` (if present) and any `PITFALLS.md` — NWS specifics (User-Agent ToS, points→grid→station flow).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Segment-builder pattern** (`claude-statusline.py`): each `_*_segment(data, ...)` returns a string or `None`; `render_top_line` space-joins present segments. Weather drops in as `_weather_segment()` with zero changes to the join logic.
- **Config loader** (`load_config`/`_deep_merge`/`DEFAULTS`): already tolerates extra keys and silent failure; extend `DEFAULTS` with `[location] lat/lon`, `[cache] weather_ttl/alerts_ttl/weather_max_stale/alerts_max_stale`, `[units] temp_unit`. Update the default path to the subfolder.
- **Color constants** (GREEN/YELLOW/RED/DIM/RESET) and the never-crash discipline (bare-`except` → omit) reused for alert severity coloring and weather degradation.
- **WxDesktopPy**: thin extraction targets — User-Agent factory, NWS points→grid→station→observation/forecast flow, alert dedup. Do **not** import its framework wholesale.

### Established Patterns
- Runtime contract: read stdin → write line(s) → exit fast; **never** hang or emit a traceback that breaks Claude Code's bar (RUN-01/02). The fire-and-forget refresh + import guards exist to preserve this under network/dep failure.
- Per-segment **silent omit** (D-10) — extended per-data-type in D2-12.
- ANSI color, no terminal width, inline layout (no right-alignment).

### Integration Points
- Output consumed by Claude Code's `statusLine` (`settings.json`); stdout only.
- New install root `~/.claude/claude-statusline/` (script + `claude-statusline.toml` + `.venv` + `cache.json` + lockfile), wired by `install.py`.
- NWS `api.weather.gov` is the only network dependency; reached only by the **detached background fetch**, never the render path.

</code_context>

<deferred>
## Deferred Ideas

- **Alert classification fidelity** (raised, deferred to planning/research as Claude's discretion within D2-11): distinguishing Watch vs Warning vs Advisory and incorporating NWS `urgency`/`certainty` (not just `severity`) into coloring/priority. Captured because the user (a meteorologist) flagged interest; refine during planning if it doesn't expand scope.
- **Extra weather variables** — dewpoint, wind, apparent temperature (heat index / wind chill): **v2** candidate, out of WX-01…06 scope.
- **ENH-03** (REQUIREMENTS v2) — multi-location / auto-geolocation. Phase 2 is single configured lat/lon.
- **Scheduled/daemon refresh** (cron/systemd `--refresh` mode) — considered and rejected for Phase 2 in favor of fire-and-forget (D2-05); revisit only if background spawn proves insufficient.

</deferred>

---

*Phase: 02-weather-layer*
*Context gathered: 2026-05-28*
