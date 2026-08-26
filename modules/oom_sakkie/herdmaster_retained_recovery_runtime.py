"""Preview-only bridge from durable manager cases to existing protected rails."""
from __future__ import annotations

import hashlib

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority


def build_retained_protected_preview(case):
    refs = tuple(str(value) for value in (case or {}).get("evidence_refs") or ())
    provider_ids = tuple(sorted({value.split(":", 1)[1] for value in refs
                                 if value.startswith("provider_message:") and ":" in value}))
    if not provider_ids:
        return _contained("retained_provider_identity_missing")
    if "litter-loss" in str((case or {}).get("dedupe_key") or ""):
        # The canonical litter-loss protected claim adapter is not yet wired;
        # never substitute sow-health or a generic manager card.
        return _contained("retained_litter_loss_protected_adapter_unavailable")
    if "expired-farrowing" in str((case or {}).get("dedupe_key") or ""):
        return _farrowing(provider_ids, str((case or {}).get("evidence_digest") or ""))
    if "retained-mortality" in str((case or {}).get("dedupe_key") or ""):
        return _mortality(provider_ids)
    return _contained("retained_recovery_case_kind_unsupported")


def _farrowing(provider_ids, recovery_identity):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select owner_user_id,private_chat_id,provider_message_id,preview_payload
                from app_private.oom_protected_action_claims
                where action_kind='herdmaster_record_farrowing_litter'
                  and provider_message_id=any(%s) order by created_at desc limit 1""",
                (list(provider_ids),))
            row = cur.fetchone()
    if not row or str(row[0] or "") != str(row[1] or ""):
        return _contained("retained_farrowing_principal_unproven")
    owner, chat, provider, preview = str(row[0]), str(row[1]), str(row[2]), dict(row[3] or {})
    counts = dict(preview.get("counts") or {})
    parsed = {"telegram_user_id": owner, "telegram_chat_id": chat,
        "provider_message_id": provider, "output_language": preview.get("language") or "af",
        "semantic": {"intent": "record_farrowing_litter",
            "language": preview.get("language") or "af", "farrowing_litter": {
                "sow_ref": preview.get("sow_pig_id"),
                "farrowing_date": preview.get("farrowing_date"),
                "total_born": counts.get("total_born"), "born_alive": counts.get("born_alive"),
                "stillborn": counts.get("stillborn"), "mummified": counts.get("mummified"),
                "mating_ref": preview.get("requested_mating_ref"),
                "father_ref": preview.get("requested_father_ref")}}}
    from modules.oom_sakkie.herdmaster_farrowing_runtime import handle_farrowing_litter_message
    from modules.oom_sakkie.protected_action_claims import create_claim
    recovery_suffix = hashlib.sha256(
        (recovery_identity + "|" + provider).encode()).hexdigest()[:12].upper()
    created = {}
    def recovery_claim(**kwargs):
        created["mission_id"] = str(kwargs["mission_id"]) + "-RECOVERY-" + recovery_suffix
        return create_claim(**{**kwargs, "mission_id": created["mission_id"]})
    result, _status = handle_farrowing_litter_message(
        parsed, issue_gateway_owner_authority(owner, chat), claim_creator=recovery_claim)
    if created.get("mission_id") and result.get("callback_token"):
        result = {**result, "mission_id": created["mission_id"],
                  "card_mission_id": created["mission_id"]}
    return _protected(result)


def _mortality(provider_ids):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_json->'herdmaster_health_loss'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_herdmaster_health_loss_runtime'
                  and review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
                order by created_at desc limit 1""", (list(provider_ids),))
            row = cur.fetchone()
    payload = dict(row[0] or {}) if row and isinstance(row[0], dict) else {}
    owner, chat = str(payload.get("owner_user_id") or ""), str(payload.get("chat_id") or "")
    if not owner or owner != chat:
        return _contained("retained_mortality_principal_unproven")
    parsed = {"telegram_user_id": owner, "telegram_chat_id": chat,
        "provider_message_id": str(payload.get("provider_message_id") or ""),
        "provider_timestamp": str(payload.get("provider_timestamp") or ""),
        "output_language": payload.get("output_language") or "af",
        "text": str(payload.get("owner_text_verbatim") or ""),
        "semantic": dict(payload.get("semantic_interpretation") or {})}
    from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_authenticated_health_loss_message
    result, _status = handle_authenticated_health_loss_message(
        parsed, issue_gateway_owner_authority(owner, chat))
    return _protected(result)


def _protected(result):
    value = dict(result or {})
    if value.get("success") is True and value.get("callback_token"):
        return {**value, "confirmation_required": True, "writes_farm_data": False}
    return _contained(str(value.get("status") or "retained_protected_repreview_unproven"))


def _contained(status):
    return {"success": False, "status": status, "suppress_owner_delivery": True,
            "telegram_sends": 0, "writes_farm_data": False, "recovery_required": True}
