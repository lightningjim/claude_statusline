---
status: partial
phase: 08-alert-timing
source: [08-VERIFICATION.md]
started: 2026-06-20
updated: 2026-06-20
---

## Current Test

[awaiting human testing]

## Tests

### 1. Alert timing renders correctly in a real terminal
expected: With the venv active and a live (or crafted) NWS alert in the cache, the weather segment renders the timing fragment as `<glyph> <event> · until <time>` (active) or `<glyph> <event> · from <time>` (upcoming), the ` · ` middot separator displays cleanly, the time matches the local wall clock, and the entire detail (including the timing) is wrapped in the alert's class color — the timing is NOT a different/dim color. Confirm an already-expired-but-cached alert shows the event with NO timing fragment (no false `until <past time>`).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
