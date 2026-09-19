"""Read-only checks for a portable, bounded Amadeus development checkout."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

LEGACY_RUNTIME_NAMES = {
    ".charlie_runner", ".codex-runtime", ".codex-worktrees", ".worktrees",
    ".w", ".tmp", ".git-local-config", ".testtmp", ".codex-test-runtime",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    "test-results", "playwright-report", "tmp", "venv", ".venv", "node_modules",
}

def git(root, *args):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Git inspection failed: " + " ".join(args))
    return result.stdout.strip()

def inspect_workspace(root, *, require_clean=False, max_worktrees=3):
    root = Path(root).resolve()
    findings = []
    actual = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    if actual != root:
        findings.append("Run from the checkout root, not a containing or nested directory.")
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if require_clean and status:
        findings.append("The checkout has uncommitted or untracked changes.")
    for entry in root.iterdir():
        name = entry.name.casefold()
        if entry.is_dir() and (name in LEGACY_RUNTIME_NAMES or name.startswith(".review_") or name.startswith(".tmp-")):
            findings.append("Legacy runtime directory inside source checkout: " + entry.name)
    ignored_evidence = git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "--", "control-tower-artifacts")
    if ignored_evidence:
        findings.append("Untracked working evidence inside source checkout; move it through the approved sibling runtime route.")
    worktrees = []
    for line in git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:]).resolve()
            worktrees.append(str(path))
            if path != root and path.is_relative_to(root):
                findings.append("Nested working copy inside source checkout: " + str(path.relative_to(root)))
    if len(worktrees) > max_worktrees:
        findings.append(f"{len(worktrees)} registered worktrees exceeds configured limit {max_worktrees}.")
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    common = common.resolve()
    if not common.is_relative_to(root):
        findings.append("This is a linked worktree; the canonical entry must be an independent checkout.")
    alternates = common / "objects" / "info" / "alternates"
    if alternates.exists() and alternates.read_text(encoding="utf-8").strip():
        findings.append("Git objects depend on an external alternate object store.")
    required = [
        "AGENTS.md", "README.md",
        "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
        "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md",
    ]
    for name in required:
        if not (root / name).is_file():
            findings.append("Missing startup entry: " + name)
    try:
        ahead, behind = git(root, "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
        comparison = {"ahead": int(ahead), "behind": int(behind)}
    except (RuntimeError, ValueError):
        comparison = None
        findings.append("Cannot compare with cached origin/main; inspect the remote.")
    return {
        "version": 1, "root": str(root), "branch": git(root, "branch", "--show-current"),
        "head": git(root, "rev-parse", "HEAD"), "origin_main_comparison": comparison,
        "clean": not bool(status), "worktrees": worktrees,
        "passed": not findings, "findings": findings,
        "scope": "Local workspace structure only; no fetch, repair, deletion or runtime acceptance.",
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--max-worktrees", type=int, default=3)
    args = parser.parse_args()
    if args.max_worktrees < 1:
        parser.error("--max-worktrees must be positive")
    try:
        report = inspect_workspace(args.root, require_clean=args.require_clean, max_worktrees=args.max_worktrees)
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
