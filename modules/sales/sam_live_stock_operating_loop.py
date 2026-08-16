"""Deployed, leased SAM Livestock inbox loop with a fail-closed shadow mode."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import socket
import threading
import uuid


ENABLED_ENV = "SAM_LIVE_STOCK_OPERATING_LOOP_ENABLED"
MODE_ENV = "SAM_LIVE_STOCK_OPERATING_LOOP_MODE"
POLL_SECONDS_ENV = "SAM_LIVE_STOCK_OPERATING_LOOP_POLL_SECONDS"
WORKER_ID_ENV = "RENDER_INSTANCE_ID"
DEFAULT_POLL_SECONDS = 60
_START_LOCK = threading.Lock()
_STARTED = False


def run_sam_live_stock_operating_cycle(*, environ=None, now=None, store=None,
                                       operator=None):
    """Reconcile once. Shadow is the only currently executable mode."""
    source = environ if environ is not None else os.environ
    observed = _aware(now or datetime.now(timezone.utc))
    next_cycle = observed + timedelta(seconds=_poll_seconds(source))
    if not _truthy(source.get(ENABLED_ENV)):
        return _safe("sam_live_stock_operating_loop_disabled", next_cycle_at=None)
    mode = str(source.get(MODE_ENV) or "shadow").strip().lower()
    if mode != "shadow":
        return _safe("sam_live_stock_operating_loop_mode_contained", success=False,
                     configured_mode=mode, next_cycle_at=next_cycle.isoformat())

    worker_id = _worker_id(source)
    cycle_id = "SAM-LIVE-CYCLE-" + uuid.uuid4().hex.upper()
    store = store or PostgresOperatingLoopStore(source)
    lease = store.acquire_cycle(worker_id=worker_id, cycle_id=cycle_id,
                                now=observed, next_cycle_at=next_cycle)
    if not lease.get("acquired"):
        return _safe("sam_live_stock_operating_loop_lease_held",
                     worker_id=worker_id, cycle_id=cycle_id,
                     next_cycle_at=lease.get("next_cycle_at"))
    proposals = []
    activated_at = _aware(lease.get("activated_at") or observed)

    def shadow_processor(payload):
        identity = _payload_identity(payload)
        if store.proposal_exists(identity):
            return {"success": True, "processed": False, "sent": False,
                    "status": "shadow_proposal_replay_suppressed",
                    "sam_decision": {}, "_operation_status_code": 200}
        try:
            inbound_at = datetime.fromtimestamp(
                int(payload.get("created_at") or 0), timezone.utc
            )
        except (TypeError, ValueError, OSError):
            inbound_at = datetime.min.replace(tzinfo=timezone.utc)
        if inbound_at < activated_at:
            return {"success": True, "processed": False, "sent": False,
                    "status": "shadow_pre_activation_backlog_observed",
                    "sam_decision": {}, "_operation_status_code": 200}
        result = _compose_shadow_proposal(payload, source)
        decision = result.get("sam_decision") if isinstance(result.get("sam_decision"), dict) else {}
        reply = str(decision.get("suggested_reply_text") or "")
        proposal = {
            **identity,
            "cycle_id": cycle_id,
            "worker_id": worker_id,
            "response_text": reply,
            "response_digest": hashlib.sha256(reply.encode("utf-8")).hexdigest(),
            "decision": decision,
            "status": "shadow_proposed" if reply else "shadow_no_reply",
            "observed_at": observed.isoformat(),
        }
        store.record_proposal(proposal)
        proposals.append(proposal)
        return result

    operator = operator or _canonical_operator
    try:
        packet = operator(source, shadow_processor)
        store.record_dispositions(
            packet.get("dispositions") or [], cycle_id=cycle_id,
            worker_id=worker_id, observed_at=observed,
        )
        store.complete_cycle(
            worker_id=worker_id, cycle_id=cycle_id, now=observed,
            next_cycle_at=next_cycle, status="completed", packet=packet,
        )
        return {
            **_safe("sam_live_stock_shadow_cycle_completed"),
            "worker_id": worker_id,
            "cycle_id": cycle_id,
            "heartbeat_at": observed.isoformat(),
            "next_cycle_at": next_cycle.isoformat(),
            "inventory_count": int(packet.get("inventory_count") or 0),
            "eligible_count": sum(bool(row.get("eligible")) for row in packet.get("dispositions") or []),
            "shadow_proposal_count": len(proposals),
        }
    except Exception as exc:
        store.complete_cycle(
            worker_id=worker_id, cycle_id=cycle_id, now=observed,
            next_cycle_at=next_cycle, status="failed",
            packet={"error_type": exc.__class__.__name__},
        )
        return _safe("sam_live_stock_shadow_cycle_failed", success=False,
                     worker_id=worker_id, cycle_id=cycle_id,
                     heartbeat_at=observed.isoformat(),
                     next_cycle_at=next_cycle.isoformat(),
                     error_type=exc.__class__.__name__)


def start_sam_live_stock_operating_loop(*, environ=None, runner=None):
    """Start a process-local daemon; the database lease arbitrates replicas."""
    global _STARTED
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(ENABLED_ENV)):
        return False
    if str(source.get(MODE_ENV) or "shadow").strip().lower() != "shadow":
        return False
    with _START_LOCK:
        if _STARTED:
            return False
        _STARTED = True
        threading.Thread(
            target=runner or _runtime_loop,
            kwargs={"environ": source},
            name="sam-live-stock-operating-loop",
            daemon=True,
        ).start()
        return True


def _runtime_loop(*, environ):
    import time
    while True:
        try:
            run_sam_live_stock_operating_cycle(environ=environ)
        except Exception:
            pass
        time.sleep(_poll_seconds(environ))


def _canonical_operator(source, processor):
    from modules.sales.sales_transaction_routes import (
        _load_sam_live_stock_history_with_status,
        _prefetch_sam_canonical_sales_evidence,
        _sam_live_stock_existing_inbound_claims,
        _sam_live_stock_inbound_claim_exists,
        _sam_live_stock_unresolved_delivery_quarantines,
    )
    from modules.sales.sam_live_stock_inbox_operator import operate_livestock_inbox
    return operate_livestock_inbox(
        environ=source,
        history_loader=_load_sam_live_stock_history_with_status,
        claim_exists=_sam_live_stock_inbound_claim_exists,
        claimed_inbound_loader=_sam_live_stock_existing_inbound_claims,
        quarantined_conversation_loader=_sam_live_stock_unresolved_delivery_quarantines,
        canonical_evidence_prefetcher=_prefetch_sam_canonical_sales_evidence,
        attention_queue_operator=False,
        inbound_processor=processor,
        max_process_count=None,
        isolate_provider_read_failures=True,
    )


def _compose_shadow_proposal(payload, source):
    from modules.sales.sales_transaction_routes import _prefetch_sam_canonical_sales_evidence
    from modules.sales.sam_live_stock_runtime import handle_sam_live_stock_chatwoot_inbound
    shadow = dict(source)
    for key in (
        "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED",
        "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED",
        "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED",
        "SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED",
        "SAM_LIVE_STOCK_BACKEND_QUOTE_PREPARE_ENABLED",
        "SAM_LIVE_STOCK_BACKEND_RESERVATION_ENABLED",
        "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_ENABLED",
    ):
        shadow[key] = "false"
    history = payload.get("_sam_authoritative_history") or {}
    evidence = payload.get("_sam_prefetched_canonical_evidence")
    if not isinstance(evidence, dict):
        evidence = _prefetch_sam_canonical_sales_evidence(shadow)

    def prohibited(*_args, **_kwargs):
        raise RuntimeError("shadow_external_effect_prohibited")

    result, status = handle_sam_live_stock_chatwoot_inbound(
        payload, environ=shadow, allow_provider_current_backlog=True,
        conversation_history_loader=lambda *_a, **_k: history,
        availability_loader=lambda: list(evidence.get("availability_rows") or []),
        availability_evidence=evidence.get("availability_evidence"),
        pricing_projection=evidence.get("pricing_projection"),
        intake_writer=prohibited, draft_order_creator=prohibited,
        draft_order_syncer=prohibited, quote_preparer=prohibited,
        chatwoot_sender=prohibited, routine_delivery_claim=prohibited,
        routine_delivery_evidence_recorder=prohibited,
    )
    result["_operation_status_code"] = status
    return result


class PostgresOperatingLoopStore:
    """Small private-schema persistence boundary for lease and shadow evidence."""
    def __init__(self, environ):
        self.database_url = str(
            environ.get("DATABASE_URL")
            or environ.get("SUPABASE_DB_URL")
            or environ.get("FARM_SUPABASE_DATABASE_URL")
            or ""
        ).strip()
        if not self.database_url:
            raise RuntimeError("sam_operating_loop_database_url_missing")

    def acquire_cycle(self, **params):
        row = self._call("app_private.acquire_sam_live_stock_operating_cycle", (
            params["worker_id"], params["cycle_id"], params["now"],
            params["next_cycle_at"],
        ), fetch=True)
        return dict(row or {})

    def record_proposal(self, proposal):
        self._call("app_private.record_sam_live_stock_shadow_proposal", (
            json.dumps(proposal, default=str),
        ))

    def proposal_exists(self, identity):
        row = self._call("app_private.sam_live_stock_shadow_proposal_exists", (
            identity["account_id"], identity["conversation_id"],
            identity["inbound_message_id"],
        ), fetch=True)
        return bool((row or {}).get("present"))

    def record_dispositions(self, dispositions, **identity):
        self._call("app_private.project_sam_live_stock_obligations", (
            json.dumps(list(dispositions), default=str), identity["cycle_id"],
            identity["worker_id"], identity["observed_at"],
        ))

    def complete_cycle(self, **params):
        self._call("app_private.complete_sam_live_stock_operating_cycle", (
            params["worker_id"], params["cycle_id"], params["now"],
            params["next_cycle_at"], params["status"],
            json.dumps(params["packet"], default=str),
        ))

    def _call(self, function, params, fetch=False):
        import psycopg
        placeholders = ",".join(["%s"] * len(params))
        with psycopg.connect(self.database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select * from {function}({placeholders})", params)
                if fetch:
                    columns = [item.name for item in cursor.description]
                    values = cursor.fetchone()
                    return dict(zip(columns, values)) if values else {}


def _payload_identity(payload):
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    return {
        "account_id": str((payload.get("account") or {}).get("id") or ""),
        "conversation_id": str(conversation.get("id") or ""),
        "inbound_message_id": str(payload.get("id") or ""),
        "contact_id": str((payload.get("sender") or {}).get("id") or ""),
    }


def _worker_id(source):
    host = str(source.get(WORKER_ID_ENV) or socket.gethostname() or "unknown")
    return f"{host}:pid-{os.getpid()}"[:160]


def _poll_seconds(source):
    try:
        return max(30, min(300, int(source.get(POLL_SECONDS_ENV) or DEFAULT_POLL_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_POLL_SECONDS


def _safe(status, *, success=True, **extra):
    return {"success": success, "status": status, "mode": "shadow",
            "customer_sends": 0, "owner_cards": 0, "intake_writes": 0,
            "order_writes": 0, "quote_writes": 0, "reservations": 0,
            "n8n_mutations": 0, "google_sheets_mutations": 0, **extra}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
