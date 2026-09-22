from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case


def _case(specialist="HERDMASTER"):
    return {"case_id":"OOM-CASE-ABC", "generation":2, "specialist":specialist,
        "summary":"Current supported finding.", "next_action":"Reassess safely.",
        "next_reassessment_at":"2026-08-17T13:00:00+00:00",
        "unknowns":["physical observation"], "evidence_digest":"d"*64}


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_farm_case_uses_existing_provider_confirmed_family_lifecycle():
    captured={}
    def deliver(parsed,result,**kwargs):
        captured.update(parsed=parsed,result=result,kwargs=kwargs)
        return {"success":True,"provider_delivery_confirmed":True,
                "telegram_message_id":"4001","telegram_sends":1}
    value=deliver_farm_manager_case(_case(),now=datetime(2026,8,17,12,tzinfo=timezone.utc),deliver=deliver)
    assert value["success"] is True and value["delivery_confirmed"] is True
    assert captured["kwargs"]["card_mission_id"] == "OOM-CASE-ABC"
    assert "Current supported finding" in captured["result"]["answer"]
    assert captured["result"]["hardware_commands"] == 0


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_non_farm_case_remains_silent():
    value=deliver_farm_manager_case(_case("SAM"),deliver=lambda *a,**k: (_ for _ in ()).throw(AssertionError()))
    assert value["status"] == "non_farm_case_delivery_suppressed"
    assert value["telegram_sends"] == 0


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_case_without_an_owner_question_remains_silent():
    case=_case(); case["unknowns"]=[]
    value=deliver_farm_manager_case(case,now=datetime(2026,8,17,12,tzinfo=timezone.utc),
        deliver=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError()))
    assert value["status"] == "no_owner_question_delivery_suppressed"
    assert value["telegram_sends"] == 0 and value["writes_farm_data"] is False
    assert value["next_reassessment_at"] == "2026-08-17T12:05:00+00:00"


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_owner_case_hides_backend_timestamp_and_canonical_jargon():
    captured={}; case=_case(); case["summary"]="Pig 126 needs one physical check."
    deliver_farm_manager_case(case,deliver=lambda parsed,result,**kwargs:
        (captured.update(result=result) or {"success":True,"provider_delivery_confirmed":True,
         "telegram_message_id":"4003","telegram_sends":1}))
    answer=captured["result"]["answer"]
    assert "2026-08-17T13:00" not in answer and "canonical" not in answer.casefold()
    assert "check this again automatically" in answer


@patch("modules.oom_sakkie.beacon_request_runtime.build_scheduled_sale_ready_stock_result")
@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_beacon_case_uses_protected_oom_delivery_without_public_effects(build):
    build.return_value={"success":True,"status":"beacon_sale_ready_stock_proposal_ready",
        "answer":"<b>BEACON proposal</b>","result_digest":"a"*64,
        "publishes":False,"spends_money":False,"customer_sends":False,
        "writes_farm_data":False,"protected_actions_performed":False}
    case=_case("BEACON")
    case["evidence_refs"]=["beacon_result:"+"a"*64]
    captured={}
    def deliver(parsed,result,**kwargs):
        captured.update(result=result,kwargs=kwargs)
        return {"success":True,"provider_delivery_confirmed":True,
                "telegram_message_id":"4002","telegram_sends":1}
    value=deliver_farm_manager_case(case,deliver=deliver)
    assert value["success"] is True and value["delivery_confirmed"] is True
    assert captured["kwargs"]["specialist"] == "BEACON"
    assert captured["result"]["publishes"] is False
    assert captured["result"]["customer_sends"] is False


@patch("modules.oom_sakkie.beacon_request_runtime.build_scheduled_sale_ready_stock_result",
       side_effect=RuntimeError("private detail"))
@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_beacon_dependency_failure_is_not_misreported_or_delivered(_build):
    value=deliver_farm_manager_case(_case("BEACON"),
        deliver=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError()))
    assert value["delivery_confirmed"] is False
    assert value["status"] == "beacon_canonical_evidence_unavailable"
    assert value["publishes"] is False and value["customer_sends"] == 0
    assert "private detail" not in str(value)


@patch("modules.oom_sakkie.beacon_request_runtime.build_scheduled_sale_ready_stock_result")
@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_beacon_changed_evidence_is_suppressed_before_provider_delivery(build):
    build.return_value={"success":True,"answer":"new","result_digest":"b"*64}
    case=_case("BEACON"); case["evidence_refs"]=["beacon_result:"+"a"*64]
    value=deliver_farm_manager_case(case,
        deliver=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError()))
    assert value["status"] == "beacon_material_evidence_changed_before_delivery"
    assert value["delivery_confirmed"] is False and value["telegram_sends"] == 0


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_provider_ambiguity_is_not_claimed_as_delivery():
    value=deliver_farm_manager_case(_case(),deliver=lambda *a,**k:{"success":True,"telegram_sends":0})
    assert value["success"] is False and value["delivery_confirmed"] is False


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"5721652188"})
def test_generation_retry_uses_stable_provider_binding_timestamp():
    timestamps=[]
    def ambiguous(parsed,result,**kwargs):
        timestamps.append(parsed["provider_timestamp"])
        return {"success":False,"status":"provider_ambiguous","telegram_sends":0}
    deliver_farm_manager_case(_case(),now=datetime(2026,8,17,12,tzinfo=timezone.utc),deliver=ambiguous)
    deliver_farm_manager_case(_case(),now=datetime(2026,8,17,12,5,tzinfo=timezone.utc),deliver=ambiguous)
    assert len(set(timestamps)) == 1
    assert timestamps[0].endswith("+00:00")


def _real_family_delivery_harness():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    events, effects = {}, []
    def store(action, identity, payload):
        if action == "load":
            return [dict(row) for row in events.values()
                if row.get("card_mission_id") == identity]
        created = identity not in events
        if created:
            events[identity] = dict(payload)
        return {"success": True, "created": created}
    def sender(*_args, **_kwargs):
        effects.append("send")
        return {"success": True, "telegram_message_id": "7001"}
    def editor(*_args, **_kwargs):
        effects.append("edit")
        return {"success": True, "telegram_message_id": "7001"}
    def deliver(parsed, result, **kwargs):
        return deliver_family_result(parsed, result, event_store=store,
            sender=sender, editor=editor, **kwargs)
    return deliver, events, effects


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"})
def test_new_generation_exact_family_presentation_replay_is_suppressed_not_failed():
    deliver, events, effects = _real_family_delivery_harness()
    first = deliver_farm_manager_case(_case(), deliver=deliver)
    assert first["success"] and first["delivery_confirmed"] and effects == ["send"]
    previous = {key: dict(value) for key, value in events.items()}
    # New canonical evidence may leave the owner-facing presentation unchanged.
    current = {**_case(), "generation": 3, "evidence_digest": "e" * 64}
    result = deliver_farm_manager_case(current, deliver=deliver)
    assert result["status"] == "family_message_replayed_noop"
    assert result["success"] and result["delivery_confirmed"] is False
    assert result["telegram_sends"] == result["telegram_edits"] == 0
    assert result["mission_id"].endswith(":G3")
    assert effects == ["send"] and events == previous


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"})
def test_exact_generation_provider_replay_preserves_success_without_new_confirmation():
    deliver, events, effects = _real_family_delivery_harness()
    assert deliver_farm_manager_case(_case(), deliver=deliver)["success"]
    previous = {key: dict(value) for key, value in events.items()}
    result = deliver_farm_manager_case(_case(), deliver=deliver)
    assert result["status"] == "family_message_provider_replay_noop"
    assert result["success"] and result["delivery_confirmed"] is False
    assert effects == ["send"] and events == previous


@pytest.mark.parametrize("change", [
    {"success": False},
    {"telegram_message_id": ""},
    {"mission_id": "FOREIGN:G2"},
    {"card_mission_id": "FOREIGN"},
    {"telegram_sends": 1},
    {"telegram_edits": 1},
    {"provider_delivery_confirmed": True},
    {"status": "family_message_notification_ambiguous"},
    {"status": "unexpected_success"},
])
@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"})
def test_unproven_or_foreign_replay_is_not_successfully_suppressed(change):
    outcome = {"success": True, "status": "family_message_replayed_noop",
        "mission_id": "OOM-CASE-ABC:G2", "card_mission_id": "OOM-CASE-ABC",
        "telegram_message_id": "7001", "telegram_sends": 0, "telegram_edits": 0}
    outcome.update(change)
    result = deliver_farm_manager_case(_case(), deliver=lambda *_args, **_kwargs: outcome)
    assert result["success"] is False and result["delivery_confirmed"] is False


@patch.dict("os.environ", {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"})
def test_real_ambiguous_family_attempt_remains_contained_without_another_send():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    events, sends = {}, []
    def store(action, identity, payload):
        if action == "load":
            return list(events.values())
        created = identity not in events
        if created:
            events[identity] = dict(payload)
        return {"success": True, "created": created}
    def sender(*_args, **_kwargs):
        sends.append(1)
        return {"success": False, "status": "provider_ambiguous"}
    def deliver(parsed, result, **kwargs):
        return deliver_family_result(parsed, result, event_store=store, sender=sender, **kwargs)
    first = deliver_farm_manager_case(_case(), deliver=deliver)
    replay = deliver_farm_manager_case(_case(), deliver=deliver)
    assert first["success"] is replay["success"] is False
    assert first["delivery_confirmed"] is replay["delivery_confirmed"] is False
    assert sends == [1]
