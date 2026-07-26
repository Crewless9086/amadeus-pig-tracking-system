"""Protected, no-send ownership resolution for canonical owner work items."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV
from modules.sales.sam_owner_work_queue import (
    build_owner_work_observation,
    load_bounded_conversation_messages,
    record_owner_work_observation,
)


TABLE = "sam_owner_ownership_resolution_events"
SUPPORTED_MODES = {"HUMAN", "AUTO_GENERAL", "AUTO_SPECIALIST"}
NO_AUTHORITY = {
    "sends_customer_message": False,
    "calls_telegram": False,
    "creates_template": False,
    "creates_order": False,
    "reserves_stock": False,
    "mutates_business_state": False,
}


def resolve_owner_work_ownership(
    request: Mapping[str, Any],
    *,
    actor_id: str,
    environ: Mapping[str, str] | None = None,
    current_reader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    claim_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    result_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    writer: Callable[[str, str, Mapping[str, str]], Mapping[str, Any]] | None = None,
    transition_reader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    refresh_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Resolve one exact exception. Ownership change never implies a send."""
    source = environ if environ is not None else os.environ
    actor_id = _clean(actor_id, 200)
    if not actor_id:
        return _result("owner_identity_required"), 403
    packet, error = _packet(request)
    if error:
        return _result(error), 400
    reader = current_reader or read_current_resolution_evidence
    current, status = reader(packet, source)
    if status >= 400:
        return _result(current.get("status", "ownership_evidence_unavailable")), status
    mismatch = _binding_error(packet, current)
    if mismatch:
        return _result(mismatch), 409
    eligible, reason = _mode_eligible(packet["target_mode"], current, source)
    if not eligible:
        return _result(reason), 409

    resolution_id = _resolution_id(packet)
    claim = _event(
        resolution_id, "claim", packet, current, actor_id,
        outcome="claimed", prior_event_id="",
    )
    claim_recorder = claim_recorder or record_resolution_event
    claimed, claim_status = claim_recorder(claim)
    if claim_status >= 400:
        return _result(claimed.get("status", "ownership_claim_failed")), claim_status
    if claimed.get("created") is not True:
        return _result(
            "ownership_resolution_replay_withheld",
            resolution_id=resolution_id,
            replay_withheld=True,
        ), 200

    writer = writer or write_conversation_ownership
    try:
        write_result = writer(packet["conversation_id"], packet["target_mode"], source)
        if write_result.get("success") is not True:
            raise RuntimeError("chatwoot_ownership_write_unconfirmed")
    except Exception as exc:
        failure = _event(
            resolution_id, "result", packet, current, actor_id,
            outcome="write_failed", prior_event_id=claim["resolution_event_id"],
            reason=exc.__class__.__name__,
        )
        (result_recorder or record_resolution_event)(failure)
        return _result(
            "ownership_write_failed", resolution_id=resolution_id,
            ownership_changed=False, retry_automatically=False,
        ), 502

    # Re-read live evidence without comparing it to the superseded exception.
    refreshed, refreshed_status = (transition_reader or read_transition_resolution_evidence)(
        packet, source
    )
    refresh_error = "" if refreshed_status < 400 else refreshed.get("status", "refresh_failed")
    if not refresh_error and _clean(refreshed.get("ownership_mode")).upper() != packet["target_mode"]:
        refresh_error = "ownership_write_not_observed"
    if not refresh_error:
        refresh_error = _stable_transition_error(current, refreshed)
    if refresh_error:
        terminal = _event(
            resolution_id, "result", packet, current, actor_id,
            outcome="refresh_failed", prior_event_id=claim["resolution_event_id"],
            reason=refresh_error,
        )
        (result_recorder or record_resolution_event)(terminal)
        return _result(
            "ownership_result_evidence_incomplete",
            resolution_id=resolution_id, ownership_changed=True,
            retry_automatically=False,
        ), 503

    observation = refreshed.get("observation")
    if not isinstance(observation, Mapping):
        return _result(
            "ownership_refresh_observation_unavailable",
            resolution_id=resolution_id, ownership_changed=True,
            retry_automatically=False,
        ), 503
    persisted, persisted_status = (refresh_recorder or record_owner_work_observation)(observation)
    if persisted_status >= 400:
        terminal = _event(
            resolution_id, "result", packet, current, actor_id,
            outcome="refresh_persistence_failed",
            prior_event_id=claim["resolution_event_id"],
            reason="ownership_refresh_persistence_failed",
        )
        (result_recorder or record_resolution_event)(terminal)
        return _result(
            "ownership_refresh_persistence_failed",
            resolution_id=resolution_id, ownership_changed=True,
            retry_automatically=False,
        ), 503
    terminal = _event(
        resolution_id, "result", packet, refreshed, actor_id,
        outcome="succeeded", prior_event_id=claim["resolution_event_id"],
    )
    recorded, result_status = (result_recorder or record_resolution_event)(terminal)
    if result_status >= 400:
        return _result(
            "ownership_result_evidence_incomplete",
            resolution_id=resolution_id, ownership_changed=True,
            retry_automatically=False,
        ), 503
    return _result(
        "ownership_resolution_completed",
        resolution_id=resolution_id,
        ownership_changed=True,
        target_mode=packet["target_mode"],
        result_event_id=recorded.get("resolution_event_id"),
        refreshed_work_event_id=observation.get("work_event_id"),
        retry_automatically=False,
    ), 200


def read_current_resolution_evidence(
    packet: Mapping[str, Any], environ: Mapping[str, str]
) -> tuple[dict[str, Any], int]:
    """Bounded exact Chatwoot/read-model revalidation immediately before write."""
    latest, status = load_latest_exception(packet["work_item_id"])
    if status >= 400:
        return latest, status
    live, live_status = read_transition_resolution_evidence(packet, environ)
    if live_status >= 400:
        return live, live_status
    observation = live["observation"]
    persisted, persisted_error = _persisted_current_binding(latest)
    if persisted_error:
        return _result(persisted_error), 409
    fresh, fresh_error = _fresh_current_binding(observation)
    if fresh_error:
        return _result(fresh_error), 409
    for key in (
        "work_item_id", "work_event_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "observation_hash", "chronology_hash",
        "latest_inbound_message_id", "unanswered_count", "review_event_id",
        "window_evidence_hash", "classification",
    ):
        if persisted[key] != fresh[key]:
            return _result(f"ownership_current_{key}_mismatch"), 409
    result_fields = {
        "work_item_id": persisted["work_item_id"],
        "work_event_id": persisted["work_event_id"],
        "account_id": persisted["account_id"],
        "conversation_id": persisted["conversation_id"],
        "contact_id": persisted["contact_id"],
        "inbox_id": persisted["inbox_id"],
        "observation_hash": persisted["observation_hash"],
        "chronology_hash": persisted["chronology_hash"],
        "latest_inbound_message_id": persisted["latest_inbound_message_id"],
        "unanswered_count": persisted["unanswered_count"],
        "review_event_id": persisted["review_event_id"],
        "window_evidence_hash": persisted["window_evidence_hash"],
        "classification": persisted["classification"],
        "ownership_mode": fresh["ownership_mode"],
        "lane": fresh["lane"],
        "protected_markers": fresh["protected_markers"],
        "specialist_markers": fresh["specialist_markers"],
        "stable_evidence": live["stable_evidence"],
        "observation": _canonical_json_value(observation),
    }
    return _result("ownership_current_evidence_loaded", **result_fields), 200


def read_transition_resolution_evidence(
    packet: Mapping[str, Any], environ: Mapping[str, str]
) -> tuple[dict[str, Any], int]:
    """Build fresh post-write evidence without requiring old event/hash equality."""
    try:
        conversation = _read_exact_conversation(packet, environ)
        inbox = _read_exact_inbox(packet, environ)
    except Exception as exc:
        return _result(
            "ownership_chatwoot_conversation_unavailable",
            error_type=exc.__class__.__name__,
        ), 503
    history, history_status = load_bounded_conversation_messages(
        packet["conversation_id"], environ
    )
    if history_status >= 400 or history.get("evidence_complete") is not True:
        return _result("ownership_chronology_unavailable"), 503
    embedded = conversation.get("inbox")
    embedded = embedded if isinstance(embedded, Mapping) else {}
    embedded_id = _clean(embedded.get("id"))
    if embedded_id and embedded_id != packet["inbox_id"]:
        return _result("ownership_current_inbox_id_mismatch"), 409
    conversation = {
        **conversation,
        "inbox": {**inbox, **embedded, "id": packet["inbox_id"]},
        "messages": history["messages"],
    }
    from modules.sales.sam_live_stock_launch_control import (
        load_latest_sam_live_stock_review_events_for_conversations,
    )
    reviews, review_status = load_latest_sam_live_stock_review_events_for_conversations(
        [packet["conversation_id"]]
    )
    if review_status >= 400 or reviews.get("success") is not True:
        return _result("ownership_review_unavailable"), 503
    review = (reviews.get("events_by_conversation_id") or {}).get(
        packet["conversation_id"]
    ) or {}
    try:
        observation = build_owner_work_observation(
            conversation, review=review,
            reconciliation_actor_id="server:ownership-refresh",
        )
        stable = _stable_evidence(observation)
    except (TypeError, ValueError) as exc:
        return _result(
            "ownership_fresh_evidence_malformed", error_type=exc.__class__.__name__
        ), 409
    return _result(
        "ownership_transition_evidence_loaded",
        ownership_mode=_clean(observation.get("ownership_mode")).upper(),
        classification=_clean(observation.get("classification")),
        work_item_id=_clean(observation.get("work_item_id")),
        work_event_id=_clean(observation.get("work_event_id")),
        observation_hash=_clean(observation.get("observation_hash")),
        stable_evidence=stable,
        observation=_canonical_json_value(observation),
    ), 200


def recover_owner_work_ownership_observation(
    request: Mapping[str, Any],
    *,
    actor_id: str,
    environ: Mapping[str, str] | None = None,
    exception_reader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    transition_reader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    claim_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    result_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
    refresh_recorder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], int]] | None = None,
) -> tuple[dict[str, Any], int]:
    """Recover evidence after a confirmed write; this function has no writer rail."""
    source = environ if environ is not None else os.environ
    actor_id = _clean(actor_id, 200)
    if not actor_id:
        return _result("owner_identity_required"), 403
    packet, error = _packet(request)
    if error:
        return _result(error), 400
    persisted, status = (exception_reader or load_latest_exception)(
        packet["work_item_id"]
    )
    if status >= 400:
        return _result(persisted.get("status", "ownership_evidence_unavailable")), status
    binding, binding_error = _persisted_current_binding(persisted)
    if binding_error:
        return _result(binding_error), 409
    mismatch = _binding_error(packet, {**binding, "classification": persisted.get("classification")})
    if mismatch:
        return _result(mismatch), 409
    try:
        before_stable = _persisted_stable_evidence(persisted)
    except (TypeError, ValueError):
        return _result("ownership_persisted_stable_evidence_malformed"), 409
    live_reader = transition_reader or read_transition_resolution_evidence
    live, live_status = live_reader(packet, source)
    if live_status >= 400:
        return _result(live.get("status", "ownership_recovery_evidence_unavailable")), live_status
    if _clean(live.get("ownership_mode")).upper() != packet["target_mode"]:
        return _result("ownership_recovery_target_mode_not_current"), 409
    expected = {**binding, "stable_evidence": before_stable}
    stable_error = _stable_transition_error(expected, live)
    if stable_error:
        return _result(stable_error), 409

    recovery_id = f"SAM-OWNER-RECOVERY-{_digest([_resolution_id(packet), live['work_event_id']])[:24]}"
    claim = _event(
        recovery_id, "claim", packet, binding, actor_id,
        outcome="recovery_claimed", prior_event_id="",
    )
    recorder = claim_recorder or record_resolution_event
    claimed, claim_status = recorder(claim)
    if claim_status >= 400:
        return _result(claimed.get("status", "ownership_recovery_claim_failed")), claim_status
    if claimed.get("created") is not True:
        return _result(
            "ownership_recovery_replay_withheld",
            resolution_id=recovery_id, replay_withheld=True,
        ), 200

    # Close the claim/read race before appending the recovered observation.
    checked, checked_status = live_reader(packet, source)
    checked_error = (
        checked.get("status", "ownership_recovery_evidence_unavailable")
        if checked_status >= 400 else _stable_transition_error(expected, checked)
    )
    if not checked_error and checked.get("work_event_id") != live.get("work_event_id"):
        checked_error = "ownership_recovery_work_event_changed"
    if checked_error:
        failure = _event(
            recovery_id, "result", packet, binding, actor_id,
            outcome="recovery_failed", prior_event_id=claim["resolution_event_id"],
            reason=checked_error,
        )
        (result_recorder or record_resolution_event)(failure)
        return _result(
            "ownership_recovery_evidence_changed",
            resolution_id=recovery_id, retry_automatically=False,
        ), 409
    observation = checked.get("observation")
    if not isinstance(observation, Mapping):
        return _result("ownership_refresh_observation_unavailable"), 503
    persisted_result, persisted_status = (
        refresh_recorder or record_owner_work_observation
    )(observation)
    if persisted_status >= 400:
        failure = _event(
            recovery_id, "result", packet, binding, actor_id,
            outcome="recovery_persistence_failed",
            prior_event_id=claim["resolution_event_id"],
            reason="ownership_refresh_persistence_failed",
        )
        (result_recorder or record_resolution_event)(failure)
        return _result(
            "ownership_recovery_persistence_failed",
            resolution_id=recovery_id, retry_automatically=False,
        ), 503
    success = _event(
        recovery_id, "result", packet, checked, actor_id,
        outcome="recovered", prior_event_id=claim["resolution_event_id"],
    )
    recorded, result_status = (result_recorder or record_resolution_event)(success)
    if result_status >= 400:
        return _result("ownership_recovery_result_failed"), 503
    return _result(
        "ownership_recovery_completed",
        resolution_id=recovery_id,
        result_event_id=recorded.get("resolution_event_id"),
        refreshed_work_event_id=observation.get("work_event_id"),
        ownership_changed=False,
        retry_automatically=False,
    ), 200


def _stable_evidence(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical evidence which must not change merely because ownership changes."""
    bundle = observation.get("unanswered_inbound_bundle")
    if not isinstance(bundle, list):
        raise ValueError("unanswered_bundle_unavailable")
    fields = {
        key: observation.get(key)
        for key in (
            "account_id", "conversation_id", "contact_id", "inbox_id",
            "latest_message_id", "latest_message_at",
            "latest_inbound_message_id", "latest_outgoing_message_id",
            "unanswered_count", "review_event_id", "reviewed_inbound_message_id",
            "provider_identity_class", "window_state",
            "window_evidence_hash", "expires_at_utc",
        )
    }
    fields["unanswered_inbound_bundle"] = bundle
    canonical = _canonical_json_value(fields)
    if any(canonical.get(key) in (None, "") for key in (
        "account_id", "conversation_id", "contact_id", "inbox_id",
        "latest_inbound_message_id", "review_event_id",
        "provider_identity_class", "window_state", "window_evidence_hash",
    )):
        raise ValueError("stable_evidence_incomplete")
    canonical["message_chronology_digest"] = _digest({
        key: canonical[key] for key in (
            "account_id", "conversation_id", "contact_id", "inbox_id",
            "latest_message_id", "latest_message_at",
            "latest_inbound_message_id", "latest_outgoing_message_id",
            "unanswered_count", "unanswered_inbound_bundle",
        )
    })
    return canonical


def _persisted_stable_evidence(latest: Mapping[str, Any]) -> dict[str, Any]:
    bundle = latest.get("unanswered_inbound_bundle")
    if bundle is None:
        bundle = latest.get("unanswered_inbound_bundle_json")
    if isinstance(bundle, str):
        bundle = json.loads(bundle)
    synthetic = {
        key: latest.get(key) for key in (
            "account_id", "conversation_id", "contact_id", "inbox_id",
            "latest_message_id", "latest_message_at",
            "latest_inbound_message_id", "latest_outgoing_message_id",
            "unanswered_count", "review_event_id", "reviewed_inbound_message_id",
            "provider_identity_class", "window_state",
            "window_evidence_hash", "expires_at_utc",
        )
    }
    synthetic["unanswered_inbound_bundle"] = bundle
    return _stable_evidence(synthetic)


def _stable_transition_error(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> str:
    before_stable = before.get("stable_evidence")
    after_stable = after.get("stable_evidence")
    if not isinstance(before_stable, Mapping) or not isinstance(after_stable, Mapping):
        return "ownership_stable_evidence_unavailable"
    for key in sorted(set(before_stable) | set(after_stable)):
        if before_stable.get(key) != after_stable.get(key):
            return f"ownership_transition_{key}_changed"
    observation = after.get("observation")
    if not isinstance(observation, Mapping):
        return "ownership_refresh_observation_unavailable"
    if _clean(observation.get("work_item_id")) != _clean(before.get("work_item_id")):
        return "ownership_transition_work_item_id_changed"
    if _clean(observation.get("work_event_id")) == _clean(before.get("work_event_id")):
        return "ownership_transition_work_event_id_unchanged"
    if _clean(observation.get("observation_hash")) == _clean(before.get("observation_hash")):
        return "ownership_transition_observation_hash_unchanged"
    if _clean(observation.get("classification")) == "OWNERSHIP_DECISION_REQUIRED":
        return "ownership_exception_not_superseded"
    return ""


def _persisted_current_binding(
    latest: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if not isinstance(latest, Mapping):
        return {}, "ownership_persisted_evidence_malformed"
    text_fields = (
        "work_item_id", "work_event_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "observation_hash", "chronology_hash",
        "latest_inbound_message_id", "review_event_id",
        "window_evidence_hash", "classification",
    )
    if any(
        not isinstance(latest.get(key), str) or not latest.get(key).strip()
        for key in text_fields
    ):
        return {}, "ownership_persisted_evidence_incomplete"
    unanswered = latest.get("unanswered_count")
    if isinstance(unanswered, bool) or not isinstance(unanswered, int) or unanswered < 0:
        return {}, "ownership_persisted_evidence_malformed"
    binding = {key: latest[key].strip() for key in text_fields}
    binding["unanswered_count"] = unanswered
    try:
        return _canonical_json_value(binding), ""
    except (TypeError, ValueError):
        return {}, "ownership_persisted_evidence_malformed"


def _fresh_current_binding(
    observation: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if not isinstance(observation, Mapping):
        return {}, "ownership_fresh_evidence_malformed"
    text_fields = (
        "work_item_id", "work_event_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "observation_hash", "chronology_hash",
        "latest_inbound_message_id", "review_event_id",
        "window_evidence_hash", "classification", "ownership_mode", "lane",
    )
    if any(
        not isinstance(observation.get(key), str)
        or not observation.get(key).strip()
        for key in text_fields
    ):
        return {}, "ownership_fresh_evidence_incomplete"
    unanswered = observation.get("unanswered_count")
    if isinstance(unanswered, bool) or not isinstance(unanswered, int) or unanswered < 0:
        return {}, "ownership_fresh_evidence_malformed"
    for key in ("protected_markers", "specialist_markers"):
        value = observation.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            return {}, "ownership_fresh_evidence_malformed"
    binding = {key: observation[key].strip() for key in text_fields}
    binding.update({
        "unanswered_count": unanswered,
        "protected_markers": list(observation["protected_markers"]),
        "specialist_markers": list(observation["specialist_markers"]),
    })
    try:
        return _canonical_json_value(binding), ""
    except (TypeError, ValueError):
        return {}, "ownership_fresh_evidence_malformed"


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp_timezone_missing")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported_json_value:{type(value).__name__}")


def _read_exact_conversation(
    packet: Mapping[str, Any], environ: Mapping[str, str]
) -> dict[str, Any]:
    """Read the exact conversation without inventory-mode filtering."""
    base = _clean(environ.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240).rstrip("/")
    account = _clean(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
    token = _clean(environ.get("CHATWOOT_API_ACCESS_TOKEN") or environ.get("CHATWOOT_API_TOKEN"), 500)
    if not base or not account or not token or account != packet["account_id"]:
        raise RuntimeError("chatwoot_ownership_reader_not_configured")
    request = urllib_request.Request(
        f"{base}/api/v1/accounts/{urllib_parse.quote(account)}/conversations/{urllib_parse.quote(packet['conversation_id'])}",
        headers={"api_access_token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=8) as response:
            if int(response.status) != 200:
                raise RuntimeError("chatwoot_ownership_conversation_unavailable")
            row = json.loads(response.read().decode("utf-8"))
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError("chatwoot_ownership_conversation_unavailable") from exc
    if not isinstance(row, Mapping):
        raise RuntimeError("chatwoot_ownership_conversation_malformed")
    contact = row.get("contact") if isinstance(row.get("contact"), Mapping) else {}
    meta = row.get("meta") if isinstance(row.get("meta"), Mapping) else {}
    sender = meta.get("sender") if isinstance(meta.get("sender"), Mapping) else {}
    actual_contact = _clean(row.get("contact_id") or contact.get("id") or sender.get("id"))
    if (
        _clean(row.get("id")) != packet["conversation_id"]
        or _clean(row.get("inbox_id")) != packet["inbox_id"]
        or actual_contact != packet["contact_id"]
        or _clean(row.get("status")).lower() != "open"
    ):
        raise RuntimeError("chatwoot_ownership_identity_changed")
    return dict(row)


def _read_exact_inbox(
    packet: Mapping[str, Any], environ: Mapping[str, str]
) -> dict[str, Any]:
    base = _clean(environ.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240).rstrip("/")
    account = _clean(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
    token = _clean(environ.get("CHATWOOT_API_ACCESS_TOKEN") or environ.get("CHATWOOT_API_TOKEN"), 500)
    if not base or not account or not token or account != packet["account_id"]:
        raise RuntimeError("chatwoot_ownership_inbox_reader_not_configured")
    request = urllib_request.Request(
        f"{base}/api/v1/accounts/{urllib_parse.quote(account)}/inboxes/{urllib_parse.quote(packet['inbox_id'])}",
        headers={"api_access_token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=8) as response:
            if int(response.status) != 200:
                raise RuntimeError("chatwoot_ownership_inbox_unavailable")
            row = json.loads(response.read().decode("utf-8"))
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError("chatwoot_ownership_inbox_unavailable") from exc
    if not isinstance(row, Mapping) or _clean(row.get("id")) != packet["inbox_id"]:
        raise RuntimeError("chatwoot_ownership_inbox_identity_changed")
    return dict(row)


def load_latest_exception(
    work_item_id: str, *, database_url: str | None = None
) -> tuple[dict[str, Any], int]:
    database_url = _clean(database_url if database_url is not None else os.getenv(DATABASE_URL_ENV), 1000)
    if not database_url:
        return _result("ownership_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=8000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select work_event_id,work_item_id,account_id,conversation_id,
                           contact_id,inbox_id,observation_hash,chronology_hash,
                           latest_message_id,latest_message_at,
                           latest_inbound_message_id,latest_outgoing_message_id,
                           unanswered_inbound_bundle_json,unanswered_count,
                           review_event_id,classification,ownership_mode,
                           reviewed_inbound_message_id,provider_identity_class,
                           window_state,reply_authority_state,window_evidence_hash,
                           expires_at_utc
                    from public.sam_owner_work_item_events
                    where work_item_id=%s
                    order by observed_at desc,created_at desc,work_event_id desc
                    limit 1
                    """,
                    (_clean(work_item_id),),
                )
                row = cursor.fetchone()
                columns = [column.name for column in cursor.description]
        if not row:
            return _result("ownership_work_item_unavailable"), 404
        result = dict(zip(columns, row))
        if result["classification"] != "OWNERSHIP_DECISION_REQUIRED":
            return _result("ownership_exception_not_current"), 409
        return result, 200
    except Exception as exc:
        return _result("ownership_database_read_failed", error_type=exc.__class__.__name__), 503


def record_resolution_event(
    event: Mapping[str, Any], *, database_url: str | None = None
) -> tuple[dict[str, Any], int]:
    database_url = _clean(database_url if database_url is not None else os.getenv(DATABASE_URL_ENV), 1000)
    if not database_url:
        return _result("ownership_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=5,
            options="-c statement_timeout=8000 -c lock_timeout=2000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    insert into public.{TABLE} (
                      resolution_event_id,resolution_id,event_type,target_mode,
                      work_item_id,work_event_id,account_id,conversation_id,
                      contact_id,inbox_id,observation_hash,chronology_hash,
                      latest_inbound_message_id,unanswered_count,review_event_id,
                      window_evidence_hash,actor_id,outcome,reason,prior_event_id,
                      created_at,contains_customer_content,sends_customer_message,
                      calls_telegram,creates_template,mutates_business_state
                    ) values (
                      %(resolution_event_id)s,%(resolution_id)s,%(event_type)s,
                      %(target_mode)s,%(work_item_id)s,%(work_event_id)s,
                      %(account_id)s,%(conversation_id)s,%(contact_id)s,
                      %(inbox_id)s,%(observation_hash)s,%(chronology_hash)s,
                      %(latest_inbound_message_id)s,%(unanswered_count)s,
                      %(review_event_id)s,%(window_evidence_hash)s,%(actor_id)s,
                      %(outcome)s,%(reason)s,%(prior_event_id)s,
                      %(created_at)s::timestamptz,false,false,false,false,false
                    )
                    on conflict (resolution_event_id) do nothing
                    returning resolution_event_id
                    """,
                    dict(event),
                )
                created = cursor.fetchone()
            connection.commit()
        return _result(
            "ownership_resolution_event_recorded" if created else "ownership_resolution_event_replay_withheld",
            created=bool(created), resolution_event_id=event["resolution_event_id"],
        ), 201 if created else 200
    except Exception as exc:
        return _result("ownership_resolution_event_failed", error_type=exc.__class__.__name__), 503


def write_conversation_ownership(
    conversation_id: str, target_mode: str, environ: Mapping[str, str]
) -> Mapping[str, Any]:
    base = _clean(environ.get("CHATWOOT_BASE_URL") or "https://app.chatwoot.com", 240).rstrip("/")
    account = _clean(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
    token = _clean(environ.get("CHATWOOT_API_ACCESS_TOKEN") or environ.get("CHATWOOT_API_TOKEN"), 500)
    if not base or not account or not token:
        raise RuntimeError("chatwoot_ownership_writer_not_configured")
    request = urllib_request.Request(
        f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}/custom_attributes",
        data=json.dumps({"custom_attributes": {"conversation_mode": target_mode}}).encode(),
        headers={"api_access_token": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=8) as response:
            if int(response.status) not in {200, 201}:
                raise RuntimeError("chatwoot_ownership_write_unconfirmed")
            return {"success": True, "status_code": int(response.status)}
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("chatwoot_ownership_write_failed") from exc


def _packet(value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Mapping):
        return {}, "ownership_request_invalid"
    keys = (
        "work_item_id", "work_event_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "observation_hash", "chronology_hash",
        "latest_inbound_message_id", "review_event_id", "window_evidence_hash",
        "target_mode",
    )
    packet = {key: _clean(value.get(key), 200) for key in keys}
    try:
        packet["unanswered_count"] = int(value.get("unanswered_count"))
    except (TypeError, ValueError):
        return {}, "ownership_unanswered_count_invalid"
    if any(not packet[key] for key in keys):
        return {}, "ownership_binding_incomplete"
    packet["target_mode"] = packet["target_mode"].upper()
    if packet["target_mode"] not in SUPPORTED_MODES:
        return {}, "ownership_mode_unsupported"
    if packet["unanswered_count"] < 0:
        return {}, "ownership_unanswered_count_invalid"
    return packet, ""


def _binding_error(packet: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    for key in (
        "work_item_id", "work_event_id", "account_id", "conversation_id",
        "contact_id", "inbox_id", "observation_hash", "chronology_hash",
        "latest_inbound_message_id", "unanswered_count", "review_event_id",
        "window_evidence_hash",
    ):
        if str(packet.get(key)) != str(current.get(key)):
            return f"ownership_{key}_changed"
    if current.get("classification") != "OWNERSHIP_DECISION_REQUIRED":
        return "ownership_exception_not_current"
    return ""


def _mode_eligible(
    mode: str, current: Mapping[str, Any], environ: Mapping[str, str]
) -> tuple[bool, str]:
    if mode == "HUMAN":
        return True, ""
    if current.get("protected_markers"):
        return False, "ownership_protected_policy_forbids_automatic_mode"
    if mode == "AUTO_GENERAL":
        if current.get("lane") != "GENERAL":
            return False, "ownership_general_lane_ineligible"
        enabled = _truthy(environ.get("SAM_AUTO_GENERAL_OWNERSHIP_ENABLED"))
    else:
        if current.get("lane") != "SPECIALIST" or not current.get("specialist_markers"):
            return False, "ownership_specialist_lane_ineligible"
        enabled = _truthy(environ.get("SAM_AUTO_SPECIALIST_OWNERSHIP_ENABLED"))
    return (True, "") if enabled else (False, "ownership_policy_eligibility_unavailable")


def _resolution_id(packet: Mapping[str, Any]) -> str:
    digest = _digest({
        "work_item_id": packet["work_item_id"],
        "work_event_id": packet["work_event_id"],
        "observation_hash": packet["observation_hash"],
        "target_mode": packet["target_mode"],
    })
    return f"SAM-OWNER-RESOLUTION-{digest[:24]}"


def _event(
    resolution_id: str, event_type: str, packet: Mapping[str, Any],
    current: Mapping[str, Any], actor_id: str, *, outcome: str,
    prior_event_id: str, reason: str = "",
) -> dict[str, Any]:
    event_id = f"SAM-OWNER-RESOLUTION-EVENT-{_digest([resolution_id, event_type])[:24]}"
    return {
        "resolution_event_id": event_id, "resolution_id": resolution_id,
        "event_type": event_type, "target_mode": packet["target_mode"],
        **{key: packet[key] for key in (
            "work_item_id", "work_event_id", "account_id", "conversation_id",
            "contact_id", "inbox_id", "observation_hash", "chronology_hash",
            "latest_inbound_message_id", "unanswered_count", "review_event_id",
            "window_evidence_hash",
        )},
        "actor_id": actor_id, "outcome": outcome, "reason": _clean(reason),
        "prior_event_id": prior_event_id or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contains_customer_content": False, **NO_AUTHORITY,
    }


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest().upper()


def _clean(value: Any, limit: int = 160) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _result(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "success": status in {
            "ownership_resolution_completed",
            "ownership_resolution_replay_withheld",
            "ownership_resolution_event_recorded",
            "ownership_resolution_event_replay_withheld",
            "ownership_current_evidence_loaded",
            "ownership_transition_evidence_loaded",
            "ownership_recovery_completed",
            "ownership_recovery_replay_withheld",
        },
        "status": status, **extra, **NO_AUTHORITY,
    }
