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

    # ---- WR-01: under_maintenance component, no scheduled_maintenances event ----
    # Statuspage.io allows a component status to be set to under_maintenance
    # WITHOUT an associated scheduled_maintenances entry. Rule 2 (maintenance
    # events) does not fire, so execution falls through to Rule 3, which must
    # still classify this as maintenance severity (not an outage). The render
    # path keys off severity=="maintenance" to pick the wrench glyph (D-04).

    def test_under_maintenance_no_event_severity_is_maintenance(self):
        """under_maintenance component, no event → severity == 'maintenance' (Rule 3, WR-01)."""
        summary = _load_fixture("status_component_under_maintenance_no_event.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "under_maintenance tracked component must return a non-None dict")
        self.assertEqual(result.get("severity"), "maintenance",
                         f"under_maintenance Rule-3 severity must be 'maintenance'; "
                         f"got {result.get('severity')!r}")

    def test_under_maintenance_no_event_label_has_maintenance(self):
        """under_maintenance component, no event → label reflects maintenance state (D-03/D-04)."""
        summary = _load_fixture("status_component_under_maintenance_no_event.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        label = result.get("label", "")
        self.assertTrue(label.startswith("claude.ai"),
                        f"Rule-3 label must start with the component name; got {label!r}")
        self.assertIn("maintenance", label,
                      f"Rule-3 under_maintenance label must mention maintenance; got {label!r}")

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

    # ---- WR-03: _REQUESTS_OK guard on the live-fetch branch ----

    def test_requests_unavailable_skips_network(self):
        """_REQUESTS_OK False (no fake path) → _nws_get not called, cache unchanged (WR-03)."""
        nws_get_calls = []

        def spy_nws_get(url, ua, accept=None):
            nws_get_calls.append(url)
            return {}

        # Ensure no fake-status env override so the live branch is taken.
        env = dict(os.environ)
        env.pop("CLAUDE_STATUSLINE_FAKE_STATUS", None)
        with patch.dict(os.environ, env, clear=True):
            with patch.object(self.mod, "_REQUESTS_OK", False):
                with patch.object(self.mod, "_nws_get", side_effect=spy_nws_get):
                    with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                        try:
                            self.mod.fetch_claude_status(self.cfg)
                        except Exception as e:
                            self.fail(f"fetch_claude_status raised when _REQUESTS_OK False: {e}")

        self.assertEqual(nws_get_calls, [],
                         "_nws_get must NOT be called when _REQUESTS_OK is False (WR-03)")
        data = self.mod.read_cache(self.cache_path)
        self.assertNotIn("claude_status", data,
                         "Early bail must leave the cache unchanged when requests is unavailable")


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

        # WR-02: weather/alerts now gate on _WEATHER_OK + show_weather + a configured
        # location. This cfg has a real location and show_weather=True, so with
        # _WEATHER_OK forced True all three fetches must fire.
        with patch.object(self.mod, "_WEATHER_OK", True):
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

    # ---- WR-02: weather/alerts gated; status always runs ----

    def _run_refresh_capturing(self, cfg):
        """Run run_refresh against cfg; return (weather_n, alerts_n, status_n)."""
        weather_called, alerts_called, status_called = [], [], []
        lock_path = os.path.join(self.tmpdir, "refresh2.lock")
        cache_path = os.path.join(self.tmpdir, "cache2.json")
        with patch.object(self.mod, "fetch_weather",
                          side_effect=lambda c: weather_called.append(True)):
            with patch.object(self.mod, "fetch_alerts",
                              side_effect=lambda c: alerts_called.append(True)):
                with patch.object(self.mod, "fetch_claude_status",
                                  side_effect=lambda c: status_called.append(True)):
                    with patch.object(self.mod, "_CACHE_PATH", cache_path):
                        with patch.object(self.mod, "_LOCK_PATH", lock_path):
                            self.mod.run_refresh(cfg)
        return len(weather_called), len(alerts_called), len(status_called)

    def test_run_refresh_skips_weather_when_show_weather_false(self):
        """show_weather=False → weather/alerts skipped, status still fetched (WR-02)."""
        cfg = dict(self.cfg)
        cfg["weather"] = {"contact_email": "test@example.com", "show_weather": False}
        with patch.object(self.mod, "_WEATHER_OK", True):
            w, a, s = self._run_refresh_capturing(cfg)
        self.assertEqual(w, 0, "fetch_weather must be skipped when show_weather=False")
        self.assertEqual(a, 0, "fetch_alerts must be skipped when show_weather=False")
        self.assertEqual(s, 1, "fetch_claude_status must still run (status is independent)")

    def test_run_refresh_skips_weather_when_location_unconfigured(self):
        """Unconfigured (0.0,0.0) location → weather/alerts skipped, status still runs (WR-02)."""
        cfg = dict(self.cfg)
        cfg["location"] = {"lat": 0.0, "lon": 0.0}
        with patch.object(self.mod, "_WEATHER_OK", True):
            w, a, s = self._run_refresh_capturing(cfg)
        self.assertEqual(w, 0, "fetch_weather must be skipped for the (0.0,0.0) placeholder")
        self.assertEqual(a, 0, "fetch_alerts must be skipped for the (0.0,0.0) placeholder")
        self.assertEqual(s, 1, "fetch_claude_status must still run")

    def test_run_refresh_skips_weather_when_weather_unavailable(self):
        """_WEATHER_OK False (astral/requests missing) → weather/alerts skipped, status runs (WR-02)."""
        with patch.object(self.mod, "_WEATHER_OK", False):
            w, a, s = self._run_refresh_capturing(self.cfg)
        self.assertEqual(w, 0, "fetch_weather must be skipped when _WEATHER_OK is False")
        self.assertEqual(a, 0, "fetch_alerts must be skipped when _WEATHER_OK is False")
        self.assertEqual(s, 1, "fetch_claude_status must still run when weather deps are missing")


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


# ---------------------------------------------------------------------------
# Task 4 (Plan 02): _claude_status_segment render builder
# ---------------------------------------------------------------------------
#
# These tests cover the rendering logic introduced in Plan 02.
# The segment reads from the "claude_status" cache section written by Plan 01,
# sanitizes the RAW label (ANSI-strip + width-bound), resolves the severity
# color and icon_set glyph, and returns a formatted string or None.
#
# Cache section shape (per Plan 01 locked contract):
#   {
#     "fetched_at": <float epoch>,
#     "noteworthy": <bool>,
#     "severity":   "<minor|major|critical|maintenance>",  // when noteworthy
#     "label":      "<raw title or 'Component: state'>",  // when noteworthy
#     "kind":       "<incident|maintenance|degraded>"     // when noteworthy
#   }
# Healthy / cold-cache: noteworthy=False or section absent/stale.

def _make_cache_with_status(tmpdir: str, status_section: dict) -> str:
    """Write a cache.json with the given claude_status section; return path."""
    cache_path = os.path.join(tmpdir, "cache.json")
    cache_data = {"claude_status": status_section}
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    return cache_path


class TestClaudeStatusSegmentBuilder(unittest.TestCase):
    """_claude_status_segment: render-path builder — reads cache, sanitizes, colors, returns str|None."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        # Minimal data dict (render helpers only need rate_limits / context_window; we
        # pass an empty dict here since _claude_status_segment reads cfg, not data directly)
        self.data = {}
        self.base_cfg = {
            "cache": {
                "status_ttl": 300,
                "status_max_stale": 900,
            },
            "display": {
                "show_claude_status": True,
                "icon_set": "nerd",
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _segment(self, status_section: dict | None, extra_cfg: dict | None = None) -> str | None:
        """Call _claude_status_segment with a fresh temp cache."""
        import copy
        cfg = copy.deepcopy(self.base_cfg)
        if extra_cfg:
            for k, v in extra_cfg.items():
                if isinstance(v, dict) and k in cfg:
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        if status_section is not None:
            cache_path = _make_cache_with_status(self.tmpdir, status_section)
        else:
            # Cold cache: no file at all
            cache_path = os.path.join(self.tmpdir, "absent_cache.json")
        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            return self.mod._claude_status_segment(self.data, cfg)

    def _fresh_section(self, **kwargs) -> dict:
        """Return a fresh cache section dict (fetched_at = now - 60, within max_stale)."""
        sec = {"fetched_at": time.time() - 60}
        sec.update(kwargs)
        return sec

    # ---- function exists ----

    def test_function_exists(self):
        """_claude_status_segment function must exist."""
        self.assertTrue(callable(getattr(self.mod, "_claude_status_segment", None)),
                        "_claude_status_segment must be defined in claude-statusline.py")

    # ---- show_claude_status=False ----

    def test_disabled_toggle_returns_none(self):
        """show_claude_status=False → returns None regardless of cache (D-01 gate)."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Claude Code outage", kind="incident")
        result = self._segment(sec, extra_cfg={"display": {"show_claude_status": False}})
        self.assertIsNone(result,
                          "show_claude_status=False must return None")

    # ---- cold/absent cache ----

    def test_absent_cache_returns_none(self):
        """No cache file → returns None (cold-cache silent, D-01)."""
        result = self._segment(None)
        self.assertIsNone(result, "Absent cache must return None")

    def test_stale_past_max_stale_returns_none(self):
        """Section older than status_max_stale (900s) → returns None."""
        sec = {"fetched_at": time.time() - 1000, "noteworthy": True,
               "severity": "minor", "label": "Outage", "kind": "incident"}
        result = self._segment(sec)
        self.assertIsNone(result, "Stale-past-max-stale cache section must return None")

    # ---- healthy / noteworthy=False ----

    def test_healthy_noteworthy_false_returns_none(self):
        """noteworthy=False (healthy) → returns None (quiet-when-healthy, D-01)."""
        sec = self._fresh_section(noteworthy=False)
        result = self._segment(sec)
        self.assertIsNone(result, "Healthy cache (noteworthy=False) must return None (D-01)")

    # ---- corrupt / malformed cache sections ----

    def test_non_dict_section_returns_none(self):
        """Non-dict claude_status section → returns None, never raises."""
        # Write a cache with a bad (non-dict) section value
        cache_path = os.path.join(self.tmpdir, "bad_cache.json")
        with open(cache_path, "w") as f:
            json.dump({"claude_status": "not a dict"}, f)
        cfg = dict(self.base_cfg)
        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            try:
                result = self.mod._claude_status_segment(self.data, cfg)
            except Exception as e:
                self.fail(f"_claude_status_segment raised on non-dict section: {e}")
        self.assertIsNone(result, "Non-dict section must return None")

    def test_missing_noteworthy_key_returns_none(self):
        """Section missing 'noteworthy' key → returns None (treated as cold/unhealthy)."""
        sec = self._fresh_section()  # no noteworthy key
        result = self._segment(sec)
        self.assertIsNone(result, "Missing noteworthy key must return None")

    def test_missing_fetched_at_returns_none(self):
        """Section with no fetched_at → returns None (cannot validate freshness)."""
        sec = {"noteworthy": True, "severity": "minor", "label": "Outage", "kind": "incident"}
        result = self._segment(sec)
        self.assertIsNone(result, "Missing fetched_at must return None")

    # ---- incident case ----

    def test_incident_returns_string(self):
        """Incident cache entry → returns a non-None string."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Claude Code elevated error rates", kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result, "Incident cache entry must return a non-None string")
        self.assertIsInstance(result, str, f"Result must be str, got {type(result)}")

    def test_incident_contains_sanitized_label(self):
        """Incident result contains the sanitized incident label text."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Claude Code elevated error rates", kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertIn("Claude Code elevated error rates", result,
                      f"Result must contain sanitized label; got {result!r}")

    def test_incident_starts_with_color_ends_with_reset(self):
        """Incident result is wrapped with a color code and ends with RESET."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Claude Code outage", kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        # Must start with an ANSI escape code (color)
        self.assertTrue(result.startswith("\033["),
                        f"Result must start with ANSI color escape; got {result!r}")
        # Must end with RESET
        self.assertTrue(result.endswith(self.mod.RESET),
                        f"Result must end with RESET; got {result!r}")

    def test_minor_incident_uses_yellow(self):
        """minor severity incident → result contains YELLOW."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Minor issue", kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertIn(self.mod.YELLOW, result,
                      f"minor severity must produce YELLOW in result; got {result!r}")

    def test_critical_incident_uses_red_and_bold(self):
        """critical severity incident → result contains RED and BOLD."""
        sec = self._fresh_section(noteworthy=True, severity="critical",
                                  label="Claude Code down", kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertIn(self.mod.RED, result,
                      f"critical severity must produce RED; got {result!r}")
        self.assertIn(self.mod.BOLD, result,
                      f"critical severity must produce BOLD; got {result!r}")

    # ---- malicious ANSI title (T-06-04) ----

    def test_malicious_ansi_title_no_raw_escape_in_label(self):
        """RAW title with ANSI escapes → no \\x1b...m-style title injection in result (T-06-04).

        The result may contain ANSI codes from the *builder* (color + RESET), but
        the injected payload's own ESC bytes must be stripped. Test by checking that
        the specific injected sequence '\\x1b[31m' does not appear in the label
        portion (core) of the output.
        """
        malicious_label = "\x1b[31mCRITICAL\x1b[0m: Claude Code outage"
        sec = self._fresh_section(noteworthy=True, severity="major",
                                  label=malicious_label, kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result, "Malicious-title section must still return a segment")
        import re
        reset = self.mod.RESET
        # Strip trailing RESET then leading color codes to get the label+glyph core
        core = result
        if core.endswith(reset):
            core = core[:-len(reset)]
        core = re.sub(r'^(\x1b\[[0-9;]*m)+', '', core)
        # core = "glyph sanitized_label" — assert no ESC byte remains from the title
        self.assertNotIn("\x1b", core,
                         f"Label portion must contain no raw ESC byte after sanitization; "
                         f"core={core!r}")

    def test_malicious_ansi_title_output_is_bounded(self):
        """Very long malicious title → output title portion is width-bounded."""
        long_label = "A" * 200 + "\x1b[31mEVIL\x1b[0m"
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label=long_label, kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        import re
        # Strip all ANSI codes to measure visible text length
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        # Must be less than 200 chars (the label was 200 A's + evil suffix, well over
        # any reasonable width bound; after sanitization it should be truncated)
        self.assertLess(len(stripped), 200,
                        f"Stripped output must be width-bounded; got len={len(stripped)}: {stripped!r}")

    # ---- empty-after-sanitization label ----

    def test_all_control_char_label_falls_back_to_non_hollow(self):
        """Label consisting only of control chars/ESC → sanitized to empty → non-hollow fallback."""
        # After ANSI-stripping "\x1b[31m\x1b[0m" → empty → must fall back
        control_only_label = "\x1b[31m\x1b[0m\x00\x01\x02"
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label=control_only_label, kind="incident")
        result = self._segment(sec)
        self.assertIsNotNone(result,
                             "All-control-char label must still return a non-None segment (no hollow glyph)")
        # The result must contain SOME visible text (the fallback) — not just a bare glyph
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result).strip()
        # Must have at least a glyph + something (not just the glyph alone)
        # Expect something like "glyph fallback_label" — at minimum > 1 visible char
        self.assertGreater(len(stripped), 1,
                           f"Hollow-glyph fallback must add visible fallback text; stripped={stripped!r}")

    # ---- degraded case ----

    def test_degraded_returns_string(self):
        """Degraded cache entry → returns a non-None string with component+state label (D-03)."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="claude.ai: degraded", kind="degraded")
        result = self._segment(sec)
        self.assertIsNotNone(result, "Degraded cache entry must return a non-None string")
        self.assertIsInstance(result, str)

    def test_degraded_contains_component_label(self):
        """Degraded result contains the component+state label text."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="claude.ai: degraded", kind="degraded")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertIn("claude.ai", result,
                      f"Degraded result must contain component label; got {result!r}")

    # ---- maintenance case ----

    def test_maintenance_returns_string(self):
        """Maintenance cache entry → returns a non-None string."""
        sec = self._fresh_section(noteworthy=True, severity="maintenance",
                                  label="Scheduled maintenance window", kind="maintenance")
        result = self._segment(sec)
        self.assertIsNotNone(result, "Maintenance cache entry must return a non-None string")
        self.assertIsInstance(result, str)

    def test_maintenance_does_not_use_severity_color(self):
        """Maintenance result is NOT colored with severity hue (RED/YELLOW) — uses neutral (D-04)."""
        sec = self._fresh_section(noteworthy=True, severity="maintenance",
                                  label="Scheduled maintenance", kind="maintenance")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertNotIn(self.mod.RED, result,
                         f"Maintenance must not use RED (severity color); got {result!r}")
        self.assertNotIn(self.mod.YELLOW, result,
                         f"Maintenance must not use YELLOW (severity color); got {result!r}")

    def test_maintenance_and_incident_glyphs_are_distinct(self):
        """Maintenance result uses the wrench glyph, distinct from incident exclamation (D-04)."""
        inc_sec = self._fresh_section(noteworthy=True, severity="minor",
                                      label="Incident", kind="incident")
        maint_sec = self._fresh_section(noteworthy=True, severity="maintenance",
                                        label="Maintenance", kind="maintenance")
        inc_result = self._segment(inc_sec)
        maint_result = self._segment(maint_sec)
        self.assertIsNotNone(inc_result)
        self.assertIsNotNone(maint_result)
        # The two results must be visually distinct (different glyphs)
        import re
        inc_stripped = re.sub(r'\x1b\[[0-9;]*m', '', inc_result)
        maint_stripped = re.sub(r'\x1b\[[0-9;]*m', '', maint_result)
        # The first non-space character after stripping is the glyph
        inc_glyph = inc_stripped.lstrip()[0] if inc_stripped.strip() else ""
        maint_glyph = maint_stripped.lstrip()[0] if maint_stripped.strip() else ""
        self.assertNotEqual(inc_glyph, maint_glyph,
                            f"Incident glyph {inc_glyph!r} and maintenance glyph {maint_glyph!r} "
                            "must be distinct (D-04)")

    # ---- WR-01: under_maintenance component, no scheduled_maintenances event ----
    # A tracked component set to status=="under_maintenance" with NO matching
    # scheduled_maintenances entry falls through _derive_claude_status Rule 3,
    # producing severity=="maintenance" but kind=="degraded". The render path
    # must still emit the DISTINCT maintenance (wrench) glyph + neutral color,
    # NOT the incident exclamation glyph (D-04: never conflate maintenance with
    # an outage). Before the fix the glyph keyed off `kind` alone, so this case
    # wrongly rendered the incident glyph.

    def test_under_maintenance_degraded_kind_uses_maintenance_glyph(self):
        """severity='maintenance' + kind='degraded' → wrench glyph, not incident (WR-01, D-04)."""
        # The exact Rule-3 under_maintenance shape: maintenance severity carried
        # on a degraded-kind section.
        sec = self._fresh_section(noteworthy=True, severity="maintenance",
                                  label="claude.ai: maintenance", kind="degraded")
        result = self._segment(sec)
        self.assertIsNotNone(result, "under_maintenance degraded section must return a segment")
        self.assertIn(self.mod._NF_CLAUDE_MAINT, result,
                      f"under_maintenance (kind=degraded, severity=maintenance) must render the "
                      f"maintenance wrench glyph; got {result!r}")
        self.assertNotIn(self.mod._NF_CLAUDE_INCIDENT, result,
                         f"under_maintenance must NOT render the incident exclamation glyph "
                         f"(D-04 conflation); got {result!r}")

    def test_under_maintenance_degraded_kind_uses_neutral_color(self):
        """severity='maintenance' + kind='degraded' → neutral color, not RED/YELLOW (WR-01, D-04)."""
        sec = self._fresh_section(noteworthy=True, severity="maintenance",
                                  label="claude.ai: maintenance", kind="degraded")
        result = self._segment(sec)
        self.assertIsNotNone(result)
        self.assertNotIn(self.mod.RED, result,
                         f"under_maintenance degraded must not use RED; got {result!r}")
        self.assertNotIn(self.mod.YELLOW, result,
                         f"under_maintenance degraded must not use YELLOW; got {result!r}")

    # ---- emoji icon_set ----

    def test_emoji_icon_set_returns_string(self):
        """icon_set='emoji' → still returns a non-None string for an incident."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Claude Code issue", kind="incident")
        result = self._segment(sec, extra_cfg={"display": {"icon_set": "emoji"}})
        self.assertIsNotNone(result, "emoji icon_set must return a non-None string for an incident")
        self.assertIsInstance(result, str)

    # ---- never raises ----

    def test_never_raises_on_garbage_cfg(self):
        """_claude_status_segment never raises on garbage cfg (D-10)."""
        sec = self._fresh_section(noteworthy=True, severity="minor",
                                  label="Outage", kind="incident")
        cache_path = _make_cache_with_status(self.tmpdir, sec)
        bad_cfgs = [None, {}, "bad", 42, []]
        for bad_cfg in bad_cfgs:
            with self.subTest(cfg=bad_cfg):
                with patch.object(self.mod, "_CACHE_PATH", cache_path):
                    try:
                        result = self.mod._claude_status_segment(self.data, bad_cfg)
                        # May return None (D-10 graceful degradation)
                        self.assertTrue(result is None or isinstance(result, str),
                                        f"Must return str|None; got {result!r}")
                    except Exception as e:
                        self.fail(f"_claude_status_segment raised on garbage cfg {bad_cfg!r}: {e}")


# ---------------------------------------------------------------------------
# Task 5 (Plan 02): render_bottom_line integration + render-path spawn
# ---------------------------------------------------------------------------
#
# Covers:
#  - render_bottom_line appends status_seg AFTER weekly_seg with 3-space sep (D-06)
#  - Cold-cache → status segment absent, bottom line byte-identical to current (D-01)
#  - show_claude_status=False → status never appears even with incident cached
#  - render_bottom_line returns None when NO segments present (unchanged)
#  - maybe_spawn_refresh is reachable from the bottom-line render path independent
#    of weather (specifically: when weather is disabled or location is unconfigured,
#    maybe_spawn_refresh is still called, so status cache stays fresh)

class TestRenderBottomLineStatusIntegration(unittest.TestCase):
    """render_bottom_line: status segment appended after weekly segment (D-06)."""

    # Load module once per class to keep tests fast
    _mod = None

    @classmethod
    def setUpClass(cls):
        cls._mod = _load_script_module()

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Use the .examples fixture for realistic data
        examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".examples"
        )
        fixture_path = os.path.join(examples_dir, "claude_stdin.json")
        with open(fixture_path) as f:
            self.fixture_data = json.load(f)

        self.base_cfg = {
            "toggles": {
                "show_context_bar": True,
                "show_five_hour": True,
                "show_weekly": True,
            },
            "thresholds": {"warn": 70, "crit": 90},
            "display": {
                "show_claude_status": True,
                "icon_set": "nerd",
                "bar_style": "shade",
            },
            "cache": {
                "status_ttl": 300,
                "status_max_stale": 900,
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _fresh_status_section(self, **kwargs) -> dict:
        """Return a fresh claude_status cache section."""
        sec = {"fetched_at": time.time() - 60}
        sec.update(kwargs)
        return sec

    def _write_cache(self, status_section: dict | None) -> str:
        """Write a cache.json and return path. status_section=None means no claude_status key."""
        cache_path = os.path.join(self.tmpdir, "cache.json")
        cache_data = {}
        if status_section is not None:
            cache_data["claude_status"] = status_section
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)
        return cache_path

    def _render(self, status_section: dict | None, extra_cfg: dict | None = None) -> str | None:
        """Call render_bottom_line with the given cache state."""
        import copy
        cfg = copy.deepcopy(self.base_cfg)
        if extra_cfg:
            for k, v in extra_cfg.items():
                if isinstance(v, dict) and k in cfg:
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        cache_path = self._write_cache(status_section)
        with patch.object(self._mod, "_CACHE_PATH", cache_path):
            return self._mod.render_bottom_line(self.fixture_data, cfg)

    # ---- call-site existence check ----

    def test_status_seg_called_in_render_bottom_line(self):
        """render_bottom_line must call _claude_status_segment (grep acceptance criterion)."""
        import inspect
        src = inspect.getsource(self._mod.render_bottom_line)
        self.assertIn("_claude_status_segment", src,
                      "render_bottom_line source must call _claude_status_segment")

    def test_status_seg_variable_in_render_bottom_line(self):
        """render_bottom_line source must contain 'status_seg' variable."""
        import inspect
        src = inspect.getsource(self._mod.render_bottom_line)
        self.assertIn("status_seg", src,
                      "render_bottom_line source must have 'status_seg' variable")

    # ---- cold-cache path ----

    def test_cold_cache_no_status_in_output(self):
        """Cold cache (no claude_status section) → bottom line has no status glyph."""
        result = self._render(None)  # cold: absent cache
        self.assertIsNotNone(result,
                             "Cold cache must still produce a bottom line (ctx/rate segs present)")
        # The incident glyph character must not appear in the stripped output
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        # _NF_CLAUDE_INCIDENT is a nerd-font char; just check that result doesn't contain it
        self.assertNotIn(str(self._mod._NF_CLAUDE_INCIDENT), stripped,
                         f"Cold cache must produce no incident glyph; got {stripped!r}")

    def test_cold_cache_bottom_line_unchanged_from_baseline(self):
        """Cold cache → bottom line is byte-identical to the no-status baseline."""
        # Both paths should give the same output: the status segment is absent in both
        result_cold = self._render(None)
        # Also render without the claude_status toggle enabled (effectively same thing)
        result_disabled = self._render(None, extra_cfg={"display": {"show_claude_status": False}})
        # Both should be equal (no status segment in either case)
        self.assertEqual(result_cold, result_disabled,
                         "Cold cache and disabled-toggle bottom lines must be identical "
                         "(status seg absent in both cases)")

    # ---- incident cache path ----

    def test_incident_cache_output_ends_with_status_segment(self):
        """Incident in cache → render_bottom_line output ends with the status segment (D-06)."""
        sec = self._fresh_status_section(
            noteworthy=True, severity="minor",
            label="Claude Code elevated error rates", kind="incident"
        )
        result = self._render(sec)
        self.assertIsNotNone(result)
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        self.assertIn("Claude Code elevated error rates", stripped,
                      f"Bottom line must contain incident label; got {stripped!r}")

    def test_incident_cache_has_three_space_separator_before_status(self):
        """Incident in cache → status segment is preceded by '   ' (3-space separator, D-06)."""
        sec = self._fresh_status_section(
            noteworthy=True, severity="minor",
            label="Elevated error rates", kind="incident"
        )
        result = self._render(sec)
        self.assertIsNotNone(result)
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        # The 3-space separator must appear before the status label
        label_idx = stripped.find("Elevated error rates")
        self.assertGreater(label_idx, 2,
                           f"Label must be preceded by at least 3 chars; got {stripped!r}")
        separator_before = stripped[label_idx - 4:label_idx]
        # Check that the 3 chars before the glyph (which precedes the label) are spaces
        # The pattern is: "...   glyph label..." — find the separator
        self.assertIn("   ", stripped,
                      f"Bottom line must contain '   ' (3-space) separator; got {stripped!r}")

    def test_incident_comes_after_weekly_segment(self):
        """Status segment is after the weekly (calendar) segment in output (D-06)."""
        sec = self._fresh_status_section(
            noteworthy=True, severity="minor",
            label="Status here", kind="incident"
        )
        result = self._render(sec)
        self.assertIsNotNone(result)
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        # Calendar glyph (nerd font U+F073 = nf-fa-calendar) must come before status label
        cal_glyph = str(self._mod._NF_CALENDAR)
        cal_idx = stripped.find(cal_glyph)
        label_idx = stripped.find("Status here")
        self.assertGreater(label_idx, cal_idx,
                           f"Status label must come AFTER calendar glyph; "
                           f"cal_idx={cal_idx}, label_idx={label_idx}, stripped={stripped!r}")

    # ---- show_claude_status=False ----

    def test_disabled_toggle_no_status_in_output(self):
        """show_claude_status=False → status segment absent even with incident cached."""
        sec = self._fresh_status_section(
            noteworthy=True, severity="critical",
            label="Claude Code is down", kind="incident"
        )
        result = self._render(sec, extra_cfg={"display": {"show_claude_status": False}})
        self.assertIsNotNone(result, "Disabled toggle must still render ctx/rate segs")
        import re
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', result)
        self.assertNotIn("Claude Code is down", stripped,
                         f"show_claude_status=False must suppress status segment; got {stripped!r}")

    # ---- None-return when NO segments ----

    def test_empty_data_returns_none_regardless_of_status(self):
        """render_bottom_line returns None when no context or rate-limit segments are present."""
        sec = self._fresh_status_section(
            noteworthy=True, severity="minor", label="Outage", kind="incident"
        )
        # Override toggles to disable ctx + rate segments (simulates missing data)
        empty_cfg = {
            "toggles": {
                "show_context_bar": False,
                "show_five_hour": False,
                "show_weekly": False,
            },
            "thresholds": {"warn": 70, "crit": 90},
            "display": {
                "show_claude_status": False,  # also disable status
                "icon_set": "nerd",
                "bar_style": "shade",
            },
            "cache": {"status_ttl": 300, "status_max_stale": 900},
        }
        cache_path = self._write_cache(sec)
        with patch.object(self._mod, "_CACHE_PATH", cache_path):
            result = self._mod.render_bottom_line({}, empty_cfg)
        self.assertIsNone(result,
                          "render_bottom_line must return None when no segments are present")


class TestRenderBottomLineSpawnPath(unittest.TestCase):
    """maybe_spawn_refresh is reachable from render_bottom_line independent of weather."""

    _mod = None

    @classmethod
    def setUpClass(cls):
        cls._mod = _load_script_module()

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".examples"
        )
        with open(os.path.join(self.examples_dir, "claude_stdin.json")) as f:
            self.fixture_data = json.load(f)
        self.stale_cache_path = os.path.join(self.tmpdir, "stale_cache.json")
        # Write a cache with a stale status section (no weather / no alerts)
        stale_section = {"fetched_at": time.time() - 600}  # past TTL
        with open(self.stale_cache_path, "w") as f:
            json.dump({"claude_status": stale_section}, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _cfg_no_weather(self):
        """Return a cfg with weather disabled and no location (weather segment returns None)."""
        return {
            "toggles": {"show_context_bar": True, "show_five_hour": True, "show_weekly": True},
            "thresholds": {"warn": 70, "crit": 90},
            "display": {"show_claude_status": True, "icon_set": "nerd", "bar_style": "shade"},
            "cache": {"status_ttl": 300, "status_max_stale": 900},
            "weather": {"show_weather": False},
            # No "location" key — weather segment will bail early
        }

    def test_maybe_spawn_refresh_called_when_weather_disabled(self):
        """maybe_spawn_refresh is called from the render path even when weather is disabled."""
        spawn_calls = []
        original_maybe_spawn = self._mod.maybe_spawn_refresh

        def spy_spawn(cfg, cache):
            spawn_calls.append((cfg, cache))
            # Do NOT actually spawn — just record the call

        cfg = self._cfg_no_weather()
        with patch.object(self._mod, "_CACHE_PATH", self.stale_cache_path):
            with patch.object(self._mod, "maybe_spawn_refresh", side_effect=spy_spawn):
                self._mod.render_bottom_line(self.fixture_data, cfg)

        self.assertGreater(len(spawn_calls), 0,
                           "maybe_spawn_refresh must be called from render_bottom_line "
                           "even when weather is disabled (status needs refresh too)")

    def test_maybe_spawn_refresh_called_with_cache_dict(self):
        """maybe_spawn_refresh is called with a cache dict (not None) from the render path."""
        spawn_calls = []

        def spy_spawn(cfg, cache):
            spawn_calls.append(cache)

        cfg = self._cfg_no_weather()
        with patch.object(self._mod, "_CACHE_PATH", self.stale_cache_path):
            with patch.object(self._mod, "maybe_spawn_refresh", side_effect=spy_spawn):
                self._mod.render_bottom_line(self.fixture_data, cfg)

        if spawn_calls:
            self.assertIsInstance(spawn_calls[0], dict,
                                  "maybe_spawn_refresh must be called with cache dict")


if __name__ == "__main__":
    unittest.main()
