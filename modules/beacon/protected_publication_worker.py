"""Deployed-only consumer for approved BEACON campaign review claims."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os

from modules.beacon.public_livestock_content_policy import assess_public_livestock_content
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.sales.beacon_campaign import (
    FACEBOOK_POST_CONFIRMATION_PHRASE, execute_beacon_facebook_page_post,
)


def run_protected_publication_cycle(*, database_url=None, worker_id=None,
                                    store=None, executor=None, now=None):
    """Claim at most one approval and give it to the canonical Meta executor."""
    current = now or datetime.now(timezone.utc)
    store = store or PostgresProtectedPublicationStore(database_url)
    claimed = store.claim(worker_id or _worker_id(), current)
    if not claimed:
        return _result("beacon_publication_cycle_silent")
    error = validate_claimed_approval(claimed, now=current)
    if error:
        store.finish(claimed["consumer_id"], "contained", {"status": error}, current)
        return _result(error, success=False)
    preview = claimed["preview_payload"]
    media = [_execution_asset(item) for item in preview["selected_media"]]
    payload = {
        "publish_packet_id": preview["packet_id"],
        "channel": "facebook_organic", "campaign_lane": "live_stock_awareness",
        "objective": "farm_awareness", "exact_text": preview["exact_post_copy"],
        "selected_assets": media, "selected_asset": media[0],
        "asset_id": media[0]["asset_id"], "owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "zero_spend": True, "protected_campaign_claim_token": claimed["callback_token"],
        "protected_campaign_digest": preview["campaign_digest"],
        "recorded_by": "beacon_protected_publication_worker",
    }
    execute = executor or execute_beacon_facebook_page_post
    try:
        outcome, status = execute(payload, database_url=database_url)
    except Exception as exc:
        outcome, status = ({"success": False, "status": "meta_provider_outcome_ambiguous",
                            "error_type": exc.__class__.__name__,
                            "automatic_retry_allowed": False}, 503)
    outcome_status = str(outcome.get("status") or "")
    provider = outcome.get("facebook_result") if isinstance(outcome.get("facebook_result"), dict) else {}
    final = "confirmed" if outcome.get("success") is True else (
        "contained_ambiguous" if ("ambiguous" in outcome_status or
            provider.get("outcome") == "ambiguous" or
            outcome_status in {"provider_timeout", "provider_connection_lost"})
        else "contained_failed")
    if store.finish(claimed["consumer_id"], final, outcome, current) is False:
        return {**outcome, "success": False, "consumer_status": "contained_ambiguous",
                "status": "publication_consumer_lease_lost_ambiguous",
                "automatic_retry_allowed": False}
    return {**outcome, "consumer_status": final, "automatic_retry_allowed": False}


def validate_claimed_approval(claim, *, now=None):
    preview = claim.get("preview_payload") if isinstance(claim.get("preview_payload"), dict) else {}
    if claim.get("action_kind") != "beacon_campaign_review" or claim.get("claim_status") != "completed":
        return "protected_campaign_owner_approval_required"
    result = claim.get("approval_result") if isinstance(claim.get("approval_result"), dict) else {}
    if result.get("status") != "beacon_campaign_review_approved":
        return "protected_campaign_owner_approval_required"
    if preview.get("contract_version") != "beacon_campaign_owner_card_v1":
        return "protected_campaign_contract_invalid"
    bound = canonical_preview_digest("beacon_campaign_review",
        {key: value for key, value in preview.items() if key != "campaign_digest"})
    if bound != preview.get("campaign_digest") or bound != claim.get("evidence_generation"):
        return "protected_campaign_binding_changed"
    try:
        expires = datetime.fromisoformat(str(preview.get("approval_expires_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return "protected_campaign_expiry_invalid"
    if expires <= (now or datetime.now(timezone.utc)):
        return "protected_campaign_approval_expired"
    media = preview.get("selected_media")
    if not isinstance(media, list) or not media:
        return "protected_campaign_exact_media_required"
    for item in media:
        if not isinstance(item, dict) or item.get("public_use_authority") != "approved":
            return "protected_campaign_media_authority_revoked"
        if not all(str(item.get(key) or "").strip() for key in (
                "asset_id", "content_sha256", "storage_readback_proof_id",
                "library_accept_event_id", "public_use_event_id", "litter_id", "event_id")):
            return "protected_campaign_media_evidence_incomplete"
    story = preview.get("story_context") if isinstance(preview.get("story_context"), dict) else {}
    sow_name = str(story.get("sow_name") or "").strip()
    litter_id = str(story.get("litter_id") or "").strip()
    caption = str(preview.get("exact_post_copy") or "")
    if not sow_name or sow_name not in caption or (litter_id and litter_id.casefold() in caption.casefold()):
        return "protected_campaign_public_sow_identity_failed"
    if any(str(item.get("litter_id") or "") != litter_id or
           str(item.get("event_id") or "") != str(story.get("event_id") or "") for item in media):
        return "protected_campaign_litter_media_binding_failed"
    if __import__("re").search(
            r"\b(follow\s+(?:along|us)|volg\s+(?:saam|ons)|contact|kontak|message|boodskap|dm|"
            r"come\s+(?:see|visit)|visit|share|read\s+more|learn\s+more|see\s+more|check\s+out|click|tap|watch|subscribe|"
            r"kom\s+(?:kyk|besoek|loer)|gaan\s+kyk|besoek|deel|lees\s+meer|vind\s+meer\s+uit|klik|druk|kyk|teken\s+in)\b",
            caption, __import__("re").I):
        return "protected_campaign_story_only_cta_failed"
    policy = assess_public_livestock_content(preview.get("exact_post_copy"),
        objective="farm_awareness", campaign_lane="live_stock_awareness", media=media)
    if not policy.get("allowed"):
        return "protected_campaign_public_policy_failed"
    return ""


class PostgresProtectedPublicationStore:
    def __init__(self, database_url=None):
        self.database_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()

    def claim(self, worker_id, now):
        if not self.database_url:
            return None
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=10) as db, db.cursor() as cur:
            cur.execute("""update app_private.beacon_protected_publication_consumers
              set status='contained_ambiguous',outcome_json=%s::jsonb,updated_at=%s,finished_at=%s
              where status='claimed' and claimed_at < %s - interval '5 minutes'""",
              (json.dumps({"status":"worker_restart_after_claim_ambiguous",
                           "automatic_retry_allowed":False}),now,now,now))
            cur.execute("""select c.callback_token,c.action_kind,c.evidence_generation,
                c.preview_payload,c.status,c.result_payload
              from app_private.oom_protected_action_claims c
              left join app_private.beacon_protected_publication_consumers p
                on p.callback_token=c.callback_token
             where c.action_kind='beacon_campaign_review' and c.status='completed'
               and c.result_payload->>'status'='beacon_campaign_review_approved'
               and p.callback_token is null
             order by c.completed_at,c.callback_token for update of c skip locked limit 1""")
            row = cur.fetchone()
            if not row: return None
            consumer_id = "BEACON-PUB-CONSUMER-" + hashlib.sha256(row[0].encode()).hexdigest()[:24].upper()
            cur.execute("""insert into app_private.beacon_protected_publication_consumers
              (consumer_id,callback_token,worker_id,status,claimed_at,updated_at)
              values(%s,%s,%s,'claimed',%s,%s) on conflict(callback_token) do nothing""",
              (consumer_id,row[0],worker_id,now,now))
            if cur.rowcount != 1: return None
            return {"consumer_id": consumer_id,"callback_token":row[0],"action_kind":row[1],
                "evidence_generation":row[2],"preview_payload":row[3],"claim_status":row[4],
                "approval_result":row[5]}

    def finish(self, consumer_id, status, outcome, now):
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=10) as db, db.cursor() as cur:
            cur.execute("""update app_private.beacon_protected_publication_consumers
              set status=%s,outcome_json=%s::jsonb,updated_at=%s,finished_at=%s
              where consumer_id=%s and status='claimed'""",
              (status,json.dumps(outcome,sort_keys=True,default=str),now,now,consumer_id))
            return cur.rowcount == 1


def _execution_asset(item):
    return {**item, "media_type": "image", "effective_public_use_approved": True,
            "storage_readback_sha256": item.get("content_sha256")}


def _worker_id():
    return str(os.getenv("RENDER_INSTANCE_ID") or os.getenv("HOSTNAME") or "beacon-worker")[:120]


def _result(status, success=True):
    return {"success": success, "status": status, "publishes": False,
            "meta_call": False, "automatic_retry_allowed": False}
