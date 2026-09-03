"""Boot-supervised, plugin-independent CHARLIE native runner service."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .canonical_client import (CanonicalClient, CursorRetirementClient,
                               GitHubObserver, SlackNotifier)
from .execution import (HermesIndependentReviewer, HermesStructuredPatchWorker,
                        NativeExecutionEngine, NativeExecutionError,
                        NativePackager, content_identity,
                        run_argv, validate_primary_repository)
from .model_adapter import HermesAuxiliaryModel, run_schema_canary

REQUIRED_NAMES = (
    "CHARLIE_CANONICAL_API_URL", "CHARLIE_HERMES_GATEWAY_TOKEN", "SLACK_BOT_TOKEN",
    "CHARLIE_SLACK_OWNER_USER_ID", "CHARLIE_SLACK_CHARLIE_CHANNEL_ID",
    "CHARLIE_SLACK_BUILD_CHANNEL_ID", "CHARLIE_SLACK_APPROVALS_CHANNEL_ID",
    "CURSOR_API_KEY", "CHARLIE_GITHUB_PACKAGER_TOKEN",
)
BROAD_GITHUB_NAMES = ("CHARLIE_GITHUB_WRITE_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
RUNNER_SECRET_NAMES = (
    "CHARLIE_HERMES_GATEWAY_TOKEN", "SLACK_BOT_TOKEN", "CURSOR_API_KEY",
    "CHARLIE_GITHUB_PACKAGER_TOKEN", "CHARLIE_GITHUB_READ_TOKEN",
)


def read_profile_values(profile_home, names=REQUIRED_NAMES, *, config_path=None):
    home = Path(profile_home).resolve(strict=True)
    dotenv = Path(config_path).resolve(strict=True) if config_path else home / ".env"
    if not dotenv.is_file():
        raise NativeExecutionError("native_profile_configuration_unavailable")
    wanted = set(names) | set(BROAD_GITHUB_NAMES) | {"CHARLIE_GITHUB_READ_TOKEN"}
    values = {}
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key in wanted:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    broad = [name for name in BROAD_GITHUB_NAMES if values.get(name) or os.environ.get(name)]
    if broad:
        raise NativeExecutionError("broad_github_credential_forbidden:" + ",".join(broad))
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise NativeExecutionError("native_protected_configuration_missing:" + ",".join(missing))
    return values


def read_environment_values(names=REQUIRED_NAMES, *, environ=None):
    """Read only the runner allowlist from a service-owned environment."""
    source = os.environ if environ is None else environ
    broad = [name for name in BROAD_GITHUB_NAMES if str(source.get(name) or "").strip()]
    if broad:
        raise NativeExecutionError("broad_github_credential_forbidden:" + ",".join(broad))
    values = {name: str(source.get(name) or "").strip()
              for name in set(names) | {"CHARLIE_GITHUB_READ_TOKEN"}}
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise NativeExecutionError("native_protected_configuration_missing:" + ",".join(missing))
    return values


class ProcessLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise NativeExecutionError("native_runner_already_active") from exc

    def release(self):
        if not self.handle:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0); msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close(); self.handle = None

    def __enter__(self):
        self.acquire(); return self

    def __exit__(self, *_args):
        self.release()


class NativeRunnerService:
    """Processes at most one canonical write mission; it has no merge/deploy API."""

    def __init__(self, *, profile_home, repository_root, worktree_root,
                 canonical=None, cursor=None, github=None, notifier=None, model=None,
                 clock=None, status_path=None, config_path=None, configuration_source="profile"):
        self.profile_home = Path(profile_home).resolve(strict=True)
        self.repository_root = Path(repository_root)
        self.worktree_root = Path(worktree_root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if canonical is None:
            values = (read_environment_values() if configuration_source == "environment"
                      else read_profile_values(self.profile_home, config_path=config_path))
            if configuration_source == "environment":
                # Retain secrets only in the deterministic parent object. They
                # must not remain inherited by model or verification children.
                for name in RUNNER_SECRET_NAMES:
                    os.environ.pop(name, None)
        else:
            values = {}
        self.canonical = canonical or CanonicalClient(values["CHARLIE_CANONICAL_API_URL"], values["CHARLIE_HERMES_GATEWAY_TOKEN"])
        self.cursor = cursor or (CursorRetirementClient(values["CURSOR_API_KEY"]) if values else None)
        read_token = values.get("CHARLIE_GITHUB_READ_TOKEN", "") if values else ""
        self.github = github or GitHubObserver(read_token)
        self.notifier = notifier or (SlackNotifier(values["SLACK_BOT_TOKEN"]) if values else None)
        self.model = model or HermesAuxiliaryModel(profile_home=self.profile_home)
        self.packager_token = values.get("CHARLIE_GITHUB_PACKAGER_TOKEN", "") if values else "test-only"
        self.slack_approval_channel = values.get("CHARLIE_SLACK_APPROVALS_CHANNEL_ID", "") if values else "C-APPROVALS"
        self.status_path = Path(status_path or (self.worktree_root / ".runner-status.json"))
        self._canary_complete = False
        self._stop_event = threading.Event()

    def _ensure_running(self):
        if getattr(self, "_stop_event", None) is not None and self._stop_event.is_set():
            raise NativeExecutionError("native_runner_shutdown_requested")

    def _status(self, **state):
        safe = {key: value for key, value in state.items() if "token" not in key.lower()}
        safe["updated_at"] = self.clock().isoformat()
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(safe, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.status_path)
        return safe

    def _record_progress(self, mission_id, payload, *, claim_id=""):
        value = dict(payload)
        if claim_id and value.get("event") != "native_writer_released":
            value["worker_claim_id"] = claim_id
        result = self.canonical.progress(mission_id, value)
        if not isinstance(result, dict) or not result or result.get("success") is False \
                or str(result.get("status") or "").endswith(("_invalid", "_conflict", "_required", "_failed")):
            raise NativeExecutionError(str((result or {}).get("status") or "native_progress_record_failed"))
        return result

    def _release_claim(self, mission_id, native_execution_id, claim_id, status):
        if not claim_id:
            return {}
        return self._record_progress(mission_id, {
            "native_execution_id": native_execution_id, "execution_status": status,
            "release_claim_id": claim_id, "event": "native_writer_released",
        })

    @staticmethod
    def _claim_identity(native_execution_id):
        return "HNC-" + hashlib.sha256((str(native_execution_id) + ":standalone").encode()).hexdigest()

    def _prove_or_reacquire_claim(self, mission_id, native):
        """Atomically prove this exact execution owns the canonical writer claim."""
        native_id = str(native.get("native_execution_id") or "")
        expected = self._claim_identity(native_id)
        stored = str(native.get("worker_claim_id") or "")
        if stored and stored != expected:
            raise NativeExecutionError("native_writer_identity_conflict")
        self._record_progress(mission_id, {
            "native_execution_id": native_id,
            "execution_status": str(native.get("execution_status") or "RUNNING"),
            "worker_claim_id": expected,
            "claim_expires_at": (self.clock() + timedelta(minutes=10)).isoformat(),
            "runner_stage": str(native.get("runner_stage") or "builder"),
            "event": "native_writer_claimed",
        })
        return expected

    def _claim_heartbeat(self, mission_id, native_execution_id, claim_id, stage):
        self._record_progress(mission_id, {
            "native_execution_id": native_execution_id,
            "execution_status": "RUNNING",
            "worker_claim_id": claim_id,
            "claim_expires_at": (self.clock() + timedelta(minutes=10)).isoformat(),
            "runner_stage": stage,
            "event": "native_writer_claimed",
        })

    def _request_admission(self, mission_id, native, *, stage):
        result = self.canonical.request_admission(
            mission_id, native["head_sha"], native["pr_number"])
        if not isinstance(result, dict) or result.get("success") is not True:
            raise NativeExecutionError("native_mission_admission_request_failed")
        self._record_progress(mission_id, {
            "native_execution_id": native["native_execution_id"],
            "execution_status": stage, "pr_number": native["pr_number"],
            "head_sha": native["head_sha"], "changed_files": native["changed_files"],
            "candidate_diff_sha256": native["candidate_diff_sha256"],
            "event": "native_mission_admission_requested",
        }, claim_id=native.get("worker_claim_id"))

    def _trusted_admission_ready(self, native):
        state = self.github.pull_state(int(native["pr_number"]))
        return (state.get("head_sha") == native.get("head_sha")
                and (state.get("checks") or {}).get("mission-admission") == "success")

    def once(self, *, dry_run=False):
        self._ensure_running()
        with ProcessLock(self.worktree_root / ".charlie-native-runner.lock"):
            self._ensure_running()
            rows = self.canonical.resumable()
            if not rows:
                return self._status(state="IDLE")
            if len(rows) != 1:
                raise NativeExecutionError("native_resumable_mission_count_invalid")
            mission_id = str(rows[0].get("mission_id") or "")
            if not mission_id:
                raise NativeExecutionError("native_resumable_mission_invalid")
            if dry_run:
                return self._status(state="DRY_RUN", mission_id=mission_id)
            return self._process(mission_id)

    def _process(self, mission_id):
        self._ensure_running()
        loaded = self.canonical.mission(mission_id)
        mission = dict(loaded.get("mission") or {})
        metadata = dict(mission.get("metadata") or {})
        retirement = dict(metadata.get("cursor_provider_retirement") or {})
        if not retirement:
            self._ensure_running()
            retirement = self._retire_attempt_five(mission_id, metadata)
        if retirement.get("provider_status") != "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT":
            raise NativeExecutionError("cursor_attempt_five_retirement_unproven")
        loaded = self.canonical.mission(mission_id)
        mission = dict(loaded.get("mission") or {})
        metadata = dict(mission.get("metadata") or {})
        existing_native = dict(metadata.get("hermes_native_execution") or {})
        writers = self.canonical.writers()
        if existing_native:
            if writers > 1:
                raise NativeExecutionError("native_writer_identity_conflict")
            claim = self._prove_or_reacquire_claim(mission_id, existing_native)
            existing_native["worker_claim_id"] = claim
            repository, _, _ = validate_primary_repository(self.repository_root, self.worktree_root)
            worktree = self.worktree_root / mission_id / existing_native["generation"] / "native-1"
            if not self._canary_complete:
                run_schema_canary(self.model)
                self._canary_complete = True
            if int(existing_native.get("pr_number") or 0):
                return self._supervise(mission, existing_native)
            return self._build(mission, existing_native, repository, worktree)
        if writers != 0:
            raise NativeExecutionError("native_writer_claim_not_released")
        authorization = self.canonical.renew_authority(mission_id)
        if authorization.get("status") != "valid" or authorization.get("version") != "charlie_pre_dispatch_authorization_v2":
            raise NativeExecutionError("fresh_native_dispatch_authorization_required")
        repository, _, main_sha = validate_primary_repository(self.repository_root, self.worktree_root)
        generation = str(authorization.get("generation") or "")
        native_id, branch = content_identity(mission_id, generation, 1)
        worktree = self.worktree_root / mission_id / generation / "native-1"
        digest = hashlib.sha256(str(worktree.resolve(strict=False)).encode()).hexdigest()
        native = self.canonical.prepare_native(mission_id, digest, main_sha)
        if native.get("native_execution_id") != native_id or native.get("branch") != branch:
            raise NativeExecutionError("native_execution_identity_conflict")
        if not self._canary_complete and not int(native.get("pr_number") or 0):
            self._ensure_running()
            run_schema_canary(self.model)
            self._canary_complete = True
        if int(native.get("pr_number") or 0):
            return self._supervise(mission, native)
        return self._build(mission, native, repository, worktree)

    def _retire_attempt_five(self, mission_id, metadata):
        self._ensure_running()
        state = dict(metadata.get("external_supervisor_state") or {})
        if int(state.get("execution_attempt") or 0) != 5 or self.cursor is None:
            raise NativeExecutionError("cursor_attempt_five_identity_incomplete")
        agent_id, run_id, branch = (str(state.get(key) or "") for key in ("cursor_agent_id", "cursor_run_id", "branch"))
        agent, run = self.cursor.get_agent(agent_id), self.cursor.get_run(agent_id, run_id)
        run_state = str(run.get("status") or "").upper()
        if run_state not in {"FINISHED", "SUCCEEDED", "FAILED", "CANCELLED"}:
            self.cursor.cancel(agent_id, run_id)
            run_state = str(self.cursor.get_run(agent_id, run_id).get("status") or "").upper()
        if run_state not in {"FINISHED", "SUCCEEDED", "FAILED", "CANCELLED"}:
            raise NativeExecutionError("cursor_attempt_five_not_terminal")
        if str(agent.get("status") or "").upper() != "ARCHIVED":
            self.cursor.archive(agent_id)
            agent = self.cursor.get_agent(agent_id)
        if str(agent.get("status") or "").upper() != "ARCHIVED" or self.github.branch_exists(branch) or self.github.find_pull(branch):
            raise NativeExecutionError("cursor_attempt_five_zero_candidate_unproven")
        return self.canonical.retire_cursor(mission_id, {
            "generation": state.get("generation"), "cursor_agent_id": agent_id,
            "cursor_run_id": run_id, "execution_attempt": 5, "provider_agent_state": "ARCHIVED",
            "provider_run_state": "CANCELLED" if run_state == "CANCELLED" else "FINISHED",
            "branch": branch, "repository_mutation": False, "remote_branch_created": False,
            "pr_number": 0, "head_sha": "", "exact_candidate": "absent",
        })

    def _build(self, mission, authorization, repository, worktree):
        self._ensure_running()
        claim = self._claim_identity(authorization["native_execution_id"])
        progress = self._record_progress(mission["mission_id"], {
            "native_execution_id": authorization["native_execution_id"], "execution_status": "RUNNING",
            "worker_claim_id": claim, "claim_expires_at": (self.clock() + timedelta(minutes=10)).isoformat(),
            "runner_stage": "builder", "event": "native_writer_claimed",
        })
        heartbeat = lambda: self._claim_heartbeat(
            mission["mission_id"], authorization["native_execution_id"], claim, "builder")
        engine = NativeExecutionEngine(HermesStructuredPatchWorker(self.model), repository, worktree,
                                       authorization, heartbeat=heartbeat)
        recovered = False
        if Path(worktree).exists():
            head = run_argv(["git", "rev-parse", "HEAD"], cwd=worktree)
            dirty = run_argv(["git", "status", "--porcelain"], cwd=worktree)
            if head.returncode or dirty.returncode:
                raise NativeExecutionError("native_worktree_recovery_unavailable")
            if head.stdout.strip() != authorization["starting_main_sha"]:
                if dirty.stdout.strip() or not authorization.get("builder_identity"):
                    raise NativeExecutionError("native_packaging_recovery_unproven")
                recovered = True
        if recovered:
            built = {"state": "PATCH_READY", "changed_files": list(authorization["allowed_files"]),
                     "worker_identity": authorization.get("builder_identity"),
                     "worker_agent_id": authorization.get("builder_agent_id")}
        else:
            self._ensure_running()
            built = engine.build_patch(mission.get("raw_text") or mission.get("title"),
                                       governance_context=self.canonical.native_context(mission["mission_id"]))
            if built.get("state") != "PATCH_READY":
                self._release_claim(mission["mission_id"], authorization["native_execution_id"], claim, "BLOCKED")
                return self._status(state="BLOCKED", mission_id=mission["mission_id"], reason=built.get("reason"))
        self._ensure_running()
        evidence = engine.verify()
        self._record_progress(mission["mission_id"], {
            "native_execution_id": authorization["native_execution_id"], "execution_status": "VERIFIED",
            "changed_files": built.get("changed_files"), "builder_identity": built.get("worker_identity"),
            "builder_agent_id": built.get("worker_agent_id"), "runner_stage": "tester",
            "stage_artifact": {"kind": "bounded_verification", "commands": evidence},
            "event": "native_verification_completed",
        }, claim_id=claim)
        heartbeat()
        self._ensure_running()
        packaged = NativePackager(worktree, authorization, self.packager_token,
                                  heartbeat=heartbeat).package(
            mission.get("title") or "CHARLIE native mission",
            "Hermes-native structured patch. Draft only; no merge or deployment authority.")
        candidate = {
            "pr_number": packaged["pr_number"], "base_sha": authorization["starting_main_sha"],
            "head_sha": packaged["commit_sha"], "branch": packaged["branch"],
            "changed_files": packaged["changed_files"], "candidate_diff_sha256": packaged["candidate_diff_sha256"],
        }
        self._record_progress(mission["mission_id"], {
            "native_execution_id": authorization["native_execution_id"], "execution_status": "PACKAGED",
            **candidate, "event": "native_candidate_packaged",
        }, claim_id=claim)
        return self._complete_initial_candidate(mission, {**authorization, **candidate,
                                                          "execution_status": "PACKAGED",
                                                          "worker_claim_id": claim}, evidence)

    def _complete_initial_candidate(self, mission, native, evidence=None):
        candidate = {key: native[key] for key in (
            "pr_number", "base_sha", "head_sha", "branch", "changed_files", "candidate_diff_sha256")}
        if native.get("execution_status") == "PACKAGED":
            self.canonical.bind_candidate(mission["mission_id"], candidate)
            self._record_progress(mission["mission_id"], {
                "native_execution_id": native["native_execution_id"], "execution_status": "CANDIDATE_BOUND",
                **candidate, "event": "native_candidate_bound",
            }, claim_id=native.get("worker_claim_id"))
            native = {**native, "execution_status": "CANDIDATE_BOUND"}
        if native.get("execution_status") == "CANDIDATE_BOUND":
            self._request_admission(mission["mission_id"], native, stage="ADMISSION_PENDING")
            native = {**native, "execution_status": "ADMISSION_PENDING"}
        if not self._trusted_admission_ready(native):
            return self._status(state="ADMISSION_PENDING", mission_id=mission["mission_id"],
                                native_execution_id=native["native_execution_id"],
                                branch=native["branch"], pr_number=native["pr_number"],
                                head_sha=native["head_sha"])
        self._claim_heartbeat(mission["mission_id"], native["native_execution_id"],
                              native.get("worker_claim_id"), "challenge_review")
        reviewer = HermesIndependentReviewer(self.model)
        packet = {"candidate": {key: candidate[key] for key in (
            "pr_number", "base_sha", "head_sha", "candidate_diff_sha256", "changed_files")},
            "verification": list(evidence or (native.get("stage_artifact") or {}).get("commands") or [])}
        self._ensure_running()
        challenge = reviewer.review("CHALLENGE", packet)
        self._claim_heartbeat(mission["mission_id"], native["native_execution_id"],
                              native.get("worker_claim_id"), "challenge_review")
        if challenge.get("verdict") != "SEND_BACK":
            raise NativeExecutionError("commissioning_genuine_send_back_required")
        recorded = self._record_progress(mission["mission_id"], {
            "native_execution_id": native["native_execution_id"], "execution_status": "SEND_BACK",
            "pr_number": candidate["pr_number"], "head_sha": candidate["head_sha"],
            "changed_files": candidate["changed_files"], "candidate_diff_sha256": candidate["candidate_diff_sha256"],
            "review_challenge": challenge, "event": "native_challenge_send_back",
        }, claim_id=native.get("worker_claim_id"))
        return self._status(state="SEND_BACK", mission_id=mission["mission_id"],
                            native_execution_id=native["native_execution_id"],
                            branch=native["branch"], pr_number=candidate["pr_number"], head_sha=candidate["head_sha"])

    def _supervise(self, mission, native):
        if native.get("execution_status") in {"PACKAGED", "CANDIDATE_BOUND", "ADMISSION_PENDING"}:
            return self._complete_initial_candidate(mission, native)
        if native.get("execution_status") in {"CORRECTION_PACKAGED", "CORRECTION_BOUND", "CORRECTION_ADMISSION_PENDING"}:
            return self._complete_corrected_candidate(mission, native)
        if (native.get("execution_status") == "SEND_BACK"
                and int(native.get("correction_rounds") or 0) == 0):
            return self._correct(mission, native)
        state = self.github.pull_state(int(native["pr_number"]))
        if (state["all_required_checks_pass"] is True
                and native.get("review_security", {}).get("verdict") == "APPROVE"
                and native.get("review_functional", {}).get("verdict") == "APPROVE"
                and state["head_sha"] == native.get("head_sha")
                and int(native.get("correction_rounds") or 0) >= 1):
            metadata = dict(mission.get("metadata") or {})
            external = dict(metadata.get("external_supervisor_state") or {})
            already_notified = str(native.get("owner_notification_head") or "") == state["head_sha"]
            if self.notifier and not already_notified:
                self.notifier.post(external.get("slack_channel_id"),
                    f"Mission {mission['mission_id']} is ready for an exact owner decision on draft PR #{state['pr_number']} head {state['head_sha']}.",
                    thread_ts=external.get("slack_thread_ts", ""),
                    idempotency_key=f"{mission['mission_id']}:{state['head_sha']}:thread")
                self.notifier.post(metadata.get("slack_approval_channel_id") or self.slack_approval_channel,
                    f"OWNER DECISION REQUIRED: mission {mission['mission_id']} PR #{state['pr_number']} exact head {state['head_sha']}. No merge or deployment has occurred.",
                    idempotency_key=f"{mission['mission_id']}:{state['head_sha']}:approvals")
            if not already_notified:
                self._record_progress(mission["mission_id"], {
                    "native_execution_id": native["native_execution_id"],
                    "execution_status": "OWNER_DECISION_REQUIRED", "pr_number": state["pr_number"],
                    "head_sha": state["head_sha"], "checks": state["checks"],
                    "review_verdict": "APPROVE", "owner_notification_head": state["head_sha"],
                    "event": "owner_decision_required",
                }, claim_id=native.get("worker_claim_id"))
            # Claim release is a separate idempotent recovery obligation. A
            # crash after recording/notifying the owner must not strand it.
            if native.get("worker_claim_id"):
                self._release_claim(mission["mission_id"], native["native_execution_id"],
                                    native["worker_claim_id"], "OWNER_DECISION_REQUIRED")
            state["state"] = "OWNER_DECISION_REQUIRED"
        status_name = state.pop("state", "SUPERVISING")
        return self._status(state=status_name, mission_id=mission["mission_id"],
                            native_execution_id=native["native_execution_id"], **state)

    def _correct(self, mission, native):
        self._ensure_running()
        worktree = self.worktree_root / mission["mission_id"] / native["generation"] / "native-1"
        findings = "; ".join(native.get("review_challenge", {}).get("findings") or [])
        claim = str(native.get("worker_claim_id") or "")
        heartbeat = lambda: self._claim_heartbeat(
            mission["mission_id"], native["native_execution_id"], claim, "correction")
        engine = NativeExecutionEngine(HermesStructuredPatchWorker(self.model), self.repository_root,
                                       worktree, native, heartbeat=heartbeat)
        self._ensure_running()
        built = engine.build_patch("Apply only this independent SEND_BACK correction: " + findings,
                                   governance_context=self.canonical.native_context(mission["mission_id"]))
        if built.get("state") != "PATCH_READY":
            raise NativeExecutionError("native_correction_not_ready")
        self._ensure_running()
        evidence = engine.verify()
        heartbeat()
        self._ensure_running()
        packaged = NativePackager(worktree, native, self.packager_token,
                                  heartbeat=heartbeat).package(
            mission.get("title") or "CHARLIE native mission",
            "Corrected Hermes-native structured patch. Draft only; no merge or deployment authority.")
        binding = {"pr_number": packaged["pr_number"], "base_sha": native["starting_main_sha"],
                   "head_sha": packaged["commit_sha"], "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                   "changed_files": packaged["changed_files"], "branch": packaged["branch"]}
        self._record_progress(mission["mission_id"], {
            "native_execution_id": native["native_execution_id"], "execution_status": "CORRECTION_PACKAGED",
            **binding, "event": "native_correction_packaged",
        }, claim_id=native.get("worker_claim_id"))
        return self._complete_corrected_candidate(mission, {**native, **binding,
                                                            "execution_status": "CORRECTION_PACKAGED"}, evidence)

    def _complete_corrected_candidate(self, mission, native, evidence=None):
        binding = {key: native[key] for key in (
            "pr_number", "base_sha", "head_sha", "candidate_diff_sha256", "changed_files", "branch")}
        if native.get("execution_status") == "CORRECTION_PACKAGED":
            self.canonical.bind_candidate(mission["mission_id"], binding)
            self._record_progress(mission["mission_id"], {
                "native_execution_id": native["native_execution_id"], "execution_status": "CORRECTION_BOUND",
                **binding, "event": "native_correction_candidate_bound",
            }, claim_id=native.get("worker_claim_id"))
            native = {**native, "execution_status": "CORRECTION_BOUND"}
        if native.get("execution_status") == "CORRECTION_BOUND":
            self._request_admission(mission["mission_id"], native,
                                    stage="CORRECTION_ADMISSION_PENDING")
            native = {**native, "execution_status": "CORRECTION_ADMISSION_PENDING"}
        if not self._trusted_admission_ready(native):
            return self._status(state="CORRECTION_ADMISSION_PENDING",
                                mission_id=mission["mission_id"],
                                native_execution_id=native["native_execution_id"],
                                branch=native["branch"], pr_number=native["pr_number"],
                                head_sha=native["head_sha"])
        self._claim_heartbeat(mission["mission_id"], native["native_execution_id"],
                              native.get("worker_claim_id"), "independent_review")
        reviewer = HermesIndependentReviewer(self.model)
        packet = {"candidate": {key: binding[key] for key in (
            "pr_number", "base_sha", "head_sha", "candidate_diff_sha256", "changed_files")},
            "verification": list(evidence or (native.get("stage_artifact") or {}).get("commands") or [])}
        self._ensure_running()
        security = reviewer.review("SECURITY", packet)
        self._claim_heartbeat(mission["mission_id"], native["native_execution_id"],
                              native.get("worker_claim_id"), "independent_review")
        self._ensure_running()
        functional = reviewer.review("FUNCTIONAL", packet)
        self._claim_heartbeat(mission["mission_id"], native["native_execution_id"],
                              native.get("worker_claim_id"), "independent_review")
        if security.get("verdict") != functional.get("verdict") or security.get("verdict") != "APPROVE":
            raise NativeExecutionError("native_corrected_review_not_approved")
        self._record_progress(mission["mission_id"], {
            "native_execution_id": native["native_execution_id"], "execution_status": "SEND_BACK_CORRECTED",
            "correction_rounds": 1, "pr_number": binding["pr_number"], "head_sha": binding["head_sha"],
            "changed_files": binding["changed_files"], "candidate_diff_sha256": binding["candidate_diff_sha256"],
            "review_security": security, "review_functional": functional,
            "event": "native_send_back_corrected",
        }, claim_id=native.get("worker_claim_id"))
        return self._status(state="CHECKS_PENDING", mission_id=mission["mission_id"],
                            native_execution_id=native["native_execution_id"],
                            branch=binding["branch"], pr_number=binding["pr_number"], head_sha=binding["head_sha"])

    def watch(self, poll_seconds=15, *, stop_event=None):
        failures = {}
        stopping = stop_event or threading.Event()
        self._stop_event = stopping
        while not stopping.is_set():
            try:
                self.once()
                failures.clear()
                stopping.wait(max(5, min(int(poll_seconds), 300)))
            except NativeExecutionError as exc:
                reason = str(exc)
                failures[reason] = failures.get(reason, 0) + 1
                self._status(state="BLOCKED", reason=reason, repeated=failures[reason])
                if failures[reason] >= 2:
                    # A repeated identical mission defect is a bounded canonical
                    # stop, not a crash. Exit cleanly so the service supervisor
                    # does not manufacture an infinite restart loop.
                    return 0
                stopping.wait(min(60, 5 * (2 ** (failures[reason] - 1))))
        self._status(state="STOPPED", reason="sigterm")
        return 0
