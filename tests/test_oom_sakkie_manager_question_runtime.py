from datetime import datetime, timedelta, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.manager_question_runtime import (
    handle_manager_question_reply, load_active_manager_question,
    semantic_context_with_manager_question)
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation
from modules.oom_sakkie.bounded_postgres_read import (
    connect_bounded_read, is_database_unavailable)
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from unittest.mock import patch
import pytest

NOW = datetime(2026, 8, 12, 6, 5, tzinfo=timezone.utc)
OWNER = "5721652188"


def parsed(text="They are eating, drinking and moving normally", *, message="3530",
           reply="3529", at=NOW):
    return {"text": text, "telegram_user_id": OWNER, "telegram_chat_id": OWNER,
            "provider_message_id": message, "provider_timestamp": at.isoformat(),
            "reply_to_message_id": reply}


def question(at=NOW-timedelta(minutes=5)):
    return {"daily_identity": "OOM-DAILY-FARM-MANAGER-2026-08-12",
        "telegram_message_id": "3529", "presented_at": at.isoformat(),
        "question": "Are the surviving littermates eating, drinking and moving normally?",
        "question_binding": {"task_id": "MORTALITY-1",
            "dedupe_key": "herdmaster:mortality-current-assessment", "domain": "herd"}}


def semantic(language="en", *, continuation=True, domain="herd_health"):
    return SemanticInterpretation(domain=domain, intent="group_welfare_follow_up",
        message_kind="observation", continuation=continuation,
        observation="Surviving littermates are eating, drinking and moving normally.",
        language=language, confidence=.98)


def memory():
    rows = {}
    def store(identity, record):
        created = identity not in rows
        if created:
            rows[identity] = record
        return {"success": True, "created": created, "record": rows[identity]}
    store.rows = rows
    return store


def test_exact_reply_binds_group_evidence_and_replay_is_silent():
    store = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, status = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=store)
    replay, replay_status = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=store)
    assert status == replay_status == 200
    assert first["status"] == "manager_question_reply_recorded"
    assert first["writes_farm_data"] is False and len(store.rows) == 1
    recorded = next(iter(store.rows.values()))
    assert recorded["dedupe_key"] == "herdmaster:mortality-current-assessment"
    assert "littermates" in recorded["semantic_facts"]["observation"].lower()
    assert replay["status"] == "manager_question_reply_replay_suppressed"
    assert replay["suppress_owner_delivery"] is True and replay["answer"] == ""


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_morning_card_rootline_update_records_manager_receipt_before_canonical_dispatch(dispatch):
    downstream = ({"handled": True, "success": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "ROOTLINE-1", "card_mission_id": "ROOTLINE-1",
        "answer": "Water evidence retained; ROOTLINE will reassess.",
        "writes_farm_data": True, "canonical_observation": {"success": True, "readback": [
            {"kind":"storage","fraction":[4,4],"state":"FULL","provider_message_id":"3600","observed_at":NOW.isoformat()},
            {"kind":"reservoir","fraction":[4,4],"state":"FULL","provider_message_id":"3600","observed_at":NOW.isoformat()}]},
        "hardware_commands": 0}, 200)
    card = {"daily_identity": "OOM-DAILY-FARM-MANAGER-2026-08-15",
        "telegram_message_id": "3599", "presented_at": NOW.isoformat(),
        "question": "Contextual update to the delivered morning farm plan",
        "question_binding": {"task_id": "OOM-DAILY-FARM-MANAGER-2026-08-15:contextual-update",
            "dedupe_key": "OOM-DAILY-FARM-MANAGER-2026-08-15:contextual-update",
            "domain": "rootline", "contextual_card_recovery": True}}
    rootline = SemanticInterpretation(domain="rootline", intent="water_observation",
        message_kind="observation", continuation=True,
        observation="Reservoir 4/4, storage 4/4, and C Camp needs water.",
        observation_facts=({"subject": "reservoir", "numerator": 4, "denominator": 4},
            {"subject": "storage_tanks", "numerator": 4, "denominator": 4}), confidence=.99)
    inbound = parsed("Reservoir is 4/4 and Storage is 4/4. C Camp needs water",
        message="3600", reply="")
    inbound["semantic"] = rootline.as_hint()
    state = memory()
    def after_claim(*_args, **_kwargs):
        assert len(state.rows) == 1
        assert next(iter(state.rows.values()))["status"] == "dispatch_claimed"
        return downstream
    dispatch.side_effect = after_claim
    value, status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline,
        question=card, event_store=state, event_loader=lambda key: state.rows.get(key, {}))
    receipt = next(row for row in state.rows.values() if row["status"] == "recorded")
    assert status == 200 and value["manager_question_status"] == "manager_question_reply_recorded"
    assert receipt["manager_card_message_id"] == "3599"
    assert receipt["provider_message_id"] == "3600"
    assert len(state.rows) == 2
    assert len(receipt["semantic_facts"]["observation_facts"]) == 2
    replay, replay_status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline,
        question=card, event_store=state, event_loader=lambda key: state.rows.get(key, {}))
    assert replay_status == 200
    assert replay["manager_question_status"] == "manager_question_reply_replay_recovered"
    assert replay["answer"] == "" and replay["suppress_owner_delivery"] is True
    dispatch.assert_called_once()
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    lifecycle = []
    def lifecycle_store(action, identity, payload):
        if action == "load":
            return [row for row in lifecycle if row.get("card_mission_id") == identity]
        created = not any(row.get("event_id") == identity for row in lifecycle)
        if created:
            lifecycle.append(dict(payload))
        return {"success": True, "created": created}
    sends = []
    def sender(_chat, _text):
        sends.append(True)
        return {"success": True, "telegram_message_id": "3601",
            "provider_timestamp": NOW.isoformat()}
    first_delivery = deliver_family_result(inbound, value, specialist="ROOTLINE",
        mission_id=value["mission_id"], card_mission_id=value["card_mission_id"],
        event_store=lifecycle_store, sender=sender)
    replay_delivery = deliver_family_result(inbound, replay, specialist="ROOTLINE",
        mission_id=replay["mission_id"], card_mission_id=replay["card_mission_id"],
        event_store=lifecycle_store, sender=sender)
    assert first_delivery["telegram_sends"] == 1
    assert replay_delivery["telegram_sends"] == replay_delivery["telegram_edits"] == 0
    assert len(sends) == 1


def rootline_question(at=NOW-timedelta(minutes=5)):
    return {"daily_identity": "OOM-DAILY-FARM-MANAGER-2026-08-12",
        "telegram_message_id": "3529", "presented_at": at.isoformat(),
        "question": "What is the current reservoir level?",
        "question_binding": {"task_id": "ROOTLINE-TANK-1",
            "dedupe_key": "rootline:reservoir-level", "domain": "rootline"}}


def rootline_semantic(text="Reservoir is full"):
    return SemanticInterpretation(domain="manager_round", intent="manager_question_reply",
        message_kind="observation", continuation=True, observation=text,
        language="en", confidence=.98)


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_exact_reservoir_full_is_typed_written_read_back_then_acknowledged_once(dispatch):
    canonical = {"success": True, "readback": [{"kind": "reservoir",
        "fraction": [1, 1], "state": "FULL", "provider_message_id": "3530",
        "observed_at": "2026-08-12T06:05:00Z"}]}
    dispatch.return_value = ({"handled": True, "success": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-1", "card_mission_id": "OOM-ROOTLINE-1",
        "answer": "Reservoir FULL recorded after canonical readback.",
        "writes_farm_data": True, "canonical_observation": canonical,
        "hardware_commands": 0}, 200)
    state = memory(); inbound = parsed("Reservoir is full")
    first, status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline_semantic(),
        question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}))
    replay, replay_status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline_semantic(),
        question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}))
    typed = dispatch.call_args.args[0]["semantic"]["observation_facts"]
    assert typed == ({"subject": "reservoir", "state": "FULL"},)
    assert status == 200 and first["answer"].endswith("canonical readback.")
    assert first["manager_question_status"] == "manager_question_reply_recorded"
    assert replay_status == 200 and replay["manager_question_status"] == "manager_question_reply_replay_recovered"
    assert replay["answer"] == "" and replay["suppress_owner_delivery"] is True
    dispatch.assert_called_once()


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_ambiguous_or_wrong_or_stale_rootline_card_never_writes_or_claims(dispatch):
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    ambiguous, status = handle_manager_question_reply(parsed("it is full"), authority,
        rootline_semantic("it is full"), question=rootline_question(), event_store=state)
    inferred = SemanticInterpretation(domain="rootline", intent="water_levels_observed",
        message_kind="observation", continuation=True, observation="it is full",
        observation_facts=({"subject":"reservoir","state":"FULL"},), confidence=.99)
    inferred_result, inferred_status = handle_manager_question_reply(parsed("it is full"), authority,
        inferred, question=rootline_question(), event_store=state)
    wrong, _ = handle_manager_question_reply(parsed("Reservoir is full", reply="9999"), authority,
        rootline_semantic(), question=rootline_question(), event_store=state)
    stale, _ = handle_manager_question_reply(parsed("Reservoir is full"), authority,
        rootline_semantic(), question=rootline_question(NOW-timedelta(days=2)), event_store=state)
    assert status == 409 and ambiguous["status"] == "manager_question_rootline_observation_ambiguous"
    assert inferred_status == 409 and inferred_result["status"] == "manager_question_rootline_observation_ambiguous"
    assert ambiguous["answer"] == "Which is full: the reservoir or the storage tanks?"
    assert wrong["handled"] is False and stale["handled"] is False
    assert state.rows == {}
    dispatch.assert_not_called()


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_typed_write_failure_and_readback_mismatch_are_not_acknowledged_and_provider_retry_owns_recovery(dispatch):
    failure = ({"handled": True, "success": False, "status": "contained",
        "systemic_exception": "rootline_canonical_observation_bridge_failed",
        "answer": "ROOTLINE could not prove canonical readback.",
        "writes_farm_data": False, "canonical_observation": {"success": False,
            "status": "tank_observation_write_failed"}, "hardware_commands": 0}, 503)
    mismatch = ({"handled": True, "success": False, "status": "contained",
        "systemic_exception": "rootline_canonical_observation_bridge_failed",
        "answer": "ROOTLINE could not prove canonical readback.",
        "writes_farm_data": True, "canonical_observation": {"success": True,
            "status": "recorded", "readback": [{"kind":"storage","fraction":[1,1],
                "state":"FULL","provider_message_id":"WRONG","observed_at":NOW.isoformat()}]},
        "hardware_commands": 0}, 503)
    success = ({"handled": True, "success": True, "status": "specialist_accepted",
        "specialist_identity": "ROOTLINE", "mission_id": "OOM-ROOTLINE-1",
        "card_mission_id": "OOM-ROOTLINE-1", "answer": "Reservoir FULL recorded.",
        "writes_farm_data": False, "canonical_observation": {"success": True,
            "readback": [{"kind": "reservoir", "fraction": [1, 1], "state": "FULL",
                "provider_message_id": "3530", "observed_at": NOW.isoformat()}]},
        "hardware_commands": 0}, 200)
    dispatch.side_effect = [failure, mismatch, success]
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    inbound = parsed("Reservoir is full")
    first, first_status = handle_manager_question_reply(inbound, authority,
        rootline_semantic(), question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}))
    second, second_status = handle_manager_question_reply(inbound, authority,
        rootline_semantic(), question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}))
    recovered, recovered_status = handle_manager_question_reply(inbound, authority,
        rootline_semantic(), question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}))
    assert first_status == second_status == 503
    assert first["manager_question_status"] == second["manager_question_status"] == "manager_question_rootline_retry_owned"
    assert "recorded against" not in first["answer"]
    assert "not recorded" in second["answer"]
    assert first["retry_owner"] == second["retry_owner"] == "same_provider_message_identity"
    assert recovered_status == 200 and recovered["manager_question_status"] == "manager_question_reply_recorded"
    assert recovered["answer"] == "Reservoir FULL recorded."
    assert dispatch.call_count == 3

    mismatch_state = memory()
    dispatch.reset_mock(); dispatch.side_effect = None; dispatch.return_value = mismatch
    mismatched, mismatch_status = handle_manager_question_reply(inbound, authority,
        rootline_semantic(), question=rootline_question(), event_store=mismatch_state,
        event_loader=lambda key: mismatch_state.rows.get(key, {}))
    assert mismatch_status == 503
    assert mismatched["manager_question_status"] == "manager_question_rootline_retry_owned"


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_repeated_provider_failures_end_in_precise_containment_not_false_in_progress(dispatch):
    dispatch.return_value = ({"handled": True, "success": False, "status": "contained",
        "answer": "unproven", "writes_farm_data": False,
        "canonical_observation": {"success": False}, "hardware_commands": 0}, 503)
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    inbound = parsed("Reservoir is full")
    results = [handle_manager_question_reply(inbound, authority, rootline_semantic(),
        question=rootline_question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {})) for _ in range(9)]
    assert all(status == 503 for _, status in results)
    assert results[-1][0]["status"] == "manager_question_rootline_retry_exhausted"
    assert "not recorded" in results[-1][0]["answer"]
    assert results[-1][0]["retry_owner"] == "rootline_technical_recovery"
    assert dispatch.call_count == 8


@patch("modules.oom_sakkie.operational_specialist_intake.handle_operational_specialist_message")
def test_rootline_success_manager_receipt_failure_retains_identity_and_replay_is_silent(dispatch):
    first_downstream = {"handled": True, "success": True, "status": "specialist_accepted",
        "specialist_identity": "ROOTLINE", "mission_id": "ROOTLINE-2",
        "card_mission_id": "ROOTLINE-2", "answer": "Evidence retained.",
        "writes_farm_data": True, "canonical_observation": {"success": True, "readback": [
            {"kind":"storage","fraction":[4,4],"state":"FULL","provider_message_id":"3600","observed_at":NOW.isoformat()},
            {"kind":"reservoir","fraction":[4,4],"state":"FULL","provider_message_id":"3600","observed_at":NOW.isoformat()}]},
        "hardware_commands": 0}
    dispatch.return_value = (first_downstream, 200)
    card = {"daily_identity": "OOM-DAILY-FARM-MANAGER-2026-08-15",
        "telegram_message_id": "3599", "presented_at": NOW.isoformat(),
        "question": "Contextual update to the delivered morning farm plan",
        "question_binding": {"task_id": "OOM-DAILY-FARM-MANAGER-2026-08-15:contextual-update",
            "dedupe_key": "OOM-DAILY-FARM-MANAGER-2026-08-15:contextual-update", "domain": "rootline"}}
    rootline = SemanticInterpretation(domain="rootline", intent="water_levels_observed",
        message_kind="observation", continuation=True,
        observation="Reservoir 4/4 and storage 4/4",
        observation_facts=({"subject":"reservoir","numerator":4,"denominator":4},
            {"subject":"storage_tanks","numerator":4,"denominator":4}), confidence=.99)
    inbound = parsed("Reservoir 4/4 and storage 4/4", message="3600", reply="")
    inbound["semantic"] = rootline.as_hint()
    state = memory(); attempts = {"count": 0}
    def recovering_store(identity, record):
        attempts["count"] += 1
        if attempts["count"] == 2:
            return {"success": False, "created": False}
        return state(identity, record)
    failed, failed_status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline,
        question=card, event_store=recovering_store, event_loader=lambda _key: {})
    replay, replay_status = handle_manager_question_reply(inbound,
        issue_gateway_owner_authority(OWNER, OWNER), rootline,
        question=card, event_store=recovering_store, event_loader=lambda key: state.rows.get(key, {}))
    assert failed_status == 503 and failed["downstream_retention_possible"] is True
    assert failed["specialist_identity"] == "ROOTLINE"
    assert failed["mission_id"] == failed["card_mission_id"] == "ROOTLINE-2"
    assert "ROOTLINE retained" in failed["answer"] and "Nothing was applied" not in failed["answer"]
    assert replay_status == 200 and replay["manager_question_status"] == "manager_question_reply_recorded"
    assert replay["answer"] == "Evidence retained."
    assert len(state.rows) == 3 and dispatch.call_count == 1


def test_afrikaans_non_reply_continuation_binds_same_active_question():
    value, status = handle_manager_question_reply(
        parsed("Hulle eet, drink en beweeg normaal", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER), semantic("af"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is True
    assert value["specialist_identity"] == "HERDMASTER"


def test_herd_question_claims_then_requires_herdmaster_consumption_before_retirement():
    state = memory()
    downstream = {"handled": True, "success": True,
        "status": "health_loss_follow_up_retained", "specialist_identity": "HERDMASTER",
        "mission_id": "OOM-HERDMASTER-PRINCE", "card_mission_id": "OOM-HERDMASTER-PRINCE",
        "answer": "HERDMASTER retained the attributable welfare update.",
        "writes_farm_data": False, "hardware_commands": 0}
    calls = []
    def dispatch(inbound, _authority):
        calls.append(inbound["provider_message_id"])
        assert next(iter(state.rows.values()))["status"] == "dispatch_claimed"
        return downstream, 200
    value, status = handle_manager_question_reply(parsed(
        "Prince is improving and eating again"),
        issue_gateway_owner_authority(OWNER, OWNER), semantic(),
        question=question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}),
        herdmaster_dispatcher=dispatch)
    assert status == 200
    assert value["manager_question_status"] == "manager_question_reply_recorded"
    assert value["specialist_identity"] == "HERDMASTER"
    assert [row["status"] for row in state.rows.values()] == ["dispatch_claimed", "recorded"]
    assert calls == ["3530"]


def test_herd_question_is_not_retired_when_herdmaster_does_not_consume_it():
    state = memory()
    value, status = handle_manager_question_reply(parsed(
        "Prince is improving and eating again"),
        issue_gateway_owner_authority(OWNER, OWNER), semantic(),
        question=question(), event_store=state,
        event_loader=lambda key: state.rows.get(key, {}),
        herdmaster_dispatcher=lambda *_: ({"handled": False, "success": False}, 200))
    assert status == 503
    assert value["status"] == "manager_question_herdmaster_retry_owned"
    assert value["retry_owner"] == "same_provider_message_identity"
    assert [row["status"] for row in state.rows.values()] == ["dispatch_claimed", "retry_owned"]


def test_unrelated_direct_specialist_request_is_not_stolen_by_manager_question():
    value, status = handle_manager_question_reply(
        parsed("What is today's irrigation plan?", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER),
        semantic(continuation=False, domain="rootline"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_manager_question_rejects_authority_not_bound_to_provider_principal():
    value, status = handle_manager_question_reply(parsed(),
        issue_gateway_owner_authority("99", "99"), semantic(),
        question=question(), event_store=lambda *_: pytest.fail("must not persist"))
    assert status == 403 and value["status"] == "manager_question_authority_denied"
    assert value["writes_farm_data"] is False


def test_unrelated_direct_request_replying_to_plan_card_is_not_stolen():
    value, status = handle_manager_question_reply(
        parsed("What is today's irrigation plan?", reply="3529"),
        issue_gateway_owner_authority(OWNER, OWNER),
        semantic(continuation=False, domain="rootline"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_protected_grouped_breeding_update_outranks_active_herd_question():
    direct = SemanticInterpretation(domain="herd_management", intent="breeding_update",
        message_kind="observation", continuation=True,
        breeding_actions=({"action":"exposure","animal_ref":"Sophie","boar_ref":"Bola",
                           "exposure_started_on":"2026-08-12","planned_days":17},),
        protected_preview_required=True, recording_prohibited=True,
        language="en", confidence=.99)
    value, status = handle_manager_question_reply(
        parsed("Sophie was placed with Bola; preview only", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER), direct,
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_stale_or_mismatched_reply_does_not_bind():
    rows = lambda _owner, _chat: [question(NOW-timedelta(days=2))]
    assert load_active_manager_question(parsed(), loader=rows) is None
    assert load_active_manager_question(parsed(reply="9999"),
        loader=lambda _owner, _chat: [question()]) is None


def test_context_database_failure_is_explicit_not_silent_no_question():
    value = load_active_manager_question(
        parsed(), loader=lambda *_: (_ for _ in ()).throw(TimeoutError("database")))
    assert value == {"load_unavailable": True, "load_failure_class": "TimeoutError"}


def test_bounded_read_sets_acquisition_query_and_lock_deadlines():
    calls = []
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,value,*_args):statements.append(value)
    class Connection:
        def cursor(self):return Cursor()
    connection = Connection()
    result = connect_bounded_read(database_url="postgresql://example", connect=lambda *a, **kw:
                                  calls.append((a, kw)) or connection)
    assert result is connection
    assert calls[0][1]["connect_timeout"] == 3
    assert "default_transaction_read_only=on" in calls[0][1]["options"]
    assert "statement_timeout=3000" in calls[0][1]["options"]
    assert "lock_timeout=1000" in calls[0][1]["options"]
    assert statements==[]


def test_bounded_read_has_hard_wall_clock_deadline_and_late_cleanup():
    import time
    from modules.oom_sakkie import bounded_postgres_read as bounded
    late = type("Late", (), {"closed": False,
        "close": lambda self: setattr(self, "closed", True)})()
    started = time.monotonic()
    with pytest.raises(bounded.RootlineConnectionDeadlineExceeded):
        bounded.connect_bounded_read(database_url="postgresql://stalled",
            connect=lambda *_args, **_kwargs: (time.sleep(.08), late)[1],
            connect_deadline_seconds=.02)
    assert time.monotonic() - started < .06
    deadline = time.monotonic() + .3
    while not late.closed and time.monotonic() < deadline:
        time.sleep(.01)
    assert late.closed is True


def test_bounded_write_uses_same_deadlines_without_read_only_mode():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres
    calls=[]
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,value,*_args):statements.append(value)
    class Connection:
        def cursor(self):return Cursor()
    connect_bounded_postgres(database_url="postgresql://example",
        connect=lambda *a,**kw:calls.append((a,kw)) or Connection())
    assert calls[0][1]["connect_timeout"]==3
    assert "statement_timeout=3000" in calls[0][1]["options"]
    assert "lock_timeout=1000" in calls[0][1]["options"]
    assert "default_transaction_read_only" not in calls[0][1]["options"]
    assert statements==[]


def test_bounded_session_setup_failure_rolls_back_and_closes():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,_value,*_args):raise RuntimeError("session setup failed")
    class Connection:
        rolled_back=False;closed=False
        def cursor(self):return Cursor()
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
    connection=Connection()
    try:
        connect_bounded_rootline_postgres(database_url="postgresql://example",
            connect=lambda *_args,**_kwargs:connection)
        raise AssertionError("setup failure was not propagated")
    except RuntimeError as exc:
        assert str(exc)=="session setup failed"
    assert connection.rolled_back is True and connection.closed is True


def test_rootline_pooled_session_enforces_transaction_local_deadlines():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,value,*_args):statements.append(value)
    class Connection:
        def cursor(self):return Cursor()
    connect_bounded_rootline_postgres(database_url="postgresql://example",
        connect=lambda *_args,**_kwargs:Connection())
    assert statements==["set transaction read only",
        "set local statement_timeout='3000ms'","set local lock_timeout='1000ms'"]


def test_rootline_connection_acquisition_has_real_wall_clock_deadline_and_late_cleanup():
    import threading
    import time
    from modules.oom_sakkie.bounded_postgres_read import (
        RootlineConnectionDeadlineExceeded, connect_bounded_rootline_postgres,
    )
    finished=threading.Event()
    class LateConnection:
        closed=False
        def close(self):self.closed=True
    late=LateConnection()
    def stalled_connect(*_args,**_kwargs):
        time.sleep(.15);finished.set();return late
    started=time.monotonic()
    with pytest.raises(RootlineConnectionDeadlineExceeded):
        connect_bounded_rootline_postgres(database_url="postgresql://stalled",
            connect=stalled_connect,connect_deadline_seconds=.03)
    assert time.monotonic()-started < .12
    assert finished.wait(.4) and late.closed is True


def test_rootline_deadline_includes_transaction_setup_and_closes_connection():
    import time
    from modules.oom_sakkie.bounded_postgres_read import (
        RootlineConnectionDeadlineExceeded, connect_bounded_rootline_postgres,
    )
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*_args):return False
        def execute(self,*_args):time.sleep(.05)
    class Connection:
        closed=False
        rolled_back=False
        def cursor(self):return Cursor()
        def rollback(self):self.rolled_back=True
        def close(self):self.closed=True
    connection=Connection();started=time.monotonic()
    with pytest.raises(RootlineConnectionDeadlineExceeded):
        connect_bounded_rootline_postgres(database_url="postgresql://setup-stall",
            connect=lambda *_args,**_kwargs:connection,connect_deadline_seconds=.02)
    assert time.monotonic()-started < .1
    deadline=time.monotonic()+.4
    while not connection.closed and time.monotonic()<deadline:time.sleep(.01)
    assert connection.closed is True


@pytest.mark.skipif(not hasattr(__import__("signal"),"setitimer"),
                    reason="POSIX interval timers are required")
def test_existing_earlier_process_alarm_is_not_suppressed_and_late_connection_closes():
    import signal
    import time
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    class EarlierDeadline(Exception):pass
    class LateConnection:
        closed=False
        def close(self):self.closed=True
    late=LateConnection()
    previous=signal.getsignal(signal.SIGALRM)
    def earlier(_signum,_frame):raise EarlierDeadline("outer_request_deadline")
    signal.signal(signal.SIGALRM,earlier);signal.setitimer(signal.ITIMER_REAL,.02)
    try:
        with pytest.raises(EarlierDeadline):
            connect_bounded_rootline_postgres(database_url="postgresql://outer-deadline",
                connect=lambda *_args,**_kwargs:(time.sleep(.08),late)[1],
                connect_deadline_seconds=.2)
        time.sleep(.1)
        assert late.closed is True
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def test_rootline_fallback_connect_slot_exhaustion_fails_immediately(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read as bounded
    class Exhausted:
        def acquire(self,**_kwargs):return False
    monkeypatch.setattr(bounded,"_FALLBACK_CONNECT_SLOTS",Exhausted())
    with pytest.raises(bounded.RootlineConnectionDeadlineExceeded,
                       match="connect_slots_exhausted"):
        bounded._thread_bounded_connect(lambda *_args,**_kwargs:None,
            "postgresql://unused",{},.1)


def test_rootline_worker_start_failure_releases_slot_and_is_typed(monkeypatch):
    import threading
    from modules.oom_sakkie import bounded_postgres_read as bounded
    released=[]
    class Slot:
        def acquire(self,**_kwargs):return True
        def release(self):released.append(True)
    monkeypatch.setattr(bounded,"_FALLBACK_CONNECT_SLOTS",Slot())
    monkeypatch.setattr(threading.Thread,"start",
        lambda _self:(_ for _ in ()).throw(RuntimeError("thread unavailable")))
    with pytest.raises(bounded.RootlineConnectionDeadlineExceeded,
                       match="worker_start_failed"):
        bounded._thread_bounded_connect(lambda *_args,**_kwargs:None,
            "postgresql://unused",{},.1)
    assert released==[True]


def test_rootline_connection_deadline_is_a_database_unavailability():
    from modules.oom_sakkie.bounded_postgres_read import (
        RootlineConnectionDeadlineExceeded, is_database_unavailable,
    )
    assert is_database_unavailable(RootlineConnectionDeadlineExceeded("bounded")) is True


def test_only_database_failures_acquire_zero_downstream_classification():
    OperationalError = type("OperationalError", (Exception,), {})
    assert is_database_unavailable(OperationalError("database")) is True
    assert is_database_unavailable(AssertionError("specialist defect")) is False


@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input",
       return_value=({"handled": False}, 200))
@patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",
       return_value=None)
@patch("modules.oom_sakkie.telegram_gateway.load_active_manager_question",
       return_value={"load_unavailable": True, "load_failure_class": "OperationalError"})
def test_authenticated_context_database_failure_returns_bounded_zero_effect_response(
        _load, _replay, _owner_task):
    token = "c" * 40
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": token,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": OWNER,
        "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER}
    payload = {"message": {"message_id": "synthetic-context-db-down",
        "date": int(NOW.timestamp()), "text": "They are eating and drinking normally",
        "from": {"id": int(OWNER)},
        "chat": {"id": int(OWNER), "type": "private"}}}
    result, status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + token}, environ=env)
    assert status == 503
    assert result["status"] == "manager_question_context_unavailable"
    assert result["sends_telegram"] is False
    assert result["delivery"]["telegram_sends"] == 0
    assert result["message"]["writes_farm_data"] is False
    assert result["message"]["hardware_commands"] == 0


@patch("modules.oom_sakkie.morning_runtime.reassess_current_brief_after_owner_answer",
       return_value={"success":True,"status":"daily_manager_unchanged_silent",
                     "telegram_sends":0,"telegram_edits":0})
@patch("modules.oom_sakkie.telegram_gateway.handle_manager_question_reply",
       return_value=({"handled":True,"success":True,
                      "status":"manager_question_reply_recorded",
                      "answer":"Thanks generic acknowledgement"},200))
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input",
       return_value=({"handled":False},200))
@patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",
       return_value=None)
@patch("modules.oom_sakkie.telegram_gateway.load_active_manager_question")
def test_complete_receipt_reassesses_with_gateway_environment_and_sends_no_generic_ack(
        active,_replay,_owner_task,_manager,reassess):
    active.return_value=question()
    token="c"*40
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":token,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":OWNER,
        "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID":OWNER}
    payload={"message":{"message_id":"3530","date":int(NOW.timestamp()),
        "text":"They are eating, drinking and moving normally",
        "from":{"id":int(OWNER)},"chat":{"id":int(OWNER),"type":"private"}}}
    result,status=handle_telegram_gateway_message(payload,
        headers={"Authorization":"Bearer "+token},environ=env)
    assert status==200 and result["delivery"]["status"]=="daily_manager_unchanged_silent"
    assert result["answer"]=="" and result["sends_telegram"] is False
    assert reassess.call_args.kwargs["environ"] is env


def test_context_places_active_manager_question_before_semantic_classification():
    context = semantic_context_with_manager_question(parsed(),
        base_context_loader=lambda _parsed: {"active_cases": [], "recent_turns": []},
        question=question())
    turn = context["recent_turns"][-1]
    assert turn["telegram_message_id"] == "3529"
    assert turn["clarification_question"].startswith("Are the surviving")


def test_partial_reply_keeps_one_smallest_visible_follow_up():
    partial = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True, observation="They are eating.",
        language="en", confidence=.9, needs_clarification=True,
        clarification_question="Are they also drinking and moving normally?")
    state = memory()
    value, _ = handle_manager_question_reply(parsed("They are eating"),
        issue_gateway_owner_authority(OWNER, OWNER), partial,
        question=question(), event_store=state)
    assert value["status"] == "manager_question_partial_reply_recorded"
    assert value["question_count"] == 1
    assert value["answer"] == "Are they also drinking and moving normally?"
    assert next(iter(state.rows.values()))["status"] == "partial"


def test_partial_facts_are_retained_in_context_and_accumulated_on_completion():
    prior = {"owner_evidence": "They are eating.", "provider_message_id": "3530",
        "provider_timestamp": NOW.isoformat(), "domain": "herd_health",
        "semantic_facts": {"observation": "They are eating.", "observation_facts": []}}
    active = question(); active["partial_replies"] = [prior]
    context = semantic_context_with_manager_question(parsed(message="3531"),
        base_context_loader=lambda _parsed: {"recent_turns": []}, question=active)
    assert context["recent_turns"][-2]["observation"] == "They are eating."
    complete = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True,
        observation="They are drinking and moving normally.", language="en", confidence=.98)
    state = memory()
    value, status = handle_manager_question_reply(parsed(
        "They are drinking and moving normally", message="3531"),
        issue_gateway_owner_authority(OWNER, OWNER), complete,
        question=active, event_store=state)
    record = next(iter(state.rows.values()))
    assert status == 200 and value["status"] == "manager_question_reply_recorded"
    assert record["generation"] == 2
    assert record["accumulated_semantic_facts"]["observations"] == [
        "They are eating.", "They are drinking and moving normally."]


def test_semantic_outage_keeps_question_visible_and_unanswered():
    state = memory()
    value, status = handle_manager_question_reply(parsed("Yes"),
        issue_gateway_owner_authority(OWNER, OWNER), None,
        question=question(), event_store=state)
    assert status == 409 and value["status"] == "manager_question_meaning_unavailable"
    assert value["answer"] == question()["question"] and state.rows == {}


def test_changed_provider_binding_cannot_be_suppressed_as_replay():
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, _ = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=state)
    changed, status = handle_manager_question_reply(
        parsed("No, one is not eating", message="3531"), authority, semantic(),
        question=question(), event_store=state)
    assert first["status"] == "manager_question_reply_recorded"
    assert status == 409 and changed["status"] == "manager_question_concurrent_reply_conflict"


def test_reloaded_partial_exact_replay_is_silent_and_does_not_advance_generation():
    partial = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True, observation="They are eating.",
        language="en", confidence=.9, needs_clarification=True,
        clarification_question="Are they also drinking and moving normally?")
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, _ = handle_manager_question_reply(parsed("They are eating"), authority, partial,
        question=question(), event_store=state)
    active = question(); active["partial_replies"] = [next(iter(state.rows.values()))]
    replay, status = handle_manager_question_reply(parsed("They are eating"), authority,
        partial, question=active, event_store=state)
    assert first["status"] == "manager_question_partial_reply_recorded"
    assert status == 200 and replay["status"] == "manager_question_reply_replay_suppressed"
    assert replay["suppress_owner_delivery"] is True and len(state.rows) == 1
