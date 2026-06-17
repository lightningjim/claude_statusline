---
status: partial
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
source: [07-VERIFICATION.md]
started: 2026-06-17T06:16:03Z
updated: 2026-06-17T06:16:03Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Bar goes quiet after dismissing the live Mythos/Fable incident
expected: After `python claude-statusline.py --dismiss s9w82lp9dcn9` then `--refresh`, the Claude-status segment on the bar no longer shows the Mythos/Fable "suspended access" incident — it falls through to the next relevant item (e.g. the Opus 4.8 elevated-errors incident) or omits silently. Re-running `--status-incidents` shows that id with STATE = dismissed.
result: [pending]

### 2. Keyword suppression silences it without an id
expected: Add `ignore_title_patterns = ["Mythos", "Fable"]` under `[claude_status]` in the user TOML, then `--refresh`; the Mythos/Fable incident is suppressed on the bar even with an empty dismissal store. A genuinely new, unrelated incident still lights the bar.
result: [pending]

### 3. Escalation safety valve still surfaces real outages
expected: With the Mythos/Fable incident dismissed by id, if a DIFFERENT tracked incident escalates above its dismissed impact (or a new un-dismissed incident appears), the bar lights as expected — muting never hides a real escalation (D-03).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
