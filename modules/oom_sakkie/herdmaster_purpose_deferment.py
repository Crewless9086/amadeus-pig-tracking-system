"""Explicit owner review dates on the existing manager case/event rail."""
from contextlib import nullcontext
from datetime import datetime, time, timedelta, timezone
import json

CONTRACT = "herdmaster.purpose_deferment.v1"


def record_deferral(claimed, parsed, *, now, connect=None):
    from modules.oom_sakkie.herdmaster_purpose_telegram import (_connect, digest, load_context,
        _case, _recommendations, REVIEW)
    from modules.oom_sakkie.herdmaster_purpose_membership import load_current_membership
    p = claimed["preview_payload"]
    if claimed["action_kind"] != REVIEW or p.get("mode") != "defer":
        raise ValueError("purpose_defer_exact_preview_required")
    binding = p["binding"]
    requested = datetime.fromisoformat(p["review_date"]).date()
    review_at = datetime.combine(requested, time(6), timezone.utc)  # explicit 08:00 SAST
    request_id = digest([claimed["callback_token"], claimed["preview_digest"]])
    event_id = "OOM-PURPOSE-DEFER-"+request_id[:32].upper()
    payload = {"contract": CONTRACT, "request_id": request_id, "case_id": binding["case_id"],
        "generation": binding["generation"], "evidence_digest": binding["evidence_digest"],
        "membership_digest": binding["membership_digest"], "owner_user_id": str(parsed["telegram_user_id"]),
        "private_chat_id": str(parsed["telegram_chat_id"]), "provider_message_id": str(parsed["provider_message_id"]),
        "source_card_message_id": str(parsed["reply_to_message_id"]), "review_at": review_at.isoformat(),
        "reason": "owner_requested_review"}
    with (connect or _connect)() as db, db.cursor() as cur:
        cur.execute("set transaction isolation level serializable")
        cur.execute("set local statement_timeout='6000ms'")
        cur.execute("set local lock_timeout='1000ms'")
        cur.execute("select event_payload from app_private.oom_manager_case_events where event_id=%s", (event_id,))
        prior = cur.fetchone()
        if prior:
            stored = (prior[0] or {}).get("purpose_review_deferred") or {}
            if any(stored.get(k) != v for k, v in payload.items()):
                raise ValueError("purpose_defer_replay_mismatch")
            return {"success": True, "status": "purpose_review_date_replayed", "event_id": event_id,
                "review_at": review_at.isoformat(), "writes_farm_data": False, "writes_manager_data": False}
        if not now < review_at <= now+timedelta(days=8):
            raise ValueError("purpose_review_future_date_required")
        context = load_context(now=now, connection=db)
        _case(context, binding)
        if _recommendations(context, binding) != p["recommendations"]:
            raise ValueError("purpose_recommendation_changed")
        load_current_membership(binding["case_id"], context["snapshot"], now=datetime.now(timezone.utc),
            expected_generation=binding["generation"], expected_evidence_digest=binding["evidence_digest"],
            connect=lambda: nullcontext(db), transaction_managed=True, lock_case=True)
        payload["requested_at"] = now.isoformat()
        cur.execute("""update app_private.oom_manager_cases set status='waiting_reassessment',
            next_reassessment_at=%s,updated_at=%s where case_id=%s and generation=%s
            and evidence_digest=%s and status in ('open','waiting_reassessment','exception')
            and assigned_worker_id is null and lease_until is null returning case_id""",
            (review_at, now, binding["case_id"], binding["generation"], binding["evidence_digest"]))
        if not cur.fetchone(): raise ValueError("purpose_defer_case_changed_or_leased")
        event = {"case_id": binding["case_id"], "generation": binding["generation"],
            "event_type": "reassessment_scheduled", "occurred_at": now.isoformat(), "purpose_review_deferred": payload}
        cur.execute("""insert into app_private.oom_manager_case_events
            (event_id,case_id,generation,event_type,event_payload,occurred_at)
            values(%s,%s,%s,'reassessment_scheduled',%s::jsonb,%s)""",
            (event_id, binding["case_id"], binding["generation"], json.dumps(event,sort_keys=True), now))
    return {"success": True, "status": "purpose_review_date_recorded", "event_id": event_id,
        "review_at": review_at.isoformat(), "writes_farm_data": False, "writes_manager_data": True}
