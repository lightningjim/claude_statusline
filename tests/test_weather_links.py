#!/usr/bin/env python3
"""
Tests for Plan 09-02 (updated in 09-04): OSC 8 weather alert links.

Task 1 (TestWeatherLinkEnabled): With links enabled and a valid UGC code + SAME the
rendered detail wraps the glyph+event+timing in an OSC 8 hyperlink pointing to
https://forecast.weather.gov/showsigwx.php?warnzone={zone}&warncounty={county}.
The trailing tally stays outside the span.

Task 2 (TestWeatherLinkDisabled, TestWeatherLinkNoUGC, TestWeatherLinkTallyOutside):
LINK-03 guarantee — no \\x1b]8 bytes when links=off or when no valid UGC/SAME exists.
Tally-outside-span boundary test (D-06).

Plan 09-04 updates:
- _make_alert_with_ugc extended with same_list kwarg (warncounty derivation)
- All URL assertions updated: api.weather.gov/alerts/active → showsigwx.php target
- test_no_same_no_link: omit-not-fake when valid Z UGC but no geocode.SAME
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

# OSC 8 escape sequences — compare as str (the module uses str throughout)
OSC8_OPEN  = "\x1b]8;;"       # ESC ] 8 ; ; (before URL)
OSC8_ST    = "\x1b\\"         # ST terminator
OSC8_CLOSE = "\x1b]8;;\x1b\\" # empty-URL close (terminates span)


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_alert_with_ugc(ugc_list, event="Tornado Warning", severity="Extreme",
                          extra_alerts=0, age_seconds=60,
                          same_list=None):
    """Build a cache dict with an active alert carrying geocode.UGC and optionally SAME.

    `same_list` defaults to ["040109"] (Oklahoma County FIPS → OKC109) for any call
    that omits the argument.  Pass same_list=[] explicitly to exercise the no-SAME
    omit-not-fake path.
    """
    if same_list is None:
        # Default: SAME for Oklahoma County (OKC109), matching OKZ034 zone fixture.
        same_list = ["040109"]
    now = time.time()
    future_expires = "2099-12-31T23:59:59Z"
    geocode: dict = {"UGC": ugc_list}
    if same_list:
        geocode["SAME"] = same_list
    props = {
        "id": "alert-001",
        "event": event,
        "severity": severity,
        "messageType": "Alert",
        "references": [],
        "sent": "2026-05-28T20:00:00Z",
        "expires": future_expires,
        "geocode": geocode,
    }
    # Extra alert geocode mirrors the primary's UGC and SAME
    extra_geocode: dict = {"UGC": ugc_list}
    if same_list:
        extra_geocode["SAME"] = same_list
    active = [{"id": "alert-001", "properties": props}]
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
                "geocode": extra_geocode,
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


def _run_segment(mod, cache_dict, cfg_override=None):
    """Call _weather_segment with monkeypatched read_cache and _WEATHER_OK=True."""
    tmpdir = tempfile.mkdtemp()
    try:
        cache_path = os.path.join(tmpdir, "cache.json")
        with open(cache_path, "w") as f:
            json.dump(cache_dict, f)

        def no_op_spawn(cfg, cache):
            pass

        cfg = {
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
            "display": {"icon_set": "emoji"},
        }
        if cfg_override:
            # Merge display sub-keys so the caller can set "links" without
            # clobbering "icon_set".
            merged = dict(cfg)
            for k, v in cfg_override.items():
                if k == "display" and isinstance(v, dict):
                    merged_display = dict(cfg.get("display", {}))
                    merged_display.update(v)
                    merged["display"] = merged_display
                else:
                    merged[k] = v
            cfg = merged

        with patch.object(mod, "_WEATHER_OK", True):
            with patch.object(mod, "_ASTRAL_OK", False):
                with patch.object(mod, "_CACHE_PATH", cache_path):
                    with patch.object(mod, "maybe_spawn_refresh", side_effect=no_op_spawn):
                        result = mod._weather_segment(None, cfg)
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Task 1: links enabled + valid UGC + SAME → OSC 8 link present (showsigwx target)
# ---------------------------------------------------------------------------

class TestWeatherLinkEnabled(unittest.TestCase):
    """With links=on and a valid Z UGC + SAME, the alert detail is wrapped in OSC 8
    pointing to forecast.weather.gov/showsigwx.php (human-readable NWS WWA page)."""

    def setUp(self):
        self.mod = _load_script_module()

    def _run_links_on(self, ugc_list, extra_alerts=0, same_list=None):
        cache = _make_alert_with_ugc(ugc_list, extra_alerts=extra_alerts,
                                     same_list=same_list)
        return _run_segment(self.mod, cache, cfg_override={"display": {"links": "on"}})

    def test_zone_ugc_link_present(self):
        """With links=on, geocode.UGC=['OKZ034'], SAME=['040109'] → showsigwx URL."""
        result = self._run_links_on(["OKZ034"])
        self.assertIsNotNone(result, "Segment must not be None")
        self.assertIn(
            "showsigwx.php?warnzone=OKZ034&warncounty=OKC109", result,
            f"Expected showsigwx URL in rendered segment; got: {result!r}"
        )
        self.assertIn(
            OSC8_OPEN + "https://forecast.weather.gov/showsigwx.php?warnzone=OKZ034&warncounty=OKC109",
            result,
            f"Expected OSC 8 open+URL in rendered segment; got: {result!r}"
        )

    def test_old_api_target_absent(self):
        """The old api.weather.gov/alerts/active URL must NOT appear in any rendered output."""
        result = self._run_links_on(["OKZ034"])
        self.assertIsNotNone(result)
        self.assertNotIn(
            "api.weather.gov/alerts/active", result,
            f"Old API target must not appear; got: {result!r}"
        )

    def test_county_fallback_ugc_link_present(self):
        """With only a county UGC (OKC109, no Z code) + SAME ['040109'], showsigwx uses county as warnzone."""
        # County UGC is the fallback warnzone when no Z code present;
        # warncounty still derived from SAME.
        result = self._run_links_on(["OKC109"])
        self.assertIsNotNone(result, "Segment must not be None")
        self.assertIn(
            "showsigwx.php?warnzone=OKC109&warncounty=OKC109", result,
            f"Expected showsigwx URL with county as warnzone; got: {result!r}"
        )

    def test_zone_preferred_over_county(self):
        """When UGC list has both Z and C codes, the Z (zone) code is used as warnzone."""
        result = self._run_links_on(["OKC109", "OKZ034"])
        self.assertIsNotNone(result, "Segment must not be None")
        # OKZ034 (zone) should be preferred over OKC109 (county) as warnzone
        self.assertIn("warnzone=OKZ034", result,
                      f"Zone code should be preferred; got: {result!r}")
        self.assertNotIn("warnzone=OKC109", result,
                         f"County code should not be warnzone when zone is present; got: {result!r}")

    def test_osc8_bytes_present_when_enabled(self):
        """OSC 8 escape bytes appear in output when links=on."""
        result = self._run_links_on(["OKZ034"])
        self.assertIsNotNone(result)
        self.assertIn(OSC8_OPEN, result,
                      f"OSC 8 open sequence must appear; got: {result!r}")
        self.assertIn(OSC8_CLOSE, result,
                      f"OSC 8 close sequence must appear; got: {result!r}")

    def test_no_valid_ugc_no_link(self):
        """When geocode.UGC has no valid code, no \\x1b]8 bytes appear."""
        # "XX9999" doesn't match Z or C pattern
        result = self._run_links_on(["XX9999"])
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No OSC 8 bytes should appear with invalid UGC; got: {result!r}")

    def test_no_same_no_link(self):
        """Valid Z UGC but NO geocode.SAME → zero \\x1b]8 bytes (omit-not-fake, D-10).

        warncounty is REQUIRED for showsigwx to list alerts; if it cannot be derived
        from SAME, build no link rather than a half/zone-only URL.
        """
        result = self._run_links_on(["OKZ034"], same_list=[])
        self.assertIsNotNone(result, "Segment must not be None")
        self.assertNotIn(OSC8_OPEN, result,
                         f"No OSC 8 bytes when SAME missing (omit-not-fake); got: {result!r}")
        self.assertNotIn("\x1b]8", result,
                         f"No OSC 8 escape bytes when SAME missing; got: {result!r}")

    def test_invalid_same_no_link(self):
        """Malformed SAME (not 6 digits) → zero \\x1b]8 bytes (D-10)."""
        result = self._run_links_on(["OKZ034"], same_list=["BAD"])
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No OSC 8 bytes with invalid SAME; got: {result!r}")

    def test_unknown_state_same_no_link(self):
        """SAME with unknown state FIPS (99) → zero \\x1b]8 bytes (D-10)."""
        result = self._run_links_on(["OKZ034"], same_list=["099037"])
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No OSC 8 bytes with unknown state FIPS; got: {result!r}")

    def test_tally_outside_link_span(self):
        """When a tally exists, it appears AFTER the OSC 8 close sequence (D-06)."""
        # 2 extra alerts → tally should appear outside the link
        result = self._run_links_on(["OKZ034"], extra_alerts=2)
        self.assertIsNotNone(result)
        # Confirm OSC 8 close is present
        self.assertIn(OSC8_CLOSE, result,
                      f"OSC 8 close must be present; got: {result!r}")
        # Find the OSC 8 close and confirm content (tally) follows it
        close_idx = result.index(OSC8_CLOSE)
        after_close = result[close_idx + len(OSC8_CLOSE):]
        self.assertTrue(len(after_close.strip()) > 0,
                        f"Tally must appear after OSC 8 close; after_close: {after_close!r}")


# ---------------------------------------------------------------------------
# Task 2: links disabled / no UGC → no OSC 8 bytes (LINK-03 guarantee)
# ---------------------------------------------------------------------------

class TestWeatherLinkDisabled(unittest.TestCase):
    """With links=off the rendered weather segment contains NO \\x1b]8 bytes."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_links_off_no_osc8_bytes(self):
        """With links=off, rendered segment has no OSC 8 escape bytes (LINK-03)."""
        # Provide SAME so we know the link *could* be built if links were on
        cache = _make_alert_with_ugc(["OKZ034"], same_list=["040109"])
        result = _run_segment(self.mod, cache,
                              cfg_override={"display": {"links": "off"}})
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No \\x1b]8 bytes when links=off; got: {result!r}")
        self.assertNotIn("\x1b]8", result,
                         f"No OSC 8 escape when links=off; got: {result!r}")

    def test_links_off_byte_identical_to_plain(self):
        """Output when links=off must be byte-identical to output with no display.links key."""
        # Provide SAME so the only difference between off/plain is the links setting
        cache = _make_alert_with_ugc(["OKZ034"], same_list=["040109"])
        result_off = _run_segment(self.mod, cache,
                                  cfg_override={"display": {"links": "off"}})
        # No links key at all (defaults to off)
        result_none = _run_segment(self.mod, cache)
        self.assertEqual(result_off, result_none,
                         "links=off and no links key must produce byte-identical output")

    def test_no_ugc_key_no_osc8_bytes(self):
        """With no geocode key in alert props, no \\x1b]8 bytes even with links=on."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72, "pop": 0},
            "alerts": {
                "fetched_at": now - 60,
                "active": [{
                    "id": "alert-001",
                    "properties": {
                        "id": "alert-001",
                        "event": "Tornado Warning",
                        "severity": "Extreme",
                        "messageType": "Alert",
                        "references": [],
                        "sent": "2026-05-28T20:00:00Z",
                        "expires": "2099-12-31T23:59:59Z",
                        # NO geocode key
                    }
                }]
            }
        }
        result = _run_segment(self.mod, cache,
                              cfg_override={"display": {"links": "on"}})
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No \\x1b]8 bytes when no UGC key; got: {result!r}")

    def test_invalid_ugc_no_osc8_bytes(self):
        """With geocode.UGC=['XX9999'] (no valid code), no \\x1b]8 bytes even with links=on."""
        cache = _make_alert_with_ugc(["XX9999"])
        result = _run_segment(self.mod, cache,
                              cfg_override={"display": {"links": "on"}})
        self.assertIsNotNone(result)
        self.assertNotIn(OSC8_OPEN, result,
                         f"No \\x1b]8 bytes with invalid UGC; got: {result!r}")

    def test_tally_appears_after_osc8_close(self):
        """With links=on + extra alerts, the tally index is after the OSC 8 close index."""
        cache = _make_alert_with_ugc(["OKZ034"], extra_alerts=2, same_list=["040109"])
        result = _run_segment(self.mod, cache,
                              cfg_override={"display": {"links": "on"}})
        self.assertIsNotNone(result)
        self.assertIn(OSC8_CLOSE, result,
                      f"OSC 8 close must appear; got: {result!r}")
        close_idx = result.index(OSC8_CLOSE)
        tail = result[close_idx + len(OSC8_CLOSE):]
        self.assertTrue(len(tail) > 0,
                        f"Expected content (tally) after OSC 8 close; tail: {tail!r}")


if __name__ == "__main__":
    unittest.main()
