"""SONOFF observation protocol; no control commands or business authority.

AES-CBC wire compatibility is derived from MIT-licensed SonoffLAN v3.13.3;
see THIRD_PARTY_NOTICES.md. CBC is not authenticated encryption.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
import json
import os
import re
import time
import uuid

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEVICES = {"100204e9bc": ("4CHPROR3", 4, 4), "100204d497": ("4CHPROR3", 4, 4),
           "1002851416": ("MINIR4", 138, 1)}
VERSION = "rootline_sonoff_observation.v1"
MAX_AGE = 60
MAX_BYTES = 16384
DIAGNOSTIC_CODES = frozenset({
    "explicit_report_processed", "query_unproven", "report_processing_failed",
    "query_timeout", "query_network_unreachable", "query_connection_failed",
    "query_invalid_json", "query_storage_failure",
    "endpoint_metadata_resolved", "discovery_unproven", "discovery_unavailable",
    "discovery_partial_or_conflicting", "discovery_identity_unproven",
    "discovery_endpoint_invalid", "discovery_device_conflict",
    "discovery_partial_or_expired", "discovery_changed_or_expired", "discovery_config_conflict",
    "txt_invalid", "txt_duplicate_or_invalid", "txt_data_missing", "txt_identity_mismatch",
    "encrypted_payload_required", "encrypted_payload_invalid", "decoded_payload_invalid",
    "sequence_invalid", "receipt_clock_invalid", "switch_fields_invalid",
    "switch_fields_conflicting", "explicit_switch_fields_missing", "sequence_generation_blocked",
    "sequence_replayed_or_reset", "observation_invalidated", "replay_store_unavailable",
    "query_http_unproven", "query_response_too_large", "query_response_unproven",
    "query_identity_mismatch", "query_correlation_missing_or_mismatch", "query_revision_invalid",
    "query_ack_without_encrypted_state", "query_data_missing", "query_iv_missing",
    "query_encrypted_fields_invalid", "discovery_missing_srv_and_txt",
    "discovery_missing_srv", "discovery_missing_txt", "discovery_missing_address",
    "discovery_conflicting_srv", "discovery_conflicting_txt", "discovery_conflicting_address",
    "discovery_ptr_missing", "discovery_ptr_conflicting",
})


class InvalidObservation(ValueError):
    """Reason codes only: never raw payloads, addresses or key material."""


def need(ok, reason):
    if not ok:
        raise InvalidObservation(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def config_validate(config):
    need(isinstance(config, dict) and set(config) == {"allowed_user_ids", "devices"}, "configuration_invalid")
    users = config["allowed_user_ids"]
    need(isinstance(users, list) and bool(users) and all(isinstance(u, str) and re.fullmatch(r"[0-9a-f]{32}", u) for u in users), "user_binding_invalid")
    devices = config["devices"]
    need(isinstance(devices, dict) and bool(devices) and set(devices) <= set(DEVICES), "device_allowlist_invalid")
    for identity, item in devices.items():
        model, uiid, _ = DEVICES[identity]
        need(isinstance(item, dict) and set(item) <= {"model", "uiid", "device_key", "generation", "endpoint", "qualification_id"}, "device_configuration_invalid")
        need(item.get("model") == model and type(item.get("uiid")) is int and item["uiid"] == uiid, "model_binding_invalid")
        need(isinstance(item.get("device_key"), str) and 16 <= len(item["device_key"]) <= 128, "device_key_missing")
        need(isinstance(item.get("generation"), str) and re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", item["generation"]), "generation_missing")
        qualification = item.get("qualification_id", "")
        need(isinstance(qualification, str) and (not qualification or re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", qualification)), "qualification_invalid")
        endpoint = item.get("endpoint")
        if endpoint is not None:
            need(isinstance(endpoint, dict) and set(endpoint) == {"address", "port", "binding_id"}, "endpoint_binding_invalid")
            try:
                address = ipaddress.IPv4Address(endpoint["address"])
            except (ValueError, TypeError):
                raise InvalidObservation("endpoint_address_invalid") from None
            need(any(address in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")), "endpoint_address_invalid")
            need(type(endpoint["port"]) is int and 1 <= endpoint["port"] <= 65535, "endpoint_port_invalid")
            need(isinstance(endpoint["binding_id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", endpoint["binding_id"]), "endpoint_binding_invalid")
    return config


def crypt(data, key, iv, *, encrypt):
    cipher = Cipher(algorithms.AES(hashlib.md5(key.encode(), usedforsecurity=False).digest()), modes.CBC(iv))
    if encrypt:
        padder = padding.PKCS7(128).padder()
        data = padder.update(data) + padder.finalize()
        worker = cipher.encryptor()
        return worker.update(data) + worker.finalize()
    worker = cipher.decryptor()
    padded = worker.update(data) + worker.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def decode(envelope, key, *, require_flag=True):
    try:
        need((not require_flag and "encrypt" not in envelope) or (envelope.get("encrypt") is True or envelope.get("encrypt") == "true"), "encrypted_payload_required")
        ciphertext = base64.b64decode(envelope["data"], validate=True)
        iv = base64.b64decode(envelope["iv"], validate=True)
        need(0 < len(ciphertext) <= MAX_BYTES and len(iv) == 16, "encrypted_payload_invalid")
        result = json.loads(crypt(ciphertext, key, iv, encrypt=False))
        need(isinstance(result, dict), "decoded_payload_invalid")
        return result
    except InvalidObservation:
        raise
    except Exception:
        raise InvalidObservation("encrypted_payload_invalid") from None


def query_payload(device_id, key, request_id):
    need(device_id in DEVICES and isinstance(request_id, str) and request_id.isdecimal(), "query_binding_invalid")
    iv = os.urandom(16)
    # The only outbound plaintext is an empty object. There is no command/params input.
    return {"deviceid": device_id, "sequence": request_id, "selfApikey": "123", "encrypt": True,
        "iv": base64.b64encode(iv).decode(), "data": base64.b64encode(crypt(b"{}", key, iv, encrypt=True)).decode()}


def parse_txt(wire):
    need(isinstance(wire, bytes) and 0 < len(wire) <= MAX_BYTES, "txt_invalid")
    fields, position = {}, 0
    try:
        while position < len(wire):
            size = wire[position]
            position += 1
            need(size > 0 and position + size <= len(wire), "txt_invalid")
            pair = wire[position:position + size]
            position += size
            key, sep, value = pair.partition(b"=")
            key = key.decode("ascii")
            need(bool(sep) and key not in fields, "txt_duplicate_or_invalid")
            fields[key] = value.decode("utf-8")
        chunks = sorted(int(k[4:]) for k in fields if re.fullmatch(r"data[0-9]+", k))
        need(bool(chunks) and chunks == list(range(1, max(chunks) + 1)) and len(chunks) <= 4, "txt_data_missing")
        fields["data"] = "".join(fields[f"data{i}"] for i in chunks)
        return fields
    except InvalidObservation:
        raise
    except (UnicodeError, ValueError, KeyError):
        raise InvalidObservation("txt_invalid") from None


def explicit_outputs(device_id, params):
    count = DEVICES[device_id][2]
    result = {}
    if "switches" in params:
        rows = params["switches"]
        need(isinstance(rows, list) and 0 < len(rows) <= count, "switch_fields_invalid")
        for row in rows:
            need(isinstance(row, dict) and type(row.get("outlet")) is int
                and 0 <= row["outlet"] < count and row["outlet"] + 1 not in result
                and row.get("switch") in {"on", "off"}, "switch_fields_invalid")
            result[row["outlet"] + 1] = row["switch"].upper()
    if "switch" in params:
        need(count == 1 and params["switch"] in {"on", "off"}, "switch_fields_invalid")
        need(not result or result.get(1) == params["switch"].upper(), "switch_fields_conflicting")
        result[1] = params["switch"].upper()
    need(bool(result), "explicit_switch_fields_missing")
    return result


class ObserverState:
    """In-memory observations, durable sequence high-water only, no restored state."""
    def __init__(self, config, persisted=None, *, monotonic=time.monotonic, utcnow=None):
        self.config = config_validate(config)
        self.monotonic = monotonic
        self.utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.boot_id = uuid.uuid4().hex
        self.channels = {identity: {} for identity in config["devices"]}
        self.reasons = {identity: "no_current_epoch_report" for identity in self.channels}
        self.diagnostics = {identity: {
            "mdns": {"count": 0, "last_result": "no_reports_received"},
            "query": {"count": 0, "last_result": "no_query_attempted"},
            "discovery": {"count": 0, "last_result": "no_discovery_attempted"},
        } for identity in self.channels}
        self.highwater = {}
        self.anchors = {}  # Fresh query anchors never survive an observer restart.
        self.revisions = {identity: 0 for identity in self.channels}
        self.healthy = True
        if persisted is not None:
            need(isinstance(persisted, dict) and persisted.get("version") == 1
                and isinstance(persisted.get("devices"), dict), "replay_store_invalid")
            for identity, item in persisted["devices"].items():
                if identity not in self.channels:
                    continue
                need(isinstance(item, dict) and set(item) in ({"generation", "sources", "blocked"},
                    {"generation", "sources", "blocked", "anchor"})
                    and type(item["blocked"]) is bool
                    and isinstance(item["sources"], dict), "replay_store_invalid")
                if item["generation"] != config["devices"][identity]["generation"]:
                    continue
                if "anchor" in item:
                    anchor = item["anchor"]
                    need(isinstance(anchor, dict) and set(anchor) == {"request_id", "device_sequence", "received_at"}
                        and isinstance(anchor["request_id"], str) and anchor["request_id"].isdecimal()
                        and type(anchor["device_sequence"]) is int and anchor["device_sequence"] >= 0
                        and isinstance(anchor["received_at"], str) and item["blocked"] is True, "replay_store_invalid")
                for source, mark in item["sources"].items():
                    need(source in {"mdns", "query"} and isinstance(mark, dict)
                        and set(mark) == {"sequence", "digest"}
                        and type(mark["sequence"]) is int and mark["sequence"] >= 0
                        and isinstance(mark["digest"], str) and re.fullmatch(r"[0-9a-f]{64}", mark["digest"]), "replay_store_invalid")
                self.highwater[identity] = deepcopy(item)

    def diagnose(self, device_id, source, reason):
        # Bounded process-local diagnostics have no evidence/freshness authority.
        item = self.diagnostics[device_id][source]
        item["count"] = min(item["count"] + 1, 1_000_000)
        item["last_result"] = reason if reason in DIAGNOSTIC_CODES else (
            "query_unproven" if source == "query" else (
                "discovery_unproven" if source == "discovery" else "report_processing_failed"))

    def metadata(self):
        return {"version": 1, "devices": deepcopy(self.highwater)}

    def invalidate(self, device_id, reason):
        self.revisions[device_id] += 1
        self.channels[device_id] = {}
        self.reasons[device_id] = reason

    def stage(self, device_id, *, source, sequence, params, report_digest, received_at, received_mono, device_sequence=None):
        need(device_id in self.channels and source in {"mdns", "query"}, "observation_binding_invalid")
        need(isinstance(sequence, str) and re.fullmatch(r"[0-9]{1,20}", sequence), "sequence_invalid")
        need(received_at.tzinfo is not None and 0 <= (self.utcnow()-received_at).total_seconds() <= MAX_AGE
            and 0 <= self.monotonic()-received_mono <= MAX_AGE, "receipt_clock_invalid")
        outputs = explicit_outputs(device_id, params)
        recovering = bool(self.highwater.get(device_id, {}).get("blocked"))
        anchor = self.anchors.get(device_id)
        anchored = bool(recovering and source == "mdns" and anchor
            and 0 <= self.monotonic()-anchor["received_mono"] <= MAX_AGE
            and 0 <= (self.utcnow()-anchor["received_at"]).total_seconds() <= MAX_AGE
            and received_mono > anchor["received_mono"] and received_at > anchor["received_at"]
            and int(sequence) >= anchor["device_sequence"])
        if recovering:
            need(anchored or (source == "query" and bool(self.config["devices"][device_id].get("qualification_id"))
                and isinstance(device_sequence, str) and re.fullmatch(r"[0-9]{1,20}", device_sequence)
                and len(outputs) == DEVICES[device_id][2]), "sequence_generation_blocked")
        sequence_number = int(sequence)
        config = self.config["devices"][device_id]
        entry = deepcopy(self.highwater.get(device_id, {"generation": config["generation"], "sources": {}, "blocked": False}))
        content_digest = digest(outputs)
        if recovering:
            # A previously qualified direct query with a fresh exact request
            # echo can recover a device reboot without owner intervention.
            entry["blocked"] = False
            if anchored:
                entry["sources"].pop("mdns", None)
            else:
                entry["sources"]["mdns"] = {"sequence": int(device_sequence), "digest": content_digest}
            entry.pop("anchor", None)
        prior = entry["sources"].get(source)
        if prior and sequence_number <= prior["sequence"]:
            if sequence_number < prior["sequence"] or content_digest != prior["digest"]:
                self.invalidate(device_id, "sequence_reset_or_conflict")
                entry["blocked"] = True
                self.highwater[device_id] = entry
            raise InvalidObservation("sequence_replayed_or_reset")
        entry["sources"][source] = {"sequence": sequence_number, "digest": content_digest}
        candidate = {}
        for channel, state in outputs.items():
            candidate[channel] = {"channel": channel, "state": state, "source": source,
                "sequence": sequence, "sequence_kind": "device_revision" if source == "mdns" else "request_echo",
                "device_sequence": sequence if source == "mdns" else device_sequence, "report_digest": report_digest,
                "received_at": received_at.isoformat(), "received_mono": received_mono}
        metadata = self.metadata()
        metadata["devices"][device_id] = entry
        return metadata, candidate, self.revisions[device_id]

    def commit(self, device_id, metadata, candidate, revision):
        # Called only AFTER HA Store.async_save succeeds under the receiver lock.
        self.highwater = deepcopy(metadata["devices"])
        if revision != self.revisions[device_id]:
            return
        self.channels[device_id].update(candidate)
        if not metadata["devices"][device_id].get("blocked"):
            self.anchors.pop(device_id, None)
        self.reasons[device_id] = "explicit_report_received"

    def snapshot(self, device_id):
        need(device_id in self.channels, "device_not_allowed")
        config = self.config["devices"][device_id]
        now, wall = self.monotonic(), self.utcnow()
        rows = []
        for channel in range(1, DEVICES[device_id][2] + 1):
            row = self.channels[device_id].get(channel)
            fresh = False
            if row is not None:
                observed = datetime.fromisoformat(row["received_at"])
                age = now-row["received_mono"]
                wall_age = (wall-observed).total_seconds()
                fresh = self.healthy and 0 <= age <= MAX_AGE and 0 <= wall_age <= MAX_AGE and abs(age-wall_age) <= 2
            rows.append({"channel": channel, "state": row["state"] if fresh else "Unknown",
                "fresh": bool(fresh), "age_seconds": age if row is not None else None,
                "received_at": row["received_at"] if row is not None else None,
                "source": row["source"] if row is not None else None,
                "sequence": row["sequence"] if row is not None else None,
                "sequence_kind": row["sequence_kind"] if row is not None else None,
                "device_sequence": row["device_sequence"] if row is not None else None,
                "report_digest": row["report_digest"] if row is not None else None})
        return {"contract_version": VERSION, "device_id": device_id, "model": DEVICES[device_id][0],
            "uiid": DEVICES[device_id][1], "generation": config["generation"], "observer_epoch": self.boot_id,
            "qualification_id": config.get("qualification_id", ""), "generated_at": wall.isoformat(),
            "maximum_age_seconds": MAX_AGE, "source_authentication": "unauthenticated_sonoff_lan_protocol",
            "control_commands": 0, "channels": rows, "status": self.reasons[device_id],
            "diagnostics": deepcopy(self.diagnostics[device_id])}
