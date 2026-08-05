"""Pure, prepare-only contract for one BEACON marketing proposal.

The module deliberately has no database, network, messaging, publication, or
provider adapter. Callers must supply evidence and private-media projections.
"""

from hashlib import sha256
import json
import re


CONTRACT_VERSION = "beacon_marketing_proposal_v1"
LIBRARY_ACCEPT = "library_accepted"
VERIFIED = "verified"
PROTECTED_CLAIM_TYPES = {
    "animal",
    "availability",
    "delivery",
    "medical",
    "performance",
    "price",
    "provenance",
    "welfare",
}
TRUSTED_MEDIA_PROJECTION = "server_resolved_current_media_v1"
TRUSTED_CLAIM_CLASSIFICATION = "server_claim_classification_v1"
SUPPORTED_CHANNELS = {
    "facebook_organic": 2200,
    "instagram_organic": 2200,
    "whatsapp_status": 700,
}
CLAIM_SIGNALS = {
    "animal": re.compile(r"\b(?:animal|boar|gilt|pig|piglet|sow)\b", re.I),
    "availability": re.compile(r"\b(?:available|for sale|in stock|ready (?:now|for sale))\b", re.I),
    "delivery": re.compile(r"\b(?:deliver|delivery|collection)\b", re.I),
    "medical": re.compile(r"\b(?:healthy|disease|treated|vaccinated|medicine|medical)\b", re.I),
    "performance": re.compile(r"\b(?:best|faster|growth rate|conversion|performance)\b", re.I),
    "price": re.compile(r"(?:\bprice\b|\bR\s?\d|\b\d+(?:[.,]\d+)?\s?rand\b)", re.I),
    "provenance": re.compile(r"\b(?:born|bred|bloodline|pedigree|origin|provenance)\b", re.I),
    "welfare": re.compile(r"\b(?:welfare|well cared|responsible care|humane)\b", re.I),
}
ZERO_AUTHORITY = {
    "writes_state": False,
    "sends_oom_sakkie_message": False,
    "sends_customer_message": False,
    "calls_meta": False,
    "publishes": False,
    "schedules": False,
    "advertises": False,
    "boosts": False,
    "spends_money": False,
    "changes_public_use": False,
    "changes_media_records": False,
}


def prepare_marketing_proposal(objective, media, draft):
    """Return one deterministic proposal or one precise missing-media request."""
    objective = _objective(objective)
    evidence = _evidence(objective["evidence"])
    selected, media_rejections = _select_media(media, objective)
    missing_facts = _validate_claims(draft, evidence)

    if not selected:
        packet = {
            "packet_type": "missing_media_request",
            "objective": objective["summary"],
            "business_reason": objective["business_reason"],
            "evidence": list(evidence.values()),
            "request_via": "oom_sakkie",
            "family_message": _shot_request(objective),
            "shot_list": [objective["missing_media"]],
            "media_rejections": media_rejections,
            "protected_actions_requested": [],
            "authority": dict(ZERO_AUTHORITY),
        }
        return _finish(packet)

    if missing_facts:
        status = "needs_factual_correction"
    else:
        status = "ready_for_owner_review"
    packet = {
        "packet_type": "marketing_proposal",
        "status": status,
        "objective": objective["summary"],
        "business_reason": objective["business_reason"],
        "audience": _required_text(draft, "audience"),
        "intended_channel": _required_text(draft, "channel"),
        "media_strategy": (
            "multi_image_useful" if len(selected) > 1 else "one_image_sufficient"
        ),
        "exact_media": selected,
        "proposed_media_order": [item["asset_id"] for item in selected],
        "draft_caption": _required_text(draft, "caption"),
        "call_to_action": _required_text(draft, "call_to_action"),
        "factual_evidence": list(evidence.values()),
        "missing_facts": missing_facts,
        "media_rejections": media_rejections,
        "decision_options": (
            ["correct", "decline"] if missing_facts
            else ["approve_proposal_only", "correct", "decline"]
        ),
        "proposal_decision_note": (
            "Approving the proposal approves only the draft for later handling; "
            "it grants no public-use, publication or spend authority."
        ),
        "approval_note": (
            "Keeping a photo in the private library does not approve public use "
            "or publication."
        ),
        "protected_actions_requested": [] if missing_facts else [
            {
                "action": "public_use_approval",
                "status": "separate_owner_decision_required",
                "scope": [item["asset_id"] for item in selected],
                "decision_options": ["approve_public_use", "decline_public_use"],
            },
            {
                "action": "publication_approval",
                "status": "separate_owner_decision_required",
                "scope": "exact caption, channel, media order and future attempt",
                "decision_options": [
                    "approve_publication", "decline_publication"
                ],
            },
        ],
        "paid_spend_approval": {
            "requested": False,
            "status": "not_requested",
            "amount": 0,
        },
        "authority": dict(ZERO_AUTHORITY),
    }
    return _finish(packet)


def _objective(value):
    if not isinstance(value, dict):
        raise ValueError("objective_required")
    result = {
        "objective_id": _required_text(value, "objective_id"),
        "summary": _required_text(value, "summary"),
        "business_reason": _required_text(value, "business_reason"),
        "evidence": value.get("evidence"),
        "media_mode": value.get("media_mode", "single"),
        "media_tags": sorted(set(value.get("media_tags") or [])),
        "missing_media": value.get("missing_media"),
    }
    if result["media_mode"] not in {"single", "multi_useful"}:
        raise ValueError("invalid_media_mode")
    shot = result["missing_media"]
    if not isinstance(shot, dict):
        raise ValueError("missing_media_spec_required")
    for field in ("subject", "angle", "orientation", "purpose"):
        _required_text(shot, field)
    return result


def _evidence(items):
    if not isinstance(items, list) or not items:
        raise ValueError("verified_business_evidence_required")
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid_evidence")
        evidence_id = _required_text(item, "evidence_id")
        if item.get("status") != VERIFIED:
            raise ValueError("unverified_business_evidence")
        normalized = {
            "evidence_id": evidence_id,
            "source_id": _required_text(item, "source_id"),
            "observed_at": _required_text(item, "observed_at"),
            "statement": _required_text(item, "statement"),
            "claim_types": sorted(set(item.get("claim_types") or [])),
            "supported_assertions": item.get("supported_assertions") or [],
            "status": VERIFIED,
        }
        if evidence_id in result and result[evidence_id] != normalized:
            raise ValueError("conflicting_evidence_identity")
        result[evidence_id] = normalized
    return result


def _select_media(items, objective):
    accepted = []
    rejected = []
    seen_assets = set()
    seen_hashes = set()
    for raw in items if isinstance(items, list) else []:
        item = raw if isinstance(raw, dict) else {}
        reason = _media_rejection(item, objective)
        asset_id = str(item.get("asset_id") or "")
        digest = str(item.get("content_sha256") or "").lower()
        if not reason and asset_id in seen_assets:
            reason = "duplicate_asset_identity"
        if not reason and digest in seen_hashes:
            reason = "duplicate_content"
        if reason:
            rejected.append({"asset_id": asset_id, "reason": reason})
            continue
        seen_assets.add(asset_id)
        seen_hashes.add(digest)
        accepted.append({
            "asset_id": asset_id,
        "content_sha256": digest,
        "storage_proof_id": item["storage_proof_id"],
        "review_event_id": item["review_event_id"],
        "current_review_proof_id": item["current_review_proof_id"],
        "private_preview_ref": item["private_preview_ref"],
            "review_status": LIBRARY_ACCEPT,
            "private_storage": True,
        "public_use_approved": False,
            "campaign_selected": True,
            "purpose": str(item.get("purpose") or ""),
        })
    limit = 1 if objective["media_mode"] == "single" else len(accepted)
    return accepted[:limit], rejected


def _media_rejection(item, objective):
    required = (
        "asset_id", "content_sha256", "storage_proof_id", "review_event_id",
        "current_review_proof_id", "private_preview_ref",
    )
    if any(not str(item.get(key) or "").strip() for key in required):
        return "per_image_provenance_incomplete"
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(item["content_sha256"])):
        return "invalid_content_sha256"
    if item.get("private_storage") is not True:
        return "private_storage_not_proven"
    if item.get("projection_authority") != TRUSTED_MEDIA_PROJECTION:
        return "trusted_current_media_projection_required"
    if item.get("review_status") != LIBRARY_ACCEPT:
        return "library_accept_required"
    tags = set(item.get("tags") or [])
    if objective["media_tags"] and not tags.intersection(objective["media_tags"]):
        return "not_suitable_for_objective"
    return ""


def _validate_claims(draft, evidence):
    claims = draft.get("claims") if isinstance(draft, dict) else None
    if not isinstance(claims, list):
        raise ValueError("structured_claims_required")
    caption = _required_text(draft, "caption")
    call_to_action = _required_text(draft, "call_to_action")
    channel = _required_text(draft, "channel")
    if channel not in SUPPORTED_CHANNELS:
        raise ValueError("unsupported_channel")
    if len(caption) > SUPPORTED_CHANNELS[channel]:
        raise ValueError("caption_too_long_for_channel")
    displayed = f"{caption}\n{call_to_action}"
    missing = []
    declared_types = set()
    composed = {"caption": [], "call_to_action": []}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("invalid_claim")
        text = _required_text(claim, "text")
        claim_types = set(claim.get("claim_types") or [])
        if not claim_types:
            raise ValueError("claim_types_required")
        if claim.get("classification_authority") != TRUSTED_CLAIM_CLASSIFICATION:
            raise ValueError("trusted_claim_classification_required")
        _required_text(claim, "classification_proof_id")
        placement = _required_text(claim, "placement")
        if placement not in composed:
            raise ValueError("invalid_claim_placement")
        composed[placement].append(text)
        declared_types.update(claim_types)
        references = claim.get("evidence_ids") or []
        for claim_type in sorted(claim_types & PROTECTED_CLAIM_TYPES):
            supported = any(
                assertion.get("text") == text
                and assertion.get("claim_type") == claim_type
                and str(assertion.get("assertion_id") or "").strip()
                for ref in references if ref in evidence
                for assertion in evidence[ref]["supported_assertions"]
                if isinstance(assertion, dict)
            )
            if not supported:
                missing.append({
                    "claim": text,
                    "claim_type": claim_type,
                    "reason": "exact_verified_assertion_required",
                })
    if " ".join(composed["caption"]) != caption:
        raise ValueError("caption_not_composed_from_validated_claims")
    if " ".join(composed["call_to_action"]) != call_to_action:
        raise ValueError("call_to_action_not_composed_from_validated_claims")
    for claim_type, pattern in CLAIM_SIGNALS.items():
        if pattern.search(displayed) and claim_type not in declared_types:
            missing.append({
                "claim": "Caption or call to action contains an undeclared protected claim.",
                "claim_type": claim_type,
                "reason": "display_copy_claim_declaration_required",
            })
    return missing


def _shot_request(objective):
    shot = objective["missing_media"]
    return (
        "Oom Sakkie, please ask the family for one photo for "
        f"{shot['purpose']}: {shot['subject']}, photographed {shot['angle']}, "
        f"in {shot['orientation']} orientation. No marketing wording is needed."
    )


def _finish(packet):
    packet.setdefault("status", "needs_missing_media")
    packet["contract_version"] = CONTRACT_VERSION
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["packet_id"] = "BEACON-PROPOSAL-" + sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:24].upper()
    return packet


def _required_text(mapping, key):
    value = str(mapping.get(key) or "").strip() if isinstance(mapping, dict) else ""
    if not value:
        raise ValueError(f"{key}_required")
    return value
