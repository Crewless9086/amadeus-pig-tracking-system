"""Prepare a pinned Desktop first-registration package; no database apply CLI.

Owner evidence is supplied for byte/shape validation, not authenticated by this
offline command. A later separately approved maintainer operation must verify
the original owner instruction, current exact candidate, expiry and this code's
hashes before calling the bounded store helper with an authenticated principal.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.desktop_consolidation_registration import (  # noqa: E402
    RegistrationError, register_first_mission, bind_successor, sha256,
    CONSOLIDATION_BASE, CONSOLIDATION_ORIGINAL, CONSOLIDATION_CHECKPOINT, CONSOLIDATION_SCOPE_CHECKPOINT,
)
from modules.charlie.mission_admission import canonical_candidate_diff  # noqa: E402
from scripts.charlie_mission_admission_guard import BOOTSTRAP_GOVERNANCE_PATHS  # noqa: E402


def _git(*args):
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return result.stdout


def verify_local_candidate(manifest):
    candidate = manifest["candidate"]
    implementation = manifest["implementation"]
    if implementation["revision"] != candidate["head_sha"]:
        raise RegistrationError("implementation_not_candidate_revision")
    if _git("rev-parse", "HEAD").decode().strip() != implementation["revision"]:
        raise RegistrationError("implementation_revision_mismatch")
    if _git("status", "--porcelain", "--untracked-files=all").strip():
        raise RegistrationError("implementation_workspace_not_clean")
    remote = _git("remote", "get-url", "origin").decode().strip().removesuffix(".git")
    repository = manifest["repository"]
    if remote not in {"https://github.com/" + repository, "git@github.com:" + repository}:
        raise RegistrationError("repository_destination_mismatch")
    for path, digest in implementation["files"].items():
        if sha256((REPO_ROOT / path).read_bytes()) != digest:
            raise RegistrationError("implementation_file_changed")
    # No remote fetch, credentials, provider read or write occurs here.
    base, head = candidate["base_sha"], candidate["head_sha"]
    if _git("rev-parse", "refs/heads/" + candidate["branch"]).decode().strip() != head:
        raise RegistrationError("candidate_branch_changed")
    for revision in (base, head):
        if _git("rev-parse", revision + "^{commit}").decode().strip() != revision:
            raise RegistrationError("candidate_revision_mismatch")
    if _git("rev-parse", head + "^{tree}").decode().strip() != candidate["tree_sha"]:
        raise RegistrationError("candidate_tree_mismatch")
    paths = sorted(filter(None, _git("diff", "--name-only", "-z", base, head, "--").decode().split("\0")))
    patch = _git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", base, head, "--")
    if (paths != candidate["changed_files"] or
            canonical_candidate_diff(paths, patch) != candidate["diff_sha256"]):
        raise RegistrationError("candidate_scope_or_diff_mismatch")
    for path in BOOTSTRAP_GOVERNANCE_PATHS:
        if _git("show", base + ":" + path) != _git("show", head + ":" + path):
            raise RegistrationError("bootstrap_governance_changed")


def verify_local_successor(manifest):
    """Execute protected-main implementation; inspect successor only as Git data."""
    candidate, implementation, merge = (manifest[key] for key in ("candidate", "implementation", "merge_evidence"))
    revision = implementation["revision"]
    if (revision != candidate["base_sha"] or revision != merge["main_sha"]
            or _git("rev-parse", "HEAD").decode().strip() != revision
            or _git("rev-parse", "refs/remotes/origin/main").decode().strip() != revision):
        raise RegistrationError("implementation_not_protected_main")
    if _git("status", "--porcelain", "--untracked-files=all").strip():
        raise RegistrationError("implementation_workspace_not_clean")
    remote = _git("remote", "get-url", "origin").decode().strip().removesuffix(".git")
    if remote not in {"https://github.com/" + manifest["repository"], "git@github.com:" + manifest["repository"]}:
        raise RegistrationError("repository_destination_mismatch")
    for path, digest in implementation["files"].items():
        if sha256((REPO_ROOT / path).read_bytes()) != digest:
            raise RegistrationError("implementation_file_changed")
    base, head = candidate["base_sha"], candidate["head_sha"]
    for commit in (base, head, merge["head_sha"], merge["merge_sha"], CONSOLIDATION_ORIGINAL, CONSOLIDATION_CHECKPOINT):
        if _git("rev-parse", commit + "^{commit}").decode().strip() != commit:
            raise RegistrationError("candidate_revision_mismatch")
    if _git("rev-parse", "refs/heads/" + candidate["branch"]).decode().strip() != head:
        raise RegistrationError("candidate_branch_changed")
    if _git("rev-parse", head + "^{tree}").decode().strip() != candidate["tree_sha"]:
        raise RegistrationError("candidate_tree_mismatch")
    try:
        for ancestor, descendant in (
            (merge["head_sha"], merge["merge_sha"]), (merge["merge_sha"], base),
            (base, head), (CONSOLIDATION_ORIGINAL, CONSOLIDATION_CHECKPOINT),
            (CONSOLIDATION_CHECKPOINT, CONSOLIDATION_SCOPE_CHECKPOINT), (CONSOLIDATION_SCOPE_CHECKPOINT, head),
        ):
            _git("merge-base", "--is-ancestor", ancestor, descendant)
    except subprocess.CalledProcessError as exc:
        raise RegistrationError("preserved_consolidation_or_merge_ancestry_changed") from exc
    def paths(left, right):
        return sorted(filter(None, _git("diff", "--name-only", "-z", left, right, "--").decode().split("\0")))
    changed = paths(base, head)
    approved = paths(CONSOLIDATION_BASE, CONSOLIDATION_SCOPE_CHECKPOINT)
    patch = _git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", base, head, "--")
    if (changed != approved or changed != candidate["changed_files"]
            or canonical_candidate_diff(changed, patch) != candidate["diff_sha256"]):
        raise RegistrationError("candidate_scope_or_diff_mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--successor", action="store_true", help="Prepare the one paused PR1342-to-PR1341 succession")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--owner-approval", type=Path, required=True)
    parser.add_argument("--owner-approval-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        prepare = bind_successor if args.successor else register_first_mission
        result = prepare(
            args.manifest.read_bytes(), expected_manifest_sha256=args.manifest_sha256,
            approval_bytes=args.owner_approval.read_bytes(),
            expected_approval_sha256=args.owner_approval_sha256)
        if args.successor:
            verify_local_successor(result["plan"]["manifest"])
        else:
            manifest = json.loads(result["plan"]["params"]["metadata_json"])["desktop_first_registration"]["manifest"]
            verify_local_candidate(manifest)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RegistrationError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "registration_preparation_blocked", "error_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, RegistrationError) else "local_verification_failed",
                          "database_accessed": False, "writes": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
