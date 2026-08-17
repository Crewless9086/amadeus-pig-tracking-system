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
def test_provider_ambiguity_is_not_claimed_as_delivery():
    value=deliver_farm_manager_case(_case(),deliver=lambda *a,**k:{"success":True,"telegram_sends":0})
    assert value["success"] is False and value["delivery_confirmed"] is False
