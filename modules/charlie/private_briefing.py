"""Executive brief scheduling and durable outbox preparation."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from modules.charlie.mission_store import _connect, _database_url
from modules.charlie.private_tools import execute_private_tool
from modules.charlie.private_store import stable_id


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
                    brief, status = execute_private_tool("executive_brief", {})
                    if status >= 400:
                        continue
                    outbox_id = stable_id("PRIVATEBRIEF", subscription_id, local_now.date().isoformat())
                    payload = {"private_text": brief.get("summary"), "chat_id": str(chat_id), "brief_type": brief_type}
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
