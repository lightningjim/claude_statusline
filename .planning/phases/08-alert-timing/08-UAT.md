---
status: complete
phase: 08-alert-timing
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-06-20T20:16:23Z
updated: 2026-06-20T20:16:23Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold-Start Smoke Test
expected: |
  `python3 claude-statusline.py < .examples/claude_stdin.json` prints the two-line
  bar and exits 0. (Verified inline: both lines rendered, exit 0; a real live NWS
  "Heat Advisory · from Tmrw. at 1:00 PM" appeared, confirming the upcoming branch +
  the "Tmrw. at" relative-day arm work against live data.)
result: pass

### 2. Alert timing renders correctly in your terminal
expected: |
  Run: `~/.claude/claude-statusline/.venv/bin/python .examples/alert_timing_demo.py`
  Confirm each scenario:
    1. ACTIVE     → `<glyph> Tornado Warning · until <time>` (whole detail one class color)
    2. UPCOMING   → `<glyph> Winter Storm Warning · from <time>`
    3. FAR-OUT    → dated `... · from <Mon> <D> at <time>` (7+ days)
    4. EXPIRED    → event only, NO `· until/from` fragment (CR-01: no false past time)
    5. PRIMARY+TALLY → timing on the primary alert only; tally trails after it
  And verify: the ` · ` middot renders cleanly, the Nerd Font alert glyphs show
  (not tofu/boxes), the timing text is the SAME color as the event (not dim), and
  the times match your local wall clock.
result: pass

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
