"""Durable Supabase state for the private CHARLIE owner interface."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from modules.charlie.mission_store import _connect, _database_url


def stable_id(prefix, *parts):
    raw = ":".join(str(part or "") for part in parts).encode("utf-8")
    return f"{prefix}-" + hashlib.sha256(raw).hexdigest()[:20].upper()


def claim_update(update_id, callback_id="", database_url=None, connect_factory=None):
    update_id = str(update_id or "").strip()
    if not update_id:
        return {"success": False, "status": "update_id_required"}, 400
    update_key = stable_id("UPDATE", update_id)
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_inbound_updates(update_key, telegram_update_id, callback_query_id)
                    values (%(key)s, %(update)s, nullif(%(callback)s, ''))
                    on conflict do nothing returning update_key
                """, {"key": update_key, "update": update_id, "callback": callback_id})
                created = bool(cursor.fetchall())
                cursor.execute("""
                    select update_key, telegram_update_id, status, result_json, received_at, completed_at
                    from public.charlie_inbound_updates
                    where telegram_update_id=%(update)s or update_key=%(key)s
                    order by case when telegram_update_id=%(update)s then 0 else 1 end
                    limit 1
                """, {"update": update_id, "key": update_key})
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "update_claim_failed", "error_type": exc.__class__.__name__}, 503
    if not row:
        return {"success": False, "status": "update_claim_readback_missing"}, 503
    if str(row[1]) != update_id:
        return {
            "success": False,
            "status": "update_key_collision",
            "created": False,
            "update_key": update_key,
        }, 409
    return {
        "success": True,
        "status": "claimed" if created else "duplicate",
        "created": created,
        "update_key": str(row[0]),
        "existing_status": str(row[2] or ""),
        "existing_result": dict(row[3] or {}),
        "received_at": row[4].isoformat() if row[4] else "",
        "completed_at": row[5].isoformat() if row[5] else "",
    }, 201 if created else 200


def reconcile_incomplete_update(update_key, *, minimum_age_seconds=30, database_url=None, connect_factory=None):
    """Close an abandoned callback claim without replaying its owner action."""
    minimum_age_seconds = max(1, min(int(minimum_age_seconds or 30), 3600))
    result = {
        "status": "completion_unknown_replay_refused",
        "reason": "The callback audit completion failed; the owner action was not replayed.",
    }
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_inbound_updates
                    set status='failed', result_json=%(result)s::jsonb, completed_at=now()
                    where update_key=%(key)s and status='processing'
                      and received_at <= now() - make_interval(secs => %(age)s)
                    returning status, result_json, completed_at
                """, {"key": update_key, "age": minimum_age_seconds, "result": json.dumps(result)})
                row = cursor.fetchone()
                if row:
                    return {
                        "success": True,
                        "status": "incomplete_update_reconciled",
                        "reconciled": True,
                        "terminal_status": str(row[0]),
                        "result": dict(row[1] or {}),
                        "completed_at": row[2].isoformat() if row[2] else "",
                    }, 200
                cursor.execute("""
                    select status, result_json, completed_at
                    from public.charlie_inbound_updates where update_key=%(key)s
                """, {"key": update_key})
                existing = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "update_reconciliation_failed", "error_type": exc.__class__.__name__}, 503
    if not existing:
        return {"success": False, "status": "update_not_found", "reconciled": False}, 404
    return {
        "success": True,
        "status": "update_still_processing" if existing[0] == "processing" else "update_already_terminal",
        "reconciled": False,
        "terminal_status": str(existing[0] or ""),
        "result": dict(existing[1] or {}),
        "completed_at": existing[2].isoformat() if existing[2] else "",
    }, 202 if existing[0] == "processing" else 200


def complete_update(update_key, *, status="processed", result=None, database_url=None, connect_factory=None):
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_inbound_updates set status=%(status)s, result_json=%(result)s::jsonb, completed_at=now()
                    where update_key=%(key)s returning update_key
                """, {"status": status, "result": json.dumps(result or {}), "key": update_key})
                found = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "update_complete_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": found, "status": "ok" if found else "not_found"}, 200 if found else 404


def bind_owner(user_id, chat_id, *, metadata=None, database_url=None, connect_factory=None):
    binding_id = stable_id("OWNER", user_id, chat_id)
    thread_id = stable_id("THREAD", binding_id, "active")
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_owner_bindings(binding_id, telegram_user_id, telegram_chat_id, metadata_json)
                    values (%(binding)s,%(user)s,%(chat)s,%(metadata)s::jsonb)
                    on conflict (telegram_user_id) do update set telegram_chat_id=excluded.telegram_chat_id,
                        status='active', last_seen_at=now(), metadata_json=excluded.metadata_json
                    returning binding_id
                """, {"binding": binding_id, "user": str(user_id), "chat": str(chat_id), "metadata": json.dumps(metadata or {})})
                binding_id = cursor.fetchone()[0]
                cursor.execute("""
                    insert into public.charlie_conversation_threads(thread_id,binding_id)
                    values (%(thread)s,%(binding)s)
                    on conflict (binding_id,status) do update set updated_at=now()
                    returning thread_id
                """, {"thread": thread_id, "binding": binding_id})
                thread_id = cursor.fetchone()[0]
                cursor.execute("""
                    insert into public.charlie_brief_subscriptions(subscription_id,binding_id,brief_type,local_time)
                    values (%(id)s,%(binding)s,'morning','06:30') on conflict (binding_id,brief_type) do nothing
                """, {"id": stable_id("BRIEF", binding_id, "morning"), "binding": binding_id})
    except Exception as exc:
        return {"success": False, "status": "owner_binding_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "owner_bound", "binding_id": binding_id, "thread_id": thread_id, "telegram_user_id": str(user_id), "telegram_chat_id": str(chat_id)}, 200


def record_message(thread_id, role, content, *, update_id="", telegram_message_id="", media=None, metadata=None, database_url=None, connect_factory=None):
    message_id = stable_id("MSG", thread_id, role, update_id or datetime.now(timezone.utc).isoformat(), content)
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_conversation_messages
                        (message_id,thread_id,telegram_update_id,telegram_message_id,role,content,media_json,metadata_json)
                    values (%(id)s,%(thread)s,nullif(%(update)s,''),nullif(%(telegram)s,''),%(role)s,%(content)s,%(media)s::jsonb,%(metadata)s::jsonb)
                    on conflict (message_id) do nothing returning message_id
                """, {"id": message_id, "thread": thread_id, "update": str(update_id), "telegram": str(telegram_message_id), "role": role,
                      "content": str(content or "")[:12000], "media": json.dumps(media or []), "metadata": json.dumps(metadata or {})})
    except Exception as exc:
        return {"success": False, "status": "message_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "recorded", "message_id": message_id}, 201


def recent_context(thread_id, limit=12, database_url=None, connect_factory=None):
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select role,content,media_json,metadata_json,created_at from public.charlie_conversation_messages
                    where thread_id=%(thread)s order by created_at desc limit %(limit)s
                """, {"thread": thread_id, "limit": max(1, min(int(limit), 30))})
                rows = cursor.fetchall()
                cursor.execute("select summary,open_context_json from public.charlie_conversation_threads where thread_id=%(thread)s", {"thread": thread_id})
                thread = cursor.fetchone() or ("", {})
                cursor.execute("""
                    select preference_key,preference_value_json from public.charlie_owner_preferences
                    where status='approved' order by preference_key
                """)
                preferences = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as exc:
        return {"success": False, "status": "context_read_failed", "error_type": exc.__class__.__name__, "messages": []}, 503
    messages = [{"role": row[0], "content": row[1], "media": row[2] or [], "metadata": row[3] or {}, "created_at": row[4].isoformat()} for row in reversed(rows)]
    return {"success": True, "status": "ok", "summary": thread[0] or "", "open_context": thread[1] or {}, "preferences": preferences, "messages": messages}, 200


def update_thread_context(thread_id, context, *, summary="", database_url=None, connect_factory=None):
    """Persist the current executive goal, subject, plan, and follow-ups across restarts."""
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_conversation_threads
                    set open_context_json=%(context)s::jsonb,
                        summary=case when %(summary)s='' then summary else %(summary)s end,
                        updated_at=now()
                    where thread_id=%(thread)s returning thread_id
                """, {"thread": thread_id, "context": json.dumps(context or {}, default=str), "summary": str(summary or "")[:1000]})
                found = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "context_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": found, "status": "context_updated" if found else "thread_not_found"}, 200 if found else 404


def record_intent(thread_id, owner_message_id, intent, database_url=None, connect_factory=None):
    intent_id = stable_id("INTENT", owner_message_id, intent.get("type"), json.dumps(intent.get("args") or {}, sort_keys=True))
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_owner_intents(intent_id,thread_id,owner_message_id,intent_type,confidence,args_json,risk_flags_json,status)
                    values (%(id)s,%(thread)s,%(message)s,%(type)s,%(confidence)s,%(args)s::jsonb,%(risks)s::jsonb,%(status)s)
                    on conflict (intent_id) do nothing returning intent_id
                """, {"id": intent_id, "thread": thread_id, "message": owner_message_id, "type": intent.get("type"),
                      "confidence": float(intent.get("confidence") or 0), "args": json.dumps(intent.get("args") or {}),
                      "risks": json.dumps(intent.get("risk_flags") or []), "status": "clarification" if intent.get("type") == "clarify" else "planned"})
    except Exception as exc:
        return {"success": False, "status": "intent_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "recorded", "intent_id": intent_id}, 201


def record_tool_execution(intent_id, tool_name, authority_tier, args, result, *, status="succeeded", database_url=None, connect_factory=None):
    key = stable_id("TOOLKEY", intent_id, tool_name)
    execution_id = stable_id("EXEC", key)
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_tool_executions(execution_id,intent_id,idempotency_key,tool_name,authority_tier,status,args_json,result_json,completed_at)
                    values (%(id)s,%(intent)s,%(key)s,%(tool)s,%(tier)s,%(status)s,%(args)s::jsonb,%(result)s::jsonb,now())
                    on conflict (idempotency_key) do nothing returning execution_id
                """, {"id": execution_id, "intent": intent_id, "key": key, "tool": tool_name, "tier": authority_tier,
                      "status": status, "args": json.dumps(args or {}), "result": json.dumps(result or {}, default=str)})
                created = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "tool_execution_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "recorded" if created else "duplicate", "execution_id": execution_id, "created": created}, 201 if created else 200


def create_approval_bundle(thread_id, title, summary, decisions, recommendation, state_hash, *, hours=24, database_url=None, connect_factory=None):
    bundle_id = stable_id("BUNDLE", thread_id, state_hash, json.dumps(decisions, sort_keys=True))
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_approval_bundles(bundle_id,thread_id,title,summary,decisions_json,recommendation_json,state_hash,expires_at)
                    values (%(id)s,%(thread)s,%(title)s,%(summary)s,%(decisions)s::jsonb,%(recommendation)s::jsonb,%(hash)s,%(expires)s)
                    on conflict (bundle_id) do update set summary=excluded.summary,expires_at=excluded.expires_at
                    returning bundle_id
                """, {"id": bundle_id, "thread": thread_id, "title": title, "summary": summary,
                      "decisions": json.dumps(decisions), "recommendation": json.dumps(recommendation), "hash": state_hash, "expires": expires})
                cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "bundle_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "pending", "bundle_id": bundle_id, "expires_at": expires.isoformat()}, 201


def decide_bundle(bundle_id, decision, *, expected_state_hash="", database_url=None, connect_factory=None):
    status = {"approve": "approved", "reject": "rejected", "defer": "deferred"}.get(str(decision), "")
    if not status:
        return {"success": False, "status": "invalid_bundle_decision"}, 400
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_approval_bundles set status=%(status)s,decided_at=now()
                    where bundle_id=%(id)s and status='pending' and expires_at>now()
                      and (%(hash)s='' or state_hash=%(hash)s)
                    returning bundle_id,decisions_json,recommendation_json,state_hash
                """, {"status": status, "id": bundle_id, "hash": expected_state_hash})
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "bundle_decision_failed", "error_type": exc.__class__.__name__}, 503
    if not row:
        return {"success": False, "status": "bundle_stale_expired_or_decided"}, 409
    return {"success": True, "status": status, "bundle_id": row[0], "decisions": row[1] or [], "recommendation": row[2] or {}, "state_hash": row[3]}, 200


def remember_preference(key, value, source_message_id="", *, approved=False, database_url=None, connect_factory=None):
    key = str(key or "").strip()[:120]
    if not key or value in (None, ""):
        return {"success": False, "status": "preference_required"}, 400
    preference_id = stable_id("PREFERENCE", key)
    status = "approved" if approved else "proposed"
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_owner_preferences
                        (preference_id,preference_key,preference_value_json,status,source_message_id,approved_at)
                    values (%(id)s,%(key)s,%(value)s::jsonb,%(status)s,nullif(%(message)s,''),case when %(approved)s then now() end)
                    on conflict (preference_key) do update set preference_value_json=excluded.preference_value_json,
                        status=excluded.status,source_message_id=excluded.source_message_id,
                        approved_at=excluded.approved_at,updated_at=now()
                    returning preference_id
                """, {"id": preference_id, "key": key, "value": json.dumps(value), "status": status, "message": source_message_id, "approved": approved})
                cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "preference_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": status, "preference_id": preference_id}, 200


def private_owner_snapshot(limit=30, database_url=None, connect_factory=None):
    """Return the owner-facing private conversation, decisions, and learning evidence."""
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select b.binding_id,b.telegram_user_id,b.telegram_chat_id,b.last_seen_at,t.thread_id,t.summary,t.open_context_json
                    from public.charlie_owner_bindings b
                    left join public.charlie_conversation_threads t on t.binding_id=b.binding_id and t.status='active'
                    where b.status='active' order by b.last_seen_at desc limit 1
                """)
                owner = cursor.fetchone()
                messages = []
                if owner and owner[4]:
                    cursor.execute("""
                        select message_id,role,content,media_json,metadata_json,created_at
                        from public.charlie_conversation_messages where thread_id=%(thread)s
                        order by created_at desc limit %(limit)s
                    """, {"thread": owner[4], "limit": max(1, min(int(limit), 100))})
                    messages = cursor.fetchall()
                cursor.execute("""
                    select bundle_id,status,title,summary,decisions_json,recommendation_json,expires_at,created_at
                    from public.charlie_approval_bundles
                    where status in ('pending','deferred') and expires_at>now()
                    order by created_at desc limit 20
                """)
                bundles = cursor.fetchall()
                cursor.execute("select count(*),count(*) filter (where status='succeeded'),count(*) filter (where status='failed') from public.charlie_tool_executions")
                tool_counts = cursor.fetchone() or (0, 0, 0)
                cursor.execute("select count(*),count(*) filter (where status='clarification') from public.charlie_owner_intents")
                intent_counts = cursor.fetchone() or (0, 0)
                cursor.execute("select preference_key,preference_value_json,updated_at from public.charlie_owner_preferences where status='approved' order by updated_at desc limit 20")
                preferences = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "private_snapshot_failed", "error_type": exc.__class__.__name__}, 503
    return {
        "success": True,
        "status": "private_snapshot_ready",
        "owner": ({"binding_id": owner[0], "telegram_user_id": owner[1], "telegram_chat_id": owner[2], "last_seen_at": owner[3].isoformat(), "thread_id": owner[4], "summary": owner[5], "open_context": owner[6] or {}} if owner else None),
        "messages": [{"message_id": row[0], "role": row[1], "content": row[2], "media": row[3] or [], "metadata": row[4] or {}, "created_at": row[5].isoformat()} for row in reversed(messages)],
        "decisions": [{"bundle_id": row[0], "status": row[1], "title": row[2], "summary": row[3], "decisions": row[4] or [], "recommendation": row[5] or {}, "expires_at": row[6].isoformat(), "created_at": row[7].isoformat()} for row in bundles],
        "preferences": [{"key": row[0], "value": row[1], "updated_at": row[2].isoformat()} for row in preferences],
        "evaluation": {"tool_runs": tool_counts[0], "tool_successes": tool_counts[1], "tool_failures": tool_counts[2], "intents": intent_counts[0], "clarifications": intent_counts[1]},
    }, 200
