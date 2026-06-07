#!/usr/bin/env python3
"""
Tests for Plan 02-03: Alert dedup + severity selection + _alert_color + render.

Task 1 covers:
  - dedup_alerts(alerts, now): references-chain dedup — drops referenced identifiers,
    Cancel/Ack/Error alerts, and expired alerts; returns survivors sorted by sent desc
  - select_alert(survivors): returns (highest_severity_alert, remaining_count) using
    the Extreme > Severe > Moderate > Minor > Unknown rank
  - _alert_color(severity): RED for Extreme/Severe, YELLOW for Moderate/Minor

Task 2 covers:
  - fetch_alerts(cfg): GETs /alerts/active?point=lat,lon with ld+json Accept header,
    dedups, writes alerts cache section; honors CLAUDE_STATUSLINE_FAKE_ALERTS env var
  - run_refresh extended: refreshes both weather and alerts under the single lock
  - _weather_segment trailing detail: alert override when within-ceiling active alert,
    else sun event fallback
  - maybe_spawn_refresh triggers on stale alerts section
"""

import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
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


def _make_alert(
    identifier: str,
    event: str,
    severity: str,
    msg_type: str = "Alert",
    references: list | None = None,
    sent: str = "2026-05-28T20:00:00Z",
    expires: str = "2099-12-31T23:59:59Z",
    urgency: str = "Unknown",
    certainty: str = "Unknown",
    vtec: list | None = None,
) -> dict:
    """Build a minimal NWS alert dict (feature.properties shape)."""
    props = {
        "id": identifier,
        "event": event,
        "severity": severity,
        "messageType": msg_type,
        "references": references if references is not None else [],
        "sent": sent,
        "expires": expires,
        "urgency": urgency,
        "certainty": certainty,
    }
    if vtec is not None:
        props["parameters"] = {"VTEC": vtec}
    return {"id": identifier, "properties": props}


# ---------------------------------------------------------------------------
# Task 1: dedup_alerts
# ---------------------------------------------------------------------------

class TestDedupAlerts(unittest.TestCase):

    def setUp(self):
        self.mod = _load_script_module()
        # Reference time well in the future so nothing expires
        self.now = datetime(2026, 5, 28, 23, 0, 0, tzinfo=timezone.utc)

    def test_dedup_alerts_exists(self):
        self.assertTrue(callable(getattr(self.mod, "dedup_alerts", None)))

    def test_empty_input_returns_empty(self):
        result = self.mod.dedup_alerts([], now=self.now)
        self.assertEqual(result, [])

    def test_referenced_alert_is_suppressed(self):
        """An alert listed in another alert's references must be dropped."""
        old = _make_alert("old-001", "Tornado Watch", "Severe",
                           sent="2026-05-28T17:00:00Z")
        new = _make_alert("new-002", "Tornado Warning", "Extreme",
                           msg_type="Update",
                           references=[{"identifier": "old-001"}],
                           sent="2026-05-28T18:00:00Z")
        result = self.mod.dedup_alerts([old, new], now=self.now)
        ids = [a["properties"]["id"] for a in result]
        self.assertIn("new-002", ids, "The update alert must survive")
        self.assertNotIn("old-001", ids, "The referenced (superseded) alert must be dropped")

    def test_cancel_alert_is_suppressed(self):
        """An alert with messageType=Cancel must be dropped."""
        alert = _make_alert("cancel-001", "Special Weather Statement", "Minor",
                             msg_type="Cancel")
        result = self.mod.dedup_alerts([alert], now=self.now)
        self.assertEqual(result, [], "Cancel alert must be removed")

    def test_ack_alert_is_suppressed(self):
        """An alert with messageType=Ack must be dropped."""
        alert = _make_alert("ack-001", "Some Alert", "Minor", msg_type="Ack")
        result = self.mod.dedup_alerts([alert], now=self.now)
        self.assertEqual(result, [], "Ack alert must be removed")

    def test_error_alert_is_suppressed(self):
        """An alert with messageType=Error must be dropped."""
        alert = _make_alert("err-001", "Some Alert", "Minor", msg_type="Error")
        result = self.mod.dedup_alerts([alert], now=self.now)
        self.assertEqual(result, [], "Error alert must be removed")

    def test_expired_alert_is_dropped(self):
        """An alert with expires < now must be removed even if not superseded."""
        past = datetime(2026, 1, 1, tzinfo=timezone.utc)
        alert = _make_alert("exp-001", "Winter Storm Warning", "Severe",
                             expires="2026-01-01T00:00:00Z")
        result = self.mod.dedup_alerts([alert], now=self.now)
        self.assertEqual(result, [], "Expired alert must be dropped")

    def test_non_expired_alert_survives(self):
        """An alert with expires in the future survives dedup."""
        alert = _make_alert("live-001", "Tornado Warning", "Extreme")
        result = self.mod.dedup_alerts([alert], now=self.now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["properties"]["id"], "live-001")

    def test_sorted_by_sent_descending(self):
        """Survivors are returned sorted by sent descending (newest first)."""
        a1 = _make_alert("a1", "Flood Watch", "Moderate", sent="2026-05-28T10:00:00Z")
        a2 = _make_alert("a2", "Wind Advisory", "Minor",   sent="2026-05-28T15:00:00Z")
        a3 = _make_alert("a3", "Dense Fog Advisory", "Minor", sent="2026-05-28T12:00:00Z")
        result = self.mod.dedup_alerts([a1, a2, a3], now=self.now)
        ids = [a["properties"]["id"] for a in result]
        self.assertEqual(ids, ["a2", "a3", "a1"])

    def test_superseded_json_fixture(self):
        """Using nws_alerts_superseded.json fixture: referenced+Cancel+expired alerts removed."""
        fixture = _load_fixture("nws_alerts_superseded.json")
        alerts = fixture.get("@graph", [])
        result = self.mod.dedup_alerts(alerts, now=self.now)
        ids = [a["properties"]["id"] for a in result]
        # "new-002" (Update referencing old-001) should survive
        self.assertIn("urn:oid:2.49.0.1.840.0.new002", ids,
                      "Update alert must survive")
        # "old-001" (referenced by new-002) must be dropped
        self.assertNotIn("urn:oid:2.49.0.1.840.0.old001", ids,
                         "Referenced alert must be suppressed")
        # Cancel alert must be dropped
        self.assertNotIn("urn:oid:2.49.0.1.840.0.cancel003", ids,
                         "Cancel alert must be dropped")
        # Expired alert must be dropped
        self.assertNotIn("urn:oid:2.49.0.1.840.0.expired004", ids,
                         "Expired alert must be dropped")

    def test_tolerates_missing_fields(self):
        """dedup_alerts tolerates alerts with missing/malformed fields (no raise)."""
        bad_alert = {"id": "bad", "properties": {}}
        try:
            result = self.mod.dedup_alerts([bad_alert], now=self.now)
            # May return empty or drop the bad alert — just must not raise
        except Exception as e:
            self.fail(f"dedup_alerts raised on malformed alert: {e}")

    def test_tolerates_missing_expires(self):
        """dedup_alerts tolerates an alert with missing expires field (skips that alert)."""
        # Alert with no expires key in properties
        alert = {
            "id": "no-exp",
            "properties": {
                "id": "no-exp",
                "event": "Test Alert",
                "severity": "Minor",
                "messageType": "Alert",
                "references": [],
                "sent": "2026-05-28T20:00:00Z",
            }
        }
        try:
            result = self.mod.dedup_alerts([alert], now=self.now)
        except Exception as e:
            self.fail(f"dedup_alerts raised on missing expires: {e}")

    def test_now_defaults_when_none(self):
        """dedup_alerts works without an explicit now (uses current time as default)."""
        alert = _make_alert("live-x", "Test Alert", "Moderate")
        try:
            result = self.mod.dedup_alerts([alert])  # no now= argument
        except Exception as e:
            self.fail(f"dedup_alerts raised when now=None: {e}")


# ---------------------------------------------------------------------------
# Phase 02.2 Task 2: _classify_alert_class
# ---------------------------------------------------------------------------

class TestClassifyAlertClass(unittest.TestCase):
    """Unit tests for _classify_alert_class — VTEC significance primary, event-name fallback,
    Statement/Other default (D-01, D-02, D-03)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_classify_alert_class_exists(self):
        self.assertTrue(callable(getattr(self.mod, "_classify_alert_class", None)))

    def test_vtec_w_gives_warning(self):
        """VTEC significance W → Warning (D-01)."""
        alert = _make_alert("t1", "Tornado Warning", "Extreme",
                            vtec=["/O.NEW.KTLX.TO.W.0001.000000T0000Z-000000T0000Z/"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Warning")

    def test_vtec_a_gives_watch(self):
        """VTEC significance A → Watch (D-01)."""
        alert = _make_alert("t2", "Tornado Watch", "Severe",
                            vtec=["/O.NEW.KTOR.TO.A.0002.000000T0000Z-000000T0000Z/"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Watch")

    def test_vtec_y_gives_advisory(self):
        """VTEC significance Y → Advisory (D-01)."""
        alert = _make_alert("t3", "Wind Advisory", "Minor",
                            vtec=["/O.NEW.KOUN.WI.Y.0003.000000T0000Z-000000T0000Z/"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Advisory")

    def test_vtec_s_gives_statement(self):
        """VTEC significance S → Statement/Other (D-01)."""
        alert = _make_alert("t4", "Special Weather Statement", "Unknown",
                            vtec=["/O.NEW.KOUN.SP.S.0001.000000T0000Z-000000T0000Z/"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Statement/Other")

    def test_vtec_f_gives_statement(self):
        """VTEC significance F → Statement/Other (D-01)."""
        alert = _make_alert("t5", "Flood Statement", "Unknown",
                            vtec=["/O.NEW.KOUN.FL.F.0001.000000T0000Z-000000T0000Z/"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Statement/Other")

    def test_event_name_fallback_warning(self):
        """No VTEC present + event ending in 'Warning' → Warning (D-02)."""
        alert = _make_alert("t6", "Tornado Warning", "Extreme")
        self.assertEqual(self.mod._classify_alert_class(alert), "Warning")

    def test_event_name_fallback_watch(self):
        """No VTEC present + event ending in 'Watch' → Watch (D-02)."""
        alert = _make_alert("t7", "Flash Flood Watch", "Severe")
        self.assertEqual(self.mod._classify_alert_class(alert), "Watch")

    def test_event_name_fallback_advisory(self):
        """No VTEC present + event ending in 'Advisory' → Advisory (D-02)."""
        alert = _make_alert("t8", "Wind Advisory", "Minor")
        self.assertEqual(self.mod._classify_alert_class(alert), "Advisory")

    def test_unclassifiable_gives_statement(self):
        """Event 'Special Weather Statement' (no trailing Warning/Watch/Advisory) → Statement/Other (D-03)."""
        alert = _make_alert("t9", "Special Weather Statement", "Minor")
        self.assertEqual(self.mod._classify_alert_class(alert), "Statement/Other")

    def test_vtec_with_fewer_than_5_fields_falls_through_to_event_name(self):
        """A malformed VTEC with <5 fields does not crash and falls back to event name."""
        alert = _make_alert("t10", "Tornado Warning", "Extreme",
                            vtec=["MALFORMED"])
        self.assertEqual(self.mod._classify_alert_class(alert), "Warning")

    def test_never_raises_on_empty_dict(self):
        """_classify_alert_class({}) returns Statement/Other without raising (D-03)."""
        try:
            result = self.mod._classify_alert_class({})
        except Exception as e:
            self.fail(f"_classify_alert_class raised on {{}}: {e}")
        self.assertEqual(result, "Statement/Other")

    def test_never_raises_loop(self):
        """_classify_alert_class never raises on malformed inputs (D-03, T-02.2-01)."""
        bad_inputs = [
            {},
            {"properties": {}},
            {"properties": {"event": None}},
            {"properties": {"event": 42}},
            {"properties": {"parameters": {"VTEC": None}}},
            {"properties": {"parameters": {"VTEC": []}}},
        ]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                try:
                    result = self.mod._classify_alert_class(bad)
                    self.assertIsInstance(result, str,
                                         f"Expected str, got {type(result)} for {bad}")
                except Exception as e:
                    self.fail(f"_classify_alert_class raised on {bad!r}: {e}")


# ---------------------------------------------------------------------------
# Phase 02.2 Task 2: _alert_intensity
# ---------------------------------------------------------------------------

class TestAlertIntensity(unittest.TestCase):
    """Unit tests for _alert_intensity — three-band bold/normal/dim model (D-06)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_alert_intensity_exists(self):
        self.assertTrue(callable(getattr(self.mod, "_alert_intensity", None)))

    def test_immediate_observed_returns_bold(self):
        """Immediate urgency + Observed certainty → BOLD (D-06 top band)."""
        alert = _make_alert("i1", "Tornado Warning", "Extreme",
                            urgency="Immediate", certainty="Observed")
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, self.mod.BOLD,
                         f"Immediate+Observed should be BOLD, got {result!r}")

    def test_expected_likely_returns_empty(self):
        """Expected urgency + Likely certainty → "" (normal, no modifier) (D-06 middle band)."""
        alert = _make_alert("i2", "Flash Flood Watch", "Severe",
                            urgency="Expected", certainty="Likely")
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, "",
                         f"Expected+Likely should be '' (normal), got {result!r}")

    def test_future_urgency_returns_dim(self):
        """Future urgency → DIM (D-06 low band)."""
        alert = _make_alert("i3", "Wind Advisory", "Minor",
                            urgency="Future", certainty="Possible")
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, self.mod.DIM,
                         f"Future urgency should be DIM, got {result!r}")

    def test_possible_certainty_returns_dim(self):
        """Possible certainty (any urgency) → DIM (D-06 low band)."""
        alert = _make_alert("i4", "Tornado Watch", "Severe",
                            urgency="Expected", certainty="Possible")
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, self.mod.DIM,
                         f"Possible certainty should be DIM, got {result!r}")

    def test_unlikely_certainty_returns_dim(self):
        """Unlikely certainty → DIM (D-06 low band)."""
        alert = _make_alert("i5", "Wind Advisory", "Minor",
                            urgency="Expected", certainty="Unlikely")
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, self.mod.DIM,
                         f"Unlikely certainty should be DIM, got {result!r}")

    def test_unknown_urgency_certainty_returns_empty(self):
        """Unknown urgency and certainty (default) → "" (normal, no modifier)."""
        alert = _make_alert("i6", "Test Alert", "Moderate")  # defaults: Unknown/Unknown
        result = self.mod._alert_intensity(alert)
        self.assertEqual(result, "",
                         f"Unknown/Unknown should be '' (normal), got {result!r}")

    def test_never_raises_on_malformed(self):
        """_alert_intensity never raises and returns '' on malformed input (T-02.2-01)."""
        bad_inputs = [{}, {"properties": {}}, {"properties": {"urgency": None}}, None]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                try:
                    if bad is None:
                        # _alert_intensity expects a dict; pass empty dict as None substitute
                        result = self.mod._alert_intensity({})
                    else:
                        result = self.mod._alert_intensity(bad)
                    self.assertIsInstance(result, str,
                                         f"Expected str return, got {type(result)} for {bad!r}")
                except Exception as e:
                    self.fail(f"_alert_intensity raised on {bad!r}: {e}")


# ---------------------------------------------------------------------------
# Task 1: select_alert
# ---------------------------------------------------------------------------

class TestSelectAlert(unittest.TestCase):

    def setUp(self):
        self.mod = _load_script_module()

    def test_select_alert_exists(self):
        self.assertTrue(callable(getattr(self.mod, "select_alert", None)))

    def test_empty_survivors_returns_none(self):
        """select_alert on an empty list returns (None, 0) or similar."""
        result = self.mod.select_alert([])
        # Should not raise; result indicates no selection
        self.assertIsNotNone(result)
        best, count = result
        self.assertIsNone(best, "Best alert must be None for empty survivors")
        self.assertEqual(count, 0, "Remaining count must be 0 for empty survivors")

    def test_extreme_beats_severe(self):
        """Extreme severity alert is selected over Severe."""
        extreme = _make_alert("e1", "Tornado Warning", "Extreme")
        severe = _make_alert("s1", "Severe Thunderstorm Warning", "Severe")
        best, remaining = self.mod.select_alert([extreme, severe])
        self.assertEqual(best["properties"]["severity"], "Extreme")
        self.assertEqual(remaining, 1)

    def test_severe_beats_moderate(self):
        """Severe severity alert is selected over Moderate."""
        severe = _make_alert("s1", "Severe Thunderstorm Warning", "Severe")
        moderate = _make_alert("m1", "Flash Flood Watch", "Moderate")
        best, remaining = self.mod.select_alert([severe, moderate])
        self.assertEqual(best["properties"]["severity"], "Severe")
        self.assertEqual(remaining, 1)

    def test_moderate_beats_minor(self):
        """Moderate severity alert is selected over Minor."""
        moderate = _make_alert("m1", "Flood Watch", "Moderate")
        minor = _make_alert("mi1", "Wind Advisory", "Minor")
        best, remaining = self.mod.select_alert([moderate, minor])
        self.assertEqual(best["properties"]["severity"], "Moderate")
        self.assertEqual(remaining, 1)

    def test_single_alert_remaining_zero(self):
        """A single survivor: remaining count is 0."""
        alert = _make_alert("a1", "Tornado Warning", "Extreme")
        best, remaining = self.mod.select_alert([alert])
        self.assertIsNotNone(best)
        self.assertEqual(remaining, 0)

    def test_three_alerts_remaining_two(self):
        """Three survivors: best selected, remaining = 2."""
        extreme = _make_alert("e1", "Tornado Warning", "Extreme")
        severe = _make_alert("s1", "Severe TS Warning", "Severe")
        moderate = _make_alert("m1", "Flash Flood Watch", "Moderate")
        best, remaining = self.mod.select_alert([extreme, severe, moderate])
        self.assertEqual(best["properties"]["severity"], "Extreme")
        self.assertEqual(remaining, 2)

    def test_active_fixture_highest_severity_and_remaining(self):
        """With nws_alerts_active.json fixture: Extreme selected, remaining=2."""
        fixture = _load_fixture("nws_alerts_active.json")
        alerts = fixture.get("@graph", [])
        best, remaining = self.mod.select_alert(alerts)
        self.assertIsNotNone(best)
        self.assertEqual(best["properties"]["severity"], "Extreme")
        self.assertEqual(remaining, 2)

    def test_tolerates_unknown_severity(self):
        """select_alert handles Unknown severity without raising."""
        alert = _make_alert("u1", "Some Alert", "Unknown")
        try:
            result = self.mod.select_alert([alert])
        except Exception as e:
            self.fail(f"select_alert raised on Unknown severity: {e}")

    def test_tolerates_empty_survivors(self):
        """select_alert([]) returns gracefully (no raise)."""
        try:
            self.mod.select_alert([])
        except Exception as e:
            self.fail(f"select_alert raised on empty: {e}")


# ---------------------------------------------------------------------------
# Task 1: _alert_color
# ---------------------------------------------------------------------------

class TestAlertColor(unittest.TestCase):

    def setUp(self):
        self.mod = _load_script_module()

    def test_alert_color_exists(self):
        self.assertTrue(callable(getattr(self.mod, "_alert_color", None)))

    def test_extreme_returns_red(self):
        """Extreme severity -> RED."""
        color = self.mod._alert_color("Extreme")
        self.assertEqual(color, self.mod.RED, "Extreme must be RED")

    def test_severe_returns_red(self):
        """Severe severity -> RED."""
        color = self.mod._alert_color("Severe")
        self.assertEqual(color, self.mod.RED, "Severe must be RED")

    def test_moderate_returns_yellow(self):
        """Moderate severity -> YELLOW."""
        color = self.mod._alert_color("Moderate")
        self.assertEqual(color, self.mod.YELLOW, "Moderate must be YELLOW")

    def test_minor_returns_yellow(self):
        """Minor severity -> YELLOW."""
        color = self.mod._alert_color("Minor")
        self.assertEqual(color, self.mod.YELLOW, "Minor must be YELLOW")

    def test_unknown_returns_non_red(self):
        """Unknown severity -> YELLOW or DIM (not RED)."""
        color = self.mod._alert_color("Unknown")
        self.assertNotEqual(color, self.mod.RED, "Unknown must not be RED")

    def test_unknown_returns_a_color(self):
        """Unknown severity -> returns a non-empty string."""
        color = self.mod._alert_color("Unknown")
        self.assertIsNotNone(color)
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0)

    def test_nonsense_severity_does_not_raise(self):
        """Nonsense severity value does not raise."""
        try:
            result = self.mod._alert_color("BLARGHHH")
        except Exception as e:
            self.fail(f"_alert_color raised on unknown severity: {e}")


# ---------------------------------------------------------------------------
# Task 2: fetch_alerts
# ---------------------------------------------------------------------------

class TestFetchAlerts(unittest.TestCase):
    """fetch_alerts: GETs NWS alerts/active, dedups, writes cache section."""

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
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fetch_alerts_exists(self):
        self.assertTrue(callable(getattr(self.mod, "fetch_alerts", None)))

    def test_fetch_alerts_endpoint_in_source(self):
        """Source contains the /alerts/active endpoint path."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("alerts/active", source)

    def test_fetch_alerts_ld_json_in_source(self):
        """Source sends Accept: application/ld+json for the alerts request."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("ld+json", source)

    def test_fetch_alerts_writes_cache_section_with_fake_fixture(self):
        """fetch_alerts with CLAUDE_STATUSLINE_FAKE_ALERTS writes the alerts cache section."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — requests not installed")
        fake_path = os.path.join(FIXTURES_DIR, "nws_alerts_active.json")
        env = {"CLAUDE_STATUSLINE_FAKE_ALERTS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_alerts(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("alerts", data, "fetch_alerts must write the 'alerts' cache section")

    def test_fetch_alerts_fake_fixture_deduped_survivors(self):
        """fetch_alerts with active fixture writes deduped survivors (all 3 from active fixture survive)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — requests not installed")
        fake_path = os.path.join(FIXTURES_DIR, "nws_alerts_active.json")
        env = {"CLAUDE_STATUSLINE_FAKE_ALERTS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_alerts(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        active = data["alerts"].get("active", [])
        self.assertGreater(len(active), 0, "Active survivors must be written to cache")

    def test_fetch_alerts_superseded_fixture_deduped(self):
        """fetch_alerts with superseded fixture: only the Update alert survives."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — requests not installed")
        fake_path = os.path.join(FIXTURES_DIR, "nws_alerts_superseded.json")
        env = {"CLAUDE_STATUSLINE_FAKE_ALERTS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_alerts(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        active = data["alerts"].get("active", [])
        ids = [a["properties"]["id"] for a in active]
        self.assertIn("urn:oid:2.49.0.1.840.0.new002", ids,
                      "Update alert must survive dedup")
        self.assertNotIn("urn:oid:2.49.0.1.840.0.old001", ids,
                         "Referenced alert must be dropped")
        self.assertNotIn("urn:oid:2.49.0.1.840.0.cancel003", ids,
                         "Cancel alert must be dropped")
        self.assertNotIn("urn:oid:2.49.0.1.840.0.expired004", ids,
                         "Expired alert must be dropped")

    def test_fetch_alerts_swallows_errors(self):
        """fetch_alerts with a failing _nws_get does not raise."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — requests not installed")

        def bad_nws_get(url, ua, accept=None):
            raise ConnectionError("network down")

        with patch.object(self.mod, "_nws_get", side_effect=bad_nws_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                try:
                    self.mod.fetch_alerts(self.cfg)
                except Exception as e:
                    self.fail(f"fetch_alerts raised: {e}")

    def test_fetch_alerts_no_real_network_call_with_fake(self):
        """When CLAUDE_STATUSLINE_FAKE_ALERTS is set, no real _nws_get is issued."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — requests not installed")
        fake_path = os.path.join(FIXTURES_DIR, "nws_alerts_active.json")
        nws_get_calls = []

        def spy_nws_get(url, ua, accept=None):
            nws_get_calls.append(url)
            return {}

        env = {"CLAUDE_STATUSLINE_FAKE_ALERTS": fake_path}
        with patch.dict(os.environ, env):
            with patch.object(self.mod, "_nws_get", side_effect=spy_nws_get):
                with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                    self.mod.fetch_alerts(self.cfg)

        # _nws_get must NOT have been called (the fake file was used instead)
        self.assertEqual(nws_get_calls, [],
                         "When CLAUDE_STATUSLINE_FAKE_ALERTS is set, _nws_get must not be called")


# ---------------------------------------------------------------------------
# Task 2: run_refresh includes fetch_alerts
# ---------------------------------------------------------------------------

class TestRunRefreshAlerts(unittest.TestCase):
    """run_refresh now calls both fetch_weather and fetch_alerts under the single lock."""

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
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_refresh_calls_fetch_alerts(self):
        """run_refresh calls fetch_alerts (in addition to fetch_weather)."""
        weather_called = []
        alerts_called = []

        def mock_fetch_weather(cfg):
            weather_called.append(True)

        def mock_fetch_alerts(cfg):
            alerts_called.append(True)

        lock_path = os.path.join(self.tmpdir, "refresh.lock")
        cache_path = os.path.join(self.tmpdir, "cache.json")

        with patch.object(self.mod, "fetch_weather", side_effect=mock_fetch_weather):
            with patch.object(self.mod, "fetch_alerts", side_effect=mock_fetch_alerts):
                with patch.object(self.mod, "_CACHE_PATH", cache_path):
                    with patch.object(self.mod, "_LOCK_PATH", lock_path):
                        self.mod.run_refresh(self.cfg)

        self.assertEqual(len(weather_called), 1, "fetch_weather must be called")
        self.assertEqual(len(alerts_called), 1, "fetch_alerts must be called")


# ---------------------------------------------------------------------------
# Task 2: maybe_spawn_refresh triggers on stale alerts section
# ---------------------------------------------------------------------------

class TestMaybeSpawnRefreshAlerts(unittest.TestCase):
    """maybe_spawn_refresh triggers when alerts section is stale."""

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
            },
        }

    def test_spawns_when_alerts_section_stale(self):
        """maybe_spawn_refresh calls Popen when alerts section is stale (past alerts_ttl)."""
        now = time.time()
        # Fresh weather, stale alerts (past 300s alerts_ttl)
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72},
            "alerts": {"fetched_at": now - 600, "active": []},
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertGreater(len(popen_calls), 0,
                           "Popen must be called when alerts section is stale")

    def test_no_spawn_when_both_fresh(self):
        """maybe_spawn_refresh does NOT spawn when both weather and alerts are fresh."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72},
            "alerts": {"fetched_at": now - 60, "active": []},
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertEqual(len(popen_calls), 0,
                         "Popen must NOT be called when both sections are fresh")


# ---------------------------------------------------------------------------
# Task 2: _weather_segment alert override rendering
# ---------------------------------------------------------------------------

class TestWeatherSegmentAlertOverride(unittest.TestCase):
    """_weather_segment replaces sun detail with alert override when within-ceiling."""

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
            },
            "toggles": {"show_thinking_glyph": True},
            "thresholds": {"warn": 70, "crit": 90},
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_segment_with_cache(self, cache_dict, spawn_recorder=None):
        """Call _weather_segment with a monkeypatched read_cache.

        Pins icon_set="emoji" so the three fallback-to-sun tests keep asserting the
        Phase 2 emoji sun glyphs (🌅/🌇) regardless of the nerd default (D-06).
        """
        cache_path = os.path.join(self.tmpdir, "cache.json")
        with open(cache_path, "w") as f:
            json.dump(cache_dict, f)

        def no_op_spawn(cfg, cache):
            if spawn_recorder is not None:
                spawn_recorder.append(True)

        # Pin icon_set="emoji" so emoji codepoint assertions remain valid under
        # the new nerd default introduced in Phase 02.1 Plan 03.
        cfg_with_emoji = dict(self.cfg)
        cfg_with_emoji["display"] = {"icon_set": "emoji"}

        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            with patch.object(self.mod, "maybe_spawn_refresh", side_effect=no_op_spawn):
                result = self.mod._weather_segment(None, cfg_with_emoji)
        return result

    def _make_cache_with_alert(self, severity="Extreme", event="Tornado Warning",
                                extra_alerts=0, age_seconds=60):
        """Build a cache dict with an active alert within the max-stale ceiling."""
        now = time.time()
        future_expires = "2099-12-31T23:59:59Z"
        # Build list of alert dicts
        active = [{
            "id": "alert-001",
            "properties": {
                "id": "alert-001",
                "event": event,
                "severity": severity,
                "messageType": "Alert",
                "references": [],
                "sent": "2026-05-28T20:00:00Z",
                "expires": future_expires,
            }
        }]
        for i in range(extra_alerts):
            active.append({
                "id": f"extra-{i:03d}",
                "properties": {
                    "id": f"extra-{i:03d}",
                    "event": "Flood Watch",
                    "severity": "Moderate",
                    "messageType": "Alert",
                    "references": [],
                    "sent": "2026-05-28T19:00:00Z",
                    "expires": future_expires,
                }
            })
        return {
            "weather": {
                "fetched_at": now - age_seconds,
                "icon": "☀️",
                "temp": 72,
                "pop": 0,
            },
            "alerts": {
                "fetched_at": now - age_seconds,
                "active": active,
            }
        }

    def test_active_alert_replaces_sun_detail(self):
        """When within-ceiling active alert exists, the trailing detail is the alert, not the sun event."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        # Should contain warning glyph or event name
        self.assertIn("Tornado Warning", result,
                      f"Alert event name must appear in segment: {result!r}")

    def test_active_alert_severity_colored_extreme(self):
        """Extreme alert: segment contains RED ANSI color code."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        self.assertIn(self.mod.RED, result,
                      f"RED color expected for Extreme alert: {result!r}")

    def test_active_alert_severity_colored_severe(self):
        """Severe alert: segment contains RED ANSI color code."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Severe", event="Severe Thunderstorm Warning")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        self.assertIn(self.mod.RED, result,
                      f"RED color expected for Severe alert: {result!r}")

    def test_active_alert_severity_colored_moderate(self):
        """Moderate alert: segment contains YELLOW ANSI color code."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Moderate", event="Flash Flood Watch")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        self.assertIn(self.mod.YELLOW, result,
                      f"YELLOW color expected for Moderate alert: {result!r}")

    def test_multiple_alerts_plus_n_suffix(self):
        """Multiple active alerts: +N suffix appears for N remaining alerts."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        # 1 Extreme + 2 extra = 3 total, remaining=2
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning", extra_alerts=2)
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        self.assertIn("+2", result,
                      f"Expected '+2' suffix for 2 remaining alerts: {result!r}")

    def test_conditions_still_present_with_alert(self):
        """Icon+temp are still shown in the segment alongside the alert."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        # Icon (☀️) and temp (72) must still be present
        self.assertIn("72", result, f"Temp must be present alongside alert: {result!r}")

    def test_beyond_max_stale_falls_back_to_sun(self):
        """Alerts beyond alerts_max_stale (900s): trailing detail falls back to sun event."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        # 1000s > 900s alerts_max_stale ceiling
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning",
                                            age_seconds=1000)
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        # Alert event name must NOT appear (stale beyond ceiling)
        self.assertNotIn("Tornado Warning", result,
                         f"Stale alert must not appear; expected sun fallback: {result!r}")
        # Sun glyph must appear instead
        self.assertTrue(
            "\U0001f305" in result or "\U0001f307" in result,
            f"Sun glyph expected after alert staleness fallback: {result!r}"
        )

    def test_no_alerts_falls_back_to_sun(self):
        """Empty active alerts list: trailing detail falls back to sun event."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72, "pop": 0},
            "alerts": {"fetched_at": now - 60, "active": []},
        }
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        # No alert event name; sun glyph present
        self.assertTrue(
            "\U0001f305" in result or "\U0001f307" in result,
            f"Sun glyph expected with empty alerts: {result!r}"
        )

    def test_cold_alerts_section_falls_back_to_sun(self):
        """Missing alerts section (cold): trailing detail falls back to sun event."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72, "pop": 0},
            # no "alerts" key at all
        }
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        self.assertTrue(
            "\U0001f305" in result or "\U0001f307" in result,
            f"Sun glyph expected with cold alerts: {result!r}"
        )

    def test_warning_glyph_in_alert_detail(self):
        """The alert trailing detail includes the warning glyph (⚠)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK False — astral/requests not installed")
        cache = self._make_cache_with_alert(severity="Extreme", event="Tornado Warning")
        result = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        # warning glyph U+26A0 ⚠ must appear in the alert detail
        self.assertIn("⚠", result,
                      f"Warning glyph ⚠ must appear in alert detail: {result!r}")


if __name__ == "__main__":
    unittest.main()
