"""Single-mission private engineering execution on the existing Render worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ast
import json
import os
from pathlib import Path
import re
import shutil
import signal
import threading
import tempfile
import urllib.request
import uuid

from modules.charlie.cloud_engineering import CONTRACT, WORKER, TERMINAL, digest, validate_manifest
from modules.charlie.native_runner.execution import (
    BUILDER_CORRECTIONS, ContextBroker, HermesIndependentReviewer, HermesStructuredPatchWorker,
    NativeAuthorization, NativeExecutionError, NativeWorktree, PatchValidator, run_argv,
)
from modules.charlie.native_runner.intake_service import NoRedirect
from modules.charlie.native_runner.model_adapter import HermesAuxiliaryModel, model_failure_diagnostics
from modules.charlie.native_runner.test_sandbox import run_isolated_tests
from modules.charlie.native_runner.schemas import NativeSchemaError

BASE_URL = "https://amadeus-pig-tracking-system.onrender.com/api/charlie/core/engineering/missions"
ROOT = Path("/var/data/cloud-engineering")
ACCEPTANCE_PATH = "tests/test_core_immutable_acceptance.py"
# Only deterministic, state-field conflicts in a successfully audited builder
# response can consume another existing builder iteration.
RECOVERABLE_BUILDER_ERRORS = frozenset({
    "native_context_state_invalid", "native_patch_state_invalid", "native_blocked_state_invalid",
})
BUILDER_SCHEMA_ERRORS = RECOVERABLE_BUILDER_ERRORS | frozenset({
    "native_response_schema_invalid", "native_response_state_invalid",
    "native_context_request_invalid", "native_test_proposal_invalid",
    "native_patch_size_invalid", "native_reason_invalid",
})
MODEL_RESPONSE_BYTES = 600000
MODEL_AUDIT_BYTES = 16384


def need(value, reason):
    if not value:
        raise NativeExecutionError(reason)


def write_once(path, value, *, max_bytes=None):
    path = Path(path)
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if max_bytes is not None:
        need(len(content) <= max_bytes, "model_evidence_size_bound")
    # Exclusive creation is private from the first byte, including on failure.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.chmod(path, 0o600)
    return hashlib.sha256(content).hexdigest()


class Client:
    def __init__(self, mission_id, token, *, opener=None):
        need(re.fullmatch("[A-Za-z0-9_-]{1,90}", mission_id), "mission_invalid")
        need(re.fullmatch("[A-Za-z0-9_-]{43,128}", token), "credential_invalid")
        self.mission_id, self.token = mission_id, token
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, operation, payload=None):
        need(operation in {"current", "claim", "check", "reserve", "progress", "complete", "block"},
             "operation_invalid")
        request = urllib.request.Request(BASE_URL + "/" + self.mission_id + "/" + operation,
            data=json.dumps(payload or {}).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST")
        # Never retry an ambiguous POST; a consumed claim/reservation stays consumed.
        with self.opener.open(request, timeout=20) as response:
            need(response.status == 200, "canonical_refused")
            raw = response.read(600001)
            need(len(raw) <= 600000, "canonical_response_bound")
            data = json.loads(raw)
        need(data.get("contract") == CONTRACT and data.get("success") is True, "canonical_invalid")
        return data["grant"]


def checked_git(arguments, cwd):
    result = run_argv(["git", *arguments], cwd=cwd, timeout=180)
    need(result.returncode == 0, "engineering_git_failed")
    return result.stdout.strip()


def stage_tree(worktree, destination, acceptance_source):
    """Only tracked regular source enters the test sandbox; no git/config/secrets."""
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    paths = checked_git(["ls-files", "-z"], worktree).split("\0")
    admitted, total = [], 0
    for relative in paths:
        if not relative:
            continue
        parts = Path(relative).parts
        if any(part in {".git", ".charlie_runner", "credentials", "secrets", ".codex", ".agents", ".aws"}
               or part.startswith(".env") for part in parts):
            continue
        source = Path(worktree) / relative
        need(not source.is_symlink() and source.is_file() and
             not any(parent.is_symlink() for parent in source.parents), "staging_nonregular_file")
        total += source.stat().st_size
        admitted.append((relative, source))
        need(total <= 150000000 and len(admitted) <= 20000, "staging_size_bound")
    for relative, source in admitted:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
    acceptance = destination / ACCEPTANCE_PATH
    need(not acceptance.exists(), "acceptance_path_collision")
    acceptance.write_text(acceptance_source, encoding="utf-8")
    acceptance.chmod(0o644)
    for directory, _, _ in os.walk(destination):
        Path(directory).chmod(0o755)
    return destination


class EngineeringRun:
    def __init__(self, client, grant, instance, *, root=ROOT, model_factory=HermesAuxiliaryModel,
                 tester=run_isolated_tests, stop=None, report=None):
        self.client, self.grant, self.instance = client, grant, instance
        self.manifest = validate_manifest(grant["manifest"])
        self.directory = Path(root) / self.manifest["generation"]
        self.model_factory, self.tester = model_factory, tester
        self.stop = stop or threading.Event()
        self.report = report or (lambda item: print(json.dumps(item, sort_keys=True), flush=True))

    def check(self):
        need(not self.stop.is_set(), "stop_requested")
        need(datetime.now(timezone.utc) < datetime.fromisoformat(self.grant["expires_at"]), "grant_expired")
        state = self.client.call("check", {"instance": self.instance})
        need(state["manifest"] == self.manifest and state["instance"] == self.instance,
             "grant_changed")
        return state

    def progress(self, stage, artifact):
        self.check()
        self.grant = self.client.call("progress", {"instance": self.instance,
            "stage": stage, "artifact_sha256": digest(artifact)})
        self.report({"status": "engineering_stage", "stage": stage,
                     "instance": self.instance, "mission_id": self.client.mission_id})

    def reserve(self, *, request_sha256, input_bytes, max_tokens, task):
        self.check()
        need(not any(item["request_sha256"] == request_sha256
                     for item in self.grant.get("reservations", [])), "duplicate_model_request")
        reservation = {"instance": self.instance, "request_id": uuid.uuid4().hex,
                       "request_sha256": request_sha256, "input_bytes": input_bytes,
                       "max_tokens": max_tokens, "task": task}
        self.grant = self.client.call("reserve", reservation)
        write_once(self.directory / ("reservation-" + reservation["request_id"] + ".json"),
                   reservation)
        # A delayed HTTP response or fsync must not start inference after the
        # deadline/stop. Keep the durable reservation consumed on refusal.
        need(not self.stop.is_set(), "stop_requested")
        need(datetime.now(timezone.utc) + timedelta(seconds=130) <
             datetime.fromisoformat(self.grant["expires_at"]), "model_deadline_margin")
        # No refund or retry after this point, including parse errors/timeouts.

    def record_model_response(self, result, request):
        """Retain successful parsed output before native semantics; never log it."""
        audit = getattr(result, "audit", None)
        need(isinstance(audit, dict) and audit.get("strict_budget") is True
             and type(audit.get("attempt_count")) is int and audit["attempt_count"] == 1,
             "strict_model_audit_required")
        audit = dict(audit)
        request_sha = audit.get("request_sha256")
        need(isinstance(request_sha, str) and re.fullmatch("[a-f0-9]{64}", request_sha),
             "model_response_reservation_invalid")
        reservations = [row for row in self.grant.get("reservations", [])
                        if row.get("request_sha256") == request_sha]
        need(len(reservations) == 1, "model_response_reservation_invalid")
        reservation = reservations[0]
        request_id = reservation.get("request_id")
        need(isinstance(request_id, str) and re.fullmatch("[a-f0-9]{32}", request_id)
             and reservation.get("instance") == self.instance
             and all(audit.get(key) == reservation.get(key)
                     for key in ("input_bytes", "max_tokens", "task"))
             and audit.get("task") == request["task"]
             and audit.get("max_tokens") == request["max_tokens"],
             "model_response_reservation_invalid")
        audit_sha = write_once(self.directory / ("model-" + request_sha + ".json"),
                               audit, max_bytes=MODEL_AUDIT_BYTES)
        name = "model-response-" + request_id + ".json"
        response_sha = write_once(self.directory / name, {
            "request_id": request_id, "request_sha256": request_sha,
            "task": audit["task"], "audit_sha256": audit_sha,
            "parsed": getattr(result, "parsed", None),
        }, max_bytes=MODEL_RESPONSE_BYTES)
        return audit, {"file": name, "sha256": response_sha, "request_id": request_id}

    def prepare(self):
        self.check()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        os.chmod(self.directory, 0o700)
        write_once(self.directory / "admission.json", {
            "manifest": self.manifest, "mission_id": self.client.mission_id,
            "instance": self.instance, "expires_at": self.grant["expires_at"]})
        repo = self.directory / "repository"
        repo.mkdir(mode=0o700)
        checked_git(["init"], repo)
        checked_git(["remote", "add", "origin",
                     "https://github.com/Crewless9086/amadeus-pig-tracking-system.git"], repo)
        checked_git(["fetch", "--no-tags", "--depth=1", "origin", self.manifest["base_sha"]], repo)
        checked_git(["checkout", "--detach", "FETCH_HEAD"], repo)
        need(checked_git(["rev-parse", "HEAD"], repo) == self.manifest["base_sha"], "base_mismatch")
        worktree = self.directory / "candidate"
        native = NativeAuthorization.from_mapping({
            "mission_id": self.client.mission_id, "generation": self.manifest["generation"],
            "native_execution_id": "HNX-" + self.manifest["generation"].upper(),
            "native_attempt": 1, "repository": "Crewless9086/amadeus-pig-tracking-system",
            "starting_main_sha": self.manifest["base_sha"],
            "branch": "charlie/" + self.client.mission_id.lower() + "-engineering",
            "worktree_digest": hashlib.sha256(str(worktree).encode()).hexdigest(),
            "owner_instruction_digest": digest(self.manifest),
            "allowed_files": self.manifest["allowed_files"],
            "allowed_commands": ["fixed isolated pytest"], "allowed_effects": ["private_patch"],
            "forbidden_effects": ["farm_write", "messages", "publish", "merge", "deploy"],
            "expires_at": self.grant["expires_at"], "status": "valid"})
        NativeWorktree(repo, worktree, native).ensure()
        self.worktree = worktree
        self.check()

    def tests(self, label, *, baseline=False):
        self.check()
        source = stage_tree(self.worktree, self.directory / (label + "-source"),
                            self.manifest["acceptance_source"])
        paths = [ACCEPTANCE_PATH] if baseline else [*self.manifest["test_paths"], ACCEPTANCE_PATH]
        # The root-private persistent artifact directory stays 0700. Only this
        # fresh ephemeral staging parent is traversable by the sandbox UID.
        with tempfile.TemporaryDirectory(prefix="core-engineering-tests-", dir="/tmp") as temporary:
            scratch = Path(temporary)
            scratch.chmod(0o711)
            result = self.tester(source, paths, scratch, timeout=120, expected_test_ids=self.expected_tests)
        self.check()
        write_once(self.directory / (label + "-tests.json"), result)
        return result

    def run(self):
        self.prepare()
        expected = ["tests/test_core_immutable_acceptance.py::" + node.name
                    for node in ast.parse(self.manifest["acceptance_source"]).body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]
        need(bool(expected), "immutable_tests_missing")
        self.expected_tests = expected
        baseline = self.tests("baseline", baseline=True)
        need(baseline.get("returncode") == 1 and
             "test_conflicting_duplicate_order" in baseline.get("stdout", "") and
             "AssertionError" in baseline.get("stdout", "") and
             (baseline.get("containment") or {}).get("verified") is True and
             (baseline.get("completion") or {}).get("verified") is True,
             "baseline_not_reproduced")
        self.progress("baseline_verified", baseline)
        profile = self.directory / "profile"
        profile.mkdir(mode=0o700)
        (profile / "config.yaml").write_text('{"auxiliary":{"transient_retries":0}}', encoding="utf-8")
        raw_model = self.model_factory(profile_home=profile, provider="openrouter",
                                       model="openai/gpt-5-mini", strict_budget=True,
                                       before_attempt=self.reserve, max_attempts=1)
        calls = []
        run = self
        class ObservedModel:
            response_evidence = None

            def complete_structured(self, **kwargs):
                # A prior response cannot justify retrying a later ambiguous call.
                self.response_evidence = None
                result = raw_model.complete_structured(**kwargs)
                audit, self.response_evidence = run.record_model_response(result, kwargs)
                calls.append(audit)
                return result
        model = ObservedModel()
        feedback, iterations = [], []
        candidate = tests = binding = diff = reviews = None
        for attempt in range(1, 4):
            self.check()
            context = ContextBroker(self.worktree, self.manifest["allowed_files"], max_bytes=290000).read(
                self.manifest["context_paths"])
            packet = {"protocol": CONTRACT, "mission_id": self.client.mission_id,
                      "generation": self.manifest["generation"], "instruction": self.manifest["instruction"],
                      "allowed_files": self.manifest["allowed_files"], "context": context,
                      "immutable_acceptance_source": self.manifest["acceptance_source"],
                      "baseline": baseline, "feedback": feedback,
                      "patch_base": "The current source in this packet. Return a diff against it.",
                      "forbidden_effects": ["publish", "messages", "farm_write", "deploy"],
                      "test_commands": self.manifest["test_paths"]}
            try:
                authored = HermesStructuredPatchWorker(model).complete(packet)
            except NativeSchemaError as exc:
                reason = (str(exc) if type(exc) is NativeSchemaError
                          and str(exc) in BUILDER_SCHEMA_ERRORS else "native_builder_response_invalid")
                evidence = model.response_evidence
                write_once(self.directory / ("builder-failure-" + str(attempt) + ".json"), {
                    "stage": "builder_semantic_validation" if evidence else "builder_completion",
                    "attempt": attempt,
                    "reason": reason, "response_evidence": evidence,
                }, max_bytes=4096)
                # Identity/audit checks must have passed and this precise call
                # must be durably recorded. Never retry an adapter-raised error.
                if evidence is None or reason not in RECOVERABLE_BUILDER_ERRORS:
                    raise NativeExecutionError(reason) from None
                self.check()
                feedback = [{"source": "builder_semantic_validator", "reason": reason,
                             "attempt": attempt,
                             "instruction": BUILDER_CORRECTIONS[reason]}]
                iterations.append({"attempt": attempt, "builder_response": evidence,
                                   "feedback": feedback})
                continue
            self.check()
            write_once(self.directory / ("builder-response-" + str(attempt) + ".json"), authored)
            need(authored["state"] == "PATCH_READY", "builder_not_ready")
            validator = PatchValidator(self.worktree, self.manifest["allowed_files"])
            try:
                validator.validate(authored["unified_diff"])
            except NativeExecutionError as exc:
                # Only a known pre-apply format/scope rejection can be revised.
                # Ambiguous model/network/canonical failures never retry.
                if str(exc) not in {"native_patch_check_failed", "native_patch_scope_violation",
                                    "native_patch_paths_invalid", "native_patch_invalid",
                                    "native_patch_operation_forbidden", "native_patch_delete_forbidden"}:
                    raise
                write_once(self.directory / ("builder-failure-" + str(attempt) + ".json"), {
                    "stage": "patch_validation", "attempt": attempt, "reason": str(exc),
                    "response_evidence": model.response_evidence,
                }, max_bytes=4096)
                self.check()
                feedback = [{"source": "patch_validator", "reason": str(exc), "attempt": attempt,
                             "instruction": BUILDER_CORRECTIONS[str(exc)]}]
                iterations.append({"attempt": attempt, "builder": authored, "feedback": feedback})
                continue
            applied = run_argv(["git", "apply", "--whitespace=error-all", "-"],
                               cwd=self.worktree, input_text=authored["unified_diff"])
            need(applied.returncode == 0, "native_patch_apply_failed")
            need(run_argv(["git", "diff", "--check"], cwd=self.worktree).returncode == 0,
                 "native_diff_check_failed")
            changed = sorted(checked_git(["diff", "--name-only"], self.worktree).splitlines())
            need(set(changed).issubset(self.manifest["allowed_files"]), "candidate_scope")
            if self.grant["state"] == "baseline_verified":
                self.progress("candidate_prepared", {"changed_files": changed,
                                                     "authored_diff_sha256": digest(authored["unified_diff"])})
            tests = self.tests("candidate-" + str(attempt))
            iteration = {"attempt": attempt, "builder": authored, "test_evidence_sha256": digest(tests)}
            iterations.append(iteration)
            if tests.get("returncode") != 0 or set(changed) != set(self.manifest["allowed_files"]):
                need((tests.get("containment") or {}).get("verified") is True and
                     (tests.get("completion") or {}).get("verified") is True, "test_execution_unproven")
                feedback = [{"source": "test_runner", "result": tests,
                             "required_changed_files": self.manifest["allowed_files"]}]
                continue
            need((tests.get("containment") or {}).get("verified") is True and
                 (tests.get("completion") or {}).get("verified") is True and
                 (tests.get("completion") or {}).get("expected_passed") is True,
                 "candidate_tests_unproven")
            if self.grant["state"] == "candidate_prepared":
                self.progress("tests_passed", tests)
            diff = checked_git(["diff", "--no-ext-diff", "--no-textconv", "--full-index"], self.worktree) + "\n"
            binding = {"pr_number": 0, "base_sha": self.manifest["base_sha"],
                       "head_sha": self.manifest["base_sha"],
                       "candidate_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
                       "changed_files": changed}
            candidate = {"diff": diff, "changed_files": changed, "builder_identity": authored["worker_identity"],
                         "builder_agent_id": authored["worker_agent_id"]}
            review_packet = {"candidate": binding, "candidate_diff": diff,
                             "candidate_source": ContextBroker(self.worktree, changed).read(changed),
                             "instruction": self.manifest["instruction"],
                             "governance_context": ContextBroker(self.worktree, changed, max_bytes=290000).read(
                                 [path for path in self.manifest["context_paths"] if path.startswith("docs/")]),
                             "immutable_acceptance_source": self.manifest["acceptance_source"],
                             "baseline": baseline, "verification": tests,
                             "publication": "private artifact, no commit or PR"}
            reviews = []
            for role in ("SECURITY", "FUNCTIONAL"):
                self.check()
                review = HermesIndependentReviewer(model).review(role, review_packet)
                self.check()
                write_once(self.directory / (role.lower() + "-review-" + str(attempt) + ".json"), review)
                reviews.append(review)
            iteration["reviews"] = reviews
            if all(review["verdict"] == "APPROVE" for review in reviews):
                break
            feedback = [{"source": review["role"], "findings": review["findings"]}
                        for review in reviews if review["verdict"] != "APPROVE"]
        else:
            raise NativeExecutionError("engineering_revision_limit")
        self.progress("reviews_passed", reviews)
        artifact = {"contract": CONTRACT, "generation": self.manifest["generation"],
                    "base_sha": self.manifest["base_sha"], "mission_id": self.client.mission_id,
                    "worker_revision": os.environ.get("RENDER_GIT_COMMIT"), "instance": self.instance,
                    "candidate": candidate, "candidate_diff": diff, "candidate_binding": binding,
                    "baseline": baseline, "tests": tests, "reviews": reviews,
                    "acceptance_sha256": self.manifest["acceptance_sha256"],
                    "iterations": iterations, "model_calls": calls,
                    "model_reservations": self.grant.get("reservations", []),
                    "reserved_micro_usd": self.grant.get("reserved_micro_usd", 0),
                    "publications": 0, "farm_actions": 0, "messages": 0, "deployments": 0}
        write_once(self.directory / "final-artifact.json", artifact)
        self.check()
        self.grant = self.client.call("complete", {"instance": self.instance,
            "artifact": artifact, "artifact_sha256": digest(artifact)})
        need(self.grant["state"] == "artifact_ready" and self.grant["artifact_sha256"] == digest(artifact),
             "canonical_artifact_not_verified")
        return self.grant


def run_worker(*, environ=None, client=None, stop=None, report=None, run_factory=EngineeringRun):
    values = os.environ if environ is None else environ
    need(values.get("CORE_NATIVE_RUNNER_MODE") == "engineering", "engineering_mode_required")
    need(values.get("RENDER_SERVICE_ID") == WORKER, "worker_service_mismatch")
    need(re.fullmatch("[a-f0-9]{40}", values.get("RENDER_GIT_COMMIT", "")), "worker_revision_invalid")
    stop = stop or threading.Event()
    report = report or (lambda item: print(json.dumps(item, sort_keys=True), flush=True))
    client = client or Client(values.get("CORE_ENGINEERING_MISSION_ID", ""),
                              values.get("CORE_ENGINEERING_TOKEN", ""))
    instance = uuid.uuid4().hex
    report({"status": "engineering_worker_started", "instance": instance,
            "revision": values["RENDER_GIT_COMMIT"], "service_id": WORKER})
    attempted = False
    try:
        while not stop.is_set():
            grant = client.call("current")
            if grant["state"] == "issued" and not attempted:
                attempted = True
                need(grant["manifest"]["worker_revision"] == values["RENDER_GIT_COMMIT"],
                     "worker_revision_mismatch")
                grant = client.call("claim", {"instance": instance,
                    "worker_revision": values["RENDER_GIT_COMMIT"], "worker_service": WORKER})
                result = run_factory(client, grant, instance, stop=stop, report=report).run()
                report({"status": "engineering_artifact_ready", "instance": instance,
                        "artifact_sha256": result["artifact_sha256"],
                        "reserved_micro_usd": result["reserved_micro_usd"]})
            else:
                report({"status": "engineering_worker_inactive", "instance": instance,
                        "canonical_state": grant["state"], "new_model_calls": 0})
            if stop.wait(30):
                break
    except Exception as exc:
        reason = str(exc) if isinstance(exc, NativeExecutionError) else "engineering_execution_failed"
        if not re.fullmatch("[a-z0-9_]{1,100}", reason):
            reason = "engineering_execution_failed"
        try:
            client.call("block", {"instance": instance, "reason": reason})
        except Exception:
            pass
        report({"status": "engineering_worker_contained", "instance": instance, "reason": reason,
                **model_failure_diagnostics(exc)})
        while not stop.wait(30):
            pass
    return 0


def main():
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    return run_worker(stop=stop)
