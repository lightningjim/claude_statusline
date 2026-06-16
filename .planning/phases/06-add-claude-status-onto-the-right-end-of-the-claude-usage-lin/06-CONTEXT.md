# Phase 6: Add Claude Status onto the right end of the Claude usage line - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a **Claude service-health indicator** to the **right end of the bottom
line** (the "Claude usage" line: context bar + 5h + weekly rate limits), placed
**after the 🗓 weekly segment**. "Claude Status" means the **Anthropic/Claude
platform health** published at `status.claude.com` — i.e. "is Claude itself
having an incident right now?" — NOT session cost, effort/fast-mode, or model
identity.

The status page is a standard **Statuspage.io v2** instance. The summary feed
(`https://status.claude.com/api/v2/summary.json`) exposes:
- `status.indicator` (`none` | `minor` | `major` | `critical`) + `status.description`
- `components[]` — each with `name` + `status` (operational / degraded_performance
  / partial_outage / major_outage / under_maintenance). Tracked components for
  this user: **Claude Code**, **claude.ai**, **Claude Cowork**.
- `incidents[]` — unresolved incidents with `name` (title), `status`
  (investigating / identified / monitoring), `impact`, and affected component refs.
- `scheduled_maintenances[]` — windows with status (scheduled / in_progress) and
  affected component refs.

Mechanically this mirrors the established **weather/alert layer**: a detached
background refresh writes a temp-file cache on a TTL; every render reads the cache
and **never blocks on the network**; the segment **omits silently** on cold cache,
no network, or parse error.

**Out of scope:** session cost (ENH-01), effort/fast-mode (ENH-02), model
identity/version display; any non-status network features; right-aligning to the
terminal edge (no terminal width available — inline placement only); a full
incident history / status dashboard; acting on incidents. Those are separate
capabilities.

</domain>

<decisions>
## Implementation Decisions

### Visibility
- **D-01:** **Quiet when healthy.** When all tracked components are operational
  and there is no relevant incident or maintenance, the segment renders **nothing**
  (returns `None`) — its mere presence signals "something is noteworthy." This
  mirrors the weather-alert override philosophy (D2-11 / WX-04): surface the
  exception, not a permanent green light. No always-on dot.

### Component scope (trigger set)
- **D-02:** **Filter to the components this user actually uses.** Only these
  trigger the indicator when degraded / under an incident / under maintenance:
  **Claude Code**, **claude.ai**, **Claude Cowork**. An outage confined to other
  components (e.g. *Claude API (api.anthropic.com)*, *Claude Console*, *Claude for
  Government*) must **not** light the bar.
  - **Note:** *Claude API* and *Console* were deliberately excluded — a Claude
    Code subscription user's traffic does not ride the developer-API component.
    Revisit only if the user asks.
  - Do **not** use the page-wide `status.indicator` rollup as the trigger (it
    fires on any component anywhere). Derive trigger state from the **tracked
    components' own statuses** + incidents/maintenances scoped to those components.

### Detail & encoding
- **D-03:** **Severity-colored glyph + short label.** When shown, render a
  severity-colored glyph plus a terse label. **Label = the incident title** from
  the relevant unresolved incident, **ANSI-sanitized and width-bounded** using the
  same handling as the weather-alert event text (Phase 02.2 / security
  T-02.2-04/05/06).
  - **Fallback:** if a tracked component is degraded but has **no associated
    incident title**, fall back to a `component + state` label (e.g.
    `Claude Code: degraded`) rather than showing a glyph with no context.
  - Severity → color follows the project band language (green/yellow/red) extended
    for status severity (none/minor/major/critical). Exact mapping (incl. an
    orange tier for `major` if desired) and the specific nerd/emoji glyphs are
    planning discretion, consistent with existing `icon_set` constants.

### Maintenance & refresh
- **D-04:** **Incidents AND scheduled maintenance.** Surface unresolved incidents
  **and** upcoming/active scheduled-maintenance windows that affect a tracked
  component. Maintenance uses a **distinct neutral/info glyph** (not the
  incident-severity colors). This reconciles with D-01: a relevant maintenance
  window is "noteworthy" so it is shown (neutral), but a fully-operational page
  with no incident and no relevant maintenance stays silent.
- **D-05:** **~5-minute cache TTL**, reusing the existing detached-refresh +
  temp-file sectioned-cache machinery (the alerts cadence). Renders read cache and
  never block; the background refresh fetches `summary.json` and writes the cache.

### Placement
- **D-06:** **Right end of the bottom line, after the 🗓 weekly segment**
  (`render_bottom_line`). Same `"   "` (3-space) inter-segment separator as the
  existing context / 5h / weekly blocks.

### Claude's Discretion
- Config toggle name & shape — follows the existing `display.*` / `toggles.*`
  pattern (e.g. a `show_claude_status` key with sensible default).
- Exact severity→color mapping (including whether `major` gets a distinct orange)
  and the specific nerd/emoji/ascii glyphs per `icon_set`.
- Whether status lives in its own cache section/TTL key or rides the existing
  cache file; the detached-fetch wiring detail.
- Exact data-derivation: mapping `summary.json` components/incidents/maintenances
  → tracked-component trigger + chosen label, including incident→component
  association via the feed's component references.
- Width budget / truncation length for the incident-title label.
- Endpoint confirmation (`status.claude.com` vs legacy `status.anthropic.com`
  redirect) and User-Agent handling for the fetch — verify at research/plan time.

</decisions>

<specifics>
## Specific Ideas

- The indicator answers one question at a glance: **"is Claude itself broken
  right now?"** — and stays out of the way otherwise (D-01).
- Mental-model parity with the weather-alert override: same "fetch on a TTL, read
  cache, never block, omit when nothing to say, sanitize untrusted text" contract.
- The trigger set is **personal and intentional** (D-02): the bar reflects *this*
  user's surfaces (Claude Code / claude.ai / Cowork), not the whole status page.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs/ADRs exist for this project — requirements are captured in the
decisions above. The relevant sources to read at research/plan time:

### Status data source
- `https://status.claude.com/api/v2/summary.json` — Statuspage.io v2 summary feed:
  `status.indicator`, `components[]`, `incidents[]`, `scheduled_maintenances[]`.
  (Statuspage.io v2 API: `status.json`, `summary.json`,
  `incidents/unresolved.json`, `scheduled-maintenances/*.json` are siblings.)

### In-repo reuse (read to confirm shapes/patterns)
- `claude-statusline.py` `render_bottom_line(data, cfg)` (≈ line 2698) — the
  insertion point; new status segment appended after `weekly_seg` (D-06).
- `claude-statusline.py` weather/alert layer (Phase 2 / 02.2) — the detached
  refresh (`run_refresh`, `--refresh` path ≈ line 2767), sectioned temp-file cache
  with TTLs (WX-05), active-alert override + ANSI-sanitized/width-bounded event
  text (the D-03 label-handling template; security T-02.2-04/05/06).
- `claude-statusline.py` `DEFAULTS` `display.*` / `toggles.*` block (≈ line 127)
  + `_deep_merge` — where the new config toggle is added.
- `color_for(...)` / GREEN/YELLOW/RED + RESET constants (≈ line 1203) and the
  `icon_set` nerd/emoji glyph-resolution pattern — reused for severity color +
  glyphs (D-03).
- NWS reuse source `/home/kcreasey/Documents/Projects/WxDesktopPy`
  `infrastructure/http/{client.py,user_agent.py}` — descriptive User-Agent + HTTP
  client pattern, if the status fetch needs the same treatment.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`render_bottom_line(data, cfg)`** (≈ 2698): assembles `[bar] pct%   ⏳ 5h%
  [reset]   🗓 wk%[reset]`; append the status segment to `parts` after `weekly_seg`
  (D-06), guarded by a `toggles`/`display` key.
- **Weather/alert refresh + cache machinery** (Phase 2): `--refresh` detached path
  (≈ 2767) + sectioned temp-file cache (WX-05) — the direct template for the
  status fetch (D-05). Status becomes another cached section.
- **Active-alert override + text sanitization** (Phase 02.2): ANSI-strip +
  width-bound of untrusted NWS event text — reuse verbatim for the incident-title
  label (D-03; honors T-02.2-04/05/06).
- **`color_for` / band constants** (≈ 1203) + `icon_set` glyph resolution — for
  severity color + nerd/emoji glyphs (D-03).
- **`DEFAULTS` `display.*`/`toggles.*` + `_deep_merge`** (≈ 127) — add the toggle.

### Established Patterns
- Per-segment builders take `(data, cfg)` explicitly and **return `None` to omit
  silently** — never fake/clamp a value (standing truth-telling rule). The status
  builder follows this for cold cache / no network / parse error (D-01 also uses
  `None` for the healthy case).
- Network work = detached refresh writes cache on a TTL; render reads cache and
  never blocks (WX-05). Status reuses this (D-05) rather than fetching inline.
- Untrusted upstream text (status feed titles) must be ANSI-sanitized + width-
  bounded before rendering (Phase 02.2 security).

### Integration Points
- `main()` (≈ 2759): `--refresh` branch runs the background fetch; the render path
  calls `render_bottom_line`. Status fetch slots into `run_refresh`; status read
  slots into `render_bottom_line`.
- New `display.show_claude_status`-style toggle in `DEFAULTS` (name = discretion).
- Tests under `tests/` — closest models are the weather-alert / override tests;
  add a status-segment test with fixtures for: operational (silent), tracked-
  component incident (glyph + title), untracked-component incident (silent),
  degraded-no-title (component+state fallback), active/upcoming maintenance
  (neutral glyph), cold-cache/no-network (silent).
- Fetch likely needs `requests` (already used by the weather layer) + a
  descriptive User-Agent (mirror the NWS client pattern if required).

</code_context>

<deferred>
## Deferred Ideas

- Always-on "operational" confirmation dot — considered and rejected (D-01:
  quiet-when-healthy).
- Tracking **Claude API** / **Console** / **Claude for Government** components —
  excluded from the trigger set (D-02); revisit only on request.
- Session cost (ENH-01), effort/fast-mode (ENH-02), model identity/version — out
  of scope; separate enhancements.
- Incident history / status dashboard, tinting the rate-limit line during an
  incident — out of scope.

</deferred>

---

*Phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin*
*Context gathered: 2026-06-16*
