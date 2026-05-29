# Phase 4: git info including active worktree — Discussion Log

**Date:** 2026-05-29
**Mode:** discuss (--chain)

> Audit trail only. Not consumed by downstream agents. See 04-CONTEXT.md for the canonical decisions.

## Area Selection

**Question:** Which areas to discuss for the git-info segment?
**Options presented:** Git fields to show / Worktree representation / Data source & speed / Layout, glyph & color
**User chose:** All four.

## Areas Discussed

### Git fields to show
**Question:** Which git fields should the segment display?
**Options presented:** Branch name / Dirty-clean indicator / Ahead-behind upstream / Short commit SHA
**User chose:** Branch name, Dirty/clean indicator, Ahead/behind upstream (NOT short SHA) → D-01

**Question:** How should the dirty state read?
**Options presented:** Single marker (rec) / Counts by type / Clean + dirty glyphs / You decide
**User chose:** Single marker → D-02

### Worktree representation
**Question:** When should the active worktree be surfaced?
**Options presented:** Only when in a linked worktree (rec) / Always show worktree name / Only when >1 worktree exists
**User chose:** Only when in a linked worktree → D-03

**Question:** How should the active worktree be labeled?
**Options presented:** Worktree dir basename (rec) / Glyph marker only / main vs linked glyph / You decide
**User chose:** Worktree dir basename → D-04

### Data source & speed
**Question:** How should git state be read, given the bar must never hang?
**Options presented:** Shell out to `git` w/ short timeout (rec) / Parse .git files directly / Hybrid stdin branch + git
**User chose:** Shell out to `git` with short timeout → D-05, D-06

**Question:** Freshness vs guaranteed-instant — how fresh should git data be?
**Options presented:** Run every render, timeout-guarded (rec) / Cache briefly like weather
**User chose:** Run every render, timeout-guarded — no cache → D-07

**Question:** Which directory defines 'the repo'?
**Options presented:** workspace.current_dir (rec) / cwd / workspace.project_dir
**User chose:** workspace.current_dir (fallback cwd) → D-08

### Layout, glyph & color
**Question:** Where should the git segment live?
**Options presented:** Top line, right after project (rec) / Top line at end / Bottom line
**User chose:** Top line, right after project → D-09

**Question:** Should the git segment be colored?
**Options presented:** Color the state, neutral branch (rec) / Clean=green/dirty=yellow whole segment / Neutral single accent / You decide
**User chose:** Color the state, neutral branch → D-10

## Deferred Ideas
- Standalone short-SHA & stash-count fields → out of v1 (D-01)
- Per-type dirty counts (+3 ~2) → single marker chosen instead (D-02)
- Git actions / commit-log / history / multi-repo → out of scope, separate phases

## Canonical Refs Surfaced
- None — project has no external specs/ADRs; requirements captured in CONTEXT.md decisions + in-repo code touchpoints.
