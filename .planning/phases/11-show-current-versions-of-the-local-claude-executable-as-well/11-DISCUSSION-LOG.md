# Phase 11: Version Display - Discussion Log

> **Audit trail only.** Not consumed by downstream agents (researcher, planner, executor).
> Decisions are captured in 11-CONTEXT.md.

**Date:** 2026-06-27
**Phase:** 11-show-current-versions-of-the-local-claude-executable-as-well
**Mode:** discuss (--chain)
**Areas discussed:** Placement & layout, Claude version source, GSD scope & gating, Format & default visibility

## Gray Areas Presented (multiSelect)

User selected ALL four offered areas.

## Questions & Selections

### Placement & layout
- Options: Bottom line trailing / Top line trailing / Own third line / Inside GSD segment
- **Selected:** Bottom line, trailing (after the Claude-status segment)

### Claude version source
- Options: stdin `version` / `claude --version` subprocess / Both (session + on-disk)
- **Selected:** stdin `version` (free, zero-latency, honors never-block contract)

### GSD scope & gating
- Source pre-locked: `installed_plugins.json` ledger (authoritative active version).
- Options: Only when .planning/ exists / Always show / Tie to show_gsd toggle
- **Selected:** Always show (omit only when plugin not installed)

### Default visibility & format
- Options: On by default dim / Off by default / On by default full color
- **Selected:** On by default, dim (new `show_versions` toggle defaults true)

### Exact label format (follow-up)
- Options: Word labels / Compact letters / Nerd Font glyphs / Bare versions
- **Selected:** Nerd Font glyphs (leading glyph per version, no word labels)

## Deferred Ideas
- Update-availability checks (newer version exists) — needs network, out of scope.
- On-disk binary vs running-session drift — needs `claude --version` subprocess, rejected
  per never-block contract.

## Claude's Discretion (handed to planner)
- Exact Nerd Font codepoints for the two version glyphs.
- Text-label fallback strings when `icon_set != "nerd"`.
- `show_versions` toggle home (`toggles` vs `display`), intra-fragment spacing, leading `v`.
