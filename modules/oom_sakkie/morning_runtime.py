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
from modules.oom_sakkie.bounded_postgres_read import OWNER_REQUEST_DEADLINE_SECONDS
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
    recipients = _configured_recipients(source)
    if not recipients:
        return _safe("morning_runtime_owner_binding_unavailable", success=False)
    if local.time() < MORNING_DUE:
        return {**_safe("morning_runtime_not_due"),
                "next_due_at": local.replace(hour=6, minute=45, second=0,
                                              microsecond=0).isoformat()}

    from modules.oom_sakkie.telegram_gateway import deliver_family_result
    deliver = deliver or deliver_family_result
    # A delayed provider tick still owns today's date-stable lifecycle. The
    # canonical claim prevents duplicate delivery, so infrastructure delay must
    # not turn the whole day into a permanent missed-window failure.

    from modules.oom_sakkie.daily_farm_manager import run_daily_farm_manager
    try:
        snapshot = _load_input_snapshot(tuple(row.telegram_user_id for row in recipients), now, source,
            herd_loader=herd_loader, rootline_loader=rootline_loader,
            litter_loader=litter_loader, sales_loader=sales_loader)
        outcomes = []
        for principal in recipients:
            # The same read-only canonical source contract is projected by the
            # specialist adapters in the recipient's language. No business
            # truth, task, claim or write is duplicated by this presentation.
            results, litters, sales = _project_input_snapshot(snapshot,
                principal.telegram_user_id, now, principal.language)
            outcomes.append(run_daily_farm_manager(
                owner_user_id=principal.telegram_user_id,
                chat_id=principal.private_chat_id, specialist_results=results,
                litter_rows=litters, sale_rows=sales, deliver=deliver, store=store,
                now=now, language=principal.language))
        summary = _recipient_summary(outcomes)
        optional_failures = list(snapshot.get("optional_source_failures") or ())
        if optional_failures:
            summary = {**summary,
                "optional_source_failure_count": len(optional_failures),
                "optional_source_failures": optional_failures}
        return summary
    except Exception as exc:
        return {**_safe("morning_runtime_recovery_pending", success=False),
                "failure_class": exc.__class__.__name__,
                "recovery_deadline_at": local.replace(
                    hour=7, minute=0, second=0, microsecond=0).isoformat()}


def reassess_current_brief_after_owner_answer(parsed, *, environ=None, deliver=None,
                                              store=None, herd_loader=None,
                                              rootline_loader=None,
                                              litter_loader=None, sales_loader=None,
                                              replace_brief=None):
    """Rebuild the shared current projection after one durable complete answer."""
    source = environ if environ is not None else os.environ
    owner = str(parsed.get("telegram_user_id") or "").strip()
    chat = str(parsed.get("telegram_chat_id") or "").strip()
    now = _aware(_provider_time(parsed.get("provider_timestamp")))
    principal = next((row for row in _configured_recipients(source)
                      if row.telegram_user_id == owner and row.private_chat_id == chat), None)
    if principal is None:
        return _safe("current_brief_owner_binding_denied", success=False)
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from modules.oom_sakkie.daily_farm_manager import run_daily_farm_manager
    results, litters, sales = _load_inputs(owner, now, source, language=principal.language,
        herd_loader=herd_loader, rootline_loader=rootline_loader,
        litter_loader=litter_loader, sales_loader=sales_loader)
    return run_daily_farm_manager(owner_user_id=owner, chat_id=chat,
        specialist_results=results, litter_rows=litters, sale_rows=sales,
        deliver=deliver or deliver_family_result, store=store, now=now,
        language=principal.language,
        replace_brief=replace_brief)


def start_production_morning_runtime(*, environ=None, runner=None):
    """Start one daemon per process; durable claims arbitrate scaled workers."""
    global _STARTED
    source = environ if environ is not None else os.environ
    explicitly = _truthy(source.get(ENABLED_ENV))
    if not explicitly or _truthy(source.get("OOM_SAKKIE_DAILY_MANAGER_RUNTIME_DISABLED")):
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


def _load_inputs(owner, now, source, *, language=None, herd_loader, rootline_loader,
                 litter_loader, sales_loader):
    snapshot = _load_input_snapshot(owner, now, source, herd_loader=herd_loader,
        rootline_loader=rootline_loader, litter_loader=litter_loader,
        sales_loader=sales_loader)
    return _project_input_snapshot(snapshot, owner, now,
        str(language or source.get("OOM_SAKKIE_DAILY_MANAGER_LANGUAGE") or "en"))


def _load_input_snapshot(owner, now, source, *, herd_loader, rootline_loader,
                         litter_loader, sales_loader):
    from modules.oom_sakkie.farm_manager_runtime import (
        _load_herdmaster_snapshot, _load_rootline_snapshot)
    injected_herd = herd_loader is not None
    injected_rootline = rootline_loader is not None
    if herd_loader is None or rootline_loader is None:
        herd_loader = herd_loader or (lambda: _load_herdmaster_snapshot(owner, now))
        rootline_loader = rootline_loader or (lambda: _load_rootline_snapshot(now))
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
        done, pending = wait(tuple(futures.values()),
                             timeout=OWNER_REQUEST_DEADLINE_SECONDS)
        if futures["herd"] not in done or futures["rootline"] not in done:
            raise TimeoutError("morning_runtime_specialist_deadline")
        herd = futures["herd"].result(); rootline = futures["rootline"].result()
        optional_source_failures = []
        litters = []
        if futures["litters"] in done:
            try:
                snapshot = futures["litters"].result()
                litters = ((snapshot.get("allocation_inputs") or {}).get("litter_rows") or [])
            except Exception as exc:
                optional_source_failures.append({
                    "source": "breeding_attention",
                    "failure_class": exc.__class__.__name__,
                })
        sales = []
        if futures["sales"] in done:
            try:
                payload, status = futures["sales"].result()
                if status == 200 and payload.get("success") is True:
                    sales = payload.get("sales_transactions") or []
            except Exception as exc:
                optional_source_failures.append({
                    "source": "sales_transactions",
                    "failure_class": exc.__class__.__name__,
                })
        for future in pending:
            future.cancel()
        return {"herd": herd, "rootline": rootline, "litters": tuple(litters),
                "sales": tuple(sales), "injected_herd": injected_herd,
                "injected_rootline": injected_rootline,
                "optional_source_failures": tuple(optional_source_failures)}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _project_input_snapshot(snapshot, owner, now, language):
    from modules.oom_sakkie.farm_manager_runtime import (
        _project_herdmaster_snapshot, _project_rootline_snapshot)
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    authority = issue_gateway_owner_authority(owner, owner)
    herd = (snapshot["herd"] if snapshot["injected_herd"] else
            _project_herdmaster_snapshot(snapshot["herd"], authority, owner, now, language))
    rootline = (snapshot["rootline"] if snapshot["injected_rootline"] else
                _project_rootline_snapshot(snapshot["rootline"], now, language))
    return [herd, rootline], list(snapshot["litters"]), list(snapshot["sales"])


def _escalate_failure(recipients, now, deliver, exc, *, store=None):
    from modules.oom_sakkie.daily_farm_manager import (
        daily_farm_manager_store, _owner_projection_identity)
    store = store or daily_farm_manager_store
    daily_identity = f"OOM-DAILY-FARM-MANAGER-{now.astimezone(SAST).date().isoformat()}"
    outcomes = []
    for principal in recipients:
        outcomes.append(_escalate_recipient_failure(principal, daily_identity, now,
            deliver, exc, store))
    return _recipient_summary(outcomes, failure=True)


def _escalate_recipient_failure(principal, daily_identity, now, deliver, exc, store):
    from modules.oom_sakkie.daily_farm_manager import (
        daily_farm_manager_store, _owner_projection_identity)
    owner = principal.telegram_user_id
    projection_identity = _owner_projection_identity(daily_identity, owner, owner)
    claim_id = projection_identity + ":DELIVERY"
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
    # Resume through the provider-attempt ledger on restart. That ledger sends
    # only if no attempt exists and refuses any ambiguous provider retry.
    if claim.get("created") is False and store is not daily_farm_manager_store:
        return {**_safe("morning_runtime_failure_replay_suppressed"),
                "failure_class": exc.__class__.__name__}
    identity = projection_identity + ":FAILURE"
    parsed = {"telegram_user_id": owner, "telegram_chat_id": owner,
              "provider_message_id": "scheduled:" + identity,
              "telegram_chat_type": "private", "output_language": principal.language,
              "provider_timestamp": now.isoformat(), "text": "Daily Farm Manager failure"}
    af = principal.language == "af"
    result = {"success": True, "status": "daily_manager_creation_failed",
              "answer": (("<b>OGGEND-PLAASPLAN NIE BESKIKBAAR NIE</b>\n\n"
                         "Oom Sakkie kon nie vandag se ondersteunde plaasbewyse saamstel nie. "
                         "Geen plaas- of hardeware-aksie is uitgevoer nie.") if af else
                         ("<b>Morning farm plan unavailable</b>\n\n"
                         "Oom Sakkie could not assemble today's supported farm evidence. "
                         "No farm or hardware action was taken.")),
              "hardware_commands": 0, "writes_farm_data": False}
    delivery = deliver(parsed, result, specialist="OOM_SAKKIE",
                       mission_id=identity, card_mission_id=projection_identity)
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


def _configured_recipients(source):
    from modules.oom_sakkie.family_access import configured_farm_manager_principals
    return configured_farm_manager_principals(source)


def _recipient_summary(outcomes, *, failure=False):
    rows = [dict(row) for row in outcomes]
    if len(rows) == 1:
        return rows[0]
    delivered = sum(int(row.get("telegram_sends") or 0) for row in rows)
    edited = sum(int(row.get("telegram_edits") or 0) for row in rows)
    success = bool(rows) and all(row.get("success") is True for row in rows)
    return {**_safe("morning_runtime_recipient_failure" if failure else
                    "morning_runtime_recipients_projected", success=success),
            "recipient_count": len(rows), "recipient_results": rows,
            "telegram_sends": delivered, "telegram_edits": edited}


def _safe(status, *, success=True):
    return {"success": success, "status": status, "telegram_sends": 0,
            "telegram_edits": 0, "hardware_commands": 0,
            "writes_farm_data": False, "protected_actions_performed": False}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _provider_time(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
