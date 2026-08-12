from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import (
    ACTION_KIND,
    handle_grouped_breeding_message,
)


def _parsed(rows):
    return {
        "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9001", "text": "grouped breeding facts",
        "semantic": {"domain": "herd_management", "evidence_generation": "GEN-1",
                     "breeding_actions": rows},
    }


def _evidence():
    return {"success": True, "allocation_inputs": {"pig_master_rows": [
        {"Pig_ID":"SOW-1","Tag_Number":"Ms Piggy"},
        {"Pig_ID":"SOW-2","Tag_Number":"Linda"},
        {"Pig_ID":"BOAR-1","Tag_Number":"Bola"},
    ]}}


def test_authenticated_group_creates_one_existing_rail_claim_and_no_write():
    captured = {}
    def claim_creator(**kwargs):
        captured.update(kwargs)
        return {"callback_token": "TOKEN", "preview_digest": "DIGEST"}
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold",
         "body_condition_score":2,"observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Body condition scored 2."},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Appears close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), claim_creator=claim_creator,
        evidence_loader=_evidence)
    assert status == 200
    assert result["status"] == "breeding_grouped_preview_ready"
    assert captured["action_kind"] == ACTION_KIND
    assert captured["preview_payload"]["writes_performed"] is False
    assert result["writes_farm_data"] is False
    assert result["sends_telegram"] is False


def test_partial_group_fails_before_claim_or_write():
    called = []
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"exposure","boar_ref":"Bola"},
    ]), issue_gateway_owner_authority("42", "42"),
        claim_creator=lambda **kwargs: called.append(kwargs), evidence_loader=_evidence)
    assert status == 200
    assert result["success"] is False
    assert called == []
    assert result["writes_farm_data"] is False


def test_ambiguous_identity_asks_one_question_before_claim():
    evidence = _evidence()
    evidence["allocation_inputs"]["pig_master_rows"].append(
        {"Pig_ID":"SOW-3","Tag_Number":"Linda"})
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"Close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), evidence_loader=lambda: evidence)
    assert status == 200
    assert result["status"] == "breeding_identity_clarification_required"
    assert result["question_count"] == 1
    assert result["question_count"] == 1


def test_non_owner_is_fail_closed():
    parsed = _parsed([{"animal_ref":"Linda","action":"near_farrowing"}])
    parsed["telegram_chat_id"] = "99"
    result, status = handle_grouped_breeding_message(
        parsed, issue_gateway_owner_authority("42", "99"))
    assert status == 403
    assert result["writes_farm_data"] is False


def test_genuine_seven_row_update_calculates_duration_and_renders_every_fact():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Ms Piggy","S6"),("Linda","S7"),("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    rows=[{"animal_ref":sow,"action":"exposure","boar_ref":boar,
           "exposure_started_on":"2026-08-12","planned_days":17}
          for sow,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                           ("Lucy","Tyson"),("Lolly","Prince"))]
    rows += [{"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
              "observed_at":"2026-08-12T11:41:25+00:00"},
             {"animal_ref":"Linda","action":"near_farrowing","prior_mating_known":False,
              "father_known":False,"observed_at":"2026-08-12T11:41:25+00:00"}]
    captured={}
    result,status=handle_grouped_breeding_message(_parsed(rows),
        issue_gateway_owner_authority("42","42"),evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    preview=captured["preview_payload"]["preview"]
    assert preview["row_count"] == 7
    assert [row["planned_removal_on"] for row in preview["rows"][:5]] == ["2026-08-29"]*5
    assert all(name in result["answer"] for name in
               ("Sophie","Olive","Shupe","Lucy","Lolly","Ms Piggy","Linda"))
    assert "Nothing has been recorded yet" in result["answer"]
    assert "previous mating date and father Unknown" in result["answer"]
