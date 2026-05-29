#!/usr/bin/env python3
"""
Tests for Phase 04 Plan 01: git helper layer.

Covers:
  - _run_git: timeout-guarded subprocess wrapper
  - _parse_git_status_v2: pure porcelain-v2 parser
  - _detect_linked_worktree: realpath-divergence worktree test
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _run_git tests
# ---------------------------------------------------------------------------

class TestRunGit(unittest.TestCase):
    """Tests for _run_git: timeout-guarded subprocess wrapper."""

    def setUp(self):
        self.mod = _load_script_module()

    def test_run_git_exists(self):
        """_run_git must be importable from the module."""
        self.assertTrue(hasattr(self.mod, "_run_git"), "_run_git not found in module")

    def test_run_git_non_existent_directory_returns_none(self):
        """_run_git returns None for a non-existent directory; never raises."""
        result = self.mod._run_git(["rev-parse", "--git-dir"], "/tmp/this-does-not-exist-ever-12345")
        self.assertIsNone(result, "Expected None for a non-existent directory")

    def test_run_git_non_repo_directory_returns_none(self):
        """_run_git returns None when the directory is not a git repo (git exits 128)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.mod._run_git(["rev-parse", "--git-dir"], tmpdir)
            self.assertIsNone(result, "Expected None for a plain (non-git) directory")

    def test_run_git_timeout_returns_none(self):
        """_run_git returns None on timeout; never raises TimeoutExpired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a real git repo (this project's own repo) so git starts and can block.
            # A timeout of 0.0001s (0.1ms) is absurdly short — git won't finish.
            real_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result = self.mod._run_git(["status", "--porcelain=v2", "--branch"], real_repo, timeout=0.0001)
            self.assertIsNone(result, "Expected None on timeout; must not raise")

    def test_run_git_valid_repo_returns_stdout(self):
        """_run_git returns stdout string for a valid git command in a real repo."""
        real_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = self.mod._run_git(["rev-parse", "--git-dir"], real_repo)
        # Should return a non-None string ending with '.git'
        self.assertIsNotNone(result, "Expected stdout for a valid repo")
        self.assertIsInstance(result, str, "Expected a string, not None")

    def test_run_git_never_uses_shell(self):
        """Verify subprocess.run is never called with shell=True in the implementation."""
        import ast
        with open(SCRIPT) as f:
            source = f.read()
        # Parse the AST and look for subprocess.run(shell=True) calls
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self.fail("Could not parse the script as Python AST")

        shell_true_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for subprocess.run(..., shell=True, ...)
                func = node.func
                is_subprocess_run = (
                    (isinstance(func, ast.Attribute) and func.attr == "run"
                     and isinstance(func.value, ast.Name) and func.value.id == "subprocess")
                    or (isinstance(func, ast.Name) and func.id == "run")
                )
                if is_subprocess_run:
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            shell_true_calls.append(node)

        self.assertEqual(len(shell_true_calls), 0,
                         f"Found {len(shell_true_calls)} subprocess.run call(s) with shell=True; none permitted")


# ---------------------------------------------------------------------------
# _parse_git_status_v2 tests
# ---------------------------------------------------------------------------

class TestParseGitStatusV2(unittest.TestCase):
    """Pure-parser tests: canned porcelain-v2 --branch fixtures (VERIFIED real git output)."""

    def setUp(self):
        self.mod = _load_script_module()
        self.parse = self.mod._parse_git_status_v2

    def test_parse_exists(self):
        """_parse_git_status_v2 must be importable from the module."""
        self.assertTrue(hasattr(self.mod, "_parse_git_status_v2"))

    def test_clean_repo_with_upstream(self):
        """Clean repo with upstream: branch='main', detached=False, dirty=False, ahead=0, behind=0."""
        stdout = (
            "# branch.oid 643e8c6b8145a4995b073cfcd89b364b29eda840\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +0 -0\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertEqual(result["branch"], "main")
        self.assertFalse(result["detached"])
        self.assertFalse(result["dirty"])
        self.assertEqual(result["ahead"], 0)
        self.assertEqual(result["behind"], 0)
        self.assertEqual(result["oid"], "643e8c6b8145a4995b073cfcd89b364b29eda840")

    def test_dirty_modified_file(self):
        """A '1 .M ...' line marks dirty=True."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +0 -0\n"
            "1 .M N... 100644 100644 100644 abc abc somefile.py\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertTrue(result["dirty"])

    def test_dirty_untracked_file(self):
        """A '? untracked.txt' line marks dirty=True."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +0 -0\n"
            "? untracked.txt\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertTrue(result["dirty"])

    def test_dirty_staged_file(self):
        """A '1 M. ...' line (staged change) marks dirty=True."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head feature\n"
            "# branch.upstream origin/feature\n"
            "# branch.ab +1 -0\n"
            "1 M. N... 100644 100644 100644 abc def somefile.py\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertTrue(result["dirty"])

    def test_ahead_behind(self):
        """'# branch.ab +40 -2' yields ahead=40, behind=2."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +40 -2\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertEqual(result["ahead"], 40)
        self.assertEqual(result["behind"], 2)

    def test_no_upstream_ahead_behind_are_none(self):
        """When '# branch.ab' line is absent, ahead and behind must be None (NOT 0)."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head local-only\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertIsNone(result["ahead"], "ahead must be None when no upstream, not 0")
        self.assertIsNone(result["behind"], "behind must be None when no upstream, not 0")

    def test_detached_head(self):
        """'# branch.head (detached)' yields detached=True, branch=None."""
        stdout = (
            "# branch.oid a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n"
            "# branch.head (detached)\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertTrue(result["detached"])
        self.assertIsNone(result["branch"])
        self.assertEqual(result["oid"], "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")

    def test_unborn_empty_repo(self):
        """'# branch.oid (initial)' yields oid=None without raising."""
        stdout = (
            "# branch.oid (initial)\n"
            "# branch.head main\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertIsNone(result["oid"])
        self.assertEqual(result["branch"], "main")
        self.assertFalse(result["detached"])

    def test_garbage_input_returns_none_or_safe_dict(self):
        """Garbage/empty input never raises; returns None or a safe dict."""
        try:
            result = self.parse("")
            # Either None or a dict — both are acceptable; neither may raise
            self.assertTrue(result is None or isinstance(result, dict))
        except Exception as e:
            self.fail(f"_parse_git_status_v2 raised on empty input: {e!r}")

    def test_garbage_string_never_raises(self):
        """Completely malformed input never raises."""
        try:
            result = self.parse("not git output at all\n\x00\x01\x02")
            self.assertTrue(result is None or isinstance(result, dict))
        except Exception as e:
            self.fail(f"_parse_git_status_v2 raised on garbage: {e!r}")

    def test_clean_no_file_lines_means_dirty_false(self):
        """Clean repo (no file lines) → dirty=False."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +0 -0\n"
        )
        result = self.parse(stdout)
        self.assertIsNotNone(result)
        self.assertFalse(result["dirty"])

    def test_return_dict_has_all_keys(self):
        """Return dict always has all six required keys."""
        stdout = (
            "# branch.oid abc1234\n"
            "# branch.head main\n"
        )
        result = self.parse(stdout)
        if result is not None:
            for key in ("branch", "detached", "oid", "dirty", "ahead", "behind"):
                self.assertIn(key, result, f"Missing key: {key}")


# ---------------------------------------------------------------------------
# _detect_linked_worktree tests
# ---------------------------------------------------------------------------

class TestDetectLinkedWorktree(unittest.TestCase):
    """Tests for _detect_linked_worktree: realpath-divergence worktree detection."""

    def setUp(self):
        self.mod = _load_script_module()
        self.detect = self.mod._detect_linked_worktree

    def test_detect_exists(self):
        """_detect_linked_worktree must be importable from the module."""
        self.assertTrue(hasattr(self.mod, "_detect_linked_worktree"))

    def test_empty_input_returns_false_none(self):
        """Empty string input → (False, None), never raises."""
        result = self.detect("")
        self.assertEqual(result, (False, None), "Empty input must return (False, None)")

    def test_fewer_than_3_lines_returns_false_none(self):
        """Fewer than 3 lines → (False, None), never raises."""
        result = self.detect("/some/.git\n/some/.git\n")
        self.assertEqual(result, (False, None), "2-line input must return (False, None)")

    def test_main_checkout_same_paths(self):
        """When git-dir and common-dir resolve to the same realpath → (False, basename)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = os.path.join(tmpdir, ".git")
            os.makedirs(git_dir)
            # Construct fake rev-parse output where git-dir == common-dir
            stdout = f"{git_dir}\n{git_dir}\n{tmpdir}\n"
            is_linked, name = self.detect(stdout)
            self.assertFalse(is_linked, "Same git-dir and common-dir means main checkout")
            self.assertEqual(name, os.path.basename(tmpdir))

    def test_linked_worktree_different_realpaths(self):
        """When git-dir realpath != common-dir realpath → (True, basename)."""
        with tempfile.TemporaryDirectory() as main_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                # Simulate: git-dir = main_dir/.git/worktrees/feat, common-dir = main_dir/.git
                git_dir_path = os.path.join(main_dir, ".git", "worktrees", "feat")
                common_dir_path = os.path.join(main_dir, ".git")
                os.makedirs(git_dir_path)
                os.makedirs(common_dir_path, exist_ok=True)
                stdout = f"{git_dir_path}\n{common_dir_path}\n{wt_dir}\n"
                is_linked, name = self.detect(stdout)
                self.assertTrue(is_linked, "Different realpaths must indicate linked worktree")
                self.assertEqual(name, os.path.basename(wt_dir))

    def test_never_raises_on_garbage(self):
        """Garbage input never raises; returns (False, None)."""
        try:
            result = self.detect("garbage\x00\x01\ninvalid")
            self.assertIsInstance(result, tuple)
        except Exception as e:
            self.fail(f"_detect_linked_worktree raised on garbage: {e!r}")

    @unittest.skipUnless(
        subprocess.run(["git", "--version"], capture_output=True).returncode == 0,
        "git not available"
    )
    def test_integration_real_git_repo_and_worktree(self):
        """Integration: real git repo + git worktree add → main=(False,...), linked=(True,basename)."""
        with tempfile.TemporaryDirectory() as base:
            main_repo = os.path.join(base, "main-repo")
            wt_dir = os.path.join(base, "wt-feature")

            # Initialize repo with a commit
            subprocess.run(["git", "init", main_repo], check=True, capture_output=True)
            subprocess.run(["git", "-C", main_repo, "config", "user.email", "test@test.com"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", main_repo, "config", "user.name", "Test"],
                           check=True, capture_output=True)
            # Create initial commit (needed for worktree add)
            readme = os.path.join(main_repo, "README.md")
            with open(readme, "w") as f:
                f.write("test\n")
            subprocess.run(["git", "-C", main_repo, "add", "README.md"], check=True, capture_output=True)
            subprocess.run(["git", "-C", main_repo, "commit", "-m", "init"],
                           check=True, capture_output=True)

            # Add a linked worktree
            subprocess.run(["git", "-C", main_repo, "worktree", "add", wt_dir, "-b", "feature"],
                           check=True, capture_output=True)

            # Test main repo: run _run_git to get rev-parse output
            rp_main = self.mod._run_git(
                ["rev-parse", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"],
                main_repo
            )
            self.assertIsNotNone(rp_main, "rev-parse should succeed in main repo")
            is_linked_main, name_main = self.detect(rp_main)
            self.assertFalse(is_linked_main, "Main checkout must NOT be detected as linked")

            # Test linked worktree: run _run_git to get rev-parse output
            rp_wt = self.mod._run_git(
                ["rev-parse", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"],
                wt_dir
            )
            self.assertIsNotNone(rp_wt, "rev-parse should succeed in linked worktree")
            is_linked_wt, name_wt = self.detect(rp_wt)
            self.assertTrue(is_linked_wt, "Linked worktree must be detected as linked")
            self.assertEqual(name_wt, "wt-feature", "Worktree basename must match the dir name")

    @unittest.skipUnless(
        subprocess.run(["git", "--version"], capture_output=True).returncode == 0,
        "git not available"
    )
    def test_integration_non_repo_dir_returns_none(self):
        """Never-crash: pointing at a plain non-repo dir returns None from _run_git, no traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.mod._run_git(
                ["rev-parse", "--absolute-git-dir", "--git-common-dir", "--show-toplevel"],
                tmpdir
            )
            # _run_git returns None (git exits 128 for non-repo); detect handles empty input
            self.assertIsNone(result, "Non-repo dir must return None from _run_git")
            # _detect_linked_worktree with empty string must not raise
            detect_result = self.detect(result or "")
            self.assertEqual(detect_result, (False, None))


# ---------------------------------------------------------------------------
# _git_segment builder tests (Task 2 — monkeypatched _run_git)
# ---------------------------------------------------------------------------

# Canned porcelain-v2 status outputs for each behavior scenario
_CLEAN_MAIN_NO_UPSTREAM = (
    "# branch.oid abc1234\n"
    "# branch.head main\n"
)

_CLEAN_MAIN_WITH_UPSTREAM = (
    "# branch.oid abc1234\n"
    "# branch.head main\n"
    "# branch.upstream origin/main\n"
    "# branch.ab +0 -0\n"
)

_DIRTY_MAIN = (
    "# branch.oid abc1234\n"
    "# branch.head main\n"
    "# branch.upstream origin/main\n"
    "# branch.ab +0 -0\n"
    "1 .M N... 100644 100644 100644 abc abc somefile.py\n"
)

_AHEAD_2_BEHIND_1 = (
    "# branch.oid abc1234\n"
    "# branch.head feature\n"
    "# branch.upstream origin/feature\n"
    "# branch.ab +2 -1\n"
)

_DETACHED_HEAD = (
    "# branch.oid 0123456789abcdefdeadbeef01234567deadbeef\n"
    "# branch.head (detached)\n"
)

_UNBORN = (
    "# branch.oid (initial)\n"
    "# branch.head main\n"
)

# Canned rev-parse outputs (3 lines: abs-git-dir, common-dir, toplevel)
def _make_main_rp(tmpdir: str) -> str:
    """rev-parse output for a main checkout (git-dir == common-dir)."""
    git_dir = f"{tmpdir}/.git"
    return f"{git_dir}\n{git_dir}\n{tmpdir}\n"

def _make_linked_rp(main_dir: str, wt_dir: str) -> str:
    """rev-parse output for a linked worktree (git-dir != common-dir)."""
    git_dir = f"{main_dir}/.git/worktrees/feat"
    common = f"{main_dir}/.git"
    return f"{git_dir}\n{common}\n{wt_dir}\n"


class TestGitSegmentBuilder(unittest.TestCase):
    """Builder tests: monkeypatched _run_git, covers all behavior cases (D-01..D-10)."""

    def setUp(self):
        self.mod = _load_script_module()

    def _call(self, status_stdout, rp_stdout=None, cfg_override=None, tmpdir=None):
        """Call _git_segment with monkeypatched _run_git returning canned outputs."""
        if tmpdir is None:
            tmpdir = "/tmp/fake-repo"
        if rp_stdout is None:
            rp_stdout = _make_main_rp(tmpdir)

        call_count = [0]
        def fake_run_git(args, cwd, timeout=0.15):
            call_count[0] += 1
            if "status" in args:
                return status_stdout
            elif "rev-parse" in args:
                return rp_stdout
            return None

        original_run_git = self.mod._run_git
        self.mod._run_git = fake_run_git
        try:
            cfg = {
                "display": {"icon_set": "nerd", "show_git": True, "bar_style": "shade"},
                "toggles": {"show_thinking_glyph": True},
                "thresholds": {"warn": 70, "crit": 90},
            }
            if cfg_override:
                for k, v in cfg_override.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
            data = {
                "workspace": {"current_dir": tmpdir, "project_dir": tmpdir},
                "cwd": tmpdir,
            }
            return self.mod._git_segment(data, cfg)
        finally:
            self.mod._run_git = original_run_git

    def test_git_segment_exists(self):
        """_git_segment is defined on the module."""
        self.assertTrue(hasattr(self.mod, "_git_segment"),
                        "_git_segment not found in module")

    def test_show_git_false_returns_none(self):
        """show_git=False → returns None (segment toggled off, D-08)."""
        result = self._call(
            _CLEAN_MAIN_NO_UPSTREAM,
            cfg_override={"display": {"show_git": False}},
        )
        self.assertIsNone(result, "Expected None when show_git=False")

    def test_status_none_returns_none(self):
        """When _run_git returns None (non-repo/timeout) → segment returns None."""
        def fake_run_git(args, cwd, timeout=0.15):
            return None
        original = self.mod._run_git
        self.mod._run_git = fake_run_git
        try:
            cfg = {"display": {"icon_set": "nerd", "show_git": True}}
            data = {"workspace": {"current_dir": "/tmp/nonrepo"}, "cwd": "/tmp/nonrepo"}
            result = self.mod._git_segment(data, cfg)
            self.assertIsNone(result, "Expected None when _run_git returns None")
        finally:
            self.mod._run_git = original

    def test_clean_main_no_upstream_shows_branch(self):
        """Clean main-checkout with no upstream: shows branch name, no dirty marker,
        no ahead/behind, no worktree marker, returns a bracketed string."""
        result = self._call(_CLEAN_MAIN_NO_UPSTREAM)
        self.assertIsNotNone(result, "Expected non-None for clean main checkout")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("["), "Segment must start with '['")
        self.assertTrue(result.endswith("]"), "Segment must end with ']'")
        self.assertIn("main", result, "Expected branch name 'main' in segment")
        # Should NOT contain ahead/behind markers
        self.assertNotIn("↑", result)
        self.assertNotIn("↓", result)

    def test_dirty_repo_shows_yellow_dirty_marker(self):
        """Dirty repo → segment contains YELLOW ANSI code and no plain-text dirty label."""
        result = self._call(_DIRTY_MAIN)
        self.assertIsNotNone(result)
        # The dirty marker must be colored YELLOW
        self.assertIn(self.mod.YELLOW, result,
                      "Expected YELLOW color code for dirty state (D-10)")
        self.assertIn(self.mod.RESET, result)

    def test_clean_repo_no_dirty_marker(self):
        """Clean repo → segment contains no YELLOW dirty marker."""
        result = self._call(_CLEAN_MAIN_WITH_UPSTREAM)
        self.assertIsNotNone(result)
        # No dirty-state marker in the nerd glyph set
        self.assertNotIn(self.mod._NF_GIT_DIRTY, result,
                         "Expected no dirty glyph in clean repo")

    def test_no_upstream_no_ahead_behind(self):
        """No upstream configured → no ahead/behind text in segment (Open Q1)."""
        result = self._call(_CLEAN_MAIN_NO_UPSTREAM)
        self.assertIsNotNone(result)
        # Neither nerd glyphs nor emoji arrows should appear when no upstream
        self.assertNotIn(self.mod._NF_GIT_AHEAD, result,
                         "Ahead glyph must not appear when no upstream")
        self.assertNotIn(self.mod._NF_GIT_BEHIND, result,
                         "Behind glyph must not appear when no upstream")
        # Also no plain arrow fallbacks
        self.assertNotIn("↑", result)
        self.assertNotIn("↓", result)

    def test_ahead_2_behind_1_shows_colored_markers(self):
        """ahead=2, behind=1 → shows ahead marker '2' and behind marker '1', colored."""
        result = self._call(_AHEAD_2_BEHIND_1)
        self.assertIsNotNone(result)
        self.assertIn("2", result, "Expected '2' for ahead count")
        self.assertIn("1", result, "Expected '1' for behind count")
        # Must have color codes (both ahead and behind are colored)
        self.assertIn(self.mod.RESET, result)

    def test_zero_ahead_zero_behind_no_markers(self):
        """ahead=0, behind=0 → ahead/behind chunk is omitted (hide-when-zero)."""
        result = self._call(_CLEAN_MAIN_WITH_UPSTREAM)
        self.assertIsNotNone(result)
        self.assertNotIn(self.mod._NF_GIT_AHEAD, result,
                         "Ahead marker must not appear when ahead=0")
        self.assertNotIn(self.mod._NF_GIT_BEHIND, result,
                         "Behind marker must not appear when behind=0")

    def test_detached_head_shows_7char_oid(self):
        """Detached HEAD → branch slot shows the 7-char short oid (oid[:7]), NOT '(detached)'."""
        result = self._call(_DETACHED_HEAD)
        self.assertIsNotNone(result)
        self.assertIn("0123456", result,
                      "Expected exactly 7-char oid prefix '0123456' in detached HEAD")
        # Exact 7 chars: '0123456' must be present but '01234567' (8 chars) must not
        self.assertNotIn("01234567", result,
                         "Only 7-char oid slice (oid[:7]) expected, not 8 chars")
        self.assertNotIn("(detached)", result,
                         "Literal '(detached)' must not appear in the segment")

    def test_unborn_branch_shows_branch_name_no_crash(self):
        """Unborn/empty repo → shows branch name, no crash."""
        result = self._call(_UNBORN)
        # May be None or a string — must never raise
        self.assertTrue(result is None or isinstance(result, str),
                        f"Expected None or str for unborn repo, got {result!r}")
        if result is not None:
            # If it renders, it should show the unborn branch name
            self.assertIn("main", result, "Expected unborn branch name 'main' in segment")

    def test_main_checkout_no_worktree_marker(self):
        """Main checkout → NO worktree glyph (_NF_GIT_WORKTREE) in segment (D-03)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            rp = _make_main_rp(tmpdir)
            result = self._call(_CLEAN_MAIN_NO_UPSTREAM, rp_stdout=rp, tmpdir=tmpdir)
        self.assertIsNotNone(result)
        self.assertNotIn(self.mod._NF_GIT_WORKTREE, result,
                         "Worktree glyph must not appear in main checkout (D-03)")

    def test_linked_worktree_shows_worktree_basename(self):
        """Linked worktree → shows _NF_GIT_WORKTREE glyph AND worktree dir basename (D-04)."""
        import tempfile
        with tempfile.TemporaryDirectory() as main_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                # Create the fake git-worktree path structure for realpath to work
                import os
                git_wt_path = os.path.join(main_dir, ".git", "worktrees", "feat")
                common_path = os.path.join(main_dir, ".git")
                os.makedirs(git_wt_path)
                os.makedirs(common_path, exist_ok=True)
                rp = f"{git_wt_path}\n{common_path}\n{wt_dir}\n"
                result = self._call(_CLEAN_MAIN_NO_UPSTREAM, rp_stdout=rp, tmpdir=wt_dir)
                self.assertIsNotNone(result)
                wt_basename = os.path.basename(wt_dir)
                self.assertIn(wt_basename, result,
                              f"Expected worktree basename '{wt_basename}' in segment (D-04)")
                self.assertIn(self.mod._NF_GIT_WORKTREE, result,
                              "Expected _NF_GIT_WORKTREE glyph in linked worktree segment (D-04)")

    def test_branch_label_is_neutral_no_green_red(self):
        """Branch label is neutral — should NOT be wrapped in GREEN or RED (D-10)."""
        result = self._call(_CLEAN_MAIN_NO_UPSTREAM)
        self.assertIsNotNone(result)
        self.assertNotIn(self.mod.GREEN, result,
                         "Branch label must not be GREEN (D-10: keep branch neutral)")
        self.assertNotIn(self.mod.RED, result,
                         "Branch label must not be RED (D-10: keep branch neutral)")

    def test_emoji_icon_set_uses_fallback_glyphs(self):
        """icon_set='emoji' → uses emoji/ascii fallback glyphs, not nerd codepoints."""
        result = self._call(
            _DIRTY_MAIN,
            cfg_override={"display": {"icon_set": "emoji"}},
        )
        self.assertIsNotNone(result)
        # Must NOT contain nerd PUA codepoints for dirty
        self.assertNotIn(self.mod._NF_GIT_DIRTY, result,
                         "Nerd dirty glyph must not appear in emoji mode")
        # Must contain the emoji dirty marker
        self.assertIn("✚", result,
                      "Expected '✚' emoji dirty marker in emoji mode")

    def test_emoji_worktree_uses_circle_glyph(self):
        """icon_set='emoji' + linked worktree → uses '⑂' emoji worktree glyph, not nerd glyph."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as main_dir:
            with tempfile.TemporaryDirectory() as wt_dir:
                git_wt_path = os.path.join(main_dir, ".git", "worktrees", "feat")
                common_path = os.path.join(main_dir, ".git")
                os.makedirs(git_wt_path)
                os.makedirs(common_path, exist_ok=True)
                rp = f"{git_wt_path}\n{common_path}\n{wt_dir}\n"
                result = self._call(
                    _CLEAN_MAIN_NO_UPSTREAM,
                    rp_stdout=rp,
                    tmpdir=wt_dir,
                    cfg_override={"display": {"icon_set": "emoji"}},
                )
                self.assertIsNotNone(result)
                self.assertNotIn(self.mod._NF_GIT_WORKTREE, result,
                                 "Nerd worktree glyph must not appear in emoji mode")
                self.assertIn("⑂", result,
                              "Expected '⑂' emoji worktree glyph in emoji mode")

    def test_never_raises_on_any_input(self):
        """_git_segment never raises on edge-case inputs."""
        original = self.mod._run_git
        try:
            self.mod._run_git = lambda *a, **kw: None
            for data, cfg in [
                ({}, {}),
                (None, {}),
                ({"workspace": None}, {"display": {}}),
                ({"workspace": {"current_dir": ""}}, {"display": {"show_git": True}}),
            ]:
                try:
                    result = self.mod._git_segment(data or {}, cfg or {})
                    self.assertTrue(result is None or isinstance(result, str))
                except Exception as exc:
                    self.fail(f"_git_segment raised on edge input {data!r}: {exc!r}")
        finally:
            self.mod._run_git = original


# ---------------------------------------------------------------------------
# End-to-end subprocess tests (Task 3)
# ---------------------------------------------------------------------------

# Project root is the actual git repo for this project (used in e2e tests)
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# An isolated HOME with no config so weather is omitted and show_git defaults True
_E2E_HOME = tempfile.mkdtemp(prefix="gsd-statusline-e2e-home-")


def _run_script_e2e(stdin_dict: dict, home: str = _E2E_HOME) -> subprocess.CompletedProcess:
    """Pipe a JSON dict to the script as a subprocess and return the result."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(stdin_dict).encode(),
        capture_output=True,
        env=env,
    )


def _minimal_data(current_dir: str) -> dict:
    """Minimal stdin JSON with workspace.current_dir pointing to current_dir."""
    return {
        "model": {"display_name": "TestModel"},
        "thinking": {"enabled": False},
        "workspace": {
            "current_dir": current_dir,
            "project_dir": current_dir,
            "added_dirs": [],
        },
        "cwd": current_dir,
        "context_window": {"used_percentage": 10},
        "rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": None},
            "seven_day": {"used_percentage": 5, "resets_at": None},
        },
    }


import json


class TestGitSegmentE2E(unittest.TestCase):
    """End-to-end subprocess tests: piping JSON to the script and inspecting stdout."""

    def test_e2e_repo_dir_shows_git_segment_between_project_and_model(self):
        """Piping the project repo as current_dir: git segment appears between [project] and [model].

        This is the D-09 ordering test: project < git < model on the top line.
        """
        data = _minimal_data(_REPO_DIR)
        result = _run_script_e2e(data)
        self.assertEqual(result.returncode, 0,
                         f"Script exited {result.returncode}; stderr: {result.stderr.decode()!r}")
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr, f"Traceback in stderr: {stderr!r}")
        top_line = result.stdout.decode().splitlines()[0]

        # Both known markers must be present
        project_marker = "[claude_statusline]"
        model_marker = "[TestModel]"
        idx_project = top_line.find(project_marker)
        idx_model = top_line.find(model_marker)

        self.assertGreater(idx_project, -1,
                           f"Project marker not found: {top_line!r}")
        self.assertGreater(idx_model, -1,
                           f"Model marker not found: {top_line!r}")

        # The git segment must appear between project and model
        project_end = idx_project + len(project_marker)
        between = top_line[project_end:idx_model]
        self.assertIn("[", between,
                      f"No git segment bracket between project and model. "
                      f"Between: {between!r}  Line: {top_line!r}")

        # Project must come before model
        self.assertLess(idx_project, idx_model,
                        f"[project] must precede [model]; line: {top_line!r}")

    def test_e2e_non_repo_dir_omits_git_segment_exits_zero(self):
        """Piping a non-repo temp dir: git segment omitted, script exits 0, no traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = _minimal_data(tmpdir)
            result = _run_script_e2e(data)
        self.assertEqual(result.returncode, 0,
                         f"Script must exit 0 even for non-repo dir; "
                         f"stderr: {result.stderr.decode()!r}")
        stderr = result.stderr.decode()
        self.assertNotIn("Traceback", stderr, f"Traceback in stderr: {stderr!r}")
        self.assertNotIn("Error", stderr)

        # The bar must still render (at minimum the model segment)
        top_line = result.stdout.decode().splitlines()[0]
        self.assertIn("[TestModel]", top_line,
                      f"Model segment must still render when git segment absent: {top_line!r}")

    def test_e2e_empty_stdin_exits_zero(self):
        """Empty stdin: script exits 0, no traceback (never-crash contract, RUN-02)."""
        env = dict(os.environ)
        env["HOME"] = _E2E_HOME
        result = subprocess.run(
            [sys.executable, SCRIPT],
            input=b"",
            capture_output=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
