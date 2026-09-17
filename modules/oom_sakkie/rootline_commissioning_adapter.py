"""Read-only deployed ROOTLINE acceptance for supervised commissioning presence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os

from modules.oom_sakkie.specialist_owner_decisions import (
    ROOTLINE_COMMISSIONING_ID, ROOTLINE_DECISION_ARTIFACT_SHA256, ROOTLINE_RELEASE_SHA256,
    validate_specialist_binding,
)

CONTRACT_VERSION = "rootline_commissioning_continuation_adapter_v1"
AVAILABILITY_RELEASE_SHA256 = "66bbb770a306df5123b350a29885b961f3295503a753eb26fdf8024bcef90ed8"
ROOTLINE_DECISION_TELEGRAM_MESSAGE_ID = "3176"


def accept_supervised_commissioning_presence(context=None, *, connect_factory=None, evidence_loader=None, now=None):
    """Accept presence only for read-only configuration discovery; never actuate."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        evidence = (evidence_loader or _load_authorization_evidence)(connect_factory)
        _validate_authorization(evidence, context or {}, now)
    except Exception:
        return _result(False, "rootline_authorization_evidence_invalid", now, {})
    return _result(True, "rootline_presence_accepted_for_read_only_configuration_discovery", now, evidence)


def _result(success, status, now, proven):
    evidence = {"commissioning_identity": ROOTLINE_COMMISSIONING_ID,
        "decision_artifact_sha256": ROOTLINE_DECISION_ARTIFACT_SHA256,
        "availability_release_sha256": AVAILABILITY_RELEASE_SHA256,
        "authorization_receipt_id": str((proven.get("receipt") or {}).get("receipt_id") or ""),
        "authorization_count": 1 if success else 0, "observed_at": now.isoformat()}
    return {"success": success, "status": status, "contract_version": CONTRACT_VERSION,
        "specialist_acceptance": success, "authorization_current": success,
        "writes_performed": False, "evidence_cutoff": now.isoformat(),
        "evidence_digest": hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "evidence": evidence, "authority": {"hardware_control": False,
            "configuration_write": False, "telegram_send": False},
        "next_state": "waiting_for_supervised_configuration_discovery" if success else "contained",
        "hardware_commands": 0}


def _load_authorization_evidence(connect_factory):
    if connect_factory is None:
        import psycopg
        connection = psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)
    else:
        connection = connect_factory()
    with connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'owner_attention',review_json->'owner_card'
                from public.sam_live_stock_conversation_review_events
                where event_source='sam_live_stock_owner_card_lifecycle'
                  and review_json->'owner_attention'->'item'->>'external_decision_identity'=%s
                  and review_json->'owner_card'->>'state'='active'""", (ROOTLINE_COMMISSIONING_ID,))
            cards = cursor.fetchall()
            cursor.execute("""select review_json->'owner_attention_receipt',review_json->'specialist_outcome_callback'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_owner_attention_queue'
                  and review_json->'owner_attention_receipt'->>'deterministic_identity'=%s""", (ROOTLINE_COMMISSIONING_ID,))
            receipts = cursor.fetchall()
            cursor.execute("""select review_json->'owner_attention_resolution'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_owner_attention_queue'
                  and review_json->'owner_attention_resolution'->>'deterministic_identity'=%s""", (ROOTLINE_COMMISSIONING_ID,))
            resolutions = cursor.fetchall()
    if len(cards) != 1 or len(receipts) != 1 or len(resolutions) != 1:
        raise ValueError("rootline_authorization_chronology_not_unique")
    return {"owner_attention": cards[0][0], "owner_card": cards[0][1],
        "receipt": receipts[0][0], "callback": receipts[0][1], "resolution": resolutions[0][0]}


def _validate_authorization(value, context, now):
    if not isinstance(value, dict): raise ValueError("authorization_mapping_required")
    attention=value.get("owner_attention") or {}; item=attention.get("item") or {}
    binding=item.get("specialist_binding") or {}; valid=validate_specialist_binding(binding)
    evidence=valid.get("evidence_binding") or {}
    receipt=value.get("receipt") or {}; callback=value.get("callback") or {}; resolution=value.get("resolution") or {}
    owner=str(context.get("owner_user_id") or ""); chat=str(context.get("chat_id") or "")
    expected_actor=_digest({"telegram_owner_id":owner}) if owner and owner==chat else ""
    replay=_digest({"card_digest":valid.get("binding_digest"),"choice":"authorize","actor_identity_hash":expected_actor})
    expires=datetime.fromisoformat(str(valid.get("expires_at") or "").replace("Z","+00:00"))
    required = (
        item.get("external_decision_identity")==ROOTLINE_COMMISSIONING_ID,
        valid.get("deterministic_identity")==ROOTLINE_COMMISSIONING_ID,
        valid.get("decision_token")==receipt.get("decision_id")==resolution.get("decision_id"),
        valid.get("binding_digest")==binding.get("binding_digest")==item.get("card_digest")==receipt.get("card_digest"),
        evidence.get("decision_artifact_sha256")==ROOTLINE_DECISION_ARTIFACT_SHA256,
        evidence.get("rootline_release_sha256")==ROOTLINE_RELEASE_SHA256,
        evidence.get("irrigation_authority") is False and evidence.get("hardware_action_performed") is False,
        receipt.get("status")=="consumed" and receipt.get("choice_id")=="authorize",
        attention.get("expected_owner_identity_hash")==expected_actor and len(expected_actor)==64,
        receipt.get("actor_identity_hash")==expected_actor and len(expected_actor)==64,
        receipt.get("replay_key")==replay and receipt.get("receipt_id")=="OOMAQ-RECEIPT-"+replay[:24],
        callback.get("deterministic_identity")==ROOTLINE_COMMISSIONING_ID,
        callback.get("outcome_code")=="supervised_commissioning_authorized",
        callback.get("specialist_callback")=="prepare_supervised_commissioning_handover",
        resolution.get("receipt_id")==receipt.get("receipt_id") and resolution.get("state")=="resolved",
        resolution.get("deterministic_identity")==ROOTLINE_COMMISSIONING_ID,
        str(value.get("owner_card",{}).get("telegram_chat_id") or "")==str(resolution.get("telegram_chat_id") or "")==chat,
        str(value.get("owner_card",{}).get("telegram_message_id") or "")==str(resolution.get("telegram_message_id") or "")==ROOTLINE_DECISION_TELEGRAM_MESSAGE_ID,
        expires.tzinfo is not None and expires.astimezone(timezone.utc)>now,
    )
    if not all(required): raise ValueError("rootline_authorization_binding_invalid")


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
