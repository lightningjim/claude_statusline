# Phase 11: Version Display - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

The statusline reports the current version of the local `claude` executable and the
installed GSD plugin version, surfaced as a small trailing fragment on the bottom line.
This phase covers sourcing those two version strings and rendering them; it does NOT
include update-availability checks, changelog/diff surfacing, or any network lookups.

</domain>

<decisions>
## Implementation Decisions

### Placement & layout
- **D-01:** Versions render as a trailing fragment on the **bottom line**, appended
  **after** the Claude-status segment in `render_bottom_line` (claude-statusline.py:4402).
  Layout: `[bar] pct%   ⏳ 5h%   🗓 wk%   <status>   <versions>`. Versions are static
  reference info and belong with the bottom line's meta/diagnostic stats, not the
  identity-focused top line.
- **D-02:** The version fragment is a single builder that returns `None` when it has
  nothing to show, and is None-filtered into the existing `parts` list exactly like the
  other bottom-line segments (so it joins with the established 3-space block separator
  and disappears cleanly when empty). The two versions (Claude, GSD) sit inside one
  fragment, internally space-separated (not 3-space-separated from each other).

### Claude version source
- **D-03:** Source the Claude version from the **stdin `version` field** that Claude Code
  already pipes in (= the version running THIS session). No subprocess, zero latency —
  honors the never-block runtime contract. Do NOT shell out to `claude --version`.
- **D-04:** If stdin `version` is missing/empty/non-string, **omit the Claude fragment**
  (omit-not-fake — see [[statusline-omit-not-fake]]). Never substitute a placeholder.

### GSD version source & gating
- **D-05:** Source the GSD version from the **installed-plugins ledger**:
  `~/.claude/plugins/installed_plugins.json` → `plugins["gsd@gsd-plugin"]` → the entry's
  `version` field (e.g. `"4.0.0"`). This is the authoritative *active* version.
  Do NOT derive it from the highest cached directory under
  `plugins/cache/gsd-plugin/gsd/*/` (stale dirs accumulate — 6 present today) and do NOT
  read the plugin's `package.json` `version` (reports an unrelated internal number,
  `2.45.0`, not the plugin version).
- **D-06:** Read the ledger safely using the existing byte-capped JSON-read pattern from
  `_read_gsd_state` (claude-statusline.py:3016): explicit byte cap, `try/except`, expanduser
  on the path. No network, so no TTL cache is needed — it is a cheap local file read.
- **D-07:** **Always show** the GSD version (in every project, not gated on `.planning/`
  presence — this differs from the existing `_gsd_segment`). Omit the GSD fragment ONLY
  when the plugin is not installed / the ledger entry is absent / the file is unreadable
  (omit-not-fake).

### Format & visibility
- **D-08:** Render each version with a **leading Nerd Font glyph**, no word labels:
  `<cc-glyph> 2.1.195  <gsd-glyph> 4.0.0`. Follow the existing `_NF_*` convention —
  literal codepoint per glyph + an intent-comment naming the nf code (as at
  claude-statusline.py:966+).
- **D-09:** The fragment renders **dimmed** (reuse the existing `DIM = "\033[2m"`
  constant, claude-statusline.py:80 — already used for reset times) so it recedes on a
  glance but is there when wanted.
- **D-10:** A new config toggle **`show_versions` defaults to `True`** (on by default).
  When false, the whole fragment is omitted.
- **D-11:** Honor the existing `icon_set` config: when `icon_set == "nerd"`, use the NF
  glyphs (D-08); when `icon_set != "nerd"`, fall back to short text labels rather than
  emitting Nerd Font codepoints — mirror the glyph-swap pattern already in
  `render_bottom_line` (claude-statusline.py:4442, where `_glyph_5h`/`_glyph_wk` swap).

### Claude's Discretion
- Exact Nerd Font codepoints for the Claude glyph and the GSD glyph (pick sensible NF
  icons — e.g. a Claude/cloud-ish glyph and a plugin/puzzle/cog glyph — following the
  `_NF_*` literal-codepoint + comment pattern). Kyle chose "Nerd Font glyphs" as the
  style; specific glyph choice is open.
- The text-label fallback strings used when `icon_set != "nerd"` (e.g. `claude`/`gsd` or
  `c`/`g`).
- Exact internal spacing within the fragment and whether the `show_versions` key lives
  under `toggles` (like `show_context_bar`, line 159) or `display` (like `show_gsd`,
  line 206) — planner picks the consistent home.
- Whether to drop a leading `v` on the numbers (`2.1.195` vs `v2.1.195`).

</decisions>

<specifics>
## Specific Ideas

- Concrete render target (nerd, on by default, dim, bottom-line trailing):
  `▓░ 12%   ⏳ 5h 8%   🗓 wk 40%   ⓘ status   <cc-glyph> 2.1.195  <gsd-glyph> 4.0.0`
- "Tell the truth at a glance" — versions should be present but unobtrusive (hence dim).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs, ADRs, or design docs govern this phase — requirements are fully
captured in the decisions above. ROADMAP.md lists `Canonical refs:` as TBD for Phase 11.

Authoritative runtime data sources (not docs, but the files the code reads):
- `~/.claude/plugins/installed_plugins.json` — the active-plugin ledger; `gsd@gsd-plugin`
  entry's `version` is the authoritative GSD version (D-05).
- stdin `version` field (see `.examples/claude_stdin.json`) — the Claude Code version
  for the running session (D-03).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `render_bottom_line` (claude-statusline.py:4402) — the integration point; build the
  versions fragment here and None-filter it into the `parts` list (line 4473).
- `_claude_status_segment` / other `*_segment` builders — the established
  "return a string or `None`" segment-builder shape to mirror.
- `_read_gsd_state` (claude-statusline.py:3016) — byte-capped, try/except, expanduser
  JSON-read pattern to copy for reading `installed_plugins.json` (`_GSD_MAX_BYTES` cap).
- `DIM` ANSI constant (claude-statusline.py:80) — for the dimmed render (D-09).
- `_NF_*` glyph constants (claude-statusline.py:966+) — literal-codepoint + intent-comment
  convention for the two new version glyphs (D-08).
- icon_set glyph-swap in `render_bottom_line` (claude-statusline.py:4442) — pattern for
  the nerd-vs-text fallback (D-11).
- `_APP_VERSION = "0.2.0"` (claude-statusline.py:878) — this app's own version string
  (unrelated to the two versions being displayed; do not confuse).

### Established Patterns
- Per-segment config toggles drive omission (`show_context_bar`, line 160; `show_gsd`,
  line 206). The new `show_versions` toggle follows this (D-10).
- Omit-not-fake on bad/absent data is a project invariant ([[statusline-omit-not-fake]]).
- Bottom-line blocks join with 3 spaces; intra-fragment items use single spaces.

### Integration Points
- New `show_versions` toggle added to the config defaults block (around line 159 / 203).
- Bottom-line `parts` assembly (line 4473) gains the versions fragment.
- `icon_set` is already resolved in `render_bottom_line` (line 4442) — reuse it.

</code_context>

<deferred>
## Deferred Ideas

- Update-availability awareness — flagging when a newer `claude` or GSD version exists
  (would require network checks; out of scope for this display-only phase).
- Surfacing on-disk binary version vs running-session version drift (would require a
  `claude --version` subprocess; rejected here per the never-block contract).

</deferred>

---

*Phase: 11-show-current-versions-of-the-local-claude-executable-as-well*
*Context gathered: 2026-06-27*
