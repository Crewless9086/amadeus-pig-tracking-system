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
    assert "BEACON (missing)" in result["answer"] and "Irrigation status could not be read" not in result["answer"]
    assert "weighing, breeding and welfare" in result["answer"]
    assert "Weigh all 2 current active/on-farm pigs" in result["answer"]
    assert "ROOTLINE priority" in result["answer"]
    assert result["weighing_worklist"] == ({"pig_id":"PIG-1","tag_number":"1"}, {"pig_id":"PIG-2","tag_number":"2"})
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
    assert "No current active/on-farm pigs" in result["answer"]


def test_weighing_loader_failure_is_a_bounded_visible_gap():
    loaders = {name:(lambda n=name:specialist(n)) for name in ("herdmaster","rootline","sam","beacon")}
    result, _ = handle_farm_manager_round(parsed(), issue_gateway_owner_authority(OWNER, OWNER), now=NOW,
        loaders=loaders, event_store=memory_store(),
        weighing_loader=lambda:(_ for _ in ()).throw(RuntimeError("down")))
    assert result["specialist_gaps"]["herdmaster_weighing"] == "contained"
    assert "HERDMASTER_WEIGHING (contained)" in result["answer"]


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
    assert "No weight, mating, farm, customer, publication or hardware action was performed." in result["answer"]
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
    assert "No weight, mating, farm, customer, publication or hardware action was performed." in result["answer"]


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
    assert "No weight, mating, farm, customer, publication or hardware action was performed." in result["answer"]


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
