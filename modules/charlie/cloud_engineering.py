"""One explicit cloud engineering grant on the canonical mission/event rails.

This opt-in boundary cannot publish, merge, deploy, message, or touch farm data.
The existing receipt-only grant and legacy Cursor commissioning stay separate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import ast
import hmac
import json
import os
import re
import uuid

from modules.charlie import mission_store
from modules.charlie.cloud_intake import hosted_connection
from modules.charlie.manager_dependency_intake import _open

CONTRACT = "core.cloud_engineering.v1"
KEY = "cloud_engineering_execution"
WORKER = "srv-dacofeoae00c73813eug"
API = "srv-d6sijjkhg0os73f7regg"
MAX_CALLS = 8
CALL_RESERVATION_MICRO_USD = 100000
MAX_BUDGET_MICRO_USD = MAX_CALLS * CALL_RESERVATION_MICRO_USD
TERMINAL = {"artifact_ready", "blocked", "revoked"}
STAGES = {"claimed", "baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"}
FORBIDDEN = ("farm_write", "hardware", "messages", "git_push", "pull_request", "merge", "deploy")


class EngineeringRefused(ValueError):
    pass


def need(value, reason):
    if not value:
        raise EngineeringRefused(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def sha(value, length=64):
    need(isinstance(value, str) and re.fullmatch("[a-f0-9]{%d}" % length, value), "invalid_digest")
    return value


def moment(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    need(parsed.utcoffset() is not None, "aware_time_required")
    return parsed


def owner_binding():
    secret = os.environ.get("OWNER_ADMIN_TOKEN", "")
    need(len(secret) >= 32, "owner_binding_unavailable")
    return hashlib.sha256(secret.encode()).hexdigest()


def mission_binding(row):
    metadata = row.get("metadata_json") or {}
    return digest({key: row.get(key) for key in ("mission_id", "status", "raw_text", "title", "source", "latest_owner_correction")}
                  | {"metadata": {key: value for key, value in metadata.items()
                                  if key not in {KEY, "execution_lease"}}})


ACCEPTANCE_PATH = "tests/test_core_immutable_acceptance.py"


def expected_tests(source):
    try:
        tree = ast.parse(source)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise EngineeringRefused("acceptance_syntax") from exc
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    need(0 < len(names) <= 30 and len(names) == len(set(names)), "acceptance_test_ids")
    return [ACCEPTANCE_PATH + "::" + name for name in names]


def validate_test_receipt(receipt, manifest, *, baseline):
    need(isinstance(receipt, dict), "test_receipt_required")
    code = 1 if baseline else 0
    need(type(receipt.get("returncode")) is int and receipt["returncode"] == code, "test_evidence")
    need((receipt.get("containment") or {}).get("verified") is True, "sandbox_evidence")
    completion = receipt.get("completion") or {}
    required = expected_tests(manifest["acceptance_source"])
    need(completion.get("verified") is True and completion.get("completed") is True and
         type(completion.get("exitstatus")) is int and completion["exitstatus"] == code and
         type(completion.get("collection_errors")) is int and completion["collection_errors"] == 0,
         "test_completion_required")
    collected = completion.get("collected")
    outcomes = completion.get("outcomes")
    paths = [ACCEPTANCE_PATH] if baseline else [*manifest["test_paths"], ACCEPTANCE_PATH]
    need(isinstance(collected, list) and 0 < len(collected) <= 2000 and
         all(isinstance(item, str) and any(item.startswith(path + "::") for path in paths)
             for item in collected) and len(collected) == len(set(collected)) and
         set(required).issubset(collected) and completion.get("expected_test_ids") == required and
         isinstance(outcomes, dict) and set(outcomes) == set(collected), "test_collection_binding")
    if baseline:
        need(any(outcomes.get(item, {}).get("call") == "failed" for item in required),
             "baseline_assertion_failure_required")
    else:
        need(completion.get("expected_passed") is True and completion.get("all_passed") is True and
             all(phases == {"setup": "passed", "call": "passed", "teardown": "passed"}
                 for phases in outcomes.values()), "tests_not_all_passed")


def validate_manifest(value):
    required = {"generation", "base_sha", "worker_revision", "api_revision", "allowed_files",
                "test_paths", "context_paths", "instruction", "acceptance_source",
                "acceptance_sha256", "budget_micro_usd", "max_seconds"}
    need(isinstance(value, dict) and set(value) == required, "manifest_shape")
    m = deepcopy(value)
    sha(m["generation"], 32)
    for key in ("base_sha", "worker_revision", "api_revision"):
        sha(m[key], 40)
    need(m["base_sha"] == m["worker_revision"] == m["api_revision"], "revision_binding")
    need(type(m["max_seconds"]) is int and 300 <= m["max_seconds"] <= 3600, "duration_bound")
    need(type(m["budget_micro_usd"]) is int and
         CALL_RESERVATION_MICRO_USD <= m["budget_micro_usd"] <= MAX_BUDGET_MICRO_USD, "budget_bound")
    from modules.charlie.native_runner.execution import normalize_repo_path
    for field, maximum in (("allowed_files", 4), ("test_paths", 6), ("context_paths", 20)):
        rows = m[field]
        need(isinstance(rows, list) and 0 < len(rows) <= maximum and len(rows) == len(set(rows)),
             "path_list_bound")
        for path in rows:
            need(normalize_repo_path(path) == path and
                 not any(part.startswith(".") for part in path.split("/")), "path_invalid")
            need(path.startswith(("modules/pig_weights/", "tests/", "docs/09-vault-brain/")) or
                 (field == "context_paths" and path in {
                     "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
                     "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md"}),
                 "path_scope")
    need(all(path.endswith(".py") and path.startswith(("modules/pig_weights/", "tests/"))
             for path in m["allowed_files"]), "edit_scope")
    need(all(path.startswith("tests/test_") and path.endswith(".py") for path in m["test_paths"]),
         "test_scope")
    need(set(m["allowed_files"]).issubset(m["context_paths"]), "context_scope")
    need(isinstance(m["instruction"], str) and 0 < len(m["instruction"]) <= 12000, "instruction_bound")
    need(isinstance(m["acceptance_source"], str) and
         0 < len(m["acceptance_source"].encode()) <= 24000, "acceptance_bound")
    need(hashlib.sha256(m["acceptance_source"].encode()).hexdigest() == sha(m["acceptance_sha256"]),
         "acceptance_changed")
    expected_tests(m["acceptance_source"])
    need(ACCEPTANCE_PATH not in m["allowed_files"] and ACCEPTANCE_PATH not in m["test_paths"] and
         ACCEPTANCE_PATH not in m["context_paths"], "acceptance_path_reserved")
    return m


def validate_active(row, grant, now, *, api_revision, binding):
    need(grant.get("contract") == CONTRACT, "grant_missing")
    need(grant["state"] not in TERMINAL, "grant_inactive")
    need(now < moment(grant["expires_at"]), "grant_expired")
    need(grant["owner_binding"] == binding, "owner_changed")
    need(grant["mission_binding"] == mission_binding(row), "mission_changed")
    need(row["status"] == "paused", "mission_not_paused")
    need(grant["manifest"]["api_revision"] == api_revision, "api_revision_changed")


def transition(grant, operation, payload, *, now):
    """Pure bounded state transition. Persistence is transactional below."""
    value = deepcopy(grant)
    need(isinstance(payload, dict), "payload_mapping")
    if operation == "claim":
        need(set(payload) == {"instance", "worker_revision", "worker_service"}, "claim_shape")
        sha(payload["instance"], 32)
        need(payload["worker_service"] == WORKER and
             payload["worker_revision"] == value["manifest"]["worker_revision"], "worker_binding")
        need(value["state"] == "issued" and not value.get("instance"), "claim_already_consumed")
        value.update(state="claimed", instance=payload["instance"], claimed_at=now.isoformat())
    else:
        need(payload.get("instance") == value.get("instance") and bool(value.get("instance")),
             "instance_mismatch")
        if operation == "check":
            need(set(payload) == {"instance"}, "check_shape")
            return value
        if operation == "reserve":
            need(set(payload) == {"instance", "request_id", "request_sha256", "input_bytes",
                                  "max_tokens", "task"}, "reservation_shape")
            sha(payload["request_id"], 32)
            sha(payload["request_sha256"])
            need(type(payload["input_bytes"]) is int and 0 < payload["input_bytes"] <= 340000,
                 "model_input_bound")
            need(type(payload["max_tokens"]) is int and 1 <= payload["max_tokens"] <= 6000,
                 "model_output_bound")
            need(payload["task"] in {"charlie_native_builder", "charlie_native_security_reviewer",
                                     "charlie_native_functional_reviewer"}, "model_role")
            calls = list(value.get("reservations") or [])
            need(not any(item["request_id"] == payload["request_id"] for item in calls),
                 "reservation_already_consumed")
            spent = value.get("reserved_micro_usd", 0)
            need(len(calls) < MAX_CALLS and spent + CALL_RESERVATION_MICRO_USD <=
                 value["manifest"]["budget_micro_usd"], "model_budget_exhausted")
            calls.append({**payload, "reserved_at": now.isoformat(),
                          "reserved_micro_usd": CALL_RESERVATION_MICRO_USD})
            value.update(reservations=calls, reserved_micro_usd=spent + CALL_RESERVATION_MICRO_USD)
        elif operation == "progress":
            need(set(payload) == {"instance", "stage", "artifact_sha256"}, "progress_shape")
            need(payload["stage"] in STAGES, "stage_invalid")
            order = ["claimed", "baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"]
            need(order.index(payload["stage"]) == order.index(value["state"]) + 1, "stage_order")
            sha(payload["artifact_sha256"])
            value.update(state=payload["stage"], stage_artifact_sha256=payload["artifact_sha256"])
        elif operation == "complete":
            need(set(payload) == {"instance", "artifact", "artifact_sha256"}, "completion_shape")
            need(value["state"] == "reviews_passed", "reviews_required")
            artifact = payload["artifact"]
            need(isinstance(artifact, dict) and len(encoded(artifact).encode()) <= 350000, "artifact_bound")
            need(digest(artifact) == sha(payload["artifact_sha256"]), "artifact_digest")
            need(artifact.get("contract") == CONTRACT and artifact.get("generation") ==
                 value["manifest"]["generation"], "artifact_identity")
            need(artifact.get("base_sha") == value["manifest"]["base_sha"], "artifact_base")
            need(type(artifact.get("tests", {}).get("returncode")) is int and
                 type(artifact.get("baseline", {}).get("returncode")) is int and
                 artifact["tests"]["returncode"] == 0 and artifact["baseline"]["returncode"] == 1,
                 "test_evidence")
            need(artifact.get("mission_id") == value["mission_id"] and artifact.get("instance") ==
                 value["instance"] and artifact.get("worker_revision") == value["manifest"]["worker_revision"],
                 "artifact_worker_identity")
            candidate = artifact.get("candidate") or {}
            binding = artifact.get("candidate_binding") or {}
            need(candidate.get("changed_files") == sorted(value["manifest"]["allowed_files"]) and
                 binding.get("changed_files") == candidate["changed_files"], "artifact_scope")
            need(isinstance(candidate.get("diff"), str) and candidate["diff"].strip() and
                 str(candidate.get("builder_identity", "")).startswith("HNW-"), "artifact_authorship")
            patch = artifact.get("candidate_diff")
            need(isinstance(patch, str) and patch.strip() and candidate.get("diff") == patch and
                 hashlib.sha256(patch.encode()).hexdigest() == binding.get("candidate_diff_sha256"),
                 "artifact_patch_binding")
            need(binding.get("base_sha") == artifact["base_sha"] and binding.get("pr_number") == 0 and
                 binding.get("head_sha") == artifact["base_sha"], "private_candidate_binding")
            need(artifact.get("acceptance_sha256") == value["manifest"]["acceptance_sha256"],
                 "immutable_acceptance_binding")
            need(all((artifact.get(k, {}).get("containment") or {}).get("verified") is True for k in ("tests", "baseline")),
                 "sandbox_evidence")
            need(all(artifact.get(k) == 0 for k in ("publications", "farm_actions", "messages", "deployments")),
                 "artifact_forbidden_effect")
            need(artifact.get("model_reservations") == value["reservations"] and
                 artifact.get("reserved_micro_usd") == value["reserved_micro_usd"], "reservation_binding")
            validate_test_receipt(artifact.get("baseline"), value["manifest"], baseline=True)
            validate_test_receipt(artifact.get("tests"), value["manifest"], baseline=False)
            calls = artifact.get("model_calls")
            need(isinstance(calls, list) and 3 <= len(calls) <= MAX_CALLS and
                 len(calls) == len(value["reservations"]), "model_call_evidence")
            requests = {item["request_sha256"]: item for item in value["reservations"]}
            need(len(requests) == len(calls) and {call.get("request_sha256") for call in calls} ==
                 set(requests), "model_reservation_evidence")
            for call in calls:
                reservation = requests[call["request_sha256"]]
                need(call.get("strict_budget") is True and call.get("attempt_count") == 1 and
                     call.get("tools_count") == 0 and all(call.get(key) == reservation[key]
                     for key in ("input_bytes", "max_tokens", "task")), "model_call_binding")
                need(isinstance(call.get("provider_request_id"), str) and
                     re.fullmatch("[A-Za-z0-9._:-]{1,200}", call["provider_request_id"]),
                     "provider_request_evidence")
            need({"charlie_native_builder", "charlie_native_security_reviewer",
                  "charlie_native_functional_reviewer"}.issubset({call["task"] for call in calls}),
                 "independent_model_roles")
            need(len({call["provider_request_id"] for call in calls}) == len(calls) and
                 all(isinstance(call.get("invocation_id"), str) and
                     re.fullmatch("native-[a-f0-9]{32}", call["invocation_id"]) for call in calls) and
                 len({call["invocation_id"] for call in calls}) == len(calls),
                 "model_invocation_independence")
            final_calls = {call["task"]: call for call in calls}
            need(candidate.get("builder_agent_id") ==
                 final_calls["charlie_native_builder"]["provider_request_id"], "builder_call_binding")
            reviews = artifact.get("reviews", [])
            need(all(r.get("candidate_binding") == binding and
                     str(r.get("reviewer_identity", "")).startswith("HNR-") and
                     r.get("reviewer_provider") == "openrouter" and
                     r.get("reviewer_model") == "openai/gpt-5-mini" and
                     r.get("reviewer_task") == "charlie_native_" + str(r.get("role", "")).lower() + "_reviewer" and
                     r.get("reviewer_agent_id") == final_calls.get(r.get("reviewer_task"), {}).get("provider_request_id")
                     for r in reviews),
                 "review_candidate_binding")
            need(len({r.get("reviewer_identity") for r in reviews}) == 2, "reviewer_independence")
            need(len(reviews) == 2 and {r.get("role") for r in reviews} == {"SECURITY", "FUNCTIONAL"}
                 and all(r.get("verdict") == "APPROVE" for r in reviews), "review_evidence")
            value.update(state="artifact_ready", artifact=artifact,
                         artifact_sha256=payload["artifact_sha256"], completed_at=now.isoformat())
        elif operation == "block":
            need(set(payload) == {"instance", "reason"}, "block_shape")
            need(isinstance(payload["reason"], str) and re.fullmatch("[a-z0-9_]{1,100}", payload["reason"]),
                 "block_reason")
            value.update(state="blocked", reason=payload["reason"])
        else:
            raise EngineeringRefused("operation_invalid")
    return value


def _connection(database_url=None, connect_factory=None):
    import time
    need(os.environ.get("CORE_CLOUD_ENGINEERING_ENABLED") == "true", "engineering_disabled")
    need(os.environ.get("RENDER_SERVICE_ID") == API, "api_service_mismatch")
    return _open(mission_store._database_url(database_url), connect_factory or hosted_connection,
                 time.monotonic() + 10)


def _row(cur, mission_id):
    need(isinstance(mission_id, str) and re.fullmatch("[A-Za-z0-9_-]{1,90}", mission_id),
         "mission_identity")
    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (CONTRACT,))
    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (mission_id,))
    cur.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s for update",
                (mission_id,))
    rows = cur.fetchmany(2)
    need(len(rows) == 1, "mission_missing")
    cur.execute("select clock_timestamp()")
    now = cur.fetchone()[0]
    row = rows[0][0]
    cur.execute("""select to_jsonb(e) from public.charlie_mission_events e
        where mission_id=%s and event_type='owner_correction_recorded'
        order by created_at desc,event_id desc limit 1""", (mission_id,))
    correction = cur.fetchone()
    row["latest_owner_correction"] = correction[0] if correction else None
    grant = (row.get("metadata_json") or {}).get(KEY)
    if grant:
        cur.execute("""select created_at from public.charlie_mission_events
            where mission_id=%s and metadata_json->>'contract'=%s
              and metadata_json->>'operation'='revoke' and metadata_json->>'generation'=%s
            order by created_at desc limit 1""", (mission_id, CONTRACT, grant["manifest"]["generation"]))
        revoked = cur.fetchone()
        if revoked:
            row["metadata_json"][KEY] = dict(grant, prior_state=grant["state"], state="revoked",
                                             revoked_at=revoked[0].isoformat())
    return row, now


def _holds(cur, mission_id):
    hold, code = mission_store.owner_execution_hold_status(mission_id, cursor=cur)
    need(code == 200 and hold.get("active") is False, "mission_held_or_unknown")


def _collision(cur, mission_id):
    cur.execute("""select mission_id from public.charlie_missions
        where (
          (mission_id<>%s and metadata_json->'cloud_engineering_execution'->>'state' in
              ('issued','claimed','baseline_verified','candidate_prepared','tests_passed','reviews_passed')
           and (metadata_json->'cloud_engineering_execution'->>'expires_at')::timestamptz>clock_timestamp()
           and not exists (select 1 from public.charlie_mission_events e
               where e.mission_id=charlie_missions.mission_id and e.metadata_json->>'contract'='core.cloud_engineering.v1'
                 and e.metadata_json->>'operation'='revoke'
                 and e.metadata_json->>'generation'=charlie_missions.metadata_json->'cloud_engineering_execution'->'manifest'->>'generation'))
          or (metadata_json->'execution_lease'->>'expires_at')::timestamptz>clock_timestamp()
          or (metadata_json->'hermes_native_execution'->>'claim_expires_at')::timestamptz>clock_timestamp()
        ) limit 1""", (mission_id,))
    need(cur.fetchone() is None, "competing_writer")
    cur.execute("""select policy_id from public.charlie_delegation_policies
        where policy_id=%s and enabled is true limit 1""", ("core.manager_dependency_intake.20261010",))
    need(cur.fetchone() is None, "receipt_grant_active")


def _save(cur, row, grant, operation, actor, now, *, update=True):
    metadata = dict(row.get("metadata_json") or {})
    metadata[KEY] = grant
    event = {"contract": CONTRACT, "operation": operation, "generation": grant["manifest"]["generation"],
             "state": grant["state"], "grant_sha256": digest(grant), "actor": actor,
             "at": now.isoformat()}
    if update:
        cur.execute("""update public.charlie_missions set metadata_json=%s::jsonb,updated_at=%s
            where mission_id=%s""", (encoded(metadata), now, row["mission_id"]))
    cur.execute("""insert into public.charlie_mission_events
        (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
        values (%s,%s,'review_note',%s,%s,%s::jsonb,%s)""",
        ("CORE-ENGINEERING-" + uuid.uuid4().hex, row["mission_id"],
         "Bounded private cloud engineering: " + operation, actor, encoded(event), now))


def _public(grant, *, owner=False):
    out = {key: value for key, value in grant.items() if key not in {"token_sha256", "owner_binding"}}
    if not owner:
        out.pop("mission_binding", None)
    return {"success": True, "contract": CONTRACT, "grant": out}


def authorize(mission_id, payload, *, actor, database_url=None, connect_factory=None):
    need(isinstance(actor, str) and actor.startswith("owner-admin:"), "owner_required")
    need(isinstance(payload, dict) and set(payload) == {"manifest", "token_sha256", "expected_mission_sha256"},
         "authorization_shape")
    manifest = validate_manifest(payload["manifest"])
    sha(payload["token_sha256"]); sha(payload["expected_mission_sha256"])
    with _connection(database_url, connect_factory) as db:
        with db.cursor() as cur:
            row, now = _row(cur, mission_id)
            _holds(cur, mission_id); _collision(cur, mission_id)
            need(row["status"] == "paused", "paused_mission_required")
            need(KEY not in (row.get("metadata_json") or {}), "fresh_mission_required")
            need(mission_binding(row) == payload["expected_mission_sha256"], "mission_preimage_changed")
            need(os.environ.get("RENDER_GIT_COMMIT") == manifest["api_revision"], "api_revision_mismatch")
            grant = {"contract": CONTRACT, "manifest": manifest, "state": "issued",
                     "mission_id": mission_id, "mission_binding": mission_binding(row),
                     "owner_binding": owner_binding(), "owner_principal": actor,
                     "token_sha256": payload["token_sha256"], "issued_at": now.isoformat(),
                     "expires_at": (now + timedelta(seconds=manifest["max_seconds"])).isoformat(),
                     "reservations": [], "reserved_micro_usd": 0, "instance": ""}
            _save(cur, row, grant, "authorize", actor, now)
    return _public(grant, owner=True)


def owner_read(mission_id, *, database_url=None, connect_factory=None):
    with _connection(database_url, connect_factory) as db:
        with db.cursor() as cur:
            row, now = _row(cur, mission_id)
            grant = (row.get("metadata_json") or {}).get(KEY)
            if grant:
                return _public(grant, owner=True)
            return {"success": True, "contract": CONTRACT, "mission_id": mission_id,
                    "mission_sha256": mission_binding(row), "state": "not_admitted"}


def revoke(mission_id, *, actor, database_url=None, connect_factory=None):
    need(isinstance(actor, str) and actor.startswith("owner-admin:"), "owner_required")
    with _connection(database_url, connect_factory) as db:
        with db.cursor() as cur:
            row, now = _row(cur, mission_id)
            grant = deepcopy((row.get("metadata_json") or {}).get(KEY))
            need(grant and grant.get("contract") == CONTRACT, "grant_missing")
            if grant["state"] != "revoked":
                grant.update(prior_state=grant["state"], state="revoked", revoked_at=now.isoformat())
                _save(cur, row, grant, "revoke", actor, now, update=False)
    return _public(grant, owner=True)


def worker_operation(mission_id, operation, payload, token, *, database_url=None, connect_factory=None):
    need(isinstance(token, str) and re.fullmatch("[A-Za-z0-9_-]{43,128}", token), "credential_invalid")
    with _connection(database_url, connect_factory) as db:
        with db.cursor() as cur:
            row, now = _row(cur, mission_id)
            grant = (row.get("metadata_json") or {}).get(KEY)
            need(grant and hmac.compare_digest(grant["token_sha256"], hashlib.sha256(token.encode()).hexdigest()),
                 "credential_mismatch")
            # A terminal state read is inert; it cannot replay admission or a model reservation.
            if operation == "current":
                need(payload == {}, "current_shape")
                return _public(grant)
            _holds(cur, mission_id); _collision(cur, mission_id)
            validate_active(row, grant, now, api_revision=os.environ.get("RENDER_GIT_COMMIT"),
                            binding=owner_binding())
            updated = transition(grant, operation, payload, now=now)
            if operation != "check":
                _save(cur, row, updated, operation, "core-cloud:" + updated.get("instance", ""), now)
    return _public(updated)
