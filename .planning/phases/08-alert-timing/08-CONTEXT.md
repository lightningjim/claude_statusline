# Phase 8: Alert Timing - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Add onset/expiry timing to the existing weather-alert override in the top-line weather
segment. An alert tells the user whether it is **upcoming** (`from <start>`) or **active**
(`until <end>`), with the time rendered in 12-hour relative-day form. Covers WX-07..10.

Locked by requirements (NOT up for discussion): the label words (`from` / `until`), the
field precedence (`onset`→`effective` for start, `ends`→`expires` for end), the time format
family (`3:00 PM` / `Tmrw. at 3:00 PM` / `<Wkdy> at 3:00 PM`), and the rule that a
null/unparseable timestamp omits the time portion rather than faking or erroring.

Out of scope: clickable links (Phase 9, builds on this alert rendering), relative
countdowns ("in 2h" — explicitly excluded in REQUIREMENTS.md).
</domain>

<decisions>
## Implementation Decisions

### Time text styling
- **D-01:** The timing fragment **inherits the alert's class color and intensity** — the
  entire alert detail (class glyph + event + separator + timing) renders as a single
  class-colored unit, including the Immediate+Observed `BOLD` intensity when
  `_alert_intensity` applies. The timing is NOT dimmed gray (deliberately diverges from the
  rate-limit reset-time `DIM` convention). The existing single `{color}…{RESET}` wrap around
  the whole detail already achieves this — the timing just goes inside that wrap.

### Placement & connector
- **D-02:** The timing is set off from the event name by a **middot separator with spaces on
  both sides: ` · ` (U+00B7)**. Render order is:
  `{class_glyph} {event} · {from|until <time>}  {tally}` — i.e. timing comes after the event
  (separated by the middot), and the per-class tally (with its existing two-space prefix)
  stays the trailing element after the timing.

### Active-vs-upcoming logic
- **D-03:** Determination is by the start time vs now. Compute start = `onset` (fallback
  `effective`) and end = `ends` (fallback `expires`), in local time. If **start > now** →
  upcoming → render `from <start>`. Otherwise (including start == now, or start in the past)
  → active → render `until <end>`.
- **D-03a:** **Anomaly guard:** if start is in the future but the end is missing / unparseable
  / already in the past (a contradictory or stale record), **omit the timing fragment
  entirely** and render the event with no time — rather than showing `from` for an alert that
  can't be coherently upcoming. (Consistent with the omit-not-fake principle, D-10.)

### Timing scope & far-out edge
- **D-04:** The timing fragment appears on the **primary selected alert (`best`) only**. The
  tallied remainder stays a bare per-class count (`+2`) with no times — keeps the dense
  bottom/top line compact.
- **D-05:** Relative-day time format (WX-10) with a far-out date fallback:
  - same calendar day → `3:00 PM`
  - next calendar day → `Tmrw. at 3:00 PM`
  - 2–6 days ahead → `<Wkdy> at 3:00 PM` (e.g. `Wed at 3:00 PM`, abbreviated weekday, no period)
  - **7+ days ahead → dated form `<Mon> <D> at 3:00 PM`** (e.g. `Jul 3 at 3:00 PM`) to
    disambiguate the weekday, which repeats exactly at the +7-day boundary. The dated
    threshold is `(target_local_date - today_local_date).days >= 7`.
  - All forms are 12-hour with uppercase `AM`/`PM` and a space before it (`3:00 PM`), per WX-10.

### Claude's Discretion
- Exact `strftime` patterns (note: `fmt_reset` uses `%-I` to strip the leading zero on the
  12h hour on Linux — reuse that idiom; `%p` yields `AM`/`PM`, lowercased elsewhere but kept
  uppercase here per WX-10).
- Local-timezone conversion of the NWS ISO-8601 timestamps (display in local time, consistent
  with the sun and rate-limit-reset segments which already render local).
- When the relevant timestamps are all null/unparseable (start fields for an upcoming alert,
  or end fields for an active alert) → omit the timing portion and fall back to today's
  `{glyph} {event}  {tally}` form (success criterion 4 / D-10).
- Whether to factor the timing into a new dedicated helper (e.g. `_fmt_alert_time`) vs inline
  — a dedicated, pure, testable formatter is encouraged given the relative-day branching.
</decisions>

<specifics>
## Specific Ideas

- Worked example (active Warning, ends 3 PM today, with 2 other alerts):
  `🔴 Tornado Warning · until 3:00 PM  +2`
- Worked example (upcoming Warning, in effect from 6 PM tonight):
  `🔴 Winter Storm Warning · from 6:00 PM`
- Worked example (far-out, in effect a week+ out):
  `🟡 Winter Storm Watch · from Jul 3 at 3:00 PM`
- The new time style intentionally differs from `fmt_reset` (`5:15pm`, lowercase, no space,
  no "at") — do NOT reuse `fmt_reset` directly; build a WX-10-styled formatter.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` § "Weather Alert Timing" — WX-07 (distinguish issued-but-not-yet-active
  from active), WX-08 (`from` + onset→effective fallback), WX-09 (`until` + ends→expires fallback),
  WX-10 (12hr relative-day format). Also "Out of Scope" row: relative countdowns excluded.
- `.planning/ROADMAP.md` § "Phase 8: Alert Timing" — goal + the 4 success criteria (what must be TRUE),
  including success criterion 4 (null/missing timestamp → omit, never fake/error).

### Project conventions
- `.planning/PROJECT.md` § "Constraints" + "Key Decisions" — omit-not-fake (D-10), never block on
  network, exit fast, ANSI color conventions.

No external specs/ADRs beyond the planning docs — requirements are fully captured above and in
the decisions section.
</canonical_refs>

<code_context>
## Existing Code Insights

(All in the single file `claude-statusline.py`.)

### Reusable Assets
- **Alert selection:** `select_alert(survivors)` (~L1440) → `(best, remaining)`. `best` is a raw
  NWS feature dict; `props = best.get("properties") or best` exposes `onset`/`ends`/`effective`/
  `expires` (plus `event`).
- **Class/color/glyph helpers:** `_classify_alert_class` (~L1261), `_alert_color` (~L1477),
  `_alert_intensity` (~L1298, BOLD for Immediate+Observed), `_ALERT_CLASS_GLYPHS_NERD/EMOJI`
  (~L783/791), `_build_alert_tally(remaining, icon_set)` (~L2031).
- **ISO-8601 parsing idiom:** `datetime.fromisoformat(s.replace("Z", "+00:00"))` already used at
  ~L1355 (dedup) and ~L2879 — reuse this for onset/ends/effective/expires (then `.astimezone()`
  to local).
- **Closest time-format analog:** `fmt_reset(epoch)` (~L2537) — same-day vs weekday-prefix branching
  and `%-I:%M%p`. Pattern to mirror, but STYLE differs (D-05); do not call it directly.

### Established Patterns
- Omit-not-fake (D-10): per-segment builders return `None`/omit fragments on bad data; never clamp
  or fabricate. The whole `_weather_segment` body is wrapped in `try/except → return None`.
- Event text is sanitized (strip ESC/control chars, truncate 64) before render (~L3676); any new
  time text is machine-formatted from parsed datetimes so it needs no sanitization.

### Integration Points
- **Render site:** `_weather_segment` Step 3c, the alert-override block at ~L3653–3690. Insert the
  timing-fragment construction between event sanitization (~L3684, where `detail = f"{class_glyph}
  {safe_event}"`) and the tally append (~L3686). Build start/end from `props`, decide upcoming vs
  active (D-03), format per D-05, and splice ` · {from|until} <time>` into `detail`. The existing
  `trailing_detail = f"{color}{detail}{RESET}"` (~L3690) keeps the single class-color wrap (D-01).
- Survivors are stored as raw feature dicts by `fetch_alerts` → `write_cache_section("alerts",
  {"active": survivors})` (~L2150), so all CAP timestamp fields are present in the cache with no
  fetch-side changes needed.
</code_context>

<deferred>
## Deferred Ideas

- Timing on the tallied (non-primary) alerts — rejected for this phase (D-04): too verbose for the
  dense line. Revisit only if the layout ever gets more room.
- Relative countdowns ("in 2h") — already in REQUIREMENTS.md "Out of Scope"; absolute clock times
  chosen for unambiguous forecaster-style reading.
- OSC 8 clickable alert links — Phase 9 (depends on this phase's finalized alert rendering).
</deferred>

---

*Phase: 08-alert-timing*
*Context gathered: 2026-06-20*
