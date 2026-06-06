---
quick_id: 260606-kpt
description: commit the D-10 GSD-fragment omit-not-fake fix
date: 2026-06-06
status: complete
---

# Quick Task 260606-kpt: Commit the D-10 GSD-fragment omit-not-fake fix

## Objective

Land a pre-existing, working-tree change that applies the project's D-10
"omit, don't fake" truth-telling rule to the GSD segment's plan-of-total
fragment. The work was already implemented and sitting uncommitted on top of
the completed v1.0 milestone; this task verifies the test suite and commits it
atomically before the milestone is archived.

## Task

1. **Verify** — run the full pytest suite; require a green result before commit.
2. **Commit code** — atomically commit the source + test changes:
   - `claude-statusline.py` — `_gsd_segment` now omits the `(done/total)`
     wave fragment when the STATE.md progress block is internally inconsistent
     (`completed_plans > total_plans`, or `total_plans <= 0`). The real
     `(51/47)` WxDesktopPy case is the regression target. Per D-10 the
     fragment is dropped silently rather than shown or clamped.
   - `tests/test_gsd_segment.py` — adds a positive control
     (`test_wave_part_rendered_when_plans_consistent`) and the regression guard
     (`test_wave_part_omitted_when_done_exceeds_total`).
3. **Track** — record the task in STATE.md "Quick Tasks Completed".

## Verify

- `pytest` exits 0 (all tests pass, astral self-skips allowed).
- The impossible `(51/47)` fragment never renders; the plan id still renders.
