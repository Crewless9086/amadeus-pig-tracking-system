"""Least-privilege state-setting transport for registered ROOTLINE devices.

The adapter owns no eligibility or scheduling. It obtains safety/output truth
from eWeLink and emits the registry-bound event for a caller-owned idempotency
identity. Auxiliary authority remains independently disabled by default.
"""
from __future__ import annotations

import json
import os
from urllib import parse as urllib_parse, request as urllib_request
from modules.telemetry.rootline_device_registry import find_device_contract

DEVICE_ID = "100204e9bc"
EVENTS = {
    (1, "ON"): "irrigation_1_ch1_on", (1, "OFF"): "irrigation_1_ch1_off",
    (2, "ON"): "irrigation_1_ch2_on", (2, "OFF"): "irrigation_1_ch2_off",
}


class RootlineIFTTTTransport:
    def __init__(self, *, token_store, environ=None, http_open=None,
                 readback=None):
        self.environ = environ if environ is not None else os.environ
        self.token_store = token_store
        self.http_open = http_open or urllib_request.urlopen
        if readback is None:
            from modules.telemetry.rootline_ewelink_readback import read_current_device
            readback = read_current_device
        self.readback = readback

    def read_safety_configuration(self, *, device_id, channel):
        contract = self._binding(device_id, channel)
        snapshot = self._snapshot(device_id, channel)
        row = self._channel(snapshot, channel)
        return {
            "authoritative": snapshot.get("actuation_configuration_safe") is True,
            "zone_id": contract["identity"] if contract["collection"] == "irrigation_zones" else None,
            "auxiliary_device_id": (contract["identity"]
                if contract["collection"] == "irrigation_auxiliary_devices" else None),
            "device_type": contract["device_type"],
            "channel": channel,
            "native_inching_enabled": row.get("native_auto_off_enabled"),
            "native_inching_seconds": row.get("native_auto_off_seconds"),
            "power_restoration_state": row.get("power_restoration_state"),
            "schedules_enabled": snapshot.get("timers_enabled"),
            "interlock_enabled": snapshot.get("interlock_enabled"),
            "scenes_enabled": snapshot.get("scenes_enabled"),
            "baseline_id": snapshot.get("commissioned_baseline_id"),
            "response_digest": snapshot.get("response_digest"),
        }

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
                and str(self.environ.get(contract["authority_flag"]) or "").lower() != "true"):
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
        self._binding(device_id, channel)
        value = self.readback(token_store=self.token_store, environ=self.environ)
        rows = value.get("channels") if isinstance(value, dict) else None
        identities = [row.get("channel") for row in rows or () if isinstance(row, dict)]
        if (not isinstance(value, dict) or value.get("device_id") != device_id
                or len(rows or ()) != 4 or sorted(identities) != [1, 2, 3, 4]
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
