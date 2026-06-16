#!/usr/bin/env python3
"""
Tests for Phase 06 Plan 01: Claude service-health data layer.

Task 1 covers:
  - Config keys: DEFAULTS["display"]["show_claude_status"], DEFAULTS["cache"]["status_ttl"],
    DEFAULTS["cache"]["status_max_stale"]
  - Status glyph constants: _NF_CLAUDE_INCIDENT, _NF_CLAUDE_MAINT
  - _claude_status_color(severity): severity→ANSI color, never raises, correct hue mapping

Task 2 covers:
  - _derive_claude_status(summary): trigger derivation from status.claude.com summary.json
    — quiet-when-healthy (D-01), untracked exclusion (D-02), incident+label (D-03),
    degraded fallback (D-03), maintenance (D-04), never raises on malformed input

Task 3 covers:
  - fetch_claude_status(cfg): honors CLAUDE_STATUSLINE_FAKE_STATUS, writes "claude_status"
    cache section, never raises
  - run_refresh: calls fetch_claude_status under the existing single lock
  - maybe_spawn_refresh: status staleness independently triggers respawn
"""

import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_fixture(name: str) -> dict:
    path = os.path.join(FIXTURES_DIR, name)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Task 1: _claude_status_color
# ---------------------------------------------------------------------------

class TestClaudeStatusColor(unittest.TestCase):
    """_claude_status_color: severity→ANSI, never raises, correct hue mapping."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_function_exists(self):
        self.assertTrue(callable(getattr(self.mod, "_claude_status_color", None)))

    def test_minor_contains_yellow(self):
        """minor severity → color contains YELLOW."""
        color = self.mod._claude_status_color("minor")
        self.assertIn(self.mod.YELLOW, color,
                      f"minor must contain YELLOW; got {color!r}")

    def test_major_contains_red_or_orange(self):
        """major severity → color contains RED (or a distinct orange hue)."""
        color = self.mod._claude_status_color("major")
        # Accept either RED or an orange-like ANSI code (256-color or distinct constant).
        # At minimum it must not be YELLOW and must contain some ANSI sequence.
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0, "major color must be non-empty")
        # Must NOT be YELLOW (that's minor's hue)
        self.assertNotEqual(color, self.mod.YELLOW,
                            "major must be distinct from minor (YELLOW)")

    def test_critical_contains_red_and_bold(self):
        """critical severity → color contains RED and BOLD."""
        color = self.mod._claude_status_color("critical")
        self.assertIn(self.mod.RED, color,
                      f"critical must contain RED; got {color!r}")
        self.assertIn(self.mod.BOLD, color,
                      f"critical must contain BOLD; got {color!r}")

    def test_maintenance_is_neutral_not_severity(self):
        """maintenance → neutral hue (DIM or DEFAULT_FG), NOT a severity color (D-04)."""
        color = self.mod._claude_status_color("maintenance")
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0, "maintenance color must be non-empty")
        # Must not be a severity red or yellow
        self.assertNotIn(self.mod.RED, color,
                         f"maintenance must not be RED; got {color!r}")
        self.assertNotIn(self.mod.YELLOW, color,
                         f"maintenance must not be YELLOW; got {color!r}")

    def test_garbage_does_not_raise(self):
        """_claude_status_color(<garbage>) never raises; returns a safe default."""
        bad_inputs = [None, "", "unknown", 42, [], {}]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                try:
                    result = self.mod._claude_status_color(bad)
                    self.assertIsInstance(result, str,
                                         f"Expected str, got {type(result)} for {bad!r}")
                    self.assertTrue(len(result) > 0,
                                    f"Color must be non-empty for {bad!r}")
                except Exception as e:
                    self.fail(f"_claude_status_color raised on {bad!r}: {e}")

    def test_none_returns_safe_default(self):
        """_claude_status_color(None) returns YELLOW (safe fallback, per spec)."""
        result = self.mod._claude_status_color(None)
        self.assertEqual(result, self.mod.YELLOW,
                         f"None input must return YELLOW; got {result!r}")


# ---------------------------------------------------------------------------
# Task 1: DEFAULTS keys
# ---------------------------------------------------------------------------

class TestDefaultsKeys(unittest.TestCase):
    """DEFAULTS must expose show_claude_status, status_ttl, status_max_stale."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_show_claude_status_in_defaults(self):
        """DEFAULTS["display"]["show_claude_status"] is True."""
        display = self.mod.DEFAULTS.get("display", {})
        self.assertIn("show_claude_status", display,
                      "DEFAULTS['display'] must have 'show_claude_status'")
        self.assertTrue(display["show_claude_status"],
                        "show_claude_status default must be True")

    def test_status_ttl_in_defaults(self):
        """DEFAULTS["cache"]["status_ttl"] == 300."""
        cache = self.mod.DEFAULTS.get("cache", {})
        self.assertIn("status_ttl", cache,
                      "DEFAULTS['cache'] must have 'status_ttl'")
        self.assertEqual(cache["status_ttl"], 300,
                         f"status_ttl must be 300; got {cache.get('status_ttl')!r}")

    def test_status_max_stale_in_defaults(self):
        """DEFAULTS["cache"]["status_max_stale"] == 900."""
        cache = self.mod.DEFAULTS.get("cache", {})
        self.assertIn("status_max_stale", cache,
                      "DEFAULTS['cache'] must have 'status_max_stale'")
        self.assertEqual(cache["status_max_stale"], 900,
                         f"status_max_stale must be 900; got {cache.get('status_max_stale')!r}")

    def test_load_config_exposes_show_claude_status(self):
        """load_config() with non-existent path still exposes show_claude_status via _deep_merge."""
        cfg = self.mod.load_config("/nonexistent/path/config.toml")
        display = cfg.get("display", {})
        self.assertIn("show_claude_status", display,
                      "load_config() must expose show_claude_status through _deep_merge")

    def test_load_config_exposes_status_ttl(self):
        """load_config() with non-existent path still exposes status_ttl."""
        cfg = self.mod.load_config("/nonexistent/path/config.toml")
        cache = cfg.get("cache", {})
        self.assertIn("status_ttl", cache,
                      "load_config() must expose status_ttl through _deep_merge")

    def test_load_config_exposes_status_max_stale(self):
        """load_config() with non-existent path still exposes status_max_stale."""
        cfg = self.mod.load_config("/nonexistent/path/config.toml")
        cache = cfg.get("cache", {})
        self.assertIn("status_max_stale", cache,
                      "load_config() must expose status_max_stale through _deep_merge")


# ---------------------------------------------------------------------------
# Task 1: Glyph constants
# ---------------------------------------------------------------------------

class TestGlyphConstants(unittest.TestCase):
    """_NF_CLAUDE_INCIDENT and _NF_CLAUDE_MAINT must exist and be non-empty strings."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_nf_claude_incident_exists(self):
        """_NF_CLAUDE_INCIDENT glyph constant exists."""
        val = getattr(self.mod, "_NF_CLAUDE_INCIDENT", None)
        self.assertIsNotNone(val, "_NF_CLAUDE_INCIDENT must be defined")
        self.assertIsInstance(val, str, "_NF_CLAUDE_INCIDENT must be a str")
        self.assertTrue(len(val) > 0, "_NF_CLAUDE_INCIDENT must be non-empty")

    def test_nf_claude_maint_exists(self):
        """_NF_CLAUDE_MAINT glyph constant exists."""
        val = getattr(self.mod, "_NF_CLAUDE_MAINT", None)
        self.assertIsNotNone(val, "_NF_CLAUDE_MAINT must be defined")
        self.assertIsInstance(val, str, "_NF_CLAUDE_MAINT must be a str")
        self.assertTrue(len(val) > 0, "_NF_CLAUDE_MAINT must be non-empty")

    def test_incident_and_maint_are_distinct(self):
        """_NF_CLAUDE_INCIDENT and _NF_CLAUDE_MAINT must be distinct glyphs (D-04)."""
        inc = getattr(self.mod, "_NF_CLAUDE_INCIDENT", "")
        maint = getattr(self.mod, "_NF_CLAUDE_MAINT", "")
        self.assertNotEqual(inc, maint,
                            "Incident and maintenance glyphs must be distinct (D-04)")


# ---------------------------------------------------------------------------
# Task 2: _derive_claude_status
# ---------------------------------------------------------------------------

class TestDeriveClaudeStatus(unittest.TestCase):
    """_derive_claude_status: trigger derivation against the full fixture matrix."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_function_exists(self):
        self.assertTrue(callable(getattr(self.mod, "_derive_claude_status", None)))

    def test_operational_returns_none(self):
        """Operational fixture (all tracked operational, no incidents) → None (D-01)."""
        summary = _load_fixture("status_operational.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNone(result,
                          f"All operational must return None (D-01); got {result!r}")

    def test_incident_untracked_returns_none(self):
        """Untracked incident (Claude API only) → None (D-02)."""
        summary = _load_fixture("status_incident_untracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNone(result,
                          f"Untracked-only incident must return None (D-02); got {result!r}")

    def test_incident_tracked_returns_dict_with_label(self):
        """Tracked incident → dict with label == incident title (D-03)."""
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "Tracked incident must return a non-None dict (D-03)")
        self.assertIsInstance(result, dict, f"Result must be a dict; got {type(result)}")
        self.assertIn("label", result, "Result dict must have 'label' key")
        # The fixture incident title is known; assert equality
        incident_title = summary["incidents"][0]["name"]
        self.assertEqual(result["label"], incident_title,
                         f"Label must equal fixture incident title; "
                         f"got {result['label']!r}, expected {incident_title!r}")

    def test_incident_tracked_has_severity(self):
        """Tracked incident → dict has 'severity' key."""
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertIn("severity", result, "Result dict must have 'severity' key")

    def test_incident_tracked_has_kind_incident(self):
        """Tracked incident → dict has kind == 'incident'."""
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "incident",
                         f"Tracked incident kind must be 'incident'; got {result.get('kind')!r}")

    def test_degraded_no_title_returns_component_state_label(self):
        """Degraded-no-title → label has 'claude.ai' prefix (D-03 fallback)."""
        summary = _load_fixture("status_degraded_no_title.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "Degraded tracked component must return a non-None dict")
        self.assertIsInstance(result, dict)
        label = result.get("label", "")
        self.assertTrue(label.startswith("claude.ai"),
                        f"Degraded fallback label must start with 'claude.ai'; got {label!r}")

    def test_degraded_no_title_kind_is_degraded(self):
        """Degraded-no-title → kind == 'degraded'."""
        summary = _load_fixture("status_degraded_no_title.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "degraded",
                         f"Degraded fallback kind must be 'degraded'; got {result.get('kind')!r}")

    def test_maintenance_returns_maintenance_kind(self):
        """Maintenance fixture (in_progress touching Claude Cowork) → kind == 'maintenance' (D-04)."""
        summary = _load_fixture("status_maintenance.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "Relevant maintenance must return a non-None dict (D-04)")
        self.assertEqual(result.get("kind"), "maintenance",
                         f"Maintenance kind must be 'maintenance'; got {result.get('kind')!r}")

    def test_maintenance_severity_is_maintenance(self):
        """Maintenance fixture → severity == 'maintenance' (D-04)."""
        summary = _load_fixture("status_maintenance.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("severity"), "maintenance",
                         f"Maintenance severity must be 'maintenance'; got {result.get('severity')!r}")

    def test_empty_dict_returns_none(self):
        """Empty dict → None, never raises (T-06-02)."""
        try:
            result = self.mod._derive_claude_status({})
        except Exception as e:
            self.fail(f"_derive_claude_status raised on {{}}: {e}")
        self.assertIsNone(result, f"Empty dict must return None; got {result!r}")

    def test_non_dict_returns_none(self):
        """Non-dict input → None, never raises (T-06-02)."""
        bad_inputs = [None, [], "bad", 42]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                try:
                    result = self.mod._derive_claude_status(bad)
                    self.assertIsNone(result,
                                      f"Non-dict must return None; got {result!r}")
                except Exception as e:
                    self.fail(f"_derive_claude_status raised on {bad!r}: {e}")

    def test_missing_keys_returns_none(self):
        """Missing components/incidents → None, never raises."""
        try:
            result = self.mod._derive_claude_status({"page": {}, "status": {}})
        except Exception as e:
            self.fail(f"_derive_claude_status raised on missing-keys dict: {e}")
        self.assertIsNone(result,
                          f"Missing keys dict must return None; got {result!r}")

    def test_malicious_title_returns_raw_label(self):
        """Malicious title fixture → derivation returns RAW label unchanged (no sanitize yet)."""
        summary = _load_fixture("status_malicious_title.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result, "Malicious-title incident must return a non-None dict")
        # The label must be returned RAW (unsanitized) — sanitization is Plan 02's job
        incident_title = summary["incidents"][0]["name"]
        self.assertEqual(result.get("label"), incident_title,
                         "Derivation must store the RAW (unsanitized) label")

    def test_malicious_title_does_not_raise(self):
        """Malicious title fixture derivation never raises."""
        summary = _load_fixture("status_malicious_title.json")
        try:
            self.mod._derive_claude_status(summary)
        except Exception as e:
            self.fail(f"_derive_claude_status raised on malicious title: {e}")


# ---------------------------------------------------------------------------
# Task 3: fetch_claude_status
# ---------------------------------------------------------------------------

class TestFetchClaudeStatus(unittest.TestCase):
    """fetch_claude_status: honors CLAUDE_STATUSLINE_FAKE_STATUS, writes cache section."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {
                "weather_ttl": 600,
                "alerts_ttl": 300,
                "weather_max_stale": 3600,
                "alerts_max_stale": 900,
                "status_ttl": 300,
                "status_max_stale": 900,
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_function_exists(self):
        self.assertTrue(callable(getattr(self.mod, "fetch_claude_status", None)))

    def test_fake_status_writes_cache_section(self):
        """fetch_claude_status with CLAUDE_STATUSLINE_FAKE_STATUS writes 'claude_status' section."""
        fake_path = os.path.join(FIXTURES_DIR, "status_incident_tracked.json")
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("claude_status", data,
                      "fetch_claude_status must write the 'claude_status' cache section")

    def test_fake_status_incident_label_matches_fixture_title(self):
        """Incident fixture → written label equals fixture incident title (D-03)."""
        fake_path = os.path.join(FIXTURES_DIR, "status_incident_tracked.json")
        summary = _load_fixture("status_incident_tracked.json")
        incident_title = summary["incidents"][0]["name"]
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        section = data.get("claude_status", {})
        self.assertEqual(section.get("label"), incident_title,
                         f"Written label must equal incident title; "
                         f"got {section.get('label')!r}, expected {incident_title!r}")

    def test_fake_status_operational_writes_section(self):
        """Operational fixture → still writes a 'claude_status' section (timestamps the fetch)."""
        fake_path = os.path.join(FIXTURES_DIR, "status_operational.json")
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("claude_status", data,
                      "Operational fetch must still write the 'claude_status' section")

    def test_fake_status_operational_has_fetched_at(self):
        """Operational fixture → section has fetched_at timestamp (prevents hot-respawn)."""
        fake_path = os.path.join(FIXTURES_DIR, "status_operational.json")
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        section = data.get("claude_status", {})
        self.assertIn("fetched_at", section,
                      "claude_status section must have fetched_at timestamp")

    def test_bad_fake_path_does_not_raise(self):
        """Bad/nonexistent fake path → never raises, leaves cache unchanged."""
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": "/nonexistent/path/status.json"}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                try:
                    self.mod.fetch_claude_status(self.cfg)
                except Exception as e:
                    self.fail(f"fetch_claude_status raised on bad fake path: {e}")
        # Cache should still not have a claude_status section (no write happened)
        data = self.mod.read_cache(self.cache_path)
        self.assertNotIn("claude_status", data,
                         "Bad fake path must leave cache unchanged")

    def test_no_real_network_call_with_fake(self):
        """When CLAUDE_STATUSLINE_FAKE_STATUS is set, _nws_get is NOT called."""
        fake_path = os.path.join(FIXTURES_DIR, "status_operational.json")
        nws_get_calls = []

        def spy_nws_get(url, ua, accept=None):
            nws_get_calls.append(url)
            return {}

        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_nws_get", side_effect=spy_nws_get):
                with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                    self.mod.fetch_claude_status(self.cfg)

        self.assertEqual(nws_get_calls, [],
                         "When CLAUDE_STATUSLINE_FAKE_STATUS is set, _nws_get must not be called")

    def test_network_error_does_not_raise(self):
        """Network error → never raises (D-10)."""
        def bad_nws_get(url, ua, accept=None):
            raise ConnectionError("network down")

        with patch.object(self.mod, "_nws_get", side_effect=bad_nws_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                try:
                    self.mod.fetch_claude_status(self.cfg)
                except Exception as e:
                    self.fail(f"fetch_claude_status raised on network error: {e}")


# ---------------------------------------------------------------------------
# Task 3: run_refresh calls fetch_claude_status
# ---------------------------------------------------------------------------

class TestRunRefreshStatus(unittest.TestCase):
    """run_refresh must call fetch_claude_status under the existing single lock."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {
                "weather_ttl": 600,
                "alerts_ttl": 300,
                "weather_max_stale": 3600,
                "alerts_max_stale": 900,
                "status_ttl": 300,
                "status_max_stale": 900,
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_refresh_calls_fetch_claude_status(self):
        """run_refresh calls fetch_claude_status (in addition to fetch_weather + fetch_alerts)."""
        weather_called = []
        alerts_called = []
        status_called = []

        def mock_fetch_weather(cfg):
            weather_called.append(True)

        def mock_fetch_alerts(cfg):
            alerts_called.append(True)

        def mock_fetch_claude_status(cfg):
            status_called.append(True)

        lock_path = os.path.join(self.tmpdir, "refresh.lock")
        cache_path = os.path.join(self.tmpdir, "cache.json")

        with patch.object(self.mod, "fetch_weather", side_effect=mock_fetch_weather):
            with patch.object(self.mod, "fetch_alerts", side_effect=mock_fetch_alerts):
                with patch.object(self.mod, "fetch_claude_status",
                                  side_effect=mock_fetch_claude_status):
                    with patch.object(self.mod, "_CACHE_PATH", cache_path):
                        with patch.object(self.mod, "_LOCK_PATH", lock_path):
                            self.mod.run_refresh(self.cfg)

        self.assertEqual(len(weather_called), 1, "fetch_weather must be called")
        self.assertEqual(len(alerts_called), 1, "fetch_alerts must be called")
        self.assertEqual(len(status_called), 1,
                         "fetch_claude_status must be called by run_refresh")


# ---------------------------------------------------------------------------
# Task 3: maybe_spawn_refresh triggers on stale status section
# ---------------------------------------------------------------------------

class TestMaybeSpawnRefreshStatus(unittest.TestCase):
    """maybe_spawn_refresh triggers on stale claude_status section."""

    def setUp(self):
        self.mod = _load_script_module()
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {
                "weather_ttl": 600,
                "alerts_ttl": 300,
                "weather_max_stale": 3600,
                "alerts_max_stale": 900,
                "status_ttl": 300,
                "status_max_stale": 900,
            },
        }

    def test_spawns_when_only_status_stale(self):
        """maybe_spawn_refresh spawns when only claude_status section is stale."""
        now = time.time()
        # Weather and alerts are fresh; claude_status is stale (past 300s TTL)
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "", "temp": 72},
            "alerts": {"fetched_at": now - 60, "active": []},
            "claude_status": {"fetched_at": now - 600},  # stale
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertGreater(len(popen_calls), 0,
                           "Popen must be called when only claude_status is stale")

    def test_spawns_when_status_absent(self):
        """maybe_spawn_refresh spawns when claude_status section is absent."""
        now = time.time()
        # Weather and alerts are fresh; claude_status is absent
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "", "temp": 72},
            "alerts": {"fetched_at": now - 60, "active": []},
            # no "claude_status" key
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertGreater(len(popen_calls), 0,
                           "Popen must be called when claude_status section is absent")

    def test_no_spawn_when_all_three_fresh(self):
        """maybe_spawn_refresh does NOT spawn when weather, alerts, AND status are fresh."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "", "temp": 72},
            "alerts": {"fetched_at": now - 60, "active": []},
            "claude_status": {"fetched_at": now - 60},  # fresh
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertEqual(len(popen_calls), 0,
                         "Popen must NOT be called when all three sections are fresh")


if __name__ == "__main__":
    unittest.main()
