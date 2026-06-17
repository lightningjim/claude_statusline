# Phase 7: Filter/dismiss Claude-status incidents - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend the **Phase 6 Claude service-health segment** with a user-controlled
**incident filter** so non-actionable, long-lived incidents stop perpetually
lighting the bar. Motivating case: `status.claude.com` logs permanent
product/policy changes (e.g. the **Mythos/Fable model access removal**) as
ongoing `monitoring` incidents that never resolve — the Phase 6 segment shows
them forever, defeating its quiet-when-noteworthy value ([[claude-status-perpetual-incidents]]).

This phase adds **filtering only** — it does NOT change how Phase 6 detects,
colors, sanitizes, caches, or places the indicator. A suppressed incident is
treated as if not noteworthy (the segment still omits silently / shows the next
relevant incident or maintenance instead).

**Out of scope:** changing the tracked-component set or the page-vs-component
trigger logic (Phase 6 D-02); changing severity color/glyph/label/sanitization
(Phase 6 D-03/D-04); a full incident-history TUI; remote/synced dismissals;
notifications. Those are separate capabilities.

</domain>

<decisions>
## Implementation Decisions

### Filter mechanism
- **D-01:** **Two complementary filters: dismiss-by-incident-id + title
  keyword/regex.**
  - **Id dismiss** = precise "I've seen this specific incident, mute it." Keyed
    on the incident's stable Statuspage feed `id`. A genuinely new incident (new
    `id`) is never auto-muted.
  - **Keyword/regex** = blanket muting by matching the incident title (e.g.
    `Mythos`, `Fable`). Covers the perpetual case without needing an id, and
    catches a renamed/recurring perpetual incident that gets a fresh id.
  - An incident is suppressed if it matches EITHER filter (subject to the
    escalation override, D-03).

### Discovery & management (CLI)
- **D-02:** **Helper CLI flags** (mirroring the existing `--refresh` arg-handling
  in `main()`):
  - `--status-incidents` (name = discretion) — print the current tracked
    incidents: `id`, `impact`, `status`, `title`, affected tracked component, and
    whether each is currently dismissed/stale. This is how the user learns an
    `id` to mute and picks keywords.
  - `--dismiss <id>` / `--undismiss <id>` — add/remove an id dismissal in the
    tool-owned store (D-05). These never read stdin and never emit the status
    line; they manage the dismissal store and exit (same shape as `--refresh`).

### Lifecycle
- **D-03:** **Re-surface on escalation.** When an incident is dismissed by id,
  store the **impact-at-dismiss-time** alongside it. If the live incident's
  impact later rises ABOVE the stored impact (e.g. `minor`→`major`/`critical`),
  the incident **re-surfaces** (the dismissal is treated as void for that
  incident while escalated) so a muted minor issue turning into a real outage is
  never hidden. Impact ordering follows the Statuspage scale
  (none < minor < major < critical). (Keyword-matched suppression is a blunt
  mute and does not carry per-incident escalation tracking — escalation
  re-surfacing applies to id-dismissals; note this distinction at planning.)
- **D-04:** **Auto-prune stale ids.** When a dismissed `id` is no longer present
  in the live feed (incident resolved/removed), the tool **removes it from the
  dismissal store automatically**, keeping the store tidy without user action.
  This is non-invasive because the store is tool-owned (D-05), not the user's
  config.

### Storage
- **D-05:** **Id-dismissals live in a tool-owned state file; keyword patterns +
  toggle live in hand-edited TOML.**
  - Tool-owned **dismissal store** (JSON/state file, e.g. alongside the existing
    cache; path/shape = discretion): each entry = `{ id, impact_at_dismiss,
    dismissed_at }`. The tool fully owns this file and may freely
    write/auto-prune it (D-04) — analogous to the cache. The user's
    `[claude_status]` TOML is **never rewritten** (avoids clobbering comments/
    formatting; the project reads TOML via `tomllib` and stays read-only on it).
  - Hand-edited **`[claude_status]` TOML** holds the keyword/regex patterns and
    the enable toggle (D-06).

### Config keys
- **D-06:** Under `[claude_status]`, minimal and matching existing style:
  - `ignore_title_patterns = [...]` — list of title patterns (substring vs regex
    semantics = planning discretion; default `[]`).
  - an enable toggle for the filter feature (name = discretion, e.g.
    `filter_enabled`), defaulting consistent with the `display.*`/`DEFAULTS`
    conventions.

### Claude's Discretion
- Exact CLI flag names (`--status-incidents` / `--dismiss` / `--undismiss`) and
  `--status-incidents` output format (table vs JSON; lean to a readable table,
  optionally a `--json` variant).
- Dismissal store path, filename, and JSON schema (reuse the cache dir/atomic-
  write helpers from Phase 2/6).
- Keyword matching semantics: case-insensitive substring (simplest) vs full
  regex; pick one, document it, fail safe (a bad regex must never crash — degrade
  to no-match, per the never-crash contract).
- Exact config key name for the enable toggle and its default value.
- Precisely where the filter is applied: inside `_derive_claude_status` (so the
  derivation already accounts for dismissals and naturally falls through to the
  next relevant incident / maintenance / `None`) vs a thin post-filter — lean
  toward integrating into the derivation so quiet-when-healthy (Phase 6 D-01)
  still holds when the only noteworthy item is suppressed.
- How (or whether) a small "N suppressed" hint surfaces — default: no bar hint
  (keep it quiet); `--status-incidents` is the visibility surface.

</decisions>

<specifics>
## Specific Ideas

- The whole point: "**lit = something I should actually care about.**" The
  Mythos/Fable perpetual incident is the canonical thing to be able to silence.
- Reconcile auto-prune with truth-telling: the tool only auto-writes its OWN
  dismissal store, never the user's config, and never fabricates status — a
  suppressed incident is omitted, not faked ([[statusline-omit-not-fake]]).
- The escalation safety valve (D-03) is what makes muting safe: you can silence
  the perpetual minor noise without risking missing it going critical.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs/ADRs exist. Requirements are captured in the decisions above
plus the Phase 6 implementation this extends:

### Phase 6 (the thing being extended — read first)
- `.planning/phases/06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin/06-CONTEXT.md` — Phase 6 decisions D-01..D-06 (tracked components, derivation, sanitization, cache, placement) that this phase must preserve.
- `.planning/phases/06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin/06-01-SUMMARY.md` / `06-02-SUMMARY.md` — the locked `claude_status` cache contract and the `_derive_claude_status` / `_claude_status_segment` shapes.

### In-repo code (read at planning time to confirm shapes)
- `claude-statusline.py`:
  - `_derive_claude_status(...)` — the pure tracked-component trigger over the
    `summary.json` shape (where id-dismiss + keyword filtering integrates, D-01).
    The feed exposes per-incident `id`, `name`, `impact`, `status`, and affected
    component refs.
  - `fetch_claude_status` + the `claude_status` cache section + the cache dir /
    atomic-write helpers — model for the tool-owned dismissal store (D-05).
  - `main()` `--refresh` arg-handling branch (≈ entry point) — the pattern for
    the new `--status-incidents` / `--dismiss` / `--undismiss` flags (D-02).
  - `DEFAULTS` `[claude_status]` block + `_deep_merge` + `tomllib` config load —
    where `ignore_title_patterns` + toggle are added (D-06); note the project
    reads TOML and must NOT write it (D-05).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_derive_claude_status`** (Phase 6) — the integration point for filtering;
  applying the filter here preserves quiet-when-healthy fall-through (Phase 6
  D-01) and the existing tie-break/selection logic.
- **`claude_status` cache section + cache dir + atomic-write helpers** — direct
  template for the tool-owned dismissal store (D-05); reuse the same dir and
  atomic write/read pattern.
- **`main()` `--refresh` branch** — the established "side-effect flag that
  doesn't read stdin or print the bar, then exits" pattern; the new management
  flags follow it.
- **`[claude_status]` DEFAULTS + `_deep_merge` + `tomllib`** — config plumbing
  for the new keyword list + toggle.

### Established Patterns
- Builders/derivation return `None` / omit on bad data; never crash, never fake
  ([[statusline-omit-not-fake]]). A bad regex or corrupt dismissal store must
  degrade to "no suppression" rather than raise.
- Render path reads cache only and never blocks; the dismissal store read happens
  on the render path and must be equally cheap and failure-tolerant.
- `cfg` threaded explicitly; glyphs via `icon_set` (unchanged here — no new
  glyphs expected).

### Integration Points
- Filtering integrates in `_derive_claude_status` (D-01); dismissal store
  read/write helpers are new (modeled on the cache); new `main()` arg branches
  for the management flags (D-02).
- Tests under `tests/` (closest: `tests/test_claude_status.py`) — add cases for:
  id-dismiss suppression, keyword suppression, escalation re-surface, auto-prune
  of stale ids, store corruption → no suppression, `--dismiss`/`--undismiss`
  store mutation, `--status-incidents` output.

</code_context>

<deferred>
## Deferred Ideas

- Threshold-based filtering (hide by impact/status, e.g. hide `monitoring`) —
  considered and not chosen as the mechanism (D-01); could be added later as an
  extra knob if id+keyword proves insufficient.
- Showing the incident id inline on the bar — rejected (adds width/noise);
  `--status-incidents` is the visibility surface (D-02).
- The tool rewriting the user's TOML to manage dismissals — rejected in favor of
  the tool-owned store (D-05).
- A bar-side "N suppressed" indicator — left off by default to stay quiet;
  revisit only if wanted.
- Remote/synced or multi-machine dismissals, notifications, full incident
  history view — out of scope.

</deferred>

---

*Phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress*
*Context gathered: 2026-06-16*
