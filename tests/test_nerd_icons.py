#!/usr/bin/env python3
"""
Tests for Phase 02.1 Plan 01: Nerd Font icon set scaffolding.

Covers:
  Task 1:
    - DEFAULTS contains "display" table with "icon_set" defaulting to "nerd"
    - load_config with [display] icon_set = "emoji" in TOML overrides the default
    - load_config with no config file returns icon_set == "nerd"
    - Module exposes BLUE, CYAN, MAGENTA, GRAY ANSI constants
    - _wx_color category mapping (storm/rain/snow/fog/sun + unknown)
    - _ASTRAL_OK defined; moon-phase callable exists or _ASTRAL_OK is False
    - _FILLED/_EMPTY frozen (D-02 regression guard)

  Task 2:
    - Named _WI_* glyph constants exist for all D-03 condition categories
    - Each glyph constant is a non-empty single-cell string
    - 28-slot moon-phase glyph table (_MOON_PHASE_GLYPHS) exists
    - Every moon-table entry is a non-empty single-cell string
    - Moon-index helper (_moon_phase_index) maps 0.0 -> 0, 14.0 -> 14 (full moon slot)
    - Moon-index helper clamps out-of-range input into [0, 27] without raising
"""

import importlib.util
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
# Task 1 tests
# ---------------------------------------------------------------------------

class TestIconSetConfig(unittest.TestCase):
    """D-06: icon_set config toggle defaults to 'nerd'."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_defaults_has_display_table(self):
        """DEFAULTS contains a 'display' table."""
        self.assertIn("display", self.mod.DEFAULTS)

    def test_defaults_icon_set_is_nerd(self):
        """DEFAULTS display.icon_set defaults to 'nerd'."""
        display = self.mod.DEFAULTS["display"]
        self.assertIn("icon_set", display)
        self.assertEqual(display["icon_set"], "nerd")

    def test_load_config_no_file_returns_nerd_default(self):
        """load_config with a missing path returns icon_set == 'nerd'."""
        cfg = self.mod.load_config("/nonexistent/path/to/config.toml")
        display = cfg.get("display", {})
        self.assertEqual(display.get("icon_set", "nerd"), "nerd")

    def test_load_config_emoji_override(self):
        """load_config with [display] icon_set = 'emoji' in TOML overrides default."""
        toml_content = b'[display]\nicon_set = "emoji"\n'
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as fh:
            fh.write(toml_content)
            tmp_path = fh.name
        try:
            cfg = self.mod.load_config(tmp_path)
            display = cfg.get("display", {})
            self.assertEqual(display.get("icon_set"), "emoji")
        finally:
            os.unlink(tmp_path)


class TestSemanticWeatherColors(unittest.TestCase):
    """D-08: BLUE/CYAN/MAGENTA/GRAY constants and _wx_color resolver."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_blue_constant_exists(self):
        """Module exposes BLUE as a non-empty ANSI escape."""
        self.assertTrue(hasattr(self.mod, "BLUE"))
        self.assertIsInstance(self.mod.BLUE, str)
        self.assertTrue(self.mod.BLUE.startswith("\033["))
        self.assertGreater(len(self.mod.BLUE), 0)

    def test_cyan_constant_exists(self):
        """Module exposes CYAN as a non-empty ANSI escape."""
        self.assertTrue(hasattr(self.mod, "CYAN"))
        self.assertIsInstance(self.mod.CYAN, str)
        self.assertTrue(self.mod.CYAN.startswith("\033["))

    def test_magenta_constant_exists(self):
        """Module exposes MAGENTA as a non-empty ANSI escape."""
        self.assertTrue(hasattr(self.mod, "MAGENTA"))
        self.assertIsInstance(self.mod.MAGENTA, str)
        self.assertTrue(self.mod.MAGENTA.startswith("\033["))

    def test_gray_constant_exists(self):
        """Module exposes GRAY as a non-empty ANSI escape."""
        self.assertTrue(hasattr(self.mod, "GRAY"))
        self.assertIsInstance(self.mod.GRAY, str)
        self.assertTrue(self.mod.GRAY.startswith("\033["))

    def test_wx_color_storm_is_magenta(self):
        """_wx_color('storm') returns MAGENTA."""
        self.assertEqual(self.mod._wx_color("storm"), self.mod.MAGENTA)

    def test_wx_color_rain_is_blue(self):
        """_wx_color('rain') returns BLUE."""
        self.assertEqual(self.mod._wx_color("rain"), self.mod.BLUE)

    def test_wx_color_snow_is_cyan(self):
        """_wx_color('snow') returns CYAN."""
        self.assertEqual(self.mod._wx_color("snow"), self.mod.CYAN)

    def test_wx_color_fog_is_gray(self):
        """_wx_color('fog') returns GRAY."""
        self.assertEqual(self.mod._wx_color("fog"), self.mod.GRAY)

    def test_wx_color_sun_is_yellow(self):
        """_wx_color('sun') returns YELLOW."""
        self.assertEqual(self.mod._wx_color("sun"), self.mod.YELLOW)

    def test_wx_color_unknown_is_reset(self):
        """_wx_color with unknown category returns RESET without raising."""
        result = self.mod._wx_color("some_unknown_condition_xyz")
        self.assertEqual(result, self.mod.RESET)

    def test_wx_color_never_raises(self):
        """_wx_color never raises on any input."""
        for val in ("", None, 42, [], "clear", "wind", "cold"):
            try:
                self.mod._wx_color(val)
            except Exception as exc:
                self.fail(f"_wx_color({val!r}) raised {exc!r}")


class TestAstralMoonImport(unittest.TestCase):
    """D-04: astral.moon.phase imported under _ASTRAL_OK guard."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_astral_ok_is_defined(self):
        """_ASTRAL_OK is defined as a bool."""
        self.assertTrue(hasattr(self.mod, "_ASTRAL_OK"))
        self.assertIsInstance(self.mod._ASTRAL_OK, bool)

    def test_moon_phase_callable_or_astral_not_ok(self):
        """When astral is importable, _moon_phase callable exists; else _ASTRAL_OK is False."""
        if self.mod._ASTRAL_OK:
            self.assertTrue(
                hasattr(self.mod, "_moon_phase"),
                "_ASTRAL_OK is True but _moon_phase callable not found",
            )
            self.assertTrue(callable(self.mod._moon_phase))
        else:
            # _ASTRAL_OK is False — guard-tolerant; callable may or may not exist
            pass


class TestFrozenBarChars(unittest.TestCase):
    """D-02: _FILLED/_EMPTY bar characters must not be changed."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_filled_is_frozen(self):
        """_FILLED == '▓' (Phase 3 territory — D-02)."""
        self.assertEqual(self.mod._FILLED, "▓")

    def test_empty_is_frozen(self):
        """_EMPTY == '░' (Phase 3 territory — D-02)."""
        self.assertEqual(self.mod._EMPTY, "░")


# ---------------------------------------------------------------------------
# Task 2 tests
# ---------------------------------------------------------------------------

class TestNerdFontGlyphConstants(unittest.TestCase):
    """All D-03 condition glyph constants exist as non-empty single-cell strings."""

    # Expected constant names for D-03 condition categories + day/night splits,
    # sun-event, thinking, rate-limit, and fallback.
    EXPECTED_CONSTANTS = [
        "_WI_DAY_CLEAR",
        "_WI_NIGHT_CLEAR",
        "_WI_DAY_PARTLY",
        "_WI_NIGHT_PARTLY",
        "_WI_CLOUDY",
        "_WI_RAIN",
        "_WI_RAIN_SHOWERS",
        "_WI_SNOW",
        "_WI_SLEET",
        "_WI_FREEZING_RAIN",
        "_WI_RAIN_SNOW",
        "_WI_THUNDERSTORM",
        "_WI_THUNDERSTORM_RAIN",
        "_WI_FOG",
        "_WI_WINDY",
        "_WI_SUNRISE",
        "_WI_SUNSET",
        "_NF_THINKING",
        "_NF_HOURGLASS",
        "_NF_CALENDAR",
        "_WI_FALLBACK",
    ]

    def setUp(self):
        self.mod = _load_script_module()

    def test_all_glyph_constants_exist(self):
        """Each expected glyph constant is defined on the module."""
        for name in self.EXPECTED_CONSTANTS:
            with self.subTest(constant=name):
                self.assertTrue(
                    hasattr(self.mod, name),
                    f"Module missing glyph constant: {name}",
                )

    def test_all_glyph_constants_are_nonempty_strings(self):
        """Each glyph constant is a non-empty string."""
        for name in self.EXPECTED_CONSTANTS:
            with self.subTest(constant=name):
                val = getattr(self.mod, name, None)
                self.assertIsInstance(val, str, f"{name} is not a str")
                self.assertGreater(len(val), 0, f"{name} is an empty string")

    def test_all_glyph_constants_are_single_cell(self):
        """Each glyph constant is a single Unicode code point (single-cell width)."""
        for name in self.EXPECTED_CONSTANTS:
            with self.subTest(constant=name):
                val = getattr(self.mod, name, None)
                if val is not None:
                    self.assertEqual(
                        len(val), 1,
                        f"{name} ({val!r}) has len {len(val)}, expected 1",
                    )


class TestMoonPhaseGlyphTable(unittest.TestCase):
    """D-04: 28-slot moon-phase glyph table and clamping index helper."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_moon_table_exists(self):
        """_MOON_PHASE_GLYPHS is defined on the module."""
        self.assertTrue(
            hasattr(self.mod, "_MOON_PHASE_GLYPHS"),
            "Module missing _MOON_PHASE_GLYPHS",
        )

    def test_moon_table_has_28_entries(self):
        """_MOON_PHASE_GLYPHS contains exactly 28 entries."""
        table = self.mod._MOON_PHASE_GLYPHS
        self.assertEqual(len(table), 28, f"Expected 28 entries, got {len(table)}")

    def test_moon_table_entries_are_single_cell_strings(self):
        """Every moon-table entry is a non-empty single-cell string."""
        table = self.mod._MOON_PHASE_GLYPHS
        for i, entry in enumerate(table):
            with self.subTest(index=i):
                self.assertIsInstance(entry, str, f"Entry {i} is not a str")
                self.assertEqual(len(entry), 1, f"Entry {i} ({entry!r}) is not single-cell")

    def test_moon_index_helper_exists(self):
        """_moon_phase_index is defined on the module."""
        self.assertTrue(
            hasattr(self.mod, "_moon_phase_index"),
            "Module missing _moon_phase_index",
        )

    def test_moon_index_zero_phase_returns_zero(self):
        """Phase 0.0 (new moon) maps to index 0."""
        idx = self.mod._moon_phase_index(0.0)
        self.assertEqual(idx, 0)

    def test_moon_index_14_returns_full_moon_slot(self):
        """Phase 14.0 maps to the full moon slot (index 14)."""
        idx = self.mod._moon_phase_index(14.0)
        self.assertEqual(idx, 14)

    def test_moon_index_clamps_negative(self):
        """Negative phase values clamp to 0 without raising."""
        idx = self.mod._moon_phase_index(-1.0)
        self.assertGreaterEqual(idx, 0)
        self.assertLessEqual(idx, 27)

    def test_moon_index_clamps_large(self):
        """Phase values >= 28 clamp to [0, 27] without raising."""
        idx = self.mod._moon_phase_index(99.0)
        self.assertGreaterEqual(idx, 0)
        self.assertLessEqual(idx, 27)

    def test_moon_index_always_in_range(self):
        """_moon_phase_index always returns a value in [0, 27] for any float."""
        for phase in (-100.0, -1.0, 0.0, 0.5, 7.0, 14.0, 21.0, 27.99, 28.0, 50.0, 999.9):
            with self.subTest(phase=phase):
                idx = self.mod._moon_phase_index(phase)
                self.assertGreaterEqual(idx, 0, f"phase={phase} -> idx={idx} (< 0)")
                self.assertLessEqual(idx, 27, f"phase={phase} -> idx={idx} (> 27)")

    def test_moon_index_never_raises(self):
        """_moon_phase_index never raises for any numeric or edge input."""
        for val in (0, 14, 27, 28, -1, 0.0, 27.99, float("nan"), float("inf")):
            try:
                self.mod._moon_phase_index(val)
            except Exception as exc:
                self.fail(f"_moon_phase_index({val!r}) raised {exc!r}")


if __name__ == "__main__":
    unittest.main()
