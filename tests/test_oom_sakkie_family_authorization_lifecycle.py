from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from modules.oom_sakkie.family_authorization_lifecycle import record_binding_decision


OWNER = "5721652188"


def binding(user="1002", role="farm_manager", family="dad"):
    permissions = (["farm_observation", "active_follow_up", "explicit_summary",
        "welfare_hold", "welfare_escalation", "found_dead_observation",
        "herdmaster_management_input", "herdmaster_reassessment",
        "irrigation_start", "irrigation_reschedule", "irrigation_pause", "irrigation_stop"]
        if role == "farm_manager" else ["explicit_summary"])
    return {"telegram_user_id": user, "role": role, "family_key": family,
        "permissions": permissions, "summary_domains": ["herd", "welfare", "breeding",
            "farrowing", "rootline", "irrigation", "water", "weather", "power"],
        "authorization_id": "CHARL-FAMILY-AUTH-20260815-" + family.upper(),
        "authorized_by_user_id": OWNER, "authorized_at": "2026-08-15T12:00:00+02:00",
        "language": "af"}


def env():
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER}


def test_records_each_identity_once_and_replay_is_zero_effect():
    rows = {}; calls = []
    def store(action, identity, payload):
        if action == "load": return list(rows.get(identity, ()))
        calls.append(identity); rows.setdefault(identity, []).append(dict(payload)); return {"success": True, "created": True}
    first = record_binding_decision(binding(), environ=env(), event_store=store)
    replay = record_binding_decision(binding(), environ=env(), event_store=store)
    assert first["created"] is True and replay["status"] == "family_binding_replay_noop"
    assert len(calls) == 1 and first["telegram_sends"] == first["farm_writes"] == 0


def test_conflicting_binding_fails_closed_without_overwrite():
    rows = {}; store_lock = Lock()
    def store(action, identity, payload):
        with store_lock:
            if action == "load": return list(rows.get(identity, ()))
            rows.setdefault(identity, []).append(dict(payload)); return {"success": True, "created": True}
    assert record_binding_decision(binding(), environ=env(), event_store=store)["success"]
    changed = binding(); changed["role"] = "read_only_family_member"; changed["permissions"] = ["explicit_summary"]
    result = record_binding_decision(changed, environ=env(), event_store=store)
    assert result["status"] == "family_binding_conflict" and not result["success"]
    assert len(next(iter(rows.values()))) == 1


def test_two_independent_family_bindings_and_concurrent_replay_remain_bounded():
    rows = {}; lock = Lock()
    def store(action, identity, payload):
        with lock:
            if action == "load": return list(rows.get(identity, ()))
            if identity in rows: return {"success": True, "created": False}
            rows[identity] = [dict(payload)]; return {"success": True, "created": True}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: record_binding_decision(binding(), environ=env(), event_store=store), range(4)))
    assert len(rows) == 1 and sum(item.get("created") is True for item in results) == 1
    mum = record_binding_decision(binding("1003", "read_only_family_member", "mum"), environ=env(), event_store=store)
    assert mum["created"] is True and len(rows) == 2
