"""ROOTLINE observation and bounded transport for commissioned SONOFF identities."""
from __future__ import annotations

import voluptuous as vol
import zeroconf as zeroconf_library
from homeassistant.components import websocket_api, zeroconf
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, __version__ as HA_VERSION
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .protocol import DEVICES, InvalidObservation, ObserverState, config_validate
from .observer import EndpointDiscovery, RawListener, Receiver
from .storage import VerifiedStore
from .command import CommandAdapter

DOMAIN = "rootline_observer"
# Exact initial qualification target, not an untested minimum-version promise.
QUALIFIED_HA_VERSION = "2026.8.3"
QUALIFIED_ZEROCONF_VERSION = "0.150.0"
CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): dict}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    if DOMAIN not in config:
        return True
    if HA_VERSION != QUALIFIED_HA_VERSION or zeroconf_library.__version__ != QUALIFIED_ZEROCONF_VERSION:
        return False
    try:
        private = config_validate(config[DOMAIN])
        store = VerifiedStore(Store(hass, 1, DOMAIN + "_sequence", private=True, atomic_writes=True),
            hass.async_add_executor_job)
        persisted = await store.async_load()
        state = ObserverState(private, persisted)
    except Exception:
        # Do not hand exception/config repr to HA logs: it may contain keys.
        return False
    shared = await zeroconf.async_get_instance(hass)
    receiver = Receiver(state, store,
        lambda coroutine: hass.async_create_background_task(coroutine, DOMAIN + ":receive"),
        discovery=EndpointDiscovery(shared))
    try:
        commands = VerifiedStore(Store(hass, 1, DOMAIN + "_commands", private=True, atomic_writes=True),
            hass.async_add_executor_job)
        command_adapter = CommandAdapter(receiver, commands, await commands.async_load())
    except Exception:
        command_adapter = None
    listener = RawListener(receiver)
    # None deliberately avoids RecordManager's cached-record seed path.
    shared.async_add_listener(listener, None)
    hass.data[DOMAIN] = {"receiver": receiver, "listener": listener, "zeroconf": shared,
        "command_adapter": command_adapter}

    async def stop(_event):
        listener.closed = True
        shared.async_remove_listener(listener)
        await receiver.stop()
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop)
    websocket_api.async_register_command(hass, snapshot)
    websocket_api.async_register_command(hass, query)
    websocket_api.async_register_command(hass, command)
    return True


def permitted(hass, connection, message):
    runtime = hass.data.get(DOMAIN)
    user = connection.user
    if (runtime is None or user is None or not user.is_active
            or user.id not in runtime["receiver"].state.config["allowed_user_ids"]):
        connection.send_error(message["id"], "unauthorized", "Observer access denied")
        return None
    if runtime["zeroconf"].done or runtime["listener"].closed:
        runtime["receiver"].state.healthy = False
        connection.send_error(message["id"], "observer_unavailable", "Observer is stopped")
        return None
    return runtime["receiver"]


@websocket_api.websocket_command({"type": DOMAIN + "/snapshot", vol.Required("device_id"): vol.In(DEVICES)})
@websocket_api.async_response
async def snapshot(hass, connection, message):
    receiver = permitted(hass, connection, message)
    if receiver is None:
        return
    try:
        result = receiver.state.snapshot(message["device_id"])
        adapter = hass.data[DOMAIN]["command_adapter"]
        result["command_capability"] = {"contract_version": "rootline_controller_command.v1",
            "available": adapter is not None and not adapter.failed, "physical_state_proof": False}
        result["controller_availability"] = receiver.availability.get(message["device_id"], {"state": "unknown"})
    except InvalidObservation:
        connection.send_error(message["id"], "device_not_allowed", "Device is not configured")
        return
    connection.send_result(message["id"], result)


@websocket_api.websocket_command({"type": DOMAIN + "/query", vol.Required("device_id"): vol.In(DEVICES)})
@websocket_api.async_response
async def query(hass, connection, message):
    receiver = permitted(hass, connection, message)
    if receiver is None:
        return
    try:
        status = await receiver.query(message["device_id"], async_get_clientsession(hass))
        result = receiver.state.snapshot(message["device_id"])
        result["query_status"] = status
        result["controller_availability"] = receiver.availability.get(message["device_id"], {"state": "unknown"})
    except InvalidObservation:
        connection.send_error(message["id"], "query_not_available", "Read-only query is unavailable")
        return
    connection.send_result(message["id"], result)


@websocket_api.websocket_command({"type": DOMAIN + "/command",
    vol.Required("device_id"): vol.In(DEVICES), vol.Required("channel"): int,
    vol.Required("state"): vol.In(("ON", "OFF")), vol.Required("attempt_id"): str,
    vol.Required("issued_at"): str, vol.Required("expires_at"): str})
@websocket_api.async_response
async def command(hass, connection, message):
    receiver = permitted(hass, connection, message)
    if receiver is None:
        return
    try:
        if hass.data[DOMAIN]["command_adapter"] is None:
            raise InvalidObservation("command_adapter_unavailable")
        request = {key: message[key] for key in
            ("device_id", "channel", "state", "attempt_id", "issued_at", "expires_at")}
        result = await hass.data[DOMAIN]["command_adapter"].command(request, async_get_clientsession(hass))
    except Exception:
        connection.send_error(message["id"], "command_unproven", "Controller command outcome is unproven")
        return
    connection.send_result(message["id"], result)
