"""Bounded authenticated transport; programme ownership remains in ROOTLINE."""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re

from .protocol import MAX_BYTES, crypt, digest, need

CHANNELS = {"100204e9bc": (1, 2, 3, 4), "100204d497": (1, 2), "1002851416": (1,)}
VERSION = "rootline_controller_command.v1"


def timestamp(value):
    need(isinstance(value, str), "command_clock_invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        need(False, "command_clock_invalid")
    need(result.tzinfo is not None, "command_clock_invalid")
    return result.astimezone(timezone.utc)


def validate(request, now):
    need(isinstance(request, dict) and set(request) == {
        "device_id", "channel", "state", "attempt_id", "issued_at", "expires_at"}, "command_binding_invalid")
    identity = request["device_id"]
    need(identity in CHANNELS and type(request["channel"]) is int
         and request["channel"] in CHANNELS[identity], "command_channel_not_allowed")
    need(request["state"] in ("ON", "OFF"), "command_state_invalid")
    need(isinstance(request["attempt_id"], str)
         and re.fullmatch(r"[A-Za-z0-9_:.-]{8,200}", request["attempt_id"]), "command_attempt_invalid")
    issued, expires = timestamp(request["issued_at"]), timestamp(request["expires_at"])
    need(0 < (expires-issued).total_seconds() <= 60 and issued <= now <= expires,
         "command_request_expired")
    return identity, issued


class CommandAdapter:
    """A consumed request is never sent again, including after HA restart."""

    def __init__(self, receiver, store, persisted=None):
        self.receiver, self.store = receiver, store
        self.locks = {identity: asyncio.Lock() for identity in CHANNELS}
        self.storage_lock = asyncio.Lock()
        self.failed = False
        self.ledger = persisted if persisted is not None else {"version": 1, "devices": {}}
        need(isinstance(self.ledger, dict) and self.ledger.get("version") == 1
             and isinstance(self.ledger.get("devices"), dict), "command_store_invalid")
        for identity, bucket in self.ledger["devices"].items():
            need(identity in CHANNELS and isinstance(bucket, dict)
                 and isinstance(bucket.get("attempts"), dict) and len(bucket["attempts"]) <= 12,
                 "command_store_invalid")
            timestamp(bucket["floor"])
            for attempt_id, record in bucket["attempts"].items():
                need(isinstance(record, dict) and isinstance(record.get("result"), dict), "command_store_invalid")
                result = record["result"]
                original = {key: result.get(key) for key in
                    ("device_id", "channel", "state", "attempt_id", "issued_at", "expires_at")}
                validate(original, timestamp(original["issued_at"]))
                need(original["device_id"] == identity and original["attempt_id"] == attempt_id
                    and record.get("binding") == digest(original)
                    and timestamp(record.get("issued_at")) == timestamp(original["issued_at"]), "command_store_invalid")
                need(result.get("version") == VERSION and type(result.get("accepted")) is bool
                    and result.get("availability") in {"online", "unknown"}
                    and result.get("status") in {"consumed_outcome_unknown", "controller_rejected",
                        "controller_accepted", "controller_response_unproven", "controller_not_sent"}
                    and (result.get("controller_command_attempted") is None
                        or type(result.get("controller_command_attempted")) is bool), "command_store_invalid")
                consumed = timestamp(result.get("consumed_at"))
                need(timestamp(original["issued_at"]) <= consumed <= timestamp(original["expires_at"]), "command_store_invalid")
                if result["accepted"]:
                    need(result["status"] == "controller_accepted" and result["availability"] == "online"
                        and result.get("controller_command_attempted") is True
                        and timestamp(result.get("responded_at")) >= consumed
                        and isinstance(result.get("response_digest"), str)
                        and re.fullmatch(r"[0-9a-f]{64}", result["response_digest"]), "command_store_invalid")
                else:
                    need(result["status"] != "controller_accepted", "command_store_invalid")

    async def save(self, candidate):
        try:
            await self.store.async_save(candidate)
        except BaseException:
            self.failed = True
            raise
        self.ledger = candidate

    async def command(self, request, session):
        now = self.receiver.state.utcnow()
        identity, issued = validate(request, now)
        need(identity in self.receiver.state.config["devices"], "device_not_allowed")
        async with self.locks[identity]:
            need(not self.failed and not self.receiver.closed, "command_adapter_unavailable")
            binding = digest(request)
            async with self.storage_lock:
                candidate = deepcopy(self.ledger)
                for other in candidate["devices"].values():
                    duplicate = other["attempts"].get(request["attempt_id"])
                    need(duplicate is None or duplicate["binding"] == binding, "command_attempt_conflict")
                bucket = candidate["devices"].setdefault(identity,
                    {"floor": "1970-01-01T00:00:00+00:00", "attempts": {}})
                previous = bucket["attempts"].get(request["attempt_id"])
                if previous is not None:
                    need(previous["binding"] == binding, "command_attempt_conflict")
                    return deepcopy(previous["result"])
                need(all(issued > timestamp(other["floor"]) for other in candidate["devices"].values()),
                    "command_attempt_retired")
                need(issued > timestamp(bucket["floor"]), "command_attempt_retired")
                if len(bucket["attempts"]) >= 12:
                    oldest = min(bucket["attempts"], key=lambda key: bucket["attempts"][key]["issued_at"])
                    removed = bucket["attempts"].pop(oldest)
                    bucket["floor"] = max(timestamp(bucket["floor"]), timestamp(removed["issued_at"])).isoformat()
                    need(issued > timestamp(bucket["floor"]), "command_attempt_retired")
                result = {"version": VERSION, **request, "accepted": False,
                    "availability": "unknown", "status": "consumed_outcome_unknown",
                    "controller_command_attempted": None,
                    "consumed_at": now.isoformat(), "responded_at": None}
                bucket["attempts"][request["attempt_id"]] = {
                    "binding": binding, "issued_at": issued.isoformat(), "result": result}
                await self.save(candidate)
            # The durable claim precedes discovery and network. Cancellation leaves it consumed.
            network_started = False
            try:
                device = self.receiver.state.config["devices"][identity]
                endpoint = device.get("endpoint")
                discovery = self.receiver.discovery
                need(discovery is not None, "command_discovery_unavailable")
                resolved, token = await discovery.resolve(identity)
                need(endpoint is None or (endpoint["address"] == resolved["address"]
                     and endpoint["port"] == resolved["port"]), "discovery_config_conflict")
                discovery.validate_command_endpoint(identity, token)
                need(self.receiver.state.utcnow() <= timestamp(request["expires_at"]), "command_request_expired")
                sequence = str(int(issued.timestamp()*1000))
                state = request["state"].lower()
                if identity == "1002851416":
                    path, params = "switch", {"switch": state}
                else:
                    path, params = "switches", {"switches": [{"outlet": request["channel"]-1, "switch": state}]}
                iv = os.urandom(16)
                payload = {"deviceid": identity, "sequence": sequence, "selfApikey": "123", "encrypt": True,
                    "iv": base64.b64encode(iv).decode(),
                    "data": base64.b64encode(crypt(json.dumps(params).encode(), device["device_key"], iv, encrypt=True)).decode()}
                async with asyncio.timeout(5):
                    need(not self.receiver.closed
                        and self.receiver.state.utcnow() <= timestamp(request["expires_at"]), "command_request_expired")
                    network_started = True
                    result["controller_command_attempted"] = True
                    async with session.post(f"http://{resolved['address']}:{resolved['port']}/zeroconf/{path}",
                            json=payload, allow_redirects=False, headers={"Connection": "close"}) as response:
                        need(response.status == 200, "command_http_unproven")
                        raw = await response.content.read(MAX_BYTES+1)
                        need(len(raw) <= MAX_BYTES, "command_response_too_large")
                        data = json.loads(raw)
                        need(isinstance(data, dict), "command_response_invalid")
                        need("deviceid" not in data or data["deviceid"] == identity, "command_identity_mismatch")
                        need("sequence" not in data or data["sequence"] == sequence, "command_sequence_mismatch")
                        discovery.validate_command_endpoint(identity, token)
                        result = {**result, "availability": "online", "responded_at": self.receiver.state.utcnow().isoformat(),
                            "response_digest": digest(data), "status": "controller_rejected"}
                        if type(data.get("error")) is int and data["error"] == 0:
                            result.update(accepted=True, status="controller_accepted")
                            if hasattr(self.receiver, "availability"):
                                self.receiver.availability[identity] = {"state": "online",
                                    "checked_at": result["responded_at"], "source": "controller_command_response",
                                    "output_state": "Unknown"}
            except asyncio.CancelledError:
                raise
            except Exception:
                result = {**result, "status": "controller_response_unproven" if network_started else "controller_not_sent",
                    "controller_command_attempted": network_started}
            async with self.storage_lock:
                candidate = deepcopy(self.ledger)
                candidate["devices"][identity]["attempts"][request["attempt_id"]]["result"] = result
                await self.save(candidate)
            return deepcopy(result)
