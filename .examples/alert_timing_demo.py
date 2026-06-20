#!/usr/bin/env python3
"""Phase 8 (Alert Timing) UAT demo — renders the weather segment for several
alert-timing scenarios using a TEMPORARY cache, so your real
~/.claude/claude-statusline/cache.json is never touched.

Run with the venv interpreter so astral/requests resolve (otherwise the weather
segment is omitted by design):

    ~/.claude/claude-statusline/.venv/bin/python .examples/alert_timing_demo.py

For each scenario it prints:
  • the rendered line WITH ANSI color (what you see on the bar)
  • the raw repr() (so escape codes / the middot are unambiguous)
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import patch

# Load the statusline module + the test factory the integration tests use.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from test_weather_alerts import _load_script_module, _make_alert  # noqa: E402

mod = _load_script_module()

CFG = {
    "location": {"lat": 35.4676, "lon": -97.5164},
    "weather": {"contact_email": "demo@example.com", "show_weather": True},
    "units": {"temp_unit": "F"},
    "cache": {"weather_ttl": 600, "alerts_ttl": 300,
              "weather_max_stale": 3600, "alerts_max_stale": 900},
    "display": {"icon_set": "nerd"},   # change to "emoji" to preview the emoji set
}


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def timed_alert(ident, event, severity, vtec, onset=None, ends=None,
                effective=None, expires="2099-12-31T23:59:59Z"):
    a = _make_alert(ident, event, severity, expires=expires, vtec=[vtec])
    p = a["properties"]
    if onset is not None:
        p["onset"] = onset
    if effective is not None:
        p["effective"] = effective
    if ends is not None:
        p["ends"] = ends
    return a


def render(alerts):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "cache.json")
        now = time.time()
        with open(path, "w") as f:
            json.dump({
                "weather": {"fetched_at": now - 60, "text_desc": "Sunny",
                            "icon_url": "https://api.weather.gov/icons/land/day/skc",
                            "temp": 72, "pop": 0},
                "alerts": {"fetched_at": now - 60, "active": alerts},
            }, f)
        with patch.object(mod, "_CACHE_PATH", path), \
             patch.object(mod, "maybe_spawn_refresh", lambda c, k: None):
            return mod._weather_segment(None, CFG)


def show(title, alerts):
    out = render(alerts)
    print(f"\n\033[1m{title}\033[0m")
    print(f"  rendered : {out}")
    print(f"  raw repr : {out!r}")


def main():
    if not mod._WEATHER_OK:
        print("astral/requests not importable — run with the venv python:")
        print("  ~/.claude/claude-statusline/.venv/bin/python "
              ".examples/alert_timing_demo.py")
        return
    now = datetime.now().astimezone()
    h = lambda n: _iso(now + timedelta(hours=n))   # noqa: E731
    d = lambda n: _iso(now + timedelta(days=n))     # noqa: E731

    show("1. ACTIVE — ends in 3h today  → expect '· until <time>' (class-colored)",
         [timed_alert("a1", "Tornado Warning", "Extreme",
                      "/O.NEW.KTLX.TO.W.0001.000000T0000Z-000000T0000Z/",
                      onset=h(-1), ends=h(3))])

    show("2. UPCOMING — onset in 6h      → expect '· from <time>'",
         [timed_alert("a2", "Winter Storm Warning", "Severe",
                      "/O.NEW.KTLX.WS.W.0001.000000T0000Z-000000T0000Z/",
                      onset=h(6), ends=h(12))])

    show("3. UPCOMING far-out — onset +8 days → expect dated '· from <Mon> <D> at <time>'",
         [timed_alert("a3", "Winter Storm Watch", "Moderate",
                      "/O.NEW.KTLX.WS.A.0001.000000T0000Z-000000T0000Z/",
                      onset=d(8), ends=d(8))])

    show("4. EXPIRED-but-cached — ends 2h ago (CR-01 fix) → expect EVENT with NO timing",
         [timed_alert("a4", "Flood Advisory", "Minor",
                      "/O.NEW.KTLX.FA.Y.0001.000000T0000Z-000000T0000Z/",
                      onset=h(-5), ends=h(-2))])

    show("5. PRIMARY + tally — active warning + 2 others → timing on primary only",
         [timed_alert("a5", "Tornado Warning", "Extreme",
                      "/O.NEW.KTLX.TO.W.0002.000000T0000Z-000000T0000Z/",
                      onset=h(-1), ends=h(2)),
          timed_alert("a6", "Flood Watch", "Moderate",
                      "/O.NEW.KTLX.FA.A.0002.000000T0000Z-000000T0000Z/",
                      onset=h(-1), ends=h(5)),
          timed_alert("a7", "Wind Advisory", "Minor",
                      "/O.NEW.KTLX.WI.Y.0002.000000T0000Z-000000T0000Z/",
                      onset=h(-1), ends=h(6))])

    print("\n(Times shown are relative to your local clock right now.)")


if __name__ == "__main__":
    main()
