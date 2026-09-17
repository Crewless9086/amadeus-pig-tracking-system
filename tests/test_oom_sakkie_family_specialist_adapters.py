from unittest.mock import patch
import hashlib, json

from modules.oom_sakkie.family_access import FamilyPrincipal, FamilyRole
from modules.oom_sakkie.family_specialist_adapters import (
    herdmaster_family_observation, load_family_summary, rootline_family_handoff)


def principal(role=FamilyRole.FARM_MANAGER):
    return FamilyPrincipal("1002", "1002", role, "dad", frozenset(),
        frozenset({"herd", "water"}), "AUTH", "5721652188",
        "2026-08-15T08:00:00+02:00", "digest", "af")


def parsed(text="Pig 11 is sick"):
    return {"telegram_user_id":"1002","telegram_chat_id":"1002",
        "telegram_chat_type":"private","provider_message_id":"501",
        "provider_timestamp":"2026-08-15T10:00:00+00:00","text":text}


@patch("modules.telemetry.rootline_daily_brief.get_rootline_daily_brief")
def test_rootline_summary_uses_canonical_packet_and_minimum_fields(loader):
    loader.return_value=({"executive_summary":"Reservoir evidence available.",
        "current_conditions":{"freshness":"fresh"},
        "power":{"interpretation":"healthy"},
        "customer_details":["must not leak"],"internal_missions":["must not leak"]},200)
    packet=load_family_summary(principal=principal(),domain="water")
    assert packet["available"] and packet["summary_lines"]==["Reservoir evidence available."]
    assert set(packet["recipient_binding"])=={"telegram_user_id","family_key","binding_digest","permitted_domain","language"}
    assert "customer" not in str(packet).lower() and "mission" not in str(packet).lower()


@patch("modules.pig_weights.herdmaster_daily_manager_evidence.load_daily_manager_evidence")
def test_herd_summary_preserves_unknown_and_does_not_copy_owner_packet(loader):
    loader.return_value={"success":True,"evidence_date":"2026-08-15","weight":{
        "current_snapshot":{"covered":81,"eligible_tagged":81}},
        "mortality":{"digest_changed":False},"customer_data":"secret"}
    packet=load_family_summary(principal=principal(),domain="herd")
    assert packet["summary_lines"]==["Gemerkte jong/groeiende varke geweeg: 81/81."]
    assert "secret" not in str(packet)


@patch("modules.oom_sakkie.family_specialist_adapters._record_once", return_value={"success":True,"created":True})
@patch("modules.pig_weights.herdmaster_natural_health_loss_intake.evaluate_health_loss_intake")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_found_dead_remains_observation_and_requires_charl_confirmation(evidence,evaluator,_record):
    evidence.return_value={"evidence_generation":"E1","as_of_timestamp":"2026-08-15T10:01:00+00:00","animals":[]}
    evaluator.return_value={"success":True,"status":"ready","identity":{"resolved":True,"pig_id":"P11"},
        "event_family":"found_dead","immediate_welfare_priority":{"level":"urgent"}}
    with patch("modules.oom_sakkie.herdmaster_health_loss_runtime.handle_authenticated_health_loss_message") as owner_handler:
        result=herdmaster_family_observation(parsed=parsed("Pig 11 is dood gevind"),
            principal=principal(),capability="found_dead_observation",replay_identity="a"*64)
    owner_handler.assert_not_called()
    assert result["success"] and result["animal_mutations"]==0
    assert "Charl" in result["answer"] and "bevestiging" in result["answer"]


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
       side_effect=RuntimeError("unavailable"))
def test_herdmaster_evidence_failure_is_hold_with_zero_mutation(_loader):
    result=herdmaster_family_observation(parsed=parsed(),principal=principal(),
        capability="farm_observation",replay_identity="a"*64)
    assert not result["success"] and result["status"]=="herdmaster_family_evidence_unavailable"
    assert result["writes_farm_data"] is False and result["animal_mutations"]==0


def test_rootline_reviewed_interface_reloads_authority_and_returns_sealed_outcome():
    from modules.telemetry.rootline_delegated_principal import CAPABILITY
    base={"authorization_id":"AUTH","principal_id":"1002","private_chat_id":"1002",
        "family_identity":"anton","role":"farm_manager","capabilities":[CAPABILITY],
        "zones":["B12345"],"commissioned_paths":["B12345"],
        "maximum_duration_seconds":3599,"authorized_at":"2026-08-15T08:00:00+00:00"}
    digest=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    auth={**base,"active":True,"revoked_at":None,"owner_authority":False,
          "authorization_digest":digest}
    artifact={"contract_version":"rootline_execution_eligibility.v5","status":"execution_eligible",
        "authority_source":"owner_approved_routine_irrigation_v1","zone_id":"B12345",
        "plan_generation":"PLAN-1","maximum_duration_seconds":3599,"command_authority":True,
        "hardware_control":True,"execution_id":"EXEC-1","eligibility_sha256":"b"*64,
        "job_id":"JOB-1","job_sha256":"c"*64,"segment_identity":"SEG-1",
        "current_segment":1,"consumption_key":"CONSUME-1"}
    item=parsed(); item["family_action"]={"authorization_digest":digest,
        "commissioned_path_id":"B12345","zone_id":"B12345","bounded_duration_seconds":3599,
        "evidence_generation":"PLAN-1","job_id":"JOB-1","job_sha256":"c"*64,
        "segment_identity":"SEG-1","current_segment":1,"execution_id":"EXEC-1",
        "eligibility_sha256":"b"*64,"consumption_key":"CONSUME-1"}
    with patch("modules.telemetry.rootline_delegated_principal.validate_execution_eligibility",
               side_effect=lambda value,now=None:value):
        result=rootline_family_handoff(parsed=item,principal=principal(),
            capability="irrigation_start",replay_identity="a"*64,
            authorization_loader=lambda _:auth,eligibility_loader=lambda:artifact,
            executor=lambda **_:{"success":True,"status":"segment_started",
                "hardware_commands":1,"provider_control_calls":1})
    assert result["success"] and result["hardware_commands"]==1
    assert result["rootline_outcome"]["contract_version"]=="rootline_delegated_outcome.v1"


def test_rootline_unreviewed_stop_and_incomplete_start_hold_without_command():
    for capability in ("irrigation_stop","irrigation_start"):
        result=rootline_family_handoff(parsed=parsed(),principal=principal(),
            capability=capability,replay_identity="a"*64)
        assert not result["success"] and result["hardware_commands"]==0
