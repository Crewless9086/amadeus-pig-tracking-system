"""Production queries and protected previews against isolated PostgreSQL."""
from unittest.mock import Mock

import pytest

from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
from tests.test_oom_sakkie_retained_report_recovery_postgres import (
    URL, store, add_report, report,
)

pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL required")


@pytest.mark.parametrize("name", [None, "", "Renamed sow"])
@pytest.mark.parametrize("language", ["af", "en"])
def test_litter_selection_uses_stable_identity_not_display_name(store, monkeypatch, name, language):
    case = litter_case(store, language=language)
    with store() as db, db.cursor() as cur:
        cur.execute("update public.pigs set pig_name=%s where pig_id='SOW-A'", (name,))
        cur.execute("insert into public.litters values('L-A','SOW-A','2026-08-15','Active')")
        cur.execute("insert into public.litters values('L-OLD','SOW-A','2026-01-15','Weaned')")
        cur.execute("insert into public.litters values('L-LATER','SOW-A','2026-09-15','Active')")
    action = Mock(return_value=({"success": True, "pig_ids": ["P1", "P2"], "selected_piglets": []}, 200))
    claim = Mock(return_value={"callback_token": "SYNTHETIC", "preview_digest": "PREVIEW"})
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead", action)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.create_claim", claim)
    result = recovery.build_retained_protected_preview(case)
    assert result["success"] and result["confirmation_required"]
    assert not result["writes_farm_data"]
    assert "Linda" not in result["answer"]
    assert ("Werpsel L-A" if language == "af" else "Litter L-A") in result["answer"]
    assert action.call_args.args == ("L-A", "2026-08-19", "Unknown")
    assert action.call_args.kwargs == {"count": 2, "changed_by": "oom_sakkie", "dry_run": True}
    assert claim.call_args.kwargs["preview_payload"]["pig_ids"] == ["P1", "P2"]
    assert len(result["reply_markup"]["inline_keyboard"][0]) == 3


@pytest.mark.parametrize("litters", [[], [("L-X", "OTHER", "2026-08-15", "Active")],
    [("L-X", "SOW-A", "2026-08-15", "Weaned")],
    [("L-X", "SOW-A", "2026-08-20", "Active")],
    [("L-X", "SOW-A", "2026-08-15", "Active"), ("L-Y", "SOW-A", "2026-08-16", "Active")]])
def test_missing_wrong_inactive_future_or_ambiguous_litter_never_claims(store, monkeypatch, litters):
    case = litter_case(store)
    with store() as db, db.cursor() as cur:
        for values in litters:
            cur.execute("insert into public.litters values(%s,%s,%s,%s)", values)
    action, claim = Mock(), Mock()
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead", action)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.create_claim", claim)
    result = recovery.build_retained_protected_preview(case)
    assert result["status"] == "retained_litter_loss_active_litter_unproven"
    assert result["suppress_owner_delivery"]
    action.assert_not_called()
    claim.assert_not_called()


def litter_case(store, language="af"):
    source = report(output_language=language, owner_text_verbatim="Sow-A 2 kleintjies dood op 19 Aug",
        provider_timestamp="2026-08-20T10:00:00+00:00",
        preview={"evaluator": {"identity": {"resolved": True, "pig_id": "SOW-A"}}})
    add_report(store, source)
    return {"dedupe_key": "herdmaster:retained-litter-loss:101:2026-08-19",
        "evidence_digest": "SYNTHETIC", "evidence_refs": ["provider_message:101",
            "incident_date:2026-08-19", recovery.retained_report_binding([source])]}


from datetime import timedelta
from psycopg.types.json import Jsonb
from modules.oom_sakkie import herdmaster_case_disposition as disposition
from modules.oom_sakkie.general_manager_worker import (
    PostgresManagerCaseStore, normalize_candidate, deliver_farm_manager_case,
)
from tests.test_oom_sakkie_retained_report_recovery_postgres import retain, NOW


def advisory(store, *, status="Active", on_farm=True, key=None, refs=None):
    pig = "PIG-SYNTHETIC-A"
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.pigs(pig_id,tag_number,status,on_farm) values(%s,'A',%s,%s)",
                    (pig, status, on_farm))
    case = retain(store, key=key or "herdmaster:herdmaster:" + pig,
                  refs=refs or ["pig:" + pig, "synthetic:source"])
    return case


def collect_dispositions(store, **kwargs):
    return disposition.collect_advisory_dispositions(NOW, connect=lambda: store(True), **kwargs)


@pytest.mark.parametrize("status", ["Dead", "Sold", "Culled"])
def test_terminal_advisory_reconciles_existing_case_once_without_farm_or_provider_effect(store, status):
    case = advisory(store, status=status, on_farm=False)
    rows = collect_dispositions(store)
    assert len(rows) == 1 and rows[0]["terminal_state"] == "completed"
    manager = PostgresManagerCaseStore(connect_factory=store)
    candidate = normalize_candidate(rows[0], now=NOW)
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, candidate, NOW) == "changed"
        assert manager._reconcile(cur, candidate, NOW) == "replayed"
        cur.execute("select status,generation from app_private.oom_manager_cases where case_id=%s", (case["case_id"],))
        assert cur.fetchone() == ("completed", 2)
        cur.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type='completed'", (case["case_id"],))
        assert cur.fetchone()[0] == 1
        for table in ("pig_lifecycle_events", "oom_protected_action_claims", "pig_welfare_case_events"):
            cur.execute("select count(*) from " + ("app_private." if table.startswith("oom_") else "public.") + table)
            assert cur.fetchone()[0] == 0
    assert collect_dispositions(store) == []


@pytest.mark.parametrize("status,on_farm", [("Active", True), ("Dead", True), ("Active", False), ("Unknown", False)])
def test_unproved_exit_stays_open_without_owner_debugging_message(store, status, on_farm):
    case = advisory(store, status=status, on_farm=on_farm)
    row = collect_dispositions(store)[0]
    assert not row.get("terminal_state") and row["unknowns"]
    sent = Mock(side_effect=AssertionError("must not send technical reconciliation"))
    result = deliver_farm_manager_case(row, deliver=sent)
    assert result["success"] and result["telegram_sends"] == 0
    sent.assert_not_called()
    manager = PostgresManagerCaseStore(connect_factory=store)
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, normalize_candidate(row, now=NOW), NOW) == "changed"
    again = collect_dispositions(store)[0]
    assert normalize_candidate(row, now=NOW)["evidence_digest"] == normalize_candidate(again, now=NOW)["evidence_digest"]
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, normalize_candidate(again, now=NOW), NOW) == "replayed"


def test_disposition_cannot_close_new_generation_or_other_worker_lease(store):
    case = advisory(store, status="Sold", on_farm=False)
    stale = normalize_candidate(collect_dispositions(store)[0], now=NOW)
    manager = PostgresManagerCaseStore(connect_factory=store)
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set generation=2,evidence_digest=%s where case_id=%s", ("1" * 64, case["case_id"]))
        assert manager._reconcile(cur, stale, NOW) == "stale"
    fresh = normalize_candidate(collect_dispositions(store)[0], now=NOW)
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set assigned_worker_id='other',lease_until=%s where case_id=%s", (NOW + timedelta(minutes=4), case["case_id"]))
        assert manager._reconcile(cur, fresh, NOW) == "deferred"
        cur.execute("select status,generation from app_private.oom_manager_cases where case_id=%s", (case["case_id"],))
        assert cur.fetchone() == ("exception", 2)


def test_current_candidate_wins_and_crossed_identity_cannot_close(store):
    case = advisory(store, status="Sold", on_farm=False)
    assert collect_dispositions(store, current_keys={case["dedupe_key"]}) == []
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s where case_id=%s", (Jsonb(["pig:PIG-OTHER"]), case["case_id"]))
    assert collect_dispositions(store) == []


@pytest.mark.parametrize("tag", ["A", "OTHER"])
def test_withdrawal_advisory_retirement_requires_bound_canonical_identity(store, tag):
    advisory(store, status="Sold", on_farm=False, key="herdmaster:pig-" + tag + "-withdrawal-sales")
    row = collect_dispositions(store)[0]
    assert (row.get("terminal_state") == "completed") == (tag == "A")
    assert "eligibility" not in row["summary"]


def test_read_failure_is_not_terminal_absence(store):
    advisory(store, status="Sold", on_farm=False)
    def failed():
        raise TimeoutError("synthetic read outage")
    with pytest.raises(TimeoutError):
        disposition.collect_advisory_dispositions(NOW, connect=failed)


from copy import deepcopy
from pathlib import Path


def completed_observation(store):
    mission, operation, pig = "OOM-HERDMASTER-SYNTHETIC", "HERD-HEALTH-LOSS-SYNTHETIC", "PIG-SYNTHETIC-A"
    advisory(store, refs=["pig:" + pig, mission])
    binding = {"operation_id": operation, "authenticated_principal_id": "42", "confirmation_ready": True,
        "provider_message_id": "101", "preview_sha256": "PREVIEW", "evidence_generation": "GEN"}
    facts = {"observed": [{"fact": "standing", "value": True}]}
    source = report(mission=mission, status="completed", event_phase="recording_completed", operation_id=operation,
        preview={"confirmation_ready": True, "confirmation_binding": binding,
            "evaluator": {"identity": {"pig_id": pig, "resolved": True}, "canonical_effects": [
                {"supported": True, "area": "medical_observation", "facts": facts}]}},
        recording_result={"success": True, "operation_id": operation, "observation_event_id": "OBS-1"})
    canonical = {"operation_id": operation, "pig_id": pig, "provider_message_id": "101",
        "preview_sha256": "PREVIEW", "evidence_generation": "GEN", "facts": facts, "actor_id": "42"}
    with store() as db, db.cursor() as cur:
        migration = Path(__file__).parents[1] / "supabase/migrations/202607200001_create_pig_observation_events.sql"
        cur.execute(migration.read_text(encoding="utf-8"))
        cur.execute("""insert into public.pig_observation_events(observation_event_id,pig_id,observed_at,
            observer_reference,observation_category,factual_note,source_system,source_reference,idempotency_key)
            values('OBS-1',%s,%s,'42','welfare','Synthetic observed fact','owner',%s,%s)""",
            (pig, NOW - timedelta(days=2), disposition._digest(canonical), operation))
    return source


def test_completed_observation_requires_exact_canonical_effect(store):
    source = completed_observation(store)
    add_report(store, source)
    row = collect_dispositions(store)[0]
    assert row["terminal_state"] == "completed"
    assert "herdmaster_disposition:confirmed_observation_recorded" in row["evidence_refs"]
    assert "advisory_proof_mission:" + source["mission_id"] in row["evidence_refs"]
    assert "advisory_proof_operation:" + source["operation_id"] in row["evidence_refs"]
    assert "advisory_proof_observation:OBS-1" in row["evidence_refs"]
    assert any(ref.startswith("advisory_proof_source_sha256:") for ref in row["evidence_refs"])


@pytest.mark.parametrize("change", ["wrong_operation", "wrong_observation", "wrong_pig", "not_completed",
    "correction", "unconfirmed", "cross_principal", "newer_question", "superseded_source", "superseded_effect"])
def test_completed_prose_cannot_replace_proven_effect(store, change):
    source = completed_observation(store)
    if change == "wrong_operation": source["recording_result"]["operation_id"] = "OTHER"
    if change == "wrong_observation": source["recording_result"]["observation_event_id"] = "OTHER"
    if change == "wrong_pig": source["preview"]["evaluator"]["identity"]["pig_id"] = "PIG-OTHER"
    if change == "not_completed": source["status"] = "waiting_for_input"
    if change == "correction": source["correction_digest"] = "CORRECTED"
    if change == "unconfirmed": source["preview"]["confirmation_ready"] = False
    if change == "cross_principal": source["chat_id"] = "99"
    add_report(store, source)
    if change in {"newer_question", "superseded_source"}:
        later = deepcopy(source)
        later.update(mission_id="OOM-HERDMASTER-LATER", status="waiting_for_input")
        if change == "superseded_source":
            later["preview"]["evaluator"]["identity"]["pig_id"] = ""
            later["superseded_duplicate_missions"] = [source["mission_id"]]
        add_report(store, later, at=NOW)
    if change == "superseded_effect":
        with store() as db, db.cursor() as cur:
            cur.execute("""insert into public.pig_observation_events(observation_event_id,pig_id,observed_at,
                observer_reference,observation_category,factual_note,source_system,idempotency_key,supersedes_observation_event_id)
                values('OBS-2','PIG-SYNTHETIC-A',%s,'42','welfare','Synthetic correction','owner','CORRECTION','OBS-1')""", (NOW,))
    assert not collect_dispositions(store)[0].get("terminal_state")


def unresolved_report():
    return report(owner_text_verbatim="Vark nr 27 dood op 19 Aug 2026",
        provider_timestamp="2026-08-20T10:00:00+00:00", preview={"evaluator": {
            "status": "identity_required", "event_family": "unknown",
            "identity": {"resolved": False, "pig_id": "", "tag_number": ""}}})


def identity_evidence():
    return {"evidence_generation": "GEN", "as_of_timestamp": NOW.isoformat(),
        "animals": [{"pig_id": "P27", "tag_number": "27", "name": "", "on_farm": True,
                     "lifecycle_status": "Active", "birth_date": "2026-01-01"}], "matings": [], "litters": []}


def test_original_unresolved_identity_uses_current_evaluator_without_altering_report(store, monkeypatch):
    from tests.test_oom_sakkie_retained_report_recovery_postgres import collect
    source = unresolved_report()
    original = deepcopy(source)
    add_report(store, source)
    retain(store, refs=["provider_message:101", "pig:P27", "tag:27", recovery.retained_report_binding([source])])
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
                        lambda **kwargs: identity_evidence())
    rows = collect(store)
    assert len(rows) == 1
    assert "retained_identity_reassessment:required" in rows[0]["evidence_refs"]
    assert "pig:P27" in rows[0]["evidence_refs"]
    assert source == original and not rows[0].get("terminal_state")
    # The actual preview boundary repeats source checks, preserving its report.
    payloads, failure = recovery._validated_report_case(rows[0], ["101"])
    assert not failure and payloads == [original]


@pytest.mark.parametrize("kind", ["contrary_family", "resolved_other", "prohibited", "ambiguous", "wrong_current_tag", "changed_text", "cancelled"])
def test_retained_reassessment_never_overrides_contrary_or_changed_evidence(store, monkeypatch, kind):
    from tests.test_oom_sakkie_retained_report_recovery_postgres import collect
    source = unresolved_report()
    if kind == "contrary_family": source["preview"]["evaluator"]["event_family"] = "welfare_update"
    if kind == "resolved_other": source["preview"]["evaluator"]["identity"] = {"resolved": True, "pig_id": "P-OTHER"}
    if kind == "prohibited": source["semantic_interpretation"] = {"recording_prohibited": True}
    add_report(store, source)
    retain(store, refs=["provider_message:101", "pig:P27", "tag:27", recovery.retained_report_binding([source])])
    evidence = identity_evidence()
    if kind == "ambiguous": evidence["animals"].append({**evidence["animals"][0], "pig_id": "P-OTHER"})
    if kind == "wrong_current_tag": evidence["animals"][0]["tag_number"] = "OTHER"
    if kind in {"changed_text", "cancelled"}:
        latest = deepcopy(source)
        latest.update({"owner_text_verbatim": "Pig 27 alive"} if kind == "changed_text" else {"status": "contained"})
        add_report(store, latest, at=NOW)
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
                        lambda **kwargs: evidence)
    assert collect(store) == []


@pytest.mark.parametrize("fault", ["", "missing_original", "late_original", "missing_card", "wrong_card_owner", "ambiguous_original", "wrong_packet", "other_principal", "same_principal_older"])
def test_legacy_packet_requires_exact_delivered_asof_source_and_verified_effect(store, fault):
    source = completed_observation(store)
    observed = NOW - timedelta(days=2)
    refs = ["HERD-NEXT-" + "A" * 24, "HERD-WEEK-" + "B" * 32,
        "result:HERD-NEXT-" + "A" * 24 + ":HERD-DAILY-EVIDENCE-SYNTHETIC",
        "observed:" + observed.isoformat()]
    if fault == "wrong_packet": refs[0] = "UNRELATED"
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s", (Jsonb(refs),))
    original = deepcopy(source)
    original.update(status="waiting_for_input", event_phase="preview_generated", operation_id="", recording_result={})
    original["preview"]["evaluator"]["smallest_missing_follow_up_question"] = "Is the animal standing?"
    original_at = observed + timedelta(minutes=1) if fault == "late_original" else observed - timedelta(minutes=10)
    if fault != "missing_original": add_report(store, original, at=original_at)
    if fault == "ambiguous_original":
        add_report(store, {**original, "mission_id": "OOM-HERDMASTER-OTHER"}, at=original_at)
    if fault in {"other_principal", "same_principal_older"}:
        prior = deepcopy(original)
        prior["mission_id"] = "OOM-HERDMASTER-OLDER"
        if fault == "other_principal":
            prior.update(owner_user_id="99", chat_id="99")
        add_report(store, prior, at=original_at - timedelta(minutes=1))
    add_report(store, source, at=observed + timedelta(minutes=10))
    if fault != "missing_card":
        with store() as db, db.cursor() as cur:
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json,created_at) values('CARD',%s,%s,%s)""",
                ('oom_sakkie_family_message_lifecycle', Jsonb({"family_message_lifecycle": {
                    "card_mission_id": source["mission_id"], "state": "delivered", "telegram_message_id": "CARD-1",
                    "owner_user_id": "99" if fault == "wrong_card_owner" else "42", "chat_id": "42"}}),
                 observed - timedelta(minutes=9)))
    row = collect_dispositions(store)[0]
    assert (row.get("terminal_state") == "completed") == (fault in {"", "same_principal_older"})
    assert ("advisory_source_observed:" + observed.isoformat() in row["evidence_refs"]) == (fault != "wrong_packet")


def test_whole_herd_composition_retains_exact_question_and_card_provenance():
    from modules.oom_sakkie.farm_manager_runtime import _whole_herd_specialist_result
    canonical = {"generated_at": NOW.isoformat(), "worklist_id": "HERD-WEEK-SYNTHETIC", "tasks": [], "cases": []}
    active = [{"pig_id": "PIG-SYNTHETIC-A", "tag_number": "A", "lifecycle_id": "OOM-HERDMASTER-SYNTHETIC",
        "state": "waiting_for_input", "card_message_id": "CARD-1", "current_question": "Is A standing?",
        "provider_timestamp": (NOW - timedelta(hours=1)).isoformat()}]
    result = _whole_herd_specialist_result(canonical, [], active, NOW)
    item = next(item for item in result.work_items if item.dedupe_key == "herdmaster:PIG-SYNTHETIC-A")
    assert "OOM-HERDMASTER-SYNTHETIC" in item.provenance.source_refs
    assert "telegram-card-CARD-1" in item.provenance.source_refs
    assert result.result_id in item.provenance.source_refs
    assert item.provenance.result_id == result.result_id


def test_unresolved_identity_recovers_date_number_without_selecting_it_as_pig(store):
    evidence = identity_evidence()
    evidence["animals"].append({**evidence["animals"][0], "pig_id": "P19", "tag_number": "19"})
    source = unresolved_report()
    identity = recovery.reassess_retained_mortality_identity(source, evidence)
    assert identity["pig_id"] == "P27" and identity["tag_number"] == "27"


@pytest.mark.parametrize("race", [False, True])
def test_full_cycles_complete_advisory_once_without_dispatch(store, race):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    import threading
    case = advisory(store, status="Sold", on_farm=False)
    now = datetime.now(timezone.utc)
    rows = disposition.collect_advisory_dispositions(now, connect=lambda: store(True))
    forbidden = Mock(side_effect=AssertionError("completed advisory must not dispatch"))
    barrier = threading.Barrier(2) if race else None
    def cycle():
        if barrier:
            barrier.wait(timeout=5)
        return PostgresManagerCaseStore(connect_factory=store).run_cycle(rows, now=now,
            source_revision="test-disposition", refresh=forbidden, deliver=forbidden)
    if race:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: cycle(), range(2)))
    else:
        results = [cycle(), cycle()]
    assert all(result["status"] == "general_manager_cycle_completed" for result in results)
    forbidden.assert_not_called()
    with store() as db, db.cursor() as cur:
        cur.execute("select status,generation from app_private.oom_manager_cases where case_id=%s", (case["case_id"],))
        assert cur.fetchone() == ("completed", 2)
        cur.execute("select event_type from app_private.oom_manager_case_events where case_id=%s", (case["case_id"],))
        assert cur.fetchall() == [("completed",)]
        for table in ("pig_lifecycle_events", "oom_protected_action_claims", "pig_welfare_case_events"):
            cur.execute("select count(*) from " + ("app_private." if table.startswith("oom_") else "public.") + table)
            assert cur.fetchone()[0] == 0


def test_locked_new_generation_survives_stale_full_cycle(store):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    import threading
    case = advisory(store, status="Sold", on_farm=False)
    now = datetime.now(timezone.utc)
    stale = disposition.collect_advisory_dispositions(now, connect=lambda: store(True))
    started = threading.Event()
    forbidden = Mock(side_effect=AssertionError("newer not-due advisory must not dispatch"))
    def cycle():
        started.set()
        return PostgresManagerCaseStore(connect_factory=store).run_cycle(stale, now=now,
            source_revision="test-disposition", refresh=forbidden, deliver=forbidden)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with store() as db, db.cursor() as cur:
            cur.execute("select case_id from app_private.oom_manager_cases where case_id=%s for update", (case["case_id"],))
            future = pool.submit(cycle)
            assert started.wait(timeout=5)
            cur.execute("""update app_private.oom_manager_cases set generation=2,evidence_digest=%s,
                summary='Newer specialist evidence',next_reassessment_at=%s where case_id=%s""",
                ("1" * 64, now + timedelta(hours=1), case["case_id"]))
        assert future.result(timeout=15)["status"] == "general_manager_cycle_completed"
    forbidden.assert_not_called()
    with store() as db, db.cursor() as cur:
        cur.execute("select status,generation,summary from app_private.oom_manager_cases where case_id=%s", (case["case_id"],))
        assert cur.fetchone() == ("exception", 2, "Newer specialist evidence")
        cur.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type='completed'", (case["case_id"],))
        assert cur.fetchone()[0] == 0


def test_disposition_budget_stops_queries_after_elapsed_deadline(store, monkeypatch):
    advisory(store, status="Sold", on_farm=False)
    clock = iter([0, 1, 7])
    monkeypatch.setattr(disposition.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError, match="herdmaster_disposition_read_deadline"):
        collect_dispositions(store)
    with store() as db, db.cursor() as cur:
        cur.execute("select status,generation from app_private.oom_manager_cases")
        assert cur.fetchone() == ("exception", 1)
