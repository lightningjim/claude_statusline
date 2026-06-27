#!/usr/bin/env python3
"""
Tests for Phase 11 Plan 01: Version-display fragment.

Task 1: Ledger reader (_read_installed_gsd_version), two NF version glyph
        constants, and the show_versions default.
Task 2: Version sanitizer (_sanitize_version), fragment builder
        (_versions_fragment), and render_bottom_line wiring.

ENV-LEAK HYGIENE (project invariant, Phase 05.1):
Any test that mutates os.environ["HOME"] for a direct in-process call MUST
wrap the mutation in unittest.mock.patch.dict(os.environ, {"HOME": fake})
as a context manager.  NEVER a bare os.environ["HOME"] = ... assignment.
The subprocess run_script(home=...) path sets HOME only in the child env dict
and is already leak-safe; it does NOT need wrapping.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "claude-statusline.py",
)

def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script(stdin_bytes: bytes, home: str | None = None) -> subprocess.CompletedProcess:
    """Run the script as a subprocess with the given stdin bytes.

    When *home* is provided, $HOME is overridden in the child process env dict
    only — os.environ is never mutated (leak-safe by design).
    """
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=stdin_bytes,
        capture_output=True,
        env=env,
    )


def _make_fake_home(plugins_content: str | None = None) -> str:
    """Create a temp dir structured like $HOME.

    When *plugins_content* is provided (a JSON string), writes it to
    <home>/.claude/plugins/installed_plugins.json.  Returns the path to the
    temp dir; caller must clean up (or use as a context).
    """
    tmpdir = tempfile.mkdtemp(prefix="gsd-statusline-test-ver-home-")
    if plugins_content is not None:
        plugins_dir = os.path.join(tmpdir, ".claude", "plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        ledger_path = os.path.join(plugins_dir, "installed_plugins.json")
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write(plugins_content)
    return tmpdir


def _strip_ansi(s: str) -> str:
    """Strip ANSI color/SGR escapes from a string."""
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


# ---------------------------------------------------------------------------
# Minimal stdin payload (mirrors .examples/claude_stdin.json structure)
# ---------------------------------------------------------------------------

_BASE_PAYLOAD: dict = {
    "session_id": "test-session",
    "version": "2.1.154",
    "model": {"display_name": "TestModel"},
    "thinking": {"enabled": False},
    "workspace": {
        "current_dir": "/tmp/test",
        "project_dir": "/tmp/test",
        "added_dirs": [],
    },
    "cwd": "/tmp/test",
    "context_window": {"used_percentage": 7, "remaining_percentage": 93},
    "rate_limits": {
        "five_hour": {"used_percentage": 30, "resets_at": None},
        "seven_day": {"used_percentage": 3, "resets_at": None},
    },
}


# ===========================================================================
# Task 1 — Reader, NF glyph constants, show_versions default
# ===========================================================================

class TestReadInstalledGsdVersion(unittest.TestCase):
    """Tests for _read_installed_gsd_version: bounded never-raising reader.

    All direct-call tests mutate $HOME via patch.dict to guarantee leak-safe
    restoration after each test (TEST ENV-LEAK HYGIENE invariant).
    """

    def setUp(self):
        self.mod = _load_script_module()
        self._homes_to_cleanup: list[str] = []

    def tearDown(self):
        for path in self._homes_to_cleanup:
            shutil.rmtree(path, ignore_errors=True)

    def _fake_home(self, plugins_content: str | None = None) -> str:
        """Create a temp home and schedule it for cleanup."""
        path = _make_fake_home(plugins_content)
        self._homes_to_cleanup.append(path)
        return path

    # --- existence ---

    def test_function_exists(self):
        """_read_installed_gsd_version must be defined and callable."""
        self.assertTrue(
            hasattr(self.mod, "_read_installed_gsd_version"),
            "_read_installed_gsd_version not found in claude-statusline.py",
        )
        self.assertTrue(callable(self.mod._read_installed_gsd_version))

    # --- happy path ---

    def test_valid_ledger_returns_version_string(self):
        """Valid ledger with gsd@gsd-plugin -> [{"version":"4.0.0"}] returns "4.0.0"."""
        ledger = json.dumps({
            "plugins": {
                "gsd@gsd-plugin": [{"version": "4.0.0"}]
            }
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertEqual(result, "4.0.0")

    # --- omit-not-fake paths ---

    def test_missing_file_returns_none(self):
        """Missing ledger file -> None, no exception."""
        fake_home = self._fake_home()  # no plugins_content → file absent
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_as_dict_returns_none(self):
        """gsd@gsd-plugin entry is a dict (not a list) -> None."""
        ledger = json.dumps({
            "plugins": {
                "gsd@gsd-plugin": {"version": "4.0.0"}  # dict, not list
            }
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_empty_list_returns_none(self):
        """gsd@gsd-plugin entry is an empty list -> None."""
        ledger = json.dumps({
            "plugins": {"gsd@gsd-plugin": []}
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_element_missing_version_key_returns_none(self):
        """gsd@gsd-plugin -> [{"name":"x"}] (no version key) -> None."""
        ledger = json.dumps({
            "plugins": {"gsd@gsd-plugin": [{"name": "gsd-plugin"}]}
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_version_non_str_returns_none(self):
        """gsd@gsd-plugin -> [{"version": 400}] (non-string version) -> None."""
        ledger = json.dumps({
            "plugins": {"gsd@gsd-plugin": [{"version": 400}]}
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_version_empty_str_returns_none(self):
        """gsd@gsd-plugin -> [{"version": ""}] (empty string) -> None."""
        ledger = json.dumps({
            "plugins": {"gsd@gsd-plugin": [{"version": ""}]}
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_malformed_json_returns_none(self):
        """Malformed JSON in ledger -> None, never raises."""
        fake_home = self._fake_home("{not valid json {{")
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    def test_gsd_entry_absent_returns_none(self):
        """gsd@gsd-plugin key absent from the plugins dict -> None."""
        ledger = json.dumps({
            "plugins": {
                "other-plugin@some-ns": [{"version": "1.0.0"}]
            }
        })
        fake_home = self._fake_home(ledger)
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._read_installed_gsd_version()
        self.assertIsNone(result)

    # --- env-leak hygiene ---

    def test_no_env_leak_after_patch_dict(self):
        """$HOME must be fully restored to its original value after each direct call.

        The patch.dict context manager is the mechanism that ensures this.
        """
        original_home = os.environ.get("HOME")
        fake_home = self._fake_home()
        with patch.dict(os.environ, {"HOME": fake_home}):
            self.mod._read_installed_gsd_version()
        # After the with-block exits, HOME must be restored
        self.assertEqual(os.environ.get("HOME"), original_home)


class TestNfVersionGlyphConstants(unittest.TestCase):
    """_NF_VERSION_CLAUDE and _NF_VERSION_GSD glyph constants (VER-04, D-08)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_nf_version_claude_exists(self):
        """_NF_VERSION_CLAUDE must be defined on the module."""
        self.assertTrue(
            hasattr(self.mod, "_NF_VERSION_CLAUDE"),
            "_NF_VERSION_CLAUDE not found in claude-statusline.py",
        )

    def test_nf_version_gsd_exists(self):
        """_NF_VERSION_GSD must be defined on the module."""
        self.assertTrue(
            hasattr(self.mod, "_NF_VERSION_GSD"),
            "_NF_VERSION_GSD not found in claude-statusline.py",
        )

    def test_nf_version_claude_is_single_codepoint(self):
        """_NF_VERSION_CLAUDE must be a non-empty string with len==1."""
        val = getattr(self.mod, "_NF_VERSION_CLAUDE", None)
        self.assertIsInstance(val, str)
        self.assertEqual(len(val), 1, f"_NF_VERSION_CLAUDE len={len(val)}, expected 1")

    def test_nf_version_gsd_is_single_codepoint(self):
        """_NF_VERSION_GSD must be a non-empty string with len==1."""
        val = getattr(self.mod, "_NF_VERSION_GSD", None)
        self.assertIsInstance(val, str)
        self.assertEqual(len(val), 1, f"_NF_VERSION_GSD len={len(val)}, expected 1")


class TestShowVersionsDefault(unittest.TestCase):
    """DEFAULTS['display']['show_versions'] must default to True (VER-05, D-10)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_show_versions_default_exists(self):
        """DEFAULTS['display']['show_versions'] must be True."""
        defaults = getattr(self.mod, "DEFAULTS", None)
        self.assertIsNotNone(defaults, "DEFAULTS not defined on module")
        display = defaults.get("display", {})
        self.assertIn(
            "show_versions", display,
            "DEFAULTS['display'] missing 'show_versions' key",
        )
        self.assertIs(
            display["show_versions"], True,
            f"DEFAULTS['display']['show_versions'] must be True, got {display['show_versions']!r}",
        )


# ===========================================================================
# Task 2 — Sanitizer, builder, and end-to-end wiring
# (These tests will fail until Task 2 implementation is added)
# ===========================================================================

class TestSanitizeVersion(unittest.TestCase):
    """Tests for _sanitize_version: injection-reject + none-pass-through (T-11-01)."""

    def setUp(self):
        self.mod = _load_script_module()

    def _sanitize(self, value):
        return self.mod._sanitize_version(value)

    def test_function_exists(self):
        """_sanitize_version must be defined and callable."""
        self.assertTrue(
            hasattr(self.mod, "_sanitize_version"),
            "_sanitize_version not found in claude-statusline.py",
        )

    def test_valid_version_passthrough(self):
        """A clean semver-like string must pass through unchanged."""
        self.assertEqual(self._sanitize("2.1.154"), "2.1.154")

    def test_valid_gsd_version_passthrough(self):
        """A clean GSD version string must pass through unchanged."""
        self.assertEqual(self._sanitize("4.0.0"), "4.0.0")

    def test_none_returns_none(self):
        """None input -> None."""
        self.assertIsNone(self._sanitize(None))

    def test_empty_string_returns_none(self):
        """Empty string -> None."""
        self.assertIsNone(self._sanitize(""))

    def test_non_string_returns_none(self):
        """Non-string input (int, list) -> None."""
        self.assertIsNone(self._sanitize(42))
        self.assertIsNone(self._sanitize(["4.0.0"]))

    def test_ansi_escape_returns_none(self):
        """A string containing ESC (\x1b) -> None (omit-not-fake, T-11-01)."""
        self.assertIsNone(self._sanitize("1.0\x1b[31m"))
        self.assertIsNone(self._sanitize("\x1b[5;31mPWNED\x1b[0m"))

    def test_control_character_returns_none(self):
        """A string containing other control chars -> None."""
        self.assertIsNone(self._sanitize("1.0\x00bad"))
        self.assertIsNone(self._sanitize("1.0\nfoo"))

    def test_too_long_returns_none(self):
        """A string longer than 64 chars -> None (length guard)."""
        self.assertIsNone(self._sanitize("1." + "0" * 64))

    def test_exactly_64_chars_passes(self):
        """A string of exactly 64 allowed chars passes."""
        val = "1." + "0" * 62  # total 64 chars
        result = self._sanitize(val)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 64)

    def test_version_with_allowed_chars(self):
        """Versions with dots, dashes, underscores, plus signs pass."""
        for v in ("1.0.0-rc1", "4.0.0+build.1", "2.1_rc", "1.0.0"):
            with self.subTest(version=v):
                result = self._sanitize(v)
                self.assertIsNotNone(result, f"Expected {v!r} to pass")


class TestVersionsFragment(unittest.TestCase):
    """Tests for _versions_fragment builder (VER-01 through VER-05)."""

    def setUp(self):
        self.mod = _load_script_module()
        self._homes_to_cleanup: list[str] = []

    def tearDown(self):
        for path in self._homes_to_cleanup:
            shutil.rmtree(path, ignore_errors=True)

    def _fake_home(self, plugins_content: str | None = None) -> str:
        path = _make_fake_home(plugins_content)
        self._homes_to_cleanup.append(path)
        return path

    def _good_ledger(self, version: str = "4.0.0") -> str:
        return json.dumps({
            "plugins": {"gsd@gsd-plugin": [{"version": version}]}
        })

    def _call(self, data: dict, cfg: dict | None = None, home: str | None = None):
        """Call _versions_fragment with optional HOME override (leak-safe)."""
        if cfg is None:
            cfg = {"display": {"show_versions": True, "icon_set": "nerd"}}
        if home is not None:
            with patch.dict(os.environ, {"HOME": home}):
                return self.mod._versions_fragment(data, cfg)
        return self.mod._versions_fragment(data, cfg)

    def test_function_exists(self):
        """_versions_fragment must be defined and callable."""
        self.assertTrue(
            hasattr(self.mod, "_versions_fragment"),
            "_versions_fragment not found in claude-statusline.py",
        )

    def test_both_present_returns_dim_wrapped_string(self):
        """With both stdin version and ledger, returns DIM-wrapped string containing both."""
        data = {"version": "2.1.154"}
        fake_home = self._fake_home(self._good_ledger())
        result = self._call(data, home=fake_home)
        self.assertIsNotNone(result)
        self.assertIn("\033[2m", result)   # DIM before the body
        self.assertIn("\033[0m", result)   # RESET after the body
        stripped = _strip_ansi(result)
        self.assertIn("2.1.154", stripped)
        self.assertIn("4.0.0", stripped)

    def test_missing_stdin_version_omits_claude_piece(self):
        """data missing 'version' -> fragment omits Claude piece, still shows GSD (D-04)."""
        data = {}  # no version key
        fake_home = self._fake_home(self._good_ledger())
        result = self._call(data, home=fake_home)
        # Still has GSD piece
        self.assertIsNotNone(result)
        stripped = _strip_ansi(result)
        self.assertIn("4.0.0", stripped)
        self.assertNotIn("2.1.154", stripped)

    def test_missing_ledger_omits_gsd_piece(self):
        """Absent ledger -> fragment omits GSD piece, still shows Claude version (D-07)."""
        data = {"version": "2.1.154"}
        fake_home = self._fake_home()  # no ledger
        result = self._call(data, home=fake_home)
        self.assertIsNotNone(result)
        stripped = _strip_ansi(result)
        self.assertIn("2.1.154", stripped)
        self.assertNotIn("4.0.0", stripped)

    def test_both_absent_returns_none(self):
        """Both pieces absent -> _versions_fragment returns None."""
        data = {}
        fake_home = self._fake_home()  # no ledger
        result = self._call(data, home=fake_home)
        self.assertIsNone(result)

    def test_show_versions_false_returns_none(self):
        """cfg display.show_versions=False -> None (toggle, VER-05 D-10)."""
        data = {"version": "2.1.154"}
        fake_home = self._fake_home(self._good_ledger())
        cfg = {"display": {"show_versions": False, "icon_set": "nerd"}}
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._versions_fragment(data, cfg)
        self.assertIsNone(result)

    def test_nerd_icon_set_uses_nf_glyphs(self):
        """icon_set='nerd' -> result contains _NF_VERSION_CLAUDE and _NF_VERSION_GSD."""
        data = {"version": "2.1.154"}
        fake_home = self._fake_home(self._good_ledger())
        cfg = {"display": {"show_versions": True, "icon_set": "nerd"}}
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._versions_fragment(data, cfg)
        self.assertIsNotNone(result)
        claude_glyph = self.mod._NF_VERSION_CLAUDE
        gsd_glyph = self.mod._NF_VERSION_GSD
        self.assertIn(claude_glyph, result, "NF Claude glyph missing in nerd mode")
        self.assertIn(gsd_glyph, result, "NF GSD glyph missing in nerd mode")

    def test_non_nerd_icon_set_no_nf_glyphs(self):
        """icon_set='emoji' -> result contains NO _NF_VERSION_* codepoints (D-11)."""
        data = {"version": "2.1.154"}
        fake_home = self._fake_home(self._good_ledger())
        cfg = {"display": {"show_versions": True, "icon_set": "emoji"}}
        with patch.dict(os.environ, {"HOME": fake_home}):
            result = self.mod._versions_fragment(data, cfg)
        self.assertIsNotNone(result)
        claude_glyph = self.mod._NF_VERSION_CLAUDE
        gsd_glyph = self.mod._NF_VERSION_GSD
        self.assertNotIn(claude_glyph, result,
                         f"NF Claude glyph {claude_glyph!r} must NOT appear in emoji mode")
        self.assertNotIn(gsd_glyph, result,
                         f"NF GSD glyph {gsd_glyph!r} must NOT appear in emoji mode")

    def test_ansi_injection_in_stdin_version_omits_piece(self):
        """stdin version containing ANSI escapes -> Claude piece omitted (T-11-01)."""
        data = {"version": "1.0\x1b[31m"}  # poisoned version
        fake_home = self._fake_home(self._good_ledger())
        result = self._call(data, home=fake_home)
        # Fragment must not contain the raw escape from stdin
        if result is not None:
            self.assertNotIn("\x1b[31m", result,
                             "Raw ANSI from stdin version must not reach terminal")
            # And the poisoned value "1.0" may be omitted entirely or just the escape
            # The sanitizer must reject the entire piece (omit-not-fake)
            stripped = _strip_ansi(result)
            self.assertNotIn("1.0", stripped,
                             "Sanitizer must reject the whole piece on any disallowed char")


class TestVersionsFragmentE2E(unittest.TestCase):
    """End-to-end subprocess tests: versions fragment on the bottom line."""

    def _make_ledger_home(self, version: str = "4.0.0") -> str:
        """Create a temp home with a GSD ledger; caller must clean up."""
        ledger = json.dumps({
            "plugins": {"gsd@gsd-plugin": [{"version": version}]}
        })
        return _make_fake_home(ledger)

    def test_e2e_both_versions_on_bottom_line(self):
        """With valid stdin version and ledger, bottom line ends with both versions."""
        home = self._make_ledger_home("4.0.0")
        try:
            payload = dict(_BASE_PAYLOAD)
            payload["version"] = "2.1.154"
            result = run_script(json.dumps(payload).encode(), home=home)
            self.assertEqual(result.returncode, 0,
                             f"Script must exit 0; stderr={result.stderr.decode()!r}")
            lines = result.stdout.decode().splitlines()
            self.assertGreater(len(lines), 1, "Expected at least 2 output lines")
            bottom = lines[1]
            stripped = _strip_ansi(bottom)
            self.assertIn("2.1.154", stripped,
                          f"Claude version missing from bottom line: {stripped!r}")
            self.assertIn("4.0.0", stripped,
                          f"GSD version missing from bottom line: {stripped!r}")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_e2e_versions_segment_is_dim_wrapped(self):
        """Bottom line contains DIM ANSI code before the version numbers."""
        home = self._make_ledger_home()
        try:
            payload = dict(_BASE_PAYLOAD)
            result = run_script(json.dumps(payload).encode(), home=home)
            self.assertEqual(result.returncode, 0)
            lines = result.stdout.decode().splitlines()
            bottom = lines[1] if len(lines) > 1 else ""
            self.assertIn("\033[2m", bottom, "Bottom line must contain DIM escape (D-09)")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_e2e_missing_stdin_version_only_gsd_shows(self):
        """Stdin payload without version -> bottom line shows GSD version only."""
        home = self._make_ledger_home("4.0.0")
        try:
            payload = dict(_BASE_PAYLOAD)
            del payload["version"]
            result = run_script(json.dumps(payload).encode(), home=home)
            self.assertEqual(result.returncode, 0)
            lines = result.stdout.decode().splitlines()
            bottom = lines[1] if len(lines) > 1 else ""
            stripped = _strip_ansi(bottom)
            self.assertIn("4.0.0", stripped)
            self.assertNotIn("2.1.154", stripped)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_e2e_no_ledger_only_claude_version_shows(self):
        """Absent ledger -> bottom line shows Claude version only, no GSD."""
        home = _make_fake_home()  # no ledger
        try:
            payload = dict(_BASE_PAYLOAD)
            payload["version"] = "2.1.154"
            result = run_script(json.dumps(payload).encode(), home=home)
            self.assertEqual(result.returncode, 0)
            lines = result.stdout.decode().splitlines()
            bottom = lines[1] if len(lines) > 1 else ""
            stripped = _strip_ansi(bottom)
            self.assertIn("2.1.154", stripped)
            self.assertNotIn("4.0.0", stripped)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_e2e_ansi_injected_version_not_echoed(self):
        """stdin version with ANSI escape chars -> no raw escape on bottom line."""
        home = self._make_ledger_home()
        try:
            payload = dict(_BASE_PAYLOAD)
            payload["version"] = "1.0\x1b[31m"  # poisoned
            result = run_script(json.dumps(payload).encode(), home=home)
            self.assertEqual(result.returncode, 0)
            bottom = result.stdout.decode().splitlines()
            bottom_line = bottom[1] if len(bottom) > 1 else ""
            # "\x1b[31m" specifically from the poisoned input must not appear
            self.assertNotIn("\x1b[31m", bottom_line,
                             "Raw ANSI from poisoned stdin version must not reach terminal")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_e2e_exits_zero_no_traceback(self):
        """Script must exit 0 and emit no Traceback in stderr."""
        home = self._make_ledger_home()
        try:
            result = run_script(json.dumps(_BASE_PAYLOAD).encode(), home=home)
            self.assertEqual(result.returncode, 0)
            stderr = result.stderr.decode()
            self.assertNotIn("Traceback", stderr, f"Traceback in stderr: {stderr!r}")
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
