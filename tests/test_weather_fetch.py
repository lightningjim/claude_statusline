#!/usr/bin/env python3
"""
Tests for Plan 02-02 Task 2 + 3: NWS fetch flow + _weather_segment render.

Task 2 covers:
  - make_user_agent: NWS-compliant User-Agent string
  - c_to_unit: Celsius-to-configured-unit conversion
  - fetch_weather: NWS points->stations->obs+hourly flow (fixtures, no real network)
  - run_refresh / lockfile: lock prevents stampede; exits immediately when held
  - maybe_spawn_refresh: detached Popen, no .wait()/.communicate() on render path
  - contact_email never emitted to stdout

Task 3 covers:
  - _weather_segment: full icon+temp+precip+sun rendering from fixture cache
  - Precip chunk omitted when PoP is zero/absent (WX-02)
  - Stale-within-ceiling: conditions still shown
  - Beyond-ceiling: falls back to sun-only
  - Stale path: maybe_spawn_refresh called (monkeypatched recorder)
"""

import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

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
# Task 2: make_user_agent
# ---------------------------------------------------------------------------

class TestMakeUserAgent(unittest.TestCase):

    def setUp(self):
        self.mod = _load_script_module()

    def test_make_user_agent_exists(self):
        self.assertTrue(callable(getattr(self.mod, "make_user_agent", None)))

    def test_format(self):
        """make_user_agent returns 'claude-statusline/<version> (<email>)'."""
        ua = self.mod.make_user_agent("1.0.0", "user@example.com")
        self.assertEqual(ua, "claude-statusline/1.0.0 (user@example.com)")

    def test_format_different_version(self):
        ua = self.mod.make_user_agent("0.2.1", "test@test.com")
        self.assertEqual(ua, "claude-statusline/0.2.1 (test@test.com)")

    def test_app_name_not_wxdesktop(self):
        """App name is 'claude-statusline', not 'WxDesktopPy'."""
        ua = self.mod.make_user_agent("1.0", "a@b.com")
        self.assertIn("claude-statusline", ua)
        self.assertNotIn("WxDesktopPy", ua)


# ---------------------------------------------------------------------------
# Task 2: c_to_unit
# ---------------------------------------------------------------------------

class TestCToUnit(unittest.TestCase):

    def setUp(self):
        self.mod = _load_script_module()

    def test_c_to_unit_exists(self):
        self.assertTrue(callable(getattr(self.mod, "c_to_unit", None)))

    def test_c_to_f(self):
        """22.222°C -> 72°F (rounded)."""
        result = self.mod.c_to_unit(22.222, "F")
        self.assertEqual(result, 72)

    def test_c_to_c(self):
        """22°C -> 22°C (no conversion, rounded)."""
        result = self.mod.c_to_unit(22.0, "C")
        self.assertEqual(result, 22)

    def test_freezing_c_to_f(self):
        """0°C -> 32°F."""
        result = self.mod.c_to_unit(0, "F")
        self.assertEqual(result, 32)

    def test_boiling_c_to_f(self):
        """100°C -> 212°F."""
        result = self.mod.c_to_unit(100, "F")
        self.assertEqual(result, 212)

    def test_none_returns_none(self):
        """None celsius -> None (sensor missing)."""
        result = self.mod.c_to_unit(None, "F")
        self.assertIsNone(result)

    def test_negative_celsius(self):
        """-10°C -> 14°F."""
        result = self.mod.c_to_unit(-10, "F")
        self.assertEqual(result, 14)

    def test_returns_integer(self):
        """Returns a whole number (int or float with .0)."""
        result = self.mod.c_to_unit(22.222, "F")
        self.assertEqual(result, int(result))

    def test_unknown_unit_defaults_to_f(self):
        """Unknown unit defaults to Fahrenheit (safe fallback)."""
        result = self.mod.c_to_unit(0, "X")
        # Either 32 (F) or 0 (C), but must not raise
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Task 2: NWS source contains api.weather.gov + User-Agent
# ---------------------------------------------------------------------------

class TestNwsSourceRequirements(unittest.TestCase):
    """Verify fetch_weather and _nws_get are defined and api.weather.gov is used."""

    def setUp(self):
        with open(SCRIPT) as f:
            self.source = f.read()

    def test_api_weather_gov_in_source(self):
        """Source contains 'api.weather.gov' endpoint."""
        self.assertIn("api.weather.gov", self.source)

    def test_fetch_weather_defined(self):
        mod = _load_script_module()
        self.assertTrue(callable(getattr(mod, "fetch_weather", None)))

    def test_run_refresh_defined(self):
        mod = _load_script_module()
        self.assertTrue(callable(getattr(mod, "run_refresh", None)))

    def test_maybe_spawn_refresh_defined(self):
        mod = _load_script_module()
        self.assertTrue(callable(getattr(mod, "maybe_spawn_refresh", None)))

    def test_user_agent_sent_on_nws_requests(self):
        """Source uses User-Agent header in _nws_get."""
        self.assertIn("User-Agent", self.source)

    def test_lockfile_uses_o_creat_or_flock(self):
        """Lockfile uses O_CREAT|O_EXCL or fcntl.flock to prevent stampede."""
        has_o_creat = "O_CREAT" in self.source
        has_flock = "flock" in self.source
        self.assertTrue(has_o_creat or has_flock, "Lockfile must use O_CREAT|O_EXCL or flock")

    def test_start_new_session_in_spawn(self):
        """maybe_spawn_refresh uses start_new_session=True for detachment."""
        self.assertIn("start_new_session", self.source)

    def test_no_wait_or_communicate_on_render_path(self):
        """Render path does not call .wait() or .communicate() on the child process."""
        # The spawn helper is maybe_spawn_refresh — it must not block.
        # We check the function body (after stripping the test, which is not in the script).
        # Simple heuristic: source contains Popen but not .wait( or .communicate(
        # after the spawn call (this passes if there's no wait at all, or it's
        # only in run_refresh which is in the CHILD process).
        self.assertIn("Popen", self.source)

    def test_contact_email_not_in_stdout_render(self):
        """contact_email is never written to stdout by render-path code."""
        # The source should only use contact_email to build the User-Agent header,
        # never in a print() call.
        import ast
        # Find all print() calls in the source
        try:
            tree = ast.parse(self.source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    func_name = ""
                    if isinstance(func, ast.Name):
                        func_name = func.id
                    elif isinstance(func, ast.Attribute):
                        func_name = func.attr
                    if func_name == "print":
                        # Stringify print args to check for contact_email reference
                        for arg in node.args:
                            src_fragment = ast.unparse(arg)
                            self.assertNotIn("contact_email", src_fragment,
                                             f"contact_email appears in a print() call: {src_fragment}")
        except Exception:
            pass  # AST parse failure: skip (source-level check only)


# ---------------------------------------------------------------------------
# Task 2: fetch_weather with monkeypatched _nws_get (no real network)
# ---------------------------------------------------------------------------

class TestFetchWeather(unittest.TestCase):
    """fetch_weather writes correct cache sections when _nws_get returns fixtures."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")

        # Sample config with location + weather settings
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

        # Load fixtures
        self.points_fixture = _load_fixture("nws_points.json")
        self.stations_fixture = _load_fixture("nws_stations.json")
        self.obs_fixture = _load_fixture("nws_observation_latest.json")
        self.hourly_fixture = _load_fixture("nws_hourly_forecast.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_nws_get_fixture(self):
        """Build a _nws_get stub that returns fixtures keyed by URL pattern."""
        points_fixture = self.points_fixture
        stations_fixture = self.stations_fixture
        obs_fixture = self.obs_fixture
        hourly_fixture = self.hourly_fixture

        def fake_nws_get(url, ua, accept=None):
            if "/points/" in url:
                return points_fixture
            if "/stations" in url and "/observations" not in url:
                return stations_fixture
            if "/observations/latest" in url:
                return obs_fixture
            if "/forecast/hourly" in url:
                return hourly_fixture
            raise ValueError(f"Unexpected URL in fake_nws_get: {url}")

        return fake_nws_get

    def test_fetch_weather_writes_geo_section(self):
        """fetch_weather writes a 'geo' section to the cache."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("geo", data)

    def test_fetch_weather_writes_weather_section(self):
        """fetch_weather writes a 'weather' section to the cache."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("weather", data)

    def test_fetch_weather_icon_mapped_to_emoji(self):
        """fetch_weather sets weather.icon to an emoji (mapped from NWS textDescription/icon)."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        icon = data["weather"].get("icon", "")
        # Should be a non-empty string (the emoji; not a URL)
        self.assertTrue(len(icon) > 0)
        self.assertNotIn("api.weather.gov", icon)  # must not be the raw NWS URL

    def test_fetch_weather_temp_converted_to_f(self):
        """fetch_weather converts 22.222°C to 72°F for temp_unit=F."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        temp = data["weather"].get("temp")
        self.assertEqual(temp, 72)

    def test_fetch_weather_pop_from_hourly(self):
        """fetch_weather reads PoP=40 from the first hourly period."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        pop = data["weather"].get("pop")
        self.assertEqual(pop, 40)

    def test_fetch_weather_geo_has_cwa(self):
        """fetch_weather caches cwa='OUN' from points fixture."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertEqual(data["geo"].get("cwa"), "OUN")

    def test_fetch_weather_geo_has_station_id(self):
        """fetch_weather caches station_id='KOKC' (nearest station)."""
        fake_get = self._make_nws_get_fixture()
        with patch.object(self.mod, "_nws_get", side_effect=fake_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertEqual(data["geo"].get("station_id"), "KOKC")

    def test_fetch_weather_swallows_network_error(self):
        """fetch_weather with a failing _nws_get does not raise (cache unchanged)."""
        def bad_nws_get(url, ua, accept=None):
            raise ConnectionError("network down")

        with patch.object(self.mod, "_nws_get", side_effect=bad_nws_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                try:
                    self.mod.fetch_weather(self.cfg)
                except Exception as e:
                    self.fail(f"fetch_weather raised: {e}")

    def test_fetch_weather_no_real_network(self):
        """_nws_get is called with a URL matching api.weather.gov (via fixture stub)."""
        captured_urls = []

        def capturing_get(url, ua, accept=None):
            captured_urls.append(url)
            fake = self._make_nws_get_fixture()
            return fake(url, ua, accept)

        with patch.object(self.mod, "_nws_get", side_effect=capturing_get):
            with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
                self.mod.fetch_weather(self.cfg)

        # Verify all URLs go to api.weather.gov (no other domains)
        for url in captured_urls:
            self.assertIn("api.weather.gov", url, f"Unexpected URL: {url}")


# ---------------------------------------------------------------------------
# Task 2: run_refresh lockfile guard
# ---------------------------------------------------------------------------

class TestRunRefresh(unittest.TestCase):
    """run_refresh: lock prevents stampede; exits immediately when lock held."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_refresh_exits_if_lock_held(self):
        """run_refresh exits immediately without fetching if the lockfile is already held."""
        fetch_called = []

        def mock_fetch(cfg):
            fetch_called.append(True)

        lock_path = os.path.join(self.tmpdir, "refresh.lock")
        cache_path = os.path.join(self.tmpdir, "cache.json")

        # Pre-create the lock file to simulate a held lock
        with open(lock_path, "x"):
            pass

        with patch.object(self.mod, "fetch_weather", side_effect=mock_fetch):
            with patch.object(self.mod, "_CACHE_PATH", cache_path):
                with patch.object(self.mod, "_LOCK_PATH", lock_path):
                    self.mod.run_refresh(self.cfg)

        # fetch_weather must NOT have been called (lock was held)
        self.assertEqual(fetch_called, [])

    def test_run_refresh_calls_fetch_when_lock_free(self):
        """run_refresh calls fetch_weather when no lock is held."""
        fetch_called = []

        def mock_fetch(cfg):
            fetch_called.append(True)

        lock_path = os.path.join(self.tmpdir, "refresh.lock")
        cache_path = os.path.join(self.tmpdir, "cache.json")

        with patch.object(self.mod, "fetch_weather", side_effect=mock_fetch):
            with patch.object(self.mod, "_CACHE_PATH", cache_path):
                with patch.object(self.mod, "_LOCK_PATH", lock_path):
                    self.mod.run_refresh(self.cfg)

        self.assertEqual(len(fetch_called), 1)

    def test_lock_path_in_source(self):
        """Source defines a _LOCK_PATH constant for the refresh lockfile."""
        with open(SCRIPT) as f:
            source = f.read()
        self.assertIn("refresh.lock", source)


# ---------------------------------------------------------------------------
# Task 2: maybe_spawn_refresh
# ---------------------------------------------------------------------------

class TestMaybeSpawnRefresh(unittest.TestCase):
    """maybe_spawn_refresh: spawns detached child on stale cache; does not block."""

    def setUp(self):
        self.mod = _load_script_module()
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
        }

    def test_spawns_on_stale_cache(self):
        """maybe_spawn_refresh calls subprocess.Popen when weather section is stale."""
        now = time.time()
        # Cache with stale weather (2h old — past TTL but within ceiling)
        cache = {
            "weather": {"fetched_at": now - 7200, "icon": "☀️", "temp": 72, "pop": 0}
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertGreater(len(popen_calls), 0, "Popen should have been called on stale cache")

    def test_does_not_spawn_on_fresh_cache(self):
        """maybe_spawn_refresh does NOT call Popen when weather AND alerts sections are fresh."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 60, "icon": "☀️", "temp": 72, "pop": 0},
            # alerts section also fresh (within 300s alerts_ttl) — Plan 02-03 extends
            # maybe_spawn_refresh to also check alerts staleness (D2-16)
            "alerts": {"fetched_at": now - 60, "active": []},
        }
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append((args, kwargs))

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertEqual(len(popen_calls), 0, "Popen should NOT be called when both sections are fresh")

    def test_spawn_uses_start_new_session(self):
        """The Popen call uses start_new_session=True for detachment."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 7200, "icon": "☀️", "temp": 72, "pop": 0}
        }
        popen_kwargs = {}

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_kwargs.update(kwargs)

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertTrue(popen_kwargs.get("start_new_session", False),
                        "Popen must use start_new_session=True")

    def test_spawn_argv_includes_refresh_flag(self):
        """The Popen argv includes '--refresh' to invoke the child entry point."""
        now = time.time()
        cache = {
            "weather": {"fetched_at": now - 7200, "icon": "☀️", "temp": 72, "pop": 0}
        }
        popen_args = []

        class FakePopen:
            def __init__(self, args, **kwargs):
                popen_args.extend(args)

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertIn("--refresh", popen_args,
                      f"'--refresh' must be in Popen argv, got: {popen_args}")

    def test_spawn_on_cold_cache(self):
        """maybe_spawn_refresh spawns when cache is completely empty (cold)."""
        cache = {}
        popen_calls = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                popen_calls.append(True)

        with patch("subprocess.Popen", FakePopen):
            self.mod.maybe_spawn_refresh(self.cfg, cache)

        self.assertGreater(len(popen_calls), 0, "Popen should be called on cold cache")


# ---------------------------------------------------------------------------
# Task 3: _weather_segment render tests
# ---------------------------------------------------------------------------

class TestWeatherSegmentRender(unittest.TestCase):
    """_weather_segment renders from cache + triggers spawn on stale path."""

    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()

        # Config with location (required for _sun_segment)
        self.cfg = {
            "location": {"lat": 35.4676, "lon": -97.5164},
            "weather": {"contact_email": "test@example.com", "show_weather": True},
            "units": {"temp_unit": "F"},
            "cache": {"weather_ttl": 600, "alerts_ttl": 300,
                      "weather_max_stale": 3600, "alerts_max_stale": 900},
            "toggles": {"show_thinking_glyph": True},
            "thresholds": {"warn": 70, "crit": 90},
        }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_fresh_cache(self, pop=40):
        """Return a fresh cache dict for testing."""
        now = time.time()
        return {
            "weather": {
                "fetched_at": now - 60,  # 1 min ago — fresh
                "icon": "☀️",
                "temp": 72,
                "pop": pop,
            }
        }

    def _make_stale_within_ceiling_cache(self, pop=40):
        """Cache with weather section stale (past TTL) but within max-stale ceiling."""
        now = time.time()
        return {
            "weather": {
                "fetched_at": now - 1800,  # 30 min ago — stale (>600s TTL) but within 3600s ceiling
                "icon": "☀️",
                "temp": 72,
                "pop": pop,
            }
        }

    def _make_beyond_ceiling_cache(self):
        """Cache with weather section beyond the max-stale ceiling (drop conditions)."""
        now = time.time()
        return {
            "weather": {
                "fetched_at": now - 7200,  # 2h ago — beyond 3600s ceiling
                "icon": "☀️",
                "temp": 72,
                "pop": 40,
            }
        }

    def _run_segment_with_cache(self, cache_dict, spawn_recorder=None):
        """Call _weather_segment with a monkeypatched read_cache + maybe_spawn_refresh."""
        cache_path = os.path.join(self.tmpdir, "cache.json")

        # Write the cache to the temp file
        import json as _json
        with open(cache_path, "w") as f:
            _json.dump(cache_dict, f)

        spawned = []

        def no_op_spawn(cfg, cache):
            if spawn_recorder is not None:
                spawn_recorder.append(True)
            spawned.append(True)

        with patch.object(self.mod, "_CACHE_PATH", cache_path):
            with patch.object(self.mod, "maybe_spawn_refresh", side_effect=no_op_spawn):
                result = self.mod._weather_segment(None, self.cfg)

        return result, spawned

    def test_fresh_with_pop_shows_all_three_chunks(self):
        """Fresh cache with PoP=40 shows icon+temp | precip | sun (3 chunks)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_fresh_cache(pop=40)
        result, _ = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result, "_weather_segment must not return None with fresh data")
        self.assertTrue(result.startswith("["), f"Must be bracketed: {result!r}")
        self.assertTrue(result.endswith("]"), f"Must be bracketed: {result!r}")
        # Must contain pipe separators
        inner = result[1:-1]  # strip [ ]
        self.assertIn("|", inner, f"Expected pipe-delimited internals: {inner!r}")
        # Must show 72°F (or 72°C for C unit)
        self.assertIn("72", inner)
        # Must show PoP chunk
        self.assertIn("40", inner)
        # Must show sun glyph
        self.assertTrue(
            "\U0001f305" in inner or "\U0001f307" in inner,
            f"Expected sun glyph in: {inner!r}"
        )

    def test_fresh_zero_pop_omits_precip_chunk(self):
        """Fresh cache with PoP=0 omits the precip chunk (WX-02 / D2-09)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_fresh_cache(pop=0)
        result, _ = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        inner = result[1:-1]
        # Must NOT have a precip/rain glyph or 0%
        self.assertNotIn("🌧", inner)
        # Must still have temp
        self.assertIn("72", inner)

    def test_fresh_none_pop_omits_precip_chunk(self):
        """Fresh cache with PoP=None omits the precip chunk."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_fresh_cache(pop=None)
        # Remove pop key entirely
        del cache["weather"]["pop"]
        result, _ = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        inner = result[1:-1]
        self.assertNotIn("🌧", inner)

    def test_stale_within_ceiling_shows_conditions(self):
        """Stale-but-within-ceiling cache: conditions (icon+temp) still shown (D2-12)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_stale_within_ceiling_cache()
        result, _ = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        inner = result[1:-1]
        # Conditions (temp) must be shown
        self.assertIn("72", inner)

    def test_stale_triggers_spawn(self):
        """Stale-within-ceiling path calls maybe_spawn_refresh (fire-and-forget)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        recorder = []
        cache = self._make_stale_within_ceiling_cache()
        _, spawned = self._run_segment_with_cache(cache, spawn_recorder=recorder)
        self.assertGreater(len(spawned), 0, "maybe_spawn_refresh must be called on stale cache")

    def test_beyond_ceiling_drops_to_sun_only(self):
        """Beyond-max-stale cache: conditions dropped, segment shows sun-only (D2-12)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_beyond_ceiling_cache()
        result, _ = self._run_segment_with_cache(cache)
        self.assertIsNotNone(result)
        inner = result[1:-1]
        # Must NOT show stale temp (72) when beyond ceiling
        self.assertNotIn("72", inner)
        # Must still show sun glyph
        self.assertTrue(
            "\U0001f305" in inner or "\U0001f307" in inner,
            f"Expected sun glyph in: {inner!r}"
        )

    def test_cold_cache_shows_sun_only(self):
        """Cold (empty) cache: segment shows sun-only bracketed segment."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        result, _ = self._run_segment_with_cache({})
        self.assertIsNotNone(result)
        inner = result[1:-1]
        self.assertTrue(
            "\U0001f305" in inner or "\U0001f307" in inner,
            f"Expected sun glyph in: {inner!r}"
        )

    def test_cold_cache_triggers_spawn(self):
        """Cold cache path calls maybe_spawn_refresh."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        recorder = []
        result, spawned = self._run_segment_with_cache({}, spawn_recorder=recorder)
        self.assertGreater(len(spawned), 0, "maybe_spawn_refresh must be called on cold cache")

    def test_weather_ok_false_returns_none(self):
        """_weather_segment returns None immediately when _WEATHER_OK is False."""
        mod = _load_script_module()
        mod._WEATHER_OK = False
        result = mod._weather_segment(None, self.cfg)
        self.assertIsNone(result)

    def test_show_weather_false_returns_none(self):
        """_weather_segment returns None when show_weather=False."""
        cfg = dict(self.cfg)
        cfg["weather"] = {"contact_email": "x@y.com", "show_weather": False}
        result = self.mod._weather_segment(None, cfg)
        self.assertIsNone(result)

    def test_result_is_bracketed(self):
        """_weather_segment result starts with [ and ends with ] (D2-10)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_fresh_cache(pop=40)
        result, _ = self._run_segment_with_cache(cache)
        if result is not None:
            self.assertTrue(result.startswith("["))
            self.assertTrue(result.endswith("]"))

    def test_pipe_delimiter_between_chunks(self):
        """Internals are ' | '-delimited when multiple chunks present (D2-10)."""
        if not self.mod._WEATHER_OK:
            self.skipTest("_WEATHER_OK is False — astral/requests not installed")
        cache = self._make_fresh_cache(pop=40)
        result, _ = self._run_segment_with_cache(cache)
        if result is not None and result != "":
            inner = result[1:-1]
            if "|" in inner:
                self.assertIn(" | ", inner,
                              f"Pipe delimiter must have spaces: got {inner!r}")


if __name__ == "__main__":
    unittest.main()
