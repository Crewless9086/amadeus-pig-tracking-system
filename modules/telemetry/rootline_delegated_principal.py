"""Sealed non-owner entry point for bounded routine ROOTLINE irrigation.

OOM Sakkie may call this boundary only after its gateway has authenticated a
typed family principal.  ROOTLINE nevertheless reloads the delegation before
loading private operational evidence.  The existing irrigation coordinator is
the sole execution/claim spine; this module owns neither Telegram nor a device
transport.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Callable, Mapping

from modules.telemetry.rootline_execution_authority import (
    CONTRACT_VERSION as ELIGIBILITY_VERSION, validate_execution_eligibility,
)

CONTRACT_VERSION = "rootline_delegated_principal.v1"
OUTCOME_VERSION = "rootline_delegated_outcome.v1"
ROLE = "farm_manager"
FAMILY_IDENTITY = "anton"
CAPABILITY = "routine_irrigation_execute"
ALLOWED_ACTIONS = frozenset({"irrigation_start", "irrigation_continue"})
EXCLUDED = frozenset({"commissioning", "autonomy_configuration", "electrical",
    "fertilizer", "borehole", "unapproved_upstream_shared_control"})


def handle_delegated_rootline_request(request: Mapping[str, Any], *,
        authorization_loader: Callable[[str], Mapping[str, Any] | None],
        eligibility_loader: Callable[[], Mapping[str, Any]],
        executor: Callable[..., Mapping[str, Any]],
        now: datetime | None = None) -> dict[str, Any]:
    """Authorize, freshly revalidate, then delegate once to the existing spine."""
    now = _aware(now or datetime.now(timezone.utc))
    structural = _validate_request(request, now)
    if structural is not None:
        return _sealed(request, structural, now=now)

    # This reload deliberately precedes every private evidence/controller load.
    try:
        authorization = authorization_loader(str(request["authorization_id"]))
    except Exception:
        authorization = None
    auth_error = _validate_authorization(authorization, request, now)
    if auth_error is not None:
        return _sealed(request, auth_error, now=now)

    try:
        artifact = eligibility_loader()
    except Exception:
        artifact = None
    current = validate_execution_eligibility(artifact, now=now)
    if current is None:
        return _sealed(request, "current_rootline_eligibility_unavailable", now=now)
    mismatch = _eligibility_mismatch(request, current)
    if mismatch:
        return _sealed(request, mismatch, now=now, artifact=current)

    try:
        result = executor(expected_artifact=current,
            delegated_authority=_delegated_authority(request, authorization, current))
    except Exception:
        return _sealed(request, "delegated_execution_outcome_ambiguous", now=now,
                       artifact=current, ambiguous=True)
    if not isinstance(result, Mapping):
        return _sealed(request, "delegated_execution_outcome_ambiguous", now=now,
                       artifact=current, ambiguous=True)
    if any(type(result.get(key, 0)) is not int or result.get(key, 0) < 0
           for key in ("hardware_commands", "provider_control_calls")):
        return _sealed(request, "delegated_execution_outcome_ambiguous", now=now,
                       artifact=current, ambiguous=True)
    return _sealed(request, str(result.get("status") or "delegated_execution_contained"),
        now=now, artifact=current, execution_result=result,
        ambiguous=result.get("provider_outcome_ambiguous") is True)


def load_delegated_authorization(authorization_id: str, *, environ=None):
    """Load one configured delegation without converting it into owner authority."""
    source = environ if environ is not None else os.environ
    try:
        rows = json.loads(str(source.get("ROOTLINE_DELEGATED_PRINCIPALS_JSON") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    matches = [dict(row) for row in rows if isinstance(row, Mapping)
               and str(row.get("authorization_id") or "") == str(authorization_id)]
    return matches[0] if len(matches) == 1 else None


def _validate_request(value, now):
    if not isinstance(value, Mapping) or value.get("contract_version") != CONTRACT_VERSION:
        return "delegated_request_contract_invalid"
    required = ("principal_id", "private_chat_id", "family_identity",
        "authorization_id", "authorization_digest", "provider_message_id",
        "provider_timestamp", "replay_identity", "evidence_generation",
        "commissioned_path_id", "zone_id", "action", "job_id", "job_sha256",
        "segment_identity", "execution_id", "eligibility_sha256", "consumption_key")
    if any(not str(value.get(key) or "").strip() for key in required):
        return "delegated_request_binding_incomplete"
    if (value.get("role") != ROLE or value.get("family_identity") != FAMILY_IDENTITY
            or value.get("capability") != CAPABILITY
            or value.get("action") not in ALLOWED_ACTIONS
            or str(value["principal_id"]) != str(value["private_chat_id"])
            or value.get("owner_authority") is not False
            or value.get("excluded_authority") != sorted(EXCLUDED)
            or not _sha(value.get("authorization_digest"))
            or value.get("replay_identity") != delegated_replay_identity(value)
            or not _sha(value.get("job_sha256"))
            or not _sha(value.get("eligibility_sha256"))
            or type(value.get("current_segment")) is not int
            or value.get("current_segment") < 1):
        return "delegated_principal_scope_invalid"
    observed = _time(value.get("provider_timestamp"))
    duration = value.get("bounded_duration_seconds")
    if observed is None or observed > now or type(duration) is not int or duration not in range(1, 3600):
        return "delegated_provider_chronology_or_duration_invalid"
    return None


def _validate_authorization(auth, request, now):
    if not isinstance(auth, Mapping):
        return "delegated_authorization_unavailable"
    material = {key: auth.get(key) for key in ("authorization_id", "principal_id",
        "private_chat_id", "family_identity", "role", "capabilities", "zones",
        "commissioned_paths", "maximum_duration_seconds", "authorized_at")}
    digest = _digest(material)
    if (auth.get("revoked_at") not in (None, "") or auth.get("active") is not True
            or auth.get("role") != ROLE or auth.get("family_identity") != FAMILY_IDENTITY
            or auth.get("owner_authority") is not False
            or auth.get("authorization_digest") != digest
            or request.get("authorization_digest") != digest
            or any(str(auth.get(key) or "") != str(request.get(key) or "") for key in
                   ("authorization_id", "principal_id", "private_chat_id", "family_identity"))
            or CAPABILITY not in (auth.get("capabilities") or [])
            or request.get("zone_id") not in (auth.get("zones") or [])
            or request.get("commissioned_path_id") not in (auth.get("commissioned_paths") or [])
            or int(auth.get("maximum_duration_seconds") or 0) < int(request["bounded_duration_seconds"])
            or _time(auth.get("authorized_at")) is None
            or _time(auth.get("authorized_at")) > now):
        return "delegated_authorization_changed_or_revoked"
    return None


def _eligibility_mismatch(request, artifact):
    if (artifact.get("contract_version") != ELIGIBILITY_VERSION
            or artifact.get("authority_source") != "owner_approved_routine_irrigation_v1"
            or artifact.get("zone_id") != request.get("zone_id")
            or artifact.get("plan_generation") != request.get("evidence_generation")
            or artifact.get("commissioned_path_id", artifact.get("zone_id")) !=
               request.get("commissioned_path_id")
            or int(artifact.get("maximum_duration_seconds") or 0) !=
               int(request.get("bounded_duration_seconds") or 0)
            or any(artifact.get(key) != request.get(key) for key in
                   ("job_id", "job_sha256", "segment_identity", "current_segment",
                    "execution_id", "eligibility_sha256", "consumption_key"))
            or artifact.get("command_authority") is not True
            or artifact.get("hardware_control") is not True):
        return "delegated_current_evidence_binding_changed"
    # Deferred/contained parents are never converted into delegated authority.
    if artifact.get("status") != "execution_eligible":
        return "delegated_parent_or_eligibility_not_dispatchable"
    return ""


def _delegated_authority(request, auth, artifact):
    material = {"contract_version": CONTRACT_VERSION,
        "principal_id": request["principal_id"], "private_chat_id": request["private_chat_id"],
        "family_identity": request["family_identity"], "role": ROLE,
        "authorization_digest": request["authorization_digest"], "capability": CAPABILITY,
        "provider_message_id": request["provider_message_id"],
        "provider_timestamp": request["provider_timestamp"],
        "replay_identity": request["replay_identity"], "zone_id": artifact["zone_id"],
        "action": request["action"], "bounded_duration_seconds": artifact["maximum_duration_seconds"],
        "execution_id": artifact["execution_id"], "eligibility_sha256": artifact["eligibility_sha256"],
        "owner_authority": False, "excluded_authority": sorted(EXCLUDED)}
    return {**material, "delegation_sha256": _digest(material)}


def delegated_replay_identity(request: Mapping[str, Any]) -> str:
    """Provider replay identity for one exact authorized job segment."""
    material = {key: request.get(key) for key in (
        "contract_version", "principal_id", "private_chat_id", "family_identity",
        "role", "authorization_id", "authorization_digest", "capability",
        "provider_message_id", "provider_timestamp", "evidence_generation",
        "commissioned_path_id", "zone_id", "action", "bounded_duration_seconds",
        "job_id", "job_sha256", "segment_identity", "current_segment",
        "execution_id", "eligibility_sha256", "consumption_key")}
    return _digest(material)


def _sealed(request, status, *, now, artifact=None, execution_result=None, ambiguous=False):
    request = request if isinstance(request, Mapping) else {}
    result = dict(execution_result or {})
    material = {"contract_version": OUTCOME_VERSION, "status": status,
        "principal_id": str(request.get("principal_id") or ""),
        "private_chat_id": str(request.get("private_chat_id") or ""),
        "family_identity": str(request.get("family_identity") or ""), "role": ROLE,
        "authorization_digest": str(request.get("authorization_digest") or ""),
        "replay_identity": str(request.get("replay_identity") or ""),
        "zone_id": str(request.get("zone_id") or ""), "action": str(request.get("action") or ""),
        "bounded_duration_seconds": _safe_int(request.get("bounded_duration_seconds")),
        "execution_id": str((artifact or {}).get("execution_id") or ""),
        "eligibility_sha256": str((artifact or {}).get("eligibility_sha256") or ""),
        "provider_outcome_ambiguous": bool(ambiguous), "owner_authority": False,
        "hardware_commands": _safe_int(result.get("hardware_commands")),
        "provider_control_calls": _safe_int(result.get("provider_control_calls")),
        "n8n_authority": False, "google_sheets_authority": False,
        "sealed_at": now.isoformat()}
    return {**material, "success": result.get("success") is True and not ambiguous,
        "outcome_sha256": _digest(material)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def _sha(value):
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def _safe_int(value):
    try: return int(value or 0)
    except (TypeError, ValueError): return 0


def _time(value):
    try: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError): return None
    return _aware(parsed) if parsed.tzinfo else None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
