"""OOM-owned protected preview/callback boundary for delegated family ROOTLINE."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Mapping

from modules.oom_sakkie.protected_action_claims import (
    bind_claim_card, canonical_preview_digest, complete_claim, contain_claim, create_claim,
)

CALLBACK_PREFIX = "oomfm:"
ACTION_KIND = "rootline_delegated_family"
PREVIEW_CONTRACT = "oom_family_rootline_preview.v1"
MISSION_PREFIX = "OOM-FAMILY-ROOTLINE-"
ALLOWED_ACTIONS = frozenset({"irrigation_start", "irrigation_continue"})
BOUND_ACTION_KEYS = ("authorization_digest", "commissioned_path_id", "zone_id",
    "bounded_duration_seconds", "evidence_generation", "job_id", "job_sha256",
    "segment_identity", "current_segment", "execution_id", "eligibility_sha256",
    "consumption_key")


def create_family_rootline_preview(*, parsed, principal, capability, replay_identity,
                                   connect_factory=None):
    action = parsed.get("family_action") if isinstance(parsed.get("family_action"), Mapping) else {}
    if capability not in ALLOWED_ACTIONS or any(action.get(key) in (None, "") for key in BOUND_ACTION_KEYS):
        return _hold("family_rootline_preview_incomplete")
    payload = {"contract_version": PREVIEW_CONTRACT,
        "actor_user_id": principal.telegram_user_id, "private_chat_id": principal.private_chat_id,
        "family_key": principal.family_key, "role": principal.role.value,
        "authorization_id": principal.authorization_id,
        "family_binding_digest": principal.binding_digest, "language": principal.language,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "allowed_action": capability, "callback_replay_identity": replay_identity,
        "owner_authority": False, "excluded_authority": ["autonomy_configuration",
            "borehole", "commissioning", "electrical", "fertilizer",
            "unapproved_upstream_shared_control"],
        **{key: action.get(key) for key in BOUND_ACTION_KEYS}}
    if (payload["family_key"] != "dad" or payload["role"] != "farm_manager"
            or payload["language"] != "af" or payload["actor_user_id"] != payload["private_chat_id"]):
        return _hold("family_rootline_preview_principal_invalid")
    digest = canonical_preview_digest(ACTION_KIND, payload)
    mission_id = MISSION_PREFIX + digest[:24].upper()
    try:
        claim = create_claim(action_kind=ACTION_KIND, owner_user_id=payload["actor_user_id"],
            private_chat_id=payload["private_chat_id"], mission_id=mission_id,
            provider_message_id=payload["provider_message_id"],
            evidence_generation=str(payload["evidence_generation"]), preview_payload=payload,
            ttl_minutes=30, connect_factory=connect_factory, supersede_active=False)
    except Exception:
        return _hold("family_rootline_preview_persistence_unavailable")
    token = str(claim.get("callback_token") or "")
    verb = "Begin veilig" if capability == "irrigation_start" else "Gaan veilig voort"
    return {**claim, "success": True, "status": "family_rootline_preview_ready",
        "mission_id": mission_id, "preview_payload": payload,
        "answer": ("<b>ROOTLINE-besluit</b>\n\nHierdie begrensde besproeiingsbesluit is gereed "
                   "vir ROOTLINE se finale gesag-, bewys- en veiligheidskontrole. "
                   "Niks is uit hierdie besluit uitgevoer nie."),
        "reply_markup": {"inline_keyboard": [[
            {"text": verb, "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
            {"text": "Kanselleer", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"}]]},
        "writes_farm_data": False, "hardware_commands": 0,
        "protected_actions_performed": False}


def prepare_family_rootline_preview(*, parsed, principal, capability, replay_identity,
        authorization_loader=None, eligibility_loader=None, connect_factory=None, environ=None):
    """Derive a preview only from current ROOTLINE truth after family authorization."""
    if capability not in ALLOWED_ACTIONS or isinstance(parsed.get("family_action"), Mapping):
        return _hold("family_rootline_preview_selector_invalid")
    from modules.telemetry.rootline_delegated_principal import load_delegated_authorization
    from modules.telemetry.rootline_execution_authority import validate_execution_eligibility
    source = environ if environ is not None else os.environ
    authorization_loader = authorization_loader or (
        lambda identity: load_delegated_authorization(identity, environ=source))
    if eligibility_loader is None:
        from modules.oom_sakkie.family_specialist_adapters import _load_rootline_eligibility
        eligibility_loader = lambda: _load_rootline_eligibility(source)
    try: authorization = authorization_loader(principal.authorization_id)
    except Exception: authorization = None
    if (not isinstance(authorization, Mapping) or authorization.get("active") is not True
            or authorization.get("revoked_at") not in (None, "")
            or authorization.get("owner_authority") is not False
            or str(authorization.get("principal_id") or "") != principal.telegram_user_id
            or str(authorization.get("private_chat_id") or "") != principal.private_chat_id
            or authorization.get("role") != "farm_manager"
            or "routine_irrigation_execute" not in (authorization.get("capabilities") or [])):
        return _hold("family_rootline_preview_authorization_unavailable")
    try: eligibility = validate_execution_eligibility(eligibility_loader())
    except Exception: eligibility = None
    if not isinstance(eligibility, Mapping) or eligibility.get("status") != "execution_eligible":
        return _hold("family_rootline_preview_evidence_unavailable")
    path = str(eligibility.get("commissioned_path_id") or eligibility.get("zone_id") or "")
    zone = str(eligibility.get("zone_id") or "")
    if (zone not in (authorization.get("zones") or [])
            or path not in (authorization.get("commissioned_paths") or [])):
        return _hold("family_rootline_preview_scope_changed")
    action = {"capability": capability, "decision_id": replay_identity,
        "authorization_digest": str(authorization.get("authorization_digest") or ""),
        "commissioned_path_id": path, "zone_id": zone,
        "bounded_duration_seconds": eligibility.get("maximum_duration_seconds"),
        "evidence_generation": eligibility.get("plan_generation"),
        **{key: eligibility.get(key) for key in ("job_id", "job_sha256", "segment_identity",
            "current_segment", "execution_id", "eligibility_sha256", "consumption_key")}}
    return create_family_rootline_preview(parsed={**dict(parsed), "family_action": action},
        principal=principal, capability=capability, replay_identity=replay_identity,
        connect_factory=connect_factory)


def bind_family_rootline_preview_card(result, delivery, *, connect_factory=None):
    token, message_id = str(result.get("callback_token") or ""), str(
        delivery.get("provider_message_id") or delivery.get("telegram_message_id") or "")
    return bool(token and message_id and bind_claim_card(token, message_id,
                                                        connect_factory=connect_factory))


def handle_family_rootline_callback(parsed, principal, *, callback_data,
        rootline_adapter, replay_store, connect_factory=None):
    claimed, status = _claim(callback_data, parsed, principal, connect_factory=connect_factory)
    if claimed.get("execute") is not True:
        return claimed, status
    payload = claimed["preview_payload"]
    reconstructed = {**dict(parsed), "text": "", "reply_to_message_id": "", "family_action": {
        "capability": payload["allowed_action"], "decision_id": claimed["callback_token"],
        "confirmed_callback": True,
        **{key: payload[key] for key in BOUND_ACTION_KEYS}}}
    from modules.oom_sakkie.family_runtime import handle_family_runtime_message
    result, result_status = handle_family_runtime_message(reconstructed, principal,
        rootline_adapter=rootline_adapter, replay_store=replay_store)
    durable = {"success": result.get("success") is True,
        "status": str(result.get("status") or "family_rootline_callback_contained"),
        "rootline_outcome_sha256": str(result.get("rootline_outcome_sha256") or ""),
        "hardware_commands": int(result.get("hardware_commands") or 0),
        "writes_farm_data": False, "provider_control_calls": int(result.get("provider_control_calls") or 0)}
    try:
        if durable["success"]: complete_claim(claimed["callback_token"], durable, connect_factory=connect_factory)
        else: contain_claim(claimed["callback_token"], durable, connect_factory=connect_factory)
    except Exception:
        return {"success": False, "status": "family_rootline_terminal_persistence_ambiguous",
            "answer": ("ROOTLINE se uitvoeruitkoms is onseker en is vir handmatige eienaarshersiening "
                       "behou. Die aksie sal nie outomaties herhaal word nie."),
            "hardware_commands": durable["hardware_commands"],
            "provider_control_calls": durable["provider_control_calls"],
            "provider_outcome_ambiguous": True, "writes_farm_data": False,
            "protected_actions_performed": False, "suppress_automatic_retry": True}, 503
    return {**result, "callback_token": claimed["callback_token"],
        "suppress_family_delivery": False}, result_status


def _claim(callback_data, parsed, principal, *, connect_factory=None):
    data = str(callback_data or "")
    if not data.startswith(CALLBACK_PREFIX) or data.count(":") != 2:
        return _hold("family_rootline_callback_invalid"), 400
    _, token, selected = data.split(":")
    if selected not in {"confirm", "cancel"}: return _hold("family_rootline_callback_invalid"), 400
    try: observed = datetime.fromisoformat(str(parsed.get("provider_timestamp") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError): observed = None
    if not token or not str(parsed.get("provider_message_id") or "") or observed is None or observed.tzinfo is None:
        return _hold("family_rootline_callback_provider_identity_required"), 409
    try:
        with (connect_factory() if connect_factory else _connect()) as db:
            with db.cursor() as cur:
                cur.execute("""select action_kind,owner_user_id,private_chat_id,mission_id,
                  preview_digest,evidence_generation,preview_payload,status,expires_at,
                  result_payload,preview_card_message_id from app_private.oom_protected_action_claims
                  where callback_token=%s for update""", (token,))
                row = cur.fetchone()
                if not row: return _hold("family_rootline_callback_unknown"), 404
                if (row[0] != ACTION_KIND or str(row[1]) != principal.telegram_user_id
                        or str(row[2]) != principal.private_chat_id
                        or principal.role.value != "farm_manager" or principal.family_key != "dad"):
                    return _hold("family_rootline_callback_unauthorized"), 403
                payload = row[6] if isinstance(row[6], Mapping) else {}
                if not _payload_matches(payload, principal, row[4]):
                    return _hold("family_rootline_callback_binding_changed"), 409
                if not row[10] or str(row[10]) != str(parsed.get("reply_to_message_id") or ""):
                    return _hold("family_rootline_callback_card_mismatch"), 409
                if row[7] in {"completed", "contained", "cancelled", "expired"}:
                    return {**_hold("family_rootline_callback_replayed_noop"),
                        "success": True, "terminal_result": row[9],
                        "suppress_family_delivery": True}, 200
                if row[7] == "executing":
                    return {**_hold("family_rootline_callback_execution_ambiguous"),
                        "suppress_family_delivery": True}, 409
                if row[7] != "active" or row[8] <= datetime.now(timezone.utc):
                    cur.execute("update app_private.oom_protected_action_claims set status='expired' where callback_token=%s and status='active'", (token,))
                    return _hold("family_rootline_callback_expired"), 409
                if selected == "cancel":
                    cur.execute("update app_private.oom_protected_action_claims set status='cancelled', confirmation_provider_message_id=%s,confirmation_provider_timestamp=%s::timestamptz where callback_token=%s and status='active'", (str(parsed["provider_message_id"]), str(parsed["provider_timestamp"]), token))
                    return {**_hold("family_rootline_preview_cancelled"), "success": True}, 200
                cur.execute("update app_private.oom_protected_action_claims set status='executing',confirmation_provider_message_id=%s,confirmation_provider_timestamp=%s::timestamptz where callback_token=%s and status='active'", (str(parsed["provider_message_id"]), str(parsed["provider_timestamp"]), token))
                if cur.rowcount != 1: return _hold("family_rootline_callback_contended"), 409
                return {"success": True, "execute": True, "callback_token": token,
                    "preview_payload": dict(payload)}, 200
    except Exception:
        return _hold("family_rootline_callback_store_unavailable"), 503


def _payload_matches(payload, principal, digest):
    return (payload.get("contract_version") == PREVIEW_CONTRACT
        and payload.get("actor_user_id") == principal.telegram_user_id
        and payload.get("private_chat_id") == principal.private_chat_id
        and payload.get("family_key") == principal.family_key
        and payload.get("role") == principal.role.value
        and payload.get("authorization_id") == principal.authorization_id
        and payload.get("family_binding_digest") == principal.binding_digest
        and payload.get("language") == principal.language
        and payload.get("allowed_action") in ALLOWED_ACTIONS
        and payload.get("owner_authority") is False
        and canonical_preview_digest(ACTION_KIND, payload) == digest)


def _connect():
    import psycopg
    return psycopg.connect(os.environ.get("DATABASE_URL"), connect_timeout=5)


def _hold(status):
    return {"success": False, "status": status,
        "answer": "ROOTLINE hou die besluit veilig terug. Niks is verander of uitgevoer nie.",
        "writes_farm_data": False, "hardware_commands": 0,
        "protected_actions_performed": False}
