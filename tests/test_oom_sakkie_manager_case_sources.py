from datetime import datetime, timedelta, timezone
from threading import Barrier

from modules.oom_sakkie.manager_case_sources import (
    _completed_bulk_batch_findings, _project_retained_herd_report_recovery,
    collect_manager_candidate, collect_manager_candidates)
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
    assert len(rows) == 2
    linda = next(row for row in rows if "litter-loss" in row["dedupe_key"])
    assert "provider_message:4052" in linda["evidence_refs"]
    assert "provider_message:4054" in linda["evidence_refs"]
    assert linda["unknowns"] == ["fresh_canonical_litter_loss_preview"]
    assert "repeat known facts" in linda["next_action"]
    mona = next(row for row in rows if "expired-farrowing" in row["dedupe_key"])
    assert mona["unknowns"] == ["fresh_canonical_farrowing_preview"]
    assert "replay" in mona["next_action"]


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


def test_mona_expired_projection_terminalizes_on_effect_or_newer_claim():
    expired = [{"mission_id": "OLD", "provider_message_id": "4051",
        "preview_payload": {"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}}]
    assert _project_retained_herd_report_recovery(NOW, [], expired,
        canonical_litters=[{"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}]) == []
    assert _project_retained_herd_report_recovery(NOW, [], expired,
        farrowing_claims=[{"mission_id": "NEW", "status": "active",
            "preview_payload": {"sow_pig_id": "MONA", "farrowing_date": "2026-08-26"}}]) == []


def test_retained_case_never_delivers_generic_manager_card_before_preview():
    case = {"dedupe_key": "herdmaster:retained-mortality:4050",
        "specialist": "HERDMASTER", "message_family": "retained_protected_recovery"}
    result = deliver_farm_manager_case(case)
    assert result["status"] == "retained_protected_repreview_unavailable"
    assert result["suppress_owner_delivery"] is True
    assert result["telegram_sends"] == 0


def test_completed_batch_projects_exact_pig_material_bcs_and_weight_findings():
    class Cursor:
        calls = 0
        def execute(self, *_args): self.calls += 1
        def fetchall(self):
            if self.calls == 1:
                return [("OBS-LOW", "PIG-A", NOW, NOW, {"body_condition_score": 2},
                    "BATCH-1", "DRAFT-1", "Teena", None),
                    ("OBS-OK", "PIG-B", NOW, NOW, {"body_condition_score": 3.5},
                    "BATCH-1", "DRAFT-1", "Bonnie", None)]
            return [("WEIGHT-1", "PIG-C", NOW.date(), 45, 40, NOW.date()-timedelta(days=7),
                     "BATCH-1", "Waki", None)]
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
