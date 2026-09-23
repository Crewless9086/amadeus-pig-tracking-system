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
    retained = [({"owner_user_id":"42", "chat_id":"42",
        "owner_text_verbatim":"Linds 3 kleintjies dood", "provider_message_id":"4052",
        "mission_id":"REPORT-A", "status":"waiting_for_input",
        "provider_timestamp":"2026-08-27T08:00:00+00:00"},),
        ({"owner_user_id":"42", "chat_id":"42",
        "owner_text_verbatim":"Linda kleintjies dood op 26 Aug", "provider_message_id":"4054",
        "mission_id":"REPORT-B", "status":"waiting_for_input",
        "provider_timestamp":"2026-08-27T08:01:00+00:00",
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
    retained = [({"owner_user_id": "42", "chat_id": "42",
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


# Full local call path; only storage transports and external effect boundaries
# are in-memory. The PG suite below separately qualifies real SQL/row locks.
import copy
import json
import pytest
from datetime import datetime, timedelta, timezone


@pytest.fixture
def retained_journey(monkeypatch):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie import family_message_lifecycle as family
    from modules.oom_sakkie import protected_action_claims as claims
    from modules.oom_sakkie import protected_delivery_lifecycle as delivery
    from modules.oom_sakkie import general_manager_worker as worker
    source = report(provider_timestamp="2026-08-20T08:00:00+00:00", output_language="af",
        owner_text_verbatim="Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe.")
    evidence = {"evidence_generation": "GEN-27", "as_of_timestamp": "2026-09-23T04:45:00+00:00",
        "animals": [{"pig_id": "P27", "tag_number": "27", "name": "Synthetic",
                     "lifecycle_status": "Active", "on_farm": True, "availability": "Herd", "pen": "PEN-A"}],
        "matings": [], "litters": []}
    state = {"history": [source], "claim": {}, "events": {}, "sends": [], "clock": 27.,
             "load_cost": 5., "family_cost": 1., "record_failure": False, "readback_failure": False,
             "welfare_appends": [], "creates": 0, "renewal_audits": [], "audit_failure": False}
    case = {"case_id": "SYNTHETIC-RETAINED", "dedupe_key": "herdmaster:retained-mortality:101",
        "specialist": "HERDMASTER", "generation": 1, "evidence_digest": "b" * 64,
        "message_family": "retained_protected_recovery", "evidence_refs": [
            "provider_message:101", "pig:P27", "tag:27", retained_report_binding([source])]}
    monkeypatch.setattr(worker.time, "monotonic", lambda: state["clock"])
    def load(**_kwargs):
        state["clock"] += state["load_cost"]
        return copy.deepcopy(evidence)
    monkeypatch.setattr(health, "load_canonical_health_loss_evidence", load)
    def create(**request):
        assert not state["claim"], "a prior claim may never be recreated"
        state["creates"] += 1
        state["claim"].update(request, callback_token="SyntheticToken27", status="active",
            preview_digest=claims.canonical_preview_digest(request["action_kind"],request["preview_payload"]),
            expires_at=datetime.now(timezone.utc)+timedelta(minutes=30), delivery_state="claim_created")
        return dict(state["claim"])
    monkeypatch.setattr(claims, "create_claim", create)
    delivery_keys=("callback_token", "preview_digest", "evidence_generation", "expires_at",
        "preview_card_message_id", "delivery_state", "delivery_attempt_id", "delivery_attempted_at",
        "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result",
        "result_payload", "confirmation_provider_message_id", "confirmation_provider_timestamp", "completed_at")
    def report_data(*_args):
        c=state["claim"]
        packed=[] if not c else [tuple(c.get(k) for k in ("owner_user_id", "private_chat_id",
            "mission_id", "provider_message_id", "status", "action_kind", "preview_payload"))+
            ({k:(v.isoformat() if isinstance(v,datetime) else copy.deepcopy(v))
              for k in delivery_keys for v in [c.get(k)]},)]
        return {"reports":copy.deepcopy(state["history"]),"lifecycle":copy.deepcopy(state["history"]),"claims":packed}
    monkeypatch.setattr(recovery,"connect_bounded_read",lambda:Connection([]))
    monkeypatch.setattr(recovery,"read_retained_health_reports",report_data)
    read_keys=("status", "expires_at", "preview_card_message_id", "preview_digest", "owner_user_id",
        "private_chat_id", "action_kind", "mission_id", "provider_message_id", "evidence_generation",
        "preview_payload", "delivery_state", "delivery_attempt_id", "delivery_attempted_at",
        "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result")
    def raw(*_args):
        state["clock"]+=1
        current=copy.deepcopy(state["history"][0])
        if state["readback_failure"] and current.get("retained_repreview"):
            current={**current,"status":"contained"}
        return current,tuple(state["claim"].get(k) for k in read_keys)
    monkeypatch.setattr(health,"_retained_preview_readback",raw)
    def record_event(event):
        if state["record_failure"]: return {"success":False},503
        row=copy.deepcopy(event["review_json"]["herdmaster_health_loss"])
        same=any(v.get("event_phase")==row.get("event_phase") for v in state["history"])
        if not same:state["history"].insert(0,row)
        state["clock"]+=1
        return {"success":True,"created":not same},200
    monkeypatch.setattr("modules.sales.sam_live_stock_launch_control.record_sam_live_stock_review_event",record_event)
    monkeypatch.setattr(health,"welfare_case_runtime_enabled",lambda:True)
    monkeypatch.setattr(health,"append_welfare_case_context",lambda row:state["welfare_appends"].append(copy.deepcopy(row)) or {"success":True})
    active_reader=health._load_active_contexts
    monkeypatch.setattr(health,"_load_active_contexts",lambda chat_id,**kwargs:active_reader(
        chat_id,owner_user_id=kwargs.get("owner_user_id",""),context_store=lambda *_a:copy.deepcopy(state["history"])))
    class ClaimDb:
        rowcount=1
        def __init__(self): self.snapshots=[]
        def __enter__(self):
            self.snapshots.append((copy.deepcopy(state["claim"]),copy.deepcopy(state["renewal_audits"])))
            return self
        def __exit__(self,kind,*_a):
            before,audits=self.snapshots.pop()
            if kind:
                state["claim"].clear();state["claim"].update(before)
                state["renewal_audits"][:]=audits
            return False
        def cursor(self):return self
        def execute(self,q,params=None):
            q=" ".join(q.lower().split());c=state["claim"];self.rowcount=1
            if q.startswith("select to_jsonb(c)"):
                self.row=(json.loads(json.dumps(c,default=str)),datetime.now(timezone.utc))
            elif q.startswith("select event_id from public.operational_events"):
                self.row=(state["renewal_audits"][0]["event_id"],) if state["renewal_audits"] else None
            elif q.startswith("select callback_token from app_private"):
                self.row=None
            elif q.startswith("select c.expires_at"):
                self.row=(c["expires_at"],c["status"],c["delivery_state"],state["renewal_audits"][-1]["payload"])
            elif "set expires_at=clock_timestamp()" in q:
                assert params==(c["callback_token"],c["expires_at"],c["status"])
                c.update(expires_at=datetime.now(timezone.utc)+timedelta(minutes=30),status="active",delivery_state="claim_created")
                self.row=(c["expires_at"],)
            elif q.startswith("insert into public.operational_events"):
                if state["audit_failure"]:raise RuntimeError("synthetic audit failure")
                state["renewal_audits"].append({**params,"payload":json.loads(params["payload"])})
                self.row=(params["event_id"],)
            elif q.startswith("select "):
                names=q.split(" from ")[0].removeprefix("select ").split(",")
                self.row=tuple(c.get(k.strip()) for k in names)
            elif "set delivery_state='delivery_pending'" in q:
                assert c["status"]=="active" and c["delivery_state"]=="claim_created" and not c.get("preview_card_message_id")
                c.update(delivery_state="delivery_pending",delivery_attempt_id=params[0],delivery_attempted_at=datetime.now(timezone.utc))
            elif "set delivery_state='delivery_confirmed'" in q:
                c.update(delivery_state="delivery_confirmed",preview_card_message_id=params[0],delivery_result=json.loads(params[1]),
                    provider_accepted_at=datetime.now(timezone.utc),delivery_confirmed_at=datetime.now(timezone.utc))
            elif "set delivery_state='delivery_ambiguous'" in q:
                c.update(delivery_state="delivery_ambiguous",delivery_ambiguous_at=datetime.now(timezone.utc))
            elif "set status='executing'" in q:
                c.update(status="executing",confirmation_provider_message_id=params[0],confirmation_provider_timestamp=datetime.fromisoformat(str(params[1]).replace("Z","+00:00")))
            elif "set status='completed'" in q:
                c.update(status="completed",result_payload=json.loads(params[0]))
            elif "set status='contained'" in q:c.update(status="contained")
            else:raise AssertionError(q)
        def fetchone(self):return self.row
    monkeypatch.setattr(delivery,"_connect",ClaimDb)
    monkeypatch.setattr(claims,"_connect",ClaimDb)
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",lambda **_k:ClaimDb())
    def family_store(action,identity,payload):
        state["clock"]+=state["family_cost"]
        if action=="load":return [v for v in state["events"].values() if v.get("card_mission_id")==identity]
        created=identity not in state["events"]
        if created:state["events"][identity]=copy.deepcopy(payload)
        return {"success":True,"created":created}
    monkeypatch.setattr(family,"_event_store",family_store)
    def sender(chat,text,**kwargs):
        state["sends"].append((chat,text,kwargs))
        return {"success":True,"telegram_message_id":"701","provider_timestamp":datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(family,"_send_telegram",sender)
    state.update(case=case,evidence=evidence,source=source,report_data=report_data,db=ClaimDb)
    return state


def test_real_retained_worker_preview_family_binding_and_replay(retained_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey
    first=deliver_farm_manager_case(j["case"],deadline_monotonic=80.)
    assert first["success"] and first["delivery_confirmed"] and first["protected_preview_card_bound"]
    assert j["creates"]==1 and len(j["sends"])==1
    assert j["sends"][0][0]=="42"
    text=j["sends"][0][1]
    assert "etiket 27" in text and "2026-08-19" in text and "verwyder en begrawe" in text
    assert "Niks word uitgevoer voordat" not in text  # generic fallback would discard precise facts
    current=j["history"][0]
    assert current["mission_id"]==j["source"]["mission_id"] and current["provider_timestamp"]==j["source"]["provider_timestamp"]
    assert current["status"]=="preview_ready" and len(j["welfare_appends"])==1
    token=j["claim"]["callback_token"];expiry=j["claim"]["expires_at"]
    j["clock"]=27.
    replay=deliver_farm_manager_case(j["case"],deadline_monotonic=80.)
    assert replay["success"] and replay["status"]=="protected_delivery_replayed_noop"
    assert replay["delivery_confirmed"] is False and replay["telegram_sends"]==0
    assert j["claim"]["callback_token"]==token and j["claim"]["expires_at"]==expiry
    assert len(j["sends"])==1 and len(j["welfare_appends"])==1


def test_real_protected_callback_resolves_persisted_retained_operation(retained_journey,monkeypatch):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    j=retained_journey;effects=[]
    def effect(lifecycle,evaluator,binding,operation,actor_id,**kwargs):
        assert operation==j["claim"]["preview_payload"]["operation_id"]
        assert binding["preview_sha256"]==j["claim"]["preview_payload"]["preview_sha256"]
        assert lifecycle["mission_id"]==j["source"]["mission_id"] and actor_id=="42"
        assert kwargs["evidence_loader"]()["evidence_generation"]==binding["evidence_generation"]
        effects.append(operation)
        return {"success":True,"status":"mortality_lifecycle_recorded","operation_id":operation,
            "pig_id":"P27","lifecycle_event_id":"LIFE-27","event_date":"2026-08-19",
            "canonical_readback":{"canonical_readback_verified":True},"writes_farm_data":True},200
    monkeypatch.setattr("modules.pig_weights.herdmaster_health_loss_recording._confirm_mortality_lifecycle",effect)
    assert deliver_farm_manager_case(j["case"])["success"] and not effects
    callback={"telegram_user_id":"42","telegram_chat_id":"42","provider_message_id":"702",
        "provider_timestamp":datetime.now(timezone.utc).isoformat(),"reply_to_message_id":"701","text":"","output_language":"af"}
    result,status=handle_protected_action_input(callback,issue_gateway_owner_authority("42","42"),
        callback_data="oompa:"+j["claim"]["callback_token"]+":confirm")
    assert status==200 and result["success"] and len(effects)==1
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    assert result["card_mission_id"]==protected_card_mission_id(j["claim"]["mission_id"],j["claim"]["preview_digest"])
    assert any(row["card_mission_id"]==result["card_mission_id"] and row["state"]=="delivered"
               for row in j["events"].values())
    assert j["claim"]["status"]=="completed"
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    edits=[]
    def edit(chat,message,text,**kwargs):
        edits.append((chat,message,text))
        return {"success":True,"telegram_message_id":message}
    visible=deliver_family_result(callback,result,specialist="HERDMASTER",mission_id=result["mission_id"],
        card_mission_id=result["card_mission_id"],editor=edit)
    assert visible["success"] and visible["telegram_edits"]==1 and visible["telegram_sends"]==0
    assert edits[0][1]=="701" and len(j["sends"])==1
    replay,replay_status=handle_protected_action_input(callback,issue_gateway_owner_authority("42","42"),
        callback_data="oompa:"+j["claim"]["callback_token"]+":confirm")
    assert replay_status==200 and replay["success"] and replay["card_mission_id"]==result["card_mission_id"]
    assert len(effects)==1
    repeated=deliver_family_result(callback,replay,specialist="HERDMASTER",mission_id=replay["mission_id"],
        card_mission_id=replay["card_mission_id"],editor=edit)
    assert repeated["telegram_sends"]==repeated["telegram_edits"]==0
    assert len(edits)==len(j["sends"])==len(effects)==1


@pytest.mark.parametrize("change,expected",[
    ({"status":"expired"},"retained_claim_expired_requires_current_review"),
    ({"expires_at":datetime(2020,1,1,tzinfo=timezone.utc),"delivery_attempt_id":"earlier"},"retained_claim_expired_requires_current_review"),
    ({"status":"cancelled"},"retained_claim_terminal_requires_current_review"),
    ({"status":"changed"},"retained_claim_terminal_requires_current_review"),
    ({"status":"completed"},"retained_claim_terminal_requires_current_review"),
    ({"delivery_state":"delivery_pending"},"retained_claim_delivery_outcome_unproven"),
    ({"delivery_state":"delivery_ambiguous"},"retained_claim_delivery_outcome_unproven"),
    ({"delivery_attempt_id":"prior"},"retained_claim_delivery_outcome_unproven"),
    ({"provider_accepted_at":datetime.now(timezone.utc)},"retained_claim_delivery_outcome_unproven"),
    ({"evidence_generation":"DIFFERENT"},"retained_claim_current_preview_mismatch"),
    ({"mission_id":"OTHER"},"retained_claim_current_preview_mismatch"),
    ({"confirmation_provider_message_id":"703"},"retained_claim_delivery_outcome_unproven"),
    ({"confirmation_provider_timestamp":datetime.now(timezone.utc)},"retained_claim_delivery_outcome_unproven"),
    ({"result_payload":{}},"retained_claim_delivery_outcome_unproven"),
    ({"completed_at":datetime.now(timezone.utc)},"retained_claim_delivery_outcome_unproven"),
])
def test_prior_claim_never_rearmed_or_reinterpreted(retained_journey,change,expected):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey
    preview=recovery.build_retained_protected_preview(j["case"])
    assert preview["success"] and not j["sends"]  # crash after preparation, before provider call
    expiry=j["claim"]["expires_at"];j["claim"].update(change)
    result=deliver_farm_manager_case(j["case"])
    assert result["status"]==expected and not result["success"]
    assert not j["sends"] and j["creates"]==1
    if "expires_at" not in change:assert j["claim"]["expires_at"]==expiry


@pytest.mark.parametrize("failure",["record_failure","readback_failure"])
def test_unproven_lifecycle_never_attempts_provider(retained_journey,failure):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;j[failure]=True
    result=deliver_farm_manager_case(j["case"])
    assert not result["success"] and not j["sends"] and not j["claim"].get("delivery_attempt_id")


def test_prepared_claim_resumes_after_record_failure_without_new_claim(retained_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;j["record_failure"]=True
    assert not deliver_farm_manager_case(j["case"])["success"]
    token=j["claim"]["callback_token"];j["record_failure"]=False
    assert deliver_farm_manager_case(j["case"])["success"]
    assert j["claim"]["callback_token"]==token and j["creates"]==1 and len(j["sends"])==1


def test_elapsed_budget_progress_and_late_preparation_containment(retained_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;j["load_cost"]=25.
    result=deliver_farm_manager_case(j["case"],deadline_monotonic=80.)
    assert result["status"]=="manager_cycle_deadline_deferred" and not j["claim"] and not j["sends"]
    j["clock"]=27.;j["load_cost"]=5.
    assert deliver_farm_manager_case(j["case"],deadline_monotonic=80.)["success"]


def test_deadline_crossed_inside_family_is_contained_without_retry(retained_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;j["family_cost"]=20.
    first=deliver_farm_manager_case(j["case"],deadline_monotonic=80.)
    assert not first["success"] and not j["sends"]
    assert j["claim"]["delivery_state"]=="delivery_ambiguous"
    j["clock"]=0.;j["family_cost"]=0.
    again=deliver_farm_manager_case(j["case"],deadline_monotonic=80.)
    assert again["status"]=="retained_claim_delivery_outcome_unproven" and not j["sends"]


def test_other_retained_family_preserves_existing_preview_contract():
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    preview={"success":True,"status":"farrowing_litter_preview_ready","answer":"Existing preview",
        "callback_token":"UNCHANGED","confirmation_required":True}
    value=deliver_farm_manager_case({"specialist":"HERDMASTER","message_family":"retained_protected_recovery",
        "dedupe_key":"herdmaster:expired-farrowing:OLD"},retained_recovery=lambda _case:preview,
        deliver=lambda *_a,**_k:pytest.fail("farrowing delivery is outside this repair"))
    assert value["callback_token"]=="UNCHANGED" and value["status"]==preview["status"]


@pytest.mark.parametrize("language",["en","af"])
def test_litter_confirmation_renderer_preserves_recipient_and_exact_selection(language):
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _litter_preview_text
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    text=_litter_preview_text({"litter_id":"L-SYNTH","pig_ids":["P-A","P-B"],"event_date":"2026-08-19","count":2},language)
    result=localize_recipient_result({"output_language":language},{"status":"litter_piglet_deaths_preview_ready",
        "answer":text,"recipient_render_contract":"specialist_structured_recipient_v1","recipient_language":language},"HERDMASTER")
    assert result["answer"]==text and "P-A, P-B" in text and "2026-08-19" in text and "L-SYNTH" in text
    assert ("Nothing has been recorded" in text)==(language=="en")


@pytest.fixture
def completed_retained_evidence(retained_journey, monkeypatch):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    j = retained_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    c = j["claim"]; payload = c["preview_payload"]
    operation = payload["operation_id"]
    completed = copy.deepcopy(j["history"][0])
    completed.update(status="completed", event_phase="recording_completed", provider_message_id="702",
        recording_result={"success": True, "status": "mortality_lifecycle_recorded",
            "operation_id": operation, "pig_id": "P27", "lifecycle_event_id": "LIFE-27",
            "welfare_case_id": "WELFARE-27", "event_date": "2026-08-19"})
    c.update(status="completed", delivery_state="delivery_confirmed", preview_card_message_id="701")
    evidence = j["report_data"]()
    evidence["lifecycle"].insert(0, completed)
    metadata = evidence["claims"][0][7]
    metadata.update(confirmation_provider_message_id="702", confirmation_provider_timestamp="2026-09-23T04:50:00Z",
        result_payload={"success": True, "status": "completed", "pig_id": "P27", "lifecycle_event_id": "LIFE-27"})
    binding = completed["preview"]["confirmation_binding"]
    event = {"operation_id": operation, "pig_id": "P27", "provider_message_id": "101",
        "preview_sha256": payload["preview_sha256"], "actor_id": "42",
        "evidence_generation": binding["evidence_generation"], "event_date": "2026-08-19",
        "resulting_status": "Dead", "resulting_on_farm": False}
    state = {"event_rows": [(event, "42", "2026-08-19")], "readback": True, "reads": 0}
    class CompletionCursor:
        def execute(self, query, params):
            assert "select e.event_payload" in query and params == ("LIFE-27", "P27", operation)
            assert "not exists" in query and "supersedes_lifecycle_event_id" in query
            state["reads"] += 1
        def fetchall(self): return state["event_rows"]
    monkeypatch.setattr("modules.pig_weights.herdmaster_health_loss_recording._readback_mortality_welfare",
        lambda *_a, **_k: {"canonical_readback_verified": state["readback"]})
    return j, evidence, state, CompletionCursor()


def test_exact_canonical_completed_operation_projects_same_retained_key(completed_retained_evidence):
    from modules.oom_sakkie.manager_case_sources import _retained_mortality_completion
    j, evidence, state, cursor = completed_retained_evidence
    candidate = _retained_mortality_completion(cursor, j["case"]["dedupe_key"], j["case"]["evidence_refs"], evidence, datetime.now(timezone.utc))
    assert candidate["terminal_state"] == "completed" and candidate["dedupe_key"] == j["case"]["dedupe_key"]
    assert set(j["case"]["evidence_refs"]).issubset(candidate["evidence_refs"])
    assert "lifecycle_event:LIFE-27" in candidate["evidence_refs"] and candidate["unknowns"] == []
    assert state["reads"] == 1 and not j["sends"]


@pytest.mark.parametrize("damage", ["latest_cancelled", "principal", "claim_not_completed", "wrong_operation",
    "missing_receipt", "wrong_pig", "wrong_callback", "wrong_binding", "duplicate_claim", "superseded_event",
    "event_provider", "event_preview", "canonical_readback"])
def test_incomplete_or_conflicting_completion_never_closes_case(completed_retained_evidence, damage):
    from modules.oom_sakkie.manager_case_sources import _retained_mortality_completion
    j, evidence, state, cursor = completed_retained_evidence
    latest, claim = evidence["lifecycle"][0], list(evidence["claims"][0])
    if damage == "latest_cancelled": latest["status"] = "contained"
    elif damage == "principal": latest["owner_user_id"] = "99"
    elif damage == "claim_not_completed": claim[4] = "active"
    elif damage == "wrong_operation": latest["recording_result"]["operation_id"] = "OTHER"
    elif damage == "missing_receipt": claim[7]["result_payload"] = {}
    elif damage == "wrong_pig": claim[7]["result_payload"]["pig_id"] = "OTHER"
    elif damage == "wrong_callback": claim[7]["confirmation_provider_message_id"] = "OTHER"
    elif damage == "wrong_binding": latest["retained_repreview"]["source_binding"] = "OTHER"
    elif damage == "duplicate_claim": evidence["claims"].append(tuple(claim))
    elif damage == "superseded_event": state["event_rows"] = []
    elif damage == "event_provider": state["event_rows"][0][0]["provider_message_id"] = "OTHER"
    elif damage == "event_preview": state["event_rows"][0][0]["preview_sha256"] = "OTHER"
    elif damage == "canonical_readback": state["readback"] = False
    evidence["claims"][0] = tuple(claim)
    assert _retained_mortality_completion(cursor, j["case"]["dedupe_key"], j["case"]["evidence_refs"], evidence, datetime.now(timezone.utc)) is None
    assert not j["sends"]


@pytest.mark.parametrize("expired_status", ["active", "expired"])
def test_never_attempted_expired_claim_renews_once_preserving_identity(retained_journey, expired_status):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    j=retained_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    c=j["claim"]; c.update(status=expired_status,expires_at=datetime.now(timezone.utc)-timedelta(seconds=5))
    if expired_status=="expired":c["delivery_state"]="expired"
    preserved={k:copy.deepcopy(c[k]) for k in ("callback_token","mission_id","provider_message_id",
        "preview_digest","preview_payload","evidence_generation")}
    old=c["expires_at"]
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    assert c["expires_at"]>old and c["status"]=="active" and c["delivery_state"]=="claim_created"
    assert {k:c[k] for k in preserved}==preserved and j["creates"]==1 and not j["sends"]
    assert len(j["renewal_audits"])==1
    assert j["renewal_audits"][0]["payload"]["old_expires_at"]==old.isoformat()
    renewed=c["expires_at"]
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    assert c["expires_at"]==renewed and len(j["renewal_audits"])==1
    c["expires_at"]=datetime.now(timezone.utc)-timedelta(seconds=1)
    result=recovery.build_retained_protected_preview(j["case"])
    assert result["status"]=="retained_claim_renewal_already_consumed" and len(j["renewal_audits"])==1


def test_expiry_cas_rolls_back_when_same_transaction_audit_fails(retained_journey):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    j=retained_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    j["claim"]["expires_at"]=datetime.now(timezone.utc)-timedelta(seconds=5)
    before=copy.deepcopy(j["claim"]);j["audit_failure"]=True
    result=recovery.build_retained_protected_preview(j["case"])
    assert result["status"]=="retained_claim_renewal_persistence_unproven"
    assert j["claim"]==before and not j["renewal_audits"] and not j["sends"]


@pytest.mark.parametrize("marker", ["preview_card_message_id","delivery_attempt_id","delivery_attempted_at",
    "provider_accepted_at","delivery_confirmed_at","delivery_ambiguous_at","delivery_result",
    "confirmation_provider_message_id","confirmation_provider_timestamp","result_payload","completed_at"])
def test_every_prior_effect_marker_blocks_expiry_renewal(retained_journey, marker):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    j=retained_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    j["claim"].update(expires_at=datetime.now(timezone.utc)-timedelta(seconds=5),**{marker:"present"})
    before=copy.deepcopy(j["claim"])
    result=recovery.build_retained_protected_preview(j["case"])
    assert not result["success"] and j["claim"]==before
    assert not j["renewal_audits"] and not j["sends"] and j["creates"]==1


@pytest.fixture(autouse=True)
def current_synthetic_recipient_policy(monkeypatch):
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "42")
    monkeypatch.setenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON", "[]")


def _current_manager(monkeypatch, **changes):
    record={"telegram_user_id":"42","family_key":"dad","role":"farm_manager",
        "permissions":[],"summary_domains":["herd"],"language":"af",
        "authorization_id":"SYNTHETIC-CURRENT","authorized_by_user_id":"99",
        "authorized_at":"2026-09-01T00:00:00+00:00",**changes}
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID","99")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","99,42")
    monkeypatch.setenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON",json.dumps([record]))


def test_current_delegated_manager_can_receive_exact_retained_preview(retained_journey,monkeypatch):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    _current_manager(monkeypatch)
    result=deliver_farm_manager_case(retained_journey["case"])
    assert result["success"] and len(retained_journey["sends"])==1
    assert retained_journey["sends"][0][0]=="42"


@pytest.mark.parametrize("policy",["missing_allowlist","not_allowed","unknown","revoked","downgraded"])
@pytest.mark.parametrize("expired",[False,True])
def test_current_recipient_denial_precedes_claim_renewal_or_persistence(retained_journey,monkeypatch,policy,expired):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey
    if expired:
        assert recovery.build_retained_protected_preview(j["case"])["success"]
        j["claim"]["expires_at"]=datetime.now(timezone.utc)-timedelta(seconds=1)
    before=copy.deepcopy(j["claim"]);history=copy.deepcopy(j["history"])
    if policy=="missing_allowlist":monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","")
    elif policy=="not_allowed":monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","99")
    elif policy=="unknown":monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID","99")
    elif policy=="revoked":_current_manager(monkeypatch,revoked_at="2026-09-22T00:00:00+00:00")
    elif policy=="downgraded":_current_manager(monkeypatch,role="trusted_family_reporter")
    result=deliver_farm_manager_case(j["case"])
    assert result["status"]=="retained_recipient_not_currently_authorized"
    assert j["claim"]==before and j["history"]==history
    assert not j["renewal_audits"] and not j["sends"]


def test_recipient_revoked_during_canonical_preview_never_creates_claim(retained_journey,monkeypatch):
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;load=health.load_canonical_health_loss_evidence
    def revoke(**kwargs):
        result=load(**kwargs)
        monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","99")
        return result
    monkeypatch.setattr(health,"load_canonical_health_loss_evidence",revoke)
    result=deliver_farm_manager_case(j["case"])
    assert result["status"]=="retained_recipient_not_currently_authorized"
    assert not j["claim"] and not j["sends"] and len(j["history"])==1


def test_recipient_revoked_after_preview_has_no_provider_attempt(retained_journey,monkeypatch):
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;build=recovery.build_retained_protected_preview
    def revoke(*args,**kwargs):
        result=build(*args,**kwargs)
        monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","99")
        return result
    monkeypatch.setattr(recovery,"build_retained_protected_preview",revoke)
    result=deliver_farm_manager_case(j["case"])
    assert result["status"]=="retained_recipient_not_currently_authorized"
    assert j["claim"]["delivery_state"]=="claim_created" and not j["claim"].get("delivery_attempt_id")
    assert not j["sends"]


def test_recipient_revoked_during_family_read_is_denied_at_sender_boundary(retained_journey,monkeypatch):
    from modules.oom_sakkie import family_message_lifecycle as family
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j=retained_journey;store=family._event_store
    def revoke(action,identity,payload):
        result=store(action,identity,payload)
        if action=="load":monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","99")
        return result
    monkeypatch.setattr(family,"_event_store",revoke)
    result=deliver_farm_manager_case(j["case"])
    assert not result["success"] and not j["sends"]
    assert j["claim"]["delivery_state"]=="delivery_ambiguous"
