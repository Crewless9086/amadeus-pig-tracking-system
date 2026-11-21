import json
import threading
from types import SimpleNamespace

import pytest

from modules.charlie.native_runner import engineering_service as svc
from modules.charlie.native_runner.execution import NativeExecutionError

REV = "a" * 40
ENV = {"CORE_NATIVE_RUNNER_MODE": "engineering", "RENDER_SERVICE_ID": svc.WORKER,
       "RENDER_GIT_COMMIT": REV}


class Stop:
    def __init__(self, rounds=2):
        self.rounds, self.waits = rounds, 0
    def is_set(self):
        return self.waits >= self.rounds
    def wait(self, seconds):
        self.waits += 1
        return self.is_set()


class Client:
    mission_id = "SYNTHETIC-ENGINEERING"
    def __init__(self, state="issued", fail_claim=False):
        self.state, self.fail_claim, self.calls = state, fail_claim, []
    def call(self, op, payload=None):
        self.calls.append((op, payload))
        if op == "claim":
            self.state = "claimed"
            if self.fail_claim:
                raise TimeoutError("ambiguous response")
        return {"state": self.state, "manifest": {"worker_revision": REV}}


def test_one_natural_pickup_and_later_idle_without_second_run():
    client, stop, reports, runs = Client(), Stop(3), [], []
    class Run:
        def __init__(self, client, grant, instance, **kw):
            runs.append(instance)
        def run(self):
            client.state = "artifact_ready"
            return {"artifact_sha256": "b" * 64, "reserved_micro_usd": 300000}
    svc.run_worker(environ=ENV, client=client, stop=stop, report=reports.append, run_factory=Run)
    assert len(runs) == 1
    assert sum(op == "claim" for op, _ in client.calls) == 1
    idle = [r for r in reports if r["status"] == "engineering_worker_inactive"]
    assert len(idle) == 2 and all(r["new_model_calls"] == 0 for r in idle)
    assert len({r["instance"] for r in reports}) == 1


@pytest.mark.parametrize("state", ["claimed", "artifact_ready", "revoked", "blocked"])
def test_restart_never_reuses_consumed_claim(state):
    client = Client(state)
    svc.run_worker(environ=ENV, client=client, stop=Stop(),
                   report=lambda _: None, run_factory=lambda *a, **k: pytest.fail("unadmitted run"))
    assert all(op == "current" for op, _ in client.calls)


def test_lost_claim_response_is_not_retried_or_executed():
    client = Client(fail_claim=True)
    reports = []
    svc.run_worker(environ=ENV, client=client, stop=Stop(), report=reports.append,
                   run_factory=lambda *a, **k: pytest.fail("ambiguous claim executed"))
    assert sum(op == "claim" for op, _ in client.calls) == 1
    assert reports[-1]["status"] == "engineering_worker_contained"


def test_wrong_revision_never_claims():
    client = Client()
    svc.run_worker(environ={**ENV, "RENDER_GIT_COMMIT": "c" * 40}, client=client,
                   stop=Stop(), report=lambda _: None)
    assert all(op != "claim" for op, _ in client.calls)


@pytest.mark.parametrize("field,value", [("CORE_NATIVE_RUNNER_MODE", "builder"),
                                        ("RENDER_SERVICE_ID", "another-service")])
def test_mode_and_provider_identity_required(field, value):
    with pytest.raises(NativeExecutionError):
        svc.run_worker(environ={**ENV, field: value}, client=Client(), stop=Stop())


def test_client_never_retries_post():
    attempts = []
    class Opener:
        def open(self, request, timeout):
            attempts.append(request)
            raise TimeoutError()
    client = svc.Client("SYNTHETIC", "x" * 43, opener=Opener())
    with pytest.raises(TimeoutError):
        client.call("claim", {"instance": "a" * 32})
    assert len(attempts) == 1
    assert attempts[0].get_method() == "POST"


def test_client_rejects_unrelated_operation_before_network():
    class Opener:
        def open(self, *args, **kwargs):
            pytest.fail("network called")
    client = svc.Client("SYNTHETIC", "x" * 43, opener=Opener())
    with pytest.raises(NativeExecutionError):
        client.call("deploy")


def test_artifact_written_exclusively(tmp_path):
    path = tmp_path / "artifact.json"
    first = svc.write_once(path, {"a": 1})
    assert len(first) == 64
    with pytest.raises(FileExistsError):
        svc.write_once(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}


def test_revocation_or_hold_blocks_before_next_stage(tmp_path):
    from datetime import datetime, timedelta, timezone
    run = object.__new__(svc.EngineeringRun)
    run.stop = threading.Event()
    run.instance = "a" * 32
    run.manifest = {}
    run.grant = {"expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    class Refused:
        def call(self, *a, **k):
            raise NativeExecutionError("grant_inactive")
    run.client = Refused()
    with pytest.raises(NativeExecutionError, match="grant_inactive"):
        run.check()


@pytest.mark.skipif(__import__("sys").platform != "linux" or __import__("os").geteuid() != 0,
                    reason="real Linux isolation required")
def test_complete_cloud_pipeline_authors_tests_reviews_and_records_private_candidate(tmp_path, monkeypatch):
    """Real Git and jailed pytest; only model and canonical HTTPS are replaced."""
    import difflib
    import hashlib
    import os
    from datetime import datetime, timedelta, timezone
    from modules.charlie import cloud_engineering as store
    from modules.charlie.native_runner.execution import run_argv
    from modules.charlie.native_runner.model_adapter import StructuredResult

    # This unrelated synthetic calculation exercises the pipeline; it is not
    # the real HERDMASTER repair that must be authored by the cloud model.
    origin = tmp_path / "origin"
    origin.mkdir()
    initial = {
        "modules/__init__.py": "",
        "docs/09-vault-brain/synthetic-governance.md": "Synthetic governing instruction.\n",
        "modules/pig_weights/__init__.py": "",
        "modules/pig_weights/synthetic.py": "def total(values):\n    return values[0]\n",
        "tests/test_synthetic.py": "from modules.pig_weights.synthetic import total\n\ndef test_one():\n    assert total([2]) == 2\n",
    }
    for path, body in initial.items():
        target = origin / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    def git(*args):
        result = run_argv(["git", *args], cwd=origin)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()
    git("init")
    git("add", ".")
    git("-c", "user.name=Synthetic Fixture", "-c", "user.email=synthetic@example.invalid", "commit", "-m", "fixture")
    revision = git("rev-parse", "HEAD")
    acceptance = ("from modules.pig_weights.synthetic import total\n\n"
                  "def test_conflicting_duplicate_order():\n    assert total([2, 3]) == 5\n")
    grant = {"contract": store.CONTRACT, "state": "claimed", "instance": "c" * 32,
             "mission_id": "CORE-SYNTHETIC", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "manifest": {"generation": "d" * 32, "base_sha": revision, "worker_revision": revision,
                          "api_revision": revision, "allowed_files": sorted([
                              "modules/pig_weights/synthetic.py", "tests/test_synthetic.py"]),
                          "test_paths": ["tests/test_synthetic.py"], "context_paths": sorted([
                              "modules/pig_weights/synthetic.py", "tests/test_synthetic.py",
                              "docs/09-vault-brain/synthetic-governance.md"]),
                          "instruction": "Correct total to add every value and add regression coverage.",
                          "acceptance_source": acceptance, "acceptance_sha256": hashlib.sha256(acceptance.encode()).hexdigest(),
                          "budget_micro_usd": 800000, "max_seconds": 1200},
             "reservations": [], "reserved_micro_usd": 0}
    real_git = svc.checked_git
    def local_fetch(args, cwd):
        if args[:2] == ["fetch", "--no-tags"]:
            args = ["fetch", "--no-tags", "--depth=1", str(origin), revision]
        return real_git(args, cwd)
    monkeypatch.setattr(svc, "checked_git", local_fetch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", revision)

    class Canonical:
        mission_id = "CORE-SYNTHETIC"
        def __init__(self):
            self.grant, self.calls = grant, []
        def call(self, operation, payload=None):
            self.calls.append(operation)
            self.grant = store.transition(self.grant, operation, payload, now=datetime.now(timezone.utc))
            return self.grant
    client = Canonical()
    invocations = []
    class Model:
        def __init__(self, **kwargs):
            assert kwargs["strict_budget"] is True and kwargs["max_attempts"] == 1
            self.reserve = kwargs["before_attempt"]
        def complete_structured(self, **kwargs):
            task = kwargs["task"]
            request_hash = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()
            self.reserve(request_sha256=request_hash, input_bytes=1000, max_tokens=kwargs["max_tokens"], task=task)
            invocations.append(task)
            audit = {"runtime_boundary": "charlie-native-runner", "task": task,
                     "purpose": kwargs["purpose"], "schema_name": kwargs["schema_name"],
                     "profile": "default", "tools_count": 0, "strict_budget": True,
                     "attempt_count": 1, "request_sha256": request_hash, "input_bytes": 1000,
                      "max_tokens": kwargs["max_tokens"], "provider_request_id": "synthetic-" + str(len(invocations)),
                     "invocation_id": "native-" + format(len(invocations), "032x")}
            if task == "charlie_native_builder":
                updated = {
                    "modules/pig_weights/synthetic.py": "def total(values):\n    return sum(values)\n",
                    "tests/test_synthetic.py": initial["tests/test_synthetic.py"] + "\ndef test_multiple():\n    assert total([2, 3]) == 5\n",
                }
                patch = "".join("".join(difflib.unified_diff(initial[path].splitlines(True),
                        body.splitlines(True), fromfile="a/" + path, tofile="b/" + path))
                        for path, body in updated.items())
                parsed = {"state": "PATCH_READY", "context_paths": [], "unified_diff": patch,
                          "test_proposal": ["fixed suite"], "reason": "Correct total."}
            else:
                packet = json.loads(kwargs["input"][0]["text"])
                assert packet["governance_context"] == [{"path": "docs/09-vault-brain/synthetic-governance.md",
                    "content": "Synthetic governing instruction.\n"}]
                assert "return sum(values)" in packet["candidate_diff"]
                assert packet["verification"]["completion"]["expected_passed"] is True
                parsed = {"verdict": "APPROVE", "findings": []}
            return StructuredResult(parsed, "openrouter", "openai/gpt-5-mini", audit["provider_request_id"], audit)
    run = svc.EngineeringRun(client, grant, "c" * 32, root=tmp_path / "private",
                             model_factory=Model, report=lambda _: None)
    result = run.run()
    assert result["state"] == "artifact_ready"
    assert result["reserved_micro_usd"] == 300000
    assert len(invocations) == 3
    artifact = result["artifact"]
    assert artifact["baseline"]["returncode"] == 1
    assert artifact["tests"]["returncode"] == 0
    assert artifact["tests"]["completion"]["expected_passed"] is True
    assert artifact["publications"] == artifact["farm_actions"] == artifact["messages"] == 0
    assert git("rev-parse", "HEAD") == revision
    assert "complete" == client.calls[-1]
    assert (run.directory / "final-artifact.json").is_file()


@pytest.mark.parametrize("late_reason", ["stop", "deadline"])
def test_reservation_remains_consumed_when_stop_or_deadline_arrives_before_inference(tmp_path, late_reason):
    from datetime import datetime, timedelta, timezone
    run = object.__new__(svc.EngineeringRun)
    run.directory, run.instance = tmp_path, "a" * 32
    run.stop = threading.Event()
    run.grant = {"reservations": [], "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
    run.check = lambda: None
    reservations = []
    class Canonical:
        def call(self, operation, payload):
            assert operation == "reserve"
            reservations.append(payload)
            result = {"reservations": reservations,
                      "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
            if late_reason == "stop":
                run.stop.set()
            else:
                result["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
            return result
    run.client = Canonical()
    with pytest.raises(NativeExecutionError, match="stop_requested|model_deadline_margin"):
        run.reserve(request_sha256="b" * 64, input_bytes=200, max_tokens=200, task="charlie_native_builder")
    assert len(reservations) == 1
    assert len(list(tmp_path.glob("reservation-*.json"))) == 1


@pytest.mark.parametrize("stage,kind,status", [("resolution", "unexpected_error", None),
    ("reservation", "unexpected_error", None), ("sdk_submission", "http_status", 400),
    ("sdk_submission", "http_status", 401), ("sdk_submission", "http_status", 402),
    ("sdk_submission", "http_status", 429), ("sdk_submission", "timeout", None),
    ("sdk_submission", "connection", None)])
def test_adapter_diagnostics_are_logged_without_changing_block_or_repeating(stage, kind, status):
    from modules.charlie.native_runner.model_adapter import NativeModelFailure
    error = NativeModelFailure(stage=stage, kind=kind, status=status)
    client, reports, runs = Client(), [], []
    class Run:
        def __init__(self, *args, **kwargs):
            runs.append(True)
        def run(self):
            raise error
    svc.run_worker(environ=ENV, client=client, stop=Stop(4), report=reports.append, run_factory=Run)
    event = reports[-1]
    assert event["status"] == "engineering_worker_contained"
    assert event["reason"] == "hermes_auxiliary_inference_failed"
    assert event["model_failure_stage"] == stage and event["model_failure_kind"] == kind
    assert event.get("model_failure_status") == status
    assert [op for op, _ in client.calls] == ["current", "claim", "block"]
    assert client.calls[-1][1] == {"instance": event["instance"], "reason": event["reason"]}
    assert len(runs) == 1


@pytest.mark.parametrize("variant", ["ordinary", "subclass", "stage", "kind", "status", "bool_status", "relation"])
def test_untrusted_or_mutated_exception_diagnostics_cannot_escape(variant):
    from modules.charlie.native_runner.model_adapter import NativeModelFailure
    private = "synthetic-private-body-or-header-92217"
    if variant == "ordinary":
        error = NativeExecutionError("hermes_auxiliary_inference_failed")
    elif variant == "subclass":
        class Untrusted(NativeModelFailure):
            pass
        error = Untrusted(stage="sdk_submission", kind="http_status", status=400)
    else:
        error = NativeModelFailure(stage="sdk_submission", kind="http_status", status=400)
    error.body = error.headers = error.message = private
    if variant in ("ordinary", "stage"):
        error.failure_stage = private
    elif variant == "kind":
        error.failure_kind = private
    elif variant == "status":
        error.failure_status = private
    elif variant == "bool_status":
        error.failure_status = True
    elif variant == "relation":
        error.failure_stage = "reservation"
    class Run:
        def __init__(self, *args, **kwargs):
            pass
        def run(self):
            raise error
    client, reports = Client(), []
    svc.run_worker(environ=ENV, client=client, stop=Stop(), report=reports.append, run_factory=Run)
    assert set(reports[-1]) == {"status", "instance", "reason"}
    assert private not in json.dumps(reports) + json.dumps(client.calls)


@pytest.fixture
def response_pipeline(tmp_path_factory, monkeypatch):
    """Actual worker, adapter, SDK, Git and canonical transitions; no network.

    The test receipt is synthetic: Linux isolation remains separately qualified.
    This fixture never imports or changes the real mortality target.
    """
    import difflib
    import hashlib
    import socket
    import sys
    from contextlib import nullcontext
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from types import ModuleType
    import httpx
    import openai
    from modules.charlie import cloud_engineering as store
    from modules.charlie.native_runner.model_adapter import (
        DEFAULT_MODEL, STRICT_BASE_URL, HermesAuxiliaryModel,
    )

    # Keep reservation/audit filenames within Windows path limits.
    tmp_path = tmp_path_factory.mktemp("p")
    state = SimpleNamespace(calls=[], outputs=[], responses=[], reports=[], runs=[],
        mutate=None, error=None, revoke=False, send_back=False, builders=0, real_tests=False)
    private = "synthetic-private-response-91827"
    state.private = private
    def reject_network(*args, **kwargs):
        pytest.fail("real network attempted")
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    # All Git writes are confined to this fixture, including clone/worktree setup.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    origin = tmp_path / "origin"
    origin.mkdir()
    initial = {"modules/pig_weights/synthetic.py": "def total(values):\n    return values[0]\n",
               "tests/test_synthetic.py": "from modules.pig_weights.synthetic import total\n\ndef test_one():\n    assert total([2]) == 2\n",
               "docs/09-vault-brain/synthetic.md": "Synthetic governance.\n"}
    for name, content in initial.items():
        path = origin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    svc.checked_git(["init"], origin)
    svc.checked_git(["add", "."], origin)
    svc.checked_git(["-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                     "commit", "-m", "fixture"], origin)
    revision = svc.checked_git(["rev-parse", "HEAD"], origin)
    acceptance = ("from modules.pig_weights.synthetic import total\n\n"
                  "def test_conflicting_duplicate_order():\n    assert total([2, 3]) == 5\n")
    allowed = sorted(name for name in initial if not name.startswith("docs/"))
    grant = {"contract": store.CONTRACT, "state": "issued", "mission_id": "CORE-SYNTHETIC",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        "manifest": {"generation": "d" * 32, "base_sha": revision,
            "worker_revision": revision, "api_revision": revision, "allowed_files": allowed,
            "test_paths": ["tests/test_synthetic.py"], "context_paths": sorted(initial),
            "instruction": "Correct the synthetic total and add regression coverage.",
            "acceptance_source": acceptance,
            "acceptance_sha256": hashlib.sha256(acceptance.encode()).hexdigest(),
            "budget_micro_usd": 700000, "max_seconds": 1200},
        "reservations": [], "reserved_micro_usd": 0}
    class Canonical:
        mission_id = "CORE-SYNTHETIC"
        def __init__(self):
            self.grant, self.calls = grant, []
        def call(self, operation, payload=None):
            self.calls.append((operation, payload))
            if operation == "current":
                return self.grant
            if self.grant["state"] in store.TERMINAL:
                raise NativeExecutionError("grant_inactive")
            self.grant = store.transition(self.grant, operation, payload,
                                          now=datetime.now(timezone.utc))
            return self.grant
    state.client = Canonical()
    real_git = svc.checked_git
    def local_fetch(args, cwd):
        if args[:2] == ["fetch", "--no-tags"]:
            args = ["fetch", "--no-tags", "--depth=1", str(origin), revision]
        return real_git(args, cwd)
    monkeypatch.setattr(svc, "checked_git", local_fetch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", revision)

    def ready():
        patch = ""
        for name in allowed:
            old = (state.runs[0].worktree / name).read_text()
            new = old + "# synthetic revision " + str(state.builders) + "\n"
            patch += "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                 fromfile="a/" + name, tofile="b/" + name))
        return {"state": "PATCH_READY", "context_paths": [], "unified_diff": patch,
                "test_proposal": ["synthetic fixed suite"], "reason": private}
    state.ready = ready
    def handler(request):
        body = json.loads(request.content)
        state.calls.append(body)
        if state.error:
            raise state.error(private, request=request)
        builder = "patch" in body["response_format"]["json_schema"]["name"]
        if builder:
            state.builders += 1
            content = state.outputs.pop(0) if state.outputs else ready()
            if callable(content):
                content = content()
        else:
            content = {"verdict": "SEND_BACK" if state.send_back else "APPROVE",
                       "findings": ["synthetic revision required"] if state.send_back else []}
        state.responses.append(content)
        if state.revoke:
            state.client.grant = {**state.client.grant, "state": "revoked"}
        return httpx.Response(200, json={"id": "gen-synthetic-" + str(len(state.calls)),
            "object": "chat.completion", "created": 1, "model": DEFAULT_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(content)}}]})
    def transport(**kwargs):
        assert kwargs == {"retries": 0, "verify": True, "trust_env": False}
        return httpx.MockTransport(handler)
    parent_http = httpx.Client(transport=httpx.MockTransport(reject_network), trust_env=False)
    parent = openai.OpenAI(api_key="synthetic-only", base_url=STRICT_BASE_URL,
                          http_client=parent_http)
    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    aux = ModuleType("agent.auxiliary_client")
    aux.resolve_provider_client = lambda **kwargs: (parent, DEFAULT_MODEL)
    monkeypatch.setitem(sys.modules, "agent", ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)
    plugins = ModuleType("hermes_cli.plugins")
    plugins._plugin_home_scope = lambda home: nullcontext()
    monkeypatch.setitem(sys.modules, "hermes_cli", ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    class Model(HermesAuxiliaryModel):
        def complete_structured(self, **kwargs):
            result = super().complete_structured(**kwargs)
            return replace(result, **state.mutate(result)) if state.mutate else result
    class Run(svc.EngineeringRun):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, root=tmp_path / "private", model_factory=Model)
            state.runs.append(self)
        def tests(self, label, *, baseline=False):
            # Portable fixtures never claim Linux sandbox isolation. One contract
            # journey runs real pytest on fixed synthetic files; others use receipts.
            self.check()
            if state.real_tests:
                import os
                import subprocess
                from pathlib import Path
                from modules.charlie.native_runner import test_sandbox
                source = svc.stage_tree(self.worktree, self.directory / (label + "-source"),
                                        self.manifest["acceptance_source"])
                tests = [svc.ACCEPTANCE_PATH] if baseline else [*self.manifest["test_paths"], svc.ACCEPTANCE_PATH]
                completion_path = self.directory / (label + "-completion.json")
                # Trusted test-only launcher: real pytest and the existing completion
                # observer, no external plugins/network/credentials or target repair.
                code = """
import importlib.util,json,socket,sys
from pathlib import Path
def deny_network(*args, **kwargs):
    raise AssertionError('synthetic fixture forbids network')
socket.create_connection=socket.socket.connect=deny_network
spec=importlib.util.spec_from_file_location('trusted_sandbox',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
import pytest
observer=module._CompletionRecorder()
status=pytest.main(['-q','--capture=no','-p','no:cacheprovider','--confcutdir=.',*json.loads(sys.argv[3])],plugins=[observer])
with Path(sys.argv[2]).open('x',encoding='utf-8') as output:
    json.dump(observer.receipt('synthetic-contract',int(status)),output)
raise SystemExit(status)
"""
                env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR") if key in os.environ}
                env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                           PYTHONPATH=str(source), TEMP=str(source), TMP=str(source))
                result = subprocess.run([sys.executable, "-B", "-c", code, test_sandbox.__file__,
                    str(completion_path), json.dumps(tests)], cwd=source, env=env,
                    text=True, capture_output=True, timeout=60, check=False)
                completion = test_sandbox._verified_completion(completion_path.read_bytes(),
                    "synthetic-contract", tests, self.expected_tests, result.returncode)
                assert completion, result.stdout + result.stderr
                receipt = {"returncode": result.returncode, "stdout": result.stdout,
                    "stderr": result.stderr, "completion": completion,
                    "containment": {"verified": True, "scope": "fixed_synthetic_fixture_only"},
                    "linux_isolation_qualified": False, "real_pytest": True}
                svc.write_once(self.directory / (label + "-tests.json"), receipt)
                return receipt
            expected = self.expected_tests
            code = 1 if baseline else 0
            phases = {"setup": "passed", "call": "failed" if baseline else "passed",
                      "teardown": "passed"}
            receipt = {"returncode": code, "stdout": "test_conflicting_duplicate_order AssertionError",
                "containment": {"verified": True}, "completion": {"verified": True,
                    "completed": True, "exitstatus": code, "collection_errors": 0,
                    "collected": expected, "expected_test_ids": expected,
                    "expected_passed": not baseline, "all_passed": not baseline,
                    "outcomes": {name: phases for name in expected}}}
            svc.write_once(self.directory / (label + "-tests.json"), receipt)
            return receipt
    def execute():
        svc.run_worker(environ={**ENV, "RENDER_GIT_COMMIT": revision}, client=state.client,
                       stop=Stop(2), report=state.reports.append, run_factory=Run)
        state.directory = state.runs[0].directory
        state.grant = state.client.grant
        state.reason = state.reports[-1].get("reason")
        assert sum(op == "claim" for op, _ in state.client.calls) == 1
        assert private not in json.dumps(state.reports)
        return state
    state.execute = execute
    yield state
    parent.close()


def _semantic_response(**changes):
    return {"state": "PATCH_READY", "context_paths": ["synthetic.py"], "unified_diff": "",
            "test_proposal": [], "reason": "synthetic-private-response-91827", **changes}


@pytest.mark.parametrize("changes,reason", [
    ({"unified_diff": "not applied"}, "native_patch_state_invalid"),
    ({"context_paths": []}, "native_patch_state_invalid"),
    ({"state": "NEEDS_CONTEXT", "context_paths": []}, "native_context_state_invalid"),
    ({"state": "NEEDS_CONTEXT", "unified_diff": "not applied"}, "native_context_state_invalid"),
    ({"state": "BLOCKED"}, "native_blocked_state_invalid"),
    ({"state": "BLOCKED", "context_paths": [], "unified_diff": "not applied"}, "native_blocked_state_invalid"),
    ({"state": "BLOCKED", "context_paths": [], "reason": " "}, "native_blocked_state_invalid"),
])
def test_real_sdk_semantic_recovery_retains_response_and_completes(response_pipeline, changes, reason):
    import hashlib
    import stat
    p = response_pipeline
    invalid = _semantic_response(**changes)
    p.outputs = [invalid]
    p.execute()
    assert p.grant["state"] == "artifact_ready", p.reports
    assert len(p.calls) == len(p.grant["reservations"]) == 4
    assert p.grant["reserved_micro_usd"] == 400000
    assert len(list(p.directory.glob("model-response-*.json"))) == 4
    for reservation in p.grant["reservations"]:
        path = p.directory / ("model-response-" + reservation["request_id"] + ".json")
        evidence = json.loads(path.read_text())
        assert len(path.read_bytes()) <= svc.MODEL_RESPONSE_BYTES
        assert evidence["request_id"] == reservation["request_id"]
        assert evidence["request_sha256"] == reservation["request_sha256"]
        audit = p.directory / ("model-" + reservation["request_sha256"] + ".json")
        assert evidence["audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
        if __import__("os").name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    failure = json.loads((p.directory / "builder-failure-1.json").read_text())
    assert failure["reason"] == reason
    raw = json.loads((p.directory / failure["response_evidence"]["file"]).read_text())
    assert raw["parsed"] == invalid
    assert failure["response_evidence"]["sha256"] == hashlib.sha256(
        (p.directory / failure["response_evidence"]["file"]).read_bytes()).hexdigest()
    assert not (p.directory / "builder-response-1.json").exists()
    artifact = p.grant["artifact"]
    assert artifact["iterations"][0]["feedback"] == [{"source": "builder_semantic_validator",
        "reason": reason, "attempt": 1,
        "instruction": svc.BUILDER_CORRECTIONS[reason]}]
    assert [r["role"] for r in artifact["reviews"]] == ["SECURITY", "FUNCTIONAL"]
    assert len({call["provider_request_id"] for call in artifact["model_calls"]}) == 4
    assert p.reports[-1]["status"] == "engineering_worker_inactive"
    # The next request contains controlled feedback, never the invalid response.
    messages = p.calls[1]["messages"]
    assert reason in json.dumps(messages) and "not applied" not in json.dumps(messages)
    assert "PATCH_READY" in p.calls[0]["messages"][0]["content"]


def test_repeated_semantics_exhaust_exactly_three_distinct_reservations(response_pipeline):
    p = response_pipeline
    p.outputs = [_semantic_response()] * 3
    p.execute()
    assert p.grant["state"] == "blocked" and p.reason == "engineering_revision_limit"
    assert len(p.calls) == len(p.grant["reservations"]) == 3
    assert len({row["request_sha256"] for row in p.grant["reservations"]}) == 3
    assert len(list(p.directory.glob("builder-failure-*.json"))) == 3
    assert len(list(p.directory.glob("model-response-*.json"))) == 3
    assert svc.checked_git(["diff", "--name-only"], p.runs[0].worktree) == ""
    assert not (p.directory / "final-artifact.json").exists()


@pytest.mark.parametrize("state,paths", [("NEEDS_CONTEXT", ["synthetic.py"]), ("BLOCKED", [])])
def test_valid_nonready_remains_terminal(response_pipeline, state, paths):
    p = response_pipeline
    p.outputs = [_semantic_response(state=state, context_paths=paths)]
    p.execute()
    assert p.reason == "builder_not_ready" and len(p.calls) == 1
    assert len(list(p.directory.glob("model-response-*.json"))) == 1
    assert not list(p.directory.glob("builder-failure-*.json"))


@pytest.mark.parametrize("kind,expected", [
    ("no_audit", "strict_model_audit_required"),
    ("wrong_reservation", "model_response_reservation_invalid"),
    ("identity", "native_runtime_identity_missing"),
    ("role", "native_runtime_role_audit_invalid"),
])
def test_identity_audit_or_reservation_failure_cannot_recover_semantics(response_pipeline, kind, expected):
    p = response_pipeline
    p.outputs = [_semantic_response()]
    def mutate(result):
        if kind == "no_audit":
            return {"audit": {}}
        if kind == "wrong_reservation":
            return {"audit": {**result.audit, "request_sha256": "a" * 64}}
        if kind == "identity":
            return {"agent_id": ""}
        return {"audit": {**result.audit, "purpose": "wrong-role"}}
    p.mutate = mutate
    p.execute()
    assert p.reason == expected and len(p.calls) == 1
    assert not list(p.directory.glob("builder-failure-*.json"))
    assert len(list(p.directory.glob("model-response-*.json"))) == (0 if kind in {"no_audit", "wrong_reservation"} else 1)


@pytest.mark.parametrize("kind", ["network", "unknown_semantic", "adapter_semantic", "structural"])
def test_unknown_structural_or_ambiguous_failure_is_not_retried(response_pipeline, monkeypatch, kind):
    import httpx
    from modules.charlie.native_runner import execution
    from modules.charlie.native_runner.schemas import NativeSchemaError
    p = response_pipeline
    if kind == "network":
        p.error = httpx.ReadTimeout
    elif kind == "structural":
        p.outputs = [_semantic_response(test_proposal=[4])]
    else:
        def refuse(*args, **kwargs):
            raise NativeSchemaError(p.private if kind == "unknown_semantic" else "native_patch_state_invalid")
        if kind == "unknown_semantic":
            monkeypatch.setattr(execution, "validate_native_response", refuse)
        else:
            # Adapter-raised semantic-looking errors have no returned response.
            p.mutate = refuse
    p.execute()
    assert p.grant["state"] == "blocked" and len(p.calls) == 1
    assert len(p.grant["reservations"]) == 1
    assert svc.checked_git(["diff", "--name-only"], p.runs[0].worktree) == ""
    for path in p.directory.glob("builder-failure-*.json"):
        assert p.private not in path.read_text()
    expected = {"network": "hermes_auxiliary_inference_failed",
                "unknown_semantic": "native_builder_response_invalid",
                "adapter_semantic": "native_patch_state_invalid",
                "structural": "native_test_proposal_invalid"}
    assert p.reason == expected[kind]


def test_revoke_after_invalid_response_prevents_next_paid_work(response_pipeline):
    p = response_pipeline
    p.outputs = [_semantic_response()]
    p.revoke = True
    p.execute()
    assert p.grant["state"] == "revoked" and p.reason == "grant_inactive"
    assert len(p.calls) == len(p.grant["reservations"]) == 1
    assert len(list(p.directory.glob("model-response-*.json"))) == 1


@pytest.mark.parametrize("kind", ["response", "audit"])
def test_private_evidence_has_a_hard_size_bound(response_pipeline, kind):
    p = response_pipeline
    if kind == "response":
        p.outputs = [_semantic_response(reason="x" * svc.MODEL_RESPONSE_BYTES)]
    else:
        p.mutate = lambda result: {"audit": {**result.audit, "extra": "x" * svc.MODEL_AUDIT_BYTES}}
    p.execute()
    assert p.reason == "model_evidence_size_bound" and len(p.calls) == 1
    assert not list(p.directory.glob("model-response-*.json"))


def test_revision_reviews_cannot_exceed_existing_seven_reservation_budget(response_pipeline):
    p = response_pipeline
    p.send_back = True
    p.execute()
    assert p.grant["state"] == "blocked"
    assert len(p.calls) == len(p.grant["reservations"]) == 7
    assert p.grant["reserved_micro_usd"] == 700000
    assert p.builders == 3
    assert not (p.directory / "final-artifact.json").exists()


@pytest.mark.parametrize("kind", ["network", "adapter_semantic"])
def test_prior_response_cannot_justify_retrying_later_ambiguous_failure(response_pipeline, kind):
    import httpx
    from modules.charlie.native_runner.schemas import NativeSchemaError
    p = response_pipeline
    def first():
        if kind == "network":
            p.error = httpx.ReadTimeout
        return _semantic_response()
    p.outputs = [first]
    if kind == "adapter_semantic":
        def mutate(result):
            if len(p.calls) == 2:
                raise NativeSchemaError("native_patch_state_invalid")
            return {}
        p.mutate = mutate
    p.execute()
    assert p.grant["state"] == "blocked"
    assert len(p.calls) == len(p.grant["reservations"]) == 2
    assert len(list(p.directory.glob("model-response-*.json"))) == 1
    assert svc.checked_git(["diff", "--name-only"], p.runs[0].worktree) == ""
    if kind == "adapter_semantic":
        assert json.loads((p.directory / "builder-failure-2.json").read_text())["response_evidence"] is None


def test_real_sdk_valid_first_response_preserves_three_call_path(response_pipeline):
    p = response_pipeline.execute()
    assert p.grant["state"] == "artifact_ready", p.reports
    assert len(p.calls) == len(p.grant["reservations"]) == 3
    assert not list(p.directory.glob("builder-failure-*.json"))


def _begin_patch_response():
    # Production-shaped format, wholly synthetic content and path.
    return _semantic_response(context_paths=[], unified_diff=(
        "*** Begin Patch\n*** Update File: modules/pig_weights/synthetic.py\n"
        "@@\n-    return values[0]\n+    return sum(values)\n*** End Patch\n"))


def _request_feedback(call):
    return json.loads(call["messages"][1]["content"])["feedback"]


def test_contract_corrections_reach_real_sdk_and_real_fail_to_pass_private_artifact(response_pipeline):
    import difflib
    import hashlib
    p = response_pipeline
    p.real_tests = True
    malformed = _begin_patch_response()
    contradictory = {**malformed, "context_paths": ["modules/pig_weights/synthetic.py"]}
    def repaired():
        patch = ""
        replacements = {
            "modules/pig_weights/synthetic.py": "def total(values):\n    return sum(values)\n",
            "tests/test_synthetic.py": ("from modules.pig_weights.synthetic import total\n\n"
                "def test_one():\n    assert total([2]) == 2\n\n"
                "def test_many():\n    assert total([2, 3]) == 5\n"),
        }
        for name, new in replacements.items():
            old = (p.runs[0].worktree / name).read_text()
            patch += "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                fromfile="a/" + name, tofile="b/" + name))
        return {**malformed, "unified_diff": patch}
    p.outputs = [malformed, contradictory, repaired]
    p.execute()
    assert p.grant["state"] == "artifact_ready", p.reports
    assert len(p.calls) == len(p.grant["reservations"]) == 5
    assert p.builders == 3 and p.grant["reserved_micro_usd"] == 500000
    assert len({r["request_sha256"] for r in p.grant["reservations"]}) == 5
    for attempt, reason, stage in [(1, "native_patch_paths_invalid", "patch_validation"),
                                  (2, "native_patch_state_invalid", "builder_semantic_validation")]:
        path = p.directory / f"builder-failure-{attempt}.json"
        failure = json.loads(path.read_text())
        assert failure["reason"] == reason and failure["stage"] == stage
        assert failure["attempt"] == attempt and len(path.read_bytes()) <= 4096
        evidence = failure["response_evidence"]
        response = p.directory / evidence["file"]
        assert hashlib.sha256(response.read_bytes()).hexdigest() == evidence["sha256"]
        assert json.loads(response.read_text())["request_id"] == p.grant["reservations"][attempt-1]["request_id"]
        feedback = _request_feedback(p.calls[attempt])
        assert feedback[0]["reason"] == reason and feedback[0]["attempt"] == attempt
        assert feedback[0]["instruction"] == svc.BUILDER_CORRECTIONS[reason]
        assert "--- a/" in feedback[0]["instruction"] and "*** Begin Patch" in feedback[0]["instruction"]
        assert malformed["unified_diff"] not in json.dumps(feedback)
    assert "context_paths=[]" in _request_feedback(p.calls[2])[0]["instruction"]
    artifact = p.grant["artifact"]
    assert artifact["baseline"]["real_pytest"] and artifact["baseline"]["returncode"] == 1
    assert "AssertionError" in artifact["baseline"]["stdout"]
    assert artifact["tests"]["real_pytest"] and artifact["tests"]["returncode"] == 0
    assert artifact["tests"]["completion"]["all_passed"]
    assert len(artifact["tests"]["completion"]["collected"]) == 3
    assert [r["role"] for r in artifact["reviews"]] == ["SECURITY", "FUNCTIONAL"]
    assert all(r["verdict"] == "APPROVE" for r in artifact["reviews"])
    assert all(r["candidate_binding"] == artifact["candidate_binding"] for r in artifact["reviews"])
    assert "return sum(values)" in artifact["candidate_diff"]
    assert json.loads((p.directory / "final-artifact.json").read_text()) == artifact
    stages = [body["stage"] for op, body in p.client.calls if op == "progress"]
    assert stages == ["baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"]
    assert sum(op == "complete" for op, _ in p.client.calls) == 1
    assert p.reports[-1]["status"] == "engineering_worker_inactive"
    assert p.reports[-1]["new_model_calls"] == 0
    assert not (p.directory / "candidate-1-tests.json").exists()
    assert not (p.directory / "candidate-2-tests.json").exists()


def test_repeated_begin_patch_rejections_are_durable_without_application_or_fourth_call(response_pipeline):
    p = response_pipeline
    p.outputs = [_begin_patch_response()] * 3
    p.execute()
    assert p.reason == "engineering_revision_limit" and p.grant["state"] == "blocked"
    assert len(p.calls) == len(p.grant["reservations"]) == 3
    assert p.grant["reserved_micro_usd"] == 300000
    assert len({r["request_sha256"] for r in p.grant["reservations"]}) == 3
    for attempt in range(1, 4):
        failure = json.loads((p.directory / f"builder-failure-{attempt}.json").read_text())
        assert failure["stage"] == "patch_validation" and failure["reason"] == "native_patch_paths_invalid"
        assert failure["attempt"] == attempt
        assert p.private not in json.dumps(failure)
    assert svc.checked_git(["diff", "--name-only"], p.runs[0].worktree) == ""
    assert not list(p.directory.glob("candidate-*-tests.json"))
    assert not list(p.directory.glob("*-review-*.json"))
    assert not (p.directory / "final-artifact.json").exists()


def test_apply_failure_never_becomes_another_builder_request(response_pipeline, monkeypatch):
    p = response_pipeline
    real = svc.run_argv
    def fail_apply(argv, **kwargs):
        if argv[:2] == ["git", "apply"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="private detail")
        return real(argv, **kwargs)
    monkeypatch.setattr(svc, "run_argv", fail_apply)
    p.execute()
    assert p.reason == "native_patch_apply_failed" and len(p.calls) == 1
    assert len(p.grant["reservations"]) == 1
    assert not list(p.directory.glob("builder-failure-*.json"))
    assert svc.checked_git(["diff", "--name-only"], p.runs[0].worktree) == ""
