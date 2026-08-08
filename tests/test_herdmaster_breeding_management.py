from copy import deepcopy
from datetime import date
import hashlib
import json

from modules.pig_weights.herdmaster_breeding_management import build_breeding_management_packet
from modules.pig_weights.herdmaster_breeding_evidence import CONTRACT_VERSION as EVIDENCE_CONTRACT_VERSION
from modules.pig_weights.herdmaster_breeding_recommendation import CONTRACT_VERSION as RECOMMENDATION_CONTRACT_VERSION


TODAY=date(2026,8,8)


def case(pid,tag,state,cycle=None,priority=20):
    return {"pig_id":pid,"tag_number":tag,"state":state,"priority":priority,"next_action":"continue","current_cycle":cycle or {"state":state},"confirmed_evidence":[f"Canonical identity {pid}."],"calculated_facts":[f"Current reproductive cycle: {state}."]}


def evidence():
    females=[
        {"pig_id":"MONA","tag_number":"Mona","sex":"Female","import_batch_id":"IMPORT-1","source_sheet_row":1},
        {"pig_id":"MYSI","tag_number":"Mysikind","sex":"Female","import_batch_id":"IMPORT-1","source_sheet_row":2},
        {"pig_id":"BABY","tag_number":"Baby","sex":"Female","import_batch_id":"IMPORT-1","source_sheet_row":3},
        {"pig_id":"WAKI","tag_number":"Waki","sex":"Female","import_batch_id":"IMPORT-1","source_sheet_row":4},
        {"pig_id":"UNKNOWN","tag_number":"Unknown Sow","sex":"Female","import_batch_id":"IMPORT-1","source_sheet_row":5},
    ]
    parentage={row["pig_id"]:{"status":"partial","dam_pig_id":None,"sire_pig_id":None,"direct_dam_pig_id":None,"direct_sire_pig_id":None,"litter_dam_pig_id":None,"litter_sire_pig_id":None,"litter_id":None,"missing_links":["mother_pig_id","father_pig_id"]} for row in females}
    reconciled={"success":True,"contract_version":EVIDENCE_CONTRACT_VERSION,"females":females,"boars":[],"parentage":parentage,"pedigrees":{row["pig_id"]:{"cycle_nodes":[]} for row in females},"coverage":{"reservation":{"complete":False,"reason":"coverage incomplete"},"withdrawal":{"complete":False,"reason":"coverage incomplete"}},"evidence_digest":"abc","evidence_generation":"GEN-1","writes_performed":False,"protected_actions_performed":False}
    cycle={"state":"assumed_pregnant","mating_id":"MAT-1","mating_date":"2026-05-02","clinical_confirmation":False}
    cases=[case("MONA","Mona","assumed_pregnant",cycle),case("MYSI","Mysikind","assumed_pregnant",{**cycle,"mating_id":"MAT-2"}),case("BABY","Baby","inconclusive"),case("WAKI","Waki","nursing"),case("UNKNOWN","Unknown Sow","missing_evidence")]
    material={"contract_version":RECOMMENDATION_CONTRACT_VERSION,"reconciliation_digest":"abc","cases":cases,"boar_inventory":[]}
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    assessment={"success":True,**material,"assessment_id":f"HERD-BREED-{digest[:32].upper()}","material_evidence_digest":digest,"evidence_generation":"GEN-1","delivery_enabled":False,"mating_execution_enabled":False,"writes_performed":False,"protected_actions_performed":False}
    return reconciled,assessment


def test_publishes_only_three_highest_value_management_actions():
    reconciled,assessment=evidence()
    result=build_breeding_management_packet(reconciled,assessment,today=TODAY)
    assert [row["action_id"] for row in result["actions"]]==["farrowing-preparation","inconclusive-cycle","post-litter-care"]
    assert len(result["actions"])==3


def test_assumed_pregnant_group_has_proportional_windows_not_clinical_claims():
    result=build_breeding_management_packet(*evidence(),today=TODAY)
    action=result["actions"][0]
    assert {row["tag_number"] for row in action["animals"]}=={"Mona","Mysikind"}
    assert {row["projected_farrowing_range"] for row in action["cycle_details"]}=={"2026-08-22 to 2026-08-26"}
    assert {row["preparation_window"] for row in action["cycle_details"]}=={"2026-08-08 to 2026-08-15"}
    assert all(row["clinical_confirmation"] is False for row in action["cycle_details"])


def test_pedigree_matrix_localizes_exact_missing_links_and_sources():
    reconciled,assessment=evidence()
    reconciled["females"][0].update(updated_at="2026-06-29")
    reconciled["parentage"]["MONA"].update(status="complete",dam_pig_id="DAM",sire_pig_id="SIRE",direct_dam_pig_id="DAM",direct_sire_pig_id="SIRE",missing_links=[])
    result=build_breeding_management_packet(reconciled,assessment,today=TODAY)
    mona=next(row for row in result["pedigree_recovery_matrix"] if row["pig_id"]=="MONA")
    assert (mona["dam_pig_id"],mona["sire_pig_id"],mona["confidence"])==("DAM","SIRE","Proven")
    assert mona["sources"][0]["type"]=="canonical_pig_master"
    assert result["recovered_parent_count"]==2
    assert result["remaining_missing_parent_links"]==8


def test_one_grouped_recovery_request_and_system_gaps_are_not_owner_questions():
    result=build_breeding_management_packet(*evidence(),today=TODAY)
    recovery=result["recovery_packet"]
    assert recovery["single_grouped_request"].startswith("Please provide one historical breeder register")
    assert len(recovery["animals"])==5
    assert {row["criterion"] for row in recovery["system_owned_not_owner_questions"]}=={"reservation","withdrawal"}


def test_unknown_pedigree_fallback_never_approves_pairing():
    result=build_breeding_management_packet(*evidence(),today=TODAY)
    fallback=result["safe_fallback_proposal"]
    assert fallback["status"]=="owner_review_only_not_implemented"
    assert "silently treat unknown as unrelated" in fallback["prohibited"]
    assert all(action["final_pairing_authorized"] is False for action in result["actions"])


def test_bilingual_packet_is_deterministic_zero_io_and_zero_authority():
    reconciled,assessment=evidence()
    first=build_breeding_management_packet(reconciled,assessment,today=TODAY)
    second=build_breeding_management_packet(deepcopy(reconciled),deepcopy(assessment),today=TODAY)
    assert first==second
    assert first["packet_id"]==second["packet_id"]
    assert "No mating is created" in first["english"]
    assert "Geen paring word geskep" in first["afrikaans"]
    assert first["delivery_enabled"] is first["mating_execution_enabled"] is first["writes_performed"] is first["protected_actions_performed"] is False


def test_reproductive_source_conflict_is_prioritized_without_physical_question():
    reconciled,assessment=evidence()
    reconciled["females"][3]["cycle_evidence"]={"status":"conflicting","conflicts":["two current litter representations"]}
    result=build_breeding_management_packet(reconciled,assessment,today=TODAY)
    assert [row["action_id"] for row in result["actions"]]==["reproductive-data-quality","farrowing-preparation","inconclusive-cycle"]
    assert result["actions"][0]["smallest_physical_observation"]=="No new physical observation is requested for a source-record conflict."


def test_rejects_malformed_duplicate_or_unbound_assessment_rows():
    reconciled,assessment=evidence()
    broken=deepcopy(assessment); broken["cases"]=["not-a-row"]
    assert build_breeding_management_packet(reconciled,broken,today=TODAY)["success"] is False
    broken=deepcopy(assessment); broken["reconciliation_digest"]="older"
    assert build_breeding_management_packet(reconciled,broken,today=TODAY)["success"] is False
    broken=deepcopy(assessment); broken["cases"].append(deepcopy(broken["cases"][0]))
    assert build_breeding_management_packet(reconciled,broken,today=TODAY)["success"] is False


def test_public_packet_is_allowlisted_and_excludes_internal_provenance_and_evidence_text():
    reconciled,assessment=evidence()
    assessment["cases"][0]["confirmed_evidence"]=["PRIVATE-INTERNAL-CONTEXT"]
    material={key:assessment[key] for key in ("contract_version","reconciliation_digest","cases","boar_inventory")}
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    assessment["material_evidence_digest"]=digest; assessment["assessment_id"]=f"HERD-BREED-{digest[:32].upper()}"
    result=build_breeding_management_packet(reconciled,assessment,today=TODAY)
    public=json.dumps(result["oom_sakkie_packet"],sort_keys=True)
    assert result["internal_only"] is True
    assert "PRIVATE-INTERNAL-CONTEXT" not in public
    assert "import_batch_id" not in public and "source_sheet_row" not in public
    assert result["oom_sakkie_packet"]["mating_execution_enabled"] is False


def test_public_packet_normalizes_control_characters_and_bounds_owner_text():
    reconciled,assessment=evidence()
    reconciled["females"][0]["tag_number"]="Mona\n@all"+("x"*200)
    assessment["cases"][0]["tag_number"]=reconciled["females"][0]["tag_number"]
    material={key:assessment[key] for key in ("contract_version","reconciliation_digest","cases","boar_inventory")}
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    assessment["material_evidence_digest"]=digest; assessment["assessment_id"]=f"HERD-BREED-{digest[:32].upper()}"
    public=build_breeding_management_packet(reconciled,assessment,today=TODAY)["oom_sakkie_packet"]
    tag=public["actions"][0]["animals"][0]["tag_number"]
    assert "\n" not in tag and len(tag)<=80


def test_rejects_duplicate_or_wrong_sex_boar_inventory():
    reconciled,assessment=evidence()
    reconciled["boars"]=[{"pig_id":"MONA","tag_number":"Collision","sex":"Male"}]
    assert build_breeding_management_packet(reconciled,assessment,today=TODAY)["success"] is False
    reconciled,assessment=evidence()
    reconciled["boars"]=[{"pig_id":"BOAR","tag_number":"Wrong","sex":"Female"}]
    assert build_breeding_management_packet(reconciled,assessment,today=TODAY)["success"] is False
