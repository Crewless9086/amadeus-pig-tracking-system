"""Append-only scheduled reassessment receipts using the existing audit rail."""
from __future__ import annotations
from contextlib import nullcontext
import hashlib
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

EVENT_SOURCE = "oom_sakkie_automatic_reassessment"


def automatic_reassessment_store(action, identity, payload):
    if action in {"load_schedule", "load_latest_outcome"}:
        return _load(action, identity)
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.oom_sakkie.automatic_reassessment_scheduler import report_recovery_source, report_recovery_binding, _parse
    body = dict(payload or {})
    candidate = body.pop("report_recovery_candidate", None)
    with connect_bounded_rootline_postgres(read_only=False, read_committed=True) as connection:
        connection.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("ROOTLINE-SCHEDULE-REPORT-RECOVERY",))
        if action == "claim_schedule" and candidate is not None and _load("load_schedule", identity, _connection=connection) is None:
            latest = _load("load_latest_outcome", "ROOTLINE", _connection=connection)
            checked_at = connection.execute("select clock_timestamp()").fetchone()[0]
            source = report_recovery_source(latest, now=checked_at, target_due=_parse(body.get("due_at")))
            expected = report_recovery_binding(source, identity, body.get("invocation_receipt")) if source else None
            if candidate == expected:
                marker = "OOM-REPORT-RECOVERY-" + hashlib.sha256(
                    (source["source_identity"]+"|"+source["source_receipt"]).encode()).hexdigest()[:40]
                prior = _load("load_schedule", marker, _connection=connection)
                if prior is None:
                    marker_body = {"status": "recovery_consumed", "report_recovery": expected,
                        "specialist": "ROOTLINE", "report_work_due": False}
                    result = _record("claim_schedule", marker, marker_body, connection)
                    if result.get("created") is not True:
                        raise RuntimeError("report_recovery_consumption_unproven")
                    actual = _load("load_schedule", marker, _connection=connection)
                    if not isinstance(actual, dict) or actual.get("report_recovery") != expected:
                        raise RuntimeError("report_recovery_consumption_mismatch")
                    body["report_recovery"] = expected
        result = _record(action, identity, body, connection)
        if result.get("success") is not True:
            raise RuntimeError("schedule_transaction_unproven")
        return result


def _record(action, identity, body, connection):
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event_id = identity if action == "claim_schedule" else f"{identity}-OUTCOME"
    event = build_sam_live_stock_review_event(
        {"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "automatic_reassessment"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id, "chatwoot_conversation_id": identity,
                  "review_json": {"automatic_reassessment": {**body, "identity": identity, "event_id": event_id}},
                  "decision_json": {}, "facts_json": {}, "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: nullcontext(connection))
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": result.get("created", status < 300)}


def _load(action, identity, *, _connection=None):
    with (nullcontext(_connection) if _connection is not None else connect_bounded_read()) as connection:
        with connection.cursor() as cursor:
            if action == "load_schedule":
                cursor.execute("""select review_json->'automatic_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'automatic_reassessment'->>'identity'=%s
                    order by created_at desc, review_event_id desc limit 1""", (EVENT_SOURCE, identity))
            else:
                # Find the newest eligible timestamp with the existing source/time
                # index, then resolve every eligible ID tie in the same snapshot.
                # OFFSET 0 keeps report filters outside the ordered source scan;
                # it skips no rows and imposes no cutoff on eligible history.
                cursor.execute("""with latest_time as materialized (
                    select created_at
                    from (
                        select created_at, review_json
                        from public.sam_live_stock_conversation_review_events
                        where event_source=%s
                        order by created_at desc offset 0
                    ) as source_history
                    where review_json->'automatic_reassessment'->>'specialist'=%s
                      and review_json->'automatic_reassessment'->>'status' in ('completed','contained')
                      and coalesce(review_json->'automatic_reassessment'->>'report_work_due','true') <> 'false'
                    order by created_at desc limit 1
                    )
                    select review_json->'automatic_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'automatic_reassessment'->>'specialist'=%s
                      and review_json->'automatic_reassessment'->>'status' in ('completed','contained')
                      and coalesce(review_json->'automatic_reassessment'->>'report_work_due','true') <> 'false'
                      and created_at = (select created_at from latest_time)
                    order by review_event_id desc limit 1""", (EVENT_SOURCE, identity, EVENT_SOURCE, identity))
            row = cursor.fetchone()
            return row[0] if row else None
