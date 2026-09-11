import importlib
import json
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import pytest
except ModuleNotFoundError:  # charlie-core intentionally runs without pytest installed
    class _UnittestOnlyMark:
        @staticmethod
        def parametrize(*_args, **_kwargs):
            return lambda function: function

    class _UnittestOnlyPytest:
        mark = _UnittestOnlyMark()

        @staticmethod
        def raises(exception, *, match=None):
            return unittest.TestCase().assertRaisesRegex(exception, match or ".*")

        @staticmethod
        def fail(message="pytest-style failure"):
            raise AssertionError(message)

    pytest = _UnittestOnlyPytest()

from modules.charlie.native_runner.execution import NativeExecutionError, NativePackager
from modules.charlie.native_runner.canonical_client import GitHubObserver
from modules.charlie.native_runner.model_adapter import HermesAuxiliaryModel, run_schema_canary
from modules.charlie.native_runner.service import (BROAD_GITHUB_NAMES, NativeRunnerService,
                                                   ProcessLock, read_environment_values,
                                                   read_profile_values)


REQUIRED = {
    "CHARLIE_CANONICAL_API_URL": "https://example.invalid",
    "CHARLIE_HERMES_GATEWAY_TOKEN": "gateway-test",
    "SLACK_BOT_TOKEN": "xoxb-test",
    "CHARLIE_SLACK_OWNER_USER_ID": "U0BSRQJASRG",
    "CHARLIE_SLACK_CHARLIE_CHANNEL_ID": "C0BSRQJ60KC",
    "CHARLIE_SLACK_BUILD_CHANNEL_ID": "C0BSTB5FQ5Q",
    "CHARLIE_SLACK_APPROVALS_CHANNEL_ID": "C0BTMNW0MT2",
    "CURSOR_API_KEY": "cursor-test",
    "CHARLIE_GITHUB_PACKAGER_TOKEN": "github-test",
}


def write_profile(tmp_path, values=None):
    home = tmp_path / "profile"
    home.mkdir()
    rows = values or REQUIRED
    (home / ".env").write_text("\n".join(f"{key}={value}" for key, value in rows.items()), encoding="utf-8")
    return home


def test_profile_reader_is_allowlisted_and_rejects_broad_github_credentials(tmp_path, monkeypatch):
    for key in BROAD_GITHUB_NAMES:
        monkeypatch.delenv(key, raising=False)
    values = read_profile_values(write_profile(tmp_path))
    assert set(REQUIRED).issubset(values)
    monkeypatch.setenv("GH_TOKEN", "must-not-be-used")
    with pytest.raises(NativeExecutionError, match="broad_github_credential_forbidden:GH_TOKEN"):
        read_profile_values(tmp_path / "profile")


def test_render_environment_reader_is_allowlisted_and_rejects_broad_credentials(monkeypatch):
    for key in set(REQUIRED) | set(BROAD_GITHUB_NAMES) | {"UNRELATED_SECRET"}:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-be-read")
    values = read_environment_values()
    assert set(REQUIRED).issubset(values)
    assert set(values) == set(REQUIRED) | {"CHARLIE_GITHUB_READ_TOKEN",
                                           "CHARLIE_NATIVE_MODEL_PROVIDER",
                                           "CHARLIE_NATIVE_MODEL"}
    assert "UNRELATED_SECRET" not in values
    monkeypatch.setenv("GITHUB_TOKEN", "forbidden")
    with pytest.raises(NativeExecutionError, match="broad_github_credential_forbidden:GITHUB_TOKEN"):
        read_environment_values()


def test_render_service_removes_parent_secrets_from_inherited_environment(tmp_path, monkeypatch):
    for key in BROAD_GITHUB_NAMES:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    service = NativeRunnerService(
        profile_home=tmp_path, repository_root=tmp_path / "repo",
        worktree_root=tmp_path / "worktrees", configuration_source="environment",
        model=SimpleNamespace(),
    )
    assert service.packager_token == REQUIRED["CHARLIE_GITHUB_PACKAGER_TOKEN"]
    for name in ("CHARLIE_HERMES_GATEWAY_TOKEN", "SLACK_BOT_TOKEN", "CURSOR_API_KEY",
                 "CHARLIE_GITHUB_PACKAGER_TOKEN"):
        assert name not in os.environ


def test_render_blueprint_is_one_paid_worker_with_one_persistent_disk():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "type: worker" in text
    assert "plan: 1c-2g" in text
    assert "numInstances: 1" in text
    assert "autoDeployTrigger: off" in text
    assert "mountPath: /var/data" in text and "sizeGB: 10" in text
    assert "type: web" not in text and "healthCheckPath:" not in text
    assert "maxShutdownDelaySeconds: 300" in text
    assert "notificationOverride:" not in text
    dockerfile = Path("deploy/charlie-native-runner/Dockerfile.render").read_text(encoding="utf-8")
    assert "python:3.12-slim@sha256:" in dockerfile
    assert "ARG HERMES_AGENT_REVISION" not in dockerfile
    assert dockerfile.count("5fc308a70719a83cccdbba4c0e39c23f5a8239d5") == 2
    assert "git -C /opt/hermes-agent rev-parse HEAD" in dockerfile
    assert "pip install --no-cache-dir --editable /opt/hermes-agent" in dockerfile
    assert 'git+https://github.com/NousResearch/hermes-agent.git@' not in dockerfile
    ignored = Path(".dockerignore").read_text(encoding="utf-8").splitlines()
    for protected in (".git", ".env*", "credentials/**", "secrets/**", "worktrees/"):
        assert protected in ignored


def test_render_bootstrap_uses_exact_revision_and_no_shell(tmp_path, monkeypatch):
    module = importlib.import_module("scripts.charlie_render_native_runner")
    disk = tmp_path / "disk"
    repository = disk / "repository"
    worktrees = disk / "worktrees"
    profile = disk / "hermes-profile"
    calls = []
    monkeypatch.setattr(module, "DISK", disk)
    monkeypatch.setattr(module, "REPOSITORY", repository)
    monkeypatch.setattr(module, "WORKTREES", worktrees)
    monkeypatch.setattr(module, "PROFILE", profile)
    class Result:
        def __init__(self, stdout=""): self.stdout = stdout
    def fake(argv, cwd=None):
        calls.append((list(argv), cwd))
        if argv[:2] == ["git", "clone"]:
            (repository / ".git").mkdir(parents=True)
        if argv[-3:] == ["remote", "get-url", "origin"]: return Result(module.ORIGIN + "\n")
        if argv[-2:] == ["rev-parse", "HEAD"]: return Result("a" * 40 + "\n")
        return Result("")
    monkeypatch.setattr(module, "run", fake)
    assert module.prepare_repository(deployed_sha="a" * 40) == "a" * 40
    assert any(row[0][:3] == ["git", "checkout", "--detach"] for row in calls)
    source = Path("scripts/charlie_render_native_runner.py").read_text(encoding="utf-8")
    assert "shell=False" in source and "shell=True" not in source


def test_watch_stops_cleanly_on_supervisor_termination(tmp_path):
    import threading
    service = object.__new__(NativeRunnerService)
    service.worktree_root = tmp_path
    service.status_path = tmp_path / "status.json"
    service.clock = lambda: datetime.now(timezone.utc)
    service.once = lambda: {"state": "IDLE"}
    stopping = threading.Event(); stopping.set()
    assert service.watch(5, stop_event=stopping) == 0
    assert json.loads(service.status_path.read_text())["state"] == "STOPPED"


def test_shutdown_during_active_cycle_prevents_next_mutating_stage(tmp_path):
    import threading
    entered = threading.Event(); release = threading.Event(); stopping = threading.Event()
    service = object.__new__(NativeRunnerService)
    service.worktree_root = tmp_path
    service.status_path = tmp_path / "status.json"
    service.clock = lambda: datetime.now(timezone.utc)
    service._stop_event = stopping
    stages = []
    def active_once():
        stages.append("model")
        entered.set(); release.wait(2)
        service._ensure_running()
        stages.append("package")
    service.once = active_once
    worker = threading.Thread(target=lambda: service.watch(5, stop_event=stopping))
    worker.start(); assert entered.wait(1)
    stopping.set(); release.set(); worker.join(2)
    assert not worker.is_alive()
    assert stages == ["model"]
    assert json.loads(service.status_path.read_text())["state"] == "STOPPED"


def test_production_lifecycle_heartbeat_fences_post_model_and_packager_stages(tmp_path):
    import threading
    service = object.__new__(NativeRunnerService)
    service._stop_event = threading.Event()
    renewed = []
    service._claim_heartbeat = lambda *args: renewed.append(args)
    service._stop_event.set()
    with pytest.raises(NativeExecutionError, match="native_runner_shutdown_requested"):
        service._lifecycle_heartbeat("mission", "HNX-1", "claim", "builder")
    assert renewed == []
    source = Path("modules/charlie/native_runner/service.py").read_text(encoding="utf-8")
    assert source.count("heartbeat = lambda: self._lifecycle_heartbeat(") == 2


def test_real_packager_stops_after_local_commit_before_push_or_pr(tmp_path):
    worktree = tmp_path / "worktree"; worktree.mkdir()
    service = object.__new__(NativeRunnerService)
    service._stop_event = __import__("threading").Event()
    service._claim_heartbeat = lambda *_: None
    remote = []
    authorization = {
        "mission_id": "CHARLIE-MISSION-13B47938FF65E2C1", "generation": "g1",
        "native_execution_id": "HNX-1", "native_attempt": 1,
        "repository": "Crewless9086/amadeus-pig-tracking-system",
        "starting_main_sha": "a" * 40, "branch": "charlie/mission-native-1",
        "worktree_digest": "b" * 64, "owner_instruction_digest": "c" * 64,
        "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
        "allowed_commands": ["git diff --check"], "allowed_effects": ["draft PR"],
        "forbidden_effects": ["merge", "deploy"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "status": "valid",
    }
    packager = NativePackager(worktree, authorization, "contained",
        heartbeat=lambda: service._lifecycle_heartbeat("mission", "HNX-1", "claim", "packager"))
    def git(*args):
        mapping = {
            ("branch", "--show-current"): "charlie/mission-native-1",
            ("remote", "get-url", "origin"): "https://github.com/Crewless9086/amadeus-pig-tracking-system.git",
            ("diff", "--name-only"): "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
            ("diff", "--cached", "--name-only"): "",
            ("rev-parse", "a" * 40 + "^{commit}"): "a" * 40,
            ("rev-parse", "HEAD"): "b" * 40,
        }
        return mapping[tuple(args)]
    packager._git = git
    packager._push_with_ephemeral_askpass = lambda: remote.append("push")
    packager._find_pull = lambda _branch: remote.append("pr")
    def argv(args, **_kwargs):
        if "commit" in args:
            service._stop_event.set()
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch("modules.charlie.native_runner.execution.run_argv", side_effect=argv):
        with pytest.raises(NativeExecutionError, match="native_runner_shutdown_requested"):
            packager.package("title", "body")
    assert remote == []


def test_model_adapter_uses_installed_low_level_boundary_without_tools_or_api_key(tmp_path):
    calls = []

    class Message:
        content = '{"status":"READY"}'
    class Choice:
        message = Message()
    class Reply:
        choices = [Choice()]
        model = "test-model"

    def call(**kwargs):
        calls.append(kwargs)
        kwargs["route_info"].update(provider="openrouter", model="test-model")
        return Reply()

    model = HermesAuxiliaryModel(profile_home=tmp_path, call=call, model="test-model")
    assert run_schema_canary(model)["status"] == "READY"
    assert calls[0]["tools"] == []
    assert calls[0]["provider"] == "openrouter"
    assert calls[0]["model"] == "test-model"
    assert "api_key" not in calls[0]
    assert not any("token" in json.dumps(value).lower() for value in calls[0].values())


def test_model_adapter_enters_explicit_hermes_profile_home(tmp_path, monkeypatch):
    import sys
    from contextlib import contextmanager
    entered = []
    hermes = type(sys)("hermes_cli")
    hermes.__path__ = []
    plugins = type(sys)("hermes_cli.plugins")
    @contextmanager
    def scope(home):
        entered.append(Path(home).resolve())
        yield
    plugins._plugin_home_scope = scope
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    class Reply:
        choices = [SimpleNamespace(message=SimpleNamespace(content='{"status":"READY"}'))]
        model = "test-model"
    def call(**kwargs):
        kwargs["route_info"].update(provider="openrouter", model="test-model")
        return Reply()
    model = HermesAuxiliaryModel(profile_home=tmp_path, call=call, model="test-model")
    run_schema_canary(model)
    assert entered == [tmp_path.resolve()]


def test_model_adapter_uses_pinned_openai_response_and_route_info(tmp_path):
    calls = []
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"status":"READY"}'))],
        model="provider-fallback-model")
    def call(**kwargs):
        calls.append(kwargs)
        kwargs["route_info"].update(provider="openrouter", model="openai/gpt-5-mini")
        return reply
    result = run_schema_canary(HermesAuxiliaryModel(profile_home=tmp_path, call=call))
    assert result == {"status": "READY", "provider": "openrouter",
                      "model": "openai/gpt-5-mini", "tools_count": 0}
    assert calls[0]["tools"] == [] and calls[0]["provider"] == "openrouter"
    fake = SimpleNamespace(content='{"status":"READY"}', provider="openrouter", model="fake")
    with pytest.raises(NativeExecutionError, match="native_model_response_invalid"):
        run_schema_canary(HermesAuxiliaryModel(profile_home=tmp_path, call=lambda **_: fake))


def test_cursor_key_is_optional_after_canonical_retirement(tmp_path, monkeypatch):
    values = dict(REQUIRED)
    values.pop("CURSOR_API_KEY")
    for key in set(REQUIRED) | set(BROAD_GITHUB_NAMES):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    resolved = read_environment_values()
    assert resolved["CURSOR_API_KEY"] == ""
    service = NativeRunnerService(
        profile_home=tmp_path, repository_root=tmp_path / "repo",
        worktree_root=tmp_path / "worktrees", configuration_source="environment",
        model=SimpleNamespace())
    assert service.cursor is None


def test_render_profile_disables_hermes_internal_transient_retries(tmp_path, monkeypatch):
    module = importlib.import_module("scripts.charlie_render_native_runner")
    monkeypatch.setattr(module, "PROFILE", tmp_path / "profile")
    module.prepare_hermes_profile()
    text = (tmp_path / "profile" / "config.yaml").read_text(encoding="utf-8")
    assert json.loads(text)["auxiliary"]["transient_retries"] == 0


def test_repeated_blocker_notifies_once_per_destination_and_holds(tmp_path):
    import threading
    notices, canonical_blocks, calls = [], [], []
    class Canonical:
        def mission(self, _mission_id):
            return {"mission": {"generation": "g1", "metadata": {
                "external_supervisor_state": {"slack_channel_id": "C1", "slack_thread_ts": "T1"},
                "slack_approval_channel_id": "C2", "dispatch_authorization": {"authorization_id": "PDA-1"}}}}
        def blocker(self, mission_id, payload):
            canonical_blocks.append((mission_id, payload)); return {"success": True}
    class Notifier:
        def post(self, channel, text, **kwargs): notices.append((channel, kwargs.get("idempotency_key")))
    service = object.__new__(NativeRunnerService)
    service.canonical, service.notifier = Canonical(), Notifier()
    service.slack_approval_channel = "C2"
    service.status_path, service.clock = tmp_path / "status.json", lambda: datetime.now(timezone.utc)
    service._active_mission_id, service._active_stage = "MISSION-1", "model"
    def once():
        calls.append("model"); raise NativeExecutionError("native_model_response_invalid")
    service.once = once
    class StopAfterHold:
        def __init__(self): self.stopped = False
        def is_set(self): return self.stopped
        def wait(self, _seconds):
            if len(calls) >= 2: self.stopped = True
            return self.stopped
    service.watch(5, stop_event=StopAfterHold())
    assert calls == ["model", "model"]
    assert [item[0] for item in notices] == ["C1", "C2"]
    assert len(canonical_blocks) == 1


def test_blocker_reporting_retries_only_incomplete_destinations(tmp_path):
    attempts = {"canonical": 0, "C1": 0, "C2": 0}
    class Canonical:
        def mission(self, _mission_id):
            return {"mission": {"generation": "g1", "metadata": {
                "external_supervisor_state": {"slack_channel_id": "C1", "slack_thread_ts": "T1"},
                "slack_approval_channel_id": "C2",
                "dispatch_authorization": {"authorization_id": "PDA-1"}}}}
        def blocker(self, _mission_id, _payload):
            attempts["canonical"] += 1
            if attempts["canonical"] == 1:
                raise OSError("transient")
            return {"success": True}
    class Notifier:
        def post(self, channel, _text, **_kwargs):
            attempts[channel] += 1
            if channel == "C2" and attempts[channel] == 1:
                raise OSError("transient")
            return {"ok": True}
    service = object.__new__(NativeRunnerService)
    service.canonical, service.notifier = Canonical(), Notifier()
    service.slack_approval_channel = "C2"
    service.status_path, service.clock = tmp_path / "status.json", lambda: datetime.now(timezone.utc)
    service._active_stage, service._active_worktree = "packaging", None
    service._repository_mutation, service._remote_mutation = True, True
    service._report_blocker("MISSION-1", "native_packaging_push_failed", 2)
    service._report_blocker("MISSION-1", "native_packaging_push_failed", 2)
    saved = json.loads(service.status_path.read_text())
    assert attempts == {"canonical": 2, "C1": 1, "C2": 2}
    assert saved["reporting"] == "complete"
    assert saved["repository_mutation"] is True and saved["remote_mutation"] is True


@pytest.mark.parametrize("patch_already_applied", [False, True])
def test_recorded_patch_restart_skips_second_model_call(tmp_path, patch_already_applied):
    repo = tmp_path / "repo"; worktree = tmp_path / "worktree"
    repo.mkdir(); worktree.mkdir()
    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runner@example.invalid"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Runner"], cwd=worktree, check=True)
    target = worktree / "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"
    target.parent.mkdir(parents=True); target.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=worktree, check=True, capture_output=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree, check=True,
                          capture_output=True, text=True).stdout.strip()
    target.write_text("after\n", encoding="utf-8")
    recorded_patch = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", "--"], cwd=worktree,
        check=True, capture_output=True, text=True).stdout
    patch_sha = __import__("hashlib").sha256(recorded_patch.encode()).hexdigest()
    auth = {"mission_id": "MISSION-1", "generation": "g1", "native_execution_id": "HNX-1",
            "native_attempt": 1, "repository": "Crewless9086/amadeus-pig-tracking-system",
            "starting_main_sha": base, "branch": "charlie/mission-native-1",
            "worktree_digest": __import__("hashlib").sha256(str(worktree.resolve()).encode()).hexdigest(),
            "owner_instruction_digest": "b" * 64,
            "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            "allowed_commands": ["git diff --check"], "allowed_effects": ["draft PR"],
            "forbidden_effects": ["merge", "deploy"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "status": "valid",
            "patch_sha256": patch_sha, "builder_identity": "HNW-PROVEN",
            "builder_agent_id": "standalone"}
    intent = {"schema": "charlie_native_patch_intent_v1", "patch": recorded_patch,
              "patch_sha256": patch_sha, "changed_files": auth["allowed_files"],
              "builder_identity": "HNW-PROVEN", "builder_agent_id": "standalone"}
    (worktree.parent / ".native-1-patch-intent.json").write_text(
        json.dumps(intent), encoding="utf-8")
    if not patch_already_applied:
        subprocess.run(["git", "checkout", "--", target.relative_to(worktree).as_posix()],
                       cwd=worktree, check=True, capture_output=True)
    service = object.__new__(NativeRunnerService)
    service.clock, service._stop_event = lambda: datetime.now(timezone.utc), threading.Event()
    service.model = SimpleNamespace(complete_structured=lambda **_: pytest.fail("second model call"))
    service.packager_token = "contained"
    service._record_progress = lambda *_args, **_kwargs: {"success": True}
    service._complete_initial_candidate = lambda *_args, **_kwargs: {"state": "PACKAGED"}
    packaged = {"pr_number": 1331, "commit_sha": "c" * 40,
                "candidate_diff_sha256": "d" * 64,
                "changed_files": auth["allowed_files"], "branch": auth["branch"]}
    with patch("modules.charlie.native_runner.service.NativePackager.package", return_value=packaged):
        result = service._build({"mission_id": "MISSION-1", "title": "doc"}, auth, repo, worktree)
    assert result["state"] == "PACKAGED"


@pytest.mark.parametrize("patch_already_applied", [False, True])
def test_correction_intent_restart_skips_second_model_call(tmp_path, patch_already_applied):
    mission = {"mission_id": "MISSION-1", "generation": "g1", "title": "doc"}
    worktree = tmp_path / "worktrees" / "MISSION-1" / "g1" / "native-1"
    worktree.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runner@example.invalid"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Runner"], cwd=worktree, check=True)
    target = worktree / "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"
    target.parent.mkdir(parents=True); target.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "candidate"], cwd=worktree, check=True, capture_output=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree, check=True,
                          capture_output=True, text=True).stdout.strip()
    target.write_text("after\n", encoding="utf-8")
    correction = subprocess.run(["git", "diff", "--binary", "--no-ext-diff", "--"], cwd=worktree,
                                check=True, capture_output=True, text=True).stdout
    digest = __import__("hashlib").sha256(correction.encode()).hexdigest()
    intent = {"schema": "charlie_native_patch_intent_v1", "patch": correction,
              "patch_sha256": digest,
              "changed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
              "builder_identity": "HNW-CORRECTION", "builder_agent_id": "standalone"}
    (worktree.parent / ".native-1-correction-patch-intent.json").write_text(
        json.dumps(intent), encoding="utf-8")
    if not patch_already_applied:
        subprocess.run(["git", "checkout", "--", target.relative_to(worktree).as_posix()],
                       cwd=worktree, check=True, capture_output=True)
    native = {"mission_id": "MISSION-1", "generation": "g1", "native_execution_id": "HNX-1",
              "native_attempt": 1, "repository": "Crewless9086/amadeus-pig-tracking-system",
              "starting_main_sha": base, "branch": "charlie/mission-native-1",
              "worktree_digest": __import__("hashlib").sha256(str(worktree.resolve()).encode()).hexdigest(),
              "owner_instruction_digest": "b" * 64,
              "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
              "allowed_commands": ["git diff --check"], "allowed_effects": ["draft PR"],
              "forbidden_effects": ["merge", "deploy"],
              "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "status": "valid",
              "pr_number": 1330, "head_sha": base, "correction_rounds": 0,
              "review_challenge": {"findings": ["clarify"]}, "worker_claim_id": "HNC-1",
              "execution_status": "CORRECTION_PATCH_INTENT_RECORDED",
              "correction_patch_sha256": digest,
              "correction_builder_identity": "HNW-CORRECTION",
              "correction_builder_agent_id": "standalone"}
    class Engine:
        def __init__(self, *_args, **_kwargs): pass
        def build_patch(self, *_args, **_kwargs): pytest.fail("second correction model call")
        def verify(self): return [{"command": "git diff --check", "returncode": 0}]
    service = object.__new__(NativeRunnerService)
    service.repository_root, service.worktree_root = tmp_path, tmp_path / "worktrees"
    service.model = SimpleNamespace(complete_structured=lambda **_: pytest.fail("second correction model call"))
    service.packager_token = "contained"
    service.clock, service._stop_event = lambda: datetime.now(timezone.utc), threading.Event()
    service.canonical = SimpleNamespace(native_context=lambda _mission: {})
    service._record_progress = lambda *_args, **_kwargs: {"success": True}
    service._complete_corrected_candidate = lambda *_args, **_kwargs: {"state": "RECOVERED"}
    packaged = {"pr_number": 1330, "commit_sha": "c" * 40,
                "candidate_diff_sha256": "d" * 64, "changed_files": native["allowed_files"],
                "branch": native["branch"]}
    with patch("modules.charlie.native_runner.service.NativeExecutionEngine", Engine), \
         patch("modules.charlie.native_runner.service.NativePackager.package", return_value=packaged):
        assert service._correct(mission, native)["state"] == "RECOVERED"


def test_supervise_routes_recorded_correction_intent_to_recovery(tmp_path):
    service = object.__new__(NativeRunnerService)
    service._active_stage = ""
    service._correct = lambda mission, native: {"state": "CORRECTION_RECOVERY", "id": native["native_execution_id"]}
    result = service._supervise({"mission_id": "MISSION-1"}, {
        "native_execution_id": "HNX-1", "execution_status": "CORRECTION_PATCH_INTENT_RECORDED"})
    assert result == {"state": "CORRECTION_RECOVERY", "id": "HNX-1"}


def test_native_runner_imports_with_plugin_package_absent(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "integrations.hermes.charlie_builder", None)
    module = importlib.reload(importlib.import_module("modules.charlie.native_runner.service"))
    assert module.NativeRunnerService


def test_cli_and_service_have_no_merge_deploy_release_or_cursor_create_path():
    script = Path("scripts/charlie_native_runner.py").read_text(encoding="utf-8")
    service = Path("modules/charlie/native_runner/service.py").read_text(encoding="utf-8")
    assert "auto-merge" not in script and "release-verify" not in script
    assert "create_agent" not in service and "attempt 6" not in service.lower()
    assert not any(name in NativeRunnerService.__dict__ for name in ("merge", "deploy", "release"))


def test_process_lock_prevents_two_local_writers(tmp_path):
    first = ProcessLock(tmp_path / "runner.lock")
    second = ProcessLock(tmp_path / "runner.lock")
    first.acquire()
    try:
        with pytest.raises(NativeExecutionError, match="native_runner_already_active"):
            second.acquire()
    finally:
        first.release()


class CanonicalFake:
    def __init__(self):
        self.retirements = 0
        self.renewals = 0
        self.prepared = 0
        self.progress_rows = []
        self.native = None

    def resumable(self):
        return [{"mission_id": "CHARLIE-MISSION-13B47938FF65E2C1"}]

    def mission(self, mission_id):
        metadata = {"external_supervisor_state": {
            "execution_attempt": 5, "generation": "slack-1787929390.145099-g1",
            "cursor_agent_id": "bc-five", "cursor_run_id": "run-five", "branch": "cursor/old-five",
            "slack_channel_id": "C-CHARLIE", "slack_thread_ts": "1787929390.145099",
        }}
        if self.retirements:
            metadata["cursor_provider_retirement"] = {"provider_status": "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT"}
        if self.native:
            metadata["hermes_native_execution"] = self.native
        return {"mission": {"mission_id": mission_id, "title": "docs", "raw_text": "clarify docs", "metadata": metadata}}

    def writers(self): return 1 if self.native and self.native.get("worker_claim_id") else 0
    def retire_cursor(self, mission_id, evidence):
        self.retirements += 1
        return {"provider_status": "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT", **evidence}
    def renew_authority(self, mission_id):
        self.renewals += 1
        return {"version": "charlie_pre_dispatch_authorization_v2", "status": "valid",
                "generation": "slack-1787929390.145099-g1"}
    def prepare_native(self, mission_id, digest, sha):
        self.prepared += 1
        identity = __import__("modules.charlie.native_runner.execution", fromlist=["content_identity"]).content_identity(
            mission_id, "slack-1787929390.145099-g1", 1)
        self.native = {"mission_id": mission_id, "generation": "slack-1787929390.145099-g1",
            "native_execution_id": identity[0], "native_attempt": 1,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "starting_main_sha": sha,
            "branch": identity[1], "worktree_digest": digest, "owner_instruction_digest": "a" * 64,
            "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            "allowed_commands": ["git status", "git diff", "git diff --check"],
            "allowed_effects": ["draft PR"], "forbidden_effects": ["merge", "deploy"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "status": "valid"}
        return self.native
    def progress(self, mission_id, payload): self.progress_rows.append(payload); return payload
    def native_context(self, mission_id): return {"governance": "bounded"}


class CursorFake:
    def __init__(self): self.archives = 0
    def get_agent(self, _): return {"id": "bc-five", "status": "ARCHIVED" if self.archives else "IDLE"}
    def get_run(self, *_): return {"id": "run-five", "status": "FINISHED"}
    def archive(self, _): self.archives += 1
    def cancel(self, *_): raise AssertionError("terminal run must not be cancelled")


class GithubFake:
    def branch_exists(self, _): return False
    def find_pull(self, _): return 0


def test_full_service_orchestration_draft_send_back_correction_mar_checks_notification(tmp_path):
    events, admissions, bindings, posts = [], [], [], []
    class Canonical:
        claim = ""
        def progress(self, mission_id, payload):
            if payload.get("event") == "native_writer_claimed":
                self.claim = payload.get("worker_claim_id")
            elif payload.get("event") == "native_writer_released":
                if payload.get("release_claim_id") != self.claim:
                    return {"success": False, "status": "native_writer_claim_conflict"}
                self.claim = ""
            elif self.claim and payload.get("worker_claim_id") != self.claim:
                return {"success": False, "status": "native_writer_claim_required"}
            events.append(payload)
            return payload
        def native_context(self, mission_id): return {"bounded": True}
        def bind_candidate(self, mission_id, payload): bindings.append(payload); return {"success": True}
        def request_admission(self, mission_id, head, pr): admissions.append((head, pr)); return {"success": True}
    class Engine:
        def __init__(self, *args, **kwargs): pass
        def build_patch(self, *args, **kwargs):
            return {"state": "PATCH_READY", "changed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
                    "worker_identity": "HNW-1", "worker_agent_id": "standalone"}
        def verify(self): return [{"command": "git diff --check", "returncode": 0}]
    heads = iter(("a" * 40, "b" * 40))
    class Packager:
        def __init__(self, *args, **kwargs): pass
        def package(self, *args):
            head = next(heads)
            return {"pr_number": 1400, "commit_sha": head, "branch": "charlie/mission-native-1",
                    "changed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
                    "candidate_diff_sha256": ("c" if head.startswith("a") else "d") * 64}
    class Reviewer:
        def __init__(self, *args): pass
        def review(self, role, packet):
            return {"role": role, "reviewer_task": f"charlie_native_{role.lower()}_reviewer",
                    "candidate_binding": packet["candidate"],
                    "verdict": "SEND_BACK" if role == "CHALLENGE" else "APPROVE",
                    "findings": ["Clarify the no-deploy boundary."] if role == "CHALLENGE" else []}
    class Github:
        def pull_state(self, number):
            return {"pr_number": number, "head_sha": bindings[-1]["head_sha"], "draft": True,
                    "checks": {name: "success" for name in __import__("modules.charlie.native_runner.canonical_client", fromlist=["GitHubObserver"]).GitHubObserver.REQUIRED},
                    "all_required_checks_pass": True}
    class Notifier:
        def post(self, channel, text, **kwargs): posts.append((channel, kwargs.get("idempotency_key"))); return {"ok": True}
    service = object.__new__(NativeRunnerService)
    service.canonical, service.model, service.packager_token = Canonical(), SimpleNamespace(complete_structured=lambda **_: None), "contained"
    service.repository_root, service.worktree_root = tmp_path, tmp_path / "worktrees"
    service.github, service.notifier, service.slack_approval_channel = Github(), Notifier(), "C-APPROVALS"
    service.clock = lambda: datetime.now(timezone.utc)
    service.status_path = tmp_path / "status.json"
    mission = {"mission_id": "CHARLIE-MISSION-13B47938FF65E2C1", "title": "docs", "raw_text": "clarify",
               "metadata": {"external_supervisor_state": {"slack_channel_id": "C-CHARLIE", "slack_thread_ts": "1787929390.145099"}}}
    authorization = {"mission_id": mission["mission_id"], "generation": "g1", "native_execution_id": "HNX-1",
        "native_attempt": 1, "repository": "Crewless9086/amadeus-pig-tracking-system", "starting_main_sha": "e" * 40,
        "branch": "charlie/mission-native-1", "worktree_digest": "f" * 64, "owner_instruction_digest": "1" * 64,
        "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"], "allowed_commands": ["git diff --check"],
        "allowed_effects": ["draft PR"], "forbidden_effects": ["merge", "deploy"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "status": "valid"}
    with patch("modules.charlie.native_runner.service.NativeExecutionEngine", Engine), \
             patch("modules.charlie.native_runner.service.NativePackager", Packager), \
             patch("modules.charlie.native_runner.service.HermesIndependentReviewer", Reviewer), \
             patch("modules.charlie.native_runner.service.run_argv",
                   return_value=SimpleNamespace(returncode=0, stdout="", stderr="")):
        first = service._build(mission, authorization, tmp_path, tmp_path / "worktree")
        assert first["state"] == "SEND_BACK" and admissions == [("a" * 40, 1400)]
        native = {**authorization, "execution_status": "SEND_BACK", "pr_number": 1400, "head_sha": "a" * 40,
                  "candidate_diff_sha256": "c" * 64, "changed_files": authorization["allowed_files"],
                  "review_challenge": events[-1]["review_challenge"], "correction_rounds": 0,
                  "worker_claim_id": service.canonical.claim}
        second = service._correct(mission, native)
        assert second["state"] == "CHECKS_PENDING" and admissions[-1] == ("b" * 40, 1400)
        corrected = {**native, "execution_status": "SEND_BACK_CORRECTED", "correction_rounds": 1,
                     "head_sha": "b" * 40, "review_security": events[-1]["review_security"],
                     "review_functional": events[-1]["review_functional"]}
        final = service._supervise(mission, corrected)
        assert final["state"] == "OWNER_DECISION_REQUIRED"
        assert len(posts) == 2 and len({item[1] for item in posts}) == 2
        corrected["owner_notification_head"] = "b" * 40
        corrected["worker_claim_id"] = ""
        service._supervise(mission, corrected)
        assert len(posts) == 2
    assert len(bindings) == 2
    assert not any(event.get("execution_status") in {"MERGED", "DEPLOYED"} for event in events)


def test_restart_after_local_commit_resumes_packaging_without_second_model_patch(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    events, packages = [], []
    class Canonical:
        def progress(self, mission_id, payload): events.append(payload); return payload
        def native_context(self, mission_id): raise AssertionError("model context must not be requested")
        def bind_candidate(self, mission_id, payload): return {"success": True}
        def request_admission(self, *args): return {"success": True}
    class Engine:
        def __init__(self, *args, **kwargs): pass
        def build_patch(self, *args, **kwargs): raise AssertionError("must not generate a second patch")
        def verify(self): return [{"command": "git diff --check", "returncode": 0}]
    class Packager:
        def __init__(self, *args, **kwargs): pass
        def package(self, *args):
            packages.append(1)
            return {"pr_number": 1401, "commit_sha": "b" * 40, "branch": "charlie/mission-native-1",
                    "changed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
                    "candidate_diff_sha256": "d" * 64}
    class Reviewer:
        def __init__(self, *_): pass
        def review(self, role, packet):
            return {"role": role, "reviewer_task": "charlie_native_challenge_reviewer",
                    "candidate_binding": packet["candidate"], "verdict": "SEND_BACK", "findings": ["one correction"]}
    class Github:
        def pull_state(self, number):
            return {"pr_number": number, "head_sha": "b" * 40,
                    "checks": {"mission-admission": "success"},
                    "all_required_checks_pass": False}
    service = object.__new__(NativeRunnerService)
    service.canonical, service.model, service.packager_token = Canonical(), SimpleNamespace(complete_structured=lambda **_: None), "contained"
    service.status_path, service.clock = tmp_path / "status.json", lambda: datetime.now(timezone.utc)
    service.github = Github()
    mission = {"mission_id": "CHARLIE-MISSION-13B47938FF65E2C1", "title": "docs"}
    authorization = {"native_execution_id": "HNX-1", "starting_main_sha": "a" * 40,
        "branch": "charlie/mission-native-1",
        "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
        "builder_identity": "HNW-original", "builder_agent_id": "standalone"}
    results = iter((SimpleNamespace(returncode=0, stdout="b" * 40 + "\n"),
                    SimpleNamespace(returncode=0, stdout="")))
    with patch("modules.charlie.native_runner.service.NativeExecutionEngine", Engine), \
         patch("modules.charlie.native_runner.service.NativePackager", Packager), \
         patch("modules.charlie.native_runner.service.HermesIndependentReviewer", Reviewer), \
         patch("modules.charlie.native_runner.service.run_argv", side_effect=lambda *a, **k: next(results)):
        result = service._build(mission, authorization, tmp_path, worktree)
    assert result["state"] == "SEND_BACK" and packages == [1]


def test_fresh_services_resume_bound_initial_and_corrected_candidates(tmp_path):
    admissions, events = [], []
    class Canonical:
        def progress(self, mission_id, payload): events.append(payload); return payload
        def request_admission(self, mission_id, head, pr): admissions.append((head, pr)); return {"success": True}
        def bind_candidate(self, *_): raise AssertionError("already-bound candidate must not rebind")
    class Reviewer:
        def __init__(self, *_): pass
        def review(self, role, packet):
            return {"role": role, "reviewer_task": f"charlie_native_{role.lower()}_reviewer",
                    "candidate_binding": packet["candidate"],
                    "verdict": "SEND_BACK" if role == "CHALLENGE" else "APPROVE",
                    "findings": ["one"] if role == "CHALLENGE" else []}
    mission = {"mission_id": "CHARLIE-MISSION-13B47938FF65E2C1"}
    base = {"native_execution_id": "HNX-1", "pr_number": 1402, "base_sha": "a" * 40,
            "head_sha": "b" * 40, "branch": "charlie/mission-native-1",
            "changed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            "candidate_diff_sha256": "c" * 64}
    def fresh():
        service = object.__new__(NativeRunnerService)
        service.canonical = Canonical()
        service.model = SimpleNamespace(complete_structured=lambda **_: None)
        service.status_path = tmp_path / f"status-{len(events)}.json"
        service.clock = lambda: datetime.now(timezone.utc)
        service.github = SimpleNamespace(pull_state=lambda number: {
            "pr_number": number, "head_sha": "b" * 40,
            "checks": {"mission-admission": "success"},
            "all_required_checks_pass": False})
        return service
    with patch("modules.charlie.native_runner.service.HermesIndependentReviewer", Reviewer):
        first = fresh()._supervise(mission, {**base, "execution_status": "CANDIDATE_BOUND"})
        assert first["state"] == "SEND_BACK"
        corrected = fresh()._supervise(mission, {**base, "execution_status": "CORRECTION_BOUND"})
        assert corrected["state"] == "CHECKS_PENDING"
    assert admissions == [("b" * 40, 1402), ("b" * 40, 1402)]
    statuses = [event["execution_status"] for event in events]
    assert statuses.index("ADMISSION_PENDING") < statuses.index("SEND_BACK")
    assert statuses.index("CORRECTION_ADMISSION_PENDING") < statuses.index("SEND_BACK_CORRECTED")


def test_initial_review_waits_for_exact_head_trusted_admission_across_restart(tmp_path):
    events, reviews = [], []
    class Canonical:
        def progress(self, mission_id, payload): events.append(payload); return payload
        def request_admission(self, *args): return {"success": True}
        def bind_candidate(self, *_): raise AssertionError("already bound")
    service = object.__new__(NativeRunnerService)
    service.canonical = Canonical()
    service.github = SimpleNamespace(pull_state=lambda number: {
        "pr_number": number, "head_sha": "b" * 40,
        "checks": {"mission-admission": "pending"},
        "all_required_checks_pass": False})
    service.model = object()
    service.status_path = tmp_path / "status.json"
    service.clock = lambda: datetime.now(timezone.utc)
    native = {"native_execution_id": "HNX-1", "execution_status": "CANDIDATE_BOUND",
              "pr_number": 1402, "base_sha": "a" * 40, "head_sha": "b" * 40,
              "branch": "charlie/mission-native-1", "changed_files": [
                  "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
              "candidate_diff_sha256": "c" * 64, "worker_claim_id": "HNC-X"}
    class Reviewer:
        def __init__(self, *_): reviews.append("constructed")
    with patch("modules.charlie.native_runner.service.HermesIndependentReviewer", Reviewer):
        result = service._supervise({"mission_id": "CHARLIE-MISSION-X"}, native)
    assert result["state"] == "ADMISSION_PENDING"
    assert reviews == []
    assert events[0]["execution_status"] == "ADMISSION_PENDING"


def test_fresh_service_releases_claim_after_owner_notification_crash_without_reposting(tmp_path):
    progress, posts = [], []
    class Canonical:
        def progress(self, mission_id, payload): progress.append(payload); return payload
    class Github:
        def pull_state(self, number):
            return {"pr_number": number, "head_sha": "b" * 40, "checks": {"all": "success"},
                    "all_required_checks_pass": True}
    class Notifier:
        def post(self, *args, **kwargs): posts.append(1)
    service = object.__new__(NativeRunnerService)
    service.canonical, service.github, service.notifier = Canonical(), Github(), Notifier()
    service.slack_approval_channel = "C-APPROVALS"
    service.status_path, service.clock = tmp_path / "status.json", lambda: datetime.now(timezone.utc)
    mission = {"mission_id": "CHARLIE-MISSION-X", "metadata": {}}
    native = {"native_execution_id": "HNX-X", "pr_number": 7, "head_sha": "b" * 40,
              "owner_notification_head": "b" * 40, "worker_claim_id": "HNC-X",
              "correction_rounds": 1, "review_security": {"verdict": "APPROVE"},
              "review_functional": {"verdict": "APPROVE"}}
    result = service._supervise(mission, native)
    assert result["state"] == "OWNER_DECISION_REQUIRED" and posts == []
    assert progress == [{"native_execution_id": "HNX-X", "execution_status": "OWNER_DECISION_REQUIRED",
                         "release_claim_id": "HNC-X", "event": "native_writer_released"}]


def test_attempt_five_retires_before_fresh_authority_and_one_native_identity(tmp_path, monkeypatch):
    canonical, cursor = CanonicalFake(), CursorFake()
    service = NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path,
        worktree_root=tmp_path / "worktrees", canonical=canonical, cursor=cursor,
        github=GithubFake(), model=object())
    monkeypatch.setattr("modules.charlie.native_runner.service.validate_primary_repository",
                        lambda *_: (tmp_path, tmp_path / "worktrees", "b" * 40))
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary",
                        lambda _: {"status": "READY"})
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary", lambda _: {"status": "READY"})
    monkeypatch.setattr(service, "_build", lambda mission, native, repository, worktree: {
        "native_execution_id": native["native_execution_id"], "worktree": str(worktree)})
    result = service.once()
    assert canonical.retirements == canonical.renewals == canonical.prepared == 1
    assert cursor.archives == 1
    assert result["native_execution_id"].startswith("HNX-")


def test_once_replay_continues_same_claimed_execution_instead_of_zero_writer_deadlock(tmp_path, monkeypatch):
    canonical = CanonicalFake()
    canonical.retirements = 1
    expected = NativeRunnerService._claim_identity("HNX-SAME")
    canonical.native = {"native_execution_id": "HNX-SAME", "generation": "g1", "pr_number": 1403,
                        "worker_claim_id": expected, "execution_status": "SEND_BACK"}
    service = NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path,
        worktree_root=tmp_path / "worktrees", canonical=canonical, cursor=CursorFake(),
        github=GithubFake(), model=object())
    monkeypatch.setattr("modules.charlie.native_runner.service.validate_primary_repository",
                        lambda *_: (tmp_path, tmp_path / "worktrees", "b" * 40))
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary",
                        lambda _: {"status": "READY"})
    calls = []
    monkeypatch.setattr(service, "_supervise", lambda mission, native: calls.append(native["native_execution_id"])
                        or {"state": "CONTINUED"})
    assert service.once()["state"] == "CONTINUED"
    assert calls == ["HNX-SAME"] and canonical.renewals == canonical.prepared == 0


def test_resume_rejects_mismatched_stored_claim_before_model_or_packaging(tmp_path, monkeypatch):
    canonical = CanonicalFake()
    canonical.retirements = 1
    canonical.native = {"native_execution_id": "HNX-SAME", "generation": "g1", "pr_number": 1403,
                        "worker_claim_id": "HNC-STALE", "execution_status": "SEND_BACK"}
    service = NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path,
        worktree_root=tmp_path / "worktrees", canonical=canonical, cursor=CursorFake(),
        github=GithubFake(), model=object())
    monkeypatch.setattr("modules.charlie.native_runner.service.validate_primary_repository",
                        lambda *_: (tmp_path, tmp_path / "worktrees", "b" * 40))
    monkeypatch.setattr(service, "_supervise", lambda *_: pytest.fail("packaging reached"))
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary",
                        lambda _: {"status": "READY"})
    with pytest.raises(NativeExecutionError, match="native_writer_identity_conflict"):
        service.once()


def test_resume_rejects_other_executions_live_claim_before_model_or_packaging(tmp_path, monkeypatch):
    class OtherWriterCanonical(CanonicalFake):
        def writers(self): return 1
        def progress(self, mission_id, payload):
            return {"success": False, "status": "native_writer_claim_conflict"}
    canonical = OtherWriterCanonical()
    canonical.retirements = 1
    native_id = "HNX-SAME"
    canonical.native = {"native_execution_id": native_id, "generation": "g1", "pr_number": 1403,
                        "worker_claim_id": NativeRunnerService._claim_identity(native_id),
                        "execution_status": "SEND_BACK"}
    service = NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path,
        worktree_root=tmp_path / "worktrees", canonical=canonical, cursor=CursorFake(),
        github=GithubFake(), model=object())
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary",
                        lambda _: {"status": "READY"})
    monkeypatch.setattr(service, "_supervise", lambda *_: pytest.fail("packaging reached"))
    with pytest.raises(NativeExecutionError, match="native_writer_claim_conflict"):
        service.once()


def test_existing_native_build_runs_canary_before_model_after_restart(tmp_path, monkeypatch):
    canonical = CanonicalFake()
    canonical.retirements = 1
    native_id = "HNX-SAME"
    canonical.native = {"native_execution_id": native_id, "generation": "g1", "pr_number": 0,
                        "worker_claim_id": NativeRunnerService._claim_identity(native_id),
                        "execution_status": "RUNNING"}
    service = NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path,
        worktree_root=tmp_path / "worktrees", canonical=canonical, cursor=CursorFake(),
        github=GithubFake(), model=object())
    monkeypatch.setattr("modules.charlie.native_runner.service.validate_primary_repository",
                        lambda *_: (tmp_path, tmp_path / "worktrees", "b" * 40))
    order = []
    original_progress = canonical.progress
    canonical.progress = lambda mission_id, payload: (
        order.append("canonical_write") or original_progress(mission_id, payload))
    monkeypatch.setattr("modules.charlie.native_runner.service.run_schema_canary",
                        lambda _: order.append("canary") or {"status": "READY"})
    monkeypatch.setattr(service, "_build", lambda *_: order.append("build") or {"state": "BUILT"})
    assert service.once()["state"] == "BUILT"
    assert order[0] == "canary"
    assert order[-1] == "build"
    assert "canonical_write" in order[1:-1]


@pytest.mark.parametrize("existing_native", [False, True])
def test_failing_canary_prevents_cursor_canonical_and_worktree_mutation(
        tmp_path, monkeypatch, existing_native):
    class GuardedCanonical(CanonicalFake):
        def progress(self, *_args, **_kwargs):
            pytest.fail("canonical writer mutation reached")
        def retire_cursor(self, *_args, **_kwargs):
            pytest.fail("canonical retirement reached")
    class GuardedCursor(CursorFake):
        def get_agent(self, _): pytest.fail("Cursor provider reached")
        def get_run(self, *_): pytest.fail("Cursor provider reached")
    canonical = GuardedCanonical()
    if existing_native:
        canonical.retirements = 1
        native_id = "HNX-SAME"
        canonical.native = {
            "native_execution_id": native_id, "generation": "g1", "pr_number": 0,
            "worker_claim_id": NativeRunnerService._claim_identity(native_id),
            "execution_status": "RUNNING",
        }
    worktrees = tmp_path / "worktrees"
    service = NativeRunnerService(
        profile_home=tmp_path, repository_root=tmp_path, worktree_root=worktrees,
        canonical=canonical, cursor=GuardedCursor(), github=GithubFake(), model=object())
    monkeypatch.setattr(
        "modules.charlie.native_runner.service.run_schema_canary",
        lambda _: (_ for _ in ()).throw(NativeExecutionError("hermes_auxiliary_canary_failed")))
    monkeypatch.setattr(
        "modules.charlie.native_runner.service.validate_primary_repository",
        lambda *_: pytest.fail("repository/worktree validation reached"))
    with pytest.raises(NativeExecutionError, match="hermes_auxiliary_canary_failed"):
        service.once()
    assert not (worktrees / "CHARLIE-MISSION-13B47938FF65E2C1").exists()


def test_model_route_mismatch_fails_closed(tmp_path):
    class Reply:
        choices = [SimpleNamespace(message=SimpleNamespace(content='{"status":"READY"}'))]
    def call(**kwargs):
        kwargs["route_info"].update(provider="other", model="openai/gpt-5-mini")
        return Reply()
    with pytest.raises(NativeExecutionError, match="native_runtime_route_mismatch"):
        run_schema_canary(HermesAuxiliaryModel(profile_home=tmp_path, call=call))


def test_render_bootstrap_git_environment_excludes_secret_names(monkeypatch):
    module = importlib.import_module("scripts.charlie_render_native_runner")
    observed = {}
    monkeypatch.setenv("PATH", "contained-path")
    monkeypatch.setenv("CHARLIE_GITHUB_PACKAGER_TOKEN", "must-not-propagate")
    def fake_run(argv, **kwargs):
        observed.update(kwargs.get("env") or {})
        return SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.run(["git", "status"])
    assert observed["PATH"] == "contained-path"
    assert "CHARLIE_GITHUB_PACKAGER_TOKEN" not in observed


def test_packager_lost_claim_fails_before_commit_push_or_pr(tmp_path):
    packager = object.__new__(NativePackager)
    packager.worktree = tmp_path
    packager.authorization = SimpleNamespace(branch="charlie/mission-native-1",
        starting_main_sha="a" * 40,
        allowed_files=("docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",))
    packager.token = "not-observed"
    calls = []
    packager.heartbeat = lambda: (_ for _ in ()).throw(NativeExecutionError("native_writer_claim_conflict"))
    packager._git = lambda *args: calls.append(args) or ""
    packager._push_with_ephemeral_askpass = lambda: calls.append("push")
    packager._github = lambda *_args: calls.append("github")
    with pytest.raises(NativeExecutionError, match="native_writer_claim_conflict"):
        packager.package("title", "body")
    assert calls == []


@pytest.mark.parametrize("admission_rows,expected", [
    ([{"name": "mission-admission", "conclusion": "success", "app": {"id": 4742997}}], True),
    ([{"name": "mission-admission", "conclusion": "success", "app": {"id": 15368}}], False),
    ([{"name": "mission-admission", "conclusion": "success", "app": {"id": 4742997}},
      {"name": "mission-admission", "conclusion": "success", "app": {"id": 15368}}], False),
])
def test_github_observer_requires_unambiguous_admission_guard_app(admission_rows, expected):
    class Client:
        def request(self, method, path, query=None):
            if "/pulls/" in path:
                return {"draft": True, "head": {"sha": "b" * 40}}
            other = [{"name": name, "conclusion": "success", "app": {"id": 15368}}
                     for name in GitHubObserver.REQUIRED if name != "mission-admission"]
            return {"check_runs": other + admission_rows}
    state = GitHubObserver(client=Client()).pull_state(1403)
    assert state["all_required_checks_pass"] is expected
    assert (state["checks"]["mission-admission"] == "success") is expected


def test_systemd_artifact_is_boot_supervised_single_service_without_hermes_dependency():
    unit = Path("deploy/charlie-native-runner/charlie-native-runner.service").read_text(encoding="utf-8")
    assert "WantedBy=multi-user.target" in unit
    assert "Restart=on-failure" in unit and "RestartSec=10s" in unit
    assert "-m scripts.charlie_native_runner --watch" in unit
    assert "hermes" not in unit.lower()
    assert "--auto-merge" not in unit and "deploy" not in unit.lower()


def test_hosted_unittest_gate_runs_when_pytest_import_is_blocked():
    code = (
        "import builtins,unittest; real=builtins.__import__; "
        "builtins.__import__=lambda name,*a,**k: "
        "(_ for _ in ()).throw(ModuleNotFoundError(name)) if name=='pytest' else real(name,*a,**k); "
        "import tests.test_charlie_native_runner as m; "
        "result=unittest.TextTestRunner(verbosity=0).run("
        "unittest.defaultTestLoader.loadTestsFromTestCase(m.HostedCharlieNativeRunnerTests)); "
        "raise SystemExit(0 if result.wasSuccessful() else 1)"
    )
    result = subprocess.run([os.sys.executable, "-c", code], capture_output=True,
                            text=True, shell=False, check=False)
    assert result.returncode == 0, result.stderr


def test_exact_systemd_module_entrypoint_imports_from_repository_root():
    result = subprocess.run([os.sys.executable, "-m", "scripts.charlie_native_runner", "--help"],
                            capture_output=True, text=True, shell=False, check=False)
    assert result.returncode == 0
    assert "--auto-merge" not in result.stdout and "--deploy" not in result.stdout


@pytest.mark.parametrize("candidate_path,summary,reason", [
    ("unauthorized.txt", "", "native_candidate_scope_mismatch"),
    ("docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
     " delete mode 100644 docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
     "native_candidate_metadata_change_rejected"),
])
def test_recovered_invalid_committed_candidate_is_rejected_before_remote_mutation(
        tmp_path, candidate_path, summary, reason):
    packager = object.__new__(NativePackager)
    packager.worktree = tmp_path
    packager.authorization = SimpleNamespace(
        branch="charlie/mission-native-1", starting_main_sha="a" * 40,
        allowed_files=("docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",))
    packager.token = "not-observed"
    calls = []
    def git(*args):
        if args == ("branch", "--show-current"): return "charlie/mission-native-1"
        if args == ("remote", "get-url", "origin"): return "https://github.com/Crewless9086/amadeus-pig-tracking-system.git"
        if args in (("diff", "--name-only"), ("diff", "--cached", "--name-only")): return ""
        if args[0:2] == ("rev-parse", "a" * 40 + "^{commit}"): return "a" * 40
        if args == ("rev-parse", "HEAD"): return "b" * 40
        if "--name-only" in args: return candidate_path
        if "--summary" in args: return summary
        raise AssertionError(args)
    packager._git = git
    packager._push_with_ephemeral_askpass = lambda: calls.append("push")
    packager._github = lambda *_args: calls.append("github")
    completed = SimpleNamespace(returncode=0, stdout=b"diff --git a/unauthorized.txt b/unauthorized.txt\n")
    with patch("modules.charlie.native_runner.execution.run_argv", return_value=completed), \
         patch("modules.charlie.native_runner.execution.subprocess.run", return_value=completed):
        with pytest.raises(NativeExecutionError, match=reason):
            packager.package("title", "body")
    assert calls == []


class HostedCharlieNativeRunnerTests(unittest.TestCase):
    """The charlie-core workflow invokes this module through unittest."""

    def test_no_tool_low_level_model_boundary(self):
        calls = []
        class Reply:
            choices = [SimpleNamespace(message=SimpleNamespace(content='{"status":"READY"}'))]
            model = "test-model"
        def call(**kwargs):
            calls.append(kwargs)
            kwargs["route_info"].update(provider="openrouter", model="test-model")
            return Reply()
        model = HermesAuxiliaryModel(profile_home=".", call=call, model="test-model")
        self.assertEqual("READY", run_schema_canary(model)["status"])
        self.assertEqual([], calls[0]["tools"])
        self.assertNotIn("api_key", calls[0])

    def test_durable_service_has_no_merge_or_deploy_surface(self):
        unit = Path("deploy/charlie-native-runner/charlie-native-runner.service").read_text(encoding="utf-8")
        script = Path("scripts/charlie_native_runner.py").read_text(encoding="utf-8")
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertNotIn("--auto-merge", script)
        self.assertFalse(any(name in NativeRunnerService.__dict__ for name in ("merge", "deploy", "release")))

    def test_plugin_absence_and_local_writer_serialization(self):
        with tempfile.TemporaryDirectory() as root:
            module = importlib.reload(importlib.import_module("modules.charlie.native_runner.service"))
            self.assertIsNotNone(module.NativeRunnerService)
            first, second = ProcessLock(Path(root) / "runner.lock"), ProcessLock(Path(root) / "runner.lock")
            first.acquire()
            try:
                with self.assertRaisesRegex(NativeExecutionError, "native_runner_already_active"):
                    second.acquire()
            finally:
                first.release()

    def test_profile_allowlist_and_broad_credential_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            home = write_profile(Path(root))
            prior = os.environ.pop("GH_TOKEN", None)
            try:
                self.assertTrue(set(REQUIRED).issubset(read_profile_values(home)))
                os.environ["GH_TOKEN"] = "must-not-be-used"
                with self.assertRaisesRegex(NativeExecutionError, "broad_github_credential_forbidden:GH_TOKEN"):
                    read_profile_values(home)
            finally:
                if prior is None:
                    os.environ.pop("GH_TOKEN", None)
                else:
                    os.environ["GH_TOKEN"] = prior

    def test_exact_systemd_entrypoint_and_pre_remote_scope_gate(self):
        result = subprocess.run([os.sys.executable, "-m", "scripts.charlie_native_runner", "--help"],
                                capture_output=True, text=True, shell=False, check=False)
        self.assertEqual(0, result.returncode)
        for candidate_path, summary, reason in (
            ("unauthorized.txt", "", "native_candidate_scope_mismatch"),
            ("docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
             " delete mode 100644 docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
             "native_candidate_metadata_change_rejected"),
        ):
            test_recovered_invalid_committed_candidate_is_rejected_before_remote_mutation(
                Path("."), candidate_path, summary, reason)
