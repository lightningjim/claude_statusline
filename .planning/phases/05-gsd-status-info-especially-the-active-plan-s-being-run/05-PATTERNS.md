# Phase 5: GSD Status Segment - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 5 new/modified symbols (2 new files + 3 insertion points in existing file)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `claude-statusline.py` — `_NF_GSD_*` constants | config | — | `_NF_GIT_*` constants (line 411) | exact |
| `claude-statusline.py` — `DEFAULTS["display"]["show_gsd"]` | config | — | `"show_git": True` (line 172) | exact |
| `claude-statusline.py` — `_read_gsd_state(planning_dir)` helper | utility | file-I/O | `_run_git` (line 1295) | role-match |
| `claude-statusline.py` — `_gsd_segment(data, cfg)` builder | controller | request-response | `_git_segment` (line 1456) | exact |
| `claude-statusline.py` — `render_top_line` insertion | route | request-response | `render_top_line` (line 1914) | exact |
| `tests/test_gsd_segment.py` | test | — | `tests/test_git_segment.py` | exact |

---

## Pattern Assignments

### `_NF_GSD_*` glyph constants

**Analog:** `_NF_GIT_*` constants, `claude-statusline.py` lines 410–423

**Pattern** (lines 410–423):
```python
# Branch glyph (powerline branch symbol — the universally recognized git branch icon)
_NF_GIT_BRANCH   = ""   # nf-pl-branch        U+E0A0

# Worktree glyph (code fork — visually suggests a branch diverging from main)
_NF_GIT_WORKTREE = ""   # nf-fa-code_fork     U+F126

# Dirty-state marker (asterisk — concise single-cell flag for uncommitted changes)
_NF_GIT_DIRTY    = ""   # nf-fa-asterisk      U+F069

# Ahead-of-upstream marker (arrow up — "you are ahead")
_NF_GIT_AHEAD    = ""   # nf-fa-arrow_up      U+F062

# Behind-upstream marker (arrow down — "you are behind")
_NF_GIT_BEHIND   = ""   # nf-fa-arrow_down    U+F063
```

**How to copy:** Define one constant per lifecycle state and one for the plan/task slot, following the same `_NF_GSD_<ROLE>  = "<glyph>"  # nf-<family>-<name>  U+XXXX` comment format. Exact codepoints are a planning decision; the grouping and comment format are the pattern. Example set:

```python
# GSD segment glyphs — Phase 05 lifecycle / plan indicators
_NF_GSD_EXECUTING = ""   # nf-fa-play          U+F04B  (green: actively running)
_NF_GSD_VERIFYING = ""   # nf-fa-check_square  U+F046  (yellow: verification step)
_NF_GSD_BLOCKED   = ""   # nf-fa-ban           U+F05E  (red: blocked)
_NF_GSD_DONE      = ""   # nf-fa-check_circle  U+F058  (green: milestone complete)
_NF_GSD_IDLE      = ""   # nf-fa-pause         U+F04C  (dim: parked / next-up)
_NF_GSD_PLAN      = ""   # nf-fa-map           U+F278  (neutral: plan slot label)
```

---

### `DEFAULTS["display"]["show_gsd"]` config toggle

**Analog:** `DEFAULTS` dict, `claude-statusline.py` lines 163–173

**Pattern** (lines 163–173):
```python
"display": {
    "icon_set": "nerd",     # "nerd" (default) or "emoji"
    # Phase 03: context-bar fill style (D-08/D-09).
    # "shade" (default) keeps the existing ▓/░ look — zero change for existing installs.
    # Other values: "solid", "solid-dim", "gradient".  Independent of icon_set (D-10).
    "bar_style": "shade",   # "shade" | "solid" | "solid-dim" | "gradient"
    # Phase 04: git segment toggle (D-08 discretion: display.show_git).
    # True (default) renders the git segment on the top line when in a git repo.
    # Set to false in [display] to suppress the segment (e.g. in test configs).
    "show_git": True,
},
```

**How to copy:** Add `"show_gsd": True,` as the next key after `"show_git"`, with the same comment style:
```python
    # Phase 05: GSD segment toggle (D-08 discretion: display.show_gsd).
    # True (default) renders the GSD segment when .planning/ exists under project_dir.
    # Set to false in [display] to suppress the segment.
    "show_gsd": True,
```

---

### `_read_gsd_state(planning_dir)` helper

**Analog:** `_run_git`, `claude-statusline.py` lines 1295–1322

**Core never-raises pattern** (lines 1295–1322):
```python
def _run_git(args: list[str], cwd: str, timeout: float = 0.15) -> str | None:
    """Run ``git -C cwd <args>`` and return stdout text, or None on any failure.

    Never raises (RUN-01/RUN-02).  On TimeoutExpired the subprocess is killed
    by subprocess.run before the exception propagates, so the render path is
    freed within *timeout* seconds.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout
    except Exception:
        return None   # TimeoutExpired, FileNotFoundError, OSError, etc.
```

**How to copy:** `_read_gsd_state` replaces the subprocess call with plain file reads (no timeout needed — local filesystem). The same `try/except Exception: return None` outer shell applies. Return a dict (or None on any miss/parse-error) rather than a string. Skeleton:

```python
def _read_gsd_state(planning_dir: str) -> dict | None:
    """Read HANDOFF.json, STATE.md frontmatter, and ROADMAP.md from planning_dir.

    Returns a dict with parsed fields, or None on any missing file / parse error.
    Never raises (RUN-01/RUN-02).
    """
    try:
        handoff_path = os.path.join(planning_dir, "HANDOFF.json")
        state_path   = os.path.join(planning_dir, "STATE.md")
        roadmap_path = os.path.join(planning_dir, "ROADMAP.md")

        with open(handoff_path) as f:
            handoff = json.loads(f.read())

        with open(state_path) as f:
            state_text = f.read()
        # parse YAML frontmatter between --- delimiters (minimal, no dep)
        ...

        with open(roadmap_path) as f:
            roadmap_text = f.read()

        return {
            "handoff": handoff,
            "state":   state_fm,   # parsed frontmatter dict
            "roadmap": roadmap_text,
        }
    except Exception:
        return None   # file missing, JSON/YAML parse error, OS error — omit silently
```

**YAML frontmatter note (planning decision):** STATE.md has a YAML block delimited by `---`. The project avoids non-stdlib parse deps for config (uses `tomllib`). Two options: (a) parse minimally by hand (split on `---`, read `key: value` lines), or (b) use `yaml` if available. The planner must decide; either way the same `try/except Exception: return None` outer guard applies.

---

### `_gsd_segment(data, cfg)` builder

**Analog:** `_git_segment(data, cfg)`, `claude-statusline.py` lines 1456–1556

**Full builder pattern** (lines 1456–1556):
```python
def _git_segment(data: dict, cfg: dict) -> str | None:
    """[<wt-marker?><branch-glyph><branch|sha> <dirty?><ahead/behind?>] or None."""
    try:
        # (1) Config toggle (D-08 discretion: display.show_git, default True)
        if not cfg.get("display", {}).get("show_git", True):
            return None

        # (2) Resolve repo dir: workspace.current_dir → cwd → os.getcwd() (D-08)
        ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
        repo_dir = ws.get("current_dir") or data.get("cwd") or os.getcwd()

        # (3) Fetch git status (timeout-guarded)
        status_out = _run_git(["status", "--porcelain=v2", "--branch"], repo_dir)
        if status_out is None:
            return None   # non-repo / timeout / git absent → omit silently (RUN-01)

        # (4) Parse output
        st = _parse_git_status_v2(status_out)
        if st is None:
            return None

        # (5) [additional data fetch]
        ...

        # (6) Resolve glyphs from icon_set
        icon_set = cfg.get("display", {}).get("icon_set", "nerd")
        if icon_set == "nerd":
            branch_glyph = _NF_GIT_BRANCH
            ...
        else:
            branch_glyph = ""
            ...

        # (7) Build neutral label
        label = f"{branch_glyph}{branch_text}" if branch_glyph else branch_text

        # (8) Colored state markers
        dirty_part = f"{YELLOW}{dirty_glyph}{RESET}" if st["dirty"] else ""

        # (9) Assemble interior
        state_parts = [p for p in [dirty_part, ab_part] if p]
        interior = f"{label} {''.join(state_parts)}" if state_parts else label

        return f"[{interior}]"
    except Exception:
        return None   # RUN-01/RUN-02: never raise, never traceback
```

**How to copy:** Mirror all eight numbered steps exactly. Replace git-specific steps with GSD equivalents:

- Step (1): `cfg.get("display", {}).get("show_gsd", True)` — same config-toggle pattern.
- Step (2): Resolve `project_dir` from `data.get("workspace", {}).get("project_dir", "")` (D-08: use `project_dir`, NOT `current_dir`).
- Step (3): Check for `.planning/` directory under `project_dir`; call `_read_gsd_state(planning_dir)`. Return `None` if absent (silent omit, D-08).
- Step (4): Infer lifecycle state (executing/verifying/blocked/done/idle) from HANDOFF + roadmap.
- Step (6): Glyph resolution — `icon_set == "nerd"` uses `_NF_GSD_*` constants; else emoji/ascii fallbacks.
- Step (7): Neutral label = plan id + task progress, e.g. `"05-02 2/3"`. No color wrap.
- Step (8): Colored status glyph — executing/done → `GREEN`, verifying → `YELLOW`, blocked → `RED`, idle → `DIM`. Pattern: `f"{color}{glyph}{RESET}"`.
- Step (9): Assemble `f"[{plan_label} {wave_part} {status_glyph}]"` (exact interior layout is a planning decision).
- Outer `except Exception: return None` is mandatory — same as git.

**Color constants reuse** (lines 76–80):
```python
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"
RESET  = "\033[0m"
```

Use `GREEN` for executing/done, `YELLOW` for verifying, `RED` for blocked, `DIM` for idle. These are module-level constants — reference directly, no import needed.

---

### `render_top_line` insertion point

**Analog:** `render_top_line`, `claude-statusline.py` lines 1914–1935

**Current assembly** (lines 1928–1934):
```python
segments = [
    _project_segment(data),
    _git_segment(data, cfg),        # D-09: immediately after project, before model
    _model_segment(data, show_thinking_glyph=show_thinking_glyph, icon_set=icon_set),
    _weather_segment(data, cfg),    # None-filtered by the existing space-join (D2-10)
]
present = [s for s in segments if s is not None]
return " ".join(present)
```

**How to copy:** Insert `_gsd_segment(data, cfg)` as the third element, immediately after `_git_segment`. Update the docstring comment to reflect Phase 05 ordering:

```python
segments = [
    _project_segment(data),
    _git_segment(data, cfg),
    _gsd_segment(data, cfg),        # D-10: immediately after git, before model
    _model_segment(data, show_thinking_glyph=show_thinking_glyph, icon_set=icon_set),
    _weather_segment(data, cfg),
]
```

`None` filtering is already handled by `present = [s for s in segments if s is not None]` — no additional wiring needed.

---

### `tests/test_gsd_segment.py`

**Analog:** `tests/test_git_segment.py` (entire file, 803 lines)

**Module loader pattern** (lines 11–26):
```python
import importlib.util
import os
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")

def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

**Fixture pattern** (lines 389–436 — canned status strings + helper functions):
```python
# Canned porcelain-v2 status outputs for each behavior scenario
_CLEAN_MAIN_NO_UPSTREAM = (
    "# branch.oid abc1234\n"
    "# branch.head main\n"
)
_DIRTY_MAIN = (
    "# branch.oid abc1234\n"
    ...
)
```

**How to copy:** Replace git fixtures with GSD planning-file fixtures. Create one dict/string per scenario:

```python
# Canned HANDOFF.json payloads for each lifecycle state
_HANDOFF_EXECUTING = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "partial": False,
    "phase": "05",
    "plan": "05-02",
    "task": "Implement _gsd_segment",
    "total_tasks": 3,
    "status": "executing",
    "completed_tasks": ["task1", "task2"],
    "remaining_tasks": ["Implement _gsd_segment"],
    "blockers": [],
}
_HANDOFF_NULL = {
    "version": "1.0",
    "timestamp": "2026-05-29T20:00:00.000Z",
    "partial": True,
    "phase": None,
    "plan": None,
    "task": None,
    "total_tasks": None,
    "status": "auto-checkpoint",
    "completed_tasks": [],
    "remaining_tasks": [],
    "blockers": [],
}
_HANDOFF_BLOCKED = {
    ...
    "status": "blocked",
    "blockers": ["waiting on external review"],
}
```

**Builder monkeypatch pattern** (lines 439–481):
```python
class TestGsdSegmentBuilder(unittest.TestCase):
    def setUp(self):
        self.mod = _load_script_module()

    def _call(self, handoff=None, state_fm=None, roadmap=None, cfg_override=None):
        """Call _gsd_segment with monkeypatched _read_gsd_state."""
        def fake_read_gsd_state(planning_dir):
            if handoff is None:
                return None
            return {"handoff": handoff, "state": state_fm or {}, "roadmap": roadmap or ""}

        original = self.mod._read_gsd_state
        self.mod._read_gsd_state = fake_read_gsd_state
        try:
            cfg = {
                "display": {"icon_set": "nerd", "show_gsd": True, "bar_style": "shade"},
                "toggles": {"show_thinking_glyph": True},
                "thresholds": {"warn": 70, "crit": 90},
            }
            if cfg_override:
                for k, v in cfg_override.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
            data = {
                "workspace": {"current_dir": "/tmp/fake", "project_dir": "/tmp/fake"},
                "cwd": "/tmp/fake",
            }
            return self.mod._gsd_segment(data, cfg)
        finally:
            self.mod._read_gsd_state = original
```

**Required test cases to cover** (mirroring git segment test set):
- `show_gsd=False` → `None`
- `_read_gsd_state` returns `None` (no `.planning/`) → `None`
- Executing state → contains plan id, GREEN color, executing glyph
- Idle state (null HANDOFF) → contains next-up plan id, DIM color, idle glyph
- Blocked state → contains RED color
- Verifying state → contains YELLOW color
- Milestone-complete (no incomplete plans) → contains done marker, GREEN
- Plan label is neutral — no GREEN or RED on the plan-id text itself (D-09)
- `icon_set='emoji'` → uses emoji/ascii fallbacks, not `_NF_GSD_*` codepoints
- Never raises on edge-case inputs (empty data, None workspace, etc.)
- E2E: piping a project with `.planning/` shows GSD segment between git and model

**E2E test helper** (lines 699–727 — pattern for piping JSON to the script):
```python
def _run_script_e2e(stdin_dict: dict, home: str = _E2E_HOME) -> subprocess.CompletedProcess:
    """Pipe a JSON dict to the script as a subprocess and return the result."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(stdin_dict).encode(),
        capture_output=True,
        env=env,
    )

def _minimal_data(current_dir: str) -> dict:
    """Minimal stdin JSON with workspace.current_dir pointing to current_dir."""
    return {
        "model": {"display_name": "TestModel"},
        "thinking": {"enabled": False},
        "workspace": {
            "current_dir": current_dir,
            "project_dir": current_dir,
            "added_dirs": [],
        },
        "cwd": current_dir,
        "context_window": {"used_percentage": 10},
        "rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": None},
            "seven_day": {"used_percentage": 5, "resets_at": None},
        },
    }
```

For the GSD E2E test, the `project_dir` must point at a directory that actually has a `.planning/` subdirectory. The project's own root (`_REPO_DIR`) qualifies — it has `.planning/HANDOFF.json` present.

---

## Shared Patterns

### Never-raises outer guard
**Source:** `_git_segment`, line 1475 + 1555–1556; `_project_segment`, lines 1444 + 1452–1453
**Apply to:** `_gsd_segment`, `_read_gsd_state`
```python
try:
    ...
except Exception:
    return None   # RUN-01/RUN-02: never raise, never traceback
```

### Config toggle gate (first line of builder body)
**Source:** `_git_segment`, lines 1476–1478
**Apply to:** `_gsd_segment`
```python
if not cfg.get("display", {}).get("show_gsd", True):
    return None
```

### icon_set glyph resolution block
**Source:** `_git_segment`, lines 1501–1514
**Apply to:** `_gsd_segment`
```python
icon_set = cfg.get("display", {}).get("icon_set", "nerd")
if icon_set == "nerd":
    exec_glyph    = _NF_GSD_EXECUTING
    idle_glyph    = _NF_GSD_IDLE
    blocked_glyph = _NF_GSD_BLOCKED
    ...
else:
    exec_glyph    = "▶"    # emoji/ascii fallbacks
    idle_glyph    = "⏸"
    blocked_glyph = "⊘"
    ...
```

### Neutral label + colored state marker composition
**Source:** `_git_segment`, lines 1526–1548
**Apply to:** `_gsd_segment` — plan id + task count are the neutral label; lifecycle glyph is the colored state marker.
```python
# Neutral: plan id + task progress (no color wrap)
label = f"{plan_id} {tasks_done}/{total_tasks}"

# Colored: lifecycle glyph only
status_glyph = f"{color}{glyph}{RESET}"

# Assemble
interior = f"{label} {wave_part} {status_glyph}"
return f"[{interior}]"
```

### workspace.project_dir resolution
**Source:** `_project_segment`, lines 1444–1448 (uses `project_dir`); `_git_segment`, lines 1481–1482 (uses `current_dir`)
**Apply to:** `_gsd_segment` — D-08 explicitly requires `project_dir`, not `current_dir`
```python
ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
project_dir = ws.get("project_dir", "")
if not project_dir:
    return None
planning_dir = os.path.join(project_dir, ".planning")
if not os.path.isdir(planning_dir):
    return None   # non-GSD project — omit silently (D-08)
```

### DEFAULTS display block extension
**Source:** `DEFAULTS`, lines 163–173
**Apply to:** New `show_gsd` key inserted after `show_git`
```python
"display": {
    "icon_set": "nerd",
    "bar_style": "shade",
    "show_git": True,
    "show_gsd": True,   # Phase 05: GSD segment toggle
},
```

---

## No Analog Found

No files in this phase lack a codebase analog. All symbols map cleanly to existing patterns.

---

## Canonical Data Shapes (read from `.planning/` files)

These field shapes are the ground truth for `_read_gsd_state` parsing. Confirmed by reading the actual files.

**HANDOFF.json** (`.planning/HANDOFF.json`):
```json
{
  "version": "1.0",
  "timestamp": "2026-05-29T19:45:36.733Z",
  "source": "auto-postool",
  "partial": true,
  "phase": null,
  "phase_name": null,
  "phase_dir": null,
  "plan": null,
  "task": null,
  "total_tasks": null,
  "status": "auto-checkpoint",
  "completed_tasks": [],
  "remaining_tasks": [],
  "blockers": [],
  "human_actions_pending": [],
  "decisions": [],
  "uncommitted_files": [],
  "next_action": null,
  "context_notes": ""
}
```
Active-execution fields: `plan` (plan id string or null), `task`, `total_tasks`, `status`, `completed_tasks[]`, `remaining_tasks[]`, `blockers[]`, `timestamp`, `partial`.

**STATE.md frontmatter** (between `---` delimiters):
```yaml
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Phase 03.1 inserted, not planned yet
stopped_at: Phase 5 context gathered
last_updated: "2026-05-29T19:43:04.863Z"
progress:
  total_phases: 7
  completed_phases: 5
  total_plans: 13
  completed_plans: 13
  percent: 71
```
Fields relevant to the segment: `progress.completed_plans`, `progress.total_plans`, `progress.percent`, `status`.

**ROADMAP.md** (checkbox line format):
```
- [x] **Phase 4: git info...** (completed 2026-05-29)
- [ ] **Phase 5: GSD status info...**
```
Plan-level checkboxes follow the same `- [x]`/`- [ ]` pattern nested within phase sections. The first `- [ ]` plan checkbox is the roadmap-fallback "next-up" position (D-05/D-06).

---

## Metadata

**Analog search scope:** `claude-statusline.py` (project root), `tests/` directory
**Files scanned:** 3 (claude-statusline.py, tests/test_git_segment.py, tests/fixtures/)
**Pattern extraction date:** 2026-05-29
