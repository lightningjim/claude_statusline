---
phase: 01-core-statusline
reviewed: 2026-05-28T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - claude-statusline.py
  - install.py
  - tests/test_skeleton_render.py
  - tests/test_bottom_line.py
  - tests/test_config.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-28
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The Phase 1 implementation is functionally solid for the happy path. The core requirements — stdlib-only (no `requests`), `tomllib` config, graceful stdin handling, ANSI bar rendering, per-segment toggles — are all correctly implemented. The `main()` entry point is safe: all segment builders are wrapped in `except Exception`, so no uncaught exception can reach the caller.

Three areas have real defects:

1. **Context bar overflows 20 chars** when `used_percentage` exceeds 104 (rendering corruption, not a crash).
2. **`pct_int` silently drops `OverflowError`** for infinity-valued inputs, relying on callers to absorb the exception rather than handling it explicitly — a fragile contract.
3. **Test infrastructure manipulates the live user config** (`~/.claude/claude-statusline.toml`) without ensuring the target directory exists and with a teardown path that can orphan the backup on write failure.

---

## Critical Issues

### CR-01: Context bar renders more than 20 characters when `used_percentage` > 104

**File:** `claude-statusline.py:245-247`
**Issue:** `_context_segment` computes `filled = math.floor(pct * 20 / 100)` and `empty = 20 - filled`. When `pct >= 105`, `filled >= 21` and `empty` is negative. Python's `str * negative` is `""`, so `_EMPTY * empty` is silently discarded and the bar string grows beyond 20 characters. At `pct=150` the bar is 30 characters wide, corrupting terminal layout.

JSON's `json.loads` converts `1e309` to `float('inf')`, but any integer `>= 105` in `used_percentage` triggers the overflow. While Claude Code should never send `>= 105`, no guard exists, and the contract says the output must never be visually broken.

**Fix:**
```python
filled = min(_BAR_WIDTH, math.floor(pct * _BAR_WIDTH / 100))
empty  = _BAR_WIDTH - filled
```
This clamps `filled` to `_BAR_WIDTH` so `empty` is always `>= 0` and the bar is always exactly 20 characters.

---

## Warnings

### WR-01: `pct_int` does not catch `OverflowError` from `math.floor(float('inf'))`

**File:** `claude-statusline.py:153-156`
**Issue:** The `except (TypeError, ValueError)` guard in `pct_int` does not catch `OverflowError`. When JSON contains `1e309` (which Python's `json.loads` parses as `float('inf')`), `math.floor(float('inf'))` raises `OverflowError`, which propagates to the caller. The callers (`_context_segment`, `_rate_segment`) each have a broad `except Exception` that absorbs it, so no crash occurs — but `pct_int`'s own contract ("returns None on any invalid input") is violated. This is a fragile design that relies on outer wrappers to paper over an internal bug.

**Fix:**
```python
def pct_int(value) -> int | None:
    if value is None:
        return None
    try:
        f = float(value)
        if not math.isfinite(f):
            return None
        return math.floor(f)
    except (TypeError, ValueError, OverflowError):
        return None
```

### WR-02: `install.py` writes settings.json non-atomically — truncation on crash

**File:** `install.py:67-71`
**Issue:** `write_settings` opens the file with `open(path, "w")` which truncates the file immediately, then writes JSON incrementally. If the process is killed (SIGKILL, power loss, disk-full) after truncation but before the write completes, `settings.json` is left empty or with partial JSON. The backup exists at `.bak`, but the user must manually recover it. A single atomic write would eliminate the risk.

**Fix:**
```python
import tempfile

def write_settings(path: str, data: dict) -> None:
    dir_ = os.path.dirname(path)
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp",
                                     encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        tmp_path = f.name
    os.replace(tmp_path, path)  # atomic on POSIX
```

### WR-03: `install.py` summary always prints `Backup:` path even when no backup was created

**File:** `install.py:129`
**Issue:** When `settings.json` does not exist before installation, no backup is written (correctly). But the final summary unconditionally prints `Backup : {BACKUP_PATH}`, implying a backup file exists that does not. A user who sees this and tries to restore from it will find no file.

**Fix:**
```python
# Replace line 129:
if os.path.exists(BACKUP_PATH):
    print(f"  Backup   : {BACKUP_PATH}")
else:
    print(f"  Backup   : (none — settings.json was new)")
```

### WR-04: `test_config.py` teardown orphans backup if the test-config write fails

**File:** `tests/test_config.py:281-293` (and equivalent block at lines 239-258 in `test_malformed_config_renders_two_lines`)
**Issue:** Both `_run_with_toml` and `test_malformed_config_renders_two_lines` follow this pattern:
1. `os.rename(real_config, backup_path)` — moves real config to backup.
2. `open(real_config, "wb")` and write — creates test config.
3. `finally: os.unlink(real_config); if had_real: os.rename(backup_path, real_config)`

If step 2 raises (e.g., `PermissionError`, or `~/.claude/` does not exist), `real_config` no longer exists (it was renamed in step 1). The `finally` block then calls `os.unlink(real_config)`, which raises `FileNotFoundError`, masking the original exception and leaving `backup_path` as an orphaned file — the real config is permanently displaced.

**Fix:**
```python
finally:
    if os.path.exists(real_config):
        os.unlink(real_config)
    if had_real and os.path.exists(backup_path):
        os.rename(backup_path, real_config)
```

### WR-05: `test_config.py` test infrastructure assumes `~/.claude/` exists

**File:** `tests/test_config.py:233-234` and `tests/test_config.py:283`
**Issue:** `test_malformed_config_renders_two_lines` creates a `NamedTemporaryFile` with `dir=os.path.expanduser("~/.claude")`, and `_run_with_toml` opens `real_config` for writing. If `~/.claude/` does not exist (clean CI environment, container, or system before first Claude Code run), both tests crash with `FileNotFoundError` rather than failing cleanly.

**Fix:**
```python
os.makedirs(os.path.expanduser("~/.claude"), exist_ok=True)
```
Add this before any test that writes to `~/.claude/`.

---

## Info

### IN-01: `%-I` strftime directive is Linux/glibc-specific

**File:** `claude-statusline.py:174`
**Issue:** `reset_dt.strftime("%-I:%M%p")` uses the `%-I` GNU extension (strip leading zero from 12h hour). This works on Linux but raises `ValueError` on macOS and Windows. The project targets Linux-only deployment, and `fmt_reset` already catches `ValueError`, so this is not a current bug. Documenting the portability constraint would help future contributors.

**Fix:** Add a comment:
```python
# %-I strips leading zero on 12h hour (GNU/Linux only; ValueError caught above for other platforms)
time_str = reset_dt.strftime("%-I:%M%p").lower()
```

### IN-02: `install.py` backup is silently overwritten on repeated installs

**File:** `install.py:107-109`
**Issue:** The backup is always written to the fixed name `settings.json.bak`. On a second install run, the `.bak` file is overwritten with the already-modified settings, so the pre-install original is lost after two runs. The installer is described as idempotent, but idempotency does not protect the original backup.

This is low risk because the second run only backs up the file then skips writing (the `statusLine` entry is already correct). Still, a user who runs the installer twice and then tries to restore from `.bak` will get the modified file, not the original.

**Fix:** Consider timestamped or versioned backups, or document the single-backup limitation prominently.

### IN-03: `_load_stdin` relies on stdin closing for termination — no timeout

**File:** `claude-statusline.py:188-196`
**Issue:** `sys.stdin.read()` blocks until EOF. If Claude Code's pipe does not close (subprocess bug, pipe stall), the statusline process hangs forever, freezing the status bar. This is documented in the runtime contract ("pipes to stdin"), but no defensive timeout exists. The risk is low in normal operation, but worth noting given the RUN-02 "must never hang" requirement.

**Fix (if hardening is desired):**
```python
import signal

def _load_stdin() -> dict:
    def _timeout(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(5)  # 5-second guard
    try:
        raw = sys.stdin.read()
        signal.alarm(0)
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}
```

---

_Reviewed: 2026-05-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
