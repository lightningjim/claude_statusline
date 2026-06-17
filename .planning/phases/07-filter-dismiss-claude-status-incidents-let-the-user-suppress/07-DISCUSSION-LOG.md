# Phase 7: Filter/dismiss Claude-status incidents - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
**Areas discussed:** Filter mechanism, Discovery & management, Lifecycle (escalation + stale ids), Storage & config keys

**Origin:** Raised by Kyle immediately after Phase 6 shipped — the live Mythos/Fable model-access-removal incident is a permanent policy change logged as an ongoing `monitoring` incident, so the Phase 6 segment is perpetually lit.

---

## Filter mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Id dismiss + keyword | Dismiss by stable incident id + optional title keyword/regex | ✓ |
| Id dismiss only | Exact id only | |
| Keyword/regex only | Title patterns only | |
| Threshold-based | Hide by impact/status | |

**User's choice:** Id dismiss + keyword (D-01).

---

## Discovery & management

| Option | Description | Selected |
|--------|-------------|----------|
| Helper CLI flag | `--status-incidents` lists current incidents (id/impact/status/title/component) | ✓ |
| Read the cache file | cat the cache JSON manually | |
| Show id inline in segment | Append id token to the bar label | |

**User's choice:** Helper CLI flag (D-02). Extended in discussion to `--dismiss <id>` / `--undismiss <id>` management commands.

---

## Lifecycle — escalation

| Option | Description | Selected |
|--------|-------------|----------|
| Re-surface on escalation | Reappears if impact rises above impact-at-dismiss | ✓ |
| Stay muted regardless | Permanent mute until resolved | |
| Re-surface on any change | Reappears on any impact/status change | |

**User's choice:** Re-surface on escalation (D-03). Requires storing impact-at-dismiss per id.

---

## Lifecycle — stale ids

| Option | Description | Selected |
|--------|-------------|----------|
| Leave config alone | Stale id = harmless no-op; helper flags stale entries | |
| Auto-prune stale ids | Tool removes ids no longer in the feed | ✓ |

**User's choice:** Auto-prune stale ids (D-04). Drove the storage decision (D-05) — auto-prune is only non-invasive if the store is tool-owned.

---

## Storage & config

| Option | Description | Selected |
|--------|-------------|----------|
| CLI + tool-owned store | id-dismissals (id + impact-at-dismiss + timestamp) in a tool-managed JSON file the tool freely auto-prunes; keyword patterns + toggle in TOML; user TOML never rewritten | ✓ |
| All in TOML, tool rewrites | Everything in [claude_status]; tool rewrites TOML to auto-prune | |

**User's choice:** CLI + tool-owned store (D-05).

### Config keys

| Option | Description | Selected |
|--------|-------------|----------|
| Patterns list + enable toggle | `ignore_title_patterns = [...]` + a master toggle | ✓ |
| Patterns + case/regex options | Plus case-sensitivity / regex-mode knobs | |
| You decide at planning | Defer naming/shape | |

**User's choice:** Patterns list + enable toggle (D-06).

---

## Claude's Discretion

- Exact flag names + `--status-incidents` output format (table vs `--json`).
- Dismissal store path/filename/schema (reuse cache dir + atomic-write helpers).
- Keyword matching semantics (case-insensitive substring vs regex; bad regex must degrade to no-match, never crash).
- Enable-toggle key name + default.
- Where the filter applies (inside `_derive_claude_status` vs post-filter — lean to derivation so quiet-when-healthy still holds).
- Whether a "N suppressed" hint surfaces (default: no bar hint).

## Deferred Ideas

- Threshold-based filtering (impact/status) — not the chosen mechanism; possible later knob.
- Inline id on the bar — rejected (width/noise).
- Tool rewriting user TOML — rejected (tool-owned store instead).
- Bar-side "N suppressed" indicator — off by default.
- Remote/synced dismissals, notifications, incident-history view — out of scope.
