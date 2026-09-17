"""Read-only Oom Sakkie view of canonical CORE mission review truth."""

from collections.abc import Mapping

from modules.charlie.mission_store import get_mission, list_missions


CANONICAL_REVIEW_SOURCE = "supabase:charlie_missions.metadata.review_packet"
HISTORICAL_REVIEW_POINTER = "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md"


def get_canonical_review_readback(
    mission_id="", *, mission_loader=get_mission, mission_lister=list_missions
):
    """Return bounded review identities; never fall back to Markdown."""
    try:
        if str(mission_id or "").strip():
            result, status_code = mission_loader(str(mission_id).strip())
            rows = [result.get("mission")] if status_code == 200 and isinstance(result, Mapping) else []
        else:
            result, status_code = mission_lister(status="owner_queue", limit=12, compact=True)
            rows = result.get("missions", []) if status_code == 200 and isinstance(result, Mapping) else []
    except Exception:
        rows, status_code = [], 503

    if status_code != 200:
        return _degraded("canonical_review_unavailable")

    missions = [_review_identity(row) for row in rows if isinstance(row, Mapping)]
    missions = [row for row in missions if row.get("mission_id")]
    return {
        "success": True,
        "status": "canonical_review_ready" if missions else "canonical_review_empty",
        "state": "ready" if missions else "Unknown",
        "source": CANONICAL_REVIEW_SOURCE,
        "mission_count": len(missions),
        "missions": missions,
        **_authority_boundary(),
    }


def _review_identity(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), Mapping) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), Mapping) else {}
    return {
        "mission_id": str(mission.get("mission_id") or ""),
        "status": str(mission.get("status") or "Unknown"),
        "updated_at": str(mission.get("updated_at") or "Unknown"),
        "review_status": str(packet.get("review_status") or "Unknown"),
        "recommended_next_action": str(packet.get("recommended_next_action") or "Unknown"),
    }


def _degraded(status):
    return {
        "success": False,
        "status": status,
        "state": "Unknown",
        "source": CANONICAL_REVIEW_SOURCE,
        "mission_count": 0,
        "missions": [],
        **_authority_boundary(),
    }


def _authority_boundary():
    return {
        "historical_pointer": HISTORICAL_REVIEW_POINTER,
        "historical_pointer_loaded": False,
        "historical_pointer_authority": False,
        "prompts_sent": 0,
        "provider_messages": 0,
        "missions_created": 0,
        "customer_writes": 0,
        "farm_writes": 0,
        "hardware_commands": 0,
    }
