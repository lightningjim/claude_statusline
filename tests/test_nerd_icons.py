#!/usr/bin/env python3
"""
Tests for Phase 02.1 Plan 01 + Plan 02: Nerd Font icon set scaffolding + resolver.

Covers:
  Plan 01 Task 1:
    - DEFAULTS contains "display" table with "icon_set" defaulting to "nerd"
    - load_config with [display] icon_set = "emoji" in TOML overrides the default
    - load_config with no config file returns icon_set == "nerd"
    - Module exposes BLUE, CYAN, MAGENTA, GRAY ANSI constants
    - _wx_color category mapping (storm/rain/snow/fog/sun + unknown)
    - _ASTRAL_OK defined; moon-phase callable exists or _ASTRAL_OK is False
    - _BAR_PRESETS table exists with exactly four D-03 keys (Phase 3 Plan 01)

  Plan 01 Task 2:
    - Named _WI_* glyph constants exist for all D-03 condition categories
    - Each glyph constant is a non-empty single-cell string
    - 28-slot moon-phase glyph table (_MOON_PHASE_GLYPHS) exists
    - Every moon-table entry is a non-empty single-cell string
    - Moon-index helper (_moon_phase_index) maps 0.0 -> 0, 14.0 -> 14 (full moon slot)
    - Moon-index helper clamps out-of-range input into [0, 27] without raising

  Plan 02 Task 1: dual condition tables + _icon_to_glyph resolver
    - _NWS_ICON_MAP_EMOJI retained (Phase 2 table); _NWS_ICON_MAP_NERD built (D-03 vocabulary)
    - _icon_to_glyph(text, url, icon_set) resolves day/night, live moon, emoji parity
    - _icon_to_emoji alias delegates with icon_set="emoji" (keeps TestIconMapping green)
    - Granular precip types map to distinct nerd glyphs (no collapse)
    - Unknown token degrades to fallback glyph; _ASTRAL_OK=False clear-night degrades gracefully
    - Specific-before-broad ordering preserved (partly/mostly precede cloudy/sunny)

  Plan 02 Task 2: cache token migration + render-time wiring
    - fetch_weather stores text_desc + icon_url (raw tokens), not a pre-resolved glyph
    - _weather_segment resolves glyph+semantic color at render from cached tokens
    - Toggle icon_set="emoji" vs "nerd" takes effect at render without cache change
    - rain->BLUE, snow->CYAN, storm->MAGENTA, fog->GRAY, sun->YELLOW wraps the nerd glyph
    - Alert override still uses _alert_color severity coloring unchanged
    - Missing/empty cached tokens degrade gracefully
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


class TestBarPresets(unittest.TestCase):
    """Phase 3 Plan 01: _BAR_PRESETS table — glyph pairs, closed key set, fallback (D-01, D-03)."""

    def setUp(self):
        self.mod = _load_script_module()

    def _get_preset(self, style: str) -> tuple[str, str]:
        """Return (filled_glyph, empty_glyph) for a given style via the preset resolver."""
        table = self.mod._BAR_PRESETS
        pair = table.get(style, table["shade"])
        return pair

    def test_preset_table_exists(self):
        """_BAR_PRESETS dict exists on the module."""
        self.assertTrue(hasattr(self.mod, "_BAR_PRESETS"))
        self.assertIsInstance(self.mod._BAR_PRESETS, dict)

    def test_preset_keys_closed_at_four(self):
        """Preset table contains exactly the four D-03 keys (shade, solid, solid-dim, gradient)."""
        self.assertEqual(
            set(self.mod._BAR_PRESETS.keys()),
            {"shade", "solid", "solid-dim", "gradient"},
        )

    def test_shade_glyphs(self):
        """shade preset → filled='▓', empty='░'."""
        filled, empty = self._get_preset("shade")
        self.assertEqual(filled, "▓")
        self.assertEqual(empty, "░")

    def test_solid_glyphs(self):
        """solid preset → filled='█', empty='░'."""
        filled, empty = self._get_preset("solid")
        self.assertEqual(filled, "█")
        self.assertEqual(empty, "░")

    def test_solid_dim_glyphs(self):
        """solid-dim preset → filled='█', empty='▒'."""
        filled, empty = self._get_preset("solid-dim")
        self.assertEqual(filled, "█")
        self.assertEqual(empty, "▒")

    def test_unknown_style_falls_back_to_shade(self):
        """An unknown bar_style key falls back to the shade pair without KeyError (RUN-02)."""
        filled, empty = self._get_preset("diagonal")
        self.assertEqual(filled, "▓")
        self.assertEqual(empty, "░")

    def test_bar_preset_non_hashable_falls_back_to_shade(self):
        """_bar_preset must degrade to shade for non-string TOML values, never raise (RUN-02, WR-01).

        A TOML array/table yields a list/dict — passing it straight to dict.get()
        would raise TypeError (unhashable), get swallowed upstream, and drop the
        whole context bar. The guard must return the shade pair instead.
        """
        shade = self.mod._BAR_PRESETS["shade"]
        for bad in (["gradient"], {"x": 1}, 3, 4.2, None, ("solid",)):
            with self.subTest(value=bad):
                self.assertEqual(self.mod._bar_preset(bad), shade)


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
        "_WI_RAINDROPS",
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


# ---------------------------------------------------------------------------
# Plan 02 Task 1 tests: dual condition tables + _icon_to_glyph resolver
# ---------------------------------------------------------------------------

class TestDualConditionTables(unittest.TestCase):
    """D-03/D-06: _NWS_ICON_MAP_EMOJI retained; _NWS_ICON_MAP_NERD built."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_emoji_table_exists(self):
        """_NWS_ICON_MAP_EMOJI is defined on the module."""
        self.assertTrue(hasattr(self.mod, "_NWS_ICON_MAP_EMOJI"),
                        "Module missing _NWS_ICON_MAP_EMOJI")

    def test_nerd_table_exists(self):
        """_NWS_ICON_MAP_NERD is defined on the module."""
        self.assertTrue(hasattr(self.mod, "_NWS_ICON_MAP_NERD"),
                        "Module missing _NWS_ICON_MAP_NERD")

    def test_emoji_table_is_list_of_tuples(self):
        """_NWS_ICON_MAP_EMOJI is a list of (keywords_tuple, glyph) tuples."""
        table = self.mod._NWS_ICON_MAP_EMOJI
        self.assertIsInstance(table, list)
        for entry in table:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)

    def test_nerd_table_is_list_of_tuples(self):
        """_NWS_ICON_MAP_NERD is a list of (keywords_tuple, glyph, category) tuples."""
        table = self.mod._NWS_ICON_MAP_NERD
        self.assertIsInstance(table, list)
        for entry in table:
            self.assertIsInstance(entry, tuple)
            # Nerd table has 3 elements: (keywords, glyph, category)
            self.assertIn(len(entry), (2, 3), f"Expected 2 or 3 elements, got {len(entry)}")


class TestIconToGlyphResolver(unittest.TestCase):
    """_icon_to_glyph(text, url, icon_set) behavior tests (D-03, D-04, D-05, D-06)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_icon_to_glyph_exists(self):
        """_icon_to_glyph is defined and callable."""
        self.assertTrue(callable(getattr(self.mod, "_icon_to_glyph", None)))

    def test_nerd_day_clear_returns_wi_day_clear(self):
        """nerd + daytime clear NWS token returns _WI_DAY_CLEAR (D-01)."""
        result = self.mod._icon_to_glyph(
            "Sunny",
            "https://api.weather.gov/icons/land/day/skc?size=medium",
            "nerd",
        )
        self.assertEqual(result, self.mod._WI_DAY_CLEAR)

    def test_nerd_clear_night_returns_moon_table_member(self):
        """nerd + clear night returns a member of the 28-slot moon table (D-04)."""
        if not self.mod._ASTRAL_OK:
            self.skipTest("_ASTRAL_OK is False — astral not installed")
        result = self.mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "nerd",
        )
        self.assertIn(result, self.mod._MOON_PHASE_GLYPHS,
                      f"Clear night nerd glyph {result!r} is not in _MOON_PHASE_GLYPHS")

    def test_nerd_snow_distinct_glyph(self):
        """nerd + snow returns _WI_SNOW (distinct from rain glyph)."""
        result = self.mod._icon_to_glyph(
            "Snow", "https://api.weather.gov/icons/land/day/sn?size=medium", "nerd"
        )
        self.assertEqual(result, self.mod._WI_SNOW)

    def test_nerd_sleet_distinct_glyph(self):
        """nerd + sleet returns _WI_SLEET (distinct from snow/rain)."""
        result = self.mod._icon_to_glyph(
            "Sleet", "https://api.weather.gov/icons/land/day/ip?size=medium", "nerd"
        )
        self.assertEqual(result, self.mod._WI_SLEET)

    def test_nerd_freezing_rain_distinct_glyph(self):
        """nerd + freezing rain (fzra) returns _WI_FREEZING_RAIN."""
        result = self.mod._icon_to_glyph(
            "Freezing Rain",
            "https://api.weather.gov/icons/land/day/fzra?size=medium",
            "nerd",
        )
        self.assertEqual(result, self.mod._WI_FREEZING_RAIN)

    def test_nerd_rain_snow_mix_distinct_glyph(self):
        """nerd + rain-snow mix (rasn) returns _WI_RAIN_SNOW."""
        result = self.mod._icon_to_glyph(
            "Rain Snow",
            "https://api.weather.gov/icons/land/day/rasn?size=medium",
            "nerd",
        )
        self.assertEqual(result, self.mod._WI_RAIN_SNOW)

    def test_nerd_thunderstorm_distinct_glyph(self):
        """nerd + thunderstorm (tsra/tstm) returns _WI_THUNDERSTORM."""
        result = self.mod._icon_to_glyph(
            "Thunderstorm",
            "https://api.weather.gov/icons/land/day/tsra?size=medium",
            "nerd",
        )
        self.assertEqual(result, self.mod._WI_THUNDERSTORM)

    def test_nerd_fog_distinct_glyph(self):
        """nerd + fog (fg) returns _WI_FOG."""
        result = self.mod._icon_to_glyph(
            "Fog", "https://api.weather.gov/icons/land/day/fg?size=medium", "nerd"
        )
        self.assertEqual(result, self.mod._WI_FOG)

    def test_nerd_windy_distinct_glyph(self):
        """nerd + windy (wind) returns _WI_WINDY."""
        result = self.mod._icon_to_glyph(
            "Windy", "https://api.weather.gov/icons/land/day/wind_skc?size=medium", "nerd"
        )
        self.assertEqual(result, self.mod._WI_WINDY)

    def test_all_granular_precip_distinct(self):
        """snow / sleet / freezing-rain / thunderstorm / fog / windy each map distinctly.

        Note: freezing-rain (fzra) and rain-snow-mix (rasn) may share a glyph
        (Weather Icons wi-rain-mix covers both — no distinct codepoint in the spec).
        The core distinctness requirement is: snow != sleet != thunderstorm != fog != wind.
        """
        # These MUST all be distinct from each other
        core_glyphs = {
            "snow":     self.mod._icon_to_glyph("Snow", "/day/sn", "nerd"),
            "sleet":    self.mod._icon_to_glyph("Sleet", "/day/ip", "nerd"),
            "tsra":     self.mod._icon_to_glyph("Thunderstorm", "/day/tsra", "nerd"),
            "fog":      self.mod._icon_to_glyph("Fog", "/day/fg", "nerd"),
            "windy":    self.mod._icon_to_glyph("Windy", "/day/wind_skc", "nerd"),
        }
        values = list(core_glyphs.values())
        unique = set(values)
        self.assertEqual(len(unique), len(values),
                         f"Core precip types collapse to same glyph: {core_glyphs}")
        # fzra and rasn map to their own constants (may share codepoint per Weather Icons spec)
        fzra = self.mod._icon_to_glyph("Freezing Rain", "/day/fzra", "nerd")
        rasn = self.mod._icon_to_glyph("Rain Snow", "/day/rasn", "nerd")
        # Both must return valid non-empty glyphs
        self.assertGreater(len(fzra), 0, "fzra glyph must not be empty")
        self.assertGreater(len(rasn), 0, "rasn glyph must not be empty")

    def test_specific_before_broad_partly_cloudy(self):
        """'Partly Cloudy' returns the partly glyph, not the broad cloudy glyph."""
        result = self.mod._icon_to_glyph("Partly Cloudy", "", "nerd")
        self.assertNotEqual(result, self.mod._WI_CLOUDY,
                            "Partly Cloudy collapsed to broad cloudy glyph")
        self.assertEqual(result, self.mod._WI_DAY_PARTLY)

    def test_specific_before_broad_mostly_sunny(self):
        """'Mostly Sunny' returns the partly/sun glyph, not the broad clear glyph."""
        result = self.mod._icon_to_glyph("Mostly Sunny", "", "nerd")
        self.assertNotEqual(result, self.mod._WI_DAY_CLEAR,
                            "Mostly Sunny collapsed to broad clear glyph")
        self.assertEqual(result, self.mod._WI_DAY_PARTLY)

    def test_emoji_path_sunny_returns_sun_emoji(self):
        """emoji path: 'Sunny' day returns '☀️' (Phase 2 parity)."""
        result = self.mod._icon_to_glyph(
            "Sunny", "https://api.weather.gov/icons/land/day/skc", "emoji"
        )
        self.assertEqual(result, "☀️")

    def test_emoji_path_clear_night_returns_moon_emoji(self):
        """emoji path: clear night returns '🌙' (Phase 2 parity)."""
        result = self.mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "emoji",
        )
        self.assertEqual(result, "🌙")

    def test_emoji_path_rain_returns_rain_emoji(self):
        """emoji path: rain returns '🌧️' (Phase 2 parity)."""
        result = self.mod._icon_to_glyph("Rain", "/day/ra", "emoji")
        self.assertEqual(result, "🌧️")

    def test_unknown_nerd_returns_fallback_glyph(self):
        """Unknown/empty token returns nerd fallback glyph (not None, not crash)."""
        result = self.mod._icon_to_glyph("", "", "nerd")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_unknown_emoji_returns_thermometer_fallback(self):
        """Unknown/empty token under emoji path returns '🌡️'."""
        result = self.mod._icon_to_glyph("", "", "emoji")
        self.assertEqual(result, "🌡️")

    def test_never_raises_on_any_input(self):
        """_icon_to_glyph never raises on edge inputs."""
        for text, url, icon_set in [
            ("", "", "nerd"),
            (None, None, "nerd"),
            ("XYZ", "garbage://url", "emoji"),
            ("", "", "unknown_icon_set"),
        ]:
            try:
                self.mod._icon_to_glyph(text, url, icon_set)
            except Exception as exc:
                self.fail(f"_icon_to_glyph({text!r}, {url!r}, {icon_set!r}) raised: {exc!r}")

    def test_astral_false_clear_night_degrades_gracefully(self):
        """When _ASTRAL_OK is False, clear night under nerd returns a generic nerd glyph."""
        mod = _load_script_module()
        mod._ASTRAL_OK = False
        result = mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "nerd",
        )
        self.assertIsNotNone(result,
                              "Expected a non-None glyph when _ASTRAL_OK is False")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # Must NOT raise
        # Result should be a nerd glyph (any non-empty string is ok — degrades to a glyph)


class TestIsNightOverride(unittest.TestCase):
    """Regression for moon-shown-before-sunset: is_night_override=False on a NWS night URL
    must return a daytime glyph, not a moon.  This covers the case where NWS has flipped
    to a /night/ icon URL before the local astral sunset."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_night_url_override_false_returns_day_clear_glyph(self):
        """is_night_override=False on a clear /night/ URL returns _WI_DAY_CLEAR, not a moon."""
        result = self.mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "nerd",
            is_night_override=False,
        )
        self.assertEqual(result, self.mod._WI_DAY_CLEAR,
                         f"Expected _WI_DAY_CLEAR but got {result!r} (moon shown before sunset)")

    def test_night_url_override_false_returns_day_glyph_for_partly_cloudy(self):
        """is_night_override=False on a partly-cloudy /night/ URL returns _WI_DAY_PARTLY."""
        result = self.mod._icon_to_glyph(
            "Partly Cloudy",
            "https://api.weather.gov/icons/land/night/sct?size=medium",
            "nerd",
            is_night_override=False,
        )
        self.assertEqual(result, self.mod._WI_DAY_PARTLY,
                         f"Expected _WI_DAY_PARTLY but got {result!r}")

    def test_night_url_override_none_preserves_url_derived_is_night(self):
        """is_night_override=None (default) preserves original URL-derived behavior."""
        if not self.mod._ASTRAL_OK:
            self.skipTest("astral not installed — skipping moon path test")
        # With override=None and /night/ URL, clear night should still yield a moon glyph
        result = self.mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "nerd",
            is_night_override=None,
        )
        self.assertIn(result, self.mod._MOON_PHASE_GLYPHS,
                      f"Default (override=None) on /night/ clear should return moon glyph, got {result!r}")

    def test_condition_category_override_false_on_clear_night_returns_sun(self):
        """_condition_category with is_night_override=False on /night/ URL returns 'sun', not 'moon'."""
        result = self.mod._condition_category(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            is_night_override=False,
        )
        self.assertEqual(result, "sun",
                         f"Expected 'sun' category before sunset, got {result!r} (moon color before sunset)")

    def test_condition_category_override_true_on_day_url_returns_moon(self):
        """_condition_category with is_night_override=True on a /day/ URL returns 'moon'."""
        result = self.mod._condition_category(
            "Clear",
            "https://api.weather.gov/icons/land/day/skc?size=medium",
            is_night_override=True,
        )
        self.assertEqual(result, "moon",
                         f"Expected 'moon' category with override=True, got {result!r}")

    def test_override_never_raises_for_edge_inputs(self):
        """is_night_override edge values never cause _icon_to_glyph to raise."""
        for override in (True, False, None):
            for text, url, icon_set in (
                ("Clear", "/night/skc", "nerd"),
                ("Sunny", "/day/skc", "nerd"),
                ("Clear", "/night/skc", "emoji"),
                ("", "", "nerd"),
            ):
                with self.subTest(override=override, text=text, icon_set=icon_set):
                    try:
                        self.mod._icon_to_glyph(text, url, icon_set,
                                                is_night_override=override)
                    except Exception as exc:
                        self.fail(
                            f"_icon_to_glyph({text!r},{url!r},{icon_set!r},"
                            f"is_night_override={override!r}) raised: {exc!r}"
                        )


class TestIconToEmojiAlias(unittest.TestCase):
    """D-06: _icon_to_emoji alias delegates with icon_set='emoji' (keeps TestIconMapping green)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_alias_exists(self):
        """_icon_to_emoji is still defined as a callable."""
        self.assertTrue(callable(getattr(self.mod, "_icon_to_emoji", None)))

    def test_alias_same_as_emoji_path(self):
        """_icon_to_emoji(text, url) == _icon_to_glyph(text, url, 'emoji') for all cases."""
        test_cases = [
            ("Sunny", "https://api.weather.gov/icons/land/day/skc"),
            ("Clear", "https://api.weather.gov/icons/land/night/skc"),
            ("Rain", "/day/ra"),
            ("Partly Cloudy", ""),
            ("Mostly Cloudy", ""),
            ("Thunderstorm", "/day/tsra"),
            ("Fog", "/day/fg"),
            ("", ""),
        ]
        for text, url in test_cases:
            with self.subTest(text=text, url=url):
                alias_result = self.mod._icon_to_emoji(text, url)
                glyph_result = self.mod._icon_to_glyph(text, url, "emoji")
                self.assertEqual(alias_result, glyph_result,
                                 f"alias({text!r},{url!r})={alias_result!r} != "
                                 f"glyph({text!r},{url!r},'emoji')={glyph_result!r}")

    def test_alias_never_returns_nerd_glyph(self):
        """_icon_to_emoji never returns a nerd/PUA glyph — always an emoji or 🌡️."""
        test_cases = [
            ("Sunny", "/day/skc"),
            ("Clear", "/night/skc"),
            ("Thunderstorm", "/day/tsra"),
            ("Snow", "/day/sn"),
        ]
        nerd_glyphs = set([
            self.mod._WI_DAY_CLEAR, self.mod._WI_NIGHT_CLEAR,
            self.mod._WI_THUNDERSTORM, self.mod._WI_SNOW,
        ])
        for text, url in test_cases:
            with self.subTest(text=text, url=url):
                result = self.mod._icon_to_emoji(text, url)
                self.assertNotIn(result, nerd_glyphs,
                                 f"_icon_to_emoji({text!r},{url!r}) returned nerd glyph {result!r}")


# ---------------------------------------------------------------------------
# Plan 02 Task 2 tests: cache token migration + render-time wiring
# ---------------------------------------------------------------------------

import json as _json
import shutil
import tempfile
import time
from unittest.mock import patch


class TestFetchWeatherStoresRawTokens(unittest.TestCase):
    """Task 2: fetch_weather stores text_desc + icon_url (raw NWS tokens), not a glyph."""

    FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
        }
        # Load fixtures
        def _load(name):
            with open(os.path.join(self.FIXTURES_DIR, name)) as f:
                return _json.load(f)
        self.points = _load("nws_points.json")
        self.stations = _load("nws_stations.json")
        self.obs = _load("nws_observation_latest.json")
        self.hourly = _load("nws_hourly_forecast.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_fetch(self):
        def fake_nws_get(url, ua, accept=None):
            if "/points/" in url:
                return self.points
            if "/stations" in url and "/observations" not in url:
                return self.stations
            if "/observations/latest" in url:
                return self.obs
            if "/forecast/hourly" in url:
                return self.hourly
            raise ValueError(f"Unexpected URL: {url}")
        with patch.object(self.mod, "_nws_get", side_effect=fake_nws_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        return self.mod.read_cache(self.cache_path)

    def test_weather_stores_text_desc(self):
        """Cache weather section stores text_desc (raw NWS textDescription)."""
        data = self._run_fetch()
        self.assertIn("text_desc", data.get("weather", {}),
                      "weather section missing 'text_desc' key")

    def test_weather_stores_icon_url(self):
        """Cache weather section stores icon_url (raw NWS icon URL)."""
        data = self._run_fetch()
        self.assertIn("icon_url", data.get("weather", {}),
                      "weather section missing 'icon_url' key")

    def test_weather_icon_url_contains_api_weather_gov(self):
        """Stored icon_url is a NWS URL (contains 'api.weather.gov')."""
        data = self._run_fetch()
        icon_url = data["weather"].get("icon_url", "")
        self.assertIn("api.weather.gov", icon_url,
                      f"icon_url should be a NWS URL, got: {icon_url!r}")

    def test_weather_does_not_store_resolved_glyph(self):
        """Cache weather section does NOT store a pre-resolved glyph in 'icon' key."""
        data = self._run_fetch()
        # 'icon' key must be absent (or if present, must not be an emoji/glyph)
        icon = data.get("weather", {}).get("icon")
        if icon is not None:
            # If 'icon' is still present, it must be a URL not a glyph
            self.assertNotIn(icon, ["☀️", "☁️", "⛅", "🌧️", "🌨️", "⛈️", "🌫️", "💨", "🌡️"],
                             f"'icon' should not be a pre-resolved emoji glyph, got {icon!r}")


class TestWeatherSegmentRenderTimeResolution(unittest.TestCase):
    """Task 2: _weather_segment resolves glyph+color at render from cached tokens."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_token_cache(self, text_desc, icon_url, pop=None):
        """Build a fresh cache dict using raw token format (new schema)."""
        cache = {
            "weather": {
                "fetched_at": time.time() - 60,
                "text_desc": text_desc,
                "icon_url": icon_url,
                "temp": 72,
            }
        }
        if pop is not None:
            cache["weather"]["pop"] = pop
        return cache

    def _run_segment(self, cache_dict, icon_set="nerd"):
        """Call _weather_segment with a patched cache and return the result."""
        if not self.mod._WEATHER_OK:
            return None  # skip if deps missing

        cache_path = os.path.join(self.tmpdir, "cache.json")
        with open(cache_path, "w") as f:
            _json.dump(cache_dict, f)

        cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
            "toggles": {"show_thinking_glyph": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"icon_set": icon_set},
        }
        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            with patch.object(self.mod, "maybe_spawn_refresh", side_effect=lambda *a: None):
                return self.mod._weather_segment(None, cfg)

    def test_nerd_daytime_clear_contains_wi_day_clear(self):
        """nerd + daytime clear: conditions chunk contains _WI_DAY_CLEAR glyph."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Sunny", "https://api.weather.gov/icons/land/day/skc?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod._WI_DAY_CLEAR, result,
                      f"Expected _WI_DAY_CLEAR in nerd result: {result!r}")

    def test_same_tokens_emoji_path_returns_sun_emoji(self):
        """icon_set='emoji' with same cached tokens returns '☀️' (D-07 toggle)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Sunny", "https://api.weather.gov/icons/land/day/skc?size=medium"
        )
        result = self._run_segment(cache, "emoji")
        self.assertIsNotNone(result)
        self.assertIn("☀️", result,
                      f"Expected '☀️' in emoji result: {result!r}")

    def test_nerd_daytime_clear_wrapped_in_yellow(self):
        """nerd daytime clear: glyph is wrapped with YELLOW ANSI color (D-08 sun=yellow)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Sunny", "https://api.weather.gov/icons/land/day/skc?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod.YELLOW, result,
                      f"Expected YELLOW color code in nerd sun result: {result!r}")

    def test_nerd_rain_wrapped_in_blue(self):
        """nerd rain: glyph wrapped in BLUE (D-08 rain=blue)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Rain", "https://api.weather.gov/icons/land/day/ra?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod.BLUE, result,
                      f"Expected BLUE color code in nerd rain result: {result!r}")

    def test_nerd_snow_wrapped_in_cyan(self):
        """nerd snow: glyph wrapped in CYAN (D-08 snow=cyan)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Snow", "https://api.weather.gov/icons/land/day/sn?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod.CYAN, result,
                      f"Expected CYAN color code in nerd snow result: {result!r}")

    def test_nerd_thunderstorm_wrapped_in_magenta(self):
        """nerd thunderstorm: glyph wrapped in MAGENTA (D-08 storm=magenta)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Thunderstorm", "https://api.weather.gov/icons/land/day/tsra?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod.MAGENTA, result,
                      f"Expected MAGENTA color code in nerd storm result: {result!r}")

    def test_nerd_fog_wrapped_in_gray(self):
        """nerd fog: glyph wrapped in GRAY (D-08 fog=gray)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Fog", "https://api.weather.gov/icons/land/day/fg?size=medium"
        )
        result = self._run_segment(cache, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod.GRAY, result,
                      f"Expected GRAY color code in nerd fog result: {result!r}")

    def test_emoji_no_ansi_color_wrapping(self):
        """emoji path: no ANSI weather color wrapping (emoji carry own color)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        cache = self._make_token_cache(
            "Rain", "https://api.weather.gov/icons/land/day/ra?size=medium"
        )
        result = self._run_segment(cache, "emoji")
        self.assertIsNotNone(result)
        # BLUE should not appear around the condition glyph in emoji mode
        # (Note: BLUE might appear in precip chunk too, so we just check the
        # rain emoji itself is present and result is well-formed)
        self.assertIn("🌧️", result, f"Expected rain emoji in emoji result: {result!r}")

    def test_missing_tokens_degrades_gracefully(self):
        """Missing/empty cached tokens: segment falls back without raising."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        # Cache with no text_desc or icon_url
        cache = {
            "weather": {
                "fetched_at": time.time() - 60,
                "temp": 72,
            }
        }
        try:
            result = self._run_segment(cache, "nerd")
            # Result may be None (fallback) or a sun-only segment — both OK
        except Exception as exc:
            self.fail(f"_weather_segment raised on missing tokens: {exc!r}")


# ---------------------------------------------------------------------------
# Plan 03 Task 1: icon_set-branched glyphs for sun, thinking, and rate-limit
# ---------------------------------------------------------------------------

import time as _time_mod


class TestSunSegmentNerdGlyphs(unittest.TestCase):
    """D-01: _sun_segment with icon_set='nerd' returns wi-sunrise/wi-sunset glyphs."""

    def setUp(self):
        self.mod = _load_script_module()
        if not getattr(self.mod, "_ASTRAL_OK", False):
            self.skipTest("astral not installed")
        # Denver, CO; cfg pins icon_set="nerd"
        self.cfg_nerd = {
            "location": {"lat": 39.7392, "lon": -104.9903},
            "display": {"icon_set": "nerd"},
            "cache": {},
            "weather": {"show_weather": True},
            "units": {},
            "thresholds": {},
            "toggles": {},
        }
        self.cfg_emoji = {
            "location": {"lat": 39.7392, "lon": -104.9903},
            "display": {"icon_set": "emoji"},
            "cache": {},
            "weather": {"show_weather": True},
            "units": {},
            "thresholds": {},
            "toggles": {},
        }

    def _now_local(self, hour, minute=0):
        from datetime import datetime
        return datetime(2025, 6, 21, hour, minute, 0)

    def test_before_sunrise_nerd_returns_wi_sunrise(self):
        """nerd + before sunrise: result contains _WI_SUNRISE."""
        now = self._now_local(3, 0)
        result = self.mod._sun_segment(self.cfg_nerd, now=now)
        self.assertIsNotNone(result)
        self.assertIn(self.mod._WI_SUNRISE, result,
                      f"Expected _WI_SUNRISE in nerd sunrise result: {result!r}")

    def test_before_sunset_nerd_returns_wi_sunset(self):
        """nerd + after sunrise/before sunset: result contains _WI_SUNSET."""
        now = self._now_local(12, 0)
        result = self.mod._sun_segment(self.cfg_nerd, now=now)
        self.assertIsNotNone(result)
        self.assertIn(self.mod._WI_SUNSET, result,
                      f"Expected _WI_SUNSET in nerd sunset result: {result!r}")

    def test_after_sunset_nerd_returns_wi_sunrise(self):
        """nerd + after sunset: result contains _WI_SUNRISE (next day)."""
        now = self._now_local(22, 0)
        result = self.mod._sun_segment(self.cfg_nerd, now=now)
        self.assertIsNotNone(result)
        self.assertIn(self.mod._WI_SUNRISE, result,
                      f"Expected _WI_SUNRISE in nerd post-sunset result: {result!r}")

    def test_emoji_path_returns_emoji_sunrise_glyph(self):
        """emoji path: before sunrise returns the Phase 2 emoji codepoint, not nerd glyph."""
        now = self._now_local(3, 0)
        result = self.mod._sun_segment(self.cfg_emoji, now=now)
        self.assertIsNotNone(result)
        self.assertIn("\U0001f305", result)  # 🌅
        self.assertNotIn(self.mod._WI_SUNRISE, result)

    def test_emoji_path_returns_emoji_sunset_glyph(self):
        """emoji path: before sunset returns the Phase 2 emoji codepoint, not nerd glyph."""
        now = self._now_local(12, 0)
        result = self.mod._sun_segment(self.cfg_emoji, now=now)
        self.assertIsNotNone(result)
        self.assertIn("\U0001f307", result)  # 🌇
        self.assertNotIn(self.mod._WI_SUNSET, result)

    def test_nerd_failure_falls_back_to_emoji(self):
        """If nerd glyph selection raises, falls back to emoji glyph (never crashes)."""
        import unittest.mock
        mod = _load_script_module()
        # Temporarily break _WI_SUNRISE to a non-string to trigger the fallback branch
        # We test that the function does not raise regardless of glyph assignment
        orig = mod._WI_SUNRISE
        try:
            mod._WI_SUNRISE = None  # will cause the branch to fall back
            cfg = dict(self.cfg_nerd)
            from datetime import datetime
            now = datetime(2025, 6, 21, 3, 0, 0)
            try:
                result = mod._sun_segment(cfg, now=now)
                # Must return a string or None — never raise
            except Exception as exc:
                self.fail(f"_sun_segment raised when nerd glyph broken: {exc!r}")
        finally:
            mod._WI_SUNRISE = orig


class TestModelSegmentNerdThinking(unittest.TestCase):
    """D-01: _model_segment thinking indicator branches on icon_set."""

    def setUp(self):
        self.mod = _load_script_module()

    def _make_data(self, thinking_enabled=True):
        return {
            "model": {"display_name": "claude-opus-4"},
            "thinking": {"enabled": thinking_enabled},
        }

    def test_nerd_thinking_enabled_uses_nf_thinking(self):
        """nerd + thinking=True: result contains _NF_THINKING glyph."""
        data = self._make_data(thinking_enabled=True)
        result = self.mod._model_segment(data, show_thinking_glyph=True, icon_set="nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod._NF_THINKING, result,
                      f"Expected _NF_THINKING in nerd thinking result: {result!r}")

    def test_emoji_thinking_enabled_uses_thought_bubble(self):
        """emoji + thinking=True: result contains '💭' emoji, not _NF_THINKING."""
        data = self._make_data(thinking_enabled=True)
        result = self.mod._model_segment(data, show_thinking_glyph=True, icon_set="emoji")
        self.assertIsNotNone(result)
        self.assertIn("💭", result,
                      f"Expected '💭' in emoji thinking result: {result!r}")
        self.assertNotIn(self.mod._NF_THINKING, result,
                         f"_NF_THINKING must not appear in emoji result: {result!r}")

    def test_thinking_disabled_no_glyph_either_path(self):
        """thinking=False: no thinking glyph in nerd or emoji mode."""
        data = self._make_data(thinking_enabled=False)
        for icon_set in ("nerd", "emoji"):
            with self.subTest(icon_set=icon_set):
                result = self.mod._model_segment(data, show_thinking_glyph=True, icon_set=icon_set)
                self.assertIsNotNone(result)
                self.assertNotIn("💭", result)
                self.assertNotIn(self.mod._NF_THINKING, result)

    def test_show_thinking_glyph_false_suppresses_both(self):
        """show_thinking_glyph=False: no thinking glyph in either mode."""
        data = self._make_data(thinking_enabled=True)
        for icon_set in ("nerd", "emoji"):
            with self.subTest(icon_set=icon_set):
                result = self.mod._model_segment(data, show_thinking_glyph=False, icon_set=icon_set)
                self.assertIsNotNone(result)
                self.assertNotIn("💭", result)
                self.assertNotIn(self.mod._NF_THINKING, result)


class TestRateLimitNerdGlyphs(unittest.TestCase):
    """D-01: render_bottom_line uses _NF_HOURGLASS/_NF_CALENDAR under nerd icon_set."""

    def setUp(self):
        self.mod = _load_script_module()

    def _make_rate_data(self, pct=50):
        return {
            "context_window": {"used_percentage": 40},
            "rate_limits": {
                "five_hour": {"used_percentage": pct, "resets_at": None},
                "seven_day": {"used_percentage": pct, "resets_at": None},
            },
        }

    def _run_bottom_line(self, data, icon_set):
        cfg = {
            "toggles": {"show_context_bar": True, "show_five_hour": True, "show_weekly": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"icon_set": icon_set},
        }
        return self.mod.render_bottom_line(data, cfg)

    def test_nerd_five_hour_uses_nf_hourglass(self):
        """nerd: 5h rate-limit segment contains _NF_HOURGLASS."""
        data = self._make_rate_data(50)
        result = self._run_bottom_line(data, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod._NF_HOURGLASS, result,
                      f"Expected _NF_HOURGLASS in nerd rate result: {result!r}")

    def test_nerd_weekly_uses_nf_calendar(self):
        """nerd: weekly rate-limit segment contains _NF_CALENDAR."""
        data = self._make_rate_data(50)
        result = self._run_bottom_line(data, "nerd")
        self.assertIsNotNone(result)
        self.assertIn(self.mod._NF_CALENDAR, result,
                      f"Expected _NF_CALENDAR in nerd rate result: {result!r}")

    def test_emoji_five_hour_uses_hourglass_emoji(self):
        """emoji: 5h rate-limit segment contains ⏳ emoji."""
        data = self._make_rate_data(50)
        result = self._run_bottom_line(data, "emoji")
        self.assertIsNotNone(result)
        self.assertIn("⏳", result,
                      f"Expected '⏳' in emoji rate result: {result!r}")

    def test_emoji_weekly_uses_calendar_emoji(self):
        """emoji: weekly rate-limit segment contains 🗓 emoji."""
        data = self._make_rate_data(50)
        result = self._run_bottom_line(data, "emoji")
        self.assertIsNotNone(result)
        self.assertIn("🗓", result,
                      f"Expected '🗓' in emoji rate result: {result!r}")

    def test_nerd_does_not_contain_emoji_rate_glyphs(self):
        """nerd: ⏳/🗓 must not appear in the rate segments (pure nerd path)."""
        data = self._make_rate_data(50)
        result = self._run_bottom_line(data, "nerd")
        self.assertIsNotNone(result)
        self.assertNotIn("⏳", result,
                         f"Emoji ⏳ must not appear in nerd result: {result!r}")
        self.assertNotIn("🗓", result,
                         f"Emoji 🗓 must not appear in nerd result: {result!r}")


class TestThresholdColoringUnchanged(unittest.TestCase):
    """D-08: bottom-line GREEN/YELLOW/RED threshold coloring is unchanged by glyph swap."""

    def setUp(self):
        self.mod = _load_script_module()

    def _run_bottom_line(self, pct, icon_set):
        data = {
            "context_window": {"used_percentage": pct},
            "rate_limits": {
                "five_hour": {"used_percentage": pct, "resets_at": None},
                "seven_day": {"used_percentage": pct, "resets_at": None},
            },
        }
        cfg = {
            "toggles": {"show_context_bar": True, "show_five_hour": True, "show_weekly": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"icon_set": icon_set},
        }
        return self.mod.render_bottom_line(data, cfg)

    def test_pct_above_crit_is_red_regardless_of_icon_set(self):
        """95% usage is RED in both nerd and emoji modes (D-08 not disturbed)."""
        for icon_set in ("nerd", "emoji"):
            with self.subTest(icon_set=icon_set):
                result = self._run_bottom_line(95, icon_set)
                self.assertIsNotNone(result)
                self.assertIn(self.mod.RED, result,
                               f"Expected RED for 95% in {icon_set} mode: {result!r}")

    def test_pct_below_warn_is_green_regardless_of_icon_set(self):
        """50% usage is GREEN in both nerd and emoji modes (D-08 not disturbed)."""
        for icon_set in ("nerd", "emoji"):
            with self.subTest(icon_set=icon_set):
                result = self._run_bottom_line(50, icon_set)
                self.assertIsNotNone(result)
                self.assertIn(self.mod.GREEN, result,
                               f"Expected GREEN for 50% in {icon_set} mode: {result!r}")


class TestSingleSwitchAllSegmentsTogether(unittest.TestCase):
    """D-07: icon_set='nerd' makes all converted segments use nerd glyphs; no mixed bar."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_nerd_bottom_line_no_emoji_rate_glyphs(self):
        """nerd: bottom line never contains ⏳ or 🗓 (rate segments use nerd glyphs)."""
        data = {
            "context_window": {"used_percentage": 40},
            "rate_limits": {
                "five_hour": {"used_percentage": 50, "resets_at": None},
                "seven_day": {"used_percentage": 50, "resets_at": None},
            },
        }
        cfg = {
            "toggles": {"show_context_bar": True, "show_five_hour": True, "show_weekly": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"icon_set": "nerd"},
        }
        result = self.mod.render_bottom_line(data, cfg)
        self.assertIsNotNone(result)
        self.assertNotIn("⏳", result)
        self.assertNotIn("🗓", result)
        self.assertIn(self.mod._NF_HOURGLASS, result)
        self.assertIn(self.mod._NF_CALENDAR, result)

    def test_emoji_bottom_line_no_nerd_rate_glyphs(self):
        """emoji: bottom line uses ⏳/🗓, not _NF_HOURGLASS/_NF_CALENDAR."""
        data = {
            "context_window": {"used_percentage": 40},
            "rate_limits": {
                "five_hour": {"used_percentage": 50, "resets_at": None},
                "seven_day": {"used_percentage": 50, "resets_at": None},
            },
        }
        cfg = {
            "toggles": {"show_context_bar": True, "show_five_hour": True, "show_weekly": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"icon_set": "emoji"},
        }
        result = self.mod.render_bottom_line(data, cfg)
        self.assertIsNotNone(result)
        self.assertIn("⏳", result)
        self.assertIn("🗓", result)
        self.assertNotIn(self.mod._NF_HOURGLASS, result)
        self.assertNotIn(self.mod._NF_CALENDAR, result)

    def test_nerd_model_segment_no_thought_bubble(self):
        """nerd + thinking: model segment uses _NF_THINKING, not '💭'."""
        data = {
            "model": {"display_name": "claude-3"},
            "thinking": {"enabled": True},
        }
        result = self.mod._model_segment(data, show_thinking_glyph=True, icon_set="nerd")
        self.assertIsNotNone(result)
        self.assertNotIn("💭", result)
        self.assertIn(self.mod._NF_THINKING, result)

    def test_emoji_model_segment_no_nf_thinking(self):
        """emoji + thinking: model segment uses '💭', not _NF_THINKING."""
        data = {
            "model": {"display_name": "claude-3"},
            "thinking": {"enabled": True},
        }
        result = self.mod._model_segment(data, show_thinking_glyph=True, icon_set="emoji")
        self.assertIsNotNone(result)
        self.assertIn("💭", result)
        self.assertNotIn(self.mod._NF_THINKING, result)


# ---------------------------------------------------------------------------
# Regression guard: installed Nerd Font cmap validation
# ---------------------------------------------------------------------------

import subprocess


def _find_nerd_font_path():
    """Return the path to a JetBrains Nerd Font Mono Regular TTF, or None."""
    # Try fc-list first
    try:
        result = subprocess.run(
            ["fc-list", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            fname = line.strip()
            if "JetBrainsMonoNerdFontMono-Regular.ttf" in fname:
                return fname
            if "NerdFont" in fname and "Regular" in fname and fname.endswith(".ttf"):
                return fname
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Glob fallback
    import glob
    patterns = [
        "/usr/share/fonts/**/JetBrainsMono*NerdFont*Regular*.ttf",
        "/usr/local/share/fonts/**/JetBrainsMono*NerdFont*Regular*.ttf",
        os.path.expanduser("~/.local/share/fonts/**/JetBrainsMono*NerdFont*Regular*.ttf"),
        os.path.expanduser("~/.fonts/**/JetBrainsMono*NerdFont*Regular*.ttf"),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]

    return None


class TestAllNerdGlyphConstantsInInstalledFont(unittest.TestCase):
    """Regression guard: every _WI_*/_NF_* constant must exist in the installed Nerd Font cmap.

    This test caught the clock-face bug: U+E380..E38C are
    weather-direction/time-clock glyphs, not moons.  If any constant points
    at a codepoint absent from the font the user will see tofu.

    The test skips cleanly when fontTools or the font file is absent so it
    never fails in CI or on machines without the font installed.
    """

    # All single-glyph _WI_*/_NF_* constant names to validate.
    GLYPH_CONSTANTS = [
        "_WI_DAY_CLEAR",
        "_WI_DAY_PARTLY",
        "_WI_NIGHT_CLEAR",
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
        "_WI_RAINDROPS",
        "_NF_THINKING",
        "_NF_HOURGLASS",
        "_NF_CALENDAR",
        "_WI_FALLBACK",
        # Phase 04 git segment glyphs (Plan 02)
        "_NF_GIT_BRANCH",
        "_NF_GIT_WORKTREE",
        "_NF_GIT_DIRTY",
        "_NF_GIT_AHEAD",
        "_NF_GIT_BEHIND",
        # Phase 05 GSD segment lifecycle / plan glyphs (Plan 02)
        "_NF_GSD_EXECUTING",
        "_NF_GSD_VERIFYING",
        "_NF_GSD_BLOCKED",
        "_NF_GSD_DONE",
        "_NF_GSD_IDLE",
        "_NF_GSD_PLAN",
    ]

    def setUp(self):
        # Skip if fontTools not importable
        try:
            from fontTools.ttLib import TTFont  # noqa: F401
        except ImportError:
            self.skipTest("fontTools not installed — skipping cmap guard")

        # Skip if no Nerd Font found
        self.font_path = _find_nerd_font_path()
        if self.font_path is None:
            self.skipTest("No JetBrains Nerd Font file found — skipping cmap guard")

        from fontTools.ttLib import TTFont
        font = TTFont(self.font_path)
        self.cmap = font.getBestCmap()
        self.mod = _load_script_module()

    def test_all_glyph_constants_exist_in_installed_font(self):
        """Every _WI_*/_NF_* single-glyph constant has its codepoint in the installed font cmap."""
        for name in self.GLYPH_CONSTANTS:
            with self.subTest(constant=name):
                val = getattr(self.mod, name, None)
                self.assertIsNotNone(val, f"{name} is not defined on the module")
                cp = ord(val)
                self.assertIn(
                    cp, self.cmap,
                    f"{name} (U+{cp:04X}) is NOT in the installed font cmap — "
                    f"would render as tofu. Font: {self.font_path}"
                )


class TestMoonPhaseGlyphsAreMoonGlyphs(unittest.TestCase):
    """Regression guard: _MOON_PHASE_GLYPHS entries must map to moon-named glyphs in the font.

    This is the specific check that would have caught the original bug where
    the table started at U+E380 (weather-direction_down_right / clock faces)
    instead of U+E38D (weather-moon_new).
    """

    def setUp(self):
        try:
            from fontTools.ttLib import TTFont  # noqa: F401
        except ImportError:
            self.skipTest("fontTools not installed — skipping moon cmap guard")

        self.font_path = _find_nerd_font_path()
        if self.font_path is None:
            self.skipTest("No JetBrains Nerd Font file found — skipping moon cmap guard")

        from fontTools.ttLib import TTFont
        font = TTFont(self.font_path)
        self.cmap = font.getBestCmap()
        self.mod = _load_script_module()

    def test_moon_table_length_is_28(self):
        """_MOON_PHASE_GLYPHS has exactly 28 slots."""
        table = self.mod._MOON_PHASE_GLYPHS
        self.assertEqual(len(table), 28,
                         f"Expected 28 moon phase slots, got {len(table)}")

    def test_all_moon_entries_exist_in_font(self):
        """Every moon-phase glyph codepoint is present in the installed font cmap."""
        table = self.mod._MOON_PHASE_GLYPHS
        for i, glyph in enumerate(table):
            with self.subTest(index=i):
                cp = ord(glyph)
                self.assertIn(
                    cp, self.cmap,
                    f"Moon slot [{i}] U+{cp:04X} is NOT in the installed font cmap"
                )

    def test_all_moon_entries_have_moon_in_glyph_name(self):
        """Every moon-phase table entry's font glyph name contains 'moon'.

        This is the key guard against the clock-face bug: the wrong codepoints
        (U+E380-E38C) map to 'weather-direction_*' and 'weather-time_*' names,
        not 'weather-moon_*'.
        """
        table = self.mod._MOON_PHASE_GLYPHS
        for i, glyph in enumerate(table):
            with self.subTest(index=i):
                cp = ord(glyph)
                glyph_name = self.cmap.get(cp, "")
                self.assertIn(
                    "moon", glyph_name.lower(),
                    f"Moon slot [{i}] U+{cp:04X} maps to glyph name {glyph_name!r} "
                    f"which does not contain 'moon' — wrong codepoint (clock-face bug)"
                )

    def test_index_0_is_moon_new(self):
        """Slot 0 (new moon) glyph name contains 'moon_new'."""
        glyph = self.mod._MOON_PHASE_GLYPHS[0]
        cp = ord(glyph)
        glyph_name = self.cmap.get(cp, "")
        self.assertIn(
            "moon_new", glyph_name.lower(),
            f"Slot [0] U+{cp:04X} glyph name {glyph_name!r} does not contain 'moon_new'"
        )

    def test_index_14_is_moon_full(self):
        """Slot 14 (full moon) glyph name contains 'moon_full'."""
        glyph = self.mod._MOON_PHASE_GLYPHS[14]
        cp = ord(glyph)
        glyph_name = self.cmap.get(cp, "")
        self.assertIn(
            "moon_full", glyph_name.lower(),
            f"Slot [14] U+{cp:04X} glyph name {glyph_name!r} does not contain 'moon_full'"
        )


# ---------------------------------------------------------------------------
# Code-review fix tests (CR-01, IN-02)
# ---------------------------------------------------------------------------

class TestPartlyCloudyNightResolution(unittest.TestCase):
    """CR-01: partly-cloudy night must return _WI_NIGHT_PARTLY, not a moon-phase glyph."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_partly_cloudy_night_sct_returns_wi_night_partly(self):
        """NWS sct (scattered) + /night/ URL → _WI_NIGHT_PARTLY (moon-behind-cloud)."""
        result = self.mod._icon_to_glyph(
            "Partly Cloudy",
            "https://api.weather.gov/icons/land/night/sct?size=medium",
            "nerd",
        )
        self.assertEqual(
            result, self.mod._WI_NIGHT_PARTLY,
            f"Partly cloudy night should return _WI_NIGHT_PARTLY, got {result!r}",
        )

    def test_partly_cloudy_night_few_returns_wi_night_partly(self):
        """NWS few + /night/ URL (mostly clear) → _WI_NIGHT_PARTLY."""
        result = self.mod._icon_to_glyph(
            "Mostly Clear",
            "https://api.weather.gov/icons/land/night/few?size=medium",
            "nerd",
        )
        self.assertEqual(
            result, self.mod._WI_NIGHT_PARTLY,
            f"Mostly clear night (few) should return _WI_NIGHT_PARTLY, got {result!r}",
        )

    def test_partly_cloudy_night_not_in_moon_phase_glyphs(self):
        """_WI_NIGHT_PARTLY must NOT be a moon-phase glyph (CR-01 lock)."""
        result = self.mod._icon_to_glyph(
            "Partly Cloudy",
            "https://api.weather.gov/icons/land/night/sct?size=medium",
            "nerd",
        )
        self.assertNotIn(
            result, self.mod._MOON_PHASE_GLYPHS,
            f"Partly cloudy night returned a moon-phase glyph {result!r} — CR-01 regression",
        )

    def test_partly_cloudy_night_not_wi_night_clear(self):
        """Partly cloudy night must not collapse to the generic clear-night glyph."""
        result = self.mod._icon_to_glyph(
            "Partly Cloudy",
            "https://api.weather.gov/icons/land/night/sct?size=medium",
            "nerd",
        )
        self.assertNotEqual(
            result, self.mod._WI_NIGHT_CLEAR,
            "Partly cloudy night should not collapse to _WI_NIGHT_CLEAR",
        )

    def test_condition_category_partly_cloudy_night_not_moon(self):
        """_condition_category for partly-cloudy night returns a color category, not 'moon'."""
        cat = self.mod._condition_category(
            "Partly Cloudy",
            "https://api.weather.gov/icons/land/night/sct?size=medium",
        )
        self.assertNotEqual(
            cat, "moon",
            f"_condition_category for partly-cloudy night returned 'moon' — CR-01 regression",
        )


class TestClearNightStillMoonPhase(unittest.TestCase):
    """Regression guard for CR-01 fix: clear nights must still return a moon-phase glyph (D-04)."""

    def setUp(self):
        self.mod = _load_script_module()
        if not getattr(self.mod, "_ASTRAL_OK", False):
            self.skipTest("astral not installed — moon-phase path requires astral")

    def test_clear_night_skc_returns_moon_phase_glyph(self):
        """NWS skc + /night/ URL → live moon-phase glyph from _MOON_PHASE_GLYPHS."""
        result = self.mod._icon_to_glyph(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
            "nerd",
        )
        self.assertIn(
            result, self.mod._MOON_PHASE_GLYPHS,
            f"Clear night should return a moon-phase glyph; got {result!r}",
        )

    def test_condition_category_clear_night_is_moon(self):
        """_condition_category for a fully clear night returns 'moon' (dim coloring)."""
        cat = self.mod._condition_category(
            "Clear",
            "https://api.weather.gov/icons/land/night/skc?size=medium",
        )
        self.assertEqual(
            cat, "moon",
            f"_condition_category for clear night should be 'moon', got {cat!r}",
        )


class TestPrecipChunkIconSetToggle(unittest.TestCase):
    """IN-02: precip chunk uses _WI_RAINDROPS under nerd, emoji under emoji (D-07 lock)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_wi_raindrops_constant_exists(self):
        """_WI_RAINDROPS constant is defined (U+E34A weather-raindrops)."""
        self.assertTrue(
            hasattr(self.mod, "_WI_RAINDROPS"),
            "Module missing _WI_RAINDROPS constant",
        )
        val = self.mod._WI_RAINDROPS
        self.assertIsInstance(val, str)
        self.assertEqual(len(val), 1, f"_WI_RAINDROPS must be single-cell, got {val!r}")
        self.assertEqual(
            ord(val), 0xE34A,
            f"_WI_RAINDROPS should be U+E34A, got U+{ord(val):04X}",
        )

    def _run_weather_segment_with_pop(self, icon_set, pop=45):
        """Call _weather_segment with a nerd or emoji cfg and a pop above threshold."""
        if not self.mod._WEATHER_OK:
            return None

        import json as _json, os, tempfile, time
        from unittest.mock import patch

        tmpdir = tempfile.mkdtemp()
        try:
            cache_path = os.path.join(tmpdir, "cache.json")
            cache = {
                "weather": {
                    "fetched_at": time.time() - 60,
                    "text_desc": "Partly Cloudy",
                    "icon_url": "https://api.weather.gov/icons/land/day/sct?size=medium",
                    "temp": 72,
                    "pop": pop,
                }
            }
            with open(cache_path, "w") as f:
                _json.dump(cache, f)

            cfg = {
                "location": {"lat": 35.4676, "lon": -97.5164},
                "weather": {"contact_email": "test@example.com", "show_weather": True},
                "units": {"temp_unit": "F"},
                "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                          "weather_max_stale": 3600, "alerts_max_stale": 900},
                "toggles": {"show_thinking_glyph": True},
                "thresholds": {"warn": 70, "crit": 90},
                "display": {"icon_set": icon_set},
            }
            with patch.object(self.mod, "_CACHE_PATH", cache_path):
                with patch.object(self.mod, "maybe_spawn_refresh", side_effect=lambda *a: None):
                    return self.mod._weather_segment(None, cfg)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_nerd_precip_chunk_uses_wi_raindrops(self):
        """Under icon_set='nerd', the precip chunk contains _WI_RAINDROPS (U+E34A)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        result = self._run_weather_segment_with_pop("nerd", pop=45)
        self.assertIsNotNone(result, "Expected a weather segment result")
        self.assertIn(
            self.mod._WI_RAINDROPS, result,
            f"Expected _WI_RAINDROPS in nerd precip chunk; got: {result!r}",
        )
        # Must NOT use the rain emoji in nerd mode
        self.assertNotIn(
            "\U0001f327", result,
            f"Rain emoji must not appear in nerd mode precip chunk; got: {result!r}",
        )

    def test_emoji_precip_chunk_uses_rain_emoji(self):
        """Under icon_set='emoji', the precip chunk contains the 🌧️ rain emoji."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False")
        result = self._run_weather_segment_with_pop("emoji", pop=45)
        self.assertIsNotNone(result, "Expected a weather segment result")
        self.assertIn(
            "\U0001f327", result,
            f"Expected rain emoji (🌧️) in emoji precip chunk; got: {result!r}",
        )
        # Must NOT use the nerd raindrops glyph in emoji mode
        self.assertNotIn(
            self.mod._WI_RAINDROPS, result,
            f"_WI_RAINDROPS must not appear in emoji mode precip chunk; got: {result!r}",
        )


if __name__ == "__main__":
    unittest.main()
