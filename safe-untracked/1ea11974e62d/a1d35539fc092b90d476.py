"""Fixed commissioning diagnostics, independent of permission to execute work.

The existing runner status file retains delivery intent; the existing notifier
performs delivery. No message accepts model, exception or mission-supplied text.
The owner-authorized policy is deliberately limited to this existing pilot.
"""
from __future__ import annotations

import copy
import hashlib
import re
import uuid
from datetime import datetime, timedelta

from .execution import NativeExecutionError

PILOT = "CHARLIE-MISSION-13B47938FF65E2C1"
DESTINATIONS = {"thread": ("C0BSRQJ60KC", "1787929390.145099"),
                "approvals": ("C0BTMNW0MT2", "")}
MAX_SENDS = 2
MAX_READS = 3
MAX_REPORTS = 16


class DiagnosticNotDelivered(NativeExecutionError):
    """An explicit Slack rejection proves that this attempt did not post."""


def exact_receipt(value, identity):
    if (not isinstance(value, dict) or set(value) != set(identity) | {"ts"}
            or any(value.get(k) != v for k, v in identity.items())
            or not isinstance(value.get("ts"), str)
            or not re.fullmatch(r"\d+\.\d+", value["ts"])):
        raise NativeExecutionError("native_diagnostic_receipt_invalid")
    return value


def acknowledged_post(value, identity):
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise NativeExecutionError("native_diagnostic_acknowledgement_invalid")
    message = value.get("message")
    if (not isinstance(message, dict) or value.get("channel") != identity["channel"]
            or message.get("ts") != value.get("ts")
            or message.get("client_msg_id") != identity["client_msg_id"]
            or str(message.get("thread_ts") or "") != identity["thread_ts"]
            or hashlib.sha256(str(message.get("text") or "").encode()).hexdigest() != identity["text_sha256"]):
        raise NativeExecutionError("native_diagnostic_acknowledgement_invalid")
    return exact_receipt({**identity, "ts": value.get("ts")}, identity)


def report(service):
    """Caller holds the dedicated local reporting lock; never consumes a grant."""
    held = service._read_status()
    fingerprint = held.get("blocker_fingerprint")
    if (held.get("state") != "BLOCKED_HOLD" or held.get("mission_id") != PILOT
            or not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        return service._status(blocker_notification_state="diagnostic_scope_not_authorized")
    text = ("CHARLIE commissioning is held. Execution remains paused; owner reconciliation is required. "
            "Mission " + PILOT + ". Blocker " + fingerprint + ".")
    reports = copy.deepcopy(held.get("diagnostic_reports", {}))
    if not isinstance(reports, dict) or len(reports) > MAX_REPORTS:
        raise NativeExecutionError("native_diagnostic_state_invalid")
    if fingerprint not in reports:
        if len(reports) >= MAX_REPORTS:
            return service._status(blocker_notification_state="diagnostic_history_capacity_hold")
        reports[fingerprint] = {}
    entries = reports[fingerprint]
    if not isinstance(entries, dict) or set(entries) - set(DESTINATIONS):
        raise NativeExecutionError("native_diagnostic_state_invalid")

    def persist():
        return service._status(diagnostic_reports=reports,
            blocker_notification_state="delivered" if all(
                entries.get(k, {}).get("state") == "confirmed" for k in DESTINATIONS)
                else "bounded_diagnostic_pending")

    identities = {}
    # Validate the complete current report before either destination can send.
    for name, (channel, thread) in DESTINATIONS.items():
        key = f"{PILOT}:{fingerprint}:diagnostic:{channel}:{thread}"
        identity = {"channel": channel, "thread_ts": thread,
                    "client_msg_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "charlie-slack:" + key)),
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
        identities[name] = (key, identity)
        entry = entries.setdefault(name, {"identity": identity, "state": "new", "sends": 0, "reads": 0})
        if (not isinstance(entry, dict) or entry.get("identity") != identity
                or set(entry) - {"identity", "state", "sends", "reads", "next_attempt_at", "receipt"}
                or not isinstance(entry.get("state"), str)
                or entry["state"] not in {"new", "prepared", "rejected", "confirmed"}
                or type(entry.get("sends")) is not int or not 0 <= entry["sends"] <= MAX_SENDS
                or type(entry.get("reads")) is not int or not 0 <= entry["reads"] <= MAX_READS):
            raise NativeExecutionError("native_diagnostic_state_invalid")
        if ((entry["state"] == "new" and (entry["sends"] or entry["reads"] or "receipt" in entry))
                or (entry["state"] != "new" and (entry["sends"] == 0 or "next_attempt_at" not in entry))
                or (entry["state"] != "confirmed" and "receipt" in entry)):
            raise NativeExecutionError("native_diagnostic_state_invalid")
        if entry["state"] == "confirmed":
            exact_receipt(entry.get("receipt"), identity)
        if "next_attempt_at" in entry:
            try:
                due = datetime.fromisoformat(entry["next_attempt_at"])
                if due.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise NativeExecutionError("native_diagnostic_state_invalid") from None
    for name, (channel, thread) in DESTINATIONS.items():
        key, identity = identities[name]
        entry = entries[name]
        if entry["state"] == "confirmed":
            continue
        if "next_attempt_at" in entry and service.clock() < datetime.fromisoformat(entry["next_attempt_at"]):
            continue
        if not service.notifier:
            continue
        if entry["state"] in {"new", "rejected"} and entry["sends"] < MAX_SENDS:
            # Persist before every POST. Restart from prepared can only read back.
            entry["sends"] += 1
            entry["state"] = "prepared"
            entry["next_attempt_at"] = (service.clock() + timedelta(seconds=60)).isoformat()
            persist()
            try:
                result = service.notifier.post(channel, text, thread_ts=thread, idempotency_key=key)
                entry["receipt"] = acknowledged_post(result, identity)
                entry["state"] = "confirmed"
                persist()
                continue
            except DiagnosticNotDelivered:
                entry["state"] = "rejected"
                persist()
                continue
            except Exception:
                # An error/malformed acknowledgement may follow a successful POST.
                # Never turn an absent or unavailable read into a resend permit.
                pass
        if entry["state"] == "prepared" and entry["reads"] < MAX_READS:
            entry["reads"] += 1
            entry["next_attempt_at"] = (service.clock() + timedelta(seconds=60)).isoformat()
            persist()
            try:
                result = service.notifier.lookup(channel, thread_ts=thread,
                    client_msg_id=identity["client_msg_id"], text_sha256=identity["text_sha256"])
                entry["receipt"] = exact_receipt(result, identity)
                entry["state"] = "confirmed"
            except Exception:
                pass
            persist()
    return persist()
