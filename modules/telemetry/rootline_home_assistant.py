"""Home Assistant SONOFF adapter beneath ROOTLINE's existing execution rail.

Registry identity and original observation clocks are retained. An API receipt
is neither fresh hardware state nor proof that a command took effect.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
import re
import time
from urllib.parse import urlsplit

TRANSPORT = "home_assistant"
MODELS = {"100204e9bc": "4CHPROR3", "100204d497": "4CHPROR3", "1002851416": "MINIR4"}
MAX_MESSAGE_BYTES = 2_000_000


class HomeAssistantUnavailable(RuntimeError):
    pass


def selected(environ=None):
    source = os.environ if environ is None else environ
    value = str(source.get("ROOTLINE_SONOFF_TRANSPORT") or "ifttt_ewelink").strip()
    if value not in {"ifttt_ewelink", TRANSPORT}:
        raise HomeAssistantUnavailable("home_assistant_transport_selection_invalid")
    return value == TRANSPORT


def configuration(environ):
    raw = str(environ.get("ROOTLINE_HOME_ASSISTANT_URL") or "").strip().rstrip("/")
    token = str(environ.get("ROOTLINE_HOME_ASSISTANT_TOKEN") or "").strip()
    try:
        parts = urlsplit(raw)
        valid = (parts.scheme == "https" and bool(parts.hostname) and
            not parts.username and not parts.password and not parts.query and
            not parts.fragment and parts.path == "" and parts.port in (None, 443))
    except ValueError:
        valid = False
    if not valid or not token or any(c in token for c in "\r\n"):
        raise HomeAssistantUnavailable("home_assistant_not_configured")
    return raw, token


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _unique_id(device_id, channel):
    return (f"switch.{device_id}_power" if device_id == "1002851416"
            else f"switch.{device_id}_toggle_{channel}")


def bind_entities(device_id, devices, entities):
    """Resolve actual entity IDs from exact immutable MQTT unique IDs."""
    if device_id not in MODELS or not isinstance(devices, list) or not isinstance(entities, list):
        raise HomeAssistantUnavailable("home_assistant_registry_invalid")
    matches = [d for d in devices if isinstance(d, dict)
        and ["mqtt", device_id] in (d.get("identifiers") or [])]
    if (len(matches) != 1 or matches[0].get("manufacturer") != "SONOFF"
            or matches[0].get("model") != MODELS[device_id]
            or not matches[0].get("id") or matches[0].get("disabled_by") is not None):
        raise HomeAssistantUnavailable("home_assistant_device_binding_invalid")
    device = matches[0]
    count = 1 if device_id == "1002851416" else 4
    result = {}
    for channel in range(1, count + 1):
        rows = [e for e in entities if isinstance(e, dict)
            and e.get("platform") == "mqtt" and e.get("unique_id") == _unique_id(device_id, channel)]
        if (len(rows) != 1 or rows[0].get("device_id") != device["id"]
                or rows[0].get("disabled_by") is not None
                or not re.fullmatch(r"switch\.[a-z0-9_]+", str(rows[0].get("entity_id") or ""))):
            raise HomeAssistantUnavailable("home_assistant_entity_binding_invalid")
        result[channel] = rows[0]["entity_id"]
    if len(set(result.values())) != count:
        raise HomeAssistantUnavailable("home_assistant_entity_binding_invalid")
    return device, result


def normalize_snapshot(device_id, devices, entities, states, *, now):
    device, bound = bind_entities(device_id, devices, entities)
    if not isinstance(states, list) or _time(now) is None:
        raise HomeAssistantUnavailable("home_assistant_states_invalid")
    channels, clocks = [], []
    for channel, entity_id in bound.items():
        rows = [s for s in states if isinstance(s, dict) and s.get("entity_id") == entity_id]
        if len(rows) != 1:
            raise HomeAssistantUnavailable("home_assistant_state_binding_invalid")
        row = rows[0]
        # No read-time fallback: polling retained MQTT is not a fresh observation.
        raw_clock = row.get("last_reported")
        observed = _time(raw_clock)
        fresh = observed is not None and timedelta(0) <= now-observed <= timedelta(minutes=5)
        state = row.get("state")
        channels.append({"channel": channel, "entity_id": entity_id,
            "output_state": state.upper() if state in {"on", "off"} else "Unknown",
            "observation_fresh": bool(fresh), "observed_at": raw_clock,
            "native_auto_off_enabled": "Unknown", "native_auto_off_seconds": None,
            "power_restoration_state": "Unknown"})
        if observed is not None:
            clocks.append(observed)
    authoritative = (len(clocks) == len(channels) and all(c["observation_fresh"]
        and c["output_state"] in {"ON", "OFF"} for c in channels))
    value = {"adapter_version": "rootline_home_assistant.v1", "device_id": device_id,
        "device_model": MODELS[device_id], "device_uiid": 138 if device_id == "1002851416" else 4,
        "firmware": device.get("sw_version"), "ha_device_id": device["id"],
        "provider_control_calls": 0, "provider_calls": 3,
        "current_outputs_authoritative": False, "hardware_freshness": "Unknown",
        "online": "Unknown", "observation_fresh": False, "entity_reports_fresh": bool(authoritative),
        "retrieved_at": min(clocks).isoformat() if len(clocks) == len(channels) else None,
        "api_received_at": now.isoformat(), "freshness_clock_source": "home_assistant_entity_report",
        "timers_enabled": "Unknown", "timers_only_turn_off": "Unknown",
        "scenes_enabled": "Unknown", "interlock_enabled": "Unknown",
        "actuation_safety_complete": False, "actuation_configuration_safe": False,
        "commissioned_baseline_id": None, "commissioned_baseline_fresh": False,
        "channels": channels}
    value["response_digest"] = _digest(value)
    return value


def validate_discovery(device_id, channel, entity):
    discovery = (entity.get("discovery_data") or {}).get("payload") or {}
    device = discovery.get("device") or {}
    suffix = "power" if device_id == "1002851416" else f"toggle_{channel}"
    topic = f"cube2ha/switch/{device_id}/{suffix}/state"
    if (discovery.get("unique_id") != _unique_id(device_id, channel)
            or discovery.get("platform") != "switch"
            or discovery.get("state_topic") != topic
            or discovery.get("command_topic") != topic[:-5] + "set"
            or discovery.get("value_template") != "{{ value_json.state }}"
            or device.get("identifiers") != device_id
            or device.get("manufacturer") != "SONOFF"
            or device.get("model") != MODELS[device_id]):
        raise HomeAssistantUnavailable("home_assistant_mqtt_discovery_invalid")
    return discovery, topic


def mqtt_snapshot(device_id, devices, entities, states, debug, *, now):
    """Preserve received report provenance without assuming hardware origin.

    The bridge can publish after a cloud command acknowledgement. Even a new
    non-retained MQTT state therefore cannot independently prove actuation.
    """
    value = normalize_snapshot(device_id, devices, entities, states, now=now)
    _, bound = bind_entities(device_id, devices, entities)
    debug_entities = debug.get("entities") if isinstance(debug, dict) else None
    if not isinstance(debug_entities, list):
        raise HomeAssistantUnavailable("home_assistant_mqtt_debug_invalid")
    clocks = []
    for row in value["channels"]:
        channel, entity_id = row["channel"], bound[row["channel"]]
        matches = [e for e in debug_entities if isinstance(e, dict) and e.get("entity_id") == entity_id]
        if len(matches) != 1:
            raise HomeAssistantUnavailable("home_assistant_mqtt_binding_invalid")
        entity = matches[0]
        discovery, topic = validate_discovery(device_id, channel, entity)
        subscriptions = [sub for sub in entity.get("subscriptions") or []
            if isinstance(sub, dict) and sub.get("topic") == topic]
        if len(subscriptions) != 1:
            raise HomeAssistantUnavailable("home_assistant_mqtt_subscription_invalid")
        availability_topic = f"cube2ha/{device_id}/availability"
        availability = [sub for sub in entity.get("subscriptions") or []
            if isinstance(sub, dict) and sub.get("topic") == availability_topic]
        availability_ok = discovery.get("availability_topic") == availability_topic and len(availability) == 1
        if availability_ok:
            try:
                reports = availability[0].get("messages") or []
                last = max(reports, key=lambda m: _time(m.get("time")) or datetime.min.replace(tzinfo=timezone.utc))
                availability_ok = (last.get("topic") == availability_topic
                    and _time(last.get("time")) is not None and _time(last["time"]) <= now
                    and json.loads(last.get("payload")).get("online") is True)
            except (ValueError, TypeError, AttributeError):
                availability_ok = False
        messages = subscriptions[0].get("messages") or []
        parsed = []
        invalid = False
        for message in messages:
            if not isinstance(message, dict) or message.get("topic") != topic:
                invalid = True
                continue
            clock = _time(message.get("time"))
            try:
                payload = json.loads(message.get("payload"))
            except (ValueError, TypeError):
                payload = None
            if clock is None or not isinstance(payload, dict) or payload.get("state") not in {"ON", "OFF"}:
                invalid = True
                continue
            parsed.append((clock, message, payload["state"]))
        latest = max(parsed, key=lambda item: item[0]) if parsed else None
        # Never discard a newer unknown/retained/conflicting report in favour
        # of an older convenient state, nor turn receipt time into device time.
        row["observation_fresh"] = False
        row["observed_at"] = None
        if latest is not None:
            clock, message, state = latest
            same_clock = [item for item in parsed if item[0] == clock]
            valid = (availability_ok and not invalid and message.get("retain") is False
                and all(item[2] == state and item[1].get("retain") is False for item in same_clock)
                and row["output_state"] == state
                and timedelta(0) <= now-clock <= timedelta(minutes=5))
            row["observed_at"] = message["time"]
            row["observation_fresh"] = valid
            row["mqtt_retained"] = message.get("retain")
            if valid:
                clocks.append(clock)
    authoritative = len(clocks) == len(value["channels"])
    value.update(current_outputs_authoritative=False, mqtt_reports_fresh=authoritative,
        hardware_freshness="Unknown",
        online="Unknown", observation_fresh=False,
        retrieved_at=min(clocks).isoformat() if authoritative else None,
        freshness_clock_source="home_assistant_mqtt_received_state_report", provider_calls=4)
    value["response_digest"] = _digest({key: item for key, item in value.items() if key != "response_digest"})
    return value


def observer_snapshot(device_id, devices, entities, envelope, *, now, environ):
    device, bound = bind_entities(device_id, devices, entities)
    uiid = 138 if device_id == "1002851416" else 4
    if (not isinstance(envelope, dict) or envelope.get("contract_version") != "rootline_sonoff_observation.v1"
            or envelope.get("device_id") != device_id or envelope.get("model") != MODELS[device_id]
            or type(envelope.get("uiid")) is not int or envelope["uiid"] != uiid
            or type(envelope.get("control_commands")) is not int or envelope["control_commands"] != 0
            or envelope.get("maximum_age_seconds") != 60
            or envelope.get("source_authentication") != "unauthenticated_sonoff_lan_protocol"
            or not re.fullmatch(r"[0-9a-f]{32}", str(envelope.get("observer_epoch") or ""))):
        raise HomeAssistantUnavailable("home_assistant_observer_binding_invalid")
    generated = _time(envelope.get("generated_at"))
    if generated is None or not timedelta(0) <= now-generated <= timedelta(seconds=15):
        raise HomeAssistantUnavailable("home_assistant_observer_clock_invalid")
    rows = envelope.get("channels")
    if (not isinstance(rows, list) or len(rows) != len(bound)
            or any(not isinstance(row, dict) or type(row.get("channel")) is not int for row in rows)
            or {row["channel"] for row in rows} != set(bound)):
        raise HomeAssistantUnavailable("home_assistant_observer_channels_invalid")
    try:
        bindings = json.loads(environ.get("ROOTLINE_HOME_ASSISTANT_OBSERVER_BINDINGS") or "{}")
        expected = bindings.get(device_id) or {}
        qualified = (bool(expected.get("qualification_id"))
            and expected.get("qualification_id") == envelope.get("qualification_id")
            and bool(expected.get("generation")) and expected["generation"] == envelope.get("generation"))
    except (ValueError, TypeError, AttributeError):
        qualified = False
    channels, clocks = [], []
    for row in rows:
        observed = _time(row.get("received_at"))
        age = row.get("age_seconds")
        source = row.get("source")
        valid = (row.get("fresh") is True and row.get("state") in {"ON", "OFF"}
            and observed is not None and timedelta(0) <= now-observed <= timedelta(seconds=60)
            and type(age) in (int, float) and 0 <= age <= 60
            and abs((generated-observed).total_seconds()-age) <= 2
            and source in {"mdns", "query"}
            and row.get("sequence_kind") == ("device_revision" if source == "mdns" else "request_echo")
            and re.fullmatch(r"[0-9]{1,20}", str(row.get("sequence") or "")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", str(row.get("report_digest") or "")) is not None)
        channels.append({"channel": row["channel"], "entity_id": bound[row["channel"]],
            "output_state": row.get("state") if valid else "Unknown", "observation_fresh": bool(valid and qualified),
            "observed_at": row.get("received_at"), "observation_source": source,
            "native_auto_off_enabled": "Unknown", "native_auto_off_seconds": None,
            "power_restoration_state": "Unknown"})
        if valid:
            clocks.append(observed)
    authoritative = qualified and len(clocks) == len(channels)
    value = {"adapter_version": "rootline_home_assistant.v1", "device_id": device_id,
        "device_model": MODELS[device_id], "device_uiid": uiid, "firmware": device.get("sw_version"),
        "ha_device_id": device["id"], "provider_control_calls": 0, "provider_calls": 3,
        "current_outputs_authoritative": bool(authoritative), "online": True if authoritative else "Unknown",
        "observation_fresh": bool(authoritative), "observer_epoch": envelope["observer_epoch"],
        "observer_generation": envelope.get("generation"), "observer_qualification_id": envelope.get("qualification_id"),
        "observer_qualified": bool(qualified),
        "observer_source_authentication": envelope["source_authentication"],
        "retrieved_at": min(clocks).isoformat() if len(clocks) == len(channels) else None,
        "api_received_at": now.isoformat(), "freshness_clock_source": "sonoff_original_observation",
        "timers_enabled": "Unknown", "timers_only_turn_off": "Unknown", "scenes_enabled": "Unknown",
        "interlock_enabled": "Unknown", "actuation_safety_complete": False,
        "actuation_configuration_safe": False, "commissioned_baseline_id": None,
        "commissioned_baseline_fresh": False, "channels": channels}
    value["response_digest"] = _digest(value)
    return value


def canonical_borehole_timer(snapshot, *, connect_factory, now):
    """Reuse current sealed configuration without refreshing hardware clocks."""
    from copy import deepcopy
    from modules.telemetry.rootline_device_spine import (
        CanonicalAuthorityResolver, _resolved_evidence, _valid_evidence, load_device_record)
    from modules.telemetry.rootline_borehole_conditions import continuous_device_profile
    key = "ewelink:ewelink_owner_account:1002851416:1"
    if (snapshot.get("device_id") != "1002851416" or snapshot.get("device_model") != "MINIR4"
            or snapshot.get("device_uiid") != 138 or len(snapshot.get("channels") or []) != 1
            or snapshot["channels"][0].get("channel") != 1):
        return snapshot
    loaded = load_device_record(key, connect_factory=connect_factory)
    record = (loaded or {}).get("device_record") or {}
    if (not continuous_device_profile(record) or record.get("standing_authority") is not True
            or record.get("commissioning_stage") != "standing_active"):
        return snapshot
    reference = (record.get("commissioning_evidence") or {}).get("provider_readback")
    if (not _valid_evidence(reference) or reference.get("source") != "provider"
            or not _resolved_evidence(reference, CanonicalAuthorityResolver(connect_factory).evidence(reference))):
        return snapshot
    proved = _time(reference.get("observed_at"))
    if proved is None or proved > now:
        return snapshot
    # Repeat currentness checks on the payload read and seal its actual material.
    with connect_factory() as db, db.cursor() as cur:
        cur.execute("""select e.evidence_payload,e.evidence_sha256,
          e.current and not exists(select 1 from app_private.rootline_device_evidence_events x
            where x.evidence_id=e.evidence_id and x.event_type='invalidated')
          from app_private.rootline_device_commissioning_evidence e
          where e.evidence_id=%s and e.source=%s and e.observed_at=%s""",
          (reference["evidence_id"], reference["source"], reference["observed_at"]))
        row = cur.fetchone()
    if (not row or row[2] is not True or row[1] != reference["sha256"]
            or not isinstance(row[0], dict) or _digest(row[0]) != reference["sha256"]):
        return snapshot
    payload = row[0]
    body = payload.get("body") or {}
    channels = body.get("channels") or []
    if (payload.get("http_status") != 200 or body.get("device_id") != "1002851416"
            or (payload.get("params") or {}).get("device_id") != "1002851416"
            or not body.get("firmware") or body["firmware"] != snapshot.get("firmware")
            or len(channels) != 1 or type(channels[0].get("channel")) is not int
            or channels[0]["channel"] != 1 or channels[0].get("native_auto_off_enabled") is not False
            or type(channels[0].get("native_auto_off_seconds")) is not int
            or channels[0]["native_auto_off_seconds"] < 0):
        return snapshot
    result = deepcopy(snapshot)
    result["channels"][0].update(native_auto_off_enabled=False,
        native_auto_off_seconds=channels[0]["native_auto_off_seconds"],
        native_auto_off_evidence_source="canonical_provider_configuration",
        native_auto_off_observed_at=reference["observed_at"],
        native_auto_off_evidence_id=reference["evidence_id"],
        native_auto_off_evidence_sha256=reference["sha256"],
        native_auto_off_registry_generation=loaded["registry_generation"])
    result["response_digest"] = _digest({k: v for k, v in result.items() if k != "response_digest"})
    return result


class HomeAssistantClient:
    """Bounded session using the installed aiohttp dependency; no command retry."""
    def __init__(self, environ):
        self.environ = environ
        self.counter = 0
        self.socket = self.session = self.loop = None
        self.command_deadline = None

    def __enter__(self):
        import asyncio
        from modules.telemetry.rootline_cycle_budget import remaining_seconds
        self.base, self.token = configuration(self.environ)
        self.deadline = time.monotonic() + remaining_seconds(15)
        self.loop = asyncio.new_event_loop()
        try:
            self._run(self._open())
            return self
        except Exception:
            self.close()
            raise HomeAssistantUnavailable("home_assistant_connection_failed") from None

    def _run(self, awaitable):
        import asyncio
        async def bounded():
            async with asyncio.timeout(max(0, self.deadline-time.monotonic())):
                return await awaitable
        return self.loop.run_until_complete(bounded())

    async def _open(self):
        import aiohttp
        trace = aiohttp.TraceConfig()
        async def reject_redirect(*_):
            raise HomeAssistantUnavailable("home_assistant_redirect_refused")
        trace.on_request_redirect.append(reject_redirect)
        self.session = aiohttp.ClientSession(trust_env=False, trace_configs=[trace],
            cookie_jar=aiohttp.DummyCookieJar(),
            timeout=aiohttp.ClientTimeout(total=15))
        self.socket = await self.session.ws_connect(self.base + "/api/websocket",
            max_msg_size=MAX_MESSAGE_BYTES)
        if (await self.socket.receive_json()).get("type") != "auth_required":
            raise HomeAssistantUnavailable("home_assistant_protocol_invalid")
        await self.socket.send_json({"type": "auth", "access_token": self.token})
        if (await self.socket.receive_json()).get("type") != "auth_ok":
            raise HomeAssistantUnavailable("home_assistant_authentication_failed")

    def request(self, kind, **fields):
        if kind not in {"config/device_registry/list", "config/entity_registry/list", "mqtt/device/debug_info", "rootline_observer/snapshot", "rootline_observer/query", "call_service"}:
            raise HomeAssistantUnavailable("home_assistant_operation_invalid")
        async def exchange():
            if (kind == "call_service" and self.command_deadline is not None
                    and time.monotonic() >= self.command_deadline):
                raise HomeAssistantUnavailable("home_assistant_on_deadline_reached")
            self.counter += 1
            await self.socket.send_json({"id": self.counter, "type": kind, **fields})
            result = await self.socket.receive_json()
            if (result.get("id") != self.counter or result.get("type") != "result"
                    or result.get("success") is not True):
                raise HomeAssistantUnavailable("home_assistant_operation_unproven")
            return result.get("result")
        return self._run(exchange())

    def states(self):
        async def read():
            async with self.session.get(self.base + "/api/states", allow_redirects=False,
                    headers={"Authorization": "Bearer " + self.token}) as response:
                if response.status != 200:
                    raise HomeAssistantUnavailable("home_assistant_read_failed")
                raw = await response.content.read(MAX_MESSAGE_BYTES + 1)
                if len(raw) > MAX_MESSAGE_BYTES:
                    raise HomeAssistantUnavailable("home_assistant_response_invalid")
                return json.loads(raw)
        return self._run(read())

    def close(self):
        if self.loop is None:
            return
        async def shutdown():
            if self.session is not None:
                await self.session.close()
        try:
            self.loop.run_until_complete(shutdown())
        finally:
            self.loop.close()
            self.loop = None

    def __exit__(self, *_):
        self.close()


def read_command_route(device_id, *, environ, now=None, client_factory=HomeAssistantClient):
    """Authenticate exact existing MQTT bindings without asserting output state."""
    from modules.telemetry.rootline_command_acceptance import ROUTE, MODE, digest
    with client_factory(environ) as client:
        devices = client.request("config/device_registry/list")
        entities = client.request("config/entity_registry/list")
        device, bound = bind_entities(device_id, devices, entities)
        debug = client.request("mqtt/device/debug_info", device_id=device["id"])
        for channel, entity_id in bound.items():
            matches = [row for row in debug.get("entities") or []
                if isinstance(row, dict) and row.get("entity_id") == entity_id]
            if len(matches) != 1:
                raise HomeAssistantUnavailable("home_assistant_mqtt_binding_invalid")
            validate_discovery(device_id, channel, matches[0])
        reports = client.states() if device_id == "1002851416" else []
    checked = (now or datetime.now(timezone.utc)).isoformat()
    result = {"contract_version": ROUTE, "acceptance_mode": MODE,
        "device_id": device_id, "device_model": MODELS[device_id],
        "device_uiid": 138 if device_id == "1002851416" else 4,
        "firmware": device.get("sw_version"), "ha_device_id": device["id"],
        "command_route_ready": True, "route_checked_at": checked,
        "retrieved_at": checked, "freshness_clock_source": "authenticated_command_route_check",
        "current_outputs_authoritative": False, "observation_fresh": False,
        "online": "Unknown", "provider_control_calls": 0, "provider_calls": 3,
        "channels": [{"channel": channel, "entity_id": entity_id,
            "output_state": "Unknown", "observation_fresh": False, "observed_at": None}
            for channel, entity_id in bound.items()]}
    if device_id == "1002851416":
        matches = [row for row in reports if isinstance(row, dict) and row.get("entity_id") == bound[1]]
        result["reported_output_state"] = str(matches[0].get("state", "unknown")).upper() if len(matches) == 1 else "Unknown"
        # These are HA entity-report clocks, not a fresh hardware observation.
        # Keep their original values so an external OFF can be distinguished
        # from the cached OFF that preceded our accepted ON command.
        result["reported_state_changed_at"] = matches[0].get("last_changed") if len(matches) == 1 else None
        result["reported_state_updated_at"] = matches[0].get("last_updated") if len(matches) == 1 else None
        result["reported_state_source"] = "home_assistant_entity_report_not_independently_verified"
        result["provider_calls"] = 4
    result["response_digest"] = digest(result)
    return result


def read_registered_device(device_id, *, environ=None, now=None, not_before=None, commissioning_connect_factory=None, client_factory=HomeAssistantClient):
    source = os.environ if environ is None else environ
    if not selected(source):
        raise HomeAssistantUnavailable("home_assistant_not_selected")
    from modules.telemetry.rootline_command_acceptance import enabled
    if enabled(source):
        return read_command_route(device_id, environ=source, now=now, client_factory=client_factory)
    try:
        barrier = _time(not_before) if not_before is not None else None
        if not_before is not None and barrier is None:
            raise HomeAssistantUnavailable("home_assistant_command_clock_invalid")
        with client_factory(source) as client:
            devices = client.request("config/device_registry/list")
            entities = client.request("config/entity_registry/list")
            envelope = client.request("rootline_observer/snapshot", device_id=device_id)
            value = observer_snapshot(device_id, devices, entities, envelope,
                now=now or datetime.now(timezone.utc), environ=source)
            consumer_age = 30 if device_id == "1002851416" else 60
            observed = _time(value.get("retrieved_at"))
            refresh = (not value["current_outputs_authoritative"] or observed is None
                or not timedelta(0) <= (now or datetime.now(timezone.utc))-observed <= timedelta(seconds=consumer_age)
                or (barrier is not None and observed <= barrier))
            if (value.get("observer_qualified") is True and refresh
                    and str(source.get("ROOTLINE_HOME_ASSISTANT_OBSERVER_QUERY_ENABLED") or "").lower() == "true"):
                envelope = client.request("rootline_observer/query", device_id=device_id)
                value = observer_snapshot(device_id, devices, entities, envelope,
                    now=now or datetime.now(timezone.utc), environ=source)
                value["provider_calls"] = 4
                value["response_digest"] = _digest({key: item for key, item in value.items() if key != "response_digest"})
        # A cached pre-command value cannot prove startup or shutdown, even
        # when it remains inside the ordinary observation age. No clock is reset.
        observed = _time(value.get("retrieved_at"))
        if barrier is not None and (observed is None or observed <= barrier):
            value.update(current_outputs_authoritative=False, observation_fresh=False, online="Unknown")
            for row in value["channels"]:
                row.update(observation_fresh=False, output_state="Unknown")
            value["response_digest"] = _digest({key: item for key, item in value.items() if key != "response_digest"})
        if device_id == "1002851416":
            connect = commissioning_connect_factory
            database_url = str(source.get("DATABASE_URL") or "").strip()
            if connect is None and database_url:
                from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
                def connect():
                    return connect_bounded_rootline_postgres(database_url=database_url, read_only=True)
            if callable(connect):
                try:
                    value = canonical_borehole_timer(value, connect_factory=connect,
                        now=now or datetime.now(timezone.utc))
                except Exception:
                    # Unsupported or invalidated configuration remains Unknown.
                    pass
        return value
    except Exception:
        raise HomeAssistantUnavailable("home_assistant_read_failed") from None


def send_state(*, environ, device_id, channel, state, before_send=None,
               network_attempt=None, on_guard=None, idempotency_key=None, client_factory=HomeAssistantClient):
    attempted = False
    attempted_at = None
    try:
        if not selected(environ) or type(channel) is not int or state not in {"ON", "OFF"}:
            raise HomeAssistantUnavailable("home_assistant_command_invalid")
        if state == "ON" and not callable(on_guard):
            raise HomeAssistantUnavailable("home_assistant_on_guard_required")
        with client_factory(environ) as client:
            devices = client.request("config/device_registry/list")
            entities = client.request("config/entity_registry/list")
            device, bound = bind_entities(device_id, devices, entities)
            entity_id = bound[channel]
            debug = client.request("mqtt/device/debug_info", device_id=device["id"])
            matches = [row for row in debug.get("entities") or []
                if isinstance(row, dict) and row.get("entity_id") == entity_id]
            if len(matches) != 1:
                raise HomeAssistantUnavailable("home_assistant_mqtt_binding_invalid")
            validate_discovery(device_id, channel, matches[0])
            if before_send is not None:
                before_send()
            if state == "ON":
                # Registry/debug preparation may consume the remaining claim
                # window. Recheck both the wall/ownership closure and the
                # independent monotonic bound immediately beside service I/O.
                deadline = on_guard()
                if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                        or time.monotonic() >= deadline):
                    raise HomeAssistantUnavailable("home_assistant_on_deadline_reached")
            if network_attempt is not None:
                network_attempt()
            if state == "ON":
                # A caller's durable-attempt callback may itself block. Neither
                # it nor event-loop scheduling may extend the admitted edge.
                final_deadline = on_guard()
                if (type(final_deadline) not in (int, float) or not math.isfinite(final_deadline)
                        or time.monotonic() >= min(deadline, final_deadline)):
                    raise HomeAssistantUnavailable("home_assistant_on_deadline_reached")
                client.command_deadline = min(deadline, final_deadline)
                client.deadline = min(getattr(client, "deadline", client.command_deadline), client.command_deadline)
            attempted_at = datetime.now(timezone.utc).isoformat()
            attempted = True
            service_result = client.request("call_service", domain="switch",
                service="turn_on" if state == "ON" else "turn_off",
                target={"entity_id": entity_id})
        from modules.telemetry.rootline_command_acceptance import RECEIPT, digest
        receipt = {"contract_version": RECEIPT, "accepted_unambiguous": True, "status": "accepted",
            "provider_command_attempted": True, "provider": TRANSPORT,
            "device_id": device_id, "channel": channel, "entity_id": entity_id,
            "requested_state": state, "idempotency_key": idempotency_key,
            "command_attempted_at": attempted_at, "accepted_at": datetime.now(timezone.utc).isoformat()}
        receipt["receipt_sha256"] = digest(receipt)
        return receipt
    except Exception:
        return {"accepted_unambiguous": False,
            "status": "provider_outcome_ambiguous" if attempted else "home_assistant_command_not_sent",
            "provider_command_attempted": attempted, "provider": TRANSPORT,
            **({"command_attempted_at": attempted_at} if attempted else {})}
