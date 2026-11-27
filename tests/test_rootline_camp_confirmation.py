"""Production-shaped MQTT debug reports through the canonical camp duty."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.telemetry import rootline_home_assistant as ha
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry.rootline_camp_confirmation import confirmation, confirmed, report_after_command
from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
from tests.test_rootline_home_assistant import debug_fixture
from tests.test_rootline_command_mode import start, recover, NOW, receipt


def observation(active, state, at, *, reported_at=None, fault=None):
    devices, entities, states, debug = debug_fixture()
    for entity, item in zip(entities, debug["entities"]):
        channel = int(entity["entity_id"].rsplit("_", 1)[1])
        entity["entity_id"] = item["entity_id"] = f"switch.100204e9bc_{channel}"
        message = item["subscriptions"][0]["messages"][0]
        message.update(time=(reported_at or at).isoformat(), payload='{"state":"'+state+'"}', qos=0)
    selected = debug["entities"][active["channel"]-1]
    message = selected["subscriptions"][0]["messages"][0]
    if fault == "retained": message["retain"] = True
    if fault == "other_topic": message["topic"] += "/wrong"
    if fault == "unknown": message["payload"] = '{"state":"UNKNOWN"}'
    if fault == "conflict": selected["subscriptions"][0]["messages"].append({**message, "payload": '{"state":"OFF"}'})
    if fault == "missing": selected["subscriptions"][0]["messages"] = []
    if fault == "ack_only":
        selected["transmitted"] = deepcopy(selected["subscriptions"])
        selected["subscriptions"][0]["messages"] = []
    if fault == "newest_retained":
        selected["subscriptions"][0]["messages"].append({**message, "time":at.isoformat(), "retain":True})
    if fault == "newest_malformed":
        selected["subscriptions"][0]["messages"].append({**message, "time":at.isoformat(), "payload":"invalid"})
    class Client:
        def __init__(self, _): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, kind, **kwargs):
            return {"config/device_registry/list": devices, "config/entity_registry/list": entities,
                "mqtt/device/debug_info": debug}[kind]
    route = ha.read_command_route("100204e9bc", environ={}, now=at, client_factory=Client)
    return output_evidence_from_snapshot(route, device_id="100204e9bc", channel=active["channel"])


def setup(*, confirm=False):
    result, artifact, memory, transport, clock = start(confirm=confirm)
    class Store:
        def __call__(self, action, body):
            if action == "confirm_irrigation_controller":
                memory("mark_active", body)
                return {"success": True, "created": True, "execution": deepcopy(body)}
            return memory(action, body)
    return result, memory, Store(), transport, clock


@pytest.mark.parametrize("fault", ["retained", "other_topic", "unknown", "conflict", "missing", "ack_only", "newest_retained", "newest_malformed"])
def test_invalid_report_cannot_confirm(fault):
    _, memory, _, _, _ = setup()
    at = NOW + timedelta(seconds=10)
    assert confirmation(memory.active, observation(memory.active, "ON", at, fault=fault), now=at) is None


@pytest.mark.parametrize("offset", [-100, 0])
def test_old_or_same_time_report_cannot_confirm(offset):
    _, memory, _, _, _ = setup()
    at = NOW + timedelta(seconds=10)
    assert confirmation(memory.active, observation(memory.active, "ON", at,
        reported_at=NOW+timedelta(seconds=offset)), now=at) is None


def test_mqtt_cannot_confirm_but_actual_controller_receipt_cannot_be_rebound():
    _, memory, _, _, _ = setup()
    active = deepcopy(memory.active)
    active["command_on_receipt"]["accepted_at"] = (NOW+timedelta(seconds=10)).isoformat()
    active["command_on_receipt"]["receipt_sha256"] = ca.digest({k:v for k,v in active["command_on_receipt"].items() if k != "receipt_sha256"})
    at = NOW+timedelta(seconds=11)
    evidence = observation(active, "ON", at, reported_at=NOW+timedelta(seconds=5))
    assert confirmation(active, evidence, now=at) is None
    active["command_on_receipt"] = receipt(active, "ON", at=NOW)
    active["controller_confirmation"] = confirmation(active, evidence, now=at)
    assert confirmed(active)
    active["execution_id"] += "-other"
    assert not confirmed(active)


def test_requested_and_running_notices_follow_recorded_report():
    from modules.oom_sakkie.rootline_activity_presentation import activity_notice
    from modules.oom_sakkie.rootline_transition_notifications import transition
    from modules.telemetry.rootline_owner_control_projection import project_execution_event
    from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
    _, memory, _, _, _ = setup()
    active = {**memory.active,"action":"mark_active","event_id":"event"}
    assert transition(active)[0] == "Requested"
    assert "awaiting the controller report" in activity_notice("Requested", active)
    assert project_execution_event("event", NOW, active)["status"] == "confirmation_pending"
    assert project_zone_lifecycle(zone_id="B12345",recommendation={},execution=active)["state"] == "Requested"
    at = NOW+timedelta(seconds=10)
    active["command_on_receipt"] = receipt(active, "ON", at=NOW)
    active["controller_confirmation"] = confirmation(active, observation(active,"ON",at), now=at)
    assert transition(active)[0] == "Started"
    assert "ON accepted" in activity_notice("Started", active)
    assert project_execution_event("event", at, active)["status"] == "on_command_accepted"


def test_pending_legacy_parent_never_authorizes_injection_or_success_credit():
    result, memory, store, transport, clock = setup()
    assert result["execution"]["command_on_receipt"]
    assert not ca.active_command(memory.active, now=NOW)
    assert ca.active_irrigation_duty(memory.rows, now=NOW) is None
    assert any(row.get("notification_state") == "Requested" for row in memory.rows)
    clock[0] += timedelta(seconds=7201)
    done = recover(store, transport, clock)
    assert done["execution"]["commanded_runtime_seconds"] == 0
    assert not ca.program_completed(done["execution"])
    assert any(row.get("notification_state") == "Interrupted" for row in memory.rows)
    assert [call[2] for call in transport.calls] == ["ON", "OFF"]


def test_fresh_confirmation_survives_missing_report_and_restart_then_later_off_contains():
    _, memory, store, transport, clock = setup(confirm=True)
    clock[0] += timedelta(seconds=10)
    evidence = observation(memory.active, "ON", clock[0])
    transport.read_output_state = lambda **_: evidence
    assert recover(store, transport, clock)["status"] == "irrigation_command_duty_active"
    assert confirmed(memory.active)
    assert ca.active_irrigation_duty(memory.rows, now=clock[0])
    original = deepcopy(memory.active["controller_confirmation"])
    clock[0] += timedelta(minutes=20)
    transport.read_output_state = lambda **_: {}
    assert recover(store, transport, clock)["status"] == "irrigation_command_duty_active"
    assert memory.active["controller_confirmation"] == original
    assert len(transport.calls) == 1
    evidence = observation(memory.active, "OFF", clock[0])
    transport.read_output_state = lambda **_: evidence
    done = recover(store, transport, clock)
    assert done["execution"]["reason"] == "controller_reported_off"
    assert done["execution"]["commanded_runtime_seconds"] == 0
    assert not ca.job_completed(done["execution"])
    assert [call[2] for call in transport.calls] == ["ON", "OFF"]
    assert recover(store, transport, clock)["hardware_commands"] == 0


def test_repeated_off_with_unchanged_entity_clock_interrupts_pending_command():
    _, memory, store, transport, clock = setup()
    clock[0] += timedelta(seconds=13)
    evidence = observation(memory.active, "OFF", clock[0])
    # HA last_changed is deliberately absent: original MQTT time is sufficient.
    assert report_after_command(memory.active, evidence, now=clock[0])["state"] == "OFF"
    transport.read_output_state = lambda **_: evidence
    done = recover(store, transport, clock)
    assert done["execution"]["reason"] == "controller_reported_off"
    assert [call[2] for call in transport.calls] == ["ON", "OFF"]


def test_actual_ack_then_native_off_revokes_parent_without_calling_controller_offline():
    from tests.test_rootline_command_mode import route
    _, memory, store, transport, clock = setup(confirm=True)
    clock[0] += timedelta(seconds=78)
    active = memory.active
    snap = route(active["device_id"], now=clock[0])
    native = {"device_id": active["device_id"], "observer_qualified": True, "observer_epoch": "a"*32,
        "channels": [{"channel": active["channel"], "entity_id": active["command_on_receipt"]["entity_id"],
            "output_state": "OFF", "observation_fresh": True, "observed_at": clock[0].isoformat(), "observation_source": "mdns"}]}
    native["response_digest"] = ca.digest(native)
    snap["controller_observation"] = native
    snap["controller_availability"] = {"state": "online", "source": "correlated_controller_query", "checked_at": clock[0].isoformat()}
    snap["response_digest"] = ca.digest({k:v for k,v in snap.items() if k != "response_digest"})
    transport.read_output_state = lambda **_: output_evidence_from_snapshot(snap, device_id=active["device_id"], channel=active["channel"])
    done = recover(store, transport, clock)
    assert done["execution"]["reason"] == "controller_reported_off"
    assert not ca.program_completed(done["execution"])
    assert ca.active_irrigation_duty(memory.rows, now=clock[0]) is None
    assert snap["controller_availability"]["state"] == "online"


def test_read_crossing_deadline_stops_without_confirmation():
    _, memory, store, transport, clock = setup()
    clock[0] += timedelta(seconds=7199)
    def read(**kwargs):
        clock[0] += timedelta(seconds=3)
        return observation(memory.active, "ON", clock[0])
    transport.read_output_state = read
    done = recover(store, transport, clock)
    assert not ca.program_completed(done["execution"])
    assert [call[2] for call in transport.calls] == ["ON", "OFF"]


def test_owned_checkpoint_precedes_confirmation_and_off(monkeypatch):
    from modules.telemetry import rootline_owned_deadlines
    _, memory, store, transport, clock = setup()
    clock[0] += timedelta(seconds=20)
    order = []
    monkeypatch.setattr(rootline_owned_deadlines, "check_owned_deadline", lambda: order.append("deadline"))
    def read(**kwargs):
        order.append("read")
        return observation(memory.active, "OFF", clock[0])
    transport.read_output_state = read
    send = transport.set_state
    def stop(**kwargs):
        order.append("OFF")
        return send(**kwargs)
    transport.set_state = stop
    recover(store, transport, clock)
    assert order == ["deadline", "read", "deadline", "OFF"]


def test_historical_command_interval_is_display_only_and_notice_identity_stable():
    from modules.telemetry.rootline_camp_confirmation import historical_command_interval
    from modules.telemetry.rootline_owner_control_projection import project_execution_event
    from modules.oom_sakkie.rootline_transition_notifications import transition
    from modules.oom_sakkie.rootline_activity_presentation import activity_notice
    _, memory, _, _, _ = setup()
    off = receipt(memory.active, "OFF", at=NOW+timedelta(seconds=3600))
    current = ca.terminal(memory.active, off, now=NOW+timedelta(seconds=3600))
    assert current["controller_confirmation_required"] is True
    assert historical_command_interval(current) is None and ca.command_seconds(current) == 0
    old = {**current,"action":"record_completed","event_id":"historical", "command_program_completed":True}
    old.pop("controller_confirmation_required")
    assert historical_command_interval(old) == 3600
    assert ca.command_seconds(old) == 0 and not ca.program_completed(old)
    assert not ca.active_command({**old,"state":"Active"},now=NOW+timedelta(seconds=40))
    assert transition(old)[0] == "Completed"  # Preserve the prior delivered event identity.
    text = activity_notice("Completed",old)
    assert "controller run unconfirmed" in text and "Programme completed" not in text
    display = project_execution_event("historical",NOW,old)
    assert "60.0 historical command minutes" in display["summary"] and display["accounted_seconds"] == 0
    failed = {**current,"action":"record_completed","event_id":"failed","controller_contradiction":{"state":"OFF"}}
    assert transition(failed)[0] == "Interrupted"
    assert historical_command_interval(failed) is None and ca.command_seconds(failed) == 0
