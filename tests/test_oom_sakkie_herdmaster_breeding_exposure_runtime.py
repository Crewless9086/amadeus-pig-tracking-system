from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import (
    ACTION_KIND,
    handle_grouped_breeding_message,
    parse_grouped_exposure_reply,
)
from pathlib import Path


def _parsed(rows):
    return {
        "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9001", "provider_timestamp":"2026-08-12T11:41:25Z",
        "text": "grouped breeding facts",
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


def test_provider_identity_and_timezone_aware_chronology_are_required_before_claim():
    for field, value in (("provider_message_id", ""), ("provider_timestamp", ""),
                         ("provider_timestamp", "2026-08-12T11:41:25"),
                         ("provider_timestamp", "not-a-time")):
        parsed = _parsed([{"animal_ref":"Linda","action":"near_farrowing"}])
        parsed[field] = value
        called = []
        result, status = handle_grouped_breeding_message(
            parsed, issue_gateway_owner_authority("42", "42"),
            evidence_loader=_evidence, claim_creator=lambda **kw: called.append(kw))
        assert status == 422
        assert result["status"] == "breeding_provider_provenance_required"
        assert result["writes_farm_data"] is False and called == []


def test_authenticated_provider_time_overrides_unproven_semantic_observation_time():
    captured = {}
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2035-01-01T00:00:00+00:00"},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2035-01-01T00:00:00+00:00"},
    ]), issue_gateway_owner_authority("42", "42"), evidence_loader=_evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    assert [row["observed_at"] for row in captured["preview_payload"]["preview"]["rows"]] == [
        "2026-08-12T11:41:25+00:00", "2026-08-12T11:41:25+00:00"]


def test_claim_persistence_failure_is_visibly_contained_without_write():
    result,status=handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"BCS 2"},
    ]),issue_gateway_owner_authority("42","42"),evidence_loader=_evidence,
       claim_creator=lambda **_kwargs:(_ for _ in ()).throw(RuntimeError("constraint")))
    assert status == 503 and result["status"] == "breeding_group_claim_unavailable"
    assert result["writes_farm_data"] is False and "Nothing was recorded" in result["answer"]
    assert "retained" not in result["answer"].lower()
    assert "original provider-bound message" in result["answer"]


def test_existing_card_bound_claim_is_a_zero_delivery_replay():
    result,status=handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"BCS 2"},
    ]),issue_gateway_owner_authority("42","42"),evidence_loader=_evidence,
       claim_creator=lambda **_kwargs:{"status":"protected_claim_existing",
          "callback_token":"TOKEN","preview_card_message_id":"3553"})
    assert status == 200 and result["status"] == "breeding_group_preview_replay_suppressed"
    assert result["replay_suppressed"] is True and result["suppress_owner_delivery"] is True
    assert result["answer"] == "" and result["writes_farm_data"] is False


def test_claim_kind_migration_is_idempotent_private_and_allows_breeding():
    sql=Path("supabase/migrations/202608120002_allow_breeding_protected_claims.sql").read_text().lower()
    assert "herdmaster_breeding_grouped" in sql
    assert "drop constraint" in sql and "add constraint" in sql
    assert "revoke all on app_private.oom_protected_action_claims from public, anon, authenticated" in sql
    assert "on conflict (migration_id) do nothing" in sql


def test_genuine_seven_row_update_calculates_duration_and_renders_every_fact():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Ms Piggy","S6"),("Linda","S7"),("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    rows=[{"animal_ref":sow,"action":"exposure","boar_ref":boar,
           "exposure_started_on":"2026-08-12","planned_days":17}
          for sow,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                           ("Lucy","Tyson"),("Lolly","Prince"))]
    rows += [{"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2},
             {"animal_ref":"Linda","action":"near_farrowing","prior_mating_known":False,
              "father_known":False}]
    captured={}
    result,status=handle_grouped_breeding_message(_parsed(rows),
        issue_gateway_owner_authority("42","42"),evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    preview=captured["preview_payload"]["preview"]
    assert preview["row_count"] == 7
    assert [row["planned_removal_on"] for row in preview["rows"][:5]] == ["2026-08-28"]*5
    assert all(name in result["answer"] for name in
               ("Sophie","Olive","Shupe","Lucy","Lolly","Ms Piggy","Linda"))
    assert "Nothing has been recorded yet" in result["answer"]
    assert "previous mating date and father Unknown" in result["answer"]
    assert preview["rows"][5]["observed_at"] == "2026-08-12T11:41:25+00:00"
    assert preview["rows"][6]["observed_at"] == "2026-08-12T11:41:25+00:00"


def test_retained_3556_afrikaans_boar_first_reply_parses_exactly_five_exposures():
    rows=parse_grouped_exposure_reply(
        "Plasing was vandag 2026-08-12\n\nBola - Sophie\n"
        "Tyson - Olive, Shupe, Lucy\nPrince - Lolly",
        provider_timestamp="2026-08-12T12:44:13+00:00")
    assert [(row["boar_ref"],row["animal_ref"]) for row in rows] == [
        ("Bola","Sophie"),("Tyson","Olive"),("Tyson","Shupe"),
        ("Tyson","Lucy"),("Prince","Lolly")]
    assert {row["exposure_started_on"] for row in rows} == {"2026-08-12"}
    assert {row["planned_days"] for row in rows} == {17}


def test_grouped_parser_supports_english_colons_conjunctions_and_named_date():
    rows=parse_grouped_exposure_reply(
        "Placed on 12 August 2026\nBola: Sophie and Olive\nTyson: Shupe & Lucy")
    assert [(row["boar_ref"],row["animal_ref"]) for row in rows] == [
        ("Bola","Sophie"),("Bola","Olive"),("Tyson","Shupe"),("Tyson","Lucy")]


def test_grouped_parser_uses_provider_date_for_today_and_ignores_explicit_not_placed():
    rows=parse_grouped_exposure_reply(
        "Vandag geplaas\nBola - Sophie\nMs Piggy en Linda was nie geplaas nie",
        provider_timestamp="2026-08-12T12:44:13+00:00")
    assert [row["animal_ref"] for row in rows] == ["Sophie"]
    assert rows[0]["exposure_started_on"] == "2026-08-12"


def test_grouped_parser_fails_closed_on_duplicate_female_or_missing_shared_date():
    assert parse_grouped_exposure_reply("Bola - Sophie\nTyson - Sophie") == ()
    assert parse_grouped_exposure_reply(
        "2026-08-12\nBola - Sophie\nTyson - Sophie") == ()


def test_deterministic_group_parser_repairs_incomplete_llm_shape_before_binding():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    parsed=_parsed([{"animal_ref":"Sophie","action":"exposure","boar_ref":"Bola"}])
    parsed["provider_message_id"]="3556"
    parsed["provider_timestamp"]="2026-08-12T12:44:13+00:00"
    parsed["text"]=("Plasing was vandag 2026-08-12\n\nBola - Sophie\n"
                    "Tyson - Olive, Shupe, Lucy\nPrince - Lolly")
    captured={}
    result,status=handle_grouped_breeding_message(parsed,issue_gateway_owner_authority("42","42"),
        evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    assert captured["provider_message_id"] == "3556"
    assert captured["preview_payload"]["preview"]["row_count"] == 5
    assert {row["planned_removal_on"] for row in captured["preview_payload"]["preview"]["rows"]} == {"2026-08-28"}
