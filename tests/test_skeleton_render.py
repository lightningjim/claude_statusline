#!/usr/bin/env python3
"""
Tests for the Walking Skeleton render — Task 1 (01-01-PLAN.md).

These tests exercise the installed script at ~/.claude/claude-statusline.py
by piping JSON to it as a subprocess and inspecting stdout.

All tests run against the real fixture (.examples/claude_stdin.json) or
crafted variants.
"""

import json
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")
FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", ".examples", "claude_stdin.json"
)


def run_script(stdin_bytes: bytes) -> subprocess.CompletedProcess:
    """Run the script with given stdin bytes, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=stdin_bytes,
        capture_output=True,
    )


def load_fixture() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


class TestSkeletonRender(unittest.TestCase):

    # --- Behavior tests ---

    def test_fixture_top_line_exact(self):
        """Given the real fixture, first line == '[claude_statusline] [Opus 4.8 (1M context) 💭]'"""
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        result = run_script(fixture_bytes)
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertEqual(first_line, "[claude_statusline] [Opus 4.8 (1M context) 💭]")

    def test_thinking_false_no_glyph(self):
        """thinking.enabled=False → model brackets contain no 💭"""
        data = load_fixture()
        data["thinking"]["enabled"] = False
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[Opus 4.8 (1M context)]", first_line)
        self.assertNotIn("💭", first_line)

    def test_thinking_absent_no_glyph(self):
        """thinking block absent → no 💭"""
        data = load_fixture()
        del data["thinking"]
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertNotIn("💭", first_line)

    def test_missing_model_omits_model_segment(self):
        """Missing model block → project segment still renders, model segment absent, exit 0"""
        data = load_fixture()
        del data["model"]
        result = run_script(json.dumps(data).encode())
        self.assertEqual(result.returncode, 0)
        first_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[claude_statusline]", first_line)
        # model display_name should not appear
        self.assertNotIn("Opus 4.8", first_line)

    def test_empty_stdin_exits_zero_no_traceback(self):
        """Empty stdin → exit 0, no traceback"""
        result = run_script(b"")
        self.assertEqual(result.returncode, 0)
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn("Error", stderr)

    def test_non_json_stdin_exits_zero_no_traceback(self):
        """Non-JSON stdin → exit 0, no traceback in stderr"""
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


if __name__ == "__main__":
    unittest.main()
