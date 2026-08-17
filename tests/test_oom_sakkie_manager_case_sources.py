from datetime import datetime, timedelta, timezone

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


def test_delivery_refresh_rejects_embedded_specialist_mismatch(monkeypatch):
    calls = []
    monkeypatch.setattr("modules.oom_sakkie.manager_case_sources._delivery_gaps",
        lambda now: calls.append("delivery"))
    result = collect_manager_candidate(now=NOW,
        dedupe_key="delivery:rootline:abc", specialist="HERDMASTER")
    assert result is None
    assert calls == []


def test_injected_collectors_are_narrowed_to_owner():
    calls = []
    def _herdmaster(now):
        calls.append("herdmaster")
        return [{"dedupe_key": "herdmaster:weekly-weight-evidence",
                 "specialist": "HERDMASTER"}]
    def _beacon(now):
        calls.append("beacon")
        return []
    result = collect_manager_candidate(now=NOW,
        dedupe_key="herdmaster:weekly-weight-evidence", specialist="HERDMASTER",
        collectors=(_beacon, _herdmaster))
    assert result["specialist"] == "HERDMASTER"
    assert calls == ["herdmaster"]


class _RootlineCursor:
    def __init__(self, rows):
        self.rows = iter(rows); self.commands = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params): self.commands.append((sql, params))
    def fetchone(self): return next(self.rows)


class _RootlineConnection:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.value


def _rootline_connector(monkeypatch, rows):
    from modules.oom_sakkie import manager_case_sources
    cursor = _RootlineCursor(rows)
    monkeypatch.setattr(manager_case_sources, "connect_bounded_read",
                        lambda: _RootlineConnection(cursor))
    return manager_case_sources, cursor


def _observation():
    return {"operating_date": "2026-08-17", "material_digest": "material-one",
        "result_id": "result-one", "evidence_generation": "generation-one",
        "delivery_state": "observation_only", "owner_user_id": "42", "chat_id": "42"}


def test_same_date_exact_provider_confirmed_plan_has_no_generic_unknown(monkeypatch):
    observed = datetime(2026, 8, 17, 9, 59, tzinfo=timezone.utc)
    observation = _observation()
    sources, cursor = _rootline_connector(monkeypatch, [
        ("OBS-1", observed, observation),
        ("DELIVERY-1", observed + timedelta(seconds=1), {
            **observation, "delivery_state": "delivered", "provider_message_id": "9001"}),
    ])
    assert sources._rootline(NOW) == []
    assert cursor.commands[1][1] == (
        "2026-08-17", "material-one", "result-one", "generation-one", "42", "42")


def test_current_observation_without_exact_delivery_returns_precise_exception(monkeypatch):
    observed = datetime(2026, 8, 17, 9, 59, tzinfo=timezone.utc)
    sources, _ = _rootline_connector(monkeypatch, [("OBS-1", observed, _observation()), None])
    case = sources._rootline(NOW)[0]
    assert case["unknowns"] == ["provider_confirmed_family_delivery_bound_to_current_plan"]
    assert "exact current-date material, result and generation" in case["summary"]
    assert "Automatic acquisition owner" in case["next_action"]
    assert "2026-08-17 12:05 SAST" in case["next_action"]


def test_missing_current_observation_names_acquisition_owner_and_retry(monkeypatch):
    sources, _ = _rootline_connector(monkeypatch, [None])
    case = sources._rootline(NOW)[0]
    assert case["unknowns"] == ["current_date_canonical_rootline_observation"]
    assert "existing Oom Sakkie ROOTLINE schedule" in case["next_action"]
    assert case["next_reassessment_at"] == (NOW + timedelta(minutes=5)).isoformat()
