---
phase: 06-add-claude-status-onto-the-right-end-of-the-claude-usage-lin
plan: "02"
subsystem: claude-status-render-layer
tags: [render, sanitize, tdd, segment, bottom-line, ansi-security, spawn]
dependency_graph:
  requires:
    - "06-01"  # cache section contract: {fetched_at, noteworthy, severity, label, kind}
  provides:
    - _claude_status_segment (render-path builder)
    - render_bottom_line (extended: status_seg appended after weekly_seg)
    - render-path maybe_spawn_refresh call (weather-independent)
  affects:
    - render_bottom_line (appends status_seg with 3-space separator)
    - _claude_status_segment (new builder, reads "claude_status" cache section)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN per task (2 tasks, 2 RED commits, 2 GREEN commits)
    - ANSI-strip + width-bound sanitizer (VERBATIM from _weather_segment :2906-2910)
    - try/except never-crash discipline (D-10) wrapping entire builder body
    - icon_set glyph resolution (nerd/emoji) for incident vs maintenance (D-04)
    - section_within_ceiling freshness gate for cold-cache silent omit (D-01)
    - render-path maybe_spawn_refresh call guarded in try/except
key_files:
  created: []
  modified:
    - claude-statusline.py (_claude_status_segment + render_bottom_line extension)
    - tests/test_claude_status.py (34 new tests: 23 builder + 11 E2E/integration)
decisions:
  - "_CLAUDE_STATUS_LABEL_MAXLEN=50: tighter than alert-override 64 (status titles are short; trailing position on already-busy bottom line)"
  - "render-path spawn placed in render_bottom_line (not main) so it is reachable regardless of weather state"
  - "Emoji fallback for incident: U+1F534 (red circle); maintenance: U+1F527 (wrench) — visually distinct (D-04)"
  - "kind or 'incident' used as hollow-glyph fallback text (WR-02): kind is already a trusted string, not from cache label"
metrics:
  duration_minutes: 7
  completed_date: "2026-06-16T20:51:15Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 2
---

# Phase 06 Plan 02: Claude Status Render Layer Summary

Claude service-health render path: `_claude_status_segment` builder that reads the Plan-01 cache section, applies the ANSI-sanitization security control (T-06-04), resolves severity color + icon_set glyph (D-03/D-04), and appends to `render_bottom_line` after the weekly segment with the 3-space separator (D-06). Includes render-path `maybe_spawn_refresh` trigger so status cache stays fresh even when weather is disabled.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for _claude_status_segment builder | 9c50ce2 | tests/test_claude_status.py |
| 1 (GREEN) | _claude_status_segment render builder | de27bdd | claude-statusline.py |
| 2 (RED) | Failing tests for render_bottom_line integration + spawn path | 74418ac | tests/test_claude_status.py |
| 2 (GREEN) | render_bottom_line append + render-path spawn trigger | 6567a4a | claude-statusline.py |

## Implementation Notes

### `_claude_status_segment(data, cfg) -> str | None`

Located after `_rate_segment` at line ~2968 in `claude-statusline.py`. Full behavior:

1. `show_claude_status=False` → `None`
2. `read_cache(_CACHE_PATH)` → `sec = cache.get("claude_status", {})` — if `section_within_ceiling` fails → `None` (cold-cache silent, D-01)
3. `noteworthy=False` → `None` (quiet-when-healthy, D-01)
4. `kind=="maintenance"` → wrench glyph (`_NF_CLAUDE_MAINT` / `🔧`) + `DIM` color (D-04)
5. Else → exclamation glyph (`_NF_CLAUDE_INCIDENT` / `🔴`) + `_claude_status_color(severity)` (D-03)
6. Sanitize label VERBATIM: `"".join(ch for ch in str(label) if ch == " " or (ch.isprintable() and ch != "\x1b"))[:50].strip()` — then `kind or "incident"` fallback when empty (WR-02)
7. `f"{color}{glyph} {safe_label}{RESET}"` — body in `try/except → None` (D-10)

### `render_bottom_line` extension

- Added `read_cache + maybe_spawn_refresh` call inside `try/except` before `_claude_status_segment` to keep status cache fresh independent of weather.
- `status_seg = _claude_status_segment(data, cfg)` — appended to `parts` list after `weekly_seg`.
- `parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]` — the existing `"   ".join(parts)` gives the 3-space D-06 separator automatically.
- None-filter handles all silent-omit cases; no extra guarding needed.

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| TestClaudeStatusSegmentBuilder (new, Task 1) | 23 | all pass |
| TestRenderBottomLineStatusIntegration (new, Task 2) | 9 | all pass |
| TestRenderBottomLineSpawnPath (new, Task 2) | 2 | all pass |
| Pre-existing test_claude_status.py (Plan 01) | 43 | all pass |
| test_bottom_line.py (regression check) | 49 | all pass |
| Full suite | 556 passed, 60 skipped | pass |

## Deviations from Plan

None — plan executed exactly as written. All behavior variants (healthy/cold/disabled/incident/degraded/maintenance/ANSI-injection/hollow-glyph) are covered. The two pre-existing E2E failures (`test_git_segment`, `test_gsd_segment`) are worktree-environment issues documented in Plan 01 SUMMARY and unchanged by this plan.

## Known Stubs

None. The render builder reads the Plan-01 cache data faithfully and outputs a real segment. No placeholder text or fake values introduced.

## Threat Surface Scan

No new threat surface beyond the plan's `<threat_model>`:

| Flag | File | Description |
|------|------|-------------|
| T-06-04 (MITIGATED) | claude-statusline.py `_claude_status_segment` | RAW cache label sanitized VERBATIM via ANSI-strip + `[:50]` width-bound + hollow-glyph fallback before reaching terminal. Test `test_malicious_ansi_title_no_raw_escape_in_label` asserts no raw `\x1b` in label core. |
| T-06-05 (MITIGATED) | claude-statusline.py `_claude_status_segment` | `try/except → None` wraps entire body; `section_within_ceiling` rejects missing/bad `fetched_at`; non-dict section caught early. |
| T-06-06 (MITIGATED) | claude-statusline.py `render_bottom_line` | `maybe_spawn_refresh` is fire-and-forget (detached child, never `.wait()`); render-path call wrapped in `try/except pass` so spawn failure never blocks render. |
| T-06-07 (MITIGATED) | claude-statusline.py `_claude_status_segment` | `_CLAUDE_STATUS_LABEL_MAXLEN=50` named constant; `test_malicious_ansi_title_output_is_bounded` asserts stripped output < 200 chars. |

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| claude-statusline.py | FOUND |
| tests/test_claude_status.py | FOUND |
| `def _claude_status_segment(` count == 1 | PASSED (grep -c returns 1) |
| `cache.get("claude_status")` count >= 1 | PASSED (returns 2) |
| `_claude_status_segment(data, cfg)` in render_bottom_line | PASSED (grep -c returns 1) |
| `status_seg` in claude-statusline.py | PASSED (grep -c returns 4) |
| Commit 9c50ce2 (RED Task 1) | FOUND |
| Commit de27bdd (GREEN Task 1) | FOUND |
| Commit 74418ac (RED Task 2) | FOUND |
| Commit 6567a4a (GREEN Task 2) | FOUND |
| tests/test_claude_status.py (77 tests) | 77 passed |
| tests/test_bottom_line.py (49 tests) | 49 passed |
| Full suite (556 passed, 60 skipped) | PASS |
