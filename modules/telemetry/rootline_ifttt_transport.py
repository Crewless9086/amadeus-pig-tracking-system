"""Least-privilege state-setting transport for registered ROOTLINE devices.

The adapter owns no eligibility or scheduling. It obtains safety/output truth
from eWeLink and emits the registry-bound event for a caller-owned idempotency
identity. Auxiliary authority remains independently disabled by default.
"""
from __future__ import annotations

import json
import os
from urllib import parse as urllib_parse, request as urllib_request
from modules.telemetry.rootline_device_registry import (
    device_channel_assignments,
    find_device_contract,
)

DEVICE_ID = "100204e9bc"
EVENTS = {
    (1, "ON"): "irrigation_1_ch1_on", (1, "OFF"): "irrigation_1_ch1_off",
    (2, "ON"): "irrigation_1_ch2_on", (2, "OFF"): "irrigation_1_ch2_off",
}


class RootlineIFTTTTransport:
    def __init__(self, *, token_store, environ=None, http_open=None,
                 readback=None, auxiliary_on_authorizer=None):
        self.environ = environ if environ is not None else os.environ
        self.token_store = token_store
        self.http_open = http_open or urllib_request.urlopen
        self.readback = readback
        self.auxiliary_on_authorizer = auxiliary_on_authorizer

    def read_safety_configuration(self, *, device_id, channel):
        contract = self._binding(device_id, channel)
        snapshot = self._snapshot(device_id, channel)
        row = self._channel(snapshot, channel)
        supervised_channels = snapshot.get("commissioned_supervised_channels") or []
        channel_commissioning = (contract["identity"] == "FERTILIZER-MIXER-CH2"
            and channel in supervised_channels)
        if contract["collection"] == "irrigation_zones":
            channel_commissioning = bool(snapshot.get("commissioned_baseline_id"))
        authoritative = snapshot.get("actuation_configuration_safe") is True
        if contract["collection"] == "irrigation_auxiliary_devices":
            authoritative = self._auxiliary_commissioning_boundary_safe(
                snapshot, contract, row)
        return {
            "authoritative": authoritative,
            "device_id": snapshot.get("device_id"),
            "zone_id": contract["identity"] if contract["collection"] == "irrigation_zones" else None,
            "auxiliary_device_id": (contract["identity"]
                if contract["collection"] == "irrigation_auxiliary_devices" else None),
            "device_type": contract["device_type"],
            "channel": channel,
            "output_state": row.get("output_state"),
            "native_inching_enabled": row.get("native_auto_off_enabled"),
            "native_inching_seconds": row.get("native_auto_off_seconds"),
            "power_restoration_state": row.get("power_restoration_state"),
            "schedules_enabled": snapshot.get("timers_enabled"),
            "timers_enabled": snapshot.get("timers_enabled"),
            "interlock_enabled": snapshot.get("interlock_enabled"),
            "scenes_enabled": snapshot.get("scenes_enabled"),
            "baseline_id": snapshot.get("commissioned_baseline_id"),
            "controller_safety_generation": snapshot.get("commissioned_baseline_id"),
            "physical_commissioning_generation": (snapshot.get("commissioned_baseline_id")
                if channel_commissioning else None),
            "commissioned": channel_commissioning,
            "response_digest": snapshot.get("response_digest"),
            "observed_at": snapshot.get("retrieved_at"),
            "relevant_outputs_off": all(
                item.get("output_state") == "OFF" for item in snapshot["channels"]),
        }

    def _auxiliary_commissioning_boundary_safe(self, snapshot, contract, target):
        """Project exact supervised safety without weakening full-device evidence."""
        assignments = device_channel_assignments(contract["device_id"])
        rows = {int(row["channel"]): row for row in snapshot["channels"]}
        if contract["identity"] == "BOREHOLE-1-MINI-R4-CH1":
            return (set(assignments) == {1} and set(rows) == {1}
                and snapshot.get("current_outputs_authoritative") is True
                and snapshot.get("timers_enabled") is False
                and snapshot.get("scenes_enabled") is False
                and snapshot.get("interlock_enabled") is False
                and target.get("output_state") == "OFF"
                and target.get("power_restoration_state") == "OFF"
                and target.get("native_auto_off_enabled") is True
                and int(target.get("native_auto_off_seconds") or 0) == 14400)
        if (snapshot.get("actuation_safety_complete") is not True
                or snapshot.get("current_outputs_authoritative") is not True
                or snapshot.get("timers_enabled") is not False
                or snapshot.get("scenes_enabled") is not False
                or snapshot.get("interlock_enabled") is not False
                or set(rows) != {1, 2, 3, 4}
                or any(row.get("output_state") != "OFF" for row in rows.values())
                or any(row.get("power_restoration_state") != "OFF"
                       for row in rows.values())):
            return False
        if (contract["identity"] == "FERTILIZER-MIXER-CH2"
                and set(assignments) != {1, 2}):
            return False
        if (target.get("native_auto_off_enabled") is not True
                or int(target.get("native_auto_off_seconds") or 0)
                    != int(contract["native_fail_stop_seconds"])):
            return False
        for assigned_channel, assigned in assignments.items():
            if assigned_channel == int(contract["channel"]):
                continue
            if (contract["identity"] == "FERTILIZER-MIXER-CH2"
                    and assigned.get("identity") != "FERTILIZER-INJECTION-CH1"):
                return False
            assigned_row = rows.get(assigned_channel) or {}
            if (str(self.environ.get(assigned["authority_flag"]) or "").lower() == "true"
                    or assigned_row.get("native_auto_off_enabled") is not True
                    or int(assigned_row.get("native_auto_off_seconds") or 0)
                        != int(assigned["native_fail_stop_seconds"])):
                return False
        return True

    def configuration_status(self, *, device_id, channel):
        """Return non-secret transport readiness without a provider call."""
        contract = self._binding(device_id, channel)
        return {"configured": bool(contract.get("on_event") and contract.get("off_event")
                                    and str(self.environ.get(
                                        "ROOTLINE_IFTTT_MAKER_KEY") or "").strip()),
                "device_id": device_id, "channel": channel}

    def read_output_state(self, *, device_id, channel):
        snapshot = self._snapshot(device_id, channel)
        row = self._channel(snapshot, channel)
        return {"authoritative": snapshot.get("current_outputs_authoritative") is True,
                "state": row.get("output_state"),
                "evidence_id": snapshot.get("response_digest"),
                "retrieved_at": snapshot.get("retrieved_at")}

    def set_state(self, *, device_id, channel, state, idempotency_key):
        contract = self._binding(device_id, channel)
        state = str(state or "").upper()
        if (state == "ON" and contract["collection"] == "irrigation_auxiliary_devices"
                and str(self.environ.get(contract["authority_flag"]) or "").lower() != "true"
                and not (callable(self.auxiliary_on_authorizer)
                         and self.auxiliary_on_authorizer(device_id=device_id,
                             channel=channel, idempotency_key=str(idempotency_key)))):
            return {"accepted_unambiguous": False, "status": "auxiliary_authority_disabled"}
        event = contract.get("on_event" if state == "ON" else "off_event" if state == "OFF" else "")
        secret = str(self.environ.get("ROOTLINE_IFTTT_MAKER_KEY") or "").strip()
        if not event or not secret or not str(idempotency_key or "").strip():
            return {"accepted_unambiguous": False, "status": "transport_not_configured"}
        url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(
            event, urllib_parse.quote(secret, safe=""))
        body = json.dumps({"value1": str(idempotency_key), "value2": device_id,
                           "value3": str(channel)}).encode()
        req = urllib_request.Request(url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.http_open(req, timeout=15) as response:
                code = int(getattr(response, "status", response.getcode()))
                response.read(4096)
        except Exception:
            return {"accepted_unambiguous": False, "status": "provider_outcome_ambiguous"}
        return {"accepted_unambiguous": 200 <= code < 300,
                "status": "accepted" if 200 <= code < 300 else "rejected",
                "event": event, "provider_status": code}

    def _snapshot(self, device_id, channel):
        contract = self._binding(device_id, channel)
        if self.readback is None:
            from modules.telemetry.rootline_ewelink_readback import read_registered_device
            value = read_registered_device(device_id, token_store=self.token_store,
                                           environ=self.environ)
        else:
            value = self.readback(token_store=self.token_store, environ=self.environ)
        rows = value.get("channels") if isinstance(value, dict) else None
        identities = [row.get("channel") for row in rows or () if isinstance(row, dict)]
        expected = ([1] if contract.get("identity") == "BOREHOLE-1-MINI-R4-CH1"
                    else [1, 2, 3, 4])
        if (not isinstance(value, dict) or value.get("device_id") != device_id
                or sorted(identities) != expected
                or value.get("provider_control_calls") != 0):
            raise RuntimeError("ewelink_safety_readback_invalid")
        return value

    @staticmethod
    def _channel(snapshot, channel):
        return next(row for row in snapshot["channels"] if row["channel"] == channel)

    @staticmethod
    def _binding(device_id, channel):
        try:
            return find_device_contract(device_id, channel)
        except (TypeError, ValueError):
            raise ValueError("rootline_device_transport_binding_invalid")
