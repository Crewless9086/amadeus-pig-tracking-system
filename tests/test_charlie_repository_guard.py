import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.charlie.repository_guard import RepositoryOperationLock, repository_lock_path


class CharlieRepositoryGuardTests(unittest.TestCase):
    def test_one_repository_lock_refuses_live_overlapping_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repository-operation.lock"
            first = RepositoryOperationLock(path)
            second = RepositoryOperationLock(path)
            self.assertTrue(first.acquire()[0])
            with patch("modules.charlie.repository_guard._pid_alive", return_value=True):
                acquired, owner = second.acquire()
            self.assertFalse(acquired)
            self.assertEqual(owner["pid"], os.getpid())
            first.release()

    def test_runner_worktrees_share_canonical_repository_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree_a = root / ".charlie_runner" / "runner-a"
            worktree_b = root / ".charlie_runner" / "runner-b"
            self.assertEqual(repository_lock_path(worktree_a), repository_lock_path(worktree_b))
            self.assertEqual(repository_lock_path(worktree_a), root / ".charlie_runner" / "repository-operation.lock")


if __name__ == "__main__":
    unittest.main()
