from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
import json
import time
import pytest

from modules.oom_sakkie.manager_case_sources import (
    _completed_bulk_batch_findings, _project_retained_herd_report_recovery,
    collect_manager_candidate, collect_manager_candidates,
    collect_manager_refresh_snapshot)
from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_retained_anton_reports_become_automatic_recovery_cases_without_replay():
    health = [
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "4052",
         "owner_text_verbatim": "Linds 3 kleintjies dood"},
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "4054",
         "owner_text_verbatim": "Linda kleintjies dood op 26 Aug"},
    ]
    expired = [{"mission_id": "OOM-MONA", "provider_message_id": "4051",
        "preview_payload": {"sow_pig_id": "PIG-MONA"}}]
    rows = _project_retained_herd_report_recovery(NOW, health, expired)
    assert len(rows) == 1
    linda = next(row for row in rows if "litter-loss" in row["dedupe_key"])
    assert "provider_message:4052" in linda["evidence_refs"]
    assert "provider_message:4054" in linda["evidence_refs"]
    assert linda["unknowns"] == ["fresh_canonical_litter_loss_preview"]
    assert "repeat known facts" in linda["next_action"]
    assert not any("expired-farrowing" in row["dedupe_key"] for row in rows)


def test_retained_recovery_never_cross_groups_principal_or_chat():
    health = [
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "1",
         "owner_text_verbatim": "Linda 3 kleintjies dood op 26 Aug"},
        {"owner_user_id": "OTHER", "chat_id": "OTHER", "provider_message_id": "2",
         "owner_text_verbatim": "Linda 3 kleintjies dood op 26 Aug"},
        {"owner_user_id": "ANTON", "chat_id": "GROUP", "provider_message_id": "3",
         "owner_text_verbatim": "Linda 3 kleintjies dood op 26 Aug"},
    ]
    rows = _project_retained_herd_report_recovery(NOW, health, [])
    assert len(rows) == 2
    assert all("provider_message:3" not in row["evidence_refs"] for row in rows)


def test_linda_recovery_partitions_incident_dates():
    health = [
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "1",
         "owner_text_verbatim": "Linda 3 kleintjies dood op 25 Aug"},
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "2",
         "owner_text_verbatim": "Linda 3 kleintjies dood op 26 Aug"},
    ]
    rows = _project_retained_herd_report_recovery(NOW, health, [])
    assert len(rows) == 2
    assert {next(ref for ref in row["evidence_refs"] if ref.startswith("incident_date:"))
            for row in rows} == {"incident_date:2026-08-25", "incident_date:2026-08-26"}


def test_pig_146_projects_but_terminal_138_is_suppressed():
    health = [
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "4050",
         "owner_text_verbatim": "Vark nr 146 dood op 23 Aug"},
        {"owner_user_id": "ANTON", "chat_id": "ANTON", "provider_message_id": "4057",
         "owner_text_verbatim": "Vark nr 138 dood op 26 Aug"},
    ]
    pigs = [{"pig_id": "P146", "tag_number": "146", "status": "Active", "on_farm": True},
            {"pig_id": "P138", "tag_number": "138", "status": "Dead", "on_farm": False}]
    rows = _project_retained_herd_report_recovery(NOW, health, [], canonical_pigs=pigs)
    assert len(rows) == 1
    assert rows[0]["dedupe_key"] == "herdmaster:retained-mortality:4050"
    assert "tag:146" in rows[0]["evidence_refs"]


def test_generic_health_projection_never_manufactures_a_farrowing_handoff():
    expired = [{"mission_id": "OLD", "provider_message_id": "4051",
        "preview_payload": {"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}}]
    assert _project_retained_herd_report_recovery(NOW, [], expired,
        canonical_litters=[{"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}]) == []
    assert _project_retained_herd_report_recovery(NOW, [], expired,
        farrowing_claims=[{"mission_id": "NEW", "status": "active",
            "preview_card_message_id": "CARD", "delivery_state": "delivery_confirmed",
            "preview_payload": {"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}}]) == []
    rows = _project_retained_herd_report_recovery(NOW, [], expired,
        farrowing_claims=[{"mission_id": "NEW", "status": "active",
            "preview_card_message_id": None, "delivery_state": "claim_created",
            "preview_payload": {"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}}])
    assert rows == []  # Only the exact durable farrowing source collector owns this family.


def test_retained_case_never_delivers_generic_manager_card_before_preview():
    case = {"dedupe_key": "herdmaster:retained-mortality:4050",
        "specialist": "HERDMASTER", "message_family": "retained_protected_recovery"}
    result = deliver_farm_manager_case(case, retained_recovery=None)
    assert result["status"] == "retained_protected_repreview_unavailable"
    assert result["suppress_owner_delivery"] is True
    assert result["telegram_sends"] == 0


def test_retained_containment_preserves_exact_failure_without_delivery():
    case = {"dedupe_key": "herdmaster:retained-mortality:4050",
        "specialist": "HERDMASTER", "message_family": "retained_protected_recovery"}
    result = deliver_farm_manager_case(case, retained_recovery=lambda _case: {
        "success": False, "status": "retained_mortality_removed_disposal_required",
        "suppress_owner_delivery": True, "telegram_sends": 0})
    assert result["status"] == "retained_mortality_removed_disposal_required"
    assert result["failure_kind"] == "retained_mortality_removed_disposal_required"
    assert result["suppress_owner_delivery"] is True


def test_retained_message_family_survives_normalization_contract():
    from modules.oom_sakkie.general_manager_worker import normalize_candidate
    raw = {"dedupe_key": "herdmaster:retained-mortality:4050",
        "specialist": "HERDMASTER", "urgency": "urgent",
        "evidence_refs": ["provider_message:4050"],
        "unknowns": ["fresh_canonical_mortality_preview"],
        "summary": "Retained mortality.", "next_action": "Build preview.",
        "next_reassessment_at": NOW.isoformat(),
        "message_family": "retained_protected_recovery"}
    normalized = normalize_candidate(raw, now=NOW)
    assert normalized["message_family"] == "retained_protected_recovery"
    assert "manager_message_family:retained_protected_recovery" in normalized["evidence_refs"]


def test_completed_batch_projects_exact_pig_material_bcs_and_weight_findings():
    class Cursor:
        calls = 0
        def execute(self, *_args): self.calls += 1
        def fetchall(self):
            if self.calls == 1:
                return [("OBS-LOW", "PIG-A", NOW, NOW, {"body_condition_score": 2},
                    "BATCH-1", "DRAFT-1", "Teena", None, None),
                    ("OBS-OK", "PIG-B", NOW, NOW, {"body_condition_score": 3.5},
                    "BATCH-1", "DRAFT-1", "Bonnie", None, None)]
            return [("WEIGHT-1", "PIG-C", NOW.date(), 45, 40, NOW.date()-timedelta(days=7),
                     "BATCH-1", "Waki", None, NOW)]
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class Connection:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    rows = _completed_bulk_batch_findings(NOW, connect=lambda: Connection())
    assert [row["dedupe_key"] for row in rows] == [
        "herdmaster:bulk-condition:PIG-A", "herdmaster:bulk-condition:PIG-B",
        "herdmaster:bulk-weight-change:PIG-C"]
    assert rows[0]["evidence_refs"][:4] == [
        "pig:PIG-A", "batch:BATCH-1", "draft:DRAFT-1", "observation:OBS-LOW"]
    assert rows[0].get("terminal_state") is None
    assert rows[1]["terminal_state"] == "completed"
    assert "+12.5%" in rows[2]["summary"]


def test_completed_batch_query_is_read_only_and_heat_free():
    source = __import__("inspect").getsource(_completed_bulk_batch_findings)
    assert "insert " not in source.casefold() and "update " not in source.casefold()
    assert "heat" not in source.casefold()
    assert source.count("row_number() over(partition by") == 2
    assert source.count("where position=1") == 2


def test_completed_batch_queries_select_one_deterministic_latest_row_per_pig():
    statements = []
    class Cursor:
        calls = 0
        def execute(self, sql, _params): statements.append(sql); self.calls += 1
        def fetchall(self): return []
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class Connection:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    assert _completed_bulk_batch_findings(NOW, connect=lambda: Connection()) == []
    assert "observed_at desc,recorded_at desc,observation_event_id desc" in statements[0]
    assert "weight_date desc,h.created_at desc,h.weight_event_id desc" in statements[1]
    assert all("where position=1" in statement for statement in statements)


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


def test_multiple_collectors_run_concurrently_but_preserve_declared_order():
    barrier = Barrier(2)
    def first(_now):
        barrier.wait(timeout=1)
        return [{"dedupe_key": "rootline:first", "specialist": "ROOTLINE"}]
    def second(_now):
        barrier.wait(timeout=1)
        return [{"dedupe_key": "herdmaster:second", "specialist": "HERDMASTER"}]

    result = collect_manager_candidates(now=NOW, collectors=(first, second))
    assert [row["dedupe_key"] for row in result] == [
        "rootline:first", "herdmaster:second"]


def test_slow_collector_becomes_owned_timeout_without_hiding_fast_result(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    release = Event()
    def slow(_now):
        release.wait(timeout=1)
        return [{"dedupe_key": "rootline:late", "specialist": "ROOTLINE"}]
    def fast(_now):
        return [{"dedupe_key": "herdmaster:current", "specialist": "HERDMASTER"}]
    monkeypatch.setattr(sources, "COLLECTOR_DEADLINE_SECONDS", 0.02)

    started = time.monotonic()
    result = collect_manager_candidates(now=NOW, collectors=(slow, fast))
    elapsed = time.monotonic() - started
    release.set()

    assert elapsed < 0.2
    assert result[0]["dedupe_key"] == "runtime:collector:slow"
    assert result[0]["evidence_refs"] == ["collector:slow:TimeoutError"]
    assert result[1] == {
        "dedupe_key": "herdmaster:current", "specialist": "HERDMASTER"}


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


def test_claim_refresh_reads_each_owning_specialist_once_for_many_cases():
    calls = []
    def _herdmaster(now):
        calls.append(("herdmaster", now))
        return [
            {"dedupe_key": "herdmaster:first", "specialist": "HERDMASTER"},
            {"dedupe_key": "herdmaster:second", "specialist": "HERDMASTER"},
            {"dedupe_key": "herdmaster:unclaimed", "specialist": "HERDMASTER"},
        ]
    def _beacon(now):
        calls.append(("beacon", now))
        return [{"dedupe_key": "beacon:current", "specialist": "BEACON"}]
    cases = [
        {"dedupe_key": "herdmaster:first", "specialist": "HERDMASTER"},
        {"dedupe_key": "herdmaster:second", "specialist": "HERDMASTER"},
        {"dedupe_key": "beacon:current", "specialist": "BEACON"},
    ]

    snapshot = collect_manager_refresh_snapshot(
        now=NOW, cases=cases, collectors=(_beacon, _herdmaster))

    assert set(snapshot) == {
        ("herdmaster:first", "HERDMASTER"),
        ("herdmaster:second", "HERDMASTER"),
        ("beacon:current", "BEACON"),
    }
    assert sorted(name for name, _ in calls) == ["beacon", "herdmaster"]


def test_beacon_candidate_identity_uses_only_consumed_campaign_evidence(monkeypatch):
    """New SAM audit rows must not manufacture a BEACON generation."""
    from modules.oom_sakkie import manager_case_sources as sources

    result = {"success": True, "result_digest": "a" * 64,
              "proposal": {"packet_id": "BEACON-ENQUIRY-STABLE"}}
    monkeypatch.setattr(
        "modules.oom_sakkie.beacon_request_runtime.build_scheduled_sale_ready_stock_result",
        lambda: result)
    monkeypatch.setattr(sources, "connect_bounded_read", lambda: (_ for _ in ()).throw(
        AssertionError("unconsumed SAM review identity must not be queried")))

    first = sources._beacon(NOW)[0]
    refreshed = sources._beacon(NOW + timedelta(seconds=1))[0]

    assert first["evidence_refs"] == [
        "beacon_result:" + "a" * 64, "packet:BEACON-ENQUIRY-STABLE"]
    assert refreshed["evidence_refs"] == first["evidence_refs"]


def test_beacon_material_proposal_change_changes_candidate_identity_once(monkeypatch):
    """A genuine campaign input change remains a successor-generation trigger."""
    from modules.oom_sakkie import manager_case_sources as sources

    results = iter((
        {"success": True, "result_digest": "a" * 64,
         "proposal": {"packet_id": "BEACON-ENQUIRY-ONE"}},
        {"success": True, "result_digest": "b" * 64,
         "proposal": {"packet_id": "BEACON-ENQUIRY-TWO"}},
    ))
    monkeypatch.setattr(
        "modules.oom_sakkie.beacon_request_runtime.build_scheduled_sale_ready_stock_result",
        lambda: next(results))

    first = sources._beacon(NOW)[0]
    changed = sources._beacon(NOW + timedelta(seconds=1))[0]

    assert first["dedupe_key"] == changed["dedupe_key"] == \
        "beacon:current-sale-opportunity"
    assert first["evidence_refs"] != changed["evidence_refs"]


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



def test_refresh_collector_error_is_not_a_missing_candidate_and_keeps_sibling():
    from modules.oom_sakkie.manager_case_sources import ManagerCollectorRefreshError
    def _herdmaster(now):
        raise RuntimeError("private connection detail must not escape")
    def _beacon(now):
        return [{"dedupe_key": "beacon:current", "specialist": "BEACON"}]
    cases = [{"dedupe_key": "herdmaster:bulk-weight-change:PIG-A", "specialist": "HERDMASTER"},
             {"dedupe_key": "beacon:current", "specialist": "BEACON"}]
    result = collect_manager_refresh_snapshot(now=NOW, cases=cases,
        collectors=(_herdmaster, _beacon))
    error = result[(cases[0]["dedupe_key"], "HERDMASTER")]
    assert isinstance(error, ManagerCollectorRefreshError)
    assert error.collector_failure_kind == "collector:herdmaster:RuntimeError"
    assert "private" not in str(error)
    assert result[("beacon:current", "BEACON")] == {"dedupe_key": "beacon:current", "specialist": "BEACON"}


def test_refresh_successful_absence_remains_unresolved_not_collector_failure():
    def _herdmaster(now):
        return []
    case = {"dedupe_key": "herdmaster:bulk-weight-change:PIG-A", "specialist": "HERDMASTER"}
    assert collect_manager_refresh_snapshot(now=NOW, cases=[case], collectors=(_herdmaster,)) == {}
    assert collect_manager_candidate(now=NOW, **case, collectors=(_herdmaster,)) is None


def test_single_refresh_preserves_sanitized_owning_collector_failure():
    import pytest
    from modules.oom_sakkie.manager_case_sources import ManagerCollectorRefreshError
    def _herdmaster(now):
        raise TimeoutError("private timeout details")
    with pytest.raises(ManagerCollectorRefreshError) as failure:
        collect_manager_candidate(now=NOW, dedupe_key="herdmaster:bulk-weight-change:PIG-A",
            specialist="HERDMASTER", collectors=(_herdmaster,))
    assert str(failure.value) == "collector:herdmaster:TimeoutError"


def test_manual_current_evidence_has_no_invented_batch_identity_or_owner_send(monkeypatch):
    class Cursor:
        calls = 0
        def execute(self, *_args): self.calls += 1
        def fetchall(self):
            if self.calls == 1:
                return [("OBS-MANUAL", "PIG-A", NOW, NOW, {"body_condition_score": 3},
                         None, None, "A", None, ["OBS-PREVIOUS", "OBS-ORIGINAL"])]
            return [("WEIGHT-MANUAL", "PIG-A", NOW.date(), 51, 50, NOW.date()-timedelta(days=7),
                     None, "A", None, NOW)]
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class Connection:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "42")
    rows = _completed_bulk_batch_findings(NOW, connect=Connection)
    assert len(rows) == 2
    assert "supersedes_observation:OBS-PREVIOUS" in rows[0]["evidence_refs"]
    assert "supersedes_observation:OBS-ORIGINAL" in rows[0]["evidence_refs"]
    assert f"weight_recorded:{NOW.isoformat()}" in rows[1]["evidence_refs"]
    for row in rows:
        assert row["terminal_state"] == "completed"
        assert not any(ref.startswith(("batch:", "draft:")) for ref in row["evidence_refs"])
        outcome = deliver_farm_manager_case({**row, "case_id": "OOM-CASE-TEST", "generation": 2},
            deliver=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale send")))
        assert outcome["telegram_sends"] == 0


def _report_recovery_fixture(*, cases=None, recent=(), reports=None, lifecycle=None, claims=(),
                             targeted=False, queries=None):
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import Connection, report
    rows = reports if reports is not None else [report()]
    if cases is None:
        cases = [("herdmaster:retained-mortality:101",
                  ["provider_message:101", "pig:P27", "tag:27"], "exception")]
    responses = [cases]
    if not targeted:
        responses.append([])  # No legacy farrowing originals in this health fixture.
        responses.append([(value,) for value in recent])
    if recent or cases:
        responses += [[(row,) for row in rows],
                      [(row,) for row in (rows if lifecycle is None else lifecycle)], list(claims)]
    responses += [[("P27", "27", "Active", True)]]
    def connect():
        connection = Connection(responses)
        cursor = connection.cursor()
        execute = cursor.execute
        def record(query, params=None):
            if query.startswith(("set transaction", "select set_config(")):
                return
            if queries is not None:
                queries.append((query, params))
            execute(query, params)
        cursor.execute = record
        connection.cursor = lambda: cursor
        return connection
    return connect


def test_old_exact_retained_report_keeps_key_and_stable_binding_across_refresh():
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from modules.oom_sakkie.general_manager_worker import normalize_candidate
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    first = _retained_herd_report_recovery_candidates(now, connect=_report_recovery_fixture())
    assert len(first) == 1 and first[0]["dedupe_key"] == "herdmaster:retained-mortality:101"
    bindings = [ref for ref in first[0]["evidence_refs"] if ref.startswith("retained_report_binding:")]
    assert len(bindings) == 1
    retained = [(first[0]["dedupe_key"], first[0]["evidence_refs"], "exception")]
    replay = _retained_herd_report_recovery_candidates(now + timedelta(days=30),
        connect=_report_recovery_fixture(cases=retained))
    assert replay[0]["evidence_refs"] == first[0]["evidence_refs"]
    assert normalize_candidate(first[0], now=now)["evidence_digest"] == normalize_candidate(replay[0], now=now)["evidence_digest"]


def test_bound_retained_case_rejects_unique_replacement_principal_or_mission():
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    refs = ["provider_message:101", "pig:P27", "tag:27", retained_report_binding([report()])]
    cases = [("herdmaster:retained-mortality:101", refs, "exception")]
    for changed in (report(owner_user_id="99", chat_id="99"), report(mission="OTHER")):
        assert _retained_herd_report_recovery_candidates(NOW,
            connect=_report_recovery_fixture(cases=cases, reports=[changed])) == []


def test_closed_retained_cases_and_changed_refs_are_not_reopened_by_recent_intake():
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    for status, refs in (("completed", ["provider_message:101", "pig:P27", "tag:27"]),
                         ("contained", ["provider_message:101", "pig:P27", "tag:27"]),
                         ("exception", ["provider_message:101", "pig:FOREIGN", "tag:27"])):
        cases = [("herdmaster:retained-mortality:101", refs, status)]
        assert _retained_herd_report_recovery_candidates(NOW,
            connect=_report_recovery_fixture(cases=cases, recent=["101"])) == []


def test_litter_retained_membership_is_exact_not_regrouped_with_new_same_day_report():
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    reports = [report("201", "REPORT-201", owner_text_verbatim="Linda 2 kleintjies dood"),
               report("202", "REPORT-202", owner_text_verbatim="Linda kleintjies dood op 19 Aug"),
               report("200", "REPORT-200", owner_text_verbatim="Linda 2 kleintjies dood op 19 Aug")]
    key = "herdmaster:retained-litter-loss:201:2026-08-19"
    refs = ["provider_message:201", "provider_message:202", "incident_date:2026-08-19"]
    cases = [(key, refs, "exception")]
    result = _retained_herd_report_recovery_candidates(NOW,
        connect=_report_recovery_fixture(cases=cases, recent=["200"], reports=reports))
    retained = next(row for row in result if row["dedupe_key"] == key)
    assert {ref for ref in retained["evidence_refs"] if ref.startswith("provider_message:")} == {
        "provider_message:201", "provider_message:202"}
    for invalid in (reports[:1], [reports[0], {**reports[1],
            "owner_text_verbatim": "Linda kleintjies dood op 20 Aug"}]):
        assert _retained_herd_report_recovery_candidates(NOW,
            connect=_report_recovery_fixture(cases=cases, reports=invalid)) == []


def test_retained_refresh_reuses_canonical_recovery_without_full_herd_overview(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    case = {"dedupe_key": "herdmaster:retained-mortality:5097", "specialist": "HERDMASTER"}
    sibling = {"dedupe_key": "herdmaster:retained-litter-loss:4052:2026-08-04",
               "specialist": "HERDMASTER"}
    calls = []
    def retained(now, *, claimed_cases):
        calls.append((now, claimed_cases))
        return [case, sibling]
    def forbidden(_now):
        raise AssertionError("unrelated herd overview must not run")
    monkeypatch.setattr(sources, "_herdmaster", forbidden)
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", retained)
    assert sources.collect_manager_refresh_snapshot(now=NOW, cases=[case]) == {
        (case["dedupe_key"], "HERDMASTER"): case}
    assert calls == [(NOW, (case,))]
    # Canonical absence cannot reuse the old candidate or invent completion.
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", lambda now, **kwargs: [])
    assert sources.collect_manager_refresh_snapshot(now=NOW, cases=[case]) == {}


def test_retained_refresh_failure_is_contained_without_stale_fallback(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    case = {"dedupe_key": "herdmaster:retained-mortality:5097", "specialist": "HERDMASTER"}
    def failing(now, *, claimed_cases):
        raise TimeoutError("private connection details")
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", failing)
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=[case])
    error = result[(case["dedupe_key"], "HERDMASTER")]
    assert isinstance(error, sources.ManagerCollectorRefreshError)
    assert str(error) == "collector:herdmaster:TimeoutError"


def test_retained_refresh_does_not_accept_wrong_specialist(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    case = {"dedupe_key": "herdmaster:retained-mortality:5097", "specialist": "ROOTLINE"}
    def forbidden(now):
        raise AssertionError("wrong specialist cannot use retained shortcut")
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", forbidden)
    monkeypatch.setattr(sources, "_herdmaster", lambda now: [])
    assert sources.collect_manager_refresh_snapshot(now=NOW, cases=[case]) == {}


def _bound_retained_case():
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    return {"case_id": "CANONICAL-101", "dedupe_key": "herdmaster:retained-mortality:101",
            "specialist": "HERDMASTER", "evidence_refs": ["provider_message:101", "pig:P27",
                "tag:27", retained_report_binding([report()])]}


def test_retained_refresh_runs_real_scoped_collector_and_ignores_caller_evidence(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    canonical = _bound_retained_case()
    cases = [(canonical["dedupe_key"], canonical["evidence_refs"], "delegated")]
    expected = sources._retained_herd_report_recovery_candidates(NOW,
        connect=_report_recovery_fixture(cases=cases))
    queries = []
    monkeypatch.setattr(sources, "connect_bounded_read",
        _report_recovery_fixture(cases=cases, targeted=True, queries=queries))
    requested = {**canonical, "evidence_refs": ["provider_message:999", "pig:WRONG"],
                 "status": "completed"}
    snapshot = sources.collect_manager_refresh_snapshot(now=NOW, cases=[requested])
    assert list(snapshot.values()) == expected
    assert len(queries) == 5
    selection, params = queries[0]
    assert "(m.case_id,m.dedupe_key) in" in selection
    assert "m.specialist='HERDMASTER'" in selection
    assert json.loads(params[0]) == [{"case_id": canonical["case_id"],
                                    "dedupe_key": canonical["dedupe_key"]}]
    assert queries[1][1][1] == ["101"]
    sql = "\n".join(query for query, _ in queries)
    assert "created_at >=" not in sql and "herdmaster_record_farrowing_litter" not in sql
    assert "from public.litters" not in sql
    assert queries[-1][0] == "select pig_id,tag_number,status,on_farm from public.current_canonical_pigs limit 5001"


@pytest.mark.parametrize("change", ["cancelled", "changed_text", "principal", "mission", "source_binding",
                                   "missing_binding", "wrong_target", "wrong_provider"])
def test_targeted_retained_refresh_keeps_canonical_source_and_identity_containment(change):
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    case = _bound_retained_case()
    original = report()
    rows, lifecycle = [original], [original]
    refs = list(case["evidence_refs"])
    if change == "cancelled":
        lifecycle = [{**original, "provider_message_id": "901", "status": "contained"}, original]
    elif change == "changed_text":
        lifecycle = [{**original, "owner_text_verbatim": "Changed original report"}, original]
    elif change == "principal":
        rows = lifecycle = [report(owner_user_id="99", chat_id="99")]
    elif change == "mission":
        rows = lifecycle = [report(mission="OTHER")]
    elif change == "source_binding":
        refs[-1] = "retained_report_binding:" + "0" * 64
    elif change == "missing_binding":
        refs.pop()
    elif change == "wrong_target":
        refs[1] = "pig:WRONG"
    elif change == "wrong_provider":
        refs[0] = "provider_message:999"
    result = _retained_herd_report_recovery_candidates(NOW, claimed_cases=[case],
        connect=_report_recovery_fixture(cases=[(case["dedupe_key"], refs, "delegated")],
            reports=rows, lifecycle=lifecycle, targeted=True))
    assert result == []


@pytest.mark.parametrize("status,refs", [("completed", []), ("contained", []),
                                      ("delegated", None), ("delegated", "provider_message:101"),
                                      ("delegated", [None])])
def test_targeted_retained_refresh_stops_after_terminal_or_malformed_canonical_case(status, refs):
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    case = _bound_retained_case()
    queries = []
    assert _retained_herd_report_recovery_candidates(NOW, claimed_cases=[case],
        connect=_report_recovery_fixture(cases=[(case["dedupe_key"], refs, status)],
            targeted=True, queries=queries)) == []
    assert len(queries) == 1


@pytest.mark.parametrize("case", [None, {}, {"case_id": "", "dedupe_key": "herdmaster:retained-mortality:101",
    "specialist": "HERDMASTER"}, {"case_id": "CANONICAL-101", "dedupe_key": "herdmaster:retained-mortality:101",
    "specialist": "ROOTLINE"}])
def test_targeted_retained_refresh_invalid_selector_never_starts_acquisition(case):
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    def forbidden():
        pytest.fail("invalid identity must fail before canonical acquisition")
    with pytest.raises(ValueError, match="retained_refresh_case_identity_invalid"):
        _retained_herd_report_recovery_candidates(NOW, claimed_cases=[case], connect=forbidden)
    assert _retained_herd_report_recovery_candidates(NOW, claimed_cases=[], connect=forbidden) == []


def test_targeted_retained_litter_refresh_preserves_exact_membership_and_projection():
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    reports = [report("201", "REPORT-201", owner_text_verbatim="Linda 2 kleintjies dood"),
               report("202", "REPORT-202", owner_text_verbatim="Linda kleintjies dood op 19 Aug")]
    case = {"case_id": "CANONICAL-LITTER", "specialist": "HERDMASTER",
            "dedupe_key": "herdmaster:retained-litter-loss:201:2026-08-19"}
    refs = ["provider_message:201", "provider_message:202", "incident_date:2026-08-19",
            retained_report_binding(reports)]
    cases = [(case["dedupe_key"], refs, "delegated")]
    discovery = _retained_herd_report_recovery_candidates(NOW,
        connect=_report_recovery_fixture(cases=cases, reports=reports))
    queries = []
    refreshed = _retained_herd_report_recovery_candidates(NOW, claimed_cases=[case],
        connect=_report_recovery_fixture(cases=cases, reports=reports, targeted=True, queries=queries))
    assert len(refreshed) == 1 and refreshed == discovery
    assert queries[1][1][1] == ["201", "202"]


@pytest.mark.parametrize("reverse", [False, True])
def test_current_key_wins_before_reconcile_independent_of_collector_order(reverse):
    current = {"dedupe_key": "herdmaster:herdmaster:PIG-A", "specialist": "HERDMASTER"}
    retired = {**current, "message_family": "herdmaster_disposition", "terminal_state": "completed"}
    readers = (lambda now: [current], lambda now: [retired])
    assert collect_manager_candidates(now=NOW, collectors=readers[::-1] if reverse else readers) == [current]


@pytest.mark.parametrize("status,on_farm,suppressed", [
    ("Sold", "No", True), ("Dead", False, True), ("Culled", "No", True),
    ("Sold", "Yes", False), ("Active", "No", False), ("Unknown", "No", False),
    ("Sold", "Unknown", False), ("Sold", None, False)])
def test_withdrawal_producer_only_retires_conclusive_departure(monkeypatch, status, on_farm, suppressed):
    from types import SimpleNamespace
    from modules.oom_sakkie import manager_case_sources as sources
    monkeypatch.setattr(sources, "_configured_owner", lambda: "42")
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *args: SimpleNamespace(work_items=()))
    monkeypatch.setattr(sources, "_completed_bulk_batch_findings", lambda now: [])
    monkeypatch.setattr(sources, "_retained_litter_followup_candidates", lambda *args: [])
    monkeypatch.setattr(sources, "_purpose_review_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("modules.pig_weights.pig_welfare_case_runtime.welfare_case_runtime_enabled", lambda: False)
    row = {"Pig_ID": "PIG-151", "Tag_Number": "151", "Status": status, "On_Farm": on_farm,
           "Withdrawal_Evidence_State": "unknown"}
    snapshot = {"overview_rows": [row]}
    monkeypatch.setattr("modules.pig_weights.herdmaster_purpose_work.load_purpose_work_snapshot",
                        lambda **kwargs: snapshot)
    key = "herdmaster:pig-151-withdrawal-sales"
    assert (key not in [v["dedupe_key"] for v in sources._herdmaster(NOW)]) is suppressed
    # Another canonical identity with the same tag makes suppression unproven.
    snapshot["overview_rows"].append({**row, "Pig_ID": "PIG-OTHER"})
    assert key in [v["dedupe_key"] for v in sources._herdmaster(NOW)]


def test_bounded_advisory_failure_is_not_missing_or_poisoned_by_broad_failure(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    case = {"case_id": "A", "dedupe_key": "herdmaster:herdmaster:PIG-A", "specialist": "HERDMASTER"}
    def fail(*args, **kwargs):
        raise TimeoutError("private details")
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_case_disposition.collect_advisory_refresh", fail)
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=[case])
    assert str(result[(case["dedupe_key"], "HERDMASTER")]) == "collector:herdmaster_advisories:TimeoutError"
    with pytest.raises(sources.ManagerCollectorRefreshError, match="herdmaster_advisories:TimeoutError"):
        sources.collect_manager_candidate(now=NOW, dedupe_key=case["dedupe_key"], specialist="HERDMASTER")


def test_retained_total_budget_includes_identity_reassessment(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    source = report(preview={"evaluator": {"status": "identity_required", "event_family": "unknown",
        "identity": {"resolved": False}}})
    case = _bound_retained_case()
    refs = ["provider_message:101", "pig:P27", "tag:27", retained_report_binding([source])]
    elapsed = [100.0]
    monkeypatch.setattr(sources.time, "monotonic", lambda: elapsed[0])
    connector = _report_recovery_fixture(cases=[(case["dedupe_key"], refs, "delegated")],
                                        reports=[source], targeted=True)
    def connect():
        elapsed[0] += 4
        return connector()
    def evidence(**kwargs):
        assert kwargs["deadline_seconds"] == 5
        elapsed[0] += 6
        return {}
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence", evidence)
    with pytest.raises(TimeoutError, match="retained_report_read_deadline"):
        sources._retained_herd_report_recovery_candidates(NOW, connect=connect, claimed_cases=[case])


def test_single_retained_refresh_preserves_owning_failure(monkeypatch):
    from modules.oom_sakkie import manager_case_sources as sources
    def failing(*args, **kwargs):
        raise TimeoutError("private details")
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", failing)
    with pytest.raises(sources.ManagerCollectorRefreshError, match="herdmaster_retained:TimeoutError"):
        sources.collect_manager_candidate(now=NOW, dedupe_key="herdmaster:retained-mortality:101", specialist="HERDMASTER")
