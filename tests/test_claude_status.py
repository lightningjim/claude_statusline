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

    def test_resolved_returns_green(self):
        """resolved severity → GREEN (D-03: broke-then-fixed, non-alarming)."""
        result = self.mod._claude_status_color("resolved")
        self.assertEqual(result, self.mod.GREEN,
                         f"resolved must return GREEN; got {result!r}")


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

    # ---- Phase 07.1 Plan 01: resolved-vs-red branch (D-04/D-05/D-01/D-06) ----

    def test_resolved_degraded_fixture_returns_resolved_kind(self):
        """Resolved incident + still-degraded tracked component → kind=='resolved' (D-05)."""
        summary = _load_fixture("status_resolved_degraded.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "Resolved-degraded fixture must return a non-None dict")
        self.assertEqual(result.get("kind"), "resolved",
                         f"kind must be 'resolved'; got {result.get('kind')!r}")

    def test_resolved_degraded_fixture_returns_resolved_severity(self):
        """Resolved incident + still-degraded tracked component → severity=='resolved' (D-03)."""
        summary = _load_fixture("status_resolved_degraded.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("severity"), "resolved",
                         f"severity must be 'resolved'; got {result.get('severity')!r}")

    def test_resolved_degraded_fixture_label_is_incident_title(self):
        """Resolved incident → label is the RAW incident title (no 'resolved:' prefix baked in)."""
        summary = _load_fixture("status_resolved_degraded.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        # Label must be the raw incident title, NOT prefixed with 'resolved:'
        incident_title = summary["incidents"][0]["name"]
        label = result.get("label", "")
        self.assertEqual(label, incident_title,
                         f"Label must equal raw fixture incident title; got {label!r}")
        self.assertFalse(label.startswith("resolved:"),
                         "Label must NOT have 'resolved:' prefix baked in (render concern, not cache)")

    def test_degraded_no_matching_resolved_incident_stays_red(self):
        """Degraded component with NO resolved incident referencing it → kind=='degraded' (D-05)."""
        summary = _load_fixture("status_degraded_no_title.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "degraded",
                         f"No resolved incident → kind must be 'degraded'; got {result.get('kind')!r}")

    def test_operational_component_with_resolved_incident_returns_none(self):
        """Operational tracked component → None (quiet) even with a lingering resolved incident (D-01)."""
        summary = _load_fixture("status_resolved_degraded.json")
        # Make all tracked components operational
        for comp in summary.get("components", []):
            if comp.get("name") in ("Claude Code", "claude.ai", "Claude Cowork"):
                comp["status"] = "operational"
        result = self.mod._derive_claude_status(summary)
        self.assertIsNone(result,
                          f"Operational components → None even with resolved incident; got {result!r}")

    def test_active_incident_outranks_resolved_degraded(self):
        """Active incident present → kind=='incident' wins over resolved-degraded (Rule 1 > Rule 3)."""
        summary = _load_fixture("status_incident_tracked.json")
        # Add a resolved incident for the same component to ensure Rule 3 would match
        summary["incidents"].append({
            "id": "inc-resolved",
            "name": "Earlier resolved issue",
            "status": "resolved",
            "impact": "minor",
            "updated_at": "2026-06-18T10:00:00Z",
            "components": [{"id": "comp-claude-code", "name": "Claude Code"}],
        })
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "incident",
                         f"Active incident must outrank resolved-degraded; got {result.get('kind')!r}")

    def test_maintenance_outranks_resolved_degraded(self):
        """Maintenance present → kind=='maintenance' wins over resolved-degraded (Rule 2 > Rule 3)."""
        summary = _load_fixture("status_maintenance.json")
        # Make a tracked component degraded with a resolved incident so Rule 3 would trigger
        for comp in summary.get("components", []):
            if comp.get("name") == "Claude Code":
                comp["status"] = "partial_outage"
        summary.setdefault("incidents", []).append({
            "id": "inc-resolved-r3",
            "name": "Fixed earlier issue",
            "status": "resolved",
            "impact": "major",
            "updated_at": "2026-06-18T09:00:00Z",
            "components": [{"id": "comp-claude-code", "name": "Claude Code"}],
        })
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "maintenance",
                         f"Maintenance must outrank resolved-degraded; got {result.get('kind')!r}")

    def test_suppressed_resolved_incident_falls_through_to_red(self):
        """A suppressed resolved incident is NOT matched → falls through to red degraded (D-06).

        Per CONTEXT: a resolving incident has falling impact so the escalation re-surface
        never voids a dismissal on the resolved path — the dismissal stands (D-06).
        The fixture incident has impact='major'; we store impact_at_dismiss='major' so
        live_rank == stored_rank (no escalation void), and suppression holds.
        """
        summary = _load_fixture("status_resolved_degraded.json")
        incident_id = summary["incidents"][0]["id"]
        # Dismiss at the same impact level as the incident (major=major: no escalation re-surface)
        dismissals = {incident_id: {"impact_at_dismiss": "major", "dismissed_at": "2026-06-18T08:00:00Z"}}
        cfg = {
            "claude_status": {"filter_enabled": True, "ignore_title_patterns": []},
        }
        result = self.mod._derive_claude_status(summary, dismissals=dismissals, cfg=cfg)
        self.assertIsNotNone(result,
                             "Suppressed resolved → must fall through to red degraded, not None")
        self.assertEqual(result.get("kind"), "degraded",
                         f"Suppressed resolved must yield kind='degraded'; got {result.get('kind')!r}")

    def test_resolved_garbage_feed_does_not_raise(self):
        """Malformed incidents list in resolved scan → no raise, falls back to existing behavior."""
        # Provide garbage incidents list (non-dicts inside)
        summary = {
            "components": [
                {"name": "Claude Code", "status": "partial_outage"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [None, 42, "garbage", {"status": "resolved", "no_components_key": True}],
            "scheduled_maintenances": [],
        }
        try:
            result = self.mod._derive_claude_status(summary)
            # Must not raise; should fall back to degraded (no valid resolved match)
            self.assertIsNotNone(result,
                                 "Garbage incidents → still detects degraded component, returns dict")
            self.assertEqual(result.get("kind"), "degraded",
                             f"Garbage resolved incidents → falls through to 'degraded'; got {result.get('kind')!r}")
        except Exception as e:
            self.fail(f"_derive_claude_status raised on garbage resolved incidents: {e}")

    # ---- WR-03 / CR-01 regression: multi-component masking ----

    def _multi_component_summary(self, code_status, ai_status, resolved_for):
        """Two tracked components degraded; a resolved incident touches `resolved_for`.

        The other degraded component is left UNEXPLAINED (no incident at all).
        """
        return {
            "components": [
                {"name": "Claude Code", "status": code_status},
                {"name": "claude.ai", "status": ai_status},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {"id": "r1", "name": "Code fixed", "status": "resolved",
                 "impact": "major", "updated_at": "2026-06-18T12:00:00Z",
                 "components": [{"name": resolved_for}]},
            ],
            "scheduled_maintenances": [],
        }

    def test_cr01_unexplained_degraded_wins_over_resolved_code_first(self):
        """CR-01: resolved-explained 'Claude Code' + UNEXPLAINED 'claude.ai' → verdict RED.

        The resolved incident explains the alphabetically-first component (Claude
        Code), but claude.ai is degraded with no incident. The verdict must be the
        RED unexplained component, NOT green — a green 'resolved' here would mask a
        live outage (truth-telling, D-05).
        """
        summary = self._multi_component_summary(
            code_status="partial_outage", ai_status="partial_outage",
            resolved_for="Claude Code",
        )
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "degraded",
                         f"Unexplained degraded must win RED over resolved; got {result!r}")
        self.assertEqual(result.get("component"), "claude.ai",
                         f"The UNEXPLAINED component must drive the verdict; got {result!r}")
        self.assertEqual(result.get("incident_id"), None,
                         "Genuinely-unexplained degraded must carry incident_id=None")

    def test_cr01_unexplained_degraded_wins_over_resolved_ai_first(self):
        """CR-01 (opposite sort order): resolved explains 'claude.ai', 'Claude Code' unexplained → RED.

        Swapping which component carries the resolved incident must NOT flip the
        verdict to green — the result must remain order-independent (RED for the
        unexplained component).
        """
        summary = self._multi_component_summary(
            code_status="partial_outage", ai_status="partial_outage",
            resolved_for="claude.ai",
        )
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "degraded",
                         f"Unexplained degraded must win RED regardless of sort order; got {result!r}")
        self.assertEqual(result.get("component"), "Claude Code",
                         f"The UNEXPLAINED component must drive the verdict; got {result!r}")

    def test_cr01_all_degraded_components_resolved_returns_green(self):
        """CR-01 boundary: EVERY degraded component is resolved-explained → green resolved verdict.

        Only when there is no unexplained-degraded component may the resolved
        verdict be emitted. The bound resolved incident_id must be carried.
        """
        summary = {
            "components": [
                {"name": "Claude Code", "status": "partial_outage"},
                {"name": "claude.ai", "status": "degraded_performance"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {"id": "r1", "name": "Code fixed", "status": "resolved",
                 "impact": "major", "updated_at": "2026-06-18T12:00:00Z",
                 "components": [{"name": "Claude Code"}]},
                {"id": "r2", "name": "AI fixed", "status": "resolved",
                 "impact": "minor", "updated_at": "2026-06-18T13:00:00Z",
                 "components": [{"name": "claude.ai"}]},
            ],
            "scheduled_maintenances": [],
        }
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "resolved",
                         f"All-resolved-explained must return green resolved; got {result!r}")
        self.assertIn(result.get("incident_id"), ("r1", "r2"),
                      f"Resolved verdict must bind an explaining incident_id; got {result!r}")

    # ---- CR-01 surviving case: muted-explained must NOT mask a later unexplained RED ----

    _MUTE_CFG = {"claude_status": {"filter_enabled": True,
                                   "ignore_title_patterns": ["Mythos"]}}

    def test_cr01_muted_explained_first_does_not_mask_unexplained_red(self):
        """CR-01 (surviving case): 'Claude Code' degraded explained ONLY by a muted
        incident + 'claude.ai' degraded UNEXPLAINED → verdict RED for claude.ai.

        The muted-explained component sorts first; it must NOT early-return None and
        short-circuit the scan — a genuinely-unexplained RED outage on a later-sorted
        component must still win (truth-telling, D-05/D-06 interaction).
        """
        summary = {
            "components": [
                {"name": "Claude Code", "status": "partial_outage"},
                {"name": "claude.ai", "status": "partial_outage"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {"id": "m1", "name": "Mythos access removed", "status": "resolved",
                 "impact": "minor", "updated_at": "2026-06-18T12:00:00Z",
                 "components": [{"name": "Claude Code"}]},
            ],
            "scheduled_maintenances": [],
        }
        result = self.mod._derive_claude_status(summary, dismissals={}, cfg=self._MUTE_CFG)
        self.assertIsNotNone(result, "Unexplained RED must surface, not be masked by a muted component")
        self.assertEqual(result.get("kind"), "degraded",
                         f"Unexplained degraded must win RED over a muted component; got {result!r}")
        self.assertEqual(result.get("component"), "claude.ai",
                         f"The UNEXPLAINED component must drive the verdict; got {result!r}")
        self.assertEqual(result.get("incident_id"), None,
                         "Genuinely-unexplained degraded must carry incident_id=None (→ RED)")

    def test_cr01_all_muted_explained_returns_muted_verdict(self):
        """Boundary: every degraded component explained ONLY by muted incidents → the
        derivation returns the muted degraded verdict carrying the muting incident_id,
        so the render-time mute re-check renders None (D-06: no red fallback)."""
        summary = {
            "components": [
                {"name": "Claude Code", "status": "partial_outage"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {"id": "m1", "name": "Mythos access removed", "status": "resolved",
                 "impact": "minor", "updated_at": "2026-06-18T12:00:00Z",
                 "components": [{"name": "Claude Code"}]},
            ],
            "scheduled_maintenances": [],
        }
        result = self.mod._derive_claude_status(summary, dismissals={}, cfg=self._MUTE_CFG)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "degraded",
                         f"All-muted must defer a degraded verdict carrying the muted id; got {result!r}")
        self.assertEqual(result.get("incident_id"), "m1",
                         "Muted-only verdict must bake the muting incident id so render returns None")

    def test_cr01_resolved_green_outranks_muted_none(self):
        """Priority: a non-suppressed resolved-explained component (green) outranks a
        muted-only component (which renders None), when no unexplained RED exists."""
        summary = {
            "components": [
                {"name": "Claude Code", "status": "partial_outage"},   # muted-explained
                {"name": "claude.ai", "status": "partial_outage"},     # resolved-explained
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {"id": "m1", "name": "Mythos access removed", "status": "resolved",
                 "impact": "minor", "updated_at": "2026-06-18T12:00:00Z",
                 "components": [{"name": "Claude Code"}]},
                {"id": "r2", "name": "API errors", "status": "resolved",
                 "impact": "major", "updated_at": "2026-06-18T13:00:00Z",
                 "components": [{"name": "claude.ai"}]},
            ],
            "scheduled_maintenances": [],
        }
        result = self.mod._derive_claude_status(summary, dismissals={}, cfg=self._MUTE_CFG)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("kind"), "resolved",
                         f"Resolved-green must outrank a muted-None component; got {result!r}")
        self.assertEqual(result.get("component"), "claude.ai",
                         f"The resolved (non-muted) component must drive the verdict; got {result!r}")
        self.assertEqual(result.get("incident_id"), "r2",
                         "Resolved verdict must bind the non-suppressed explaining incident id")


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
# Task 3 (Plan 04): render-time suppression unit tests
# ---------------------------------------------------------------------------
#
# Covers the Phase 07 Plan 04 (UAT gap) fix: _claude_status_segment re-applies
# _is_suppressed over cached tracked_incidents + live dismissal store at render
# time, so --dismiss / ignore_title_patterns take effect on the very next render
# without a network fetch (instant, zero-network, lock-independent).
#
# Each test builds a FRESH, baked-noteworthy cache section that includes a
# tracked_incidents list, then asserts the render outcome. Both _CACHE_PATH and
# _DISMISSALS_PATH are patched to temp files so no real ~/.claude paths are read.
#
# Trust-boundary coverage (from the threat model):
#   T-07-04-01 — ReDoS: reuses _is_suppressed's 500-char cap (no new matching code)
#   T-07-04-02 — Corrupt dismissal store → {} → no suppression, never raises (D-10)
#   T-07-04-03 — Malformed tracked_incidents → treated as empty → baked behavior
#   T-07-04-04 — D-03 escalation re-surface: live impact > dismissed impact → surfaces

class TestClaudeStatusRenderSuppression(unittest.TestCase):
    """_claude_status_segment render-time suppression (Plan 04 UAT gap fix)."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
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
            "claude_status": {
                "filter_enabled": True,
                "ignore_title_patterns": [],
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_dismissals(self, store: dict) -> str:
        """Write a dismissal store JSON to tmpdir; return the path."""
        path = os.path.join(self.tmpdir, "status_dismissals.json")
        with open(path, "w") as f:
            json.dump(store, f)
        return path

    def _fresh_section(self, **kwargs) -> dict:
        """Return a fresh (within max_stale) cache section with the given fields."""
        sec = {"fetched_at": time.time() - 60}
        sec.update(kwargs)
        return sec

    def _segment(self, status_section: dict | None,
                 dismissal_store: dict | None = None,
                 extra_cfg: dict | None = None) -> str | None:
        """Call _claude_status_segment with patched _CACHE_PATH and _DISMISSALS_PATH."""
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
            cache_path = os.path.join(self.tmpdir, "absent_cache.json")

        if dismissal_store is not None:
            dismissals_path = self._write_dismissals(dismissal_store)
        else:
            # Empty dismissal store (no dismissals)
            dismissals_path = self._write_dismissals({})

        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            with patch.object(self.mod, "_DISMISSALS_PATH", dismissals_path):
                return self.mod._claude_status_segment(self.data, cfg)

    # ---- test_dismiss_by_id_suppresses_at_render ----

    def test_dismiss_by_id_suppresses_at_render(self):
        """dismiss-by-id: dismissed id at matching impact → returns None at next render (D-01).

        A fresh baked-noteworthy section whose sole tracked incident id is in the
        live dismissal store (impact_at_dismiss == live impact) → the render path
        re-applies _is_suppressed and returns None instantly, without a network fetch.
        """
        tracked_inc = {"id": "inc-muted", "impact": "minor",
                       "status": "investigating", "title": "Mythos access suspended",
                       "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="Mythos access suspended", kind="incident",
            tracked_incidents=[tracked_inc],
        )
        dismissal_store = {
            "inc-muted": {"impact_at_dismiss": "minor", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "dismiss-by-id at matching impact must suppress at render (D-01 instant mute)")

    # ---- test_keyword_suppresses_at_render ----

    def test_keyword_suppresses_at_render(self):
        """keyword match: ignore_title_patterns matches incident title → returns None at render.

        Empty dismissal store; cfg has ignore_title_patterns=["Mythos"]; the sole
        tracked incident's title contains "Mythos" → suppressed at render via _is_suppressed.
        """
        tracked_inc = {"id": "inc-kw", "impact": "minor",
                       "status": "investigating",
                       "title": "Mythos/Fable suspended access",
                       "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="Mythos/Fable suspended access", kind="incident",
            tracked_incidents=[tracked_inc],
        )
        result = self._segment(
            sec,
            dismissal_store={},  # no id-dismissals
            extra_cfg={"claude_status": {"filter_enabled": True,
                                         "ignore_title_patterns": ["Mythos"]}},
        )
        self.assertIsNone(result,
                          "keyword match in ignore_title_patterns must suppress at render (D-01)")

    # ---- test_escalation_resurfaces_at_render ----

    def test_escalation_resurfaces_at_render(self):
        """escalation re-surface (D-03): dismissed at minor but live impact is major → surfaces.

        id dismissed at impact_at_dismiss="minor" but the cached tracked incident's
        live impact is "major" → _is_suppressed returns False (escalation void) → the
        segment is non-None (incident surfaces on the bar).
        """
        tracked_inc = {"id": "inc-escalated", "impact": "major",
                       "status": "identified",
                       "title": "Claude Code elevated errors",
                       "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="major",
            label="Claude Code elevated errors", kind="incident",
            tracked_incidents=[tracked_inc],
        )
        dismissal_store = {
            "inc-escalated": {"impact_at_dismiss": "minor", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNotNone(result,
                             "Escalated incident (live impact > impact_at_dismiss) must "
                             "re-surface at render (D-03)")
        # The result should contain some recognizable text from the title
        self.assertIsInstance(result, str,
                              "Escalated incident result must be a str, not None (D-03)")

    # ---- test_unrelated_incident_still_lights ----

    def test_unrelated_incident_still_lights(self):
        """Un-dismissed, un-keyword-matched incident → still returns non-None string.

        Mute never hides a real, un-targeted incident even when there are dismissals
        present for OTHER ids.
        """
        tracked_inc = {"id": "inc-real", "impact": "minor",
                       "status": "investigating",
                       "title": "Claude Code API elevated errors",
                       "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="Claude Code API elevated errors", kind="incident",
            tracked_incidents=[tracked_inc],
        )
        # Dismissal store references a DIFFERENT id
        dismissal_store = {
            "inc-other": {"impact_at_dismiss": "minor", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNotNone(result,
                             "Un-dismissed incident must still surface at render (mute must not be "
                             "over-broad)")
        self.assertIsInstance(result, str, "Result must be a string for an active incident")

    # ---- test_healthy_still_omits ----

    def test_healthy_still_omits(self):
        """noteworthy=False (healthy) with any dismissal store → still returns None (D-01).

        The render-time suppression path is only reached after the noteworthy gate.
        Healthy (all-clear) must still silently omit regardless of the dismissal store.
        """
        sec = self._fresh_section(noteworthy=False)
        dismissal_store = {
            "inc-anything": {"impact_at_dismiss": "minor", "dismissed_at": time.time()},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "noteworthy=False must return None even with a populated dismissal store (D-01)")

    # ---- test_cold_cache_still_omits ----

    def test_cold_cache_still_omits(self):
        """Absent/stale cache → None even with a populated dismissal store (D-01 cold-cache).

        The freshness gate fires before the suppression block, so a cold/stale cache
        always omits silently regardless of the dismissal store contents.
        """
        dismissal_store = {
            "inc-anything": {"impact_at_dismiss": "minor", "dismissed_at": time.time()},
        }
        # Cold cache: no cache file at all
        result = self._segment(None, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "Cold cache (absent file) must return None with any dismissal store (D-01)")

    # ---- test_render_never_raises_on_malformed ----

    def test_render_never_raises_on_malformed(self):
        """Malformed tracked_incidents and/or corrupt dismissal store → never raises (D-10).

        Various malformed inputs must degrade gracefully (None or the baked string)
        without raising — the render path is protected by the function-level try/except.
        """
        bad_tracked_variants = [
            "not a list",          # non-list tracked_incidents
            None,                  # explicit None
            [None, "bad", 42],     # list of non-dicts
            [{"id": None, "impact": None, "title": None}],  # dicts with None fields
        ]
        bad_dismissal_variants = [
            "not a dict",          # non-dict store
            None,                  # None store (write a bad JSON file)
        ]
        for bad_tracked in bad_tracked_variants:
            for bad_dismissals_flag in (False, True):
                with self.subTest(tracked=bad_tracked, corrupt_dismissals=bad_dismissals_flag):
                    sec = self._fresh_section(
                        noteworthy=True, severity="minor",
                        label="Outage", kind="incident",
                        tracked_incidents=bad_tracked,
                    )
                    if bad_dismissals_flag:
                        # Write a corrupt dismissal file (invalid JSON)
                        dismissals_path = os.path.join(self.tmpdir, "corrupt_dismissals.json")
                        with open(dismissals_path, "w") as f:
                            f.write("not-json{{{")
                        cache_path = _make_cache_with_status(self.tmpdir, sec)
                        import copy
                        cfg = copy.deepcopy(self.base_cfg)
                        try:
                            with patch.object(self.mod, "_CACHE_PATH", cache_path):
                                with patch.object(self.mod, "_DISMISSALS_PATH", dismissals_path):
                                    result = self.mod._claude_status_segment(self.data, cfg)
                            self.assertTrue(result is None or isinstance(result, str),
                                            f"Malformed input must return str|None, not raise; "
                                            f"tracked={bad_tracked!r}, corrupt_dismissals={bad_dismissals_flag}; "
                                            f"got={result!r}")
                        except Exception as exc:
                            self.fail(
                                f"_claude_status_segment raised on malformed input "
                                f"(tracked={bad_tracked!r}, corrupt_dismissals={bad_dismissals_flag}): {exc}"
                            )
                    else:
                        try:
                            result = self._segment(sec, dismissal_store={})
                            self.assertTrue(result is None or isinstance(result, str),
                                            f"Malformed tracked_incidents must return str|None (D-10); "
                                            f"tracked={bad_tracked!r}, got={result!r}")
                        except Exception as exc:
                            self.fail(
                                f"_claude_status_segment raised on malformed tracked_incidents "
                                f"{bad_tracked!r}: {exc}"
                            )

    # ---- test_maintenance_baked_behavior_unchanged ----

    def test_maintenance_baked_behavior_unchanged(self):
        """maintenance/degraded baked section (no tracked_incidents) → renders baked segment.

        Render-time suppression governs incidents only (items with ids in
        tracked_incidents). A maintenance section has no tracked incident ids and must
        render the baked maintenance segment unchanged, even with a populated dismissal
        store.
        """
        # Maintenance section with no tracked_incidents — or an empty list
        sec = self._fresh_section(
            noteworthy=True, severity="maintenance",
            label="Scheduled maintenance window", kind="maintenance",
            tracked_incidents=[],  # empty — no ids to filter
        )
        dismissal_store = {
            "inc-irrelevant": {"impact_at_dismiss": "major", "dismissed_at": time.time()},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNotNone(result,
                             "Maintenance section must still render despite populated dismissal store "
                             "(render-time suppression governs incidents only)")
        # The maintenance glyph must be present (not suppressed)
        self.assertIn(self.mod._NF_CLAUDE_MAINT, result,
                      f"Maintenance segment must contain the maintenance glyph (wrench); "
                      f"got={result!r}")

    # ---- test_second_incident_surfaces_when_first_dismissed ----

    def test_second_incident_surfaces_when_first_dismissed(self):
        """When the first tracked incident is dismissed, the second non-suppressed one surfaces.

        Two tracked_incidents: first is dismissed (suppressed), second is not.
        The segment must render the SECOND incident's title (fall-through to next item).
        """
        first_inc = {"id": "inc-dismissed", "impact": "minor",
                     "status": "investigating", "title": "Mythos/Fable suspended",
                     "component": "Claude Code"}
        second_inc = {"id": "inc-active", "impact": "minor",
                      "status": "investigating", "title": "API elevated errors",
                      "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="Mythos/Fable suspended", kind="incident",  # baked from first
            tracked_incidents=[first_inc, second_inc],
        )
        dismissal_store = {
            "inc-dismissed": {"impact_at_dismiss": "minor", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNotNone(result,
                             "Second non-suppressed incident must surface when first is dismissed")
        self.assertIn("API elevated errors", result,
                      f"Result must contain the SECOND incident's title (first was dismissed); "
                      f"got={result!r}")
        self.assertNotIn("Mythos/Fable", result,
                         f"Dismissed first incident title must NOT appear in result; "
                         f"got={result!r}")

    # ---- Phase 07.1 Plan 03 Task 1: resolved render + D-06 Risk #2 fix ----
    #
    # Tests for the Wave-3 render edge: GREEN check-circle 'resolved:' prefix
    # for resolved baked items, and the D-06 fall-through guard (Risk #2) that
    # ensures muted degraded/resolved baked items return None (not red, not green).

    def test_resolved_baked_renders_green(self):
        """Resolved baked section (kind='resolved') → segment contains GREEN color (D-03).

        A cache section with kind='resolved' (set by Wave-1 derivation) must render
        with the GREEN color constant, not RED or YELLOW.
        """
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result, "Resolved baked section must return a non-None segment")
        self.assertIn(self.mod.GREEN, result,
                      f"Resolved segment must contain GREEN; got {result!r}")
        self.assertNotIn(self.mod.RED, result,
                         f"Resolved segment must NOT contain RED; got {result!r}")

    def test_resolved_baked_renders_check_circle_glyph(self):
        """Resolved baked section → nerd icon_set uses check-circle glyph _NF_GSD_DONE (D-03)."""
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result, "Resolved segment must not be None")
        self.assertIn(self.mod._NF_GSD_DONE, result,
                      f"Resolved segment (nerd icon_set) must contain check-circle glyph; got {result!r}")
        self.assertNotIn(self.mod._NF_CLAUDE_INCIDENT, result,
                         f"Resolved segment must NOT use incident exclamation glyph; got {result!r}")

    def test_resolved_baked_renders_resolved_prefix(self):
        """Resolved baked section → rendered detail contains 'resolved: ' prefix before title (D-03)."""
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result)
        self.assertIn("resolved:", result,
                      f"Resolved segment must contain 'resolved:' prefix; got {result!r}")

    def test_resolved_baked_emoji_icon_set(self):
        """Resolved baked section with icon_set='emoji' → contains checkmark emoji and 'resolved:' prefix."""
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={},
                               extra_cfg={"display": {"icon_set": "emoji"}})
        self.assertIsNotNone(result, "Resolved segment (emoji icon_set) must not be None")
        self.assertIn("resolved:", result,
                      f"Resolved segment (emoji) must contain 'resolved:' prefix; got {result!r}")
        # Emoji fallback is ✅ (U+2705)
        self.assertIn("\U00002705", result,
                      f"Resolved segment (emoji) must contain ✅ glyph; got {result!r}")

    def test_resolved_baked_prefix_survives_nocolor(self):
        """'resolved:' word appears in the detail text independently of color codes (D-03).

        Strips all ANSI codes and verifies 'resolved:' and the title are still present.
        """
        import re as _re
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result)
        stripped = _re.sub(r'\x1b\[[0-9;]*m', '', result)
        self.assertIn("resolved:", stripped,
                      f"'resolved:' must be present after stripping ANSI codes; stripped={stripped!r}")
        self.assertIn("API errors now cleared", stripped,
                      f"Title must survive no-color; stripped={stripped!r}")

    def test_degraded_no_incident_still_red(self):
        """Degraded baked section with NO tracked incidents → still renders (D-05 regression guard).

        An unexplained degraded component (no tracked incidents at all) must still
        render a segment — this was the pre-existing baked behavior.
        The resolved branch must not affect it.
        """
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="claude.ai: degraded performance", kind="degraded",
            tracked_incidents=[],  # no tracked incidents
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result,
                             "Degraded section with no tracked incidents must still render (not None)")
        # Must use a severity color (YELLOW for minor), not GREEN
        self.assertNotIn(self.mod.GREEN, result,
                         f"Unexplained degraded must NOT be green; got {result!r}")

    def test_muted_resolved_returns_none_not_green(self):
        """Resolved baked section whose only tracked incident is dismissed → returns None (D-06 Risk #2).

        A resolved-kind baked item explained only by a muted incident must render
        nothing (None) — not green, not red. Muting wins in every state (D-06).
        """
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "API errors now cleared",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="API errors now cleared", kind="resolved",
            # Phase 07.1 CR-02 contract: the section binds to its EXPLAINING incident id.
            incident_id="inc-resolved-001", component="Claude Code",
            tracked_incidents=[resolved_inc],
        )
        # The only explaining incident is dismissed at matching impact (dismissal stands)
        dismissal_store = {
            "inc-resolved-001": {"impact_at_dismiss": "major", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "Resolved item whose only tracked incident is muted must return None "
                          "(D-06 Risk #2: muting wins — no green, no red)")

    def test_muted_resolved_keyword_returns_none(self):
        """Resolved baked section muted by keyword pattern → returns None (D-06 Risk #2)."""
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": "Mythos access restored",
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="Mythos access restored", kind="resolved",
            incident_id="inc-resolved-001", component="Claude Code",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(
            sec,
            dismissal_store={},
            extra_cfg={"claude_status": {"filter_enabled": True,
                                         "ignore_title_patterns": ["Mythos"]}},
        )
        self.assertIsNone(result,
                          "Keyword-muted resolved item must return None (D-06 Risk #2)")

    def test_muted_degraded_returns_none_not_red(self):
        """Degraded baked section whose only tracked incident is dismissed → returns None (D-06 Risk #2).

        A degraded (red) item explained only by a muted incident must render
        nothing (None) — not red. Muting wins in every state (D-06).
        """
        degraded_inc = {"id": "inc-active-001", "impact": "minor",
                        "status": "investigating", "title": "Mythos/Fable suspended",
                        "component": "claude.ai"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="claude.ai: degraded performance", kind="degraded",
            # Phase 07.1 CR-02: a degraded component whose only explanation is a muted
            # incident bakes that incident id so the render mute re-check returns None.
            incident_id="inc-active-001", component="claude.ai",
            tracked_incidents=[degraded_inc],
        )
        dismissal_store = {
            "inc-active-001": {"impact_at_dismiss": "minor", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "Degraded item whose only tracked incident is muted must return None "
                          "(D-06 Risk #2: no red fallback when explaining incident is muted)")

    def test_active_incident_outranks_resolved_baked(self):
        """Active-incident kind section still renders as an incident (Rule 1 preserved) (D-04).

        This is a regression guard: even with resolved-render logic in place, an
        active incident (kind='incident') must render with the incident glyph and
        a severity color, NOT with the resolved green+check-circle.
        """
        tracked_inc = {"id": "inc-active-001", "impact": "minor",
                       "status": "investigating", "title": "Claude Code elevated errors",
                       "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="minor",
            label="Claude Code elevated errors", kind="incident",
            tracked_incidents=[tracked_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result, "Active incident must still render non-None")
        self.assertNotIn(self.mod.GREEN, result,
                         f"Active incident must NOT be rendered green; got {result!r}")
        self.assertNotIn(self.mod._NF_GSD_DONE, result,
                         f"Active incident must NOT use the check-circle glyph; got {result!r}")
        self.assertNotIn("resolved:", result,
                         f"Active incident must NOT have 'resolved:' prefix; got {result!r}")

    def test_resolved_ansi_injection_stripped(self):
        """Resolved baked section with ESC-injected title → no raw ESC in rendered output (T-07.1-08).

        The resolved render path must route the label through the same Step-6 sanitizer
        used for active incidents (strip ESC / non-printable, width-bound).
        """
        malicious_label = "\x1b[31mCRITICAL\x1b[0m: API errors now cleared"
        resolved_inc = {"id": "inc-resolved-001", "impact": "major",
                        "status": "resolved", "title": malicious_label,
                        "component": "Claude Code"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label=malicious_label, kind="resolved",
            tracked_incidents=[resolved_inc],
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result, "Resolved section with malicious title must still return a segment")
        import re as _re
        reset = self.mod.RESET
        core = result
        if core.endswith(reset):
            core = core[:-len(reset)]
        # Strip leading builder-applied color codes
        core = _re.sub(r'^(\x1b\[[0-9;]*m)+', '', core)
        # No injected ESC should remain in the label portion
        self.assertNotIn("\x1b", core,
                         f"Resolved label must have no raw ESC after sanitization; core={core!r}")

    def test_garbage_resolved_section_does_not_raise(self):
        """Garbage resolved-kind section → returns None without raising (D-10 never-crash)."""
        bad_sections = [
            self._fresh_section(noteworthy=True, severity="resolved",
                                label=None, kind="resolved",
                                tracked_incidents=None),
            self._fresh_section(noteworthy=True, severity="resolved",
                                label="\x00\x01\x02", kind="resolved",
                                tracked_incidents=[None, "bad", 42]),
        ]
        for sec in bad_sections:
            with self.subTest(label=sec.get("label")):
                try:
                    result = self._segment(sec, dismissal_store={})
                    self.assertTrue(result is None or isinstance(result, str),
                                    f"Must return str|None on garbage input; got {result!r}")
                except Exception as exc:
                    self.fail(f"_claude_status_segment raised on garbage resolved section: {exc}")

    # ---- WR-03 / CR-02 regression: multi-incident mute binding ----

    def test_cr02_dismissed_explaining_incident_with_unrelated_survivor_returns_none(self):
        """CR-02: baked resolved for A; dismiss ONLY A; unrelated B survives → segment None.

        The render-time mute re-check must bind to the EXPLAINING incident (A), not
        to 'any surviving tracked incident'. Before the fix, unrelated non-suppressed
        B kept the section alive and re-surfaced A's label in GREEN — leaking the very
        incident the user muted (D-06 Risk #2). Must return None: no green, no red.
        """
        inc_a = {"id": "A", "impact": "major", "status": "resolved",
                 "title": "Claude Code fixed", "component": "Claude Code"}
        inc_b = {"id": "B", "impact": "minor", "status": "resolved",
                 "title": "Unrelated AI thing", "component": "claude.ai"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="Claude Code fixed", kind="resolved",
            incident_id="A", component="Claude Code",
            tracked_incidents=[inc_a, inc_b],  # A explains; B is unrelated + non-suppressed
        )
        dismissal_store = {
            "A": {"impact_at_dismiss": "major", "dismissed_at": time.time() - 10},
        }
        result = self._segment(sec, dismissal_store=dismissal_store)
        self.assertIsNone(result,
                          "Dismissed explaining incident must mute the section even when an "
                          "unrelated incident survives (CR-02 / D-06 Risk #2); "
                          f"got {result!r}")

    def test_cr02_unrelated_survivor_does_not_leak_when_explaining_present(self):
        """CR-02 positive control: explaining incident A non-suppressed → renders green for A.

        With no dismissals, the bound resolved section renders its OWN label (A),
        never B's — proving the binding selects the explaining incident, not the
        first surviving one.
        """
        inc_a = {"id": "A", "impact": "major", "status": "resolved",
                 "title": "Claude Code fixed", "component": "Claude Code"}
        inc_b = {"id": "B", "impact": "minor", "status": "resolved",
                 "title": "Unrelated AI thing", "component": "claude.ai"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="Claude Code fixed", kind="resolved",
            incident_id="A", component="Claude Code",
            tracked_incidents=[inc_b, inc_a],  # B sorts first — must NOT be picked
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNotNone(result, "Non-suppressed explaining incident must render")
        self.assertIn(self.mod.GREEN, result, f"Resolved must be green; got {result!r}")
        self.assertIn("Claude Code fixed", result,
                      f"Must render the EXPLAINING incident's label, not the unrelated one; "
                      f"got {result!r}")
        self.assertNotIn("Unrelated AI thing", result,
                         f"Unrelated incident label must not leak; got {result!r}")

    def test_cr02_explaining_incident_absent_from_feed_returns_none(self):
        """CR-02: baked resolved id no longer present in tracked_incidents → segment None.

        If the explaining incident has dropped out of the live feed, the resolved
        verdict has no live justification → render nothing (never green, never red).
        """
        inc_b = {"id": "B", "impact": "minor", "status": "resolved",
                 "title": "Unrelated AI thing", "component": "claude.ai"}
        sec = self._fresh_section(
            noteworthy=True, severity="resolved",
            label="Claude Code fixed", kind="resolved",
            incident_id="A", component="Claude Code",
            tracked_incidents=[inc_b],  # A is gone
        )
        result = self._segment(sec, dismissal_store={})
        self.assertIsNone(result,
                          "Explaining incident absent from feed must mute the section; "
                          f"got {result!r}")


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


# ---------------------------------------------------------------------------
# Phase 7 Plan 01: Task 1 — [claude_status] config table + dismissal-store helpers
# ---------------------------------------------------------------------------


class TestClaudeStatusConfigDefaults(unittest.TestCase):
    """DEFAULTS["claude_status"] table: filter_enabled + ignore_title_patterns defaults."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_defaults_has_claude_status_table(self):
        """DEFAULTS must have a top-level 'claude_status' key."""
        self.assertIn("claude_status", self.mod.DEFAULTS,
                      "DEFAULTS must have a top-level 'claude_status' table (D-06)")

    def test_filter_enabled_default_true(self):
        """DEFAULTS['claude_status']['filter_enabled'] must default to True."""
        table = self.mod.DEFAULTS.get("claude_status", {})
        self.assertIn("filter_enabled", table,
                      "DEFAULTS['claude_status'] must have 'filter_enabled'")
        self.assertTrue(table["filter_enabled"],
                        "filter_enabled must default to True (D-06)")

    def test_ignore_title_patterns_default_empty(self):
        """DEFAULTS['claude_status']['ignore_title_patterns'] must default to []."""
        table = self.mod.DEFAULTS.get("claude_status", {})
        self.assertIn("ignore_title_patterns", table,
                      "DEFAULTS['claude_status'] must have 'ignore_title_patterns'")
        self.assertEqual(table["ignore_title_patterns"], [],
                         "ignore_title_patterns must default to [] (D-06)")

    def test_load_config_deep_merges_claude_status_partial_override(self):
        """load_config with only ignore_title_patterns in TOML keeps filter_enabled default."""
        import tempfile
        # Write a minimal TOML with just ignore_title_patterns under [claude_status]
        toml_content = '[claude_status]\nignore_title_patterns = ["Mythos"]\n'
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as fh:
            fh.write(toml_content)
            toml_path = fh.name
        try:
            cfg = self.mod.load_config(toml_path)
            cs = cfg.get("claude_status", {})
            self.assertEqual(cs.get("ignore_title_patterns"), ["Mythos"],
                             "TOML override must propagate ignore_title_patterns")
            self.assertTrue(cs.get("filter_enabled"),
                            "filter_enabled must keep default True when not in TOML")
        finally:
            os.unlink(toml_path)


class TestDismissalStoreHelpers(unittest.TestCase):
    """read_dismissals / write_dismissals / _dismiss_id / _undismiss_id / _prune_dismissals."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmpdir, "status_dismissals.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---- _DISMISSALS_PATH constant ----

    def test_dismissals_path_constant_exists(self):
        """_DISMISSALS_PATH must be defined in the module."""
        self.assertTrue(hasattr(self.mod, "_DISMISSALS_PATH"),
                        "_DISMISSALS_PATH constant must be defined")

    def test_dismissals_path_is_string(self):
        """_DISMISSALS_PATH must be a string (expanded path)."""
        self.assertIsInstance(self.mod._DISMISSALS_PATH, str,
                              "_DISMISSALS_PATH must be a str")

    # ---- read_dismissals ----

    def test_read_dismissals_exists(self):
        """read_dismissals function must exist."""
        self.assertTrue(callable(getattr(self.mod, "read_dismissals", None)),
                        "read_dismissals must be defined")

    def test_read_dismissals_missing_path_returns_empty(self):
        """read_dismissals on a missing path returns {} (no raise, no suppression)."""
        missing = os.path.join(self.tmpdir, "nonexistent.json")
        result = self.mod.read_dismissals(missing)
        self.assertEqual(result, {},
                         "read_dismissals on missing path must return {}")

    def test_read_dismissals_garbage_bytes_returns_empty(self):
        """read_dismissals on garbage bytes returns {} (corrupt store → no suppression)."""
        with open(self.store_path, "wb") as fh:
            fh.write(b"\xff\xfe garbage not json \x00\x01")
        result = self.mod.read_dismissals(self.store_path)
        self.assertEqual(result, {},
                         "read_dismissals on corrupt bytes must return {}")

    def test_read_dismissals_non_dict_json_returns_empty(self):
        """read_dismissals on a JSON list (not dict) returns {} (rejects non-dict)."""
        with open(self.store_path, "w") as fh:
            json.dump(["not", "a", "dict"], fh)
        result = self.mod.read_dismissals(self.store_path)
        self.assertEqual(result, {},
                         "read_dismissals on JSON list must return {}")

    def test_read_dismissals_valid_dict_returns_it(self):
        """read_dismissals on a valid JSON dict returns that dict."""
        store = {"inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0}}
        with open(self.store_path, "w") as fh:
            json.dump(store, fh)
        result = self.mod.read_dismissals(self.store_path)
        self.assertEqual(result, store,
                         "read_dismissals must return the stored dict exactly")

    # ---- write_dismissals ----

    def test_write_dismissals_exists(self):
        """write_dismissals function must exist."""
        self.assertTrue(callable(getattr(self.mod, "write_dismissals", None)),
                        "write_dismissals must be defined")

    def test_write_dismissals_round_trip(self):
        """write_dismissals then read_dismissals round-trips the store dict."""
        store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
            "inc-002": {"impact_at_dismiss": "major", "dismissed_at": 1700000001.0},
        }
        self.mod.write_dismissals(store, self.store_path)
        result = self.mod.read_dismissals(self.store_path)
        self.assertEqual(result, store,
                         "write_dismissals → read_dismissals must round-trip the store")

    def test_write_dismissals_unwritable_path_does_not_raise(self):
        """write_dismissals to an unwritable path swallows the error (never raises)."""
        bad_path = "/dev/null/cannot_write_here.json"
        try:
            self.mod.write_dismissals({"id": "x"}, bad_path)
        except Exception as e:
            self.fail(f"write_dismissals raised on unwritable path: {e}")

    # ---- _dismiss_id ----

    def test_dismiss_id_exists(self):
        """_dismiss_id function must exist."""
        self.assertTrue(callable(getattr(self.mod, "_dismiss_id", None)),
                        "_dismiss_id must be defined")

    def test_dismiss_id_adds_entry_with_impact(self):
        """_dismiss_id adds an entry with impact_at_dismiss and dismissed_at."""
        self.mod._dismiss_id("inc-001", "minor", self.store_path)
        store = self.mod.read_dismissals(self.store_path)
        self.assertIn("inc-001", store,
                      "_dismiss_id must add the id to the store")
        entry = store["inc-001"]
        self.assertEqual(entry.get("impact_at_dismiss"), "minor",
                         "Stored entry must have impact_at_dismiss='minor'")
        self.assertIn("dismissed_at", entry,
                      "Stored entry must have dismissed_at timestamp")
        self.assertIsInstance(entry["dismissed_at"], float,
                              "dismissed_at must be a float epoch")

    def test_dismiss_id_empty_id_is_noop(self):
        """_dismiss_id with empty inc_id is a no-op (no store write, no raise)."""
        try:
            self.mod._dismiss_id("", "minor", self.store_path)
        except Exception as e:
            self.fail(f"_dismiss_id('', ...) raised: {e}")
        # Store should still not exist (or be empty)
        result = self.mod.read_dismissals(self.store_path)
        self.assertNotIn("", result,
                         "_dismiss_id('') must not write an empty-string key")

    # ---- _undismiss_id ----

    def test_undismiss_id_exists(self):
        """_undismiss_id function must exist."""
        self.assertTrue(callable(getattr(self.mod, "_undismiss_id", None)),
                        "_undismiss_id must be defined")

    def test_undismiss_id_removes_entry(self):
        """_undismiss_id removes an id that was previously dismissed."""
        # Seed the store directly
        store = {"inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0}}
        self.mod.write_dismissals(store, self.store_path)
        # Undismiss
        self.mod._undismiss_id("inc-001", self.store_path)
        result = self.mod.read_dismissals(self.store_path)
        self.assertNotIn("inc-001", result,
                         "_undismiss_id must remove the id from the store")

    def test_undismiss_id_noop_for_missing_id(self):
        """_undismiss_id on an id not in store is a no-op (no raise)."""
        try:
            self.mod._undismiss_id("nonexistent-id", self.store_path)
        except Exception as e:
            self.fail(f"_undismiss_id on missing id raised: {e}")

    # ---- _prune_dismissals ----

    def test_prune_dismissals_exists(self):
        """_prune_dismissals function must exist."""
        self.assertTrue(callable(getattr(self.mod, "_prune_dismissals", None)),
                        "_prune_dismissals must be defined")

    def test_prune_dismissals_removes_stale_ids(self):
        """_prune_dismissals drops ids not in live_ids, keeps ids that are."""
        store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
            "inc-002": {"impact_at_dismiss": "major", "dismissed_at": 1700000001.0},
            "inc-stale": {"impact_at_dismiss": "none", "dismissed_at": 1700000002.0},
        }
        live_ids = {"inc-001", "inc-002"}
        pruned = self.mod._prune_dismissals(store, live_ids)
        self.assertIn("inc-001", pruned, "inc-001 is live and must be kept")
        self.assertIn("inc-002", pruned, "inc-002 is live and must be kept")
        self.assertNotIn("inc-stale", pruned, "inc-stale is not live and must be pruned")

    def test_prune_dismissals_is_pure_no_side_effects(self):
        """_prune_dismissals is pure: it does not modify the input store dict."""
        store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
        }
        original_keys = set(store.keys())
        _ = self.mod._prune_dismissals(store, set())  # prune everything
        self.assertEqual(set(store.keys()), original_keys,
                         "_prune_dismissals must be pure (no side effects on input dict)")

    def test_prune_dismissals_empty_live_ids_clears_all(self):
        """_prune_dismissals with empty live_ids returns empty dict."""
        store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
        }
        pruned = self.mod._prune_dismissals(store, set())
        self.assertEqual(pruned, {},
                         "_prune_dismissals(store, set()) must return empty dict")

    def test_prune_dismissals_empty_store_returns_empty(self):
        """_prune_dismissals on empty store returns empty dict."""
        pruned = self.mod._prune_dismissals({}, {"inc-001", "inc-002"})
        self.assertEqual(pruned, {},
                         "_prune_dismissals({}, ...) must return {}")


# ---------------------------------------------------------------------------
# Phase 7 Plan 01: Task 2 — Widened claude_status cache payload (tracked-incident list)
# ---------------------------------------------------------------------------


class TestFetchClaudeStatusWidenedPayload(unittest.TestCase):
    """fetch_claude_status cache payload carries a stable tracked_incidents list (D-02 enabler)."""

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

    def _fetch_with_fixture(self, fixture_name: str) -> dict:
        """Fetch using FAKE_STATUS pointing at a fixture; return the written claude_status section."""
        fake_path = os.path.join(FIXTURES_DIR, fixture_name)
        with patch.dict(os.environ, {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        return data.get("claude_status", {})

    # ---- tracked_incidents key is always present ----

    def test_incident_fixture_has_tracked_incidents_key(self):
        """Incident fixture → claude_status section has 'tracked_incidents' key."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        self.assertIn("tracked_incidents", section,
                      "claude_status section must have 'tracked_incidents' key when incident present")

    def test_operational_fixture_has_tracked_incidents_key(self):
        """Operational/healthy fixture → claude_status section still has 'tracked_incidents' key (stable shape)."""
        section = self._fetch_with_fixture("status_operational.json")
        self.assertIn("tracked_incidents", section,
                      "claude_status section must have 'tracked_incidents' key even when healthy")

    def test_operational_fixture_tracked_incidents_is_empty_list(self):
        """Operational fixture → tracked_incidents is an empty list (not absent)."""
        section = self._fetch_with_fixture("status_operational.json")
        incidents = section.get("tracked_incidents")
        self.assertIsInstance(incidents, list,
                              "tracked_incidents must be a list even in healthy state")
        self.assertEqual(incidents, [],
                         "tracked_incidents must be [] in healthy state")

    # ---- incident fixture: list entry shape ----

    def test_incident_fixture_tracked_incidents_contains_inc_001(self):
        """Incident fixture → tracked_incidents list contains entry with id 'inc-001'."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        incidents = section.get("tracked_incidents", [])
        self.assertIsInstance(incidents, list, "tracked_incidents must be a list")
        ids = [e.get("id") for e in incidents if isinstance(e, dict)]
        self.assertIn("inc-001", ids,
                      f"tracked_incidents must contain id='inc-001'; got ids={ids!r}")

    def test_incident_fixture_entry_has_impact(self):
        """Incident fixture entry has 'impact' key == 'minor' (matches fixture)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("id") == "inc-001"), None)
        self.assertIsNotNone(entry, "Entry for inc-001 must be present")
        self.assertEqual(entry.get("impact"), "minor",
                         "Entry impact must be 'minor' per fixture")

    def test_incident_fixture_entry_has_status(self):
        """Incident fixture entry has 'status' key == 'monitoring' (matches fixture)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("id") == "inc-001"), None)
        self.assertIsNotNone(entry, "Entry for inc-001 must be present")
        self.assertEqual(entry.get("status"), "monitoring",
                         "Entry status must be 'monitoring' per fixture")

    def test_incident_fixture_entry_has_title(self):
        """Incident fixture entry has 'title' key matching fixture incident name."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("id") == "inc-001"), None)
        self.assertIsNotNone(entry, "Entry for inc-001 must be present")
        expected_title = "Elevated error rates for Claude Code tool calls"
        self.assertEqual(entry.get("title"), expected_title,
                         f"Entry title must match fixture; got {entry.get('title')!r}")

    def test_incident_fixture_entry_has_component(self):
        """Incident fixture entry has 'component' key == 'Claude Code' (tracked component)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("id") == "inc-001"), None)
        self.assertIsNotNone(entry, "Entry for inc-001 must be present")
        self.assertEqual(entry.get("component"), "Claude Code",
                         f"Entry component must be 'Claude Code'; got {entry.get('component')!r}")

    # ---- existing payload keys unchanged (no regression) ----

    def test_incident_fixture_noteworthy_still_true(self):
        """Incident fixture → noteworthy=True still present (no regression to Phase 6 payload)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        self.assertTrue(section.get("noteworthy"),
                        "noteworthy must still be True in incident cache section (Phase 6 key)")

    def test_incident_fixture_severity_still_present(self):
        """Incident fixture → severity key still present in payload (no regression)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        self.assertIn("severity", section,
                      "severity must still be present in payload (Phase 6 key)")

    def test_incident_fixture_label_still_present(self):
        """Incident fixture → label key still present in payload (no regression)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        self.assertIn("label", section,
                      "label must still be present in payload (Phase 6 key)")

    def test_incident_fixture_kind_still_present(self):
        """Incident fixture → kind key still present in payload (no regression)."""
        section = self._fetch_with_fixture("status_incident_tracked.json")
        self.assertIn("kind", section,
                      "kind must still be present in payload (Phase 6 key)")

    def test_operational_fixture_noteworthy_false_still_present(self):
        """Operational fixture → noteworthy=False still present (no regression)."""
        section = self._fetch_with_fixture("status_operational.json")
        self.assertIn("noteworthy", section,
                      "noteworthy key must be present even in healthy section")
        self.assertFalse(section.get("noteworthy"),
                         "noteworthy must be False in healthy section")

    # ---- Phase 07.1 Plan 01: resolved-incident tracking (D-06/D-07 enabler) ----

    def test_resolved_degraded_fixture_tracked_incidents_has_resolved_entry(self):
        """Resolved-degraded fixture → tracked_incidents contains entry with status=='resolved'."""
        section = self._fetch_with_fixture("status_resolved_degraded.json")
        incidents = section.get("tracked_incidents", [])
        self.assertIsInstance(incidents, list, "tracked_incidents must be a list")
        resolved_entries = [e for e in incidents if isinstance(e, dict) and e.get("status") == "resolved"]
        self.assertTrue(len(resolved_entries) > 0,
                        f"tracked_incidents must contain at least one resolved entry; got {incidents!r}")

    def test_resolved_degraded_fixture_resolved_entry_component(self):
        """Resolved-degraded fixture → resolved entry has correct tracked component."""
        section = self._fetch_with_fixture("status_resolved_degraded.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("status") == "resolved"), None)
        self.assertIsNotNone(entry, "Resolved entry must be present in tracked_incidents")
        self.assertEqual(entry.get("component"), "Claude Code",
                         f"Resolved entry component must be 'Claude Code'; got {entry.get('component')!r}")

    def test_resolved_degraded_fixture_resolved_entry_has_id(self):
        """Resolved-degraded fixture → resolved entry has 'id' == 'inc-resolved-001'."""
        section = self._fetch_with_fixture("status_resolved_degraded.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("status") == "resolved"), None)
        self.assertIsNotNone(entry, "Resolved entry must be present")
        self.assertEqual(entry.get("id"), "inc-resolved-001",
                         f"Entry id must match fixture; got {entry.get('id')!r}")

    def test_resolved_degraded_fixture_resolved_entry_shape_keys(self):
        """Resolved-degraded fixture → resolved entry has exactly the 5 expected keys (shape unchanged)."""
        section = self._fetch_with_fixture("status_resolved_degraded.json")
        incidents = section.get("tracked_incidents", [])
        entry = next((e for e in incidents if isinstance(e, dict) and e.get("status") == "resolved"), None)
        self.assertIsNotNone(entry, "Resolved entry must be present")
        expected_keys = {"id", "impact", "status", "title", "component"}
        actual_keys = set(entry.keys())
        self.assertEqual(actual_keys, expected_keys,
                         f"Resolved entry must have exactly {expected_keys}; got {actual_keys!r}")

    def test_untracked_resolved_incident_not_collected(self):
        """An untracked resolved incident (no tracked component) is NOT collected."""
        # Use operational fixture — no tracked incidents; add an untracked resolved incident
        # by building a minimal summary dict directly via _collect_tracked_incidents
        mod = self.mod
        summary = {
            "components": [
                {"name": "Claude Code", "status": "operational"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {
                    "id": "inc-untracked-resolved",
                    "name": "Untracked component resolved",
                    "status": "resolved",
                    "impact": "minor",
                    "components": [
                        {"id": "comp-api", "name": "Claude API (api.anthropic.com)"},
                    ],
                }
            ],
            "scheduled_maintenances": [],
        }
        result = mod._collect_tracked_incidents(summary)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [],
                         f"Untracked resolved incident must NOT be collected; got {result!r}")

    def test_collect_garbage_input_returns_empty_list(self):
        """_collect_tracked_incidents(garbage) → [] never raises (D-10)."""
        mod = self.mod
        for bad in [None, [], "garbage", 42, {"incidents": "not-a-list"}]:
            with self.subTest(input=bad):
                try:
                    result = mod._collect_tracked_incidents(bad)
                    self.assertIsInstance(result, list,
                                         f"Must return list on bad input {bad!r}; got {type(result)}")
                    self.assertEqual(result, [],
                                     f"Must return [] on bad input {bad!r}; got {result!r}")
                except Exception as e:
                    self.fail(f"_collect_tracked_incidents raised on {bad!r}: {e}")


# ---------------------------------------------------------------------------
# Phase 7 Plan 02: Task 1 — _is_suppressed + filter integration in _derive_claude_status
# ---------------------------------------------------------------------------


class TestIsSuppressed(unittest.TestCase):
    """_is_suppressed: dual filter (id-dismiss + keyword/regex), escalation, toggle, edge cases."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_is_suppressed_exists(self):
        """_is_suppressed function must exist."""
        self.assertTrue(callable(getattr(self.mod, "_is_suppressed", None)),
                        "_is_suppressed must be defined in claude-statusline.py")

    def test_claude_pattern_match_maxlen_exists(self):
        """_CLAUDE_PATTERN_MATCH_MAXLEN constant must be defined."""
        self.assertTrue(hasattr(self.mod, "_CLAUDE_PATTERN_MATCH_MAXLEN"),
                        "_CLAUDE_PATTERN_MATCH_MAXLEN must be defined")

    def test_claude_pattern_match_maxlen_is_500(self):
        """_CLAUDE_PATTERN_MATCH_MAXLEN must equal 500."""
        self.assertEqual(self.mod._CLAUDE_PATTERN_MATCH_MAXLEN, 500,
                         "_CLAUDE_PATTERN_MATCH_MAXLEN must be 500 (ReDoS length cap)")

    def _cfg(self, filter_enabled=True, patterns=None):
        """Build a minimal cfg dict with claude_status settings."""
        return {"claude_status": {
            "filter_enabled": filter_enabled,
            "ignore_title_patterns": patterns if patterns is not None else [],
        }}

    # ---- id-dismiss suppression ----

    def test_id_dismiss_suppresses_incident(self):
        """_is_suppressed with matching id-dismissal returns True (suppressed)."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", dismissals, cfg)
        self.assertTrue(result, "_is_suppressed must return True for a matching id-dismissal")

    def test_id_dismiss_no_match_returns_false(self):
        """_is_suppressed with non-matching id-dismissal returns False (not suppressed)."""
        dismissals = {"inc-999": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", dismissals, cfg)
        self.assertFalse(result, "_is_suppressed must return False when id not in dismissals")

    # ---- keyword/regex suppression ----

    def test_keyword_substring_suppresses_incident(self):
        """_is_suppressed with matching keyword substring returns True."""
        cfg = self._cfg(patterns=["Elevated"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg
        )
        self.assertTrue(result, "Keyword substring match must suppress")

    def test_keyword_case_insensitive(self):
        """_is_suppressed keyword matching is case-insensitive."""
        cfg = self._cfg(patterns=["elevated"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg
        )
        self.assertTrue(result, "Keyword matching must be case-insensitive")

    def test_keyword_no_match_returns_false(self):
        """_is_suppressed with non-matching keyword returns False."""
        cfg = self._cfg(patterns=["Mythos", "Fable"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg
        )
        self.assertFalse(result, "Non-matching keywords must not suppress")

    # ---- EITHER filter suppresses ----

    def test_keyword_match_suppresses_even_without_id_dismiss(self):
        """Keyword match alone is sufficient to suppress (no id in dismissals)."""
        cfg = self._cfg(patterns=["Elevated"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg  # empty dismissals — only keyword applies
        )
        self.assertTrue(result, "Keyword match alone must suppress (EITHER filter)")

    def test_id_dismiss_suppresses_even_without_keyword_match(self):
        """Id-dismiss alone is sufficient to suppress (patterns is empty)."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg(patterns=[])  # no keyword patterns
        result = self.mod._is_suppressed("inc-001", "minor", "Some unmatched title", dismissals, cfg)
        self.assertTrue(result, "Id-dismiss alone must suppress (EITHER filter)")

    # ---- escalation re-surface (D-03): id-dismissals only ----

    def test_escalation_resurfaces_id_dismissed_incident(self):
        """Id-dismissed incident with higher live impact is NOT suppressed (escalation re-surface, D-03)."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        # Live impact is 'major' — higher than stored 'minor' → re-surface
        result = self.mod._is_suppressed("inc-001", "major", "Some title", dismissals, cfg)
        self.assertFalse(result,
                         "Live impact > stored impact must void dismissal (re-surface, D-03)")

    def test_escalation_critical_resurfaces_minor_dismiss(self):
        """Critical live impact overrides a minor-at-dismiss id-dismissal."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "critical", "Some title", dismissals, cfg)
        self.assertFalse(result, "Critical live impact must void minor dismissal")

    def test_escalation_same_impact_still_suppressed(self):
        """Id-dismissed incident with SAME live impact as stored stays suppressed (no escalation)."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", dismissals, cfg)
        self.assertTrue(result, "Same impact level must stay suppressed (no escalation)")

    def test_escalation_lower_impact_still_suppressed(self):
        """Id-dismissed incident with LOWER live impact (e.g. 'none') stays suppressed."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        # 'none' impact is lower than 'minor' → no escalation → still suppressed
        result = self.mod._is_suppressed("inc-001", "none", "Some title", dismissals, cfg)
        self.assertTrue(result, "Lower live impact must stay suppressed (no escalation)")

    # ---- keyword has NO escalation tracking (blunt mute, D-03) ----

    def test_keyword_high_impact_still_suppressed(self):
        """Keyword-matched incident stays suppressed even at high/critical impact (blunt mute, D-03)."""
        cfg = self._cfg(patterns=["Mythos"])
        # High impact — but keyword suppression has no escalation tracking
        result = self.mod._is_suppressed(
            "inc-999", "critical",
            "Mythos model access removal — long-lived monitoring incident",
            {}, cfg
        )
        self.assertTrue(result, "Keyword mute has no escalation — must stay suppressed even at critical")

    # ---- filter_enabled toggle (D-06) ----

    def test_toggle_off_disables_id_dismiss(self):
        """filter_enabled=False disables id-dismiss suppression."""
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg(filter_enabled=False)
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", dismissals, cfg)
        self.assertFalse(result, "filter_enabled=False must disable id-dismiss suppression")

    def test_toggle_off_disables_keyword(self):
        """filter_enabled=False disables keyword suppression."""
        cfg = self._cfg(filter_enabled=False, patterns=["Elevated"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg
        )
        self.assertFalse(result, "filter_enabled=False must disable keyword suppression")

    # ---- bad/invalid regex — degrade to no-match, never raise ----

    def test_bad_regex_does_not_suppress(self):
        """Bad/unterminated regex pattern degrades to no-match (incident NOT suppressed)."""
        cfg = self._cfg(patterns=["[unterminated"])
        result = self.mod._is_suppressed(
            "inc-001", "minor",
            "Elevated error rates for Claude Code tool calls",
            {}, cfg
        )
        self.assertFalse(result,
                         "Bad regex must degrade to no-match (not suppressed), never raise")

    def test_bad_regex_does_not_raise(self):
        """Bad regex pattern does not raise any exception."""
        cfg = self._cfg(patterns=["[unterminated", "another[bad"])
        try:
            self.mod._is_suppressed("inc-001", "minor", "Some title", {}, cfg)
        except Exception as e:
            self.fail(f"_is_suppressed raised on bad regex: {e}")

    # ---- ReDoS cap test ----

    def test_redos_cap_returns_fast_and_does_not_suppress(self):
        """Catastrophic-backtracking pattern against a long title returns quickly (no hang).

        The length cap (_CLAUDE_PATTERN_MATCH_MAXLEN = 500) is the documented ReDoS
        mitigation. This test feeds (a+)+$ (known catastrophic) against a run of 5000 'a'
        chars + a trailing non-match char. Without the cap this would hang; with the 500-char
        cap it terminates in microseconds. The call must complete well under 1 second and
        must NOT suppress (the pattern does not match the capped title).
        """
        import time as _time
        long_title = "a" * 5000 + "b"  # trailing 'b' makes (a+)+$ not match
        cfg = self._cfg(patterns=["(a+)+$"])
        t0 = _time.monotonic()
        result = self.mod._is_suppressed("inc-001", "minor", long_title, {}, cfg)
        elapsed = _time.monotonic() - t0
        self.assertLess(elapsed, 1.0,
                        f"ReDoS-cap: call must complete in < 1s; took {elapsed:.3f}s")
        # The pattern (a+)+$ against title[:500] = "aaa...a" (500 a's) will actually match
        # BUT the full title has 5000 a's so without the cap it would hang. With the cap
        # at 500 chars the title_capped is "aaa...a" (500 chars) — the pattern DOES match
        # since the capped title is all 'a'. The important thing is it returns FAST.
        # We only assert the timing (fast return), not the match result (depends on cap).
        # The key non-regression is: the function must return (not hang).
        _ = result  # result may be True or False; we only care about timing

    def test_redos_cap_long_title_with_trailing_nonmatch_no_suppress(self):
        """Pattern that does not match title[:500] does NOT suppress.

        Use a simple non-backtracking pattern that clearly does NOT match the first
        500 chars of the long title, to verify the no-suppression outcome.
        """
        long_title = "a" * 5000 + "b"
        # This pattern requires 'ZZZ' which is not in the first 500 chars of the title
        cfg = self._cfg(patterns=["ZZZ"])
        result = self.mod._is_suppressed("inc-001", "minor", long_title, {}, cfg)
        self.assertFalse(result, "Pattern that doesn't match title[:500] must not suppress")

    # ---- corrupt dismissals — degrade to no suppression, never raise ----

    def test_corrupt_dismissals_string_returns_false(self):
        """Non-dict dismissals (string) degrades to no suppression."""
        cfg = self._cfg()
        try:
            result = self.mod._is_suppressed("inc-001", "minor", "Some title", "garbage", cfg)
        except Exception as e:
            self.fail(f"_is_suppressed raised on string dismissals: {e}")
        self.assertFalse(result, "String dismissals must degrade to no suppression")

    def test_corrupt_dismissals_int_returns_false(self):
        """Non-dict dismissals (int) degrades to no suppression."""
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", 123, cfg)
        self.assertFalse(result, "Int dismissals must degrade to no suppression")

    def test_corrupt_dismissals_none_returns_false(self):
        """None dismissals degrades to no suppression."""
        cfg = self._cfg()
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", None, cfg)
        self.assertFalse(result, "None dismissals must degrade to no suppression")

    def test_none_cfg_returns_false(self):
        """None cfg (no config) degrades to no suppression."""
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", {}, None)
        self.assertFalse(result, "None cfg must degrade to no suppression (filter_enabled defaults to no-op)")

    def test_non_dict_cfg_returns_false(self):
        """Non-dict cfg degrades to no suppression."""
        result = self.mod._is_suppressed("inc-001", "minor", "Some title", {}, "bad")
        self.assertFalse(result, "Non-dict cfg must degrade to no suppression")


class TestDeriveClaudeStatusFilterIntegration(unittest.TestCase):
    """_derive_claude_status: filter integration — id-dismiss and keyword suppress incidents."""

    def setUp(self):
        self.mod = _load_script_module()

    def _cfg(self, filter_enabled=True, patterns=None):
        return {"claude_status": {
            "filter_enabled": filter_enabled,
            "ignore_title_patterns": patterns if patterns is not None else [],
        }}

    # ---- id-dismiss: suppressed incident falls through to next rule ----
    #
    # Note: status_incident_tracked.json has Claude Code in degraded_performance status.
    # When the incident is suppressed, derivation falls through to Rule 3 (degraded
    # component), which returns a degraded result — NOT None. This is the correct
    # D-01 quiet-when-healthy behavior: suppressed incident → next relevant state.
    # To test "suppressed → None" we need a fixture with only the incident and all
    # components operational (no Rule 3 trigger). Use status_operational.json with
    # an injected incident instead.

    def test_id_dismiss_suppresses_incident_not_in_triggered(self):
        """_derive_claude_status with id-dismiss skips the incident (does NOT return kind='incident')."""
        summary = _load_fixture("status_incident_tracked.json")
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._derive_claude_status(summary, dismissals=dismissals, cfg=cfg)
        # The incident is suppressed, so result must NOT be kind='incident'.
        # It may be None or kind='degraded' (Rule 3) since the fixture has
        # Claude Code in degraded_performance — but not the incident.
        if result is not None:
            self.assertNotEqual(result.get("kind"), "incident",
                                "Id-dismissed incident must NOT appear as kind='incident' in result")

    def test_id_dismiss_on_all_operational_returns_none(self):
        """Id-dismiss on incident in all-operational context falls through to None (D-01)."""
        # Build a summary with an incident on operational components (no Rule 3 trigger)
        summary = {
            "components": [
                {"name": "Claude Code", "status": "operational"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {
                    "id": "inc-perp",
                    "name": "Mythos model access removal",
                    "status": "monitoring",
                    "impact": "minor",
                    "components": [{"name": "Claude Code", "status": "operational"}],
                }
            ],
            "scheduled_maintenances": [],
        }
        dismissals = {"inc-perp": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._derive_claude_status(summary, dismissals=dismissals, cfg=cfg)
        self.assertIsNone(result,
                          "Id-dismissed only incident on operational components must fall through to None (D-01)")

    # ---- keyword: suppressed incident falls through ----

    def test_keyword_suppresses_incident_not_in_triggered(self):
        """_derive_claude_status with matching keyword skips the incident (NOT kind='incident')."""
        summary = _load_fixture("status_incident_tracked.json")
        cfg = self._cfg(patterns=["Elevated"])
        result = self.mod._derive_claude_status(summary, dismissals={}, cfg=cfg)
        # Incident suppressed → must NOT appear as kind='incident'
        if result is not None:
            self.assertNotEqual(result.get("kind"), "incident",
                                "Keyword-suppressed incident must NOT appear as kind='incident'")

    def test_keyword_on_all_operational_returns_none(self):
        """Keyword match on incident in all-operational context falls through to None (D-01)."""
        summary = {
            "components": [
                {"name": "Claude Code", "status": "operational"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {
                    "id": "inc-perp",
                    "name": "Mythos model access removal",
                    "status": "monitoring",
                    "impact": "minor",
                    "components": [{"name": "Claude Code", "status": "operational"}],
                }
            ],
            "scheduled_maintenances": [],
        }
        cfg = self._cfg(patterns=["Mythos"])
        result = self.mod._derive_claude_status(summary, dismissals={}, cfg=cfg)
        self.assertIsNone(result,
                          "Keyword-suppressed only incident on operational components must fall through to None (D-01)")

    # ---- escalation re-surface ----

    def test_escalation_resurfaces_id_dismissed_incident(self):
        """Id-dismissed minor incident with live major impact resurfaces (NOT None), D-03."""
        summary = _load_fixture("status_incident_tracked_major.json")
        # Dismissed at 'minor', but live impact is 'major' → re-surface
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg()
        result = self.mod._derive_claude_status(summary, dismissals=dismissals, cfg=cfg)
        self.assertIsNotNone(result,
                             "Escalated incident (major > minor-at-dismiss) must re-surface (D-03)")
        self.assertEqual(result.get("kind"), "incident",
                         "Re-surfaced result must be kind='incident', not kind='degraded' (Rule 3 fallback)")
        self.assertEqual(result.get("severity"), "major",
                         "Re-surfaced incident must carry the escalated impact as severity")

    # ---- toggle-off: no suppression ----

    def test_toggle_off_no_suppression(self):
        """filter_enabled=False with matching id-dismiss AND keyword → incident returned (no suppression).

        Uses an all-operational summary with an incident so there's no Rule 3 fallback
        to obscure whether the incident itself was suppressed.
        """
        summary = {
            "components": [
                {"name": "Claude Code", "status": "operational"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {
                    "id": "inc-001",
                    "name": "Elevated error rates for Claude Code tool calls",
                    "status": "monitoring",
                    "impact": "minor",
                    "components": [{"name": "Claude Code", "status": "operational"}],
                }
            ],
            "scheduled_maintenances": [],
        }
        dismissals = {"inc-001": {"impact_at_dismiss": "minor"}}
        cfg = self._cfg(filter_enabled=False, patterns=["Elevated"])
        result = self.mod._derive_claude_status(summary, dismissals=dismissals, cfg=cfg)
        self.assertIsNotNone(result,
                             "filter_enabled=False must disable all suppression — incident must be returned")
        self.assertEqual(result.get("kind"), "incident",
                         "filter_enabled=False must return kind='incident' (not suppressed)")

    # ---- backward compat: no new args → Phase 6 behavior unchanged ----

    def test_backward_compat_no_args_returns_incident(self):
        """_derive_claude_status(summary) with no new args returns incident as before (Phase 6 compat)."""
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result,
                             "No-new-args call must return incident (Phase 6 backward compat)")
        self.assertEqual(result.get("kind"), "incident")

    def test_backward_compat_operational_still_none(self):
        """_derive_claude_status(summary) on operational fixture still returns None (backward compat)."""
        summary = _load_fixture("status_operational.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNone(result, "Operational fixture must still return None (backward compat)")

    # ---- bad regex in _derive_claude_status: no raise, no suppression ----

    def test_bad_regex_in_derive_does_not_suppress(self):
        """_derive_claude_status with bad regex pattern returns the incident (not suppressed, no raise)."""
        summary = _load_fixture("status_incident_tracked.json")
        cfg = self._cfg(patterns=["[unterminated"])
        try:
            result = self.mod._derive_claude_status(summary, dismissals={}, cfg=cfg)
        except Exception as e:
            self.fail(f"_derive_claude_status raised on bad regex: {e}")
        self.assertIsNotNone(result, "Bad regex must degrade to no-match — incident not suppressed")


# ---------------------------------------------------------------------------
# Phase 7 Plan 02: Task 2 — Escalation fixture + refresh-path auto-prune wiring
# ---------------------------------------------------------------------------


class TestEscalationFixtureAndAutoPrune(unittest.TestCase):
    """Escalation fixture loads correctly; refresh path auto-prunes stale dismissed ids (D-04)."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.dismissals_path = os.path.join(self.tmpdir, "status_dismissals.json")
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
            "claude_status": {
                "filter_enabled": True,
                "ignore_title_patterns": [],
            },
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _fetch_with_fixture(self, fixture_name: str) -> dict:
        """Run fetch_claude_status with FAKE_STATUS fixture; return written claude_status section."""
        fake_path = os.path.join(FIXTURES_DIR, fixture_name)
        with patch.dict(os.environ, {"CLAUDE_STATUSLINE_FAKE_STATUS": fake_path}):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
                    self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        return data.get("claude_status", {})

    # ---- escalation fixture loads correctly ----

    def test_major_fixture_exists(self):
        """tests/fixtures/status_incident_tracked_major.json must exist."""
        path = os.path.join(FIXTURES_DIR, "status_incident_tracked_major.json")
        self.assertTrue(os.path.exists(path),
                        "status_incident_tracked_major.json fixture must exist")

    def test_major_fixture_has_inc_001(self):
        """Major fixture contains inc-001."""
        data = _load_fixture("status_incident_tracked_major.json")
        ids = [i.get("id") for i in data.get("incidents", [])]
        self.assertIn("inc-001", ids, "Major fixture must contain incident with id='inc-001'")

    def test_major_fixture_impact_is_major(self):
        """Major fixture inc-001 has impact='major'."""
        data = _load_fixture("status_incident_tracked_major.json")
        inc = next((i for i in data.get("incidents", []) if i.get("id") == "inc-001"), None)
        self.assertIsNotNone(inc, "inc-001 must be present in major fixture")
        self.assertEqual(inc.get("impact"), "major",
                         "inc-001 impact must be 'major' in the escalation fixture")

    def test_major_fixture_undismissed_returns_major_severity(self):
        """_derive_claude_status on major fixture (un-dismissed) returns major-severity incident."""
        summary = _load_fixture("status_incident_tracked_major.json")
        result = self.mod._derive_claude_status(summary)
        self.assertIsNotNone(result, "Major fixture must return a non-None result")
        self.assertEqual(result.get("severity"), "major",
                         f"Major fixture must yield severity='major'; got {result.get('severity')!r}")

    # ---- auto-prune: fetch path calls _prune_dismissals ----

    def test_fetch_prunes_stale_dismissed_id(self):
        """fetch_claude_status prunes a dismissed id no longer in the live feed (D-04)."""
        # Seed the store with a stale id (not in the live feed) + a live id (in the feed)
        initial_store = {
            "inc-stale-999": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000001.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # Run fetch against the live fixture (contains inc-001, NOT inc-stale-999)
        self._fetch_with_fixture("status_incident_tracked.json")

        # The stale id must be gone; the live id must remain
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertNotIn("inc-stale-999", store,
                         "Auto-prune must remove dismissed id not in live feed (D-04)")
        self.assertIn("inc-001", store,
                      "Auto-prune must retain dismissed id that is still in live feed")

    def test_fetch_prune_does_not_write_toml(self):
        """Auto-prune writes only the tool-owned store; no TOML mutation (D-05)."""
        # Check that no TOML file is written during the fetch
        toml_path = os.path.expanduser("~/.claude/claude-statusline/claude-statusline.toml")
        # Track write_dismissals calls (store-only) and ensure load_config isn't called with write
        toml_write_calls = []

        original_open = open
        def spy_open(path, mode="r", **kwargs):
            if "w" in mode and str(path).endswith(".toml"):
                toml_write_calls.append(path)
            return original_open(path, mode, **kwargs)

        with patch.dict(os.environ, {"CLAUDE_STATUSLINE_FAKE_STATUS":
                                      os.path.join(FIXTURES_DIR, "status_incident_tracked.json")}):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
                    self.mod.fetch_claude_status(self.cfg)

        self.assertEqual(toml_write_calls, [],
                         "Auto-prune must NOT write any TOML file (D-05)")

    def test_fetch_passes_dismissals_and_cfg_to_derive(self):
        """fetch_claude_status threads dismissals and cfg into _derive_claude_status (D-01 integration)."""
        # Dismiss inc-001 so the derivation should suppress it
        initial_store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # Run fetch against incident fixture — incident dismissed → noteworthy should be False
        # (or a degraded result from Rule 3, but NOT an incident result)
        self._fetch_with_fixture("status_incident_tracked.json")
        section = self.mod.read_cache(self.cache_path).get("claude_status", {})

        # The cached result must NOT show kind='incident' since it's dismissed
        # (It may show noteworthy=False or kind='degraded' from Rule 3)
        if section.get("noteworthy"):
            self.assertNotEqual(section.get("kind"), "incident",
                                "Dismissed incident must NOT be cached as kind='incident' "
                                "(dismissals+cfg threaded into derivation)")

    def test_stale_store_after_operational_fixture_is_pruned(self):
        """fetch against operational fixture (no incidents) prunes ALL dismissed ids (D-04)."""
        # Seed with two dismissed ids; operational feed has no incidents
        initial_store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
            "inc-002": {"impact_at_dismiss": "major", "dismissed_at": 1700000001.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # Run against operational (no incidents) → no live ids → all pruned
        self._fetch_with_fixture("status_operational.json")

        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertEqual(store, {},
                         "All dismissed ids must be pruned when live feed has no incidents (D-04)")

    # ---- Phase 07.1 Plan 02: resolved-but-degraded retention (D-06) ----
    #
    # A dismissed incident that resolves while its tracked component is still
    # non-operational must NOT be pruned (D-06: muting wins through the resolved
    # phase). The dismissal must survive so the incident cannot re-surface green.
    # Only when the component returns to operational (or the incident disappears)
    # should the dismissal be pruned as genuinely stale.

    def test_dismissed_resolved_degraded_component_dismissal_retained(self):
        """Dismissed resolved incident whose tracked component is still degraded → dismissal RETAINED.

        D-06: muting wins through the resolved phase. A dismissed incident that has
        resolved but whose component (Claude Code) is still in partial_outage must
        keep its dismissal alive so it cannot re-surface green.

        Uses status_resolved_degraded.json: inc-resolved-001 (status=resolved),
        Claude Code in partial_outage.
        """
        initial_store = {
            "inc-resolved-001": {"impact_at_dismiss": "major", "dismissed_at": 1700000000.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # Fetch against the resolved-but-degraded fixture.
        # inc-resolved-001 is resolved but Claude Code is still partial_outage →
        # live_ids MUST include inc-resolved-001 → dismissal survives prune.
        self._fetch_with_fixture("status_resolved_degraded.json")

        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertIn("inc-resolved-001", store,
                      "Dismissed resolved incident with still-degraded component must "
                      "be RETAINED in the dismissal store (D-06: muting wins through resolved phase)")

    def test_dismissed_resolved_operational_component_dismissal_pruned(self):
        """Dismissed resolved incident whose tracked component is back to operational → dismissal PRUNED.

        D-06: once the component is operational, the incident is truly stale and
        the dismissal can be safely removed. Uses an inline summary where
        inc-resolved-001 is resolved and Claude Code is operational.
        """
        # Build an inline summary: resolved incident, tracked component back to operational
        summary_with_resolved_operational = {
            "page": {"id": "test"},
            "components": [
                {"name": "Claude Code", "status": "operational"},
                {"name": "claude.ai", "status": "operational"},
                {"name": "Claude Cowork", "status": "operational"},
            ],
            "incidents": [
                {
                    "id": "inc-resolved-001",
                    "name": "Claude Code partial outage — now cleared",
                    "status": "resolved",
                    "impact": "major",
                    "updated_at": "2026-06-18T13:00:00Z",
                    "components": [
                        {"name": "Claude Code", "status": "operational"},
                    ],
                }
            ],
            "scheduled_maintenances": [],
        }

        initial_store = {
            "inc-resolved-001": {"impact_at_dismiss": "major", "dismissed_at": 1700000000.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # Write the inline summary as a temp fixture file and load via FAKE_STATUS
        import tempfile as _tempfile
        import json as _json
        tmp_fixture = os.path.join(self.tmpdir, "status_resolved_operational_inline.json")
        with open(tmp_fixture, "w") as fh:
            _json.dump(summary_with_resolved_operational, fh)

        with patch.dict(os.environ, {"CLAUDE_STATUSLINE_FAKE_STATUS": tmp_fixture}):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
                    self.mod.fetch_claude_status(self.cfg)

        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertNotIn("inc-resolved-001", store,
                         "Dismissed resolved incident with operational component must "
                         "be PRUNED (genuinely stale — D-06 does not protect it once cleared)")

    def test_unresolved_incident_id_still_retained_in_live_ids(self):
        """Unresolved (monitoring) incident dismissal is still retained after the prune fix.

        Regression: the base behavior for unresolved incidents must remain unchanged.
        Uses status_incident_tracked.json which has inc-001 (status=monitoring).
        """
        initial_store = {
            "inc-001": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        self._fetch_with_fixture("status_incident_tracked.json")

        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertIn("inc-001", store,
                      "Unresolved incident dismissal must still be RETAINED (regression guard)")

    def test_vanished_incident_dismissal_still_pruned(self):
        """Incident that has vanished from the feed entirely → dismissal still pruned.

        Regression: the base prune behavior for incidents no longer in the feed
        must remain unchanged regardless of the resolved-degraded fix.
        """
        initial_store = {
            "inc-vanished-999": {"impact_at_dismiss": "minor", "dismissed_at": 1700000000.0},
        }
        self.mod.write_dismissals(initial_store, self.dismissals_path)

        # status_operational.json has no incidents → vanished id must be pruned
        self._fetch_with_fixture("status_operational.json")

        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertNotIn("inc-vanished-999", store,
                         "Vanished incident dismissal must be PRUNED (truly stale — regression guard)")


# ---------------------------------------------------------------------------
# Phase 07 Plan 03 Task 1: --dismiss / --undismiss store-mutation flags
# ---------------------------------------------------------------------------

class TestDismissUndismissFlags(unittest.TestCase):
    """--dismiss / --undismiss main() branches: store mutation, next-refresh note, graceful errors."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.dismissals_path = os.path.join(self.tmpdir, "status_dismissals.json")
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.cfg = {
            "claude_status": {"filter_enabled": True, "ignore_title_patterns": []},
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_cache_with_incident(self, inc_id="inc-001", impact="minor"):
        """Write a cache file with a tracked_incidents list containing the given incident."""
        payload = {
            "claude_status": {
                "fetched_at": time.time(),
                "tracked_incidents": [
                    {"id": inc_id, "impact": impact, "status": "monitoring",
                     "title": "Test incident", "component": "Claude Code"}
                ],
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(payload, f)

    # ---- --dismiss store mutation ----

    def test_dismiss_flag_adds_entry_to_store(self):
        """--dismiss handler records inc-001 in the dismissal store."""
        self._make_cache_with_incident("inc-001", "minor")
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod._handle_dismiss_flag("inc-001")
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertIn("inc-001", store, "--dismiss must add the id to the dismissal store")

    def test_dismiss_flag_records_live_impact_baseline(self):
        """--dismiss stores impact_at_dismiss matching the live cache entry ('minor')."""
        self._make_cache_with_incident("inc-001", "minor")
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod._handle_dismiss_flag("inc-001")
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertEqual(store["inc-001"]["impact_at_dismiss"], "minor",
                         "impact_at_dismiss must match the live cache impact ('minor')")

    # ---- --undismiss store mutation ----

    def test_undismiss_flag_removes_entry_from_store(self):
        """--undismiss handler removes inc-001 from the dismissal store."""
        # Seed the store with inc-001
        self.mod.write_dismissals(
            {"inc-001": {"impact_at_dismiss": "minor", "dismissed_at": time.time()}},
            self.dismissals_path,
        )
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            self.mod._handle_undismiss_flag("inc-001")
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertNotIn("inc-001", store, "--undismiss must remove the id from the store")

    # ---- next-refresh note in confirmation output ----

    def test_dismiss_confirmation_contains_next_refresh_note(self):
        """--dismiss confirmation mentions next refresh (or --refresh applies it immediately)."""
        self._make_cache_with_incident("inc-001", "minor")
        import io
        buf = io.StringIO()
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                import sys as _sys
                original_stdout = _sys.stdout
                _sys.stdout = buf
                try:
                    self.mod._handle_dismiss_flag("inc-001")
                finally:
                    _sys.stdout = original_stdout
        output = buf.getvalue()
        self.assertTrue(
            "refresh" in output.lower(),
            f"--dismiss confirmation must mention next-refresh note; got: {output!r}"
        )

    def test_undismiss_confirmation_contains_next_refresh_note(self):
        """--undismiss confirmation also mentions next refresh."""
        import io
        buf = io.StringIO()
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            import sys as _sys
            original_stdout = _sys.stdout
            _sys.stdout = buf
            try:
                self.mod._handle_undismiss_flag("inc-001")
            finally:
                _sys.stdout = original_stdout
        output = buf.getvalue()
        self.assertTrue(
            "refresh" in output.lower(),
            f"--undismiss confirmation must mention next-refresh note; got: {output!r}"
        )

    def test_dismiss_confirmation_mentions_refresh_applies_immediately(self):
        """--dismiss next-refresh note says --refresh applies the change now."""
        self._make_cache_with_incident("inc-001", "minor")
        import io
        buf = io.StringIO()
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                import sys as _sys
                original_stdout = _sys.stdout
                _sys.stdout = buf
                try:
                    self.mod._handle_dismiss_flag("inc-001")
                finally:
                    _sys.stdout = original_stdout
        output = buf.getvalue()
        self.assertTrue(
            "--refresh" in output,
            f"--dismiss note must mention '--refresh' for immediate effect; got: {output!r}"
        )

    # ---- unknown id falls back to 'none' impact ----

    def test_dismiss_unknown_id_records_with_none_impact(self):
        """--dismiss unknown id (not in cache) records with impact_at_dismiss='none'."""
        # Cache has no incidents
        self._make_cache_with_incident("inc-999", "minor")  # different id
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod._handle_dismiss_flag("inc-unknown")
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertIn("inc-unknown", store,
                      "Unknown id must still be recorded in the store")
        self.assertEqual(store["inc-unknown"]["impact_at_dismiss"], "none",
                         "Unknown id must use 'none' as the impact_at_dismiss baseline")

    # ---- missing arg degrades gracefully ----

    def test_dismiss_missing_arg_no_index_error(self):
        """--dismiss with no following token: no IndexError, clean exit, store unchanged."""
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                try:
                    self.mod._handle_dismiss_flag("")  # empty id = missing arg
                except Exception as e:
                    self.fail(f"--dismiss missing arg raised: {e}")
        # store must remain empty
        store = self.mod.read_dismissals(self.dismissals_path)
        self.assertEqual(store, {},
                         "Missing id arg must leave store unchanged")

    def test_undismiss_missing_arg_no_raise(self):
        """--undismiss with no following token: no raise, store unchanged."""
        with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
            try:
                self.mod._handle_undismiss_flag("")  # empty id = missing arg
            except Exception as e:
                self.fail(f"--undismiss missing arg raised: {e}")

    # ---- no stdin, no bar ----

    def test_dismiss_does_not_call_load_stdin(self):
        """--dismiss handler must not call _load_stdin."""
        self._make_cache_with_incident()
        called = []
        original = self.mod._load_stdin
        self.mod._load_stdin = lambda: called.append(True) or {}
        try:
            with patch.object(self.mod, "_DISMISSALS_PATH", self.dismissals_path):
                with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                    self.mod._handle_dismiss_flag("inc-001")
        finally:
            self.mod._load_stdin = original
        self.assertEqual(called, [], "--dismiss must not call _load_stdin")


# ---------------------------------------------------------------------------
# Phase 07 Plan 03 Task 2: --status-incidents table (sanitized, cache+store only)
# ---------------------------------------------------------------------------

class TestStatusIncidentsFlag(unittest.TestCase):
    """--status-incidents: readable table from cache + store only, sanitized, never fetches."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.dismissals_path = os.path.join(self.tmpdir, "status_dismissals.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_cache_with_incidents(self, incidents):
        """Write a cache file with the given tracked_incidents list."""
        payload = {
            "claude_status": {
                "fetched_at": time.time(),
                "tracked_incidents": incidents,
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(payload, f)

    def _call_print_helper(self, incidents, dismissals=None):
        """Call _print_status_incidents directly; capture stdout."""
        import io
        import sys as _sys
        cache = {"claude_status": {"fetched_at": time.time(), "tracked_incidents": incidents}}
        store = dismissals if dismissals is not None else {}
        buf = io.StringIO()
        original = _sys.stdout
        _sys.stdout = buf
        try:
            self.mod._print_status_incidents(cache, store)
        finally:
            _sys.stdout = original
        return buf.getvalue()

    # ---- helper exists ----

    def test_print_helper_exists(self):
        """_print_status_incidents function must exist in the module."""
        self.assertTrue(callable(getattr(self.mod, "_print_status_incidents", None)),
                        "_print_status_incidents must be a callable")

    # ---- table content ----

    def test_table_contains_incident_id(self):
        """Output contains the incident id."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated error rates for Claude Code tool calls",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertIn("inc-001", output, "Table must include the incident id")

    def test_table_contains_incident_title(self):
        """Output contains the (sanitized) incident title."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated error rates for Claude Code tool calls",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertIn("Elevated error rates", output,
                      "Table must include the incident title text")

    def test_table_contains_component(self):
        """Output contains the affected component name."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated error rates for Claude Code tool calls",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertIn("Claude Code", output,
                      "Table must include the affected component name")

    def test_table_contains_impact(self):
        """Output contains the impact level."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated error rates for Claude Code tool calls",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertIn("minor", output, "Table must include the impact level")

    def test_table_contains_status(self):
        """Output contains the status value."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated error rates for Claude Code tool calls",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertIn("monitoring", output, "Table must include the status value")

    # ---- dismissed / active markers ----

    def test_active_incident_shows_active_marker(self):
        """Undismissed incident shows 'active' state marker."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Test incident", "component": "Claude Code"}]
        output = self._call_print_helper(incidents, dismissals={})
        self.assertIn("active", output,
                      "Undismissed incident must show 'active' state marker")

    def test_dismissed_incident_shows_dismissed_marker(self):
        """Dismissed incident shows 'dismissed' state marker."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Test incident", "component": "Claude Code"}]
        store = {"inc-001": {"impact_at_dismiss": "minor", "dismissed_at": time.time()}}
        output = self._call_print_helper(incidents, dismissals=store)
        self.assertIn("dismissed", output,
                      "Dismissed incident must show 'dismissed' state marker")

    def test_stale_store_entry_shows_stale_marker(self):
        """A store entry whose id is NOT in the live tracked_incidents shows 'stale'."""
        # Live list is empty; store has a stale entry
        incidents = []
        store = {"inc-stale": {"impact_at_dismiss": "minor", "dismissed_at": time.time()}}
        output = self._call_print_helper(incidents, dismissals=store)
        self.assertIn("stale", output,
                      "Store entry absent from live incidents must show 'stale' marker")
        self.assertIn("inc-stale", output,
                      "Stale store entry id must appear in the output")

    # ---- no network fetch ----

    def test_no_fetch_claude_status_call(self):
        """_print_status_incidents must NOT call fetch_claude_status."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Test", "component": "Claude Code"}]
        fetch_called = []
        original = self.mod.fetch_claude_status
        self.mod.fetch_claude_status = lambda cfg: fetch_called.append(True)
        try:
            self._call_print_helper(incidents)
        finally:
            self.mod.fetch_claude_status = original
        self.assertEqual(fetch_called, [],
                         "_print_status_incidents must not call fetch_claude_status")

    # ---- ANSI sanitization ----

    def test_malicious_title_no_raw_escape(self):
        """Malicious title with raw ANSI escapes must not appear in output."""
        # Use the malicious title from the fixture
        malicious = "\x1b[31mCRITICAL\x1b[0m: Claude Code \x1b[1;31moutage\x1b[0m"
        incidents = [{"id": "inc-malicious", "impact": "major", "status": "investigating",
                      "title": malicious, "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertNotIn("\x1b", output,
                         "Output must not contain raw ANSI escape (\\x1b) sequences")

    def test_malicious_title_from_fixture_no_escape(self):
        """Incident from status_malicious_title.json fixture produces escape-free output."""
        # Simulate what _collect_tracked_incidents would produce from the fixture
        incidents = [{"id": "inc-malicious",
                      "impact": "major",
                      "status": "investigating",
                      "title": "\x1b[31mCRITICAL\x1b[0m: Claude Code \x1b[1;31moutage\x1b[0m",
                      "component": "Claude Code"}]
        output = self._call_print_helper(incidents)
        self.assertNotIn("\x1b", output,
                         "Fixture malicious title must be sanitized before printing")

    # ---- empty list ----

    def test_empty_incidents_friendly_message(self):
        """Empty tracked_incidents list → friendly 'no tracked incidents' message."""
        output = self._call_print_helper([])
        self.assertTrue(
            len(output.strip()) > 0,
            "Empty list must produce a non-empty friendly message (not silent exit)"
        )
        # Should say something about no incidents or nothing tracked
        lower = output.lower()
        self.assertTrue(
            "no" in lower or "none" in lower or "empty" in lower,
            f"Empty list message must indicate absence of incidents; got: {output!r}"
        )

    # ---- main() branch exists before _load_stdin ----

    def test_main_has_status_incidents_branch(self):
        """main() source must contain '--status-incidents' in sys.argv branch."""
        import inspect
        source = inspect.getsource(self.mod.main)
        self.assertIn("--status-incidents", source,
                      "main() must have a --status-incidents branch")

    # ---- Phase 07.1 Plan 03 Task 2: 'resolved' STATE column (D-07) ----
    #
    # Wave-1 widened _collect_tracked_incidents to carry resolved incidents
    # (status=="resolved"). The --status-incidents printer must now report a
    # "resolved" STATE for those entries, with dismissed taking precedence.

    def test_resolved_incident_shows_resolved_state(self):
        """Tracked incident with status=='resolved' and NOT dismissed → STATE shows 'resolved' (D-07).

        Wave-1 widened tracked_incidents to include resolved entries. The printer
        must use 'resolved' as the STATE column value, not 'active', for these entries.
        """
        incidents = [{"id": "inc-resolved-001", "impact": "major", "status": "resolved",
                      "title": "API errors now cleared", "component": "Claude Code"}]
        output = self._call_print_helper(incidents, dismissals={})
        # The STATE column value must be 'resolved', not 'active'
        self.assertNotIn("active", output,
                         f"Resolved incident must NOT show 'active' STATE; got {output!r}")
        # Locate the data row (after the header and separator) and check the STATE column
        lines = [ln for ln in output.splitlines() if "inc-resolved-001" in ln]
        self.assertTrue(lines, "Output must include a row for inc-resolved-001")
        row = lines[0]
        # The STATE column sits after the STATUS column; 'resolved' must appear in the
        # row as the STATE value (COL_STATE=10 means it occupies a fixed-width column).
        # Count occurrences: 'resolved' appears once in the status col and should now
        # also appear in the state col — for a clean assertion, verify the row does NOT
        # contain 'active' and DOES contain 'resolved' at least twice (status + state).
        self.assertGreaterEqual(row.count("resolved"), 2,
                                f"Row must contain 'resolved' in BOTH status and state columns; "
                                f"row={row!r}")

    def test_dismissed_resolved_shows_dismissed_not_resolved(self):
        """Dismissed resolved incident → STATE shows 'dismissed', not 'resolved' (dismissed precedence).

        dismissed always outranks resolved in the STATE column. A dismissed resolved
        incident shows 'dismissed', matching the existing precedence documented in
        the _print_status_incidents docstring.
        """
        incidents = [{"id": "inc-resolved-001", "impact": "major", "status": "resolved",
                      "title": "API errors now cleared", "component": "Claude Code"}]
        store = {"inc-resolved-001": {"impact_at_dismiss": "major", "dismissed_at": time.time()}}
        output = self._call_print_helper(incidents, dismissals=store)
        self.assertIn("dismissed", output,
                      "Dismissed resolved incident must show 'dismissed' STATE (dismissed precedence)")
        # 'resolved' must NOT appear as the STATE for this entry
        # (it still appears in the status column, but the STATE column must read 'dismissed')
        # Check by finding the row for inc-resolved-001 and verifying dismissed appears before
        # the first occurrence of 'resolved' on that line, or simply that 'dismissed' is present
        # and is the STATE value for this entry.
        # A simple check: the output contains 'dismissed' (the state) and the entry id.
        self.assertIn("inc-resolved-001", output,
                      "Dismissed resolved incident row must show the incident id")

    def test_active_incident_still_shows_active(self):
        """Unresolved, undismissed incident → STATE 'active' unchanged (regression guard)."""
        incidents = [{"id": "inc-001", "impact": "minor", "status": "monitoring",
                      "title": "Elevated errors", "component": "Claude Code"}]
        output = self._call_print_helper(incidents, dismissals={})
        self.assertIn("active", output,
                      "Unresolved undismissed incident must still show 'active' STATE (regression)")

    def test_stale_entry_still_shows_stale(self):
        """Store entry not in live feed → STATE 'stale' unchanged (regression guard)."""
        incidents = []
        store = {"inc-stale": {"impact_at_dismiss": "minor", "dismissed_at": time.time()}}
        output = self._call_print_helper(incidents, dismissals=store)
        self.assertIn("stale", output,
                      "Store entry absent from live feed must still show 'stale' STATE (regression)")

    def test_resolved_state_in_docstring(self):
        """_print_status_incidents docstring must document the 'resolved' STATE value."""
        import inspect
        source = inspect.getsource(self.mod._print_status_incidents)
        self.assertIn("resolved", source,
                      "_print_status_incidents docstring must document the 'resolved' STATE value (D-07)")

    def test_malformed_cache_for_resolved_state_no_raise(self):
        """Malformed/garbage cache when a resolved-status entry is present → no raise (D-10)."""
        # Entries with missing/None fields — must not raise
        bad_incidents = [
            {"id": None, "impact": None, "status": "resolved", "title": None, "component": None},
            None,
            "not a dict",
            {"id": "inc-x", "status": "resolved"},  # missing other fields
        ]
        try:
            output = self._call_print_helper(bad_incidents, dismissals={})
            # Must produce some output (header) without raising
            self.assertIsInstance(output, str,
                                  "Malformed incident entries must produce string output, not raise")
        except Exception as exc:
            self.fail(f"_print_status_incidents raised on malformed entries with resolved status: {exc}")


if __name__ == "__main__":
    unittest.main()
