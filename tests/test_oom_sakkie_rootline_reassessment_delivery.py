import hashlib
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.oom_sakkie.rootline_material import rootline_material_digest
from modules.oom_sakkie import rootline_reassessment_store
from modules.oom_sakkie.rootline_reassessment_lifecycle import _owner_plan_fingerprint

ENV={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true",
     "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
     "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
HEADERS={"X-Oom-Sakkie-Telegram-Token":"x"*40}

def current(status="Hold", operating_date="2026-08-04"):
    return {"success":True,"overall_status":"Plan ready","result_id":"R1","generation":"G1",
        "operating_date":operating_date,
        "current_power":{"battery_soc_pct":50},"battery_policy":{"governing_reserve_soc_pct":63},
        "recommendations":[{"subject":"C12345","status":status,"reason":"Fresh evidence supports this C Camp decision."}],
        "owner_brief":{"family_fact_needed":"","reassess":"At 10:00 or when material evidence changes."}}

def memory_store():
    rows={}
    def store(action,identity,payload):
        if action=="record_observation":
            if identity in rows:return {"success":True,"created":False}
            rows[identity]=payload;return {"success":True,"created":True}
        if action=="load_delivered":
            found=[v for v in rows.values() if v.get("delivery_state")=="delivered" and f'{v["owner_user_id"]}|{v["chat_id"]}'==identity]
            return found[-1] if found else None
        if action=="load_identity": return rows.get(identity)
        if action=="claim_pending":
            if identity in rows:return {"success":True,"created":False}
            rows[identity]=payload;return {"success":True,"created":True}
        if action in {"mark_delivered","mark_ambiguous"}:
            rows[identity]={**rows[identity],**payload};return {"success":True,"created":True}
    return rows,store

def payload():
    return {"owner_user_id":"42","chat_id":"42","trigger":"declared_time",
            "trigger_id":"ROOTLINE-20260804-1000","trigger_timestamp":"2026-08-04T10:00:00+02:00"}

def test_changed_reassessment_uses_family_rail_then_replay_is_zero_send():
    rows,store=memory_store(); calls=[]
    def deliver(parsed,result,**kwargs):
        calls.append((parsed,result,kwargs)); return {"success":True,"status":"family_message_delivered",
            "telegram_message_id":"8001","telegram_sends":1,"telegram_edits":0}
    first,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:current("Run later"),state_store=store,family_delivery=deliver)
    replay,replay_status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:current("Run later"),state_store=store,family_delivery=deliver)
    assert status==200 and first["telegram_sends"]==1 and first["delivery_record"]["success"] is True
    assert replay_status==200 and replay["notify_owner"] is False and replay["telegram_sends"]==0
    assert len(calls)==1 and first["hardware_commands"]==0 and first["writes_farm_data"] is False

def test_ambiguous_delivery_is_contained_and_never_blind_retried():
    rows,store=memory_store(); calls=[]
    def ambiguous(*args,**kwargs):
        calls.append(1);return {"success":False,"status":"family_message_delivery_ambiguous","telegram_sends":0}
    first,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=ambiguous)
    replay,replay_status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=ambiguous)
    assert status==202 and replay_status==202 and replay["status"]=="rootline_reassessment_delivery_ambiguous"
    assert len(calls)==1 and replay["telegram_sends"]==0

def test_provider_confirmed_family_receipt_failure_keeps_physical_delivery_truth():
    rows,store=memory_store(); calls=[]
    def confirmed_receipt_down(*args,**kwargs):
        calls.append(1);return {"success":False,
            "status":"family_message_provider_confirmed_receipt_unavailable",
            "provider_delivery_confirmed":True,"telegram_message_id":"8002",
            "telegram_sends":1,"telegram_edits":0}
    first,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=confirmed_receipt_down)
    replay,replay_status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=confirmed_receipt_down)
    assert status==200 and first["delivery_record"]["success"] is True
    assert first["telegram_sends"]==1 and replay_status==200
    assert replay["telegram_sends"]==0 and len(calls)==1

def test_reassessment_denies_unbound_owner_and_unsafe_authority():
    _,status=handle_rootline_reassessment_trigger({**payload(),"chat_id":"99"},HEADERS,ENV,
        specialist_loader=current,state_store=memory_store()[1])
    assert status==403

def test_recurring_material_after_intervening_delivery_gets_new_date_identity():
    rows,store=memory_store(); calls=[]
    def deliver(parsed,result,**kwargs):
        calls.append(kwargs["mission_id"])
        return {"success":True,"status":"family_message_delivered",
            "telegram_message_id":str(8100+len(calls)),"telegram_sends":1,"telegram_edits":0}
    for day,status in (("2026-08-11","Hold"),("2026-08-12","Run later"),("2026-08-15","Hold")):
        result,http=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
            specialist_loader=lambda d=day,s=status:current(s,d),
            state_store=store,family_delivery=deliver)
        assert http==200 and result["telegram_sends"]==1
    assert len(calls)==3 and len(set(calls))==3
    assert all(rows[identity]["operating_date"]==day for identity,day in zip(calls,
        ("2026-08-11","2026-08-12","2026-08-15")))

def test_moving_canonical_plan_check_is_not_a_material_owner_change():
    first=current("Run later")
    first["next_reassessment"]={"trigger":"canonical_plan_reassessment",
        "at":"2026-08-19T08:30:00+02:00","also_on":["new_canonical_evidence"]}
    later={**first,"generation":"G2","result_id":"R2",
        "next_reassessment":{**first["next_reassessment"],
            "at":"2026-08-19T08:45:00+02:00"}}
    assert rootline_material_digest(first)==rootline_material_digest(later)


def test_production_shaped_3986_to_3987_clock_only_change_is_silent():
    rows, store = memory_store()
    calls = []

    def result(at, generation, result_id):
        reason_b = "A completed irrigation is recorded for this zone today."
        reason_c = ("Continue the durable parent irrigation objective after verified "
                    "segment OFF and fresh reassessment.")
        return {"success": True, "operating_date": "2026-08-24",
            "generation": generation, "result_id": result_id,
            "evidence_cutoff": "2026-08-24T12:16:14+00:00",
            "recommendations": [
                {"subject": "B12345", "status": "Do Not Run", "reason": reason_b,
                 "preferred_window": "on_material_evidence_change"},
                {"subject": "C12345", "status": "Recommend", "reason": reason_c,
                 "preferred_window": "now_after_fresh_execution_revalidation",
                 "planned_duration_minutes": 60}],
            "irrigation_lifecycle": {
                "B12345": {"state": "Eligible", "reason": reason_b,
                    "zone_id": "B12345"},
                "C12345": {"state": "Eligible", "reason": reason_c,
                    "zone_id": "C12345"}},
            "owner_brief": {"family_fact_needed": "", "reassess": ""},
            # This production trigger retained its moving clock in the old
            # material digest, even though only the rendered next-check line changed.
            "next_reassessment": {"trigger": "durable_backend_schedule", "at": at}}

    def deliver(*_args, **_kwargs):
        calls.append(1)
        return {"success": True, "status": "family_message_delivered",
            "telegram_message_id": "3986", "telegram_sends": 1, "telegram_edits": 0}

    first, first_status = handle_rootline_reassessment_trigger(
        payload(), HEADERS, ENV,
        specialist_loader=lambda: result("2026-08-24T14:16:10+02:00", "68246A588C700598",
                                         "ROOTLINE-RESULT-20260824-68246A588C700598"),
        state_store=store, family_delivery=deliver)
    # Production message 3986 predates the structured owner-plan fingerprint.
    # Its stored trigger is the runtime invocation, not the plan schedule mode.
    predecessor = next(row for row in rows.values()
        if row.get("provider_message_id") == "3986")
    predecessor.pop("owner_plan_reassessment", None)
    predecessor.pop("owner_plan_fingerprint", None)
    predecessor.pop("owner_plan_fingerprint_version", None)
    predecessor["trigger"] = "declared_time"
    later, later_status = handle_rootline_reassessment_trigger(
        {**payload(), "trigger_id": "ROOTLINE-20260824-1416"}, HEADERS, ENV,
        specialist_loader=lambda: result("2026-08-24T14:46:14+02:00", "0B03E23C5CAA017B",
                                         "ROOTLINE-RESULT-20260824-0B03E23C5CAA017B"),
        state_store=store, family_delivery=deliver)

    assert first_status == later_status == 200
    assert first["telegram_sends"] == 1
    assert later["status"] == "rootline_reassessment_unchanged"
    assert later["telegram_sends"] == 0 and later["notify_owner"] is False
    assert len(calls) == 1


def test_owner_plan_fingerprint_does_not_suppress_genuine_visible_zone_change():
    rows, store = memory_store()
    calls = []
    first = current("Hold", "2026-08-24")
    first["next_reassessment"] = {"trigger": "durable_backend_schedule",
        "at": "2026-08-24T14:16:10+02:00"}
    changed = current("Recommend", "2026-08-24")
    changed["next_reassessment"] = {"trigger": "durable_backend_schedule",
        "at": "2026-08-24T14:46:14+02:00"}

    def deliver(*_args, **_kwargs):
        calls.append(1)
        return {"success": True, "status": "family_message_delivered",
            "telegram_message_id": str(3985 + len(calls)), "telegram_sends": 1,
            "telegram_edits": 0}

    handle_rootline_reassessment_trigger(payload(), HEADERS, ENV,
        specialist_loader=lambda: first, state_store=store, family_delivery=deliver)
    result, status = handle_rootline_reassessment_trigger(
        {**payload(), "trigger_id": "ROOTLINE-20260824-1416"}, HEADERS, ENV,
        specialist_loader=lambda: changed, state_store=store, family_delivery=deliver)
    assert status == 200 and result["telegram_sends"] == 1
    assert len(calls) == 2


def test_owner_plan_fingerprint_normalizes_only_approximate_clock_en_and_af():
    en = "<b>Next automatic reassessment:</b> around {}\nNo action required from you."
    af = "<b>Volgende outomatiese herbeoordeling:</b> omtrent {}\nGeen aksie word vereis nie."
    assert _owner_plan_fingerprint(en.format("14:16")) == _owner_plan_fingerprint(
        en.format("14:46"))
    assert _owner_plan_fingerprint(af.format("14:16")) == _owner_plan_fingerprint(
        af.format("14:46"))


def test_owner_plan_fingerprint_preserves_mode_conditions_and_fixed_deadlines():
    prefix = "<b>Next automatic reassessment:</b> "
    assert _owner_plan_fingerprint(prefix + "around 14:16 after fresh evidence") != (
        _owner_plan_fingerprint(prefix + "around 14:46 after provider recovery"))
    assert _owner_plan_fingerprint(prefix + "at fixed deadline 14:16") != (
        _owner_plan_fingerprint(prefix + "at fixed deadline 14:46"))
    assert _owner_plan_fingerprint(prefix + "when conditions change") != (
        _owner_plan_fingerprint(prefix + "on the next automatic cycle"))


def test_owner_plan_fingerprint_preserves_lifecycle_completion_and_question_text():
    base = ("<b>ROOTLINE — TODAY’S WATER PLAN</b>\n"
            "• <b>B Camp:</b> Ready after the final safety check\n"
            "<b>What I need from you:</b> Nothing\n"
            "<b>Next automatic reassessment:</b> around 14:16")
    assert _owner_plan_fingerprint(base) != _owner_plan_fingerprint(
        base.replace("Ready after the final safety check", "Completed — off and verified"))
    assert _owner_plan_fingerprint(base) != _owner_plan_fingerprint(
        base.replace("Nothing", "Is the tank low?"))

def test_legacy_ambiguous_identity_is_not_detached_or_retried():
    rows,store=memory_store(); value=current("Hold","2026-08-11")
    material=rootline_material_digest(value)
    legacy="OOM-ROOTLINE-REASSESS-"+hashlib.sha256(
        f"42|42|{material}".encode()).hexdigest()[:24].upper()
    rows[legacy]={"identity":legacy,"owner_user_id":"42","chat_id":"42",
        "operating_date":"2026-08-11","material_digest":material,
        "delivery_state":"ambiguous"}
    calls=[]
    result,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:current("Hold","2026-08-15"),
        state_store=store,family_delivery=lambda *a,**k:calls.append(1))
    assert status==202
    assert result["status"]=="rootline_reassessment_legacy_delivery_unresolved"
    assert result["telegram_sends"]==0 and calls==[]

def test_legacy_delivered_history_date_prevents_same_day_redelivery():
    rows,base_store=memory_store(); value=current("Hold","2026-08-15")
    material=rootline_material_digest(value)
    legacy="OOM-ROOTLINE-REASSESS-"+hashlib.sha256(
        f"42|42|{material}".encode()).hexdigest()[:24].upper()
    # Production store reconstructs this date from the earlier pending event
    # when the latest historical MARK_DELIVERED event omitted it.
    rows[legacy]={"identity":legacy,"owner_user_id":"42","chat_id":"42",
        "operating_date":"2026-08-15","material_digest":material,
        "delivery_state":"delivered"}
    calls=[]
    result,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:value,state_store=base_store,
        family_delivery=lambda *a,**k:calls.append(1))
    assert status==200 and result["status"] in {
        "rootline_reassessment_unchanged", "rootline_reassessment_replayed_noop"}
    assert result["telegram_sends"]==0 and calls==[]

def test_store_reconstructs_date_from_append_only_pending_history(monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def execute(self,*_): pass
        def fetchall(self):
            return [({"identity":"LEGACY","delivery_state":"delivered"},),
                    ({"identity":"LEGACY","delivery_state":"pending",
                      "operating_date":"2026-08-15"},)]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(rootline_reassessment_store,"connect_bounded_read",
                        lambda **_:Connection())
    loaded=rootline_reassessment_store._load("load_identity","LEGACY")
    assert loaded=={"identity":"LEGACY","delivery_state":"delivered",
                    "operating_date":"2026-08-15"}


def test_store_load_delivered_enriches_only_exact_predecessor_pending_packet(monkeypatch):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def execute(self,*_): pass
        def fetchall(self):
            return [
                ({"identity":"CURRENT","owner_user_id":"42","chat_id":"42",
                  "delivery_state":"delivered","provider_message_id":"8001"},),
                ({"identity":"OTHER","owner_user_id":"42","chat_id":"42",
                  "delivery_state":"pending","answer":"wrong"},),
                ({"identity":"CURRENT","owner_user_id":"42","chat_id":"42",
                  "delivery_state":"pending","operating_date":"2026-08-24",
                  "answer":"exact prior plan","zones":[{"zone_id":"B12345"}]},),
            ]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(rootline_reassessment_store,"connect_bounded_read",
                        lambda **_:Connection())
    loaded=rootline_reassessment_store._load("load_delivered","42|42")
    assert loaded["identity"] == "CURRENT"
    assert loaded["answer"] == "exact prior plan"
    assert loaded["operating_date"] == "2026-08-24"
    assert loaded["zones"] == [{"zone_id":"B12345"}]
