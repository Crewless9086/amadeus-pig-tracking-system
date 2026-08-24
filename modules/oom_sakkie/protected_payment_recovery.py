"""Durable recovery for owner-confirmed SAM payment claims.

The scheduler may resume only the exact executing claim that already carries a
provider confirmation receipt.  It never creates a preview or a claim.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import uuid

from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.protected_action_claims import complete_claim
from modules.oom_sakkie.sam_payment_owner_runtime import execute_claimed_sale_payment

WORKER_ID = "oom-sakkie-protected-payment-recovery-v1"
INTERVAL_SECONDS = 300
LEASE_SECONDS = 180
MORTALITY_PRESENTATION_VERSION = "health_loss_completion_typed_v2"


def run_payment_recovery_cycle(*, now=None, connect_factory=None,
                               executor=execute_claimed_sale_payment,
                               completer=complete_claim,
                               deliverer=deliver_family_result, store=None):
    now = now or datetime.now(timezone.utc)
    cycle_id = f"PAYREC-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:10].upper()}"
    next_cycle = now + timedelta(seconds=INTERVAL_SECONDS)
    store = store or _RecoveryStore(connect_factory)
    store.start_cycle(cycle_id, now, next_cycle)
    claim = store.acquire(cycle_id, now)
    if not claim:
        result = _summary("payment_recovery_idle", cycle_id, next_cycle)
        store.finish_cycle(cycle_id, now, result)
        return result

    token = claim["callback_token"]
    try:
        if claim["status"] == "completed":
            result = dict(claim.get("result_payload") or {})
        else:
            result, status = executor(claim, connect_factory=connect_factory)
            if status != 200 or result.get("success") is not True:
                pending = {**_summary("payment_recovery_pending", cycle_id, next_cycle),
                    "claim_digest": claim["preview_digest"],
                    "underlying_status": str(result.get("status") or "")}
                store.release(token, cycle_id, now, "execution_pending", pending)
                store.finish_cycle(cycle_id, now, pending)
                return pending
            completion = completer(token, result, connect_factory=connect_factory)
            result = dict(completion.get("result") or result)

        bound = {**dict(claim.get("preview_payload") or {}),
            "canonical_effect_kind": str(claim.get("canonical_effect_kind") or "")}
        parsed = {"telegram_user_id": claim["owner_user_id"],
            "telegram_chat_id": claim["private_chat_id"], "telegram_chat_type": "private",
            "provider_message_id": "recovery:" + cycle_id,
            "provider_timestamp": now.isoformat(), "text": ""}
        specialist = "SAM"
        if claim.get("action_kind") == "mortality":
            from modules.oom_sakkie.family_access import resolve_family_principal
            from modules.oom_sakkie.herdmaster_health_loss_runtime import mortality_completion_recovery_result
            from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
            language = resolve_family_principal(parsed, os.environ).language
            parsed["output_language"] = language
            if _bound_effect_kind(bound, result) == "mortality":
                result = mortality_completion_recovery_result(result, bound, language)
            else:
                answer = str(result.get("answer") or "").strip()
                if (_bound_effect_kind(bound, result) != "health_observation"
                        or not answer or str(result.get("status") or "") != "completed"):
                    raise ValueError("health_loss_recovery_effect_unresolved")
                result = {**result, "writes_farm_data": False, "rows_created": 0,
                    "delivery_recovery_required": True,
                    "recipient_render_contract": "specialist_structured_recipient_v1",
                    "recipient_language": language}
            result["card_mission_id"] = protected_card_mission_id(
                claim["mission_id"], claim["preview_digest"])
            result["presentation_version"] = MORTALITY_PRESENTATION_VERSION
            specialist = "HERDMASTER"
        delivery = deliverer(parsed, result, specialist=specialist,
            mission_id=claim["mission_id"], card_mission_id=str(
                result.get("card_mission_id") or claim.get("card_mission_id") or claim["mission_id"]))
        if not delivery.get("success") or not str(delivery.get("telegram_message_id") or ""):
            pending = {**_summary("payment_recovery_delivery_pending", cycle_id, next_cycle),
                "claim_digest": claim["preview_digest"], "telegram_sends": 0,
                "telegram_edits": int(delivery.get("telegram_edits") or 0)}
            store.release(token, cycle_id, now, "delivery_pending", pending)
            store.finish_cycle(cycle_id, now, pending)
            return pending
        completed = {**_summary("payment_recovery_completed", cycle_id, next_cycle),
            "claim_digest": claim["preview_digest"],
            "provider_message_id": str(delivery["telegram_message_id"]),
            "telegram_sends": int(delivery.get("telegram_sends") or 0),
            "telegram_edits": int(delivery.get("telegram_edits") or 0),
            "payment_write_observed": result.get("writes_to_supabase") is True,
            "canonical_status": str(result.get("status") or "")}
        if claim.get("action_kind") == "mortality":
            completed["presentation_version"] = MORTALITY_PRESENTATION_VERSION
        store.release(token, cycle_id, now, "completed", completed)
        store.finish_cycle(cycle_id, now, completed)
        return completed
    except Exception as exc:
        unresolved = isinstance(exc, ValueError) and str(exc) == "health_loss_recovery_effect_unresolved"
        pending = {**_summary("payment_recovery_pending", cycle_id, next_cycle),
            "claim_digest": claim.get("preview_digest", ""),
            "error_type": type(exc).__name__}
        store.release(token, cycle_id, now,
                      "effect_unresolved" if unresolved else "exception_pending", pending)
        store.finish_cycle(cycle_id, now, pending)
        return pending


def _summary(status, cycle_id, next_cycle):
    return {"success": status in {"payment_recovery_idle", "payment_recovery_completed"},
        "status": status, "worker_id": WORKER_ID, "cycle_id": cycle_id,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "next_cycle_at": next_cycle.isoformat(), "writes_to_supabase": False,
        "telegram_sends": 0, "telegram_edits": 0}


def _bound_effect_kind(bound, result):
    explicit = str((bound or {}).get("effect_kind") or "")
    canonical = str((bound or {}).get("canonical_effect_kind") or "")
    status = str((result or {}).get("status") or "")
    if explicit == "mortality":
        return "mortality" if status.startswith("mortality_lifecycle_") else "unknown"
    if explicit == "health_observation":
        return "health_observation" if status == "completed" else "unknown"
    if canonical in {"mortality", "health_observation"} and status == "completed":
        return canonical
    if status.startswith("mortality_lifecycle_"):
        return "mortality"
    if status == "completed" and "OBSERVATION RECORDED" in str(
            (result or {}).get("answer") or ""):
        return "health_observation"
    return "unknown"


class _RecoveryStore:
    def __init__(self, connect_factory=None):
        self.connect_factory = connect_factory

    def connect(self):
        if self.connect_factory:
            return self.connect_factory()
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres
        return connect_bounded_postgres(database_url=os.environ.get("DATABASE_URL"))

    def start_cycle(self, cycle_id, now, next_cycle):
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute("""insert into app_private.oom_protected_payment_recovery_cycles
                  (cycle_id,worker_id,trigger_kind,started_at,heartbeat_at,next_cycle_at,status)
                  values(%s,%s,'render_cron',%s,%s,%s,'running')""",
                  (cycle_id, WORKER_ID, now, now, next_cycle))

    def acquire(self, cycle_id, now):
        lease_until = now + timedelta(seconds=LEASE_SECONDS)
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute("""select c.callback_token from app_private.oom_protected_action_claims c
                  left join app_private.oom_protected_payment_recovery_leases l using(callback_token)
                  where c.action_kind=any(%s)
                    and c.confirmation_provider_message_id is not null
                    and ((c.action_kind='sam_sale_payment' and
                          (c.status='executing' or (c.status='completed' and l.last_status='delivery_pending')))
                      or (c.action_kind='mortality' and c.status='completed' and
                          (l.callback_token is null or l.last_status='delivery_pending'
                           or (l.last_status='completed' and
                               coalesce(l.last_result->>'presentation_version','')<>%s))))
                    and (l.callback_token is null or l.lease_until<=%s)
                  order by c.confirmation_provider_timestamp limit 1 for update of c skip locked""",
                  (["sam_sale_payment","mortality"],MORTALITY_PRESENTATION_VERSION,now))
                row = cur.fetchone()
                if not row:
                    return None
                token = row[0]
                cur.execute("""insert into app_private.oom_protected_payment_recovery_leases
                  (callback_token,worker_id,cycle_id,lease_until,heartbeat_at,attempt_count,last_status)
                  values(%s,%s,%s,%s,%s,1,'executing')
                  on conflict(callback_token) do update set worker_id=excluded.worker_id,
                    cycle_id=excluded.cycle_id,lease_until=excluded.lease_until,
                    heartbeat_at=excluded.heartbeat_at,
                    attempt_count=app_private.oom_protected_payment_recovery_leases.attempt_count+1,
                    last_status='executing' where app_private.oom_protected_payment_recovery_leases.lease_until<=%s
                  returning callback_token""", (token, WORKER_ID, cycle_id, lease_until, now, now))
                if not cur.fetchone():
                    return None
                cur.execute("""select c.callback_token,c.action_kind,c.owner_user_id,c.private_chat_id,c.mission_id,
                  preview_digest,evidence_generation,preview_payload,status,result_payload,
                  preview_card_message_id,confirmation_provider_message_id,confirmation_provider_timestamp,
                  case when exists(select 1 from public.pig_lifecycle_events life
                         where life.pig_id=c.preview_payload->'identity'->>'pig_id'
                           and life.idempotency_key=c.preview_payload->>'operation_id'
                           and life.lifecycle_event_type='exited_farm') then 'mortality'
                       when exists(select 1 from public.pig_observation_events observation
                         where observation.pig_id=c.preview_payload->'identity'->>'pig_id'
                           and observation.idempotency_key=c.preview_payload->>'operation_id')
                         then 'health_observation' else 'unknown' end
                  from app_private.oom_protected_action_claims c where callback_token=%s""", (token,))
                values = cur.fetchone()
        keys = ("callback_token","action_kind","owner_user_id","private_chat_id","mission_id",
            "preview_digest","evidence_generation","preview_payload","status","result_payload",
            "preview_card_message_id","confirmation_provider_message_id","confirmation_provider_timestamp",
            "canonical_effect_kind")
        return dict(zip(keys, values))

    def release(self, token, cycle_id, now, status, result):
        heartbeat = datetime.now(timezone.utc)
        retry = heartbeat + timedelta(seconds=INTERVAL_SECONDS)
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute("""update app_private.oom_protected_payment_recovery_leases
                  set lease_until=%s,heartbeat_at=%s,last_status=%s,last_result=%s::jsonb
                  where callback_token=%s and cycle_id=%s""",
                  (heartbeat if status == "completed" else retry, heartbeat, status,
                   json.dumps(result, sort_keys=True), token, cycle_id))

    def finish_cycle(self, cycle_id, now, result):
        completed = datetime.now(timezone.utc)
        with self.connect() as db:
            with db.cursor() as cur:
                cur.execute("""update app_private.oom_protected_payment_recovery_cycles
                  set heartbeat_at=%s,completed_at=%s,status=%s,result=%s::jsonb
                  where cycle_id=%s and worker_id=%s""",
                  (completed, completed, result["status"], json.dumps(result, sort_keys=True), cycle_id, WORKER_ID))
