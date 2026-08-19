from datetime import datetime, timezone

from modules.oom_sakkie.automatic_reassessment_scheduler import (
    SCHEDULER_IDENTITY, run_due_reassessment,
)
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger

NOW = datetime(2026, 8, 5, 8, 15, tzinfo=timezone.utc)


def memory_store():
    rows = {}
    def store(action, identity, payload):
        if action == "load_latest_outcome":
            matches = [v for k, v in rows.items() if k.endswith("-OUTCOME") and v.get("specialist") == identity]
            return matches[-1] if matches else None
        if action == "load_schedule":
            matches = [v for k, v in rows.items() if k.startswith(identity)]
            return matches[-1] if matches else None
        key = identity if action == "claim_schedule" else identity + "-OUTCOME"
        if key in rows:
            return {"success": True, "created": False}
        rows[key] = dict(payload)
        return {"success": True, "created": True}
    return rows, store


def scheduled_payload(**changes):
    value = {"scheduler_identity": SCHEDULER_IDENTITY, "specialist": "ROOTLINE",
             "due_at": "2026-08-05T10:15:00+02:00",
             "evidence_cutoff": "2026-08-05T10:14:59+02:00"}
    value.update(changes)
    return value


def test_due_claim_is_deterministic_and_replay_never_invokes_twice():
    rows, store = memory_store(); calls = []
    def invoke():
        calls.append(1)
        return {"success": True, "status": "rootline_reassessment_unchanged",
                "notify_owner": False, "telegram_sends": 0, "telegram_edits": 0,
                "hardware_commands": 0, "writes_farm_data": False}
    first = run_due_reassessment(payload=scheduled_payload(), invoke=invoke, store=store, now=NOW)
    replay = run_due_reassessment(payload=scheduled_payload(), invoke=invoke, store=store, now=NOW)
    assert first["terminal_outcome"] == "completed"
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    assert len(calls) == 1 and len(rows) == 2
    assert first["next_due_at"] == "2026-08-05T10:30:00+02:00"


def test_clock_drift_future_due_and_unsupported_specialist_fail_closed():
    _, store = memory_store()
    future = run_due_reassessment(payload=scheduled_payload(due_at="2026-08-05T11:00:00+02:00"),
                                  invoke=lambda: {}, store=store, now=NOW)
    unsupported = run_due_reassessment(payload=scheduled_payload(specialist="HERDMASTER"),
                                       invoke=lambda: {}, store=store, now=NOW)
    assert future["status"] == "scheduled_reassessment_not_due"
    assert unsupported["status"] == "scheduled_reassessment_binding_invalid"
    assert future["telegram_sends"] == unsupported["hardware_commands"] == 0


def test_only_bounded_latest_missed_run_can_execute_after_restart():
    _, store = memory_store(); calls = []
    old = run_due_reassessment(
        payload=scheduled_payload(due_at="2026-08-05T09:30:00+02:00"),
        invoke=lambda: calls.append(1), store=store, now=NOW)
    recent = run_due_reassessment(
        payload=scheduled_payload(due_at="2026-08-05T09:50:00+02:00"),
        invoke=lambda: {"success": True, "status": "rootline_reassessment_unchanged"},
        store=store, now=NOW)
    assert old["status"] == "scheduled_reassessment_not_due" and calls == []
    assert recent["success"] is True


def test_restart_after_claim_reenters_specialist_recovery():
    rows, store = memory_store()
    identity = "OOM-SCHEDULE-ROOTLINE-20260805T101500+0200"
    receipt = __import__("hashlib").sha256(
        "oom_sakkie_reassessment_schedule.v1|ALERT-POWER-BACKEND-DELIVERY:OOM-SAKKIE-REASSESSMENT|ROOTLINE|2026-08-05T10:15:00+02:00".encode()
    ).hexdigest()
    rows[identity] = {"invocation_receipt": receipt, "terminal_outcome": "claimed"}
    calls = []
    result = run_due_reassessment(payload=scheduled_payload(), invoke=lambda: calls.append("specialist"),
        recover_delivery=lambda: (calls.append("delivery") or
            {"success":True,"status":"protected_delivery_replayed_noop"}),
        store=store, now=NOW)
    assert result["status"] == "protected_delivery_replayed_noop"
    assert calls == ["delivery"] and result["terminal_outcome"] == "claimed"
    assert result.get("next_due_at") is None


def test_restart_recovery_does_not_claim_completion_when_outcome_write_fails():
    rows, backing = memory_store()
    identity = "OOM-SCHEDULE-ROOTLINE-20260805T101500+0200"
    receipt = __import__("hashlib").sha256(
        "oom_sakkie_reassessment_schedule.v1|ALERT-POWER-BACKEND-DELIVERY:OOM-SAKKIE-REASSESSMENT|ROOTLINE|2026-08-05T10:15:00+02:00".encode()
    ).hexdigest()
    rows[identity] = {"invocation_receipt": receipt, "status": "claimed", "terminal_outcome": ""}
    def failing(action, item, payload):
        return {"success": False} if action == "record_outcome" else backing(action, item, payload)
    result = run_due_reassessment(payload=scheduled_payload(), invoke=lambda: {}, store=failing, now=NOW)
    assert result["status"] == "scheduled_reassessment_claim_interrupted"
    assert result["terminal_outcome"] == "claimed"
    assert result.get("next_due_at") is None and rows[identity]["status"] == "claimed"


def test_durable_next_due_suppresses_early_scheduler_tick():
    rows, store = memory_store()
    rows["prior-OUTCOME"] = {"specialist": "ROOTLINE", "status": "completed",
                             "next_due_at": "2026-08-05T11:00:00+02:00"}
    calls = []
    result = run_due_reassessment(payload=scheduled_payload(), invoke=lambda: calls.append(1),
                                  store=store, now=NOW)
    assert result["status"] == "scheduled_reassessment_not_yet_due"
    assert result["next_due_at"] == "2026-08-05T11:00:00+02:00" and calls == []


def test_non_bucket_next_due_never_runs_early():
    rows, store = memory_store()
    rows["prior-OUTCOME"] = {"specialist": "ROOTLINE", "status": "completed",
                             "next_due_at": "2026-08-05T10:40:00+02:00"}
    early = run_due_reassessment(payload=scheduled_payload(due_at="2026-08-05T10:30:00+02:00"),
                                 invoke=lambda: {"success": True}, store=store,
                                 now=datetime(2026, 8, 5, 8, 30, tzinfo=timezone.utc))
    allowed = run_due_reassessment(payload=scheduled_payload(due_at="2026-08-05T10:45:00+02:00",
                                      evidence_cutoff="2026-08-05T10:44:59+02:00"),
                                   invoke=lambda: {"success": True, "status": "unchanged"}, store=store,
                                   now=datetime(2026, 8, 5, 8, 45, tzinfo=timezone.utc))
    assert early["status"] == "scheduled_reassessment_not_yet_due"
    assert allowed["terminal_outcome"] == "completed"


def test_due_bucket_runs_after_owned_second_offset_has_elapsed():
    rows, store = memory_store()
    rows["prior-OUTCOME"] = {"specialist": "ROOTLINE", "status": "completed",
                             "next_due_at": "2026-08-05T10:15:26+02:00"}
    calls = []
    result = run_due_reassessment(payload=scheduled_payload(),
        invoke=lambda: calls.append(1) or {"success": True, "status": "unchanged"},
        store=store, now=datetime(2026, 8, 5, 8, 15, 43, tzinfo=timezone.utc))
    assert result["terminal_outcome"] == "completed"
    assert calls == [1]


def test_gateway_scheduled_unchanged_records_receipt_and_zero_io():
    rows, schedules = memory_store(); state_rows = {}
    material = {"success": True, "overall_status": "Hold", "result_id": "R1", "generation": "G1",
                "recommendations": [{"subject": "C Camp", "status": "Hold", "reason": "No change."}],
                "evidence_cutoff": "2026-08-05T10:14:00+02:00",
                "owner_brief": {"family_fact_needed": ""}}
    from modules.oom_sakkie.rootline_reassessment_lifecycle import _material_digest
    digest = _material_digest(material)
    def state(action, identity, payload):
        if action == "record_observation":
            created = identity not in state_rows
            state_rows.setdefault(identity, payload)
            return {"success": True, "created": created}
        if action == "load_delivered":
            return {"owner_user_id": "42", "chat_id": "42", "material_digest": digest,
                    "operating_date": "", "result_id": "R1",
                    "evidence_generation": "G1", "delivery_state": "delivered",
                    "provider_message_id": "3240"}
        return state_rows.get(identity)
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
           "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}
    payload = {**scheduled_payload(), "owner_user_id": "42", "chat_id": "42",
               "trigger": "declared_time", "trigger_id": "ROOTLINE-20260805-1015",
               "trigger_timestamp": "2026-08-05T10:15:00+02:00"}
    result, status = handle_rootline_reassessment_trigger(
        payload, {"X-Oom-Sakkie-Telegram-Token": "x" * 40}, env,
        specialist_loader=lambda: material, state_store=state, schedule_store=schedules,
        scheduler_now=NOW, family_delivery=lambda *a, **k: (_ for _ in ()).throw(AssertionError("send")))
    assert status == 200 and result["status"] == "rootline_reassessment_unchanged"
    assert result["telegram_sends"] == result["hardware_commands"] == 0
    assert result["writes_farm_data"] is False and len(rows) == 2


def test_fresh_plan_is_delivered_before_contained_execution_with_zero_hardware_commands():
    rows,schedules=memory_store(); cycles=[]; deliveries=[]
    lifecycle = {}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true",
         "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42",
         "ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"}
    bound={**scheduled_payload(),"owner_user_id":"42","chat_id":"42","trigger":"declared_time",
           "trigger_id":"AUTO-1","trigger_timestamp":"2026-08-05T10:15:00+02:00"}
    def cycle(**kwargs):
        cycles.append(kwargs)
        return {"success":True,"status":"zone_contained","hardware_commands":0,
                "telegram_messages":0,"writes_farm_data":False}
    def deliver(*args,**kwargs):
        deliveries.append((args,kwargs)); return {"success":True,"status":"family_message_delivered",
            "telegram_message_id":"9100","telegram_sends":1}
    current = {"success":True,"overall_status":"Hold","operating_date":"2026-08-05",
        "result_id":"RESULT-1","generation":"GEN-1",
        "evidence_cutoff":"2026-08-05T10:14:00+02:00",
        "recommendations":[{"subject":"B12345","status":"Hold","reason":"Contained."}],
        "owner_brief":{"family_fact_needed":""}}
    def state(action, identity, payload):
        if action == "load_delivered":
            delivered = [row for row in lifecycle.values() if row.get("delivery_state") == "delivered"]
            return delivered[-1] if delivered else None
        if action == "load_identity": return lifecycle.get(identity)
        if action in {"record_observation", "claim_pending"}:
            created = identity not in lifecycle; lifecycle.setdefault(identity, payload)
            return {"success":True,"created":created}
        if action == "mark_delivered":
            lifecycle[identity] = {**lifecycle[identity], **payload}; return {"success":True}
    value,status=handle_rootline_reassessment_trigger(bound,
        {"X-Oom-Sakkie-Telegram-Token":"x"*40},env,schedule_store=schedules,
        state_store=state,
        scheduler_now=NOW,family_delivery=deliver,execution_cycle=cycle,
        specialist_loader=lambda:current)
    assert status==200 and value["status"]=="scheduled_rootline_plan_and_execution_completed"
    assert value["plan_delivery_status"]=="delivered_current_irrigation_plan"
    assert value["plan_reassessment_status"]=="rootline_reassessment_changed"
    assert value["execution_status"]=="zone_contained"
    assert len(cycles)==len(deliveries)==1 and value["hardware_commands"]==0
    assert value["telegram_sends"]==1
    assert cycles[0]["owner_user_id"]==cycles[0]["chat_id"]=="42"
    assert cycles[0]["observation_store"] is not None


def test_plan_delivery_failure_and_containment_return_exact_separate_statuses():
    _, schedules = memory_store(); events = {}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true",
         "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42",
         "ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"}
    bound={**scheduled_payload(),"owner_user_id":"42","chat_id":"42","trigger":"declared_time",
           "trigger_id":"AUTO-FAIL","trigger_timestamp":"2026-08-05T10:15:00+02:00"}
    current={"success":True,"overall_status":"Hold","operating_date":"2026-08-05",
        "result_id":"RESULT-FAIL","generation":"GEN-FAIL",
        "evidence_cutoff":"2026-08-05T10:14:00+02:00","recommendations":[],
        "owner_brief":{"family_fact_needed":""}}
    def state(action, identity, payload):
        if action == "load_delivered": return None
        if action == "load_identity": return events.get(identity)
        if action in {"record_observation","claim_pending"}:
            created=identity not in events; events.setdefault(identity,payload)
            return {"success":True,"created":created}
        return {"success":False}
    result,status=handle_rootline_reassessment_trigger(bound,
        {"X-Oom-Sakkie-Telegram-Token":"x"*40},env,schedule_store=schedules,
        state_store=state,scheduler_now=NOW,specialist_loader=lambda:current,
        family_delivery=lambda *a,**k:{"success":False,"status":"family_message_delivery_failed",
            "telegram_sends":0},
        execution_cycle=lambda **k:{"success":True,"status":"zone_contained",
            "hardware_commands":0,"writes_farm_data":False})
    assert status==202 and result["status"]=="scheduled_rootline_plan_or_execution_contained"
    assert result["plan_delivery_status"]=="current_irrigation_plan_delivery_unconfirmed"
    assert result["plan_reassessment_status"]=="rootline_reassessment_changed"
    assert result["execution_status"]=="zone_contained"
    assert result["hardware_commands"]==result["telegram_sends"]==0


def test_scheduler_denies_unknown_or_configured_family_before_load_delivery_or_execution():
    calls = []
    family_binding = __import__("json").dumps([{"telegram_user_id": "43",
        "role": "trusted_family_reporter", "family_key": "dad",
        "permissions": ["farm_observation"], "summary_domains": [],
        "authorization_id": "AUTH-1", "authorized_by_user_id": "42",
        "authorized_at": "2026-08-01T08:00:00+02:00"}])
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
        "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": "42",
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42,43",
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": family_binding,
        "ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}
    for target in ("43", "99"):
        value, status = handle_rootline_reassessment_trigger(
            {**scheduled_payload(), "owner_user_id": target, "chat_id": target,
             "trigger": "declared_time", "trigger_id": "DENIED-" + target,
             "trigger_timestamp": "2026-08-05T10:15:00+02:00"},
            {"X-Oom-Sakkie-Telegram-Token": "x" * 40}, env,
            specialist_loader=lambda: calls.append("load"),
            family_delivery=lambda *a, **k: calls.append("send"),
            execution_cycle=lambda **k: calls.append("execute"))
        assert status == 403 and value["status"] == "rootline_reassessment_owner_binding_denied"
    assert calls == []


def test_scheduled_ambiguous_delivery_is_contained_and_never_claimed_complete():
    rows, schedules = memory_store(); state_rows = {}
    def state(action, identity, payload):
        if action == "record_observation":
            created = identity not in state_rows
            state_rows.setdefault(identity, payload)
            return {"success": True, "created": created}
        if action == "load_delivered": return None
        if action == "load_identity": return state_rows.get(identity)
        if action == "claim_pending":
            state_rows.setdefault(identity, payload); return {"success": True, "created": True}
        if action == "mark_ambiguous":
            state_rows[identity] = {**state_rows[identity], **payload}; return {"success": True}
    current = {"success": True, "overall_status": "Hold", "result_id": "R2", "generation": "G2",
               "evidence_cutoff": "2026-08-05T10:14:00+02:00",
               "recommendations": [{"subject": "C Camp", "status": "Hold", "reason": "Changed."}],
               "owner_brief": {"family_fact_needed": ""}}
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
           "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}
    payload = {**scheduled_payload(), "owner_user_id": "42", "chat_id": "42",
               "trigger": "declared_time", "trigger_id": "ROOTLINE-20260805-1015",
               "trigger_timestamp": "2026-08-05T10:15:00+02:00"}
    result, status = handle_rootline_reassessment_trigger(
        payload, {"X-Oom-Sakkie-Telegram-Token": "x" * 40}, env,
        specialist_loader=lambda: current, state_store=state, schedule_store=schedules,
        scheduler_now=NOW,
        family_delivery=lambda *a, **k: {"success": False,
            "status": "family_message_delivery_ambiguous", "telegram_sends": 0})
    assert status == 202 and result["terminal_outcome"] == "contained"
    assert result["status"] == "scheduled_reassessment_delivery_contained"
    assert result["scheduled_underlying_status"] == "rootline_reassessment_changed"
    assert rows[next(k for k in rows if k.endswith("-OUTCOME"))]["status"] == "contained"


def test_evidence_newer_than_bound_is_contained_before_any_delivery():
    _, schedules = memory_store(); sends = []
    current = {"success": True, "evidence_cutoff": "2026-08-05T10:15:01+02:00"}
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
           "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}
    payload = {**scheduled_payload(), "owner_user_id": "42", "chat_id": "42",
               "trigger": "declared_time", "trigger_id": "ROOTLINE-20260805-1015",
               "trigger_timestamp": "2026-08-05T10:15:00+02:00"}
    result, status = handle_rootline_reassessment_trigger(
        payload, {"X-Oom-Sakkie-Telegram-Token": "x" * 40}, env,
        specialist_loader=lambda: current, state_store=lambda *a: None,
        schedule_store=schedules, scheduler_now=NOW,
        family_delivery=lambda *a, **k: sends.append(1))
    assert status == 202 and result["terminal_outcome"] == "contained"
    assert sends == [] and result["telegram_sends"] == 0


def test_material_change_notifies_once_then_next_bucket_is_silent():
    rows, schedules = memory_store(); events = {}; delivered = []; sends = []
    current = {"success": True, "overall_status": "Needs data", "result_id": "R3", "generation": "G3",
               "evidence_cutoff": "2026-08-05T10:14:00+02:00",
               "recommendations": [{"subject": "C Camp", "status": "Hold", "reason": "Storage changed."}],
               "next_reassessment": {"trigger": "new_canonical_evidence_or_next_read",
                                     "at": "2026-08-05T10:30:00+02:00"},
               "owner_brief": {"family_fact_needed": "Current storage level?"}}
    def state(action, identity, payload):
        if action == "record_observation":
            created = identity not in events
            events.setdefault(identity, payload)
            return {"success": True, "created": created}
        if action == "load_delivered": return delivered[-1] if delivered else None
        if action == "load_identity": return events.get(identity)
        if action == "claim_pending":
            created = identity not in events; events.setdefault(identity, payload)
            return {"success": True, "created": created}
        if action == "mark_delivered":
            events[identity] = {**events[identity], **payload}; delivered.append(events[identity])
            return {"success": True}
    def family(*args, **kwargs):
        sends.append(1); return {"success": True, "status": "family_message_delivered",
                                 "telegram_message_id": "9001", "telegram_sends": 1}
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
           "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}
    headers = {"X-Oom-Sakkie-Telegram-Token": "x" * 40}
    base = {**scheduled_payload(), "owner_user_id": "42", "chat_id": "42",
            "trigger": "declared_time", "trigger_id": "ROOTLINE-20260805-1015",
            "trigger_timestamp": "2026-08-05T10:15:00+02:00"}
    first, _ = handle_rootline_reassessment_trigger(base, headers, env, specialist_loader=lambda: current,
        state_store=state, schedule_store=schedules, scheduler_now=NOW, family_delivery=family)
    replay, _ = handle_rootline_reassessment_trigger(base, headers, env, specialist_loader=lambda: current,
        state_store=state, schedule_store=schedules, scheduler_now=NOW, family_delivery=family)
    later = {**base, "due_at": "2026-08-05T10:30:00+02:00",
             "evidence_cutoff": "2026-08-05T10:29:59+02:00",
             "trigger_id": "ROOTLINE-20260805-1030", "trigger_timestamp": "2026-08-05T10:30:00+02:00"}
    later_current = {**current, "evidence_cutoff": "2026-08-05T10:29:00+02:00"}
    unchanged, _ = handle_rootline_reassessment_trigger(later, headers, env, specialist_loader=lambda: later_current,
        state_store=state, schedule_store=schedules,
        scheduler_now=datetime(2026, 8, 5, 8, 30, tzinfo=timezone.utc), family_delivery=family)
    assert first["telegram_sends"] == 1 and replay["status"] == "scheduled_reassessment_replayed_noop"
    assert unchanged["status"] == "rootline_reassessment_unchanged" and unchanged["telegram_sends"] == 0
    assert len(sends) == 1
    observations = [row for row in events.values()
                    if row.get("delivery_state") == "observation_only"]
    assert len(observations) == 2
    assert {row["evidence_cutoff"] for row in observations} == {
        "2026-08-05T10:14:00+02:00", "2026-08-05T10:29:00+02:00"}
