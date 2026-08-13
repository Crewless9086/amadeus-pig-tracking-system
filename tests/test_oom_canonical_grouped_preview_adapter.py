from copy import deepcopy
from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.grouped_weight_runtime import handle_grouped_weight_message
from modules.pig_weights.canonical_grouped_preview import preview_application_typed


PIGS = [
    {"pig_id":"PIG-OPAQUE-A","tag_number":"A1","status":"Active","on_farm":"Yes","current_pen_id":"PEN-OLD"},
    {"pig_id":"PIG-OPAQUE-B","tag_number":"B2","status":"Active","on_farm":"Yes","current_pen_id":""},
]
PENS = [{"pen_id":"PEN-OPAQUE-D3","pen_name":"D3","active":True}]
TEXT = "A1 - 47.20 kg, B2 - 118 kg; all moved to pen D3 on 2026-08-13"


def _parsed(text=TEXT):
    return {"text":text,"telegram_user_id":"42","telegram_chat_id":"42",
        "provider_message_id":"5001","provider_timestamp":"2026-08-13T06:30:00+00:00",
        "semantic":{"domain":"herd_management","language":"en"}}


def _preflight(payload):
    return {"success":True,"accepted_count":len(payload["rows"]),"accepted_rows":payload["rows"]},200


def _claim(**kwargs):
    return {"success":True,"callback_token":"opaque123","preview_digest":"f"*64}


def _run(*, pigs=PIGS, pens=PENS, text=TEXT, claim=_claim):
    return handle_grouped_weight_message(_parsed(text),issue_gateway_owner_authority("42","42"),
        readiness_loader=lambda:{"success":True,"pigs":deepcopy(pigs)},preflight=_preflight,
        pen_loader=lambda:deepcopy(pens),claim_creator=claim)


def test_typed_oom_matches_equivalent_application_canonical_rows_and_digest():
    result,status=_run()
    application=preview_application_typed({"effective_date":"2026-08-13","destination_pen":"D3",
        "rows":[{"identity":"A1","weight_kg":"47.20"},{"identity":"B2","weight_kg":118}]},
        pigs=PIGS,pens=PENS)
    assert status==200 and result["success"] is True
    assert result["mappings"]==application["rows"]
    assert result["weight_date"]==application["effective_date"]
    assert result["confirmation_required"]==application["confirmation_required"] is True
    assert result["preview_digest"]==application["preview_digest"]
    assert result["protected_claim_digest"]=="f"*64


def test_unknown_optional_values_are_preserved_in_canonical_rows():
    captured={}
    def claim(**kwargs):captured.update(kwargs);return _claim(**kwargs)
    result,status=_run(text="A1 47.2 kg, B2 118 kg on 2026-08-13",claim=claim)
    assert status==200 and result["success"] is True
    assert result["mappings"][1]["current_pen_id"]=="Unknown"
    assert {row["moved_to_pen_id"] for row in result["mappings"]}=={"Unknown"}
    assert all(row["condition_notes"]=="Unknown" for row in result["mappings"])
    execution_rows=captured["preview_payload"]["rows"]
    assert execution_rows[1]["current_pen_id"]==""
    assert {row["moved_to_pen_id"] for row in execution_rows}=={""}
    assert all(isinstance(row["weight_kg"],float) for row in execution_rows)


def test_ambiguous_and_inactive_identity_fail_before_claim_creation():
    for pigs,expected in (
        (PIGS+[{**PIGS[0],"pig_id":"PIG-OTHER"}],"animal_identity_ambiguous"),
        ([{**PIGS[0],"status":"Sold"},PIGS[1]],"animal_not_active_on_farm"),
    ):
        claim=[]
        result,status=_run(pigs=pigs,claim=lambda **kwargs:claim.append(kwargs))
        assert status==200 and result["success"] is False and result["status"]==expected
        assert claim==[]


def test_malformed_or_conflicting_date_fails_closed_without_claim():
    claim=[]
    result,status=_run(text="A1 47 kg on 2026-08-12, B2 118 kg on 2026-08-13",
        claim=lambda **kwargs:claim.append(kwargs))
    assert status==200 and result["status"]=="weight_date_ambiguous"
    assert claim==[]


def test_identical_replay_is_deterministic_and_zero_effect():
    first,_=_run(); second,_=_run()
    assert first["preview_digest"]==second["preview_digest"]
    assert first["mappings"]==second["mappings"]
    for result in (first,second):
        assert result["writes_farm_data"] is False
        assert result["writes_weights"] is False
        canonical=result["canonical_preview"]
        assert canonical["writes_performed"] is False
        assert {canonical[key] for key in ("database_calls","provider_calls","telegram_calls","google_sheets_calls","farm_writes")}=={0}


def test_execution_and_completion_modules_are_never_called_by_preview():
    with patch("modules.oom_sakkie.protected_action_claims.execute_grouped_weight_claim") as execute, \
         patch("modules.oom_sakkie.protected_action_claims.complete_claim") as complete:
        result,status=_run()
    assert status==200 and result["success"] is True
    execute.assert_not_called(); complete.assert_not_called()
