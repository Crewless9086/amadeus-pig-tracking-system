"""Recoverable delivery state machine for canonical protected-action claims.

The claim row remains the action spine.  This module grants no domain or
hardware authority; it only serializes delivery of the already-reviewed card.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import uuid
from typing import Callable, Mapping

CONTRACT_VERSION = "oom_protected_delivery.v1"
TERMINAL = frozenset({"completed", "contained", "cancelled", "expired", "changed"})


def recover_protected_card(*, callback_token: str, preview_digest: str,
                           owner_user_id: str, private_chat_id: str,
                           action_kind: str, deliver: Callable[..., Mapping],
                           connect_factory=None, defer_attempt=False,
                           deadline_monotonic=None) -> dict:
    """Send/bind at most once, or durably contain an ambiguous provider call.

    With defer_attempt, deliver receives a gate called after preparation and
    before its first journal/provider effect. A committed compare-and-set then
    owns the provider attempt before network I/O.
    Concurrent schedulers observe that marker; process loss leaves it durable
    and restart treats it as ambiguous instead of sending again.
    """
    factory = connect_factory or _connect
    binding = dict(callback_token=callback_token, preview_digest=preview_digest,
        owner_user_id=owner_user_id, private_chat_id=private_chat_id,
        action_kind=action_kind, factory=factory, deadline_monotonic=deadline_monotonic)
    owned = None
    gate_result = None

    def begin_attempt():
        nonlocal owned, gate_result
        # A callback may cross this boundary once. A late/concurrent caller must
        # reacquire the same canonical claim and cannot inherit another's send.
        if owned is not None or gate_result is not None:
            return _safe("protected_delivery_gate_already_used")
        value = _claim_delivery(**binding, start_attempt=True)
        if value.get("attempt_owned") is True:
            owned = value["attempt_id"]
            return None
        gate_result = value
        return value

    if defer_attempt:
        prior = _claim_delivery(**binding, start_attempt=False)
        if prior is not None:
            return prior
    else:
        denied = begin_attempt()
        if denied is not None:
            return denied
    try:
        result = dict((deliver(begin_attempt) if defer_attempt else deliver()) or {})
    except Exception:
        if owned is None:
            return {**_safe("protected_delivery_preparation_unavailable"),
                "success": False, "delivery_definitely_not_sent": True}
        result = {}
    if owned is None:
        # Preparation never acquired effect ownership. It cannot have called the
        # provider through this path, and must not turn a timeout into ambiguity.
        return gate_result if gate_result is not None else result
    attempt_id = owned
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


def _claim_delivery(*, callback_token, preview_digest, owner_user_id, private_chat_id,
                    action_kind, factory, start_attempt, deadline_monotonic):
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
        now = datetime.now(timezone.utc)  # Fresh after bounded connect/row-lock wait.
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
        if not start_attempt:
            return None
        from modules.oom_sakkie.family_message_lifecycle import _provider_deadline_available
        if not _provider_deadline_available(deadline_monotonic):
            return {**_safe("family_message_cycle_deadline_deferred"),
                "success": False, "delivery_definitely_not_sent": True}
        # A future explicitly audited correction cannot let an old finalizer
        # match a new attempt for the same claim and preview.
        attempt_id = _attempt_identity(callback_token, preview_digest, nonce=uuid.uuid4().hex)
        cur.execute("""update app_private.oom_protected_action_claims
          set delivery_state='delivery_pending',delivery_attempt_id=%s,
              delivery_attempted_at=now() where callback_token=%s and status='active'
          and preview_card_message_id is null and coalesce(delivery_state,'claim_created')='claim_created'""",
          (attempt_id, callback_token))
        if cur.rowcount != 1:
            return _safe("protected_delivery_claim_not_owned")
    return {"attempt_owned": True, "attempt_id": attempt_id}


def _attempt_identity(token, digest, *, nonce=None):
    import hashlib
    material = f"{CONTRACT_VERSION}|{token}|{digest}"
    if nonce is not None:
        material += "|attempt-v2|" + nonce
    return hashlib.sha256(material.encode()).hexdigest()


def _bounded(result):
    return {key: result.get(key) for key in
        ("success", "status", "telegram_message_id", "telegram_sends", "telegram_edits",
         "delivery_definitely_not_sent", "provider_delivery_confirmed")}


def _safe(status):
    return {"success": True, "status": status, "telegram_sends": 0,
        "telegram_edits": 0, "hardware_commands": 0, "provider_control_calls": 0,
        "writes_farm_data": False}


def _connect():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    return connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"), read_only=False)
