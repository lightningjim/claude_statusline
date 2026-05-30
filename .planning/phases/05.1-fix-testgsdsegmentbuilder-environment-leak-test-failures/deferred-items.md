# Deferred Items — Phase 05.1 Plan 01

## Out-of-Scope Pre-Existing Failures

### TestGsdSegmentE2E::test_e2e_repo_dir_shows_gsd_segment_between_git_and_model

**Status:** Pre-existing, out of scope (confirmed failing before any changes in this plan).

**Cause:** This E2E test runs from within a git worktree where the project directory
basename is `agent-aade395d1ed7bd925` (the worktree name), not `claude_statusline`.
The test asserts `[claude_statusline]` appears in the top line, which fails because
the project segment shows the worktree directory name instead.

**Not introduced by this plan.** This plan's scope is TestGsdSegmentBuilder only.

**Fix:** This test should be run from the main repo checkout, not from a worktree.
Alternatively, the test could be made more resilient to project name variations.
Deferred to a future test-hygiene phase.
