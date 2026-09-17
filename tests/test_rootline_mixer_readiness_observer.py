from datetime import datetime, timezone

from modules.telemetry.rootline_mixer_readiness_observer import collect_mixer_readiness
from modules.oom_sakkie.general_manager_worker import (
    deliver_farm_manager_case, run_general_manager_cycle,
)


NOW = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def provider(*args, **kwargs):
    assert args == ("100204d497",)
    observed = kwargs.get("now") or NOW
    return {"authoritative": True, "observation_fresh": True,
        "provider_timestamp_fresh": True, "device_id": "100204d497",
        "retrieved_at": observed.isoformat(),
        "response_digest": ("a" if observed == NOW else "c") * 64,
        "provider_control_calls": 0, "channels": [
            {"channel": 1, "output_state": "OFF", "native_auto_off_enabled": True,
             "native_auto_off_seconds": 120},
            {"channel": 2, "output_state": "OFF", "native_auto_off_enabled": True,
             "native_auto_off_seconds": 300}]}


def test_ready_readback_is_bounded_stable_and_replay_silent():
    first = collect_mixer_readiness(now=NOW, token_store=object(), readback=provider,
        execution_store=lambda action, payload: None)[0]
    later = collect_mixer_readiness(now=NOW.replace(minute=4), token_store=object(),
        readback=provider, execution_store=lambda action, payload: None)[0]
    assert first["urgency"] == "watch"
    assert first["unknowns"] == []
    assert first["attention_visibility"] == "equipment_health_only"
    assert first["presentation_identity"]["human_name"] == "Fertilizer mixer"
    assert first["equipment_identity"] == "FERTILIZER-MIXER-CH2"
    assert first["equipment_lifecycle"] == "ready_for_commissioning"
    assert first["equipment_evidence"]["provider_readiness_proven"] is True
    assert "physical_commissioning_proven" not in first["equipment_evidence"]
    assert "Automatic mixing is not proven enabled" in first["summary"]
    assert first["evidence_refs"][:-1] == later["evidence_refs"][:-1]
    assert "100204d497" not in first["summary"]
    assert "token" not in repr(first).lower()


def test_active_execution_or_unsafe_channel_fails_closed():
    def unsafe(*args, **kwargs):
        value = provider(*args, **kwargs)
        value["channels"][1] = {"channel": 2, "output_state": "ON",
            "native_auto_off_enabled": False, "native_auto_off_seconds": 1}
        return value
    row = collect_mixer_readiness(now=NOW, token_store=object(), readback=unsafe,
        execution_store=lambda action, payload: {"execution_id": "EXEC-1"})[0]
    assert row["urgency"] == "urgent"
    assert set(row["unknowns"]) == {"current_off", "native_fail_stop_enabled",
        "native_fail_stop_seconds", "no_conflicting_active_execution"}
    assert row["attention_visibility"] == "owner_attention_exception"
    assert row["equipment_lifecycle"] == "held"
    assert "EXEC-1" not in repr(row)


def test_control_call_claim_never_projects_ready():
    def invalid(*args, **kwargs):
        value = provider(*args, **kwargs)
        value["provider_control_calls"] = 1
        return value
    row = collect_mixer_readiness(now=NOW, token_store=object(), readback=invalid,
        execution_store=lambda action, payload: None)[0]
    assert row["unknowns"] == ["zero_control_calls"]


def test_stale_provider_timestamp_fails_closed():
    def stale(*args, **kwargs):
        value = provider(*args, **kwargs)
        value["observation_fresh"] = False
        value["provider_timestamp_fresh"] = False
        return value
    row = collect_mixer_readiness(now=NOW, token_store=object(), readback=stale,
        execution_store=lambda action, payload: None)[0]
    assert set(row["unknowns"]) == {
        "provider_observation_fresh", "provider_timestamp_not_stale"}


def test_authenticated_current_receipt_allows_omitted_provider_timestamp():
    def no_timestamp(*args, **kwargs):
        value = provider(*args, **kwargs)
        value["provider_timestamp_fresh"] = None
        return value
    row = collect_mixer_readiness(now=NOW, token_store=object(), readback=no_timestamp,
        execution_store=lambda action, payload: None)[0]
    assert row["unknowns"] == []


def test_existing_manager_cycle_collects_readiness_without_a_second_scheduler(monkeypatch):
    import modules.oom_sakkie.manager_case_sources as sources
    import modules.telemetry.rootline_mixer_readiness_observer as observer
    monkeypatch.setattr(sources, "collect_manager_candidates", lambda **kwargs: [])
    monkeypatch.setattr(observer, "collect_mixer_readiness", lambda **kwargs: [{
        "dedupe_key": "rootline-readiness:fertilizer-mixer-ch2",
        "specialist": "ROOTLINE", "urgency": "watch",
        "evidence_refs": ["readiness:" + "b" * 64], "unknowns": [],
        "summary": "ready", "next_action": "observe",
        "next_reassessment_at": NOW.isoformat(),
    }])
    monkeypatch.setattr("modules.oom_sakkie.general_manager_worker.build_scheduled_brain_guard_audit",
        lambda **kwargs: {"passed": True})

    class Store:
        def run_cycle(self, candidates, **kwargs):
            return {"candidates": list(candidates), "deliver": kwargs["deliver"]}

    result = run_general_manager_cycle(now=NOW, source_revision="revision", store=Store())
    assert [row["dedupe_key"] for row in result["candidates"]] == [
        "rootline-readiness:fertilizer-mixer-ch2"]
    assert result["deliver"] is None


def test_readiness_attention_never_uses_telegram_delivery():
    result = deliver_farm_manager_case({
        "dedupe_key": "rootline-readiness:fertilizer-mixer-ch2",
        "specialist": "ROOTLINE",
    }, deliver=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("send")))
    assert result["status"] == "readiness_attention_only"
    assert result["telegram_sends"] == 0
    assert result["provider_actions"] == 0
