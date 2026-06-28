# Milestones

## v1.1 QOL and fixes (Shipped: 2026-06-28)

**Phases completed:** 4 phases (8–11), 9 plans
**Timeline:** 2026-06-20 → 2026-06-27 · git range `feat(08-01)` → `feat(11-01)`
**Audit:** ✅ PASSED — 12/12 requirements (WX-07..10, LINK-01..03, DEBT-01..05) + Phase 11 VER-01..05 (see `milestones/v1.1-MILESTONE-AUDIT.md`)

**Key accomplishments:**

- **Alert timing on the weather segment** — distinguishes an issued-but-not-yet-active alert (`from <onset>`, falling back to `effective`) from an active one (`until <ends>`, falling back to `expires`), in 12hr am/pm form with same-day / `Tmrw. at` / `<Wkdy> at` relative-day formatting; a null/missing timestamp omits the time rather than faking it (Phase 8, WX-07..10).
- **OSC 8 clickable links** for both Claude Status incidents (wrapping the whole segment to the specific `status.claude.com` incident page, never the homepage) and weather alerts, with a tri-state `links` config + capability auto-detect (gated on `VTE_VERSION>=5000`) and allowlist URL validators, degrading to clean plain text on terminals without OSC 8 support (Phase 9, LINK-01..03).
- **Weather link re-targeted to the human-readable NWS showsigwx page** — warnzone+warncounty derived from the alert's SAME/UGC codes via a FIPS-state table, omit-not-fake when codes are absent (Phase 9, GAP-09-A/B closure).
- **Cleared the v1.0 audit's five-item tech-debt bundle** — `pyproject.toml`↔`_APP_VERSION` version sync (0.2.0), WX-05 cache-TTL text↔code alignment (10 min), REQUIREMENTS traceability/footer reconciliation, `requirements-completed` frontmatter formally retired-with-note, and the astral/requests weather tests made runnable under system `python3` (228 pass / 47 skip / 0 fail) (Phase 10, DEBT-01..05).
- **Version-display fragment** — a dimmed trailing bottom-line fragment showing the running Claude Code version (from stdin `version`, no subprocess) and the active GSD plugin version (from the `installed_plugins.json` ledger, not cache dirs), with Nerd Font glyphs + text fallback, a `show_versions` toggle (default on), an ANSI-injection-rejecting sanitizer, and omit-not-fake on every bad-data path (Phase 11, VER-01..05).

**Open items at close:** none. The pre-close audit flagged 1 artifact (quick task `260606-kpt`) but it was verified already complete and committed (`c5e394e`) — a false positive, not deferred work.

---

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
