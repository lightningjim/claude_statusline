#!/usr/bin/env python3
"""
Tests for Phase 05 Plan 01: GSD data-access + lifecycle-inference layer.

Covers:
  - _read_gsd_state: bounded never-raising reader for HANDOFF.json + STATE.md
    frontmatter + ROADMAP.md
  - _infer_gsd_lifecycle: pure HANDOFF-first/roadmap-fallback resolver producing
    plan id, task progress, plan-of-total, and lifecycle state
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# NOTE: timestamps below are fixed instants for readability. Tests that need a
# LIVE handoff must restamp to now() at call time (see TestGsdSegmentBuilder._call
# and TestInferGsdLifecycle._make_live_state). Do not rely on these values being
# within the _GSD_HANDOFF_STALE_SECONDS window at runtime.

_VALID_HANDOFF = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "source": "auto-postool",
    "partial": False,
    "phase": "05",
    "phase_name": "gsd-status-info",
    "phase_dir": None,
    "plan": "05-02",
    "task": "Implement _gsd_segment",
    "total_tasks": 3,
    "status": "executing",
    "completed_tasks": ["task1", "task2"],
    "remaining_tasks": ["Implement _gsd_segment"],
    "blockers": [],
    "human_actions_pending": [],
    "decisions": [],
    "uncommitted_files": [],
    "next_action": None,
    "context_notes": "",
}

_NULL_HANDOFF = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "source": "auto-postool",
    "partial": True,
    "phase": None,
    "phase_name": None,
    "phase_dir": None,
    "plan": None,
    "task": None,
    "total_tasks": None,
    "status": "auto-checkpoint",
    "completed_tasks": [],
    "remaining_tasks": [],
    "blockers": [],
    "human_actions_pending": [],
    "decisions": [],
    "uncommitted_files": [],
    "next_action": None,
    "context_notes": "",
}

_BLOCKED_HANDOFF = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "source": "auto-postool",
    "partial": False,
    "phase": "05",
    "phase_name": "gsd-status-info",
    "phase_dir": None,
    "plan": "05-01",
    "task": "Some task",
    "total_tasks": 2,
    "status": "blocked",
    "completed_tasks": ["task1"],
    "remaining_tasks": ["Some task"],
    "blockers": ["waiting on external review"],
    "human_actions_pending": [],
    "decisions": [],
    "uncommitted_files": [],
    "next_action": None,
    "context_notes": "",
}

_VERIFYING_HANDOFF = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "source": "auto-postool",
    "partial": False,
    "phase": "05",
    "phase_name": "gsd-status-info",
    "phase_dir": None,
    "plan": "05-01",
    "task": "Some task",
    "total_tasks": 2,
    "status": "verifying",
    "completed_tasks": ["task1"],
    "remaining_tasks": ["Some task"],
    "blockers": [],
    "human_actions_pending": [],
    "decisions": [],
    "uncommitted_files": [],
    "next_action": None,
    "context_notes": "",
}

_VALID_STATE_MD = """\
---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 5 context gathered
last_updated: "2026-05-29T19:43:04.863Z"
progress:
  total_phases: 7
  completed_phases: 5
  total_plans: 15
  completed_plans: 13
  percent: 71
---

# Project State
"""

_ROADMAP_WITH_INCOMPLETE = """\
- [x] **Phase 4: git info** (completed 2026-05-29)
- [ ] **Phase 5: GSD status info**

### Phase 4: git info

Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Git helper layer

**Wave 2**

- [x] 04-02-PLAN.md — _git_segment builder

### Phase 5: GSD status info

Plans:
**Wave 1**

- [ ] 05-01-PLAN.md — GSD data-access layer

**Wave 2**

- [ ] 05-02-PLAN.md — _gsd_segment builder
"""

_ROADMAP_ALL_COMPLETE = """\
- [x] **Phase 4: git info** (completed 2026-05-29)
- [x] **Phase 5: GSD status info** (completed 2026-05-29)

### Phase 4: git info

Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Git helper layer

**Wave 2**

- [x] 04-02-PLAN.md — _git_segment builder

### Phase 5: GSD status info

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — GSD data-access layer

**Wave 2**

- [x] 05-02-PLAN.md — _gsd_segment builder
"""


# ---------------------------------------------------------------------------
# Real-ROADMAP.md-format fixtures (WR-04): incomplete work appears as phase
# headers ("- [ ] **Phase 03.1: ...**") and "- [ ] TBD (run ...)" placeholders,
# while completed plans are "- [x] NN-MM-PLAN.md".  There is NO unchecked
# "- [ ] NN-MM-PLAN.md" line — the shape the synthetic fixtures used.  These
# fixtures fail against the pre-CR-01 code (which falsely reported "done") and
# pass after the fix (idle + next-incomplete identifier).
# ---------------------------------------------------------------------------

_ROADMAP_REAL_INCOMPLETE = """\
- [x] **Phase 3: Presets** (completed 2026-05-29)
- [ ] **Phase 03.1: Resolve default bar gradient vs shade test drift (INSERTED)**
- [x] **Phase 4: git info** (completed 2026-05-29)
- [x] **Phase 5: GSD status info** (completed 2026-05-29)

### Phase 03.1: Resolve default bar gradient vs shade test drift (INSERTED)

**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 03.1 to break down)

### Phase 4: git info

Plans:
- [x] 04-01-PLAN.md — Git helper layer
- [x] 04-02-PLAN.md — _git_segment builder

### Phase 5: GSD status info

Plans:
- [x] 05-01-PLAN.md — GSD data-access layer
- [x] 05-02-PLAN.md — _gsd_segment builder
"""

# STATE progress with completed_phases < total_phases → milestone NOT complete.
_STATE_PROGRESS_INCOMPLETE = {
    "total_phases": 7,
    "completed_phases": 6,
    "total_plans": 15,
    "completed_plans": 15,
    "percent": 86,
}

# Real-format roadmap where every phase header is checked (nothing incomplete).
_ROADMAP_REAL_ALL_COMPLETE = """\
- [x] **Phase 3: Presets** (completed 2026-05-29)
- [x] **Phase 03.1: Resolve default bar gradient vs shade test drift (INSERTED)** (done)
- [x] **Phase 4: git info** (completed 2026-05-29)
- [x] **Phase 5: GSD status info** (completed 2026-05-29)

### Phase 5: GSD status info

Plans:
- [x] 05-01-PLAN.md — GSD data-access layer
- [x] 05-02-PLAN.md — _gsd_segment builder
"""

# STATE progress with completed_phases == total_phases AND plans complete →
# milestone IS complete.
_STATE_PROGRESS_COMPLETE = {
    "total_phases": 7,
    "completed_phases": 7,
    "total_plans": 15,
    "completed_plans": 15,
    "percent": 100,
}


def _write_planning_dir(tmpdir, handoff=None, state_md=None, roadmap=None):
    """Write fixture files to tmpdir and return it as a planning_dir path."""
    if handoff is not None:
        with open(os.path.join(tmpdir, "HANDOFF.json"), "w") as f:
            json.dump(handoff, f)
    if state_md is not None:
        with open(os.path.join(tmpdir, "STATE.md"), "w") as f:
            f.write(state_md)
    if roadmap is not None:
        with open(os.path.join(tmpdir, "ROADMAP.md"), "w") as f:
            f.write(roadmap)
    return tmpdir


# ---------------------------------------------------------------------------
# _read_gsd_state tests
# ---------------------------------------------------------------------------

class TestReadGsdState(unittest.TestCase):
    """Tests for _read_gsd_state: bounded never-raising reader."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_function_exists(self):
        """_read_gsd_state must be importable from the module."""
        self.assertTrue(hasattr(self.mod, "_read_gsd_state"),
                        "_read_gsd_state not found in claude-statusline.py")

    def test_max_bytes_constant_exists(self):
        """_GSD_MAX_BYTES constant must be defined."""
        self.assertTrue(hasattr(self.mod, "_GSD_MAX_BYTES"),
                        "_GSD_MAX_BYTES not found in claude-statusline.py")

    def test_valid_fixtures_returns_dict(self):
        """Valid HANDOFF.json + STATE.md + ROADMAP.md → dict with all three keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("handoff", result)
        self.assertIn("state", result)
        self.assertIn("roadmap", result)

    def test_handoff_parsed_as_dict(self):
        """handoff key must be a dict (parsed from JSON)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsInstance(result["handoff"], dict)
        self.assertEqual(result["handoff"]["plan"], "05-02")

    def test_state_frontmatter_parsed(self):
        """state key must be a dict with milestone and progress sub-dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        state = result["state"]
        self.assertIsInstance(state, dict)
        self.assertEqual(state.get("milestone"), "v1.0")

    def test_progress_subkeys_are_ints(self):
        """progress.total_plans, completed_plans, percent must be ints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        progress = result["state"].get("progress", {})
        self.assertIsInstance(progress.get("total_plans"), int)
        self.assertIsInstance(progress.get("completed_plans"), int)
        self.assertIsInstance(progress.get("percent"), int)
        self.assertEqual(progress["total_plans"], 15)
        self.assertEqual(progress["completed_plans"], 13)

    def test_roadmap_is_string(self):
        """roadmap key must be a raw string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsInstance(result["roadmap"], str)
        self.assertIn("05-01-PLAN.md", result["roadmap"])

    def test_missing_handoff_returns_none(self):
        """Missing HANDOFF.json → None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, None, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsNone(result)

    def test_missing_state_returns_none(self):
        """Missing STATE.md → None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, None, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsNone(result)

    def test_missing_roadmap_returns_none(self):
        """Missing ROADMAP.md → None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_planning_dir(tmpdir, _VALID_HANDOFF, _VALID_STATE_MD, None)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsNone(result)

    def test_malformed_handoff_returns_none(self):
        """Malformed JSON in HANDOFF.json → None, no traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "HANDOFF.json"), "w") as f:
                f.write("{this is not valid JSON!}")
            _write_planning_dir(tmpdir, None, _VALID_STATE_MD, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        self.assertIsNone(result)

    def test_never_raises_on_nonexistent_dir(self):
        """Non-existent planning_dir → None, no exception."""
        result = self.mod._read_gsd_state("/tmp/this-path-does-not-exist-xyz-12345")
        self.assertIsNone(result)

    def test_no_frontmatter_in_state_returns_none(self):
        """STATE.md with no --- delimiters → None (no frontmatter to parse)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_state = "# Project State\nNo frontmatter here.\n"
            _write_planning_dir(tmpdir, _VALID_HANDOFF, bad_state, _ROADMAP_WITH_INCOMPLETE)
            result = self.mod._read_gsd_state(tmpdir)
        # Either None or dict with empty state — both acceptable; must not raise
        # The key contract is: no exception is raised. If it returns None that's fine;
        # if it returns a dict with empty state that's also fine.
        self.assertTrue(result is None or isinstance(result, dict))


# ---------------------------------------------------------------------------
# _infer_gsd_lifecycle tests
# ---------------------------------------------------------------------------

class TestInferGsdLifecycle(unittest.TestCase):
    """Tests for _infer_gsd_lifecycle: pure HANDOFF-first/roadmap-fallback resolver."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_function_exists(self):
        """_infer_gsd_lifecycle must be importable from the module."""
        self.assertTrue(hasattr(self.mod, "_infer_gsd_lifecycle"),
                        "_infer_gsd_lifecycle not found in claude-statusline.py")

    def test_stale_seconds_constant_exists(self):
        """_GSD_HANDOFF_STALE_SECONDS constant must be defined."""
        self.assertTrue(hasattr(self.mod, "_GSD_HANDOFF_STALE_SECONDS"),
                        "_GSD_HANDOFF_STALE_SECONDS not found in claude-statusline.py")

    def test_none_input_returns_none(self):
        """_infer_gsd_lifecycle(None) → None."""
        result = self.mod._infer_gsd_lifecycle(None)
        self.assertIsNone(result)

    def _make_live_state(self, handoff_override=None, state_override=None, roadmap=None):
        """Build a live state dict with a recent timestamp."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VALID_HANDOFF)
        handoff["timestamp"] = now_z
        if handoff_override:
            handoff.update(handoff_override)
        state_fm = {
            "milestone": "v1.0",
            "status": "executing",
            "progress": {
                "total_plans": 15,
                "completed_plans": 13,
                "percent": 71,
            },
        }
        if state_override:
            state_fm.update(state_override)
        return {
            "handoff": handoff,
            "state": state_fm,
            "roadmap": roadmap or _ROADMAP_WITH_INCOMPLETE,
        }

    def test_live_executing_plan_and_tasks(self):
        """Live HANDOFF naming 05-02 at 2/3 tasks → executing with correct fields."""
        state = self._make_live_state()
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("plan_id"), "05-02")
        self.assertEqual(result.get("state"), "executing")
        self.assertEqual(result.get("tasks_done"), 2)
        self.assertEqual(result.get("total_tasks"), 3)

    def test_live_blocked_state(self):
        """Live HANDOFF with non-empty blockers → state == 'blocked'."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_BLOCKED_HANDOFF)
        handoff["timestamp"] = now_z
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "blocked")

    def test_live_verifying_state(self):
        """Live HANDOFF with status containing 'verif' → state == 'verifying'."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VERIFYING_HANDOFF)
        handoff["timestamp"] = now_z
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "verifying")

    def test_stale_handoff_falls_back_to_roadmap(self):
        """Stale HANDOFF timestamp → roadmap fallback; first incomplete plan id shown, state idle."""
        stale_handoff = dict(_VALID_HANDOFF)
        stale_handoff["timestamp"] = "2020-01-01T00:00:00.000Z"  # very old
        state = {
            "handoff": stale_handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "idle")
        self.assertEqual(result.get("plan_id"), "05-01")

    def test_null_handoff_falls_back_to_roadmap(self):
        """Null plan in HANDOFF → roadmap fallback; first incomplete plan shown, state idle."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "idle")
        self.assertEqual(result.get("plan_id"), "05-01")

    def test_all_complete_roadmap_done_state(self):
        """All complete (STATE progress confirms) → state == 'done' with milestone.

        Updated for CR-01: "done" is now positively confirmed from STATE.md
        progress (completed_phases == total_phases and plans complete), not
        inferred from the absence of an unchecked PLAN.md line.  The all-complete
        roadmap is supplied too, but the progress block is the authoritative
        signal.
        """
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_COMPLETE)},
            "roadmap": _ROADMAP_ALL_COMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "done")
        self.assertEqual(result.get("milestone"), "v1.0")

    # --- CR-01 / WR-02 / WR-04 regression: real ROADMAP.md format ---

    def test_real_format_incomplete_resolves_idle_not_done(self):
        """WR-04/CR-01: real-roadmap format + STATE progress incomplete → idle, NOT done.

        Mirrors the production .planning/: incomplete work is a phase header
        ("- [ ] **Phase 03.1: ...**") + a "- [ ] TBD" placeholder, completed plans
        are "- [x] NN-MM-PLAN.md", and STATE progress has completed_phases (6) <
        total_phases (7).  A stale/null HANDOFF must NOT report milestone-complete.
        Fails against pre-CR-01 code (returned done/v1.0); passes after the fix.
        """
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_INCOMPLETE)},
            "roadmap": _ROADMAP_REAL_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertNotEqual(result.get("state"), "done",
                            "Incomplete milestone must not resolve to 'done' (CR-01)")
        self.assertEqual(result.get("state"), "idle")
        self.assertIsNone(result.get("milestone"),
                          "Milestone label must not be set in a non-done state")

    def test_real_format_incomplete_surfaces_next_phase_id(self):
        """WR-04/D-06: real-roadmap fallback surfaces the next incomplete phase id.

        No unchecked PLAN.md row exists, so the next incomplete marker is the
        phase header "- [ ] **Phase 03.1: ...**"; the segment must surface 03.1
        (via phase_id) so the user knows where they'll resume.
        """
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_INCOMPLETE)},
            "roadmap": _ROADMAP_REAL_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        # No plan-row id in the real-format incomplete roadmap.
        self.assertIsNone(result.get("plan_id"))
        self.assertEqual(result.get("phase_id"), "03.1",
                         "Next incomplete phase header (03.1) must be surfaced")

    def test_real_format_all_complete_resolves_done(self):
        """WR-04/D-07: real format + STATE progress fully complete → done + milestone.

        Second fixture where completed_phases == total_phases (7/7) and plans are
        complete (15/15): positively confirms the milestone, so state == 'done'.
        """
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_COMPLETE)},
            "roadmap": _ROADMAP_REAL_ALL_COMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "done")
        self.assertEqual(result.get("milestone"), "v1.0")

    def test_empty_roadmap_resolves_idle_not_done(self):
        """WR-02: an empty/unparseable roadmap must resolve to idle, never done."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_INCOMPLETE)},
            "roadmap": "",
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "idle")
        self.assertNotEqual(result.get("state"), "done")

    def test_no_progress_block_resolves_idle_not_done(self):
        """WR-02/CR-01: absent STATE progress can never positively confirm done."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_ALL_COMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "idle",
                         "No progress data → cannot confirm completion → idle (not done)")

    def test_plan_checkbox_path_still_works(self):
        """WR-04: the synthetic plan-checkbox fallback path is preserved.

        With an unchecked "- [ ] 05-01-PLAN.md" row and incomplete progress, the
        plan-row id (preferred over phase id) is still surfaced, state idle.
        """
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_INCOMPLETE)},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "idle")
        self.assertEqual(result.get("plan_id"), "05-01")

    # --- WR-01 regression: ANSI-injection / unbounded width ---

    def test_live_plan_field_is_sanitized(self):
        """WR-01: an ESC + 200 'X' plan value must not emit \\x1b and must be width-bounded."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VALID_HANDOFF)
        handoff["timestamp"] = now_z
        handoff["plan"] = "\033[5;31mPWNED\033[0m" + ("X" * 200)
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        plan_id = result.get("plan_id") or ""
        self.assertNotIn("\x1b", plan_id, "ESC must be stripped from untrusted plan field")
        self.assertLessEqual(len(plan_id), 24, "plan_id must be width-bounded")

    def test_milestone_label_is_sanitized(self):
        """WR-01: a malicious milestone label must not emit \\x1b and must be width-bounded."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {
                "milestone": "\033[5;31m" + ("Z" * 200),
                "progress": dict(_STATE_PROGRESS_COMPLETE),
            },
            "roadmap": _ROADMAP_REAL_ALL_COMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "done")
        milestone = result.get("milestone") or ""
        self.assertNotIn("\x1b", milestone, "ESC must be stripped from untrusted milestone")
        self.assertLessEqual(len(milestone), 24, "milestone must be width-bounded")

    # --- WR-03 regression: non-positive total_tasks ---

    def test_zero_total_tasks_dropped(self):
        """WR-03: total_tasks == 0 is treated as 'no task count' (None)."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VALID_HANDOFF)
        handoff["timestamp"] = now_z
        handoff["total_tasks"] = 0
        handoff["completed_tasks"] = []
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertIsNone(result.get("total_tasks"),
                          "Non-positive total_tasks must become None (no task count)")

    def test_negative_total_tasks_dropped(self):
        """WR-03: a negative total_tasks is treated as 'no task count' (None)."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VALID_HANDOFF)
        handoff["timestamp"] = now_z
        handoff["total_tasks"] = -3
        handoff["completed_tasks"] = ["a", "b"]
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertIsNone(result.get("total_tasks"))
        self.assertGreaterEqual(result.get("tasks_done"), 0,
                                "tasks_done must never be negative")

    def test_plans_done_total_from_state(self):
        """plans_done / plans_total derived from STATE progress block."""
        state = self._make_live_state()
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("plans_done"), 13)
        self.assertEqual(result.get("plans_total"), 15)

    def test_tasks_done_clamped_to_total(self):
        """tasks_done is clamped to total_tasks (no negative/over)."""
        from datetime import datetime, timezone
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        handoff = dict(_VALID_HANDOFF)
        handoff["timestamp"] = now_z
        handoff["completed_tasks"] = ["a", "b", "c", "d", "e"]  # 5 > total_tasks=3
        handoff["total_tasks"] = 3
        state = {
            "handoff": handoff,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        # tasks_done must not exceed total_tasks
        tasks_done = result.get("tasks_done")
        total_tasks = result.get("total_tasks")
        if tasks_done is not None and total_tasks is not None:
            self.assertLessEqual(tasks_done, total_tasks)

    def test_partial_empty_dict_does_not_raise(self):
        """Partial/empty state dict must not raise."""
        try:
            result = self.mod._infer_gsd_lifecycle({})
            # Result can be anything (including None) — just must not raise
        except Exception as e:
            self.fail(f"_infer_gsd_lifecycle raised on empty dict: {e}")

    def test_missing_handoff_key_does_not_raise(self):
        """State dict missing 'handoff' key must not raise."""
        try:
            result = self.mod._infer_gsd_lifecycle({"state": {}, "roadmap": ""})
        except Exception as e:
            self.fail(f"_infer_gsd_lifecycle raised on missing handoff key: {e}")

    def test_result_has_expected_keys(self):
        """Result dict must have the documented keys (plan_id, state, etc.)."""
        state = self._make_live_state()
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        for key in ("plan_id", "state", "tasks_done", "total_tasks", "plans_done", "plans_total"):
            self.assertIn(key, result, f"Missing key '{key}' in _infer_gsd_lifecycle result")

    def test_roadmap_pattern_strips_plan_suffix(self):
        """Roadmap fallback strips -PLAN.md suffix, returning bare plan id like '05-01'."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_WITH_INCOMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        plan_id = result.get("plan_id", "")
        # Must NOT contain "-PLAN.md"
        self.assertNotIn("-PLAN.md", plan_id, "plan_id should not contain -PLAN.md suffix")


# ---------------------------------------------------------------------------
# _gsd_segment builder tests (Wave 2, Plan 02)
# ---------------------------------------------------------------------------

import subprocess

# Project repo root (for E2E tests — this repo has .planning/)
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Isolated HOME for E2E tests (no config installed — weather omitted)
_E2E_HOME = tempfile.mkdtemp(prefix="gsd-statusline-gsd-e2e-home-")


def _run_script_e2e(stdin_dict: dict, home: str = _E2E_HOME) -> subprocess.CompletedProcess:
    """Pipe a JSON dict to the script as a subprocess and return the result."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(stdin_dict).encode(),
        capture_output=True,
        env=env,
    )


def _minimal_data_with_project(project_dir: str) -> dict:
    """Minimal stdin JSON with workspace.project_dir pointing to project_dir."""
    return {
        "model": {"display_name": "TestModel"},
        "thinking": {"enabled": False},
        "workspace": {
            "current_dir": project_dir,
            "project_dir": project_dir,
            "added_dirs": [],
        },
        "cwd": project_dir,
        "context_window": {"used_percentage": 10},
        "rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": None},
            "seven_day": {"used_percentage": 5, "resets_at": None},
        },
    }


class TestGsdSegmentBuilder(unittest.TestCase):
    """Tests for _gsd_segment: builder monkeypatch approach (no disk I/O)."""

    def setUp(self):
        self.mod = _load_script_module()

    def _call(self, handoff=None, state_fm=None, roadmap=None, cfg_override=None):
        """Call _gsd_segment with monkeypatched _read_gsd_state.

        Passes a fake project_dir that has a .planning/ directory stub (so the
        os.path.isdir check passes) but monkeypatches _read_gsd_state to return
        controlled fixture data.
        """
        import tempfile as _tmpfile, os as _os

        # We need an actual directory for the os.path.isdir(.planning) guard
        with _tmpfile.TemporaryDirectory() as tmpdir:
            planning_dir = _os.path.join(tmpdir, ".planning")
            _os.makedirs(planning_dir)

            def fake_read_gsd_state(_planning_dir):
                if handoff is None:
                    return None
                # D-01: stamp the handoff timestamp to NOW so the real staleness
                # check (_GSD_HANDOFF_STALE_SECONDS) reads it as live, independent
                # of the ambient wall clock. Mirrors TestInferGsdLifecycle._make_live_state.
                # Uses dict(handoff) copy — never mutate shared module-level fixtures.
                from datetime import datetime, timezone
                live_handoff = dict(handoff)
                live_handoff["timestamp"] = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                )
                return {
                    "handoff": live_handoff,
                    "state": state_fm or {},
                    "roadmap": roadmap or "",
                }

            original = self.mod._read_gsd_state
            self.mod._read_gsd_state = fake_read_gsd_state
            try:
                cfg = {
                    "display": {"icon_set": "nerd", "show_gsd": True, "bar_style": "shade"},
                    "toggles": {"show_thinking_glyph": True},
                    "thresholds": {"warn": 70, "crit": 90},
                }
                if cfg_override:
                    for k, v in cfg_override.items():
                        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                            cfg[k].update(v)
                        else:
                            cfg[k] = v
                data = {
                    "workspace": {"current_dir": tmpdir, "project_dir": tmpdir},
                    "cwd": tmpdir,
                }
                return self.mod._gsd_segment(data, cfg)
            finally:
                self.mod._read_gsd_state = original

    def test_show_gsd_false_returns_none(self):
        """show_gsd=False -> None (config toggle, D-08)."""
        result = self._call(
            handoff=_VALID_HANDOFF,
            cfg_override={"display": {"show_gsd": False}},
        )
        self.assertIsNone(result)

    def test_read_gsd_state_returns_none_gives_none(self):
        """_read_gsd_state returning None -> _gsd_segment returns None (no .planning/)."""
        result = self._call(handoff=None)
        self.assertIsNone(result)

    def test_executing_contains_plan_id(self):
        """Executing state: output contains the plan id."""
        result = self._call(handoff=_VALID_HANDOFF)
        self.assertIsNotNone(result)
        self.assertIn("05-02", result)

    def test_executing_contains_green(self):
        """Executing state: GREEN ANSI code present for lifecycle glyph."""
        result = self._call(handoff=_VALID_HANDOFF)
        self.assertIsNotNone(result)
        self.assertIn("\033[32m", result)

    def test_executing_plan_id_not_wrapped_in_color(self):
        """D-09: plan id label is neutral — GREEN/RED must NOT immediately precede the plan id."""
        result = self._call(handoff=_VALID_HANDOFF)
        self.assertIsNotNone(result)
        # The plan id must not be directly preceded by a GREEN or RED escape
        green = "\033[32m"
        red = "\033[31m"
        plan_id = "05-02"
        for color in (green, red):
            idx = result.find(color + plan_id)
            self.assertEqual(
                idx, -1,
                f"Plan id immediately preceded by color code {color!r} (D-09 violated): {result!r}",
            )

    def test_executing_contains_task_progress(self):
        """Executing state with completed_tasks: output contains N/M progress."""
        result = self._call(handoff=_VALID_HANDOFF)
        self.assertIsNotNone(result)
        # _VALID_HANDOFF has completed_tasks=["task1","task2"], total_tasks=3 -> "2/3"
        self.assertIn("2/3", result)

    def test_blocked_contains_red(self):
        """Blocked state: RED ANSI code present for lifecycle glyph."""
        result = self._call(handoff=_BLOCKED_HANDOFF)
        self.assertIsNotNone(result)
        self.assertIn("\033[31m", result)

    def test_verifying_contains_yellow(self):
        """Verifying state: YELLOW ANSI code present for lifecycle glyph."""
        result = self._call(handoff=_VERIFYING_HANDOFF)
        self.assertIsNotNone(result)
        self.assertIn("\033[33m", result)

    def test_idle_state_contains_dim(self):
        """Idle state (null HANDOFF, roadmap fallback): DIM ANSI code present."""
        result = self._call(
            handoff=_NULL_HANDOFF,
            roadmap=_ROADMAP_WITH_INCOMPLETE,
        )
        self.assertIsNotNone(result)
        self.assertIn("\033[2m", result)

    def test_idle_state_contains_next_plan_id(self):
        """Idle state: output contains the next-up plan id from the roadmap."""
        result = self._call(
            handoff=_NULL_HANDOFF,
            roadmap=_ROADMAP_WITH_INCOMPLETE,
        )
        self.assertIsNotNone(result)
        # First incomplete plan in _ROADMAP_WITH_INCOMPLETE is 05-01
        self.assertIn("05-01", result)

    def test_milestone_complete_contains_done_glyph_and_green(self):
        """Milestone-complete (done) state: milestone label + GREEN done glyph (D-07).

        Updated for CR-01: done is confirmed from STATE progress (7/7 phases,
        15/15 plans), not from the absence of an unchecked PLAN.md line.
        """
        state_fm = {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_COMPLETE)}
        result = self._call(
            handoff=_NULL_HANDOFF,
            state_fm=state_fm,
            roadmap=_ROADMAP_ALL_COMPLETE,
        )
        self.assertIsNotNone(result)
        # Done state must show GREEN (not omit)
        self.assertIn("\033[32m", result)
        # Must contain the milestone label
        self.assertIn("v1.0", result)

    def test_idle_phase_id_rendered_when_no_plan_id(self):
        """CR-01/D-06: real-format roadmap (phase header, no plan row) renders phase id.

        Null HANDOFF + incomplete STATE progress + a roadmap whose next incomplete
        marker is "- [ ] **Phase 03.1: ...**" → idle segment surfacing 03.1
        (NOT a done/milestone segment, NOT omitted).
        """
        state_fm = {"milestone": "v1.0", "progress": dict(_STATE_PROGRESS_INCOMPLETE)}
        result = self._call(
            handoff=_NULL_HANDOFF,
            state_fm=state_fm,
            roadmap=_ROADMAP_REAL_INCOMPLETE,
        )
        self.assertIsNotNone(result)
        self.assertIn("03.1", result)
        self.assertIn("\033[2m", result)   # DIM idle glyph
        self.assertNotIn("v1.0", result)   # not a done/milestone render

    def test_zero_total_tasks_omits_progress_fragment(self):
        """WR-03: total_tasks == 0 → no 'N/N' progress fragment is rendered."""
        import re as _re
        handoff = dict(_VALID_HANDOFF)
        handoff["total_tasks"] = 0
        handoff["completed_tasks"] = []
        from datetime import datetime, timezone
        handoff["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = self._call(handoff=handoff, roadmap=_ROADMAP_WITH_INCOMPLETE)
        self.assertIsNotNone(result)
        # No "<digits>/<digits>" task-progress fragment may appear.
        self.assertIsNone(
            _re.search(r"\b\d+/\d+\b", result),
            f"Non-positive total_tasks must not render an N/N fragment: {result!r}",
        )

    def test_malicious_plan_field_not_in_rendered_segment(self):
        """WR-01: an ESC + long plan value must not inject \\x1b nor blow segment width."""
        handoff = dict(_VALID_HANDOFF)
        handoff["plan"] = "\033[5;31mPWNED\033[0m" + ("X" * 200)
        from datetime import datetime, timezone
        handoff["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = self._call(handoff=handoff, roadmap=_ROADMAP_WITH_INCOMPLETE)
        self.assertIsNotNone(result)
        # The injected blink/color sequence "\033[5;31m" must not appear verbatim.
        self.assertNotIn("\033[5;31m", result,
                         "Untrusted plan ESC sequence leaked into rendered segment")
        self.assertNotIn("PWNED\033", result)
        # The 200 'X' run must be truncated — the segment stays width-bounded.
        self.assertNotIn("X" * 30, result, "plan label must be truncated, not unbounded")

    def test_icon_set_emoji_uses_fallback_glyphs(self):
        """icon_set='emoji': output uses ascii/emoji fallbacks, no _NF_GSD_* codepoints."""
        result = self._call(
            handoff=_VALID_HANDOFF,
            cfg_override={"display": {"icon_set": "emoji"}},
        )
        self.assertIsNotNone(result)
        # Should not contain any of the 6 nerd codepoints
        for attr in ("_NF_GSD_EXECUTING", "_NF_GSD_VERIFYING", "_NF_GSD_BLOCKED",
                     "_NF_GSD_DONE", "_NF_GSD_IDLE", "_NF_GSD_PLAN"):
            nerd_char = getattr(self.mod, attr, None)
            if nerd_char:
                self.assertNotIn(
                    nerd_char, result,
                    f"Nerd glyph {attr} ({nerd_char!r}) found in emoji-mode result: {result!r}",
                )

    def test_icon_set_emoji_output_nonempty(self):
        """icon_set='emoji': output is a non-None, non-empty bracketed string."""
        result = self._call(
            handoff=_VALID_HANDOFF,
            cfg_override={"display": {"icon_set": "emoji"}},
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("[") and result.endswith("]"),
                        f"Expected bracketed string, got: {result!r}")

    def test_no_workspace_returns_none(self):
        """data with no workspace key -> None (no traceback, never-raise)."""
        try:
            result = self.mod._gsd_segment({}, {"display": {"show_gsd": True}})
            # None is expected when project_dir is absent/empty
            self.assertIsNone(result)
        except Exception as e:
            self.fail(f"_gsd_segment raised on empty data: {e}")

    def test_none_workspace_returns_none(self):
        """data with workspace=None -> None (never raises)."""
        try:
            result = self.mod._gsd_segment(
                {"workspace": None},
                {"display": {"show_gsd": True}},
            )
            self.assertIsNone(result)
        except Exception as e:
            self.fail(f"_gsd_segment raised on workspace=None: {e}")

    def test_nonexistent_project_dir_returns_none(self):
        """project_dir pointing to non-existent path -> None (no traceback)."""
        try:
            result = self.mod._gsd_segment(
                {"workspace": {"project_dir": "/tmp/definitely-does-not-exist-gsd-test"}},
                {"display": {"show_gsd": True}},
            )
            self.assertIsNone(result)
        except Exception as e:
            self.fail(f"_gsd_segment raised on nonexistent project_dir: {e}")

    def test_project_dir_without_planning_returns_none(self):
        """project_dir without .planning/ subdirectory -> None (silent omit, D-08)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.mod._gsd_segment(
                {"workspace": {"project_dir": tmpdir}},
                {"display": {"show_gsd": True}},
            )
            self.assertIsNone(result)

    def test_output_is_bracketed(self):
        """Successful output is a [<interior>] bracketed string."""
        result = self._call(handoff=_VALID_HANDOFF)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("[") and result.endswith("]"),
                        f"Expected bracketed string, got: {result!r}")


class TestGsdSegmentE2E(unittest.TestCase):
    """End-to-end subprocess tests: piping JSON to the script and inspecting stdout."""

    def test_e2e_repo_dir_shows_gsd_segment_between_git_and_model(self):
        """Piping the project repo as project_dir: gsd segment appears between [git] and [model].

        This repo has .planning/ so with show_gsd defaulting True a [gsd] segment
        is expected on the top line between [git] and [model] (D-10 ordering).
        """
        data = _minimal_data_with_project(_REPO_DIR)
        result = _run_script_e2e(data)
        self.assertEqual(
            result.returncode, 0,
            f"Script exited {result.returncode}; stderr: {result.stderr.decode()!r}",
        )
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr, f"Traceback in stderr: {stderr!r}")

        top_line = result.stdout.decode().splitlines()[0]

        # Both project and model must be present
        project_marker = "[claude_statusline]"
        model_marker = "[TestModel]"
        idx_project = top_line.find(project_marker)
        idx_model = top_line.find(model_marker)

        self.assertGreater(idx_project, -1, f"Project marker not found: {top_line!r}")
        self.assertGreater(idx_model, -1, f"Model marker not found: {top_line!r}")

        # A [gsd] segment must appear between project and model.
        # We know [git] is between project and model (Phase 04), and [gsd] comes after [git].
        # So there must be at least two bracketed items between project and model.
        project_end = idx_project + len(project_marker)
        between = top_line[project_end:idx_model]
        # Count opening brackets in the region between [project] and [model]
        bracket_count = between.count("[")
        self.assertGreaterEqual(
            bracket_count, 2,
            f"Expected at least [git] + [gsd] between project and model; "
            f"between={between!r}  line={top_line!r}",
        )

    def test_e2e_no_planning_dir_omits_gsd_segment_exits_zero(self):
        """Piping a dir without .planning/: gsd segment omitted, script exits 0, no traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = _minimal_data_with_project(tmpdir)
            result = _run_script_e2e(data)
        self.assertEqual(
            result.returncode, 0,
            f"Script must exit 0 even for non-GSD dir; stderr: {result.stderr.decode()!r}",
        )
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr, f"Traceback in stderr: {stderr!r}")
        self.assertNotIn("Error", stderr)
        # Bar must still render (at minimum the model segment)
        top_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[TestModel]", top_line,
                      f"Model segment must still render when gsd segment absent: {top_line!r}")


if __name__ == "__main__":
    unittest.main()
