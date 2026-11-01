"""Least-privilege state-setting transport for registered ROOTLINE devices.

The adapter owns no eligibility or scheduling. It obtains safety/output truth
from eWeLink and emits the registry-bound event for a caller-owned idempotency
identity. Auxiliary authority remains independently disabled by default.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import time
from datetime import datetime, timezone, timedelta
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


def output_evidence_from_snapshot(snapshot, *, device_id, channel):
    """Preserve target readback and full irrigation-output dependency evidence."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    channels = snapshot.get("channels")
    rows = [row for row in (channels if isinstance(channels, list) else []) if isinstance(row, dict)
            and type(row.get("channel")) is int and row["channel"] == channel]
    matched = (snapshot.get("device_id") == device_id and type(channel) is int
        and len(rows) == 1)
    result = {"authoritative": matched and snapshot.get("current_outputs_authoritative") is True,
        "state": rows[0].get("output_state") if matched else "Unknown",
        "device_id": snapshot.get("device_id"),
        "channel": rows[0].get("channel") if matched else None,
        "evidence_id": snapshot.get("response_digest"),
        "retrieved_at": snapshot.get("retrieved_at")}
    if device_id == DEVICE_ID and type(channel) is int and channel in (1, 2, 4):
        result["irrigation_output_evidence"] = {
            "device_id": snapshot.get("device_id"),
            "current_outputs_authoritative": snapshot.get("current_outputs_authoritative"),
            "provider_control_calls": snapshot.get("provider_control_calls"),
            "response_digest": snapshot.get("response_digest"),
            "retrieved_at": snapshot.get("retrieved_at"),
            "channels": deepcopy(channels),
        }
    return result


def irrigation_dependency_verified(output, *, device_id, channel, now):
    """Require one exact B/C output ON and all other irrigation outputs OFF."""
    if (device_id != DEVICE_ID or type(channel) is not int or channel not in (1, 2)
            or not isinstance(output, dict) or output.get("authoritative") is not True
            or output.get("state") != "ON" or output.get("device_id") != device_id
            or type(output.get("channel")) is not int or output["channel"] != channel):
        return False
    proof = output.get("irrigation_output_evidence")
    if (not isinstance(proof, dict) or proof.get("device_id") != device_id
            or proof.get("current_outputs_authoritative") is not True
            or not isinstance(proof.get("response_digest"), str)
            or len(proof["response_digest"]) != 64
            or any(char not in "0123456789abcdef" for char in proof["response_digest"])
            or type(proof.get("provider_control_calls")) is not int
            or proof["provider_control_calls"] != 0
            or proof["response_digest"] != output.get("evidence_id")
            or proof.get("retrieved_at") != output.get("retrieved_at")
            or ("response_digest" in output
                and output["response_digest"] != proof["response_digest"])):
        return False
    rows = proof.get("channels")
    if (not isinstance(rows, list) or len(rows) != 4
            or any(not isinstance(row, dict) or type(row.get("channel")) is not int
                   for row in rows)
            or {row["channel"] for row in rows} != {1, 2, 3, 4}
            or any(row.get("output_state") != ("ON" if row["channel"] == channel else "OFF")
                   for row in rows)):
        return False
    raw_observed = proof.get("retrieved_at")
    if not isinstance(raw_observed, (str, datetime)):
        return False
    try:
        observed = (raw_observed if isinstance(raw_observed, datetime) else
            datetime.fromisoformat(raw_observed.replace("Z", "+00:00")))
        if "observed_at" in output:
            reported = output["observed_at"]
            reported = (reported if isinstance(reported, datetime) else
                datetime.fromisoformat(str(reported).replace("Z", "+00:00")))
            if reported != observed:
                return False
        return (isinstance(now, datetime) and now.tzinfo is not None
            and now.utcoffset() is not None and observed.tzinfo is not None
            and observed.utcoffset() is not None
            and timedelta(0) <= now-observed <= timedelta(minutes=5))
    except (TypeError, ValueError, OverflowError):
        return False


class RootlineIFTTTTransport:
    def __init__(self, *, token_store, environ=None, http_open=None,
                 readback=None, auxiliary_on_authorizer=None,
                 commissioning_connect_factory=None, auxiliary_active_reader=None):
        self.environ = environ if environ is not None else os.environ
        self.token_store = token_store
        self.http_open = http_open or urllib_request.urlopen
        self.readback = readback
        self.auxiliary_on_authorizer = auxiliary_on_authorizer
        self.commissioning_connect_factory = commissioning_connect_factory
        self.auxiliary_active_reader = auxiliary_active_reader

    def read_safety_configuration(self, *, device_id, channel):
        contract = self._binding(device_id, channel)
        snapshot = self._snapshot(device_id, channel)
        row = self._channel(snapshot, channel)
        supervised_channels = snapshot.get("commissioned_supervised_channels") or []
        channel_commissioning = (contract["identity"] in {
            "FERTILIZER-MIXER-CH2", "FERTILIZER-INJECTION-CH1"}
            and channel in supervised_channels)
        commissioning_generation = (snapshot.get("commissioned_baseline_id")
            if channel_commissioning else None)
        if contract["identity"] == "FERTILIZER-INJECTION-CH1":
            # CH2's historical proof never commissions CH1. Resolve the exact
            # injector's current canonical evidence on every safety read, also
            # at the coordinator's final command edge (no cached authority).
            canonical = self._injector_commissioning(snapshot)
            channel_commissioning = canonical is not None
            commissioning_generation = canonical["generation"] if canonical else None
        if contract["collection"] == "irrigation_zones":
            channel_commissioning = bool(snapshot.get("commissioned_baseline_id"))
            commissioning_generation = (snapshot.get("commissioned_baseline_id")
                if channel_commissioning else None)
        if contract["identity"] == "A12345":
            canonical = self._a_irrigation_commissioning(snapshot)
            channel_commissioning = canonical is not None
            commissioning_generation = (canonical["canonical_registry_sha256"]
                if canonical else None)
        authoritative = snapshot.get("actuation_configuration_safe") is True
        if contract["identity"] == "A12345":
            authoritative = authoritative and channel_commissioning
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
            "physical_commissioning_generation": commissioning_generation,
            "commissioned": channel_commissioning,
            "response_digest": snapshot.get("response_digest"),
            "observed_at": snapshot.get("retrieved_at"),
            "relevant_outputs_off": all(
                item.get("output_state") == "OFF" for item in snapshot["channels"]
                if contract["collection"] == "irrigation_zones"
                or item.get("channel") == channel
                or item.get("channel") not in device_channel_assignments(device_id)),
        }

    def _a_irrigation_commissioning(self, snapshot):
        from modules.telemetry.rootline_ewelink_commissioned_baseline import load_canonical_a_irrigation_binding
        from modules.telemetry.rootline_device_registry import get_device_contract
        connect = self.commissioning_connect_factory
        if connect is None:
            from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
            database_url = str(self.environ.get("DATABASE_URL") or "").strip()
            if not database_url:
                return None
            connect = lambda: connect_bounded_rootline_postgres(database_url=database_url, read_only=True)
        try:
            binding = load_canonical_a_irrigation_binding(connect_factory=connect)
            contract = get_device_contract("A12345")
            row = self._channel(snapshot, 4)
            if (not binding or binding["canonical_registry_sha256"] != contract.get("canonical_registry_sha256")
                    or snapshot.get("device_id") != "100204e9bc"
                    or snapshot.get("firmware") != binding["commissioning_evidence"]["firmware"]
                    or snapshot.get("commissioned_baseline_fresh") is not True
                    or row.get("native_auto_off_enabled") is not True
                    or row.get("native_auto_off_seconds") != 3599
                    or row.get("power_restoration_state") != "OFF"):
                return None
            return binding
        except Exception:
            return None

    def _injector_commissioning(self, snapshot):
        from modules.telemetry.rootline_ewelink_commissioned_baseline import (
            canonical_injector_commissioning,
        )
        connect = self.commissioning_connect_factory
        if connect is None:
            database_url = str(self.environ.get("DATABASE_URL")
                or getattr(self.token_store, "database_url", "") or "").strip()
            if not database_url:
                return None
            from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
            def connect():
                return connect_bounded_rootline_postgres(
                    database_url=database_url, read_only=True)
        try:
            return canonical_injector_commissioning(snapshot, connect_factory=connect)
        except Exception:
            # Missing/invalidated proof or a failed canonical read cannot grant
            # ON. Existing OFF supervision never needs this commissioning gate.
            return None

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
                and type(target.get("native_auto_off_seconds")) is int
                and 1 <= target["native_auto_off_seconds"] <= 14400)
        if (snapshot.get("actuation_safety_complete") is not True
                or snapshot.get("current_outputs_authoritative") is not True
                or snapshot.get("timers_enabled") is not False
                or snapshot.get("scenes_enabled") is not False
                or snapshot.get("interlock_enabled") is not False
                or set(rows) != {1, 2, 3, 4}
                or target.get("output_state") != "OFF"
                or any(row.get("output_state") not in {"ON", "OFF"} for row in rows.values())
                or any(rows[channel].get("output_state") != "OFF"
                       for channel in set(rows) - set(assignments))
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
            # A commissioned sibling can operate independently. Its exact
            # state and native shutdown remain proven; unassigned outputs must
            # remain OFF. Atomic per-device claims prevent duplicate ownership.
            if (assigned_row.get("native_auto_off_enabled") is not True
                    or int(assigned_row.get("native_auto_off_seconds") or 0)
                        != int(assigned["native_fail_stop_seconds"])):
                return False
            if assigned_row.get("output_state") == "ON":
                try:
                    reader = self.auxiliary_active_reader
                    if reader is None:
                        from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
                        reader = lambda identity: rootline_irrigation_execution_store("load_active_auxiliary", identity)
                    active = reader(assigned["identity"])
                    if not active_auxiliary_output_owned(active, assigned, snapshot.get("retrieved_at")):
                        return False
                except Exception:
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
        output = output_evidence_from_snapshot(snapshot, device_id=device_id, channel=channel)
        from modules.telemetry.rootline_ewelink_request_budget import current_duty, RequestBudget
        duty = current_duty()
        from modules.telemetry.rootline_irrigation_execution_store import is_a_commissioning_duty
        if (duty.get("execution_id") and not is_a_commissioning_duty(duty)
                and output.get("authoritative") is True and output.get("state") == "OFF"):
            try:
                RequestBudget(self._request_environment()).release_after_off(
                    duty["execution_id"], device_id=device_id, channel=channel,
                    evidence={**output, "response_digest": output.get("evidence_id")})
            except Exception:
                # Cleanup failure never suppresses genuine shutdown evidence;
                # its unused reserve remains conservatively charged on restart.
                pass
        return output

    def _request_environment(self):
        source = dict(self.environ)
        if not source.get("DATABASE_URL"):
            source["DATABASE_URL"] = getattr(self.token_store, "database_url", "")
        return source

    def prepare_execution_capacity(self, execution):
        from modules.telemetry.rootline_ewelink_request_budget import RequestBudget
        device_id = execution.get("device_id") or "1002851416"
        channel = execution.get("channel") or 1
        contract = self._binding(device_id, channel)
        record = self.token_store.latest()
        return RequestBudget(self._request_environment()).reserve_for_on(
            execution_id=execution["execution_id"], device_id=device_id, channel=channel,
            device_type=contract["device_type"], region=(record or {}).get("region"))

    def set_state(self, *, device_id, channel, state, idempotency_key):
        contract = self._binding(device_id, channel)
        state = str(state or "").upper()
        if (contract["collection"] == "irrigation_zones"
                and contract.get("commissioned") is not True):
            from modules.telemetry.rootline_ewelink_request_budget import current_duty
            duty = current_duty()
            safe_a_off = (state == "OFF" and contract["identity"] == "A12345"
                and duty.get("zone_id") == "A12345" and duty.get("device_id") == device_id
                and duty.get("channel") == channel
                and str(duty.get("commissioning_id") or "").startswith("ROOTLINE-COMMISSION-")
                and str(idempotency_key).startswith(str(duty.get("execution_id") or "") + ":OFF:"))
            if not safe_a_off:
                return {"accepted_unambiguous": False, "status": "irrigation_output_not_commissioned"}
        if (state == "ON" and contract["collection"] == "irrigation_auxiliary_devices"
                and str(self.environ.get(contract["authority_flag"]) or "").lower() != "true"
                and not (callable(self.auxiliary_on_authorizer)
                         and self.auxiliary_on_authorizer(device_id=device_id,
                             channel=channel, idempotency_key=str(idempotency_key)))):
            return {"accepted_unambiguous": False, "status": "auxiliary_authority_disabled"}
        return self._send_bound_state(contract=contract, device_id=device_id,
            channel=channel, state=state, idempotency_key=idempotency_key)

    def _send_bound_state(self, *, contract, device_id, channel, state,
                          idempotency_key, before_send=None, known_no_send=None,
                          network_attempt=None):
        event = contract.get("on_event" if state == "ON" else "off_event" if state == "OFF" else "")
        secret = str(self.environ.get("ROOTLINE_IFTTT_MAKER_KEY") or "").strip()
        if not event or not secret or not str(idempotency_key or "").strip():
            if known_no_send is not None: known_no_send("transport_not_configured")
            return {"accepted_unambiguous": False, "status": "transport_not_configured"}
        url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(
            event, urllib_parse.quote(secret, safe=""))
        body = json.dumps({"value1": str(idempotency_key), "value2": device_id,
                           "value3": str(channel)}).encode()
        req = urllib_request.Request(url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        if state == "ON":
            from modules.telemetry.rootline_ewelink_request_budget import current_duty, RequestBudget
            duty = current_duty()
            try:
                if (idempotency_key != str(duty.get("execution_id") or "") + ":ON"
                        or not duty.get("claimed_at") or not duty.get("primary_stop_deadline")):
                    raise ValueError("execution_binding_missing")
                edge_deadline = RequestBudget(self._request_environment()).begin_on(
                    execution_id=duty["execution_id"], permit=duty.get("provider_capacity_permit"),
                    device_id=device_id, channel=channel, claimed_at=duty["claimed_at"],
                    primary_stop_deadline=duty["primary_stop_deadline"])
            except Exception:
                if known_no_send is not None: known_no_send("provider_capacity_not_available")
                return {"accepted_unambiguous": False,
                    "status": "provider_capacity_not_available", "provider_command_attempted": False}
        if before_send is not None:
            try:
                final_deadline = before_send()
                if state == "ON":
                    edge_deadline = min(edge_deadline, final_deadline)
            except Exception:
                if known_no_send is not None: known_no_send("a_commissioning_sender_refused")
                return {"accepted_unambiguous": False, "status": "a_commissioning_sender_refused",
                    "provider_command_attempted": False}
        # No database work, provider probe or pacing remains beyond this check.
        # A slow accounting acknowledgement cannot create a late ON command.
        if state == "ON" and time.monotonic() >= edge_deadline:
            if known_no_send is not None: known_no_send("provider_command_deadline_reached")
            return {"accepted_unambiguous": False, "status": "provider_command_deadline_reached",
                "provider_command_attempted": False}
        # Set the private A marker before entering the provider call. Any
        # exception or missing acknowledgement after this point is outstanding.
        if network_attempt is not None: network_attempt()
        try:
            with self.http_open(req, timeout=15) as response:
                code = int(getattr(response, "status", response.getcode()))
                response.read(4096)
        except Exception:
            return {"accepted_unambiguous": False, "status": "provider_outcome_ambiguous"}
        return {"accepted_unambiguous": 200 <= code < 300,
                "status": "accepted" if 200 <= code < 300 else "rejected",
                "event": event, "provider_status": code}

    def read_a_commissioning_configuration(self):
        """Observe exact CH4 configuration without asserting commissioning."""
        snapshot = self._snapshot(DEVICE_ID, 4)
        record = self.token_store.latest() or {}
        account = record.get("provider_account_digest")
        if not _a_digest(account):
            raise ValueError("a_commissioning_account_binding_missing")
        material = _a_configuration_material(snapshot)
        return {"contract_version": "rootline_a_configuration_observation.v1",
            "zone_id": "A12345", "device_id": DEVICE_ID, "channel": 4,
            "provider_account_binding": "ewelink_owner_account",
            "provider_account_digest": account, "commissioned": False,
            "ordinary_eligibility": False,
            "ifttt_automation_configuration": "Unknown",
            "configuration": material, "configuration_sha256": _a_json_digest(material),
            "snapshot": deepcopy(snapshot), "response_digest": snapshot.get("response_digest"),
            "observed_at": snapshot.get("retrieved_at")}

    def set_a_commissioning_state(self, *, operation_claim, state, idempotency_key):
        from modules.telemetry.rootline_irrigation_execution_store import (
            _A_COMMISSIONING_SENDER, _ACommissioningSender, authorize_a_commissioning_sender)
        from modules.telemetry.rootline_ewelink_request_budget import execution_duty
        context = _A_COMMISSIONING_SENDER.get()
        # Refuse before even reading a provider or consuming capacity when the
        # caller has no store-owned, live sender transaction.
        if (not isinstance(context, _ACommissioningSender) or context.used
                or context.claim != operation_claim or context.state != state
                or context.key != idempotency_key or state not in {"ON", "OFF"}):
            return {"accepted_unambiguous": False, "status": "a_commissioning_locked_sender_required",
                "provider_command_attempted": False}
        contract = self._binding(DEVICE_ID, 4)
        if (contract.get("identity") != "A12345" or contract.get("channel") != 4
                or contract.get("on_event") != "irrigation_1_ch4_on"
                or contract.get("off_event") != "irrigation_1_ch4_off"):
            context.note_known_no_send("a_commissioning_binding_changed")
            return {"accepted_unambiguous": False, "status": "a_commissioning_binding_changed",
                "provider_command_attempted": False}
        # Explicit scope is necessary: the generic execution wrapper does not
        # bind new transport methods. OFF deliberately has no provider read.
        with execution_duty(operation_claim):
            try:
                configuration = self.read_a_commissioning_configuration() if state == "ON" else None
            except Exception:
                context.note_known_no_send("a_commissioning_configuration_read_failed")
                return {"accepted_unambiguous": False,
                    "status": "a_commissioning_configuration_read_failed", "provider_command_attempted": False}
            return self._send_bound_state(contract=contract, device_id=DEVICE_ID,
                channel=4, state=state, idempotency_key=idempotency_key,
                before_send=lambda: authorize_a_commissioning_sender(
                    operation_claim, state, idempotency_key, configuration),
                known_no_send=context.note_known_no_send,
                network_attempt=context.note_network_attempt)

    def read_a_commissioning_output(self, *, operation_claim):
        """One canonical A observation; current OFF never discharges its duty."""
        from modules.telemetry.rootline_irrigation_execution_store import (
            _A_COMMISSIONING_OBSERVER, _ACommissioningObserver)
        context = _A_COMMISSIONING_OBSERVER.get()
        if (not isinstance(context, _ACommissioningObserver)
                or context.claim != operation_claim or context.read_performed):
            raise ValueError("a_commissioning_locked_observer_required")
        context.read_performed = True
        snapshot = self._snapshot(DEVICE_ID, 4)
        return output_evidence_from_snapshot(snapshot, device_id=DEVICE_ID, channel=4)

    def release_a_commissioning_capacity(self, *, operation_claim, evidence):
        """Discharge only the store-validated safe branch, with ledger readback."""
        from modules.telemetry.rootline_irrigation_execution_store import (
            _A_COMMISSIONING_OBSERVER, _ACommissioningObserver)
        from modules.telemetry.rootline_ewelink_request_budget import RequestBudget
        context = _A_COMMISSIONING_OBSERVER.get()
        if (not isinstance(context, _ACommissioningObserver) or not context.safe_to_release
                or context.claim != operation_claim or context.final_evidence != evidence):
            raise ValueError("a_commissioning_safe_retirement_required")
        budget = RequestBudget(self._request_environment())
        budget.release_after_off(operation_claim["execution_id"], device_id=DEVICE_ID, channel=4,
            evidence={**evidence, "response_digest": evidence.get("evidence_id")})
        with budget._locked() as connection:
            if operation_claim["execution_id"] in budget._load(connection)["reserves"]:
                raise ValueError("a_commissioning_reserve_release_unproven")
        return True

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


def active_auxiliary_output_owned(active, contract, observed_at):
    """Prove one already-ON sibling belongs to its current bounded execution."""
    if not isinstance(active, dict) or not isinstance(contract, dict):
        return False
    try:
        def parse(value):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("auxiliary_time_provenance_missing")
            return parsed.astimezone(timezone.utc)
        observed = parse(observed_at)
        claimed = parse(active.get("claimed_at"))
        deadline = parse(active.get("primary_stop_deadline"))
        start = active.get("start_evidence") or {}
        started = parse(start.get("retrieved_at") or start.get("observed_at"))
        return (active.get("state") == "Active" and active.get("on_attempts") == 1
            and bool(active.get("execution_id"))
            and active.get("auxiliary_device_id") == contract.get("identity")
            and active.get("device_id") == contract.get("device_id")
            and active.get("channel") == contract.get("channel")
            and type(active.get("maximum_duration_seconds")) is int
            and 0 < active["maximum_duration_seconds"] <= contract["native_fail_stop_seconds"]
            and claimed <= started <= observed < deadline
            and deadline <= claimed + timedelta(seconds=active["maximum_duration_seconds"])
            and start.get("authoritative") is True and start.get("state") == "ON"
            and bool(start.get("evidence_id") or start.get("response_digest")))
    except (ValueError, TypeError, KeyError, OverflowError):
        return False



def _a_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _a_json_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _a_configuration_material(snapshot):
    keys = ("device_id", "firmware", "device_model", "device_uiid", "configuration_generation",
        "commissioned_baseline_id", "commissioned_baseline_sha256", "timers_enabled",
        "scenes_enabled", "interlock_enabled", "interlock_evidence_source",
        "scenes_evidence_source", "control_path_evidence_source")
    rows = snapshot.get("channels") or []
    return {**{key: snapshot.get(key) for key in keys}, "channels": sorted([
        {key: row.get(key) for key in ("channel", "native_auto_off_enabled",
            "native_auto_off_seconds", "power_restoration_state")}
        for row in rows if isinstance(row, dict)], key=lambda row: row.get("channel") or 0)}


def validate_a_commissioning_configuration(value, *, grant, now, after=None):
    """Require actual normalized provider fields plus separately bound IFTTT evidence."""
    from modules.telemetry.rootline_ewelink_commissioned_baseline import commissioned_controller_baseline
    def need(ok):
        if not ok:
            raise ValueError("a_commissioning_configuration_unproven")
    need(isinstance(value, dict) and isinstance(grant, dict))
    snapshot = value.get("snapshot")
    need(isinstance(snapshot, dict))
    material = _a_configuration_material(snapshot)
    baseline = commissioned_controller_baseline()
    need(value.get("contract_version") == "rootline_a_configuration_observation.v1"
        and value.get("device_id") == DEVICE_ID and value.get("zone_id") == "A12345"
        and type(value.get("channel")) is int and value["channel"] == 4
        and value.get("commissioned") is False and value.get("ordinary_eligibility") is False
        and value.get("ifttt_automation_configuration") == "Unknown"
        and value.get("provider_account_binding") == "ewelink_owner_account"
        and _a_digest(value.get("provider_account_digest"))
        and value["provider_account_digest"] == grant.get("provider_account_digest")
        and value.get("configuration") == material
        and value.get("configuration_sha256") == _a_json_digest(material)
        and value["configuration_sha256"] == grant.get("configuration_sha256"))
    need(snapshot.get("device_id") == DEVICE_ID and snapshot.get("device_uiid") == 9
        and snapshot.get("firmware") == grant.get("firmware") == baseline["firmware"]
        and snapshot.get("configuration_generation") == grant.get("configuration_generation")
            == baseline["configuration_generation"]
        and baseline.get("revoked") is False and snapshot.get("commissioned_baseline_fresh") is True
        and snapshot.get("commissioned_baseline_id") == baseline["baseline_id"]
        and snapshot.get("commissioned_baseline_sha256") == grant.get("configuration_baseline_sha256")
            == baseline["baseline_sha256"]
        and snapshot.get("current_outputs_authoritative") is True
        and snapshot.get("actuation_safety_complete") is True
        and snapshot.get("actuation_configuration_safe") is True
        and snapshot.get("observation_fresh") is True and snapshot.get("online") is True
        and snapshot.get("provider_control_calls") == 0
        and type(snapshot.get("provider_control_calls")) is int
        and snapshot.get("timers_enabled") is False and snapshot.get("scenes_enabled") is False
        and snapshot.get("interlock_enabled") is False
        and snapshot.get("scene_evidence_conflict") is False
        and snapshot.get("safety_readback_missing") == []
        and snapshot.get("control_path_evidence_source") in {
            "provider_readback", "commissioned_configuration_baseline", "mixed_provider_and_commissioned_baseline"})
    rows = snapshot.get("channels")
    need(isinstance(rows, list) and len(rows) == 4
        and all(isinstance(row, dict) and type(row.get("channel")) is int for row in rows)
        and {row["channel"] for row in rows} == {1, 2, 3, 4}
        and all(row.get("output_state") == "OFF" and row.get("native_auto_off_enabled") is True
            and type(row.get("native_auto_off_seconds")) is int
            and 0 < row["native_auto_off_seconds"] <= 3600
            and row.get("power_restoration_state") == "OFF" for row in rows)
        and next(row for row in rows if row["channel"] == 4)["native_auto_off_seconds"] == 3599)
    # IFTTT automation configuration is not part of the relay GET contract.
    # Never synthesize its absence from current OFF. The root-bound canonical
    # grant must preserve the actual accepted, same-generation configuration evidence.
    paths = grant.get("ifttt_control_path_evidence")
    need(isinstance(paths, dict) and paths.get("channels") == [1, 2, 3, 4]
        and paths.get("device_id") == DEVICE_ID
        and paths.get("configuration_generation") == baseline["configuration_generation"]
        and paths.get("conflicting_automations") == []
        and isinstance(paths.get("reference"), str) and bool(paths["reference"].strip())
        and _a_digest(paths.get("artifact_sha256"))
        and paths.get("source") in {"owner_authenticated_configuration", "canonical_configuration_evidence"})
    observed = datetime.fromisoformat(str(snapshot.get("retrieved_at")).replace("Z", "+00:00"))
    need(isinstance(now, datetime) and now.tzinfo is not None and observed.tzinfo is not None
        and timedelta(0) <= now - observed <= timedelta(seconds=30)
        and (after is None or observed >= after)
        and value.get("observed_at") == snapshot.get("retrieved_at")
        and _a_digest(snapshot.get("response_digest"))
        and value.get("response_digest") == snapshot["response_digest"])
    return True


def a_commissioning_final_off_verified(value, *, now, after):
    """Fresh exact CH4 OFF plus all sibling OFF, independent of expired grants."""
    return _a_commissioning_output_verified(value, target_state="OFF", now=now, after=after)


def a_commissioning_start_verified(value, *, now, after):
    """Fresh own CH4 ON with all three siblings OFF; HTTP acceptance is absent."""
    return _a_commissioning_output_verified(value, target_state="ON", now=now, after=after)


def _a_commissioning_output_verified(value, *, target_state, now, after):
    try:
        if (not isinstance(value, dict) or value.get("authoritative") is not True
                or value.get("device_id") != DEVICE_ID or type(value.get("channel")) is not int
                or value["channel"] != 4 or value.get("state") != target_state):
            return False
        proof = value.get("irrigation_output_evidence")
        if (not isinstance(proof, dict) or proof.get("device_id") != DEVICE_ID
                or proof.get("current_outputs_authoritative") is not True
                or not _a_digest(proof.get("response_digest"))
                or proof["response_digest"] != value.get("evidence_id")
                or proof.get("retrieved_at") != value.get("retrieved_at")
                or type(proof.get("provider_control_calls")) is not int
                or proof["provider_control_calls"] != 0):
            return False
        observed = datetime.fromisoformat(str(proof.get("retrieved_at")).replace("Z", "+00:00"))
        rows = proof.get("channels")
        return (observed.tzinfo is not None and after <= observed <= now
            and now - observed <= timedelta(seconds=30)
            and isinstance(rows, list) and len(rows) == 4
            and all(isinstance(row, dict) and type(row.get("channel")) is int
                and row.get("output_state") == (target_state if row["channel"] == 4 else "OFF") for row in rows)
            and {row["channel"] for row in rows} == {1, 2, 3, 4})
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
