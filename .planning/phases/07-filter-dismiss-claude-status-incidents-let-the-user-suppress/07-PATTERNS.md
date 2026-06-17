# Phase 7: Filter/dismiss Claude-status incidents - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 1 source file (`claude-statusline.py`) + 1 test file (`tests/test_claude_status.py`) — single-file Python CLI; all new code lands in these two files
**Analogs found:** 5 / 5 (every new unit has a strong in-repo analog)

> **Standing contract (applies to ALL new code below):** builders/derivation/store reads return `None`/omit/degrade on bad data — never crash, never fake ([[statusline-omit-not-fake]], D-10). A bad regex, corrupt dismissal store, or missing file MUST degrade to "no suppression", never raise. Every analog below already implements `try/except → safe default`; copy that discipline verbatim.

---

## File Classification

This is a single-file tool. "New file" = new function/section inside `claude-statusline.py`; tests go in the existing `tests/test_claude_status.py`. No new modules, no UI layer.

| New unit (function / section) | Lands in | Role | Data Flow | Closest Analog | Match Quality |
|-------------------------------|----------|------|-----------|----------------|---------------|
| Filtering logic (id-dismiss + title keyword/regex, escalation re-surface, auto-prune) integrated into `_derive_claude_status` | `claude-statusline.py` (≈1298) | derivation / pure transform | transform (filter over feed) | `_derive_claude_status` itself (modify in place) | exact (in-place) |
| Dismissal store read/write helpers (e.g. `read_dismissals` / `write_dismissals` / `_dismiss_id` / `_undismiss_id` / `_prune_dismissals`) | `claude-statusline.py` (new section near ≈260) | store / persistence | file-I/O (atomic JSON read/write) | `read_cache` + `write_cache_section` (≈263–309) | exact (role + flow) |
| `--status-incidents` / `--dismiss <id>` / `--undismiss <id>` arg branches | `claude-statusline.py` `main()` (≈3207) | CLI / entry-point | request-response (side-effect flag, no stdin, no bar, exit) | `--refresh` branch in `main()` (≈3207–3210) | exact (role + flow) |
| Config keys `ignore_title_patterns` + `filter_enabled` under `[claude_status]` | `claude-statusline.py` `DEFAULTS` (≈131) | config | static / read-only TOML merge | `DEFAULTS["display"]` block (≈170–188) + `_deep_merge` (≈196) + `load_config` (≈213) | exact |
| New test cases (id-dismiss, keyword suppress, escalation re-surface, auto-prune, corrupt store → no suppression, `--dismiss`/`--undismiss` mutation, `--status-incidents` output) | `tests/test_claude_status.py` | test | n/a | `TestDeriveClaudeStatus` (≈212) + `TestFetchClaudeStatus` (≈380) | exact |

---

## Pattern Assignments

### 1. Filtering logic — modify `_derive_claude_status(summary)` (derivation, transform)

**Analog:** `_derive_claude_status` itself — `claude-statusline.py:1298-1432`. Filtering integrates here (CONTEXT D-01) so quiet-when-healthy fall-through (Phase 6 D-01) still holds: when the only noteworthy item is suppressed, Rule 4 naturally returns `None`.

**Signature change note:** the current function is pure over `summary` only. To apply id-dismiss + escalation it needs the dismissal store and the keyword/toggle config. Thread them as new params with safe defaults so existing callers/tests don't break, e.g. `_derive_claude_status(summary, dismissals=None, cfg=None)`. Default `None` → behaves exactly as today (no suppression). The render path reads them and passes them in.

**Per-incident shape it already consumes** (confirmed from `tests/fixtures/status_incident_tracked.json:43-57` and the loop at `1357-1383`): each incident dict has `id` (stable Statuspage feed id — e.g. `"inc-001"`), `name` (title), `status` (`investigating`/`identified`/`monitoring`), `impact` (`none`/`minor`/`major`/`critical`), and `components[]` (refs with `name`). **`id` is present in the feed — use it as the dismissal key.**

**Existing incident-collection loop to extend (the suppression filter slots in here)** — `claude-statusline.py:1356-1383`:
```python
        triggered_incidents = []
        for inc in incidents_raw:
            if not isinstance(inc, dict):
                continue
            inc_status = inc.get("status", "")
            if not isinstance(inc_status, str):
                continue
            if inc_status not in ("investigating", "identified", "monitoring"):
                continue
            tracked = _tracked_component_names(inc.get("components", []))
            if not tracked:
                continue
            # >>> NEW: suppression filter goes HERE, before append (D-01) <<<
            #   inc_id   = inc.get("id", "")
            #   impact   = inc.get("impact", "none")
            #   title    = inc.get("name", "")
            #   if _is_suppressed(inc_id, impact, title, dismissals, cfg):
            #       continue   # treat as not-noteworthy → falls through to next / maintenance / None
            triggered_incidents.append(inc)

        if triggered_incidents:
            impact_rank = {"critical": 3, "major": 2, "minor": 1, "none": 0}
            best = max(
                triggered_incidents,
                key=lambda i: impact_rank.get(i.get("impact", "none"), 0),
            )
            ...
```

**Existing impact-ordering map to reuse for escalation (D-03)** — `claude-statusline.py:1373`:
```python
            impact_rank = {"critical": 3, "major": 2, "minor": 1, "none": 0}
```
Escalation re-surface = `impact_rank[live_impact] > impact_rank[impact_at_dismiss]` → ignore the dismissal (re-surface). Reuse this exact dict; do not invent a second ordering. Note (CONTEXT D-03): escalation tracking applies to **id-dismissals only**; keyword suppression is a blunt mute with no per-incident escalation.

**Never-raise wrapper already in place** — `claude-statusline.py:1321` and `1431-1432`:
```python
    try:
        if not isinstance(summary, dict):
            return None
        ...
    except Exception:
        return None
```
The new suppression helper (`_is_suppressed`) must be equally defensive: wrap the regex match in `try/except` and **return `False` (not suppressed) on a bad pattern** — a bad regex never hides a real incident and never raises. Mirror the per-item `try/except` discipline seen at `1446-1449` (`_build_alert_tally`).

---

### 2. Dismissal store helpers — new functions (store, file-I/O)

**Analog:** `read_cache` (`claude-statusline.py:263-277`) + `write_cache_section` (`claude-statusline.py:280-309`). Reuse the **same cache dir** (`~/.claude/claude-statusline/`) and the **same atomic temp-then-`os.replace` write**. CONTEXT D-05 makes the store tool-owned (like the cache) — the tool freely writes/auto-prunes it; the user's TOML is never rewritten.

**Cache dir + path constant to mirror** — `claude-statusline.py:260`:
```python
_CACHE_PATH = os.path.expanduser("~/.claude/claude-statusline/cache.json")
```
Define a sibling, e.g. `_DISMISSALS_PATH = os.path.expanduser("~/.claude/claude-statusline/status_dismissals.json")`. (Schema/filename are discretion per D-05; keep it in the same dir.) Suggested store shape per CONTEXT D-05: `{ "<id>": { "impact_at_dismiss": "minor", "dismissed_at": <epoch> }, ... }` (one entry per dismissed id).

**Read pattern to copy** — `claude-statusline.py:263-277`:
```python
def read_cache(path: str | None = None) -> dict:
    """Load cache.json; return {} on any error (cold cache, malformed JSON, etc.)."""
    if path is None:
        path = _CACHE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}
```
`read_dismissals` copies this exactly → **corrupt store / missing file → `{}` → no suppression** (satisfies the "corrupt store → no suppression" requirement for free).

**Atomic write pattern to copy** — `claude-statusline.py:294-309`:
```python
    try:
        cache = read_cache(path)
        section_data = {"fetched_at": now}
        section_data.update(payload)
        cache[section_name] = section_data
        # Atomic write: temp file in same dir, then os.replace
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        # Any OS/JSON error is swallowed — cache miss on next render, not a crash
        pass
```
`write_dismissals(store, path=...)` copies the temp-then-`os.replace` block verbatim (the store is a flat dict, so it writes the whole dict — no per-section merge needed). Swallow all write errors. `_dismiss_id` / `_undismiss_id` / `_prune_dismissals(live_ids)` (D-04 auto-prune) are read-modify-write helpers built on these two: read → mutate dict → write.

**Auto-prune (D-04)** runs on the refresh/derive path: after computing the set of live incident `id`s from the feed, drop any stored id not in that set, then `write_dismissals`. This is non-invasive because the store is tool-owned (never the user's config).

---

### 3. CLI arg branches — extend `main()` (CLI, side-effect-then-exit)

**Analog:** the `--refresh` branch — `claude-statusline.py:3204-3210`:
```python
    # --refresh mode: invoked by the detached background child (D2-05).
    # Loads config, runs the NWS fetch, writes cache, exits.
    # Never reads stdin; never writes to stdout (only the render path does that).
    if "--refresh" in sys.argv:
        cfg = load_config()
        run_refresh(cfg)
        sys.exit(0)
```

The new flags follow this **exact shape**: detect the flag in `sys.argv`, do the side effect, `sys.exit(0)` — **before** `_load_stdin()` and before any `print` of the bar (`claude-statusline.py:3212-3219`). They never read stdin and never emit the status line (CONTEXT D-02). Add them after `--refresh` and before the render path. Suggested:

```python
    if "--dismiss" in sys.argv:
        cfg = load_config()
        idx = sys.argv.index("--dismiss")
        inc_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        _dismiss_id(inc_id, ...)   # read store, look up live impact for escalation baseline, write
        sys.exit(0)

    if "--undismiss" in sys.argv:
        ...
        _undismiss_id(inc_id, ...)
        sys.exit(0)

    if "--status-incidents" in sys.argv:
        cfg = load_config()
        # read the claude_status cache section (read_cache) + the dismissal store;
        # print a readable table of id / impact / status / title / tracked component /
        # dismissed?/stale?  (lean to a table; optional --json variant — discretion)
        sys.exit(0)
```

Notes:
- Arg parsing here is hand-rolled `sys.argv` index lookup (matching the existing `"--refresh" in sys.argv` style) — there is **no argparse** in this file; do not introduce one. Guard the `idx + 1` lookup so a missing value degrades gracefully (print a usage hint, exit non-fatally) rather than `IndexError`.
- `--status-incidents` reads from the **cache section + store only** (render-path discipline: cheap, no network). It does not fetch. The full incident list with `id`s comes from the `claude_status` cache; if the cache only stores the derived single result today (see `fetch_claude_status` payload at `1620-1628`), planning must decide whether to also cache the raw tracked-incident list so `--status-incidents` can show every id. This is the one place the cache payload likely needs widening — flag for the planner.

---

### 4. Config keys — extend `DEFAULTS` + reuse `_deep_merge` / `load_config` (config)

**Analog:** the `[claude_status]`-adjacent config plumbing. There is currently **no `claude_status` table in `DEFAULTS`** — the Phase 6 toggle lives at `display.show_claude_status` (`claude-statusline.py:184-187`). CONTEXT D-06 asks for keys under `[claude_status]`. Two consistent options for the planner (both honor existing style):
  - (a) add a new top-level `"claude_status": { "filter_enabled": ..., "ignore_title_patterns": [] }` table in `DEFAULTS`, **or**
  - (b) nest under an existing pattern.
  CONTEXT D-06 explicitly says `[claude_status]` — prefer (a): a new top-level `claude_status` table.

**DEFAULTS block to model the new table on** — `claude-statusline.py:170-188` (the `display` table shows the comment-per-key convention and boolean-default style):
```python
    "display": {
        "icon_set": "nerd",
        "bar_style": "shade",
        "show_git": True,
        "show_gsd": True,
        # Phase 06: Claude service-health segment toggle ...
        "show_claude_status": True,
    },
```
New table to add (matching style; comment each key, default the list to `[]`, default the toggle consistent with the other booleans):
```python
    # Phase 07: Claude-status incident filter (D-06). Hand-edited TOML only —
    # the tool NEVER rewrites this table (id-dismissals live in the tool-owned
    # store, D-05). A bad regex degrades to no-match, never crashes (D-10).
    "claude_status": {
        "filter_enabled": True,            # master toggle for the suppression filter
        "ignore_title_patterns": [],       # title patterns (e.g. "Mythos", "Fable")
    },
```

**Merge — reuse as-is** — `claude-statusline.py:196-210`:
```python
def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
```
A user's `[claude_status]` table deep-merges over the defaults; absent keys keep defaults. **No change needed** — the new table just works.

**Load — reuse as-is, NEVER write** — `claude-statusline.py:226-235`:
```python
    if path is None:
        path = os.path.expanduser("~/.claude/claude-statusline/claude-statusline.toml")
    try:
        with open(path, "rb") as fh:
            parsed = tomllib.load(fh)
        return _deep_merge(DEFAULTS, parsed)
    except Exception:
        return copy.deepcopy(DEFAULTS)
```
**Critical (D-05):** the project reads TOML via `tomllib` and there is no TOML writer anywhere in the file — keep it that way. `ignore_title_patterns` + the toggle are hand-edited only; dismissal ids go to the tool-owned JSON store (Pattern 2), never back into TOML.

---

### 5. Tests — extend `tests/test_claude_status.py`

**Analog A — derivation tests:** `TestDeriveClaudeStatus` (`tests/test_claude_status.py:212-373`). Convention: load a JSON fixture via `_load_fixture(name)`, call `self.mod._derive_claude_status(summary)`, assert on the returned dict / `None`; plus dedicated "never raises on malformed input" tests (`test_empty_dict_returns_none` ≈328, `test_non_dict_returns_none` ≈336, `test_missing_keys_returns_none` ≈348).

Representative excerpt to copy — `tests/test_claude_status.py:235-262`:
```python
    def test_incident_tracked_returns_dict_with_label(self):
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        ...
    def test_incident_tracked_has_kind_incident(self):
        summary = _load_fixture("status_incident_tracked.json")
        result = self.mod._derive_claude_status(summary)
        self.assertEqual(result["kind"], "incident")
```

New derivation tests follow this shape (pass dismissals/cfg as new args):
- **id-dismiss suppression** — dismiss `"inc-001"` (the id in `status_incident_tracked.json:45`) → `_derive_claude_status(summary, dismissals={...}, cfg=...)` returns `None`.
- **keyword suppression** — `cfg` with `ignore_title_patterns=["Elevated"]` (matches the fixture title `"Elevated error rates for Claude Code tool calls"`, `:46`) → `None`.
- **escalation re-surface (D-03)** — dismissed at `impact_at_dismiss="minor"`, fixture impact raised to `"major"` → result is NOT `None` (re-surfaces).
- **corrupt store → no suppression** — pass a garbage/`{}` dismissals value → behaves as un-suppressed (mirrors the existing "never raises on malformed input" tests at `:328-353`).
- **bad regex → no-match, no raise** — `ignore_title_patterns=["[unterminated"]` → derivation returns the incident (not suppressed) and does not raise.

**New fixtures:** add escalation/variant fixtures alongside the existing 7 in `tests/fixtures/` (`status_incident_tracked.json` etc.) — e.g. a `status_incident_tracked_major.json` for the escalation case. Reuse the same Statuspage v2 shape (`incidents[].id/name/status/impact/components[]`).

**Analog B — store write + CLI/env-mock tests:** `TestFetchClaudeStatus` (`tests/test_claude_status.py:380-466`). Convention: `tempfile.mkdtemp()` in `setUp`, `shutil.rmtree` in `tearDown`, and `patch.object(self.mod, "_CACHE_PATH", self.cache_path)` to redirect the store to a temp path; `patch.dict(os.environ, ...)` for env-var-driven fixtures.

Excerpt to copy — `tests/test_claude_status.py:383-413`:
```python
    def setUp(self):
        self.mod = _load_script_module()
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "cache.json")
        self.cfg = { ... "cache": {... "status_ttl": 300, "status_max_stale": 900} }

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fake_status_writes_cache_section(self):
        ...
        with patch.object(self.mod, "_CACHE_PATH", self.cache_path):
            self.mod.fetch_claude_status(self.cfg)
        data = self.mod.read_cache(self.cache_path)
        self.assertIn("claude_status", data, ...)
```

New store/CLI tests follow this shape:
- **`--dismiss`/`--undismiss` mutation** — `patch.object(self.mod, "_DISMISSALS_PATH", tmp_path)`, call the helper (`_dismiss_id` / `_undismiss_id`), then `read_dismissals(tmp_path)` and assert the id is present / absent.
- **auto-prune of stale ids** — seed the store with an id not in the live feed, run derive/prune, assert it's gone.
- **corrupt store file → `read_dismissals` returns `{}`** (no raise) — write garbage bytes to the temp path, assert `{}`.
- **`--status-incidents` output** — invoke via subprocess on the script (or call the render/print helper directly), assert the table contains the fixture id/title and the dismissed/stale markers. Use `CLAUDE_STATUSLINE_FAKE_STATUS` / cache fixtures the same way `TestFetchClaudeStatus` uses env-mock + temp cache.

---

## Shared Patterns

### Never-crash / omit-not-fake (applies to ALL new units)
**Source:** every analog — `_derive_claude_status` outer `try/except` (`claude-statusline.py:1321,1431`), `read_cache` (`263-277`), `write_cache_section` (`294-309`), per-item guard in `_build_alert_tally` (`1443-1462`), `load_config` (`228-235`).
**Apply to:** filter helper, store helpers, CLI branches, config load.
```python
    try:
        ...real work...
    except Exception:
        return <safe default>   # None / {} / False / pass — NEVER raise, NEVER fake
```
Bad regex → `False` (not suppressed). Corrupt/missing store → `{}` (no suppression). The bar must keep rendering.

### Atomic tool-owned write (store)
**Source:** `write_cache_section` temp-then-`os.replace` — `claude-statusline.py:301-306`.
**Apply to:** `write_dismissals` and all store mutators.
```python
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
```
Same dir as the cache; render path never reads a half-written file.

### Read-only TOML (config)
**Source:** `load_config` / `tomllib.load` — `claude-statusline.py:228-235`. There is **no TOML writer in the codebase**.
**Apply to:** all config handling. `ignore_title_patterns` + toggle are hand-edited only (D-05/D-06). Dismissal ids live in the tool-owned JSON store, never written back to TOML.

### Side-effect-flag-then-exit (CLI)
**Source:** `--refresh` branch — `claude-statusline.py:3204-3210`. Detect flag in `sys.argv`, do work, `sys.exit(0)` before stdin read / bar print. Hand-rolled `sys.argv` parsing (no argparse).
**Apply to:** `--status-incidents`, `--dismiss`, `--undismiss`.

---

## No Analog Found

None. Every new unit maps to a strong in-repo analog. The single nuance requiring a planning decision (not a missing analog):

| Concern | Note for planner |
|---------|------------------|
| `--status-incidents` needs every tracked incident's `id` | The current `claude_status` cache payload (`fetch_claude_status`, `claude-statusline.py:1620-1628`) stores only the single derived result (severity/label/kind), not the per-incident id list. To list ids for the user to dismiss, planning must widen the cached payload to include the raw tracked-incident records (`id`/`impact`/`status`/`name`/component) — a payload extension, not a new pattern. Reuse `write_cache_section` as-is. |

---

## Metadata

**Analog search scope:** `claude-statusline.py` (3223 lines) — sections: `DEFAULTS`/config (131-235), cache helpers (260-336), `_CLAUDE_*` constants (1274-1295), `_derive_claude_status` (1298-1432), `fetch_claude_status`/`run_refresh` (1561-1690), `main()` (3199-3223); `tests/test_claude_status.py` (TestDeriveClaudeStatus, TestFetchClaudeStatus); `tests/fixtures/status_*.json` (7 fixtures).
**Files scanned:** 2 source/test files + 7 fixtures
**Pattern extraction date:** 2026-06-17
