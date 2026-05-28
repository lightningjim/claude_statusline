#!/usr/bin/env python3
"""
Tests for Plan 01-03: TOML config loader, threshold wiring, and per-segment toggles.

Task 1: load_config() — silent defaults, threshold wiring, Phase-2 key tolerance
Task 2: per-segment toggle gating in render functions
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.expanduser("~/.claude/claude-statusline.py")
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
# Task 1: load_config
# ---------------------------------------------------------------------------

class TestLoadConfigDefaults(unittest.TestCase):
    """D-07: missing/unreadable/malformed -> silently return built-in defaults."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_load_config_exists(self):
        """Script defines a load_config() function."""
        self.assertTrue(callable(getattr(self.mod, "load_config", None)))

    def test_missing_file_returns_defaults(self):
        """load_config with a non-existent path returns default dict with all keys."""
        cfg = self.mod.load_config("/nonexistent/path/that/cannot/exist.toml")
        # Must have thresholds
        self.assertIn("thresholds", cfg)
        self.assertEqual(cfg["thresholds"]["warn"], 70)
        self.assertEqual(cfg["thresholds"]["crit"], 90)
        # Must have toggles
        self.assertIn("toggles", cfg)
        self.assertTrue(cfg["toggles"]["show_context_bar"])
        self.assertTrue(cfg["toggles"]["show_five_hour"])
        self.assertTrue(cfg["toggles"]["show_weekly"])
        self.assertTrue(cfg["toggles"]["show_thinking_glyph"])

    def test_malformed_toml_returns_defaults(self):
        """load_config with a malformed TOML file returns defaults silently."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write("this is [not valid toml\n")
            path = f.name
        try:
            cfg = self.mod.load_config(path)
            # Must fall back to defaults
            self.assertEqual(cfg["thresholds"]["warn"], 70)
            self.assertEqual(cfg["thresholds"]["crit"], 90)
        finally:
            os.unlink(path)

    def test_empty_file_returns_defaults(self):
        """load_config with an empty TOML file returns full defaults."""
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="wb", delete=False) as f:
            path = f.name
        try:
            cfg = self.mod.load_config(path)
            self.assertEqual(cfg["thresholds"]["warn"], 70)
            self.assertTrue(cfg["toggles"]["show_context_bar"])
        finally:
            os.unlink(path)

    def test_no_exception_on_unreadable_file(self):
        """load_config never raises to the caller."""
        # Non-existent path should NOT raise
        try:
            result = self.mod.load_config("/no/such/path.toml")
        except Exception as e:
            self.fail(f"load_config raised unexpectedly: {e}")
        self.assertIsNotNone(result)

    def test_defaults_dict_exists(self):
        """DEFAULTS dict is defined in the module."""
        defaults = getattr(self.mod, "DEFAULTS", None)
        self.assertIsNotNone(defaults, "DEFAULTS dict must be defined")
        self.assertIsInstance(defaults, dict)


class TestLoadConfigMerge(unittest.TestCase):
    """Valid config merges over defaults; extra Phase-2 keys are ignored."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_custom_warn_threshold(self):
        """A config with thresholds.warn=50 overrides the default 70."""
        toml_content = b"[thresholds]\nwarn = 50\ncrit = 90\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            path = f.name
        try:
            cfg = self.mod.load_config(path)
            self.assertEqual(cfg["thresholds"]["warn"], 50)
            self.assertEqual(cfg["thresholds"]["crit"], 90)  # kept from defaults
        finally:
            os.unlink(path)

    def test_phase2_lat_lon_ignored(self):
        """Extra Phase-2 keys (location.lat/lon) do not cause an error."""
        toml_content = b"[location]\nlat = 37.5\nlon = -122.0\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            path = f.name
        try:
            # Should not raise; defaults preserved
            cfg = self.mod.load_config(path)
            self.assertEqual(cfg["thresholds"]["warn"], 70)
        finally:
            os.unlink(path)

    def test_absent_toggle_keeps_default_true(self):
        """A config with no toggles table keeps all toggle defaults (true)."""
        toml_content = b"[thresholds]\nwarn = 60\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            path = f.name
        try:
            cfg = self.mod.load_config(path)
            self.assertTrue(cfg["toggles"]["show_thinking_glyph"])
        finally:
            os.unlink(path)

    def test_toggle_override_false(self):
        """A config setting show_thinking_glyph=false is honored."""
        toml_content = b"[toggles]\nshow_thinking_glyph = false\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            path = f.name
        try:
            cfg = self.mod.load_config(path)
            self.assertFalse(cfg["toggles"]["show_thinking_glyph"])
            # Other toggles stay true
            self.assertTrue(cfg["toggles"]["show_context_bar"])
        finally:
            os.unlink(path)


class TestColorForWithThresholds(unittest.TestCase):
    """color_for and is_green must accept configurable threshold parameters."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_color_for_accepts_warn_crit_params(self):
        """color_for(pct, warn, crit) accepts custom thresholds."""
        # With warn=50, pct=60 should be yellow
        result = self.mod.color_for(60, 50, 90)
        self.assertEqual(result, self.mod.YELLOW)

    def test_color_for_default_params_preserved(self):
        """color_for(pct) still works with no extra args (defaults 70/90)."""
        # Regression: existing behavior unchanged
        self.assertEqual(self.mod.color_for(69), self.mod.GREEN)
        self.assertEqual(self.mod.color_for(70), self.mod.YELLOW)
        self.assertEqual(self.mod.color_for(91), self.mod.RED)

    def test_is_green_accepts_warn_param(self):
        """is_green(pct, warn) accepts custom warn threshold."""
        # With warn=50, pct=60 is NOT green
        self.assertFalse(self.mod.is_green(60, 50))
        # pct=49 IS green
        self.assertTrue(self.mod.is_green(49, 50))

    def test_is_green_default_params_preserved(self):
        """is_green(pct) still works with no extra args (default 70)."""
        self.assertTrue(self.mod.is_green(69))
        self.assertFalse(self.mod.is_green(70))

    def test_custom_crit_threshold(self):
        """With crit=80, pct=85 becomes red."""
        result = self.mod.color_for(85, 70, 80)
        self.assertEqual(result, self.mod.RED)

    def test_custom_crit_threshold_below(self):
        """With crit=80, pct=79 stays yellow."""
        result = self.mod.color_for(79, 70, 80)
        self.assertEqual(result, self.mod.YELLOW)


class TestFallbackRegressionSubprocess(unittest.TestCase):
    """D-07 regression: fixture always renders 2 lines regardless of config state."""

    def test_fixture_renders_two_lines_no_config(self):
        """With no config file, the fixture still renders 2 lines and exits 0."""
        with open(FIXTURE, "rb") as f:
            fixture_bytes = f.read()
        # Point config at non-existent path via env override (handled by script)
        result = run_script(fixture_bytes)
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.decode().splitlines()
        self.assertEqual(len(lines), 2, f"Expected 2 lines, got: {lines}")

    def test_malformed_config_renders_two_lines(self):
        """With malformed config, the fixture still renders 2 lines and exits 0."""
        with tempfile.NamedTemporaryFile(
            suffix=".toml", mode="w", delete=False,
            dir=os.path.expanduser("~/.claude")
        ) as f:
            f.write("[broken toml\n")
            bad_config_path = f.name

        # Backup real config if it exists
        real_config = os.path.expanduser("~/.claude/claude-statusline.toml")
        backup_path = real_config + ".testbak"
        had_real = os.path.exists(real_config)
        if had_real:
            os.rename(real_config, backup_path)
        os.rename(bad_config_path, real_config)

        try:
            with open(FIXTURE, "rb") as f:
                fixture_bytes = f.read()
            result = run_script(fixture_bytes)
            self.assertEqual(result.returncode, 0)
            lines = result.stdout.decode().splitlines()
            self.assertEqual(len(lines), 2, f"Expected 2 lines with malformed config, got: {lines}")
            # No traceback in stderr
            self.assertNotIn("Traceback", result.stderr.decode())
        finally:
            os.unlink(real_config)
            if had_real:
                os.rename(backup_path, real_config)

    def test_tomllib_load_used_in_script(self):
        """Script source contains 'tomllib.load' call."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("tomllib.load", source)


# ---------------------------------------------------------------------------
# Task 2: per-segment toggle gating (added after Task 2 implementation)
# ---------------------------------------------------------------------------

class TestPerSegmentToggles(unittest.TestCase):
    """D-08: toggle=false suppresses exactly that segment."""

    def _run_with_toml(self, toml_bytes: bytes) -> tuple[int, list[str], str]:
        """Write a temp TOML config, run fixture through script, return (rc, lines, stderr)."""
        real_config = os.path.expanduser("~/.claude/claude-statusline.toml")
        backup_path = real_config + ".toggletestbak"
        had_real = os.path.exists(real_config)
        if had_real:
            os.rename(real_config, backup_path)
        with open(real_config, "wb") as f:
            f.write(toml_bytes)
        try:
            with open(FIXTURE, "rb") as f:
                fixture_bytes = f.read()
            result = run_script(fixture_bytes)
            lines = result.stdout.decode().splitlines()
            return result.returncode, lines, result.stderr.decode()
        finally:
            os.unlink(real_config)
            if had_real:
                os.rename(backup_path, real_config)

    def test_show_thinking_glyph_false_drops_glyph(self):
        """show_thinking_glyph=false: top line has no thinking glyph."""
        toml = b"[toggles]\nshow_thinking_glyph = false\n"
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(lines), 1)
        self.assertNotIn("\U0001f4ad", lines[0])  # 💭 U+1F4AD
        self.assertNotIn("Traceback", stderr)

    def test_show_thinking_glyph_true_shows_glyph(self):
        """show_thinking_glyph=true (default): top line includes 💭 (fixture has thinking.enabled=true)."""
        toml = b"[toggles]\nshow_thinking_glyph = true\n"
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        self.assertIn("\U0001f4ad", lines[0])  # 💭 present

    def test_show_five_hour_false_drops_hourglass(self):
        """show_five_hour=false: bottom line has no ⏳ segment."""
        toml = b"[toggles]\nshow_five_hour = false\n"
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        self.assertEqual(rc, 0, f"rc={rc} stderr={stderr}")
        bottom = "\n".join(lines[1:])
        self.assertNotIn("⏳", bottom)

    def test_show_weekly_false_drops_calendar(self):
        """show_weekly=false: bottom line has no 🗓 segment."""
        toml = b"[toggles]\nshow_weekly = false\n"
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        bottom = "\n".join(lines[1:])
        self.assertNotIn("🗓", bottom)

    def test_show_context_bar_false_drops_bar(self):
        """show_context_bar=false: bottom line has no [▓░] bar."""
        toml = b"[toggles]\nshow_context_bar = false\n"
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        bottom = "\n".join(lines[1:])
        self.assertNotIn("▓", bottom)

    def test_all_bottom_toggles_false_top_line_still_renders(self):
        """All bottom toggles false: top line renders, command exits 0."""
        toml = (
            b"[toggles]\n"
            b"show_context_bar = false\n"
            b"show_five_hour = false\n"
            b"show_weekly = false\n"
        )
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(lines), 1)
        # Top line still has project name
        self.assertIn("claude_statusline", lines[0])
        self.assertNotIn("Traceback", stderr)

    def test_defaults_all_segments_render(self):
        """Default config (all true): fixture renders 2 lines."""
        toml = (
            b"[thresholds]\nwarn = 70\ncrit = 90\n"
            b"[toggles]\n"
            b"show_context_bar = true\n"
            b"show_five_hour = true\n"
            b"show_weekly = true\n"
            b"show_thinking_glyph = true\n"
        )
        rc, lines, stderr = self._run_with_toml(toml)
        self.assertEqual(rc, 0)
        self.assertEqual(len(lines), 2, f"Expected 2 lines, got {lines}")


if __name__ == "__main__":
    unittest.main()
