from datetime import datetime, timezone

from modules.oom_sakkie.manager_case_sources import (
    collect_manager_candidate, collect_manager_candidates)


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_collectors_preserve_specialist_candidates():
    def rootline(_now):
        return [{"dedupe_key": "rootline:plan", "specialist": "ROOTLINE"}]

    assert collect_manager_candidates(now=NOW, collectors=(rootline,)) == [
        {"dedupe_key": "rootline:plan", "specialist": "ROOTLINE"}]


def test_collector_failure_becomes_one_owned_runtime_case():
    def beacon(_now):
        raise RuntimeError("secret detail must not escape")

    result = collect_manager_candidates(now=NOW, collectors=(beacon,))
    assert len(result) == 1
    case = result[0]
    assert case["dedupe_key"] == "runtime:collector:beacon"
    assert case["specialist"] == "RUNTIME"
    assert case["urgency"] == "urgent"
    assert case["evidence_refs"] == ["collector:beacon:RuntimeError"]
    assert "secret detail" not in str(case)


def test_single_case_refresh_invokes_only_owning_collector(monkeypatch):
    calls = []
    def herdmaster(now):
        calls.append("herdmaster")
        return [{"dedupe_key": "herdmaster:weekly-weight-evidence",
                 "specialist": "HERDMASTER"}]
    monkeypatch.setattr("modules.oom_sakkie.manager_case_sources._herdmaster", herdmaster)
    result = collect_manager_candidate(now=NOW,
        dedupe_key="herdmaster:weekly-weight-evidence", specialist="HERDMASTER")
    assert result == {"dedupe_key": "herdmaster:weekly-weight-evidence",
                      "specialist": "HERDMASTER"}
    assert calls == ["herdmaster"]


def test_single_case_refresh_rejects_specialist_prefix_mismatch(monkeypatch):
    calls = []
    monkeypatch.setattr("modules.oom_sakkie.manager_case_sources._herdmaster",
        lambda now: calls.append("herdmaster"))
    result = collect_manager_candidate(now=NOW,
        dedupe_key="herdmaster:weekly-weight-evidence", specialist="BEACON")
    assert result is None
    assert calls == []
