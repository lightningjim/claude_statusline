# Phase 9: Clickable Links - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 9-clickable-links
**Areas discussed:** Capability gate + default, Status link target, Weather alert link target, Clickable span

---

## Capability gate + default

### Gate strategy
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect + toggle override | Sniff env for OSC 8 support; emit when supported; toggle can force-on/off | ✓ |
| Config toggle only (explicit) | No sniffing; single key on=always / off=always | |
| Toggle default + allowlist | Toggle master switch + built-in allowlist auto-enable | |

### Default
| Option | Description | Selected |
|--------|-------------|----------|
| OFF (opt-in) | Safest; no escape-noise risk; flip on after confirming terminal | ✓ |
| ON (opt-out) | Links immediately in capable terminals | |

### Toggle model (clarifier)
| Option | Description | Selected |
|--------|-------------|----------|
| Tri-state: off / auto / on (default off) | off=plain, auto=sniff, on=force; opt in via auto/on | ✓ |
| Boolean + auto when enabled (default off) | false=plain; true=auto-detect (no force-on) | |

### Sniff aggressiveness (clarifier)
| Option | Description | Selected |
|--------|-------------|----------|
| Conservative allowlist | Only known-good terminals; unknown=plain; force "on" for others | ✓ |
| Optimistic with denylist | Assume support unless known-bad signal present | |

**User's choice:** Tri-state `off`(default)/`auto`/`on` toggle; `auto` uses a conservative
allowlist of known-good terminals; default OFF (opt-in).
**Notes:** Auto-detect exists but lives behind the opt-in. Bias toward false negatives because a
false positive emits the exact LINK-03 failure (visible escape noise). JetBrains terminals'
uneven OSC 8 support reinforced the conservative posture.

---

## Status link target

| Option | Description | Selected |
|--------|-------------|----------|
| Specific incident page | status.claude.com/incidents/{id} from cached id | ✓ |
| Status homepage | status.claude.com dashboard | |
| Incident page, homepage fallback | per-incident URL, homepage when id missing | |

**User's choice:** Specific incident page.
**Notes:** By omit-not-fake (D-10), a missing/empty id renders plain text (no link) rather than
substituting the homepage — captured as D-03a.

---

## Weather alert link target

### Target (initial)
| Option | Description | Selected |
|--------|-------------|----------|
| NWS API detail URL (CAP/JSON) | api.weather.gov/alerts/{id}; literal but raw JSON | |
| alerts.weather.gov zone/event page | human-facing site | ✓ (initial) |
| Use props.web if present, else API URL | prefer human link when present | |

### URL form
| Option | Description | Selected |
|--------|-------------|----------|
| Zone page from UGC code | per-zone page from geocode.UGC | ✓ (initial) |
| I'll give the exact template | user supplies precise pattern | |
| Reconsider: use API URL after all | canonical api.weather.gov/alerts/{id} | |

### Resolution (after verification: legacy host is decommissioning)
| Option | Description | Selected |
|--------|-------------|----------|
| Zone link, verify host at plan time | lock zone link, planner confirms alerts-v2 deep-link | |
| API per-zone (guaranteed) | api.weather.gov/alerts/active?zone={UGC}; never breaks | ✓ |
| I'll confirm the URL now | user pastes exact alerts-v2 template | |

### Zone identifier
| Option | Description | Selected |
|--------|-------------|----------|
| First forecast-zone UGC (Zxxx) | prefer ??Z### from geocode.UGC; county/plain fallback | ✓ |
| User's point (lat,lon) | ?point=lat,lon from existing coords | |
| All UGC codes joined | ?zone=A&zone=B… full coverage | |

**User's choice:** `https://api.weather.gov/alerts/active?zone={UGC}` where UGC = first
forecast-zone (`??Z###`) code in `geocode.UGC`; county fallback, else plain text.
**Notes:** Web research during discussion found the legacy human per-zone page
(`alerts.weather.gov/cap/wwaatmget.php?x={UGC}&y=0`) is on the decommissioning `alerts.weather.gov`
host, and the replacement `alerts-v2.weather.gov` zone deep-link format could not be confirmed
(sites unreachable, search intermittently down). Chose the guaranteed-resolving canonical API
endpoint instead. Reported honestly rather than baking a URL that would 404.

---

## Clickable span

### Weather span
| Option | Description | Selected |
|--------|-------------|----------|
| Glyph + event + timing (not tally) | link the part describing THE alert; +2 stays plain | ✓ |
| Whole unit incl. tally | link the entire colored unit including +2 | |
| Event name text only | link just the event words | |

### Status span
| Option | Description | Selected |
|--------|-------------|----------|
| Whole status segment | glyph + label/title is the link | ✓ |
| Title/label text only | only the title text is the link | |

**User's choice:** Weather = glyph + event + timing fragment (tally outside the link); Status =
whole segment.
**Notes:** OSC 8 wraps the chosen portion; the existing Phase-8 `{color}…{RESET}` SGR wrap
composes inside the OSC 8 span (SGR is valid inside OSC 8).

---

## Claude's Discretion

- Config key name/placement for the tri-state toggle (default `"off"`, via existing config dict +
  `_deep_merge` override).
- Allowlist membership and exact env vars read in `auto` mode.
- OSC 8 emission helper shape (single pure `osc8(text, url, *, enabled)` returning plain text when
  disabled/unsupported).
- URL-component validation charsets (required for security; reject → plain text).
- Whether to read `geocode.UGC` at fetch time vs render time (raw feature already cached).

## Deferred Ideas

- Prettier human NWS page (alerts-v2 zone deep-link / per-alert page) — revisit if NWS documents a
  stable human URL; legacy host is being decommissioned.
- `properties.web` human link preference — not chosen (inconsistent presence).
- Linking other segments (model, context bar, sun, rate-limit reset) — out of scope.
- Per-alert API URL (`api.weather.gov/alerts/{id}`) — considered; zone-scoped endpoint chosen.
