import json

import modules.oom_sakkie.family_activation_runtime as runtime


OWNER = "5721652188"


def binding(user, role, family, permissions):
    return {"telegram_user_id": user, "role": role, "family_key": family,
        "permissions": permissions, "summary_domains": ["herd", "welfare", "breeding",
            "farrowing", "irrigation", "water", "weather", "power"], "language": "af",
        "authorization_id": ("OOM-FAMILY-AUTH-ANTON-20260815" if family == "dad"
            else "OOM-FAMILY-AUTH-ANTOINETTE-20260815"), "authorized_by_user_id": OWNER,
        "authorized_at": "2026-08-16T08:00:00+02:00"}


def environment():
    anton = binding("8228742738", "farm_manager", "dad", ["farm_observation",
        "active_follow_up", "explicit_summary", "welfare_hold", "welfare_escalation",
        "found_dead_observation", "herdmaster_management_input", "herdmaster_reassessment",
        "irrigation_start", "irrigation_continue"])
    antoinette = binding("8235612950", "read_only_family_member", "mum", ["explicit_summary"])
    return {runtime.ENABLED_ENV: "true", "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([anton, antoinette])}


def test_deployed_activation_records_and_delivers_each_binding_once():
    records = []; deliveries = []
    result = runtime.activate_family_access(environ=environment(),
        binding_recorder=lambda row, **_: records.append(row) or {
            "success": True, "created": True},
        deliver=lambda parsed, value, **kwargs: deliveries.append((parsed, value, kwargs)) or {
            "success": True, "provider_delivery_confirmed": True,
            "telegram_message_id": str(len(deliveries)), "telegram_sends": 1,
            "telegram_edits": 0})
    assert result["success"] and result["telegram_sends"] == 2
    assert len(records) == len(deliveries) == 2
    assert all(row[0]["telegram_user_id"] == row[0]["telegram_chat_id"] for row in deliveries)
    assert "STOP/OFF" in deliveries[0][1]["answer"]
    assert "leesalleen" in deliveries[1][1]["answer"]
    assert result["farm_writes"] == result["hardware_commands"] == 0


def test_invalid_or_partial_configuration_sends_nothing():
    source = environment(); source["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"] = "[]"
    calls = []
    result = runtime.activate_family_access(environ=source,
        binding_recorder=lambda *_args, **_kwargs: calls.append(1),
        deliver=lambda *_args, **_kwargs: calls.append(1))
    assert not result["success"] and calls == [] and result["telegram_sends"] == 0


def test_any_identity_or_scope_drift_sends_and_writes_nothing():
    for mutate in (
        lambda rows: rows[0].update(telegram_user_id="9999999999"),
        lambda rows: rows[0].update(role="read_only_family_member"),
        lambda rows: rows[0]["permissions"].append("irrigation_stop"),
        lambda rows: rows[0]["permissions"].remove("irrigation_continue"),
        lambda rows: rows[1]["summary_domains"].remove("power"),
        lambda rows: rows[0].update(authorization_id="OTHER"),
    ):
        source = environment(); rows = json.loads(source["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"])
        mutate(rows); source["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"] = json.dumps(rows)
        calls = []
        result = runtime.activate_family_access(environ=source,
            binding_recorder=lambda *_args, **_kwargs: calls.append("write"),
            deliver=lambda *_args, **_kwargs: calls.append("send"))
        assert not result["success"] and calls == []


def test_startup_requires_explicit_flag_and_starts_once(monkeypatch):
    monkeypatch.setattr(runtime, "_STARTED", False)
    assert runtime.start_family_access_activation(environ={}) is False
    calls = []
    assert runtime.start_family_access_activation(environ={runtime.ENABLED_ENV: "true"},
        runner=lambda **_: calls.append(1)) is True
    assert runtime.start_family_access_activation(environ={runtime.ENABLED_ENV: "true"},
        runner=lambda **_: calls.append(1)) is False
