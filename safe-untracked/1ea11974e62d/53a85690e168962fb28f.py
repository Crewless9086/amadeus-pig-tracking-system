"""Offline caller/Flask-handler/store contracts; no app startup or database.

AST loading executes the tracked functions unchanged, including their real
decorators and gateway check. Only database I/O and unrelated listing reads
are replaced. This is not Postgres concurrency or deployed-runtime proof.
"""
import ast
import hmac
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Blueprint, Flask, jsonify, request

from modules.charlie.native_runner.canonical_client import CanonicalClient, GitHubObserver, JsonClient
from modules.charlie.native_runner.execution import NativeExecutionError
from modules.charlie.native_runner.service import NativeRunnerService

MISSION = "CHARLIE-MISSION-TEST"
NATIVE = "HNX-TEST"
TOKEN = "isolated-test-gateway-credential-000000"
SOURCE = Path(__file__).resolve().parents[1]


def load_functions(relative_path, names, scope):
    path = SOURCE / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


class Plane:
    def __init__(self):
        self.native = {"mission_id": MISSION, "native_execution_id": NATIVE,
                       "generation": "g1", "status": "valid", "execution_status": "RUNNING"}
        self.metadata = {"hermes_native_execution": self.native,
                         "cursor_provider_retirement": {"provider_status": "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT"}}
        self.fail_read = False
        self.missing = False
        self.writes = []
        self.requests = []
        self.provider_reads = []
        self.pull = {}
        plane = self

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def cursor(self): return self
            def execute(self, sql, params=None):
                self.sql = sql
                if plane.fail_read:
                    raise OSError("isolated database unavailable")
                if sql.lstrip().startswith("update"):
                    plane.metadata = json.loads(params["metadata"])
                    plane.writes.append(params)
            def fetchone(self):
                if plane.missing: return None
                return ("in_progress", plane.metadata) if "select status," in self.sql else (plane.metadata,)
            def fetchall(self): return [(MISSION, "in_progress", plane.metadata)]

        scope = {"_clean_text": lambda v,n: str(v or "").strip()[:n],
                 "_database_url": lambda _: "disposable-placeholder", "_connect": lambda *_: Cursor(),
                 "_insert_event": lambda *_: None, "datetime": datetime, "timedelta": timedelta,
                 "timezone": timezone, "json": json, "re": re, "hashlib": hashlib}
        self.store = load_functions("modules/charlie/mission_store.py", [
            "record_hermes_native_execution_state", "list_resumable_hermes_native_executions",
            "retire_cursor_provider_execution", "bind_external_supervisor_candidate",
            "invalidate_external_candidate_admission"], scope)
        bp = Blueprint("offline_native_contract", __name__)
        def mission(_):
            return {"success": True, "status": "ok", "mission": {
                "mission_id": MISSION, "metadata": self.metadata}}, 200
        def missions(**_):
            return ({"success": False, "missions": []}, 503) if self.fail_read else ({"missions": []}, 200)
        route_scope = {**scope, "charlie_bp": bp, "jsonify": jsonify, "request": request,
                       "hmac": hmac, "env_value": lambda _: TOKEN,
                       "get_mission": mission, "list_missions": missions,
                       "urllib": SimpleNamespace(error=urllib.error, request=SimpleNamespace(
                           Request=urllib.request.Request, urlopen=self.read_github))}
        load_functions("modules/charlie/routes.py", ["_require_hermes_gateway_access",
            "charlie_hermes_native_execution_progress_route", "charlie_hermes_native_recovery_route",
            "charlie_hermes_writer_count_route", "charlie_hermes_mission_status_route",
            "charlie_hermes_cursor_retirement_route", "charlie_external_supervisor_candidate_route"], route_scope)
        app = Flask("offline_native_contract")
        app.register_blueprint(bp, url_prefix="/api")
        self.http = app.test_client()
        self.api = CanonicalClient("https://example.invalid/api", TOKEN,
            client=JsonClient("https://example.invalid/api", TOKEN, opener=self.open))

    def read_github(self, req, **_):
        self.provider_reads.append(req.full_url)
        return Reply(200, json.dumps(self.pull).encode())

    def open(self, req, **_):
        self.requests.append((req.method, req.full_url, json.loads(req.data) if req.data else None))
        path = urllib.parse.urlsplit(req.full_url).path
        response = self.http.open(path, method=req.method, headers=dict(req.header_items()), data=req.data)
        if response.status_code >= 400:
            raise urllib.error.HTTPError(req.full_url, response.status_code, "test failure", {}, io.BytesIO(response.data))
        return Reply(response.status_code, response.data)


class Reply:
    def __init__(self, status, body): self.status, self.body = status, body
    def read(self, *_): return self.body
    def __enter__(self): return self
    def __exit__(self, *_): pass


def client_response(body, code=200):
    def opened(req, **_):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        if code >= 400:
            raise urllib.error.HTTPError(req.full_url, code, "isolated rejection", {}, io.BytesIO(raw))
        return Reply(code, raw)
    return CanonicalClient("https://example.invalid/api", TOKEN,
                           client=JsonClient("https://example.invalid/api", TOKEN, opener=opened))


def service_at(tmp_path, canonical=None):
    def forbidden_model(**_): raise AssertionError("isolated test must not invoke a model")
    return NativeRunnerService(profile_home=tmp_path, repository_root=tmp_path / "repository",
        worktree_root=tmp_path / "worktrees", canonical=canonical or Plane().api,
        model=SimpleNamespace(complete_structured=forbidden_model),
        cursor=object(), github=object())


def claim_payload():
    return {"native_execution_id": NATIVE, "event": "native_writer_claimed",
            "execution_status": "RUNNING", "worker_claim_id": NativeRunnerService._claim_identity(NATIVE),
            "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=9)).isoformat()}


def hold(service):
    service.status_path.parent.mkdir(parents=True, exist_ok=True)
    value = {"state": "BLOCKED_HOLD", "mission_id": MISSION, "reason": "hermes_auxiliary_inference_failed",
             "stage": "model_canary", "blocker_fingerprint": "f" * 64, "generation": "g1",
             "authority_identity": "PDA-TEST", "runner_revision": "a" * 40, "repeated": 2,
             "repository_mutation": False, "remote_mutation": False,
             "reporting_completed": {"canonical": True, "thread": True, "approvals": True}}
    service.status_path.write_text(json.dumps(value), encoding="utf-8")
    return value


def test_actual_claim_handler_grants_heartbeat_and_releases_exact_identity():
    plane = Plane()
    payload = claim_payload()
    result = plane.api.progress(MISSION, payload)
    assert result["mission_id"] == MISSION and result["worker_claim_id"] == payload["worker_claim_id"]
    result = plane.api.progress(MISSION, payload)
    assert result["claim_expires_at"] == payload["claim_expires_at"]
    result = plane.api.progress(MISSION, {"native_execution_id": NATIVE, "event": "native_writer_released",
        "execution_status": "OWNER_DECISION_REQUIRED", "release_claim_id": payload["worker_claim_id"]})
    assert result["worker_claim_id"] == "" and len(plane.writes) == 3


def test_actual_retirement_handler_projects_agent_ids_and_replays_same_receipt():
    plane = Plane()
    evidence = {"generation": "g1", "cursor_agent_id": "bc-test", "cursor_run_id": "run-test",
        "execution_attempt": 5, "provider_agent_state": "ARCHIVED", "provider_run_state": "FINISHED",
        "branch": "cursor/test", "repository_mutation": False, "remote_branch_created": False,
        "pr_number": 0, "head_sha": "", "exact_candidate": "absent"}
    plane.metadata = {"external_supervisor_state": dict(evidence), "dispatch_authorization": {"generation": "g1"}}
    result = plane.api.retire_cursor(MISSION, evidence)
    assert result["agent_id"] == "bc-test" and result["run_id"] == "run-test"
    assert plane.api.retire_cursor(MISSION, evidence) == result and len(plane.writes) == 1
    with pytest.raises(NativeExecutionError): plane.api.retire_cursor(MISSION, {**evidence, "cursor_run_id": "run-other"})
    assert len(plane.writes) == 1


def test_actual_claim_409_has_zero_downstream_effects(tmp_path):
    plane = Plane()
    plane.native.update(worker_claim_id="HNC-OTHER", claim_expires_at=claim_payload()["claim_expires_at"])
    service = service_at(tmp_path, plane.api)
    effects = []
    def forbidden(*_, **__): effects.append("downstream"); raise AssertionError("effect after rejected claim")
    with patch("modules.charlie.native_runner.service.NativeExecutionEngine", forbidden), \
         patch("modules.charlie.native_runner.service.NativePackager", forbidden), \
         patch("modules.charlie.native_runner.service.run_schema_canary", forbidden):
        with pytest.raises(NativeExecutionError) as rejected:
            service._build({"mission_id": MISSION}, {"native_execution_id": NATIVE}, tmp_path, tmp_path / "native-1")
    assert getattr(rejected.value, "status_code", None) == 409
    assert effects == [] and plane.writes == [] and not (tmp_path / "native-1").exists()


def test_reproduction_6_real_http_conflict_rejected_by_service_guard(tmp_path):
    service = service_at(tmp_path, client_response({"success": False, "status": "native_writer_claim_conflict"}, 409))
    with pytest.raises(NativeExecutionError): service._record_progress(MISSION, claim_payload())


def test_existing_execution_rejected_claim_precedes_model_and_repository(tmp_path):
    plane = Plane()
    service = service_at(tmp_path, plane.api)
    original = plane.api.progress
    def raced(mid, payload):
        plane.native.update(worker_claim_id="HNC-RACING", claim_expires_at=payload["claim_expires_at"])
        return original(mid, payload)
    plane.api.progress = raced
    effects = []
    def forbidden(*_, **__): effects.append("downstream"); raise AssertionError("unowned execution")
    with patch("modules.charlie.native_runner.service.run_schema_canary", forbidden), \
         patch("modules.charlie.native_runner.service.validate_primary_repository", forbidden):
        with pytest.raises(NativeExecutionError): service.once()
    assert effects == [] and plane.writes == []


@pytest.mark.parametrize("code", [400, 404, 409, 500, 503])
def test_failed_progress_http_is_never_an_acknowledgement(code):
    api = client_response({"success": False, "status": "native_writer_claim_conflict"}, code)
    with pytest.raises(NativeExecutionError): api.progress(MISSION, claim_payload())


@pytest.mark.parametrize("body,code", [({}, 200), ({"success": True}, 201),
    ({"success": False, "authorization": {}}, 200), (b"", 201), (b"{bad", 201),
    ({"success": True, "status": "native_execution_state_recorded", "authorization": {}}, 202)])
def test_malformed_or_wrong_http_success_cannot_grant_claim(body, code):
    with pytest.raises(NativeExecutionError): client_response(body, code).progress(MISSION, claim_payload())


@pytest.mark.parametrize("key,value", [("mission_id", "OTHER"), ("native_execution_id", "HNX-OTHER"),
    ("worker_claim_id", "HNC-OTHER"), ("event", "different"), ("execution_status", "FAILED"), ("claim_expires_at", "")])
def test_successful_transport_with_wrong_operation_identity_is_rejected(key, value):
    payload = claim_payload()
    authorization = {"mission_id": MISSION, **payload, key: value}
    body = {"success": True, "status": "native_execution_state_recorded", "authorization": authorization}
    with pytest.raises(NativeExecutionError): client_response(body, 201).progress(MISSION, payload)


def test_handler_discovery_and_writer_failure_never_report_idle_or_zero(tmp_path):
    plane = Plane(); plane.fail_read = True
    service = service_at(tmp_path, plane.api)
    with pytest.raises(NativeExecutionError): service.once()
    with pytest.raises(NativeExecutionError): plane.api.writers()
    assert json.loads(service.status_path.read_text())["state"] == "BLOCKED" and plane.writes == []


def test_discovery_failure_replaces_stale_idle_projection(tmp_path):
    plane = Plane(); plane.metadata = {}
    service = service_at(tmp_path, plane.api)
    assert service.once()["state"] == "IDLE"
    plane.fail_read = True
    with pytest.raises(NativeExecutionError): service.once()
    assert json.loads(service.status_path.read_text())["state"] == "BLOCKED"


@pytest.mark.parametrize("body", [{}, {"success": False, "executions": []},
    {"success": True, "status": "native_recovery_ready"},
    {"success": True, "status": "native_recovery_ready", "executions": {}},
    {"success": True, "status": "native_recovery_ready", "executions": [{"mission_id": ""}]}])
def test_invalid_discovery_schema_is_not_an_empty_queue(body):
    with pytest.raises(NativeExecutionError): client_response(body).resumable()


@pytest.mark.parametrize("count", [None, False, "0", -1, 0.0])
def test_invalid_writer_schema_is_not_zero(count):
    with pytest.raises(NativeExecutionError): client_response({"success": True, "running": count}).writers()


def test_actual_empty_discovery_and_zero_writers_are_accepted(tmp_path):
    plane = Plane(); plane.metadata = {}
    assert plane.api.resumable() == [] and plane.api.writers() == 0
    assert service_at(tmp_path, plane.api).once()["state"] == "IDLE"


def test_actual_gateway_rejection_has_no_store_effects():
    plane = Plane(); plane.api.client.token = "wrong-test-token"
    with pytest.raises(NativeExecutionError): plane.api.progress(MISSION, claim_payload())
    assert plane.writes == []


def test_absent_read_is_explicit_only_for_github_branch():
    api = client_response({"message": "Not Found"}, 404)
    observer = GitHubObserver(client=api.client)
    assert observer.branch_exists("charlie/test") is False
    with pytest.raises(NativeExecutionError): api.mission(MISSION)
    with pytest.raises(NativeExecutionError): observer.find_pull("charlie/test")


def test_real_successful_branch_and_empty_pull_responses():
    observer = GitHubObserver(client=client_response({"ref": "refs/heads/charlie/test", "object": {"sha": "a" * 40}}).client)
    assert observer.branch_exists("charlie/test") is True
    observer.client = client_response([]).client
    assert observer.find_pull("charlie/test") == 0


def test_sigterm_preserves_hold_and_receipts_for_fresh_process(tmp_path):
    service = service_at(tmp_path); prior = hold(service)
    stopped = threading.Event(); stopped.set()
    assert service.watch(stop_event=stopped) == 0
    stored = json.loads(service.status_path.read_text())
    assert all(stored[k] == v for k,v in prior.items())
    assert stored["process_state"] == "STOPPED"
    fresh = service_at(tmp_path)
    with pytest.raises(NativeExecutionError): fresh.once()


def test_two_disposable_python_processes_preserve_and_enforce_the_same_hold(tmp_path):
    service = service_at(tmp_path); hold(service)
    # Real process replacement; the supervisor stop event is simulated because
    # Windows SIGTERM does not provide POSIX graceful-shutdown semantics.
    script = r'''
import os, sys, socket, json, threading, types
from pathlib import Path
def denied(*a, **k): raise AssertionError("child network/model forbidden")
socket.socket.connect = denied; socket.create_connection = denied; socket.getaddrinfo = denied
import modules.charlie.native_runner
if os.environ.get("CHARLIE_REPAIR_BASELINE_SOURCE"):
    for leaf in ("canonical_client", "service"):
        name = "modules.charlie.native_runner." + leaf
        path = Path(os.environ["CHARLIE_REPAIR_BASELINE_SOURCE"]) / "modules/charlie/native_runner" / (leaf + ".py")
        mod = types.ModuleType(name); mod.__file__ = str(path); mod.__package__ = "modules.charlie.native_runner"
        sys.modules[name] = mod; setattr(sys.modules[mod.__package__], leaf, mod)
        exec(compile(path.read_bytes(), str(path), "exec"), mod.__dict__)
from modules.charlie.native_runner.service import NativeRunnerService
from modules.charlie.native_runner.execution import NativeExecutionError
root = Path(sys.argv[1])
service = NativeRunnerService(profile_home=root, repository_root=root / "repo", worktree_root=root / "worktrees",
    canonical=types.SimpleNamespace(resumable=denied, mission=denied), cursor=object(), github=object(), model=object())
if sys.argv[2] == "stop":
    stopping = threading.Event(); stopping.set(); service.watch(stop_event=stopping)
else:
    try: service.once()
    except NativeExecutionError as exc:
        assert str(exc) == "native_execution_held", str(exc)
    else: raise AssertionError("held process executed")
print(json.dumps({"state": json.loads(service.status_path.read_text())["state"]}))
'''
    for mode in ("stop", "restart"):
        result = subprocess.run([sys.executable, "-B", "-c", script, str(tmp_path), mode],
                                capture_output=True, text=True, timeout=15, check=False)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["state"] == "BLOCKED_HOLD"


@pytest.mark.parametrize("update", [{"state": "IDLE"}, {"state": "STOPPED", "reason": "sigterm"},
                                    {"state": "RUNNING", "reason": "different"}])
def test_ordinary_status_updates_cannot_erase_hold(tmp_path, update):
    service = service_at(tmp_path); prior = hold(service)
    service._status(**update)
    stored = json.loads(service.status_path.read_text())
    assert all(stored[k] == v for k,v in prior.items())


def test_changed_revision_and_resume_string_never_open_a_held_cycle(tmp_path, monkeypatch):
    plane = Plane(); plane.metadata["native_runner_resume_identity"] = "unverified-owner-string"
    service = service_at(tmp_path, plane.api); hold(service)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    effects = []
    service.once = lambda: effects.append("execution")
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, _): self.stopped = True; return True
    service.watch(stop_event=Stop())
    assert effects == []
    stored = json.loads(service.status_path.read_text())
    assert stored["blocker_fingerprint"] == "f" * 64 and stored["state"] == "BLOCKED_HOLD"


def test_canonical_blocker_contains_once_even_without_local_projection(tmp_path):
    plane = Plane(); plane.metadata["native_runner_blocker"] = {"reason": "unfunded", "notification_identity": "f" * 64}
    service = service_at(tmp_path, plane.api)
    with patch("modules.charlie.native_runner.service.run_schema_canary", side_effect=AssertionError("paid cycle")):
        with pytest.raises(NativeExecutionError): service.once()
    assert json.loads(service.status_path.read_text())["state"] == "BLOCKED_HOLD"
    assert plane.writes == []


@pytest.mark.parametrize("malformed", [None, {}, [], "", False])
def test_malformed_canonical_blocker_never_authorizes_execution(tmp_path, malformed):
    plane = Plane(); plane.metadata["native_runner_blocker"] = malformed
    service = service_at(tmp_path, plane.api)
    with patch("modules.charlie.native_runner.service.run_schema_canary", side_effect=AssertionError("paid cycle")):
        with pytest.raises(NativeExecutionError): service.once()
    assert plane.writes == []


def test_api_outage_retains_known_generation_authority_and_receipts(tmp_path):
    service = service_at(tmp_path); prior = hold(service)
    service.canonical = client_response({"success": False}, 503)
    service._active_stage = "transport"
    service._report_blocker(MISSION, "native_transport_unavailable", 2)
    stored = json.loads(service.status_path.read_text())
    assert all(stored[k] == v for k,v in prior.items())


def test_ordinary_update_cannot_reset_notification_receipts_or_retry_budget(tmp_path):
    service = service_at(tmp_path); hold(service)
    service._status(state="BLOCKED_HOLD", reporting_attempts={"thread": 2})
    stored = service._status(state="IDLE", reporting_attempts={"thread": 0}, reporting_completed={"thread": False})
    assert stored["reporting_completed"]["thread"] is True and stored["reporting_attempts"]["thread"] == 2


def test_retry_count_survives_restart_and_alternating_errors(tmp_path):
    service = service_at(tmp_path)
    service._active_stage = "discovery"
    service._report_blocker("", "native_transport_unavailable", 1)
    fresh = service_at(tmp_path)
    fresh._active_mission_id = ""
    def failed(): raise NativeExecutionError("native_canonical_response_invalid")
    fresh.once = failed
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, _): self.stopped = True; return True
    fresh.watch(stop_event=Stop())
    stored = json.loads(fresh.status_path.read_text())
    assert stored["repeated"] == 2 and stored["state"] == "BLOCKED_HOLD"


def test_held_watch_retains_process_lock_for_its_whole_lifetime(tmp_path):
    from modules.charlie.native_runner.service import ProcessLock
    service = service_at(tmp_path); hold(service)
    observed = []
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, _):
            with pytest.raises(NativeExecutionError):
                with ProcessLock(service.worktree_root / ".charlie-native-runner.lock"):
                    observed.append("second writer")
            self.stopped = True; return True
    service.watch(stop_event=Stop())
    assert observed == []


@pytest.mark.parametrize("raw", ["{bad", "null", "[]", "{}", '{"state":"unknown"}',
                                  '{"state":"BLOCKED_HOLD","repeated":"2"}'])
def test_malformed_status_preserved_and_never_opens_discovery(tmp_path, raw):
    service = service_at(tmp_path)
    service.status_path.parent.mkdir(parents=True)
    service.status_path.write_text(raw)
    with pytest.raises(NativeExecutionError): service.once()
    assert service.status_path.read_text() == raw


def test_reporting_receipt_survives_interruption_before_next_destination(tmp_path):
    service = service_at(tmp_path)
    service._active_stage = "model_canary"
    posts = []
    class Notifier:
        def post(self, channel, *_, **__):
            posts.append(channel)
            if channel == "C-APPROVALS": raise KeyboardInterrupt("isolated termination")
            return {"ok": True}
    class Canonical:
        def mission(self, _): return {"mission": {"metadata": {"external_supervisor_state": {
            "generation": "g1", "slack_channel_id": "C-THREAD", "slack_thread_ts": "1.1"},
            "dispatch_authorization": {"authorization_id": "PDA-TEST"}}}}
        def blocker(self, *_): return {"success": True}
    service.canonical, service.notifier = Canonical(), Notifier()
    with pytest.raises(KeyboardInterrupt): service._report_blocker(MISSION, "unfunded", 2)
    saved = json.loads(service.status_path.read_text())
    assert saved["reporting_completed"]["thread"] is True and saved["generation"] == "g1"
    fresh = service_at(tmp_path); fresh.canonical = Canonical(); fresh.notifier = Notifier()
    fresh._active_stage = "model_canary"
    with pytest.raises(KeyboardInterrupt): fresh._report_blocker(MISSION, "unfunded", 2)
    assert posts.count("C-THREAD") == 1


def test_blueprint_url_reaches_actual_api_handler():
    import yaml
    path = Path(os.environ.get("CHARLIE_REPAIR_BASELINE_BLUEPRINT") or SOURCE / "render.yaml")
    blueprint = yaml.safe_load(path.read_text())
    worker = next(s for s in blueprint["services"] if s["name"] == "charlie-native-runner")
    base = next(v["value"] for v in worker["envVars"] if v["key"] == "CHARLIE_CANONICAL_API_URL")
    plane = Plane(); plane.api.client.base_url = base
    assert plane.api.mission(MISSION)["mission"]["mission_id"] == MISSION
    assert plane.requests[-1][1].endswith("/api/charlie/hermes/missions/" + MISSION)
