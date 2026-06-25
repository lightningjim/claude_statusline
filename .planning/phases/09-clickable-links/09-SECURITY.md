---
phase: 09-clickable-links
threats_total: 9
threats_closed: 7
threats_open: 0
accepted_risks: 2
register_authored_at_plan_time: true
audited: 2026-06-25
asvs_level: L1-baseline
block_on: high
---

# Security Audit — Phase 09: Clickable Links

**Audit posture:** FORCE — every mitigation assumed absent until a code match proves it present.  
**Implementation file:** `claude-statusline.py` (single-file statusline; READ-ONLY during audit).  
**Trust boundary:** network-sourced strings (status.claude.com incident `id`, api.weather.gov CAP `geocode.UGC` / `geocode.SAME`) and env var `VTE_VERSION` flow into the OSC 8 hyperlink URI field interpreted by the terminal emulator.

---

## Threat Verification Register

| Threat ID | Category | Disposition | Status | Evidence (file:line) |
|-----------|----------|-------------|--------|----------------------|
| T-09-01 | Tampering | mitigate | CLOSED | `_valid_ugc`: `re.fullmatch(r"[A-Z]{2}[CZ][0-9]{3}", s)` at `claude-statusline.py:340`; `_valid_incident_id`: `re.fullmatch(r"[0-9a-z]+", s)` at `claude-statusline.py:359`. Both applied BEFORE embedding. ESC/ST/control bytes fail fullmatch → None → osc8() returns plain text. |
| T-09-02 | Tampering | mitigate | CLOSED | `osc8()` at `claude-statusline.py:145`: `if not enabled or not url: return text` — zero `\x1b]8` bytes on rejected path. Exactly two call sites (`claude-statusline.py:4088` weather, `:4362` status) — single logical emission point confirmed. |
| T-09-03 | Tampering | mitigate | CLOSED | `_weather_segment` Step 3c at `claude-statusline.py:4055-4063`: every UGC code candidate passed through `_valid_ugc(_code)` before assignment to `_ugc`. URL built only when `(_ugc and _county)` at `:4082`; otherwise `_wx_url = None` → `osc8()` returns plain text. |
| T-09-04a | Information Disclosure | accept | ACCEPT confirmed | Tally assembled as `trailing_detail = linkable + tally` at `claude-statusline.py:4098` — concatenated to the `osc8()` result after the OSC 8 close, not inside `detail` before wrapping. Tally is genuinely outside the span in source order. Carries no secret. |
| T-09-05a | Tampering | mitigate | CLOSED | `_claude_status_segment` at `claude-statusline.py:4359`: `_validated_id = _valid_incident_id(_inc_id)`. URL built at `:4360-4361` only when `_validated_id` is truthy; `osc8()` at `:4362` receives `None` on bad/missing/hyphenated id → plain text. Hyphenated Statuspage slugs (e.g. `"inc-001"`) rejected because `re.fullmatch(r"[0-9a-z]+", ...)` rejects the hyphen character. |
| T-09-06 | Spoofing | mitigate | CLOSED | At `claude-statusline.py:4360-4361`: `_status_url = (f"https://status.claude.com/incidents/{_validated_id}" if _validated_id else None)`. No homepage fallback: grep for `"https://status.claude.com"` (bare homepage as a URL string) returns zero matches — confirmed absent. `osc8()` passthrough when url is None. |
| T-09-04b | Tampering | mitigate | CLOSED | `_same_to_county_ugc` at `claude-statusline.py:454`: `re.fullmatch(r"[0-9]{6}", s)` validates SAME before any slice. Derived county code re-validated through `_valid_ugc(candidate)` at `:464` — same allowlist used everywhere. Any non-match → None → `_wx_url = None` → zero `\x1b]8` bytes. |
| T-09-05b | Denial of Service | mitigate | CLOSED | `_osc8_enabled` at `claude-statusline.py:294-299`: `_vte = os.environ.get("VTE_VERSION", "")` then `try: if int(_vte) >= 5000: return True except (TypeError, ValueError): pass`. Both exception types caught; non-numeric or pre-5000 VTE_VERSION biases to False without raising. Never hangs. |
| T-09-SC | Tampering | accept | ACCEPT confirmed | All top-level imports (`claude-statusline.py:22-70`): `os`, `sys`, `copy`, `json`, `math`, `re`, `subprocess`, `tomllib`, `datetime` — all stdlib. Pre-existing `astral` and `requests` guards unchanged. Phase 9 additions (`osc8`, `_osc8_enabled`, `_valid_ugc`, `_valid_incident_id`, `_same_to_county_ugc`, `_FIPS_STATE_POSTAL`) use only `re` and `os`. No new third-party imports. |

---

## Accepted Risks

### T-09-04a — Tally Information Disclosure (accept)

The per-class tally (`+N`) is plain text appended outside the OSC 8 span. It references the count of remaining non-primary alerts by class. No secret data. The boundary is structurally enforced at `claude-statusline.py:4098` where the tally string is concatenated to the `osc8()` return value, never to `detail` before the OSC 8 wrap. Risk is negligible.

### T-09-SC — Supply Chain (accept)

Phase 9 introduces no new pip/third-party dependencies. All new code paths are stdlib-only (`re`, `os`). Pre-existing `requests` and `astral` are guarded under `_REQUESTS_OK` / `_ASTRAL_OK` flags unchanged from prior phases. No package legitimacy gate is required for a zero-new-dependency phase.

---

## Unregistered Threat Flags

None. All four SUMMARY `## Threat Flags` sections (09-01 through 09-04) explicitly state no new security-relevant surface was introduced beyond the plan-time threat model. No unregistered flags to record.

---

## Audit Trail

| Date | Auditor | Action | Outcome |
|------|---------|--------|---------|
| 2026-06-25 | claude-sonnet-4-6 (security audit) | Initial State-B audit — verify plan-time threat register against implementation | SECURED — 7/7 mitigate threats CLOSED, 2/2 accept dispositions confirmed, 0 open threats |

**Files examined:**
- `/home/kcreasey/Documents/Projects/claude_statusline/claude-statusline.py` (implementation, lines 133-4366)
- `.planning/phases/09-clickable-links/09-01-PLAN.md` through `09-04-PLAN.md` (threat models)
- `.planning/phases/09-clickable-links/09-01-SUMMARY.md` through `09-04-SUMMARY.md` (build evidence)
- `.planning/phases/09-clickable-links/09-VERIFICATION.md` (functional verification state)

**Key grep confirmations:**
- `re.fullmatch` occurrences: 3 in validators (L340, L359, L454) + 1 comment — all expected
- `osc8(` call sites: 2 render sites (L4088, L4362) + 1 definition (L133) + 3 comment refs
- Bare homepage `"https://status.claude.com"` as URL string: 0 occurrences
- `_valid_incident_id` at status render site: present (L4359)
- `_valid_ugc` in weather Step 3c: present (L4055-4063)
- VTE gate `int(_vte) >= 5000` with `except (TypeError, ValueError)`: present (L294-299)
- `_same_to_county_ugc` re-validates through `_valid_ugc`: confirmed (L464)
