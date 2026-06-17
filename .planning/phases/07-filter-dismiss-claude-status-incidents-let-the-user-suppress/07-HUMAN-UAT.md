---
status: complete
phase: 07-filter-dismiss-claude-status-incidents-let-the-user-suppress
source: [07-VERIFICATION.md]
started: 2026-06-17T06:16:03Z
updated: 2026-06-17T13:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Bar goes quiet after dismissing the live Mythos/Fable incident
expected: After `python claude-statusline.py --dismiss s9w82lp9dcn9` then `--refresh`, the Claude-status segment on the bar no longer shows the Mythos/Fable "suspended access" incident — it falls through to the next relevant item (e.g. the Opus 4.8 elevated-errors incident) or omits silently. Re-running `--status-incidents` shows that id with STATE = dismissed.
result: issue
reported: "I still see it, and I see it in the cache.json even after having run refresh. It finally disappeared but only within the 5 min cache window — meaning the --refresh didn't seem to work."
severity: major

### 2. Keyword suppression silences it without an id
expected: Add `ignore_title_patterns = ["Mythos", "Fable"]` under `[claude_status]` in the user TOML, then `--refresh`; the Mythos/Fable incident is suppressed on the bar even with an empty dismissal store. A genuinely new, unrelated incident still lights the bar.
result: pass

### 3. Escalation safety valve still surfaces real outages
expected: With the Mythos/Fable incident dismissed by id, if a DIFFERENT tracked incident escalates above its dismissed impact (or a new un-dismissed incident appears), the bar lights as expected — muting never hides a real escalation (D-03).
result: pass

## Summary

total: 3
passed: 2
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Dismissing an incident (--dismiss <id>) suppresses it on the bar immediately, as the --refresh help text promises."
  status: failed
  reason: "User reported: I still see it, and I see it in cache.json even after running --refresh; it only disappeared within the 5-min cache window, so --refresh didn't apply the dismissal immediately."
  severity: major
  test: 1
  root_cause: |
    Two compounding causes.
    (1) Dismissal is applied at FETCH time, not RENDER time. _derive_claude_status runs inside
    fetch_claude_status (claude-statusline.py:2129) and the suppressed/notable result is baked into
    the cache payload (noteworthy/label, :2145/:2150). The render path _claude_status_segment (:3520)
    reads the baked value and never re-applies _is_suppressed against the dismissal store — so a
    purely-local, zero-network action (--dismiss) cannot take effect until a fresh NETWORK fetch runs.
    (2) Manual --refresh silently no-ops under the stampede lock. run_refresh (:2161) grabs an exclusive
    O_CREAT|O_EXCL lock (:2182) and returns immediately doing nothing if the lock is already held
    (:2183-2185), exiting 0. Every render spawns a detached --refresh child via maybe_spawn_refresh
    (:2217, called at :3343/:3705); since Claude Code renders constantly, the user's foreground --refresh
    collided with an in-flight background child and no-op'd. The incident only cleared when a later
    background fetch completed on its own ~5-min cycle. The help text (:429 "run --refresh to apply it
    immediately") is therefore misleading under lock contention.
  artifacts:
    - path: "claude-statusline.py"
      issue: "Dismissal baked at fetch-time (_derive_claude_status @ fetch_claude_status:2129, cache write :2145/:2150); render path :3520 does not re-apply suppression."
    - path: "claude-statusline.py"
      issue: "run_refresh:2183-2185 silently returns 0 when the stampede lock is held — manual --refresh is unreliable despite :429 help text."
  missing:
    - "Apply dismissal/keyword suppression at RENDER time (re-run _is_suppressed over cached tracked_incidents in _claude_status_segment) so --dismiss is instant and network-independent."
    - "Alternatively/additionally: make manual --refresh reliable (wait-for-lock or bypass the stampede lock for explicit foreground invocation) and correct the :429 help text."
