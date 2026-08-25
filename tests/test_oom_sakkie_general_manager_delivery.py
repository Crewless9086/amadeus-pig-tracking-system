from datetime import datetime, timezone
from unittest.mock import patch

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
    value=deliver_farm_manager_case(case,
        deliver=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError()))
    assert value["status"] == "no_owner_question_delivery_suppressed"
    assert value["telegram_sends"] == 0 and value["writes_farm_data"] is False


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
