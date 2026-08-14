from datetime import datetime, timezone
import time

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState,
)
from modules.oom_sakkie.farm_manager_runtime import handle_farm_manager_round, is_farm_manager_round
from modules.oom_sakkie import farm_manager_runtime
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

NOW = datetime(2026, 8, 3, 6, 35, tzinfo=timezone.utc)
OWNER = "5721652188"
EXACT = ("Morning Oom Sakkie. What needs our attention on the farm today? We are weighing all the pigs today "
         "and want to get the matings going. Please give us today’s irrigation plan, breeding suggestions, "
         "weighing priorities, welfare checks and anything else we should look out for.")


def specialist(name, state=WorkState.DUE_TODAY, value=50, question="", availability=SpecialistAvailability.AVAILABLE):
    p = Provenance(name, name + "-result", (name + ":canonical",), NOW, 1.0)
    item = SpecialistWorkItem(name + "-item", name + ":daily", "herd" if name == "herdmaster" else "water_energy",
        name.upper() + " priority", "Current canonical evidence supports this priority.",
        "Specialist reassesses when new evidence arrives.", "charl", state, Authority.ADVISORY, p,
        business_value=value, genuine_question=question, question_for="charl" if question else "")
    return SpecialistResult(name, name + "-result", NOW, availability, work_items=(item,))


def parsed(text=EXACT):
    return {"text": text, "telegram_user_id": OWNER, "telegram_chat_id": OWNER,
            "provider_message_id": "3192", "provider_timestamp": "2026-08-03T05:15:11+00:00"}


def memory_store():
    rows = {}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        if identity in rows: return {"success": True, "created": False}
        rows[identity] = payload
        return {"success": True, "created": True}
    return store


def test_exact_multidomain_request_outranks_legacy_irrigation_intent():
    assert is_farm_manager_round(EXACT)
    assert is_farm_manager_round("Give today's irrigation and breeding priorities")
    assert not is_farm_manager_round("What is the irrigation status?")


def test_consolidates_max_three_actions_one_question_and_partial_failure():
    loaders = {"herdmaster": lambda: specialist("herdmaster", state=WorkState.WAITING_EVIDENCE, value=100, question="One herd fact?"),
        "rootline": lambda: specialist("rootline", value=90, question="One water fact?"),
        "sam": lambda: specialist("sam", value=80),
        "beacon": lambda: SpecialistResult("beacon", "beacon-missing", NOW, SpecialistAvailability.MISSING)}
    result, status = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders, event_store=memory_store(),
        weighing_loader=lambda: ({"pig_id":"PIG-1","tag_number":"1"}, {"pig_id":"PIG-2","tag_number":"2"}))
    assert status == 200 and result["status"] == "farm_manager_round_ready"
    assert result["action_count"] == 3 and result["question_count"] == 1
    assert result["specialist_gaps"] == {"beacon": "missing"}
    assert "BEACON" not in result["answer"] and "missing" not in result["answer"].lower()
    assert "Irrigation status could not be read" not in result["answer"]
    assert "Weigh all" not in result["answer"]
    assert "active/on-farm pigs" not in result["answer"]
    assert "ROOTLINE priority" in result["answer"]
    assert result["weighing_worklist"] == ()
    assert all(result[key] is False for key in ("writes_farm_data", "writes_weights", "writes_mating", "hardware_commands", "publishes"))


def test_stale_specialist_blocks_only_its_conclusion_and_replay_is_deterministic():
    loaders = {name: (lambda n=name: specialist(n, availability=SpecialistAvailability.STALE))
               for name in ("herdmaster", "rootline", "sam", "beacon")}
    store = memory_store()
    first, _ = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders, event_store=store, weighing_loader=lambda:())
    second, _ = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders, event_store=store, weighing_loader=lambda:())
    assert first["mission_id"] == second["mission_id"]
    assert first["result_digest"] == second["result_digest"]
    assert first["action_count"] <= 3 and first["question_count"] <= 1

    conflict = parsed(EXACT + " changed")
    conflict_result, conflict_status = handle_farm_manager_round(conflict,
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders, event_store=store, weighing_loader=lambda:())
    assert conflict_status == 409 and conflict_result["status"] == "farm_manager_provider_binding_conflict"


def test_anonymous_manager_request_fails_closed():
    result, status = handle_farm_manager_round(parsed(), None, now=NOW, loaders={}, event_store=memory_store())
    assert status == 200 and result == {"handled": False}


def test_losing_provider_claim_reloads_winner_and_contains_conflict():
    winner = {}
    def store(action, identity, payload):
        if action == "load": return winner.get("row")
        winner["row"] = {"binding": {**payload["binding"], "content_digest": "different"},
                         "result": payload["result"]}
        return {"success": True, "created": False}
    loaders = {name: (lambda n=name: specialist(n)) for name in ("herdmaster", "rootline", "sam", "beacon")}
    result, status = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER),
        now=NOW, loaders=loaders, event_store=store, weighing_loader=lambda:())
    assert status == 409 and result["status"] == "farm_manager_provider_binding_conflict"


def test_completed_pig125_is_suppressed_and_active_pig11_appears_once():
    p = Provenance("herdmaster", "herd-result", ("canonical:lifecycle",), NOW, 1.0)
    pig125 = SpecialistWorkItem("pig125", "herdmaster:PIG-2026-BCEB", "herd", "Pig 125 completed",
        "Closed lifecycle.", "No action.", "charl", WorkState.COMPLETED, Authority.ADVISORY, p, business_value=100)
    pig11 = SpecialistWorkItem("pig11", "herdmaster:PIG-2026-E88A", "herd", "Pig 11 monitoring",
        "Active welfare lifecycle remains open.", "Continue the already-scheduled appetite reassessment; do not repeat answered questions.",
        "charl", WorkState.PLANNED, Authority.ADVISORY, p, business_value=99)
    herd = SpecialistResult("herdmaster", "herd-result", NOW, work_items=(pig125, pig11))
    loaders = {"herdmaster":lambda:herd, "rootline":lambda:specialist("rootline"),
        "sam":lambda:SpecialistResult("sam","sam-missing",NOW,SpecialistAvailability.MISSING),
        "beacon":lambda:SpecialistResult("beacon","beacon-missing",NOW,SpecialistAvailability.MISSING)}
    result, _ = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW,
        loaders=loaders, event_store=memory_store(), weighing_loader=lambda:())
    assert "Pig 125" not in result["answer"]
    assert result["answer"].count("Pig 11") == 1
    assert "active/on-farm pigs" not in result["answer"]


def test_owner_reported_dead_pig127_keeps_mortality_lifecycle_without_obsolete_breathing_question():
    result = farm_manager_runtime._active_welfare_result(({
        "pig_id":"PIG-2026-D13C", "tag_number":"127", "lifecycle_id":"PIG127-MORTALITY",
        "card_message_id":"3203", "provider_timestamp":"2026-08-03T06:00:00+00:00",
        "reported_dead":True, "current_question":"Is Pig 127 breathing?"},), NOW)
    assert len(result.work_items)==1
    item=result.work_items[0]
    assert "mortality record follow-up" in item.title
    assert "breathing" not in item.next_action.lower() and item.genuine_question==""


def test_retired_broad_weighing_loader_is_never_consulted():
    loaders = {name:(lambda n=name:specialist(n)) for name in ("herdmaster","rootline","sam","beacon")}
    result, _ = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW,
        loaders=loaders, event_store=memory_store(),
        weighing_loader=lambda:(_ for _ in ()).throw(RuntimeError("down")))
    assert "herdmaster_weighing" not in result["specialist_gaps"]
    assert result["weighing_worklist"] == ()
    assert "weigh all" not in result["answer"].lower()


def test_daily_evidence_failure_does_not_hide_supported_herd_work(monkeypatch):
    base=specialist("herdmaster")
    monkeypatch.setattr(farm_manager_runtime,"load_current_breeding_operating_loop",lambda:{})
    monkeypatch.setattr(farm_manager_runtime,"_load_observations",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_load_active_lifecycles",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_whole_herd_specialist_result",lambda *args:base)
    monkeypatch.setattr(farm_manager_runtime,"load_daily_manager_evidence",
        lambda **kwargs:(_ for _ in ()).throw(RuntimeError("optional unavailable")))
    result=farm_manager_runtime._load_herdmaster(
        issue_gateway_owner_authority(OWNER,OWNER),OWNER,NOW)
    assert any(item.title=="Weekly weighing evidence unavailable" for item in result.work_items)
    assert any(item.dedupe_key==base.work_items[0].dedupe_key for item in result.work_items)


def test_versioned_daily_evidence_is_combined_with_supported_herd_work(monkeypatch):
    base=specialist("herdmaster")
    daily=specialist("herdmaster",value=125)
    monkeypatch.setattr(farm_manager_runtime,"load_current_breeding_operating_loop",lambda:{})
    monkeypatch.setattr(farm_manager_runtime,"_load_observations",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_load_active_lifecycles",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_whole_herd_specialist_result",lambda *args:base)
    monkeypatch.setattr(farm_manager_runtime,"load_daily_manager_evidence",lambda **kwargs:{})
    monkeypatch.setattr(farm_manager_runtime,"consume_daily_manager_evidence",
        lambda *args,**kwargs:daily)
    result=farm_manager_runtime._load_herdmaster(
        issue_gateway_owner_authority(OWNER,OWNER),OWNER,NOW)
    assert result.result_id==base.result_id+":"+daily.result_id
    assert result.work_items[0].dedupe_key==daily.work_items[0].dedupe_key


def test_two_distinct_manager_rounds_reuse_same_versioned_daily_evidence(monkeypatch):
    base=specialist("herdmaster")
    monkeypatch.setattr(farm_manager_runtime,"load_current_breeding_operating_loop",lambda:{})
    monkeypatch.setattr(farm_manager_runtime,"_load_observations",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_load_active_lifecycles",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_whole_herd_specialist_result",lambda *args:base)
    packet={"material_digest":"D1"}
    daily=specialist("herdmaster",value=125)
    monkeypatch.setattr(farm_manager_runtime,"load_daily_manager_evidence",lambda **kwargs:packet)
    monkeypatch.setattr(farm_manager_runtime,"consume_daily_manager_evidence",
        lambda value,**kwargs:daily if value is packet else None)
    authority=issue_gateway_owner_authority(OWNER,OWNER)
    first=farm_manager_runtime._load_herdmaster(authority,OWNER,NOW)
    second=farm_manager_runtime._load_herdmaster(authority,OWNER,NOW)
    assert first.result_id==second.result_id
    assert first.work_items[0].dedupe_key==daily.work_items[0].dedupe_key
    assert second.work_items[0].dedupe_key==daily.work_items[0].dedupe_key


def _changed_daily_packet():
    return {"packet_type":"herdmaster.daily_manager_evidence.v1",
        "material_digest":"A"*64,
        "weight":{"historical_completion_percentage":None,
            "current_snapshot":{"eligible_tagged":1,"covered":1,
                "coverage_percentage":100.0,"status":"complete"},
            "missing_eligible_tagged":[],"breeding_excluded":[],
            "untagged_excluded":[],"inactive_off_farm":[],"unknown_eligibility":[],
            "conflicting_weight_evidence":[],"material_weight_findings":[]},
        "mortality":{"digest_changed":True,"candidate_deaths":[{"event_id":"D1","pig_id":"P1"}],
            "canonical_death_event_fingerprints":{"D1":"F1"},
            "durable_death_event_fingerprints":{"D1":"F1"}},
        "specialist_mortality_packet":{"review_identity":"HERDMASTER-MORTALITY-CURRENT"},
        "authority":{"read_only":True,"writes_farm_data":False,
            "hardware_commands":0,"sends_messages":False}}


def test_changed_mortality_without_open_lifecycle_opens_followup_without_precomposition_write(monkeypatch):
    base=specialist("herdmaster")
    monkeypatch.setattr(farm_manager_runtime,"load_current_breeding_operating_loop",lambda:{})
    monkeypatch.setattr(farm_manager_runtime,"_load_observations",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_load_active_lifecycles",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_whole_herd_specialist_result",lambda *args:base)
    monkeypatch.setattr(farm_manager_runtime,"load_daily_manager_evidence",lambda **kwargs:_changed_daily_packet())
    result=farm_manager_runtime._load_herdmaster(
        issue_gateway_owner_authority(OWNER,OWNER),OWNER,NOW)
    assert any("Mortality follow-up" in item.title for item in result.work_items)
    assert farm_manager_runtime._mortality_fingerprints(
        type("Brief",(),{"queue":result.work_items})())=={"D1":"F1"}


def test_completed_nonmortality_lifecycle_does_not_suppress_new_death(monkeypatch):
    base=specialist("herdmaster")
    monkeypatch.setattr(farm_manager_runtime,"load_current_breeding_operating_loop",lambda:{})
    monkeypatch.setattr(farm_manager_runtime,"_load_observations",lambda owner:())
    monkeypatch.setattr(farm_manager_runtime,"_load_active_lifecycles",
        lambda owner:({"pig_id":"P1","state":"completed","mortality_closed":False},))
    monkeypatch.setattr(farm_manager_runtime,"_whole_herd_specialist_result",lambda *args:base)
    monkeypatch.setattr(farm_manager_runtime,"load_daily_manager_evidence",lambda **kwargs:_changed_daily_packet())
    result=farm_manager_runtime._load_herdmaster(
        issue_gateway_owner_authority(OWNER,OWNER),OWNER,NOW)
    assert any("Mortality follow-up" in item.title for item in result.work_items)


def test_independent_specialists_share_one_bounded_delivery_budget_and_text_is_telegram_safe():
    def slow(name):
        time.sleep(0.12)
        value = specialist(name)
        item = value.work_items[0]
        return SpecialistResult(name, value.result_id, NOW, work_items=(SpecialistWorkItem(
            item.item_id, item.dedupe_key, item.domain, item.title, "why " * 600,
            "next " * 600, item.assignee, item.state, item.authority, item.provenance,
            business_value=item.business_value),))
    loaders={name:(lambda n=name:slow(n)) for name in ("herdmaster","rootline","sam","beacon")}
    started=time.monotonic()
    result,_=handle_farm_manager_round(parsed(),issue_gateway_owner_authority(OWNER,OWNER),now=NOW,
        loaders=loaders,event_store=memory_store(),weighing_loader=lambda:())
    elapsed=time.monotonic()-started
    assert elapsed < 0.35
    assert len(result["answer"]) <= 3900
    assert "authority" not in result["answer"].lower()
    assert result["answer"].count("<b>") == result["answer"].count("</b>")


def test_slow_specialist_is_contained_without_blocking_supported_brief_and_html_is_escaped():
    def slow():
        time.sleep(0.5)
        return specialist("beacon")
    hostile = specialist("herdmaster")
    original = hostile.work_items[0]
    hostile = SpecialistResult("herdmaster", hostile.result_id, NOW, work_items=(SpecialistWorkItem(
        original.item_id, original.dedupe_key, original.domain, "Pig <unsafe> & current", original.why,
        original.next_action, original.assignee, original.state, original.authority, original.provenance,
        business_value=original.business_value),))
    loaders={"herdmaster":lambda:hostile,"rootline":lambda:specialist("rootline"),
        "sam":lambda:specialist("sam"),"beacon":slow}
    started=time.monotonic()
    result,_=handle_farm_manager_round(parsed(),issue_gateway_owner_authority(OWNER,OWNER),now=NOW,
        loaders=loaders,event_store=memory_store(),weighing_loader=lambda:(),specialist_budget_seconds=0.05)
    assert time.monotonic()-started < 0.3
    assert result["specialist_gaps"]["beacon"] == "contained"
    assert "&lt;unsafe&gt; &amp; current" in result["answer"]
    assert "<unsafe>" not in result["answer"]
    assert "authority" not in result["answer"].lower()


def test_escape_heavy_specialist_text_stays_valid_and_inside_telegram_budget():
    def hostile(name):
        value=specialist(name);item=value.work_items[0];noise="&<>"*900
        return SpecialistResult(name,value.result_id,NOW,work_items=(SpecialistWorkItem(
            item.item_id,item.dedupe_key,item.domain,noise,noise,noise,item.assignee,item.state,
            item.authority,item.provenance,business_value=item.business_value),))
    loaders={name:(lambda n=name:hostile(n)) for name in ("herdmaster","rootline","sam","beacon")}
    result,status=handle_farm_manager_round(parsed(),issue_gateway_owner_authority(OWNER,OWNER),now=NOW,
        loaders=loaders,event_store=memory_store(),weighing_loader=lambda:())
    assert status==200 and result["success"] is True and len(result["answer"])<=3900
    assert result["answer"].count("<b>")==result["answer"].count("</b>")
    assert "authority" not in result["answer"].lower()


def test_repeated_timeouts_remain_inside_shared_worker_bulkhead():
    def slow():
        time.sleep(0.15)
        return specialist("beacon")
    for index in range(3):
        row=parsed(EXACT+f" {index}");row["provider_message_id"]=str(4000+index)
        loaders={name:slow for name in ("herdmaster","rootline","sam","beacon")}
        result,_=handle_farm_manager_round(row,issue_gateway_owner_authority(OWNER,OWNER),now=NOW,
            loaders=loaders,event_store=memory_store(),weighing_loader=lambda:(),specialist_budget_seconds=0.01)
        assert result["success"] is True
    assert len(farm_manager_runtime._SPECIALIST_EXECUTOR._threads) <= 8
