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
        """Verify no shell=True in the source — injection surface control."""
        import re
        with open(SCRIPT) as f:
            source = f.read()
        # Strip comments, then check
        non_comment = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        self.assertNotIn("shell=True", non_comment, "shell=True must never appear in the implementation")


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


if __name__ == "__main__":
    unittest.main()
