"""Application-only adapter for the pure canonical grouped preview contract."""
from __future__ import annotations

from typing import Mapping, Sequence

from modules.pig_weights.canonical_grouped_preview import preview_application_typed


def attach_canonical_preview(
    legacy_result: Mapping,
    *,
    pig_snapshot: Sequence[Mapping] | None = None,
    pen_snapshot: Sequence[Mapping] | None = None,
):
    """Attach canonical evidence to rows already accepted by authoritative preflight.

    Optional injected snapshots exist for isolated conformance/failure tests.
    The application endpoint derives its snapshot from accepted preflight rows,
    avoiding any second database or Sheets read.
    """
    result = dict(legacy_result) if isinstance(legacy_result, Mapping) else {}
    accepted = result.get("accepted_rows")
    if result.get("success") is not True or not isinstance(accepted, list) or not accepted:
        return result

    if pig_snapshot is None:
        pig_snapshot = [
            {
                "pig_id": row.get("pig_id"),
                "tag_number": row.get("tag_number"),
                "status": "Active",
                "on_farm": True,
                "current_pen_id": row.get("current_pen_id"),
            }
            for row in accepted
        ]
    if pen_snapshot is None:
        pen_snapshot = [
            {"pen_id": pen_id, "pen_name": pen_id, "active": True}
            for pen_id in dict.fromkeys(
                str(row.get("moved_to_pen_id") or "").strip()
                for row in accepted
            )
            if pen_id
        ]

    canonical = preview_application_typed(
        {
            "effective_date": accepted[0].get("weight_date"),
            "rows": [
                {
                    "identity": row.get("pig_id"),
                    "weight_kg": row.get("weight_kg"),
                    "moved_to_pen_id": row.get("moved_to_pen_id"),
                    "condition_notes": row.get("condition_notes"),
                }
                for row in accepted
            ],
        },
        pigs=pig_snapshot,
        pens=pen_snapshot,
    )
    result["canonical_preview"] = canonical
    if canonical.get("success") is not True:
        result.update({
            "ok": False,
            "success": False,
            "error": "canonical_preview_blocked",
            "message": "Canonical grouped preview validation failed closed; nothing was recorded.",
        })
        return result
    result["preview_digest"] = canonical["preview_digest"]
    result["confirmation_required"] = canonical["confirmation_required"]
    return result
