# Phase 3: Block-Fill Presets for the Progress Bar - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 03-presets-for-the-type-of-block-fill-for-the-progress-bar-incl
**Areas discussed:** Preset catalog, Sub-cell fractional fill, Color treatment, Config & default

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Preset catalog | Which fill styles to ship | ✓ |
| Sub-cell fractional fill | Whole-cell vs 1/8 partial-block smoothing | ✓ |
| Config & default | Selection key, default value, icon_set coupling | ✓ |
| Color treatment | Uniform vs filled/empty split | ✓ |

**User's choice:** All four areas.

---

## Preset Catalog

Rendered candidate catalog presented (shade/solid/solid-dim/gradient/ascii/dots/braille). Question asked which *additions* beyond the kept `shade` baseline to ship.

| Option | Description | Selected |
|--------|-------------|----------|
| solid `█░` | Full block filled, light-shade empty; highest contrast | ✓ |
| solid-dim `█▒` | Full block filled, medium-shade empty (visible rail) | ✓ |
| ascii `[=== ]` | Bracketed = / space; pure ASCII, font-independent | |
| dots `●○` | Filled/hollow circles; softer aesthetic | |

**User's choice:** `solid █░`, `solid-dim █▒`, plus free-text addition: *"More detailed, blank empty — utilizing the left blocks that go all the way down to eighth"* → the **gradient** preset (full `█` + 1/8 partial-block boundary cell + blank empty track).
**Notes:** `ascii` and `dots` declined. `shade` kept as baseline regardless. Braille / Nerd-powerline left out (noted as deferred).

---

## Sub-cell Fractional Fill

| Option | Description | Selected |
|--------|-------------|----------|
| Gradient preset only | Only gradient renders the fractional boundary; others whole-cell | ✓ |
| All full-block presets | solid + solid-dim also get sub-cell smoothing | |
| Independent toggle | Separate smooth=true/false layered onto any preset | |

**User's choice:** Gradient preset only.
**Notes:** Keeps each preset to one fixed look; whole-cell floor unchanged for shade/solid/solid-dim.

---

## Color Treatment

| Option | Description | Selected |
|--------|-------------|----------|
| Filled colored, empty gray | Filled = threshold color, empty = dim gray (`\033[90m`) | ✓ |
| Uniform (keep as today) | Whole bar shares one threshold color | |
| Per-preset choice | Each preset declares its own color treatment | |

**User's choice:** Filled colored, empty gray.
**Notes:** Changes current uniform behavior; moot for gradient (blank empty) but sharpens the block presets.

---

## Config & Default

**Q1 — Default bar_style:**

| Option | Description | Selected |
|--------|-------------|----------|
| shade `▓░` | Keep current look as default; backward compatible | ✓ |
| gradient | New sub-cell gradient as out-of-box default | |
| solid `█░` | High-contrast full-block default | |

**Q2 — Coupling with icon_set:**

| Option | Description | Selected |
|--------|-------------|----------|
| Independent | bar_style its own key; works under nerd or emoji | ✓ |
| Couple to icon_set | emoji forces ASCII bar; nerd unlocks fancier presets | |

**User's choice:** Default `shade`; `bar_style` independent of `icon_set`.
**Notes:** Key `bar_style` lives in `[display]`, mirroring `icon_set`. Block chars are standard Unicode, so no font coupling needed.

---

## Claude's Discretion

- Exact eighth-block math and edge cases for the gradient preset.
- Refactor of hardcoded `_FILLED`/`_EMPTY` constants into a preset table.
- Silent fallback to `shade` on unknown `bar_style` value.
- Updating affected test assertions (`test_nerd_icons.py`, `test_bottom_line.py`).

## Deferred Ideas

- `ascii` and `dots` presets — considered, not selected.
- Braille and Nerd-Font/powerline fill styles — future preset-expansion pass.
