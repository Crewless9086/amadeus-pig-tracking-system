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


PACKET_ID = "BEACON-WEEK-2026-07-25-P1-S1"
SUPERSEDED_PACKET_ID = "BEACON-WEEK-2026-07-25-P1"
SUPERSEDED_CANONICAL_SHA256 = (
    "85575b4822fd22bd6bc2544bbdc91f861ef12b2cfa2b5edd0475b98ba6e4408d"
)
EXPECTED_CANONICAL_SHA256 = (
    "3c3aa998ab4b5309e7846ce4c8865456e71a4fbee774d030bb7114ae63ad7e91"
)
EXPECTED_CAPTION_SHA256 = (
    "27fe1763541ba365134ae82ef6414c87fff7bd744a46af71dd9c988889e2e75b"
)
CAMPAIGN_LANE = "live_stock_awareness"
ALBUM_STORY = "Ms. Piggy and her litter – July 2026"
OWNER_CONFIRMED_SUBJECT = "Ms. Piggy and her litter"
EXACT_CAPTION = (
    "These three came straight over to inspect the camera while Ms. Piggy stayed "
    "close to the rest of the litter behind them. That mix of confidence, "
    "curiosity and staying close to mum is one of those ordinary farm moments "
    "worth sharing.\n\n"
    "Follow the farm journey for more honest moments from behind the scenes at "
    "Amadeus Farm."
)
SUPERSEDED_CAPTION = (
    "These three came straight over to inspect the camera while Waki’s attention "
    "stayed with the rest of the litter behind them. That mix of confidence, "
    "curiosity and staying close to mum is one of those ordinary farm moments "
    "worth sharing.\n\n"
    "Follow the farm journey for more honest moments from behind the scenes at "
    "Amadeus Farm."
)
MEDIA_SPEC = (
    {
        "asset_id": "BEACON-ASSET-3D9A65053184D8181A",
        "order": 1,
        "width": 4000,
        "height": 3000,
        "file_size_bytes": 4873496,
        "upload_timestamp": "2026-07-24T17:29:01.555089+00:00",
        "camera_datetime": "2026-07-21T14:18:53",
    },
    {
        "asset_id": "BEACON-ASSET-983952CB4A95A0BEBB",
        "order": 2,
        "width": 4000,
        "height": 3000,
        "file_size_bytes": 5493225,
        "upload_timestamp": "2026-07-24T17:28:53.392664+00:00",
        "camera_datetime": "2026-07-21T14:18:51",
    },
    {
        "asset_id": "BEACON-ASSET-13F7A5168AE3BFF676",
        "order": 3,
        "width": 4000,
        "height": 3000,
        "file_size_bytes": 3453322,
        "upload_timestamp": "2026-07-24T17:28:43.815487+00:00",
        "camera_datetime": "2026-07-21T14:18:49",
    },
)
AUTHORITY = {
    "publish": False,
    "Meta_call": False,
    "upload": False,
    "import": False,
    "send": False,
    "spend": False,
    "campaign_mutation": False,
    "business_data_mutation": False,
}


def build_post_one_owner_review(assets):
    """Bind exact corrected copy to the exact three eligible assets or withhold."""
    by_id = {
        str(asset.get("asset_id") or ""): asset
        for asset in assets or []
        if isinstance(asset, dict)
    }
    selected, blockers = [], []
    for expected in MEDIA_SPEC:
        asset = by_id.get(expected["asset_id"])
        if not asset:
            blockers.append(f"{expected['asset_id']}:missing")
            continue
        reasons = _asset_reasons(asset, expected)
        if reasons:
            blockers.extend(
                f"{expected['asset_id']}:{reason}" for reason in reasons
            )
            continue
        selected.append(
            {
                "order": expected["order"],
                "asset_id": expected["asset_id"],
                "owner_confirmed_subject": OWNER_CONFIRMED_SUBJECT,
                "subject_authority": "owner_correction_2026-07-25",
                "capture_date": expected["camera_datetime"],
                "capture_date_status": (
                    "approximate_exif_datetime_timezone_unknown"
                ),
                "upload_timestamp": expected["upload_timestamp"],
                "mime_type": "image/jpeg",
                "dimensions": (
                    f"{expected['width']} × {expected['height']}"
                ),
                "file_size_bytes": expected["file_size_bytes"],
                "approval_status": "approved",
                "public_use_approved": True,
                "trusted_server_hash_verified": True,
                "prior_use": {
                    "selected_in_prior_draft": True,
                    "included_in_failed_attempt": False,
                    "uploaded_unpublished": False,
                    "confirmed_published": False,
                },
                "thumbnail_url": (
                    f"/api/beacon/weekly-owner-review/{PACKET_ID}/media/"
                    f"{expected['asset_id']}"
                ),
            }
        )
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
        "supersedes": {
            "packet_id": SUPERSEDED_PACKET_ID,
            "canonical_sha256": SUPERSEDED_CANONICAL_SHA256,
            "reason": (
                "owner_corrected_subject_identity_from_waki_to_"
                "ms_piggy_and_her_litter"
            ),
            "prior_packet_preserved": True,
        },
        "caption": EXACT_CAPTION if not blockers else "",
        "caption_sha256": sha256(EXACT_CAPTION.encode("utf-8")).hexdigest(),
        "channel": "Facebook Page",
        "scheduled_time": "owner_selection_required",
        "album_story": ALBUM_STORY,
        "capture_date_display": (
            "Around 21 July 2026 · camera evidence · timezone unknown"
        ),
        "media": {
            "exact_order": [item["asset_id"] for item in selected],
            "assets": selected,
        },
        "confirmed_publication_count": 0,
        "prior_confirmed_use": "none_evidenced",
        "public_livestock_policy": policy,
        "authority": deepcopy(AUTHORITY),
        "next_gate": "exact_owner_review_of_superseding_packet_required",
    }
    canonical = _canonical_packet(packet)
    packet["canonical_sha256"] = sha256(canonical).hexdigest()
    if not blockers and packet["canonical_sha256"] != EXPECTED_CANONICAL_SHA256:
        packet["review_status"] = "withheld"
        packet["caption"] = ""
        packet["blockers"] = ["canonical_packet_hash_mismatch"]
    else:
        packet["blockers"] = blockers
    return packet


def historical_post_one_packets():
    """Return immutable review history; historical packets are never current."""
    return [
        {
            "packet_id": SUPERSEDED_PACKET_ID,
            "canonical_sha256": SUPERSEDED_CANONICAL_SHA256,
            "caption": SUPERSEDED_CAPTION,
            "status": "owner_superseded",
            "current_reviewable": False,
            "superseded_by": PACKET_ID,
            "reason": "owner_corrected_subject_identity",
            "publish": False,
            "Meta_call": False,
        }
    ]


def load_post_one_thumbnail(asset_id, *, database_url=None, environ=None):
    """Return one validated approved image for an authenticated no-store proxy."""
    asset_id = str(asset_id or "").strip()
    expected = next(
        (item for item in MEDIA_SPEC if item["asset_id"] == asset_id), None
    )
    if expected is None:
        return {"success": False, "status": "packet_media_not_found"}, 404
    result, status = list_beacon_media_assets(
        limit=100, database_url=database_url
    )
    if status != 200:
        return {
            "success": False,
            "status": "packet_media_read_unavailable",
        }, status
    asset = next(
        (
            item
            for item in result.get("assets", [])
            if item.get("asset_id") == asset_id
        ),
        None,
    )
    if not asset or _asset_reasons(asset, expected):
        return {
            "success": False,
            "status": "packet_media_not_eligible",
        }, 409
    loaded, loaded_status = load_supabase_asset_bytes(asset, environ=environ)
    if loaded_status != 200 or not loaded.get("success"):
        return {
            "success": False,
            "status": "packet_media_bytes_unavailable",
        }, loaded_status
    validation = validate_facebook_image_asset(
        asset, loaded.get("data"), loaded.get("returned_mime")
    )
    if (
        not validation.get("allowed")
        or validation.get("width") != expected["width"]
        or validation.get("height") != expected["height"]
        or len(loaded.get("data") or b"") != expected["file_size_bytes"]
    ):
        return {
            "success": False,
            "status": "packet_media_validation_failed",
        }, 409
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


def _canonical_packet(packet):
    """Hash the owner-reviewed contract, excluding display-only enrichments."""
    canonical_assets = []
    for asset in packet["media"]["assets"]:
        canonical_assets.append(
            {
                key: value
                for key, value in asset.items()
                if key != "thumbnail_url"
            }
        )
    canonical = {
        "packet_id": packet["packet_id"],
        "review_status": packet["review_status"],
        "supersedes": packet["supersedes"],
        "caption": packet["caption"],
        "caption_sha256": packet["caption_sha256"],
        "channel": packet["channel"],
        "scheduled_time": packet["scheduled_time"],
        "media": {
            "exact_order": packet["media"]["exact_order"],
            "assets": canonical_assets,
        },
        "public_livestock_policy": packet["public_livestock_policy"],
        "authority": packet["authority"],
        "next_gate": packet["next_gate"],
    }
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _asset_reasons(asset, expected):
    reasons = []
    approval = str(
        asset.get("effective_approval_status")
        or asset.get("approval_status")
        or ""
    ).lower()
    if approval not in {"approved", "approved_public_use"}:
        reasons.append("not_approved")
    public_use = asset.get("effective_public_use_approved")
    if not bool(
        public_use
        if public_use is not None
        else asset.get("public_use_approved")
    ):
        reasons.append("not_public_use_approved")
    if asset.get("content_hash_provenance") != "server_computed_on_upload":
        reasons.append("trusted_server_hash_required")
    digest = str(asset.get("content_sha256") or "").strip().lower()
    if len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        reasons.append("trusted_sha256_required")
    if asset.get("media_type") != "image":
        reasons.append("image_required")
    if str(asset.get("mime_type") or "").lower() != "image/jpeg":
        reasons.append("jpeg_required")
    if asset.get("file_size_bytes") != expected["file_size_bytes"]:
        reasons.append("file_size_mismatch")
    created_at = str(asset.get("created_at") or "")
    if created_at != expected["upload_timestamp"]:
        reasons.append("upload_timestamp_mismatch")
    return reasons
