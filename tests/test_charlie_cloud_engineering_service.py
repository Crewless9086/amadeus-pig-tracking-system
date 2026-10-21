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
