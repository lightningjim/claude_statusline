# SECURITY.md

**Phase:** 07 — filter/dismiss Claude-status incidents  
**Audit Date:** 2026-06-17  
**ASVS Level:** 1  
**Threats Closed:** 15/15  
**Threats Open:** 0/15

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-07-01 | Tampering | mitigate | CLOSED | `read_dismissals` (claude-statusline.py:334-349): `json.load` inside `try/except Exception: return {}`; explicit `if not isinstance(data, dict): return {}` at :345. Non-dict and corrupt inputs degrade to `{}`. |
| T-07-02 | DoS | mitigate | CLOSED | `write_dismissals` (claude-statusline.py:352-371): `tmp = path + ".tmp"` then `os.replace(tmp, path)` at :364-368. Atomic replace; any OS error swallowed by `except Exception: pass` at :369. |
| T-07-03 | Injection | accept(01)/mitigate(03) | CLOSED | `_collect_tracked_incidents` stores titles RAW (line :2040 comment); `_print_status_incidents` defines `_sanitize` at :528-533 filtering `\x1b` and all non-printable chars, applied to every field (`id`, `impact`, `status`, `component`, `title`) at :554-558 before any `print()`. |
| T-07-04 | DoS | mitigate | CLOSED | `_CLAUDE_PATTERN_MATCH_MAXLEN = 500` at :1555; `title_capped = str(title)[:_CLAUDE_PATTERN_MATCH_MAXLEN]` at :1655 slices title before any substring or regex match. Regex compilation failure caught by `except Exception: pass` at :1674 — bad pattern → no-match, no-raise, no-suppress. |
| T-07-05 | Info Disclosure | mitigate | CLOSED | `_is_suppressed` (:1689-1693): `live_rank = _CLAUDE_IMPACT_RANK.get(...)`, `if live_rank > stored_rank: return False` — dismissal void, incident re-surfaces when impact escalates. Shared `_CLAUDE_IMPACT_RANK` dict at :1559 is the single ordering used by both `_is_suppressed` and `_derive_claude_status`. |
| T-07-06 | Tampering | mitigate | CLOSED | `_is_suppressed` (:1641-1642): `if not isinstance(dismissals, dict): dismissals = {}` normalizes corrupt/non-dict stores. Outer `except Exception: return False` at :1698-1700 ensures no raise on any unexpected input. |
| T-07-07 | Tampering | mitigate | CLOSED | `write_dismissals(_DISMISSALS_PATH)` called only at :2121 inside `fetch_claude_status`, which is invoked only from `run_refresh` (called only when `"--refresh" in sys.argv`, :3791). No TOML write calls anywhere in the prune path. User config file (`~/.claude/claude-statusline/claude-statusline.toml`) is never opened for writing by any phase 07 code path. |
| T-07-08 | Injection | mitigate | CLOSED | `_print_status_incidents` (:528-533): inner `_sanitize` strips every char failing `ch == " " or (ch.isprintable() and ch != "\x1b")`, width-bounded to `_CLAUDE_STATUS_LABEL_MAXLEN`. Applied to all columns at :554-558, :568. Test `test_malicious_title_no_raw_escape` at tests/test_claude_status.py:3039 asserts `\x1b` absent from output. |
| T-07-09 | DoS | mitigate | CLOSED | `main()` at :3799-3808: `inc_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""` for both `--dismiss` and `--undismiss`. `_handle_dismiss_flag` (:445) and `_handle_undismiss_flag` (:471) both gate on `if not inc_id:` → print usage hint, return cleanly — no IndexError, no traceback. |
| T-07-10 | Tampering | accept | CLOSED | Documented `accept` in threat register (07-03-PLAN.md:198): arbitrary id writes only to tool-owned `_DISMISSALS_PATH`; auto-pruned on next fetch when id absent from feed; no TOML write; no impact on real incidents; local single-user tool. No code mitigation required. |
| T-07-04-01 | DoS | mitigate | CLOSED | `_claude_status_segment` render path calls `_is_suppressed` at :3602 (no new matching code forked). The 500-char cap at :1655 is therefore inherited on the render path. ReDoS test `test_redos_cap_returns_fast_and_does_not_suppress` at tests/test_claude_status.py:2319 verifies sub-1s completion. |
| T-07-04-02 | Tampering | mitigate | CLOSED | `_claude_status_segment` (:3575-3580): `read_dismissals(_DISMISSALS_PATH)` in inner `try/except` (any exception → `dismissals = {}`); explicit `if not isinstance(dismissals, dict): dismissals = {}` guard. Whole function in `try/except → None` at :3664. |
| T-07-04-03 | Tampering | mitigate | CLOSED | `_claude_status_segment` (:3582-3583): `tracked_incs = raw_tracked if isinstance(raw_tracked, list) else []`; per-item `if not isinstance(inc, dict): continue` at :3597. Function `try/except → None` at :3664. Test `test_render_never_raises_on_malformed` at tests/test_claude_status.py:1330 covers non-dict list items and corrupt store simultaneously. |
| T-07-04-04 | Info Disclosure | accept/mitigate | CLOSED | `_claude_status_segment` (:3599-3602) reads `inc_impact = inc.get("impact", "none")` from the live cached incident and passes it as the `impact` argument to `_is_suppressed`. Escalation comparison (`live_rank > stored_rank → return False`) at :1691-1693 voids the dismissal and allows re-surface. Test `test_escalation_resurfaces_at_render` at tests/test_claude_status.py:1242 asserts non-None result when dismissed at minor but live impact is major. |
| T-07-SC | Tampering (supply chain) | mitigate | CLOSED | `pyproject.toml` dependencies: `["requests", "astral"]` — unchanged from pre-phase-07 baseline. All phase 07 code uses stdlib only (`json`, `os`, `re`, `time`). No new package installs. |

---

## Unregistered Flags

The 07-04-SUMMARY.md `## Threat Flags` section maps all four flags to existing threat IDs (T-07-04-02, T-07-04-03, T-07-04-01, T-07-04-04). No unregistered surface detected.

---

## Accepted Risks Log

| Risk ID | Threat | Rationale |
|---------|--------|-----------|
| T-07-10 | `--dismiss` accepts arbitrary incident id | Id is written only to the tool-owned dismissal store (`status_dismissals.json`), never the user TOML. Stale arbitrary ids are auto-pruned on the next background fetch when absent from the live feed. Impact is limited to silencing a non-existent incident in a local single-user tool. |

---

## Notes

- All implementation files are READ-ONLY; no patches applied during this audit.
- Render-time suppression (Plan 04 gap closure) confirmed present at `_claude_status_segment` lines 3565-3619.
- The `_DISMISS_REFRESH_NOTE` stale `--refresh` claim was confirmed removed; current text at :428-431 correctly reads "at the very next render (no --refresh required)."
- 199 phase-07 unit tests pass (confirmed in 07-04-SUMMARY.md verification block); TestClaudeStatusRenderSuppression class (9 tests) covers T-07-04-01 through T-07-04-04.
