"""Production-owned, read-only morning farm-manager lifecycle."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, time, timezone
import os
import threading
from zoneinfo import ZoneInfo


SAST = ZoneInfo("Africa/Johannesburg")
MORNING_DUE = time(6, 45)
PLAN_WINDOW_END = time(7, 0)
POLL_SECONDS = 60
OWNER_ENV = "OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID"
ENABLED_ENV = "OOM_SAKKIE_DAILY_MANAGER_RUNTIME_ENABLED"
_START_LOCK = threading.Lock()
_STARTED = False


class MorningWindowMissed(RuntimeError):
    """The process became available only after today's bounded plan window."""


def run_morning_cycle(*, now=None, environ=None, deliver=None, store=None,
                      herd_loader=None, rootline_loader=None, litter_loader=None,
                      sales_loader=None):
    """Run the due daily plan or its one bounded visible failure escalation."""
    source = environ if environ is not None else os.environ
    now = _aware(now or datetime.now(timezone.utc))
    local = now.astimezone(SAST)
    owner = _configured_owner(source)
    if not owner:
        return _safe("morning_runtime_owner_binding_unavailable", success=False)
    if local.time() < MORNING_DUE:
        return {**_safe("morning_runtime_not_due"),
                "next_due_at": local.replace(hour=6, minute=45, second=0,
                                              microsecond=0).isoformat()}

    from modules.oom_sakkie.telegram_gateway import deliver_family_result
    deliver = deliver or deliver_family_result
    if local.time() >= PLAN_WINDOW_END:
        return _escalate_failure(
            owner, now, deliver, MorningWindowMissed("morning_plan_window_missed"),
            store=store)

    from modules.oom_sakkie.daily_farm_manager import run_daily_farm_manager
    try:
        results, litters, sales = _load_inputs(
            owner, now, source,
            herd_loader=herd_loader, rootline_loader=rootline_loader,
            litter_loader=litter_loader, sales_loader=sales_loader)
        return run_daily_farm_manager(
            owner_user_id=owner, chat_id=owner, specialist_results=results,
            litter_rows=litters, sale_rows=sales, deliver=deliver, store=store,
            now=now, language=str(source.get("OOM_SAKKIE_DAILY_MANAGER_LANGUAGE") or "en"))
    except Exception as exc:
        return {**_safe("morning_runtime_recovery_pending", success=False),
                "failure_class": exc.__class__.__name__,
                "recovery_deadline_at": local.replace(
                    hour=7, minute=0, second=0, microsecond=0).isoformat()}


def start_production_morning_runtime(*, environ=None, runner=None):
    """Start one daemon per process; durable claims arbitrate scaled workers."""
    global _STARTED
    source = environ if environ is not None else os.environ
    explicitly = _truthy(source.get(ENABLED_ENV))
    render_owned = _truthy(source.get("RENDER"))
    if not (explicitly or render_owned) or _truthy(source.get("OOM_SAKKIE_DAILY_MANAGER_RUNTIME_DISABLED")):
        return False
    with _START_LOCK:
        if _STARTED:
            return False
        _STARTED = True
        target = runner or _runtime_loop
        threading.Thread(target=target, kwargs={"environ": source},
                         name="oom-sakkie-morning-runtime", daemon=True).start()
        return True


def _runtime_loop(*, environ):
    import time as clock
    while True:
        try:
            run_morning_cycle(environ=environ)
        except Exception:
            # The next bounded poll resumes from durable lifecycle state.
            pass
        clock.sleep(POLL_SECONDS)


def _load_inputs(owner, now, source, *, herd_loader, rootline_loader,
                 litter_loader, sales_loader):
    if herd_loader is None or rootline_loader is None:
        from modules.oom_sakkie.farm_manager_runtime import _load_herdmaster, _load_rootline
        from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
        authority = issue_gateway_owner_authority(owner, owner)
        herd_loader = herd_loader or (lambda: _load_herdmaster(
            authority, owner, now, str(source.get("OOM_SAKKIE_DAILY_MANAGER_LANGUAGE") or "en")))
        rootline_loader = rootline_loader or (lambda: _load_rootline(now))
    if litter_loader is None:
        from modules.pig_weights.farm_supabase_read_service import get_breeding_attention_source_snapshot
        litter_loader = lambda: get_breeding_attention_source_snapshot(deadline_seconds=20)
    if sales_loader is None:
        from modules.sales.sales_transaction_read import list_sales_transactions
        sales_loader = list_sales_transactions
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oom-morning-input")
    try:
        futures = {"herd": executor.submit(herd_loader),
                   "rootline": executor.submit(rootline_loader),
                   "litters": executor.submit(litter_loader),
                   "sales": executor.submit(sales_loader)}
        done, pending = wait(tuple(futures.values()), timeout=40)
        if futures["herd"] not in done or futures["rootline"] not in done:
            raise TimeoutError("morning_runtime_specialist_deadline")
        results = [futures["herd"].result(), futures["rootline"].result()]
        litters = []
        if futures["litters"] in done:
            snapshot = futures["litters"].result()
            litters = ((snapshot.get("allocation_inputs") or {}).get("litter_rows") or [])
        sales = []
        if futures["sales"] in done:
            payload, status = futures["sales"].result()
            if status == 200 and payload.get("success") is True:
                sales = payload.get("sales_transactions") or []
        for future in pending:
            future.cancel()
        return results, litters, sales
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _escalate_failure(owner, now, deliver, exc, *, store=None):
    from modules.oom_sakkie.daily_farm_manager import daily_farm_manager_store
    store = store or daily_farm_manager_store
    daily_identity = f"OOM-DAILY-FARM-MANAGER-{now.astimezone(SAST).date().isoformat()}"
    claim_id = daily_identity + ":DELIVERY"
    claim = store("claim_daily", claim_id, {
        "daily_identity": daily_identity,
        "status": "failure_detected",
        "observed_at": now.isoformat(),
        "failure_class": exc.__class__.__name__,
        "contract_version": "oom_sakkie_daily_farm_manager.v2",
    })
    if not isinstance(claim, dict) or claim.get("success") is not True:
        return {**_safe("morning_runtime_failure_claim_unproven", success=False),
                "failure_class": exc.__class__.__name__}
    if claim.get("created") is False:
        return {**_safe("morning_runtime_failure_replay_suppressed"),
                "failure_class": exc.__class__.__name__}
    identity = daily_identity + ":FAILURE"
    parsed = {"telegram_user_id": owner, "telegram_chat_id": owner,
              "provider_message_id": "scheduled:" + identity,
              "provider_timestamp": now.isoformat(), "text": "Daily Farm Manager failure"}
    result = {"success": True, "status": "daily_manager_creation_failed",
              "answer": ("<b>Morning farm plan unavailable</b>\n\n"
                         "Oom Sakkie could not assemble today's supported farm evidence. "
                         "No farm or hardware action was taken. The incident is retained for recovery."),
              "hardware_commands": 0, "writes_farm_data": False}
    delivery = deliver(parsed, result, specialist="OOM_SAKKIE",
                       mission_id=identity, card_mission_id=identity)
    confirmed = bool((delivery or {}).get("success")
                     and (delivery or {}).get("telegram_message_id"))
    store("record_daily", claim_id + ":OUTCOME", {
        "daily_identity": daily_identity,
        "status": "failure_presented" if confirmed else "provider_ambiguous",
        "observed_at": now.isoformat(),
        "failure_class": exc.__class__.__name__,
        "telegram_message_id": str((delivery or {}).get("telegram_message_id") or ""),
        "telegram_sends": int((delivery or {}).get("telegram_sends") or 0),
    })
    return {**_safe("morning_runtime_failure_escalated", success=False),
            "failure_class": exc.__class__.__name__,
            "telegram_sends": int((delivery or {}).get("telegram_sends") or 0),
            "telegram_message_id": str((delivery or {}).get("telegram_message_id") or ""),
            "provider_delivery_confirmed": confirmed}


def _configured_owner(source):
    explicit = str(source.get(OWNER_ENV) or "").strip()
    allowed = {value.strip() for value in str(
        source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if value.strip()}
    if explicit:
        return explicit if explicit in allowed else ""
    return next(iter(allowed)) if len(allowed) == 1 else ""


def _safe(status, *, success=True):
    return {"success": success, "status": status, "telegram_sends": 0,
            "telegram_edits": 0, "hardware_commands": 0,
            "writes_farm_data": False, "protected_actions_performed": False}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
