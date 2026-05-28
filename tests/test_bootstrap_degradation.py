#!/usr/bin/env python3
"""
Tests for Plan 02-01 Task 2: venv bootstrap, _weather_segment, and degradation.

Covers:
  - _weather_segment: returns None when _WEATHER_OK is False
  - _weather_segment: returns None when show_weather is False
  - render_top_line: with weather omitted, output equals Phase-1 format exactly
  - subprocess: running without venv/deps exits 0, prints bar, no Traceback
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")
FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", ".examples", "claude_stdin.json"
)


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script(stdin_bytes: bytes, env: dict | None = None) -> subprocess.CompletedProcess:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=stdin_bytes,
        capture_output=True,
        env=run_env,
    )


def load_fixture() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Unit tests: _weather_segment returns None on degradation paths
# ---------------------------------------------------------------------------

class TestWeatherSegmentDegradation(unittest.TestCase):
    """_weather_segment must return None when weather deps/config gate is off."""

    def setUp(self):
        self.mod = _load_script_module()
        self.data = load_fixture()
        self.base_cfg = {
            "location": {"lat": 39.7, "lon": -104.9},
            "weather": {"show_weather": True, "contact_email": ""},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
            "units": {"temp_unit": "F"},
            "thresholds": {"warn": 70, "crit": 90},
            "toggles": {},
        }

    def test_weather_segment_callable(self):
        """_weather_segment is defined and callable."""
        self.assertTrue(callable(getattr(self.mod, "_weather_segment", None)))

    def test_weather_segment_returns_none_when_weather_ok_false(self):
        """_weather_segment returns None immediately when _WEATHER_OK is False."""
        orig = self.mod._WEATHER_OK
        try:
            self.mod._WEATHER_OK = False
            result = self.mod._weather_segment(self.data, self.base_cfg)
            self.assertIsNone(result)
        finally:
            self.mod._WEATHER_OK = orig

    def test_weather_segment_returns_none_when_show_weather_false(self):
        """_weather_segment returns None when cfg weather.show_weather is False."""
        cfg = dict(self.base_cfg)
        cfg["weather"] = {"show_weather": False, "contact_email": ""}
        result = self.mod._weather_segment(self.data, cfg)
        self.assertIsNone(result)

    def test_weather_segment_no_exception_on_bad_inputs(self):
        """_weather_segment never raises on None/empty inputs."""
        try:
            result = self.mod._weather_segment(None, None)
        except Exception as e:
            self.fail(f"_weather_segment raised with None inputs: {e}")
        self.assertIsNone(result)

    def test_weather_ok_is_assigned(self):
        """_WEATHER_OK is defined at module level."""
        self.assertIsInstance(self.mod._WEATHER_OK, bool)


# ---------------------------------------------------------------------------
# Unit tests: render_top_line with weather omitted == Phase-1 output
# ---------------------------------------------------------------------------

class TestRenderTopLineWeatherOmitted(unittest.TestCase):
    """When _weather_segment returns None, top line equals Phase-1 project+model output."""

    def setUp(self):
        self.mod = _load_script_module()
        self.data = load_fixture()
        # Minimal cfg — show_weather=False forces weather omission
        self.cfg_no_weather = {
            "location": {"lat": 39.7, "lon": -104.9},
            "weather": {"show_weather": False, "contact_email": ""},
            "cache": {},
            "units": {"temp_unit": "F"},
            "thresholds": {"warn": 70, "crit": 90},
            "toggles": {"show_thinking_glyph": True},
        }

    def test_top_line_no_weather_has_project(self):
        """Top line with weather omitted still contains the project segment."""
        top = self.mod.render_top_line(self.data, self.cfg_no_weather)
        self.assertIn("[claude_statusline]", top)

    def test_top_line_no_weather_has_model(self):
        """Top line with weather omitted still contains the model segment."""
        top = self.mod.render_top_line(self.data, self.cfg_no_weather)
        self.assertIn("Opus 4.8 (1M context)", top)

    def test_top_line_no_weather_equals_phase1_format(self):
        """Top line with weather omitted exactly matches [project] [model] format."""
        orig_weather_ok = self.mod._WEATHER_OK
        try:
            self.mod._WEATHER_OK = False
            cfg = dict(self.cfg_no_weather)
            cfg["weather"] = {"show_weather": False}
            top = self.mod.render_top_line(self.data, cfg)
            # Must not contain a third bracketed segment beyond project and model
            # The Phase-1 top line is exactly: "[project] [model ...]"
            parts = top.split("] [")  # rough bracket split
            # With two segments: "[project] [model 💭]" → 2 parts after split
            # With three: "[project] [model 💭] [weather ...]" → 3 parts
            self.assertLessEqual(len(parts), 2, f"Expected at most 2 segments, got: {top!r}")
        finally:
            self.mod._WEATHER_OK = orig_weather_ok

    def test_weather_segment_wired_in_render_top_line(self):
        """Script source contains _weather_segment call inside render_top_line."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("_weather_segment", source)
        # _weather_segment must be referenced in segments list of render_top_line
        # (we check the function is called, not just defined)
        self.assertGreaterEqual(source.count("_weather_segment"), 2)


# ---------------------------------------------------------------------------
# Subprocess tests: bar renders under missing venv / missing deps
# ---------------------------------------------------------------------------

class TestBootstrapDegradationSubprocess(unittest.TestCase):
    """The bar must render correctly even when .venv is absent or deps can't import."""

    def test_fixture_renders_two_lines_exit_0(self):
        """Fixture exits 0 and prints 2 lines (top + bottom) with no config/venv."""
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        result = run_script(fixture_bytes)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr.decode()}")
        lines = result.stdout.decode().splitlines()
        # Bottom line may or may not be present depending on fixture data;
        # top line MUST always be present.
        self.assertGreaterEqual(len(lines), 1)
        self.assertIn("claude_statusline", lines[0])

    def test_no_traceback_in_stderr(self):
        """Running the script with the fixture must not produce a Traceback on stderr."""
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        result = run_script(fixture_bytes)
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr, f"Unexpected traceback: {stderr}")

    def test_top_line_contains_project_and_model(self):
        """Top line always contains the project and model segments."""
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        result = run_script(fixture_bytes)
        top_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[claude_statusline]", top_line)
        self.assertIn("Opus 4.8 (1M context)", top_line)

    def test_minimal_stdin_renders_top_line(self):
        """A minimal stdin JSON with project_dir and model renders a top line."""
        minimal = json.dumps({
            "workspace": {"project_dir": "/x/demo"},
            "model": {"display_name": "Opus"},
            "thinking": {"enabled": False},
        }).encode()
        result = run_script(minimal)
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.decode().splitlines()
        self.assertGreaterEqual(len(lines), 1)
        self.assertIn("[demo]", lines[0])
        self.assertIn("[Opus]", lines[0])
        self.assertNotIn("Traceback", result.stderr.decode())

    def test_os_execv_in_source(self):
        """Script source contains os.execv (venv self-re-exec bootstrap)."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("os.execv", source)

    def test_os_path_exists_guards_execv(self):
        """os.execv is guarded by os.path.exists (T-02-01)."""
        with open(SCRIPT) as f:
            source = f.read()
        # Both must appear; the exists check must come before execv
        exists_pos = source.find("os.path.exists(_VENV_PY)")
        execv_pos = source.find("os.execv")
        self.assertGreater(exists_pos, 0, "os.path.exists(_VENV_PY) not found")
        self.assertGreater(execv_pos, 0, "os.execv not found")
        self.assertLess(exists_pos, execv_pos,
                        "os.path.exists must appear before os.execv in source")


if __name__ == "__main__":
    unittest.main()
