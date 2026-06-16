---
phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
verified: 2026-06-16T00:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
human_verification_result: confirmed by user 2026-06-16 ("Works" — nerd-font glyphs render correctly; quiet-when-healthy confirmed live)
human_verification:
  - test: "Pipe a real session JSON with a warm incident cache present and observe the bottom line in Claude Code's terminal"
    expected: "Severity-colored glyph (exclamation for incident, wrench for maintenance) plus the sanitized incident title appears at the right end of the bottom line, separated from the weekly segment by three spaces"
    why_human: "Cannot drive the full interactive Claude Code terminal environment from a test runner; render_bottom_line produces the correct output in unit tests but actual font rendering of the nerd-font glyphs requires visual inspection"
  - test: "With all tracked components operational and cache populated (healthy fetch), confirm the bottom line is unchanged from the no-status baseline"
    expected: "No extra glyph or text appears; the bar is identical to what Phase 5 produced"
    why_human: "Quiet-when-healthy is tested in code but the terminal visual experience (absence of spurious UI) requires human confirmation"
---

# Phase 06: Claude Status Segment Verification Report

**Phase Goal:** A quiet-when-healthy Claude service-health indicator at the right end of the bottom line (after the calendar weekly segment, 3-space separator) that triggers ONLY on the tracked components this user runs — Claude Code, claude.ai, Claude Cowork (D-02, deriving from the components' own statuses + scoped incident/maintenance refs, never the page-wide rollup) — surfacing unresolved incidents as a severity-colored glyph + ANSI-sanitized incident title (with a component+state fallback when no title) and scheduled-maintenance windows as a distinct neutral glyph (D-03/D-04), all on the existing detached ~5-minute sectioned-cache + render-never-blocks machinery, omitting silently (return None) when healthy, cold, or on any parse/network error (D-01/D-05/D-06).

**Verified:** 2026-06-16
**Status:** passed (human visual items confirmed by user 2026-06-16)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | When all tracked components are operational and there is no incident or maintenance touching them, derivation yields None (D-01) | VERIFIED | `_derive_claude_status(status_operational.json)` returns `None`; test `test_operational_returns_none` passes; behavioral spot-check confirmed |
| 2  | An unresolved incident scoped only to an untracked component does NOT produce a trigger (D-02) | VERIFIED | `_derive_claude_status(status_incident_untracked.json)` returns `None`; test `test_incident_untracked_returns_none` passes; `status.indicator` rollup is never consulted (only in docstring as "do not use") |
| 3  | An unresolved incident touching a tracked component produces severity from the feed + the incident title as label (D-03) | VERIFIED | `_derive_claude_status(status_incident_tracked.json)` returns `{"severity":"minor","label":"Elevated error rates for Claude Code tool calls","kind":"incident"}`; test `test_incident_tracked_returns_dict_with_label` asserts label equality |
| 4  | A tracked component degraded with no associated incident title produces a component+state label (D-03 fallback) | VERIFIED | `_derive_claude_status(status_degraded_no_title.json)` returns `{"severity":"minor","label":"claude.ai: degraded","kind":"degraded"}`; test `test_degraded_no_title_returns_component_state_label` passes |
| 5  | An active or upcoming scheduled-maintenance window touching a tracked component produces a maintenance trigger with a DISTINCT neutral glyph, not an incident glyph (D-04) | VERIFIED | `_derive_claude_status(status_maintenance.json)` returns `{"severity":"maintenance","kind":"maintenance",...}`; `_claude_status_segment` branches on `kind=="maintenance" or severity=="maintenance"` (WR-01 fix at line 3051) → `_NF_CLAUDE_MAINT` (wrench); tests `test_maintenance_returns_maintenance_kind` and `test_maintenance_uses_distinct_wrench_glyph` pass |
| 6  | The background refresh fetches status.claude.com summary.json and writes a claude_status cache section on a ~5-minute TTL, never crashing the child (D-05) | VERIFIED | `fetch_claude_status` at line 1561 calls `_nws_get` with hardcoded URL, calls `write_cache_section(_CACHE_PATH,"claude_status",...)` at line 1631; `run_refresh` at line 1678 calls `fetch_claude_status(cfg)` under the single O_CREAT|O_EXCL lock; `maybe_spawn_refresh` at line 1720 adds `status_stale` to the spawn trigger; DEFAULTS `cache.status_ttl=300`; whole body in `try/except: pass`; all fetch tests pass |
| 7  | The render path never blocks on the network — `_claude_status_segment` does only cache reads + string work; `maybe_spawn_refresh` is fire-and-forget (D-05) | VERIFIED | `_claude_status_segment` body contains no network calls; `maybe_spawn_refresh` call in `render_bottom_line` (line 3182) is wrapped in `try/except: pass`; status fetch runs only in detached `--refresh` child |
| 8  | Untrusted incident/maintenance titles are ANSI/control-char sanitized and width-bounded before terminal output; no raw ESC byte reaches the terminal (D-03, T-06-04) | VERIFIED | Sanitizer at lines 3068-3071: `"".join(ch for ch in str(label) if ch == " " or (ch.isprintable() and ch != "\x1b"))[:50].strip()`; spot-check confirms `\x1b[31mRED\x1b[0m` → `[31mRED[0m` (ESC stripped); test `test_malicious_ansi_title_no_raw_escape_in_label` asserts no `\x1b` in label portion; `_CLAUDE_STATUS_LABEL_MAXLEN=50` enforced |
| 9  | Status segment is placed at the right end of the bottom line after the weekly segment with the 3-space inter-segment separator (D-06) | VERIFIED | `render_bottom_line` at line 3187: `parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]` → `"   ".join(parts)`; test `test_incident_comes_after_weekly_segment` asserts calendar glyph index < status label index; test `test_incident_cache_has_three_space_separator_before_status` asserts `"   "` in output |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-statusline.py` | `def fetch_claude_status(`, `_derive_claude_status`, `_claude_status_color`, `_NF_CLAUDE_*`, `_claude_status_segment`, `run_refresh` + `maybe_spawn_refresh` wiring | VERIFIED | All 5 functions defined (grep -c returns 1 each); constants at lines 482-485; DEFAULTS at lines 157-187; wiring at lines 1678, 1720 |
| `tests/test_claude_status.py` | 85 tests covering data layer + render layer | VERIFIED | 85 tests, 15 subtests pass in 0.19s; covers all D-01..D-06 behaviors, ANSI injection, WR-01 under_maintenance fixture, WR-02 spawn gating, WR-03 _REQUESTS_OK guard |
| `tests/fixtures/status_operational.json` | All operational, empty incidents/maintenances | VERIFIED | File exists; `_derive_claude_status` returns None against it |
| `tests/fixtures/status_incident_tracked.json` | Incident touching Claude Code | VERIFIED | File exists; derivation returns incident label |
| `tests/fixtures/status_incident_untracked.json` | Incident touching only Claude API | VERIFIED | File exists; derivation returns None |
| `tests/fixtures/status_degraded_no_title.json` | claude.ai degraded, no incident | VERIFIED | File exists; derivation returns `claude.ai: degraded` fallback |
| `tests/fixtures/status_maintenance.json` | in_progress maintenance touching Claude Cowork | VERIFIED | File exists; derivation returns `kind="maintenance"` |
| `tests/fixtures/status_malicious_title.json` | Incident with raw ANSI escapes in title | VERIFIED | File exists; sanitization E2E test passes |
| `tests/fixtures/status_component_under_maintenance_no_event.json` | Under-maintenance component, no scheduled_maintenances entry (WR-01) | VERIFIED | File exists; derivation returns `severity="maintenance"`, render uses wrench glyph |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_refresh` | `fetch_claude_status` | call at line 1678 | VERIFIED | `fetch_claude_status(cfg)` present under the single O_CREAT|O_EXCL lock; `grep -c "fetch_claude_status(cfg)"` = 2 (definition context + call site) |
| `fetch_claude_status` | `claude_status` cache section | `write_cache_section(_CACHE_PATH, "claude_status", payload, now)` at line 1631 | VERIFIED | Call present; tests confirm section written with correct keys |
| `_claude_status_segment` | `claude_status` cache section | `cache.get("claude_status", {})` at line 3027 | VERIFIED | Pattern present; `grep -c cache.get.*claude_status` = 2 |
| `render_bottom_line` | `_claude_status_segment` | `status_seg = _claude_status_segment(data, cfg)` at line 3185 | VERIFIED | Call present; `grep -c "_claude_status_segment(data, cfg)"` = 1 |
| `render_bottom_line` | `maybe_spawn_refresh` | call at line 3182 inside `try/except` | VERIFIED | Spawn reachable independent of `_WEATHER_OK` guard; test `test_maybe_spawn_refresh_called_when_weather_disabled` passes |
| `maybe_spawn_refresh` | `status_stale` trigger | `status_section = cache.get("claude_status", {})` + `status_stale = not section_is_fresh(...)` at lines 1716-1720 | VERIFIED | Status staleness independently triggers refresh; `grep -c status_stale` >= 1 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `_claude_status_segment` | `sec` (claude_status cache section) | `read_cache(_CACHE_PATH)` → `cache.get("claude_status", {})` | Yes — populated by `fetch_claude_status` which calls `_derive_claude_status(summary)` from live or fixture JSON; healthy refresh writes `{noteworthy:False}` to prevent hot-respawn loop | FLOWING |
| `_derive_claude_status` | `summary` | `_nws_get("https://status.claude.com/api/v2/summary.json", ua, accept=None)` | Yes — live endpoint or CLAUDE_STATUSLINE_FAKE_STATUS fixture file | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command / Check | Result | Status |
|----------|----------------|--------|--------|
| D-01: operational fixture → None | `m._derive_claude_status(status_operational.json)` → `None` | `None` | PASS |
| D-02: untracked fixture → None | `m._derive_claude_status(status_incident_untracked.json)` → `None` | `None` | PASS |
| D-03: tracked incident → label | `m._derive_claude_status(status_incident_tracked.json).label` | `'Elevated error rates for Claude Code tool calls'` | PASS |
| D-03 fallback: degraded → component+state | `m._derive_claude_status(status_degraded_no_title.json).label` | `'claude.ai: degraded'` | PASS |
| D-04: maintenance kind | `m._derive_claude_status(status_maintenance.json).kind` | `'maintenance'` | PASS |
| ANSI sanitization | `\x1b[31mRED\x1b[0m` through sanitizer | `[31mRED[0m` (no ESC byte) | PASS |
| D-06 placement | `test_incident_comes_after_weekly_segment` | calendar glyph idx < label idx | PASS |
| Full test suite | `python3 -m pytest tests/ -q` | 566 passed, 60 skipped, 269 subtests | PASS |
| D-02: `status.indicator` not used | `inspect.getsource(_derive_claude_status)` | Only in docstring comment; never in logic path | PASS |

### Probe Execution

No probe scripts declared or present for this phase.

### Requirements Coverage

Phase 6 has no REQUIREMENTS.md IDs. Verified against CONTEXT decisions D-01 through D-06:

| Decision | Description | Status | Evidence |
|----------|-------------|--------|----------|
| D-01 | Quiet when healthy — returns None when all operational, no incidents/maintenance | SATISFIED | `_derive_claude_status` Rule 4 returns `None`; `_claude_status_segment` returns `None` when `noteworthy=False` |
| D-02 | Filter to tracked components only (Claude Code, claude.ai, Claude Cowork); never use page-wide rollup | SATISFIED | `_CLAUDE_TRACKED_COMPONENTS` frozenset at line 1274; `_derive_claude_status` never reads `status.indicator`; untracked fixture verified returns None |
| D-03 | Severity-colored glyph + ANSI-sanitized incident title; component+state fallback when no title | SATISFIED | `_claude_status_segment` steps 5-7; `_CLAUDE_STATUS_LABEL_MAXLEN=50`; sanitizer strips ESC+control chars; hollow-glyph fallback when empty |
| D-04 | Incidents AND maintenance; maintenance uses DISTINCT neutral glyph | SATISFIED | Rule 2 handles scheduled/in_progress maintenance; `_NF_CLAUDE_MAINT` (wrench) ≠ `_NF_CLAUDE_INCIDENT` (exclamation); WR-01 fix: branch on `kind=="maintenance" or severity=="maintenance"` at line 3051 so `under_maintenance` component without event also gets wrench |
| D-05 | ~5-minute cache TTL; detached refresh writes cache; render reads cache and never blocks | SATISFIED | `status_ttl=300` in DEFAULTS; `fetch_claude_status` runs only in `--refresh` child; `maybe_spawn_refresh` fire-and-forget; render-path spawn in `render_bottom_line` wrapped in `try/except: pass` |
| D-06 | Placement at right end of bottom line after weekly segment; 3-space separator | SATISFIED | `parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]` → `"   ".join(parts)` |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | No TBD/FIXME/XXX in new code; no placeholder returns; no hardcoded empty collections on render path | — | — |

Scan checked: `_derive_claude_status`, `fetch_claude_status`, `_claude_status_color`, `_claude_status_segment`, `render_bottom_line` additions. All empty-return paths (`return None`) are guarded by legitimate early-exit conditions (toggle=false, cold cache, noteworthy=False, exception), not placeholder stubs.

### Human Verification Required

#### 1. Active incident visual rendering in Claude Code terminal

**Test:** With a warm `claude_status` cache section containing `noteworthy=True, severity="minor", label="<some title>", kind="incident"` (set via `CLAUDE_STATUSLINE_FAKE_STATUS`), pipe a real session JSON to `claude-statusline.py` and observe the terminal output.

**Expected:** The bottom line ends with `   ` (3-space gap) then a yellow-colored exclamation glyph (nerd font U+F06A) followed by the sanitized incident title text; the title is within 50 characters; no raw ESC bytes from the title are visible.

**Why human:** Nerd-font glyph rendering requires visual inspection in a real terminal with the font installed. The unit tests mock the cache and verify the string output, but can't confirm the glyph appears as intended vs. a fallback box character.

#### 2. Quiet-when-healthy: confirm no status segment on healthy cache

**Test:** Ensure the `claude_status` cache section is populated with `noteworthy=False` (healthy state), then observe the bottom line.

**Expected:** The bottom line is visually identical to Phase 5's output — no extra glyph or text at the right end.

**Why human:** Terminal visual confirmation that no spurious element appears when all systems are operational; the omission-when-healthy property is tested in code (test confirms output matches cold-cache baseline) but a human should verify the live terminal experience is clean.

### Gaps Summary

No gaps. All 9 must-have truths are verified against actual codebase evidence. The two human verification items are visual/terminal concerns that cannot be assessed programmatically.

---

_Verified: 2026-06-16_
_Verifier: Claude (gsd-verifier)_
