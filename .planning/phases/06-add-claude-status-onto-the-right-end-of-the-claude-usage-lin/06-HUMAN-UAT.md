---
status: partial
phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
source: [06-VERIFICATION.md]
started: 2026-06-16T00:00:00Z
updated: 2026-06-16T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Nerd-font status glyphs render as real glyphs (not tofu boxes)
expected: In the actual terminal, the incident glyph (`_NF_CLAUDE_INCIDENT`, exclamation U+F06A) and the maintenance glyph (`_NF_CLAUDE_MAINT`, wrench U+F0AD) display as proper Nerd Font glyphs at single-cell width — not a missing-glyph box/▯ — when `icon_set = "nerd"`. (Emoji/ascii fallbacks apply for other icon sets.)
result: [pending]

### 2. Quiet-when-healthy live look
expected: When all tracked components (Claude Code, claude.ai, Claude Cowork) are operational with no relevant incident or maintenance, the bottom line shows ONLY the context bar + 5h + weekly segments — no trailing status element, no stray separator at the right end.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
