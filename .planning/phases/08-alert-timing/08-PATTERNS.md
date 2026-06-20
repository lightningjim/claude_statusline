# Phase 8: Alert Timing - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 2 (1 new function + 1 integration site in `claude-statusline.py`; 1 test class in `tests/test_weather_alerts.py`)
**Analogs found:** 4 / 4

---

## File Classification

| New/Modified Unit | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `_fmt_alert_time(dt, now)` (new function in `claude-statusline.py`) | utility / formatter | transform | `fmt_reset(epoch)` at L2537 | role-match (same-day vs multi-day branching; strftime idiom identical; style differs) |
| `_weather_segment` Step 3c integration (~L3684–3690) | segment builder | request-response | existing Step 3c alert-override block (~L3653–3690) | exact (splice into the existing `detail` construction) |
| `test_weather_alerts.py` — new test class for `_fmt_alert_time` + timing render | test | transform / request-response | `TestWeatherSegmentAlertOverride` and `TestWeatherSegmentAlertOverrideV2` (same file, L872–1426) | exact (same module-load pattern, `_make_alert` factory, `_run_segment` helper) |

---

## Pattern Assignments

### `_fmt_alert_time(dt, now)` — new pure formatter

**Analog:** `fmt_reset(epoch)` at `claude-statusline.py` L2537–2558

**Purpose:** Given a tz-aware `datetime` for the target event and a tz-aware `datetime` for the current moment, return a WX-10-styled time string (`3:00 PM` / `Tmrw. at 3:00 PM` / `Wed at 3:00 PM` / `Jul 3 at 3:00 PM`), or `None` on any failure.

**Imports pattern** — all already in module scope; no new imports needed.

**Core branching pattern from analog** (`fmt_reset`, L2537–2558):
```python
def fmt_reset(epoch) -> str | None:
    if epoch is None:
        return None
    try:
        reset_dt = datetime.fromtimestamp(float(epoch))
        today = datetime.now().date()
        # Format: %-I strips leading zero on 12h hour (Linux); %p gives AM/PM
        time_str = reset_dt.strftime("%-I:%M%p").lower()  # e.g. "5:15pm"
        if reset_dt.date() == today:
            return time_str
        # Different day: prepend abbreviated weekday
        weekday = reset_dt.strftime("%a")  # e.g. "Mon"
        return f"{weekday} {time_str}"
    except (OSError, OverflowError, ValueError, TypeError):
        return None
```

**How `_fmt_alert_time` differs from the analog:**
- Accepts a tz-aware `datetime` (already converted to local) rather than a Unix epoch — skip the `fromtimestamp` call.
- Time style is WX-10: `%-I:%M %p` (space before AM/PM, uppercase `%p`, no `.lower()`). Note `%p` already yields uppercase on Linux.
- Branching has four arms (not two): same day → bare time; next day → `Tmrw. at <time>`; 2–6 days ahead → `<Wkdy> at <time>` (`%a`, no period); 7+ days ahead → `<Mon> <D> at <time>` (e.g. `Jul 3 at 3:00 PM`).
- Far-out threshold: `(target_local.date() - now_local.date()).days >= 7`.
- Returns `None` on any exception (same omit-not-fake contract as `fmt_reset`).

**strftime idioms to reuse from analog:**
- `%-I` — strips leading zero on 12-hour clock (Linux; used at L2552).
- `%M` — zero-padded minutes.
- `%p` — uppercase AM/PM (analog lowercases it; WX-10 keeps uppercase).
- `%a` — abbreviated weekday e.g. `Mon` (used at L2556).
- New for far-out arm: `%b` — abbreviated month e.g. `Jul`; `%-d` — day without leading zero (Linux).

**ISO-8601 parse idiom** (reuse from `dedup_alerts` L1351–1361 and `_gsd_segment` L2879):
```python
# _parse_dt inner helper in dedup_alerts (L1351-1361)
def _parse_dt(s):
    if not s:
        return None
    try:
        s2 = s
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        return datetime.fromisoformat(s2)
    except Exception:
        return None

# Single-line form used in _gsd_segment (L2879):
ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
```
Apply the same `.replace("Z", "+00:00")` idiom when parsing `onset`/`effective`/`ends`/`expires` from `props`. After parsing, call `.astimezone()` with no argument to convert to local time.

**Error handling pattern** — mirror `fmt_reset`:
```python
except (OSError, OverflowError, ValueError, TypeError):
    return None
```
Use a broad `except Exception: return None` since timestamp parse errors (from malformed NWS data) should silently omit the timing fragment, consistent with D-10.

---

### `_weather_segment` Step 3c — integration splice (~L3684–3690)

**Analog:** the existing alert-override block at `claude-statusline.py` L3653–3690

**Current state** (L3653–3690, verbatim for reference):
```python
# Step 3c: Trailing detail — alert override or sun event (D2-11, D2-12, WX-04)
trailing_detail = None
# Attempt alert override: only when alerts section is within ceiling + non-empty
try:
    if section_within_ceiling(alerts_section, max_stale=alerts_max_stale, now=now):
        active = alerts_section.get("active") or []
        if active:
            best, remaining_alerts = select_alert(active)
            if best is not None:
                try:
                    props = best.get("properties") or best
                    event = props.get("event", "Unknown Alert")
                except Exception:
                    event = "Unknown Alert"
                # D-05/D-06: class-driven hue + urgency/certainty intensity
                color = _alert_color(best)
                # D-04: class glyph resolved via icon_set toggle
                best_class = _classify_alert_class(best)
                if icon_set == "nerd":
                    class_glyph = _ALERT_CLASS_GLYPHS_NERD.get(best_class, _WI_ALERT_STATEMENT)
                else:
                    class_glyph = _ALERT_CLASS_GLYPHS_EMOJI.get(best_class, "ℹ️")
                # Sanitize event text — strip ESC/control seqs, truncate to 64 (T-02.2-04)
                safe_event = "".join(
                    ch for ch in str(event)
                    if ch == " " or (ch.isprintable() and ch != "\x1b")
                )[:64].strip()
                # D-10: never emit a hollow glyph — if sanitization left nothing
                # (e.g. an all-control-char event), fall back to the class name (WR-02).
                if not safe_event:
                    safe_event = best_class
                detail = f"{class_glyph} {safe_event}"
                # D-08: per-class tally of remaining alerts (not flat +N)
                if remaining_alerts:
                    tally = _build_alert_tally(remaining_alerts, icon_set)
                    if tally:
                        detail += f"  {tally}"
                trailing_detail = f"{color}{detail}{RESET}"
except Exception:
    pass  # alert override failed: fall through to sun event
```

**Splice point:** between L3684 (`detail = f"{class_glyph} {safe_event}"`) and L3686 (`if remaining_alerts:`). The timing fragment is inserted into `detail` before the tally is appended, so the final render order is:

```
{class_glyph} {safe_event} · {from|until} <time>  {tally}
```

**Splice pattern to add** (between L3684 and L3686):
```python
# D-01/D-02/D-03: Build and splice timing fragment
try:
    props_timing = best.get("properties") or best
    # D-03: start = onset → effective fallback; end = ends → expires fallback
    start_raw = props_timing.get("onset") or props_timing.get("effective")
    end_raw   = props_timing.get("ends")  or props_timing.get("expires")
    timing_fragment = _fmt_alert_timing(start_raw, end_raw, now=now)
    if timing_fragment:
        detail += f" · {timing_fragment}"
except Exception:
    pass  # timing parse failed → omit silently (D-10)
```

Note: `now` is already in scope in `_weather_segment` (used by `section_within_ceiling`). The `props` variable holding event/severity is already extracted above at L3663; re-read from `best` as `props_timing` to be explicit, or reuse `props` if it is already in local scope at the splice point.

The existing `trailing_detail = f"{color}{detail}{RESET}"` at L3690 remains unchanged — the timing is already inside `detail`, so it inherits the class color and intensity (D-01).

---

## Shared Patterns

### ISO-8601 Timestamp Parsing
**Source:** `claude-statusline.py` L1351–1361 (inner `_parse_dt` in `dedup_alerts`) and L2879 (inline in `_gsd_segment`)
**Apply to:** `_fmt_alert_time` (or its caller in the splice)

```python
s2 = s.replace("Z", "+00:00")
dt = datetime.fromisoformat(s2)
local_dt = dt.astimezone()  # converts to local timezone
```

### Omit-not-Fake Error Handling
**Source:** `claude-statusline.py` L2537–2558 (`fmt_reset`) and L3691–3692 (alert-override except clause)
**Apply to:** `_fmt_alert_time` and the splice in Step 3c

```python
# fmt_reset pattern (L2558)
except (OSError, OverflowError, ValueError, TypeError):
    return None

# Step 3c outer pattern (L3691-3692) — catch-all so a timing failure never breaks the segment
except Exception:
    pass  # fall through to sun event
```

New code follows the same philosophy: return `None` / pass silently on any parse or format failure.

### Alert Property Access Pattern
**Source:** `claude-statusline.py` L3662–3665 (inside `_weather_segment` Step 3c)
**Apply to:** the timing splice when reading `onset`/`ends`/etc.

```python
try:
    props = best.get("properties") or best
    event = props.get("event", "Unknown Alert")
except Exception:
    event = "Unknown Alert"
```

Mirror this guarded `props = best.get("properties") or best` pattern when accessing timing fields — NWS feature dicts nest their CAP fields under `properties`, but the cache may store the properties dict directly.

---

## Test Patterns

### Test file: `tests/test_weather_alerts.py`

**Where new tests go:** Append a new `TestAlertTimingFormatter` class (for `_fmt_alert_time` unit tests) and a new `TestWeatherSegmentAlertTiming` class (for integration / render tests) to `tests/test_weather_alerts.py` after the existing `TestWeatherSegmentAlertOverrideV2` class (currently ending at L1426).

### Module-load convention (L36–41):
```python
def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```
Every `setUp` calls `self.mod = _load_script_module()`. New test classes follow the same pattern.

### Alert factory convention (`_make_alert`, L50–76):
```python
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
```
For timing tests, extend this by adding `onset`, `effective`, `ends` keys directly into `props` (or build a separate thin factory).

### `_run_segment` helper pattern (`TestWeatherSegmentAlertOverrideV2`, L1236–1247):
```python
def _run_segment(self, cache_dict, cfg=None):
    cache_path = os.path.join(self.tmpdir, "cache.json")
    with open(cache_path, "w") as f:
        json.dump(cache_dict, f)
    cfg = cfg or self.cfg_emoji

    def no_op_spawn(cfg_, cache_):
        pass

    with patch.object(self.mod, "_CACHE_PATH", cache_path):
        with patch.object(self.mod, "maybe_spawn_refresh", side_effect=no_op_spawn):
            return self.mod._weather_segment(None, cfg)
```
Copy this exact helper into the new integration test class. The `icon_set="emoji"` cfg pin is important so assertions about glyph codepoints remain deterministic.

### `_make_active_cache` helper pattern (L1249–1254):
```python
def _make_active_cache(self, alerts, age_seconds=60):
    now = time.time()
    return {
        "weather": {"fetched_at": now - age_seconds, "icon": "☀️", "temp": 72, "pop": 0},
        "alerts": {"fetched_at": now - age_seconds, "active": alerts},
    }
```
Reuse or extend: for timing tests, include `onset`/`ends` fields directly in the alert's `properties` dict.

### Guard for `_WEATHER_OK` (present in every integration test, e.g. L965–966):
```python
if not self.mod._WEATHER_OK:
    self.skipTest("_WEATHER_OK False — astral/requests not installed")
```
Apply to every test that calls `_weather_segment`.

### Pure formatter tests (e.g. `TestSelectAlert`, no `_WEATHER_OK` guard needed):
`_fmt_alert_time` is a pure function with no network or astral dependency. Its unit tests do NOT need the `_WEATHER_OK` guard — call `self.mod._fmt_alert_time(...)` directly with constructed `datetime` objects.

---

## No Analog Found

None — every new unit has a strong analog in the existing codebase.

---

## Metadata

**Analog search scope:** `claude-statusline.py` (4,114 lines), `tests/test_weather_alerts.py` (1,430 lines)
**Key files scanned:** `claude-statusline.py`, `tests/test_weather_alerts.py`, `tests/fixtures/nws_alerts_active.json`
**Pattern extraction date:** 2026-06-20
