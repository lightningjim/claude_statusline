# Phase 3: Block-Fill Presets for the Progress Bar - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a config-selectable set of fill-style "presets" for the 20-wide context bar (`_context_segment`). The bar is currently hardcoded to `▓` (filled) / `░` (empty). This phase keeps that look as one preset and adds visually interesting variations, selectable via config.

In scope: the fill glyphs of the context bar, sub-cell rendering precision, and the per-preset color treatment. Out of scope: bar width, what the bar measures, new bar segments, and any non-context-bar visuals (git/GSD/worktree info are later phases).
</domain>

<decisions>
## Implementation Decisions

### Preset catalog
- **D-01:** Ship four presets. `shade` (current `▓`/`░`) is retained as the baseline. Three additions: `solid` (`█`/`░`), `solid-dim` (`█`/`▒`), and `gradient`.
- **D-02:** `gradient` = full `█` blocks for filled cells, a **sub-cell boundary cell** using left-aligned partial blocks down to 1/8 (`▏▎▍▌▋▊▉`), and a **blank** (space `" "`) empty track — not `░` or `▒`.
- **D-03:** `ascii` and `dots` were considered and explicitly **not** included. Braille and Nerd/powerline fills were not added (can be revisited in a future phase if desired).

### Sub-cell fractional fill
- **D-04:** Sub-cell precision (the 1/8 partial-block boundary cell) applies to the `gradient` preset **only**. `shade`, `solid`, and `solid-dim` stay whole-cell — floored to whole cells (~5%/cell), exactly as `_context_segment` does today.
- **D-05:** Each preset has exactly one fixed look — no independent `smooth` toggle layered across presets.

### Color treatment
- **D-06:** Uniform rule across all presets: **filled cells render in the threshold color** (green/yellow/red via `color_for`); **empty cells render in dim gray** (`GRAY = \033[90m`, already defined at line 88). This changes the current behavior where the whole bar (including empty `░`) shares one threshold color.
- **D-07:** For `gradient`, the empty track is blank space, so the gray treatment is effectively moot there; the rule still sharpens `shade`/`solid`/`solid-dim`.

### Config & default
- **D-08:** New config key `bar_style` (string) in the `[display]` section, mirroring the existing `icon_set` pattern. Values: `"shade" | "solid" | "solid-dim" | "gradient"`.
- **D-09:** Default is `"shade"` — zero visual change for existing installs; users opt into the new styles. Add it to `DEFAULTS["display"]`.
- **D-10:** `bar_style` is **independent** of `icon_set`. All four presets use standard Unicode block characters (not Nerd-Font PUA glyphs), so they work identically under `nerd` or `emoji`.

### Claude's Discretion
- Exact eighth-block math for `gradient` (e.g. `round(pct/100 × _BAR_WIDTH × 8)` eighths → full cells + boundary glyph index) and its edge cases (0% all-blank, 100% all-`█`).
- How to refactor the hardcoded `_FILLED`/`_EMPTY` constants (lines 92–93) into a preset table/lookup, and where that table lives.
- Silent fallback to the default `"shade"` when `bar_style` is set to an unknown value (consistent with the project's graceful-degradation contract).
- Updating the existing `_FILLED`/`_EMPTY` assertions in `tests/test_nerd_icons.py` (lines 193–198) to match the refactor.
</decisions>

<specifics>
## Specific Ideas

- The `gradient` preset is the user's own addition, described as "more detailed, blank empty — utilizing the left blocks that go all the way down to eighth." It is the visually richest option and the reason sub-cell rendering enters this phase.
- The user prefers the empty track to read as *empty* (blank) for the gradient look, while accepting a dim-gray track for the block-based presets.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs, ADRs, or design docs exist for this phase — requirements are fully captured in the decisions above. ROADMAP.md lists no `Canonical refs:` for Phase 3.

The relevant in-repo code (not external specs, but where the work lands) is enumerated in `<code_context>` below.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `claude-statusline.py:137-139` — `DEFAULTS["display"]` (currently holds `icon_set`). Add `bar_style` here.
- `claude-statusline.py:164` `load_config()` + `_deep_merge()` (line 147) — config plumbing; new key flows through automatically once added to `DEFAULTS`.
- `claude-statusline.py:88` `GRAY = "\033[90m"` — already-defined dim color for empty-cell treatment (D-06).
- `claude-statusline.py:1147` `color_for()` — threshold→ANSI color helper for filled cells.
- The `icon_set` toggle (Phase 02.1) is the established pattern for a config-driven visual switch — `bar_style` mirrors it (D-08).

### Established Patterns
- `claude-statusline.py:1280` `_context_segment()` builds the bar as `_FILLED * filled + _EMPTY * empty`, floors to whole cells via `math.floor(pct * _BAR_WIDTH / 100)`, clamps to `[0, _BAR_WIDTH]` (CR-01), and wraps the whole bar in a single threshold color. This is the function the phase modifies.
- `claude-statusline.py:90-94` — `_FILLED`/`_EMPTY`/`_BAR_WIDTH` constants. Lines 91 carry the comment "Phase 3: DO NOT modify here — block-fill variations are Phase 3's scope (D-02)" — this phase owns them.
- Graceful degradation contract (RUN-02): unknown/malformed config must never crash — drives the silent-fallback-to-`shade` discretion item.

### Integration Points
- `tests/test_nerd_icons.py:193-198` asserts `_FILLED == "▓"` and `_EMPTY == "░"` — will need updating when constants are refactored into a preset table.
- `tests/test_bottom_line.py:244-257` asserts the bar fill cell counts (`▓`×N, `░`×M) — these assume the `shade` default; should remain valid since default stays `shade`, but verify after refactor.
- `tests/test_config.py:340-346` `show_context_bar=false` drops the bar entirely — orthogonal to `bar_style`; bar_style only matters when the bar renders.
</code_context>

<deferred>
## Deferred Ideas

- `ascii` (`[=== ]`) and `dots` (`●○`) presets — considered, not selected for this phase. Easy future additions if portability or a softer aesthetic is later wanted.
- Braille (`⣿⣀`) and Nerd-Font/powerline fill styles — not added now; candidates for a future preset-expansion pass.
</deferred>

---

*Phase: 03-presets-for-the-type-of-block-fill-for-the-progress-bar-incl*
*Context gathered: 2026-05-29*
