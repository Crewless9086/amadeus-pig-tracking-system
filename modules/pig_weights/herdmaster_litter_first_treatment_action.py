"""One canonical first-treatment command used by every owner channel."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Mapping

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights.farm_supabase_write_service import (
    apply_litter_first_treatment_packet,
)
from modules.pig_weights.herdmaster_litter_first_treatment_intake import (
    ACTION_KIND,
    LitterTreatmentEvidenceError,
    prepare_litter_first_treatment_preview,
)
from modules.pig_weights.pig_weights_service import (
    _build_litter_health_treatment_row,
)


CONTRACT_VERSION = "herdmaster_litter_first_treatment_action_v1"
PREVIEW_TTL_SECONDS = 30 * 60
TREATMENT_TYPES = {
    "antiparasitic": "Antiparasitic",
    "deworming": "Deworming",
    "vaccination": "Vaccination",
}


def preview_first_treatment(
    payload: Mapping,
    *,
    actor_id: str,
    channel: str,
    source_reference: str,
    connect_factory=None,
    evidence_loader=None,
):
    """Load canonical evidence and return the same protected preview per channel."""
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    try:
        canonical = (evidence_loader or load_first_treatment_evidence)(
            connect_factory=connect_factory
        )
        result = prepare_litter_first_treatment_preview(
            {
                "authenticated": True,
                "authenticated_principal_id": actor_id,
                "source_reference": str(source_reference or "").strip(),
                "litter_first_treatment": dict(payload or {}),
            },
            canonical,
        )
    except (LitterTreatmentEvidenceError, RuntimeError, OSError, ValueError):
        return _result(False, "litter_treatment_evidence_unavailable"), 503
    if result.get("success") is not True:
        status = str(result.get("status") or "litter_treatment_preview_rejected")
        return {
            "contract_version": CONTRACT_VERSION,
            "handled": True,
            **result,
        }, 200 if result.get("question") else 409
    preview = dict(result["preview"])
    digest = _preview_digest(preview)
    preview["preview_digest"] = digest
    preview["confirmation_binding"] = _confirmation_binding(digest, actor_id)
    preview["input_channel"] = str(channel or "unknown")
    return _result(
        True,
        "litter_first_treatment_preview_ready",
        preview=preview,
        preview_digest=digest,
        confirmation_binding=preview["confirmation_binding"],
        operation_id=preview["operation_id"],
        action_kind=ACTION_KIND,
        confirmation_required=True,
        writes_farm_data=False,
    ), 200


def execute_first_treatment(
    payload: Mapping,
    *,
    actor_id: str,
    channel: str,
    source_reference: str,
    confirmation_binding: Mapping,
    connect_factory=None,
    evidence_loader=None,
):
    """Re-preview fresh truth, verify the exact preview, commit, and read back."""
    try:
        canonical = (evidence_loader or load_first_treatment_evidence)(
            connect_factory=connect_factory
        )
    except (RuntimeError, OSError, ValueError):
        return _result(False, "litter_treatment_evidence_unavailable"), 503
    preview_result, status = preview_first_treatment(
        payload,
        actor_id=actor_id,
        channel=channel,
        source_reference=source_reference,
        connect_factory=connect_factory,
        evidence_loader=lambda **_kwargs: canonical,
    )
    if status != 200 or preview_result.get("success") is not True:
        return preview_result, status
    preview = preview_result["preview"]
    if not _valid_confirmation(
        confirmation_binding, preview["preview_digest"], str(actor_id or "").strip()
    ):
        return _result(False, "exact_preview_confirmation_required"), 409

    products = {
        str(row.get("product_id") or ""): dict(row)
        for row in canonical.get("products", [])
    }
    treatment_rows = []
    for pig_id in preview["pig_ids"]:
        for treatment in preview["protocol"]["treatments"]:
            product = products.get(treatment["product_id"])
            if not product:
                return _result(False, "canonical_treatment_product_changed"), 409
            treatment_rows.append(
                _build_litter_health_treatment_row(
                    pig_id=pig_id,
                    action_date=datetime.fromisoformat(preview["action_date"]).date(),
                    treatment_type=TREATMENT_TYPES[treatment["role"]],
                    product=product,
                    dose_value=treatment["dose"],
                    route=treatment["route"],
                    batch_lot_number=treatment["batch_lot_number"],
                    given_by=str(actor_id),
                    notes=preview["protocol"]["notes"],
                    litter_id=preview["litter_id"],
                    treatment_context="first_treatment",
                    protected_operation_id=preview["operation_id"],
                )
            )
    try:
        committed = apply_litter_first_treatment_packet(
            {
                "litter_id": preview["litter_id"],
                "sow_pig_id": preview["sow_pig_id"],
                "pig_ids": preview["pig_ids"],
                "action_date": preview["action_date"],
                "protected_operation_id": preview["operation_id"],
                "earmarked": preview["protocol"]["earmarked"],
                "male_count": preview["male_count"],
                "female_count": preview["female_count"],
                "treatment_rows": treatment_rows,
            },
            connect_factory=connect_factory,
        )
        readback = farm_supabase_read_service.get_litter_detail(
            preview["litter_id"], connect_factory=connect_factory
        )
    except ValueError as exc:
        return _result(False, str(exc)), 409
    except Exception:
        return _result(False, "litter_first_treatment_store_unavailable"), 503
    if not readback or readback.get("first_treatment_complete") is not True:
        return _result(
            False,
            "litter_treatment_readback_recovery_required",
            recovery_required=True,
        ), 503
    replay = committed.get("status") == "first_treatment_replayed_noop"
    return _result(
        True,
        "litter_first_treatment_replayed_noop"
        if replay
        else "litter_first_treatment_recorded",
        operation_id=preview["operation_id"],
        pig_ids=preview["pig_ids"],
        protocol=preview["protocol"],
        medical_readback=committed.get("medical_readback") or [],
        canonical_readback=readback,
        rows_created=int(committed.get("treatment_rows_created") or 0),
        writes_farm_data=not replay,
    ), 200 if replay else 201


def load_first_treatment_evidence(*, connect_factory=None):
    """Read exact litter, product, and approved protocol setting evidence."""
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                "select pig_id,tag_number,pig_name as name "
                "from public.current_canonical_pigs"
            )
            animals = _rows(cursor)
            cursor.execute(
                "select setting_key,setting_value from public.app_settings "
                "where setting_key=%s",
                ("herdmaster_first_treatment_protocol_v1",),
            )
            settings = _rows(cursor)
            cursor.execute(
                "select litter_id from public.current_canonical_litters "
                "where lower(litter_status)='active'"
            )
            litter_ids = [row[0] for row in cursor.fetchall()]
    products = farm_supabase_read_service.get_products(
        connect_factory=connect_factory
    )
    litters = []
    for litter_id in litter_ids:
        detail = farm_supabase_read_service.get_litter_detail(
            litter_id, connect_factory=connect_factory
        )
        if detail:
            litters.append(
                {
                    "litter_id": litter_id,
                    "sow_pig_id": detail.get("mother_pig_id"),
                    "litter_status": detail.get("litter_status"),
                    "active_count": detail.get("active_count"),
                    "first_treatment_complete": detail.get(
                        "first_treatment_complete"
                    ),
                    "first_treatment_partial": detail.get(
                        "first_treatment_partial"
                    ),
                    "detail": detail,
                }
            )
    material = {
        "animals": animals,
        "litters": litters,
        "products": products,
        "settings": settings,
    }
    generation = "litter-treatment:" + hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return {
        "evidence_generation": generation,
        **material,
    }


def render_first_treatment_preview(preview: Mapping) -> str:
    identity = (
        str(preview.get("sow_name") or "")
        or str(preview.get("sow_tag_number") or "")
        or "the sow"
    )
    treatments = "; ".join(
        f"{row['product_name']} {row['dose']} {row['dose_unit']} "
        f"{row['route']} batch {row['batch_lot_number']}"
        for row in preview.get("protocol", {}).get("treatments", [])
    )
    piglets = ", ".join(
        str(row.get("tag_number") or row.get("name") or row.get("pig_id"))
        + f" ({row.get('pig_id')})"
        for row in preview.get("piglets", [])
    )
    return (
        f"HERDMASTER first-treatment preview for {identity}'s litter "
        f"({preview.get('litter_id')}): {preview.get('male_count')} male + "
        f"{preview.get('female_count')} female = {preview.get('total_count')} "
        f"active piglets. Protocol: {treatments}. Earmarking: "
        f"{'yes' if preview.get('protocol', {}).get('earmarked') else 'no'}. "
        f"Piglets: {piglets}. Confirm this exact protected record."
    )


def _preview_digest(preview):
    material = {
        key: preview[key]
        for key in (
            "contract_version",
            "evidence_generation",
            "sow_pig_id",
            "litter_id",
            "action_date",
            "pig_ids",
            "male_count",
            "female_count",
            "protocol",
            "operation_id",
        )
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _confirmation_binding(digest, actor_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    issued_at = int(now.timestamp())
    material = f"{CONTRACT_VERSION}|{digest}|{actor_id}|{issued_at}"
    secret = _confirmation_secret()
    signature = (
        hmac.new(secret, material.encode(), hashlib.sha256).hexdigest()
        if secret
        else ""
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "preview_digest": digest,
        "actor_id": actor_id,
        "issued_at": issued_at,
        "signature": signature,
    }


def _valid_confirmation(binding, digest, actor_id, *, now=None):
    if not isinstance(binding, Mapping):
        return False
    now = now or datetime.now(timezone.utc)
    try:
        issued_at = int(binding.get("issued_at"))
    except (TypeError, ValueError):
        return False
    if not 0 <= int(now.timestamp()) - issued_at <= PREVIEW_TTL_SECONDS:
        return False
    expected = _confirmation_binding(
        digest,
        actor_id,
        now=datetime.fromtimestamp(issued_at, timezone.utc),
    )
    return (
        str(binding.get("preview_digest") or "") == digest
        and str(binding.get("actor_id") or "") == actor_id
        and bool(expected["signature"])
        and hmac.compare_digest(
            str(binding.get("signature") or ""), expected["signature"]
        )
    )


def _confirmation_secret():
    return str(os.getenv("OWNER_SESSION_SECRET") or os.getenv("SECRET_KEY") or "").encode()


def _connect(connect_factory=None):
    database_url = str(os.getenv(DATABASE_URL_ENV) or "")
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg

    return psycopg.connect(database_url, connect_timeout=10)


def _rows(cursor):
    names = [
        item.name if hasattr(item, "name") else item[0]
        for item in cursor.description
    ]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _result(success, status, **extra):
    return {
        "success": success,
        "handled": True,
        "status": status,
        "contract_version": CONTRACT_VERSION,
        "action_kind": ACTION_KIND,
        **extra,
    }
