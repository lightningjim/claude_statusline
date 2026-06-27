---
phase: 11-show-current-versions-of-the-local-claude-executable-as-well
plan: "01"
subsystem: bottom-line-rendering
tags: [version-display, nerd-fonts, ledger-reader, sanitization, tdd]
dependency_graph:
  requires: []
  provides: [_read_installed_gsd_version, _sanitize_version, _versions_fragment, _NF_VERSION_CLAUDE, _NF_VERSION_GSD, show_versions]
  affects: [render_bottom_line, DEFAULTS.display]
tech_stack:
  added: []
  patterns: [byte-capped-json-read, omit-not-fake, try-except-none, nerd-font-glyph-constants, patch-dict-env-isolation]
key_files:
  created: [tests/test_versions_fragment.py]
  modified: [claude-statusline.py, tests/test_nerd_icons.py, tests/test_claude_status.py]
decisions:
  - "show_versions toggle placed in DEFAULTS['display'] alongside show_gsd / show_claude_status (not 'toggles') — matches the most recent three segment toggles (Phase 04-06 cluster)"
  - "Text-label fallback for non-nerd icon_set uses 'claude' / 'gsd' prefix (D-11)"
  - "_NF_VERSION_CLAUDE = U+F0C2 (fa-cloud) for the running Claude Code session; _NF_VERSION_GSD = U+F12E (fa-puzzle-piece) for the GSD plugin (both in installed JetBrains Nerd Font)"
  - "_sanitize_version uses fullmatch allowlist [0-9A-Za-z._+-] and 64-char cap; omit-not-fake on any disallowed char including ESC/control (T-11-01)"
  - "test_claude_status test_empty_data_returns_none_regardless_of_status updated to add show_versions=False — the test's intent is 'all segments disabled -> None'; explicitly opting out of the new toggle is correct, not a weakness"
metrics:
  duration: "~30 min"
  completed_date: "2026-06-27"
  tasks_completed: 3
  tasks_total: 3
  files_created: 1
  files_modified: 3
---

# Phase 11 Plan 01: Version Display Fragment Summary

Dimmed trailing bottom-line fragment showing Claude version (from stdin `version`) and GSD plugin version (from `~/.claude/plugins/installed_plugins.json`), with injection-rejecting sanitizer, nerd/text icon fallback, and per-segment toggle.

## What Was Built

### New Functions (claude-statusline.py)

- `_read_installed_gsd_version() -> str | None`: byte-capped (65 536 B) JSON reader for the GSD installed-plugins ledger. Step-by-step isinstance guards: data→dict, plugins→dict, gsd entry→non-empty list, element[0]→dict, version→non-empty str; whole body in try/except → None. Reads `~/.claude/plugins/installed_plugins.json` only — not plugins/cache/* dirs or package.json (D-05).
- `_sanitize_version(value) -> str | None`: rejects non-str, empty, >64 chars, and any char outside `[0-9A-Za-z._+-]` (including ESC, control, ANSI). Omit-not-fake — never strips and keeps a partial version (T-11-01).
- `_versions_fragment(data, cfg) -> str | None`: show_versions toggle guard → icon_set resolution → Claude piece (stdin `version` + sanitize) → GSD piece (ledger + sanitize) → join with single space → wrap in DIM/RESET. Both pieces independently optional; returns None when both absent. Whole body in try/except → None.

### New Constants (claude-statusline.py)

- `_NF_VERSION_CLAUDE = ""` (U+F0C2 nf-fa-cloud) — cloud glyph for Claude/AI version
- `_NF_VERSION_GSD = ""` (U+F12E nf-fa-puzzle_piece) — puzzle-piece glyph for GSD plugin version

Both registered in `EXPECTED_CONSTANTS` (single-codepoint guard) and `GLYPH_CONSTANTS` (installed-font cmap guard) in `tests/test_nerd_icons.py`.

### Config Default

`DEFAULTS["display"]["show_versions"] = True` added alongside `show_claude_status`, with a `# Phase 11:` intent comment referencing D-10 / VER-05.

### render_bottom_line Wiring

`versions_seg = _versions_fragment(data, cfg)` built after `status_seg` and appended as the last element of the `parts` list; the existing `"   ".join(parts)` provides the 3-space block separator for free; the None-filter drops it cleanly when absent.

### Test Module

`tests/test_versions_fragment.py` (new, 42 tests):
- `TestReadInstalledGsdVersion`: all reader behavior cases (valid, absent file, non-list entry, empty list, missing-version-key, non-str version, empty-str version, malformed JSON, absent gsd key), plus env-leak meta-test. All HOME mutations via `patch.dict` (TEST ENV-LEAK HYGIENE invariant).
- `TestNfVersionGlyphConstants`: existence + single-codepoint guard for both new NF constants.
- `TestShowVersionsDefault`: DEFAULTS["display"]["show_versions"] is True.
- `TestSanitizeVersion`: valid passthrough, None/empty/non-str rejection, ESC/control rejection, length cap, allowed-chars passthrough.
- `TestVersionsFragment`: both-present, missing-Claude-piece, missing-GSD-piece, both-absent, show_versions=False, nerd-glyph assertion, no-nerd-glyph-in-emoji-mode, ANSI-injection rejection.
- `TestVersionsFragmentE2E`: subprocess run_script tests for both versions on bottom line, DIM wrap, missing version, absent ledger, ANSI injection, exit-0-no-traceback.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 617aa25 | test(11-01) | add failing tests — RED phase for all three tasks |
| 6834c1f | feat(11-01) | implement ledger reader, NF version glyphs, show_versions default (Task 1 GREEN) |
| ea8cb1d | feat(11-01) | implement _sanitize_version, _versions_fragment, render wiring (Task 2 GREEN) |
| 1b33b0b | feat(11-01) | Task 3 — full-suite regression + live smoke render verified |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_empty_data_returns_none_regardless_of_status now failed**
- **Found during:** Task 3 full-suite run
- **Issue:** `test_claude_status.py::TestRenderBottomLineStatusIntegration::test_empty_data_returns_none_regardless_of_status` asserted `render_bottom_line({}, empty_cfg)` is None. The `empty_cfg` disabled all other segments but not `show_versions`. With the real GSD ledger present in the developer's home, `_read_installed_gsd_version()` returned "4.0.0" and the versions fragment rendered — correctly, per D-07 (always show when ledger present). The test's intent is "all segments disabled → None"; the fix adds `show_versions: False` to `empty_cfg` so all segments are genuinely disabled.
- **Fix:** Added `"show_versions": False` to `empty_cfg["display"]` in the test.
- **Files modified:** `tests/test_claude_status.py`
- **Commit:** 1b33b0b (included in Task 3 commit)

## Verification

### Automated Tests

```
/usr/bin/pytest tests/ -q
885 passed, 68 skipped, 296 subtests passed
```

### Env-Leak Regression

```
/usr/bin/pytest tests/test_versions_fragment.py tests/test_gsd_segment.py tests/test_claude_status.py -q
All pass — no order-dependent failures
```

### Live Smoke Render

```
python3 claude-statusline.py < .examples/claude_stdin.json
[claude_statusline] [...] [Opus 4.8 (1M context) ] [...]
[...7%...]  [...30%...]  [...3%...]   <DIM>  2.1.154  4.0.0<RESET>
exit=0
```

Bottom line ends with the dimmed two-version fragment containing both "2.1.154" (from stdin `version`) and "4.0.0" (from installed_plugins.json ledger).

## Known Stubs

None. Both version values are wired to live data sources (stdin and local file).

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. The only new file reads are:
- `~/.claude/plugins/installed_plugins.json` — local, user-owned path, byte-capped, try/except (T-11-02 mitigated)

Trust boundary T-11-01 (version strings echoed to terminal) mitigated by `_sanitize_version` allowlist.

## Self-Check: PASSED

- `tests/test_versions_fragment.py` — FOUND (42 tests, all pass)
- `claude-statusline.py::_read_installed_gsd_version` — FOUND
- `claude-statusline.py::_sanitize_version` — FOUND
- `claude-statusline.py::_versions_fragment` — FOUND
- `claude-statusline.py::_NF_VERSION_CLAUDE` — FOUND (U+F0C2, len=1)
- `claude-statusline.py::_NF_VERSION_GSD` — FOUND (U+F12E, len=1)
- `claude-statusline.py::DEFAULTS["display"]["show_versions"]` — FOUND, is True
- Commits 617aa25, 6834c1f, ea8cb1d, 1b33b0b — all present in git log
