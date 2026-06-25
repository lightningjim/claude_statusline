---
status: testing
phase: 09-clickable-links
source: [09-VERIFICATION.md]
started: 2026-06-21T01:31:51Z
updated: 2026-06-25T17:05:00Z
---

## Current Test

[gap closure 09-04 applied — re-verification round: Test 2 (LINK-02) needs a human click in a supporting terminal to confirm the new showsigwx target opens a populated, readable NWS WWA page. GAP-09-B (WR-01) resolved via automated tests.]

## Tests

### 1. LINK-01 — Claude Status incident is clickable
expected: In a supporting terminal, the status segment opens the relevant `https://status.claude.com/incidents/<id>` page; link text indistinguishable from normal text; correct incident page, never homepage.
result: skipped — no active Claude Status incident available to click during testing. Mechanism shares the `osc8()` path exercised by Test 2.

### 2. LINK-02 — Weather alert is clickable
expected: In a supporting terminal, the alert segment opens the NWS alert detail URL; the tally (`+N`) is not part of the clickable region.
result: RE-TEST PENDING (fix applied in 09-04). The original ISSUE (link opened raw CAP JSON at `api.weather.gov/alerts/active?zone=<UGC>`) is fixed: the link now targets `https://forecast.weather.gov/showsigwx.php?warnzone={zoneUGC}&warncounty={countyUGC}`, with `warncounty` derived from `geocode.SAME`. Automated tests confirm the URL string + omit-not-fake on missing SAME. HUMAN STEP: in a supporting terminal during an active alert, click the weather segment and confirm it opens a populated, human-readable WWA-by-location page (not JSON, not an empty page). Tally-outside-span unchanged.

### 3. LINK-03 — Plain-text fallback, no escape noise
expected: In a non-supporting terminal (xterm) or with `links="off"`, both segments render as plain colored text — no `]8;;`, no stray ESC, no broken unicode.
result: PASSED — fallback confirmed clean on xterm/GNOME. Clickability also confirmed working in the JetBrains/PyCharm terminal after a forced terminal reload (OSC 8 is supported there; the earlier failure was stale terminal state).

### 4. WR-01 (advisory) — VTE version threshold under links="auto"
expected: With `links="auto"` on VTE < 5000, either no link or escape garbage.
result: RESOLVED via 09-04 (automated). `_osc8_enabled` now gates the VTE branch on `int(VTE_VERSION) >= 5000` with a defensive `try/except`; pre-5000 / empty / non-numeric → False without raising. 8 `TestOsc8EnabledVteGate` cases pass under /usr/bin/pytest. No human step needed.

### 5. WR-02 (advisory) — JetBrains JediTerm discrimination under links="auto"
expected: With `links="auto"` on legacy JediTerm, either no link or escape garbage.
result: skipped — WON'T FIX. The user's PyCharm terminal supports OSC 8 (Test 3 reload confirmed); dropping JetBrains from `auto` would break working links. The env var cannot distinguish legacy from reworked JediTerm, and `auto` is opt-in (default is `off`). Document the known limitation in a code comment instead of changing behavior.

## Summary

total: 5
passed: 1
issues: 0
pending: 1
skipped: 1
blocked: 0

(Re-verification round after 09-04: GAP-09-B resolved automated; GAP-09-A fix applied, 1 human click re-test pending on Test 2.)

## Gaps

### GAP-09-A — Weather alert link points at machine-readable JSON, not a human page (LINK-02)
status: fix_applied (09-04) — awaiting human re-verification on Test 2
severity: minor (feature works; target UX is wrong)
truth: Clicking a weather alert opened `https://api.weather.gov/alerts/active?zone=<UGC>` — raw CAP JSON — instead of a readable NWS hazards page.
fix: Point the link at `https://forecast.weather.gov/showsigwx.php?warnzone={zoneUGC}&warncounty={countyUGC}` (NWS "WWA Summary by Location"). Verified live: this page lists EVERY active watch/warning/advisory for the location (tested a 2-alert LA County zone CAZ373 → both Air Quality Alert and Extreme Heat Watch shown). `warncounty` is REQUIRED — zone-only does not populate the alert list.
derivation: NWS zone alerts carry no county code in `geocode.UGC` (only the Z-code). Derive `countyUGC` from `geocode.SAME` (FIPS): SAME is `P SS CCC` → `{state-postal-from-FIPS(SS)}` + `C` + `CCC`. Verified: SAME `006037` → `CAC037` (LA); SAME `040109` → `OKC109` (Oklahoma County). Needs a FIPS-state-code → 2-letter-postal lookup table (50 states + DC + territories), stdlib-only.
omit-not-fake: If no valid `SAME` is present so a valid county UGC cannot be built, OMIT the link (return plain text) per D-10 — do NOT emit a half-URL or fall back to a wrong page.
sites: `_weather_segment` Step 3c (claude-statusline.py ~L3949-3965), reuses `osc8()`, `_osc8_enabled()`, `_valid_ugc()`.

### GAP-09-B — links="auto" enables OSC 8 on pre-0.50 VTE (WR-01, advisory)
status: RESOLVED (09-04, automated — `int(VTE_VERSION) >= 5000` gate, 8 tests pass)
severity: minor (only affects opt-in `auto` mode; default is `off`)
truth: `_osc8_enabled` returned True for any non-empty `VTE_VERSION`, but VTE only added OSC 8 in 0.50 (`VTE_VERSION >= 5000`). Old VTE terminals on `auto` could see raw escapes.
fix: Gate the VTE branch on `int(VTE_VERSION) >= 5000` (parse defensively; non-numeric → treat as unsupported → False). Site: `_osc8_enabled` (claude-statusline.py ~L291-293).

### Non-gap (WON'T FIX, documented) — WR-02 JetBrains discrimination
JetBrains stays in the `auto` allowlist. Add a code comment near the `TERMINAL_EMULATOR`/JetBrains branch noting that legacy and reworked JediTerm export the same env var and cannot be distinguished; users on a truly legacy terminal can set `links="off"`.
