"""Executive brief scheduling and durable outbox preparation."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from modules.charlie.mission_store import _connect, _database_url
from modules.charlie.private_store import stable_id
from modules.charlie.private_executive import build_executive_plan, compose_executive_reply, run_executive_plan


def queue_due_private_briefs(*, now=None, database_url=None, connect_factory=None):
    now = now or datetime.now(ZoneInfo("Africa/Johannesburg"))
    queued = []
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select s.subscription_id,b.telegram_chat_id,s.brief_type,s.local_time,s.timezone
                    from public.charlie_brief_subscriptions s
                    join public.charlie_owner_bindings b on b.binding_id=s.binding_id
                    where s.enabled=true and b.status='active'
                      and (s.last_delivery_date is null or s.last_delivery_date < %(today)s)
                """, {"today": now.date()})
                subscriptions = cursor.fetchall()
                for subscription_id, chat_id, brief_type, local_time, timezone_name in subscriptions:
                    local_now = now.astimezone(ZoneInfo(str(timezone_name or "Africa/Johannesburg")))
                    if local_now.time().replace(tzinfo=None) < local_time:
                        continue
                    plan = build_executive_plan("Give me the morning brief", {"type": "executive_brief", "args": {}, "risk_flags": []}, {})
                    evidence = run_executive_plan(plan, f"BRIEF-{subscription_id}-{local_now.date().isoformat()}")
                    brief_text = compose_executive_reply(plan, evidence)
                    if not evidence or not evidence[0].get("success"):
                        continue
                    outbox_id = stable_id("PRIVATEBRIEF", subscription_id, local_now.date().isoformat())
                    payload = {"private_text": brief_text, "chat_id": str(chat_id), "brief_type": brief_type}
                    cursor.execute("""
                        insert into public.charlie_notification_outbox(outbox_id,idempotency_key,channel,recipient_key,event_type,payload_json)
                        values (%(id)s,%(id)s,'telegram','owner','private_executive_brief',%(payload)s::jsonb)
                        on conflict (outbox_id) do nothing returning outbox_id
                    """, {"id": outbox_id, "payload": json.dumps(payload)})
                    if cursor.fetchall():
                        cursor.execute("update public.charlie_brief_subscriptions set last_delivery_date=%(today)s where subscription_id=%(id)s", {"today": local_now.date(), "id": subscription_id})
                        queued.append(outbox_id)
    except Exception as exc:
        return {"success": False, "status": "private_brief_queue_failed", "error_type": exc.__class__.__name__, "queued": []}, 503
    return {"success": True, "status": "private_briefs_queued", "queued": queued}, 200


def queue_due_private_followups(*, now=None, database_url=None, connect_factory=None):
    now = now or datetime.now(ZoneInfo("UTC"))
    queued = []
    try:
        with _connect(_database_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select t.thread_id,b.telegram_chat_id,t.open_context_json
                    from public.charlie_conversation_threads t
                    join public.charlie_owner_bindings b on b.binding_id=t.binding_id
                    where t.status='active' and b.status='active'
                """)
                for thread_id, chat_id, raw_context in cursor.fetchall():
                    context = dict(raw_context or {})
                    pending = list(context.get("pending_follow_ups") or [])
                    changed = False
                    for item in pending:
                        if item.get("status") != "pending" or not _due(item.get("due_at"), now):
                            continue
                        follow_up_id = str(item.get("follow_up_id") or stable_id("FOLLOWUP", thread_id, item.get("request"), item.get("due_at")))
                        plan = build_executive_plan(item.get("request") or "Give me a CORE status", {"type": "read_core_status", "args": {}, "risk_flags": []}, {"open_context": context})
                        evidence = run_executive_plan(plan, follow_up_id)
                        text = "CHARLIE follow-up\n" + compose_executive_reply(plan, evidence)
                        cursor.execute("""
                            insert into public.charlie_notification_outbox(outbox_id,idempotency_key,channel,recipient_key,event_type,payload_json)
                            values (%(id)s,%(id)s,'telegram','owner','private_executive_follow_up',%(payload)s::jsonb)
                            on conflict (outbox_id) do nothing returning outbox_id
                        """, {"id": follow_up_id, "payload": json.dumps({"private_text": text, "chat_id": str(chat_id), "follow_up_id": follow_up_id})})
                        if cursor.fetchall():
                            queued.append(follow_up_id)
                        item["status"] = "queued"
                        item["completed_at"] = now.isoformat()
                        changed = True
                    if changed:
                        context["pending_follow_ups"] = pending[-20:]
                        context["stage"] = "follow_up_queued"
                        cursor.execute("update public.charlie_conversation_threads set open_context_json=%(context)s::jsonb,updated_at=now() where thread_id=%(thread)s", {"context": json.dumps(context), "thread": thread_id})
    except Exception as exc:
        return {"success": False, "status": "private_follow_up_queue_failed", "error_type": exc.__class__.__name__, "queued": []}, 503
    return {"success": True, "status": "private_follow_ups_queued", "queued": queued}, 200


def _due(value, now):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) <= now
    except (TypeError, ValueError):
        return False
