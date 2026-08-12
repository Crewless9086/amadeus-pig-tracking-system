from modules.oom_sakkie.herdmaster_breeding_semantic_mapper import resolve_breeding_actions


def entities():
    pairs = (("Sophie","PIG-S","Female"),("Olive","PIG-O","Female"),
             ("Shupe","PIG-H","Female"),("Lucy","PIG-LU","Female"),
             ("Lolly","PIG-LO","Female"),("Ms Piggy","PIG-MS","Female"),
             ("Linda","PIG-LI","Female"),("Bola","PIG-B","Male"),
             ("Tyson","PIG-T","Male"),("Prince","PIG-P","Male"))
    return [{"name":name,"tag_number":name,"pig_id":pig_id,"sex":sex,
             "status":"Active","on_farm":True,"updated_at":"2026-08-12T10:00:00Z"}
            for name,pig_id,sex in pairs]


def facts():
    rows=[{"kind":"exposure","sow":sow,"boar":boar,
           "exposure_started_on":"2026-08-12","planned_days":17}
          for sow,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                           ("Lucy","Tyson"),("Lolly","Prince"))]
    rows.extend(({"kind":"recovery_hold","sow":"Ms Piggy","body_condition_score":2},
                 {"kind":"near_farrowing","sow":"Linda","prior_mating_known":False,
                  "father_known":False}))
    return rows


def test_genuine_group_resolves_every_fact_into_exact_herdmaster_actions():
    result=resolve_breeding_actions(facts(),provider_timestamp="2026-08-12T11:41:25Z",
                                    entity_loader=entities)
    assert result["success"] is True and result["row_count"] == 7
    assert [row["pig_id"] for row in result["breeding_actions"]] == [
        "PIG-S","PIG-O","PIG-H","PIG-LU","PIG-LO","PIG-MS","PIG-LI"]
    assert result["breeding_actions"][0]["planned_removal_on"] == "2026-08-29"
    assert result["breeding_actions"][5]["body_condition_score"] == 2
    assert "unknown" in result["breeding_actions"][6]["factual_note"].lower()
    assert len(result["evidence_generation"]) == 64


def test_resolution_fails_closed_for_ambiguity_duplicate_or_wrong_sex():
    ambiguous=entities()+[{**entities()[0],"pig_id":"PIG-S2"}]
    assert resolve_breeding_actions(facts(),provider_timestamp="2026-08-12T11:41:25Z",
        entity_loader=lambda:ambiguous)["status"] == "canonical_breeding_entity_ambiguous"
    duplicate=facts()+[facts()[0]]
    assert resolve_breeding_actions(duplicate,provider_timestamp="2026-08-12T11:41:25Z",
        entity_loader=entities)["status"] == "duplicate_sow_in_group"
    wrong=entities(); wrong[0]["sex"]="Male"
    assert resolve_breeding_actions(facts(),provider_timestamp="2026-08-12T11:41:25Z",
        entity_loader=lambda:wrong)["status"] == "canonical_breeding_entity_not_found"


def test_provider_time_and_unknown_parent_evidence_are_mandatory():
    assert resolve_breeding_actions(facts(),provider_timestamp="",entity_loader=entities)["success"] is False
    changed=facts(); changed[-1]["father_known"]=True
    assert resolve_breeding_actions(changed,provider_timestamp="2026-08-12T11:41:25Z",
        entity_loader=entities)["status"] == "near_farrowing_unknowns_not_preserved"
