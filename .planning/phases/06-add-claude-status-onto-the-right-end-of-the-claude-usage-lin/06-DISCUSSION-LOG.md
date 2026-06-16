# Phase 6: Add Claude Status onto the right end of the Claude usage line - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
**Areas discussed:** Meaning of "Claude Status", Visibility, Component scope, Detail & encoding, Maintenance, Refresh

---

## Meaning of "Claude Status" (domain definition)

| Option | Description | Selected |
|--------|-------------|----------|
| Service health | Anthropic/Claude platform status from status.claude.com (operational/degraded/outage); cached network fetch like weather/alerts | ✓ |
| Session cost | Session spend from stdin cost.* (ENH-01) | |
| Effort / fast-mode | Model operating mode from stdin effort.level + fast_mode (ENH-02) | |
| Model identity/version | model.id / version surfaced compactly | |

**User's choice:** Service health.
**Notes:** Phase line was thin (added via `/gsd:add-phase`). The phrasing "Claude Status" = the Anthropic status page. Maps onto the existing cached, never-blocking weather/alert pattern. Confirmed `status.claude.com/api/v2/summary.json` is a Statuspage.io v2 feed.

---

## Visibility (quiet vs always-on)

| Option | Description | Selected |
|--------|-------------|----------|
| Quiet when healthy | Show nothing when all-operational; appears only on degraded/incident — alert-override style | ✓ |
| Always-on dot | Always render a severity dot, green when operational | |
| Always-on, dim when healthy | Always present, dim/neutral when healthy, colored on trouble | |

**User's choice:** Quiet when healthy (D-01).
**Notes:** Consistent with the weather-alert override philosophy.

---

## Component scope (trigger set)

| Option | Description | Selected |
|--------|-------------|----------|
| Filter to what you use | Only relevant components (e.g. Claude Code + Claude API) trigger it | ✓ |
| Overall rollup | Use page-wide status.indicator; any component anywhere triggers | |
| All components, ranked | Track all, show worst/most-relevant | |

**User's choice:** Filter to what you use (D-02). Follow-up multi-select chose the exact set: **Claude Code, claude.ai, Claude Cowork**.
**Notes:** User intentionally excluded *Claude API (api.anthropic.com)* and *Console* (recommended Claude API was dropped) — sensible for a Claude Code subscription user whose traffic does not ride the developer-API component. Flagged for confirmation; left as chosen.

---

## Detail & encoding

| Option | Description | Selected |
|--------|-------------|----------|
| Glyph + short label | Severity glyph + terse label (component / phase / title) | ✓ |
| Bare colored glyph | Severity-colored glyph only, no text | |
| Glyph + count | Glyph + count of affected tracked components | |

**User's choice:** Glyph + short label (D-03).

### Label content (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Component + phase | e.g. "Claude Code: monitoring" | |
| Component name only | e.g. "Claude Code" | |
| Incident title | The incident's own title, ANSI-sanitized + width-bounded | ✓ |
| Degraded state word | "degraded" / "partial outage" / "major outage" | |

**User's choice:** Incident title.
**Notes:** Reuse the Phase 02.2 ANSI-sanitize + width-bound handling. Fallback to `component + state` when a tracked component is degraded but has no associated incident title.

---

## Maintenance & refresh (asked together)

### Maintenance

| Option | Description | Selected |
|--------|-------------|----------|
| Incidents only | Only unresolved incidents on tracked components; ignore maintenance | |
| Active maintenance too | Also surface in-progress maintenance windows | |
| Incidents + upcoming | Surface incidents AND upcoming/active scheduled maintenance | ✓ |

**User's choice:** Incidents + upcoming (D-04).
**Notes:** Maintenance shown with a distinct neutral/info glyph; reconciles with quiet-when-healthy (maintenance is "noteworthy," not silent).

### Refresh / cache TTL

| Option | Description | Selected |
|--------|-------------|----------|
| ~2 min | Short TTL — incidents move fast | |
| ~5 min | Matches existing alerts cache cadence | ✓ |
| You decide | Sensible TTL at planning time | |

**User's choice:** ~5 min (D-05). Reuse detached-refresh + temp-file cache machinery.

---

## Claude's Discretion

- Config toggle name & shape (`display.*` / `toggles.*` pattern).
- Exact severity→color mapping (incl. whether `major` gets a distinct orange) and the nerd/emoji/ascii glyphs per `icon_set`.
- Cache section/TTL key layout and detached-fetch wiring.
- Data-derivation: components/incidents/maintenances → tracked-component trigger + label; incident→component association.
- Label truncation width.
- Endpoint confirmation (status.claude.com vs legacy redirect) + User-Agent handling.

## Deferred Ideas

- Always-on "operational" confirmation dot — rejected (D-01).
- Tracking Claude API / Console / Claude for Government components — excluded (D-02); revisit on request.
- Session cost (ENH-01), effort/fast-mode (ENH-02), model identity/version — out of scope.
- Incident history / status dashboard; tinting the rate-limit line during an incident — out of scope.
