"""Append-only persistence for ROOTLINE reassessment notification state."""
from __future__ import annotations
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

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
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            if action == "load_identity":
                cursor.execute("""select review_json->'rootline_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'rootline_reassessment'->>'identity'=%s
                    order by created_at desc,review_event_id desc limit 10""", (EVENT_SOURCE, identity))
                rows = cursor.fetchall()
                if not rows:
                    return None
                latest = dict(rows[0][0] or {})
                if not str(latest.get("operating_date") or ""):
                    dated = next((dict(row[0] or {}) for row in rows
                        if str((row[0] or {}).get("operating_date") or "")), None)
                    if dated:
                        latest["operating_date"] = dated["operating_date"]
                return latest
            else:
                owner, chat = identity.split("|", 1)
                cursor.execute("""select review_json->'rootline_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_reassessment'->>'owner_user_id'=%s
                      and review_json->'rootline_reassessment'->>'chat_id'=%s
                    order by created_at desc,review_event_id desc limit 20""", (EVENT_SOURCE, owner, chat))
                rows = cursor.fetchall()
                delivered = next((dict(row[0] or {}) for row in rows
                    if str((row[0] or {}).get("delivery_state") or "") == "delivered"), None)
                if delivered is None:
                    return None
                same_identity = [dict(row[0] or {}) for row in rows
                    if str((row[0] or {}).get("identity") or "") == str(delivered.get("identity") or "")]
                return _merge_missing(delivered, same_identity)


def _merge_missing(latest, history):
    merged = dict(latest or {})
    for prior in history:
        for key, value in dict(prior or {}).items():
            if key not in merged or merged.get(key) in (None, "", [], {}):
                merged[key] = value
    return merged
