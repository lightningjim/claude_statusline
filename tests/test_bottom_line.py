#!/usr/bin/env python3
"""
Tests for Plan 01-02: bottom line helpers and rendering.

Task 1 helpers: color_for, is_green, fmt_reset, pct_int
Task 2 behavior: render_bottom_line integration via subprocess
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")
FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", ".examples", "claude_stdin.json"
)

# ---------------------------------------------------------------------------
# Helpers to load helpers from the script without executing main()
# ---------------------------------------------------------------------------

def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script(stdin_bytes: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=stdin_bytes,
        capture_output=True,
    )


def load_fixture() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Task 1: helpers — color_for, is_green, fmt_reset, pct_int
# ---------------------------------------------------------------------------

class TestColorFor(unittest.TestCase):
    """FMT-01: green<70 / yellow 70-90 / red strictly >90"""

    def setUp(self):
        self.mod = _load_script_module()

    def test_69_is_green(self):
        """color_for(69) returns GREEN (below yellow threshold)"""
        result = self.mod.color_for(69)
        self.assertEqual(result, self.mod.GREEN)

    def test_70_is_yellow(self):
        """color_for(70) returns YELLOW (at yellow threshold, not red)"""
        result = self.mod.color_for(70)
        self.assertEqual(result, self.mod.YELLOW)

    def test_89_is_yellow(self):
        """color_for(89) returns YELLOW"""
        result = self.mod.color_for(89)
        self.assertEqual(result, self.mod.YELLOW)

    def test_90_is_yellow(self):
        """color_for(90) returns YELLOW (red is strictly >90, so 90 is still yellow)"""
        result = self.mod.color_for(90)
        self.assertEqual(result, self.mod.YELLOW)

    def test_91_is_red(self):
        """color_for(91) returns RED (first value in strictly->90 zone)"""
        result = self.mod.color_for(91)
        self.assertEqual(result, self.mod.RED)

    def test_0_is_green(self):
        """color_for(0) is green"""
        result = self.mod.color_for(0)
        self.assertEqual(result, self.mod.GREEN)

    def test_100_is_red(self):
        """color_for(100) is red"""
        result = self.mod.color_for(100)
        self.assertEqual(result, self.mod.RED)


class TestIsGreen(unittest.TestCase):
    """is_green gates reset display: True only for pct < 70 (D-04)"""

    def setUp(self):
        self.mod = _load_script_module()

    def test_69_is_green(self):
        self.assertTrue(self.mod.is_green(69))

    def test_30_is_green(self):
        """fixture 5h value (30) is green"""
        self.assertTrue(self.mod.is_green(30))

    def test_70_is_not_green(self):
        """70 is the threshold — no longer green, reset time must show"""
        self.assertFalse(self.mod.is_green(70))

    def test_100_is_not_green(self):
        self.assertFalse(self.mod.is_green(100))


class TestFmtReset(unittest.TestCase):
    """fmt_reset: epoch -> LOCAL time, same-day shorthand vs weekday shorthand (LIM-04)"""

    def setUp(self):
        self.mod = _load_script_module()

    def test_same_day_no_weekday(self):
        """A same-local-day epoch yields just hour:minuteam/pm, no weekday prefix."""
        # Use today's date at some hour to guarantee same-day
        now = datetime.now()
        # Construct a datetime later today (or at least same calendar day)
        same_day = now.replace(hour=17, minute=15, second=0, microsecond=0)
        epoch = int(same_day.timestamp())
        result = self.mod.fmt_reset(epoch)
        # Should NOT contain a day name
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            self.assertNotIn(day, result)
        # Should end in am or pm
        self.assertTrue(result.endswith("am") or result.endswith("pm"),
                        f"Expected am/pm suffix, got: {result!r}")

    def test_same_day_no_leading_zero(self):
        """Same-day format has no leading zero on hour (e.g., '5:15am' not '05:15am')"""
        now = datetime.now()
        same_day = now.replace(hour=5, minute=15, second=0, microsecond=0)
        epoch = int(same_day.timestamp())
        result = self.mod.fmt_reset(epoch)
        self.assertFalse(result.startswith("0"),
                         f"Should have no leading zero, got: {result!r}")
        # hour=5 is 5 AM → '5:15am'
        self.assertEqual(result, "5:15am")

    def test_different_day_has_weekday(self):
        """A future-day epoch yields 'Www HH:MMam/pm' (abbreviated weekday prefix)."""
        # Pick an epoch far in the future (definitely not today)
        # 2099-01-01 00:00:00 UTC
        far_future_epoch = 4070908800  # 2099-01-01 00:00:00 UTC
        result = self.mod.fmt_reset(far_future_epoch)
        # Should contain a weekday abbreviation
        has_weekday = any(
            result.startswith(day)
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        )
        self.assertTrue(has_weekday, f"Expected weekday prefix, got: {result!r}")

    def test_lowercase_am_pm(self):
        """am/pm suffix is lowercase."""
        now = datetime.now()
        morning = now.replace(hour=9, minute=0, second=0, microsecond=0)
        epoch = int(morning.timestamp())
        result = self.mod.fmt_reset(epoch)
        self.assertNotIn("AM", result)
        self.assertNotIn("PM", result)

    def test_bad_epoch_returns_none_or_empty(self):
        """Out-of-range or non-numeric epoch degrades gracefully, does not raise."""
        result = self.mod.fmt_reset(None)
        # Should return None or empty string — never raise
        self.assertTrue(result is None or result == "")

    def test_negative_epoch_returns_none_or_empty(self):
        """Negative epoch (which might be valid but unusual) handles gracefully."""
        try:
            result = self.mod.fmt_reset(-99999999999999)
            self.assertTrue(result is None or isinstance(result, str))
        except Exception as e:
            self.fail(f"fmt_reset raised on extreme negative epoch: {e}")


class TestPctInt(unittest.TestCase):
    """pct_int floors consistently (matches bash cut -d. behavior), degrades on bad input."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_integer_passthrough(self):
        self.assertEqual(self.mod.pct_int(30), 30)

    def test_float_floors(self):
        self.assertEqual(self.mod.pct_int(30.9), 30)

    def test_float_string_floors(self):
        """Numeric string like '47.8' floors to 47."""
        self.assertEqual(self.mod.pct_int("47.8"), 47)

    def test_none_returns_none(self):
        self.assertIsNone(self.mod.pct_int(None))

    def test_string_non_numeric_returns_none(self):
        self.assertIsNone(self.mod.pct_int("abc"))

    def test_zero(self):
        self.assertEqual(self.mod.pct_int(0), 0)

    def test_100(self):
        self.assertEqual(self.mod.pct_int(100), 100)


# ---------------------------------------------------------------------------
# Task 2: bottom-line rendering integration
# ---------------------------------------------------------------------------

class TestBottomLineFixture(unittest.TestCase):
    """The real fixture produces exactly two lines; bottom line content verified."""

    def setUp(self):
        with open(FIXTURE, "rb") as f:
            self.fixture_bytes = f.read()
        self.fixture_data = load_fixture()

    def test_two_output_lines(self):
        """Fixture produces exactly 2 output lines."""
        result = run_script(self.fixture_bytes)
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.decode().splitlines()
        self.assertEqual(len(lines), 2, f"Expected 2 lines, got: {lines!r}")

    def test_bottom_line_has_ctx_pct(self):
        """Bottom line contains '7%' (the fixture context usage)."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        self.assertIn("7%", bottom)

    def test_bottom_line_has_bracket_bar(self):
        """Bottom line contains '[' and ']' enclosing the context bar."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        self.assertIn("[", bottom)
        self.assertIn("]", bottom)

    def test_bottom_line_bar_fill_cells(self):
        """Bar fill: floor(7*20/100) = 1 filled block + 19 empty blocks (CTX-01)."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        # Strip ANSI codes to count raw characters
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # Extract bar between first '[' and first ']'
        bar_start = stripped.index("[") + 1
        bar_end = stripped.index("]")
        bar = stripped[bar_start:bar_end]
        self.assertEqual(len(bar), 20, f"Bar should be exactly 20 chars, got {len(bar)}: {bar!r}")
        self.assertEqual(bar.count("▓"), 1, f"Expected 1 filled block, got bar: {bar!r}")
        self.assertEqual(bar.count("░"), 19, f"Expected 19 empty blocks, got bar: {bar!r}")

    def test_bottom_line_has_five_hour_glyph(self):
        """Bottom line contains the five_hour glyph (LIM-01).

        With icon_set="nerd" (default), the script renders the Nerd Font hourglass
        (U+F254, nf-fa-hourglass) instead of the Phase 2 emoji ⏳.
        """
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        # Nerd Font hourglass (U+F254) is the default; emoji ⏳ only appears when
        # icon_set="emoji" is set in the user's TOML.
        self.assertIn("", bottom)

    def test_bottom_line_has_five_hour_pct(self):
        """Bottom line contains '30%' (fixture five_hour usage, LIM-01)."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        self.assertIn("30%", bottom)

    def test_bottom_line_has_weekly_glyph(self):
        """Bottom line contains the weekly glyph (LIM-02).

        With icon_set="nerd" (default), the script renders the Nerd Font calendar
        (U+F073, nf-fa-calendar) instead of the Phase 2 emoji 🗓.
        """
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        # Nerd Font calendar (U+F073) is the default; emoji 🗓 only appears when
        # icon_set="emoji" is set in the user's TOML.
        self.assertIn("", bottom)

    def test_bottom_line_has_weekly_pct(self):
        """Bottom line contains '3%' (fixture seven_day usage, LIM-02)."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        self.assertIn("3%", bottom)

    def test_bottom_line_no_reset_time_all_green(self):
        """Fixture: all indicators green (7, 30, 3) — NO reset time on bottom line (D-04)."""
        result = run_script(self.fixture_bytes)
        bottom = result.stdout.decode().splitlines()[1]
        # Strip ANSI codes before looking for time patterns
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # Reset times look like "4:40pm" or "Mon 4:40pm" — check no colon+digits+am/pm pattern
        self.assertNotRegex(stripped, r'\d:\d{2}[ap]m',
                            "No reset time expected when all indicators are green")


class TestBottomLineSynthetic(unittest.TestCase):
    """Synthetic payloads to verify non-green reset display and degradation (D-04, D-10)."""

    def _run(self, data: dict) -> tuple[int, list[str]]:
        payload = json.dumps(data).encode()
        result = run_script(payload)
        lines = result.stdout.decode().splitlines()
        return result.returncode, lines

    def test_five_hour_nongreen_shows_reset(self):
        """five_hour=78% (yellow) → reset time appears after ⏳ indicator (LIM-03)."""
        data = load_fixture()
        data["rate_limits"]["five_hour"]["used_percentage"] = 78
        rc, lines = self._run(data)
        self.assertEqual(rc, 0)
        bottom = lines[1] if len(lines) > 1 else ""
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # Should contain a time pattern (same-day for fixture epoch ~16:40 local)
        self.assertRegex(stripped, r'\d:\d{2}[ap]m',
                         "Non-green 5h indicator should show reset time")

    def test_weekly_green_no_reset(self):
        """seven_day=3% (green) → no reset time after calendar glyph even when 5h is non-green (D-04).

        Uses Nerd Font calendar (U+F073) since icon_set defaults to 'nerd' (Phase 02.1).
        """
        data = load_fixture()
        data["rate_limits"]["five_hour"]["used_percentage"] = 78
        # seven_day stays at 3% (green)
        rc, lines = self._run(data)
        self.assertEqual(rc, 0)
        bottom = lines[1] if len(lines) > 1 else ""
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # The calendar glyph (Nerd Font U+F073, default) must be present
        # U+F073 = nf-fa-calendar (Nerd Font), the default weekly glyph
        _cal_glyph = "\uF073"
        cal_idx = stripped.find(_cal_glyph)
        self.assertGreater(cal_idx, -1, "Calendar glyph must be in bottom line")
        after_cal = stripped[cal_idx:]
        self.assertNotRegex(after_cal, r'\d:\d{2}[ap]m',
                            "Green weekly indicator must NOT show reset time")

    def test_five_hour_red_shows_reset(self):
        """five_hour=95% (red) → ⏳ indicator has a reset time (LIM-03)."""
        data = load_fixture()
        data["rate_limits"]["five_hour"]["used_percentage"] = 95
        rc, lines = self._run(data)
        self.assertEqual(rc, 0)
        bottom = lines[1] if len(lines) > 1 else ""
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        self.assertRegex(stripped, r'\d:\d{2}[ap]m',
                         "Red 5h indicator should show reset time")

    def test_missing_rate_limits_still_renders_context(self):
        """Missing rate_limits block → context bar + % still renders, exit 0 (D-10)."""
        data = load_fixture()
        del data["rate_limits"]
        rc, lines = self._run(data)
        self.assertEqual(rc, 0)
        # Should still have 2 lines (top + bottom context bar)
        self.assertGreaterEqual(len(lines), 1)
        bottom = lines[1] if len(lines) > 1 else ""
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # Context bar should still be present
        self.assertIn("7%", stripped)
        # Rate glyphs should be absent
        self.assertNotIn("⏳", stripped)
        self.assertNotIn("🗓", stripped)

    def test_missing_context_window_still_renders_rate(self):
        """Missing context_window block → rate segments still render, exit 0 (D-10).

        With icon_set='nerd' (default, Phase 02.1), rate glyphs are Nerd Font
        hourglass (U+F254) and calendar (U+F073) instead of ⏳/🗓.
        """
        data = load_fixture()
        del data["context_window"]
        rc, lines = self._run(data)
        self.assertEqual(rc, 0)
        bottom = lines[1] if len(lines) > 1 else ""
        # Nerd Font rate glyphs must be present (default icon_set="nerd")
        # U+F254 = nf-fa-hourglass; U+F073 = nf-fa-calendar
        self.assertIn("\uF254", bottom)
        self.assertIn("\uF073", bottom)
        # Context bar brackets should be absent in the bottom line
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)
        # No bar block — there should be no filled/empty bar chars
        self.assertNotIn("▓", stripped)
        self.assertNotIn("░", stripped)

    def test_empty_stdin_still_exits_zero(self):
        """Empty stdin → exit 0, no traceback (regression from skeleton)."""
        result = run_script(b"")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
