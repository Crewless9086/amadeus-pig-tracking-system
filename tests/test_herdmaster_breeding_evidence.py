from copy import deepcopy
from datetime import date

from modules.pig_weights.herdmaster_breeding_evidence import reconcile_breeding_evidence
from modules.pig_weights.herdmaster_breeding_recommendation import evaluate_breeding_attention

TODAY=date(2026,8,6)


def pig(pig_id,tag,sex,**updates):
    row={"pig_id":pig_id,"tag_number":tag,"sex":sex,"animal_type":"Sow" if sex=="Female" else "Boar","status":"Active","on_farm":True,"purpose":"Breeding","date_of_birth":"2025-01-01","current_pen_id":"PEN-1","current_pen_name":"D1","latest_weight_kg":100,"latest_weight_date":"2026-07-20","medical_status":"Clear","available_for_breeding":"available","current_cycle":{"state":"no_active_cycle"},"observations":{"observed_at":"2026-08-06","body_condition":3,"legs_sound":True,"visible_concern":"none","heat":"observed"} if sex=="Female" else {"observed_at":"2026-08-06","legs_sound":True,"feet_sound":True,"build_acceptable":True,"visible_concern":"none"}}
    row.update(updates);return row


def snapshot(**updates):
    rows=[pig("SOW","Sally","Female",mother_pig_id="SD",father_pig_id="SS"),pig("BOAR","Bert","Male",mother_pig_id="BD",father_pig_id="BS",reservation_status="not_reserved")]
    for pid in ("SD","SS","BD","BS"):
        rows.append({"pig_id":pid,"tag_number":pid,"sex":"Female" if pid.endswith("D") else "Male","animal_type":"Grower","status":"Removed","on_farm":False,"purpose":"Unknown","mother_pig_id":"F-"+pid,"father_pig_id":"M-"+pid})
        rows.extend([{"pig_id":"F-"+pid,"tag_number":"F-"+pid,"status":"Removed","on_farm":False,"mother_pig_id":"FF-"+pid,"father_pig_id":"FM-"+pid},{"pig_id":"M-"+pid,"tag_number":"M-"+pid,"status":"Removed","on_farm":False,"mother_pig_id":"MF-"+pid,"father_pig_id":"MM-"+pid}])
        for prefix in ("FF-","FM-","MF-","MM-"):
            rows.append({"pig_id":prefix+pid,"tag_number":prefix+pid,"status":"Removed","on_farm":False,"mother_pig_id":"X-"+prefix+pid,"father_pig_id":"Y-"+prefix+pid})
    observations=[{"observation_event_id":"OBS-"+row["pig_id"],"pig_id":row["pig_id"],"observed_at":row["observations"]["observed_at"],"measurements_json":row["observations"]} for row in rows[:2]]
    data={"pigs":rows,"location_events":[{"location_event_id":"LOC-S","pig_id":"SOW","move_date":"2026-08-01","to_pen_id":"PEN-1","to_pen_name":"D1"},{"location_event_id":"LOC-B","pig_id":"BOAR","move_date":"2026-08-01","to_pen_id":"PEN-1","to_pen_name":"D1"}],"litters":[],"mating_events":[],"medical_events":[],"observations":observations,"active_outlets":[],"order_lines":[],"auction_members":[],"carcass_reservations":[],"reservation_coverage":{"complete":True,"complete_through":"2026-08-06","pig_ids":["SOW","BOAR"]},"withdrawal_coverage":{"complete":True,"complete_through":"2026-08-06","pig_ids":["SOW","BOAR"]},"policy":{"breeding_body_condition_min":2.5,"breeding_body_condition_max":4.0}}
    data.update(updates);return data


def test_recovers_current_pen_from_latest_valid_projection():
    data=snapshot();data["pigs"][0]["current_pen_id"]="";data["pigs"][0]["current_pen_name"]=""
    result=reconcile_breeding_evidence(data,today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["current_pen_name"]=="D1"
    assert sow["pen_evidence"]["status"]=="recovered"


def test_conflicting_current_and_latest_pen_fails_closed():
    data=snapshot();data["location_events"][0].update(to_pen_id="PEN-2",to_pen_name="D2")
    sow=next(row for row in reconcile_breeding_evidence(data,today=TODAY)["females"] if row["pig_id"]=="SOW")
    assert sow["current_pen_name"] is None
    assert sow["pen_evidence"]["status"]=="conflicting"


def test_complete_reservation_coverage_allows_authoritative_not_reserved():
    result=reconcile_breeding_evidence(snapshot(),today=TODAY)
    assert {row["reservation_status"] for row in result["females"]+result["boars"]}=={"not_reserved"}
    assert result["coverage"]["reservation"]["complete"] is True


def test_absence_without_complete_reservation_coverage_remains_unknown():
    data=snapshot(reservation_coverage={"complete":False,"pig_ids":[]})
    assert {row["reservation_status"] for row in reconcile_breeding_evidence(data,today=TODAY)["females"]+reconcile_breeding_evidence(data,today=TODAY)["boars"]}=={"unknown"}


def test_withdrawal_calculation_requires_complete_coverage_and_detects_hold():
    event={"medical_event_id":"MED-1","pig_id":"SOW","treatment_date":"2026-08-01","withdrawal_days":10,"withdrawal_end_date":None}
    data=snapshot(medical_events=[event])
    sow=reconcile_breeding_evidence(data,today=TODAY)["females"][0]
    assert sow["withdrawal_evidence_state"]=="hold"
    assert sow["withdrawal_evidence"]["history"][0]["withdrawal_end_date"]=="2026-08-11"
    data["medical_events"]=[];data["withdrawal_coverage"]={"complete":False,"pig_ids":[]}
    assert reconcile_breeding_evidence(data,today=TODAY)["females"][0]["withdrawal_evidence_state"]=="unknown"


def test_conflicting_recorded_and_calculated_withdrawal_fails_closed():
    event={"medical_event_id":"MED-1","pig_id":"SOW","treatment_date":"2026-07-01","withdrawal_days":5,"withdrawal_end_date":"2026-07-20"}
    sow=reconcile_breeding_evidence(snapshot(medical_events=[event]),today=TODAY)["females"][0]
    assert sow["withdrawal_evidence_state"]=="conflicting"


def test_litter_origin_recovers_exact_parentage_without_name_inference():
    data=snapshot();data["pigs"][0].update(mother_pig_id="",father_pig_id="",litter_id="LIT-1")
    data["litters"]=[{"litter_id":"LIT-1","sow_pig_id":"SD","boar_pig_id":"SS","is_superseded":False}]
    parentage=reconcile_breeding_evidence(data,today=TODAY)["parentage"]["SOW"]
    assert (parentage["dam_pig_id"],parentage["sire_pig_id"])==("SD","SS")


def test_direct_parent_offspring_and_sibling_exclusions_are_exact():
    data=snapshot();data["pigs"][1].update(mother_pig_id="SD",father_pig_id="SS")
    relation=reconcile_breeding_evidence(data,today=TODAY)["pair_relatedness"][0]
    assert relation["status"]=="excluded"
    assert relation["reasons"]==["full sibling"]
    data["pigs"][0]["father_pig_id"]="BOAR"
    relation=reconcile_breeding_evidence(data,today=TODAY)["pair_relatedness"][0]
    assert relation["reasons"]==["direct ancestor/descendant"]


def test_partial_pedigree_identifies_exact_missing_links():
    data=snapshot();data["pigs"][0]["mother_pig_id"]=""
    result=reconcile_breeding_evidence(data,today=TODAY)
    assert result["parentage"]["SOW"]["missing_links"]==["mother_pig_id"]
    assert any(row["pig_id"]=="SOW" and row["field"]=="mother_pig_id" for row in result["data_quality_recovery"])
    assert result["pair_relatedness"][0]["status"]=="unknown"


def test_recovered_evidence_can_produce_one_valid_recommendation():
    result=reconcile_breeding_evidence(snapshot(),today=TODAY)
    recommendation=evaluate_breeding_attention(result,today=TODAY)
    case=recommendation["cases"][0]
    assert case["recommended_boar"]["pig_id"]=="BOAR"
    assert case["pairing_assessment"]=="recommended"
    assert recommendation["writes_performed"] is False


def test_incomplete_reservation_negative_coverage_is_disclosed_not_global_block():
    data=snapshot(reservation_coverage={"complete":False,"pig_ids":[]})
    result=reconcile_breeding_evidence(data,today=TODAY)
    case=evaluate_breeding_attention(result,today=TODAY)["cases"][0]
    assert case["pairing_assessment"]=="recommended"
    assert case["smallest_physical_question"] is None


def test_only_physical_gaps_allow_one_shortlisted_inspection():
    data=snapshot()
    data["observations"][0]["measurements_json"]={}
    result=reconcile_breeding_evidence(data,today=TODAY)
    case=evaluate_breeding_attention(result,today=TODAY)["cases"][0]
    assert case["pairing_assessment"]=="possible_but_needs_one_observation"
    assert case["smallest_physical_question"].startswith("For Sally")


def test_unchanged_replay_and_input_row_reordering_are_deterministic():
    data=snapshot();first=reconcile_breeding_evidence(data,today=TODAY)
    reordered=deepcopy(data);reordered["pigs"].reverse();reordered["location_events"].reverse()
    second=reconcile_breeding_evidence(reordered,today=TODAY)
    assert first==second
    assert evaluate_breeding_attention(first,today=TODAY)["assessment_id"]==evaluate_breeding_attention(second,today=TODAY)["assessment_id"]


def test_duplicate_canonical_pig_identity_fails_closed():
    data=snapshot();data["pigs"].append(deepcopy(data["pigs"][0]))
    result=reconcile_breeding_evidence(data,today=TODAY)
    assert result["success"] is False
    assert "duplicated" in result["reason"]


def test_future_movement_and_embedded_observation_are_not_authoritative():
    data=snapshot()
    data["pigs"][0]["current_pen_id"]="";data["pigs"][0]["current_pen_name"]=""
    data["location_events"][0]["move_date"]="2026-08-07"
    data["observations"]=[]
    result=reconcile_breeding_evidence(data,today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["current_pen_name"] is None
    assert sow["observations"]=={}


def test_withdrawal_malformed_negative_boolean_and_inclusive_end_fail_closed():
    for days in (-1, True):
        data=snapshot(medical_events=[{"medical_event_id":"BAD","pig_id":"SOW","treatment_date":"2026-07-01","withdrawal_days":days}])
        assert reconcile_breeding_evidence(data,today=TODAY)["females"][0]["withdrawal_evidence_state"]=="conflicting"
    data=snapshot(medical_events=[{"medical_event_id":"TODAY","pig_id":"SOW","treatment_date":"2026-08-01","withdrawal_days":5}])
    assert reconcile_breeding_evidence(data,today=TODAY)["females"][0]["withdrawal_evidence_state"]=="hold"


def test_new_unresolved_mating_overrides_stale_no_cycle_projection():
    data=snapshot(mating_events=[{"mating_id":"MAT-NEW","sow_pig_id":"SOW","boar_pig_id":"BOAR","mating_date":"2026-08-01"}])
    result=reconcile_breeding_evidence(data,today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["current_cycle"]["state"]=="post_mating_monitoring"
    assert sow["cycle_evidence"]["status"]=="recovered"


def test_conflicting_cycle_mating_fails_closed():
    data=snapshot(mating_events=[{"mating_id":"MAT-NEW","sow_pig_id":"SOW","boar_pig_id":"BOAR","mating_date":"2026-08-01"}])
    data["pigs"][0]["current_cycle"]={"state":"assumed_pregnant","mating_id":"MAT-OLD","mating_date":"2026-07-01"}
    result=reconcile_breeding_evidence(data,today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["current_cycle"]["state"]=="missing_evidence"
    assert sow["cycle_evidence"]["status"]=="conflicting"


def test_conflicting_litter_and_explicit_zero_weaned_do_not_inflate_score():
    base={"litter_id":"LIT-X","sow_pig_id":"SOW","boar_pig_id":"BOAR","farrowing_date":"2026-05-01","born_alive":10,"weaned_count":0,"is_superseded":False}
    data=snapshot(litters=[base]);data["pigs"].append({"pig_id":"CHILD","tag_number":"Child","status":"Active","on_farm":True,"litter_id":"LIT-X"})
    result=reconcile_breeding_evidence(data,today=TODAY)
    assert result["litters"][0]["weaned_count"]==0
    case=evaluate_breeding_attention(result,today=TODAY)["cases"][0]
    assert case["boar_assessments"][0]["service_history"]["surviving_piglets"]==0
    conflicting=deepcopy(base);conflicting["weaned_count"]=8
    result=reconcile_breeding_evidence(snapshot(litters=[base,conflicting]),today=TODAY)
    assert result["litters"]==[]


def test_conflicting_current_mating_or_litter_blocks_cycle_and_recommendation():
    mating={"mating_id":"MAT-X","sow_pig_id":"SOW","boar_pig_id":"BOAR","mating_date":"2026-08-01"}
    conflict={**mating,"boar_pig_id":"OTHER"}
    result=reconcile_breeding_evidence(snapshot(mating_events=[mating,conflict]),today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["current_cycle"]["state"]=="missing_evidence"
    assert sow["cycle_evidence"]["status"]=="conflicting"


def test_two_current_litter_ids_for_same_sow_and_farrowing_date_conflict():
    first={"litter_id":"LIT-A","sow_pig_id":"SOW","boar_pig_id":"BOAR","farrowing_date":"2026-08-01","born_alive":2,"weaned_count":None,"is_superseded":False}
    second={**first,"litter_id":"LIT-B"}
    result=reconcile_breeding_evidence(snapshot(litters=[first,second]),today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert result["litters"]==[]
    assert sow["cycle_evidence"]["status"]=="conflicting"
    assert evaluate_breeding_attention(result,today=TODAY)["cases"][0]["recommended_boar"] is None
    assert evaluate_breeding_attention(result,today=TODAY)["cases"][0]["recommended_boar"] is None
    litter={"litter_id":"LIT-X","sow_pig_id":"SOW","boar_pig_id":"BOAR","farrowing_date":"2026-08-01","born_alive":2,"weaned_count":None,"is_superseded":False}
    result=reconcile_breeding_evidence(snapshot(litters=[litter,{**litter,"born_alive":3}]),today=TODAY)
    sow=next(row for row in result["females"] if row["pig_id"]=="SOW")
    assert sow["cycle_evidence"]["status"]=="conflicting"


def test_all_set_like_inputs_reorder_to_same_digest_and_private_raw_rows_stay_internal():
    data=snapshot(
        mating_events=[{"mating_id":"M1","sow_pig_id":"SOW","boar_pig_id":"BOAR","mating_date":"2026-01-01","outcome":"closed"}],
        medical_events=[{"medical_event_id":"MED","pig_id":"SOW","treatment_date":"2026-01-01","withdrawal_days":1}],
        active_outlets=[{"outlet_assignment_id":"Z","pig_id":"BOAR","active":True},{"outlet_assignment_id":"A","pig_id":"BOAR","active":True}],
    )
    first=reconcile_breeding_evidence(data,today=TODAY)
    reordered=deepcopy(data)
    for key in ("pigs","location_events","litters","mating_events","medical_events","observations","active_outlets","order_lines","auction_members","carcass_reservations"):
        reordered[key].reverse()
    second=reconcile_breeding_evidence(reordered,today=TODAY)
    assert first["evidence_digest"]==second["evidence_digest"]
    packet=evaluate_breeding_attention(first,today=TODAY)["oom_sakkie_packet"]
    assert first["privacy_boundary"]=="internal_authorized_evidence_only"
    assert "medical_events" not in packet and "pigs" not in packet and "pairings" not in packet
