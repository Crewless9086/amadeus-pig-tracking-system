"""Synthetic production-shaped farm brief; collectors and delivery are inert."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from modules.oom_sakkie import daily_farm_manager as daily
from modules.oom_sakkie import farm_manager_runtime as runtime
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.farm_manager_loop import build_family_brief
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.general_manager_worker import ManagerCaseError, normalize_candidate
from modules.oom_sakkie.owner_response_composer import compose_manager_brief
from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery, daily_packet, snapshot

NOW = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)
OWNER = "OFFLINE-BRIEF-OWNER"
REASON = "Weekly irrigation demand, water and dry observed weather support one bounded gravity-fed segment."


def production_results(language="en"):
    source = snapshot()
    source["canonical"]["generated_at"] = NOW.isoformat()
    packet = daily_packet()
    packet["material_digest"] = "SYNTHETIC-BRIEF-73"
    packet["mortality"]["digest_changed"] = False
    weight = packet["weight"]
    weight["window"] = {"start": "2026-09-29", "end": "2026-09-30"}
    weight["current_snapshot"] = {"covered": 0, "eligible_tagged": 73, "status": "partial"}
    weight["missing_eligible_tagged"] = [
        {"pig_id": f"OFFLINE-WEIGHT-{n}", "tag": f"SYNTHETIC-TAG-{n:03d}"} for n in range(73)]
    source["daily_packet"] = packet
    herd = runtime._project_herdmaster_snapshot(source, None, OWNER, NOW, language)
    raw = {"success": True, "result_id": "SYNTHETIC-ROOTLINE", "generated_at": NOW.isoformat(),
        "recommendations": [{"subject": zone, "status": "Recommend", "reason": REASON}
                            for zone in ("B12345", "C12345")],
        "owner_brief": {"family_fact_needed": "No owner fact is required now."},
        "irrigation_lifecycle": {zone: {"contract_version": "rootline_zone_lifecycle.v1",
            "zone_id": zone, "state": "Completed", "reason": "record_completed",
            "next_action_owner": "ROOTLINE", "next_action": "reassess",
            "completion_evidence": {"zone_id": zone, "shutdown_verified": True,
                "objective_satisfied": True,
                "shutdown_evidence": {"authoritative": True, "state": "OFF"}}}
            for zone in ("B12345", "C12345")}}
    root = runtime._project_rootline_snapshot({"raw": raw}, NOW, language)
    return [herd, root]


def without_display(results):
    return [replace(result, work_items=tuple(replace(item, metadata={
        key: value for key, value in item.metadata.items() if key != "brief_facts"})
        for item in result.work_items)) for result in results]


def request(language="en"):
    return {"text": "Give me the farm brief.", "telegram_user_id": OWNER,
        "telegram_chat_id": OWNER, "provider_message_id": "SYNTHETIC-INBOUND-1",
        "provider_timestamp": NOW.isoformat(), "output_language": language,
        "semantic": {"domain": "manager_round", "language": language,
            "message_kind": "question", "confidence": 1.0,
            "read_query": {"kind": "farm_brief"}}}


def round_with(results, language="en", store=None):
    values = {result.specialist: result for result in results}
    loaders = {name: lambda name=name: values.get(name) or runtime._missing(name, NOW)
               for name in ("herdmaster", "rootline", "sam", "beacon")}
    rows = {}
    def memory(action, identity, payload):
        if action == "load":
            return rows.get(identity)
        created = identity not in rows
        rows.setdefault(identity, payload)
        return {"success": True, "created": created}
    result, code = runtime.handle_farm_manager_round(request(language),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store or memory)
    assert code == 200
    return result, rows, memory


@pytest.mark.parametrize("language", ["en", "af"])
def test_real_producers_to_farm_round_and_family_delivery_are_compact_and_truthful(language):
    results = production_results(language)
    result, stored, _ = round_with(results, language)
    brief = build_family_brief(results, now=NOW)
    assert result["success"] is True and result["action_count"] == 3 and result["question_count"] == 1
    answer = result["answer"]
    assert len(answer) < 1100
    assert answer.count("?") == 1 and answer.count(result["clarification_question"]) == 1
    assert "0/73" in answer and "73" in answer and "29–30 September 2026" in answer
    assert "22–26 " + ("Augustus" if language == "af" else "August") + " 2026" in answer
    assert "Mysikind" in answer and "Mona" in answer
    assert "SYNTHETIC-TAG-" not in answer and "OFFLINE-" not in answer
    assert "2026-09-29" not in answer and "2026-08-22" not in answer
    assert "Next:" not in answer and "bronwoorde" not in answer
    assert "unconfirmed" in answer if language == "en" else "onbevestig" in answer
    assert ("Controller OFF verified" if language == "en" else "Beheerder AF geverifieer") in answer
    assert "<b>B &amp; C " in answer
    assert ("Recommendation: one limited gravity-fed run" if language == "en" else
            "Aanbeveling: een beperkte swaartekragbeurt") in answer
    assert not any(text in answer.lower() for text in ("watering completed", "73 pigs today", "weigh every", "start irrigation"))
    # The case projection is bounded; the owning packet retains detailed rows.
    weights = next(item for item in brief.queue if item.dedupe_key == "herdmaster:weekly-weight-evidence")
    assert "SYNTHETIC-TAG-005 (+67)" in weights.next_action
    assert "SYNTHETIC-TAG-072" not in weights.next_action and len(weights.next_action) < 500
    assert result["clarification_question"] in {item.genuine_question for item in brief.queue}
    assert all(result[key] is False for key in runtime.ZERO_AUTHORITY)
    transport = []
    family_rows = {}
    def events(action, identity, payload):
        if action == "load":
            return [row for row in family_rows.values() if row.get("card_mission_id") == identity]
        created = identity not in family_rows
        family_rows.setdefault(identity, payload)
        return {"success": True, "created": created}
    def send(chat, text, **kwargs):
        transport.append((chat, text))
        return {"success": True, "telegram_message_id": "SYNTHETIC-CARD-1"}
    receipt = deliver_family_result(request(language), result, specialist="OOM_SAKKIE",
        mission_id=result["mission_id"], card_mission_id=result["card_mission_id"],
        event_store=events, sender=send)
    assert receipt["success"] is True and transport == [(OWNER, answer)]
    assert len(stored) == 1


@pytest.mark.parametrize("language", ["en", "af"])
def test_display_facts_do_not_change_daily_material_notifications_or_manager_candidates(monkeypatch, language):
    results = production_results(language)
    prior = without_display(results)
    old = daily.build_daily_management_packet(prior, now=NOW, language=language)
    new = daily.build_daily_management_packet(results, now=NOW, language=language)
    for key in ("material_digest", "notification_keys", "candidate_notification_keys", "question_binding", "all_tasks"):
        assert old[key] == new[key]
    from modules.pig_weights import herdmaster_purpose_work as reads
    from modules.pig_weights import pig_welfare_case_runtime as welfare
    monkeypatch.setattr(sources, "_configured_owner", lambda: OWNER)
    monkeypatch.setattr(sources, "_completed_bulk_batch_findings", lambda now: [])
    monkeypatch.setattr(sources, "_retained_litter_followup_candidates", lambda *args: [])
    monkeypatch.setattr(sources, "_purpose_review_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(welfare, "welfare_case_runtime_enabled", lambda: False)
    monkeypatch.setattr(reads, "load_purpose_work_snapshot", lambda **kwargs: {
        "snapshot_observed_at": NOW.isoformat(), "overview_rows": [], "litter_rows": []})
    def candidates(herd):
        monkeypatch.setattr(runtime, "_load_herdmaster", lambda *args: herd)
        return sources._herdmaster(NOW)
    before, after = candidates(prior[0]), candidates(results[0])
    assert before == after
    # The production collector keeps its own existing admission bound. A long
    # opaque tag list cannot be made newly admissible by presentation metadata.
    def admitted(row):
        try:
            return normalize_candidate(row, now=NOW)
        except ManagerCaseError as exc:
            return ("contained", str(exc))
    assert [admitted(row) for row in before] == [admitted(row) for row in after]
    assert any(isinstance(admitted(row), dict) for row in after)
    delivery = MemoryDelivery(monkeypatch)
    common = dict(owner_user_id=OWNER, chat_id=OWNER, litter_rows=(), now=NOW,
        language=language, deliver=delivery.deliver, replace_brief=delivery.replace)
    first = daily.run_daily_farm_manager(specialist_results=prior, **common)
    provider_before = deepcopy(delivery.sends)
    events_before = deepcopy(delivery.family_rows)
    replay = daily.run_daily_farm_manager(specialist_results=results, **common)
    assert first["success"] is True
    assert replay["status"] == "daily_manager_unchanged_silent"
    assert replay["telegram_sends"] == replay["telegram_edits"] == 0
    assert delivery.sends == provider_before and delivery.family_rows == events_before


def test_same_inbound_preserves_old_delivered_round_without_recomposition():
    current = production_results()
    old, rows, store = round_with(without_display(current))
    assert "SYNTHETIC-TAG-" in old["answer"]
    replay, _, _ = round_with(current, store=store)
    assert replay["status"] == "farm_manager_round_replay_suppressed"
    assert replay["answer"] == old["answer"] and replay["result_digest"] == old["result_digest"]
    assert replay["mission_id"] == old["mission_id"] and len(rows) == 1


@pytest.mark.parametrize("language", ["en", "af"])
def test_unknown_weight_counts_dates_and_nonverified_controller_remain_unknown_or_held(language):
    results = production_results(language)
    weight = next(item for item in results[0].work_items if item.metadata.get("brief_facts", {}).get("kind") == "weight_status_review")
    facts = {**weight.metadata["brief_facts"], "covered": None, "eligible": None,
             "status_checks": None, "window_start": None, "window_end": None}
    results[0] = replace(results[0], work_items=(replace(weight, metadata={**weight.metadata, "brief_facts": facts}),))
    root = runtime._project_rootline_snapshot({"raw": {"success": True, "result_id": "UNKNOWN",
        "generated_at": NOW.isoformat(), "recommendations": [{"subject": zone, "status": "Hold", "reason": ""}
            for zone in ("B12345", "C12345")]}}, NOW, language)
    answer = compose_manager_brief(build_family_brief([results[0], root], now=NOW), language=language)
    assert "0/0" not in answer and "OFF verified" not in answer and "AF geverifieer" not in answer
    assert ("unknown/unknown" if language == "en" else "onbekend/onbekend") in answer
    assert ("period unknown" if language == "en" else "tydperk onbekend") in answer


def test_foreign_or_malformed_display_metadata_uses_original_bounded_evidence():
    results = production_results()
    weights = next(item for item in results[0].work_items if item.metadata.get("brief_facts", {}).get("kind") == "weight_status_review")
    malformed = replace(weights, metadata={**weights.metadata, "brief_facts": {
        "kind": "weight_status_review", "covered": 99, "eligible": 73, "status_checks": 73}})
    foreign = replace(weights, metadata={**weights.metadata, "brief_facts": {
        "kind": "farrowing_outcome_unconfirmed", "labels": ["Forged animal"]}})
    for item in (malformed, foreign):
        result = replace(results[0], work_items=(item,))
        answer = compose_manager_brief(build_family_brief([result], now=NOW))
        assert "Weighing: 0 of 73 recorded" in answer and "99/73" not in answer
        assert "Forged animal" not in answer and len(answer) < 1200


def test_irrigation_mixed_states_and_foreign_off_receipt_are_not_grouped_as_verified():
    results = production_results()
    raw = {"success": True, "result_id": "MIXED", "generated_at": NOW.isoformat(),
        "recommendations": [{"subject": zone, "status": "Recommend", "reason": REASON} for zone in ("B12345", "C12345")],
        "irrigation_lifecycle": {zone: {"contract_version": "rootline_zone_lifecycle.v1", "zone_id": zone,
            "state": "Completed", "next_action_owner": "ROOTLINE", "completion_evidence": {
                "zone_id": "B12345", "shutdown_verified": True, "objective_satisfied": True,
                "shutdown_evidence": {"authoritative": True, "state": "OFF"}}} for zone in ("B12345", "C12345")}}
    root = runtime._project_rootline_snapshot({"raw": raw}, NOW)
    answer = compose_manager_brief(build_family_brief([root], now=NOW))
    assert "B camp:</b> Controller OFF verified" in answer
    assert "C camp:</b> Not running" in answer and "B &amp; C" not in answer
    assert "Recommendation:" in answer and "watering completed" not in answer


@pytest.mark.parametrize("status", ["Hold", "Needs Data", "Do Not Run", "Unknown"])
def test_old_support_reason_never_upgrades_a_current_hold_to_a_recommendation(status):
    root = runtime._project_rootline_snapshot({"raw": {"success": True, "result_id": "HELD",
        "generated_at": NOW.isoformat(), "recommendations": [{"subject": zone,
            "status": status, "reason": REASON} for zone in ("B12345", "C12345")]}}, NOW)
    answer = compose_manager_brief(build_family_brief([root], now=NOW))
    assert "Recommendation:" not in answer and "Not running" in answer
    assert "Controller OFF verified" not in answer
