from unittest.mock import patch

from modules.oom_sakkie.rootline_operational_adapter import dispatch_rootline_operation


def context():
    return {"contract_version":"oom_rootline_operational_dispatch_v1",
            "mission_id":"OOM-ROOTLINE-1","owner_user_id":"42","chat_id":"42",
            "provider_message_id":"3213","provider_timestamp":"2026-08-03T16:22:07+00:00",
            "content_sha256":"a"*64,
            "authority":{"farm_observation_write":False,"hardware_control":False,
                         "telegram_send":False,"automatic_on_retry":False},
            "observations":[{"kind":"reservoir_level","value":"4/4","numerator":4,"denominator":4,
                             "provider_message_id":"3213","observed_at":"2026-08-03T16:22:07+00:00"}],
            "visible_irrigation_need_zone":"C12345"}


def current():
    return {"success":True,"contract_version":"rootline_specialist_result_v1",
            "result_id":"ROOT-1","generation":"GEN-1",
            "recommendations":[{"subject":"C12345","status":"Recommend"}],
            "evidence":{"gaps":["current_channel_state"]},
            "next_reassessment":{"trigger":"fresh_channel_readback"}}


@patch("modules.oom_sakkie.rootline_operational_adapter.build_current_rootline_specialist_result")
def test_authenticated_packet_is_consumed_without_telegram_or_hardware_authority(loader):
    loader.return_value=current()
    result=dispatch_rootline_operation(context())
    assert result["specialist_acceptance"] is True and result["recommendation"]=="Reassess"
    assert result["canonical_recommendation_before_observation"]=="Recommend"
    assert result["owner_observations"]==context()["observations"]
    assert result["hardware_commands"]==0
    assert result["authority"]["telegram_send"] is False
    assert result["authority"]["hardware_control"] is False


@patch("modules.oom_sakkie.rootline_operational_adapter.build_current_rootline_specialist_result")
def test_unavailable_datum_limits_result_without_legacy_sheet_response(loader):
    item=current(); item["recommendations"][0]["recommendation"]="Needs Data"
    loader.return_value=item
    result=dispatch_rootline_operation(context())
    assert result["success"] is True and result["recommendation"]=="Reassess"
    assert result["unavailable"]==("current_channel_state",)


@patch("modules.oom_sakkie.rootline_operational_adapter.build_current_rootline_specialist_result")
def test_missing_or_malformed_specialist_fails_closed(loader):
    loader.side_effect=RuntimeError("offline")
    assert dispatch_rootline_operation(context())["specialist_acceptance"] is False
    loader.side_effect=None; loader.return_value={"success":True,"contract_version":"wrong"}
    assert dispatch_rootline_operation(context())["hardware_commands"]==0


def test_empty_packet_does_not_create_work():
    result=dispatch_rootline_operation({})
    assert result["success"] is False and result["hardware_commands"]==0

def test_internal_caller_cannot_bypass_authenticated_binding():
    for field in ("contract_version","mission_id","provider_message_id","provider_timestamp","content_sha256","authority"):
        item=context(); item.pop(field)
        result=dispatch_rootline_operation(item)
        assert result["success"] is False and result["reason"]=="authenticated_operational_binding_invalid"

def test_malformed_observation_and_identity_are_rejected_before_rootline_read():
    for change in ({"owner_user_id":"99"},{"provider_timestamp":"not-a-time"},
                   {"content_sha256":"bad"},{"visible_irrigation_need_zone":"B12345"}):
        item={**context(),**change}
        assert dispatch_rootline_operation(item)["success"] is False
    item=context(); item["observations"]=[{**item["observations"][0],"kind":"<b>unsafe</b>"}]
    assert dispatch_rootline_operation(item)["reason"]=="owner_observation_binding_invalid"
