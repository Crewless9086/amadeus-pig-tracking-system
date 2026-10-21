"""Authenticated, zero-control projection of current ROOTLINE B evidence.

This composes existing canonical/provider rails.  It is not a status engine and
does not create a claim, eligibility record, cycle, command, or farm fact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract

CONTRACT_VERSION = "rootline_operational_evidence.v1"
MISSION_ID = "RMQ-20260813-04"
ZONE_ID = "B12345"


def build_rootline_operational_evidence(*, requester, requested_at=None,
                                        database_url=None, provider_reader=None):
    observed = requested_at or datetime.now(timezone.utc)
    revision = str(os.environ.get("RENDER_GIT_COMMIT") or "").strip().lower()
    revision = revision if re.fullmatch(r"[0-9a-f]{40}", revision) else "Unknown"
    database_url = str(database_url or os.environ.get("DATABASE_URL") or "").strip()
    audit = _audit(requester, observed, revision)
    if revision == "Unknown":
        return _failure("deployed_revision_unavailable", audit, revision), 503
    if not database_url:
        return _failure("canonical_evidence_unavailable", audit, revision), 503
    try:
        from modules.telemetry.rootline_owner_status import get_rootline_owner_status
        owner_status, owner_status_code = get_rootline_owner_status(
            database_url=database_url, now=observed)
        if owner_status_code != 200 or owner_status.get("success") is not True:
            raise RuntimeError("owner_status_unavailable")
        canonical = _read_canonical(database_url, observed)
    except Exception as exc:
        result = _failure("canonical_evidence_read_failed", audit, revision)
        result["error_type"] = exc.__class__.__name__
        return result, 503

    controller = _controller(provider_reader, observed)
    app_zone = next((row for row in owner_status.get("zones", [])
                     if row.get("zone_id") == ZONE_ID), {})
    status_bound = (owner_status.get("plan_generation") == canonical.get("evidence_generation")
        and owner_status.get("plan_identity") == canonical.get("result_id")
        and owner_status.get("operating_date") == canonical.get("operating_date"))
    recommendation = _recommendation(app_zone, canonical, status_bound=status_bound)
    evidence = {
        "success": True, "status": "operational_evidence_available",
        "contract_version": CONTRACT_VERSION, "mission_id": MISSION_ID,
        "mode": "read_only", "requested_revision": revision,
        "audit": audit, "recommendation": recommendation,
        "job": canonical["job"], "claim": canonical["claim"],
        "eligibility": canonical["eligibility"],
        "hold_reason": recommendation.get("hold_reason") or "Unknown",
        "latest_autonomous_cycle": canonical["cycle"],
        "controller": controller,
        "execution": canonical["execution"],
        "evidence_semantics": {
            "controller_state_proves_physical_flow": False,
            "physical_flow": canonical["execution"].get("physical_flow_confirmation") or "Unknown",
            "completion_requires": ["canonical completed event", "provider-confirmed OFF",
                                    "supported physical flow/outcome evidence"],
            "source_completion_is_b_irrigation_completion": False,
        },
        "channel_projection": {**canonical["channel_projection"],
            "application": {"decision": recommendation["decision"],
                            "source": "rootline_owner_status.v1"}},
        "safety": {"can_control": False, "control_routes_exposed": False,
                   "provider_control_calls": 0, "canonical_writes": 0,
                   "telegram_sends": 0, "worker_invocations": 0},
    }
    evidence["evidence_sha256"] = _digest({k: v for k, v in evidence.items()
                                            if k not in {"audit", "evidence_sha256"}})
    return evidence, 200


def _read_canonical(database_url, observed):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    with connect_bounded_rootline_postgres(database_url=database_url, read_only=True) as db:
        with db.cursor() as cur:
            cur.execute("set transaction isolation level repeatable read")
            cur.execute("select transaction_timestamp()")
            snapshot_cutoff = cur.fetchone()[0]
            operating_date = observed.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
            cur.execute("""select review_json->'rootline_reassessment',created_at
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_rootline_reassessment'
                  and review_json->'rootline_reassessment'->>'operating_date'=
                      (%s at time zone 'Africa/Johannesburg')::date::text
                order by created_at desc limit 1""", (observed,))
            row = cur.fetchone(); reassessment = _json(row[0]) if row else {}
            cur.execute("""select review_json->'rootline_execution',created_at
                from public.sam_live_stock_conversation_review_events
                where event_source='rootline_irrigation_execution'
                  and review_json->'rootline_execution'->>'zone_id'=%s
                order by created_at desc limit 200""", (ZONE_ID,))
            events = [({**_json(value), "recorded_at": created.isoformat()})
                      for value, created in cur.fetchall()]
            cur.execute("""select mission_id,status,expires_at,preview_digest,
                       evidence_generation,preview_payload,result_payload,
                       preview_card_message_id,created_at,completed_at
                from app_private.oom_protected_action_claims
                where action_kind='rootline_irrigation_segment' and mission_id=%s
                order by created_at desc limit 1""", (MISSION_ID,))
            claim_row = cur.fetchone()
    eligibility, bound = _bind_execution_events(events, operating_date)
    job_id = str(eligibility.get("job_id") or "")
    execution_id = str(eligibility.get("execution_id") or "")
    latest = bound[0] if bound else {}
    job_event = next((e for e in bound if e.get("job_id") == job_id), {})
    terminal = next((e for e in bound if e.get("action") in
                    {"record_completed", "contain_zone", "record_ambiguous_shutdown",
                     "record_claim_recovery"}), {})
    started = next((e for e in bound if e.get("action") in
                   {"claim_before_on", "mark_active", "record_on_outcome"}), {})
    reassessment_at = row[1] if row else None
    reassessment_fresh = _fresh(reassessment_at, observed, minutes=35)
    identity_bound = _identity_bound(eligibility, bound, reassessment)
    current_bound = identity_bound and reassessment_fresh
    if not current_bound:
        bound = []; job_event = {}; terminal = {}; started = {}; eligibility = {}
    claim = _claim(claim_row, observed)
    claim_bound = (current_bound and claim.get("job_id") == job_id
        and claim.get("execution_id") == execution_id
        and claim.get("eligibility_id") == eligibility.get("eligibility_id")
        and claim.get("eligibility_sha256") == eligibility.get("eligibility_sha256")
        and claim.get("segment_identity") == eligibility.get("segment_identity")
        and claim.get("evidence_generation") == reassessment.get("evidence_generation")
        and claim.get("observed_status") not in {"executing", "completed", "contained"})
    claim["binding_status"] = "current" if claim_bound else "Unknown"
    claim["replay_status"] = ("pending_exact_confirmation" if claim_bound
        and claim.get("observed_status") == "active" and claim.get("expired") is False
        else "non_replayable_or_unproven")
    return {
        "reassessment_fresh": reassessment_fresh,
        "reassessment_observed_at": reassessment_at.isoformat() if reassessment_at else "Unknown",
        "evidence_generation": reassessment.get("evidence_generation") or "Unknown",
        "result_id": reassessment.get("result_id") or "Unknown",
        "operating_date": reassessment.get("operating_date") or "Unknown",
        "job": _pick(job_event, ("job_id", "job_sha256", "state", "current_segment",
            "segment_number", "expected_segment_count", "requested_total_duration_seconds",
            "governed_executable_duration_seconds", "cumulative_verified_runtime_seconds",
            "remaining_seconds", "recorded_at")),
        "claim": claim,
        "eligibility": _pick(eligibility, ("eligibility_id", "eligibility_sha256", "status",
            "eligible", "reason", "operating_date", "segment_number", "recorded_at")),
        "cycle": {"identity": (reassessment.get("identity") or "Unknown") if reassessment_fresh else "Unknown",
            "result_id": (reassessment.get("result_id") or "Unknown") if reassessment_fresh else "Unknown",
            "trigger": (reassessment.get("trigger") or "Unknown") if reassessment_fresh else "Unknown",
            "recorded_at": (row[1].isoformat() if row else "Unknown"),
            "next_reassessment_at": ((reassessment.get("next_reassessment_at") or "Unknown")
                                     if reassessment_fresh else "Unknown"),
            "terminal_started": "Unknown",
            "snapshot_cutoff": snapshot_cutoff.isoformat()},
        "execution": _execution(latest, started, terminal),
        "channel_projection": {"telegram": {"delivery_state": reassessment.get("delivery_state") or "Unknown",
                "provider_message_id": str(reassessment.get("provider_message_id") or "Unknown"),
                "evidence_identity": reassessment.get("identity") or "Unknown"},
            "parity": "Unknown", "reason": "no independently content-bound Telegram projection rail"},
    }


def _controller(provider_reader, observed):
    contract = commissioned_irrigation_contract(ZONE_ID)
    result = {"zone_id": ZONE_ID, "device_id": contract["device_id"],
        "channel": contract["channel"], "mapping_sha256": contract["contract_sha256"],
        "commissioned": True, "provider": contract["provider"], "state": "Unknown",
        "observed_at": "Unknown", "provider_evidence_status": "Unavailable",
        "controller_state_proves_physical_flow": False, "provider_control_calls": 0}
    if provider_reader is None:
        return result
    try:
        readback = provider_reader(contract["device_id"])
        if readback.get("device_id") != contract["device_id"]:
            raise ValueError("provider_device_binding_mismatch")
        channels = ((readback.get("channels") or readback.get("switches"))
                    if isinstance(readback, dict) else None)
        matches = [row for row in channels or []
                   if int(row.get("outlet") or row.get("channel") or 0) == contract["channel"]]
        if len(matches) != 1:
            raise ValueError("provider_channel_binding_ambiguous")
        channel = matches[0]
        state = str(channel.get("output_state") or channel.get("switch")
                    or channel.get("state") or "").upper()
        if state not in {"ON", "OFF"}:
            raise ValueError("provider_channel_state_invalid")
        receipt_at = _time(readback.get("trusted_receipt_at") or readback.get("retrieved_at"))
        digest = str(readback.get("response_digest") or "")
        if not receipt_at or not _fresh(receipt_at, observed, minutes=5) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("provider_readback_freshness_or_digest_invalid")
        result.update({"state": state,
            "observed_at": receipt_at.isoformat(),
            "provider_evidence_status": "Available",
            "readback_digest": digest,
            "provider_control_calls": int(readback.get("provider_control_calls") or 0)})
        if result["provider_control_calls"] != 0:
            raise ValueError("provider_readback_reported_control_call")
    except Exception as exc:
        result.update({"provider_evidence_status": "Ambiguous",
                       "provider_error": exc.__class__.__name__, "state": "Unknown"})
    return result


def _claim(row, observed):
    if not row: return {"observed_status": "absent", "binding_status": "Unknown",
                        "replay_status": "non_replayable_or_unproven"}
    status = str(row[1] or "Unknown"); expiry = row[2]
    return {"mission_id": row[0], "observed_status": status,
        "expired": bool(expiry and expiry <= observed), "expires_at": expiry.isoformat() if expiry else "Unknown",
        "preview_digest": row[3] or "Unknown", "evidence_generation": row[4] or "Unknown",
        "job_id": (_json(row[5])).get("job_id") or "Unknown",
        "execution_id": (_json(row[5])).get("execution_id") or "Unknown",
        "eligibility_id": (_json(row[5])).get("eligibility_id") or "Unknown",
        "eligibility_sha256": (_json(row[5])).get("eligibility_sha256") or "Unknown",
        "segment_identity": (_json(row[5])).get("segment_identity") or "Unknown",
        "result_status": (_json(row[6])).get("status") or "Unknown",
        "card_message_id": str(row[7] or "Unknown"), "created_at": row[8].isoformat(),
        "completed_at": row[9].isoformat() if row[9] else "Unknown",
        "database_state_only": True}


def _execution(latest, started, terminal):
    objective = terminal.get("objective_evidence") or {}
    physical = objective.get("physical_flow_confirmation") or "Unknown"
    shutdown = terminal.get("shutdown_evidence") or {}
    stopped = (terminal.get("shutdown_verified") is True
               and shutdown.get("authoritative") is True
               and str(shutdown.get("state") or "").upper() == "OFF")
    segment_completed = (terminal.get("action") == "record_completed"
                         and terminal.get("objective_satisfied") is True and stopped)
    physical_completed = (segment_completed and terminal.get("job_completed") is True
        and physical not in {None, "", "Unknown", "Unavailable"})
    return {"execution_id": (latest or started).get("execution_id") or "Unknown",
        "state": terminal.get("state") or latest.get("state") or latest.get("action") or "Unknown",
        "latest_event_at": latest.get("recorded_at") or "Unknown",
        "start_supported": bool(started), "stop_supported": stopped,
        "control_segment_completion_supported": segment_completed,
        "b_irrigation_completion_supported": physical_completed,
        "physical_flow_confirmation": physical,
        "provider_output_state": shutdown.get("state") or "Unknown"}


def _bind_execution_events(events, operating_date):
    current = [e for e in events if str(e.get("operating_date") or "") == operating_date]
    eligibility = next((e for e in current if e.get("action") == "record_eligibility"), {})
    job_id = str(eligibility.get("job_id") or "")
    execution_id = str(eligibility.get("execution_id") or "")
    if not job_id or not execution_id:
        return eligibility, []
    bound = [e for e in current if e.get("job_id") == job_id
             and e.get("execution_id") == execution_id]
    return eligibility, bound


def _identity_bound(eligibility, bound, reassessment):
    if not eligibility or not bound:
        return False
    generation = str(reassessment.get("evidence_generation") or "")
    if not generation or str(eligibility.get("evidence_generation") or
                             eligibility.get("plan_generation") or "") != generation:
        return False
    keys = ("job_id", "job_sha256", "execution_id", "eligibility_id",
            "eligibility_sha256", "segment_identity", "segment_number")
    if any(eligibility.get(key) in {None, "", "Unknown"} for key in keys):
        return False
    for event in bound:
        for key in keys:
            if event.get(key) in {None, "", "Unknown"} or event.get(key) != eligibility.get(key):
                return False
    return True


def _recommendation(zone, canonical, *, status_bound):
    freshness = canonical.get("reassessment_fresh") is True and status_bound is True
    historical = str(zone.get("decision") or "Unknown")
    return {"zone_id": ZONE_ID, "zone_name": "B Camp",
        "decision": historical if freshness else "Unknown",
        "historical_decision": historical, "reason": zone.get("reason") or "Unknown",
        "hold_reason": zone.get("eligibility_blocker") or "Unknown",
        "observed_at": canonical.get("reassessment_observed_at") or "Unknown",
        "freshness": "fresh" if freshness else "stale_or_absent"}


def _audit(requester, observed, revision):
    requester = str(requester or "Unknown")
    material = {"contract": CONTRACT_VERSION, "requester": requester,
                "requested_at": observed.isoformat(), "revision": revision, "zone_id": ZONE_ID}
    return {**material, "audit_id": "ROOTLINE-READ-" + _digest(material)[:24].upper(),
            "audit_sink": "application_structured_log", "emitted": False}


def _failure(status, audit, revision):
    return {"success": False, "status": status, "contract_version": CONTRACT_VERSION,
        "mission_id": MISSION_ID, "mode": "read_only", "requested_revision": revision,
        "audit": audit, "safety": {"can_control": False, "provider_control_calls": 0,
        "canonical_writes": 0, "telegram_sends": 0, "worker_invocations": 0}}


def _json(value):
    if isinstance(value, dict): return value
    try: return json.loads(value) if value else {}
    except (TypeError, ValueError): return {}


def _pick(source, keys):
    return {key: source.get(key, "Unknown") for key in keys} if source else {"status": "absent"}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _fresh(value, observed, *, minutes):
    parsed = value if isinstance(value, datetime) else _time(value)
    if not parsed:
        return False
    age = observed.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
    return 0 <= age.total_seconds() <= minutes * 60
