"""Exact OMQ child/PR1343 maintainer reconciliation; no public apply endpoint.

Caller authentication is a trusted maintainer boundary, never inferred from files.
Preparation is DB-free. Apply performs canonical metadata reconciliation only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = "oom_desktop_candidate_reconciliation_v1"
MISSION_ID = "OMQ-20260813-03-MORNING-CONTAINMENT"
PARENT_ID = "OMQ-20260813-03"
BASE = "3e77d3434b071078a41917a68fa63f2fa7b314ec"
HEAD = "228da3269907398e17eb3568113d3fd7881d493b"
BRANCH = "codex/oom-general-manager-repair-20260921"
PATHS = sorted([
    "modules/oom_sakkie/general_manager_worker.py", "modules/oom_sakkie/farm_manager_runtime.py",
    "scripts/oom_sakkie_morning_scheduler.py", "tests/test_oom_sakkie_general_manager_postgres.py",
    "tests/test_oom_sakkie_morning_scheduler.py", "tests/test_oom_sakkie_herd_morning_language.py",
])
HELPERS = ("modules/charlie/mission_store.py", "modules/charlie/mission_control.py")
MAINTAINER_PATHS = {"scripts/reconcile_oom_desktop_candidate.py",
    "tests/test_oom_desktop_candidate_reconciliation.py",
    ".github/workflows/oom-desktop-rebind-qualification.yml"}
DECISION = "reconcile_exact_oom_child_pr1343"
TASK_ID = "01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6"
REMOVED_EFFECTS = {"test_fixture_only_successor_for_pr_1336",
    "application_revision_rollback_to_9edc57d643bae3974f3321478fc59e1631c50623"}
ADDED_EFFECTS = {"exact_pr1343_six_file_source_repair",
    "existing_scheduler_application_release:crn-d9us4d3ncjis73adehrg",
    "application_revision_rollback:web:86e95d09078a5b1a2eb8b698e04489d9a2184e38",
    "application_revision_rollback:scheduler:203a7e9b44db5edf644a3ee1feba54118b12ede6"}
REQUIRED_TESTS = {"Closed Render migration rail with disposable Postgres",
    "Playwright real-browser behavior gate", "Unit tests with disposable Postgres audit rails",
    "charlie-core", "mission-admission"}
REQUIRED_ACCEPTANCE = {
    "Release only the protected merge whose application tree equals PR1343 head228da3269907398e17eb3568113d3fd7881d493b to existing web srv-d6sijjkhg0os73f7regg and scheduler crn-d9us4d3ncjis73adehrg after protected merge and required checks.",
    "No database migration, permission or configuration change, farm write, hardware command, manual cron trigger or manufactured acceptance.",
    "Verify exact loaded revisions and genuine agent/owner journeys; source, CI, health and terminal-created fixtures are not business completion.",
}


class ReconciliationError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _require(condition, reason):
    if not condition:
        raise ReconciliationError(reason)


def _fields(value, keys, reason):
    _require(isinstance(value, dict) and set(value) == set(keys), reason)
    return value


def _sha(value, size=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None


def _time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None, "timezone_required")
    return parsed


def _load(raw, expected, label):
    _require(isinstance(raw, bytes) and len(raw) <= 2_000_000 and _sha(expected)
             and digest(raw) == expected, label + "_digest_mismatch")
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReconciliationError("nonfinite_json")))


def prepare_reconciliation(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
                           expected_approval_sha256, now=None):
    """Validate a pinned proposal; supplied approval bytes are not authentication."""
    now = now or _now()
    m = _fields(_load(manifest_bytes, expected_manifest_sha256, "manifest"), {
        "version", "mission_id", "parent_mission_id", "candidate", "generation", "desktop",
        "expected_child_record", "expected_child_sha256", "expected_parent_record", "expected_parent_sha256",
        "expected_correction", "contract", "implementation", "idempotency_key", "expires_at"}, "manifest_fields")
    a = _fields(_load(approval_bytes, expected_approval_sha256, "approval"), {
        "version", "decision", "approval_id", "manifest_sha256", "owner_principal", "desktop_task_id",
        "source", "evidence_ref", "instruction_text", "issued_at", "expires_at"}, "approval_fields")
    _require(m["version"] == a["version"] == VERSION and m["mission_id"] == MISSION_ID
             and m["parent_mission_id"] == PARENT_ID and a["decision"] == DECISION
             and a["manifest_sha256"] == expected_manifest_sha256, "scope_or_approval_mismatch")
    for key in ("approval_id", "owner_principal", "evidence_ref", "instruction_text"):
        _require(isinstance(a[key], str) and a[key].strip() == a[key] and 1 <= len(a[key]) <= 2000,
                 "approval_identity_missing")
    _require(len(a["owner_principal"]) <= 180 and len(a["evidence_ref"]) <= 500, "approval_identity_too_long")
    issued, expires = _time(a["issued_at"]), _time(a["expires_at"])
    _require(issued <= now < expires and expires == _time(m["expires_at"])
             and 0 < (expires - issued).total_seconds() <= 86400, "approval_not_current")
    source = _fields(a["source"], {"kind", "task_id", "request_text", "answer_text",
        "transcript_sha256", "observed_at", "source_message_id"}, "approval_source_fields")
    _require(source["kind"] == "current_conversation_transcript" and source["task_id"] == TASK_ID
             and source["source_message_id"] is None
             and all(isinstance(source[k], str) and source[k].strip() for k in ("request_text", "answer_text"))
             and digest(canonical({k: source[k] for k in ("task_id", "request_text", "answer_text")})) == source["transcript_sha256"]
             and _time(source["observed_at"]) <= issued, "approval_source_invalid")
    d = _fields(m["desktop"], {"task_id", "principal", "transport"}, "desktop_fields")
    _require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", str(d["task_id"]))
             and d["task_id"] == TASK_ID and d["transport"] == "codex_desktop" and d["principal"] == "codex_desktop:" + d["task_id"]
             and a["desktop_task_id"] == d["task_id"], "desktop_identity_invalid")
    for key in ("generation", "idempotency_key"):
        _require(isinstance(m[key], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,159}", m[key]), key + "_invalid")
    c = _fields(m["candidate"], {"pr_number", "branch", "base_sha", "head_sha", "tree_sha", "diff_sha256", "changed_files"}, "candidate_fields")
    _require(type(c["pr_number"]) is int and c["pr_number"] == 1343 and c["branch"] == BRANCH
             and c["base_sha"] == BASE and c["head_sha"] == HEAD and _sha(c["tree_sha"], 40)
             and _sha(c["diff_sha256"]) and c["changed_files"] == PATHS, "candidate_identity_changed")
    implementation = _fields(m["implementation"], {"base_revision", "adapter_sha256", "helper_files"}, "implementation_fields")
    _require(implementation["base_revision"] == BASE and _sha(implementation["adapter_sha256"])
             and set(implementation["helper_files"]) == set(HELPERS)
             and all(_sha(x) for x in implementation["helper_files"].values()), "implementation_pins_invalid")
    for name, mission in (("child", MISSION_ID), ("parent", PARENT_ID)):
        row = m["expected_" + name + "_record"]
        _require(isinstance(row, dict) and row.get("mission_id") == mission and row.get("status") == "in_progress"
                 and isinstance(row.get("metadata_json"), dict)
                 and _sha(m["expected_" + name + "_sha256"])
                 and digest(canonical(row)) == m["expected_" + name + "_sha256"], "expected_" + name + "_record_invalid")
    metadata = m["expected_child_record"]["metadata_json"]
    family, packet, prior_contract, admission = [metadata.get(key) or {} for key in (
        "mission_family", "review_packet", "mission_admission_contract", "mission_admission")]
    _require(all(isinstance(x, dict) for x in (family, packet, prior_contract, admission))
             and family.get("root_mission_id") == PARENT_ID and family.get("generation")
             and family.get("parent_mission_id", PARENT_ID) == PARENT_ID
             and packet.get("pr_number") == 1336 and admission.get("status") == "valid"
             and admission.get("mission_id") == MISSION_ID
             and admission.get("root_mission_id") == family["root_mission_id"]
             and admission.get("generation") == prior_contract.get("generation") == family["generation"]
             and admission.get("head_sha") == packet.get("candidate_revision")
             and admission.get("base_sha") == prior_contract.get("base_sha")
             and isinstance(admission.get("signed_receipt"), dict)
             and m["generation"] != family["generation"], "predecessor_binding_invalid")
    _require(not metadata.get("execution_lease")
             and not any((metadata.get(key) or {}).get("status") == "valid"
                         for key in ("dispatch_authorization", "hermes_native_execution")), "active_execution_conflict")
    correction = _fields(m["expected_correction"], {"event_id", "metadata", "recorded_by"}, "correction_fields")
    _require(correction["metadata"].get("event_id") == correction["event_id"]
             and correction["metadata"].get("mission_id") == MISSION_ID
             and correction["metadata"].get("event_type") == "owner_correction_recorded"
             and correction["metadata"].get("recorded_by") == correction["recorded_by"], "predecessor_correction_invalid")
    contract = _fields(m["contract"], {"generation", "branch", "base_sha", "allowed_files", "forbidden_files",
        "allowed_effects", "forbidden_effects", "required_tests", "operational_acceptance"}, "contract_fields")
    _require(contract["generation"] == m["generation"] and contract["branch"] == BRANCH
             and contract["base_sha"] == BASE and contract["allowed_files"] == PATHS, "contract_identity_changed")
    for key in ("allowed_files", "forbidden_files", "allowed_effects", "forbidden_effects", "required_tests", "operational_acceptance"):
        _require(isinstance(contract[key], list) and contract[key] and len(contract[key]) <= 100
                 and all(isinstance(v, str) and 0 < len(v) <= 2000 for v in contract[key])
                 and len(set(contract[key])) == len(contract[key]), "contract_lists_invalid")
    _require(not set(contract["allowed_effects"]) & set(contract["forbidden_effects"]), "effect_scope_conflict")
    _require(REMOVED_EFFECTS <= set(prior_contract.get("allowed_effects") or [])
             and "cron_deploy" in (prior_contract.get("forbidden_effects") or [])
             and set(contract["allowed_effects"]) == (set(prior_contract["allowed_effects"]) - REMOVED_EFFECTS) | ADDED_EFFECTS
             and set(contract["forbidden_effects"]) == set(prior_contract["forbidden_effects"]) - {"cron_deploy"}
             and set(contract["forbidden_files"]) == set(prior_contract.get("forbidden_files") or [])
             and REQUIRED_TESTS | set(prior_contract.get("required_tests") or []) <= set(contract["required_tests"])
             and REQUIRED_ACCEPTANCE <= set(contract["operational_acceptance"]), "approved_scope_delta_changed")
    return {"manifest": m, "approval": a, "manifest_sha256": expected_manifest_sha256,
            "approval_sha256": expected_approval_sha256,
            "event_id": "OOM-DESKTOP-REBIND-" + expected_manifest_sha256.upper()}


def verify_source_and_candidate(plan):
    """Read only trusted implementation files and inert candidate Git objects."""
    m = plan["manifest"]
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=ROOT)
    _require(git("rev-parse", "origin/main").decode().strip() == BASE, "protected_main_changed")
    _require(set(git("diff", "--name-only", BASE, "--").decode().splitlines()) <= MAINTAINER_PATHS,
             "trusted_checkout_changed")
    _require(set(git("ls-files", "--others", "--exclude-standard").decode().splitlines()) <= MAINTAINER_PATHS,
             "untracked_trusted_dependency")
    _require(digest(Path(__file__).read_bytes()) == m["implementation"]["adapter_sha256"], "adapter_source_changed")
    for path, expected in m["implementation"]["helper_files"].items():
        _require(digest((ROOT / path).read_bytes()) == expected, "helper_source_changed")
    c = m["candidate"]
    _require(git("rev-parse", HEAD + "^{tree}").decode().strip() == c["tree_sha"], "candidate_tree_changed")
    paths = sorted(git("diff", "--name-only", BASE, HEAD, "--").decode().splitlines())
    _require(paths == PATHS, "candidate_paths_changed")
    patch = git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", BASE, HEAD, "--")
    from modules.charlie.mission_admission import canonical_candidate_diff
    _require(canonical_candidate_diff(paths, patch) == c["diff_sha256"], "candidate_diff_changed")


class _BorrowedConnection:
    """Existing helper contexts cannot commit/close the transaction they borrow."""
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def cursor(self):
        return self.connection.cursor()


def _read_record(cursor, mission_id, *, lock=False):
    cursor.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s" +
                   (" for update" if lock else ""), (mission_id,))
    row = cursor.fetchone()
    _require(row and isinstance(row[0], dict), "mission_record_unavailable")
    return row[0]


def _event(cursor, event_id):
    cursor.execute("select metadata_json,recorded_by,event_type from public.charlie_mission_events "
                   "where mission_id=%s and event_id=%s", (MISSION_ID, event_id))
    return cursor.fetchone()


def _latest_correction(cursor):
    cursor.execute("select event_id,metadata_json,recorded_by from public.charlie_mission_events "
                   "where mission_id=%s and event_type='owner_correction_recorded' "
                   "order by created_at desc,event_id desc limit 1", (MISSION_ID,))
    return cursor.fetchone()


def _same_scalar_record(left, right):
    return {k: v for k, v in left.items() if k not in {"metadata_json", "updated_at"}} == {
        k: v for k, v in right.items() if k not in {"metadata_json", "updated_at"}}


def _bindings(plan):
    m = plan["manifest"]
    family = dict(m["expected_child_record"]["metadata_json"]["mission_family"])
    family["generation"] = m["generation"]
    c = m["candidate"]
    return {"review_packet": {"pr_number": 1343, "branch_name": BRANCH, "candidate_revision": HEAD,
                "candidate_tree": c["tree_sha"], "candidate_diff_sha256": c["diff_sha256"], "changed_files": PATHS},
            "mission_admission_contract": m["contract"], "mission_family": family,
            "external_supervisor": m["desktop"],
            "desktop_candidate_reconciliation": {"version": VERSION, "event_id": plan["event_id"],
                "manifest_sha256": plan["manifest_sha256"], "approval_sha256": plan["approval_sha256"]}}


def reconcile_candidate(manifest_bytes, approval_bytes, *, expected_manifest_sha256,
                        expected_approval_sha256, authenticated_owner_principal="",
                        authenticated_desktop_principal="", dry_run=True,
                        database_url=None, connect_factory=None):
    plan = prepare_reconciliation(manifest_bytes, approval_bytes,
        expected_manifest_sha256=expected_manifest_sha256, expected_approval_sha256=expected_approval_sha256)
    if dry_run:
        return {"status": "prepared", "writes": 0, **plan}
    m, a = plan["manifest"], plan["approval"]
    _require(authenticated_owner_principal == a["owner_principal"]
             and authenticated_desktop_principal == m["desktop"]["principal"], "independent_authentication_required")
    _require((isinstance(database_url, str) and database_url.strip()) or callable(connect_factory),
             "explicit_database_connection_required")
    verify_source_and_candidate(plan)
    from modules.charlie import mission_store as store
    from modules.charlie.mission_control import (apply_event_to_projection, validate_mission_control_event,
        build_mission_control_event, canonical_event_equal)
    _require(validate_mission_control_event(m["expected_correction"]["metadata"])[0], "predecessor_correction_invalid")
    proposed = _bindings(plan)
    with store._connect(database_url or "", connect_factory) as connection:
        _require(not getattr(connection, "autocommit", False), "transaction_required")
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='3s'")
            cursor.execute("set local statement_timeout='10s'")
            records = {mid: _read_record(cursor, mid, lock=True) for mid in sorted((MISSION_ID, PARENT_ID))}
            _require(_now() < _time(m["expires_at"]), "approval_expired_under_lock")
            _require(records[PARENT_ID] == m["expected_parent_record"], "parent_state_changed")
            before = records[MISSION_ID]
            recorded = _event(cursor, plan["event_id"])
            if recorded:
                history = recorded[0]
                _require(recorded[1:] == (a["owner_principal"], "workflow_updated")
                         and history.get("manifest_sha256") == plan["manifest_sha256"]
                         and history.get("approval_sha256") == plan["approval_sha256"]
                         and history.get("previous_record") == m["expected_child_record"]
                         and history.get("parent_record") == m["expected_parent_record"]
                         and history.get("manifest") == m and history.get("approval") == a,
                         "replay_history_conflict")
                metadata = before["metadata_json"]
                _require(_same_scalar_record(before, m["expected_child_record"])
                         and all(metadata.get(k) == v for k, v in proposed.items()), "replay_binding_conflict")
                correction = _latest_correction(cursor)
                _require(correction and correction[0] == history["correction"]["event_id"]
                         and correction[1] == history["correction"] and correction[2] == a["owner_principal"],
                         "replay_correction_conflict")
                current = metadata.get("mission_admission") or {}
                _require(current == history["invalidated_admission"] or (
                    all(current.get(k) == v for k, v in {"mission_id": MISSION_ID,
                        "root_mission_id": proposed["mission_family"]["root_mission_id"], "generation": m["generation"],
                        "base_sha": BASE, "head_sha": HEAD}.items()) and isinstance(current.get("signed_receipt"), dict)),
                    "replay_admission_conflict")
                return {"status": "exact_replay", "mission_id": MISSION_ID, "writes": 0}
            _require(before == m["expected_child_record"] and digest(canonical(before)) == m["expected_child_sha256"],
                     "predecessor_state_changed")
            correction = _latest_correction(cursor)
            expected = m["expected_correction"]
            _require(correction == (expected["event_id"], expected["metadata"], expected["recorded_by"]),
                     "predecessor_correction_changed")
            payload = {"event_type": "owner_correction_recorded", "summary": a["instruction_text"],
                "corrects_event_id": expected["event_id"], "idempotency_key": m["idempotency_key"] + ":owner",
                "current_worker": m["desktop"]["principal"],
                "evidence_refs": [a["evidence_ref"], "sha256:" + plan["manifest_sha256"], "sha256:" + plan["approval_sha256"]]}
            result, status = store.invalidate_mission_admission_for_owner_correction(MISSION_ID, m["generation"],
                owner_authentication={"authenticated": True, "principal_type": "owner_admin", "principal_id": a["owner_principal"]},
                correction_payload=payload, connect_factory=lambda _: _BorrowedConnection(connection))
            _require(status < 400 and result.get("status") == "mission_admission_invalidated", "owner_invalidation_failed")
            intermediate = _read_record(cursor, MISSION_ID)
            invalidated = result["admission"]
            _require(_same_scalar_record(before, intermediate)
                     and intermediate["metadata_json"] == {**before["metadata_json"], "mission_admission": invalidated},
                     "invalidation_readback_mismatch")
            correction = _latest_correction(cursor)
            _require(correction and correction[0] == result["correction_event_id"]
                     and correction[2] == a["owner_principal"]
                     and canonical_event_equal(correction[1], build_mission_control_event(
                         MISSION_ID, payload, recorded_by=a["owner_principal"])), "correction_readback_mismatch")
            updated = {**intermediate["metadata_json"], **proposed}
            updated["mission_control_projection"] = apply_event_to_projection(
                {**before, "metadata": updated}, correction[1])
            history = {"version": VERSION, "manifest": m, "approval": a,
                "manifest_sha256": plan["manifest_sha256"], "approval_sha256": plan["approval_sha256"],
                "previous_record": before, "parent_record": records[PARENT_ID], "correction": correction[1],
                "invalidated_admission": invalidated, "bindings": proposed}
            cursor.execute("update public.charlie_missions m set metadata_json=%s::jsonb,updated_at=now() "
                           "where mission_id=%s and to_jsonb(m)=%s::jsonb returning mission_id",
                           (canonical(updated).decode(), MISSION_ID, canonical(intermediate).decode()))
            _require(cursor.fetchone() == (MISSION_ID,), "conditional_binding_lost")
            cursor.execute("insert into public.charlie_mission_events "
                "(event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at) "
                "values(%s,%s,'workflow_updated',%s,%s,%s::jsonb,now())",
                (plan["event_id"], MISSION_ID, "Owner-approved exact Desktop PR1343 candidate reconciliation.",
                 a["owner_principal"], canonical(history).decode()))
            after = _read_record(cursor, MISSION_ID)
            _require(_same_scalar_record(before, after) and after["metadata_json"] == updated
                     and _read_record(cursor, PARENT_ID) == records[PARENT_ID]
                     and _event(cursor, plan["event_id"]) == (history, a["owner_principal"], "workflow_updated")
                     and _latest_correction(cursor) == correction, "final_readback_mismatch")
    return {"status": "candidate_reconciled", "mission_id": MISSION_ID, "pr_number": 1343,
            "head_sha": HEAD, "writes": 5, "admission_issued": False, "release_performed": False}


def main():
    parser = argparse.ArgumentParser(description="Prepare only; never applies a canonical mutation.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--approval-sha256", required=True)
    args = parser.parse_args()
    plan = prepare_reconciliation(Path(args.manifest).read_bytes(), Path(args.approval).read_bytes(),
        expected_manifest_sha256=args.manifest_sha256, expected_approval_sha256=args.approval_sha256)
    verify_source_and_candidate(plan)
    print(json.dumps({"status": "prepared", "writes": 0, "mission_id": MISSION_ID,
                      "manifest_sha256": plan["manifest_sha256"]}))


if __name__ == "__main__":
    main()
