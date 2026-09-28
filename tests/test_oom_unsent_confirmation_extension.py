"""Synthetic extension proofs; only explicitly configured disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from threading import Barrier, Event

import pytest

from scripts import extend_oom_unsent_confirmation as extension
from scripts import correct_oom_presend_timeout as correction
from tests.test_oom_presend_timeout_correction import plan as original_plan
from tests.test_oom_presend_timeout_correction import database as correction_database


def material_fixture():
    evidence = {"animals": [{"pig_id": "SYNTHETIC-ANIMAL", "name": "Synthetic", "tag_number": "27",
        "lifecycle_status": "Active", "on_farm": True, "availability": "Herd", "pen": "PEN-A",
        "birth_date": "", "lifecycle_effective_date": ""}], "matings": [], "litters": [],
        "as_of_timestamp": "2026-09-22T08:00:00+00:00"}
    evidence["evidence_generation"] = extension._digest({k: evidence[k] for k in ("animals", "matings", "litters")})
    evidence["animal_evidence_generations"] = {"SYNTHETIC-ANIMAL": extension._digest({
        "animal": evidence["animals"][0], "matings": [], "litters": []})}
    return evidence


def bind_real_preview(original, evidence):
    old = deepcopy(original["preimage"])
    source = old["source_history"][0]["record"]
    source.update({"provider_timestamp": "2026-08-20T08:00:00+00:00", "output_language": "af",
        "owner_text_verbatim": "Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe."})
    preview = extension._preview(source, evidence)
    assert preview["success"] and preview["confirmation_ready"], preview
    source["preview"] = preview
    source["operation_id"] = preview["confirmation_binding"]["operation_id"]
    claim = old["claim"][0]["record"]
    claim["preview_payload"] = {"operation_id": source["operation_id"],
        "preview_sha256": preview["confirmation_binding"]["preview_sha256"],
        "identity": preview["evaluator"]["identity"], "event_family": preview["evaluator"]["event_family"],
        "effect_kind": "mortality"}
    claim["preview_digest"] = correction.canonical_preview_digest("mortality", claim["preview_payload"])
    claim["evidence_generation"] = evidence["evidence_generation"]
    claim["delivery_attempt_id"] = correction._sha("oom_protected_delivery.v1|" + claim["callback_token"] + "|" + claim["preview_digest"])
    binding = correction.retained_report_binding([source])
    source["retained_repreview"].update({"source_binding": binding, "claim_preview_digest": claim["preview_digest"],
        "claim_evidence_generation": claim["evidence_generation"]})
    old["case"][0]["record"]["evidence_refs"][-1] = binding
    old["claim_audits"][0]["payload_json"].update({"preview_digest": claim["preview_digest"],
        "evidence_generation": claim["evidence_generation"], "source_binding": binding})
    old["related_claims"] = [{"record": deepcopy(claim)}]
    old["card_mission_id"] = correction.protected_card_mission_id(claim["mission_id"], claim["preview_digest"])
    return correction.prepare_plan(old, prevention_revision=original["prevention_revision"],
        prevention_tree=original["prevention_tree"], authorization_expires_at=original["authorization_expires_at"])


def fixture(original=None, material_evidence=None):
    material = material_evidence or material_fixture()
    original = original or bind_real_preview(original_plan(), material)
    now = datetime.now(timezone.utc)
    corrected_at = now - timedelta(hours=1)
    prior = original["preimage"]
    old = prior["claim"][0]["record"]
    old_case = prior["case"][0]["record"]
    event_id = "OOM-PRESEND-CORRECTION-" + original["claim_hash"][:32].upper()
    payload = {"contract_version": correction.CONTRACT, "plan_sha256": correction.plan_digest(original),
        "preimage_sha256": original["preimage_sha256"], "claim_hash": original["claim_hash"],
        "case_id": old_case["case_id"], "generation": old_case["generation"],
        "evidence_digest": old_case["evidence_digest"], "preview_digest": old["preview_digest"],
        "archived_claim_markers": {k: old[k] for k in correction.ARCHIVED_MARKERS},
        "original_renewal": deepcopy(prior["claim_audits"][0]), "one_time_only": True,
        "new_expires_at": (corrected_at + timedelta(minutes=30)).isoformat(),
        "authority_reference": "SYNTHETIC-ORIGINAL-AUTHORITY",
        "prevention_revision": original["prevention_revision"], "prevention_tree": original["prevention_tree"],
        "deployed_revision": "f" * 40, "provider_attempts": 0, "farm_writes": 0, "scheduler_triggers": 0}
    audit = {"event_id": event_id, "event_type": correction.EVENT_TYPE,
        "idempotency_key": "oom-presend-timeout-correction:" + original["claim_hash"],
        "occurred_at": corrected_at.isoformat(), "payload_json": payload}
    claim = {**deepcopy(old), "status": "active", "delivery_state": "claim_created",
        "expires_at": payload["new_expires_at"], **{k: None for k in correction.ARCHIVED_MARKERS[:4]}}
    case = {**deepcopy(old_case), "status": "exception", "updated_at": corrected_at.isoformat(),
        "last_heartbeat_at": corrected_at.isoformat(), "next_reassessment_at": corrected_at.isoformat()}
    case_event = {"record": {"event_id": event_id + "-REASSESS", "case_id": case["case_id"],
        "generation": case["generation"], "event_type": "reassessment_scheduled",
        "occurred_at": corrected_at.isoformat(), "event_payload": {
            "correction_audit_event_id": event_id, "plan_sha256": correction.plan_digest(original),
            "outcome_status": "proven_presend_timeout_classification_corrected"}}}
    evidence = {k: deepcopy(prior[k]) for k in ("animal", "source_history", "family", "card_mission_id")}
    evidence.update({"claim": [{"record": claim}], "related_claims": [{"record": deepcopy(claim)}],
        "case": [{"record": case}], "case_events": [case_event], "claim_audits": [audit, deepcopy(prior["claim_audits"][0])],
        "operations": [], "material_evidence": deepcopy(material)})
    return original, evidence, now


def proposal(original, evidence, now):
    return extension.prepare_plan(evidence, original_correction_plan=original,
        prevention_revision="1" * 40, prevention_tree="2" * 40,
        authorization_expires_at=now + timedelta(hours=1))


def inspect(plan, fresh, now, *, authority_changes=None, deployment_changes=None):
    claim = plan["preimage"]["claim"][0]["record"]
    authority = {"authority_reference": "SYNTHETIC-NEW-APPROVAL-ATTESTATION",
        "plan_sha256": extension.plan_digest(plan), "owner_user_id": claim["owner_user_id"],
        "private_chat_id": claim["private_chat_id"], "authorization_expires_at": plan["authorization_expires_at"]}
    authority.update(authority_changes or {})
    deployed = {"loaded_tree": plan["prevention_tree"], "loaded_revision": "3" * 40}
    deployed.update(deployment_changes or {})
    return extension.inspect_proposal(plan, fresh_preimage=fresh, now=now,
        authority=authority, loaded_prevention=deployed)


def test_exact_proposal_keeps_original_audits_and_has_no_authority_or_writes():
    original, evidence, now = fixture()
    before = deepcopy((original, evidence))
    plan = proposal(original, evidence, now)
    result = inspect(plan, evidence, now)
    assert (original, evidence) == before
    assert plan["ttl_seconds"] == 1800
    assert plan["expected_expires_at"] == evidence["claim"][0]["record"]["expires_at"]
    assert result == {"status": "proposal_consistent_not_authorized", "metadata_writes": 0,
        "plan_sha256": extension.plan_digest(plan), "proposed_expires_at": (now + timedelta(minutes=30)).isoformat()}


@pytest.mark.parametrize("fault", ["attempt_id", "attempt_time", "delivery_result", "ambiguous", "accepted",
    "card", "confirmation", "completed", "cancelled", "expired_status", "expiry", "token", "principal",
    "payload", "generation", "evidence_digest", "source_binding", "leased", "delivered_case", "terminal_case",
    "source_principal", "source_text", "source_terminal", "source_added", "animal", "duplicate_animal",
    "family", "boolean_family_count", "operation", "related_claim", "renewal", "correction", "repeat_extension"])
def test_unsafe_or_changed_evidence_cannot_form_proposal(fault):
    original, e, now = fixture()
    c, m = e["claim"][0]["record"], e["case"][0]["record"]
    source = e["source_history"][0]["record"]
    if fault == "attempt_id": c["delivery_attempt_id"] = "SYNTHETIC-ATTEMPT"
    elif fault == "attempt_time": c["delivery_attempted_at"] = now.isoformat()
    elif fault == "delivery_result": c["delivery_result"] = {"success": False}
    elif fault == "ambiguous": c["delivery_state"] = "delivery_ambiguous"
    elif fault == "accepted": c["provider_accepted_at"] = now.isoformat()
    elif fault == "card": c["preview_card_message_id"] = "SYNTHETIC-CARD"
    elif fault == "confirmation": c["confirmation_provider_message_id"] = "101"
    elif fault == "completed": c["status"] = "completed"
    elif fault == "cancelled": c["status"] = "cancelled"
    elif fault == "expired_status": c["status"] = "expired"
    elif fault == "expiry": c["expires_at"] = (now - timedelta(minutes=5)).isoformat()
    elif fault == "token": c["callback_token"] = "SYNTHETIC-OTHER-TOKEN"
    elif fault == "principal": c["owner_user_id"] = "9001"
    elif fault == "payload": c["preview_payload"]["identity"]["pig_id"] = "SYNTHETIC-OTHER"
    elif fault == "generation": m["generation"] += 1
    elif fault == "evidence_digest": m["evidence_digest"] = "a" * 64
    elif fault == "source_binding": m["evidence_refs"][-1] = "retained_report_binding:" + "0" * 64
    elif fault == "leased": m["lease_until"] = (now + timedelta(minutes=1)).isoformat()
    elif fault == "delivered_case": m["last_delivery_digest"] = m["evidence_digest"]
    elif fault == "terminal_case": m["status"] = "contained"
    elif fault == "source_principal": source["owner_user_id"] = "9001"
    elif fault == "source_text": source["owner_text_verbatim"] = "Changed material report"
    elif fault == "source_terminal": source["status"] = "completed"
    elif fault == "source_added": e["source_history"].append(deepcopy(e["source_history"][0]))
    elif fault == "animal": e["animal"][0]["record"]["on_farm"] = False
    elif fault == "duplicate_animal": e["animal"].append(deepcopy(e["animal"][0]))
    elif fault == "family": e["family"][0]["row_count"] = 1
    elif fault == "boolean_family_count": e["family"][0]["row_count"] = False
    elif fault == "operation": e["operations"] = [{"record": {"idempotency_key": "SYNTHETIC-OP"}}]
    elif fault == "related_claim": e["related_claims"].append(deepcopy(e["related_claims"][0]))
    elif fault == "renewal": e["claim_audits"][1]["payload_json"]["one_time_only"] = False
    elif fault == "correction": e["claim_audits"][0]["payload_json"]["plan_sha256"] = "0" * 64
    elif fault == "repeat_extension": e["claim_audits"].append({"event_type": "protected_unsent_confirmation_expiry_extended"})
    if fault != "related_claim": e["related_claims"] = [{"record": deepcopy(c)}]
    with pytest.raises(ValueError):
        proposal(original, e, now)


@pytest.mark.parametrize("change", ["actor", "chat", "digest", "deadline", "empty_reference", "wrong_tree", "invalid_revision"])
def test_unbound_external_attestations_are_rejected(change):
    original, e, now = fixture()
    p = proposal(original, e, now)
    authority, deployment = {}, {}
    if change == "actor": authority["owner_user_id"] = "9001"
    elif change == "chat": authority["private_chat_id"] = "9001"
    elif change == "digest": authority["plan_sha256"] = "0" * 64
    elif change == "deadline": authority["authorization_expires_at"] = (now + timedelta(days=1)).isoformat()
    elif change == "empty_reference": authority["authority_reference"] = ""
    elif change == "wrong_tree": deployment["loaded_tree"] = "4" * 40
    elif change == "invalid_revision": deployment["loaded_revision"] = "unverified"
    with pytest.raises(ValueError):
        inspect(p, e, now, authority_changes=authority, deployment_changes=deployment)


def test_natural_case_timestamps_and_safe_deadline_history_can_advance_without_freezing_whole_case():
    original, e, now = fixture()
    p = proposal(original, e, now)
    fresh = deepcopy(e)
    case = fresh["case"][0]["record"]
    for field in extension.CASE_CLOCKS:
        case[field] = (now - timedelta(seconds=1)).isoformat()
    fresh["case_events"].insert(0, {"record": {"event_id": "SYNTHETIC-NATURAL-DEADLINE",
        "case_id": case["case_id"], "generation": case["generation"], "event_type": "exception",
        "occurred_at": (now - timedelta(seconds=1)).isoformat(), "event_payload": {
            "outcome_status": "manager_cycle_deadline_deferred", "failure_kind": "",
            "provider_ambiguity_contained": False, "deadline_phase": "before_retained_preview"}}})
    assert inspect(p, fresh, now)["metadata_writes"] == 0


@pytest.mark.parametrize("fault", ["future_due", "clock_regression", "removed_history", "unsafe_history", "foreign_history",
                                  "changed_case_status", "competing_attempt", "expired_approval", "unexpired_claim", "ttl"])
def test_changed_snapshot_or_approval_cannot_pass_pure_inspection(fault):
    original, e, now = fixture()
    p = proposal(original, e, now)
    fresh = deepcopy(e)
    if fault == "future_due": fresh["case"][0]["record"]["next_reassessment_at"] = (now + timedelta(seconds=1)).isoformat()
    elif fault == "clock_regression": fresh["case"][0]["record"]["updated_at"] = (now - timedelta(days=1)).isoformat()
    elif fault == "removed_history": fresh["case_events"] = []
    elif fault in {"unsafe_history", "foreign_history"}:
        event = deepcopy(fresh["case_events"][0])
        event["record"].update({"event_id": "SYNTHETIC-UNSAFE", "event_type": "exception"})
        event["record"]["event_payload"] = {"outcome_status": "protected_delivery_ambiguous"}
        if fault == "foreign_history": event["record"]["case_id"] = "OTHER"
        fresh["case_events"].append(event)
    elif fault == "changed_case_status": fresh["case"][0]["record"]["status"] = "waiting_reassessment"
    elif fault == "competing_attempt": fresh["claim"][0]["record"]["delivery_attempt_id"] = "COMPETING"
    elif fault == "expired_approval": now += timedelta(hours=2)
    elif fault == "unexpired_claim": now -= timedelta(hours=1)
    elif fault == "ttl": p["ttl_seconds"] = 3600
    with pytest.raises(ValueError):
        inspect(p, fresh, now)


def apply(plan, connect, *, authorize=None, verify_prevention=None):
    c = plan["preimage"]["claim"][0]["record"]
    def approved(digest):
        return {"authority_reference": "SYNTHETIC-EXACT-OWNER-APPROVAL", "plan_sha256": digest,
            "owner_user_id": c["owner_user_id"], "private_chat_id": c["private_chat_id"],
            "authorization_expires_at": plan["authorization_expires_at"]}
    return extension.apply_extension(plan, connect_factory=connect,
        authorize=authorize or approved, verify_prevention=verify_prevention or
        (lambda revision, tree: {"loaded_revision": "3" * 40, "loaded_tree": tree}))


@pytest.mark.parametrize("hook", ["authorize", "verify_prevention"])
def test_untrusted_hook_cannot_reach_database(hook):
    original, e, now = fixture()
    with pytest.raises(ValueError):
        apply(proposal(original, e, now), lambda: pytest.fail("database opened"), **{hook: lambda *a: False})


@pytest.mark.parametrize("authority", [False, {}, {"authority_reference": "unbound"}])
def test_denied_authority_cannot_invoke_deployment_proof_or_connection(authority):
    original, e, now = fixture()
    def forbidden(*args): pytest.fail("unapproved external boundary")
    with pytest.raises(ValueError, match="authority_attestation_unbound"):
        apply(proposal(original, e, now), forbidden, authorize=lambda _digest: authority,
              verify_prevention=forbidden)


@pytest.mark.parametrize("fault", ["ttl", "expired", "future_expiry"])
def test_bad_plan_never_invokes_external_hooks(fault):
    original, e, now = fixture()
    p = proposal(original, e, now)
    if fault == "ttl": p["ttl_seconds"] = 3600
    elif fault == "expired": p["authorization_expires_at"] = (now - timedelta(seconds=1)).isoformat()
    else: p["expected_expires_at"] = (now + timedelta(hours=1)).isoformat()
    def forbidden(*args): pytest.fail("invalid plan crossed external boundary")
    with pytest.raises(ValueError):
        apply(p, forbidden, authorize=forbidden, verify_prevention=forbidden)


@pytest.mark.parametrize("change", ["pen", "mating", "litter", "preview"])
def test_real_evaluator_rejects_material_evidence_change(change):
    original, e, now = fixture()
    p = proposal(original, e, now)
    fresh = deepcopy(e)
    material = fresh["material_evidence"]
    if change == "pen": material["animals"][0]["pen"] = "PEN-B"
    elif change == "mating": material["matings"] = [{"mating_id": "M", "sow_pig_id": "SYNTHETIC-ANIMAL"}]
    elif change == "litter": material["litters"] = [{"litter_id": "L", "sow_pig_id": "SYNTHETIC-ANIMAL"}]
    else: fresh["source_history"][0]["record"]["preview"]["owner_text"] = "Changed preview"
    with pytest.raises(ValueError): inspect(p, fresh, now)


def test_fresh_canonical_clock_keeps_the_same_material_preview_and_expiry_binding():
    original, evidence, now = fixture()
    p = proposal(original, evidence, now)
    fresh = deepcopy(evidence)
    fresh["material_evidence"]["as_of_timestamp"] = now.isoformat()
    assert inspect(p, fresh, now)["metadata_writes"] == 0
    # Expiry formatting may normalize; the actual prior instant cannot move.
    fresh["claim"][0]["record"]["expires_at"] = (extension._time(p["expected_expires_at"]) + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="claim_not_exact_unsent_correction"):
        inspect(p, fresh, now)


@pytest.fixture
def extension_database(correction_database):
    """Actual canonical reader SQL and actual claim/audit/farm table schemas.

    The inherited fixture enforces a localhost disposable URL and isolated
    schema. Canonical views project synthetic fixture rows; no production data
    or evaluator, reader, authentication, or transaction result is mocked.
    """
    initial, connect, old_snapshot, insert = correction_database
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    with connect() as db, db.cursor() as cur:
        cur.execute("""alter table public.pigs
            add column tag_number text, add column pig_name text, add column animal_type text,
            add column sex text, add column date_of_birth date, add column mother_pig_id text,
            add column father_pig_id text, add column litter_id text, add column purpose text,
            add column notes text, add column exit_date date, add column exit_reason text,
            add column exit_order_id text, add column litter_size_born integer,
            add column litter_size_weaned integer, add column wean_date date,
            add column wean_weight_kg numeric, add column earmarked boolean, add column earmark_date date,
            add column initial_pen_id text""")
        # Only foreign-key anchor tables outside this reader's domain are stubs.
        for table, key, kind in (("bulk_weight_batches", "batch_id", "uuid"),
                ("bulk_weight_batch_rows", "row_id", "uuid"), ("orders", "order_id", "text"),
                ("order_lines", "order_line_id", "text")):
            cur.execute(f"create table public.{table}({key} {kind} primary key)")
        definitions = (
            ("202606290001_create_farm_canonical_tables.sql", "pens"),
            ("202606290001_create_farm_canonical_tables.sql", "litters"),
            ("202606290001_create_farm_canonical_tables.sql", "mating_events"),
            ("202606290001_create_farm_canonical_tables.sql", "pig_location_events"),
            ("202608120001_create_breeding_exposure_events.sql", "pig_breeding_exposure_events"),
            ("202605210003_create_sales_transaction_tables.sql", "sales_transactions"),
            ("202605210003_create_sales_transaction_tables.sql", "sales_transaction_items"),
            ("202607210001_create_pig_lifecycle_events.sql", "pig_lifecycle_events"),
            ("202608200002_create_pig_welfare_case_lifecycle.sql", "pig_welfare_cases"),
            ("202608200002_create_pig_welfare_case_lifecycle.sql", "pig_welfare_case_events"),
        )
        for filename, table in definitions:
            ddl = (migrations / filename).read_text(encoding="utf-8")
            cur.execute(re.search(r"create table if not exists public\." + table + r"\s*\(.*?\n\);", ddl, re.S)[0])
        cur.execute("alter table public.mating_events add column source_exposure_identity text,add column exposure_group_identity text")
        cur.execute("alter table public.pig_breeding_exposure_events add column exposure_group_identity text")
        cur.execute("alter table public.sales_transactions add column sale_channel text")
        cur.execute("alter table public.litters add column wean_date date")
        cur.execute("insert into public.pens(pen_id,pen_name) values('PEN-A','Pen A'),('PEN-B','Pen B')")
        cur.execute("update public.pigs set tag_number='27',pig_name='Synthetic',purpose='Herd',initial_pen_id='PEN-A'")
        cur.execute("create or replace view public.current_canonical_pigs as select * from public.pigs")
        cur.execute("create view public.current_canonical_litters as select * from public.litters")
        cur.execute("""create view public.current_canonical_pig_state as
            select p.*,null::numeric current_weight_kg,null::date last_weight_date,
                coalesce(latest.to_pen_id,p.initial_pen_id) current_pen_id,pen.pen_name current_pen_name
            from public.pigs p left join lateral (select l.to_pen_id from public.pig_location_events l
                where l.pig_id=p.pig_id order by l.move_date desc,l.created_at desc,l.location_event_id desc limit 1) latest on true
            left join public.pens pen on pen.pen_id=coalesce(latest.to_pen_id,p.initial_pen_id)""")
        evidence = extension._read_material(db)
    real = bind_real_preview(initial, evidence)
    claim = real["preimage"]["claim"][0]["record"]
    with connect() as db, db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims set preview_payload=%s::jsonb,
            preview_digest=%s,evidence_generation=%s,delivery_attempt_id=%s""",
            (json.dumps(claim["preview_payload"]), claim["preview_digest"], claim["evidence_generation"], claim["delivery_attempt_id"]))
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s::jsonb",
            (json.dumps(real["preimage"]["case"][0]["record"]["evidence_refs"]),))
        cur.execute("update public.sam_live_stock_conversation_review_events set review_json=%s::jsonb",
            (json.dumps({"herdmaster_health_loss": real["preimage"]["source_history"][0]["record"]}),))
        cur.execute("update public.operational_events set payload_json=%s::jsonb",
            (json.dumps(real["preimage"]["claim_audits"][0]["payload_json"]),))
    # Bind the full PostgreSQL record shapes, including default/optional fields.
    before = old_snapshot()
    before["card_mission_id"] = real["preimage"]["card_mission_id"]
    original = correction.prepare_plan(before, prevention_revision=real["prevention_revision"],
        prevention_tree=real["prevention_tree"], authorization_expires_at=real["authorization_expires_at"])
    _, corrected, now = fixture(original, evidence)
    c, m = corrected["claim"][0]["record"], corrected["case"][0]["record"]
    with connect() as db, db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims set status='active',delivery_state='claim_created',
            expires_at=%s,delivery_attempt_id=null,delivery_attempted_at=null,delivery_ambiguous_at=null,delivery_result=null""", (c["expires_at"],))
        cur.execute("""update app_private.oom_manager_cases set status='exception',updated_at=%s,
            last_heartbeat_at=%s,next_reassessment_at=%s""", tuple(m[k] for k in ("updated_at", "last_heartbeat_at", "next_reassessment_at")))
    audit = corrected["claim_audits"][0]
    insert("public.operational_events", {**audit, "schema_version": "1", "domain": "incidents",
        "aggregate_type": "protected_action_claim", "aggregate_id": original["claim_hash"],
        "source_system": "manual_presend_timeout_correction", "authority_tier": "owner_approved",
        "privacy_class": "owner_private", "freshness_at": audit["occurred_at"], "provenance_json": {"source_ref": "synthetic"}})
    insert("app_private.oom_manager_case_events", corrected["case_events"][0]["record"])
    preimage = extension.read_preimage(original, connect_factory=connect)
    p = proposal(original, preimage, now)
    def state():
        with connect() as db, db.cursor() as cur:
            tables = ("app_private.oom_protected_action_claims", "app_private.oom_manager_cases",
                "app_private.oom_manager_case_events", "public.operational_events",
                "public.sam_live_stock_conversation_review_events", "public.pigs",
                "public.pig_lifecycle_events", "public.pig_welfare_case_events")
            return {table: correction._rows(cur, "select to_jsonb(t) from " + table + " t order by to_jsonb(t)::text", (), ("record",)) for table in tables}
    return p, connect, state, insert


def test_postgres_two_writes_preserve_all_state_and_replay_after_progress(extension_database):
    p, connect, state, _insert = extension_database
    before = state()
    result = apply(p, connect)
    after = state()
    assert result["metadata_writes"] == 2
    claim_table = "app_private.oom_protected_action_claims"
    changed = after[claim_table][0]["record"]
    old = before[claim_table][0]["record"]
    assert {k: v for k, v in changed.items() if k != "expires_at"} == {k: v for k, v in old.items() if k != "expires_at"}
    audits = after["public.operational_events"]
    event = next(e["record"] for e in audits if e["record"]["event_type"] == extension.EVENT_TYPE)
    assert extension._time(changed["expires_at"]) - extension._time(event["occurred_at"]) == timedelta(minutes=30)
    assert all(row in audits for row in before["public.operational_events"])
    for table in before:
        if table not in {claim_table, "public.operational_events"}: assert after[table] == before[table]
    assert apply(p, connect)["metadata_writes"] == 0
    with connect() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set delivery_attempt_id='SYNTHETIC-LATER',delivery_state='delivery_confirmed',preview_card_message_id='CARD'")
        cur.execute("update app_private.oom_manager_cases set status='completed',last_delivery_digest=evidence_digest")
    progressed = state()
    assert apply(p, connect)["metadata_writes"] == 0 and state() == progressed
    changed_plan = deepcopy(p)
    changed_plan["authorization_expires_at"] = (extension._time(p["authorization_expires_at"]) + timedelta(minutes=5)).isoformat()
    with pytest.raises(ValueError, match="extension_replay_conflict"): apply(changed_plan, connect)
    assert state() == progressed


@pytest.mark.parametrize("write", [1, 2])
def test_postgres_failure_after_either_write_rolls_back_everything(extension_database, write):
    p, connect, state, _insert = extension_database
    before = state()
    with pytest.raises(RuntimeError, match="synthetic transaction interruption"):
        apply(p, lambda: connect(fault=write))
    assert state() == before


def test_postgres_two_operators_commit_one_extension(extension_database):
    p, connect, state, _insert = extension_database
    barrier = Barrier(2)
    def run(_index):
        barrier.wait(timeout=5)
        return apply(p, connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(r["metadata_writes"] for r in results) == [0, 2]
    assert sum(e["record"]["event_type"] == extension.EVENT_TYPE for e in state()["public.operational_events"]) == 1


@pytest.mark.parametrize("change", ["attempt", "cancellation", "lease", "not_due", "source", "principal", "animal",
                                  "derived_pen", "mating", "litter", "family", "related", "operation", "welfare", "history_overflow"])
def test_postgres_fresh_canonical_change_rejects_without_extension(extension_database, change):
    p, connect, state, insert = extension_database
    c = p["preimage"]["claim"][0]["record"]
    with connect() as db, db.cursor() as cur:
        if change == "attempt": cur.execute("update app_private.oom_protected_action_claims set delivery_attempt_id='OTHER',delivery_attempted_at=now()")
        elif change == "cancellation": cur.execute("update app_private.oom_protected_action_claims set status='cancelled'")
        elif change == "lease": cur.execute("update app_private.oom_manager_cases set assigned_worker_id='WORKER',lease_until=now()+interval '1 minute'")
        elif change == "not_due": cur.execute("update app_private.oom_manager_cases set next_reassessment_at=now()+interval '1 minute'")
        elif change == "animal": cur.execute("update public.pigs set on_farm=false")
        elif change == "derived_pen": cur.execute("insert into public.pig_location_events(location_event_id,pig_id,move_date,to_pen_id) values('NEW-MOVE','SYNTHETIC-ANIMAL',current_date,'PEN-B')")
        elif change == "mating": cur.execute("insert into public.mating_events(mating_id,sow_pig_id,mating_date) values('NEW-MATING','SYNTHETIC-ANIMAL',current_date)")
        elif change == "litter": cur.execute("insert into public.litters(litter_id,sow_pig_id,farrowing_date) values('NEW-LITTER','SYNTHETIC-ANIMAL',current_date)")
        elif change == "related": cur.execute("""insert into app_private.oom_protected_action_claims(callback_token,action_kind,owner_user_id,
            private_chat_id,mission_id,provider_message_id,preview_digest,evidence_generation,preview_payload,expires_at)
            values('OTHER','mortality','9000','9000','OTHER','100','OTHER','OTHER','{}',now())""")
        elif change == "operation": cur.execute("""insert into public.pig_lifecycle_events(lifecycle_event_id,pig_id,lifecycle_event_type,
            effective_at,actor_reference,source_system,source_reference,idempotency_key) values('LIFE','SYNTHETIC-ANIMAL',
            'exited_farm',now(),'synthetic','owner','synthetic',%s)""", (c["preview_payload"]["operation_id"],))
    if change in {"source", "principal"}:
        source = deepcopy(p["preimage"]["source_history"][0]["record"])
        if change == "source": source["status"] = "contained"
        else: source["owner_user_id"] = source["chat_id"] = "9001"
        insert("public.sam_live_stock_conversation_review_events", {"review_event_id": "NEW-SOURCE", "event_source": correction.REPORT_SOURCE,
            "review_json": {"herdmaster_health_loss": source}, "created_at": datetime.now(timezone.utc)})
    elif change == "family":
        insert("public.sam_live_stock_conversation_review_events", {"review_event_id": "NEW-FAMILY", "event_source": correction.FAMILY_SOURCE,
            "review_json": {"family_message_lifecycle": {"mission_id": c["mission_id"], "state": "unknown"}}, "created_at": datetime.now(timezone.utc)})
    elif change == "welfare":
        occurred = datetime.now(timezone.utc) - timedelta(minutes=1)
        insert("public.pig_welfare_cases", {"welfare_case_id": "W", "pig_id": "SYNTHETIC-ANIMAL", "episode_key": "W",
            "concern_key": "mortality", "episode_started_at": occurred, "first_reported_at": occurred, "created_by": "owner",
            "source_system": "owner", "source_reference": "synthetic", "provenance_json": {}, "idempotency_key": "W"})
        insert("public.pig_welfare_case_events", {"welfare_case_event_id": "WC", "welfare_case_id": "W", "sequence_no": 1,
            "event_type": "closed", "case_state": "closed", "urgency": "urgent", "responsible_owner": "owner", "closure_kind": "death",
            "closure_reason": "synthetic", "occurred_at": occurred, "actor_reference": "owner", "source_system": "owner",
            "source_reference": "synthetic", "provenance_json": {}, "idempotency_key": "WC"})
    elif change == "history_overflow":
        for index in range(129):
            insert("app_private.oom_manager_case_events", {"event_id": f"SAFE-{index}", "case_id": "SYNTHETIC-CASE", "generation": 1,
                "event_type": "heartbeat", "event_payload": {}, "occurred_at": datetime.now(timezone.utc)})
    before = state()
    with pytest.raises(ValueError): apply(p, connect)
    assert state() == before


def test_postgres_competing_claim_attempt_is_seen_after_row_lock_wait(extension_database):
    p, connect, state, _insert = extension_database
    waiting = Event()
    class ObservedCursor:
        def __init__(self, cursor): self.cursor = cursor
        def __getattr__(self, name): return getattr(self.cursor, name)
        def __enter__(self): self.cursor.__enter__(); return self
        def __exit__(self, *args): return self.cursor.__exit__(*args)
        def execute(self, query, params=None):
            if "where callback_token=%s for update" in query: waiting.set()
            return self.cursor.execute(query, params)
    class ObservedConnection:
        def __init__(self): self.db = connect()
        def __getattr__(self, name): return getattr(self.db, name)
        def __enter__(self): self.db.__enter__(); return self
        def __exit__(self, *args): return self.db.__exit__(*args)
        def cursor(self): return ObservedCursor(self.db.cursor())
    with ThreadPoolExecutor(max_workers=1) as pool:
        with connect() as blocker, blocker.cursor() as cur:
            cur.execute("select callback_token from app_private.oom_protected_action_claims for update")
            cur.execute("update app_private.oom_protected_action_claims set delivery_attempt_id='COMPETING',delivery_attempted_at=now()")
            future = pool.submit(apply, p, ObservedConnection)
            assert waiting.wait(timeout=5)
        with pytest.raises(ValueError, match="claim_not_exact_unsent_correction"): future.result(timeout=10)
    assert not any(e["record"]["event_type"] == extension.EVENT_TYPE for e in state()["public.operational_events"])


def test_postgres_final_read_sees_source_append_with_repeatable_read_connection_default(extension_database, monkeypatch):
    from psycopg import IsolationLevel
    p, connect, state, insert = extension_database
    real_read = extension._read_material
    def concurrent_source_append(db):
        material = real_read(db)
        source = deepcopy(p["preimage"]["source_history"][0]["record"])
        source["status"] = "contained"
        insert("public.sam_live_stock_conversation_review_events", {"review_event_id": "DURING-MATERIAL",
            "event_source": correction.REPORT_SOURCE, "created_at": datetime.now(timezone.utc),
            "review_json": {"herdmaster_health_loss": source}})
        return material
    monkeypatch.setattr(extension, "_read_material", concurrent_source_append)
    def repeatable_connection():
        connection = connect()
        connection.db.isolation_level = IsolationLevel.REPEATABLE_READ
        return connection
    before = state()
    with pytest.raises(ValueError, match="source_history_changed"):
        apply(p, repeatable_connection)
    after = state()
    assert after["app_private.oom_protected_action_claims"] == before["app_private.oom_protected_action_claims"]
    assert after["public.operational_events"] == before["public.operational_events"]
