import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from modules.telemetry import rootline_home_assistant as ha
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport

NOW = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)
ENV = {"ROOTLINE_SONOFF_TRANSPORT": "home_assistant",
       "ROOTLINE_HOME_ASSISTANT_URL": "https://ha.example.test",
       "ROOTLINE_HOME_ASSISTANT_TOKEN": "test-secret"}


def fixture(device_id="100204e9bc"):
    devices = [{"id": "registry-device", "identifiers": [["mqtt", device_id]],
                "manufacturer": "SONOFF", "model": ha.MODELS[device_id], "sw_version": "3.8.2"}]
    channels = range(1, 2 if device_id == "1002851416" else 5)
    entities = [{"entity_id": f"switch.renamed_{channel}", "platform": "mqtt",
        "unique_id": ha._unique_id(device_id, channel), "device_id": "registry-device"}
        for channel in channels]
    states = [{"entity_id": row["entity_id"], "state": "off", "last_reported": NOW.isoformat()}
              for row in entities]
    return devices, entities, states


def debug_fixture():
    devices, entities, states = fixture()
    debug = {"entities": []}
    for channel, entity in enumerate(entities, 1):
        topic = f"cube2ha/switch/100204e9bc/toggle_{channel}/state"
        availability = "cube2ha/100204e9bc/availability"
        message = {"topic": topic, "retain": False, "time": NOW.isoformat(), "payload": '{"state":"OFF"}'}
        debug["entities"].append({"entity_id": entity["entity_id"],
            "discovery_data": {"payload": {"unique_id": entity["unique_id"], "platform": "switch",
                "state_topic": topic, "command_topic": topic[:-5] + "set",
                "availability_topic": availability, "value_template": "{{ value_json.state }}",
                "device": {"identifiers": "100204e9bc", "manufacturer": "SONOFF", "model": "4CHPROR3"}}},
            "subscriptions": [{"topic": topic, "messages": [message]},
                {"topic": availability, "messages": [{"topic": availability, "retain": True,
                    "time": NOW.isoformat(), "payload": '{"online":true}'}]}],
            "transmitted": []})
    return devices, entities, states, debug


class HomeAssistantTests(unittest.TestCase):
    def test_nonretained_report_remains_unproven_hardware_origin(self):
        snap = ha.mqtt_snapshot("100204e9bc", *debug_fixture(), now=NOW)
        self.assertTrue(snap["mqtt_reports_fresh"])
        self.assertFalse(snap["current_outputs_authoritative"])
        self.assertEqual(snap["retrieved_at"], NOW.isoformat())
        self.assertFalse(snap["actuation_configuration_safe"])

    def test_retained_transmitted_stale_future_and_conflicting_reports_fail(self):
        for fault in ("retained", "transmitted", "stale", "future", "conflict", "offline", "wrong_topic"):
            devices, entities, states, debug = debug_fixture()
            entity = debug["entities"][0]
            messages = entity["subscriptions"][0]["messages"]
            if fault == "retained": messages[0]["retain"] = True
            if fault == "transmitted":
                entity["transmitted"] = [entity["subscriptions"][0]]
                entity["subscriptions"][0]["messages"] = []
            if fault == "stale": messages[0]["time"] = (NOW-timedelta(minutes=6)).isoformat()
            if fault == "future": messages[0]["time"] = (NOW+timedelta(seconds=1)).isoformat()
            if fault == "conflict": messages.append({**messages[0], "payload": '{"state":"ON"}'})
            if fault == "offline": entity["subscriptions"][1]["messages"][0]["payload"] = '{"online":false}'
            if fault == "wrong_topic": messages[0]["topic"] += "/wrong"
            with self.subTest(fault=fault):
                snap = ha.mqtt_snapshot("100204e9bc", devices, entities, states, debug, now=NOW)
                self.assertFalse(snap["current_outputs_authoritative"])
                self.assertIsNone(snap["retrieved_at"])

    def test_discovery_topic_cannot_redirect_control_binding(self):
        devices, entities, states, debug = debug_fixture()
        debug["entities"][0]["discovery_data"]["payload"]["command_topic"] = "other/device/set"
        with self.assertRaises(ha.HomeAssistantUnavailable):
            ha.mqtt_snapshot("100204e9bc", devices, entities, states, debug, now=NOW)

    def observer_envelope(self):
        return {"contract_version": "rootline_sonoff_observation.v1", "device_id": "100204e9bc",
            "model": "4CHPROR3", "uiid": 4, "control_commands": 0, "maximum_age_seconds": 60,
            "source_authentication": "unauthenticated_sonoff_lan_protocol", "observer_epoch": "a" * 32,
            "generation": "test-generation", "qualification_id": "test-qualification", "generated_at": NOW.isoformat(),
            "channels": [{"channel": channel, "state": "OFF", "fresh": True, "received_at": NOW.isoformat(),
                "age_seconds": 0, "source": "query", "sequence_kind": "request_echo", "sequence": "1795286400000",
                "report_digest": "b" * 64} for channel in range(1, 5)]}

    def test_observer_requires_exact_qualification_and_original_receipts(self):
        import json
        devices, entities, _ = fixture()
        envelope = self.observer_envelope()
        snap = ha.observer_snapshot("100204e9bc", devices, entities, envelope, now=NOW, environ=ENV)
        self.assertFalse(snap["current_outputs_authoritative"])
        self.assertEqual(snap["device_uiid"], 4)
        source = {**ENV, "ROOTLINE_HOME_ASSISTANT_OBSERVER_BINDINGS": json.dumps({"100204e9bc": {
            "generation": "test-generation", "qualification_id": "test-qualification"}})}
        snap = ha.observer_snapshot("100204e9bc", devices, entities, envelope, now=NOW, environ=source)
        self.assertTrue(snap["current_outputs_authoritative"])
        self.assertEqual(snap["retrieved_at"], NOW.isoformat())
        envelope["channels"][0]["received_at"] = (NOW-timedelta(seconds=61)).isoformat()
        snap = ha.observer_snapshot("100204e9bc", devices, entities, envelope, now=NOW, environ=source)
        self.assertFalse(snap["current_outputs_authoritative"])
        self.assertIsNone(snap["retrieved_at"])

    def test_observer_wrong_identity_channel_clock_or_uiid_is_rejected(self):
        devices, entities, _ = fixture()
        for fault in ("device_id", "uiid", "clock", "duplicate"):
            envelope = self.observer_envelope()
            if fault == "device_id": envelope["device_id"] = "100204d497"
            if fault == "uiid": envelope["uiid"] = 9
            if fault == "clock": envelope["generated_at"] = (NOW+timedelta(seconds=1)).isoformat()
            if fault == "duplicate": envelope["channels"][0]["channel"] = 2
            with self.subTest(fault=fault), self.assertRaises(ha.HomeAssistantUnavailable):
                ha.observer_snapshot("100204e9bc", devices, entities, envelope, now=NOW, environ=ENV)

    def test_backend_query_refresh_requires_existing_qualification_and_enablement(self):
        import json
        from copy import deepcopy
        devices, entities, _ = fixture()
        fresh = self.observer_envelope()
        stale = deepcopy(fresh)
        for row in stale["channels"]:
            row.update(fresh=False, state="Unknown", age_seconds=70,
                received_at=(NOW-timedelta(seconds=70)).isoformat())
        for qualified, enabled in ((False, True), (True, False), (True, True)):
            calls = []
            class Client:
                def __init__(self, _): pass
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def request(self, kind, **fields):
                    calls.append(kind)
                    if kind == "config/device_registry/list": return devices
                    if kind == "config/entity_registry/list": return entities
                    if kind == "rootline_observer/snapshot": return stale
                    if kind == "rootline_observer/query": return fresh
                    raise AssertionError(kind)
            source = {**ENV, "ROOTLINE_HOME_ASSISTANT_OBSERVER_QUERY_ENABLED": str(enabled).lower()}
            if qualified:
                source["ROOTLINE_HOME_ASSISTANT_OBSERVER_BINDINGS"] = json.dumps({"100204e9bc": {
                    "generation": "test-generation", "qualification_id": "test-qualification"}})
            value = ha.read_registered_device("100204e9bc", environ=source, now=NOW, client_factory=Client)
            self.assertEqual(calls.count("rootline_observer/query"), int(qualified and enabled))
            self.assertEqual(value["current_outputs_authoritative"], qualified and enabled)

    def test_default_and_invalid_selection(self):
        self.assertFalse(ha.selected({}))
        with self.assertRaises(ha.HomeAssistantUnavailable):
            ha.selected({"ROOTLINE_SONOFF_TRANSPORT": "typo"})

    def test_reject_credentials_and_untrusted_endpoint_shapes(self):
        for url in ("http://ha.test", "https://user:password@ha.test", "https://ha.test/path", "https://ha.test?x=1"):
            with self.subTest(url=url), self.assertRaises(ha.HomeAssistantUnavailable):
                ha.configuration({**ENV, "ROOTLINE_HOME_ASSISTANT_URL": url})

    def test_entity_names_are_resolved_by_exact_unique_id(self):
        devices, entities, _ = fixture()
        self.assertEqual(ha.bind_entities("100204e9bc", devices, entities)[1][1], "switch.renamed_1")
        entities[0]["device_id"] = "wrong-device"
        with self.assertRaises(ha.HomeAssistantUnavailable):
            ha.bind_entities("100204e9bc", devices, entities)

    def test_duplicate_and_wrong_model_fail_closed(self):
        devices, entities, _ = fixture()
        with self.assertRaises(ha.HomeAssistantUnavailable):
            ha.bind_entities("100204e9bc", devices, entities + [entities[0]])
        devices[0]["model"] = "MINIR4"
        with self.assertRaises(ha.HomeAssistantUnavailable):
            ha.bind_entities("100204e9bc", devices, entities)

    def test_fresh_ha_cache_is_not_hardware_proof(self):
        snap = ha.normalize_snapshot("100204e9bc", *fixture(), now=NOW)
        self.assertTrue(snap["entity_reports_fresh"])
        self.assertFalse(snap["current_outputs_authoritative"])
        self.assertEqual(snap["online"], "Unknown")
        self.assertFalse(snap["actuation_configuration_safe"])

    def test_stale_future_or_missing_report_never_retimestamped(self):
        for clock in (None, (NOW-timedelta(hours=1)).isoformat(), (NOW+timedelta(seconds=1)).isoformat()):
            devices, entities, states = fixture()
            for row in states:
                row["last_reported"] = clock
                row["last_updated"] = NOW.isoformat()
            snap = ha.normalize_snapshot("100204e9bc", devices, entities, states, now=NOW)
            self.assertFalse(snap["entity_reports_fresh"])
            self.assertFalse(snap["current_outputs_authoritative"])
            self.assertEqual(snap["channels"][0]["observed_at"], clock)

    def test_transport_selection_never_falls_back_to_ewelink(self):
        transport = RootlineIFTTTTransport(token_store=None, environ=ENV,
            readback=lambda **_: self.fail("legacy readback used"))
        with patch.object(ha, "read_registered_device", return_value=ha.normalize_snapshot("100204e9bc", *fixture(), now=NOW)):
            self.assertFalse(transport.read_output_state(device_id="100204e9bc", channel=1)["authoritative"])
        with patch.object(ha, "send_state") as send:
            result = transport.set_state(device_id="100204e9bc", channel=1, state="ON", idempotency_key="EXEC:ON")
            self.assertFalse(result["provider_command_attempted"])
            send.assert_not_called()

    def test_off_send_failure_is_not_retried(self):
        devices, entities, _ = fixture()
        calls = []
        class Client:
            def __init__(self, _): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def request(self, kind, **fields):
                calls.append((kind, fields))
                if kind == "config/device_registry/list": return devices
                if kind == "config/entity_registry/list": return entities
                if kind == "mqtt/device/debug_info": return debug_fixture()[3]
                raise TimeoutError("secret transport detail")
        result = ha.send_state(environ=ENV, device_id="100204e9bc", channel=1,
                               state="OFF", client_factory=Client)
        self.assertEqual(result["status"], "provider_outcome_ambiguous")
        self.assertTrue(result["provider_command_attempted"])
        self.assertEqual(len([c for c in calls if c[0] == "call_service"]), 1)
        self.assertNotIn("secret", repr(result))
        self.assertEqual(calls[-1][1]["target"], {"entity_id": "switch.renamed_1"})

if __name__ == "__main__": unittest.main()


class BackendEdgeTests(unittest.TestCase):
    def test_borehole_refreshes_at_consumer_age_without_retimestamping(self):
        import json
        from copy import deepcopy
        devices, entities, _ = fixture("1002851416")
        for age, expected in ((0, 0), (30, 0), (31, 1), (60, 1)):
            envelope = HomeAssistantTests().observer_envelope()
            envelope.update(device_id="1002851416", model="MINIR4", uiid=138)
            envelope["channels"] = envelope["channels"][:1]
            envelope["channels"][0].update(age_seconds=age, received_at=(NOW-timedelta(seconds=age)).isoformat())
            fresh = deepcopy(envelope)
            fresh["channels"][0].update(age_seconds=0, received_at=NOW.isoformat())
            calls = []
            class Client:
                def __init__(self, _): pass
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def request(self, kind, **fields):
                    calls.append(kind)
                    return {"config/device_registry/list": devices, "config/entity_registry/list": entities,
                        "rootline_observer/snapshot": envelope, "rootline_observer/query": fresh}[kind]
            env = {**ENV, "ROOTLINE_HOME_ASSISTANT_OBSERVER_QUERY_ENABLED": "true",
                "ROOTLINE_HOME_ASSISTANT_OBSERVER_BINDINGS": json.dumps({"1002851416": {
                    "generation":"test-generation", "qualification_id":"test-qualification"}})}
            result = ha.read_registered_device("1002851416", environ=env, now=NOW, client_factory=Client)
            with self.subTest(age=age):
                self.assertEqual(calls.count("rootline_observer/query"), expected)
                self.assertEqual(result["retrieved_at"], (NOW if expected else NOW-timedelta(seconds=age)).isoformat())

    def test_low_level_on_requires_final_finite_unexpired_guard_after_preparation(self):
        devices, entities, _, debug = debug_fixture()
        for deadline, accepted in ((None, False), (True, False), (float("nan"), False),
                (float("inf"), False), (999, False), (1000, False), (1001, True)):
            calls = []
            class Client:
                def __init__(self, _): pass
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def request(self, kind, **fields):
                    calls.append(kind)
                    return {"config/device_registry/list": devices, "config/entity_registry/list": entities,
                        "mqtt/device/debug_info": debug, "call_service": {}}[kind]
            def guard():
                self.assertEqual(calls, ["config/device_registry/list", "config/entity_registry/list", "mqtt/device/debug_info"])
                return deadline
            with patch.object(ha.time, "monotonic", return_value=1000):
                result = ha.send_state(environ=ENV, device_id="100204e9bc", channel=1, state="ON",
                    on_guard=None if deadline is None else guard, client_factory=Client)
            with self.subTest(deadline=deadline):
                self.assertEqual(result["provider_command_attempted"], accepted)
                self.assertEqual(calls.count("call_service"), int(accepted))

    def test_only_exact_fresh_owned_borehole_can_prepare_on_guard(self):
        from copy import deepcopy
        from modules.telemetry import rootline_ifttt_transport as transport_module
        from modules.telemetry.rootline_device_registry import find_device_contract
        from modules.telemetry import rootline_ewelink_request_budget as budget
        from modules.telemetry import rootline_cycle_budget as cycle
        class Clock(datetime):
            value = NOW
            @classmethod
            def now(cls, tz=None): return cls.value
        duty = {"contract_version":"rootline_borehole_runtime_eligibility.v5", "stop_mode":"conditions",
            "device_key":"ewelink:ewelink_owner_account:1002851416:1", "device_id":"1002851416",
            "channel":1, "auxiliary_device_id":"BOREHOLE-1-MINI-R4-CH1", "requested_seconds":None,
            "native_fail_stop_seconds":0, "state":"claimed", "on_attempts":0,
            "execution_id":"ROOTLINE-BOREHOLE-TEST", "operation":"command_off_to_on",
            "claimed_at":NOW.isoformat(), "primary_stop_deadline":None, "native_fail_stop_deadline":None,
            "provider_capacity_permit":"home_assistant:"+"a"*64,
            "condition_evidence":{"event_id":"condition-proof", "assessed_at":NOW.isoformat(),
                "start_eligible":True,"stop_required":False,"protection_safe":True},
            "energy_context":{"observed_at":NOW.isoformat(),"battery_soc_pct":57,"solar_power_w":0,
                "grid_power_w":0,"load_power_w":1000,"battery_power_w":1254}}
        snapshot = {"device_id":"1002851416", "device_model":"MINIR4", "device_uiid":138,
            "current_outputs_authoritative":True,"observer_qualified":True,
            "freshness_clock_source":"sonoff_original_observation", "retrieved_at":NOW.isoformat(),
            "online":True,"observation_fresh":True,"provider_control_calls":0,"response_digest":"b"*64,
            "channels":[{"channel":1,"output_state":"OFF","native_auto_off_enabled":False}]}
        contract = find_device_contract("1002851416", 1)
        transport = RootlineIFTTTTransport(token_store=None, environ={**ENV, contract["authority_flag"]:"true"})
        for fault in (None,"old_claim","future_claim","deadline","adoption","wrong_permit","rain","protection",
                "low_power","sunshine","stale_power","unknown_timer","unqualified","stale_output","on_output"):
            item, snap = deepcopy(duty), deepcopy(snapshot)
            if fault == "old_claim": item["claimed_at"]=(NOW-timedelta(seconds=31)).isoformat()
            if fault == "future_claim": item["claimed_at"]=(NOW+timedelta(seconds=1)).isoformat()
            if fault == "deadline": item["primary_stop_deadline"]=NOW.isoformat()
            if fault == "adoption": item["operation"]="adopt_observed_on"
            if fault == "wrong_permit": item["provider_capacity_permit"]="unbound"
            if fault == "rain": item["condition_evidence"]["stop_required"]=True
            if fault == "protection": item["condition_evidence"]["protection_safe"]=False
            if fault == "low_power": item["energy_context"]["battery_soc_pct"]=30
            if fault == "sunshine": item["energy_context"]["solar_power_w"]=1500
            if fault == "stale_power": item["energy_context"]["observed_at"]=(NOW-timedelta(minutes=16)).isoformat()
            if fault == "unknown_timer": snap["channels"][0]["native_auto_off_enabled"]="Unknown"
            if fault == "unqualified": snap["observer_qualified"]=False
            if fault == "stale_output": snap["retrieved_at"]=(NOW-timedelta(seconds=31)).isoformat()
            if fault == "on_output": snap["channels"][0]["output_state"]="ON"
            with self.subTest(fault=fault), patch.object(transport_module,"datetime",Clock), \
                    patch.object(budget,"current_duty",return_value=item), \
                    patch.object(cycle,"on_deadline",return_value=1010), \
                    patch.object(transport_module.time,"monotonic",return_value=1000), \
                    patch.object(transport,"_snapshot",return_value=snap):
                Clock.value=NOW
                if fault is not None:
                    with self.assertRaises(ValueError):
                        transport._home_assistant_borehole_on_guard(contract,"1002851416",1,item["execution_id"]+":ON")
                else:
                    guard=transport._home_assistant_borehole_on_guard(contract,"1002851416",1,item["execution_id"]+":ON")
                    self.assertEqual(guard(),1010)
                    Clock.value=NOW+timedelta(seconds=31)
                    with self.assertRaises(ValueError): guard()


class FinalSendTimingTests(unittest.TestCase):
    def test_delayed_attempt_callback_cannot_send_past_admission(self):
        devices, entities, _, debug = debug_fixture()
        now, calls = [1000.0], []
        class Client:
            def __init__(self, _): self.deadline=1015
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def request(self, kind, **fields):
                calls.append(kind)
                return {"config/device_registry/list":devices,"config/entity_registry/list":entities,
                    "mqtt/device/debug_info":debug,"call_service":{}}[kind]
        def attempt(): now[0]=1002
        with patch.object(ha.time,"monotonic",side_effect=lambda:now[0]):
            result=ha.send_state(environ=ENV,device_id="100204e9bc",channel=1,state="ON",
                on_guard=lambda:1001,network_attempt=attempt,client_factory=Client)
        self.assertFalse(result["provider_command_attempted"])
        self.assertNotIn("call_service",calls)

    def test_on_client_budget_is_clamped_to_original_final_deadline(self):
        devices, entities, _, debug = debug_fixture()
        class Client:
            def __init__(self, _): self.deadline=1015
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def request(inner,kind,**fields):
                if kind=="call_service":
                    self.assertEqual(inner.deadline,1001)
                    self.assertEqual(inner.command_deadline,1001)
                return {"config/device_registry/list":devices,"config/entity_registry/list":entities,
                    "mqtt/device/debug_info":debug,"call_service":{}}[kind]
        deadlines=iter([1001,1004])
        with patch.object(ha.time,"monotonic",return_value=1000):
            result=ha.send_state(environ=ENV,device_id="100204e9bc",channel=1,state="ON",
                on_guard=lambda:next(deadlines),client_factory=Client)
        self.assertTrue(result["provider_command_attempted"])

    def test_actual_exchange_rechecks_deadline_before_socket_send(self):
        import asyncio
        calls=[]
        class Socket:
            async def send_json(self, message): calls.append(message)
        client=ha.HomeAssistantClient(ENV)
        client.loop=asyncio.new_event_loop()
        client.socket=Socket()
        client.deadline=ha.time.monotonic()+15
        client.command_deadline=ha.time.monotonic()-1
        try:
            with self.assertRaises(ha.HomeAssistantUnavailable):
                client.request("call_service",domain="switch",service="turn_on",target={"entity_id":"switch.synthetic"})
            self.assertEqual(calls,[])
        finally: client.close()


class PostCommandEvidenceTests(unittest.TestCase):
    def test_pre_command_fresh_state_never_proves_command_effect(self):
        import json
        from copy import deepcopy
        devices, entities, _ = fixture()
        fresh = HomeAssistantTests().observer_envelope()
        old = deepcopy(fresh)
        for row in old["channels"]:
            row.update(received_at=(NOW-timedelta(seconds=2)).isoformat(),age_seconds=2)
        for enabled, returned_new in ((False,False),(True,False),(True,True)):
            calls=[]
            class Client:
                def __init__(self,_):pass
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def request(self,kind,**fields):
                    calls.append(kind)
                    return {"config/device_registry/list":devices,"config/entity_registry/list":entities,
                        "rootline_observer/snapshot":old,"rootline_observer/query":fresh if returned_new else old}[kind]
            source={**ENV,"ROOTLINE_HOME_ASSISTANT_OBSERVER_QUERY_ENABLED":str(enabled).lower(),
                "ROOTLINE_HOME_ASSISTANT_OBSERVER_BINDINGS":json.dumps({"100204e9bc":{
                    "generation":"test-generation","qualification_id":"test-qualification"}})}
            result=ha.read_registered_device("100204e9bc",environ=source,now=NOW,
                not_before=(NOW-timedelta(seconds=1)).isoformat(),client_factory=Client)
            with self.subTest(enabled=enabled,returned_new=returned_new):
                self.assertEqual(calls.count("rootline_observer/query"),int(enabled))
                self.assertEqual(result["current_outputs_authoritative"],enabled and returned_new)
                if not returned_new:
                    self.assertEqual(result["channels"][0]["observed_at"],(NOW-timedelta(seconds=2)).isoformat())
                    self.assertEqual(result["channels"][0]["output_state"],"Unknown")

    def test_transport_carries_attempt_clock_only_to_exact_output_read(self):
        transport=RootlineIFTTTTransport(token_store=None,environ=ENV)
        with patch.object(ha,"send_state",return_value={"provider_command_attempted":True,
                "accepted_unambiguous":False,"status":"provider_outcome_ambiguous","command_attempted_at":NOW.isoformat()}):
            result=transport.set_state(device_id="100204e9bc",channel=1,state="OFF",idempotency_key="OWNED:OFF:1")
        self.assertTrue(result["provider_command_attempted"])
        snap=ha.normalize_snapshot("100204e9bc",*fixture(),now=NOW)
        with patch.object(ha,"read_registered_device",return_value=snap) as read:
            transport.read_output_state(device_id="100204e9bc",channel=1)
            self.assertEqual(read.call_args.kwargs["not_before"],NOW.isoformat())
            transport.read_output_state(device_id="100204e9bc",channel=2)
            self.assertNotIn("not_before",read.call_args.kwargs)

    def test_missing_attempt_clock_refuses_cached_read(self):
        transport=RootlineIFTTTTransport(token_store=None,environ=ENV)
        with patch.object(ha,"send_state",return_value={"provider_command_attempted":True,"status":"accepted"}):
            transport.set_state(device_id="100204e9bc",channel=1,state="OFF",idempotency_key="OWNED:OFF:1")
        with patch.object(ha,"read_registered_device") as read:
            with self.assertRaises(RuntimeError):transport.read_output_state(device_id="100204e9bc",channel=1)
            read.assert_not_called()


class CanonicalTimerTests(unittest.TestCase):
    def test_current_configuration_retains_original_clocks_and_fails_closed(self):
        from copy import deepcopy
        from unittest.mock import MagicMock
        payload = {"http_status": 200, "params": {"device_id": "1002851416"},
            "body": {"device_id": "1002851416", "firmware": "1.2.0", "channels": [
                {"channel": 1, "native_auto_off_enabled": False, "native_auto_off_seconds": 36000}]}}
        observed = (NOW-timedelta(days=5)).isoformat()
        snapshot = {"device_id": "1002851416", "device_model": "MINIR4", "device_uiid": 138,
            "firmware": "1.2.0", "retrieved_at": (NOW-timedelta(hours=2)).isoformat(),
            "current_outputs_authoritative": False, "observation_fresh": False,
            "channels": [{"channel": 1, "output_state": "Unknown", "observation_fresh": False,
                "observed_at": (NOW-timedelta(hours=2)).isoformat(), "native_auto_off_enabled": "Unknown"}]}
        faults = (None, "invalidated", "payload_hash", "reference_hash", "wrong_device", "wrong_channel",
            "timer_enabled", "timer_missing", "wrong_firmware", "future", "resolver_invalid", "no_record",
            "wrong_profile", "not_active", "wrong_source", "seconds_bool", "params_wrong", "http_failed")
        for fault in faults:
            with self.subTest(fault=fault):
                material = deepcopy(payload)
                if fault == "wrong_device": material["body"]["device_id"]="other"
                if fault == "wrong_channel": material["body"]["channels"][0]["channel"]=2
                if fault == "timer_enabled": material["body"]["channels"][0]["native_auto_off_enabled"]=True
                if fault == "timer_missing": del material["body"]["channels"][0]["native_auto_off_enabled"]
                if fault == "wrong_firmware": material["body"]["firmware"]="2.0.0"
                if fault == "seconds_bool": material["body"]["channels"][0]["native_auto_off_seconds"]=True
                if fault == "params_wrong": material["params"]["device_id"]="other"
                if fault == "http_failed": material["http_status"]=503
                digest = ha._digest(material)
                reference = {"source":"provider", "evidence_id":"provider-config", "sha256":digest,
                    "observed_at": observed}
                if fault == "future": reference["observed_at"]=(NOW+timedelta(seconds=1)).isoformat()
                if fault == "wrong_source": reference["source"]="canonical"
                loaded = {"registry_generation":6, "device_record":{"standing_authority":True,
                    "commissioning_stage":"standing_active", "commissioning_evidence":{"provider_readback":reference}}}
                if fault == "not_active": loaded["device_record"]["standing_authority"]=False
                if fault == "payload_hash": material["extra"]="unsealed"
                connect = MagicMock()
                connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (
                    material, "f"*64 if fault == "reference_hash" else digest, fault != "invalidated")
                resolved = {"evidence_id":"provider-config", "sha256":digest, "current":fault != "resolver_invalid"}
                with patch("modules.telemetry.rootline_device_spine.load_device_record", return_value=None if fault == "no_record" else loaded) as loader, patch(
                        "modules.telemetry.rootline_device_spine.CanonicalAuthorityResolver.evidence", return_value=resolved), patch(
                        "modules.telemetry.rootline_borehole_conditions.continuous_device_profile", return_value=fault not in {"wrong_profile","no_record"}):
                    result = ha.canonical_borehole_timer(snapshot, connect_factory=connect, now=NOW)
                loader.assert_called_once_with("ewelink:ewelink_owner_account:1002851416:1", connect_factory=connect)
                if fault:
                    self.assertEqual(result, snapshot)
                else:
                    self.assertIs(result["channels"][0]["native_auto_off_enabled"], False)
                    self.assertEqual(result["channels"][0]["native_auto_off_observed_at"], observed)
                    self.assertEqual(result["channels"][0]["native_auto_off_registry_generation"], 6)
                    self.assertEqual(result["retrieved_at"], snapshot["retrieved_at"])
                    self.assertIs(result["current_outputs_authoritative"], False)
                    self.assertIs(result["observation_fresh"], False)
                    self.assertEqual(result["channels"][0]["output_state"], "Unknown")
                    self.assertEqual(snapshot["channels"][0]["native_auto_off_enabled"], "Unknown")
