#!/usr/bin/env python3
"""
Tests for Plan 09-01: OSC 8 hyperlink foundation.

Task 1: osc8() helper + OSC 8 byte constants (TestOsc8Helper)
Task 2: links config key + _osc8_enabled() auto-detect resolver (TestOsc8Enabled)
Task 3: URL-component allowlist validators (TestUrlValidators)
"""

import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Task 1: osc8() helper
# ---------------------------------------------------------------------------

class TestOsc8Helper(unittest.TestCase):
    """Unit tests for the osc8() helper and OSC 8 byte constants."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module()

    def test_enabled_wraps_url(self):
        """osc8 with enabled=True wraps text in OSC 8 escape sequence."""
        result = self.mod.osc8("X", "https://e.com", enabled=True)
        self.assertEqual(result, "\033]8;;https://e.com\033\\X\033]8;;\033\\")

    def test_disabled_returns_text_unchanged(self):
        """osc8 with enabled=False returns text byte-for-byte unchanged."""
        result = self.mod.osc8("X", "https://e.com", enabled=False)
        self.assertEqual(result, "X")

    def test_disabled_contains_no_osc8_bytes(self):
        """Disabled path: output contains no \\x1b]8 byte sequence (LINK-03)."""
        result = self.mod.osc8("X", "https://e.com", enabled=False)
        self.assertNotIn("\x1b]8", result)

    def test_empty_url_returns_text_unchanged(self):
        """osc8 with empty url returns text unchanged even when enabled=True."""
        result = self.mod.osc8("X", "", enabled=True)
        self.assertEqual(result, "X")

    def test_none_url_returns_text_unchanged(self):
        """osc8 with None url returns text unchanged even when enabled=True."""
        result = self.mod.osc8("X", None, enabled=True)
        self.assertEqual(result, "X")

    def test_sgr_codes_preserved_inside_span(self):
        """osc8 preserves SGR codes already inside text (e.g. colored text)."""
        colored_text = "\033[31mX\033[0m"
        result = self.mod.osc8(colored_text, "https://e.com", enabled=True)
        # The colored text must appear inside the OSC 8 span
        self.assertIn(colored_text, result)
        # And the OSC 8 framing must be present
        self.assertTrue(result.startswith("\033]8;;https://e.com\033\\"))
        self.assertTrue(result.endswith("\033]8;;\033\\"))

    def test_osc8_constants_exist(self):
        """Module exposes the three _OSC8_ constants spelled with \\033."""
        self.assertTrue(hasattr(self.mod, "_OSC8_OPEN_PRE"))
        self.assertTrue(hasattr(self.mod, "_OSC8_ST"))
        self.assertTrue(hasattr(self.mod, "_OSC8_CLOSE"))
        # Verify they use octal \033 spelling (same byte as \x1b)
        self.assertEqual(self.mod._OSC8_OPEN_PRE[0], "\x1b")
        self.assertEqual(self.mod._OSC8_ST[0], "\x1b")
        self.assertEqual(self.mod._OSC8_CLOSE[0], "\x1b")


# ---------------------------------------------------------------------------
# Task 2: _osc8_enabled() resolver
# ---------------------------------------------------------------------------

# All env markers that trigger auto=True detection; we clear ALL of them for
# the "no known marker" test so a developer's real terminal doesn't leak in.
_ALL_MARKERS = {
    "TERM_PROGRAM": "",
    "WT_SESSION": "",
    "KITTY_WINDOW_ID": "",
    "VTE_VERSION": "",
    "TERMINAL_EMULATOR": "",
}


class TestOsc8Enabled(unittest.TestCase):
    """Unit tests for _osc8_enabled() tri-state config resolver."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module()

    def test_off_returns_false(self):
        """links='off' always returns False."""
        result = self.mod._osc8_enabled({"display": {"links": "off"}})
        self.assertIs(result, False)

    def test_on_returns_true(self):
        """links='on' always returns True regardless of env."""
        # Clear all env markers to confirm it's truly env-independent
        with patch.dict(os.environ, _ALL_MARKERS, clear=False):
            result = self.mod._osc8_enabled({"display": {"links": "on"}})
        self.assertIs(result, True)

    def test_auto_with_known_term_program(self):
        """links='auto' returns True when TERM_PROGRAM is an allowlisted terminal."""
        env = {"TERM_PROGRAM": "iTerm.app", **{k: "" for k in _ALL_MARKERS if k != "TERM_PROGRAM"}}
        with patch.dict(os.environ, env, clear=False):
            result = self.mod._osc8_enabled({"display": {"links": "auto"}})
        self.assertIs(result, True)

    def test_auto_without_known_marker_returns_false(self):
        """links='auto' returns False when no known terminal marker present (bias to False, D-02)."""
        with patch.dict(os.environ, _ALL_MARKERS, clear=False):
            result = self.mod._osc8_enabled({"display": {"links": "auto"}})
        self.assertIs(result, False)

    def test_empty_cfg_returns_false(self):
        """Empty config defaults to off (returns False)."""
        result = self.mod._osc8_enabled({})
        self.assertIs(result, False)

    def test_unknown_value_returns_false(self):
        """Unknown/garbage value defaults to off, mirroring _bar_preset fallback."""
        result = self.mod._osc8_enabled({"display": {"links": "garbage"}})
        self.assertIs(result, False)


# ---------------------------------------------------------------------------
# Task 3: URL-component validators
# ---------------------------------------------------------------------------

class TestUrlValidators(unittest.TestCase):
    """Unit tests for _valid_ugc() and _valid_incident_id() allowlist validators."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module()

    # --- _valid_ugc ---

    def test_ugc_forecast_zone_accepted(self):
        """Valid forecast zone code (^[A-Z]{2}Z[0-9]{3}$) is accepted and returned."""
        self.assertEqual(self.mod._valid_ugc("OKZ034"), "OKZ034")

    def test_ugc_county_code_accepted(self):
        """Valid county code (^[A-Z]{2}C[0-9]{3}$) is accepted and returned."""
        self.assertEqual(self.mod._valid_ugc("OKC109"), "OKC109")

    def test_ugc_lowercase_rejected(self):
        """Lowercase UGC code is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_ugc("okz034"))

    def test_ugc_wrong_digit_count_rejected(self):
        """UGC with wrong digit count is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_ugc("OKZ34"))

    def test_ugc_with_st_byte_rejected(self):
        """UGC containing ST byte (\\033\\\\) is rejected — must not be stripped (security)."""
        self.assertIsNone(self.mod._valid_ugc("OKZ034\033\\"))

    def test_ugc_none_rejected(self):
        """None input is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_ugc(None))

    def test_ugc_empty_rejected(self):
        """Empty string is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_ugc(""))

    # --- _valid_incident_id ---

    def test_incident_id_alnum_accepted(self):
        """Valid Statuspage hex/alnum id (^[0-9a-z]+$) is accepted and returned."""
        self.assertEqual(self.mod._valid_incident_id("abc123def"), "abc123def")

    def test_incident_id_uppercase_rejected(self):
        """Uppercase incident id is rejected (strict lowercase-only charset)."""
        self.assertIsNone(self.mod._valid_incident_id("ABC123"))

    def test_incident_id_path_traversal_rejected(self):
        """Path traversal pattern '../etc' is rejected."""
        self.assertIsNone(self.mod._valid_incident_id("../etc"))

    def test_incident_id_esc_byte_rejected(self):
        """Incident id containing ESC byte (\\x1b) is rejected (security)."""
        self.assertIsNone(self.mod._valid_incident_id("ab\x1bc"))

    def test_incident_id_empty_rejected(self):
        """Empty string is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_incident_id(""))

    def test_incident_id_none_rejected(self):
        """None input is rejected (returns None)."""
        self.assertIsNone(self.mod._valid_incident_id(None))


if __name__ == "__main__":
    unittest.main()
