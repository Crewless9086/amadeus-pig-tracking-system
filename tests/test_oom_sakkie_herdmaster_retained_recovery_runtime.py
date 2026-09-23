from unittest.mock import patch

from modules.oom_sakkie.herdmaster_retained_recovery_runtime import (
    build_retained_protected_preview, execute_claimed_litter_piglet_deaths,
    retained_report_binding)


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
        "owner_text_verbatim":"Linds 3 kleintjies dood", "provider_message_id":"4052",
        "mission_id":"REPORT-A", "status":"waiting_for_input"},),
        ({"owner_user_id":"ANTON", "chat_id":"ANTON",
        "owner_text_verbatim":"Linda kleintjies dood op 26 Aug", "provider_message_id":"4054",
        "mission_id":"REPORT-B", "status":"waiting_for_input",
        "preview":{"evaluator":{"identity":{"resolved":True,"pig_id":"SOW-A"}}}},)]
    case = {"dedupe_key":"herdmaster:retained-litter-loss:4052:2026-08-26",
        "evidence_digest":"DIGEST", "evidence_refs":["provider_message:4052",
        "provider_message:4054", "incident_date:2026-08-26"]}
    case["evidence_refs"].append(retained_report_binding([row[0] for row in retained]))
    dry = {"success":True,"pig_ids":["P1","P2","P3"],"selected_piglets":[]}
    claim = {"callback_token":"TOKEN","preview_digest":"PREVIEW"}
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               side_effect=[Connection([retained, retained, []]), Connection([[("LITTER-LINDA",)]])]), \
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
        "mission_id": "REPORT-C", "status": "waiting_for_input",
        "provider_message_id": "3926", "provider_timestamp": "2026-08-23T20:29:12+00:00",
        "output_language": "af", "owner_text_verbatim": "Vark nr 146 dood op 23 Aug 2026"},)]
    preview = {"success": True, "question_count": 1,
        "owner_text": "One question: was 146 removed and disposed?",
        "evaluator": {"identity": {"pig_id": "PIG-2026-E58B", "tag_number": "146"}}}
    case = {"dedupe_key": "herdmaster:retained-mortality:3926",
        "evidence_refs": ["provider_message:3926", "pig:PIG-2026-E58B", "tag:146"]}
    case["evidence_refs"].append(retained_report_binding([row[0] for row in retained]))
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               return_value=Connection([retained, retained, []])), \
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


# Synthetic identities below deliberately differ from private farm evidence.
def report(provider="101", mission="REPORT-101", **changes):
    return {"owner_user_id": "42", "chat_id": "42", "provider_message_id": provider,
        "mission_id": mission, "status": "waiting_for_input",
        "owner_text_verbatim": "Vark nr 27 dood op 19 Aug", **changes}


def report_evidence(rows, *, lifecycle=None, claims=()):
    return {"reports": rows, "lifecycle": list(rows if lifecycle is None else lifecycle),
            "claims": list(claims)}


def test_resolver_rejects_missing_member_wrong_principal_and_provider_collision():
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import resolve_retained_health_reports as resolve
    base = report()
    for evidence, ids in [
        (report_evidence([base]), ["101", "102"]),
        (report_evidence([base, report("102", "REPORT-102", owner_user_id="99", chat_id="99")]), ["101", "102"]),
        (report_evidence([base, report(owner_user_id="99", chat_id="99")]), ["101"]),
        (report_evidence([report(chat_id="GROUP")]), ["101"]),
        (report_evidence([base, report(mission="OTHER")]), ["101"]),
    ]:
        rows, failure = resolve(evidence, ids)
        assert rows == [] and failure


def test_latest_mission_state_includes_new_callback_id_and_corrections():
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import resolve_retained_health_reports as resolve
    base = report()
    for change in ({"status": "contained", "provider_message_id": "901"},
                   {"status": "completed"}, {"status": "preview_correction_pending"},
                   {"correction_digest": "NEW"}, {"invalidated_operation_ids": ["OLD"]},
                   {"owner_text_verbatim": "Corrected observation"}):
        rows, failure = resolve(report_evidence([base], lifecycle=[{**base, **change}, base]), ["101"])
        assert rows == [] and failure == "retained_report_no_longer_unresolved"
    rows, failure = resolve(report_evidence([base]), ["101"])
    assert rows == [base] and failure == ""


def test_related_consumption_and_duplicate_binding_never_revive_original_report():
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import resolve_retained_health_reports as resolve
    base = report()
    for link in ({"consumed_context_missions": ["REPORT-101"]},
                 {"superseded_duplicate_bindings": [{"mission_id": "REPORT-101",
                     "provider_message_id": "101", "tag_number": "27"}]},
                 {"superseded_duplicate_bindings": [{"mission_id": "REPORT-101"}]}):
        related = report("901", "CORRECTION", **link)
        rows, failure = resolve(report_evidence([base], lifecycle=[related, base]), ["101"])
        assert rows == [] and failure == "retained_report_correction_requires_reconciliation"


def test_existing_protected_attempts_do_not_license_a_new_recovery_identity():
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import resolve_retained_health_reports as resolve
    for status in ("active", "cancelled", "changed", "executing", "contained", "completed", "expired"):
        for mission, provider, payload in (
            ("REPORT-101", "901", {}), ("DERIVED", "101", {}),
            ("DERIVED", "901", {"provider_message_ids": ["101", "102"]})):
            claim = ("42", "42", mission, provider, status, "mortality", payload)
            rows, failure = resolve(report_evidence([report()], claims=[claim]), ["101"])
            assert rows == [] and failure == "retained_report_existing_protected_attempt"


def test_preview_boundary_reloads_lifecycle_and_never_claims_cancelled_report():
    original = report()
    cancelled = {**original, "status": "contained", "provider_message_id": "901"}
    case = {"dedupe_key": "herdmaster:retained-mortality:101",
            "evidence_refs": ["provider_message:101", "pig:P27", "tag:27"]}
    with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
               return_value=Connection([[(original,)], [(cancelled,), (original,)], []])), \
         patch("modules.oom_sakkie.protected_action_claims.create_claim") as claim, \
         patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence") as farm:
        result = build_retained_protected_preview(case)
    assert result["status"] == "retained_report_no_longer_unresolved"
    assert result["suppress_owner_delivery"] and result["telegram_sends"] == 0
    farm.assert_not_called(); claim.assert_not_called()


def test_resolver_overflow_never_uses_partial_evidence():
    import pytest
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import read_retained_health_reports
    for responses in ([[(report(),)] * 1025],
                      [[(report(),)], [(report(),)] * 1025],
                      [[(report(),)], [(report(),)], [("42",) * 7] * 1025]):
        with pytest.raises(ValueError, match="read_bound_exceeded"):
            read_retained_health_reports(Cursor(responses), ["101"])


def test_changed_incident_or_tag_contains_before_preview_and_claim():
    import pytest
    # A syntactically valid reference cannot retarget a canonical owner report.
    cases = [({"dedupe_key": "herdmaster:retained-mortality:101",
               "evidence_refs": ["provider_message:101", "pig:P28", "tag:28"]}, report()),
             ({"dedupe_key": "herdmaster:retained-litter-loss:101:2026-08-20",
               "evidence_refs": ["provider_message:101", "incident_date:2026-08-20"]},
              report(owner_text_verbatim="Linda 2 kleintjies dood op 19 Aug"))]
    for case, row in cases:
        case["evidence_refs"].append(retained_report_binding([row]))
        with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
                   return_value=Connection([[(row,)], [(row,)], []])), \
             patch("modules.oom_sakkie.protected_action_claims.create_claim") as claim:
            result = build_retained_protected_preview(case)
        expected = ("retained_mortality_exact_identity_unproven" if "mortality" in case["dedupe_key"]
                    else "retained_litter_loss_exact_facts_unproven")
        assert result["status"] == expected
        assert result["success"] is False and result["suppress_owner_delivery"] is True
        claim.assert_not_called()


def test_bound_principal_and_source_mission_replacement_is_not_a_new_preview():
    base = report()
    case = {"dedupe_key": "herdmaster:retained-mortality:101", "evidence_refs": [
        "provider_message:101", "pig:P27", "tag:27", retained_report_binding([base])]}
    for changed in (report(owner_user_id="99", chat_id="99"), report(mission="REPLACED")):
        with patch("modules.oom_sakkie.herdmaster_retained_recovery_runtime.connect_bounded_read",
                   return_value=Connection([[(changed,)], [(changed,)], []])), \
             patch("modules.oom_sakkie.protected_action_claims.create_claim") as claim:
            result = build_retained_protected_preview(case)
        assert result["status"] == "retained_report_source_binding_unproven"
        claim.assert_not_called()
