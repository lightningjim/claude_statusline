# Phase 9: Clickable Links - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Wrap two already-rendered pieces of status text in OSC 8 hyperlinks: Claude Status events
(usage/bottom line) and the primary weather alert (top line). In a terminal that supports
OSC 8, the text is clickable; in one that does not — or when the config toggle is off — the
exact same text renders as plain text with **zero stray escape bytes**. Covers LINK-01/02/03.

This phase changes how existing text is *wrapped*, not *what* text is rendered. The Phase-8
alert detail (`{class_glyph} {event} · {from|until <time>}  {tally}`) and the Phase-6/7
Claude-status segment are the inputs; OSC 8 nests around portions of them.

**Locked by requirements (NOT up for discussion):** OSC 8 is the mechanism; status events link
to status.claude.com, weather alerts link to an NWS detail URL; links degrade to plain text via
a capability gate / config toggle and must never emit raw escape sequences as visible noise.

Out of scope: linking any other segment (model, context bar, sun, rate-limit reset); changing
alert/status text content; a human-prettier NWS alert page (none reliably exists — see Deferred).
</domain>

<decisions>
## Implementation Decisions

### Capability gate & config toggle
- **D-01:** OSC 8 emission is governed by a **tri-state config toggle**: `off` (default) /
  `auto` / `on`.
  - `off` (default) → always plain text, never emit OSC 8 (opt-in posture; safest re: noise).
  - `on` → always emit OSC 8, regardless of terminal (user's manual override / force-on).
  - `auto` → emit OSC 8 only when env sniffing detects a known-good terminal; plain otherwise.
- **D-02:** `auto` mode uses a **conservative allowlist** of known-OSC-8-capable terminals.
  Unknown terminal → plain text (no link). Detection is env-var based (e.g. `TERM_PROGRAM`,
  `WT_SESSION` for Windows Terminal, `TERMINAL_EMULATOR`/JetBrains signal, VTE markers, kitty,
  WezTerm, iTerm2). To use links in a terminal not yet on the list, set the toggle to `on`.
  Rationale: env sniffing is heuristic; a false positive emits visible escape noise (the exact
  LINK-03 failure), so we bias toward false negatives. (Note: Kyle's JetBrains terminals have
  uneven OSC 8 support — classic vs reworked — which is precisely why `auto` is allowlist-gated
  and the default is `off`.)

### Status (Claude Status) link target
- **D-03:** A Claude Status event links to the **specific incident page**:
  `https://status.claude.com/incidents/{id}`, where `{id}` is the incident id already cached in
  `tracked_incidents` (Statuspage.io id == incident page slug).
- **D-03a:** If the incident id is missing/empty/unusable → render **plain text, no link**
  (do NOT substitute the status.claude.com homepage as a stand-in). Omit-not-fake (D-10).

### Weather alert link target
- **D-04:** A weather alert links to the **NWS API per-zone active-alerts endpoint**:
  `https://api.weather.gov/alerts/active?zone={UGC}`. (Chosen over the per-alert API URL and
  over the legacy human page on the decommissioning `alerts.weather.gov` host — see Specifics +
  Deferred. This URL is guaranteed-resolving and future-proof; it returns CAP/JSON and is
  zone-scoped, i.e. shows all active alerts for that zone, not solely the linked one.)
- **D-05:** `{UGC}` = the **first forecast-zone code** (pattern `^[A-Z]{2}Z[0-9]{3}$`, e.g.
  `OKZ034`) found in the alert's `geocode.UGC` list. Fallback chain: if no forecast-zone code
  exists (county/SAME-only alert, e.g. a polygon-based Tornado Warning carrying only `??C###`),
  fall back to the **county code**; if neither yields a usable code → **plain text, no link**.
  Omit-not-fake (D-10).

### Clickable span (what text carries the link)
- **D-06:** Weather alert clickable span = **glyph + event + timing fragment** — i.e. the
  Phase-8 `{class_glyph} {event} · {from|until <time>}` portion. The trailing per-class tally
  (`+2`, with its two-space prefix) stays **outside** the link (it refers to other alerts). The
  OSC 8 wrap goes around this portion; the existing `{color}…{RESET}` SGR wrap composes with it
  (SGR codes are valid inside an OSC 8 span — keep the single class-color wrap from Phase 8 D-01).
- **D-07:** Claude Status clickable span = the **whole rendered status segment** (glyph +
  label/title) — biggest, easiest click target.

### Claude's Discretion
- Exact config key name/placement for the tri-state toggle (suggest a single `links` /
  `osc8_links` string key in the existing config dict, default `"off"`; reuse `_deep_merge` so a
  hand-edited TOML overrides it, consistent with the Phase-07 incident-filter config pattern).
- Exact allowlist membership and which env vars to read for `auto` detection (start conservative;
  WezTerm, kitty, iTerm2, Windows Terminal, VTE/GNOME, modern JetBrains are the obvious seeds).
- OSC 8 emission idiom: a single pure helper `osc8(text, url, *, enabled) -> str` that returns
  `text` unchanged when disabled/unsupported and otherwise wraps as
  `ESC ] 8 ; ; {url} ST {text} ESC ] 8 ; ; ST` (ST = `ESC \`). Pure + testable; both call sites
  go through it so the "no stray escapes when off" guarantee lives in one place.
- URL-component sanitization/validation **is required, not optional** (see Specifics — security):
  validate `{id}` and `{UGC}` against strict charsets before embedding, strip any ESC/control
  bytes; reject → plain text.
- Whether to extract `geocode.UGC` at fetch time (store alongside survivors) or read it from the
  cached raw feature at render time (the raw feature is already cached, so render-time read needs
  no fetch change — mirrors Phase-8's note that all CAP fields are present in the cache).
</decisions>

<specifics>
## Specific Ideas

- **Worked examples (links ON, capable terminal):**
  - Weather: `🔴 Tornado Warning · until 3:00 PM` is one hyperlink →
    `https://api.weather.gov/alerts/active?zone=OKZ034`; the trailing `  +2` is plain.
  - Status: the entire `<glyph> <label>` status fragment is one hyperlink →
    `https://status.claude.com/incidents/<id>`.
- **Links OFF / unsupported terminal:** byte-for-byte identical to today's output — no `ESC]8`,
  no `ST`, nothing. This is the LINK-03 acceptance bar; test it by asserting the rendered string
  contains no `\x1b]8`.
- **Security (carry forward from this project's secure-phase work):** `{id}` and `{UGC}` originate
  from network responses (status.claude.com summary; NWS CAP). They are interpolated into an OSC 8
  URL field — an attacker-controlled value containing `ESC \` (ST) or control bytes could break out
  of the URI and inject escape sequences into the terminal. MUST validate against a strict allowlist
  charset (incident id: Statuspage hex/alnum; UGC: `^[A-Z]{2}[CZ][0-9]{3}$`) and strip/reject
  otherwise → plain text. This is the OSC 8 analog of the existing event/label sanitization.
- **NWS web reality (verified during discussion):** there is no stable, pretty per-alert human
  page. The legacy human per-zone page `https://alerts.weather.gov/cap/wwaatmget.php?x={UGC}&y=0`
  exists but lives on `alerts.weather.gov`, which NWS is **decommissioning** — deliberately NOT
  used. The current human site is `alerts-v2.weather.gov` but its zone deep-link format could not
  be confirmed at discussion time. Hence the canonical API endpoint (D-04).
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` § "Clickable Links" — LINK-01 (status events → OSC 8 to
  status.claude.com page/incident), LINK-02 (weather alerts → OSC 8 to NWS alert detail URL),
  LINK-03 (degrade to plain text via capability gate / config toggle, never emit raw escapes).
- `.planning/ROADMAP.md` § "Phase 9: Clickable Links" — goal + the 3 success criteria.

### Project conventions
- `.planning/PROJECT.md` § "Constraints" + "Key Decisions" — omit-not-fake (D-10), never block on
  network, exit fast, ANSI color conventions, terminal output has no guaranteed width.

### Builds directly on
- `.planning/phases/08-alert-timing/08-CONTEXT.md` — finalized alert rendering this phase wraps:
  the `{class_glyph} {event} · {from|until <time>}  {tally}` order (D-02) and the single
  `{color}{detail}{RESET}` class-color wrap (D-01), plus the render site (`_weather_segment`
  Step 3c, the alert-override block ~L3653–3690).

### External (mechanism + data source)
- OSC 8 hyperlink spec — de-facto reference:
  `https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda`
  (sequence form, ST vs BEL terminator, terminal support matrix, URI escaping rules).
- NWS Alerts Web Service docs — `https://www.weather.gov/documentation/services-web-alerts`
  (the `?zone={UGC}` active-alerts query parameter used by D-04).
</canonical_refs>

<code_context>
## Existing Code Insights

(All in the single file `claude-statusline.py`.)

### Reusable Assets
- **ANSI constants:** `RESET` / `BOLD` / `ESC` near L81–84 — pattern for defining escape
  constants; add OSC 8 byte constants alongside (or build them inside the `osc8()` helper).
- **Sanitization idioms:** `_sanitize` inside `_print_status_incidents` (~L532, strips ESC +
  non-printable) and the event sanitization at ~L3676 — analogs for validating URL components
  before embedding. The OSC 8 helper needs the same defensive posture for the URL field.
- **Config + override:** the config default dict (~L150) and `_deep_merge` (~L203) + the
  hand-edited-TOML override pattern noted at ~L189 (Phase-07 incident filter) — add the tri-state
  `links` key here with default `"off"`.
- **Incident id source:** `_collect_tracked_incidents` (~L2157) stores each incident's `id`
  (~L2204) in the `claude_status.tracked_incidents` cache section — the id for D-03 is already
  available; no fetch change needed.
- **Alert data source:** survivors are cached as raw NWS feature dicts (`fetch_alerts` →
  `write_cache_section("alerts", {"active": survivors})`); `props = best.get("properties") or
  best` exposes `geocode.UGC` for D-05 — present in cache, no fetch change needed.

### Established Patterns
- Omit-not-fake (D-10): per-segment builders omit fragments on bad data; `_weather_segment` is
  wrapped `try/except → return None`. The OSC 8 helper must return plain text (never a partial
  escape) on any bad/missing URL component.
- Single canonical color wrap per alert (Phase-8 D-01) — OSC 8 must nest with, not replace, it.

### Integration Points
- **Weather render site:** `_weather_segment` Step 3c alert-override block (~L3653–3690). The
  glyph+event(+timing) `detail` is assembled before the tally append (~L3686) and wrapped
  `trailing_detail = f"{color}{detail}{RESET}"` (~L3690). Wrap the glyph+event+timing portion in
  OSC 8 here (D-06) — before the tally is appended so the tally stays outside the link.
- **Status render site:** `_claude_status_segment` (~L3857) — wrap the whole returned segment in
  OSC 8 (D-07).
- **Toggle plumbing:** both call sites resolve the tri-state toggle (+ `auto` env detection) once
  and pass `enabled` into the shared `osc8()` helper.

</code_context>

<deferred>
## Deferred Ideas

- **Prettier human NWS alert page** (`alerts-v2.weather.gov` zone deep-link, or a per-alert page
  if NWS ever publishes one). Not used now: the replacement site's deep-link format was
  unconfirmable at discussion time and the legacy human page is on the decommissioning
  `alerts.weather.gov` host. Revisit if/when NWS documents a stable human zone/alert URL.
- **`properties.web` human link preference** for alerts that carry one — considered, not chosen
  (inconsistent presence; the API zone URL is uniform and guaranteed).
- **Linking other segments** (model, context bar, sun, rate-limit reset) — out of scope; LINK
  requirements cover only status events and weather alerts.
- **Per-alert API URL** (`api.weather.gov/alerts/{id}`) — considered; zone-scoped endpoint chosen
  instead so the link surfaces the alert in the context of the zone's full active set.

</deferred>

---

*Phase: 09-clickable-links*
*Context gathered: 2026-06-20*
