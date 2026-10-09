"""CHARLIE owner command layer modules."""

import os
import hashlib
import hmac
import json
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


INTAKE_EXECUTION_MODE = "manager_dependency_intake_only"
INITIALIZATION_VERSION = "charlie_stopped_initialization_v1"


def governed_runtime_binding(repo_root, *, required=False):
    """Resolve only the explicitly initialized sibling tuple, never an env override."""
    root = Path(repo_root).resolve()
    state = root.parent
    path = state / "initialization.json"
    if not path.exists():
        if required:
            raise RuntimeError("governed_runtime_binding_missing")
        return None
    if path.is_symlink() or len(path.read_bytes()) > 32768:
        raise RuntimeError("governed_runtime_binding_invalid")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        key = (state / "activation-authority.key").read_bytes()
        unsigned = {k: v for k, v in record.items() if k != "signature_hmac_sha256"}
        signature = hmac.new(key, json.dumps(unsigned, sort_keys=True,
            separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        canonical = Path(record["canonical_root"]).resolve()
        assigned = Path(record["assigned_root"]).resolve()
        roots = (state / "core-runtime-current", state / "core-execution-current")
        if (record["version"] != INITIALIZATION_VERSION or record["predecessor"] != "absent"
                or record["status"] != "initialization_stopped" or len(key) < 32
                or not hmac.compare_digest(signature, record["signature_hmac_sha256"])
                or Path(record["state_root"]) != state or state.parent != assigned
                or canonical == state or canonical in state.parents
                or root not in roots or shared_repository_root(root).resolve() != canonical
                or any(item.is_symlink() or item.resolve() != item for item in (*roots, state, assigned))):
            raise ValueError("binding")
        if (assigned / (state.name + "-initialization.lock")).exists():
            raise ValueError("incomplete initialization")
        plan = json.loads((state / "promotion-ledger" / "initialization-plan.json").read_text())
        lane = json.loads((state / "promotion-ledger" / "initialization-lane.json").read_text())
        plan_digest = hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k != "plan_sha256"},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (plan_digest != record["plan_sha256"] or plan.get("plan_sha256") != plan_digest
                or lane != {"mission_id": record["mission_id"], "plan_sha256": plan_digest}
                or hashlib.sha256((state / "validation-receipt.key").read_bytes()).hexdigest()
                    != record["validation_key_sha256"]):
            raise ValueError("initialization completion drift")
        interpreter = Path(record["interpreter"])
        if not interpreter.is_absolute() or interpreter.resolve() != interpreter or not interpreter.is_file():
            raise ValueError("interpreter")
        if hashlib.sha256(interpreter.read_bytes()).hexdigest() != record["interpreter_sha256"]:
            raise ValueError("interpreter drift")
        return record
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("governed_runtime_binding_invalid") from exc


def governed_state_root(repo_root, default_root):
    binding = governed_runtime_binding(repo_root)
    return Path(binding["state_root"]) if binding else Path(default_root)
