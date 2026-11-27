"""Offline protocol and actual zeroconf-record tests; never opens a device socket."""
import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import types

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "deploy/home-assistant/custom_components/rootline_observer"
namespace = types.ModuleType("rootline_observer_test")
namespace.__path__ = [str(PACKAGE)]
sys.modules.setdefault("rootline_observer_test", namespace)
p = importlib.import_module("rootline_observer_test.protocol")
IDENTITY = "100204e9bc"


class Clock:
    def __init__(self):
        self.mono = 1000.0
        self.wall = datetime(2026, 11, 21, 18, tzinfo=timezone.utc)
    def advance(self, seconds):
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


def setup_state(persisted=None, generation="fixture-generation", endpoint=False):
    clock = Clock()
    # A new random synthetic key per test; no key literal or real key fixture.
    device = {"model": "4CHPROR3", "uiid": 4, "generation": generation,
              "device_key": os.urandom(16).hex()}
    if endpoint:
        device["endpoint"] = {"address": "10.0.0.2", "port": 8081, "binding_id": "fixture-binding"}
    config = {"allowed_user_ids": ["1" * 32], "devices": {IDENTITY: device}}
    state = p.ObserverState(config, persisted, monotonic=lambda: clock.mono, utcnow=lambda: clock.wall)
    return clock, state


def params(channels=range(4), state="off"):
    return {"switches": [{"outlet": channel, "switch": state} for channel in channels]}


def encrypted(value, key):
    iv = os.urandom(16)
    data = p.crypt(json.dumps(value, separators=(",", ":")).encode(), key, iv, encrypt=True)
    return {"data": base64.b64encode(data).decode(), "iv": base64.b64encode(iv).decode()}


def wire(state, seq, value=None):
    envelope = encrypted(params() if value is None else value, state.config["devices"][IDENTITY]["device_key"])
    fields = {"id": IDENTITY, "type": "strip", "seq": str(seq), "encrypt": "true", "iv": envelope["iv"]}
    data = envelope["data"]
    fields.update({f"data{n // 220 + 1}": data[n:n+220] for n in range(0, len(data), 220)})
    pairs = [f"{key}={value}".encode() for key, value in fields.items()]
    return b"".join(bytes([len(pair)]) + pair for pair in pairs)


def accept(state, clock, seq, value=None):
    payload = params() if value is None else value
    stage = state.stage(IDENTITY, source="mdns", sequence=str(seq), params=payload,
        report_digest=p.digest({"seq": seq, "params": payload}), received_at=clock.wall, received_mono=clock.mono)
    state.commit(IDENTITY, *stage)


def test_config_binding_and_redaction():
    _, state = setup_state(endpoint=True)
    bad = deepcopy(state.config)
    bad["devices"][IDENTITY]["endpoint"]["address"] = "127.0.0.1"
    with pytest.raises(p.InvalidObservation, match="endpoint_address_invalid"):
        p.config_validate(bad)
    for key, value in (("model", "MINIR4"), ("uiid", 9)):
        bad = deepcopy(state.config)
        bad["devices"][IDENTITY][key] = value
        with pytest.raises(p.InvalidObservation, match="model_binding_invalid"):
            p.config_validate(bad)
    output = json.dumps(state.snapshot(IDENTITY))
    assert state.config["devices"][IDENTITY]["device_key"] not in output
    assert "10.0.0.2" not in output


def test_same_value_new_revision_renews_but_duplicate_does_not():
    clock, state = setup_state()
    accept(state, clock, 1)
    clock.advance(10)
    with pytest.raises(p.InvalidObservation, match="sequence_replayed"):
        accept(state, clock, 1)
    assert state.snapshot(IDENTITY)["channels"][0]["age_seconds"] == 10
    accept(state, clock, 2)
    assert state.snapshot(IDENTITY)["channels"][0]["age_seconds"] == 0


def test_partial_outlets_never_refresh_missing_outputs():
    clock, state = setup_state()
    accept(state, clock, 1, params([0]))
    rows = state.snapshot(IDENTITY)["channels"]
    assert rows[0]["fresh"] and all(not row["fresh"] for row in rows[1:])
    clock.advance(61)
    accept(state, clock, 2, params([1]))
    rows = state.snapshot(IDENTITY)["channels"]
    assert not rows[0]["fresh"] and rows[1]["fresh"] and not rows[2]["fresh"]


def test_ping_ack_missing_and_duplicate_outlets_do_not_create_state():
    clock, state = setup_state()
    for value in ({"online": True}, {"error": 0}, {"switches": []},
                  {"switches": [{"outlet": 0, "switch": "off"}] * 2}):
        with pytest.raises(p.InvalidObservation):
            accept(state, clock, 1, value)
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])


def test_restart_restores_highwater_only_and_reset_requires_generation():
    clock, state = setup_state()
    accept(state, clock, 10)
    metadata = state.metadata()
    assert "state" not in json.dumps(metadata) and "device_key" not in json.dumps(metadata)
    clock2, restarted = setup_state(metadata)
    assert all(not row["fresh"] for row in restarted.snapshot(IDENTITY)["channels"])
    with pytest.raises(p.InvalidObservation):
        accept(restarted, clock2, 10)
    with pytest.raises(p.InvalidObservation):
        accept(restarted, clock2, 1)
    with pytest.raises(p.InvalidObservation, match="generation_blocked"):
        accept(restarted, clock2, 11)
    clock3, blocked = setup_state(restarted.metadata())
    with pytest.raises(p.InvalidObservation, match="generation_blocked"):
        accept(blocked, clock3, 12)
    clock4, changed = setup_state(restarted.metadata(), generation="reviewed-new-generation")
    accept(changed, clock4, 1)
    assert changed.snapshot(IDENTITY)["channels"][0]["fresh"]


def test_expiry_and_wall_clock_skew_cannot_restamp_state():
    clock, state = setup_state()
    accept(state, clock, 1)
    before = state.snapshot(IDENTITY)["channels"][0]["received_at"]
    clock.wall += timedelta(seconds=3)
    assert not state.snapshot(IDENTITY)["channels"][0]["fresh"]
    clock.wall -= timedelta(seconds=3)
    clock.advance(61)
    row = state.snapshot(IDENTITY)["channels"][0]
    assert not row["fresh"] and row["received_at"] == before


def observer_module():
    pytest.importorskip("zeroconf", reason="Use the pinned offline observer test dependencies")
    return importlib.import_module("rootline_observer_test.observer")


class Store:
    def __init__(self): self.saved = None
    async def async_save(self, value): self.saved = deepcopy(value)
    async def async_load(self): return deepcopy(self.saved)


def test_actual_zeroconf_raw_record_receipt_excludes_cache_and_address(monkeypatch):
    o = observer_module()
    from zeroconf import DNSText, DNSAddress, RecordUpdate
    async def run():
        clock, state = setup_state()
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        monkeypatch.setattr(o, "current_time_millis", lambda: clock.mono * 1000)
        listener = o.RawListener(receiver)
        zc = types.SimpleNamespace(done=False)
        old = DNSText(f"eWeLink_{IDENTITY}._ewelink._tcp.local.", 16, 1, 120, wire(state, 1), created=clock.mono*1000-1)
        address = DNSAddress("device.local.", 1, 1, 120, bytes([10, 0, 0, 2]), created=clock.mono*1000)
        listener.async_update_records(zc, clock.mono*1000, [RecordUpdate(old, None), RecordUpdate(address, None)])
        assert not receiver.tasks
        record = DNSText(old.name, 16, 1, 120, wire(state, 2), created=clock.mono*1000)
        listener.async_update_records(zc, clock.mono*1000, [RecordUpdate(record, old)])
        await asyncio.gather(*receiver.tasks)
        assert state.snapshot(IDENTITY)["channels"][0]["fresh"]
        assert state.snapshot(IDENTITY)["channels"][0]["received_at"] == clock.wall.isoformat()
        clock.advance(3)
        # Same value with a genuine newer revision remains observable even if
        # a ServiceBrowser would suppress a no-change state notification.
        record2 = DNSText(old.name, 16, 1, 120, wire(state, 3), created=clock.mono*1000)
        listener.async_update_records(zc, clock.mono*1000, [RecordUpdate(record2, record)])
        await asyncio.gather(*receiver.tasks)
        assert state.snapshot(IDENTITY)["channels"][0]["age_seconds"] == 0
        await receiver.stop()
    asyncio.run(run())


@pytest.mark.parametrize("reason", ["device_goodbye", "receiver_overflow"])
def test_invalidation_fences_candidate_during_store_save(reason):
    o = observer_module()
    async def run():
        clock, state = setup_state()
        entered, release = asyncio.Event(), asyncio.Event()
        class BlockingStore(Store):
            async def async_save(self, value):
                entered.set()
                await release.wait()
                await super().async_save(value)
        store = BlockingStore()
        receiver = o.Receiver(state, store, asyncio.create_task)
        pending = asyncio.create_task(receiver.receive(IDENTITY, wire(state, 1), clock.wall, clock.mono))
        await entered.wait()
        state.invalidate(IDENTITY, reason)
        release.set()
        await pending
        assert state.highwater[IDENTITY]["sources"]["mdns"]["sequence"] == 1
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
    asyncio.run(run())


def test_failed_persistence_and_shutdown_never_publish_candidate():
    o = observer_module()
    async def run():
        clock, state = setup_state()
        class BrokenStore:
            async def async_save(self, value): raise OSError("synthetic failure")
        receiver = o.Receiver(state, BrokenStore(), asyncio.create_task)
        await receiver.receive(IDENTITY, wire(state, 1), clock.wall, clock.mono)
        assert not state.healthy
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
        await receiver.stop()
        receiver.submit(IDENTITY, wire(state, 2), clock.wall, clock.mono)
        assert not receiver.tasks
    asyncio.run(run())


class Session:
    def __init__(self, key, mode="valid"):
        self.key, self.mode, self.calls, self.prior = key, mode, [], None
    def post(self, url, **kwargs):
        payload = kwargs["json"]
        self.calls.append((url, kwargs))
        assert url == "http://10.0.0.2:8081/zeroconf/getState"
        assert kwargs["allow_redirects"] is False
        assert p.decode(payload, self.key) == {}
        assert len(payload["sequence"]) == 13
        value = {"error": 0, "seq": 1, "sequence": payload["sequence"], **encrypted(params(), self.key)}
        if self.mode == "no_switches": value.update(encrypted({"online": True}, self.key))
        if self.mode == "bad_cipher": value["data"] = "!invalid!"
        if self.mode == "missing_data": value.pop("data")
        if self.mode == "missing_iv": value.pop("iv")
        if self.mode == "null_data": value["data"] = None
        if self.mode == "null_iv": value["iv"] = None
        if self.mode == "no_echo": value.pop("sequence")
        if self.mode == "ack": value = {"error": 0, "sequence": payload["sequence"]}
        if self.mode == "ack_seq": value = {"error": 0, "sequence": payload["sequence"], "seq": 1}
        if self.mode == "wrong_device": value["deviceid"] = "100204d497"
        if self.mode == "replay" and self.prior is not None: value = self.prior
        self.prior = value
        raw = json.dumps(value).encode()
        status = 404 if self.mode == "unsupported" else 200
        class Response:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return False
            async def read(self, limit): return raw[:limit]
        response = Response()
        response.status, response.content = status, response
        return response


def test_query_same_device_revision_new_exact_echo_can_refresh():
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
        first = state.snapshot(IDENTITY)["channels"][0]
        clock.advance(6)
        assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
        second = state.snapshot(IDENTITY)["channels"][0]
        assert first["device_sequence"] == second["device_sequence"] == "1"
        assert first["sequence"] != second["sequence"]
        assert second["received_at"] != first["received_at"] and second["fresh"]
        assert len(session.calls) == 2
    asyncio.run(run())


@pytest.mark.parametrize("case", ["fresh", "preanchor", "expired", "restart", "lower_sequence"])
def test_ack_anchor_only_accepts_subsequent_raw_report(case):
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        accept(state, clock, 100)
        store = Store()
        receiver = o.Receiver(state, store, asyncio.create_task)
        prior_revision = state.revisions[IDENTITY]
        prior_at, prior_mono = clock.wall, clock.mono
        clock.advance(1)
        session = Session(state.config["devices"][IDENTITY]["device_key"], "ack_seq")
        assert await receiver.query(IDENTITY, session) == "query_anchor_waiting_report"
        assert all(row["state"] == "Unknown" for row in state.snapshot(IDENTITY)["channels"])
        assert state.metadata()["devices"][IDENTITY]["blocked"]
        assert receiver.availability[IDENTITY]["state"] == "online"
        if case == "restart":
            state = p.ObserverState(state.config, state.metadata(), monotonic=lambda: clock.mono, utcnow=lambda: clock.wall)
            receiver = o.Receiver(state, store, asyncio.create_task)
        clock.advance(61 if case == "expired" else 1)
        await receiver.receive(IDENTITY, wire(state, 0 if case == "lower_sequence" else 1),
            prior_at if case == "preanchor" else clock.wall,
            prior_mono if case == "preanchor" else clock.mono,
            revision=prior_revision if case == "preanchor" else state.revisions[IDENTITY])
        fresh = any(row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
        assert fresh is (case == "fresh")
        if fresh:
            assert all(row["source"] == "mdns" for row in state.snapshot(IDENTITY)["channels"])
    asyncio.run(run())


def test_fresh_ack_after_ha_restart_recovers_unchanged_device_sequence():
    o = observer_module()
    async def run():
        clock, previous = setup_state(endpoint=True)
        accept(previous, clock, 1)
        state = p.ObserverState(previous.config, previous.metadata(),
            monotonic=lambda: clock.mono, utcnow=lambda: clock.wall)
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        clock.advance(1)
        assert await receiver.query(IDENTITY, Session(state.config["devices"][IDENTITY]["device_key"], "ack_seq")) == "query_anchor_waiting_report"
        assert not any(row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
        clock.advance(1)
        await receiver.receive(IDENTITY, wire(state, 1), clock.wall, clock.mono)
        assert all(row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["no_echo", "ack", "wrong_device", "unsupported", "replay"])
def test_query_failure_is_unknown_and_no_retry(mode):
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        session = Session(state.config["devices"][IDENTITY]["device_key"], mode)
        if mode == "replay":
            assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
            before = state.snapshot(IDENTITY)["channels"][0]["received_at"]
            clock.advance(6)
        assert await receiver.query(IDENTITY, session) == "query_unproven"
        assert len(session.calls) == (2 if mode == "replay" else 1)
        if mode == "replay":
            assert state.snapshot(IDENTITY)["channels"][0]["received_at"] == before
        else:
            assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
    asyncio.run(run())


def test_queued_reports_are_fenced_by_goodbye_before_processing():
    o = observer_module()
    async def run():
        clock, state = setup_state()
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        await receiver.lock.acquire()
        receiver.submit(IDENTITY, wire(state, 1), clock.wall, clock.mono)
        state.invalidate(IDENTITY, "device_goodbye")
        receiver.lock.release()
        await asyncio.gather(*receiver.tasks)
        assert not state.highwater
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
    asyncio.run(run())


def test_inflight_query_cannot_publish_after_invalidation():
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        class InvalidatingSession(Session):
            def post(self, url, **kwargs):
                response = super().post(url, **kwargs)
                state.invalidate(IDENTITY, "device_goodbye")
                return response
        session = InvalidatingSession(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "query_unproven"
        assert len(session.calls) == 1 and not state.highwater
    asyncio.run(run())


def test_query_without_qualified_endpoint_or_unknown_device_never_sends():
    o = observer_module()
    async def run():
        _, state = setup_state()
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        for identity in (IDENTITY, "unregistered"):
            with pytest.raises(p.InvalidObservation):
                await receiver.query(identity, session)
        assert not session.calls
    asyncio.run(run())


def test_ha_websocket_auth_allowlist_and_extra_command_fields(monkeypatch):
    observer_module()
    vol = pytest.importorskip("voluptuous")
    # Exercise our HA adapter against its pinned public API signatures. This
    # is not a replacement for loading the package on HA during qualification.
    modules = {}
    for name in ("homeassistant", "homeassistant.components", "homeassistant.const",
                 "homeassistant.helpers", "homeassistant.helpers.aiohttp_client", "homeassistant.helpers.storage"):
        modules[name] = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, modules[name])
    def command(schema):
        def decorate(function):
            function.command_schema = vol.Schema({vol.Required("id"): int, **schema})
            return function
        return decorate
    modules["homeassistant.components"].websocket_api = types.SimpleNamespace(
        websocket_command=command, async_response=lambda fn: fn)
    modules["homeassistant.components"].zeroconf = types.SimpleNamespace()
    modules["homeassistant.const"].EVENT_HOMEASSISTANT_STOP = "stop"
    modules["homeassistant.const"].__version__ = "2026.8.3"
    modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda _: (_ for _ in ()).throw(AssertionError("Unexpected network session"))
    modules["homeassistant.helpers.storage"].Store = Store
    name = "rootline_observer_adapter_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    for function in (module.snapshot, module.query):
        for extra in ({"command": "switch"}, {"params": {"switch": "on"}}, {"url": "http://other"}):
            with pytest.raises(vol.Invalid):
                function.command_schema({"id": 1, "type": "rootline_observer/" + function.__name__, "device_id": IDENTITY, **extra})
    _, state = setup_state()
    receiver = types.SimpleNamespace(state=state)
    hass = types.SimpleNamespace(data={module.DOMAIN: {"receiver": receiver,
        "zeroconf": types.SimpleNamespace(done=False), "listener": types.SimpleNamespace(closed=False)}})
    errors = []
    connection = types.SimpleNamespace(user=types.SimpleNamespace(id="2"*32, is_active=True),
        send_error=lambda *args: errors.append(args))
    assert module.permitted(hass, connection, {"id": 1}) is None
    assert errors[0][1] == "unauthorized"
    connection.user.id = "1"*32
    assert module.permitted(hass, connection, {"id": 1}) is receiver
    connection.user.is_active = False
    assert module.permitted(hass, connection, {"id": 1}) is None


def test_native_store_silent_write_failure_and_corruption_fail_closed(tmp_path):
    storage = importlib.import_module("rootline_observer_test.storage")
    async def run():
        class Native:
            path = str(tmp_path / "native-store")
            key = "rootline_observer_sequence"
            write = False
            async def async_save(self, value):
                if self.write:
                    Path(self.path).write_text(json.dumps({"key": self.key, "version": 1,
                        "minor_version": 1, "data": value}), encoding="utf-8")
        async def execute(function): return function()
        native = Native()
        verified = storage.VerifiedStore(native, execute)
        assert await verified.async_load() is None
        value = {"version": 1, "devices": {}}
        with pytest.raises(p.InvalidObservation, match="write_unproven"):
            await verified.async_save(value)
        native.write = True
        await verified.async_save(value)
        assert await verified.async_load() == value
        Path(native.path).write_text("corrupt", encoding="utf-8")
        with pytest.raises(p.InvalidObservation, match="replay_store_invalid"):
            await verified.async_load()
        assert Path(native.path).read_text() == "corrupt"
    asyncio.run(run())


def test_qualified_correlated_full_query_recovers_passive_revision_reset():
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        state.config["devices"][IDENTITY]["qualification_id"] = "tested-query-qualification"
        accept(state, clock, 10)
        with pytest.raises(p.InvalidObservation):
            accept(state, clock, 1)
        assert state.highwater[IDENTITY]["blocked"]
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
        assert state.highwater[IDENTITY]["blocked"] is False
        assert state.highwater[IDENTITY]["sources"]["mdns"]["sequence"] == 1
        with pytest.raises(p.InvalidObservation):
            accept(state, clock, 1)
        assert state.highwater[IDENTITY]["blocked"] is False
        clock.advance(1)
        accept(state, clock, 2)
        assert state.snapshot(IDENTITY)["channels"][0]["fresh"]
    asyncio.run(run())


def test_transient_storage_failure_recovers_without_restart_or_old_state():
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        class FlakyStore(Store):
            fail = True
            async def async_save(self, value):
                if self.fail: raise OSError("synthetic write failure")
                await super().async_save(value)
        store = FlakyStore()
        receiver = o.Receiver(state, store, asyncio.create_task)
        old_epoch = state.boot_id
        await receiver.receive(IDENTITY, wire(state, 10), clock.wall, clock.mono)
        assert receiver.storage_failed and not state.healthy
        assert state.highwater[IDENTITY]["sources"]["mdns"]["sequence"] == 10
        store.fail = False
        await receiver.recover_storage()
        assert receiver.storage_failed  # Bounded backoff, no busy retry.
        clock.advance(5)
        await receiver.recover_storage()
        assert state.healthy and not receiver.storage_failed and state.boot_id != old_epoch
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
        assert store.saved["devices"][IDENTITY]["sources"]["mdns"]["sequence"] == 10
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
        assert state.snapshot(IDENTITY)["channels"][0]["fresh"]
    asyncio.run(run())


@pytest.mark.parametrize("mode,code", [
    ("no_echo", "query_correlation_missing_or_mismatch"),
    ("bad_cipher", "encrypted_payload_invalid"),
    ("ack", "query_ack_without_encrypted_state"),
    ("missing_data", "query_data_missing"),
    ("missing_iv", "query_iv_missing"),
    ("null_data", "query_encrypted_fields_invalid"),
    ("null_iv", "query_encrypted_fields_invalid"),
    ("no_switches", "explicit_switch_fields_missing"),
    ("unsupported", "query_http_unproven"),
])
def test_query_diagnostics_preserve_evidence(mode, code):
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        accept(state, clock, 1)
        clock.advance(6)
        before, metadata = state.snapshot(IDENTITY), state.metadata()
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        assert await receiver.query(IDENTITY, Session(state.config["devices"][IDENTITY]["device_key"], mode)) == "query_unproven"
        after = state.snapshot(IDENTITY)
        assert after["channels"] == before["channels"]
        assert state.metadata() == metadata
        assert after["diagnostics"]["query"] == {"count": 1, "last_result": code}
    asyncio.run(run())


def test_passive_diagnostics_preserve_evidence_and_are_bounded(monkeypatch):
    o = observer_module()
    async def run():
        clock, state = setup_state()
        assert state.snapshot(IDENTITY)["diagnostics"]["mdns"] == {"count": 0, "last_result": "no_reports_received"}
        accept(state, clock, 1)
        clock.advance(6)
        before, metadata = state.snapshot(IDENTITY), state.metadata()
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        for packet, code in ((b"\x05a", "txt_invalid"),
                (wire(state, 2, {"online": True}), "explicit_switch_fields_missing"),
                (wire(state, "invalid"), "sequence_invalid")):
            await receiver.receive(IDENTITY, packet, clock.wall, clock.mono)
            assert state.snapshot(IDENTITY)["diagnostics"]["mdns"]["last_result"] == code
            assert state.snapshot(IDENTITY)["channels"] == before["channels"]
            assert state.metadata() == metadata
        state.diagnostics[IDENTITY]["mdns"]["count"] = 1_000_000
        state.diagnose(IDENTITY, "mdns", "hostile address/key/envelope text")
        result = state.snapshot(IDENTITY)
        assert result["diagnostics"]["mdns"] == {"count": 1_000_000, "last_result": "report_processing_failed"}
        assert "hostile" not in json.dumps(result)
        result["diagnostics"]["mdns"]["count"] = -1
        assert state.diagnostics[IDENTITY]["mdns"]["count"] == 1_000_000
    asyncio.run(run())


def test_query_arbitrary_exception_is_redacted_without_freshness_change():
    o = observer_module()
    async def run():
        clock, state = setup_state(endpoint=True)
        accept(state, clock, 1)
        clock.advance(6)
        before, metadata = state.snapshot(IDENTITY), state.metadata()
        class HostileSession:
            def post(self, *args, **kwargs):
                raise RuntimeError("hostile address/key/envelope text")
        receiver = o.Receiver(state, Store(), asyncio.create_task)
        assert await receiver.query(IDENTITY, HostileSession()) == "query_unproven"
        after = state.snapshot(IDENTITY)
        assert after["channels"] == before["channels"] and state.metadata() == metadata
        assert after["diagnostics"]["query"] == {"count": 1, "last_result": "query_unproven"}
        assert "hostile" not in json.dumps(after)
    asyncio.run(run())


# Native records/cache, synthetic private addresses and no device sockets.
def discovery_fixture(state, *, address="10.0.0.2", port=8081, txt=None, ttl=120):
    import ipaddress
    from zeroconf import DNSAddress, DNSService, DNSText, current_time_millis
    from zeroconf._cache import DNSCache
    name = f"ewelink_{IDENTITY}._ewelink._tcp.local."
    server = "synthetic-device.local."
    now = current_time_millis()
    records = [DNSService(name, 33, 1, ttl, 0, 0, port, server, created=now),
        DNSText(name, 16, 1, ttl, wire(state, 1) if txt is None else txt, created=now),
        DNSAddress(server, 1, 1, ttl, ipaddress.IPv4Address(address).packed, created=now)]
    cache = DNSCache()
    cache.async_add_records(records)
    shared = types.SimpleNamespace(cache=cache, done=False, started=True)
    return shared, records


def test_native_serviceinfo_cache_metadata_never_becomes_switch_evidence():
    o = observer_module()
    async def run():
        _, state = setup_state()
        shared, _ = discovery_fixture(state)
        resolver = o.EndpointDiscovery(shared)
        endpoint, token = await resolver.resolve(IDENTITY)
        assert endpoint == {"address": "10.0.0.2", "port": 8081}
        resolver.validate(IDENTITY, token)
        assert not state.highwater and not state.channels[IDENTITY]
        assert all(not row["fresh"] for row in state.snapshot(IDENTITY)["channels"])
        assert not hasattr(resolver, "endpoint")
    asyncio.run(run())


@pytest.mark.parametrize("case", ["public", "loopback", "linklocal", "port_zero",
    "duplicate_id", "case_duplicate_id", "wrong_id", "partial", "conflicting_srv", "conflicting_txt",
    "multiple_addresses", "expired", "goodbye", "device_conflict", "stopped"])
def test_discovery_binding_fails_closed(case):
    o = observer_module()
    from zeroconf import DNSAddress, DNSService, DNSText, current_time_millis
    _, state = setup_state()
    address = {"public": "8.8.8.8", "loopback": "127.0.0.1", "linklocal": "169.254.1.2"}.get(case, "10.0.0.2")
    shared, records = discovery_fixture(state, address=address, port=0 if case == "port_zero" else 8081,
        ttl=0 if case == "goodbye" else 120)
    now = current_time_millis()
    if case in {"duplicate_id", "case_duplicate_id", "wrong_id"}:
        pair = b"id=" + (IDENTITY if case != "wrong_id" else "100204d497").encode()
        text = bytes([len(pair)]) + pair
        if case == "duplicate_id": text += text
        if case == "case_duplicate_id": text += text.replace(b"id=", b"ID=")
        shared.cache.async_remove_records([records[1]])
        shared.cache.async_add_records([DNSText(records[1].name, 16, 1, 120, text, created=now)])
    if case == "partial": shared.cache.async_remove_records([records[0]])
    if case == "conflicting_srv":
        shared.cache.async_add_records([DNSService(records[0].name, 33, 1, 120, 0, 0, 9999, records[0].server, created=now)])
    if case == "conflicting_txt":
        shared.cache.async_add_records([DNSText(records[1].name, 16, 1, 120, wire(state, 2), created=now)])
    if case == "multiple_addresses":
        shared.cache.async_add_records([DNSAddress(records[2].name, 1, 1, 120, bytes([10,0,0,3]), created=now)])
    if case == "expired":
        for record in records: record.created = now-121000
    if case == "device_conflict":
        shared.cache.async_add_records([DNSService("ewelink_100204d497._ewelink._tcp.local.", 33, 1, 120, 0, 0, 8081, records[0].server, created=now)])
    if case == "stopped": shared.done = True
    with pytest.raises(p.InvalidObservation): o.EndpointDiscovery(shared).binding(IDENTITY)
    assert not state.highwater


def test_discovered_query_and_changed_binding_preserve_existing_contract():
    o = observer_module()
    async def run():
        clock, state = setup_state()
        shared, records = discovery_fixture(state)
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "explicit_query_report_received"
        before = deepcopy(state.highwater)
        received = state.snapshot(IDENTITY)["channels"][0]["received_at"]
        with pytest.raises(p.InvalidObservation, match="rate_limited"):
            await receiver.query(IDENTITY, session)
        assert len(session.calls) == 1
        clock.advance(6)
        class Changed(Session):
            def post(self, url, **kwargs):
                result = super().post(url, **kwargs)
                shared.cache.async_remove_records([records[0]])
                return result
        changed = Changed(session.key)
        assert await receiver.query(IDENTITY, changed) == "query_unproven"
        assert len(changed.calls) == 1 and state.highwater == before
        assert state.snapshot(IDENTITY)["channels"][0]["received_at"] == received
        assert not receiver.tasks
    asyncio.run(run())


def test_configured_endpoint_conflict_never_posts():
    o = observer_module()
    async def run():
        _, state = setup_state(endpoint=True)
        shared, _ = discovery_fixture(state, address="10.0.0.3")
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "query_unproven"
        assert not session.calls and not state.highwater
        assert state.snapshot(IDENTITY)["diagnostics"]["discovery"]["last_result"] == "discovery_config_conflict"
    asyncio.run(run())


def test_stop_cancels_pending_discovery_and_prevents_http(monkeypatch):
    o = observer_module()
    async def run():
        _, state = setup_state()
        shared, records = discovery_fixture(state)
        shared.cache.async_remove_records(records)
        entered, cleaned = asyncio.Event(), asyncio.Event()
        class PendingBrowser:
            def __init__(self, zc, type_, handlers):
                assert zc is shared and type_ == "_ewelink._tcp.local."
                entered.set()
            async def async_cancel(self): cleaned.set()
        monkeypatch.setattr(o, "AsyncServiceBrowser", PendingBrowser)
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        query = asyncio.create_task(receiver.query(IDENTITY, session))
        await entered.wait()
        await receiver.stop()
        with pytest.raises(asyncio.CancelledError): await query
        assert cleaned.is_set() and not session.calls and not receiver.tasks
        assert not state.healthy and not state.highwater
    asyncio.run(run())


@pytest.mark.parametrize("identity", list(p.DEVICES))
def test_all_three_fixed_identities_resolve_metadata_only(identity):
    o = observer_module()
    from zeroconf import DNSService, DNSText, DNSAddress, current_time_millis
    from zeroconf._cache import DNSCache
    async def run():
        now = current_time_millis()
        name, server = f"ewelink_{identity}._ewelink._tcp.local.", "synthetic-device.local."
        pair = b"id=" + identity.encode()
        cache = DNSCache()
        cache.async_add_records([DNSService(name, 33, 1, 120, 0, 0, 8081, server, created=now),
            DNSText(name, 16, 1, 120, bytes([len(pair)])+pair, created=now),
            DNSAddress(server, 1, 1, 120, bytes([10,0,0,2]), created=now)])
        resolver = o.EndpointDiscovery(types.SimpleNamespace(cache=cache, done=False, started=True))
        endpoint, token = await resolver.resolve(identity)
        assert endpoint["address"] == "10.0.0.2"
        resolver.validate(identity, token)
    asyncio.run(run())


def test_native_incomplete_discovery_is_bounded_and_removes_listener():
    o = observer_module()
    from zeroconf._cache import DNSCache
    from zeroconf._history import QuestionHistory
    async def run():
        _, state = setup_state()
        listeners, packets = [], []
        shared = types.SimpleNamespace(cache=DNSCache(), done=False, started=True,
            loop=asyncio.get_running_loop(), question_history=QuestionHistory(),
            async_add_listener=lambda listener, question: listeners.append(listener),
            async_remove_listener=lambda listener: listeners.remove(listener),
            async_send=lambda packet, address, port: packets.append(packet))
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert not packets  # Construction is passive.
        started = asyncio.get_running_loop().time()
        assert await receiver.query(IDENTITY, session) == "query_unproven"
        assert asyncio.get_running_loop().time()-started < 2.5
        assert packets and not listeners and not session.calls and not state.highwater
        assert {question.name.lower() for packet in packets for question in packet.questions} == {
            "_ewelink._tcp.local."}
        assert state.diagnostics[IDENTITY]["discovery"]["last_result"] == "discovery_ptr_missing"
    asyncio.run(run())


def test_stop_cancels_inflight_http_without_evidence():
    o = observer_module()
    async def run():
        _, state = setup_state()
        shared, _ = discovery_fixture(state)
        entered, cleaned = asyncio.Event(), asyncio.Event()
        class Hanging(Session):
            def post(self, url, **kwargs):
                response = super().post(url, **kwargs)
                async def read(_limit):
                    entered.set()
                    try: await asyncio.Event().wait()
                    finally: cleaned.set()
                response.read = read
                return response
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Hanging(state.config["devices"][IDENTITY]["device_key"])
        query = asyncio.create_task(receiver.query(IDENTITY, session))
        await entered.wait()
        await receiver.stop()
        with pytest.raises(asyncio.CancelledError): await query
        assert cleaned.is_set() and len(session.calls) == 1 and not receiver.tasks and not state.highwater
    asyncio.run(run())


@pytest.mark.parametrize("case,code", [
    ("none", "discovery_missing_srv_and_txt"),
    ("srv", "discovery_missing_srv"),
    ("txt", "discovery_missing_txt"),
    ("address", "discovery_missing_address"),
    ("srv_conflict", "discovery_conflicting_srv"),
    ("txt_conflict", "discovery_conflicting_txt"),
    ("address_conflict", "discovery_conflicting_address"),
    ("expired", "discovery_missing_srv_and_txt"),
])
def test_incomplete_discovery_reports_only_structure_without_state_change(monkeypatch, case, code):
    o = observer_module()
    from zeroconf import DNSService, DNSText, DNSAddress, current_time_millis
    async def run():
        clock, state = setup_state()
        accept(state, clock, 1)
        clock.advance(6)
        before, metadata = state.snapshot(IDENTITY), state.metadata()
        shared, records = discovery_fixture(state)
        if case == "none": shared.cache.async_remove_records(records)
        if case in {"srv", "txt", "address"}:
            shared.cache.async_remove_records([records[{"srv":0,"txt":1,"address":2}[case]]])
        now = current_time_millis()
        if case == "srv_conflict":
            shared.cache.async_add_records([DNSService(records[0].name,33,1,120,0,0,9999,records[0].server,created=now)])
        if case == "txt_conflict":
            shared.cache.async_add_records([DNSText(records[1].name,16,1,120,wire(state,2),created=now)])
        if case == "address_conflict":
            shared.cache.async_add_records([DNSAddress(records[2].name,1,1,120,bytes([10,0,0,3]),created=now)])
        if case == "expired":
            for record in records: record.created = now-121000
        class IncompleteInfo:
            def __init__(self, type_, name):
                assert type_ == "_ewelink._tcp.local."
                assert name == f"ewelink_{IDENTITY}.{type_}"
            async def async_request(self, zc, timeout):
                assert zc is shared and timeout == 1500
                return False
        monkeypatch.setattr(o, "AsyncServiceInfo", IncompleteInfo)
        from zeroconf import DNSPointer
        shared.cache.async_add_records([DNSPointer("_ewelink._tcp.local.",12,1,120,
            f"ewelink_{IDENTITY}._ewelink._tcp.local.",created=now)])
        class QuietBrowser:
            def __init__(self, *_args, **_kwargs): pass
            async def async_cancel(self): pass
        monkeypatch.setattr(o, "AsyncServiceBrowser", QuietBrowser)
        receiver = o.Receiver(state, Store(), asyncio.create_task, o.EndpointDiscovery(shared))
        session = Session(state.config["devices"][IDENTITY]["device_key"])
        assert await receiver.query(IDENTITY, session) == "query_unproven"
        after = state.snapshot(IDENTITY)
        assert after["channels"] == before["channels"] and state.metadata() == metadata
        assert not session.calls and not receiver.tasks
        assert after["diagnostics"]["discovery"] == {"count":1,"last_result":code}
        assert after["diagnostics"]["query"] == {"count":1,"last_result":code}
        rendered = json.dumps(after["diagnostics"])
        assert "10.0.0." not in rendered and "synthetic-device" not in rendered
        assert state.config["devices"][IDENTITY]["device_key"] not in rendered
    asyncio.run(run())


def native_discovery_shared(cache):
    from zeroconf._history import QuestionHistory
    listeners, packets, browsers = [], [], []
    def add(listener, question):
        listeners.append(listener)
        if hasattr(listener, "query_scheduler"): browsers.append(listener)
    shared = types.SimpleNamespace(cache=cache, done=False, started=True,
        loop=asyncio.get_running_loop(), question_history=QuestionHistory(),
        async_add_listener=add, async_remove_listener=lambda listener:listeners.remove(listener),
        async_send=lambda packet,address,port:packets.append(packet))
    return shared, listeners, packets, browsers


def test_valid_exact_cache_skips_browser_and_resolution(monkeypatch):
    o = observer_module()
    async def run():
        _, state = setup_state()
        shared, _ = discovery_fixture(state)
        def forbidden(*_args, **_kwargs): raise AssertionError("unnecessary discovery")
        monkeypatch.setattr(o,"AsyncServiceBrowser",forbidden)
        monkeypatch.setattr(o,"AsyncServiceInfo",forbidden)
        endpoint, token = await o.EndpointDiscovery(shared).resolve(IDENTITY)
        assert endpoint == {"address":"10.0.0.2","port":8081}
        assert not state.highwater and not state.channels[IDENTITY]
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["advertised_case", "unrelated", "expired_ptr", "conflicting_srv", "resolution_timeout"])
def test_native_ptr_browse_wire_case_disposal_and_strict_binding(monkeypatch, mode):
    o = observer_module()
    from zeroconf import DNSPointer, DNSService, DNSText, DNSAddress, DNSIncoming, current_time_millis
    from zeroconf._cache import DNSCache
    async def run():
        clock, state = setup_state()
        accept(state,clock,1)
        before, metadata = state.snapshot(IDENTITY), state.metadata()
        shared,listeners,packets,browsers = native_discovery_shared(DNSCache())
        advertised = f"eWeLink_{IDENTITY}._ewelink._tcp.local."
        requested = []
        original_info = o.AsyncServiceInfo
        def info(type_, name):
            requested.append(name)
            return original_info(type_,name)
        monkeypatch.setattr(o,"AsyncServiceInfo",info)
        injected = False
        def send(packet,address,port):
            nonlocal injected
            packets.append(packet)
            if injected: return
            injected = True
            now = current_time_millis()
            alias = "eWeLink_unknown._ewelink._tcp.local." if mode == "unrelated" else advertised
            shared.cache.async_add_records([DNSPointer("_ewelink._tcp.local.",12,1,120,alias,
                created=now-121000 if mode == "expired_ptr" else now),
                DNSService(advertised,33,1,120,0,0,8081,"Synthetic-Device.local.",created=now),
                DNSText(advertised,16,1,120,wire(state,2),created=now),
                DNSAddress("Synthetic-Device.local.",1,1,120,bytes([10,0,0,2]),created=now)])
            if mode == "resolution_timeout":
                shared.cache.async_remove_records(shared.cache.get_all_by_details(advertised,33,1))
                shared.cache.async_remove_records(shared.cache.get_all_by_details(advertised,16,1))
            if mode == "conflicting_srv":
                shared.cache.async_add_records([DNSService(advertised,33,1,120,0,0,9999,"Synthetic-Device.local.",created=now)])
        shared.async_send=send
        receiver=o.Receiver(state,Store(),asyncio.create_task,o.EndpointDiscovery(shared))
        session=Session(state.config["devices"][IDENTITY]["device_key"])
        started=asyncio.get_running_loop().time()
        result=await receiver.query(IDENTITY,session)
        assert asyncio.get_running_loop().time()-started < 4.5
        assert packets and len(browsers)==1 and not listeners
        assert browsers[0].done and browsers[0]._query_sender_task is None
        sent = len(packets)
        await asyncio.sleep(2.1)
        assert len(packets) == sent
        first_questions=[q for raw in packets[0].packets() for q in DNSIncoming(raw).questions]
        assert first_questions and all(q.name=="_ewelink._tcp.local." and q.type==12 for q in first_questions)
        if mode == "advertised_case":
            assert requested==[advertised] and result=="explicit_query_report_received" and len(session.calls)==1
        else:
            assert result=="query_unproven" and not session.calls
            assert state.snapshot(IDENTITY)["channels"]==before["channels"] and state.metadata()==metadata
        if mode in {"unrelated","expired_ptr"}: assert not requested
        if mode == "resolution_timeout":
            wire_questions=[q for packet in packets[1:] for raw in packet.packets() for q in DNSIncoming(raw).questions]
            exact_questions=[q for q in wire_questions if q.type in {16,33}]
            assert exact_questions and all(q.name==advertised for q in exact_questions)
        assert not receiver.tasks
    asyncio.run(run())


def test_native_browser_cancellation_disposes_listener_and_scheduler():
    o=observer_module()
    from zeroconf._cache import DNSCache
    async def run():
        _,state=setup_state()
        shared,listeners,packets,browsers=native_discovery_shared(DNSCache())
        receiver=o.Receiver(state,Store(),asyncio.create_task,o.EndpointDiscovery(shared))
        session=Session(state.config["devices"][IDENTITY]["device_key"])
        query=asyncio.create_task(receiver.query(IDENTITY,session))
        await asyncio.sleep(0.2)
        assert listeners and browsers
        await receiver.stop()
        with pytest.raises(asyncio.CancelledError): await query
        assert not listeners and not receiver.tasks and not session.calls and not state.highwater
        assert browsers[0].done
        sent = len(packets)
        await asyncio.sleep(1.2)
        assert len(packets) == sent
    asyncio.run(run())


def test_native_resolution_cancellation_disposes_service_listener():
    o=observer_module()
    from zeroconf import DNSPointer,current_time_millis
    from zeroconf._cache import DNSCache
    async def run():
        _,state=setup_state()
        shared,listeners,packets,browsers=native_discovery_shared(DNSCache())
        resolving=asyncio.Event()
        advertised=f"eWeLink_{IDENTITY}._ewelink._tcp.local."
        def send(packet,address,port):
            packets.append(packet)
            if any(q.type in {16,33} for q in packet.questions): resolving.set()
            if len(packets)==1:
                shared.cache.async_add_records([DNSPointer("_ewelink._tcp.local.",12,1,120,advertised,created=current_time_millis())])
        shared.async_send=send
        receiver=o.Receiver(state,Store(),asyncio.create_task,o.EndpointDiscovery(shared))
        session=Session(state.config["devices"][IDENTITY]["device_key"])
        query=asyncio.create_task(receiver.query(IDENTITY,session))
        async with asyncio.timeout(3): await resolving.wait()
        assert browsers[0].done and listeners
        await receiver.stop()
        with pytest.raises(asyncio.CancelledError): await query
        assert not listeners and not receiver.tasks and not session.calls and not state.highwater
    asyncio.run(run())


# Bounded query diagnostics preserve operational behavior and private data.
import asyncio, errno, json
import pytest
from aiohttp import ClientConnectionError, ClientConnectorError

@pytest.mark.parametrize("boundary,error,expected", [
 ("connect",TimeoutError("secret address"),"query_timeout"),
 ("read",TimeoutError("secret key"),"query_timeout"),
 ("connect",OSError(errno.EHOSTUNREACH,"secret address"),"query_network_unreachable"),
 ("connect",OSError(errno.ENETUNREACH,"secret address"),"query_network_unreachable"),
 ("connect",ConnectionRefusedError(errno.ECONNREFUSED,"secret"),"query_connection_failed"),
 ("read",ClientConnectionError("secret"),"query_connection_failed"),
 ("connect",ClientConnectorError(None,OSError(errno.EHOSTUNREACH,"secret")),"query_network_unreachable"),
 ("read",RuntimeError("secret payload"),"query_unproven"),
 ("json",None,"query_invalid_json"),
 ("storage",OSError(errno.EHOSTUNREACH,"secret storage"),"query_storage_failure"),
])
def test_actual_query_boundaries_preserve_outcome(boundary,error,expected):
 async def run():
  o=observer_module();clock,state=setup_state(endpoint=True)
  class BrokenStore(Store):
   async def async_save(self,value):
    if boundary=="storage":raise error
    return await super().async_save(value)
  receiver=o.Receiver(state,BrokenStore(),asyncio.create_task)
  class BrokenSession(Session):
   def post(self,url,**kwargs):
    response=super().post(url,**kwargs)
    if boundary=="connect":raise error
    original=response.read
    async def read(limit):
     if boundary=="read":raise error
     if boundary=="json":return b'{SECRET INVALID'
     return await original(limit)
    response.read=read
    return response
  session=BrokenSession(state.config["devices"][IDENTITY]["device_key"],"ack_seq" if boundary=="storage" else "valid")
  assert await receiver.query(IDENTITY,session)=="query_unproven"
  snap=state.snapshot(IDENTITY)
  assert snap["diagnostics"]["query"]["last_result"]==expected
  assert len(session.calls)==1 and snap["control_commands"]==0
  assert all(row["state"]=="Unknown" for row in snap["channels"])
  assert receiver.availability[IDENTITY]["state"]==("online" if boundary=="storage" else "offline")
  rendered=json.dumps(snap)
  assert "secret" not in rendered.lower() and "10.0.0.2" not in rendered
  assert state.config["devices"][IDENTITY]["device_key"] not in rendered
 asyncio.run(run())

@pytest.mark.parametrize("boundary",["connect","read","storage"])
def test_cancellation_is_not_converted_or_retried(boundary):
 async def run():
  o=observer_module();clock,state=setup_state(endpoint=True)
  class CancelStore(Store):
   async def async_save(self,value):
    if boundary=="storage":raise asyncio.CancelledError()
    return await super().async_save(value)
  receiver=o.Receiver(state,CancelStore(),asyncio.create_task)
  class CancelSession(Session):
   def post(self,url,**kwargs):
    response=super().post(url,**kwargs)
    if boundary=="connect":raise asyncio.CancelledError()
    original=response.read
    async def read(limit):
     if boundary=="read":raise asyncio.CancelledError()
     return await original(limit)
    response.read=read;return response
  session=CancelSession(state.config["devices"][IDENTITY]["device_key"],"ack_seq" if boundary=="storage" else "valid")
  with pytest.raises(asyncio.CancelledError):await receiver.query(IDENTITY,session)
  assert len(session.calls)==1 and not receiver.tasks
  assert state.snapshot(IDENTITY)["diagnostics"]["query"]["count"]==0
 asyncio.run(run())


def test_outer_timeout_translates_cancellation_without_retry(monkeypatch):
 async def run():
  o=observer_module();clock,state=setup_state(endpoint=True)
  receiver=o.Receiver(state,Store(),asyncio.create_task)
  timeout=asyncio.timeout;limits=[]
  def bounded(seconds):
   limits.append(seconds)
   return timeout(0.01)
  monkeypatch.setattr(o.asyncio,"timeout",bounded)
  class Hanging(Session):
   def post(self,url,**kwargs):
    response=super().post(url,**kwargs)
    async def read(limit):await asyncio.Event().wait()
    response.read=read;return response
  session=Hanging(state.config["devices"][IDENTITY]["device_key"])
  assert await receiver.query(IDENTITY,session)=="query_unproven"
  assert limits==[5] and len(session.calls)==1 and not receiver.tasks
  assert state.snapshot(IDENTITY)["diagnostics"]["query"]["last_result"]=="query_timeout"
  assert receiver.availability[IDENTITY]["state"]=="offline"
 asyncio.run(run())
