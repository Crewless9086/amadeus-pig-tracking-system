"""CHARLIE owner command layer modules."""

import os
import sys
from pathlib import Path


TEST_CONTROL_ROOT_ENV = "CHARLIE_TEST_CONTROL_ROOT"
TEST_ISOLATION_ENV = "CHARLIE_TEST_ISOLATION"
TERMINATION_ENABLE_ENV = "CHARLIE_PROCESS_TERMINATION_ENABLED"
SUBPROCESS_TESTS_ENABLE_ENV = "CHARLIE_SUBPROCESS_TESTS_ENABLED"


def shared_repository_root(repo_root):
    """Resolve the primary checkout used for shared runtime state."""
    repo_root = Path(repo_root)
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return repo_root
    try:
        marker = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return repo_root
    if not marker.lower().startswith("gitdir:"):
        return repo_root
    git_dir = Path(marker.split(":", 1)[1].strip())
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    return git_dir.parent.parent.parent if git_dir.parent.name == "worktrees" else repo_root


def test_isolation_enabled(environ=None):
    values = os.environ if environ is None else environ
    return str(values.get(TEST_ISOLATION_ENV) or "") == "1"


def validated_test_control_root(repo_root, environ=None):
    """Return a test root only when it is outside the shared repository."""
    values = os.environ if environ is None else environ
    configured = str(values.get(TEST_CONTROL_ROOT_ENV) or "").strip()
    if not configured:
        raise RuntimeError("CHARLIE test isolation requires CHARLIE_TEST_CONTROL_ROOT")
    root = Path(configured).resolve()
    shared = shared_repository_root(repo_root).resolve()
    if root == shared or shared in root.parents:
        raise RuntimeError("CHARLIE test control root must be outside the shared repository")
    return root


def runtime_path_root(default_root, repo_root=None, environ=None):
    """Preserve production paths while redirecting tests to validated storage."""
    values = os.environ if environ is None else environ
    if test_isolation_enabled(values):
        return validated_test_control_root(repo_root or default_root, values)
    return Path(default_root)


def _guard_direct_charlie_test_execution():
    """Require explicit safe isolation before a CHARLIE test runs as a script."""
    script = Path(str(sys.argv[0] or ""))
    if not (
        script.name.startswith("test_charlie_")
        and script.suffix == ".py"
        and (script.parent.name == "tests" or Path.cwd().name == "tests")
    ):
        return
    repo_root = Path(__file__).resolve().parents[2]
    if not test_isolation_enabled():
        raise RuntimeError(
            "Direct CHARLIE test execution requires CHARLIE_TEST_ISOLATION=1 "
            "and a safe CHARLIE_TEST_CONTROL_ROOT; prefer "
            "`python -m unittest tests.test_charlie_<module>`."
        )
    validated_test_control_root(repo_root)
    os.environ.pop(TERMINATION_ENABLE_ENV, None)
    os.environ.pop(SUBPROCESS_TESTS_ENABLE_ENV, None)


_guard_direct_charlie_test_execution()
