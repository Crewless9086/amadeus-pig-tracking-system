from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Barrier
import pytest

from modules.telemetry.rootline_provider_availability import (
    CONTRACT, project_scope, read_provider_availability, read_notification_receipt)
from modules.oom_sakkie.rootline_transition_notifications import (
    recover_provider_notifications, compose_provider_notice, provider_availability_text)

NOW = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)
SCOPE = "a" * 64


def event(identity="FAIL-1", at=NOW, *, category="application_call_limit", action="request_completed", scope=SCOPE, generation=1):
    failure = {"category": category, "retry_after_seconds": 3600}
    detail = {"scope": scope, "failure": failure, "outcome": "failed", "attempt_id": "attempt1"}
    if action == "complete_snapshot_restored_availability":
        category = None
        detail = {"scope": scope, "group_id": "group1", "provider_remaining": "Unknown"}
    state = {"version": 1, "coverage_start": (NOW-timedelta(days=30)).isoformat(),
        "scopes": {scope: {"category": category, "failures": generation if category else 0,
            "generation": generation, "probe_group": None, "probe_until": None,
            "next_probe_at": (at+timedelta(hours=1)).isoformat() if category else None}},
        "reserves": {}, "provider_remaining": "Unknown", "provider_entitlement": "Unknown"}
    return (identity, at, {"action": action, "detail": detail, "state": state, "attempt_units": 0})


def snapshot(latest=None, failure=None, restoration=None, now=NOW):
    latest = latest or event()
    failure = failure or event()
    value = project_scope(SCOPE, latest, failure, restoration, now=now)
    return {"contract": CONTRACT, "status": value["state"] if value else "unobserved", "scopes": [value] if value else []}


class Memory:
    def __init__(self):
        self.receipts = {}
        self.duties = []
        self.calls = []
        self.lock = Lock()
        self.persist = True
    def store(self, action, payload):
        if action == "load_active": return self.duties[0] if self.duties else None
        if action == "load_active_borehole": return None
        if action == "load_active_auxiliaries": return []
        assert action == "record_notification_delivery"
        if not self.persist: return {"success": False}
        with self.lock:
            row = {**deepcopy(payload), "event_id": "receipt-"+str(len(self.receipts)+1)}
            prior = self.receipts.get(payload["notification_identity"], {})
            if not prior.get("delivery_confirmed"):
                self.receipts[payload["notification_identity"]] = row
        return {"success": True}
    def receipt(self, identity):
        with self.lock: return deepcopy(self.receipts.get(identity, {}))
    def notify(self, state, payload, **kwargs):
        self.calls.append((state, deepcopy(payload), kwargs))
        return {"success": True, "provider_delivery_confirmed": True,
            "provider_message_id": str(len(self.calls)), "telegram_sends": 1}
    def run(self, current, *, now=NOW, notify=None, loader=None):
        return recover_provider_notifications(notify=notify or self.notify, now=now,
            store=self.store, receipt_loader=self.receipt, loader=loader or (lambda **_: deepcopy(current)), clock=lambda: now)


def test_canonical_412_incident_is_stable_across_hourly_failure_generations():
    first = event(at=NOW-timedelta(days=3))
    ids = []
    for generation in (1, 5, 100):
        value = project_scope(SCOPE, event("L"+str(generation), generation=generation), first, None, now=NOW)
        ids.append(value["incident_id"])
        assert value["outage_started_at"] == first[1].isoformat()
        assert value["provider_reset_at"] == "Unknown"
    assert len(set(ids)) == 1


def test_persistent_outage_restart_midnight_and_new_retry_do_not_notify_again():
    memory = Memory()
    first = event(at=NOW-timedelta(days=3))
    a = snapshot(failure=first)
    assert memory.run(a)["notification_count"] == 1
    for hours in (1, 12, 48):
        later = NOW+timedelta(hours=hours)
        b = snapshot(event("RETRY"+str(hours), later, generation=hours), first, now=later)
        assert memory.run(b, now=later)["telegram_sends"] == 0
    assert len(memory.calls) == 1


def test_current_outage_before_rollout_is_not_hidden_by_day_epoch():
    memory = Memory()
    current = snapshot(failure=event("OLD", NOW-timedelta(days=17)))
    assert memory.run(current)["notification_count"] == 1
    assert "Recorded since" in compose_provider_notice(*memory.calls[0][:2])


def test_active_duty_and_later_unverified_off_escalate_once_each():
    memory = Memory(); current = snapshot()
    memory.run(current)
    memory.duties = [{"execution_id": "RUN-1", "zone_id": "B12345", "state": "Active",
        "primary_stop_deadline": (NOW+timedelta(minutes=5)).isoformat()}]
    assert memory.run(current)["notification_count"] == 1
    assert memory.calls[-1][0] == "ProviderSafety"
    assert memory.run(current)["telegram_sends"] == 0
    later = NOW+timedelta(minutes=6)
    assert memory.run(current, now=later)["notification_count"] == 1
    assert memory.calls[-1][1]["severity"] == "off_unverified"
    assert memory.run(current, now=later)["telegram_sends"] == 0
    assert "OFF duties are still attempted" in compose_provider_notice(*memory.calls[-1][:2])
    assert "OFF deadline has passed" in compose_provider_notice(*memory.calls[-1][:2])


def test_proven_not_dispatched_claim_does_not_raise_equipment_running_alarm():
    memory = Memory(); memory.duties = [{"execution_id":"RUN", "on_not_dispatched":True}]
    assert memory.run(snapshot())["notification_count"] == 1
    assert [call[0] for call in memory.calls] == ["ProviderUnavailable"]


def test_unknown_active_duties_do_not_suppress_known_outage_or_claim_safe():
    memory=Memory(); original=memory.store
    def store(action,payload):
        if action == "load_active": raise RuntimeError("offline")
        return original(action,payload)
    memory.store=store
    result=memory.run(snapshot())
    assert len(memory.calls)==1 and result["success"] is False
    assert result["status"] == "rootline_provider_safety_evidence_unavailable"


def test_verified_full_restoration_notifies_once_after_confirmed_outage():
    memory=Memory(); failure=event(at=NOW-timedelta(minutes=2)); memory.run(snapshot(failure=failure))
    restored=event("RESTORED",action="complete_snapshot_restored_availability")
    current=snapshot(restored,failure,restored)
    assert memory.run(current)["notification_count"]==1
    assert memory.calls[-1][0]=="ProviderRestored"
    assert memory.run(current)["telegram_sends"]==0
    answer=compose_provider_notice(*memory.calls[-1][:2])
    assert "not the current state, resumed irrigation" in answer and "17:00" not in answer  # rendered SAST
    assert "19:00 SAST" in answer


def test_unannounced_historical_recovery_is_not_replayed():
    memory=Memory(); failure=event(at=NOW-timedelta(days=4))
    restored=event("R",NOW-timedelta(days=3),action="complete_snapshot_restored_availability")
    assert memory.run(snapshot(restored,failure,restored))["telegram_sends"]==0
    assert memory.calls==[]


def test_delayed_restoration_reports_dated_recovery_once_without_claiming_current_state():
    memory=Memory(); failure=event(at=NOW-timedelta(hours=2)); memory.run(snapshot(failure=failure))
    restored=event("R",NOW-timedelta(hours=1),action="complete_snapshot_restored_availability")
    assert memory.run(snapshot(restored,failure,restored))["telegram_sends"]==1
    assert memory.calls[-1][0]=="ProviderRestored"
    assert "not the current state" in compose_provider_notice(*memory.calls[-1][:2])
    assert memory.run(snapshot(restored,failure,restored))["telegram_sends"]==0
    assert len(memory.calls)==2


@pytest.mark.parametrize("damage", ["wrong_scope","no_group","nonzero_failures","wrong_action","future","before_failure"])
def test_invalid_or_expired_recovery_proof_is_rejected(damage):
    failure=event(at=NOW-timedelta(minutes=2))
    recovery=list(event("R",action="complete_snapshot_restored_availability"))
    if damage=="wrong_scope": recovery[2]["detail"]["scope"]="b"*64
    elif damage=="no_group": recovery[2]["detail"].pop("group_id")
    elif damage=="nonzero_failures": recovery[2]["state"]["scopes"][SCOPE]["failures"]=1
    elif damage=="wrong_action": recovery[2]["action"]="request_completed"
    elif damage=="future": recovery[1]=NOW+timedelta(seconds=1)
    elif damage=="before_failure": recovery[1]=NOW-timedelta(minutes=3)
    latest=event("LATEST",action="complete_snapshot_restored_availability")
    with pytest.raises(ValueError): project_scope(SCOPE, latest, failure, tuple(recovery), now=NOW)


def test_http_success_alone_cannot_restore_availability():
    failed=event(at=NOW-timedelta(minutes=1))
    latest=event("HTTP")
    latest[2]["detail"]["failure"]=None; latest[2]["detail"]["outcome"]="http_succeeded"
    assert project_scope(SCOPE,latest,failed,None,now=NOW)["state"]=="unavailable"


def test_recovery_invalidated_by_new_outage_before_send():
    memory=Memory(); failure=event(at=NOW-timedelta(minutes=2)); memory.run(snapshot(failure=failure))
    restored=event("R",action="complete_snapshot_restored_availability")
    old=snapshot(restored,failure,restored)
    new=snapshot(failure=event("NEW"))
    loads=iter([old,new])
    result=memory.run(old,loader=lambda **_:next(loads))
    assert result["status"]=="rootline_provider_notice_superseded" and len(memory.calls)==1
    assert memory.run(new)["notification_count"]==1
    assert memory.calls[-1][1]["incident_id"] != memory.calls[0][1]["incident_id"]


def test_definitely_not_sent_retains_identity_and_frozen_content_for_retry():
    memory=Memory(); current=snapshot()
    def failed(state,payload,**kwargs):
        memory.calls.append((state,deepcopy(payload),kwargs))
        return {"delivery_definitely_not_sent":True,"telegram_sends":0}
    assert memory.run(current,notify=failed)["success"] is False
    identity=memory.calls[0][1]["notification_identity"]
    newer=snapshot(event("RETRY",generation=99))
    assert memory.run(newer)["notification_count"]==1
    assert memory.calls[-1][1]==memory.calls[0][1]
    assert memory.calls[-1][2]["retry_proof_identity"]
    assert memory.receipts[identity]["provider_message_id"]


def test_ambiguous_delivery_never_remints_or_marks_sent():
    memory=Memory()
    result=memory.run(snapshot(),notify=lambda *a,**k:{"telegram_sends":0,"status":"ambiguous"})
    assert result["success"] is False
    assert memory.run(snapshot())["status"]=="rootline_provider_delivery_ambiguous"
    assert not memory.calls
    assert all(not x["delivery_confirmed"] for x in memory.receipts.values())


def test_confirmed_flag_without_message_id_does_not_count_sent():
    memory=Memory()
    result=memory.run(snapshot(),notify=lambda *a,**k:{"provider_delivery_confirmed":True})
    assert result["notification_count"]==0 and result["success"] is False


def test_deadline_deferral_remains_retryable_without_ambiguity_receipt():
    memory=Memory()
    result=memory.run(snapshot(),notify=lambda *a,**k:{"status":"family_message_cycle_deadline_deferred"})
    assert result["status"]=="rootline_provider_notifications_deferred" and not memory.receipts
    assert memory.run(snapshot())["notification_count"]==1


@pytest.mark.parametrize("language", ["en","af"])
def test_plain_owner_wording_preserves_off_and_unknown_reset(language):
    payload=snapshot()["scopes"][0]
    text=compose_provider_notice("ProviderUnavailable",payload,language=language)
    assert "application_call_limit" not in text and "412" not in text and SCOPE not in text
    assert ("AF-opdragte" if language=="af" else "OFF duties") in text
    assert ("onbekend" if language=="af" else "unknown") in text


@pytest.mark.parametrize("status", ["unknown","unobserved"])
def test_missing_provider_evidence_is_never_recovered(status):
    text=provider_availability_text({"contract":CONTRACT,"status":status,"scopes":[]})
    assert "could not be verified" in text and "restored" not in text


class QueueConnection:
    def __init__(self,batches): self.batches=list(batches); self.queries=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def cursor(self): return self
    def execute(self,sql,params): self.queries.append((sql,params)); self.current=self.batches.pop(0)
    def fetchone(self): return self.current[0] if self.current else None
    def fetchall(self): return self.current


def test_actual_reader_uses_canonical_envelopes_and_episode_boundaries():
    failure=event("OLD",NOW-timedelta(days=3)); latest=event("RETRY",generation=64)
    connection=QueueConnection([[latest],[],[failure]])
    result=read_provider_availability(now=NOW,connect=lambda **_:connection)
    assert result["scopes"][0]["failure_event_id"]=="OLD"
    assert len(connection.queries)==3
    for sql,params in connection.queries:
        assert "event_source=%s" in sql and "chatwoot_conversation_id=%s" in sql
        assert params[0]=="rootline_provider_availability"
    assert "limit 2" in connection.queries[1][0]
    assert "order by created_at,review_event_id limit 1" in connection.queries[2][0]


def test_reader_uses_previous_recovery_for_the_restored_incident():
    prior=event("R0",NOW-timedelta(days=4),action="complete_snapshot_restored_availability")
    failure=event("F1",NOW-timedelta(days=3))
    restored=event("R1",action="complete_snapshot_restored_availability")
    connection=QueueConnection([[restored],[restored,prior],[failure]])
    result=read_provider_availability(now=NOW,connect=lambda **_:connection)
    assert result["scopes"][0]["state"]=="restored"
    assert connection.queries[2][1][2:6]==(prior[1],prior[0],restored[1],restored[0])


def test_empty_ledger_does_not_imply_recovery():
    connection=QueueConnection([[]])
    assert read_provider_availability(now=NOW,connect=lambda **_:connection)["status"]=="unobserved"


def test_receipt_read_prefers_confirmed_over_a_racing_ambiguous_record():
    connection=QueueConnection([[({"delivery_confirmed":True,"provider_message_id":"42"},)]])
    incident="ROOTLINE-PROVIDER-"+"A"*32
    identity=incident+":unavailable"
    assert read_notification_receipt(identity,connect=lambda **_:connection)["provider_message_id"]=="42"
    sql,params=connection.queries[0]
    assert params==(incident,identity) and "chatwoot_conversation_id=%s" in sql
    assert sql.index("delivery_confirmed")<sql.index("delivery_ambiguous")


def test_direct_owner_response_exposes_same_typed_outage():
    from modules.oom_sakkie.owner_response_composer import compose_rootline
    text=compose_rootline({"success":True,"provider_availability":snapshot()})
    assert "Fresh switch-status verification is unavailable" in text
    assert "OFF duties are still attempted" in text
    assert len(text)<=3900


def test_current_specialist_reads_availability_without_provider_request(monkeypatch):
    import modules.telemetry.rootline_specialist_result as specialist
    import modules.telemetry.rootline_provider_availability as provider
    monkeypatch.setattr(specialist,"read_current_water_energy_evidence",lambda **kw:({},"2026-11-20",NOW))
    monkeypatch.setattr(specialist,"build_rootline_specialist_result",lambda *a,**kw:{"success":True})
    seen=[]
    monkeypatch.setattr(provider,"read_provider_availability",lambda **kw:seen.append(kw) or snapshot())
    result=specialist.build_current_rootline_specialist_result(now=NOW,database_url="local-test")
    assert result["provider_availability"]["status"]=="unavailable"
    assert seen==[{"database_url":"local-test","now":NOW}]


def test_current_specialist_keeps_unknown_when_availability_read_fails(monkeypatch):
    import modules.telemetry.rootline_specialist_result as specialist
    import modules.telemetry.rootline_provider_availability as provider
    def unavailable(**kw): raise RuntimeError("offline")
    monkeypatch.setattr(provider,"read_provider_availability",unavailable)
    result=specialist._with_provider_availability({"success":True},now=NOW)
    assert result["success"] is True and result["provider_availability"]["status"]=="unknown"


class FamilyRail:
    """Exercise production atomic delivery code with only its effects replaced."""
    def __init__(self):
        self.rows={}; self.sent=[]; self.lock=Lock(); self.barrier=None; self.fail=False
    def store(self,action,identity,payload):
        if action=="load":
            with self.lock: rows=[deepcopy(row) for row in self.rows.values() if row.get("card_mission_id")==identity]
            if self.barrier: self.barrier.wait(timeout=5)
            return rows
        with self.lock:
            created=identity not in self.rows
            if created: self.rows[identity]=deepcopy(payload)
        return {"success":True,"created":created}
    def send(self,chat,text):
        with self.lock: self.sent.append(text)
        if self.fail:return {"success":False,"delivery_definitely_not_sent":True}
        return {"success":True,"telegram_message_id":"700"}
    def notify(self,state,payload,retry_proof_identity=""):
        from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
        from modules.oom_sakkie.family_presentation import envelope
        from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
        identity=payload["notification_identity"]+":"+state.upper()
        text=compose_provider_notice(state,payload)
        retry=issue_delivery_retry_authority(mission_id=identity,card_mission_id=identity,
            text=envelope(text),proof_identity=retry_proof_identity) if retry_proof_identity else None
        result=deliver_family_result({"telegram_user_id":"42","telegram_chat_id":"42",
            "provider_message_id":"scheduled:minute","provider_timestamp":NOW.isoformat()},
            {"success":True,"status":state.lower(),"answer":text},specialist="ROOTLINE",
            mission_id=identity,card_mission_id=identity,event_store=self.store,sender=self.send,
            editor=lambda *a:pytest.fail("incident must not edit unrelated card"),delivery_retry_authority=retry)
        return {**result,"provider_delivery_confirmed":bool(result.get("telegram_message_id")) and
            (result.get("success") is True or result.get("provider_delivery_confirmed") is True),
            "provider_message_id":str(result.get("telegram_message_id") or "")}


def test_two_workers_use_actual_family_atomic_claim_and_send_only_once():
    memory=Memory(); family=FamilyRail(); family.barrier=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes=list(executor.map(lambda _:memory.run(snapshot(),notify=family.notify),range(2)))
    assert sum(row["telegram_sends"] for row in outcomes)==1 and len(family.sent)==1
    family.barrier=None
    assert memory.run(snapshot(),notify=family.notify)["telegram_sends"]==0


def test_actual_family_failed_delivery_retries_same_identity_once():
    memory=Memory(); family=FamilyRail(); family.fail=True
    assert memory.run(snapshot(),notify=family.notify)["notification_count"]==0
    family.fail=False
    assert memory.run(snapshot(),notify=family.notify)["notification_count"]==1
    assert len(family.sent)==2 and family.sent[0]==family.sent[1]
    assert memory.run(snapshot(),notify=family.notify)["telegram_sends"]==0


def test_execution_receipt_failure_recovers_confirmed_family_delivery_without_resend():
    memory=Memory(); family=FamilyRail(); memory.persist=False
    first=memory.run(snapshot(),notify=family.notify)
    assert first["success"] is False and len(family.sent)==1
    memory.persist=True
    later=memory.run(snapshot(),notify=family.notify)
    assert later["notification_count"]==1 and len(family.sent)==1


@pytest.mark.parametrize("report_due", [False,True])
def test_actual_gateway_reports_provider_outage_before_failed_plan(report_due,monkeypatch):
    from modules.oom_sakkie import automatic_reassessment_scheduler as scheduler
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.telemetry import rootline_water_energy_plan as planning
    calls=[]; delivered=[]
    monkeypatch.setattr(scheduler,"run_due_reassessment",lambda **kw:(kw["invoke"] if report_due else kw["invoke_not_due"])())
    monkeypatch.setattr(planning,"ensure_due_daily_program",lambda **kw:({"success":True},200))
    def safety(**kw):
        calls.append("safety")
        return {"success":True,"status":"no_active_irrigation","hardware_commands":0,"telegram_sends":0}
    def provider(**kw):
        calls.append("provider_notice")
        value=snapshot()["scopes"][0]
        return {**kw["notify"]("ProviderUnavailable",{**value,"notification_identity":value["incident_id"]+":unavailable"}),
            "status":"provider_observed"}
    def failed_plan():
        calls.append("plan")
        raise RuntimeError("offline plan unavailable")
    def delivery(parsed,result,**kw):
        delivered.append(result)
        return {"success":True,"telegram_message_id":"700","telegram_sends":1}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"scheduler_identity":scheduler.SCHEDULER_IDENTITY,"specialist":"ROOTLINE",
        "owner_user_id":"42","chat_id":"42","due_at":NOW.isoformat(),"evidence_cutoff":NOW.isoformat(),
        "trigger_id":"MINUTE1","trigger":"declared_time","trigger_timestamp":NOW.isoformat()}
    result,status=handle_rootline_reassessment_trigger(payload,{"X-Oom-Sakkie-Telegram-Token":"x"*40},env,
        schedule_store=lambda *a:{},state_store=lambda *a:{},scheduler_now=NOW,specialist_loader=failed_plan,
        active_supervision_cycle=safety,managed_device_cycle=safety,provider_notification_cycle=provider,
        family_delivery=delivery)
    assert calls[:2]==["safety","safety"]
    assert calls.count("provider_notice")==1 and len(delivered)==1
    assert result["telegram_sends"]==1
    if report_due: assert calls.index("provider_notice")<calls.index("plan")
    else: assert "plan" not in calls
    assert "OFF duties" in delivered[0]["answer"] or "AF-opdragte" in delivered[0]["answer"]
    assert delivered[0]["recipient_render_contract"]=="specialist_structured_recipient_v1"


def test_afrikaans_notification_survives_actual_family_recipient_boundary():
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    text=compose_provider_notice("ProviderUnavailable",snapshot()["scopes"][0],language="af")
    result=localize_recipient_result({"output_language":"af"},{"status":"providerunavailable","answer":text,
        "recipient_render_contract":"specialist_structured_recipient_v1","recipient_language":"af"},"ROOTLINE")
    assert result["answer"]==text and not result.get("recipient_language_render_unrecognized")


def test_pending_outage_still_alerts_after_reporting_was_offline_for_days():
    memory=Memory(); first=event("OLD",NOW-timedelta(days=20))
    assert memory.run(snapshot(failure=first))["notification_count"]==1
    assert memory.calls[0][1]["failure_event_id"]=="OLD"


def test_wrong_incident_receipt_fails_closed():
    memory=Memory(); current=snapshot(); identity=current["scopes"][0]["incident_id"]+":unavailable"
    memory.receipts[identity]={"notification_identity":identity,"execution_id":"OTHER",
        "delivery_confirmed":True,"provider_message_id":"700"}
    with pytest.raises(ValueError,match="receipt_binding"):
        memory.run(current)
    assert not memory.calls


def test_frozen_retry_payload_cannot_switch_scope_or_duty():
    memory=Memory(); current=snapshot()
    memory.run(current,notify=lambda *a,**k:{"delivery_definitely_not_sent":True})
    receipt=next(iter(memory.receipts.values()))
    receipt["provider_notice"]["scope"]="b"*64
    with pytest.raises(ValueError,match="evidence_binding"):
        memory.run(current)
    assert not memory.calls


def test_daily_plan_and_manager_facts_retain_provider_outage():
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan,manager_brief_facts
    from modules.oom_sakkie.owner_response_composer import _irrigation_brief
    value={"success":True,"provider_availability":snapshot(),"recommendations":[]}
    assert "Fresh switch-status verification is unavailable" in compose_daily_rootline_plan(value)
    facts=manager_brief_facts(value)
    assert facts["provider_availability"]["status"]=="unavailable"
    # Empty recommendation fixtures have typed Needs Data status in all registry zones.
    assert "Fresh switch-status verification is unavailable" in _irrigation_brief(facts,False)


def test_delayed_recovery_direct_answer_never_claims_current_device_state():
    failure=event(at=NOW-timedelta(days=2))
    restored=event("R",NOW-timedelta(days=1),action="complete_snapshot_restored_availability")
    text=provider_availability_text(snapshot(restored,failure,restored))
    assert "last complete recovery check" in text and "does not prove the current device state" in text


def test_registry_e_camp_duty_is_not_mislabelled_borehole():
    memory=Memory();memory.duties=[{"execution_id":"E-RUN","zone_id":"E12345","state":"Active"}]
    memory.run(snapshot())
    assert memory.calls[-1][1]["duty_label"]=="E Camp"


@pytest.mark.parametrize("identity", ["NOTICE", "ROOTLINE-PROVIDER-"+"A"*32, "ROOTLINE-PROVIDER-"+"A"*32+":wrong", None])
def test_receipt_rejects_invalid_identity_before_database_connection(identity):
    def forbidden(**kwargs):
        raise AssertionError("invalid identity must not connect")
    with pytest.raises(ValueError,match="provider_notification_identity_invalid"):
        read_notification_receipt(identity,connect=forbidden)


@pytest.mark.parametrize("suffix", [":unavailable", ":restored", ":safety:"+"a1"*12])
def test_production_receipt_reader_accepts_each_notice_identity(suffix):
    incident="ROOTLINE-PROVIDER-"+"A"*32
    identity=incident+suffix
    connection=QueueConnection([[]])
    assert read_notification_receipt(identity,connect=lambda **_:connection)=={}
    assert connection.queries[0][1]==(incident,identity)


@pytest.mark.parametrize("suffix", [":safety:", ":safety:"+"a"*23,
    ":safety:"+"a"*25, ":safety:"+"A"*24, ":safety:"+"g"*24,
    ":safety:"+"a"*24+":extra", ":restored:extra", ":unavailable:extra"])
def test_production_receipt_reader_rejects_malformed_notice_suffix(suffix):
    def forbidden(**kwargs):
        raise AssertionError("malformed identity must not connect")
    with pytest.raises(ValueError,match="provider_notification_identity_invalid"):
        read_notification_receipt("ROOTLINE-PROVIDER-"+"A"*32+suffix,connect=forbidden)


def test_generated_active_duty_safety_notice_reaches_actual_receipt_reader():
    memory=Memory()
    memory.duties=[{"execution_id":"E-RUN","zone_id":"E12345","state":"Active"}]
    connection=QueueConnection([[],[]])
    result=recover_provider_notifications(notify=memory.notify,now=NOW,
        store=memory.store,receipt_loader=lambda identity:read_notification_receipt(
            identity,connect=lambda **_:connection),loader=lambda **_:snapshot(),clock=lambda:NOW)
    assert result["notification_count"]==2
    assert [call[0] for call in memory.calls]==["ProviderUnavailable","ProviderSafety"]
    assert ":safety:" in connection.queries[1][1][1]
    assert all(params[0]==params[1].partition(":")[0] for _,params in connection.queries)
