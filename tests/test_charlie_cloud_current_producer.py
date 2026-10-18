"""Exact current cloud producer compatibility; real manager/receipt PostgreSQL paths.

Original anchors and packet identities remain frozen. Only latest evidence may
use the owner-bound current API revision. All records are synthetic per-test
schemas; no provider, real owner, credentials or production database is used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os

import pytest

from modules.charlie import cloud_intake as cloud
from modules.charlie import manager_dependency_intake as intake
from modules.oom_sakkie import general_manager_worker as manager
from tests.test_charlie_manager_dependency_intake_postgres import dbcase, snapshot, consume, REVISION as ORIGINAL
from tests.test_charlie_cloud_intake_postgres import h, proposal, prepare, packet, policy_row, failed_partial_epoch, recovery_proposal
from tests.test_charlie_cloud_intake import TOKEN, REVISION as CURRENT

pytestmark = pytest.mark.skipif(not os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL"),
                                reason="explicit isolated PostgreSQL required")
STALE = "c" * 40
SUCCESSOR = "e" * 40


def produce_latest(h, revision):
    """Use the actual manager producer, with only synthetic scheduling made due."""
    with h.db() as db:
        original = db.execute("select to_jsonb(e) from app_private.oom_manager_case_events e "
            "where event_id=any(%s) order by event_id", ([d["anchor_event_id"] for d in h.deps],)).fetchall()
        db.execute("update app_private.oom_manager_cases set next_reassessment_at=now()-interval '1 second'")
    def _herdmaster(now): return []
    produced = manager.run_general_manager_cycle(now=datetime.now(timezone.utc), source_revision=revision,
        store=h.store, collectors=(_herdmaster,), deliver=lambda *a, **kw: pytest.fail("no delivery allowed"))
    assert produced["reconciliation_pending"] == 2 and produced["exceptions"] == 0, produced
    with h.db() as db:
        assert db.execute("select to_jsonb(e) from app_private.oom_manager_case_events e "
            "where event_id=any(%s) order by event_id", ([d["anchor_event_id"] for d in h.deps],)).fetchall() == original
        rows = db.execute("select to_jsonb(e),to_jsonb(c) from app_private.oom_manager_case_events e "
            "join app_private.oom_manager_worker_cycles c on c.cycle_id=e.event_payload->>'cycle_id' "
            "where e.event_type='delivery_suppressed' and e.event_payload ? 'technical_dependency' "
            "order by e.occurred_at desc,e.event_id desc limit 2").fetchall()
    assert len(rows) == 2 and all(c["source_revision"] == revision for e, c in rows)
    assert all(e["event_id"] not in {d["anchor_event_id"] for d in h.deps} for e, c in rows)
    return rows


@pytest.mark.parametrize("revision", [ORIGINAL, CURRENT])
def test_original_or_current_latest_preserves_scope_packets_and_exact_replay(h, monkeypatch, revision):
    old = policy_row(h); scope = deepcopy(old["scope_json"])
    packets = [intake._packets(old, scope, dep) for dep in scope["dependencies"]]
    produce_latest(h, revision)
    ready_before = snapshot(h)
    admitted = prepare(h)
    first = h.cloud(cloud.cycle, packet(admitted), TOKEN)
    assert first["success"] is True, first
    actual = policy_row(h)
    assert actual["scope_json"] == scope
    replay_packets = [intake._packets(actual, scope, dep) for dep in scope["dependencies"]]
    for before_packet, after_packet in zip(packets, replay_packets):
        assert before_packet[:2] == after_packet[:2] and before_packet[3:] == after_packet[3:]
        assert intake.canonical_event_equal(before_packet[2], after_packet[2])
    after = snapshot(h)
    assert after["cases"] == ready_before["cases"]
    assert all(row in after["manager_events"] for row in ready_before["manager_events"])
    assert h.cloud(cloud.cycle, packet(admitted), TOKEN) == first
    assert snapshot(h) == after
    monkeypatch.setattr(cloud, "POLL_SECONDS", 0)
    later = h.cloud(cloud.cycle, packet(admitted, request_id="3"*32), TOKEN)
    assert later["success"] and all(r["status"] == "intake_exact_replay" for r in later["intake"]["results"])
    assert snapshot(h)["commands"] == after["commands"]
    assert all(r["counts"] == [1, 1, 1] and r["verified"] for r in h.cloud(cloud.readiness)["receipts"])


@pytest.mark.parametrize("revision", [CURRENT, STALE])
def test_original_anchor_never_uses_current_override(h, revision):
    produce_latest(h, CURRENT)
    with h.db() as db:
        db.execute("update app_private.oom_manager_worker_cycles set source_revision=%s where cycle_id=any(%s)",
                   (revision, [d["anchor_cycle_id"] for d in h.deps]))
    before = snapshot(h); policy = policy_row(h)
    with pytest.raises(intake.IntakeRefused, match="pending_cycle_unproven"):
        h.cloud(cloud.readiness)
    assert snapshot(h) == before and policy_row(h) == policy


@pytest.mark.parametrize("revision", [STALE, "f"*40, "unknown"])
def test_unrelated_or_previous_cloud_latest_remains_refused(h, revision):
    produce_latest(h, revision)
    before = snapshot(h); policy = policy_row(h)
    with pytest.raises(intake.IntakeRefused, match="pending_cycle_unproven"):
        h.cloud(cloud.readiness)
    assert snapshot(h) == before and policy_row(h) == policy


@pytest.mark.parametrize("key,value", [("RENDER_GIT_COMMIT", ""), ("RENDER_GIT_COMMIT", "bad"),
                                       ("RENDER_SERVICE_ID", cloud.WORKER_SERVICE)])
def test_readiness_requires_exact_current_api_identity(h, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    before = snapshot(h)
    with pytest.raises(cloud.CloudIntakeRefused): h.cloud(cloud.readiness)
    assert snapshot(h) == before


def test_create_validates_provider_before_accepting_latest(h):
    produce_latest(h, CURRENT)
    p = proposal(h); p["provider"]["api_revision"] = STALE
    before = snapshot(h); policy = policy_row(h)
    with pytest.raises(cloud.CloudIntakeRefused, match="hosted_api_identity_mismatch"):
        h.cloud(cloud.create_epoch, p, actor="owner-admin:synthetic")
    assert snapshot(h) == before and policy_row(h) == policy


def test_enable_refuses_stale_bound_provider_after_api_change(h, monkeypatch):
    produce_latest(h, CURRENT)
    admitted = h.cloud(cloud.create_epoch, proposal(h), actor="owner-admin:synthetic")
    monkeypatch.setenv("RENDER_GIT_COMMIT", SUCCESSOR)
    before = snapshot(h); policy = policy_row(h)
    with pytest.raises(cloud.CloudIntakeRefused, match="hosted_api_identity_mismatch"):
        h.cloud(cloud.set_enabled, admitted["epoch"]["epoch_id"], {"policy_sha256": admitted["policy_sha256"]},
                enabled=True, actor="owner-admin:synthetic")
    assert snapshot(h) == before and policy_row(h) == policy


@pytest.mark.parametrize("drift", ["revision", "service", "stored_provider"])
def test_inner_receipt_transaction_rejects_identity_or_context_change(h, monkeypatch, drift):
    produce_latest(h, CURRENT); admitted = prepare(h)
    real = intake.consume_manager_dependencies
    def changed(**kw):
        if drift == "stored_provider":
            with h.db() as db:
                db.execute("update public.charlie_delegation_policies set metadata_json="
                    "jsonb_set(metadata_json,'{cloud_receipt_epoch,provider,api_revision}',%s::jsonb)",
                    (json.dumps(STALE),))
        else: monkeypatch.setenv("RENDER_GIT_COMMIT" if drift == "revision" else "RENDER_SERVICE_ID",
                                STALE if drift == "revision" else cloud.WORKER_SERVICE)
        result = real(**kw)
        if drift != "stored_provider":
            monkeypatch.setenv("RENDER_GIT_COMMIT", CURRENT); monkeypatch.setenv("RENDER_SERVICE_ID", cloud.API_SERVICE)
        return result
    monkeypatch.setattr(intake, "consume_manager_dependencies", changed)
    if drift == "stored_provider":
        with pytest.raises(cloud.CloudIntakeRefused, match="hosted_api_identity_mismatch"):
            h.cloud(cloud.cycle, packet(admitted), TOKEN)
    else:
        result = h.cloud(cloud.cycle, packet(admitted), TOKEN)
        assert result["success"] is False
    assert not snapshot(h)["commands"]
    assert not [r for r in snapshot(h)["findings"] if r[0]["event_type"] == "finding_recorded"]


def test_loaded_identity_change_between_committed_pair_and_link_refuses_link(h, monkeypatch):
    produce_latest(h, CURRENT); admitted = prepare(h)
    real_locked = intake._locked_inputs; real_consume = intake.consume_manager_dependencies; calls = []
    def changed(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: monkeypatch.setenv("RENDER_GIT_COMMIT", STALE)
        return real_locked(*args, **kwargs)
    def restore(**kw):
        try: return real_consume(**kw)
        finally: monkeypatch.setenv("RENDER_GIT_COMMIT", CURRENT)
    monkeypatch.setattr(intake, "_locked_inputs", changed)
    monkeypatch.setattr(intake, "consume_manager_dependencies", restore)
    result = h.cloud(cloud.cycle, packet(admitted), TOKEN)
    assert not result["success"] and result["intake"]["failures"] == 2
    assert all(r["reason"] == "cloud_api_identity_changed" for r in result["intake"]["results"])
    readback = h.cloud(cloud.evidence, admitted["epoch"]["epoch_id"])
    assert [r["counts"] for r in readback["receipts"]] == [[1, 1, 0], [0, 0, 0]]


def test_inner_context_does_not_reapply_commissioning_freshness_limit(h):
    produce_latest(h, CURRENT); admitted = prepare(h)
    with h.db() as db:
        db.execute("update public.charlie_delegation_policies set metadata_json="
            "jsonb_set(metadata_json,'{cloud_receipt_epoch,provider,observed_at}',to_jsonb(now()-interval '11 minutes'))")
    result = h.cloud(cloud.cycle, packet(admitted), TOKEN)
    assert result["success"] is True, result


def test_ordinary_consumer_stays_original_producer_only(dbcase):
    h = dbcase
    before = snapshot(h)
    assert consume(h)["failures"] == 0
    produce_latest(h, CURRENT)
    stable = snapshot(h)
    result = consume(h)
    assert result["failures"] == 2 and all(r["reason"] == "pending_cycle_unproven" for r in result["results"])
    assert snapshot(h) == stable
    assert before["cases"][0][0]["evidence_refs"] == stable["cases"][0][0]["evidence_refs"]


def test_revoked_old_epoch_does_not_authorize_latest_but_new_recovery_preserves_pair(h, monkeypatch):
    failed = failed_partial_epoch(h, monkeypatch)
    prior = policy_row(h)
    monkeypatch.setenv("RENDER_GIT_COMMIT", SUCCESSOR)
    produce_latest(h, CURRENT)
    with pytest.raises(intake.IntakeRefused, match="pending_cycle_unproven"):
        h.cloud(cloud.readiness)
    produce_latest(h, SUCCESSOR)
    before = snapshot(h)
    ready = h.cloud(cloud.readiness)
    assert ready["epoch"]["provider"]["api_revision"] == CURRENT
    p = recovery_proposal(h)
    p["provider"]["api_revision"] = p["provider"]["worker_revision"] = SUCCESSOR
    prepared = h.cloud(cloud.create_epoch, p, actor="owner-admin:synthetic")
    enabled = h.cloud(cloud.set_enabled, prepared["epoch"]["epoch_id"],
        {"policy_sha256": prepared["policy_sha256"]}, enabled=True, actor="owner-admin:synthetic")
    request = packet(enabled, request_id="4"*32, instance="5"*32); request["worker_revision"] = SUCCESSOR
    result = h.cloud(cloud.cycle, request, "b"*64)
    assert result["success"] is True, result
    actual = policy_row(h)
    assert actual["scope_json"] == prior["scope_json"]
    after = snapshot(h)
    assert before["commands"][0] in after["commands"]
    assert all(row in after["findings"] for row in before["findings"])
    assert all(r["verified"] and r["counts"] == [1, 1, 1] for r in h.cloud(cloud.evidence, enabled["epoch"]["epoch_id"])["receipts"])
    assert any(r[0]["metadata_json"].get("prior_policy") == prior for r in after["findings"] if r[0]["event_type"] == "review_note")
    assert failed["epoch"]["epoch_id"] != enabled["epoch"]["epoch_id"]


@pytest.mark.parametrize("wrong_service", [cloud.WORKER_SERVICE, "srv-other-api"])
def test_matching_wrong_provider_and_environment_cannot_borrow_api_identity(h, monkeypatch, wrong_service):
    prepare(h)
    current = policy_row(h)
    epoch = current["metadata_json"][cloud.META_KEY]
    epoch["worker_instance"] = "2"*32
    epoch["provider"]["api_service_id"] = wrong_service
    context = {key: deepcopy(epoch[key]) for key in ("contract", "epoch_id", "issued_at", "expires_at",
        "scope_sha256", "worker_token_sha256", "worker_instance", "provider")}
    monkeypatch.setenv("RENDER_SERVICE_ID", wrong_service)
    with h.db() as db:
        database_now = db.execute("select clock_timestamp()").fetchone()[0]
    with pytest.raises(intake.IntakeRefused, match="cloud_api_identity_changed"):
        intake._cloud_epoch_matches(current, deepcopy(current), context, database_now)


@pytest.mark.parametrize("drift", ["status", "worker", "trigger", "chronology", "payload", "generation"])
def test_current_latest_still_requires_every_original_evidence_predicate(h, drift):
    event, cycle = produce_latest(h, CURRENT)[0]
    with h.db() as db:
        if drift == "status": db.execute("update app_private.oom_manager_worker_cycles set status='failed' where cycle_id=%s", (cycle["cycle_id"],))
        elif drift == "worker": db.execute("update app_private.oom_manager_worker_cycles set worker_id='other' where cycle_id=%s", (cycle["cycle_id"],))
        elif drift == "trigger": db.execute("update app_private.oom_manager_worker_cycles set trigger_identity='other' where cycle_id=%s", (cycle["cycle_id"],))
        else:
            # Manager evidence is append-only. Add a distinct later adverse row;
            # never rewrite the producer's genuine event or disable its trigger.
            payload = deepcopy(event["event_payload"])
            generation = event["generation"]
            occurred_at = datetime.fromisoformat(event["occurred_at"]) + timedelta(microseconds=1)
            if drift == "chronology": occurred_at += timedelta(minutes=1)
            elif drift == "payload": payload["technical_dependency"]["dependency_id"] = "other"
            else: generation += 1
            db.execute("""insert into app_private.oom_manager_case_events
                (event_id,case_id,generation,event_type,event_payload,occurred_at)
                values(%s,%s,%s,%s,%s::jsonb,%s)""",
                (event["event_id"]+"-ADVERSE",event["case_id"],generation,event["event_type"],
                 json.dumps(payload),occurred_at))
            assert db.execute("select to_jsonb(e) from app_private.oom_manager_case_events e where event_id=%s",
                              (event["event_id"],)).fetchone()[0] == event
    before = snapshot(h); policy = policy_row(h)
    with pytest.raises(intake.IntakeRefused): h.cloud(cloud.readiness)
    assert snapshot(h) == before and policy_row(h) == policy
