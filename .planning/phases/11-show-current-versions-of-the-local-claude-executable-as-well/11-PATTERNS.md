# Phase 11: Version Display - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 2 (1 modified, 1 new) covering 6 new code elements
**Analogs found:** 6 / 6 (all exact in-repo analogs)

This is a single-file Python project: the whole statusline lives in `claude-statusline.py`
(~209 KB) with a stdlib-only `unittest` suite under `tests/`. There are no controllers /
services / components — "files" here are functions, constant blocks, and config keys inside
the one module. Each new code element is classified and mapped to its closest existing analog
below. All analogs are exact (same role + same data flow), since the codebase already contains
several bottom-line segment builders to mirror.

## File Classification

| New/Modified element | Role | Data Flow | Closest Analog | Match Quality |
|----------------------|------|-----------|----------------|---------------|
| `claude-statusline.py` :: 2 new `_NF_VERSION_*` glyph consts | constant block | n/a (literal) | `_NF_GSD_*` / `_NF_CLAUDE_*` block (line 966+) | exact |
| `claude-statusline.py` :: `_read_installed_gsd_version()` (new helper) | utility (reader) | file-I/O (local JSON read) | `_read_gsd_state` (line 3016) | exact (byte-capped JSON read) |
| `claude-statusline.py` :: `_versions_fragment()` (new builder) | segment builder | transform → str\|None | `_rate_segment` (4121) / `_claude_status_segment` (4157) | exact |
| `claude-statusline.py` :: wiring in `render_bottom_line` | integration point | request-response (render path) | `render_bottom_line` (4402); glyph-swap (4442); parts join (4473) | exact (self) |
| `claude-statusline.py` :: `show_versions` default toggle | config | n/a (default dict) | `toggles` block (159) / `display` block (193) | exact |
| `tests/test_versions_fragment.py` (new module) | test | n/a | `tests/test_bottom_line.py` | exact (bottom-line segment tests) |

## Pattern Assignments

### `_NF_VERSION_*` glyph constants (constant block, ~line 988 / 994)

**Analog:** `_NF_GSD_*` and the Claude-status glyph block (`claude-statusline.py:959-1002`)

**Convention to copy** — one literal codepoint per glyph + an intent-comment naming the
`nf-*` code and the U+F0xx hex. Codepoints must exist in the installed JetBrains Nerd Font
cmap (there is an installed-font cmap guard in `test_nerd_icons.py` — see D-08).

```python
# Git markers (959-963)
_NF_GIT_AHEAD    = ""   # nf-fa-arrow_up      U+F062
_NF_GIT_BEHIND   = ""   # nf-fa-arrow_down    U+F063

# GSD lifecycle (973-988) — same pattern
_NF_GSD_EXECUTING = ""   # nf-fa-play          U+F04B  (green: actively running)
_NF_GSD_PLAN      = ""   # nf-fa-map           U+F278  (neutral: plan slot label)
```

Header-comment idiom to mirror (965-970): a banner naming the phase, the semantic rationale,
and the cmap-guard note. The two new glyphs (Claude version, GSD version) are Claude's
discretion for codepoint choice (D-08) but MUST carry the `# nf-...  U+F0xx  (intent)` comment.

---

### `_read_installed_gsd_version()` (utility / reader, file-I/O)

**Analog:** `_read_gsd_state(planning_dir)` (`claude-statusline.py:3016-3067`)

**Byte cap constant to reuse** (`claude-statusline.py:2972`):
```python
_GSD_MAX_BYTES = 65_536
```

**Pattern to copy** — explicit byte-capped read, whole body in `try/except Exception`,
return `None` on any failure (omit-not-fake, D-06):
```python
    try:
        ...
        with open(handoff_path, encoding="utf-8") as fh:
            handoff = json.loads(fh.read(_GSD_MAX_BYTES))   # byte-capped read
        if not isinstance(handoff, dict):
            return None
        ...
        return { ... }
    except Exception:
        return None   # file missing, JSON parse error, OS error — omit silently
```

**Adaptation notes (D-05, verified against live ledger):**
- Path: `os.path.expanduser("~/.claude/plugins/installed_plugins.json")`.
- The shape is `data["plugins"]["gsd@gsd-plugin"]` → **a JSON array**, not a dict. The version
  lives at index `[0]["version"]` (e.g. `"4.0.0"`). Guard with `isinstance(..., list)` and a
  non-empty check before indexing — mirror the `isinstance(handoff, dict)` guard above.
- Do NOT scan `plugins/cache/gsd-plugin/gsd/*/` dirs and do NOT read the plugin `package.json`
  (D-05 — both report wrong/stale numbers; 6 stale cache dirs present today).
- No TTL cache needed — cheap local read (D-06).

---

### `_versions_fragment(data, cfg)` (segment builder, transform → str | None)

**Analog:** `_rate_segment` (`claude-statusline.py:4121-4144`) and `_claude_status_segment`
(`4157-4199`) — the "return a string or `None`, body wrapped in try/except" segment shape.

**Builder skeleton to copy** (from `_rate_segment`):
```python
def _rate_segment(block, glyph, warn=70, crit=90) -> str | None:
    """<glyph> <pct>%[ <dim reset>] colored by threshold, or None if missing."""
    try:
        pct = pct_int(block.get("used_percentage"))
        if pct is None:
            return None
        ...
        result = f"{glyph} {pct_str}"
        ...
        return result
    except Exception:
        return None
```

**Toggle-guard idiom to copy** (from `_claude_status_segment:4178-4181`):
```python
        _cfg = cfg if isinstance(cfg, dict) else {}
        if not _cfg.get("display", {}).get("show_claude_status", True):
            return None
```

**Fragment-specific construction (D-02 / D-04 / D-07 / D-09):**
- Build a list of pieces; the Claude version piece and GSD version piece are independent.
  - Claude piece: read `data.get("version")`; if missing / empty / non-`str`, omit ONLY that
    piece (D-04). Source is the stdin `version` field — verified present in
    `.examples/claude_stdin.json` as `"2.1.154"`. No subprocess (D-03).
  - GSD piece: from `_read_installed_gsd_version()`; omit ONLY that piece if `None` (D-07).
- The two pieces are joined with a **single space** internally (D-02), then the whole fragment
  is wrapped in `DIM ... RESET` (D-09 — see Shared Patterns). If BOTH pieces are absent,
  return `None` so the fragment None-filters out cleanly.
- GSD version is **always shown** when the ledger entry exists — NOT gated on `.planning/`
  presence. This deliberately differs from `_gsd_segment` (3349-3360), which omits when
  `.planning/` is absent (D-07).

---

### Wiring into `render_bottom_line` (integration point, render path)

**Analog:** `render_bottom_line` itself (`claude-statusline.py:4402-4478`).

**icon_set glyph-swap pattern to mirror** (D-11, `claude-statusline.py:4442-4448`):
```python
        _icon_set = _display.get("icon_set", "nerd")
        if _icon_set == "nerd":
            _glyph_5h = _NF_HOURGLASS
            _glyph_wk = _NF_CALENDAR
        else:
            _glyph_5h = "⏳"
            _glyph_wk = "🗓"
```
For versions, when `_icon_set == "nerd"` use the two `_NF_VERSION_*` glyphs; otherwise fall
back to short text labels (e.g. `c`/`g` or `claude`/`gsd` — Claude's discretion, D-11). Do NOT
emit NF codepoints under non-nerd `icon_set`. `_icon_set` is already resolved at line 4442 —
reuse the same local, do not re-read config.

**Toggle-gated build + None-filter join** (`claude-statusline.py:4471-4476`) — append the
versions segment AFTER `status_seg` (D-01):
```python
        status_seg = _claude_status_segment(data, cfg)

        parts = [s for s in [ctx_seg, five_hour_seg, weekly_seg, status_seg] if s is not None]
        if not parts:
            return None
        return "   ".join(parts)        # 3-space block separator (D-02)
```
New code: build `versions_seg = _versions_fragment(data, cfg) if toggles.get("show_versions", True) else None`
(or read from `display` if the planner homes the toggle there — see Conventions), then add
`versions_seg` as the last element of the `parts` list. The existing `"   ".join` gives the
3-space block separation for free; the single-space intra-fragment spacing lives inside
`_versions_fragment` (D-02).

**Never-crash envelope:** the whole `render_bottom_line` body is already inside
`try/except Exception: return None` (4419 / 4477) — the new wiring inherits it. The builder
itself must ALSO be self-guarded (per the `_rate_segment` skeleton) so one bad piece never
takes down the line.

---

### `show_versions` config default (config)

**Analog:** the `DEFAULTS` dict — `toggles` block (`claude-statusline.py:159-164`) and the
`display` block (`193-216`).

**Two candidate homes (D-10 / Claude's discretion — planner picks the consistent one):**

`toggles` block (159), alongside other per-segment on/off switches:
```python
    "toggles": {
        "show_context_bar":    True,
        "show_five_hour":      True,
        "show_weekly":         True,
        "show_thinking_glyph": True,
    },
```

`display` block (193), where the most recent segment toggles live (`show_git` 202,
`show_gsd` 206, `show_claude_status` 210) — each with a phase-tagged intent comment:
```python
        # Phase 05: GSD segment toggle (D-08 discretion: display.show_gsd).
        # True (default) renders the GSD segment when .planning/ exists under project_dir.
        "show_gsd": True,
```
Newer segment toggles (Phases 04-06) cluster under `display`, so `show_versions: True` under
`display` with a `# Phase 11:` comment is the more current convention; the older `toggles`
block holds the original Phase 1-2 switches. **Default value is `True` (on) regardless of home
(D-10).** Whichever block is chosen, the `render_bottom_line` read site must match it
(`toggles.get(...)` vs `_display.get(...)`).

---

### `tests/test_versions_fragment.py` (test module)

**Analog:** `tests/test_bottom_line.py` (segment-level bottom-line tests).

**Module-load + run harness to copy** (`tests/test_bottom_line.py:9-64`):
```python
import importlib.util, json, os, subprocess, sys, tempfile, unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")

def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def run_script(stdin_bytes: bytes, home: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home          # override $HOME to control config + ledger lookups
    return subprocess.run([sys.executable, SCRIPT], input=stdin_bytes, capture_output=True, env=env)
```

**Test-class idiom to copy** (`test_bottom_line.py:339-396`):
- `setUp` loads the module via `_load_script_module()` for direct unit calls
  (`self.mod._versions_fragment(...)`), OR drive end-to-end via `run_script(payload, home=...)`.
- ANSI-strip before asserting on visible text:
  `stripped = re.sub(r'\x1b\[[0-9;]*m', '', bottom)`.
- Bottom line is `lines[1]` (`bottom = lines[1] if len(lines) > 1 else ""`).

**`$HOME` control is the key affordance for this fragment.** The GSD version reads
`~/.claude/plugins/installed_plugins.json`; point `$HOME` (via the `home=` kwarg) at a
`tempfile`-built fake home containing a crafted `installed_plugins.json` to exercise:
present-entry, missing-entry, unreadable-file, and malformed-JSON cases (omit-not-fake, D-07).
The Claude version comes from stdin `version`, so vary the payload dict directly for
present / missing / empty / non-string cases (D-04). Cases to mirror from the synthetic class:
nerd vs non-nerd `icon_set` glyph swap (D-11), `show_versions=False` omission (D-10), and
dim-wrapping presence (D-09).

---

## Shared Patterns

### Omit-not-fake / never-crash (project invariant)
**Source:** every segment builder — `_rate_segment` (4143), `_read_gsd_state` (3066),
`_claude_status_segment` (4173), `render_bottom_line` (4477).
**Apply to:** `_read_installed_gsd_version`, `_versions_fragment`, and the render wiring.
```python
    try:
        ...
    except Exception:
        return None   # bad/absent data → omit the segment; never clamp, fake, or raise
```
Reinforced by memory `statusline-omit-not-fake`: drop the piece on bad data; never substitute
a placeholder version.

### Dimmed rendering
**Source:** `DIM` constant (`claude-statusline.py:80`) + its use in `_rate_segment:4141`.
**Apply to:** the whole versions fragment (D-09).
```python
DIM    = "\033[2m"    # dim/neutral — used for reset times (D-04)
RESET  = "\033[0m"
# usage: result += f" {DIM}{reset_str}{RESET}"
```
Wrap the assembled versions string as `f"{DIM}{body}{RESET}"` so it recedes on a glance.

### icon_set nerd-vs-text fallback
**Source:** `render_bottom_line:4442-4448` (`_glyph_5h`/`_glyph_wk` swap).
**Apply to:** the versions glyph selection (D-11). Reuse the `_icon_set` local already resolved
at 4442 — do not re-read `cfg["display"]["icon_set"]`.

### Byte-capped local JSON read
**Source:** `_GSD_MAX_BYTES = 65_536` (2972) + `_read_gsd_state` (3016).
**Apply to:** `_read_installed_gsd_version` — `fh.read(_GSD_MAX_BYTES)` then `json.loads`,
inside `try/except`, with `isinstance` shape guards before indexing.

## No Analog Found

None. Every new element maps to an exact in-repo analog (this codebase already ships multiple
bottom-line segment builders, a byte-capped local-JSON reader, glyph-constant blocks, and a
matching test module). There is no RESEARCH.md for this phase and none is needed.

## Conventions

Convention derivation skipped (`no-readable-files`): the shared `gsd-tools.cjs verify
conventions --derive` module is JS/TS-oriented and finds nothing to vote on in this single-file
Python repo. Conventions below are read directly from the module's established style.

| Axis | Dominant | Share | Entropy | Status |
|------|----------|-------|---------|--------|
| Module-private name casing | `_snake_case` leading underscore (`_rate_segment`, `_read_gsd_state`, `_versions_fragment`) | high | low | named contract |
| Constant name casing | `_UPPER_SNAKE` with `_NF_*` / `_GSD_*` namespace prefixes | high | low | named contract |
| Builder return contract | `-> str \| None` (return `None` to omit; body wrapped in `try/except Exception`) | high | low | named contract |
| Comment style | intent-comment naming the spec decision (`(D-0x)`) + phase tag (`# Phase NN:`) | high | low | named contract |
| Config home for new segment toggles | `display` block (Phases 04-06) vs older `toggles` block (Phases 1-2) | ~60% display | medium | contested hotspot (author's choice) |

**Contested hotspots (author's choice):** the home of the new `show_versions` toggle —
`display` (recent convention, `show_git`/`show_gsd`/`show_claude_status`) vs `toggles` (original
switches) — is the one genuinely contested axis. Each block is internally consistent; pick the
`display` block to match the most recent three segment toggles and tag it `# Phase 11:`. This is
the same shape as the GSD plugin's prototype CJS↔SDK dual-resolver split (each directory locally
consistent, contested only repo-wide): match the local cluster's style, do not invent a third.

## Metadata

**Analog search scope:** `claude-statusline.py` (single module), `tests/` (16 test modules),
live `~/.claude/plugins/installed_plugins.json` (ledger shape verification),
`.examples/claude_stdin.json` (stdin `version` field verification).
**Files scanned:** 4 read targets + 2 grep/python shape probes.
**Pattern extraction date:** 2026-06-27
