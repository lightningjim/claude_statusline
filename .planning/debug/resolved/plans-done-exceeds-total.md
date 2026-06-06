---
status: resolved
trigger: "GSD segment shows plans done greater than plans total: [4 (51/47) ] — 51 > 47 looks wrong"
created: 2026-05-30
updated: 2026-05-30
---

# Debug Session: plans-done-exceeds-total

## Symptoms

- **Observed bar (verbatim from user):**
  `[WxDesktopPy] [main 6] [4 (51/47) ] [Opus 4.8 (1M context) ] [ 91°F |  8:38pm]`
- **Expected behavior:** GSD plan counter should never show done > total. `51/47` is impossible.
- **Actual behavior:** GSD segment rendered `(51/47)` — plans_done (51) > plans_total (47).
- **Timeline:** Noticed 2026-05-30. Rendered while Claude Code ran in the WxDesktopPy project.

## Root Cause

**Upstream data inconsistency with no display guard** (not a parsing bug).

WxDesktopPy's `/home/kcreasey/Documents/Projects/WxDesktopPy/.planning/STATE.md` frontmatter
literally contains:

```yaml
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 47
  completed_plans: 51
```

So `completed_plans=51 > total_plans=47` is genuine in the source file (GSD tooling
over-incremented `completed_plans` without resyncing `total_plans`). The statusline parser
(claude-statusline.py ~1584-1595) reads these faithfully and the render site (line 1843)
echoed them verbatim — `wave_part = f" ({plans_done}/{plans_total})"` — with no `done ≤ total`
guard anywhere between parse and render.

specialist_hint: python

## Fix

**Decision (user, 2026-05-30):** Omit the `(x/y)` fragment when the source data is
inconsistent — truth-preserving, consistent with D-10 ("return None to omit silently, no
placeholders"). Chosen over clamping (which would falsely read as "complete") and over a
statusline-only no-op.

`claude-statusline.py` ~line 1842, in `_gsd_segment`'s active/idle interior build:

```python
if (
    plans_done is not None
    and plans_total is not None
    and plans_total > 0
    and plans_done <= plans_total
):
    wave_part = f" ({plans_done}/{plans_total})"
else:
    wave_part = ""
```

The phase/plan id and status glyph still render — only the impossible fragment is dropped.
This also guards a non-positive `total_plans` (no `(N/0)`).

## Verification

- New regression tests in `tests/test_gsd_segment.py` (TestGsdSegmentBuilder):
  - `test_wave_part_rendered_when_plans_consistent` — positive control, `(13/15)` still renders.
  - `test_wave_part_omitted_when_done_exceeds_total` — the real 51/47 case: no `(51/47)`/`/47`,
    plan id `05-02` still present.
  - `test_wave_part_omitted_when_total_is_zero` — no `(N/0)` fragment.
- Full suite: 446 passed, 53 skipped, 232 subtests passed.

## Files Changed

- `claude-statusline.py` — done≤total + total>0 guard on the GSD wave_part fragment.
- `tests/test_gsd_segment.py` — 3 regression tests.

## Note / Follow-up (out of scope for this repo)

The underlying `51/47` in WxDesktopPy's STATE.md is still inconsistent. That is a
WxDesktopPy GSD-state data issue, not a claude_statusline bug — fix there separately if the
inflated `completed_plans` count matters.
