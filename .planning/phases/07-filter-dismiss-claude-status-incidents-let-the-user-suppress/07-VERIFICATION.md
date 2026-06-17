---
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
verified: 2026-06-17T00:00:00Z
status: verified
human_verified: 2026-06-17T13:30:00Z
score: 7/7 must-haves verified
overrides_applied: 0
human_uat_result: "3/3 resolved — 2 passed live; 1 issue (dismiss took effect only on next ~5-min cache cycle, not on --refresh) diagnosed and closed by gap-closure plan 07-04 (render-time suppression, 9 passing tests)."
human_verification:
  - test: "Dismiss the live Mythos/Fable perpetual incident and confirm the bar goes quiet"
    expected: >
      After running `python claude-statusline.py --dismiss <id-of-mythos-fable-incident>`
      followed by `python claude-statusline.py --refresh`, the Claude-status segment on the
      bar should stop lighting (go quiet / show no indicator) for that specific incident.
      Running `--status-incidents` should list the incident as "dismissed".
    why_human: >
      The full pipeline — fetch_claude_status writing a new cache with the dismissal
      applied in _derive_claude_status, then render_bottom_line reading that cache and
      omitting the segment — spans a real network fetch + cache TTL + terminal render that
      cannot be verified by grep or unit tests alone. Specifically this confirms that
      (a) the suppressed incident falls through to None (not maintenance, not degraded)
      in the live feed, and (b) the bar segment actually disappears rather than showing
      a residual indicator.
  - test: "Confirm the bar re-surfaces the Mythos incident if it escalates above its dismissed impact"
    expected: >
      With the Mythos incident dismissed at "minor" impact, if its live impact were to
      rise to "major" or "critical", the bar indicator should re-appear (escalation
      re-surface, D-03). This cannot be triggered on-demand in the live feed but the
      user should be aware the safety valve exists; for now, confirm the escalation
      re-surface test fixture (status_incident_tracked_major.json with inc-001 at major)
      passes and the logic is readable in _is_suppressed.
    why_human: >
      Escalation re-surface can only be truly confirmed against a real escalating incident.
      The unit tests cover the logic path (major > minor-at-dismiss → re-surface) but
      real-world confirmation requires observing the bar over time or using a staging feed.
---

# Phase 7: Filter/Dismiss Claude-Status Incidents Verification Report

**Phase Goal:** Extend the Phase 6 Claude service-health segment with a user-controlled
incident filter so non-actionable, long-lived incidents (canonical case: perpetual
Mythos/Fable access-removal incident) stop perpetually lighting the bar — FILTERING ONLY,
preserving Phase 6 detect/color/sanitize/cache/placement, and never crashing/hanging the
render path. (Authoritative acceptance: CONTEXT.md decisions D-01..D-06.)

**Verified:** 2026-06-17
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from CONTEXT.md D-01..D-06 + plan must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | D-01: `_is_suppressed` exists and is threaded into `_derive_claude_status`; suppressed incident falls through to next relevant item / None | VERIFIED | `def _is_suppressed(` at line 1578; called at line 1793 inside incident loop with `continue` on True; `_derive_claude_status` new signature `(summary, dismissals=None, cfg=None)` at line 1702 |
| 2 | D-02: `--status-incidents`, `--dismiss <id>`, `--undismiss <id>` exist as `main()` branches before `_load_stdin`; none read stdin or print the bar | VERIFIED | Branches at lines 3737, 3745, 3753 — all before `cfg = load_config(); data = _load_stdin()` at line 3762; smoke tests confirm each exits 0 without bar output |
| 3 | D-03: Escalation re-surface for id-dismissals only (live_rank > stored_rank via `_CLAUDE_IMPACT_RANK`); keyword is blunt mute with no escalation | VERIFIED | `_CLAUDE_IMPACT_RANK` module constant at line 1558; escalation check at lines 1688-1692 (`if live_rank > stored_rank: return False`); keyword branch returns `True` immediately with no rank comparison |
| 4 | D-04: `_prune_dismissals` wired into `fetch_claude_status` on the refresh path; prune block at lines 2108-2123; runs only in the detached child | VERIFIED | Lines 2109-2121 read store, collect live ids from summary, call `_prune_dismissals`, write pruned store if changed; wrapped in `try/except` |
| 5 | D-05: Tool-owned `_DISMISSALS_PATH` JSON store; `read_dismissals`/`write_dismissals` helpers; NO TOML writer | VERIFIED | `_DISMISSALS_PATH` at line 331; `read_dismissals` at 334, `write_dismissals` at 352; `grep -c "tomllib.dump|toml.*write|.write_text.*toml" claude-statusline.py` = 0 |
| 6 | D-06: DEFAULTS has top-level `claude_status` table with `filter_enabled=True` and `ignore_title_patterns=[]` | VERIFIED | Lines 192-195: `"claude_status": {"filter_enabled": True, "ignore_title_patterns": []}` as top-level sibling of `"display"` |
| 7 | Never-crash: corrupt/missing store → no suppression; bad/catastrophic regex → length-capped (500), degrades to no-match | VERIFIED | `read_dismissals` wraps all in `try/except → {}`; `_is_suppressed` whole body in `try/except → False`; `_CLAUDE_PATTERN_MATCH_MAXLEN = 500` at line 1554; title sliced at line 1654 before any matching |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-statusline.py` | `_DISMISSALS_PATH`, store helpers (5 functions), DEFAULTS `claude_status` table, `_is_suppressed`, updated `_derive_claude_status`, `_collect_tracked_incidents`, CLI handlers, `main()` branches | VERIFIED | All present and substantive; see line numbers above |
| `tests/test_claude_status.py` | 8 new test classes covering all D-01..D-06 behaviors | VERIFIED | `TestClaudeStatusConfigDefaults` (L1405), `TestDismissalStoreHelpers` (L1453), `TestFetchClaudeStatusWidenedPayload` (L1649), `TestIsSuppressed` (L1793), `TestDeriveClaudeStatusFilterIntegration` (L2047), `TestEscalationFixtureAndAutoPrune` (L2223), `TestDismissUndismissFlags` (L2376), `TestStatusIncidentsFlag` (L2559) |
| `tests/fixtures/status_incident_tracked_major.json` | Escalation fixture with inc-001 at impact "major" | VERIFIED | File exists; contains `"impact": "major"` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_derive_claude_status` incident loop | `_is_suppressed` | `continue` before `triggered_incidents.append` | WIRED | Line 1793-1800: `if _is_suppressed(...): continue` |
| `_is_suppressed` escalation check | `_CLAUDE_IMPACT_RANK` | `live_rank > stored_rank` | WIRED | Lines 1688-1692 use the module constant; no duplicate ordering |
| `fetch_claude_status` refresh path | `_prune_dismissals` + `write_dismissals` | live incident ids from summary | WIRED | Lines 2118-2121 |
| `--dismiss` branch | `_handle_dismiss_flag` → `_dismiss_id` | impact baseline from cached `tracked_incidents` | WIRED | Line 3740 → lines 448-458 |
| `--status-incidents` branch | `read_cache` + `read_dismissals` | no network call | WIRED | Lines 3755-3757; `fetch_claude_status` is not called in this branch |
| `_print_status_incidents` | ANSI sanitizer | verbatim `isprintable` + `\x1b` strip from `_claude_status_segment` | WIRED | Lines 528-532 |
| `fetch_claude_status` | `_derive_claude_status(summary, dismissals=dismissals, cfg=cfg)` | dismissals and cfg threaded in | WIRED | Line 2129 |
| `write_dismissals` | atomic temp + `os.replace` | copied from `write_cache_section` | WIRED | Lines 364-368 |
| `fetch_claude_status` payload | `tracked_incidents` key in both noteworthy and healthy branches | `_collect_tracked_incidents(summary)` | WIRED | Lines 2134, 2145, 2150 |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes, no regressions | `python -m pytest tests/ -q` | 671 passed, 60 skipped — matches expected baseline | PASS |
| Phase 7 test suite passes | `python -m pytest tests/test_claude_status.py -q` | 190 passed, 15 subtests passed | PASS |
| `--status-incidents` exits without reading stdin | `python claude-statusline.py --status-incidents` | Printed sanitized incident table, exited 0 | PASS |
| `--dismiss x` exits without reading stdin or printing bar | `echo '' | python claude-statusline.py --dismiss test-smoke-id` | Confirmation + refresh note, exited 0 | PASS |
| `--undismiss x` cleans up, exits 0 | `echo '' | python claude-statusline.py --undismiss test-smoke-id` | Removal confirmation, exited 0; store remains `{}` | PASS |
| Missing argument to `--dismiss` | `echo '' | python claude-statusline.py --dismiss` | Usage hint printed, exited 0, no IndexError | PASS |
| No TOML writer introduced | `grep -c "tomllib.dump|toml.*write|.write_text.*toml" claude-statusline.py` | 0 | PASS |
| No argparse introduced | `grep -c "import argparse" claude-statusline.py` | 0 | PASS |
| `_is_suppressed` definition + call site count | `grep -c "_is_suppressed" claude-statusline.py` | 6 | PASS |
| `_prune_dismissals` call site on refresh path | `grep -c "_prune_dismissals" claude-statusline.py` | 2 (definition + call) | PASS |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_print_status_incidents` | `tracked_incidents` from cache | `read_cache(_CACHE_PATH)["claude_status"]["tracked_incidents"]` | Yes — populated by `_collect_tracked_incidents(summary)` from live Statuspage feed during `fetch_claude_status` | FLOWING |
| `_derive_claude_status` | `dismissals` dict | `read_dismissals(_DISMISSALS_PATH)` (tool-owned JSON) | Yes — real on-disk store; degrades to `{}` on missing/corrupt | FLOWING |
| `_is_suppressed` | `title_capped` | `str(title)[:500]` from incident `name` field | Yes — live incident title from Statuspage feed | FLOWING |

Live smoke test of `--status-incidents` showed real live incidents (Mythos-related: "We've suspended access to Claude Mythos 5...") confirming the full fetch → cache → CLI read pipeline is active.

---

### Requirements Coverage

No formal REQ-IDs assigned to this phase (REQUIREMENTS.md has none for Phase 7; acceptance is governed by CONTEXT.md D-01..D-06). All 7 decisions verified above.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `claude-statusline.py` | 2412, 2717 | String literal "TBD" in comments | Info | Pre-existing comments in the GSD-state parser describing how the parser treats placeholder text — not Phase 7 code, not an unresolved debt marker. Not a blocker. |

No new `TBD`/`FIXME`/`XXX` markers introduced by Phase 7. No stub components, no empty implementations, no hardcoded empty data in the Phase 7 code paths.

---

### Human Verification Required

#### 1. Bar goes quiet after dismissing the live Mythos/Fable perpetual incident

**Test:** Run `python claude-statusline.py --status-incidents` to find the id of the
Mythos/Fable incident currently showing as "active". Then run:
```
python claude-statusline.py --dismiss <id>
python claude-statusline.py --refresh
```
Wait for the refresh to complete, then trigger the statusline as Claude Code normally would.

**Expected:** The Claude-status segment on the bar disappears (no indicator shown).
Running `--status-incidents` again should list the incident as "dismissed". The bar
should remain quiet until the incident id changes (new real incident) or the impact
escalates above "minor" (the dismissal baseline).

**Why human:** The full pipeline — detached `fetch_claude_status` child writing a new
cache section with `_derive_claude_status(summary, dismissals=dismissals, cfg=cfg)` that
accounts for the dismissal, then the render path reading that cache and `_claude_status_segment`
returning `None` — spans a real network call, cache TTL, and terminal ANSI render. Unit
tests cover the logic; this confirms the end-to-end wiring against the live feed and the
actual terminal output. Also confirms quiet-when-healthy is preserved (Phase 6 D-01) when
the only noteworthy item is suppressed.

---

#### 2. Escalation re-surface awareness (informational)

**Test:** No active action required. Verify that the test
`TestEscalationFixtureAndAutoPrune` passes (it does: 190 passed) and that `_is_suppressed`
in the source (lines 1686-1693) contains the `live_rank > stored_rank` re-surface logic.
Escalation cannot be triggered against the live feed on demand.

**Expected:** The unit test `test_dismissed_minor_live_major_resurfaces` passes (confirmed),
and the docstring at line 1609-1613 accurately describes the behavior. Real-world
confirmation would require observing the bar over a period where a dismissed minor incident
actually escalates.

**Why human:** Live escalation confirmation requires a real incident transition. The logic
is fully unit-tested and readable; this item is informational rather than a blocking
verification gap.

---

### Gaps Summary

No gaps found. All 7 D-01..D-06 decisions are implemented, tested, and the live smoke
tests confirm the CLI flags exit correctly, the dismissal store is clean after round-trip,
and the full test suite shows no regressions (671 passed, 60 skipped — matches expected
baseline).

Status is `human_needed` solely because confirming the bar goes quiet after dismissing
the real live Mythos/Fable incident in an actual Claude Code session cannot be done
programmatically. All automated checks passed.

---

_Verified: 2026-06-17_
_Verifier: Claude (gsd-verifier)_
