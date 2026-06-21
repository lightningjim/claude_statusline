---
status: partial
phase: 09-clickable-links
source: [09-VERIFICATION.md]
started: 2026-06-21T01:31:51Z
updated: 2026-06-21T01:31:51Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. LINK-01 — Claude Status incident is clickable
expected: In a supporting terminal (iTerm2, WezTerm, or with `links="on"`), the status segment text is clickable and opens the relevant `https://status.claude.com/incidents/<id>` page. Link text (glyph + label) is visually indistinguishable from normal text — no escape-sequence fragments visible. Correct incident page opens, never the homepage.
result: [pending]

### 2. LINK-02 — Weather alert is clickable
expected: In a supporting terminal with an active weather alert (valid UGC in geocode), the alert segment opens `https://api.weather.gov/alerts/active?zone=<UGC>`. The tally (`+N`) is NOT part of the clickable region.
result: [pending]

### 3. LINK-03 — Plain-text fallback, no escape noise
expected: In a non-supporting terminal (xterm, or `links="off"`), both the status and weather segments render as plain colored text — no visible `]8;;` fragments, no stray ESC characters, no broken unicode.
result: [pending]

### 4. WR-01 (advisory) — VTE version threshold under links="auto"
expected: With `links="auto"` in a VTE terminal where `VTE_VERSION` < 5000 (older GNOME Terminal / Terminator), either no link is emitted (correct conservative behavior) or visible escape garbage appears (confirming WR-01). Fix if confirmed: gate `auto` on `int(VTE_VERSION) >= 5000`.
result: [pending]

### 5. WR-02 (advisory) — JetBrains JediTerm discrimination under links="auto"
expected: With `links="auto"` in the legacy JetBrains JediTerm terminal, either no link is emitted or visible escape garbage appears (confirming WR-02). `TERMINAL_EMULATOR=JetBrains-JediTerm` cannot distinguish legacy from reworked terminal. Conservative fix: drop JetBrains from the `auto` allowlist (users opt in via `links="on"`).
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
