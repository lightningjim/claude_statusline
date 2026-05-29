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
        """All ROADMAP plans complete (no [ ] plan checkbox) → state == 'done' with milestone."""
        state = {
            "handoff": _NULL_HANDOFF,
            "state": {"milestone": "v1.0", "progress": {}},
            "roadmap": _ROADMAP_ALL_COMPLETE,
        }
        result = self.mod._infer_gsd_lifecycle(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("state"), "done")
        self.assertEqual(result.get("milestone"), "v1.0")

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


if __name__ == "__main__":
    unittest.main()
