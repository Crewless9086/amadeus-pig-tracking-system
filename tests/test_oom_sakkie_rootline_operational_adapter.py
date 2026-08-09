from unittest.mock import patch

from modules.oom_sakkie.rootline_operational_adapter import dispatch_rootline_operation, persist_rootline_observations


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

@patch("modules.oom_sakkie.rootline_operational_adapter.record_tank_observations_transactional")
def test_fraction_observations_write_once_and_require_exact_canonical_readback(writer):
    both=context();both["observations"].append({"kind":"storage_level","value":"2/4","numerator":2,"denominator":4,
        "provider_message_id":"3213","observed_at":both["provider_timestamp"]})
    writer.return_value=({"success":True,"status":"recorded","created_count":2,
        "observation_ids":["ROOTLINE-TANK-S","ROOTLINE-TANK-R"],"observation_generation":"gen",
        "readback":[
            {"kind":"storage","fraction":[2,4],"state":"OK","provider_message_id":"3213","observed_at":both["provider_timestamp"]},
            {"kind":"reservoir","fraction":[4,4],"state":"FULL","provider_message_id":"3213","observed_at":both["provider_timestamp"]}]},201)
    from modules.oom_sakkie.gateway_authority import (
        issue_gateway_owner_authority,
        issue_rootline_observation_write_authority,
    )
    authority=issue_rootline_observation_write_authority(
        issue_gateway_owner_authority("42","42"),
        mission_id=both["mission_id"],
        provider_message_id=both["provider_message_id"],
        provider_timestamp=both["provider_timestamp"],
        content_sha256=both["content_sha256"],
    )
    result=persist_rootline_observations(both,authority,database_url="postgresql://test")
    assert result["success"] is True and result["canonical_writes"]==2
    payloads=writer.call_args.args[0]
    assert payloads[0]["storage_fraction"]==[2,4] and payloads[1]["reservoir_fraction"]==[4,4]
    writer.return_value=({"success":True,"status":"recorded","created_count":2,
        "observation_ids":["ROOTLINE-TANK-S","ROOTLINE-TANK-R"],"readback":[]},201)
    assert persist_rootline_observations(both,authority,database_url="postgresql://test")["status"]=="canonical_observation_readback_mismatch"


def test_observation_write_authority_is_distinct_and_exactly_request_bound():
    from modules.oom_sakkie.gateway_authority import (
        bind_gateway_owner_authority,
        issue_gateway_owner_authority,
        issue_rootline_observation_write_authority,
        ROOTLINE_READ_ONLY_TOOL,
    )
    base=issue_gateway_owner_authority("42","42")
    read_only=bind_gateway_owner_authority(base,ROOTLINE_READ_ONLY_TOOL)
    denied=persist_rootline_observations(context(),read_only,database_url="postgresql://must-not-connect")
    assert denied["status"]=="observation_write_authority_denied"
    authority=issue_rootline_observation_write_authority(base,mission_id="OOM-ROOTLINE-other",
        provider_message_id="3213",provider_timestamp=context()["provider_timestamp"],
        content_sha256=context()["content_sha256"])
    denied=persist_rootline_observations(context(),authority,database_url="postgresql://must-not-connect")
    assert denied["status"]=="observation_write_authority_denied"


def test_invalid_or_duplicate_observations_never_reach_writer():
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority,issue_rootline_observation_write_authority
    item=context()
    authority=issue_rootline_observation_write_authority(issue_gateway_owner_authority("42","42"),
        mission_id=item["mission_id"],provider_message_id=item["provider_message_id"],
        provider_timestamp=item["provider_timestamp"],content_sha256=item["content_sha256"])
    with patch("modules.oom_sakkie.rootline_operational_adapter.record_tank_observations_transactional") as writer:
        malformed={**item,"observations":[{**item["observations"][0],"denominator":0}]}
        assert persist_rootline_observations(malformed,authority)["status"]=="owner_observation_binding_invalid"
        duplicate={**item,"observations":[item["observations"][0],dict(item["observations"][0])]}
        assert persist_rootline_observations(duplicate,authority)["status"]=="duplicate_water_observation_ambiguous"
        writer.assert_not_called()


@patch("modules.oom_sakkie.rootline_operational_adapter.record_tank_observations_transactional")
def test_indeterminate_database_failure_never_claims_zero_writes(writer):
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority,issue_rootline_observation_write_authority
    item=context()
    authority=issue_rootline_observation_write_authority(issue_gateway_owner_authority("42","42"),
        mission_id=item["mission_id"],provider_message_id=item["provider_message_id"],
        provider_timestamp=item["provider_timestamp"],content_sha256=item["content_sha256"])
    writer.return_value=({"success":False,"status":"tank_observation_write_failed","write_outcome":"indeterminate"},503)
    result=persist_rootline_observations(item,authority)
    assert result["canonical_writes"] is None and result["write_outcome"]=="indeterminate"
