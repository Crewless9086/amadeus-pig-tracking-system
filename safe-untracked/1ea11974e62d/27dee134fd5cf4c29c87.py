"""SEND_BACK regressions: actual HTTP handlers/store; disposable Git only."""
import copy
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_charlie_native_runner_contracts import Plane, Reply, MISSION, NATIVE, TOKEN, service_at, claim_payload
from modules.charlie.native_runner.canonical_client import CanonicalClient, JsonClient, NativeHTTPError
from modules.charlie.native_runner.candidate_contract import binding_from_authority, canonical_projection
from modules.charlie.native_runner.execution import HermesIndependentReviewer, NativeExecutionEngine, NativeExecutionError, REMOTE
from modules.charlie.native_runner.review_packet import build_review_packet, verification_snapshot


def setup_candidate(plane):
    plane.native.update(starting_main_sha="a" * 40, branch="charlie/test", pr_number=1,
        head_sha="b" * 40, candidate_diff_sha256="c" * 64, changed_files=["docs/test.md"],
        allowed_files=["docs/test.md"], forbidden_files=[".git/**", ".env*"],
        allowed_effects=["draft PR"], forbidden_effects=["merge", "deploy"],
        allowed_commands=["git diff --check"], owner_instruction_digest=hashlib.sha256(b"Clarify docs.").hexdigest())
    plane.metadata["mission_vault"] = {"problem_statement": "Clarify docs.",
        "test_plan": ["git diff --check"], "acceptance_criteria": ["Document the owner boundary."]}
    return {"mission_id": MISSION, "metadata": plane.metadata}


def api(plane, opener=None):
    return CanonicalClient("https://example.invalid/api", TOKEN,
                           client=JsonClient("https://example.invalid/api", TOKEN, opener=opener or plane.open))


def test_F5_first_binding_and_exact_replay_read_back_full_contract_one_write():
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    first = plane.api.bind_candidate(MISSION, binding)
    replay = api(plane).bind_candidate(MISSION, binding)
    assert first["acknowledgement"] == "external_candidate_bound"
    assert replay["acknowledgement"] == "exact_replay" and replay["binding"] == first["binding"]
    assert len(plane.writes) == 1
    assert [r[0] for r in plane.requests] == ["POST", "GET", "POST", "GET"]


@pytest.mark.parametrize("restart", [False, True])
def test_F5_lost_acknowledgement_and_restart_never_duplicate_binding(restart):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    def lost(req, **kwargs):
        if req.method == "GET" and restart: raise TimeoutError("isolated readback outage")
        result = plane.open(req, **kwargs)
        if req.method == "POST": raise TimeoutError("isolated lost acknowledgement after commit")
        return result
    if restart:
        with pytest.raises(NativeExecutionError): api(plane, lost).bind_candidate(MISSION, binding)
        result = api(plane).bind_candidate(MISSION, binding)
        assert result["acknowledgement"] == "exact_replay"
    else:
        assert api(plane, lost).bind_candidate(MISSION, binding)["acknowledgement"] == "acknowledgement_lost"
    assert len(plane.writes) == 1


def test_F5_exact_binding_survives_a_fresh_python_process(tmp_path):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    plane.api.bind_candidate(MISSION, binding)
    state = tmp_path / "canonical.json"
    state.write_text(json.dumps({"metadata": plane.metadata, "binding": binding}))
    child = tmp_path / "replay.py"
    child.write_text('''import json, os, socket, sys
from pathlib import Path
def denied(*a, **k): raise AssertionError("offline child network denied")
socket.socket.connect = denied
socket.create_connection = denied
socket.getaddrinfo = denied
if os.environ.get("CHARLIE_REPAIR_BASELINE_SOURCE"):
    import modules.charlie.native_runner.canonical_client as client
    path = Path(os.environ["CHARLIE_REPAIR_BASELINE_SOURCE"])/"modules/charlie/native_runner/canonical_client.py"
    exec(compile(path.read_bytes(), str(path), "exec"), client.__dict__)
from tests.test_charlie_native_runner_contracts import Plane, MISSION
plane = Plane()
with open(sys.argv[1]) as f: saved = json.load(f)
plane.metadata = saved["metadata"]
result = plane.api.bind_candidate(MISSION, saved["binding"])
assert result["acknowledgement"] == "exact_replay"
assert plane.writes == [] and plane.provider_reads == []
assert not any(n == "app" or n.startswith("agent.") for n in sys.modules)
print("exact replay; zero new binding writes; zero provider effects")
''')
    result = subprocess.run([sys.executable, str(child), str(state)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "zero new binding writes" in result.stdout and len(plane.writes) == 1


@pytest.mark.parametrize("field", ["mission_id", "pr_number", "head_sha", "changed_files", "allowed_files",
                                  "forbidden_files", "allowed_effects", "forbidden_effects", "required_tests",
                                  "operational_acceptance", "base_sha", "generation", "branch"])
def test_F5_authenticated_readback_mismatch_cannot_progress(field):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    def mismatch(req, **kwargs):
        response = plane.open(req, **kwargs)
        if req.method == "GET":
            body = json.loads(response.body)
            row = body["mission"]
            if field == "mission_id": row[field] = "OTHER"
            elif field in {"pr_number", "head_sha", "changed_files"}:
                row["metadata"]["review_packet"]["candidate_revision" if field == "head_sha" else field] = "wrong"
            else: row["metadata"]["mission_admission_contract"][field] = "wrong"
            return Reply(200, json.dumps(body).encode())
        return response
    with pytest.raises(NativeExecutionError): api(plane, mismatch).bind_candidate(MISSION, binding)
    assert len(plane.writes) == 1 and len(plane.requests) == 2


@pytest.mark.parametrize("mutation", [{"pr_number": 2}, {"branch_name": "charlie/other"},
    {"base_sha": "d" * 40}, {"generation": "g2"}, {"allowed_effects": ["merge"]},
    {"changed_files": ["other.md"], "allowed_files": ["other.md"]}])
def test_F5_actual_409_rejection_never_becomes_readback_success(mutation):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    plane.api.bind_candidate(MISSION, binding)
    count = len(plane.requests)
    with pytest.raises(NativeHTTPError) as caught:
        plane.api.bind_candidate(MISSION, {**binding, **mutation})
    assert caught.value.status_code == 409 and len(plane.writes) == 1
    assert len(plane.requests) == count + 1  # rejected POST only, no readback bypass


@pytest.mark.parametrize("code,status", [(200, "external_candidate_bound"), (201, "exact_replay"),
                                         (202, "external_candidate_bound"), (204, "external_candidate_bound")])
def test_F5_http_outcome_and_operation_must_match(code, status):
    plane = Plane(); mission = setup_candidate(plane); calls = []
    def malformed(req, **_):
        calls.append(req.method)
        return Reply(code, json.dumps({"success": True, "status": status, "mission_id": MISSION,
                                      "pr_number": 1, "head_sha": "b" * 40}).encode())
    with pytest.raises(NativeExecutionError):
        api(plane, malformed).bind_candidate(MISSION, binding_from_authority(mission, plane.native))
    assert calls == ["POST"] and plane.writes == []


@pytest.mark.parametrize("wrong", [{"pr_number": True}, {"pr_number": 2}, {"head_sha": "d" * 40}])
def test_F5_replay_ack_cannot_contradict_candidate_identity(wrong):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    plane.api.bind_candidate(MISSION, binding)
    count = len(plane.requests)
    def contradictory(req, **kwargs):
        result = plane.open(req, **kwargs)
        if req.method == "POST":
            return Reply(200, json.dumps({**json.loads(result.body), **wrong}).encode())
        return result
    with pytest.raises(NativeExecutionError): api(plane, contradictory).bind_candidate(MISSION, binding)
    assert len(plane.requests) == count + 1 and len(plane.writes) == 1


def test_F5_boolean_PR_is_not_integer_identity_in_readback():
    plane = Plane(); mission = setup_candidate(plane)
    def malformed(req, **kwargs):
        response = plane.open(req, **kwargs)
        if req.method == "GET":
            data = json.loads(response.body)
            data["mission"]["metadata"]["review_packet"]["pr_number"] = True
            return Reply(200, json.dumps(data).encode())
        return response
    with pytest.raises(NativeExecutionError):
        api(plane, malformed).bind_candidate(MISSION, binding_from_authority(mission, plane.native))
    assert len(plane.writes) == 1


@pytest.mark.parametrize("field", ["test_plan", "acceptance_criteria"])
def test_F5_missing_canonical_acceptance_is_blocking_not_invented(field):
    plane = Plane(); mission = setup_candidate(plane)
    del mission["metadata"]["mission_vault"][field]
    with pytest.raises(NativeExecutionError): binding_from_authority(mission, plane.native)
    assert not plane.requests and not plane.writes


def test_F5_corrected_head_actual_handler_invalidates_once_then_replays_without_provider_read():
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    plane.api.bind_candidate(MISSION, binding)
    plane.metadata["mission_admission"] = {"status": "valid", "head_sha": binding["head_sha"]}
    changed = {**binding, "head_sha": "d" * 40, "candidate_diff_sha256": "e" * 64}
    plane.pull = {"state": "open", "head": {"sha": changed["head_sha"], "ref": changed["branch_name"]},
                  "base": {"sha": changed["base_sha"]}}
    result = plane.api.bind_candidate(MISSION, changed)
    assert result["binding"] == changed
    assert len(plane.writes) == 3  # first binding, old admission invalidation, corrected binding
    assert len(plane.provider_reads) == 1
    assert api(plane).bind_candidate(MISSION, changed)["acknowledgement"] == "exact_replay"
    assert len(plane.writes) == 3 and len(plane.provider_reads) == 1


def test_F5_conflicting_head_genuine_409_has_no_write_or_downstream_effect(tmp_path):
    plane = Plane(); mission = setup_candidate(plane)
    binding = binding_from_authority(mission, plane.native)
    plane.api.bind_candidate(MISSION, binding)
    native = {**plane.native, "head_sha": "e" * 40, "execution_status": "PACKAGED"}
    plane.pull = {"state": "open", "head": {"sha": "d" * 40, "ref": binding["branch_name"]},
                  "base": {"sha": binding["base_sha"]}}
    service = service_at(tmp_path, plane.api)
    with pytest.raises(NativeHTTPError) as caught: service._complete_initial_candidate(mission, native)
    assert caught.value.status_code == 409 and len(plane.writes) == 1
    assert len(plane.provider_reads) == 1  # synthetic read only, zero provider writes
    assert not any(r[1].endswith("/progress") or r[1].endswith("/admission") for r in plane.requests)
    assert not service.worktree_root.exists()


@pytest.mark.parametrize("corrected", [False, True])
def test_F1_packaged_and_bound_progress_use_actual_handler_contract_on_restart(tmp_path, corrected):
    plane = Plane(); mission = setup_candidate(plane)
    if corrected:
        plane.native = plane.api.progress(MISSION, claim_payload())
    service = service_at(tmp_path, plane.api)
    service.packager_token = "test-only"
    service._trusted_admission_ready = lambda _: False
    service._request_admission = lambda *a, **k: None
    plane.api.native_context = lambda _: {"offline": True}
    evidence = [{"command": "git diff --check", "returncode": 0}]
    engine = SimpleNamespace(build_patch=lambda *a, **k: {"state": "PATCH_READY", "changed_files": ["docs/test.md"]},
                             verify=lambda: evidence)
    packaged = SimpleNamespace(package=lambda *a: {"pr_number": 1, "commit_sha": "b" * 40,
        "branch": "charlie/test", "changed_files": ["docs/test.md"], "candidate_diff_sha256": "c" * 64})
    # Simulate interruption immediately after the PACKAGED durable write.
    class Interrupted(Exception): pass
    method = "_complete_corrected_candidate" if corrected else "_complete_initial_candidate"
    with patch("modules.charlie.native_runner.service.NativeExecutionEngine", return_value=engine), \
         patch("modules.charlie.native_runner.service.NativePackager", return_value=packaged), \
         patch("modules.charlie.native_runner.service.run_argv", return_value=SimpleNamespace(returncode=0, stdout="")), \
         patch.object(service, method, side_effect=Interrupted):
        with pytest.raises(Interrupted):
            if corrected: service._correct(mission, plane.native)
            else: service._build(mission, plane.native, tmp_path, tmp_path / "unused-worktree")
    restored = plane.metadata["hermes_native_execution"]
    assert "base_sha" not in restored and restored["starting_main_sha"] == "a" * 40
    assert restored["stage_artifact"]["commands"] == evidence
    result = getattr(service, method)({"mission_id": MISSION, "metadata": plane.metadata}, restored)
    assert result["state"] in {"ADMISSION_PENDING", "CORRECTION_ADMISSION_PENDING"}
    assert plane.metadata["review_packet"]["candidate_revision"] == "b" * 40
    for _, url, payload in plane.requests:
        if url.endswith("/progress"):
            assert not ({"branch", "base_sha"} & set(payload))
    assert len([r for r in plane.requests if r[1].endswith("/external-candidate")]) == 1


@pytest.fixture
def content_candidate(tmp_path):
    plane = Plane(); mission = setup_candidate(plane)
    root = tmp_path / "worktrees" / MISSION / "g1" / "native-1"
    root.mkdir(parents=True)
    def git(*args):
        return subprocess.check_output(["git", "-c", "user.name=Isolated Test", "-c", "user.email=test@example.invalid",
            *args], cwd=root, stderr=subprocess.PIPE).decode().strip()
    git("init", "-b", "charlie/test"); git("remote", "add", "origin", REMOTE)
    (root / "docs").mkdir(); (root / "docs/test.md").write_text("Before.\n")
    git("add", "docs/test.md"); git("commit", "-m", "disposable base")
    plane.native["starting_main_sha"] = git("rev-parse", "HEAD")
    (root / "docs/test.md").write_text("After: owner approval required.\n")
    engine = object.__new__(NativeExecutionEngine)
    engine.authorization = SimpleNamespace(starting_main_sha=plane.native["starting_main_sha"], allowed_commands=["git diff --check"])
    engine.worktree = SimpleNamespace(worktree_root=root); engine.heartbeat = lambda: None
    evidence = engine.verify()
    # Compute the observed digest independently of the verification implementation.
    plane.native.update(verification_snapshot(root, plane.native["starting_main_sha"]))
    git("add", "docs/test.md"); git("commit", "-m", "disposable candidate")
    plane.native.update(head_sha=git("rev-parse", "HEAD"), stage_artifact={"commands": evidence})
    return plane, mission, root, evidence


class RecordingModel:
    def __init__(self, during=None): self.calls = []; self.during = during
    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.during: self.during()
        return SimpleNamespace(parsed={"verdict": "APPROVE", "findings": []},
            provider="isolated", model="synthetic-fixture", agent_id="test-reviewer",
            audit={"runtime_boundary": "charlie-native-runner", **{k: kwargs[k] for k in ("task", "purpose", "schema_name")}})


@pytest.mark.parametrize("stage", ["PACKAGED", "CANDIDATE_BOUND", "ADMISSION_PENDING", "SEND_BACK",
                                  "CORRECTION_PACKAGED", "CORRECTION_BOUND", "CORRECTION_ADMISSION_PENDING"])
def test_F2_claim_heartbeat_preserves_interrupted_recovery_stage(tmp_path, stage):
    plane = Plane(); setup_candidate(plane)
    plane.native["execution_status"] = stage
    payload = claim_payload(); payload.pop("execution_status")
    native = plane.api.progress(MISSION, payload)
    service_at(tmp_path, plane.api)._claim_heartbeat(MISSION, NATIVE, native["worker_claim_id"], "review")
    restored = api(plane).mission(MISSION)["mission"]["metadata"]["hermes_native_execution"]
    assert restored["execution_status"] == stage and restored["worker_claim_id"] == native["worker_claim_id"]


@pytest.mark.parametrize("role", ["CHALLENGE", "SECURITY", "FUNCTIONAL"])
def test_F4_actual_content_reaches_fresh_reviewer_at_exact_head(content_candidate, tmp_path, role):
    plane, mission, root, evidence = content_candidate
    service = service_at(tmp_path, plane.api); service.model = RecordingModel()
    service._trusted_admission_ready = lambda _: True
    result = service._review_candidate(role, mission, plane.native)
    packet = json.loads(service.model.calls[0]["input"][0]["text"])
    assert "Before." in packet["content"]["diff"] and "owner approval required" in packet["content"]["diff"]
    assert packet["content"]["files"] == [{"path": "docs/test.md", "before": "Before.\n", "after": "After: owner approval required.\n"}]
    assert packet["verification"][0]["stdout"] == "" and packet["verification"][0]["returncode"] == 0
    assert packet["contract"]["operational_acceptance"] == ["Document the owner boundary."]
    assert result["packet_sha256"] == packet["packet_sha256"]
    assert "never invent" in service.model.calls[0]["instructions"].lower()
    assert result["verdict"] == "APPROVE"  # fixture only; challenge is never forced to invent SEND_BACK
    assert not plane.requests and not plane.writes


def test_F4_metadata_only_packet_rejected_before_model():
    model = RecordingModel()
    with pytest.raises(NativeExecutionError): HermesIndependentReviewer(model).review("SECURITY", {"candidate": {}})
    assert model.calls == []


@pytest.mark.parametrize("corrected", [False, True])
def test_F4_actual_initial_and_corrected_caller_transmits_content(content_candidate, tmp_path, corrected):
    plane, mission, root, evidence = content_candidate
    service = service_at(tmp_path, plane.api)
    service._trusted_admission_ready = lambda _: True
    service._claim_heartbeat = lambda *a, **k: None
    native = {**plane.native, "base_sha": plane.native["starting_main_sha"],
              "execution_status": "CORRECTION_ADMISSION_PENDING" if corrected else "ADMISSION_PENDING"}
    packets = []
    class Captured(Exception): pass
    class Reviewer:
        def __init__(self, *_): pass
        def review(self, role, packet): packets.append(packet); raise Captured()
    with patch("modules.charlie.native_runner.service.HermesIndependentReviewer", Reviewer):
        with pytest.raises(Captured):
            method = service._complete_corrected_candidate if corrected else service._complete_initial_candidate
            method(mission, native, evidence)
    assert "Before." in packets[0]["content"]["diff"]
    assert packets[0]["content"]["files"][0]["after"] == "After: owner approval required.\n"
    assert packets[0]["verification"][0]["candidate_diff_sha256"] == native["candidate_diff_sha256"]
    assert plane.writes == []  # capture occurs before any verdict


@pytest.mark.parametrize("change", ["head", "scope", "diff", "evidence", "instruction", "dirty"])
def test_F4_wrong_content_or_unbound_evidence_is_blocking(content_candidate, change):
    plane, mission, root, evidence = content_candidate
    native = copy.deepcopy(plane.native)
    if change == "head": native["head_sha"] = "d" * 40
    if change == "scope": native["changed_files"] = ["wrong.md"]
    if change == "diff": native["candidate_diff_sha256"] = "e" * 64
    if change == "evidence": evidence[0]["candidate_diff_sha256"] = "f" * 64
    if change == "instruction": native["owner_instruction_digest"] = "0" * 64
    if change == "dirty": (root / "docs/test.md").write_text("unreviewed change")
    with pytest.raises(NativeExecutionError): build_review_packet(root, mission, native, evidence)


@pytest.mark.parametrize("change", ["remote_head", "local_content"])
def test_F4_head_or_content_change_during_review_cannot_record_verdict(content_candidate, tmp_path, change):
    plane, mission, root, _ = content_candidate
    service = service_at(tmp_path, plane.api); observations = []
    def ready(_):
        observations.append(1)
        return change != "remote_head" or len(observations) == 1
    service._trusted_admission_ready = ready
    service.model = RecordingModel(lambda: (root / "docs/test.md").write_text("unreviewed") if change == "local_content" else None)
    with pytest.raises(NativeExecutionError): service._review_candidate("SECURITY", mission, plane.native)
    assert len(service.model.calls) == 1 and plane.writes == []
