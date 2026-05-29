---
phase: 05-gsd-status-info
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - claude-statusline.py
  - tests/test_gsd_segment.py
  - tests/test_nerd_icons.py
  - tests/test_skeleton_render.py
  - tests/test_bootstrap_degradation.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the new GSD-status segment added in Phase 5: `_read_gsd_state`, `_parse_gsd_frontmatter`, `_infer_gsd_lifecycle`, `_gsd_segment`, the `_NF_GSD_*` glyph constants, the `_GSD_MAX_BYTES` / `_GSD_HANDOFF_STALE_SECONDS` constants, the `display.show_gsd` default, and the `render_top_line` wiring.

The never-raise discipline is solid: every helper is wrapped in `try/except Exception → None`, all reads are byte-capped via `_GSD_MAX_BYTES`, paths are built only from `os.path.join(project_dir, "<fixed-name>")` with no attacker-controlled components, and naive-timestamp / partial-dict edge cases degrade to `idle`/omission rather than crashing (verified by direct execution). The 48-test GSD suite passes.

However there is one **BLOCKER**: the roadmap-fallback "done" detection is keyed on a `- [ ] NN-NN-PLAN.md` regex that does not match this repo's actual `ROADMAP.md` format. Against the real `.planning/ROADMAP.md`, a stale HANDOFF causes the segment to report `state: done` / milestone complete even though phases 03.1 and 05 are still open (verified empirically). The test suite hides this because its fixtures use a synthetic roadmap that *does* contain `- [ ] NN-NN-PLAN.md` lines.

Secondary concerns: untrusted free-text fields (`plan`, `milestone`) are rendered into the line without sanitization (violates the project's stated ANSI-injection / structured-fields-only contract), and the test fixtures diverge from the real artifact format.

## Critical Issues

### CR-01: Roadmap-fallback regex never matches the real ROADMAP.md → false "milestone done"

**File:** `claude-statusline.py:1596-1626`
**Issue:**
`_infer_gsd_lifecycle`'s fallback path (taken whenever HANDOFF is stale/null) finds the "next incomplete plan" with:

```python
_PLAN_CHECKBOX = _re.compile(r"-\s\[\s\]\s+(\d+(?:\.\d+)?-\d+-PLAN\.md)")
```

If no `- [ ] NN-NN-PLAN.md` line is found, the function falls through to `state: "done"` and emits the milestone label.

The real `.planning/ROADMAP.md` in this repo lists incomplete work as **phase headers** (`- [ ] **Phase 03.1: ...**`) and as **`- [ ] TBD`** plan placeholders — there is **no** unchecked `- [ ] NN-NN-PLAN.md` line anywhere (`grep -nE "\- \[ \].*PLAN\.md" .planning/ROADMAP.md` → no matches). Verified empirically: with a stale HANDOFF, `_infer_gsd_lifecycle` returns `state=done, milestone=v1.0` even though phases 03.1 and 05 are open. The bar would announce the v1.0 milestone as complete when it is not — a correctness/data-integrity defect at the heart of this feature ("the active plan being run").

The unit tests pass only because their fixture (`_ROADMAP_WITH_INCOMPLETE`) is hand-written to contain `- [ ] 05-01-PLAN.md` lines that the real roadmap does not use.

**Fix:** Make the fallback recognize the actual incomplete markers and stop treating "no unchecked PLAN.md line" as proof of completion. Either broaden the regex to also match unchecked phase headers / `TBD` plan rows, or derive completeness authoritatively from STATE.md `progress` (which is already parsed):

```python
# Prefer STATE progress as the source of truth for completeness.
if plans_done is not None and plans_total is not None and plans_done < plans_total:
    # milestone NOT complete — fall back to idle even if no PLAN.md checkbox matched
    return {
        "plan_id":     next_plan_id,   # may be None; render a generic "idle" if so
        "tasks_done":  None, "total_tasks": None,
        "plans_done":  plans_done, "plans_total": plans_total,
        "state":       "idle", "milestone": None,
    }
```

Only return `"done"` when the roadmap and/or `progress.completed_plans == progress.total_plans` actually confirm completion. Add a test fixture that mirrors the real ROADMAP.md format (phase-level `- [ ]` + `TBD` placeholders, no unchecked `PLAN.md`) and assert it does NOT resolve to `done`.

## Warnings

### WR-01: Untrusted `plan` / `milestone` file text rendered into the line without sanitization

**File:** `claude-statusline.py:1584-1585` (plan_id), `1722-1723` (milestone), consumed at `1713`, `1716`, `1729`, `1731`, `1739`
**Issue:**
The project contract (CLAUDE.md / PROJECT.md) requires "only structured fields rendered into the line, never raw untrusted file text" and explicitly calls out ANSI-injection. The live-HANDOFF path renders `handoff.get("plan")` verbatim, and the done path renders `state_fm.get("milestone")` verbatim. Both originate from on-disk files (`HANDOFF.json`, `STATE.md`) that the statusline treats as untrusted input. Verified: a `plan` value of `"\033[5;31mPWNED...\033[0m" + "X"*200` flows unmodified through `_infer_gsd_lifecycle` into `_gsd_segment`'s interior. This can inject ANSI escapes (blink/color/cursor moves) and blow the segment width unbounded, corrupting the bar. `plan_id` from the roadmap-fallback path is safe (constrained by the regex), but the live-HANDOFF and milestone paths are not.

**Fix:** Sanitize/clamp the two free-text fields before rendering — strip control characters (esp. `\x1b`) and truncate to a sane width, consistent with how structured fields elsewhere are constrained:

```python
def _sanitize_label(s, maxlen=24):
    s = "".join(ch for ch in str(s) if ch == " " or (ch.isprintable() and ch != "\x1b"))
    return s[:maxlen]
# apply to handoff_plan before returning plan_id, and to milestone_label
```

### WR-02: `_infer_gsd_lifecycle` returns "done" with `plan_id=None` whenever roadmap parsing fails

**File:** `claude-statusline.py:1617-1626`
**Issue:**
A `roadmap` value of `""` (empty/unreadable file content that still parsed as a string) or any roadmap whose format the regex doesn't understand produces `state: "done"`. This conflates three distinct conditions — "milestone genuinely complete", "roadmap unparseable", and "roadmap uses an unexpected format" — into the single most-misleading outcome (claiming completion). This is the same root cause as CR-01 but is called out separately as the general design smell: "done" is the fall-through default rather than a positively-confirmed state.

**Fix:** Treat an empty/unrecognized roadmap as `idle` (or omit the segment) rather than `done`. Only emit `done` when completeness is positively confirmed (see CR-01 fix using STATE `progress`).

### WR-03: `tasks_done` clamp does not guard a zero/negative `total_tasks`

**File:** `claude-statusline.py:1580-1582`
**Issue:**
`tasks_done = min(len(completed_tasks), total_tasks)`. If a malformed HANDOFF supplies `total_tasks: 0` or a negative value (it is coerced via `int()` but not range-checked), `tasks_done` becomes `0` or negative, and the render produces nonsensical progress like `05-02 -1/-1`. It will not crash, but it displays garbage instead of degrading to "no progress shown".

**Fix:** Clamp `total_tasks` to a sensible floor and drop the progress fragment when invalid:

```python
if total_tasks is not None and total_tasks <= 0:
    total_tasks = None        # treat as "no task count"
tasks_done = max(0, len(completed_tasks))
if total_tasks is not None:
    tasks_done = min(tasks_done, total_tasks)
```

### WR-04: Test fixtures diverge from the real artifact format, masking CR-01

**File:** `tests/test_gsd_segment.py:141-193` (`_ROADMAP_WITH_INCOMPLETE`, `_ROADMAP_ALL_COMPLETE`)
**Issue:**
Both roadmap fixtures use `- [ ] 05-01-PLAN.md` / `- [x] 05-01-PLAN.md` lines. The real `.planning/ROADMAP.md` never marks plans incomplete with a `PLAN.md` filename — incomplete work appears as phase headers and `TBD` rows. Because the fixtures don't reflect the production format, the entire fallback path is tested against an input shape the code will never actually see in this repo, giving false confidence (all 48 tests green while the real behavior is broken — see CR-01).

**Fix:** Add at least one fixture copied from the real ROADMAP.md structure (phase-level `- [ ]`, `- [ ] TBD` plan placeholders, all `PLAN.md` lines checked) and assert the inferred state is `idle`/omitted — not `done` — when the milestone is incomplete. This test should fail today and pass after CR-01 is fixed.

## Info

### IN-01: `import re` performed inside the function on every stale/fallback render

**File:** `claude-statusline.py:1596`
**Issue:**
`import re as _re` and the `re.compile(...)` of `_PLAN_CHECKBOX` run on every fallback invocation. `import` of an already-loaded module is cheap, but the pattern is recompiled each call. Other modules in this file (`json`, `os`, `datetime`) are imported at top level and constants are module-level.

**Fix:** Hoist `_PLAN_CHECKBOX = re.compile(...)` to module scope alongside the other GSD constants and use the top-level `import` already present elsewhere.

### IN-02: `_parse_gsd_frontmatter` misclassifies scalar values that end in a colon

**File:** `claude-statusline.py:1474`
**Issue:**
`if v == "" or v.endswith(":")` starts a nested mapping. A legitimate scalar whose value ends in `:` (e.g. `stopped_at: see step 2:`) would be misread as a mapping key and dropped. None of the keys the GSD segment consumes (`milestone`, `progress.*`) are affected, so this is cosmetic for now, but it is a latent parser fragility.

**Fix:** Only treat a line as a mapping header when the value is empty (`v == ""`); rely on the next line's two-space indent to confirm nesting, rather than the `endswith(":")` heuristic.

### IN-03: Dead/duplicate `project_dir` resolution pattern differs subtly between segments

**File:** `claude-statusline.py:1657-1658` vs `1864`
**Issue:**
`_gsd_segment` guards `data.get("workspace")` with an `isinstance` check before `.get("project_dir")`, while `_project_segment` (line 1864) calls `data.get("workspace", {}).get("project_dir", "")` without the `isinstance` guard — so `_project_segment` would raise (and be swallowed) if `workspace` were a non-dict, while `_gsd_segment` handles it cleanly. The inconsistency is harmless (both end up returning `None`) but the differing patterns invite confusion.

**Fix:** Standardize on the `isinstance`-guarded `workspace` access used in `_gsd_segment`/`_git_segment` across all segment builders.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
