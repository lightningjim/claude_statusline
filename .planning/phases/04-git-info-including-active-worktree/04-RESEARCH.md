# Phase 4: git info including active worktree - Research

**Researched:** 2026-05-29
**Domain:** Git CLI introspection from Python (subprocess), statusline segment rendering
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Segment shows three fields: branch name, a dirty/clean indicator, and ahead/behind upstream. Short SHA and stash count are NOT standalone fields in v1.
- **D-02:** Dirty state renders as a single marker (one glyph when the working tree has uncommitted changes — modified/staged/untracked combined — nothing when clean). No per-type file counts.
- **D-03:** Worktree marker is surfaced ONLY when the session is inside a linked worktree (a `git worktree add` checkout). The main checkout shows just branch + state.
- **D-04:** When in a linked worktree, label it with the worktree directory basename (with a worktree glyph), e.g. `⑂ feature-x` — distinct from and in addition to the branch name.
- **D-05:** Read git state by shelling out to `git` (subprocess) — `rev-parse`, `status --porcelain`, worktree introspection. Adds a `subprocess` import (note: `subprocess` is ALREADY imported in the file — line 67). git's own logic is authoritative.
- **D-06:** Wrap git calls in a hard timeout (target ~150ms). On timeout or any error, the segment omits silently (returns `None`). The bar must never hang on git.
- **D-07:** Run git every render, timeout-guarded — NO caching. (Contrast with weather, which IS cached.)
- **D-08:** Resolve "the repo" from `workspace.current_dir`, falling back to `cwd` when absent. NOT `project_dir` — a linked worktree lives outside the project root.
- **D-09:** Place the git segment on the top line, immediately after the project name: `[project] [git] [model 💭] [weather]`.
- **D-10:** Color the state, keep the branch neutral. Branch/worktree label neutral; dirty marker and ahead/behind markers colored (reuse `color_for` / existing color conventions — e.g. dirty → yellow). Not a whole-segment wash.

### Claude's Discretion
- Glyphs follow `icon_set` (nerd primary, emoji fallback) — same single toggle that governs every other segment; choose specific git/branch/worktree glyphs during planning consistent with the existing nerd set.
- Detached HEAD: show the short SHA in the branch slot (the "branch field" gracefully degrades to a SHA).
- Ahead/behind rendering: exact form (`↑N↓M`, spacing, hide-when-zero, behavior with no upstream) is a planning detail; omit cleanly when there's no tracked upstream.
- Separator / spacing follows the existing top-line segment style.
- Exact timeout value (~150ms) is tunable; pick a safe default and consider a config knob only if it falls out naturally.
- Config toggle for the segment should follow the `display.*` pattern (e.g. a `show_git` toggle alongside `show_weather`); naming at planning time.

### Deferred Ideas (OUT OF SCOPE)
- Standalone short-SHA and stash-count fields — left out of v1 (D-01).
- Per-type dirty counts (`+3 ~2`) — deferred in favor of the single marker (D-02).
- Git actions / commit-log / history / multi-repo views — out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

This phase predates formal requirement IDs in REQUIREMENTS.md (the git segment is an enhancement, like Phase 3, with scope driven entirely by CONTEXT.md D-01..D-10). No new REQ-IDs were supplied by the orchestrator. The two project-wide runtime requirements still bind:

| ID | Description | Research Support |
|----|-------------|------------------|
| RUN-01 | Reads stdin, writes stdout, exits fast | Hard 150ms timeout on git subprocess + never-block contract (see Architecture, Pitfall 1) |
| RUN-02 | Missing/malformed input never crashes the bar | `_git_segment` returns None on any error; all git calls wrapped in try/except (see Code Examples) |

The planner should NOT invent new REQ-IDs; track this phase's scope against D-01..D-10 from CONTEXT.md as Phase 3 did.
</phase_requirements>

## Summary

Everything needed for this phase is available from the `git` CLI already installed (verified `git version 2.53.0`). The entire git state — branch name (or detached state), dirty/clean, and ahead/behind upstream — comes from a SINGLE invocation of `git -C <dir> status --porcelain=v2 --branch`. Worktree detection needs ONE additional cheap invocation (`git -C <dir> rev-parse --absolute-git-dir --git-common-dir --show-toplevel`). So the whole feature is two git subprocess calls per render, both timeout-guarded — comfortably within the 150ms budget on a local repo (typical cold run is single-digit milliseconds; large worktrees with thousands of dirty files are the only realistic slow case, which the timeout covers).

The codebase already has every pattern this phase needs: per-segment builders that return `str | None` (`_project_segment`, `_model_segment`), `cfg` threaded as an explicit param, `color_for`/`GREEN`/`YELLOW`/`RED`/`RESET` constants, the `icon_set` nerd/emoji toggle resolved at render time, `display.*` config keys with `_deep_merge`, and — critically — `subprocess` is ALREADY imported (line 67, added for `maybe_spawn_refresh`). The new builder `_git_segment(data, cfg)` slots into `render_top_line` between `_project_segment(data)` and `_model_segment(...)`.

**Primary recommendation:** Implement `_git_segment(data, cfg)` backed by two helpers: a `_run_git(args, cwd, timeout)` wrapper using `subprocess.run(..., capture_output=True, text=True, timeout=...)` inside a try/except that returns `None` on `TimeoutExpired`/`CalledProcessError`/`OSError`/any exception; and a pure parser `_parse_git_status_v2(stdout)` that extracts branch/detached/dirty/ahead/behind from the porcelain-v2 header lines. Detect a linked worktree by comparing the real paths of `--absolute-git-dir` and `--git-common-dir` (they diverge only inside a linked worktree). Resolve the repo dir from `workspace.current_dir` then `cwd` (D-08). Run git every render, no cache (D-07).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Determine repo directory | Render path (`_git_segment`) | stdin (`workspace.current_dir`/`cwd`) | D-08: directory comes from session JSON; segment owns the fallback logic |
| Read git state (branch/dirty/ahead-behind) | Local `git` CLI subprocess | — | D-05: git is authoritative; no reimplementation in Python |
| Detect linked worktree | Local `git` CLI subprocess | — | git-dir/common-dir divergence is the canonical, version-stable signal |
| Timeout / never-hang guard | `_run_git` wrapper (`subprocess.run(timeout=)`) | — | D-06/RUN-01: render path must never block |
| Parse porcelain output | Pure Python parser (`_parse_git_status_v2`) | — | Pure function = unit-testable without a real repo |
| Color/glyph rendering | `_git_segment` + existing `color_for`/`icon_set` | DEFAULTS config | D-10/discretion: reuse established color + glyph machinery |
| Config toggle | `DEFAULTS["display"]` + `_deep_merge` | — | Mirrors `show_weather`/`bar_style` precedent |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `subprocess` (stdlib) | Python 3.14 | Shell out to `git` with a hard timeout | Already imported (line 67); `subprocess.run(timeout=)` is the canonical never-hang idiom [VERIFIED: codebase grep + Python docs] |
| `os` / `os.path` (stdlib) | Python 3.14 | `os.path.basename`, `os.path.realpath` for worktree label + path divergence test | Already imported (line 22); matches `_project_segment`'s `os.path.basename` usage [VERIFIED: codebase] |
| `git` CLI | 2.53.0 installed | Authoritative branch/dirty/ahead-behind/worktree state | D-05 locked; porcelain formats are explicitly stability-guaranteed by git [VERIFIED: `git --version`] [CITED: git-status(1) "Porcelain Format Version 2"] |

### Supporting
No third-party packages. This phase adds ZERO dependencies. (Unlike weather, no `requests`/`astral` involvement, no venv concern — git is a plain external binary.)

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `git` subprocess | `pygit2` / `GitPython` | Rejected by D-05 (locked on subprocess) AND adds a dependency + venv-availability concern. git CLI is authoritative and already present. |
| Single `status --porcelain=v2 --branch` call | Separate `rev-parse --abbrev-ref HEAD` + `status --porcelain` + `rev-list --count` calls | Multi-call is 3-4× the process spawns within the 150ms budget and reintroduces detached/no-upstream special-casing that v2 already encodes in its header. Single call is strictly better (see Pitfall 4). |
| `--porcelain=v2` | `--porcelain` (v1) / `--porcelain=v1 -b` | v1's branch header (`## main...origin/main [ahead 1]`) is human-text and harder to parse robustly; v2's `# branch.*` key/value header lines are designed for machine parsing. [CITED: git-status(1)] |

**Installation:**
```bash
# No installation. git is already present (git version 2.53.0) and subprocess/os are stdlib.
```

**Version verification:** Confirmed locally — `git version 2.53.0` [VERIFIED: Bash `git --version`]. The porcelain-v2 format and `rev-parse --absolute-git-dir`/`--git-common-dir` flags have existed since git 2.13 (2017), far below the installed version, so no version gating is needed for this single-user tool.

## Package Legitimacy Audit

> No external packages are installed by this phase. Only stdlib (`subprocess`, `os`) and the already-present `git` binary are used. Package Legitimacy Gate is N/A.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
stdin JSON ──> _load_stdin() ──> data{}
                                   │
                                   ▼
                          render_top_line(data, cfg)
                                   │
        ┌──────────────┬──────────┴───────────┬───────────────┐
        ▼              ▼                        ▼               ▼
 _project_segment  _git_segment(data,cfg)  _model_segment  _weather_segment
   (basename)          │                                       (cached)
                       │ resolve dir: workspace.current_dir → cwd (D-08)
                       ▼
              ┌─────────────────────────────────────────────┐
              │  _run_git(["status","--porcelain=v2",        │
              │            "--branch"], dir, timeout≈0.15)   │──timeout/err──> None ──> segment omitted
              │  _run_git(["rev-parse","--absolute-git-dir", │
              │            "--git-common-dir","--show-toplevel"], dir) │
              └─────────────────────────────────────────────┘
                       │ stdout
                       ▼
              _parse_git_status_v2(stdout)  (pure, unit-testable)
                       │  → branch | detached-sha, dirty?, ahead, behind
                       ▼
              worktree test: realpath(absolute-git-dir) != realpath(common-dir)
                       │  → linked? worktree-basename = basename(show-toplevel)
                       ▼
              assemble: [<wt-glyph wt-name> ]<branch-glyph><branch-neutral> <dirty?><ahead/behind?>
                       │  branch neutral (D-10); dirty/ab colored; glyphs per icon_set
                       ▼
              "[ main]"  /  "[ main ✚ ↑2]"  /  "[⑂ feature  feat]"  (None on non-repo)
```

### Recommended Project Structure
```
claude-statusline.py        # single-file project — ALL code goes here (no new files)
├── _run_git(...)           # NEW: subprocess wrapper, timeout-guarded, returns str|None
├── _parse_git_status_v2()  # NEW: pure parser of porcelain-v2 header → dict
├── _detect_linked_worktree()  # NEW: path-divergence test → (is_linked, wt_basename) | None
├── _git_segment(data, cfg) # NEW: the builder — orchestrates the above, returns str|None
└── render_top_line(...)    # EDIT: insert _git_segment between project and model
tests/test_git_segment.py   # NEW: mirrors tests/ conventions
```

### Pattern 1: Per-segment builder returning `str | None`
**What:** Each top-line segment is a function `(data[, cfg]) -> str | None`; returning `None` omits it from the space-join in `render_top_line`. The existing `present = [s for s in segments if s is not None]` filter handles omission with zero extra code.
**When to use:** Always for this segment — it is exactly how `_project_segment`, `_model_segment`, `_weather_segment` already work.
**Example:**
```python
# Source: claude-statusline.py:1268-1279 (_project_segment) — the canonical shape to mirror
def _project_segment(data: dict) -> str | None:
    try:
        project_dir = data.get("workspace", {}).get("project_dir", "")
        if not project_dir:
            return None
        basename = os.path.basename(project_dir.rstrip("/"))
        if not basename:
            return None
        return f"[{basename}]"
    except Exception:
        return None
```

### Pattern 2: Hard-timeout subprocess that never raises (the never-hang contract)
**What:** `subprocess.run(args, capture_output=True, text=True, timeout=<seconds>)` wrapped in try/except returning `None` on ANY exception (notably `subprocess.TimeoutExpired`, plus `OSError` if git is absent, plus `CalledProcessError` if you pass `check=True`).
**When to use:** Every git call on the render path (D-06).
**Example:**
```python
# Source: Python docs subprocess.run / timeout semantics [CITED: docs.python.org/3/library/subprocess.html]
def _run_git(args: list[str], cwd: str, timeout: float = 0.15) -> str | None:
    """Run `git <args>` in cwd; return stdout text or None on any failure/timeout.

    Never raises (RUN-01/RUN-02). On TimeoutExpired the child is killed by
    subprocess.run before the exception propagates, so the render path is freed
    within `timeout` seconds and the segment omits silently.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None          # non-repo (rc=128), empty-repo HEAD failures, etc.
        return proc.stdout
    except Exception:
        return None              # TimeoutExpired, FileNotFoundError (no git), OSError, ...
```
**Note on timeout granularity:** `subprocess.run(timeout=)` accepts a float in seconds; `0.15` = 150ms. On timeout, `run()` kills the process and then raises `TimeoutExpired` — verified behavior; the `except` swallows it. Use `git -C <cwd>` rather than the `cwd=` kwarg so a non-existent directory degrades through git's own error (rc≠0) rather than an `os.chdir` failure (both paths return None anyway, but `-C` keeps the working directory of the parent untouched).

### Pattern 3: Resolve repo dir from stdin with fallback (D-08)
```python
# D-08: workspace.current_dir, fallback cwd. NOT project_dir (worktrees live outside it).
ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
repo_dir = ws.get("current_dir") or data.get("cwd") or os.getcwd()
```
Fixture confirms both fields exist: `workspace.current_dir` and top-level `cwd` are both present in `.examples/claude_stdin.json` [VERIFIED: Bash python3 fixture read]. `gitBranch` IS present in the fixture but EMPTY (`""`) and per CONTEXT code-context note it gives branch-only with no dirty/worktree info — so do NOT rely on it; git introspection is required for the headline feature.

### Pattern 4: icon_set glyph resolution at render time
**What:** Read `cfg["display"]["icon_set"]` (default `"nerd"`) inside the builder and pick nerd vs emoji glyphs, exactly like `_model_segment` / `_rate_segment` call sites.
**Example:**
```python
# Source: claude-statusline.py:1684-1693 (rate glyph resolution) — mirror this shape
icon_set = cfg.get("display", {}).get("icon_set", "nerd")
if icon_set == "nerd":
    branch_glyph, wt_glyph, dirty_glyph = _NF_GIT_BRANCH, _NF_GIT_WORKTREE, _NF_GIT_DIRTY
else:
    branch_glyph, wt_glyph, dirty_glyph = "", "⑂", "✚"   # emoji/ascii fallbacks
```

### Anti-Patterns to Avoid
- **Caching git state:** D-07 explicitly forbids it. Branch/dirty change constantly; a cache lags reality right after a commit/switch. Run git every render. (This is the opposite of the weather pattern — do NOT copy `read_cache`/`maybe_spawn_refresh`.)
- **Spawning a detached background process for git:** unnecessary — git is local and fast; the timeout guard replaces the detach pattern (CONTEXT "git uses a timeout guard instead (local, so no detach needed)").
- **Multiple git invocations for branch/dirty/ahead-behind:** one `status --porcelain=v2 --branch` returns all three. Extra calls waste the budget and reintroduce edge-case branching.
- **Parsing `git status` human output / `--porcelain=v1`:** use v2's `# branch.*` machine header.
- **Letting any git error reach the caller:** wrap everything; return `None`. RUN-01/RUN-02 are project-wide non-negotiables (note the whole file's bare-`except Exception` discipline).
- **Coloring the whole segment:** D-10 — branch label neutral, only state markers colored.
- **Using `subprocess.Popen` + manual `.communicate(timeout=)`:** works but `subprocess.run(timeout=)` is the higher-level idiom already proven sufficient; Popen is only needed for the fire-and-forget weather child.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Branch name / detached detection | Read `.git/HEAD` and parse `ref:` | `git status --porcelain=v2 --branch` → `# branch.head` | git handles packed-refs, detached, rebases, bisect, worktree HEADs correctly |
| Dirty/clean detection | `os.walk` + mtime/diff | porcelain-v2 file lines (any present line = dirty) | git respects `.gitignore`, submodules, assume-unchanged, sparse-checkout |
| Ahead/behind counts | `git rev-list --count A..B` parsing + upstream resolution | `# branch.ab +N -M` line from the same status call | One line, already computed, absent-when-no-upstream is a clean signal |
| Linked-worktree detection | Scan `.git/worktrees/` dir | Compare realpath of `--absolute-git-dir` vs `--git-common-dir` | Canonical, version-stable, single rev-parse call; no filesystem walking |
| Worktree label | Parse `git worktree list` output | `basename(git rev-parse --show-toplevel)` | One value, no list parsing; equals the dir name the user thinks in (D-04) |
| Process timeout | `signal.alarm` / threads | `subprocess.run(timeout=)` | Cross-platform, kills the child, raises a catchable exception |

**Key insight:** git's porcelain-v2 `--branch` header was purpose-built to give a status-line tool exactly branch + upstream + ahead/behind + dirty in one parse. Reimplementing any of it in Python re-creates bugs git already solved. The only Python logic that should exist is (a) the timeout wrapper, (b) a thin header parser, (c) the path-divergence worktree test, (d) glyph/color assembly.

## Common Pitfalls

### Pitfall 1: A pathological repo blows the render budget
**What goes wrong:** A worktree with tens of thousands of modified/untracked files makes `git status` take >150ms, stalling the bar.
**Why it happens:** `status` scans the working tree; huge dirty trees are slow.
**How to avoid:** The `timeout=0.15` on `subprocess.run` caps it — on timeout the segment omits (`None`) and the rest of the bar renders. Do NOT raise the timeout to "be safe"; the whole point is bounded latency. (Optional, NOT required by CONTEXT: `git status --porcelain=v2 --branch --untracked-files=no` is faster but would make dirty miss untracked-only states, contradicting D-02's "untracked combined" — so keep untracked on.)
**Warning signs:** Bar visibly lags when cwd is a giant repo.

### Pitfall 2: Empty repo (freshly `git init`, no commits) has no HEAD
**What goes wrong:** `rev-parse HEAD` / `--short HEAD` fails (rc=128, "ambiguous argument 'HEAD'") on a repo with zero commits. [VERIFIED: Bash empty-repo probe]
**Why it happens:** HEAD points at an unborn branch.
**How to avoid:** Get the branch from `# branch.head` in porcelain-v2 (which still prints the unborn branch name, e.g. `main`, with `# branch.oid (initial)`) rather than from `rev-parse HEAD`. For the detached-HEAD short-SHA fallback (discretion), source the SHA from `# branch.oid` — but guard: if `branch.oid` is `(initial)`, there is no SHA, so show the (unborn) `branch.head` name instead of crashing. [VERIFIED: probe shows `# branch.oid (initial)` + `# branch.head main`]
**Warning signs:** Segment vanishes or errors only in brand-new repos.

### Pitfall 3: No upstream configured → no ahead/behind lines
**What goes wrong:** Expecting a `# branch.ab` line that isn't there → `KeyError`/index error.
**Why it happens:** porcelain-v2 omits BOTH `# branch.upstream` and `# branch.ab` when the branch has no tracking upstream. [VERIFIED: no-upstream probe]
**How to avoid:** Treat missing `branch.upstream`/`branch.ab` as "no upstream" and omit the ahead/behind chunk cleanly (matches the discretion note "omit cleanly when there's no tracked upstream"). Parser should default ahead/behind to `None`, not `0`.
**Warning signs:** Crash or spurious `↑0↓0` on local-only branches.

### Pitfall 4: Detached HEAD has no branch name
**What goes wrong:** Trying to show a branch name when there is none.
**Why it happens:** `# branch.head` literally reads `(detached)` in detached state. [VERIFIED: detach probe]
**How to avoid:** When `branch.head == "(detached)"`, fall back to the short SHA from `# branch.oid` (first 7-8 chars) per the discretion decision. Detached + no upstream is normal, so also expect no `branch.ab`.
**Warning signs:** Literal `(detached)` text leaking into the bar.

### Pitfall 5: `git` binary absent on PATH
**What goes wrong:** `FileNotFoundError` from subprocess.
**Why it happens:** git not installed / not on PATH (unlikely on dev box, but RUN-02 demands tolerance).
**How to avoid:** The blanket `except Exception` in `_run_git` already catches `FileNotFoundError` → returns `None` → segment omits. No separate availability check needed (do not pre-probe with `shutil.which`; just let the call fail closed).
**Warning signs:** Traceback on a machine without git (caught by the never-crash tests).

### Pitfall 6: Worktree path comparison fooled by symlinks / relative paths
**What goes wrong:** `--git-common-dir` can be returned as a RELATIVE path (e.g. `.git`) or contain `/../` segments (verified: linked worktree common-dir came back as `.../worktrees/wt-feature/../..`), so a naive string `==` between git-dir and common-dir mis-detects.
**Why it happens:** git returns these paths in mixed absolute/relative forms depending on flag and cwd. [VERIFIED: worktree probe — common-dir had `/../..`]
**How to avoid:** Normalize BOTH with `os.path.realpath(...)` before comparing. In the MAIN checkout they resolve EQUAL; in a LINKED worktree they DIVERGE (git-dir = `.../​.git/worktrees/<name>`, common-dir = `.../​.git`). Equivalently/more simply: linked iff `"/.git/worktrees/" in os.path.realpath(absolute_git_dir)`. Recommend the realpath-inequality test as primary, with the substring as a sanity cross-check during planning. [VERIFIED: both signals observed in probe]
**Warning signs:** Worktree marker showing in the main checkout, or missing in a real linked worktree.

## Code Examples

### One-call status read (branch + dirty + ahead/behind)
```bash
# Source: git-status(1) "Porcelain Format Version 2"; output VERIFIED in-repo
$ git -C <dir> status --porcelain=v2 --branch
# branch.oid 643e8c6b8145a4995b073cfcd89b364b29eda840
# branch.head main
# branch.upstream origin/main      # absent if no upstream
# branch.ab +40 -0                 # absent if no upstream; +ahead -behind
1 .M N... 100644 100644 100644 <oid> <oid> .planning/HANDOFF.json   # any '1'/'2'/'u'/'?' line ⇒ dirty
```

### Pure parser (unit-testable without a real repo)
```python
def _parse_git_status_v2(stdout: str) -> dict | None:
    """Parse `status --porcelain=v2 --branch` stdout → state dict, or None if unparseable.

    Returns: {"branch": str|None, "detached": bool, "oid": str|None,
              "dirty": bool, "ahead": int|None, "behind": int|None}
    Never raises.
    """
    try:
        branch = None; oid = None; detached = False
        ahead = behind = None; dirty = False
        for line in stdout.splitlines():
            if line.startswith("# branch.head "):
                head = line[len("# branch.head "):].strip()
                if head == "(detached)":
                    detached = True
                else:
                    branch = head
            elif line.startswith("# branch.oid "):
                val = line[len("# branch.oid "):].strip()
                oid = None if val == "(initial)" else val
            elif line.startswith("# branch.ab "):
                # format: "+N -M"
                parts = line[len("# branch.ab "):].split()
                for p in parts:
                    if p.startswith("+"): ahead = int(p[1:])
                    elif p.startswith("-"): behind = int(p[1:])
            elif line[:2] in ("1 ", "2 ", "u ") or line.startswith("? "):
                dirty = True
        return {"branch": branch, "detached": detached, "oid": oid,
                "dirty": dirty, "ahead": ahead, "behind": behind}
    except Exception:
        return None
```

### Worktree detection (one rev-parse call)
```bash
# Source: git-rev-parse(1); divergence VERIFIED in-repo
$ git -C <dir> rev-parse --absolute-git-dir --git-common-dir --show-toplevel
# MAIN checkout:  /repo/.git   /repo/.git   /repo                 (git-dir == common-dir)
# LINKED wt:      /repo/.git/worktrees/feat   /repo/.git/worktrees/feat/../..   /repo-feat
#                 → realpath(line1) != realpath(line2)  ⇒ linked; basename(line3) = "repo-feat"
```
```python
def _detect_linked_worktree(rev_parse_stdout: str) -> tuple[bool, str | None]:
    """Return (is_linked, worktree_basename). Never raises."""
    try:
        lines = rev_parse_stdout.splitlines()
        if len(lines) < 3:
            return (False, None)
        git_dir   = os.path.realpath(lines[0].strip())
        common    = os.path.realpath(lines[1].strip())
        toplevel  = lines[2].strip()
        is_linked = git_dir != common
        name = os.path.basename(toplevel.rstrip("/")) if toplevel else None
        return (is_linked, name)
    except Exception:
        return (False, None)
```

### Builder skeleton (assembles per D-01..D-10)
```python
def _git_segment(data: dict, cfg: dict) -> str | None:
    """[<wt?> <branch|sha> <dirty?> <ahead/behind?>] for the session repo, or None.

    D-08 dir resolution; D-05/D-06 git via timeout-guarded subprocess; D-07 no cache;
    D-10 neutral branch + colored state; icon_set glyphs. Never raises (RUN-01/02).
    """
    try:
        # config toggle (discretion: display.show_git, default True)
        if not cfg.get("display", {}).get("show_git", True):
            return None
        ws = data.get("workspace", {}) if isinstance(data.get("workspace"), dict) else {}
        repo_dir = ws.get("current_dir") or data.get("cwd") or os.getcwd()

        status_out = _run_git(["status", "--porcelain=v2", "--branch"], repo_dir)
        if status_out is None:
            return None                      # non-repo / timeout / no git → omit
        st = _parse_git_status_v2(status_out)
        if st is None:
            return None

        rp_out = _run_git(["rev-parse", "--absolute-git-dir",
                           "--git-common-dir", "--show-toplevel"], repo_dir)
        is_linked, wt_name = _detect_linked_worktree(rp_out or "")

        icon_set = cfg.get("display", {}).get("icon_set", "nerd")
        # ... pick glyphs by icon_set; build neutral branch label
        #     (branch or short oid if detached); colored dirty marker (YELLOW);
        #     colored ahead/behind only when st["ahead"]/["behind"] is not None;
        #     prepend "<wt_glyph> <wt_name> " only when is_linked and wt_name (D-03/D-04).
        # ... return f"[{...}]"
    except Exception:
        return None
```

### Integration into render_top_line (one-line insert)
```python
# Source: claude-statusline.py:1648-1652 — insert _git_segment between project and model (D-09)
segments = [
    _project_segment(data),
    _git_segment(data, cfg),          # NEW — D-09: immediately after project
    _model_segment(data, show_thinking_glyph=show_thinking_glyph, icon_set=icon_set),
    _weather_segment(data, cfg),
]
```

## Runtime State Inventory

> Greenfield-style feature addition to a single file; no rename/refactor/migration. The categories below are answered for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — feature reads live git state every render, persists nothing (D-07 forbids caching). | none |
| Live service config | None — no external service; git is a local binary. | none |
| OS-registered state | None. | none |
| Secrets/env vars | None — no new env vars or secrets. (Existing `CLAUDE_STATUSLINE_FAKE_ALERTS` is weather-only and unrelated.) | none |
| Build artifacts | None — single-file script; no package rebuild. `pyproject.toml` deps unchanged (no new dependency). | none |

## Common Pitfalls Cross-check: ASVS / Security

See Security Domain below — the only security-relevant surface is subprocess argument construction (fixed argv, no shell), which the design already enforces.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `git status --porcelain` (v1) human-ish branch header | `--porcelain=v2 --branch` machine `# branch.*` lines | git 2.11/2.13 (2017) | Robust single-call parse; what modern statusline tools (starship, posh-git) use |
| `signal.alarm` for timeouts | `subprocess.run(timeout=)` | Python 3.3+ | Cross-platform, kills child, catchable; no signal-handler fragility |
| `git symbolic-ref`/read `.git/HEAD` for branch | porcelain-v2 `# branch.head` | git 2.13 | Handles detached/unborn/worktree uniformly |

**Deprecated/outdated:** none relevant. `--porcelain` (v1) is not deprecated but v2 is preferred for new machine consumers.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Specific Nerd Font codepoints for git-branch / worktree / dirty glyphs are NOT yet chosen — planner picks them consistent with the existing `_WI_*`/`_NF_*` set and validates against the installed font (the repo has a fontTools cmap guard test, `test_nerd_icons.py`). | Standard Stack / Pattern 4 | Wrong/missing glyph renders as tofu; mitigated by the existing cmap guard test the planner should extend. Tagged [ASSUMED] — glyph choice is open discretion, confirm during planning. |
| A2 | 150ms is an adequate default timeout for the user's repos. | Pitfall 1 | If user routinely works in a multi-GB monorepo worktree the segment may often omit; tunable per discretion. [ASSUMED] |
| A3 | `display.show_git` is the chosen config key name. | Builder skeleton | Cosmetic; CONTEXT marks naming as discretion. [ASSUMED] |

## Open Questions

1. **Exact ahead/behind glyph form (`↑2↓1` vs `⇡2⇣1`, hide-when-zero, color split).**
   - What we know: data (ahead/behind ints or None) comes free from `# branch.ab`; D-10 says color the markers.
   - What's unclear: visual form is explicit discretion.
   - Recommendation: planner decides; suggest `↑N` (GREEN-ish/neutral) and `↓N` (YELLOW) only when the count > 0, omit the whole chunk when no upstream.

2. **Should the dirty marker color be YELLOW (matching `color_for` warn) or a dedicated color?**
   - What we know: D-10 example explicitly says "dirty → yellow"; `YELLOW` constant exists.
   - Recommendation: use `YELLOW` for dirty — directly satisfies D-10's worked example.

3. **Nerd Font glyph codepoints (A1).** Resolve at planning against `test_nerd_icons.py`'s installed-font cmap so no tofu ships.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `git` CLI | All git state (D-05) | ✓ | 2.53.0 | Segment omits (None) via `_run_git` exception path — bar still renders |
| `subprocess` (stdlib) | Timeout-guarded calls | ✓ | py3.14 | — (already imported, line 67) |
| `os.path.realpath`/`basename` | Worktree test + label | ✓ | py3.14 | — (already imported) |
| Nerd Font (terminal) | nerd glyphs | ✓ (per Phase 02.1 install) | — | `icon_set="emoji"`/ascii fallbacks already in design |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `git` — if absent, segment silently omits (RUN-02 honored).

## Validation Architecture

> `workflow.nyquist_validation` is `false` in `.planning/config.json`. Section intentionally omitted per the skip rule. (Test guidance is still provided below under Testing, since the project has an established `tests/` suite and `code_review: true`.)

### Testing (project convention, not Nyquist)
The repo's tests run the script as a subprocess piping JSON (`tests/test_skeleton_render.py`, `tests/test_bottom_line.py`) AND import it as a module to unit-test helpers (`_load_script_module` via `importlib.util` in `test_bottom_line.py`). For the git segment, recommend a NEW `tests/test_git_segment.py` with three layers:

1. **Pure-parser unit tests** (no git, no mocking): feed canned `--porcelain=v2 --branch` strings to `_parse_git_status_v2` and `_detect_linked_worktree` — cover clean, dirty, detached, unborn/`(initial)`, no-upstream, ahead/behind. Fast and deterministic. (The canned strings in this doc's Code Examples are VERIFIED real git output and can be used as fixtures.)
2. **Builder tests via monkeypatching `_run_git`** (import the module, monkeypatch the module-level `_run_git` to return canned stdout/None) — verify segment assembly, neutral-branch/colored-state (D-10), worktree marker only when linked (D-03/D-04), icon_set glyph swap, and `None` on non-repo.
3. **Real-repo integration test using `tempfile` + actual `git`** (mirrors the probes in this research): `git init`, commit, `git worktree add`, then assert the segment text — gated/skipped if `git` is unavailable. Also a never-crash test: point at a non-repo dir and assert exit 0 / no traceback (matches existing `test_empty_stdin_exits_zero_no_traceback` style).

Run command (repo convention): `python3 -m pytest tests/test_git_segment.py -x`.

## Security Domain

> `security_enforcement` not present in config; treated as default. The only security-relevant surface is subprocess execution.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation / Injection | yes | Fixed argv list (`["git","-C",cwd,*args]`) passed to `subprocess.run` WITHOUT `shell=True` — no shell interpolation possible. `cwd` comes from stdin but is only ever an argument to `-C`, never concatenated into a shell string. Mirrors the existing `maybe_spawn_refresh` fixed-argv discipline (T-02-08). |
| V2 Authentication | no | n/a — read-only local git introspection |
| V6 Cryptography | no | n/a |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via attacker-controlled cwd/branch name | Tampering / EoP | No `shell=True`; argv is a fixed list; output is read, never re-executed. Branch names containing shell metacharacters are inert (they're just printed). |
| Hang / resource exhaustion from a pathological repo | Denial of Service | `subprocess.run(timeout=0.15)` bounds runtime; child killed on timeout. (RUN-01) |
| Output spoofing (branch name with ANSI escapes leaking into the bar) | Tampering | LOW risk for a personal tool; planner MAY strip control chars from the branch label, but this is not required by CONTEXT. Note as optional hardening. |

## Sources

### Primary (HIGH confidence)
- `claude-statusline.py` (read in full, 1743 lines) — segment patterns (`_project_segment` L1268, `_model_segment` L1282, `render_top_line` L1637), `subprocess` import L67, `color_for`/constants L76-88/L1177, `icon_set` resolution L1684, fixed-argv subprocess L1160.
- Live git probes (Bash, `git version 2.53.0`): `status --porcelain=v2 --branch` output; `rev-parse --absolute-git-dir --git-common-dir --show-toplevel` divergence in main vs linked worktree; non-repo rc=128; empty-repo `(initial)`/HEAD failure; no-upstream omitted `branch.ab`; detached `(detached)`.
- `.examples/claude_stdin.json` — confirmed `workspace.current_dir`, `cwd` present; `gitBranch` present but empty.
- `tests/test_skeleton_render.py`, `tests/test_bottom_line.py` — subprocess + `importlib` test conventions.
- `.planning/phases/04-git-info-including-active-worktree/04-CONTEXT.md` — locked decisions D-01..D-10.
- git-status(1) "Porcelain Format Version 2" and git-rev-parse(1) — format/flag semantics [CITED].
- Python `subprocess` docs — `run(timeout=)` kills child then raises `TimeoutExpired` [CITED: docs.python.org/3/library/subprocess.html].

### Secondary (MEDIUM confidence)
- Worktree git-dir/common-dir divergence as the canonical linked-worktree test — corroborated by the live probe (PRIMARY) and matches common practice in statusline tools.

### Tertiary (LOW confidence)
- None. All load-bearing claims were verified against live git output or the codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — git present + verified; zero new deps; subprocess already imported.
- Architecture: HIGH — directly mirrors three existing segment builders and the fixed-argv subprocess pattern already in the file.
- Git command behavior/edge cases: HIGH — every edge case (non-repo, empty repo, detached, no upstream, linked worktree) was empirically probed with the installed git 2.53.0.
- Glyph codepoints: MEDIUM — specific nerd glyphs left to planning (A1), validated by existing cmap guard test.

**Research date:** 2026-05-29
**Valid until:** 2026-06-28 (stable — git CLI formats and stdlib subprocess are long-stable; only the glyph-codepoint decision is open)
