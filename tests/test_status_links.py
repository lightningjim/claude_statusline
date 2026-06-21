#!/usr/bin/env python3
"""
Tests for Plan 09-03: OSC 8 status incident links.

Task 1 (TestStatusLinkEnabled): With links enabled and a valid incident id
(matching ^[0-9a-z]+$) the whole rendered status segment is wrapped in an
OSC 8 hyperlink to https://status.claude.com/incidents/{id}.

Task 2 (TestStatusLinkDisabled): LINK-03 guarantee — no \\x1b]8 bytes when
links=off; D-03a guarantee — no homepage substitution when id is
missing/invalid.
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

# OSC 8 escape sequences — compare as str (the module uses str throughout)
OSC8_OPEN  = "\x1b]8;;"        # ESC ] 8 ; ; (before URL)
OSC8_ST    = "\x1b\\"          # ST terminator
OSC8_CLOSE = "\x1b]8;;\x1b\\"  # empty-URL close (terminates span)

STATUS_BASE_URL = "https://status.claude.com/incidents/"
STATUS_HOMEPAGE = "https://status.claude.com"


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_cache_with_status(tmpdir: str, status_section: dict) -> str:
    """Write a cache.json with the given claude_status section; return path."""
    cache_path = os.path.join(tmpdir, "cache.json")
    cache_data = {"claude_status": status_section}
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    return cache_path


def _fresh_incident_section(incident_id: str | None = "abc123def456",
                             title: str = "Elevated error rates for Claude Code",
                             impact: str = "minor") -> dict:
    """Return a fresh cache section for a tracked incident with the given id.

    If incident_id is None the tracked_incidents list contains an incident
    without an 'id' key (simulates missing id).
    """
    now = time.time()
    if incident_id is None:
        tracked = [{"title": title, "impact": impact}]  # no 'id' key
    else:
        tracked = [{"id": incident_id, "title": title, "impact": impact}]
    return {
        "fetched_at": now - 60,
        "noteworthy": True,
        "kind": "incident",
        "severity": "minor",
        "label": title,
        "tracked_incidents": tracked,
    }


def _run_segment(mod, status_section: dict, links: str = "on", tmpdir: str | None = None) -> str | None:
    """Call _claude_status_segment with a monkeypatched cache and given links setting."""
    own_tmpdir = tmpdir is None
    if own_tmpdir:
        tmpdir = tempfile.mkdtemp()
    try:
        cache_path = _make_cache_with_status(tmpdir, status_section)
        cfg = {
            "cache": {
                "status_ttl": 300,
                "status_max_stale": 900,
            },
            "display": {
                "show_claude_status": True,
                "icon_set": "nerd",
                "links": links,
            },
        }
        with patch.object(mod, "_CACHE_PATH", cache_path):
            return mod._claude_status_segment({}, cfg)
    finally:
        if own_tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Task 1 (RED): links enabled + valid incident id → OSC 8 link present
# ---------------------------------------------------------------------------

class TestStatusLinkEnabled(unittest.TestCase):
    """With links=on and a valid incident id the whole status segment is wrapped in OSC 8."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, incident_id: str = "abc123def456") -> str | None:
        sec = _fresh_incident_section(incident_id=incident_id)
        return _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)

    def test_link_present_with_valid_id(self):
        """With links=on and a valid id (^[0-9a-z]+$) the segment contains the incident URL."""
        result = self._run("abc123def456")
        self.assertIsNotNone(result, "Segment must not be None")
        expected_url = STATUS_BASE_URL + "abc123def456"
        self.assertIn(expected_url, result,
                      f"Expected incident URL in rendered segment; got: {result!r}")

    def test_osc8_open_present_with_valid_id(self):
        """OSC 8 open sequence is present in rendered segment when links=on + valid id."""
        result = self._run("abc123def456")
        self.assertIsNotNone(result)
        self.assertIn(OSC8_OPEN, result,
                      f"OSC 8 open sequence must appear; got: {result!r}")

    def test_osc8_close_present_with_valid_id(self):
        """OSC 8 close sequence is present in rendered segment when links=on + valid id."""
        result = self._run("abc123def456")
        self.assertIsNotNone(result)
        self.assertIn(OSC8_CLOSE, result,
                      f"OSC 8 close sequence must appear; got: {result!r}")

    def test_full_osc8_open_with_url(self):
        """The OSC 8 open+URL sequence appears correctly in the rendered segment."""
        result = self._run("abc123def456")
        self.assertIsNotNone(result)
        expected = OSC8_OPEN + STATUS_BASE_URL + "abc123def456"
        self.assertIn(expected, result,
                      f"Expected full OSC 8 open+URL; got: {result!r}")

    def test_hyphenated_id_no_link(self):
        """A hyphenated id (inc-001, fails ^[0-9a-z]+$) → no OSC 8 bytes (D-03a)."""
        sec = _fresh_incident_section(incident_id="inc-001")
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result, "Segment must still render (just without link)")
        self.assertNotIn(OSC8_OPEN, result,
                         f"Hyphenated id must not produce OSC 8 bytes; got: {result!r}")
        self.assertNotIn("\x1b]8", result,
                         f"No OSC 8 escape bytes for hyphenated id; got: {result!r}")

    def test_hyphenated_id_no_homepage_fallback(self):
        """Hyphenated id → no homepage link target either (D-03a: omit-not-fake)."""
        sec = _fresh_incident_section(incident_id="inc-001")
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        # The status homepage must not appear as an OSC 8 link target
        self.assertNotIn(OSC8_OPEN + STATUS_HOMEPAGE, result,
                         f"Homepage must not be substituted; got: {result!r}")

    def test_missing_id_no_link(self):
        """Missing incident id → no OSC 8 bytes (D-03a)."""
        sec = _fresh_incident_section(incident_id=None)
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result, "Segment must still render")
        self.assertNotIn(OSC8_OPEN, result,
                         f"Missing id must not produce OSC 8 bytes; got: {result!r}")

    def test_missing_id_no_homepage_fallback(self):
        """Missing id → no homepage substitution (D-03a)."""
        sec = _fresh_incident_section(incident_id=None)
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN + STATUS_HOMEPAGE, result,
                         f"Homepage must not be substituted for missing id; got: {result!r}")


# ---------------------------------------------------------------------------
# Task 2 (RED): links disabled / invalid/missing id → no OSC 8 bytes (LINK-03 + D-03a)
# ---------------------------------------------------------------------------

class TestStatusLinkDisabled(unittest.TestCase):
    """With links=off the rendered status segment contains NO \\x1b]8 bytes (LINK-03)."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_links_off_no_osc8_bytes(self):
        """With links=off, rendered segment has no OSC 8 escape bytes (LINK-03)."""
        sec = _fresh_incident_section(incident_id="abc123def456")
        result = _run_segment(self.mod, sec, links="off", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No \\x1b]8 bytes when links=off; got: {result!r}")
        self.assertNotIn("\x1b]8", result,
                         f"No OSC 8 escape when links=off; got: {result!r}")

    def test_links_off_byte_identical_to_no_links_key(self):
        """Output when links=off must be byte-identical to output with no display.links key."""
        sec = _fresh_incident_section(incident_id="abc123def456")
        result_off = _run_segment(self.mod, sec, links="off", tmpdir=self.tmpdir)
        # No links key at all (defaults to off)
        cache_path = _make_cache_with_status(self.tmpdir, sec)
        cfg_no_links = {
            "cache": {"status_ttl": 300, "status_max_stale": 900},
            "display": {"show_claude_status": True, "icon_set": "nerd"},
            # no 'links' key
        }
        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            result_none = self.mod._claude_status_segment({}, cfg_no_links)
        self.assertEqual(result_off, result_none,
                         "links=off and no links key must produce byte-identical output")

    def test_injection_id_no_osc8_bytes(self):
        """An injection-bearing id (contains ESC byte) → no \\x1b]8 bytes."""
        # _valid_incident_id allowlist rejects any non-[0-9a-z] chars incl. ESC
        evil_id = "abc\x1bdef"
        sec = _fresh_incident_section(incident_id=evil_id)
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result, "Segment must still render")
        self.assertNotIn(OSC8_OPEN, result,
                         f"Injection id must not produce OSC 8 bytes; got: {result!r}")

    def test_injection_id_no_homepage_fallback(self):
        """Injection id → no homepage link target (D-03a)."""
        evil_id = "abc\x1bdef"
        sec = _fresh_incident_section(incident_id=evil_id)
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN + STATUS_HOMEPAGE, result,
                         f"Homepage must not be substituted for injection id; got: {result!r}")

    def test_empty_id_no_osc8_bytes(self):
        """An empty incident id → no OSC 8 bytes (D-03a)."""
        sec = _fresh_incident_section(incident_id="")
        # Also put it in tracked_incidents with empty string
        sec["tracked_incidents"] = [{"id": "", "title": "Some incident", "impact": "minor"}]
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result, "Segment must still render")
        self.assertNotIn(OSC8_OPEN, result,
                         f"Empty id must not produce OSC 8 bytes; got: {result!r}")

    def test_empty_id_no_homepage_fallback(self):
        """Empty id → no homepage substitution (D-03a)."""
        sec = _fresh_incident_section(incident_id="")
        sec["tracked_incidents"] = [{"id": "", "title": "Some incident", "impact": "minor"}]
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN + STATUS_HOMEPAGE, result,
                         f"Homepage must not be substituted for empty id; got: {result!r}")

    def test_no_incidents_slug_with_empty_id_no_link(self):
        """The rendered segment never contains 'incidents/' with an empty slug when id is missing."""
        sec = _fresh_incident_section(incident_id=None)
        result = _run_segment(self.mod, sec, links="on", tmpdir=self.tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn("incidents//", result,
                         f"Must not emit empty-slug incidents URL; got: {result!r}")
        self.assertNotIn("incidents/\x1b", result,
                         f"Must not emit incidents URL followed by ESC; got: {result!r}")


# ---------------------------------------------------------------------------
# Fixture-driven tests: status_incident_valid_id.json → fetch → segment
# ---------------------------------------------------------------------------

class TestStatusLinkEnabledViaFixture(unittest.TestCase):
    """Use CLAUDE_STATUSLINE_FAKE_STATUS to feed status_incident_valid_id.json through
    fetch_claude_status, then assert _claude_status_segment emits an OSC 8 link."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.valid_id_fixture = os.path.join(FIXTURES_DIR, "status_incident_valid_id.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _fetch_and_segment(self, fixture_path: str, links: str = "on") -> str | None:
        """Run fetch_claude_status with FAKE_STATUS → fixture, then call _claude_status_segment."""
        cache_path = os.path.join(self.tmpdir, "cache.json")
        cfg = {
            "cache": {"status_ttl": 300, "status_max_stale": 900},
            "display": {"show_claude_status": True, "icon_set": "nerd", "links": links},
        }
        env = {"CLAUDE_STATUSLINE_FAKE_STATUS": fixture_path}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(self.mod, "_CACHE_PATH", cache_path):
                self.mod.fetch_claude_status(cfg)
        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            return self.mod._claude_status_segment({}, cfg)

    def test_valid_id_fixture_contains_incident_key(self):
        """Fixture status_incident_valid_id.json has an 'incidents' key (must_haves check)."""
        with open(self.valid_id_fixture) as f:
            data = json.load(f)
        self.assertIn("incidents", data,
                      "status_incident_valid_id.json must have an 'incidents' key")
        self.assertTrue(len(data["incidents"]) > 0,
                        "status_incident_valid_id.json must have at least one incident")

    def test_valid_id_matches_allowlist(self):
        """The incident id in status_incident_valid_id.json matches ^[0-9a-z]+$ (no hyphen)."""
        import re
        with open(self.valid_id_fixture) as f:
            data = json.load(f)
        inc_id = data["incidents"][0]["id"]
        self.assertIsNotNone(re.fullmatch(r"[0-9a-z]+", inc_id),
                             f"id {inc_id!r} must match ^[0-9a-z]+$ (no hyphen)")

    def test_valid_id_fixture_produces_link(self):
        """status_incident_valid_id.json + links=on → OSC 8 link to the incident page."""
        result = self._fetch_and_segment(self.valid_id_fixture, links="on")
        self.assertIsNotNone(result, "Segment must not be None")
        self.assertIn(OSC8_OPEN, result,
                      f"OSC 8 open must appear with valid-id fixture; got: {result!r}")
        self.assertIn(STATUS_BASE_URL + "abc123def456", result,
                      f"Incident URL must appear; got: {result!r}")

    def test_hyphenated_id_fixture_no_link(self):
        """status_incident_tracked.json (id 'inc-001', hyphenated) + links=on → no OSC 8 (D-03a)."""
        hyphen_fixture = os.path.join(FIXTURES_DIR, "status_incident_tracked.json")
        result = self._fetch_and_segment(hyphen_fixture, links="on")
        self.assertIsNotNone(result, "Segment must still render")
        self.assertNotIn(OSC8_OPEN, result,
                         f"Hyphenated id must not produce OSC 8 bytes; got: {result!r}")

    def test_hyphenated_id_no_homepage_fallback_via_fixture(self):
        """Hyphenated id via fixture → no homepage as link target (D-03a)."""
        hyphen_fixture = os.path.join(FIXTURES_DIR, "status_incident_tracked.json")
        result = self._fetch_and_segment(hyphen_fixture, links="on")
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN + STATUS_HOMEPAGE, result,
                         f"Homepage must not be substituted; got: {result!r}")

    def test_valid_id_fixture_links_off_no_osc8(self):
        """status_incident_valid_id.json + links=off → no OSC 8 bytes (LINK-03)."""
        result = self._fetch_and_segment(self.valid_id_fixture, links="off")
        self.assertIsNotNone(result, "Segment must still render")
        self.assertNotIn(OSC8_OPEN, result,
                         f"No OSC 8 bytes when links=off; got: {result!r}")


if __name__ == "__main__":
    unittest.main()
