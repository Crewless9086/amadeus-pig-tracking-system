import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from modules.charlie.private_policy import authenticate_private_action_context
from modules.charlie.private_runtime import handle_authenticated_private_action
from modules.charlie.private_tools import execute_private_tool


ENV = {
    "CHARLIE_EXECUTIVE_ENABLED": "true",
    "CHARLIE_TELEGRAM_BOT_TOKEN": "bot-token",
    "CHARLIE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_TELEGRAM_OWNER_USER_ID": "42",
    "CHARLIE_TELEGRAM_OWNER_CHAT_ID": "42",
}
PAYLOAD = {"message": {"from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}
TITLE = "Phase A observation-only Shadow Control Tower comparison of human Control Tower decisions"
RAW = TITLE
ADMISSION = {
    "portfolio_epoch": "CORE-CURRENT-2026-08-14",
    "classification": "current",
    "lifecycle_state": "WORKING",
    "admission_version": "portfolio_admission_v1",
    "admission_evidence": "owner_approved_cmq_20260813_05_bootstrap",
    "decision_authority": "human_control_tower",
    "dispatch_authority": "human_control_tower",
    "runnable": False,
}


def context(mission_id):
    return authenticate_private_action_context(PAYLOAD, HEADERS, mission_id, ENV)


def args(mission_id="CMQ-20260813-05", **changes):
    value = {"mission_id": mission_id, "title": TITLE, "raw_text": RAW,
        "mission_type": "system improvement", "urgency": "P1",
        "portfolio_admission": ADMISSION}
    value.update(changes)
    return value


@patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.get_mission")
def test_exact_owner_approved_id_is_forwarded_unchanged_and_verified(get_mission, record_mission, _list):
    get_mission.side_effect = [({"status": "not_found"}, 404),
        ({"mission": {"mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
            "status": "paused", "metadata": {"portfolio_admission": ADMISSION}}}, 200)]
    record_mission.return_value = ({"mission_id": "CMQ-20260813-05", "stored": True}, 201)
    result, status = execute_private_tool("create_mission", args(), context("CMQ-20260813-05"))
    assert status == 200 and result["mission_id"] == "CMQ-20260813-05" and result["verified"]
    mission = record_mission.call_args.args[0]
    assert mission["mission_id"] == "CMQ-20260813-05"
    assert mission["metadata"]["opaque_identity_owner_approved"] is True
    assert record_mission.call_args.kwargs["exact_identity"] is True


@patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.get_mission")
def test_raw_private_authentication_boundary_seals_and_forwards_exact_id(get_mission, record_mission, _list):
    get_mission.side_effect = [({"status": "not_found"}, 404),
        ({"mission": {"mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
            "status": "paused", "metadata": {"portfolio_admission": ADMISSION}}}, 200)]
    record_mission.return_value = ({"mission_id": "CMQ-20260813-05", "stored": True}, 201)
    action = {"action": "create_mission", **args()}
    result, status = handle_authenticated_private_action(
        action, PAYLOAD, HEADERS, existing_mission_id="CMQ-20260813-05", environ=ENV)
    assert status == 200 and result["mission_id"] == "CMQ-20260813-05"
    assert record_mission.call_args.args[0]["mission_id"] == "CMQ-20260813-05"
    assert record_mission.call_args.kwargs["exact_identity"] is True


@patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.get_mission")
def test_suffixed_opaque_identity_is_not_reduced_to_embedded_digits(get_mission, record_mission, _list):
    mission_id = "CMQ-20260813-02A"
    get_mission.side_effect = [({"status": "not_found"}, 404),
        ({"mission": {"mission_id": mission_id, "title": TITLE, "raw_text": RAW}}, 200)]
    record_mission.return_value = ({"mission_id": mission_id}, 201)
    result, status = execute_private_tool("create_mission",
        args(mission_id, portfolio_admission=None), context(mission_id))
    assert status == 200 and result["mission_id"] == mission_id
    assert record_mission.call_args.args[0]["mission_id"] == mission_id


def test_explicit_identity_requires_sealed_auth_and_exact_binding():
    for runtime_context in (None, {}, context("CMQ-OTHER-05")):
        result, status = execute_private_tool("create_mission", args(), runtime_context)
        assert status == 409 and result["success"] is False
    assert execute_private_tool("create_mission", args(), context("CMQ-OTHER-05"))[0]["status"] == \
        "explicit_mission_identity_binding_conflict"


def test_malformed_multiple_alias_and_conflicting_content_fail_closed():
    cases = [
        ("CMQ--20260813-05", "explicit_mission_identity_malformed"),
        ("CMQ-20260813-05 CMQ-20260813-06", "explicit_mission_identity_malformed"),
        ("cmq-20260813-05", "explicit_mission_identity_malformed"),
    ]
    for mission_id, expected in cases:
        result, status = execute_private_tool("create_mission", args(mission_id), context(mission_id))
        assert status == 409 and result["status"] == expected
    result, status = execute_private_tool("create_mission",
        args(title=f"{TITLE} for CMQ-20260813-99"), context("CMQ-20260813-05"))
    assert status == 409 and result["status"] == "explicit_mission_identity_content_conflict"
    result, status = execute_private_tool("create_mission",
        args(raw_text="x" * 3001), context("CMQ-20260813-05"))
    assert status == 409 and result["status"] == "explicit_mission_identity_content_invalid"


@patch("modules.charlie.private_tools.get_mission")
def test_exact_replay_returns_same_canonical_mission_without_write(get_mission):
    get_mission.return_value = ({"mission": {
        "mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
        "status": "paused", "metadata": {"portfolio_admission": ADMISSION}}}, 200)
    with patch("modules.charlie.private_tools.record_mission") as record:
        result, status = execute_private_tool("create_mission", args(), context("CMQ-20260813-05"))
    assert status == 200 and result["duplicate_prevented"] is True
    assert result["mission_id"] == "CMQ-20260813-05"
    record.assert_not_called()


@patch("modules.charlie.private_tools.get_mission")
def test_conflicting_exact_identity_replay_fails_without_write(get_mission):
    get_mission.return_value = ({"mission": {
        "mission_id": "CMQ-20260813-05", "title": "Different mission", "raw_text": "Different"}}, 200)
    with patch("modules.charlie.private_tools.record_mission") as record:
        result, status = execute_private_tool("create_mission", args(), context("CMQ-20260813-05"))
    assert status == 409 and result["status"] == "mission_identity_replay_conflict"
    record.assert_not_called()


@patch("modules.charlie.private_tools.get_mission", return_value=({"status": "not_found"}, 404))
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.list_missions")
def test_title_collision_under_other_identity_fails_closed(list_missions, record_mission, _get):
    list_missions.return_value = ({"missions": [{
        "mission_id": "CMQ-OTHER-01", "title": TITLE, "status": "approved"}]}, 200)
    result, status = execute_private_tool("create_mission", args(), context("CMQ-20260813-05"))
    assert status == 409 and result["status"] == "mission_title_identity_conflict"
    record_mission.assert_not_called()


def test_concurrent_exact_creation_converges_on_one_identity():
    lock = threading.Lock()
    durable = {}
    writes = []

    def get_mission(mission_id):
        with lock:
            if mission_id not in durable:
                return {"status": "not_found"}, 404
            return {"mission": dict(durable[mission_id])}, 200

    def record_mission(mission, source_context=None, exact_identity=False):
        assert exact_identity is True
        with lock:
            writes.append(mission["mission_id"])
            durable.setdefault(mission["mission_id"], {
                "mission_id": mission["mission_id"], "title": mission["title"],
                "raw_text": mission["raw_text"], "status": mission["status"],
                "metadata": dict(mission["metadata"])})
        return {"mission_id": mission["mission_id"]}, 201

    with patch("modules.charlie.private_tools.get_mission", side_effect=get_mission), \
         patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200)), \
         patch("modules.charlie.private_tools.record_mission", side_effect=record_mission):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: execute_private_tool(
                "create_mission", args(), context("CMQ-20260813-05")), range(2)))
    assert all(status == 200 and result["mission_id"] == "CMQ-20260813-05"
        for result, status in results)
    assert set(durable) == {"CMQ-20260813-05"}
    assert set(writes) <= {"CMQ-20260813-05"}


@patch("modules.charlie.private_tools.get_mission")
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
def test_legacy_authenticated_creation_without_explicit_id_is_unchanged(_list, record_mission, get_mission):
    record_mission.return_value = ({"mission_id": "CHARLIE-MISSION-GENERATED"}, 201)
    get_mission.return_value = ({"mission": {"mission_id": "CHARLIE-MISSION-GENERATED"}}, 200)
    result, status = execute_private_tool("create_mission", {"title": TITLE}, context("OWNER-BOUND-CONTEXT"))
    assert status == 200 and result["mission_id"] == "CHARLIE-MISSION-GENERATED"
    assert "mission_id" not in record_mission.call_args.args[0]


@patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
@patch("modules.charlie.private_tools.record_mission")
@patch("modules.charlie.private_tools.get_mission")
def test_bootstrap_admission_is_structured_non_runnable_and_verified(get_mission, record_mission, _list):
    get_mission.side_effect = [({"status": "not_found"}, 404), ({"mission": {
        "mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
        "status": "paused", "metadata": {"portfolio_admission": ADMISSION}}}, 200)]
    record_mission.return_value = ({"mission_id": "CMQ-20260813-05", "stored": True}, 201)
    result, status = execute_private_tool("create_mission",
        args(portfolio_admission=ADMISSION), context("CMQ-20260813-05"))
    assert status == 200 and result["verified"] is True
    mission = record_mission.call_args.args[0]
    assert mission["status"] == "paused"
    assert mission["metadata"]["portfolio_admission"] == ADMISSION
    assert result["portfolio_admission"] == ADMISSION


def test_bootstrap_admission_rejects_malformed_alias_and_other_mission_without_store_access():
    invalid = [None, [], {**ADMISSION, "runnable": True},
        {**ADMISSION, "portfolio_epoch": "CORE-CURRENT-OTHER"}]
    with patch("modules.charlie.private_tools.get_mission") as get_mission, \
         patch("modules.charlie.private_tools.record_mission") as record_mission:
        missing = args()
        missing.pop("portfolio_admission")
        result, status = execute_private_tool("create_mission", missing,
            context("CMQ-20260813-05"))
        assert status == 409 and result["status"] == "portfolio_admission_required"
        for value in invalid:
            supplied = "bad" if value is None else value
            result, status = execute_private_tool("create_mission",
                args(portfolio_admission=supplied), context("CMQ-20260813-05"))
            assert status == 409 and result["success"] is False
        result, status = execute_private_tool("create_mission",
            args("CMQ-20260813-02A", portfolio_admission=ADMISSION),
            context("CMQ-20260813-02A"))
    assert status == 409 and result["status"] == "portfolio_admission_not_authorized"
    get_mission.assert_not_called()
    record_mission.assert_not_called()


@patch("modules.charlie.private_tools.get_mission")
def test_bootstrap_exact_replay_requires_identical_admission_and_writes_nothing(get_mission):
    get_mission.return_value = ({"mission": {
        "mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
        "status": "paused", "metadata": {"portfolio_admission": ADMISSION}}}, 200)
    with patch("modules.charlie.private_tools.record_mission") as record:
        result, status = execute_private_tool("create_mission",
            args(portfolio_admission=ADMISSION), context("CMQ-20260813-05"))
    assert status == 200 and result["duplicate_prevented"] is True
    record.assert_not_called()

    get_mission.return_value = ({"mission": {
        "mission_id": "CMQ-20260813-05", "title": TITLE, "raw_text": RAW,
        "status": "paused", "metadata": {"portfolio_admission": {
            **ADMISSION, "lifecycle_state": "OWNER_HOLD"}}}}, 200)
    with patch("modules.charlie.private_tools.record_mission") as record:
        conflict, conflict_status = execute_private_tool("create_mission",
            args(portfolio_admission=ADMISSION), context("CMQ-20260813-05"))
    assert conflict_status == 409 and conflict["status"] == "mission_identity_replay_conflict"
    record.assert_not_called()
