---
quick_id: 260606-kpt
description: commit the D-10 GSD-fragment omit-not-fake fix
date: 2026-06-06
status: complete
commit: c5e394e
---

# Quick Task 260606-kpt: Summary

One-liner: Verified and committed the pre-existing D-10 omit-not-fake fix for the GSD segment's plan-of-total fragment.

## What shipped

- **`claude-statusline.py`** — `_gsd_segment` guards the `(done/total)` wave
  fragment behind `plans_total > 0 and plans_done <= plans_total`. When the
  STATE.md progress block is internally inconsistent (the real `(51/47)`
  WxDesktopPy case), the fragment is omitted silently per D-10 rather than
  shown or clamped. The plan id still renders.
- **`tests/test_gsd_segment.py`** — added `test_wave_part_rendered_when_plans_consistent`
  (positive control) and `test_wave_part_omitted_when_done_exceeds_total`
  (regression guard).

## Verification

- Full suite: **493 passed, 6 skipped** (astral self-skips), 143 subtests passed.
- Targeted `test_gsd_segment.py`: **65 passed**.

## Commit

- `c5e394e` — fix(gsd): omit plan-of-total fragment on impossible done>total ratio (D-10)
