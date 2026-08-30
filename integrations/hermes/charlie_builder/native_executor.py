"""Hermes-native, no-tool structured-patch execution in an isolated worktree."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .schemas import (NATIVE_PATCH_SCHEMA, NATIVE_REVIEW_SCHEMA,
                      validate_native_response, validate_native_review)
from modules.charlie.mission_admission import canonical_candidate_diff

REPOSITORY = "Crewless9086/amadeus-pig-tracking-system"
REMOTE = "https://github.com/Crewless9086/amadeus-pig-tracking-system.git"
MAX_CONTEXT_BYTES = 400_000
MAX_CONTEXT_ROUNDS = 3
DENIED_CONTEXT_PARTS = frozenset({".git", ".charlie_runner", "credentials", "secrets"})
DENIED_CONTEXT_PREFIXES = (".env",)
DENIED_PATCH_PREFIXES = (".github/", ".cursor/")


class NativeExecutionError(RuntimeError):
    """Stable fail-closed native execution reason."""


@dataclass(frozen=True)
class NativeAuthorization:
    mission_id: str
    generation: str
    native_execution_id: str
    native_attempt: int
    repository: str
    starting_main_sha: str
    branch: str
    worktree_digest: str
    owner_instruction_digest: str
    allowed_files: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    expires_at: str
    status: str = "valid"

    @classmethod
    def from_mapping(cls, value):
        row = dict(value or {})
        required = (
            "mission_id", "generation", "native_execution_id", "repository",
            "starting_main_sha", "branch", "worktree_digest", "owner_instruction_digest", "expires_at",
        )
        if any(not str(row.get(key) or "").strip() for key in required):
            raise NativeExecutionError("native_authorization_incomplete")
        files = tuple(sorted({normalize_repo_path(path) for path in row.get("allowed_files") or []}))
        commands = tuple(str(item).strip() for item in row.get("allowed_commands") or [] if str(item).strip())
        allowed_effects = tuple(str(item).strip() for item in row.get("allowed_effects") or [] if str(item).strip())
        effects = tuple(str(item).strip() for item in row.get("forbidden_effects") or [] if str(item).strip())
        try:
            expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise NativeExecutionError("native_authorization_invalid") from exc
        if (
            row.get("status") != "valid" or not str(row["native_execution_id"]).startswith("HNX-")
            or int(row.get("native_attempt") or 0) != 1 or row["repository"] != REPOSITORY
            or len(str(row["starting_main_sha"])) != 40 or not str(row["branch"]).startswith("charlie/")
            or not files or not commands or not allowed_effects or not effects
            or expires_at <= datetime.now(timezone.utc)
        ):
            raise NativeExecutionError("native_authorization_invalid")
        return cls(
            str(row["mission_id"]).strip(), str(row["generation"]).strip(),
            str(row["native_execution_id"]).strip(), int(row["native_attempt"]),
            str(row["repository"]).strip(), str(row["starting_main_sha"]).strip(),
            str(row["branch"]).strip(), str(row["worktree_digest"]).strip(),
            str(row["owner_instruction_digest"]).strip(), files, commands, allowed_effects, effects,
            expires_at.isoformat(),
        )


def content_identity(mission_id, generation, native_attempt=1):
    raw = f"{mission_id}:{generation}:native-{int(native_attempt)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return "HNX-" + digest.upper(), "charlie/" + mission_id.lower() + f"-native-{int(native_attempt)}"


def normalize_repo_path(value):
    raw = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or raw.startswith("/"):
        raise NativeExecutionError("repository_path_invalid")
    return path.as_posix()


def _safe_env(extra=None):
    keep = {"PATH", "SystemRoot", "WINDIR", "HOME", "USERPROFILE", "TMP", "TEMP", "LANG", "LC_ALL"}
    env = {key: value for key, value in os.environ.items() if key in keep}
    env.update({str(key): str(value) for key, value in dict(extra or {}).items()})
    return env


def run_argv(argv, *, cwd, timeout=120, env=None, input_text=None):
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(item, str) for item in argv):
        raise NativeExecutionError("native_command_invalid")
    try:
        return subprocess.run(
            list(argv), cwd=str(cwd), env=_safe_env(env), input=input_text,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeExecutionError("native_command_failed") from exc


def _resolved_inside(path, root):
    resolved = Path(path).resolve(strict=False)
    base = Path(root).resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise NativeExecutionError("native_path_escape") from exc
    return resolved


class NativeWorktree:
    def __init__(self, repository_root, worktree_root, authorization, *, runner=run_argv):
        self.repository_root = Path(repository_root).resolve(strict=True)
        requested_worktree = Path(worktree_root).absolute()
        for candidate in (requested_worktree, *requested_worktree.parents):
            if candidate.is_symlink():
                raise NativeExecutionError("native_worktree_symlink_rejected")
        self.worktree_root = requested_worktree.resolve(strict=False)
        self.authorization = authorization if isinstance(authorization, NativeAuthorization) else NativeAuthorization.from_mapping(authorization)
        self.runner = runner
        digest = hashlib.sha256(str(self.worktree_root).encode()).hexdigest()
        if digest != self.authorization.worktree_digest:
            raise NativeExecutionError("native_worktree_identity_mismatch")
        self.worktree_root.parent.mkdir(parents=True, exist_ok=True)
        if self.worktree_root.parent.is_symlink():
            raise NativeExecutionError("native_worktree_symlink_rejected")
        _resolved_inside(self.worktree_root, self.worktree_root.parent)
        if self.worktree_root == self.repository_root or self.repository_root in self.worktree_root.parents:
            raise NativeExecutionError("native_worktree_not_isolated")

    def ensure(self):
        if self.worktree_root.exists():
            if self.worktree_root.is_symlink():
                raise NativeExecutionError("native_worktree_symlink_rejected")
            origin = self._git("remote", "get-url", "origin")
            head = self._git("rev-parse", "HEAD")
            branch = self._git("branch", "--show-current")
            ancestor = self.runner(
                ["git", "merge-base", "--is-ancestor", self.authorization.starting_main_sha, head],
                cwd=self.worktree_root,
            )
            status_result = self.runner(["git", "status", "--porcelain"], cwd=self.worktree_root)
            if status_result.returncode != 0:
                raise NativeExecutionError("native_git_identity_failed")
            changed = tuple(filter(None, status_result.stdout.splitlines()))
            changed_paths = {
                normalize_repo_path(item[3:].split(" -> ")[-1]) for item in changed if len(item) > 3
            }
            if (origin != REMOTE or branch != self.authorization.branch
                    or ancestor.returncode != 0
                    or not changed_paths.issubset(self.authorization.allowed_files)):
                raise NativeExecutionError("native_worktree_recovery_conflict")
            return self.worktree_root
        self.worktree_root.parent.mkdir(parents=True, exist_ok=True)
        created = self.runner([
            "git", "worktree", "add", "-b", self.authorization.branch,
            str(self.worktree_root), self.authorization.starting_main_sha,
        ], cwd=self.repository_root, timeout=180)
        if created.returncode != 0:
            raise NativeExecutionError("native_worktree_create_failed")
        return self.ensure()

    def _git(self, *args):
        result = self.runner(["git", *args], cwd=self.worktree_root)
        if result.returncode != 0:
            raise NativeExecutionError("native_git_identity_failed")
        return result.stdout.strip()


class ContextBroker:
    def __init__(self, worktree, allowed_files, *, max_bytes=MAX_CONTEXT_BYTES):
        self.worktree = Path(worktree).resolve(strict=True)
        self.allowed_files = frozenset(normalize_repo_path(path) for path in allowed_files)
        self.max_bytes = int(max_bytes)
        self._seen = set()
        self._total = 0

    def read(self, paths):
        unique = list(dict.fromkeys(normalize_repo_path(path) for path in paths))
        if len(self._seen.union(unique)) > 20:
            raise NativeExecutionError("native_context_file_limit")
        payload = []
        for relative in unique:
            parts = PurePosixPath(relative).parts
            if any(part in DENIED_CONTEXT_PARTS for part in parts) or any(
                relative == prefix or relative.startswith(prefix) for prefix in DENIED_CONTEXT_PREFIXES
            ):
                raise NativeExecutionError("native_context_path_forbidden")
            tracked = run_argv(["git", "ls-files", "--error-unmatch", "--", relative], cwd=self.worktree)
            if tracked.returncode != 0:
                raise NativeExecutionError("native_context_not_tracked")
            unresolved = self.worktree / relative
            if unresolved.is_symlink() or any(parent.is_symlink() for parent in unresolved.parents if parent != self.worktree):
                raise NativeExecutionError("native_context_file_invalid")
            target = _resolved_inside(unresolved, self.worktree)
            if not target.is_file():
                raise NativeExecutionError("native_context_file_invalid")
            raw = target.read_bytes()
            if b"\x00" in raw:
                raise NativeExecutionError("native_context_binary_rejected")
            if relative not in self._seen:
                self._total += len(raw)
                self._seen.add(relative)
            if self._total > self.max_bytes:
                raise NativeExecutionError("native_context_size_limit")
            payload.append({"path": relative, "content": raw.decode("utf-8")})
        return payload


class PatchValidator:
    _HEADER = re.compile(r"^(?:---|\+\+\+) (?:a/|b/)?(.+)$", re.MULTILINE)

    def __init__(self, worktree, allowed_files):
        self.worktree = Path(worktree).resolve(strict=True)
        self.allowed_files = frozenset(normalize_repo_path(path) for path in allowed_files)

    def validate(self, patch):
        text = str(patch or "")
        if not text or len(text.encode()) > 200000 or "GIT binary patch" in text or "Binary files " in text:
            raise NativeExecutionError("native_patch_invalid")
        if any(marker in text for marker in (
            "old mode ", "new mode ", "rename from ", "rename to ",
            "new file mode ", "deleted file mode ",
        )):
            raise NativeExecutionError("native_patch_operation_forbidden")
        paths = []
        for raw in self._HEADER.findall(text):
            if raw == "/dev/null":
                raise NativeExecutionError("native_patch_delete_forbidden")
            relative = normalize_repo_path(raw.split("\t", 1)[0])
            if relative.startswith(DENIED_PATCH_PREFIXES) or relative not in self.allowed_files:
                raise NativeExecutionError("native_patch_scope_violation")
            unresolved = self.worktree / relative
            if unresolved.is_symlink() or any(parent.is_symlink() for parent in unresolved.parents if parent != self.worktree):
                raise NativeExecutionError("native_patch_symlink_rejected")
            target = _resolved_inside(unresolved, self.worktree)
            paths.append(relative)
        if not paths or not set(paths).issubset(self.allowed_files):
            raise NativeExecutionError("native_patch_paths_invalid")
        check = run_argv(
            ["git", "apply", "--check", "--whitespace=error-all", "-"],
            cwd=self.worktree, input_text=text,
        )
        if check.returncode != 0:
            raise NativeExecutionError("native_patch_check_failed")
        return tuple(sorted(set(paths)))

    def apply(self, patch):
        expected = self.validate(patch)
        applied = run_argv(
            ["git", "apply", "--whitespace=error-all", "-"],
            cwd=self.worktree, input_text=patch,
        )
        if applied.returncode != 0:
            raise NativeExecutionError("native_patch_apply_failed")
        changed = run_argv(["git", "diff", "--name-only", "--"], cwd=self.worktree)
        actual = tuple(sorted(normalize_repo_path(item) for item in changed.stdout.splitlines() if item.strip()))
        if changed.returncode != 0 or not set(actual).issubset(self.allowed_files) or actual != expected:
            raise NativeExecutionError("native_patch_post_apply_scope_violation")
        checked = run_argv(["git", "diff", "--check"], cwd=self.worktree)
        if checked.returncode != 0:
            raise NativeExecutionError("native_diff_check_failed")
        return actual


class HermesStructuredPatchWorker:
    def __init__(self, llm):
        if llm is None or not hasattr(llm, "complete_structured"):
            raise NativeExecutionError("hermes_structured_llm_unavailable")
        self.llm = llm

    def complete(self, packet, *, purpose="charlie.native.builder"):
        result = self.llm.complete_structured(
            instructions=(
                "Act only as a no-tool patch author. Return NEEDS_CONTEXT, PATCH_READY, or BLOCKED. "
                "Never claim to read files not included in the packet. PATCH_READY must contain a "
                "unified diff limited to allowed_files and a short test proposal."
            ),
            input=[{"type": "text", "text": json.dumps(packet, sort_keys=True)}],
            json_schema=NATIVE_PATCH_SCHEMA,
            schema_name="charlie.native.patch.v1",
            purpose=purpose,
            temperature=0.0,
            max_tokens=6000,
            timeout=120,
        )
        return validate_native_response(getattr(result, "parsed", None))


class HermesIndependentReviewer:
    """Fresh no-tool role-scoped reviewer; it never receives builder state or credentials."""

    def __init__(self, llm):
        if llm is None or not hasattr(llm, "complete_structured"):
            raise NativeExecutionError("hermes_structured_reviewer_unavailable")
        self.llm = llm

    def review(self, role, packet):
        role = str(role or "").upper()
        if role not in {"SECURITY", "FUNCTIONAL"}:
            raise NativeExecutionError("native_review_role_invalid")
        result = self.llm.complete_structured(
            instructions=(f"Act as an independent {role} reviewer with no tools. Review only the exact "
                          "candidate diff and evidence in this fresh packet. Return APPROVE or SEND_BACK; "
                          "SEND_BACK must include concrete findings. Never perform repository actions."),
            input=[{"type": "text", "text": json.dumps(packet, sort_keys=True)}],
            json_schema=NATIVE_REVIEW_SCHEMA, schema_name=f"charlie.native.{role.lower()}.review.v1",
            purpose=f"charlie.native.{role.lower()}_reviewer", temperature=0.0,
            max_tokens=3000, timeout=120,
        )
        return {"role": role, "reviewer_identity": f"hermes-native-{role.lower()}-reviewer-v1",
                **validate_native_review(getattr(result, "parsed", None))}


class NativeExecutionEngine:
    def __init__(self, worker, repository_root, worktree_root, authorization, *, heartbeat=None):
        self.worker = worker
        self.authorization = authorization if isinstance(authorization, NativeAuthorization) else NativeAuthorization.from_mapping(authorization)
        self.worktree = NativeWorktree(repository_root, worktree_root, self.authorization)
        self.heartbeat = heartbeat or (lambda: None)

    def build_patch(self, instruction, governance_context=None):
        root = self.worktree.ensure()
        broker = ContextBroker(root, self.authorization.allowed_files)
        context = broker.read(self.authorization.allowed_files)
        packet = {
            "protocol": "charlie_hermes_native_patch_v1",
            "mission_id": self.authorization.mission_id,
            "generation": self.authorization.generation,
            "instruction": str(instruction or "").strip(),
            "allowed_files": list(self.authorization.allowed_files),
            "allowed_commands": list(self.authorization.allowed_commands),
            "forbidden_effects": list(self.authorization.forbidden_effects),
            "governance_context": dict(governance_context or {}),
            "context": context,
        }
        requested = set(self.authorization.allowed_files)
        for _ in range(MAX_CONTEXT_ROUNDS + 1):
            self.heartbeat()
            response = self.worker.complete(packet)
            self.heartbeat()
            if response["state"] == "BLOCKED":
                return response
            if response["state"] == "PATCH_READY":
                changed = PatchValidator(root, self.authorization.allowed_files).apply(response["unified_diff"])
                return {**response, "changed_files": list(changed)}
            fresh = [path for path in response["context_paths"] if path not in requested]
            if not fresh:
                raise NativeExecutionError("native_context_request_replay")
            requested.update(fresh)
            packet["context"].extend(broker.read(fresh))
        raise NativeExecutionError("native_context_round_limit")

    def verify(self):
        evidence = []
        admitted = {
            "git status": ["git", "status"],
            "git diff": ["git", "diff"],
            "git diff --check": ["git", "diff", "--check"],
        }
        for command in self.authorization.allowed_commands:
            self.heartbeat()
            if command not in admitted:
                raise NativeExecutionError("native_verification_command_not_admitted")
            result = run_argv(admitted[command], cwd=self.worktree.worktree_root)
            evidence.append({"command": command, "returncode": result.returncode})
            if result.returncode != 0:
                raise NativeExecutionError("native_verification_failed")
        self.heartbeat()
        return evidence


_EXECUTOR_LOCK = threading.Lock()


def execution_lock():
    """One process-local lock complements canonical one-writer serialization."""
    return _EXECUTOR_LOCK


class NativePackager:
    """Deterministic parent-only commit, branch push and draft-PR packaging."""

    def __init__(self, worktree, authorization, token, *, opener=None):
        self.worktree = Path(worktree).resolve(strict=True)
        self.authorization = authorization if isinstance(authorization, NativeAuthorization) else NativeAuthorization.from_mapping(authorization)
        self.token = str(token or "").strip()
        self.opener = opener or urllib.request.urlopen
        if not self.token:
            raise NativeExecutionError("github_packager_token_required")

    def package(self, title, body):
        branch = self._git("branch", "--show-current")
        origin = self._git("remote", "get-url", "origin")
        changed = tuple(sorted(filter(None, self._git("diff", "--name-only").splitlines())))
        if (
            branch != self.authorization.branch or branch in {"main", "master"}
            or origin != REMOTE
            or (changed and not set(changed).issubset(self.authorization.allowed_files))
        ):
            raise NativeExecutionError("native_packaging_identity_invalid")
        if self._git("rev-parse", f"{self.authorization.starting_main_sha}^{{commit}}") != self.authorization.starting_main_sha:
            raise NativeExecutionError("native_packaging_base_invalid")
        ancestor = run_argv(
            ["git", "merge-base", "--is-ancestor", self.authorization.starting_main_sha, "HEAD"],
            cwd=self.worktree,
        )
        if ancestor.returncode != 0:
            raise NativeExecutionError("native_packaging_base_invalid")
        if changed:
            added = run_argv(["git", "add", "--", *changed], cwd=self.worktree)
            if added.returncode != 0:
                raise NativeExecutionError("native_packaging_add_failed")
            committed = run_argv([
                "git", "-c", "user.name=CHARLIE Native Packager",
                "-c", "user.email=charlie-native@users.noreply.github.com",
                "commit", "-m", str(title)[:72]], cwd=self.worktree)
            if committed.returncode != 0:
                raise NativeExecutionError("native_packaging_commit_failed")
        head = self._git("rev-parse", "HEAD")
        if head == self.authorization.starting_main_sha:
            raise NativeExecutionError("native_packaging_no_candidate")
        self._push_with_ephemeral_askpass()
        pull = self._find_pull(branch)
        if not pull:
            pull = self._github("POST", "/repos/Crewless9086/amadeus-pig-tracking-system/pulls", {
                "title": str(title)[:120], "body": str(body), "head": branch,
                "base": "main", "draft": True,
            })
        if not pull.get("draft") or (pull.get("head") or {}).get("sha") != head:
            raise NativeExecutionError("native_packaging_pr_unverified")
        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index",
             self.authorization.starting_main_sha, head, "--"],
            cwd=str(self.worktree), env=_safe_env(), capture_output=True, check=False, shell=False,
        )
        if diff.returncode != 0:
            raise NativeExecutionError("native_candidate_diff_failed")
        candidate_files = tuple(sorted(filter(None, self._git(
            "diff", "--no-ext-diff", "--no-textconv", "--name-only",
            self.authorization.starting_main_sha, head, "--").splitlines())))
        if candidate_files != tuple(sorted(self.authorization.allowed_files)):
            raise NativeExecutionError("native_candidate_scope_mismatch")
        return {"commit_sha": head, "pr_number": int(pull["number"]),
                "pr_url": pull.get("html_url"), "branch": branch,
                "changed_files": list(candidate_files),
                "candidate_diff_sha256": canonical_candidate_diff(list(candidate_files), diff.stdout)}

    def _git(self, *args):
        result = run_argv(["git", *args], cwd=self.worktree)
        if result.returncode != 0:
            raise NativeExecutionError("native_packaging_git_failed")
        return result.stdout.strip()

    def _push_with_ephemeral_askpass(self):
        root = Path(tempfile.mkdtemp(prefix="charlie-packager-"))
        helper = root / ("askpass.cmd" if os.name == "nt" else "askpass")
        try:
            if os.name == "nt":
                helper.write_text(f"@echo off\r\nif %1==Username echo x-access-token\r\nif %1==Password echo {self.token}\r\n", encoding="utf-8")
            else:
                helper.write_text(
                    "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' x-access-token;; *Password*) printf '%s\\n' '"
                    + self.token.replace("'", "'\\''") + "';; esac\n", encoding="utf-8")
                helper.chmod(0o700)
            pushed = run_argv(
                ["git", "push", "-u", "origin", self.authorization.branch],
                cwd=self.worktree,
                env={"GIT_ASKPASS": str(helper), "GIT_TERMINAL_PROMPT": "0"},
                timeout=180,
            )
            if pushed.returncode != 0:
                raise NativeExecutionError("native_packaging_push_failed")
        finally:
            try:
                helper.unlink(missing_ok=True)
                root.rmdir()
            except OSError:
                pass

    def _github(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            "https://api.github.com" + path, data=data, method=method,
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": "Bearer " + self.token,
                     "X-GitHub-Api-Version": "2022-11-28",
                     **({"Content-Type": "application/json"} if data else {})},
        )
        try:
            with self.opener(request, timeout=30) as response:
                result = json.loads(response.read().decode() or "{}")
        except (urllib.error.URLError, ValueError) as exc:
            raise NativeExecutionError("native_packaging_github_unavailable") from exc
        if not isinstance(result, (dict, list)):
            raise NativeExecutionError("native_packaging_github_invalid")
        return result

    def _find_pull(self, branch):
        pulls = self._github("GET", "/repos/Crewless9086/amadeus-pig-tracking-system/pulls?state=open&base=main&head=Crewless9086:" + branch)
        if len(pulls) > 1:
            raise NativeExecutionError("native_packaging_duplicate_pr")
        return pulls[0] if pulls else None
