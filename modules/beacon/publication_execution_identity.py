"""Exact successor identity and fresh timing gate for the contained BEACON proposal."""

from datetime import datetime, timezone
from hashlib import sha256

PROPOSAL_ID = "BEACON-PROPOSAL-18DEAAD8E896A87FE961F45B"
SUCCESSOR_EXECUTION_ID = "BEACON-PUBLICATION-EXECUTION-928F7D5A9731FFDE3D62CE1A"
TERMINAL_EXECUTION_IDS = frozenset({
    "BEACON-FB-POST-A3E2BBED0CEA5F93E2",
    "BEACON-FB-POST-A3E2BBED0CEA5F93E2-RESULT",
})
ASSET_ID = "BEACON-ASSET-15EBF5E67DBFD12693"
CAPTION_SHA256 = "58a60223599365b90803570909e09f3828c32768d8b27470dc1304ff27fc17d4"


def validate_successor_execution(
    payload, *, now=None, authoritative_timing_authorization_id=None
):
    """Require one newly timed authority for the exact preserved publication."""
    if any(str(payload.get(key) or "") in TERMINAL_EXECUTION_IDS for key in (
            "publish_packet_id", "execution_event_id",
            "publication_execution_identity")):
        return "terminal_publication_execution_non_reusable"
    if str(payload.get("publish_packet_id") or "") != PROPOSAL_ID:
        return ""
    if payload.get("publication_execution_identity") != SUCCESSOR_EXECUTION_ID:
        return "successor_publication_execution_identity_required"
    if payload.get("asset_id") != ASSET_ID:
        return "successor_publication_asset_mismatch"
    selected = payload.get("selected_assets")
    if not isinstance(selected, list):
        selected = [payload.get("selected_asset")] if isinstance(
            payload.get("selected_asset"), dict
        ) else []
    if (len(selected) != 1 or selected[0].get("asset_id") != ASSET_ID
            or str(selected[0].get("media_type") or "").lower() != "image"):
        return "successor_publication_media_order_mismatch"
    caption = payload.get("exact_text") if isinstance(payload.get("exact_text"), str) else ""
    if sha256(caption.encode("utf-8")).hexdigest() != CAPTION_SHA256:
        return "successor_publication_caption_mismatch"
    if payload.get("channel") != "facebook_organic":
        return "successor_publication_channel_mismatch"
    if payload.get("zero_spend") is not True:
        return "successor_publication_zero_spend_required"
    if not str(payload.get("timing_authorization_id") or "").strip():
        return "successor_publication_timing_authorization_required"
    if (authoritative_timing_authorization_id is not None
            and payload.get("timing_authorization_id")
            != authoritative_timing_authorization_id):
        return "successor_publication_timing_authorization_mismatch"
    start = _time(payload.get("timing_start")); end = _time(payload.get("timing_end"))
    current = _time(now) or datetime.now(timezone.utc)
    if not start or not end or not start <= current <= end or end <= start:
        return "successor_publication_timing_window_invalid"
    return ""


def _time(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
