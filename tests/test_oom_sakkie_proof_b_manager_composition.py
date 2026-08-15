from datetime import datetime, timezone
from threading import Barrier, Lock, Thread

from modules.oom_sakkie.farm_manager_loop import SpecialistAvailability, SpecialistResult
from modules.oom_sakkie.farm_manager_runtime import (
    _canonical_tasks_with_current_mating, _current_cycle_observations,
    _whole_herd_specialist_result, handle_farm_manager_round,
)
from modules.oom_sakkie.family_message_lifecycle import bind_existing_card, deliver_family_result
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority


NOW = datetime(2026, 8, 3, 10, 46, 23, tzinfo=timezone.utc)
OWNER = "5721652188"
TEXT = ("Oom Sakkie, what needs attention on the farm today? Give me the current priorities "
        "for the herd, irrigation, sales and marketing, and tell me what we should do next.")


def canonical():
    def task(pig, tag, mating, date):
        return {"task_id": "TASK-" + pig, "pig_id": pig, "tag_number": tag,
            "known_evidence": {"current_mating_id": mating, "current_mating_date": date}}
    return {"success": True, "writes_performed": False,
        "generated_at": NOW.isoformat(), "worklist_id": "HERD-CURRENT",
        "tasks": [task("PIG-2026-D050", "Mona", "MAT-MONA", "2026-05-02"),
                  task("PIG-2026-21BE", "Mysikind", "MAT-MYSI", "2026-05-02"),
                  task("PIG-2026-7DAA", "Baby", "MAT-BABY", "2026-05-19")]}


def deployed_shape_canonical():
    value = canonical()
    cases = []
    for task in value["tasks"]:
        known = task["known_evidence"]
        mating_id = known.pop("current_mating_id")
        mating_date = known.pop("current_mating_date")
        known["latest_mating_date"] = mating_date
        cases.append({"pig_id": task["pig_id"], "mating_history": [
            {"mating_id": mating_id, "date": mating_date, "canonical_mating": True,
             "status": "Open"}]})
    value["cases"] = cases
    return value


def observations():
    return [
        {"pig_id": "PIG-2026-D050", "operational_result": "Assumed Pregnant",
         "observed_signs": "belly dropping and teats are growing", "mating_id": "MAT-MONA",
         "mating_date": "2026-05-02", "observed_at": "2026-08-01T11:51:04+00:00",
         "source_identity": "TELEGRAM-3151-C19F2C2B-MONA"},
        {"pig_id": "PIG-2026-21BE", "operational_result": "Assumed Pregnant",
         "observed_signs": "belly dropping and teats are growing", "mating_id": "MAT-MYSI",
         "mating_date": "2026-05-02", "observed_at": "2026-08-01T11:51:04+00:00",
         "source_identity": "TELEGRAM-3151-C19F2C2B-MYSIKIND"},
        {"pig_id": "PIG-2026-7DAA", "operational_result": "Inconclusive",
         "observed_signs": "visual inspection inconclusive", "mating_id": "MAT-BABY",
         "mating_date": "2026-05-19", "observed_at": "2026-08-01T11:51:04+00:00",
         "source_identity": "TELEGRAM-3151-C19F2C2B-BABY"},
    ]


def active():
    return [{"pig_id": "PIG-2026-D13C", "tag_number": "127",
        "lifecycle_id": "OOM-HERDMASTER-368E7C97C6D82C2416716A19",
        "state": "waiting_for_input", "card_message_id": "3203",
        "provider_timestamp": "2026-08-03T06:31:20+00:00",
        "current_question": "Is Pig 127 breathing now, and does it look normal or distressed?"}]


def weights():
    return ({"pig_id": "PIG-W1", "tag_number": "41"},
            {"pig_id": "PIG-W2", "tag_number": "52"})


def parsed():
    return {"text": TEXT, "telegram_user_id": OWNER, "telegram_chat_id": OWNER,
        "provider_message_id": "3208", "provider_timestamp": NOW.isoformat()}


def test_whole_herd_result_starts_with_pig127_and_combines_preparation_with_weighing():
    result = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    assert result.availability is SpecialistAvailability.AVAILABLE
    assert len(result.work_items) == 2
    assert result.work_items[0].state.value == "urgent"
    assert "Pig 127" in result.work_items[0].title
    assert result.work_items[0].genuine_question.count("?") == 1
    herd = result.work_items[1]
    assert "Mysikind" in herd.title and "Mona" in herd.title
    assert "Monday weighing" in herd.title
    assert "2026-08-22" in herd.why and "2026-08-26" in herd.why
    assert "not clinically confirmed" in herd.why
    assert "Weigh these 2 pigs: 41, 52" in herd.next_action


def test_reproductive_observations_require_newest_exact_current_mating_cycle():
    rows = observations() + [
        {**observations()[0], "mating_id": "MAT-OLD", "mating_date": "2025-11-01",
         "observed_at": "2025-12-01T08:00:00+00:00", "source_identity": "OLD-MONA"},
        {**observations()[0], "operational_result": "Inconclusive",
         "observed_at": "2026-07-31T08:00:00+00:00", "source_identity": "EARLIER-MONA"},
    ]
    selected = _current_cycle_observations(
        {row["pig_id"]: row for row in canonical()["tasks"]}, rows, NOW)
    mona = [row for row in selected if row["pig_id"] == "PIG-2026-D050"]
    assert len(mona) == 1
    assert mona[0]["source_identity"] == "TELEGRAM-3151-C19F2C2B-MONA"
    result = _whole_herd_specialist_result(canonical(), rows, active(), weights(), NOW)
    assert any("Mona" in item.title for item in result.work_items)


def test_deployed_task_and_case_shape_supplies_exact_current_mating_binding():
    shaped = deployed_shape_canonical()
    tasks = _canonical_tasks_with_current_mating(shaped)
    assert tasks["PIG-2026-D050"]["known_evidence"] == {
        "latest_mating_date": "2026-05-02", "current_mating_id": "MAT-MONA",
        "current_mating_date": "2026-05-02"}
    result = _whole_herd_specialist_result(shaped, observations(), active(), weights(), NOW)
    assert any("Mona" in item.title and "Mysikind" in item.title for item in result.work_items)


def test_ambiguous_canonical_mating_history_does_not_promote_observation():
    shaped = deployed_shape_canonical()
    mona = next(row for row in shaped["cases"] if row["pig_id"] == "PIG-2026-D050")
    mona["mating_history"].append({**mona["mating_history"][0], "mating_id": "MAT-CONFLICT"})
    result = _whole_herd_specialist_result(shaped, observations(), active(), weights(), NOW)
    assert all("Mona" not in item.title for item in result.work_items)
    assert "Pig 127" in result.work_items[0].title


def test_prior_cycle_or_conflicting_same_time_observation_is_section_local():
    old_mona = {**observations()[0], "mating_id": "MAT-OLD", "mating_date": "2025-11-01"}
    conflicting = {**observations()[1], "operational_result": "Inconclusive",
        "source_identity": "CONFLICTING-MYSIKIND"}
    result = _whole_herd_specialist_result(canonical(),
        [old_mona, observations()[1], conflicting, observations()[2]], active(), weights(), NOW)
    assert result.availability is SpecialistAvailability.AVAILABLE
    assert all("Mona" not in item.title and "Mysikind" not in item.title for item in result.work_items)
    assert "Pig 127" in result.work_items[0].title
    assert any(item.title == "Complete Monday weighing"
               and "Weigh these 2 pigs: 41, 52" in item.next_action for item in result.work_items)


def test_missing_malformed_or_naive_observation_time_cannot_create_reproductive_work():
    invalid = [{**observations()[0], "observed_at": value,
                "source_identity": "INVALID-" + str(index)}
               for index, value in enumerate((None, "not-a-time", "2026-08-01T11:51:04"))]
    result = _whole_herd_specialist_result(canonical(), invalid, active(), weights(), NOW)
    assert "Pig 127" in result.work_items[0].title
    assert all("Mona" not in item.title for item in result.work_items)
    assert any(item.title == "Complete Monday weighing" for item in result.work_items)


def test_missing_and_contained_zero_action_specialists_are_suppressed_not_global_waiting():
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    rootline = SpecialistResult("rootline", "rootline-contained", NOW,
                                SpecialistAvailability.CONTAINED)
    loaders = {"herdmaster": lambda: herd, "rootline": lambda: rootline,
        "sam": lambda: SpecialistResult("sam", "sam-zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "beacon-missing", NOW,
                                             SpecialistAvailability.MISSING)}
    rows = {}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert status == 200 and result["action_count"] == 2
    assert result["question_count"] == 1
    assert "Pig 127" in result["answer"]
    assert result["answer"].count("Is Pig 127 breathing now") == 1
    assert "BOUNDED WAITING" not in result["answer"]
    assert not any(term in result["answer"].lower() for term in (
        "adapter", "packet", "contained", "missing specialist", "evidence loader"))


def test_v1_zero_action_waiting_result_is_recomposed_once_and_then_replays():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    old_binding = {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v1"}
    rows = {mission: {"binding": old_binding, "result": {
        "action_count": 0, "answer": "<b>BOUNDED WAITING</b>"}}}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "rootline-zero", NOW),
        "sam": lambda: SpecialistResult("sam", "sam-zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "beacon-zero", NOW)}
    first, first_status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert first_status == 200 and first["action_count"] == 2
    assert "BOUNDED WAITING" not in first["answer"]
    replay, replay_status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert replay_status == 200 and replay["status"] == "farm_manager_round_replay_suppressed"


def test_v2_precomposition_clock_defect_recomposes_under_v3():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    old_binding = {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v2"}
    rows = {mission: {"binding": old_binding, "result": {"action_count": 1,
        "answer": "Refresh today's irrigation decision",
        "specialist_gaps": {"herdmaster": "invalid_future_evidence"}}}}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "zero", NOW),
        "sam": lambda: SpecialistResult("sam", "zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert status == 200 and "Pig 127" in result["answer"]
    assert result["binding"]["contract_version"] == "oom_sakkie_farm_manager_round_v5"


def test_live_composition_clock_accepts_result_generated_after_invocation():
    invoked = NOW
    composed = NOW.replace(second=NOW.second + 5)
    ticks = iter((invoked, composed))
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), composed)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "zero", composed),
        "sam": lambda: SpecialistResult("sam", "zero", composed),
        "beacon": lambda: SpecialistResult("beacon", "zero", composed)}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), loaders=loaders,
        event_store=lambda action, identity, payload: None if action == "load" else {"success": True, "created": True},
        weighing_loader=weights, clock=lambda: next(ticks))
    assert status == 200 and "Pig 127" in result["answer"]
    assert "invalid_future_evidence" not in result["specialist_gaps"].values()


def test_large_weighing_journey_is_concise_and_unlabelled_pigs_fail_closed():
    herd_weights = tuple({"pig_id": f"PIG-{index:03d}",
                          "tag_number": None if index < 4 else str(index)}
                         for index in range(30))
    result = _whole_herd_specialist_result(
        canonical(), observations(), active(), herd_weights, NOW)
    action = next(item for item in result.work_items if "Monday weighing" in item.title)
    assert "26 identified active/on-farm pigs" in action.next_action
    assert "4 unlabelled pigs" in action.next_action
    assert "None" not in action.next_action
    assert len(action.next_action) < 450


def test_all_unlabelled_weighing_candidates_remain_visible_but_unrecordable():
    no_reproductive = []
    unlabelled = tuple({"pig_id": f"PIG-U-{index}", "tag_number": None}
                       for index in range(5))
    result = _whole_herd_specialist_result(
        canonical(), no_reproductive, (), unlabelled, NOW)
    assert len(result.work_items) == 1
    item = result.work_items[0]
    assert item.state.value == "waiting_for_evidence"
    assert item.title == "Identify unlabelled pigs before weighing"
    assert "5 current weighing candidates" in item.why
    assert "Keep 5 unlabelled pigs out of the recording preview" in item.next_action
    assert "None" not in item.next_action


def test_v3_truncated_large_herd_result_can_recompose_once_under_v4():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    prior = {"binding": {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v3"},
        "result": {"action_count": 3, "answer": "Pig 127. Weigh these 137 pigs: 1, None, 2…"}}
    rows = {mission: prior}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "zero", NOW),
        "sam": lambda: SpecialistResult("sam", "zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert status == 200 and result["binding"]["contract_version"] == "oom_sakkie_farm_manager_round_v5"
    assert "Pig 127" in result["answer"] and "None" not in result["answer"]


def test_v4_obsolete_breathing_question_recomposes_once_under_v5():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    prior = {"binding": {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v4"},
        "result": {"action_count": 2,
            "answer": "Pig 127 welfare follow-up. Is Pig 127 breathing now?"}}
    rows = {mission: prior}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    reported_dead = [{**active()[0], "reported_dead": True}]
    herd = _whole_herd_specialist_result(canonical(), observations(), reported_dead, weights(), NOW)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "zero", NOW),
        "sam": lambda: SpecialistResult("sam", "zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert status == 200
    assert result["binding"]["contract_version"] == "oom_sakkie_farm_manager_round_v5"
    assert "breathing" not in result["answer"].casefold()
    assert "mortality" in result["answer"].casefold()


def test_v4_obsolete_question_preserves_card_without_matching_mortality_evidence():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    prior = {"binding": {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v4"},
        "result": {"action_count": 2,
            "answer": "Pig 127 welfare follow-up. Is Pig 127 breathing now?"}}
    rows = {mission: prior}
    def store(action, identity, payload):
        if action == "load": return rows.get(identity)
        rows[identity] = payload; return {"success": True, "created": True}
    loaders = {"herdmaster": lambda: _whole_herd_specialist_result(
            canonical(), observations(), active(), weights(), NOW),
        "rootline": lambda: SpecialistResult("rootline", "zero", NOW),
        "sam": lambda: SpecialistResult("sam", "zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=store, weighing_loader=weights)
    assert status == 409
    assert result["status"] == "farm_manager_material_recomposition_evidence_unavailable"
    assert rows[mission] == prior


def test_whole_herd_packet_does_not_repeat_the_unbounded_weighing_read():
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
    loaders = {name: (lambda result=result: result) for name, result in {
        "herdmaster": herd, "rootline": SpecialistResult("rootline", "zero", NOW),
        "sam": SpecialistResult("sam", "zero", NOW), "beacon": SpecialistResult("beacon", "zero", NOW)}.items()}
    result, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=lambda action, identity, payload: None if action == "load" else {"success": True, "created": True},
        weighing_loader=lambda: (_ for _ in ()).throw(AssertionError("duplicate weighing read")))
    assert status == 200 and result["action_count"] == 2


def test_concurrent_material_recomposition_has_one_durable_winner():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    old = {"binding": {"owner": OWNER, "chat": OWNER,
        "provider_message_id": "3208", "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v1"},
        "result": {"action_count": 0, "answer": "BOUNDED WAITING"}}
    barrier, lock = Barrier(2), Lock()
    state = {"winner": None, "records": 0}
    def store(action, identity, payload):
        if action == "load":
            with lock: winner = state["winner"]
            if winner is None: barrier.wait()
            return winner or old
        with lock:
            if state["winner"] is None:
                state["winner"] = payload; state["records"] += 1
                return {"success": True, "created": True}
            return {"success": True, "created": False}
    outputs = []
    def run(suffix):
        herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
        loaders = {"herdmaster": lambda: herd,
            "rootline": lambda: SpecialistResult("rootline", "zero" + suffix, NOW),
            "sam": lambda: SpecialistResult("sam", "zero", NOW),
            "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}
        outputs.append(handle_farm_manager_round(parsed(),
            issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
            event_store=store, weighing_loader=weights))
    threads = [Thread(target=run, args=(suffix,)) for suffix in ("-A", "-B")]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert state["records"] == 1
    assert {result[0]["result_digest"] for result in outputs} == {
        state["winner"]["result"]["result_digest"]}
    assert sorted(result[0]["status"] for result in outputs) == [
        "farm_manager_round_ready", "farm_manager_round_replay_suppressed"]


def test_material_correction_edits_card_3209_once_then_delivery_replay_is_silent():
    mission = "OOM-FARM-ROUND-0FCB0C799AFC160886B57077"
    old_binding = {"owner": OWNER, "chat": OWNER, "provider_message_id": "3208",
        "provider_timestamp": NOW.isoformat(),
        "content_digest": __import__("hashlib").sha256(TEXT.encode()).hexdigest(),
        "contract_version": "oom_sakkie_farm_manager_round_v4"}
    manager_rows = {mission: {"binding": old_binding,
        "result": {"action_count": 1,
            "answer": "Pig 127 welfare follow-up. Is Pig 127 breathing now?"}}}
    def manager_store(action, identity, payload):
        if action == "load": return manager_rows.get(identity)
        manager_rows[identity] = payload; return {"success": True, "created": True}
    herd = _whole_herd_specialist_result(canonical(), observations(),
        [{**active()[0], "reported_dead": True}], weights(), NOW)
    loaders = {"herdmaster": lambda: herd,
        "rootline": lambda: SpecialistResult("rootline", "zero", NOW),
        "sam": lambda: SpecialistResult("sam", "zero", NOW),
        "beacon": lambda: SpecialistResult("beacon", "zero", NOW)}

    class FamilyMemory:
        def __init__(self): self.rows = {}; self.sent = []; self.edited = []
        def store(self, action, identity, payload):
            if action == "load": return list(self.rows.values())
            created = identity not in self.rows
            if created: self.rows[identity] = dict(payload)
            return {"success": True, "created": created}
        def send(self, chat, text):
            self.sent.append((chat, text)); return {"success": True, "telegram_message_id": "unexpected"}
        def edit(self, chat, message_id, text):
            self.edited.append((chat, message_id, text))
            return {"success": True, "telegram_message_id": message_id}
    family = FamilyMemory()
    bound = bind_existing_card(parsed(), specialist="OOM_SAKKIE", mission_id=mission,
        telegram_message_id="3209", text_sha256="a" * 64, expected_bot_identity="oom-bot",
        provider_evidence_loader=lambda chat, message: {"delivered": True,
            "bot_identity": "oom-bot", "chat_id": chat, "telegram_message_id": message,
            "text_sha256": "a" * 64}, event_store=family.store)
    assert bound["telegram_sends"] == 0
    corrected, status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=manager_store, weighing_loader=weights)
    first_delivery = deliver_family_result(parsed(), corrected, specialist="OOM_SAKKIE",
        mission_id=mission, card_mission_id=mission, event_store=family.store,
        sender=family.send, editor=family.edit)
    replay, replay_status = handle_farm_manager_round(parsed(),
        issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders,
        event_store=manager_store, weighing_loader=weights)
    replay_delivery = deliver_family_result(parsed(), replay, specialist="OOM_SAKKIE",
        mission_id=mission, card_mission_id=mission, event_store=family.store,
        sender=family.send, editor=family.edit)
    assert status == replay_status == 200
    assert first_delivery["telegram_message_id"] == "3209"
    assert first_delivery["telegram_edits"] == 1 and first_delivery["telegram_sends"] == 0
    assert replay_delivery["telegram_edits"] == replay_delivery["telegram_sends"] == 0
    assert family.sent == [] and len(family.edited) == 1
