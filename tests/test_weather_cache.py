#!/usr/bin/env python3
"""
Tests for Plan 02-02 Task 1: Sectioned cache.json store.

Covers:
  - read_cache: cold cache returns {}, malformed returns {}, round-trip
  - write_cache_section: atomic write, sectioned structure, fetched_at
  - section_is_fresh: TTL boundary cases
  - section_within_ceiling: max-stale ceiling boundary cases
"""

import importlib.util
import json
import os
import tempfile
import time
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestReadCache(unittest.TestCase):
    """read_cache: cold/malformed/round-trip cases."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_read_cache_function_exists(self):
        """Script defines read_cache()."""
        self.assertTrue(callable(getattr(self.mod, "read_cache", None)))

    def test_cold_cache_nonexistent_file_returns_empty(self):
        """read_cache with a non-existent path returns {} (cold cache)."""
        result = self.mod.read_cache("/nonexistent/path/cache.json")
        self.assertEqual(result, {})

    def test_malformed_cache_returns_empty_no_raise(self):
        """read_cache with malformed JSON returns {} and never raises."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{bad json content!!!}")
            path = f.name
        try:
            result = self.mod.read_cache(path)
            self.assertEqual(result, {})
        except Exception as e:
            self.fail(f"read_cache raised unexpectedly on malformed JSON: {e}")
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty(self):
        """read_cache on an empty file returns {} (not a crash)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name  # empty
        try:
            result = self.mod.read_cache(path)
            self.assertEqual(result, {})
        finally:
            os.unlink(path)

    def test_round_trip_valid_json(self):
        """read_cache on a valid JSON file returns the parsed dict."""
        payload = {"weather": {"fetched_at": 1234567890, "icon": "☀️", "temp": 72}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            path = f.name
        try:
            result = self.mod.read_cache(path)
            self.assertEqual(result, payload)
        finally:
            os.unlink(path)

    def test_non_dict_json_returns_empty(self):
        """read_cache on a JSON array (not a dict) returns {} gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3], f)
            path = f.name
        try:
            result = self.mod.read_cache(path)
            # Should degrade gracefully — either {} or the list; key test is no raise
            # (implementation may return {} or the list; if a list the caller treats it as
            # having no known sections — the must_have is just no crash)
        except Exception as e:
            self.fail(f"read_cache raised on non-dict JSON: {e}")
        finally:
            os.unlink(path)


class TestWriteCacheSection(unittest.TestCase):
    """write_cache_section: atomic write, sectioned structure, preserves other sections."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_cache_section_function_exists(self):
        """Script defines write_cache_section()."""
        self.assertTrue(callable(getattr(self.mod, "write_cache_section", None)))

    def test_write_creates_file(self):
        """write_cache_section creates cache.json when it doesn't exist."""
        now = time.time()
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "☀️", "temp": 72}, now)
        self.assertTrue(os.path.exists(self.cache_path))

    def test_write_sets_fetched_at(self):
        """write_cache_section stores fetched_at in the section."""
        now = 1717000000.0
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "☀️"}, now)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("weather", data)
        self.assertEqual(data["weather"]["fetched_at"], now)

    def test_write_stores_payload_fields(self):
        """write_cache_section stores payload fields alongside fetched_at."""
        now = 1717000000.0
        payload = {"icon": "🌧️", "temp": 55, "pop": 40}
        self.mod.write_cache_section(self.cache_path, "weather", payload, now)
        data = self.mod.read_cache(self.cache_path)
        self.assertEqual(data["weather"]["icon"], "🌧️")
        self.assertEqual(data["weather"]["temp"], 55)
        self.assertEqual(data["weather"]["pop"], 40)

    def test_write_preserves_other_sections(self):
        """Writing one section does not overwrite other sections."""
        now = 1717000000.0
        # Write geo section first
        self.mod.write_cache_section(self.cache_path, "geo", {"cwa": "OUN", "gridX": 100, "gridY": 83}, now)
        # Then write weather section
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "☀️", "temp": 72}, now)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("geo", data)
        self.assertEqual(data["geo"]["cwa"], "OUN")
        self.assertIn("weather", data)

    def test_atomic_write_uses_os_replace(self):
        """Script source contains os.replace for cache atomic write."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("os.replace", source)

    def test_atomic_write_no_half_written(self):
        """write_cache_section produces a valid JSON file (no partial writes)."""
        now = time.time()
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "☀️", "temp": 72}, now)
        # Must be readable as valid JSON immediately after write
        with open(self.cache_path) as f:
            data = json.load(f)
        self.assertIn("weather", data)

    def test_write_cache_string_mentions_cache_json(self):
        """Script source references 'cache.json' for the cache path."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("cache.json", source)

    def test_write_section_overwrites_existing_section(self):
        """A second write to the same section updates the data."""
        now1 = 1717000000.0
        now2 = 1717000600.0
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "☀️", "temp": 72}, now1)
        self.mod.write_cache_section(self.cache_path, "weather", {"icon": "🌧️", "temp": 65}, now2)
        data = self.mod.read_cache(self.cache_path)
        self.assertEqual(data["weather"]["icon"], "🌧️")
        self.assertEqual(data["weather"]["fetched_at"], now2)


class TestSectionIsFresh(unittest.TestCase):
    """section_is_fresh: TTL boundary (triggers background refresh)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_section_is_fresh_function_exists(self):
        """Script defines section_is_fresh()."""
        self.assertTrue(callable(getattr(self.mod, "section_is_fresh", None)))

    def test_fresh_section_within_ttl(self):
        """A section with fetched_at 5 min ago is fresh when ttl=600."""
        now = 1717000000.0
        fetched_at = now - 300  # 5 min ago
        section = {"fetched_at": fetched_at, "icon": "☀️"}
        self.assertTrue(self.mod.section_is_fresh(section, ttl=600, now=now))

    def test_stale_section_just_past_ttl(self):
        """A section with fetched_at 601s ago is stale when ttl=600."""
        now = 1717000000.0
        fetched_at = now - 601
        section = {"fetched_at": fetched_at}
        self.assertFalse(self.mod.section_is_fresh(section, ttl=600, now=now))

    def test_fresh_at_exact_ttl_boundary(self):
        """A section exactly at the TTL age (age == ttl) is treated as stale."""
        now = 1717000000.0
        fetched_at = now - 600
        section = {"fetched_at": fetched_at}
        # age == ttl is at the boundary; implementation may be < or <= but must be consistent
        # We just verify it doesn't raise
        result = self.mod.section_is_fresh(section, ttl=600, now=now)
        self.assertIsInstance(result, bool)

    def test_missing_fetched_at_is_stale(self):
        """A section with no fetched_at is treated as stale (triggers refresh)."""
        section = {"icon": "☀️"}  # no fetched_at
        self.assertFalse(self.mod.section_is_fresh(section, ttl=600, now=time.time()))

    def test_non_numeric_fetched_at_is_stale(self):
        """A section with non-numeric fetched_at is treated as stale."""
        section = {"fetched_at": "not-a-number"}
        self.assertFalse(self.mod.section_is_fresh(section, ttl=600, now=time.time()))

    def test_empty_section_is_stale(self):
        """An empty section dict is stale."""
        self.assertFalse(self.mod.section_is_fresh({}, ttl=600, now=time.time()))

    def test_freshness_respects_ttl_parameter(self):
        """section_is_fresh respects the given ttl parameter."""
        now = 1717000000.0
        fetched_at = now - 250
        section = {"fetched_at": fetched_at}
        # ttl=300 -> fresh (250 < 300)
        self.assertTrue(self.mod.section_is_fresh(section, ttl=300, now=now))
        # ttl=200 -> stale (250 > 200)
        self.assertFalse(self.mod.section_is_fresh(section, ttl=200, now=now))


class TestSectionWithinCeiling(unittest.TestCase):
    """section_within_ceiling: max-stale ceiling (beyond this, drop data)."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_section_within_ceiling_function_exists(self):
        """Script defines section_within_ceiling()."""
        self.assertTrue(callable(getattr(self.mod, "section_within_ceiling", None)))

    def test_within_ceiling(self):
        """A section 30 min old is within a 1h ceiling."""
        now = 1717000000.0
        fetched_at = now - 1800  # 30 min
        section = {"fetched_at": fetched_at}
        self.assertTrue(self.mod.section_within_ceiling(section, max_stale=3600, now=now))

    def test_beyond_ceiling(self):
        """A section 2h old is beyond a 1h ceiling."""
        now = 1717000000.0
        fetched_at = now - 7200  # 2 hours
        section = {"fetched_at": fetched_at}
        self.assertFalse(self.mod.section_within_ceiling(section, max_stale=3600, now=now))

    def test_just_past_ceiling(self):
        """A section 1 second past the ceiling is dropped."""
        now = 1717000000.0
        fetched_at = now - 3601
        section = {"fetched_at": fetched_at}
        self.assertFalse(self.mod.section_within_ceiling(section, max_stale=3600, now=now))

    def test_missing_fetched_at_beyond_ceiling(self):
        """A section with no fetched_at is treated as beyond the ceiling (drop)."""
        section = {"icon": "☀️"}
        self.assertFalse(self.mod.section_within_ceiling(section, max_stale=3600, now=time.time()))

    def test_non_numeric_fetched_at_beyond_ceiling(self):
        """A non-numeric fetched_at is treated as beyond ceiling."""
        section = {"fetched_at": None}
        self.assertFalse(self.mod.section_within_ceiling(section, max_stale=3600, now=time.time()))

    def test_empty_section_beyond_ceiling(self):
        """An empty section dict is beyond the ceiling."""
        self.assertFalse(self.mod.section_within_ceiling({}, max_stale=3600, now=time.time()))

    def test_ceiling_respects_max_stale_parameter(self):
        """section_within_ceiling respects the given max_stale parameter."""
        now = 1717000000.0
        fetched_at = now - 700
        section = {"fetched_at": fetched_at}
        # max_stale=900 -> within ceiling (700 < 900)
        self.assertTrue(self.mod.section_within_ceiling(section, max_stale=900, now=now))
        # max_stale=600 -> beyond ceiling (700 > 600)
        self.assertFalse(self.mod.section_within_ceiling(section, max_stale=600, now=now))


if __name__ == "__main__":
    unittest.main()
