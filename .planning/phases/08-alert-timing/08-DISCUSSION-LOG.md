# Phase 8: Alert Timing — Discussion Log

> **Audit trail only.** Not consumed by downstream agents (researcher, planner, executor).
> Decisions live in `08-CONTEXT.md`; this log preserves how they were reached.

**Date:** 2026-06-20
**Phase:** 08-alert-timing
**Mode:** discuss (interactive), `--chain`
**Areas discussed:** Time text styling, Placement & connector, Active-vs-upcoming logic, Timing scope & far-out edge

## Pre-discussion analysis

WX-07..10 lock most of the "what" — label words (`from`/`until`), field precedence
(onset→effective, ends→expires), the 12hr relative-day format family, and omit-on-null. The
discussion therefore targeted only the unspecified "how": styling, layout, active/upcoming
determination, and scope/edges. Grounded in the live render site `_weather_segment` Step 3c
(`claude-statusline.py` ~L3653–3690).

## Area: Time text styling

- **Options:** Dimmed gray (DIM, matches reset-time convention) / Inherit class color / Class
  color but not bold.
- **Selected:** Inherit class color — whole detail stays one class hue (incl. BOLD intensity).
- → **D-01**

## Area: Placement & connector

- **Q1 options:** Event+time then tally / Event+tally then time / Separator before time.
  - **Selected:** Separator before time → `{glyph} {event} <sep> {time}  {tally}`.
- **Q2 (separator char) options:** Middot `·` / En dash `–` / Em dash `—`.
  - **Selected:** Middot `·` (U+00B7), spaces both sides.
- → **D-02**

## Area: Active-vs-upcoming logic

- **Options:** Onset/effective > now → upcoming / Same + anomaly guard (future start but
  stale/invalid end → omit timing).
- **Selected:** Onset future AND ends valid — i.e. with the anomaly guard.
- → **D-03 / D-03a** (onset==now resolves to active/`until`)

## Area: Timing scope & far-out edge

- **Q1 (scope) options:** Primary alert only / Timing on all (verbose).
  - **Selected:** Primary alert only.
  - → **D-04**
- **Q2 (far-out) options:** Accept ambiguity (keep spec) / Add date fallback >6 days.
  - **Selected:** Add date fallback — `<Mon> <D> at 3:00 PM` (e.g. `Jul 3 at 3:00 PM`) at 7+ days.
  - → **D-05**

## Deferred / redirected

- Timing on tallied non-primary alerts (rejected this phase — verbosity).
- Relative countdowns ("in 2h") — already out of scope in REQUIREMENTS.md.
- OSC 8 clickable alert links — Phase 9.

## Claude's discretion (captured)

strftime patterns, local-tz conversion of NWS timestamps, dedicated `_fmt_alert_time`-style
helper, and the all-null-timestamps → event-only fallback. See CONTEXT.md "Claude's Discretion".
