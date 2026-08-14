"""Append-only scheduled reassessment receipts using the existing audit rail."""
from __future__ import annotations
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

EVENT_SOURCE = "oom_sakkie_automatic_reassessment"


def automatic_reassessment_store(action, identity, payload):
    if action in {"load_schedule", "load_latest_outcome"}:
        return _load(action, identity)
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    body = dict(payload or {})
    event_id = identity if action == "claim_schedule" else f"{identity}-OUTCOME"
    event = build_sam_live_stock_review_event(
        {"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "automatic_reassessment"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id, "chatwoot_conversation_id": identity,
                  "review_json": {"automatic_reassessment": {**body, "identity": identity, "event_id": event_id}},
                  "decision_json": {}, "facts_json": {}, "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": result.get("created", status < 300)}


def _load(action, identity):
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            if action == "load_schedule":
                cursor.execute("""select review_json->'automatic_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'automatic_reassessment'->>'identity'=%s
                    order by created_at desc, review_event_id desc limit 1""", (EVENT_SOURCE, identity))
            else:
                cursor.execute("""select review_json->'automatic_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'automatic_reassessment'->>'specialist'=%s
                      and review_json->'automatic_reassessment'->>'status' in ('completed','contained')
                    order by created_at desc, review_event_id desc limit 1""", (EVENT_SOURCE, identity))
            row = cursor.fetchone()
            return row[0] if row else None
