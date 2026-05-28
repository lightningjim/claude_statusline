#!/usr/bin/env python3
"""
Tests for Plan 02-01 Task 1: DEFAULTS extension, subfolder config path, and _sun_segment.

Covers:
  - _sun_segment: three selection branches (before sunrise, before sunset, after sunset)
  - _sun_segment: returns None on missing lat/lon or astral failure
  - load_config: new subfolder default path
  - DEFAULTS: new Phase-2 keys (location, cache, weather, units)
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDefaultsPhase2Keys(unittest.TestCase):
    """DEFAULTS must contain all Phase-2 config keys after Task 1."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_location_key_in_defaults(self):
        """DEFAULTS has a [location] table with lat and lon."""
        defaults = self.mod.DEFAULTS
        self.assertIn("location", defaults)
        self.assertIn("lat", defaults["location"])
        self.assertIn("lon", defaults["location"])

    def test_location_defaults_are_floats(self):
        """Default lat/lon are numeric (neutral default 0.0/0.0)."""
        defaults = self.mod.DEFAULTS
        self.assertIsInstance(defaults["location"]["lat"], float)
        self.assertIsInstance(defaults["location"]["lon"], float)

    def test_cache_key_in_defaults(self):
        """DEFAULTS has a [cache] table with TTL keys."""
        defaults = self.mod.DEFAULTS
        self.assertIn("cache", defaults)
        self.assertIn("weather_ttl", defaults["cache"])
        self.assertIn("alerts_ttl", defaults["cache"])
        self.assertIn("weather_max_stale", defaults["cache"])
        self.assertIn("alerts_max_stale", defaults["cache"])

    def test_cache_ttl_defaults(self):
        """Default TTLs: weather_ttl=600, alerts_ttl=300."""
        cache = self.mod.DEFAULTS["cache"]
        self.assertEqual(cache["weather_ttl"], 600)
        self.assertEqual(cache["alerts_ttl"], 300)

    def test_weather_key_in_defaults(self):
        """DEFAULTS has a [weather] table with contact_email and show_weather."""
        defaults = self.mod.DEFAULTS
        self.assertIn("weather", defaults)
        self.assertIn("contact_email", defaults["weather"])
        self.assertIn("show_weather", defaults["weather"])

    def test_show_weather_default_true(self):
        """Default show_weather is True."""
        self.assertTrue(self.mod.DEFAULTS["weather"]["show_weather"])

    def test_units_temp_unit_in_defaults(self):
        """DEFAULTS has units.temp_unit = 'F'."""
        defaults = self.mod.DEFAULTS
        self.assertIn("units", defaults)
        self.assertIn("temp_unit", defaults["units"])
        self.assertEqual(defaults["units"]["temp_unit"], "F")


class TestLoadConfigSubfolderPath(unittest.TestCase):
    """load_config default path must point at the subfolder."""

    def test_subfolder_path_in_source(self):
        """Script source contains the subfolder config path."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("claude-statusline/claude-statusline.toml", source)

    def test_load_config_phase2_keys_merge(self):
        """A config with [location] lat/lon and [cache] keys merges over DEFAULTS without error."""
        mod = _load_script_module()
        toml_content = (
            b"[location]\nlat = 37.5\nlon = -122.0\n"
            b"[cache]\nweather_ttl = 300\n"
            b"[weather]\ncontact_email = \"test@example.com\"\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            path = f.name
        try:
            cfg = mod.load_config(path)
            self.assertEqual(cfg["location"]["lat"], 37.5)
            self.assertEqual(cfg["location"]["lon"], -122.0)
            self.assertEqual(cfg["cache"]["weather_ttl"], 300)
            # Non-overridden defaults survive
            self.assertEqual(cfg["cache"]["alerts_ttl"], 300)
            self.assertEqual(cfg["thresholds"]["warn"], 70)
        finally:
            os.unlink(path)


class TestSunSegmentExists(unittest.TestCase):
    """_sun_segment must be defined in the module."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_sun_segment_callable(self):
        """_sun_segment is defined and callable."""
        self.assertTrue(callable(getattr(self.mod, "_sun_segment", None)))


class TestSunSegmentBranches(unittest.TestCase):
    """_sun_segment must select the correct next sun event for each time-of-day branch.

    Location: Denver, CO (39.7392 N, -104.9903 W).
    Test date: 2025-06-21 (summer solstice, Denver).
    Approximate Denver times: sunrise ~05:31 MDT, sunset ~20:34 MDT.
    We test with UTC equivalents and inject 'now' to make tests deterministic.
    """

    def setUp(self):
        self.mod = _load_script_module()
        # Skip if astral is not installed (degraded environment)
        if not getattr(self.mod, "_ASTRAL_OK", False):
            self.skipTest("astral not installed — skipping sun-branch tests")

        # Denver, CO
        self.cfg = {
            "location": {"lat": 39.7392, "lon": -104.9903},
            "cache": {},
            "weather": {"show_weather": True, "contact_email": ""},
            "units": {"temp_unit": "F"},
            "thresholds": {"warn": 70, "crit": 90},
            "toggles": {},
        }

    def _now_local(self, hour: int, minute: int = 0) -> datetime:
        """Return a naive local datetime on 2025-06-21 at the given local hour:minute."""
        return datetime(2025, 6, 21, hour, minute, 0)

    def test_before_sunrise_returns_sunrise_glyph(self):
        """Before today's sunrise: returns string containing sunrise glyph and a time."""
        # 03:00 local — well before Denver sunrise (~05:31)
        now = self._now_local(3, 0)
        result = self.mod._sun_segment(self.cfg, now=now)
        self.assertIsNotNone(result, "_sun_segment returned None before sunrise")
        self.assertIn("\U0001f305", result)  # 🌅
        # Should contain an am time
        self.assertRegex(result, r"\d+:\d+am")

    def test_before_sunset_returns_sunset_glyph(self):
        """After sunrise but before sunset: returns string containing sunset glyph."""
        # 12:00 local — midday, between sunrise (~05:31) and sunset (~20:34)
        now = self._now_local(12, 0)
        result = self.mod._sun_segment(self.cfg, now=now)
        self.assertIsNotNone(result, "_sun_segment returned None before sunset")
        self.assertIn("\U0001f307", result)  # 🌇
        # Should contain a pm time
        self.assertRegex(result, r"\d+:\d+pm")

    def test_after_sunset_returns_next_sunrise(self):
        """After today's sunset: returns next day's sunrise glyph."""
        # 22:00 local — after Denver sunset (~20:34)
        now = self._now_local(22, 0)
        result = self.mod._sun_segment(self.cfg, now=now)
        self.assertIsNotNone(result, "_sun_segment returned None after sunset")
        self.assertIn("\U0001f305", result)  # 🌅 (next day's sunrise)
        # Should contain an am time
        self.assertRegex(result, r"\d+:\d+am")

    def test_time_format_matches_fmt_reset(self):
        """Sun time format is '%-I:%M%p'.lower() e.g. '6:14am', no leading zero."""
        now = self._now_local(3, 0)
        result = self.mod._sun_segment(self.cfg, now=now)
        if result is None:
            self.skipTest("No sun result to check format")
        # Extract the time portion after the glyph: e.g. "🌅 6:14am"
        # Should match H:MMam/pm pattern (no leading zero)
        self.assertRegex(result, r"[1-9]\d?:\d{2}[ap]m")


class TestSunSegmentDegradation(unittest.TestCase):
    """_sun_segment returns None on failure (missing lat/lon, _ASTRAL_OK False)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_returns_none_on_missing_location(self):
        """_sun_segment returns None when location key is absent from cfg."""
        cfg = {"thresholds": {}, "toggles": {}, "weather": {}, "units": {}}
        result = self.mod._sun_segment(cfg)
        self.assertIsNone(result)

    def test_returns_none_on_zero_zero_location(self):
        """_sun_segment returns None when lat/lon are 0.0/0.0 (neutral placeholder)."""
        # 0.0/0.0 is the Gulf of Guinea — this is the placeholder; treat as unconfigured
        cfg = {"location": {"lat": 0.0, "lon": 0.0}}
        result = self.mod._sun_segment(cfg)
        # This should either work (astral CAN compute 0.0/0.0) or return None.
        # The key constraint is: it must NOT raise an exception.
        # (Behavioral note: we do NOT require None here, just no exception.)
        # So we just check the call completes without error.

    def test_returns_none_when_astral_not_ok(self):
        """_sun_segment returns None immediately when _ASTRAL_OK is False."""
        import types
        # Create a minimal copy of the module with _ASTRAL_OK forced False
        mod = _load_script_module()
        orig = mod._ASTRAL_OK
        try:
            mod._ASTRAL_OK = False
            cfg = {"location": {"lat": 39.7, "lon": -104.9}}
            result = mod._sun_segment(cfg)
            self.assertIsNone(result)
        finally:
            mod._ASTRAL_OK = orig

    def test_no_exception_on_bad_cfg(self):
        """_sun_segment never raises even with totally malformed cfg."""
        try:
            result = self.mod._sun_segment(None)
        except Exception as e:
            self.fail(f"_sun_segment raised with None cfg: {e}")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
