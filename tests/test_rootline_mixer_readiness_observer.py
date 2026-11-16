from datetime import datetime, timezone

import pytest

from modules.telemetry.rootline_mixer_readiness_observer import collect_mixer_readiness
from modules.oom_sakkie.general_manager_worker import (
    deliver_farm_manager_case, run_general_manager_cycle,
)


NOW = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


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


def test_registry_binding_drift_fails_before_provider_or_ledger_calls(monkeypatch):
    import modules.telemetry.rootline_mixer_readiness_observer as observer
    from modules.telemetry.rootline_device_registry import get_device_contract
    contract = get_device_contract("FERTILIZER-MIXER-CH2")
    contract["native_fail_stop_seconds"] = 300
    monkeypatch.setattr(observer, "get_device_contract", lambda identity: contract)
    def unexpected(*args, **kwargs):
        raise AssertionError("External dependency must not be called")
    with pytest.raises(ValueError, match="rootline_mixer_registry_binding_invalid"):
        collect_mixer_readiness(now=NOW, token_store=object(), readback=unexpected,
            execution_store=unexpected)


@pytest.mark.parametrize("age,state", [(0,"ON"),(0,"OFF"),(121,"OFF")])
def test_projection_is_timestamped_informational_and_never_command_ready(age,state):
    from datetime import timedelta
    stamp=NOW-timedelta(seconds=age)
    proof={"authoritative":True,"device_id":"100204d497","channel":2,"state":state,
        "retrieved_at":stamp.isoformat(),"evidence_id":"proof"}
    execution={"auxiliary_device_id":"FERTILIZER-MIXER-CH2","device_id":"100204d497",
        "channel":2,"start_evidence":proof}
    calls=[]
    def ledger(action,selector):
        calls.append((action,selector))
        return [execution] if action=="load_auxiliary_history" else None
    row=collect_mixer_readiness(now=NOW,readback=lambda *_a,**_k:pytest.fail("provider poll"),execution_store=ledger)[0]
    assert all(selector=="FERTILIZER-MIXER-CH2" for _,selector in calls)
    assert row["canonical_observation"]["observed_at"]==stamp.isoformat()
    assert row["canonical_observation"]["current_state"]==(state if age<=120 else "Unknown")
    assert not row["equipment_evidence"]["provider_readiness_proven"]
    assert row["attention_visibility"]=="equipment_health_only"


def test_missing_canonical_observation_never_invents_current_timestamp():
    row=collect_mixer_readiness(now=NOW,execution_store=lambda *_:None)[0]
    assert row["canonical_observation"]["current_state"]=="Unknown"
    assert row["canonical_observation"]["observed_at"] is None
    assert not any(ref.startswith("observed:") for ref in row["evidence_refs"])


def test_actual_projection_retires_old_readiness_exception_without_claiming_ready():
    from modules.oom_sakkie.owner_attention_projection import build_owner_attention_projection
    candidate=collect_mixer_readiness(now=NOW,execution_store=lambda *_:None)[0]
    prior={"dedupe_key":candidate["dedupe_key"],"specialist":"ROOTLINE","urgency":"urgent",
        "lifecycle":"open","operational_status":"exception","evidence_refs":["readiness:old"],
        "unknowns":["current_provider_mixer_readiness"],"summary":"Old readiness unavailable",
        "next_action":"Check readiness"}
    result=build_owner_attention_projection([candidate],generated_at=NOW,prior_cases=[prior])
    assert result["items"]==[]
    assert not candidate["equipment_evidence"]["provider_readiness_proven"]
    faulty={**candidate,"unknowns":["shutdown_unverified"]}
    assert build_owner_attention_projection([faulty],generated_at=NOW)["items"]
