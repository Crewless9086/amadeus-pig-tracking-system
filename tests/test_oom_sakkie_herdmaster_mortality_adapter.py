from datetime import date, datetime, timezone

from modules.oom_sakkie.herdmaster_mortality_adapter import consume_mortality_packet
from modules.pig_weights.herdmaster_mortality_intelligence import build_oom_sakkie_mortality_packet

NOW=datetime(2026,8,5,7,0,tzinfo=timezone.utc)


def evidence(events=None):
    return {"mortality_events":events or [{"event_id":"E1","pig_id":"P1",
        "effective_date":"2026-08-04","event_kind":"individual_death",
        "confirmation":"confirmed","canonical_status":"current"}],
        "feed_observations":[],"water_observations":[],"surviving_controls":[]}


def test_authenticated_manager_consumer_is_bounded_bilingual_and_zero_authority():
    packet=build_oom_sakkie_mortality_packet(evidence(),analysis_end=date(2026,8,5))
    result,binding=consume_mortality_packet(packet,observed_at=NOW,language="af")
    assert result.availability.value=="available" and len(result.work_items)==1
    item=result.work_items[0]
    assert "Ons kan" in item.why and item.genuine_question.count("?")==1
    assert "oorlewende" in item.next_action and "Please check" not in item.genuine_question
    assert item.authority.value=="advisory" and not binding["writes_farm_data"]
    assert not binding["writes_lifecycle"] and not binding["writes_medical"]
    assert not binding["sends_telegram"] and not binding["diagnoses"] and not binding["treats"]


def test_pig127_active_lifecycle_is_preserved_without_duplicate_case_or_question():
    packet=build_oom_sakkie_mortality_packet(evidence(),analysis_end=date(2026,8,5))
    result,binding=consume_mortality_packet(packet,observed_at=NOW,
        active_lifecycles=[{"pig_id":"PIG-2026-D13C","state":"waiting_for_confirmation"}])
    assert binding["active_lifecycle_pig_ids"]==("PIG-2026-D13C",)
    assert "Pig 127" not in result.work_items[0].title
    assert result.work_items[0].dedupe_key=="herdmaster:mortality-current-assessment"


def test_active_welfare_question_owns_the_single_question_budget():
    packet=build_oom_sakkie_mortality_packet(evidence(),analysis_end=date(2026,8,5))
    result,_=consume_mortality_packet(packet,observed_at=NOW,active_lifecycles=[{
        "pig_id":"PIG-2026-D13C","state":"waiting_for_input",
        "current_question":"Is Pig 127 breathing normally?","reported_dead":True}])
    item=result.work_items[0]
    assert item.genuine_question=="" and item.question_for==""


def test_review_identity_is_stable_while_material_digest_changes():
    first=build_oom_sakkie_mortality_packet(evidence(),analysis_end=date(2026,8,5))
    changed=build_oom_sakkie_mortality_packet(evidence([
        *evidence()["mortality_events"],{"event_id":"E2","pig_id":"P2",
        "effective_date":"2026-08-05","event_kind":"individual_death",
        "confirmation":"confirmed","canonical_status":"current"}]),analysis_end=date(2026,8,5))
    assert first["review_identity"]==changed["review_identity"]=="HERDMASTER-MORTALITY-CURRENT"
    assert first["evidence_digest"]!=changed["evidence_digest"]


def test_malformed_or_authority_bearing_packet_fails_closed():
    packet=build_oom_sakkie_mortality_packet(evidence(),analysis_end=date(2026,8,5))
    result,binding=consume_mortality_packet({**packet,"authority":{**packet["authority"],"writes":True}},
                                            observed_at=NOW)
    assert result.availability.value=="contained" and binding["systemic_exception"]=="mortality_packet_invalid"
    assert not binding["writes_farm_data"] and not binding["sends_telegram"]
    malformed={**packet,"rolling_counts":{"30":{}}}
    result,binding=consume_mortality_packet(malformed,observed_at=NOW)
    assert result.availability.value=="contained" and binding["systemic_exception"]=="mortality_packet_invalid"
    for hostile in (["writes"],"writes"):
        result,binding=consume_mortality_packet({**packet,"authority":hostile},observed_at=NOW)
        assert result.availability.value=="contained"
        assert binding["systemic_exception"]=="mortality_packet_invalid"
