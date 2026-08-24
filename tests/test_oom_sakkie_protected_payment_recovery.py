from datetime import datetime, timezone
from threading import Barrier, Lock, Thread
import pytest

from modules.oom_sakkie.protected_payment_recovery import (
    _health_observation_completion, run_payment_recovery_cycle)


CLAIM = {"callback_token": "retained", "action_kind": "sam_sale_payment",
    "owner_user_id": "owner", "private_chat_id": "owner", "mission_id": "SMQ-20260813-05",
    "preview_digest": "outer-digest", "evidence_generation": "evidence-digest",
    "preview_payload": {"payment_preview_digest": "payment-digest"}, "status": "executing",
    "result_payload": None, "preview_card_message_id": "3638",
    "confirmation_provider_message_id": "original-callback",
    "confirmation_provider_timestamp": "2026-08-15T12:16:15+00:00"}
OBSERVATION_BINDING = {"canonical_human_identity":{"pig_name":"","tag_number":"Prince"},
    "canonical_observation":{"observed":[{"fact":key,"value":True} for key in
        ("eating_reported","standing_reported","moving_reported","normal_behaviour_reported")]},
    "canonical_welfare_state":"monitoring"}


def test_observation_completion_uses_human_identity_facts_and_recipient_language():
    bound={**OBSERVATION_BINDING,
        "canonical_human_identity":{"pig_name":"Prince","tag_number":"146"}}
    en=_health_observation_completion(bound,"en")
    af=_health_observation_completion(bound,"af")
    assert en.startswith("<b>Prince (tag 146) — OBSERVATION RECORDED</b>")
    assert "eating, standing, walking and acting normally" in en
    assert "Welfare monitoring remains open" in en and "PIG-" not in en
    assert af.startswith("<b>Prince (tag 146) — WAARNEMING AANGETEKEN</b>")
    assert "eet, staan, loop en tree normaal op" in af
    assert "Welfare" not in af and "OBSERVATION" not in af


@pytest.mark.parametrize(("state","expected"),(
    ("monitoring","Welfare monitoring remains open"),
    ("open","Welfare follow-up remains open"),
    ("escalated","Welfare follow-up is escalated"),
    ("closed","The welfare case is closed"),
))
def test_observation_completion_preserves_exact_welfare_state(state,expected):
    value=_health_observation_completion({**OBSERVATION_BINDING,
        "canonical_welfare_state":state},"en")
    assert expected in value


@pytest.mark.parametrize("patch",(
    {"canonical_human_identity":{}},
    {"canonical_observation":{"observed":[]}},
    {"canonical_welfare_state":""},
))
def test_observation_completion_fails_closed_when_canonical_binding_incomplete(patch):
    with pytest.raises(ValueError,match="health_loss_recovery_effect_unresolved"):
        _health_observation_completion({**OBSERVATION_BINDING,**patch},"en")


def test_observation_completion_escapes_human_identity():
    value=_health_observation_completion({**OBSERVATION_BINDING,
        "canonical_human_identity":{"pig_name":"Prince <One>","tag_number":"A&B"}},"en")
    assert "Prince &lt;One&gt; (tag A&amp;B)" in value
    assert "<One>" not in value


class Store:
    def __init__(self):
        self.lock = Lock(); self.claimed = False; self.cycles = []; self.releases = []
    def start_cycle(self, cycle, now, next_cycle): self.cycles.append((cycle, "started"))
    def acquire(self, cycle, now):
        with self.lock:
            if self.claimed: return None
            self.claimed = True
            return dict(CLAIM)
    def release(self, token, cycle, now, status, result): self.releases.append(status)
    def finish_cycle(self, cycle, now, result): self.cycles.append((cycle, result["status"]))


def test_recovery_binds_existing_claim_completes_and_edits_original_card():
    store = Store(); calls = {"execute": 0, "complete": 0, "deliver": 0}
    result_payload = {"success": True, "status": "payment_state_recorded",
        "received_amount": "4470.51", "payment_method": "EFT", "payment_date": "2026-08-11",
        "card_mission_id": "SMQ-20260813-05:PAYMENT:PAYMENT-DIGEST", "answer": "closed",
        "writes_to_supabase": True, "reply_markup": {"inline_keyboard": []}}
    def execute(claim, **_): calls["execute"] += 1; return dict(result_payload), 200
    def complete(token, result, **_): calls["complete"] += 1; return {"result": result}
    def deliver(parsed, result, **kwargs):
        calls["deliver"] += 1
        assert parsed["telegram_user_id"] == "owner"
        assert kwargs["card_mission_id"] == result_payload["card_mission_id"]
        return {"success": True, "telegram_message_id": "3638", "telegram_sends": 0, "telegram_edits": 1}
    result = run_payment_recovery_cycle(now=datetime(2026, 8, 15, 15, tzinfo=timezone.utc),
        store=store, executor=execute, completer=complete, deliverer=deliver)
    assert result["status"] == "payment_recovery_completed"
    assert result["provider_message_id"] == "3638"
    assert result["payment_write_observed"] is True
    assert calls == {"execute": 1, "complete": 1, "deliver": 1}


def test_sequential_replay_is_idle_with_zero_effect():
    store = Store(); effects = []
    run_payment_recovery_cycle(store=store,
        executor=lambda claim, **_: effects.append("write") or ({"success": True,
          "status": "recorded", "card_mission_id": "card"}, 200),
        completer=lambda token, result, **_: {"result": result},
        deliverer=lambda *a, **k: {"success": True, "telegram_message_id": "3638"})
    replay = run_payment_recovery_cycle(store=store,
        executor=lambda *a, **k: effects.append("duplicate"),
        deliverer=lambda *a, **k: effects.append("message"))
    assert replay["status"] == "payment_recovery_idle"
    assert effects == ["write"]
    assert replay["telegram_sends"] == replay["telegram_edits"] == 0


def test_completed_mortality_is_automatically_recomposed_and_delivered_without_writer(monkeypatch):
    class MortalityStore(Store):
        def acquire(self, cycle, now):
            with self.lock:
                if self.claimed: return None
                self.claimed = True
                return {**CLAIM, **OBSERVATION_BINDING, "action_kind": "mortality", "status": "completed",
                    "mission_id": "OOM-HERDMASTER-1", "preview_digest": "d"*64,
                    "canonical_effect_kind": "mortality",
                    "preview_payload": {"identity": {"pig_id": "PIG-126", "tag_number": "126"}},
                    "result_payload": {"success": True, "status": "completed",
                        "answer": "<b>Die vark SE AFSTERWE AANGETEKEN</b>",
                        "writes_farm_data": True, "rows_created": 1,
                        "lifecycle_event_id": "LIFE-1", "welfare_case_closed": True}}
    class Principal: language = "af"
    monkeypatch.setattr("modules.oom_sakkie.family_access.resolve_family_principal",
                        lambda *args, **kwargs: Principal())
    store=MortalityStore(); writes=[]; delivered=[]
    def deliver(parsed, result, **kwargs):
        delivered.append((parsed,result,kwargs))
        assert parsed["provider_message_id"] == "original-callback"
        assert parsed["provider_timestamp"] == "2026-08-15T12:16:15+00:00"
        return {"success":True,"telegram_message_id":"3959","telegram_sends":0,"telegram_edits":1}
    outcome=run_payment_recovery_cycle(store=store,
        executor=lambda *args,**kwargs:writes.append(args), deliverer=deliver)
    assert outcome["status"]=="payment_recovery_completed" and writes==[]
    parsed,result,kwargs=delivered[0]
    assert parsed["output_language"]=="af" and kwargs["specialist"]=="HERDMASTER"
    assert result["answer"].startswith("<b>VARK 126 AANGETEKEN</b>")
    assert "Die vark SE AFSTERWE" not in result["answer"]
    assert result["writes_farm_data"] is False and result["rows_created"]==0
    assert outcome["presentation_version"]=="health_loss_completion_factual_v3"


def test_completed_prince_observation_is_not_rewritten_as_death(monkeypatch):
    class ObservationStore(Store):
        def acquire(self, cycle, now):
            with self.lock:
                if self.claimed: return None
                self.claimed = True
                return {**CLAIM, **OBSERVATION_BINDING, "action_kind": "mortality", "status": "completed",
                    "mission_id": "OOM-HERDMASTER-PRINCE", "preview_digest": "e"*64,
                    "canonical_effect_kind": "health_observation",
                    "preview_payload": {"identity": {"pig_id": "PIG-2026-E057",
                        "tag_number": "Prince"}},
                    "result_payload": {"success": True, "status": "completed",
                        "answer": "<b>HERDMASTER OBSERVATION RECORDED</b>\n\nThe confirmed factual observation was recorded once.",
                        "writes_farm_data": True, "rows_created": 1}}
    class Principal: language = "en"
    monkeypatch.setattr("modules.oom_sakkie.family_access.resolve_family_principal",
                        lambda *args, **kwargs: Principal())
    delivered=[]
    outcome=run_payment_recovery_cycle(store=ObservationStore(),
        executor=lambda *a,**k:(_ for _ in ()).throw(AssertionError("no writer")),
        deliverer=lambda parsed,result,**kwargs: delivered.append(result) or
            {"success":True,"telegram_message_id":"3979","telegram_sends":0,"telegram_edits":1})
    assert outcome["status"]=="payment_recovery_completed"
    assert delivered[0]["answer"].startswith("<b>Prince — OBSERVATION RECORDED</b>")
    assert "eating, standing, walking and acting normally" in delivered[0]["answer"]
    assert "Welfare monitoring remains open" in delivered[0]["answer"]
    assert "PIG-2026" not in delivered[0]["answer"]
    assert "DEATH" not in delivered[0]["answer"]
    assert delivered[0]["writes_farm_data"] is False and delivered[0]["rows_created"]==0


def test_database_confirmation_datetime_keeps_exact_iso_provider_binding(monkeypatch):
    class ObservationStore(Store):
        def acquire(self, cycle, now):
            with self.lock:
                if self.claimed: return None
                self.claimed=True
                return {**CLAIM,**OBSERVATION_BINDING,"action_kind":"mortality","status":"completed",
                    "canonical_effect_kind":"health_observation",
                    "confirmation_provider_timestamp":datetime(2026,8,24,9,42,31,
                        178208,tzinfo=timezone.utc),
                    "result_payload":{"status":"completed",
                        "answer":"<b>HERDMASTER OBSERVATION RECORDED</b>"}}
    class Principal: language="en"
    monkeypatch.setattr("modules.oom_sakkie.family_access.resolve_family_principal",
                        lambda *a,**k:Principal())
    seen=[]
    result=run_payment_recovery_cycle(store=ObservationStore(),
        deliverer=lambda parsed,*a,**k: seen.append(parsed["provider_timestamp"]) or
            {"success":True,"telegram_message_id":"3979","telegram_edits":1})
    assert result["status"]=="payment_recovery_completed"
    assert seen==["2026-08-24T09:42:31.178208+00:00"]


def test_unknown_legacy_health_effect_fails_closed_without_delivery():
    class UnknownStore(Store):
        def acquire(self, cycle, now):
            with self.lock:
                if self.claimed: return None
                self.claimed=True
                return {**CLAIM,"action_kind":"mortality","status":"completed",
                    "result_payload":{"success":True,"status":"completed","answer":"untyped"}}
    delivered=[]
    store=UnknownStore()
    outcome=run_payment_recovery_cycle(store=store,
        deliverer=lambda *a,**k:delivered.append(1))
    assert outcome["status"]=="payment_recovery_pending" and delivered==[]
    assert store.releases == ["effect_unresolved"]


def test_unresolved_legacy_claim_does_not_starve_later_typed_recoveries(monkeypatch):
    base={**CLAIM,"action_kind":"mortality","status":"completed"}
    claims=[
        {**base,"preview_digest":"a"*64,"result_payload":{"status":"completed","answer":"untyped"}},
        {**base,"preview_digest":"b"*64,"canonical_effect_kind":"mortality",
         "preview_payload":{"identity":{"tag_number":"126"}},
         "result_payload":{"status":"completed","answer":"old death"}},
        {**base,**OBSERVATION_BINDING,"preview_digest":"c"*64,"canonical_effect_kind":"health_observation",
         "result_payload":{"status":"completed","answer":"<b>HERDMASTER OBSERVATION RECORDED</b>"}},
    ]
    class QueueStore(Store):
        def acquire(self, cycle, now): return claims.pop(0) if claims else None
    class Principal: language="en"
    monkeypatch.setattr("modules.oom_sakkie.family_access.resolve_family_principal",
                        lambda *a,**k:Principal())
    store=QueueStore(); delivered=[]
    outcomes=[run_payment_recovery_cycle(store=store,
        deliverer=lambda parsed,result,**kwargs: delivered.append(result["answer"]) or
            {"success":True,"telegram_message_id":"card","telegram_edits":1})
        for _ in range(3)]
    assert [row["status"] for row in outcomes] == ["payment_recovery_pending",
        "payment_recovery_completed","payment_recovery_completed"]
    assert "DEATH RECORDED" in delivered[0]
    assert delivered[1].startswith("<b>Prince — OBSERVATION RECORDED</b>")


def test_concurrent_cycles_lease_one_execution_only():
    store = Store(); barrier = Barrier(2); effects = []
    def run():
        barrier.wait()
        return run_payment_recovery_cycle(store=store,
            executor=lambda claim, **_: effects.append("write") or ({"success": True,
              "status": "recorded", "card_mission_id": "card"}, 200),
            completer=lambda token, result, **_: {"result": result},
            deliverer=lambda *a, **k: {"success": True, "telegram_message_id": "3638"})
    threads = [Thread(target=run) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert effects == ["write"]


def test_store_records_actual_finish_heartbeat_not_cycle_start():
    class Cursor:
        def __init__(self): self.params = None
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params): self.params = params
    class Connection:
        def __init__(self, cursor): self.value = cursor
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return self.value
    from modules.oom_sakkie.protected_payment_recovery import _RecoveryStore
    cursor = Cursor(); started = datetime(2026, 8, 15, 13, 15, tzinfo=timezone.utc)
    _RecoveryStore(lambda: Connection(cursor)).finish_cycle("cycle", started, {"status": "idle"})
    assert cursor.params[0] > started
    assert cursor.params[1] == cursor.params[0]
