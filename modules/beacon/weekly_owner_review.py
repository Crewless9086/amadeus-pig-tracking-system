"""Exact non-executing owner-review packet for Beacon's first weekly post."""

from copy import deepcopy
from hashlib import sha256
import json

from modules.beacon.facebook_media_transport import (
    load_supabase_asset_bytes,
    validate_facebook_image_asset,
)
from modules.beacon.media_library import list_beacon_media_assets
from modules.beacon.public_livestock_content_policy import (
    assess_public_livestock_content,
)


PACKET_ID = "BEACON-WEEK-2026-07-25-P1"
CAMPAIGN_LANE = "live_stock_awareness"
EXACT_CAPTION = (
    "These three came straight over to inspect the camera while Waki’s attention stayed "
    "with the rest of the litter behind them. That mix of confidence, curiosity "
    "and staying close to mum is one of those ordinary farm moments worth sharing.\n\n"
    "Follow the farm journey for more honest moments from behind the scenes at "
    "Amadeus Farm."
)
MEDIA_SPEC = (
    {"asset_id": "BEACON-ASSET-3D9A65053184D8181A", "order": 1, "width": 4000, "height": 3000,
     "visual": "Three curious piglets at the front, with Waki and the litter behind."},
    {"asset_id": "BEACON-ASSET-983952CB4A95A0BEBB", "order": 2, "width": 4000, "height": 3000,
     "visual": "The group gathers closer while Waki remains visible at the back."},
    {"asset_id": "BEACON-ASSET-13F7A5168AE3BFF676", "order": 3, "width": 4000, "height": 3000,
     "visual": "Three piglets face the camera, completing the inspection sequence."},
)
AUTHORITY = {
    "posts_publicly": False,
    "calls_meta": False,
    "sends_customer_messages": False,
    "spends_money": False,
    "creates_or_updates_campaigns": False,
    "imports_evidence": False,
    "writes_database": False,
    "writes_business_or_farm_data": False,
    "creates_orders": False,
    "reserves_stock": False,
    "changes_stock": False,
}


def build_post_one_owner_review(assets):
    """Bind exact reviewed copy to the exact three eligible assets or fail closed."""
    by_id = {
        str(asset.get("asset_id") or ""): asset
        for asset in assets or [] if isinstance(asset, dict)
    }
    selected, blockers = [], []
    for expected in MEDIA_SPEC:
        asset = by_id.get(expected["asset_id"])
        if not asset:
            blockers.append(f"{expected['asset_id']}:missing")
            continue
        reasons = _asset_reasons(asset)
        if reasons:
            blockers.extend(f"{expected['asset_id']}:{reason}" for reason in reasons)
            continue
        selected.append({
            "asset_id": expected["asset_id"],
            "order": expected["order"],
            "title": str(asset.get("title") or expected["asset_id"]),
            "media_type": "image",
            "mime_type": str(asset.get("mime_type") or ""),
            "width": expected["width"],
            "height": expected["height"],
            "dimensions_display": f"{expected['width']} × {expected['height']}",
            "visual": expected["visual"],
            "approval_status": str(
                asset.get("effective_approval_status")
                or asset.get("approval_status") or ""
            ),
            "public_use_approved": True,
            "trusted_server_hash_verified": True,
            "thumbnail_url": (
                f"/api/beacon/weekly-owner-review/{PACKET_ID}/media/"
                f"{expected['asset_id']}"
            ),
        })
    policy = assess_public_livestock_content(
        EXACT_CAPTION,
        objective="farm_awareness",
        campaign_lane=CAMPAIGN_LANE,
        media=selected,
    )
    if not policy["allowed"]:
        blockers.append(policy["status"])
    packet = {
        "packet_id": PACKET_ID,
        "review_status": (
            "awaiting_exact_owner_review" if not blockers else "withheld"
        ),
        "title": "The inspection committee",
        "channel": "Facebook Page",
        "campaign_lane": CAMPAIGN_LANE,
        "audience": "People who enjoy honest farm life, animals, and behind-the-scenes stories.",
        "timing": {
            "recommendation": "Owner selects the final publishing time.",
            "rationale": "No verified posting-time baseline is available; timing is not presented as optimized.",
        },
        "draft_copy": EXACT_CAPTION if not blockers else "",
        "caption_sha256": sha256(EXACT_CAPTION.encode("utf-8")).hexdigest(),
        "media": {
            "status": "approved_media_sequence_selected" if len(selected) == len(MEDIA_SPEC) and not blockers else "media_sequence_withheld",
            "asset_count": len(selected),
            "assets": selected,
            "exact_order": [item["asset_id"] for item in selected],
            "execution_must_recheck": True,
        },
        "public_livestock_policy": policy,
        "measurable_objective": {
            "metric": "verified organic reactions, comments, and shares",
            "measurement_window": "7 days after an owner-approved post",
            "target": "owner_sets_target_before_publication",
        },
        "evidence_not_available": [
            "verified posting-time performance baseline",
            "imported Meta Ads Insights evidence",
            "SAM-attributed qualified enquiries, orders, sales, or revenue",
        ],
        "blockers": blockers,
        "next_gate": "Charl reviews this exact caption and three-image order. This packet does not publish.",
        "authority": deepcopy(AUTHORITY),
    }
    canonical = json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    packet["canonical_sha256"] = sha256(canonical).hexdigest()
    return packet


def load_post_one_thumbnail(asset_id, *, database_url=None, environ=None):
    """Return one validated approved image for an authenticated no-store proxy."""
    asset_id = str(asset_id or "").strip()
    expected = next((item for item in MEDIA_SPEC if item["asset_id"] == asset_id), None)
    if expected is None:
        return {"success": False, "status": "packet_media_not_found"}, 404
    result, status = list_beacon_media_assets(limit=100, database_url=database_url)
    if status != 200:
        return {"success": False, "status": "packet_media_read_unavailable"}, status
    asset = next((item for item in result.get("assets", []) if item.get("asset_id") == asset_id), None)
    if not asset or _asset_reasons(asset):
        return {"success": False, "status": "packet_media_not_eligible"}, 409
    loaded, loaded_status = load_supabase_asset_bytes(asset, environ=environ)
    if loaded_status != 200 or not loaded.get("success"):
        return {"success": False, "status": "packet_media_bytes_unavailable"}, loaded_status
    validation = validate_facebook_image_asset(
        asset, loaded.get("data"), loaded.get("returned_mime")
    )
    if (
        not validation.get("allowed")
        or validation.get("width") != expected["width"]
        or validation.get("height") != expected["height"]
    ):
        return {"success": False, "status": "packet_media_validation_failed"}, 409
    return {
        "success": True,
        "status": "packet_media_validated",
        "data": loaded["data"],
        "mime_type": validation["returned_mime"],
        "asset_id": asset_id,
        "width": validation["width"],
        "height": validation["height"],
        "posts_publicly": False,
        "calls_meta": False,
        "writes_performed": False,
    }, 200


def _asset_reasons(asset):
    reasons = []
    approval = str(
        asset.get("effective_approval_status")
        or asset.get("approval_status") or ""
    ).lower()
    if approval not in {"approved", "approved_public_use"}:
        reasons.append("not_approved")
    public_use = asset.get("effective_public_use_approved")
    if not bool(public_use if public_use is not None else asset.get("public_use_approved")):
        reasons.append("not_public_use_approved")
    if asset.get("content_hash_provenance") != "server_computed_on_upload":
        reasons.append("trusted_server_hash_required")
    digest = str(asset.get("content_sha256") or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        reasons.append("trusted_sha256_required")
    if asset.get("media_type") != "image":
        reasons.append("image_required")
    return reasons
