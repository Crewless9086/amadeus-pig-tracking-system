from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, Thread

from modules.oom_sakkie.rootline_physical_acceptance import (
    CONTRACT_VERSION, attach_physical_acceptance,
)

NOW = datetime(2026, 8, 15, 14, 5, tzinfo=timezone.utc)
EXECUTIONS = {
    "ROOTLINE-EXECUTION-79A473B14C98D5E58B9DD2D5": "C12345",
    "ROOTLINE-EXECUTION-8CF9AD2989F15CC5BDC696AE": "B12345",
}


def payload():
    return {"contract_version": CONTRACT_VERSION, "mission_id": "RMQ-20260813-04",
        "owner_user_id": "7", "private_chat_id": "7",
        "observed_at": NOW.isoformat(),
        "source": "control_tower_authenticated_owner_statement",
        "observations": [{"execution_id": execution, "zone_id": zone,
            "water_flow": "normal", "stopped_flow": "normal",
            "physically_off_now": True} for execution, zone in EXECUTIONS.items()]}


def execution_loader(execution_id):
    zone = EXECUTIONS.get(execution_id)
    return {"action": "record_completed", "state": "Completed",
        "execution_id": execution_id, "zone_id": zone,
        "verified_runtime_seconds": 3599, "shutdown_verified": True,
        "start_evidence": {"state": "ON"}, "shutdown_evidence": {"state": "OFF"}}


class Store:
    def __init__(self):
        self.events = {}
        self.lock = Lock()

    def __call__(self, action, identity, packet):
        with self.lock:
            rows = self.events.setdefault(identity, {})
            if action == "load":
                return deepcopy(rows.get("record_acceptance"))
            if action == "load_delivery":
                return deepcopy(rows.get("record_delivery_confirmed") or
                                rows.get("record_delivery_ambiguous"))
            created = action not in rows
            if created:
                rows[action] = deepcopy(packet)
            return {"success": True, "created": created}


def test_authenticated_fact_records_and_delivers_once_then_replays_silently():
    store = Store(); sends = []
    sender = lambda chat, text: (sends.append((chat, text)) or
                                 {"success": True, "telegram_message_id": "9001"})
    first, first_status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store, sender=sender,
        now=NOW, allowed_owner_ids={"7"})
    replay, replay_status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store, sender=sender,
        now=NOW, allowed_owner_ids={"7"})
    assert (first_status, replay_status) == (201, 200)
    assert first["telegram_sends"] == 1 and replay["telegram_sends"] == 0
    assert len(sends) == 1 and first["acceptance_sha256"] == replay["acceptance_sha256"]
    assert first["hardware_commands"] == replay["provider_control_calls"] == 0


def test_conflict_or_unproven_execution_is_zero_effect():
    store = Store(); sends = []
    ok, _ = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store,
        sender=lambda *_: (sends.append(1) or {"success": True, "telegram_message_id": "1"}),
        now=NOW, allowed_owner_ids={"7"})
    changed = payload(); changed["observed_at"] = "2026-08-15T14:04:00+00:00"
    conflict, status = attach_physical_acceptance(changed, owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store,
        sender=lambda *_: {"success": True, "telegram_message_id": "2"},
        now=NOW, allowed_owner_ids={"7"})
    assert status == 409 and conflict["status"] == "physical_acceptance_conflict"
    missing, status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=lambda _identity: None, event_store=Store(),
        sender=lambda *_: (_ for _ in ()).throw(AssertionError("sent")),
        now=NOW, allowed_owner_ids={"7"})
    assert status == 409 and missing["hardware_commands"] == 0 and len(sends) == 1


def test_owner_zone_and_physical_bindings_fail_closed():
    for change in ("owner", "zone", "execution", "flow", "off"):
        item = payload()
        if change == "owner": item["private_chat_id"] = "8"
        if change == "zone": item["observations"][0]["zone_id"] = "B12345"
        if change == "execution": item["observations"][0]["execution_id"] = "ROOTLINE-EXECUTION-OTHER"
        if change == "flow": item["observations"][0]["water_flow"] = "unknown"
        if change == "off": item["observations"][0]["physically_off_now"] = False
        result, status = attach_physical_acceptance(item, owner_principal="owner:abc",
            execution_loader=execution_loader, event_store=Store(), now=NOW,
            allowed_owner_ids={"7"})
        assert status == 400 and result["writes_farm_data"] is False


def test_concurrent_recovery_has_one_delivery_winner():
    store = Store(); sends = []; results = []
    def run():
        results.append(attach_physical_acceptance(payload(), owner_principal="owner:abc",
            execution_loader=execution_loader, event_store=store,
            sender=lambda *_: (sends.append(1) or {"success": True, "telegram_message_id": "9"}),
            now=NOW, allowed_owner_ids={"7"}))
    workers = [Thread(target=run) for _ in range(8)]
    for worker in workers: worker.start()
    for worker in workers: worker.join()
    assert len(sends) == 1
    assert sum(result[0].get("telegram_sends", 0) for result in results) == 1
    assert all(result[0]["hardware_commands"] == 0 for result in results)


def test_ambiguous_delivery_is_never_retried():
    store = Store(); sends = []
    first, status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store,
        sender=lambda *_: (sends.append(1) or {"success": False}),
        now=NOW, allowed_owner_ids={"7"})
    replay, replay_status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=store,
        sender=lambda *_: (sends.append(1) or {"success": True, "telegram_message_id": "10"}),
        now=NOW, allowed_owner_ids={"7"})
    assert status == 502 and replay_status == 409
    assert len(sends) == 1 and replay["telegram_sends"] == 0


def test_confirmed_provider_send_without_durable_marker_is_not_reported_complete():
    store = Store()
    def failing_store(action, identity, packet):
        if action == "record_delivery_confirmed":
            return {"success": False, "created": False}
        return store(action, identity, packet)
    result, status = attach_physical_acceptance(payload(), owner_principal="owner:abc",
        execution_loader=execution_loader, event_store=failing_store,
        sender=lambda *_: {"success": True, "telegram_message_id": "11"},
        now=NOW, allowed_owner_ids={"7"})
    assert status == 503
    assert result["status"] == "physical_acceptance_delivery_confirmation_persistence_unproven"
    assert result["provider_delivery_confirmed"] is True
    assert result["telegram_sends"] == 1 and result["hardware_commands"] == 0
