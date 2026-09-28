"""Synthetic manual-correction proofs; production connections are never defaulted."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from scripts import correct_oom_presend_timeout as correction


def preimage():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    iso = old.isoformat()
    source = {"mission_id": "SYNTHETIC-SOURCE", "provider_message_id": "100",
              "owner_user_id": "9000", "chat_id": "9000", "status": "preview_ready",
              "event_phase": "retained_preview_generated:synthetic", "operation_id": "SYNTHETIC-OP",
              "preview": {"confirmation_binding": {"operation_id": "SYNTHETIC-OP", "preview_sha256": "a" * 64}},
              "correction_digest": "", "invalidated_operation_ids": [], "consumed_context_missions": [],
              "superseded_duplicate_bindings": [], "superseded_duplicate_missions": []}
    payload = {"effect_kind": "mortality", "event_family": "mortality",
               "operation_id": "SYNTHETIC-OP", "preview_sha256": "a" * 64,
               "identity": {"pig_id": "SYNTHETIC-ANIMAL", "resolved": True}}
    digest = correction.canonical_preview_digest("mortality", payload)
    token = "SYNTHETIC-NONPRODUCTION-TOKEN"
    claim = {"callback_token": token, "mission_id": "SYNTHETIC-CLAIM", "action_kind": "mortality",
        "owner_user_id": "9000", "private_chat_id": "9000", "provider_message_id": "100",
        "preview_digest": digest, "preview_payload": payload, "evidence_generation": "SYNTHETIC-GENERATION",
        "status": "active", "expires_at": (old + timedelta(minutes=30)).isoformat(),
        "delivery_state": "delivery_ambiguous", "delivery_attempt_id": correction._sha(
            "oom_protected_delivery.v1|" + token + "|" + digest),
        "delivery_attempted_at": iso, "delivery_ambiguous_at": (old + timedelta(seconds=2)).isoformat(),
        "delivery_result": {"success": False, "status": "family_message_cycle_deadline_deferred",
                            "telegram_message_id": None, "telegram_sends": 0, "telegram_edits": 0},
        "created_at": (old - timedelta(hours=1)).isoformat(),
        **{key: None for key in correction.EMPTY_MARKERS}}
    binding = correction.retained_report_binding([source])
    source["retained_repreview"] = {"contract_version": "retained_health_preview_v1", "source_binding": binding,
        "claim_mission_id": claim["mission_id"], "claim_preview_digest": digest,
        "claim_evidence_generation": claim["evidence_generation"]}
    case = {"case_id": "SYNTHETIC-CASE", "dedupe_key": "herdmaster:retained-mortality:100",
        "specialist": "HERDMASTER", "urgency": "urgent", "status": "contained", "generation": 1,
        "evidence_digest": "b" * 64, "evidence_refs": ["provider_message:100", "pig:SYNTHETIC-ANIMAL", binding],
        "unknowns": [], "summary": "Synthetic test only", "next_action": "reassess",
        "next_reassessment_at": iso, "created_at": iso, "updated_at": iso, "last_heartbeat_at": iso,
        "assigned_worker_id": None, "lease_until": None, "last_delivery_digest": None, "last_delivery_at": None}
    cycle = {"cycle_id": "SYNTHETIC-CYCLE", "source_revision": "c" * 40, "status": "failed",
             "started_at": str(old - timedelta(seconds=40)), "case_counts": {"exceptions": 1}}
    renewal = {"claim_hash": correction._sha(token), "mission_id": claim["mission_id"],
        "preview_digest": digest, "evidence_generation": claim["evidence_generation"], "source_binding": binding,
        "new_expires_at": claim["expires_at"], "old_expires_at": (old - timedelta(hours=1)).isoformat(),
        "one_time_only": True, "provider_attempts": 0, "farm_writes": 0,
        "old_status": "active", "new_status": "active", "old_delivery_state": "claim_created",
        "new_delivery_state": "claim_created", "contract_version": "retained_protected_preview_expiry_renewal.v1"}
    event = {"event_id": "SYNTHETIC-CONTAINED", "case_id": case["case_id"], "generation": 1,
        "event_type": "contained", "occurred_at": (old + timedelta(seconds=3)).isoformat(),
        "event_payload": {"cycle_id": cycle["cycle_id"], "outcome_status": "protected_delivery_ambiguous",
                          "provider_ambiguity_contained": True}}
    return {"case": [{"record": case}], "claim": [{"record": claim}], "related_claims": [{"record": deepcopy(claim)}],
        "family": [{"row_count": 0, "effect_rows": 0}], "case_events": [{"record": event}],
        "claim_audits": [{"event_id": "SYNTHETIC-RENEWAL", "event_type": "retained_protected_preview_expiry_renewed",
            "idempotency_key": "synthetic-renewal", "payload_json": renewal, "occurred_at": str(old)}],
        "source_history": [{"review_event_id": "SYNTHETIC-SOURCE-EVENT", "created_at": str(old), "record": source}],
        "animal": [{"record": {"pig_id": "SYNTHETIC-ANIMAL", "status": "Active", "on_farm": True}}],
        "cycle": [cycle], "card_mission_id": correction.protected_card_mission_id(claim["mission_id"], digest)}


def plan(evidence=None):
    return correction.prepare_plan(evidence or preimage(), prevention_revision="d" * 40,
        prevention_tree="e" * 40, authorization_expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def authorize(digest):
    assert len(digest) == 64
    return "SYNTHETIC-OWNER-WRITE-AND-TRANSPORT-AUTHORITY"


def deployed(candidate, tree):
    assert candidate == "d" * 40 and tree == "e" * 40
    return {"loaded_revision": "f" * 40, "loaded_tree": tree}


def apply(p, connect, **kwargs):
    return correction.apply_correction(p, authorize=kwargs.get("authorize", authorize),
        verify_prevention=kwargs.get("verify_prevention", deployed), connect_factory=connect)


def test_preparation_is_pure_bound_and_does_not_grant_authority():
    evidence = preimage(); before = deepcopy(evidence)
    p = plan(evidence)
    assert evidence == before
    assert p["ttl_seconds"] == 1800 and "authorized" not in p
    assert p["preimage_sha256"] == correction._digest(evidence)
    assert p["provider_ids"] == ["100"]


@pytest.mark.parametrize("fault", ["already_sent", "unknown_result", "notification_deadline", "boolean_count",
    "attempt", "card", "confirmation", "cancelled", "leased", "delivered_case", "wrong_source_owner",
    "superseded", "bridge", "animal", "renewal", "cycle", "digest", "related", "family"])
def test_unsafe_or_unproven_preimages_fail_before_authority_or_connection(fault):
    e = preimage(); c = e["claim"][0]["record"]; m = e["case"][0]["record"]
    s = e["source_history"][0]["record"]
    if fault == "already_sent": c["provider_accepted_at"] = c["delivery_attempted_at"]
    elif fault == "unknown_result": c["delivery_result"] = {}
    elif fault == "notification_deadline": c["delivery_result"]["telegram_message_id"] = "SYNTHETIC-CARD"
    elif fault == "boolean_count": c["delivery_result"]["telegram_sends"] = False
    elif fault == "attempt": c["delivery_attempt_id"] = "wrong"
    elif fault == "card": c["preview_card_message_id"] = "SYNTHETIC-CARD"
    elif fault == "confirmation": c["confirmation_provider_message_id"] = "101"
    elif fault == "cancelled": c["status"] = "cancelled"
    elif fault == "leased": m["assigned_worker_id"] = "SYNTHETIC-WORKER"
    elif fault == "delivered_case": m["last_delivery_digest"] = m["evidence_digest"]
    elif fault == "wrong_source_owner": s["owner_user_id"] = "9001"
    elif fault == "superseded": s["consumed_context_missions"] = ["OTHER-SYNTHETIC"]
    elif fault == "bridge": s["retained_repreview"]["claim_preview_digest"] = "wrong"
    elif fault == "animal": e["animal"][0]["record"]["on_farm"] = False
    elif fault == "renewal": e["claim_audits"][0]["payload_json"]["one_time_only"] = False
    elif fault == "cycle": e["case_events"][0]["record"]["event_payload"]["cycle_id"] = "OTHER"
    elif fault == "digest": c["preview_payload"]["operation_id"] = "OTHER"
    elif fault == "related": e["related_claims"].append(deepcopy(e["related_claims"][0]))
    elif fault == "family": e["family"][0]["row_count"] = 1
    if fault != "related": e["related_claims"] = [{"record": deepcopy(c)}]
    with pytest.raises((ValueError, KeyError)):
        plan(e)


@pytest.mark.parametrize("hook", ["authorize", "verify_prevention"])
def test_authority_and_deployment_are_required_before_connection(hook):
    calls = []
    with pytest.raises(ValueError):
        apply(plan(), lambda: calls.append("connected"), **{hook: lambda *args: False})
    assert calls == []


def test_plan_tampering_fails_before_hooks():
    p = plan(); p["ttl_seconds"] = 3600
    with pytest.raises(ValueError, match="plan_binding_mismatch"):
        apply(p, lambda: pytest.fail("connection"), authorize=lambda *a: pytest.fail("authority"))


def test_expired_plan_never_invokes_authority_deployment_or_connection():
    p = plan(); p["authorization_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    forbidden = lambda *args: pytest.fail("expired plan crossed external boundary")
    with pytest.raises(ValueError, match="authorization_expired"):
        apply(p, forbidden, authorize=forbidden, verify_prevention=forbidden)


def test_timestamp_readback_accepts_trimmed_fraction_but_rejects_other_changes():
    actual = {"expires_at": "2026-01-01T00:00:00.12345+00:00", "preview_digest": "same"}
    expected = {"expires_at": "2026-01-01T00:00:00.123450+00:00", "preview_digest": "same"}
    assert correction._same_projection(actual, expected, {"expires_at"})
    assert not correction._same_projection({**actual, "preview_digest": "changed"}, expected, {"expires_at"})


def disposable_url():
    url = os.environ.get("OOM_DESKTOP_REBIND_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("explicit disposable PostgreSQL URL required")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or "test" not in parsed.path.casefold() or parsed.query or parsed.fragment
            or any(os.environ.get(k) for k in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"))):
        raise ValueError("disposable_local_test_database_required")
    return url


@pytest.fixture
def database():
    url = disposable_url()
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
    schema = "presend_correction_" + uuid4().hex
    migration_dir = Path(__file__).resolve().parents[1] / "supabase/migrations"
    class Cursor:
        def __init__(self, cur, fault=None): self.cur, self.fault, self.writes = cur, fault, 0
        def __getattr__(self, name): return getattr(self.cur, name)
        def __enter__(self): self.cur.__enter__(); return self
        def __exit__(self, *args): return self.cur.__exit__(*args)
        def execute(self, query, params=None):
            query = query.replace("public.", schema + ".").replace("app_private.", schema + ".")
            self.cur.execute(query, params)
            if query.strip().lower().startswith(("insert ", "update ")):
                self.writes += 1
                if self.writes == self.fault:
                    raise RuntimeError("synthetic transaction interruption")
            return self
    class Connection:
        def __init__(self, fault=None):
            self.db = psycopg.connect(url, connect_timeout=3)
            self.fault = fault
        def __getattr__(self, name): return getattr(self.db, name)
        def __enter__(self): self.db.__enter__(); return self
        def __exit__(self, *args): return self.db.__exit__(*args)
        def cursor(self): return Cursor(self.db.cursor(), self.fault)
    with psycopg.connect(url, connect_timeout=3) as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
    try:
        with Connection() as db, db.cursor() as cur:
            definitions = (
                ("202608110001_create_oom_protected_action_claims.sql", "app_private.oom_protected_action_claims"),
                ("202608170002_create_oom_manager_case_runtime.sql", "app_private.oom_manager_cases"),
                ("202608170002_create_oom_manager_case_runtime.sql", "app_private.oom_manager_case_events"),
                ("202608170002_create_oom_manager_case_runtime.sql", "app_private.oom_manager_worker_cycles"),
                ("202607190001_create_operational_event_fabric.sql", "public.operational_events"),
            )
            for filename, table in definitions:
                ddl = (migration_dir / filename).read_text(encoding="utf-8")
                statement = re.search(r"create table if not exists " + re.escape(table) + r"\s*\(.*?\n\);", ddl, re.S)[0]
                cur.execute(statement)
            delivery = (migration_dir / "202608160004_add_protected_delivery_lifecycle.sql").read_text(encoding="utf-8")
            cur.execute(delivery.split("revoke all", 1)[0])
            cur.execute("create unique index one_active_claim on app_private.oom_protected_action_claims(mission_id) where status='active'")
            cur.execute("""create table public.sam_live_stock_conversation_review_events(
                review_event_id text primary key,event_source text not null,review_json jsonb not null,
                created_at timestamptz not null,chatwoot_conversation_id text)""")
            cur.execute("create table public.pigs(pig_id text primary key,status text,on_farm boolean)")
            cur.execute("create view public.current_canonical_pigs as select * from public.pigs")
        e = preimage()
        def insert(table, row):
            with Connection() as db, db.cursor() as cur:
                columns = list(row)
                # table/columns are test-owned identifiers, never external input.
                cur.execute("insert into " + table + "(" + ",".join(columns) + ") values(" +
                    ",".join(["%s"] * len(columns)) + ")", tuple(
                        Jsonb(row[k]) if isinstance(row[k], (dict, list)) else row[k] for k in columns))
        insert("app_private.oom_protected_action_claims", e["claim"][0]["record"])
        insert("app_private.oom_manager_cases", e["case"][0]["record"])
        insert("app_private.oom_manager_case_events", e["case_events"][0]["record"])
        cycle = e["cycle"][0]
        insert("app_private.oom_manager_worker_cycles", {**cycle, "worker_id": "SYNTHETIC-WORKER",
            "trigger_identity": "SYNTHETIC-TRIGGER", "heartbeat_at": cycle["started_at"],
            "next_cycle_at": cycle["started_at"]})
        source = e["source_history"][0]
        insert("public.sam_live_stock_conversation_review_events", {
            "review_event_id": source["review_event_id"], "created_at": source["created_at"],
            "event_source": correction.REPORT_SOURCE, "review_json": {"herdmaster_health_loss": source["record"]}})
        insert("public.pigs", e["animal"][0]["record"])
        audit = e["claim_audits"][0]
        insert("public.operational_events", {**audit, "schema_version": "1", "domain": "incidents",
            "aggregate_type": "protected_action_claim", "aggregate_id": correction._sha(e["claim"][0]["record"]["callback_token"]),
            "source_system": "synthetic", "authority_tier": "bounded_auto", "privacy_class": "owner_private",
            "freshness_at": audit["occurred_at"], "provenance_json": {"source_ref": "synthetic"}})
        provisional = plan(e)
        def snapshot():
            with Connection() as db, db.cursor() as cur:
                cases = correction._rows(cur, "select to_jsonb(m) from app_private.oom_manager_cases m", (), ("record",))
                claims = correction._rows(cur, "select to_jsonb(c) from app_private.oom_protected_action_claims c", (), ("record",))
                return correction._fresh(cur, provisional, claims, cases)
        actual_plan = plan(snapshot())
        yield actual_plan, Connection, snapshot, insert
    finally:
        with psycopg.connect(url, connect_timeout=3) as db:
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def test_postgres_four_writes_preserve_history_and_replay_after_worker_progress(database):
    p, connect, snapshot, _insert = database
    before = snapshot()
    result = apply(p, connect)
    after = snapshot()
    assert result["metadata_writes"] == 4
    c = after["claim"][0]["record"]; m = after["case"][0]["record"]
    assert c["delivery_state"] == "claim_created" and c["delivery_attempt_id"] is None
    assert m["status"] == "waiting_reassessment" and m["generation"] == 1
    for key in ("callback_token", "mission_id", "preview_payload", "preview_digest", "evidence_generation"):
        assert c[key] == before["claim"][0]["record"][key]
    audit = next(x for x in after["claim_audits"] if x["event_type"] == correction.EVENT_TYPE)
    assert audit["payload_json"]["archived_claim_markers"]["delivery_result"] == before["claim"][0]["record"]["delivery_result"]
    assert audit["payload_json"]["original_renewal"] == before["claim_audits"][0]
    assert audit["payload_json"]["deployed_revision"] != p["prevention_revision"]
    assert before["source_history"] == after["source_history"] and before["animal"] == after["animal"]
    assert apply(p, connect)["metadata_writes"] == 0
    with connect() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set delivery_state='delivery_confirmed',preview_card_message_id='SYNTHETIC-DELIVERED'")
        cur.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest")
    progressed = snapshot()
    assert apply(p, connect)["status"] == "already_applied" and snapshot() == progressed


@pytest.mark.parametrize("write", [1, 2, 3, 4])
def test_postgres_failure_after_each_write_rolls_back_all_metadata(database, write):
    p, connect, snapshot, _insert = database
    before = snapshot()
    with pytest.raises(RuntimeError, match="synthetic transaction interruption"):
        apply(p, lambda: connect(fault=write))
    assert snapshot() == before


@pytest.mark.parametrize("changed", ["claim", "case", "animal", "family", "source", "related"])
def test_postgres_changed_preimage_rejects_without_any_correction(database, changed):
    p, connect, snapshot, insert = database
    with connect() as db, db.cursor() as cur:
        if changed == "claim": cur.execute("update app_private.oom_protected_action_claims set status='cancelled'")
        elif changed == "case": cur.execute("update app_private.oom_manager_cases set generation=2")
        elif changed == "animal": cur.execute("update public.pigs set on_farm=false")
        elif changed == "source": cur.execute("update public.sam_live_stock_conversation_review_events set review_json=jsonb_set(review_json,'{herdmaster_health_loss,status}','\"cancelled\"'::jsonb)")
        elif changed == "related":
            cur.execute("""insert into app_private.oom_protected_action_claims(callback_token,action_kind,owner_user_id,
                private_chat_id,mission_id,provider_message_id,preview_digest,evidence_generation,preview_payload,
                expires_at) values('SYNTHETIC-OTHER','mortality','9000','9000','SYNTHETIC-OTHER','100','OTHER','OTHER','{}',now())""")
    if changed == "family":
        insert("public.sam_live_stock_conversation_review_events", {"review_event_id": "SYNTHETIC-FAMILY",
            "created_at": datetime.now(timezone.utc), "event_source": correction.FAMILY_SOURCE,
            "review_json": {"family_message_lifecycle": {"card_mission_id": p["preimage"]["card_mission_id"], "state": "unknown"}}})
    before = snapshot()
    with pytest.raises(ValueError, match="fresh_preimage_mismatch"):
        apply(p, connect)
    assert snapshot() == before


def test_postgres_two_operators_commit_one_correction(database):
    p, connect, snapshot, _insert = database
    barrier = Barrier(2)
    def run():
        barrier.wait(timeout=5)
        return apply(p, connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(r["metadata_writes"] for r in results) == [0, 4]
    assert len([e for e in snapshot()["claim_audits"] if e["event_type"] == correction.EVENT_TYPE]) == 1


def test_postgres_changed_authorization_window_cannot_extend_again(database):
    p, connect, snapshot, _insert = database
    apply(p, connect); before = snapshot()
    other = deepcopy(p)
    other["authorization_expires_at"] = (correction._time(p["authorization_expires_at"]) + timedelta(minutes=5)).isoformat()
    with pytest.raises(ValueError, match="correction_replay_conflict"):
        apply(other, connect)
    assert snapshot() == before
