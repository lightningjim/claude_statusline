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
# Plan 09-04 Task 3: VTE version gate (WR-01) + JetBrains doc comment (WR-02)
# ---------------------------------------------------------------------------
# OSC 8 landed in VTE 0.50 (VTE_VERSION == 5000).  Under links=auto, the VTE
# branch must return True only for VTE_VERSION >= 5000; pre-5000, empty, or
# non-numeric values bias to False (D-02) and must never raise (T-09-05).
# JetBrains branch is unchanged (WR-02: cannot distinguish legacy/reworked JediTerm).

class TestOsc8EnabledVteGate(unittest.TestCase):
    """VTE_VERSION >= 5000 gate under links=auto (WR-01 / GAP-09-B)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module()

    # Clear all markers except the one under test so a real developer terminal
    # env does not leak into these isolated assertions (mirrors the existing
    # auto+no-markers pattern in TestOsc8Enabled).
    _OTHER_MARKERS = {
        "TERM_PROGRAM": "",
        "WT_SESSION": "",
        "KITTY_WINDOW_ID": "",
        "TERMINAL_EMULATOR": "",
    }

    def _run_auto(self, env_patch):
        """Run _osc8_enabled(links=auto) with env_patch merged over cleared markers."""
        full_env = {**self._OTHER_MARKERS, **env_patch}
        with patch.dict(os.environ, full_env, clear=False):
            return self.mod._osc8_enabled({"display": {"links": "auto"}})

    def test_vte_5000_returns_true(self):
        """VTE_VERSION='5000' (OSC 8 first shipped) → True."""
        result = self._run_auto({"VTE_VERSION": "5000"})
        self.assertIs(result, True,
                      "VTE_VERSION==5000 should enable OSC 8")

    def test_vte_6800_returns_true(self):
        """VTE_VERSION='6800' (> 5000) → True."""
        result = self._run_auto({"VTE_VERSION": "6800"})
        self.assertIs(result, True,
                      "VTE_VERSION > 5000 should enable OSC 8")

    def test_vte_4604_returns_false(self):
        """VTE_VERSION='4604' (VTE 0.46.4, pre-OSC8) → False."""
        result = self._run_auto({"VTE_VERSION": "4604"})
        self.assertIs(result, False,
                      "VTE_VERSION < 5000 must not enable OSC 8 (pre-OSC8 VTE)")

    def test_vte_empty_string_returns_false(self):
        """VTE_VERSION='' (set but empty) → False."""
        result = self._run_auto({"VTE_VERSION": ""})
        self.assertIs(result, False,
                      "Empty VTE_VERSION must not enable OSC 8")

    def test_vte_unset_returns_false(self):
        """VTE_VERSION unset → False (no VTE marker)."""
        # _OTHER_MARKERS clears TERM_PROGRAM/WT_SESSION/KITTY_WINDOW_ID/TERMINAL_EMULATOR.
        # VTE_VERSION is absent from env_patch; os.environ.get("VTE_VERSION", "") → ""
        # → int("") raises ValueError → False.  Functionally identical to VTE_VERSION="".
        result = self._run_auto({})
        self.assertIs(result, False, "Unset VTE_VERSION must not enable OSC 8")

    def test_vte_garbage_returns_false_no_exception(self):
        """VTE_VERSION='garbage' (non-numeric) → False; must not raise (T-09-05)."""
        try:
            result = self._run_auto({"VTE_VERSION": "garbage"})
        except Exception as exc:
            self.fail(f"_osc8_enabled raised {type(exc).__name__} on non-numeric VTE_VERSION: {exc}")
        self.assertIs(result, False,
                      "Non-numeric VTE_VERSION must not enable OSC 8")

    def test_vte_4999_returns_false(self):
        """VTE_VERSION='4999' (one below threshold) → False."""
        result = self._run_auto({"VTE_VERSION": "4999"})
        self.assertIs(result, False,
                      "VTE_VERSION 4999 (one below 5000) must not enable OSC 8")

    def test_jetbrains_unaffected_by_vte_gate(self):
        """TERMINAL_EMULATOR='JetBrains-JediTerm', VTE unset → True (WR-02: JetBrains stays in allowlist)."""
        env = {
            "TERM_PROGRAM": "",
            "WT_SESSION": "",
            "KITTY_WINDOW_ID": "",
            "VTE_VERSION": "",
            "TERMINAL_EMULATOR": "JetBrains-JediTerm",
        }
        with patch.dict(os.environ, env, clear=False):
            result = self.mod._osc8_enabled({"display": {"links": "auto"}})
        self.assertIs(result, True,
                      "JetBrains terminal must still be in auto allowlist (WR-02)")


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
