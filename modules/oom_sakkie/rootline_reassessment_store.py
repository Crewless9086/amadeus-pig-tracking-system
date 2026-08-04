"""Append-only persistence for ROOTLINE reassessment notification state."""
from __future__ import annotations
import os

EVENT_SOURCE = "oom_sakkie_rootline_reassessment"


def rootline_reassessment_state_store(action, identity, payload):
    if action in {"load_delivered", "load_identity"}:
        return _load(action, identity)
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event_payload = dict(payload or {})
    event_id = identity if action == "claim_pending" else f"{identity}-{action.upper()}"
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "rootline_reassessment"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = event_id
    event["chatwoot_conversation_id"] = identity
    event["review_json"] = {"rootline_reassessment": {**event_payload, "identity": identity, "event_id": event_id}}
    event["decision_json"] = {}; event["facts_json"] = {}
    event["customer_message_excerpt"] = ""; event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": result.get("created", status < 300)}


def _load(action, identity):
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            if action == "load_identity":
                cursor.execute("""select review_json->'rootline_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'rootline_reassessment'->>'identity'=%s
                    order by created_at desc,review_event_id desc limit 1""", (EVENT_SOURCE, identity))
            else:
                owner, chat = identity.split("|", 1)
                cursor.execute("""select review_json->'rootline_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_reassessment'->>'owner_user_id'=%s
                      and review_json->'rootline_reassessment'->>'chat_id'=%s
                      and review_json->'rootline_reassessment'->>'delivery_state'='delivered'
                    order by created_at desc,review_event_id desc limit 1""", (EVENT_SOURCE, owner, chat))
            row = cursor.fetchone()
            return row[0] if row else None
