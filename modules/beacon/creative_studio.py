import hashlib
import json
import os
from decimal import Decimal, InvalidOperation

from modules.beacon.creative_providers import (
    ALLOWED_CREATIVE_PROVIDERS,
    DISABLED_PROVIDER_FLAGS,
    evaluate_disabled_provider,
)
from services.database_service import DATABASE_URL_ENV


RAW_INTAKE_BUCKET = "beacon-raw-intake"
REVIEW_TYPES = frozenset({
    "brand", "privacy", "safety", "animal_product_fidelity",
    "provider_disclosure", "evaluation", "owner_public_use",
})
REVIEW_DECISIONS = frozenset({"approved", "rejected"})
TRUSTED_HASH_PROVENANCE = frozenset({
    "server_computed_on_upload",
    "deterministic_disabled_adapter_manifest",
})

CREATIVE_AUTHORITY_FLAGS = {
    **DISABLED_PROVIDER_FLAGS,
    "calls_meta": False,
    "calls_chatwoot": False,
    "calls_n8n": False,
    "reserves_stock": False,
    "dispatch_enabled": False,
    "customer_public_output_enabled": False,
}


def build_creative_job_contract(payload):
    payload = payload if isinstance(payload, dict) else {}
    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in ALLOWED_CREATIVE_PROVIDERS:
        raise ValueError("creative_provider_not_allowlisted")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("exact_prompt_required")
    if len(prompt.encode("utf-8")) > 100_000:
        raise ValueError("exact_prompt_too_large")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("creative_parameters_must_be_object")
    source_assets = payload.get("source_assets")
    if not isinstance(source_assets, list) or not source_assets:
        raise ValueError("approved_source_assets_required")

    normalized_sources = []
    seen = set()
    for source in source_assets:
        if not isinstance(source, dict):
            raise ValueError("source_asset_must_be_object")
        asset_id = str(source.get("asset_id") or "").strip()
        content_sha256 = str(source.get("content_sha256") or "").strip().lower()
        if not asset_id or not _is_sha256(content_sha256):
            raise ValueError("source_asset_id_and_sha256_required")
        if asset_id in seen:
            raise ValueError("duplicate_source_asset")
        seen.add(asset_id)
        normalized_sources.append({"asset_id": asset_id, "content_sha256": content_sha256})

    canonical_parameters = _canonical_json(parameters)
    canonical_sources = _canonical_json(normalized_sources)
    request_hash = _sha256(_canonical_json({
        "provider": provider,
        "prompt": prompt,
        "parameters": parameters,
        "sources": normalized_sources,
    }))
    idempotency_key = str(payload.get("idempotency_key") or request_hash).strip()
    if not idempotency_key or len(idempotency_key) > 200:
        raise ValueError("invalid_idempotency_key")
    estimated_cost, cost_currency, estimate_source = _cost_estimate(payload)
    job_id = "BEACON-CREATIVE-" + _sha256(idempotency_key)[:24].upper()
    attempt_id = "BEACON-ATTEMPT-" + request_hash[:24].upper()
    return {
        "job_id": job_id,
        "attempt_id": attempt_id,
        "idempotency_key": idempotency_key,
        "request_sha256": request_hash,
        "provider": provider,
        "exact_prompt": prompt,
        "prompt_sha256": _sha256(prompt),
        "parameters": parameters,
        "parameters_canonical_json": canonical_parameters,
        "parameters_sha256": _sha256(canonical_parameters),
        "source_assets": normalized_sources,
        "source_lineage_sha256": _sha256(canonical_sources),
        "estimated_cost": estimated_cost,
        "cost_currency": cost_currency,
        "cost_estimate_source": estimate_source,
        **CREATIVE_AUTHORITY_FLAGS,
    }


def create_mock_creative_job(payload, recorded_by, database_url=None, connect=None, uploader=None, environ=None):
    try:
        contract = build_creative_job_contract(payload)
    except ValueError as exc:
        return _failure(str(exc), 400)
    actor = str(recorded_by or "").strip()
    if actor != "authenticated_owner_admin":
        return _failure("authenticated_owner_admin_required", 403)
    database_url = database_url if database_url is not None else os.environ.get(DATABASE_URL_ENV, "")
    if not database_url:
        return _failure("not_configured", 503)
    if connect is None:
        try:
            import psycopg
        except ImportError:
            return _failure("dependency_missing", 500)
        connect = psycopg.connect

    try:
        with connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                source_rows = _load_and_validate_sources(cursor, contract["source_assets"])
                manifest = evaluate_disabled_provider(
                    contract["provider"], contract["exact_prompt"], contract["parameters"], source_rows
                )
                variant = _variant_record(contract, manifest)
                created_count = _insert_contract(
                    cursor, contract, source_rows, manifest, variant, actor,
                    uploader=uploader, environ=environ,
                )
    except CreativeStudioValidationError as exc:
        return _failure(str(exc), 409)
    except Exception as exc:
        return {
            **_failure_body("beacon_creative_job_write_failed"),
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 500

    return {
        "success": True,
        "status": "beacon_creative_job_recorded" if created_count else "beacon_creative_job_already_recorded",
        "created_count": created_count,
        "job": _public_contract(contract),
        "mock_manifest": {k: v for k, v in manifest.items() if k != "manifest_bytes"},
        "variant": variant,
        "next_gate": "distinct_brand_privacy_safety_fidelity_disclosure_evaluation_and_public_use_review",
        **CREATIVE_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def record_creative_review(job_id, payload, recorded_by, database_url=None, connect=None):
    payload = payload if isinstance(payload, dict) else {}
    actor = str(recorded_by or "").strip()
    if actor != "authenticated_owner_admin":
        return _failure("authenticated_owner_admin_required", 403)
    review_type = str(payload.get("review_type") or "").strip().lower()
    decision = str(payload.get("decision") or "").strip().lower()
    if review_type not in REVIEW_TYPES or decision not in REVIEW_DECISIONS:
        return _failure("invalid_creative_review_decision", 400)
    job_id = str(job_id or "").strip()
    if not job_id:
        return _failure("creative_job_id_required", 400)
    notes = str(payload.get("notes") or "")
    event_id = "BEACON-REVIEW-" + _sha256(_canonical_json({
        "job_id": job_id, "review_type": review_type, "decision": decision,
        "notes": notes, "actor": actor,
    }))[:24].upper()
    database_url = database_url if database_url is not None else os.environ.get(DATABASE_URL_ENV, "")
    if not database_url:
        return _failure("not_configured", 503)
    if connect is None:
        try:
            import psycopg
        except ImportError:
            return _failure("dependency_missing", 500)
        connect = psycopg.connect
    try:
        with connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.beacon_creative_review_events
                       (review_event_id, job_id, review_type, decision, notes, recorded_by)
                       values (%s, %s, %s, %s, %s, %s)
                       on conflict (review_event_id) do nothing""",
                    (event_id, job_id, review_type, decision, notes, actor),
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {**_failure_body("beacon_creative_review_write_failed"), "error_type": exc.__class__.__name__, "error": str(exc)[:240]}, 500
    return {
        "success": True,
        "status": "beacon_creative_review_recorded" if created_count else "beacon_creative_review_already_recorded",
        "created_count": created_count,
        "review_event_id": event_id,
        "job_id": job_id,
        "review_type": review_type,
        "decision": decision,
        "recorded_by": actor,
        "approval_executes_action": False,
        **CREATIVE_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def _load_and_validate_sources(cursor, requested_sources):
    verified = []
    for requested in requested_sources:
        cursor.execute(
            """select a.asset_id, a.content_sha256, a.content_hash_provenance,
                      coalesce((select e.event_type from public.beacon_media_asset_events e
                                where e.asset_id = a.asset_id
                                  and e.event_type in ('approved_public_use', 'rejected_public_use', 'archived')
                                order by e.created_at desc limit 1), '')
               from public.beacon_media_assets a where a.asset_id = %s""",
            (requested["asset_id"],),
        )
        row = cursor.fetchone()
        if not row:
            raise CreativeStudioValidationError("source_asset_not_found")
        stored_hash = str(row[1] or "").lower()
        if not _is_sha256(stored_hash) or stored_hash != requested["content_sha256"]:
            raise CreativeStudioValidationError("source_asset_integrity_failed")
        if str(row[2] or "") not in TRUSTED_HASH_PROVENANCE:
            raise CreativeStudioValidationError("source_asset_hash_provenance_untrusted")
        if row[3] != "approved_public_use":
            raise CreativeStudioValidationError("source_asset_owner_approval_required")
        verified.append({"asset_id": row[0], "content_sha256": stored_hash})
    return verified


def _insert_contract(cursor, contract, sources, manifest, variant, actor, uploader=None, environ=None):
    cursor.execute(
        """insert into public.beacon_creative_jobs
           (job_id, idempotency_key, request_sha256, provider, exact_prompt, prompt_sha256,
            parameters_json, parameters_canonical_json, parameters_sha256, source_lineage_sha256, recorded_by)
           values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
           on conflict (idempotency_key) do nothing""",
        (contract["job_id"], contract["idempotency_key"], contract["request_sha256"], contract["provider"],
         contract["exact_prompt"], contract["prompt_sha256"], json.dumps(contract["parameters"], ensure_ascii=False),
         contract["parameters_canonical_json"], contract["parameters_sha256"], contract["source_lineage_sha256"], actor),
    )
    created_count = cursor.rowcount
    if not created_count:
        cursor.execute(
            """select request_sha256 from public.beacon_creative_jobs
               where idempotency_key = %s""",
            (contract["idempotency_key"],),
        )
        existing = cursor.fetchone()
        if not existing or existing[0] != contract["request_sha256"]:
            raise CreativeStudioValidationError("creative_idempotency_key_conflict")
        return 0
    if uploader is None:
        from modules.beacon.media_library import upload_bytes_to_supabase_storage
        uploader = upload_bytes_to_supabase_storage
    upload_result, upload_status = uploader(
        variant["storage_bucket"], variant["storage_path"], manifest["manifest_bytes"],
        variant["mime_type"], environ=environ,
    )
    if upload_status >= 400:
        raise CreativeStudioValidationError(
            "mock_variant_storage_write_failed:" + str(upload_result.get("status") or upload_status)
        )
    for position, source in enumerate(sources):
        cursor.execute(
            """insert into public.beacon_creative_job_sources
               (job_id, asset_id, source_position, content_sha256) values (%s,%s,%s,%s)""",
            (contract["job_id"], source["asset_id"], position, source["content_sha256"]),
        )
    cursor.execute(
        """insert into public.beacon_creative_provider_attempts
           (attempt_id, job_id, provider, model_identifier, manifest_json, manifest_sha256)
           values (%s,%s,%s,%s,%s::jsonb,%s)""",
        (contract["attempt_id"], contract["job_id"], contract["provider"], manifest["model_identifier"],
         json.dumps({k: v for k, v in manifest.items() if k != "manifest_bytes"}, sort_keys=True), manifest["manifest_sha256"]),
    )
    cursor.execute(
        """insert into public.beacon_creative_cost_events
           (cost_event_id, attempt_id, estimated_cost, actual_cost, currency, estimate_source, recorded_by)
           values (%s,%s,%s,0,%s,%s,%s)""",
        ("BEACON-COST-" + contract["request_sha256"][:24].upper(), contract["attempt_id"], contract["estimated_cost"],
         contract["cost_currency"], contract["cost_estimate_source"], actor),
    )
    cursor.execute(
        """insert into public.beacon_media_assets
           (asset_id, storage_bucket, storage_path, original_filename, media_type, mime_type,
            file_size_bytes, source, source_reference, title, description, content_sha256,
            content_hash_provenance, approval_status, public_use_approved, created_by)
           values (%s,%s,%s,%s,%s,%s,%s,'creative_studio_mock',%s,%s,%s,%s,
                   'deterministic_disabled_adapter_manifest','needs_review',false,%s)
           on conflict (asset_id) do nothing""",
        (variant["asset_id"], variant["storage_bucket"], variant["storage_path"],
         variant["variant_id"] + ".json", variant["media_type"], variant["mime_type"],
         len(manifest["manifest_bytes"]), contract["job_id"], "Creative Studio mock variant",
         "Deterministic provider-disabled mock manifest; no provider output.", variant["content_sha256"], actor),
    )
    cursor.execute(
        """insert into public.beacon_creative_variants
           (variant_id, attempt_id, asset_id, storage_bucket, storage_path, media_type, mime_type,
            content_sha256, approval_status, public_use_approved)
           values (%s,%s,%s,%s,%s,%s,%s,%s,'needs_review',false)""",
        (variant["variant_id"], contract["attempt_id"], variant["asset_id"], variant["storage_bucket"],
         variant["storage_path"], variant["media_type"], variant["mime_type"], variant["content_sha256"]),
    )
    return 1


def _variant_record(contract, manifest):
    variant_id = "BEACON-VARIANT-" + manifest["deterministic_digest"][:24].upper()
    asset_id = "BEACON-ASSET-" + manifest["manifest_sha256"][:24].upper()
    return {
        "variant_id": variant_id,
        "asset_id": asset_id,
        "storage_bucket": RAW_INTAKE_BUCKET,
        "storage_path": f"creative-studio/{contract['job_id']}/{contract['attempt_id']}/{variant_id}.json",
        "media_type": manifest["output_media_type"],
        "mime_type": manifest["output_mime_type"],
        "content_sha256": manifest["manifest_sha256"],
        "approval_status": "needs_review",
        "public_use_approved": False,
        **CREATIVE_AUTHORITY_FLAGS,
    }


def _public_contract(contract):
    return {k: v for k, v in contract.items() if k != "parameters_canonical_json"}


def _cost_estimate(payload):
    try:
        value = Decimal(str(payload.get("estimated_cost", "0")))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid_estimated_cost")
    if value < 0:
        raise ValueError("invalid_estimated_cost")
    currency = str(payload.get("cost_currency") or "ZAR").strip().upper()
    source = str(payload.get("cost_estimate_source") or "owner_entered_unverified_estimate").strip()
    if not currency or len(currency) > 8 or not source:
        raise ValueError("cost_estimate_provenance_required")
    return value, currency, source


def _canonical_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("creative_parameters_not_json_serializable")


def _sha256(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _is_sha256(value):
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _failure(status, status_code):
    return _failure_body(status), status_code


def _failure_body(status):
    return {"success": False, "status": status, **CREATIVE_AUTHORITY_FLAGS}


class CreativeStudioValidationError(ValueError):
    pass
