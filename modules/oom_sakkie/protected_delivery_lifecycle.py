"""Recoverable delivery state machine for canonical protected-action claims.

The claim row remains the action spine.  This module grants no domain or
hardware authority; it only serializes delivery of the already-reviewed card.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Callable, Mapping

CONTRACT_VERSION = "oom_protected_delivery.v1"
TERMINAL = frozenset({"completed", "contained", "cancelled", "expired", "changed"})


def recover_protected_card(*, callback_token: str, preview_digest: str,
                           owner_user_id: str, private_chat_id: str,
                           action_kind: str, deliver: Callable[[], Mapping],
                           connect_factory=None) -> dict:
    """Send/bind at most once, or durably contain an ambiguous provider call.

    A committed compare-and-set owns the provider attempt before network I/O.
    Concurrent schedulers observe that marker; process loss leaves it durable
    and restart treats it as ambiguous instead of sending again.
    """
    now = datetime.now(timezone.utc)
    factory = connect_factory or _connect
    # Phase one commits ownership before crossing the provider boundary.  A
    # worker loss after provider acceptance therefore leaves a durable pending
    # marker which restart contains instead of resending.
    with factory() as db:
      with db.cursor() as cur:
        cur.execute("""select status,expires_at,preview_card_message_id,preview_digest,
          owner_user_id,private_chat_id,action_kind,delivery_state,delivery_attempt_id,
          delivery_attempted_at
          from app_private.oom_protected_action_claims where callback_token=%s for update""",
          (str(callback_token),))
        row = cur.fetchone()
        if not row:
            return _safe("protected_delivery_claim_missing")
        status, expires, card, digest, owner, chat, kind, state, attempt_id, attempted_at = row
        if (str(digest) != str(preview_digest) or str(owner) != str(owner_user_id)
                or str(chat) != str(private_chat_id) or str(kind) != str(action_kind)):
            return _safe("protected_delivery_binding_mismatch")
        if status in TERMINAL or expires <= now:
            if status == "active" and expires <= now:
                cur.execute("""update app_private.oom_protected_action_claims
                  set status='expired',delivery_state='expired'
                  where callback_token=%s and status='active'""", (callback_token,))
            return _safe("protected_delivery_terminal_noop")
        if card:
            return {**_safe("protected_delivery_replayed_noop"),
                "provider_card_message_id": str(card), "delivery_confirmed": True}
        if state in {"delivery_pending", "provider_accepted", "delivery_ambiguous"}:
            if (state == "delivery_pending" and attempted_at
                    and (now - attempted_at).total_seconds() < 30):
                return _safe("protected_delivery_in_progress")
            cur.execute("""update app_private.oom_protected_action_claims
              set delivery_state='delivery_ambiguous',delivery_ambiguous_at=coalesce(delivery_ambiguous_at,now())
              where callback_token=%s""", (callback_token,))
            return {**_safe("protected_delivery_ambiguous"),
                "success": False, "provider_outcome_ambiguous": True,
                "do_not_retry_provider_effect": True}
        attempt_id = _attempt_identity(callback_token, preview_digest)
        cur.execute("""update app_private.oom_protected_action_claims
          set delivery_state='delivery_pending',delivery_attempt_id=%s,
              delivery_attempted_at=now() where callback_token=%s and status='active'
          and preview_card_message_id is null and coalesce(delivery_state,'claim_created')='claim_created'""",
          (attempt_id, callback_token))
        if cur.rowcount != 1:
            return _safe("protected_delivery_claim_not_owned")
    try:
        result = dict(deliver() or {})
    except Exception:
        result = {}
    with factory() as db:
      with db.cursor() as cur:
        cur.execute("""select delivery_state,delivery_attempt_id,preview_card_message_id
          from app_private.oom_protected_action_claims where callback_token=%s for update""",
          (str(callback_token),))
        final = cur.fetchone()
        if (not final or final[0] != "delivery_pending"
                or str(final[1] or "") != attempt_id or final[2]):
            return {**_safe("protected_delivery_binding_ambiguous"), "success": False,
                "provider_outcome_ambiguous": True, "do_not_retry_provider_effect": True}
        message_id = str(result.get("telegram_message_id") or "")
        accepted = result.get("success") is True and bool(message_id)
        if not accepted:
            cur.execute("""update app_private.oom_protected_action_claims
              set delivery_state='delivery_ambiguous',delivery_ambiguous_at=now(),
                  delivery_result=%s::jsonb where callback_token=%s""",
              (json.dumps(_bounded(result)), callback_token))
            return {**_safe("protected_delivery_ambiguous"), "success": False,
                "provider_outcome_ambiguous": True, "do_not_retry_provider_effect": True}
        cur.execute("""update app_private.oom_protected_action_claims
          set delivery_state='delivery_confirmed',provider_accepted_at=now(),
              delivery_confirmed_at=now(),preview_card_message_id=%s,
              delivery_result=%s::jsonb where callback_token=%s
              and delivery_attempt_id=%s and preview_card_message_id is null""",
          (message_id, json.dumps(_bounded(result)), callback_token, attempt_id))
        if cur.rowcount != 1:
            return {**_safe("protected_delivery_binding_ambiguous"), "success": False,
                "provider_outcome_ambiguous": True, "do_not_retry_provider_effect": True}
    return {**result, "status": "protected_delivery_confirmed",
        "protected_preview_card_bound": True, "delivery_confirmed": True}


def _attempt_identity(token, digest):
    import hashlib
    return hashlib.sha256(f"{CONTRACT_VERSION}|{token}|{digest}".encode()).hexdigest()


def _bounded(result):
    return {key: result.get(key) for key in
        ("success", "status", "telegram_message_id", "telegram_sends", "telegram_edits")}


def _safe(status):
    return {"success": True, "status": status, "telegram_sends": 0,
        "telegram_edits": 0, "hardware_commands": 0, "provider_control_calls": 0,
        "writes_farm_data": False}


def _connect():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    return connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"), read_only=False)
