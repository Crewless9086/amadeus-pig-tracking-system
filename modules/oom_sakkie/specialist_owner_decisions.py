"""Closed, I/O-free contracts for specialist-owned protected decisions."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping


CONTRACT_VERSION = "oom_sakkie_specialist_owner_decision_v1"
SPECIALISTS = frozenset({"SAM_Livestock", "BEACON", "ROOTLINE"})
DECISION_TYPES = {
    "SAM_Livestock": frozenset({"sales_protected_decision"}),
    "BEACON": frozenset({"organic_publication_decision"}),
    "ROOTLINE": frozenset({"supervised_commissioning_decision"}),
}
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_CHOICE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")

BEACON_PROPOSAL_ID = "BEACON-PROPOSAL-18DEAAD8E896A87FE961F45B"
BEACON_ASSET_ID = "BEACON-ASSET-15EBF5E67DBFD12693"
BEACON_ASSET_SHA256 = "15ebf5e67dbfd12693bab79464c7012d221c4686207a730dac3161e097048b55"
BEACON_LIBRARY_EVENT_ID = "BEACON-LIBRARY-EVENT-010D4FE746D9F81B19127540"
BEACON_PUBLIC_USE_EVENT_ID = "BEACON-LIBRARY-EVENT-4464A3626276FBAAAEC845B5"
BEACON_CAPTION_UTF8_HEX = (
    "42656c6c6120656e2068616172203133206b6c65696e207661726b69657320e2809420736f6d6d657220"
    "e280996e206d6f6f69206f6f6d626c696b206f6d207465206465656c2e20f09f90b7"
)
BEACON_CAPTION_SHA256 = "58a60223599365b90803570909e09f3828c32768d8b27470dc1304ff27fc17d4"
REJECTED_MUTATED_PROPOSAL_ID = "BEACON-PROPOSAL-9971D111AB23533027A45463"
BEACON_CHOICES = [
    {"id": "approve", "label": "Approve exact publication", "outcome_code": "exact_publication_approved",
     "specialist_callback": "prepare_exact_publication_handover", "next_action_owner": "BEACON", "public_action": False},
    {"id": "correct", "label": "Request correction", "outcome_code": "correction_requested",
     "specialist_callback": "prepare_reviewed_correction", "next_action_owner": "BEACON", "public_action": False},
    {"id": "decline", "label": "Decline", "outcome_code": "proposal_declined",
     "specialist_callback": "close_without_public_action", "next_action_owner": "BEACON", "public_action": False},
]


ROOTLINE_COMMISSIONING_ID = "ROOTLINE-SONOFF-COMMISSIONING-20260802"
ROOTLINE_DECISION_ARTIFACT_SHA256 = "8263e5d43e786e215ac06f8413abeee16ff24f65bac0f0bfe41592183527deda"
ROOTLINE_RELEASE_SHA256 = "98d9fe68235017a7033f89ae0f8dc6aee09aea4c9a7fab2cd2dc3985dda40afc"
ROOTLINE_CHOICES = [
    {"id": "authorize", "label": "Authorize supervised commissioning", "outcome_code": "supervised_commissioning_authorized", "specialist_callback": "prepare_supervised_commissioning_handover", "next_action_owner": "ROOTLINE", "public_action": False},
    {"id": "not_now", "label": "Not now", "outcome_code": "commissioning_deferred", "specialist_callback": "retain_hardware_containment", "next_action_owner": "ROOTLINE", "public_action": False},
]

def beacon_organic_publication_binding(*, preview_reference: str, expires_at: str) -> dict[str, Any]:
    """Build the first reviewed BEACON binding from pinned authoritative bytes."""
    caption = bytes.fromhex(BEACON_CAPTION_UTF8_HEX)
    if hashlib.sha256(caption).hexdigest() != BEACON_CAPTION_SHA256:
        raise ValueError("authoritative caption bytes changed")
    raw = {
        "contract_version": CONTRACT_VERSION,
        "specialist_identity": "BEACON",
        "decision_type": "organic_publication_decision",
        "deterministic_identity": BEACON_PROPOSAL_ID,
        "decision_token": _digest(BEACON_PROPOSAL_ID)[:20],
        "evidence_binding": {
            "asset_identity": BEACON_ASSET_ID,
            "asset_sha256": BEACON_ASSET_SHA256,
            "library_accept_event_id": BEACON_LIBRARY_EVENT_ID,
            "public_use_event_id": BEACON_PUBLIC_USE_EVENT_ID,
            "caption_utf8_hex": BEACON_CAPTION_UTF8_HEX,
            "caption_sha256": BEACON_CAPTION_SHA256,
            "channel": "facebook_organic",
            "image_order": [BEACON_ASSET_ID],
            "zero_spend": True,
            "timing_start": "2026-08-01T08:00:00+02:00",
            "timing_end": "2026-08-01T09:00:00+02:00",
        },
        "chronology_binding": {
            "latest_library_event_id": BEACON_PUBLIC_USE_EVENT_ID,
            "publication_authorization_count": 0,
            "prior_campaign_use_count": 0,
        },
        "allowed_owner_choices": BEACON_CHOICES,
        "expiry_revalidation": "authoritative_specialist_chronology",
        "expires_at": _time(expires_at).isoformat(),
        "resolution_contract": "exact_once_receipt_then_edit_same_card_remove_buttons",
    }
    validated = validate_specialist_binding(raw)
    validated["_transient_preview_reference"] = _preview(preview_reference)
    return validated


def rootline_supervised_commissioning_binding(*, expires_at: str) -> dict[str, Any]:
    raw = {
        "contract_version": CONTRACT_VERSION, "specialist_identity": "ROOTLINE",
        "decision_type": "supervised_commissioning_decision",
        "deterministic_identity": ROOTLINE_COMMISSIONING_ID,
        "decision_token": _digest(ROOTLINE_COMMISSIONING_ID)[:20],
        "evidence_binding": {
            "decision_artifact_sha256": ROOTLINE_DECISION_ARTIFACT_SHA256,
            "rootline_release_sha256": ROOTLINE_RELEASE_SHA256,
            "controller": "SONOFF 4CH Pro R3", "firmware": "3.8.2",
            "channel_1": "B Camp", "channel_2": "C Camp",
            "native_auto_off_max_seconds": 3600, "power_restore_state": "OFF",
            "supervised_short_pulse_only": True, "irrigation_authority": False,
            "hardware_action_performed": False,
        },
        "chronology_binding": {
            "decision_artifact_sha256": ROOTLINE_DECISION_ARTIFACT_SHA256,
            "earlier_valve_proof_is_approval": False,
            "commissioning_authorization_count": 0,
        },
        "allowed_owner_choices": ROOTLINE_CHOICES,
        "expiry_revalidation": "authoritative_specialist_chronology",
        "expires_at": _time(expires_at).isoformat(),
        "resolution_contract": "exact_once_receipt_then_edit_same_card_remove_buttons",
    }
    return validate_specialist_binding(raw)

def validate_specialist_binding(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(raw, ensure_ascii=False)) if isinstance(raw, Mapping) else {}
    specialist = _id(value.get("specialist_identity"), "specialist identity")
    decision_type = _id(value.get("decision_type"), "decision type")
    if specialist not in SPECIALISTS or decision_type not in DECISION_TYPES[specialist]:
        raise ValueError("unsupported specialist decision type")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("specialist decision contract version invalid")
    identity = _id(value.get("deterministic_identity"), "deterministic identity")
    if identity == REJECTED_MUTATED_PROPOSAL_ID:
        raise ValueError("mutated proposal identity rejected")
    token = _id(value.get("decision_token"), "decision token")
    if token != _digest(identity)[:20]:
        raise ValueError("decision token mismatch")
    evidence = value.get("evidence_binding") if isinstance(value.get("evidence_binding"), dict) else {}
    chronology = value.get("chronology_binding") if isinstance(value.get("chronology_binding"), dict) else {}
    choices = _choices(value.get("allowed_owner_choices"))
    expires = _time(value.get("expires_at"))
    if value.get("expiry_revalidation") != "authoritative_specialist_chronology":
        raise ValueError("specialist revalidation contract invalid")
    if value.get("resolution_contract") != "exact_once_receipt_then_edit_same_card_remove_buttons":
        raise ValueError("specialist resolution contract invalid")
    if specialist == "BEACON":
        _validate_beacon(identity, evidence, chronology, choices)
    elif specialist == "ROOTLINE":
        _validate_rootline(identity, evidence, chronology, choices)
    core = {key: value[key] for key in (
        "contract_version", "specialist_identity", "decision_type", "deterministic_identity", "decision_token",
        "evidence_binding", "chronology_binding", "allowed_owner_choices", "expiry_revalidation", "expires_at",
        "resolution_contract")}
    core["expires_at"] = expires.isoformat()
    core["binding_digest"] = _digest(core)
    return core


def specialist_decision_current(binding: Mapping[str, Any], current: Mapping[str, Any], *, now=None) -> bool:
    valid = validate_specialist_binding(binding)
    if _time(now) >= _time(valid["expires_at"]):
        return False
    return hmac.compare_digest(_digest(valid["chronology_binding"]), _digest(dict(current)))


def specialist_choice(binding: Mapping[str, Any], choice_id: str) -> dict[str, Any]:
    valid = validate_specialist_binding(binding)
    choice = next((row for row in valid["allowed_owner_choices"] if row["id"] == choice_id), None)
    if choice is None:
        raise ValueError("specialist owner choice invalid")
    authority = {
        "specialist_identity": valid["specialist_identity"],
        "decision_type": valid["decision_type"],
        "deterministic_identity": valid["deterministic_identity"],
        "outcome_code": choice["outcome_code"],
        "specialist_callback": choice["specialist_callback"],
        "next_action_owner": choice["next_action_owner"],
        "publish": False,
        "meta_call": False,
        "customer_contact": False,
        "advertise": False,
        "boost": False,
        "spend": False,
    }
    if choice_id == "approve" and valid["specialist_identity"] == "BEACON":
        authority["bounded_publication_handover"] = {
            key: valid["evidence_binding"][key] for key in (
                "asset_identity", "asset_sha256", "caption_utf8_hex", "caption_sha256", "channel",
                "image_order", "zero_spend", "timing_start", "timing_end")
        }
    return authority


def render_beacon_card(binding: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    preview_reference = _preview(binding.get("_transient_preview_reference"))
    valid = validate_specialist_binding(binding)
    if valid["specialist_identity"] != "BEACON":
        raise ValueError("BEACON binding required")
    evidence = valid["evidence_binding"]
    caption = bytes.fromhex(evidence["caption_utf8_hex"]).decode("utf-8")
    text = (
        "Oom Sakkie — Protected BEACON publication decision\n\n"
        f"Authenticated private preview: {preview_reference}\n"
        "Channel: Facebook organic\n"
        f"Caption: {caption}\n"
        "Recommended timing: Saturday 2026-08-01, 08:00-09:00 SAST\n\n"
        "Approval permits only this exact single-image, exact-caption, zero-spend Facebook organic publication at that timing. "
        "It does not permit different copy/media, customer contact, advertising, boosting, spending, or campaign reuse."
    )
    buttons = [[{"text": row["label"], "callback_data":
        f"sam_live_owner_decision:{valid['decision_token']}:{row['id']}"}]
        for row in valid["allowed_owner_choices"]]
    if any(len(row[0]["callback_data"].encode()) > 64 for row in buttons):
        raise ValueError("specialist callback exceeds Telegram limit")
    return text, {"inline_keyboard": buttons}


def render_rootline_commissioning_card(binding: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    valid = validate_specialist_binding(binding)
    if valid["specialist_identity"] != "ROOTLINE":
        raise ValueError("ROOTLINE binding required")
    text = (
        "<b>ROOTLINE — SUPERVISED COMMISSIONING DECISION</b>\n\n"
        "May ROOTLINE commission the proven SONOFF irrigation controller in one supervised session? "
        "B Camp/channel 1 and C Camp/channel 2 will be configured and tested independently. "
        "Native auto-OFF will be no more than 3,600 seconds; conflicting schedules, scenes and timers "
        "must first be absent or disabled; and power restoration must remain OFF.\n\n"
        "Commissioning uses one short supervised pulse per channel—not irrigation. Charl must physically "
        "confirm the correct valve starts, the other channel stays off, and native auto-OFF stops the tested "
        "valve. Production irrigation remains supervised until both channels independently pass.\n\n"
        "Earlier valve testing is evidence only and is not commissioning approval. No configuration or "
        "hardware actuation occurs unless this exact procedure is explicitly authorized."
    )
    buttons = [[{"text": row["label"], "callback_data":
        f"sam_live_owner_decision:{valid['decision_token']}:{row['id']}"}]
        for row in valid["allowed_owner_choices"]]
    return text, {"inline_keyboard": buttons}


def _validate_rootline(identity, evidence, chronology, choices):
    expected = {
        "decision_artifact_sha256": ROOTLINE_DECISION_ARTIFACT_SHA256,
        "rootline_release_sha256": ROOTLINE_RELEASE_SHA256,
        "controller": "SONOFF 4CH Pro R3", "firmware": "3.8.2",
        "channel_1": "B Camp", "channel_2": "C Camp",
        "native_auto_off_max_seconds": 3600, "power_restore_state": "OFF",
        "supervised_short_pulse_only": True, "irrigation_authority": False,
        "hardware_action_performed": False,
    }
    expected_chronology = {
        "decision_artifact_sha256": ROOTLINE_DECISION_ARTIFACT_SHA256,
        "earlier_valve_proof_is_approval": False,
        "commissioning_authorization_count": 0,
    }
    if identity != ROOTLINE_COMMISSIONING_ID or evidence != expected or chronology != expected_chronology or choices != ROOTLINE_CHOICES:
        raise ValueError("ROOTLINE commissioning evidence binding changed")


def _validate_beacon(identity, evidence, chronology, choices):
    expected = {
        "asset_identity": BEACON_ASSET_ID, "asset_sha256": BEACON_ASSET_SHA256,
        "library_accept_event_id": BEACON_LIBRARY_EVENT_ID, "public_use_event_id": BEACON_PUBLIC_USE_EVENT_ID,
        "caption_utf8_hex": BEACON_CAPTION_UTF8_HEX, "caption_sha256": BEACON_CAPTION_SHA256,
        "channel": "facebook_organic", "image_order": [BEACON_ASSET_ID], "zero_spend": True,
        "timing_start": "2026-08-01T08:00:00+02:00", "timing_end": "2026-08-01T09:00:00+02:00",
    }
    if identity != BEACON_PROPOSAL_ID or any(evidence.get(k) != v for k, v in expected.items()):
        raise ValueError("BEACON proposal evidence binding changed")
    caption = bytes.fromhex(evidence["caption_utf8_hex"])
    if hashlib.sha256(caption).hexdigest() != evidence["caption_sha256"]:
        raise ValueError("BEACON caption bytes changed")
    if chronology != {"latest_library_event_id": BEACON_PUBLIC_USE_EVENT_ID,
                       "publication_authorization_count": 0, "prior_campaign_use_count": 0}:
        raise ValueError("BEACON chronology binding changed")
    if choices != BEACON_CHOICES:
        raise ValueError("BEACON owner choices changed")


def _choices(raw):
    if not isinstance(raw, list) or not 2 <= len(raw) <= 3:
        raise ValueError("specialist choices invalid")
    result = []
    for row in raw:
        if not isinstance(row, Mapping):
            raise ValueError("specialist choice invalid")
        item = dict(row)
        item["id"] = _choice(item.get("id"))
        for key in ("label", "outcome_code", "specialist_callback", "next_action_owner"):
            if not str(item.get(key) or "").strip():
                raise ValueError("specialist choice incomplete")
        if item.get("public_action") is not False:
            raise ValueError("owner decision cannot perform public action")
        result.append(item)
    return result


def _preview(value):
    text = str(value or "").strip()
    if not text.startswith("https://") or len(text) > 1800:
        raise ValueError("authenticated private preview reference invalid")
    return text


def _id(value, field):
    text = str(value or "").strip()
    if not _OPAQUE.fullmatch(text):
        raise ValueError(f"{field} invalid")
    return text


def _choice(value):
    text = str(value or "").strip()
    if not _CHOICE.fullmatch(text):
        raise ValueError("choice id invalid")
    return text


def _time(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware expiry required")
    return parsed.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
