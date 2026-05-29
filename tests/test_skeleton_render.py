#!/usr/bin/env python3
"""
Tests for the Walking Skeleton render -- Task 1 (01-01-PLAN.md).

These tests exercise the installed script at ~/.claude/claude-statusline.py
by piping JSON to it as a subprocess and inspecting stdout.

All tests run against the real fixture (.examples/claude_stdin.json) or
crafted variants.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")
FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", ".examples", "claude_stdin.json"
)

# Isolate from the host's real ~/.claude/claude-statusline/ install (config + cache)
# so these Phase-1 render contracts stay deterministic even on a machine where weather
# is configured. Empty HOME -> no config -> default location 0.0/0.0 -> weather segment
# omitted, leaving exactly the Phase-1 top/bottom lines.
_ISOLATED_HOME = tempfile.mkdtemp(prefix="gsd-statusline-test-home-")

# Phase 04: a second isolated HOME that has a config with display.show_git=false,
# so test_fixture_top_line_exact stays an exact-equality guard even after the git
# segment was wired in (D-09).  The git segment is omitted when show_git=false,
# so the asserted exact string [claude_statusline] [Opus 4.8 (1M context) ] stays valid.
_NO_GIT_HOME = tempfile.mkdtemp(prefix="gsd-statusline-test-nogit-home-")
_NO_GIT_CFG_DIR = os.path.join(_NO_GIT_HOME, ".claude", "claude-statusline")
os.makedirs(_NO_GIT_CFG_DIR, exist_ok=True)
with open(os.path.join(_NO_GIT_CFG_DIR, "claude-statusline.toml"), "w") as _fh:
    _fh.write("[display]\nshow_git = false\n")


def run_script(stdin_bytes: bytes, home: str | None = None) -> subprocess.CompletedProcess:
    """Run the script with given stdin bytes under an isolated HOME."""
    env = dict(os.environ)
    env["HOME"] = home if home is not None else _ISOLATED_HOME
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=stdin_bytes,
        capture_output=True,
        env=env,
    )


def load_fixture() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


class TestSkeletonRender(unittest.TestCase):

    # --- Behavior tests ---

    def test_fixture_top_line_exact(self):
        """Given the real fixture and show_git=false config, first line matches exactly.

        Phase 04: _git_segment is now wired between project and model (D-09).
        The fixture's workspace.current_dir points to this repo, so the git
        segment would render with show_git=true.  To keep this test an exact-
        equality guard on the [project] [model] ordering without knowing the
        current branch/state, we run it under _NO_GIT_HOME which has
        [display] show_git = false => git segment omitted.

        Phase 02.1: with icon_set='nerd' (the default), the thinking indicator
        is the Nerd Font lightbulb glyph (U+F0EB, nf-fa-lightbulb).
        """
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        result = run_script(fixture_bytes, home=_NO_GIT_HOME)
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        # U+F0EB is the nf-fa-lightbulb Nerd Font glyph (_NF_THINKING); it replaces
        # the thought-bubble emoji when icon_set="nerd" (default).
        self.assertEqual(first_line, "[claude_statusline] [Opus 4.8 (1M context) ]")

    def test_thinking_false_no_glyph(self):
        """thinking.enabled=False => model brackets contain no thinking glyph"""
        data = load_fixture()
        data["thinking"]["enabled"] = False
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[Opus 4.8 (1M context)]", first_line)
        self.assertNotIn("\U0001f4ad", first_line)  # no thought bubble

    def test_thinking_absent_no_glyph(self):
        """thinking block absent => no thinking glyph"""
        data = load_fixture()
        del data["thinking"]
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertNotIn("\U0001f4ad", first_line)  # no thought bubble

    def test_missing_model_omits_model_segment(self):
        """Missing model block => project segment still renders, model segment absent, exit 0"""
        data = load_fixture()
        del data["model"]
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[claude_statusline]", first_line)
        # model display_name should not appear
        self.assertNotIn("Opus 4.8", first_line)

    def test_empty_stdin_exits_zero_no_traceback(self):
        """Empty stdin => exit 0, no traceback"""
        result = run_script(b"")
        self.assertEqual(result.returncode, 0)
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn("Error", stderr)

    def test_non_json_stdin_exits_zero_no_traceback(self):
        """Non-JSON stdin => exit 0, no traceback in stderr"""
        result = run_script(b"not json")
        self.assertEqual(result.returncode, 0)
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr)

    # --- Source tests ---

    def test_shebang_first_line(self):
        """First line of script is exactly '#!/usr/bin/env python3'"""
        with open(SCRIPT) as f:
            first_line = f.readline().rstrip("\n")
        self.assertEqual(first_line, "#!/usr/bin/env python3")

    def test_imports_tomllib_and_requests_is_guarded(self):
        """Script imports tomllib; requests is guarded in try/except (Phase 2 D2-12).

        Phase 1 D-12 (zero deps) is superseded by Phase 2 D2-01; requests is now
        a guarded import that sets _REQUESTS_OK=False on ImportError, so the weather
        segment omits cleanly without breaking the Phase-1 bar.
        """
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("import tomllib", source)
        # requests must be guarded (in a try/except), not a bare top-level import
        self.assertIn("import requests", source)
        self.assertIn("_REQUESTS_OK = True", source)
        self.assertIn("_REQUESTS_OK = False", source)

    # --- Phase 04 D-09 ordering guard ---

    def test_d09_git_segment_between_project_and_model(self):
        """D-09: git segment appears AFTER [project] and BEFORE [model] on the top line.

        Run the fixture (whose workspace.current_dir is this real repo) under the
        default show_git=true config and assert positional ordering:
            index_of([claude_statusline]) < index_of(branch text) < index_of([Opus ...])

        This is the canonical D-09 guard.  The branch text varies with the current
        checkout, so we look for the bracketed git segment '[' between the two known
        fixed markers rather than asserting a specific branch name.
        """
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        # Use the default isolated home (no config -> show_git defaults to True)
        result = run_script(fixture_bytes, home=_ISOLATED_HOME)
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]

        project_marker = "[claude_statusline]"
        model_marker = "[Opus 4.8 (1M context)"

        idx_project = first_line.find(project_marker)
        idx_model = first_line.find(model_marker)

        self.assertGreater(idx_project, -1,
                           f"Project marker not found in top line: {first_line!r}")
        self.assertGreater(idx_model, -1,
                           f"Model marker not found in top line: {first_line!r}")

        # Find the git segment: a '[' that appears between project end and model start
        project_end = idx_project + len(project_marker)
        between = first_line[project_end:idx_model]
        self.assertIn("[", between,
                      f"No git segment bracket found between project and model. "
                      f"Between text: {between!r}  Full line: {first_line!r}")

        # Also assert project comes before model (basic ordering check)
        self.assertLess(idx_project, idx_model,
                        f"[project] must appear before [model]; line: {first_line!r}")


if __name__ == "__main__":
    unittest.main()
