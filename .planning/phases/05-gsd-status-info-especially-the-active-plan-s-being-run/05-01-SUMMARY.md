---
phase: 05-gsd-status-info-especially-the-active-plan-s-being-run
plan: 01
subsystem: gsd-state
tags: [tdd, data-access, inference, never-raises]
dependency_graph:
  requires: [claude-statusline.py git helper layer (04-01)]
  provides: [_read_gsd_state, _infer_gsd_lifecycle, _GSD_MAX_BYTES, _GSD_HANDOFF_STALE_SECONDS]
  affects: [claude-statusline.py]
tech_stack:
  added: []
  patterns: [try/except-Exception-return-None outer guard, bounded file read, minimal hand-parsed YAML frontmatter, TDD RED/GREEN]
key_files:
  created: [tests/test_gsd_segment.py]
  modified: [claude-statusline.py]
decisions:
  - _GSD_MAX_BYTES = 65536 — 64 KiB cap per file; generous for all three .planning/ files while bounding DoS risk (T-05-01)
  - _GSD_HANDOFF_STALE_SECONDS = 3600 — 1 hour; D-05 documented staleness window; generous because executor always writes on checkpoint
  - STATE.md frontmatter hand-parsed (split on --- delimiters; walk key:value lines; coerce digit-only to int; handle nested progress: block) — no new dep, matches project's stdlib-only convention
  - lifecycle priority: blocked > verifying > executing > idle > done (D-03)
  - roadmap fallback uses regex r"-\s\[\s\]\s+(\d+(?:\.\d+)?-\d+-PLAN\.md)" to find first incomplete plan checkbox
  - plans_done/plans_total sourced from STATE.md progress block (consistent single source)
  - re imported inline inside _infer_gsd_lifecycle (already stdlib; avoids polluting module top-level with a rarely-needed import)
metrics:
  duration: "10 min"
  completed: "2026-05-29"
  tasks: 2
  files: 2
---

# Phase 05 Plan 01: GSD Data-Access + Lifecycle-Inference Layer Summary

**One-liner:** Bounded never-raising `_read_gsd_state` + pure `_infer_gsd_lifecycle` resolving HANDOFF-first/ROADMAP-fallback lifecycle state (executing/verifying/blocked/idle/done) with 28 passing unit tests.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for _read_gsd_state + _infer_gsd_lifecycle | 7f043d1 | tests/test_gsd_segment.py (+519 lines) |
| 1+2 (GREEN) | Implement _read_gsd_state + _infer_gsd_lifecycle | 21ba7c9 | claude-statusline.py (+277 lines) |

## What Was Built

### `_read_gsd_state(planning_dir: str) -> dict | None`

Reads the three `.planning/` files that the GSD segment needs:

- **HANDOFF.json** — parsed with `json.loads` (already imported)
- **STATE.md** — hand-parsed YAML frontmatter via `_parse_gsd_frontmatter`; extracts `milestone`, `status`, and the nested `progress:` block (`total_plans`, `completed_plans`, `percent`) coerced to int
- **ROADMAP.md** — raw text string (consumed by the lifecycle inferrer)

Each file is read with an explicit `_GSD_MAX_BYTES` (65536) cap. The entire body is wrapped in `try/except Exception: return None`. Returns `None` on any missing file, parse error, or OS error. Never raises (RUN-01/RUN-02).

### `_infer_gsd_lifecycle(state: dict | None) -> dict | None`

Pure function over the dict from `_read_gsd_state`. Implements the D-05 HANDOFF-first/ROADMAP-fallback decision:

- HANDOFF is "live" when `plan` is a non-null string AND timestamp is ≤ `_GSD_HANDOFF_STALE_SECONDS` (3600 s) old
- Live HANDOFF lifecycle priority: `blocked` (blockers non-empty) > `verifying` (status contains "verif") > `executing`
- Stale/null HANDOFF: scan ROADMAP for first `- [ ] NN-NN-PLAN.md` checkbox → `idle` with that plan id
- No incomplete plan checkbox → `done` with `milestone` label from STATE frontmatter

Returns `{plan_id, tasks_done, total_tasks, plans_done, plans_total, state, milestone}` with `None` for N/A fields. Never raises; returns `None` only when input is `None`.

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

- RED commit `7f043d1`: `test(05-01): add failing tests for _read_gsd_state + _infer_gsd_lifecycle (TDD RED)` — 28 tests all fail before implementation
- GREEN commit `21ba7c9`: `feat(05-01): add _read_gsd_state + _infer_gsd_lifecycle helpers (TDD GREEN)` — 28 tests all pass after implementation
- No REFACTOR commit needed — implementation was clean on first pass

## Verification

- `python -m pytest tests/test_gsd_segment.py -q` → 28 passed
- `grep -n "def _read_gsd_state\|def _infer_gsd_lifecycle\|_GSD_MAX_BYTES\|_GSD_HANDOFF_STALE_SECONDS" claude-statusline.py` → 4 symbols present
- `python -c "import ast; ast.parse(open('claude-statusline.py').read())"` → no syntax error
- `grep -n "^import \|^from " claude-statusline.py` → stdlib only + existing requests/astral; `timezone` added to existing `datetime` import (stdlib)
- Full suite: 2 pre-existing Phase 03.1 bar-style failures unchanged; no regressions introduced

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns outside the designed `.planning/` subtree, or schema changes at trust boundaries introduced. File reads are strictly under `planning_dir` using `os.path.join(planning_dir, "<fixed-name>")` — the T-05-01/T-05-02 mitigations in the threat register are implemented as designed.

## Self-Check: PASSED

- tests/test_gsd_segment.py exists: FOUND
- claude-statusline.py modified: FOUND
- Commit 7f043d1 exists: FOUND (RED)
- Commit 21ba7c9 exists: FOUND (GREEN)
- 28 tests pass: VERIFIED
