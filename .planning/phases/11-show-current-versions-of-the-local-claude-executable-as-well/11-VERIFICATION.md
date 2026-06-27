---
phase: 11-show-current-versions-of-the-local-claude-executable-as-well
verified: 2026-06-27T22:30:00Z
status: passed
score: 6/6 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Phase 11: Version Display Fragment — Verification Report

**Phase Goal:** The statusline reports the current version of the local `claude` executable (from the stdin `version` field) and the installed GSD plugin version (from `~/.claude/plugins/installed_plugins.json`), rendered as a dimmed trailing fragment on the bottom line, with omit-not-fake on every bad-data path.
**Verified:** 2026-06-27T22:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | With stdin `version` present and ledger readable, the bottom line ends with a dimmed fragment containing both version numbers after the Claude-status segment, single-space-joined (D-01, D-02, D-09) | VERIFIED | Live render: `\033[2m 2.1.154  4.0.0\033[0m`; `parts` list at line 4661 appends `versions_seg` after `status_seg`; body is `" ".join(pieces)` (line 4546) |
| 2 | When stdin `version` is missing/empty/non-string, the Claude piece is omitted with no placeholder; sourced only from stdin `version`, no subprocess (D-03, D-04) | VERIFIED | Line 4519: `data.get("version") if isinstance(data, dict) else None`; no subprocess call exists on the version path; E2E test `test_e2e_missing_stdin_version_only_gsd_shows` passes |
| 3 | When the ledger is absent/unreadable/malformed (non-list entry, empty list, bad JSON), the GSD piece is omitted and no exception escapes render_bottom_line; sourced from `[0]['version']` via byte-capped read, shown in every project (D-05, D-06, D-07) | VERIFIED | `_read_installed_gsd_version` lines 3117-3144: step-by-step isinstance guards, `try/except Exception: return None`, `fh.read(_GSD_MAX_BYTES)`; 9 reader test cases (valid, absent file, dict-entry, empty-list, missing-key, non-str, empty-str, malformed JSON, absent gsd key) all pass |
| 4 | When `show_versions` is false, the entire versions fragment is absent from the bottom line; toggle defaults to True (D-10) | VERIFIED | `DEFAULTS["display"]["show_versions"] = True` at line 215; `_versions_fragment` line 4512 returns None when false; `test_show_versions_false_returns_none` passes |
| 5 | When icon_set != 'nerd', the fragment uses short text labels and emits zero Nerd Font codepoints; when icon_set == 'nerd' each version leads with a single-codepoint Nerd Font glyph (D-08, D-11) | VERIFIED | `_NF_VERSION_CLAUDE = ''` (len=1), `_NF_VERSION_GSD = ''` (len=1); lines 4522-4536 branch on `_icon_set == "nerd"` for glyphs vs text labels `"claude"` / `"gsd"`; emoji-mode test asserts no NF codepoints; human visual checkpoint (11-02) approved by Kyle |
| 6 | A version string carrying ANSI/control characters is rejected (piece omitted), never echoed raw into the terminal (T-11-01) | VERIFIED | `_sanitize_version` line 4473: `re.fullmatch(r"[0-9A-Za-z._+\-]+", value)` rejects ESC/control/ANSI; `test_ansi_escape_returns_none` and `test_e2e_ansi_injected_version_not_echoed` pass; review confirmed `fullmatch` closes the `$`-vs-`fullmatch` gap |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-statusline.py` | `_read_installed_gsd_version`, `_sanitize_version`, `_versions_fragment`, `_NF_VERSION_*` constants, `show_versions` default | VERIFIED | All symbols present; functions are substantive (not stubs); wired into `render_bottom_line` at line 4659-4661 |
| `tests/test_versions_fragment.py` | Unit + E2E coverage for reader, sanitizer, fragment, wiring, omit-not-fake paths | VERIFIED | 42 tests across 6 test classes; all pass under `/usr/bin/pytest`; env-leak hygiene confirmed (no bare `os.environ["HOME"] = ...` assignment) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `render_bottom_line` | `_versions_fragment` | `versions_seg = _versions_fragment(data, cfg)` appended in parts list | WIRED | Line 4659 calls builder; line 4661 appends `versions_seg` as last element of `parts`; None-filter drops it cleanly |
| `_versions_fragment` | `_read_installed_gsd_version` | GSD piece at line 4530 | WIRED | `raw_gsd = _read_installed_gsd_version()` is called unconditionally inside builder |
| `_read_installed_gsd_version` | `~/.claude/plugins/installed_plugins.json` | `os.path.expanduser("~/.claude/plugins/installed_plugins.json")` at line 3118 | WIRED | Reads the fixed ledger path; byte-capped; NOT plugins/cache dirs or package.json (D-05 honored) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `_versions_fragment` (Claude piece) | `raw_claude` | `data.get("version")` — stdin field | Yes (stdin JSON, no subprocess) | FLOWING |
| `_versions_fragment` (GSD piece) | `raw_gsd` | `_read_installed_gsd_version()` — live filesystem read | Yes (live `~/.claude/plugins/installed_plugins.json`, byte-capped) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Bottom line ends with dimmed two-version fragment | `python3 claude-statusline.py < .examples/claude_stdin.json` | DIM body: `' 2.1.154  4.0.0'`; exit=0 | PASS |
| `_sanitize_version` rejects ANSI | `_sanitize_version("1.0\x1b[31m")` | Returns None | PASS |
| `_sanitize_version` passes clean versions | `_sanitize_version("2.1.154")` | Returns `"2.1.154"` | PASS |
| `_NF_VERSION_CLAUDE` single codepoint | `len(_NF_VERSION_CLAUDE)` | `1` (U+F0C2) | PASS |
| `_NF_VERSION_GSD` single codepoint | `len(_NF_VERSION_GSD)` | `1` (U+F12E) | PASS |
| `show_versions` default | `DEFAULTS["display"]["show_versions"]` | `True` | PASS |
| Full test suite | `/usr/bin/pytest tests/ -q` | 885 passed, 68 skipped, 296 subtests — exit 0 | PASS |

### Probe Execution

Step 7c: SKIPPED — no conventional `scripts/*/tests/probe-*.sh` probes exist for this project. The behavioral spot-checks in Step 7b cover the equivalent ground.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| VER-01 | 11-01-PLAN.md | Claude version from stdin `version`, omit-not-fake (D-03, D-04) | SATISFIED | `data.get("version")` at line 4519; no subprocess; sanitizer rejects non-str/empty |
| VER-02 | 11-01-PLAN.md | GSD version from `installed_plugins.json` ledger `[0]["version"]`, always-show, omit-not-fake (D-05, D-06, D-07) | SATISFIED | `_read_installed_gsd_version` with full shape guards and byte cap; shown in every project when ledger present |
| VER-03 | 11-01-PLAN.md | Dimmed trailing fragment after Claude-status segment, single-space internal join, None-filtered (D-01, D-02, D-09) | SATISFIED | `" ".join(pieces)` + `f"{DIM}{body}{RESET}"`; appended as last element of `parts` list after `status_seg` |
| VER-04 | 11-01-PLAN.md | Nerd Font glyphs with text-label fallback per `icon_set` (D-08, D-11) | SATISFIED | `_NF_VERSION_CLAUDE`/`_NF_VERSION_GSD` single codepoints; text labels `"claude"`/`"gsd"` for non-nerd; human checkpoint approved |
| VER-05 | 11-01-PLAN.md | `show_versions` config toggle, default True (D-10) | SATISFIED | `DEFAULTS["display"]["show_versions"] = True`; toggle gate at line 4512 |

Note: VER-01..VER-05 are phase-local IDs derived from CONTEXT decisions D-01..D-11; they are intentionally not present in `.planning/REQUIREMENTS.md` (consistent with prior CONTEXT-driven phases). All five intents are delivered.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `claude-statusline.py` | 3014, 3370 | `"TBD"` appears in comments | INFO | Not a code-debt marker — these comments describe how the GSD STATE.md regex parser handles documents that contain `"- [ ] TBD (...)"` placeholder strings. The word appears inside a quoted string in the comment body (describing document content), not as a standalone `# TBD` intent annotation. Pre-existing code unrelated to Phase 11's new functions. |
| `claude-statusline.py` | 4472 | `import re as _re` inside `_sanitize_version` | INFO | Cosmetic: shadows the module-level `re`; functionally correct (import is cached). Flagged in REVIEW.md as IN-02. Non-blocking. |
| `claude-statusline.py` | 4512 | Default `True` hardcoded at read site (also in `DEFAULTS`) | INFO | Latent duplicate default, mirrors existing pattern for `show_gsd`/`show_claude_status`. Flagged in REVIEW.md as IN-03. Non-blocking. |

No `TBD`/`FIXME`/`XXX` debt markers exist in Phase 11's new code (`_read_installed_gsd_version`, `_sanitize_version`, `_versions_fragment`, glyph constants, `show_versions` default). The two "TBD" occurrences in pre-existing parser comments are not debt markers and do not indicate incomplete implementation.

### Human Verification Required

The wave-2 human checkpoint (11-02-PLAN.md) was completed and approved by Kyle prior to this verification. Evidence: `11-02-SUMMARY.md` records explicit approval of both Nerd Font glyphs (U+F0C2 cloud, U+F12E puzzle-piece), the dimmed trailing layout, and the accurate version numbers. No further human testing is required.

### Gaps Summary

No gaps. All six observable truths are verified by direct code inspection, behavioral spot-checks, full test suite passage (885 passed, 68 skipped), and a completed human visual checkpoint. The phase goal is achieved.

---

_Verified: 2026-06-27T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
