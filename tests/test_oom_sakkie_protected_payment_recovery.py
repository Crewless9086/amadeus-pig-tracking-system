from datetime import datetime, timezone
from threading import Barrier, Lock, Thread

from modules.oom_sakkie.protected_payment_recovery import run_payment_recovery_cycle


CLAIM = {"callback_token": "retained", "action_kind": "sam_sale_payment",
    "owner_user_id": "owner", "private_chat_id": "owner", "mission_id": "SMQ-20260813-05",
    "preview_digest": "outer-digest", "evidence_generation": "evidence-digest",
    "preview_payload": {"payment_preview_digest": "payment-digest"}, "status": "executing",
    "result_payload": None, "preview_card_message_id": "3638",
    "confirmation_provider_message_id": "original-callback",
    "confirmation_provider_timestamp": "2026-08-15T12:16:15+00:00"}


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
