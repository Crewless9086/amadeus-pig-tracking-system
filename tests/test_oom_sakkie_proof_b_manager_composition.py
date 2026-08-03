from datetime import datetime, timezone
from threading import Barrier, Lock, Thread

from modules.oom_sakkie.farm_manager_loop import SpecialistAvailability, SpecialistResult
from modules.oom_sakkie.farm_manager_runtime import (
    _current_cycle_observations, _whole_herd_specialist_result, handle_farm_manager_round,
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
        "contract_version": "oom_sakkie_farm_manager_round_v1"}
    manager_rows = {mission: {"binding": old_binding,
        "result": {"action_count": 0, "answer": "BOUNDED WAITING"}}}
    def manager_store(action, identity, payload):
        if action == "load": return manager_rows.get(identity)
        manager_rows[identity] = payload; return {"success": True, "created": True}
    herd = _whole_herd_specialist_result(canonical(), observations(), active(), weights(), NOW)
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
