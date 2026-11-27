"""Actual adapter path with synthetic encrypted requests; no device sockets."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import types

import pytest

package = types.ModuleType("rootline_command_adapter_test")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "deploy/home-assistant/custom_components/rootline_observer")]
sys.modules.setdefault(package.__name__, package)
c = importlib.import_module(package.__name__ + ".command")
p = importlib.import_module(package.__name__ + ".protocol")


class Store:
    value = None
    async def async_save(self, value):
        self.value = deepcopy(value)


class Discovery:
    async def resolve(self, identity):
        return {"address": "10.0.0.2", "port": 8081}, identity
    def validate(self, identity, token):
        assert token == identity
    validate_command_endpoint = validate


class Session:
    def __init__(self, response=None, fail=False):
        self.response = {"error": 0} if response is None else response
        self.calls = []
        self.fail = fail
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail:
            raise OSError("synthetic offline")
        body = json.dumps(self.response).encode()
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def read(self, limit): return body[:limit]
            @property
            def content(self): return self
        return Response()


def fixture():
    now = [datetime(2026, 11, 27, 10, tzinfo=timezone.utc)]
    devices = {identity: {"device_key": os.urandom(16).hex()} for identity in c.CHANNELS}
    receiver = types.SimpleNamespace(closed=False, discovery=Discovery(),
        state=types.SimpleNamespace(utcnow=lambda: now[0], config={"devices": devices}))
    store = Store()
    request = {"device_id": "100204d497", "channel": 1, "state": "OFF", "attempt_id": "execution:OFF:1",
        "issued_at": now[0].isoformat(), "expires_at": (now[0]+timedelta(seconds=30)).isoformat()}
    return now, receiver, store, request


def test_actual_ack_and_restart_duplicate_preserve_original_result():
    async def run():
        _, receiver, store, request = fixture()
        session = Session()
        result = await c.CommandAdapter(receiver, store).command(request, session)
        assert result["accepted"] and result["status"] == "controller_accepted"
        again = await c.CommandAdapter(receiver, store, store.value).command(request, session)
        assert again == result and len(session.calls) == 1
        url, kwargs = session.calls[0]
        assert url.endswith("/zeroconf/switches") and kwargs["allow_redirects"] is False
        assert p.decode(kwargs["json"], receiver.state.config["devices"][request["device_id"]]["device_key"]) == {
            "switches": [{"outlet": 0, "switch": "off"}]}
    asyncio.run(run())


@pytest.mark.parametrize("response", [{"error": False}, {"error": "0"}, {"error": 1},
    {"error": 0, "deviceid": "wrong"}, {"error": 0, "sequence": "wrong"}, {}])
def test_unproven_or_rejected_response_never_accepts(response):
    async def run():
        _, receiver, store, request = fixture()
        result = await c.CommandAdapter(receiver, store).command(request, Session(response))
        assert result["accepted"] is False
    asyncio.run(run())


def test_unreachable_attempt_consumed_and_no_automatic_replay():
    async def run():
        _, receiver, store, request = fixture()
        failed = Session(fail=True)
        result = await c.CommandAdapter(receiver, store).command(request, failed)
        online = Session()
        again = await c.CommandAdapter(receiver, store, store.value).command(request, online)
        assert not result["accepted"] and again == result and not online.calls
    asyncio.run(run())


def test_cancelled_consumed_attempt_survives_restart():
    async def run():
        _, receiver, store, request = fixture()
        class CancelledDiscovery(Discovery):
            async def resolve(self, identity): raise asyncio.CancelledError()
        receiver.discovery = CancelledDiscovery()
        with pytest.raises(asyncio.CancelledError):
            await c.CommandAdapter(receiver, store).command(request, Session())
        receiver.discovery = Discovery()
        session = Session()
        result = await c.CommandAdapter(receiver, store, store.value).command(request, session)
        assert result["status"] == "consumed_outcome_unknown" and not session.calls
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"channel": 3}, {"channel": True}, {"state": "toggle"},
    {"device_id": "unknown"}, {"url": "http://anything"}])
def test_input_boundaries(changes):
    async def run():
        _, receiver, store, request = fixture()
        session = Session()
        with pytest.raises(p.InvalidObservation):
            await c.CommandAdapter(receiver, store).command({**request, **changes}, session)
        assert not session.calls and store.value is None
    asyncio.run(run())


def test_pruning_does_not_reenable_old_on_and_ledger_remains_bounded():
    async def run():
        now, receiver, store, request = fixture()
        adapter = c.CommandAdapter(receiver, store)
        old = {**request, "state": "ON"}
        await adapter.command(old, Session())
        for number in range(1, 30):
            now[0] += timedelta(seconds=1)
            next_request = {**request, "attempt_id": f"execution:OFF:{number+1}",
                "issued_at": now[0].isoformat(), "expires_at": (now[0]+timedelta(seconds=30)).isoformat()}
            await adapter.command(next_request, Session())
        assert len(store.value["devices"][request["device_id"]]["attempts"]) == 12
        session = Session()
        with pytest.raises(p.InvalidObservation, match="retired"):
            await c.CommandAdapter(receiver, store, store.value).command(old, session)
        assert not session.calls and len(json.dumps(store.value)) < 22000
    asyncio.run(run())


@pytest.mark.parametrize("change", ["state", "address", "port", "identity"])
def test_real_discovery_allows_state_change_but_fences_endpoint_change(change):
    from tests.test_rootline_ha_observer import setup_state, discovery_fixture, wire
    from zeroconf import DNSText, DNSAddress, DNSService, current_time_millis
    import ipaddress
    o = importlib.import_module(package.__name__ + ".observer")
    async def run():
        now, receiver, store, request = fixture()
        clock, state = setup_state()
        clock.wall = now[0]
        request["device_id"] = "100204e9bc"
        shared, records = discovery_fixture(state)
        receiver.state = state
        receiver.discovery = o.EndpointDiscovery(shared)
        class ChangingSession(Session):
            def post(self, url, **kwargs):
                result = super().post(url, **kwargs)
                at = current_time_millis()
                if change in {"state", "identity"}:
                    text = wire(state, 2)
                    if change == "identity":
                        text = text.replace(b"100204e9bc", b"100204d497")
                    shared.cache.async_remove_records([records[1]])
                    shared.cache.async_add_records([DNSText(records[1].name, 16, 1, 120, text, created=at)])
                elif change == "address":
                    shared.cache.async_remove_records([records[2]])
                    shared.cache.async_add_records([DNSAddress(records[2].name, 1, 1, 120,
                        ipaddress.IPv4Address("10.0.0.3").packed, created=at)])
                else:
                    shared.cache.async_remove_records([records[0]])
                    shared.cache.async_add_records([DNSService(records[0].name,33,1,120,0,0,9999,records[0].server,created=at)])
                return result
        result = await c.CommandAdapter(receiver, store).command(request, ChangingSession())
        assert result["accepted"] is (change == "state")
    asyncio.run(run())
