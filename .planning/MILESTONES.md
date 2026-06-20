# Milestones

## v1.0 MVP (Shipped: 2026-06-20)

**Phases completed:** 12 phases (8 integer + 4 inserted decimals), 28 plans, 26 tasks
**Timeline:** 2026-05-28 → 2026-06-20 (23 days, 273 commits)
**Audit:** ✅ PASSED — 19/19 requirements, 0 orphaned/0 missing wires, 5/5 E2E flows (see `milestones/v1.0-MILESTONE-AUDIT.md`)

**Key accomplishments:**

- **Core two-line statusline from stdin** — top line `[project] [model 💭]`; bottom line a 20-wide `▓░` context bar + %, plus 5h/weekly rate indicators threshold-colored (green<70/yellow/red>90) with reset times shown only when not green; stdlib-`tomllib` TOML config with per-segment toggles; graceful degradation to exit 0 on any malformed/missing stdin (Phase 1).
- **NWS weather layer that never blocks the render** — condition glyph + temp + precip, local `astral` sunrise/sunset, active-alert override, all served from a sectioned temp-file cache fed by a detached fire-and-forget refresh (Phase 2).
- **Nerd Font icon set behind an `icon_set` toggle** (nerd default / emoji fallback) — render-time glyph resolver with day/night variants, live moon phases, and semantic color, validated by a fontTools cmap guard test (Phase 02.1).
- **Meteorologist-grade alert handling** — VTEC-significance Watch/Warning/Advisory classification with per-class glyph, hue, and urgency/certainty intensity, plus a per-class remainder tally and ANSI-sanitized event text (Phase 02.2).
- **Configurable context-bar fill** via `bar_style` — shade (default), solid, solid-dim, and a 1/8 sub-cell gradient preset (Phase 3).
- **Two read-only top-line context segments** — git (branch/dirty/ahead-behind + linked-worktree marker, timeout-guarded, omits off-repo) and GSD planning status (active plan + task progress + lifecycle glyph, HANDOFF-first with roadmap fallback) (Phases 4–5).
- **Claude service-health indicator on the usage line** — quiet-when-healthy `status.claude.com` segment (tracked components only), with a config-driven incident filter/dismiss + management CLI (`--status-incidents`/`--dismiss`/`--undismiss`) and resolved-vs-unresolved coloring (Phases 6, 7, 07.1).

**Inserted (decimal) phases:** 02.1 Nerd Font icon set · 02.2 W/W/A differentiation · 03.1 default-bar test-drift fix · 05.1 GSD test hermeticity.

**Open items at close:** none. The pre-close audit flagged 2 artifacts (Phase 06 UAT, quick task 260606-kpt) but both were verified already complete/resolved (quick task committed as `c5e394e`) — false positives, not deferred work.

**Known deferred to v1.1 "QOL and fixes":** clickable links for status/weather alerts; a tech-debt cleanup phase aggregating all `v1.0-MILESTONE-AUDIT.md` tech_debt items (see STATE.md Pending Todos).

---
