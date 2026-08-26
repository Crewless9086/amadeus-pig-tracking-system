from unittest.mock import patch

from modules.oom_sakkie.herdmaster_retained_recovery_runtime import (
    build_retained_protected_preview, execute_claimed_litter_piglet_deaths)


class Cursor:
    def __init__(self, results): self.results, self.index = results, -1
    def execute(self, *_args): self.index += 1
    def fetchall(self): return self.results[self.index]
    def fetchone(self):
        rows = self.results[self.index]
        return rows[0] if rows else None
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class Connection:
    def __init__(self, results): self.results = results
    def cursor(self): return Cursor(self.results)
    def __enter__(self): return self
    def __exit__(self, *_args): return False


def test_production_linda_builder_creates_exact_protected_preview_without_write():
    retained = [({"owner_user_id":"ANTON", "chat_id":"ANTON",
        "owner_text_verbatim":"Linds 3 kleintjies dood", "provider_message_id":"4052"},),
        ({"owner_user_id":"ANTON", "chat_id":"ANTON",
        "owner_text_verbatim":"Linda kleintjies dood op 26 Aug", "provider_message_id":"4054"},)]
    case = {"dedupe_key":"herdmaster:retained-litter-loss:4052:2026-08-26",
        "evidence_digest":"DIGEST", "evidence_refs":["provider_message:4052",
        "provider_message:4054", "incident_date:2026-08-26"]}
    dry = {"success":True,"pig_ids":["P1","P2","P3"],"selected_piglets":[]}
    claim = {"callback_token":"TOKEN","preview_digest":"PREVIEW"}
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               return_value=Connection([retained, [("LITTER-LINDA",)]])), \
         patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead",
               return_value=(dry, 200)) as action, \
         patch("modules.oom_sakkie.protected_action_claims.create_claim",
               return_value=claim) as create:
        result = build_retained_protected_preview(case)
    assert result["success"] is True and result["callback_token"] == "TOKEN"
    assert result["confirmation_required"] is True and result["writes_farm_data"] is False
    assert action.call_args.kwargs["dry_run"] is True
    assert create.call_args.kwargs["preview_payload"]["pig_ids"] == ["P1","P2","P3"]


def test_linda_execution_uses_exact_bound_selection_only_after_claim():
    claimed={"preview_payload":{"contract_version":"herdmaster_litter_piglet_deaths_v1",
        "owner_user_id":"ANTON","litter_id":"L1","event_date":"2026-08-26",
        "reason":"Unknown","operation_id":"HERD-LITTER-LOSS-EXACT",
        "pig_ids":["P1","P2","P3"]}}
    with patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead",
               return_value=({"success":True,"piglet_count":3},200)) as action, \
         patch("modules.pig_weights.pig_weights_service._get_pig_master_rows",
               return_value=[]):
        result,status=execute_claimed_litter_piglet_deaths(
            claimed,{"telegram_user_id":"ANTON"})
    assert status == 200 and result["success"] is True
    assert action.call_args.kwargs == {"pig_ids":["P1","P2","P3"],
        "changed_by":"oom_sakkie:HERD-LITTER-LOSS-EXACT","dry_run":False}


def test_same_receipt_recovers_committed_deaths_without_second_mutation():
    operation="HERD-LITTER-LOSS-EXACT"
    claimed={"mission_id":"MISSION","preview_payload":{
        "contract_version":"herdmaster_litter_piglet_deaths_v1",
        "owner_user_id":"ANTON","litter_id":"L1","event_date":"2026-08-26",
        "reason":"Unknown","operation_id":operation,"pig_ids":["P1","P2","P3"]}}
    rows=[{"Pig_ID":pig,"Status":"Dead","On_Farm":"No",
           "General_Notes":"Recorded by oom_sakkie:"+operation} for pig in ("P1","P2","P3")]
    with patch("modules.pig_weights.pig_weights_service._get_pig_master_rows",
               return_value=rows), \
         patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead") as action:
        result,status=execute_claimed_litter_piglet_deaths(claimed,{"telegram_user_id":"ANTON"})
    assert status==200 and result["status"]=="litter_piglet_deaths_recovered_from_canonical"
    assert result["rows_updated"]==0
    action.assert_not_called()


def test_partial_operation_marker_with_missing_bound_row_holds_without_mutation():
    operation="HERD-LITTER-LOSS-PARTIAL"
    claimed={"mission_id":"MISSION","preview_payload":{
        "contract_version":"herdmaster_litter_piglet_deaths_v1",
        "owner_user_id":"ANTON","litter_id":"L1","event_date":"2026-08-26",
        "reason":"Unknown","operation_id":operation,"pig_ids":["P1","P2","P3"]}}
    rows=[{"Pig_ID":"P1","Status":"Dead","On_Farm":"No",
           "General_Notes":"oom_sakkie:"+operation},
          {"Pig_ID":"P2","Status":"Active","On_Farm":"Yes","General_Notes":""}]
    with patch("modules.pig_weights.pig_weights_service._get_pig_master_rows",
               return_value=rows), \
         patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead") as action:
        result,status=execute_claimed_litter_piglet_deaths(claimed,{"telegram_user_id":"ANTON"})
    assert status==503 and result["recovery_required"] is True
    assert result["status"]=="litter_piglet_deaths_partial_readback_recovery_required"
    action.assert_not_called()


def test_pig138_unknown_case_kind_is_suppressed_before_any_claim():
    result=build_retained_protected_preview({"dedupe_key":"herdmaster:suppressed:138",
        "evidence_refs":["provider_message:4057"]})
    assert result["success"] is False and result["suppress_owner_delivery"] is True


def test_mona_existing_undelivered_claim_is_routed_without_duplicate_claim():
    row = [("ANTON", "ANTON", "4051", {"counts": {"total_born": 12,
        "stillborn": 1}, "farrowing_date": "2026-08-26"}, "TOKEN", "MISSION",
        "DIGEST", "active", None)]
    case = {"dedupe_key": "herdmaster:expired-farrowing:OLD",
        "evidence_digest": "EVIDENCE", "evidence_refs": ["provider_message:4051"]}
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               return_value=Connection([row])), \
         patch("modules.oom_sakkie.protected_action_claims.create_claim") as create:
        result = build_retained_protected_preview(case)
    assert result["success"] is True and result["callback_token"] == "TOKEN"
    assert result["mission_id"] == "MISSION"
    create.assert_not_called()


def test_pig146_fresh_recovery_proves_identity_then_retains_only_missing_disposal():
    retained = [({"owner_user_id": "ANTON", "chat_id": "ANTON",
        "provider_message_id": "3926", "provider_timestamp": "2026-08-23T20:29:12+00:00",
        "output_language": "af", "owner_text_verbatim": "Vark nr 146 dood op 23 Aug 2026"},)]
    preview = {"success": True, "question_count": 1,
        "owner_text": "One question: was 146 removed and disposed?",
        "evaluator": {"identity": {"pig_id": "PIG-2026-E58B", "tag_number": "146"}}}
    case = {"dedupe_key": "herdmaster:retained-mortality:3926",
        "evidence_refs": ["provider_message:3926", "pig:PIG-2026-E58B", "tag:146"]}
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               return_value=Connection([retained])), \
         patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
               return_value={"evidence_generation": "EVIDENCE"}), \
         patch("modules.oom_sakkie.herdmaster_health_loss_preview.prepare_health_loss_owner_preview",
               return_value=preview), \
         patch("modules.oom_sakkie.protected_action_claims.create_claim") as create:
        result = build_retained_protected_preview(case)
    assert result["status"] == "retained_mortality_removed_disposal_required"
    assert result["missing_facts"] == ["removed_disposal"]
    assert result["suppress_owner_delivery"] is True
    create.assert_not_called()
