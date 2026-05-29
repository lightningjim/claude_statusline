---
phase: 03-presets-for-the-type-of-block-fill-for-the-progress-bar-incl
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - claude-statusline.py
  - tests/test_bottom_line.py
  - tests/test_config.py
  - tests/test_nerd_icons.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the `bar_style` preset feature: the `_BAR_PRESETS` table, the `_bar_preset()`
resolver, the gradient eighth-block sub-cell rendering in `_context_segment`, per-cell
coloring, and the new/changed tests. All 168 tests in the three test files pass (20 skipped
for missing optional deps).

The gradient math is correct and well-clamped. I traced the eighth-block arithmetic across
0%, 100%, sub-1%, whole-cell-boundary, negative, and overflow inputs — `total_eighths` is
clamped to `[0, _BAR_WIDTH*8]` so the bar is always exactly 20 cells wide and
`_GRADIENT_PARTIAL` is never indexed out of range. The non-gradient branch is likewise
clamped (`max(0, min(_BAR_WIDTH, ...))`). The 0%/100% edge cases produce all-blank and
all-full output respectively, matching the tests.

The one substantive defect is in the fallback path: `_bar_preset()` documents "Never raises"
and RUN-02 requires an unknown `bar_style` to silently fall back to shade, but a non-hashable
TOML value (e.g. `bar_style = ["gradient"]`, a valid TOML array) makes `dict.get()` raise
`TypeError`, which is swallowed by the outer handler and **drops the entire context bar**
rather than degrading to shade. The process still exits 0, so this is a graceful-degradation
contract violation, not a crash.

## Warnings

### WR-01: `_bar_preset` raises on non-hashable `bar_style`, silently dropping the context bar instead of falling back to shade

**File:** `claude-statusline.py:110-115` (also `:1356`)
**Issue:**
`_bar_preset` is documented as "Never raises — an unknown/missing bar_style silently returns
the shade pair (RUN-02)." It uses `_BAR_PRESETS.get(style, ...)`, but `dict.get()` raises
`TypeError: unhashable type` when `style` is a list/dict. A user TOML of
`bar_style = ["gradient"]` (a perfectly legal TOML array) flows through `load_config` →
`render_bottom_line` (`_display.get("bar_style", "shade")` returns the list unchanged) →
`_context_segment(..., bar_style=["gradient"])`. Because the gradient branch is gated on
`bar_style == "gradient"` (a safe `==` that is False for a list), execution reaches
`_bar_preset(["gradient"])`, which raises. The exception is caught by `_context_segment`'s
`except: return None`, so the whole context segment is omitted — the bottom line renders with
no `[...]` bar at all instead of the shade fallback the contract promises.

Verified end-to-end: with `bar_style = ["gradient"]` the bottom line renders as
` 50%    50%` — no bar bracket. Scalars (`int`, `None`, unknown strings) fall
back correctly; only non-hashable values trip this.

**Fix:** Make the resolver tolerate non-hashable / non-string input so it actually honors its
"never raises / always shade" contract:
```python
def _bar_preset(style: str) -> tuple[str, str]:
    """Return (filled_glyph, empty_glyph) for *style*, falling back to shade (RUN-02)."""
    try:
        return _BAR_PRESETS.get(style, _BAR_PRESETS["shade"])
    except TypeError:
        # Non-hashable bar_style (e.g. a TOML array) — degrade to shade, never raise.
        return _BAR_PRESETS["shade"]
```
A matching test belongs in `TestPerSegmentToggles` / `TestBarStylePresets`, e.g.
`bar_style = ["gradient"]` (or `bar_style = 5`) must still produce a 20-cell shade bar.

### WR-02: No test covers the non-string `bar_style` fallback path (RUN-02 gap)

**File:** `tests/test_config.py:377-392`, `tests/test_nerd_icons.py:228-232`
**Issue:**
`test_unknown_bar_style_falls_back_to_shade` only exercises an unknown **string**
(`"diagonal"`), and `test_unknown_style_falls_back_to_shade` only passes the string
`"diagonal"` to the resolver. Neither covers the non-hashable / non-string case that WR-01
shows actually breaks the fallback. The RUN-02 guarantee ("unknown bar_style must silently
fall back, never raise") is asserted only for the easy path. Because the suite is green, the
WR-01 defect ships undetected.

**Fix:** Add a case feeding a TOML array and a numeric value, asserting a 20-cell shade bar
and exit 0 (depends on WR-01 fix landing):
```python
def test_non_string_bar_style_falls_back_to_shade(self):
    toml = b"[display]\nbar_style = [\"gradient\"]\n"
    rc, lines, stderr = self._run_with_toml(toml)
    self.assertEqual(rc, 0)
    bar = self._extract_bar(lines[1])
    self.assertEqual(bar.count("▓"), 1)
    self.assertEqual(bar.count("░"), 19)
```

## Info

### IN-01: `_FILLED` / `_EMPTY` module constants are now dead code

**File:** `claude-statusline.py:102-103`
**Issue:**
`_FILLED` and `_EMPTY` are described as "Backward-compat references kept for any code that
still uses the bare names," but the gradient and whole-cell branches now resolve glyphs via
`_bar_preset(bar_style)` or hardcode `"█"`/`" "`. A repo-wide grep finds no remaining readers
in `claude-statusline.py` or `tests/`. They are unused.
**Fix:** Remove both lines, or add a comment confirming they are an intentional public-ish
export. Leaving unused "backward-compat" names invites confusion about whether the bar still
reads them.

### IN-02: `_BAR_PRESETS["gradient"]` empty glyph (`" "`) is never consumed via `_bar_preset`

**File:** `claude-statusline.py:99`, `:1330-1350`
**Issue:**
The gradient branch hardcodes `"█"` for full cells and `" "` for the blank track and never
calls `_bar_preset("gradient")`. The `("█", " ")` pair in the table is therefore inert for
the actual render path (it only matters if some future caller resolves the gradient pair
directly). This is a latent divergence: if someone edits the table's gradient glyphs expecting
the bar to change, nothing happens.
**Fix:** Either drive the gradient full/blank glyphs from `_bar_preset("gradient")` so the
table is the single source of truth, or add a comment at line 99 noting the gradient pair is
documentation-only and the real glyphs live in the gradient branch.

### IN-03: Gradient rounding uses banker's rounding inconsistently with the floor-based whole-cell path

**File:** `claude-statusline.py:1334` vs `:1354`
**Issue:**
The gradient branch uses `round(pct / 100 * _BAR_WIDTH * 8)` (Python banker's rounding,
round-half-to-even) while the whole-cell branch uses `math.floor(pct * _BAR_WIDTH / 100)`
(truncation, matching the documented bash `cut -d.` behavior). The two presets therefore use
different rounding rules, so the same `pct` can render a fuller-looking gradient bar than the
shade bar at the same value (e.g. pct just under a boundary). This is intentional sub-cell
precision, not a bug, but it is undocumented and a half-eighth value would round-to-even
surprisingly. The test mirrors the impl's `round` so it can't catch a divergence.
**Fix:** Add a one-line comment at `:1334` stating gradient deliberately uses nearest-eighth
rounding (vs the whole-cell floor) so the contrast is intentional, and that the test must keep
its rounding in lockstep with the implementation.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
