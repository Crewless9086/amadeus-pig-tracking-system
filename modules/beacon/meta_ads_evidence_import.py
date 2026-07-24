"""Owner-approved append-only import for bounded Meta Ads evidence packets."""

from base64 import urlsafe_b64encode
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import os

from modules.beacon.meta_ads_insights_preview import (
    build_meta_ads_insights_preview,
)


DATABASE_URL_ENV = "DATABASE_URL"
PACKET_TTL_SECONDS = 600
IMPORT_SOURCE = "meta_ads_insights"
IMPORT_MODE = "beacon_meta_ads_owner_approved_append_only_import"
_METRIC_NAMES = (
    "spend", "reach", "impressions", "clicks", "inline_link_clicks",
)
_SAFE_EVIDENCE_STATES = {"verified", "missing", "unsupported"}
AUTHORITY = {
    "automatic_import": False,
    "owner_approved_evidence_append_only": True,
    "updates_existing_evidence": False,
    "deletes_existing_evidence": False,
    "calls_meta_write": False,
    "creates_or_updates_campaigns": False,
    "creates_or_updates_ads": False,
    "publishes_content": False,
    "sends_customer_messages": False,
    "spends_money": False,
    "changes_budget_or_payment": False,
    "writes_business_or_farm_data": False,
}
SIGNING_DIAGNOSTICS = {
    "stable_signing_source_required": True,
    "stable_signing_source_configured": False,
    "configured_secret_exposed": False,
    "derived_signing_key_exposed": False,
    "process_local_fallback_enabled": False,
    "cross_worker_validation_supported": False,
}
COMPATIBILITY_PLACEHOLDER_FIELDS = (
    "reactions",
    "comments",
    "shares",
    "messages_to_sam",
    "qualified_buyer_leads",
    "booking_review_requests",
)


def prepare_meta_ads_import_packet(
    *,
    start_date,
    end_date,
    level="ad",
    preview_builder=None,
    database_url=None,
    connect_factory=None,
    now=None,
):
    """Prepare a signed exact packet; performs Meta/DB reads but no writes."""
    now_dt = _now(now)
    signing_key = _stable_signing_key()
    if signing_key is None:
        return _signing_unavailable(), 503
    preview_builder = preview_builder or build_meta_ads_insights_preview
    preview, preview_http_status = preview_builder(
        start_date=start_date, end_date=end_date, level=level
    )
    if preview_http_status != 200 or preview.get("status") != "preview_ready":
        return {
            "success": False,
            "status": "meta_preview_not_importable",
            "preview_status": preview.get("status"),
            "preview_http_status": preview_http_status,
            "blockers": list(preview.get("blockers") or []),
            "packet_prepared": False,
            **AUTHORITY,
        }, 409

    candidates, exclusions = _import_candidates(preview)
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return _unavailable("database_not_configured"), 503
    try:
        with _connect(database_url, connect_factory) as connection:
            existing, total_rows, legacy_rows = _existing_state(
                connection, [item["logical_snapshot_key"] for item in candidates]
            )
    except Exception as exc:
        return _database_failure("prepare_read_failed", exc), 500

    planned = _plan_dispositions(candidates, existing)
    prepared_at = now_dt.isoformat()
    expires_at = (now_dt + timedelta(seconds=PACKET_TTL_SECONDS)).isoformat()
    packet = {
        "schema_version": "beacon_meta_import_packet_v1",
        "mode": IMPORT_MODE,
        "reporting_window": deepcopy(preview.get("reporting_window") or {}),
        "retrieved_at": str(preview.get("retrieved_at") or ""),
        "prepared_at": prepared_at,
        "expires_at": expires_at,
        "currency": deepcopy(preview.get("account_currency") or {}),
        "items": planned,
        "exclusions": exclusions,
        "database_snapshot": {
            "total_performance_rows": total_rows,
            "legacy_row_count": legacy_rows,
            "existing_matching_snapshot_count": len(existing),
        },
        "authority": dict(AUTHORITY),
    }
    packet_hash = _packet_hash(packet)
    signature = _packet_signature(packet_hash, expires_at, signing_key)
    counts = _packet_counts(planned, exclusions)
    return {
        "success": True,
        "status": "meta_import_packet_prepared",
        "packet_prepared": True,
        "packet": packet,
        "packet_hash": packet_hash,
        "approval_signature": signature,
        "approval_expires_at": expires_at,
        "approval_requires_exact_hash": True,
        "signing": _signing_diagnostics(True),
        "compatibility_placeholder_fields": list(
            COMPATIBILITY_PLACEHOLDER_FIELDS
        ),
        **counts,
        **AUTHORITY,
    }, 200


def execute_meta_ads_import_packet(
    payload,
    *,
    database_url=None,
    connect_factory=None,
    now=None,
):
    """Append the exact owner-approved signed packet; never updates/deletes."""
    payload = payload if isinstance(payload, dict) else {}
    signing_key = _stable_signing_key()
    if signing_key is None:
        return _signing_unavailable(), 503
    packet = payload.get("packet") if isinstance(payload.get("packet"), dict) else {}
    supplied_hash = str(payload.get("packet_hash") or "").strip()
    approved_hash = str(payload.get("approved_packet_hash") or "").strip()
    signature = str(payload.get("approval_signature") or "").strip()
    if payload.get("owner_approved") is not True:
        return _rejected("owner_exact_packet_approval_required"), 403
    exact_hash = _packet_hash(packet)
    if not supplied_hash or not hmac.compare_digest(supplied_hash, exact_hash):
        return _rejected("packet_hash_mismatch"), 409
    if not approved_hash or not hmac.compare_digest(approved_hash, exact_hash):
        return _rejected("approved_packet_hash_mismatch"), 409
    expires_at = str(packet.get("expires_at") or "")
    if not _valid_signature(exact_hash, expires_at, signature, signing_key):
        return _rejected("packet_signature_invalid"), 409
    expiry = _parse_time(expires_at)
    if expiry is None or _now(now) >= expiry:
        return _rejected("packet_expired"), 409
    if packet.get("schema_version") != "beacon_meta_import_packet_v1":
        return _rejected("packet_schema_unsupported"), 409
    items = packet.get("items") if isinstance(packet.get("items"), list) else []
    if any(not _valid_planned_item(item) for item in items):
        return _rejected("packet_item_invalid"), 409

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return _unavailable("database_not_configured"), 503
    try:
        with _connect(database_url, connect_factory) as connection:
            logical_keys = [item["logical_snapshot_key"] for item in items]
            existing, total_before, legacy_before = _existing_state(
                connection, logical_keys
            )
            database_snapshot = packet.get("database_snapshot") or {}
            if (
                total_before != database_snapshot.get("total_performance_rows")
                or legacy_before != database_snapshot.get("legacy_row_count")
            ):
                connection.rollback()
                return _rejected("packet_database_state_changed"), 409
            replanned = _plan_dispositions(
                [_candidate_from_planned(item) for item in items], existing
            )
            if _disposition_projection(replanned) != _disposition_projection(items):
                connection.rollback()
                return _rejected("packet_database_state_changed"), 409
            batch_id = "BEACON-META-BATCH-" + exact_hash[:24].upper()
            created_count = 0
            duplicate_count = 0
            with connection.cursor() as cursor:
                for item in items:
                    if item["disposition"] == "duplicate":
                        duplicate_count += 1
                        continue
                    params = _insert_params(item, batch_id, exact_hash)
                    cursor.execute(_INSERT_SQL, params)
                    if cursor.rowcount != 1:
                        connection.rollback()
                        return _rejected("append_conflict_detected"), 409
                    created_count += 1
                cursor.execute(
                    "select count(*) from public.beacon_campaign_performance_events"
                )
                total_after = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    select count(*) from public.beacon_campaign_performance_events
                    where coalesce(evidence_source, 'legacy_unlabelled')
                          <> 'meta_ads_insights'
                    """
                )
                legacy_after = int(cursor.fetchone()[0])
            if legacy_after != legacy_before or total_after != total_before + created_count:
                connection.rollback()
                return _rejected("append_only_reconciliation_failed"), 409
            connection.commit()
    except Exception as exc:
        return _database_failure("execute_append_failed", exc), 500

    return {
        "success": True,
        "status": "meta_evidence_import_appended",
        "import_batch_id": batch_id,
        "packet_hash": exact_hash,
        "created_count": created_count,
        "duplicate_withheld_count": duplicate_count,
        "legacy_rows_before": legacy_before,
        "legacy_rows_after": legacy_after,
        "legacy_rows_untouched": legacy_before == legacy_after,
        "rollback_mode": "append_owner_approved_correction_or_exclusion_never_update_delete",
        "incorrect_batch_plan": incorrect_batch_exclusion_plan(
            batch_id,
            [
                item["performance_event_id"]
                for item in items if item["disposition"] != "duplicate"
            ],
        ),
        "signing": _signing_diagnostics(True),
        "compatibility_placeholder_fields": list(
            COMPATIBILITY_PLACEHOLDER_FIELDS
        ),
        **AUTHORITY,
    }, 201 if created_count else 200


def _import_candidates(preview):
    candidates, exclusions = [], []
    currency = preview.get("account_currency") or {}
    if currency.get("status") != "verified" or not currency.get("value"):
        return [], [{"reason": "verified_currency_required"}]
    for index, event in enumerate(preview.get("proposed_append_only_events") or []):
        reason = _event_exclusion_reason(event)
        if reason:
            exclusions.append({"event_index": index, "reason": reason})
            continue
        identity = event.get("identity") or {}
        window = event.get("reporting_window") or {}
        logical_seed = {
            "source": IMPORT_SOURCE,
            "level": event.get("level"),
            "campaign_id": identity.get("campaign_id"),
            "adset_id": identity.get("adset_id"),
            "ad_id": identity.get("ad_id"),
            "start": window.get("start"),
            "end": window.get("end"),
        }
        logical_key = "META-LOGICAL-" + _digest(logical_seed)[:32].upper()
        evidence = {
            "metrics": {
                name: deepcopy((event.get("metrics") or {}).get(name) or {})
                for name in _METRIC_NAMES
            },
            "actions": deepcopy(event.get("actions") or {}),
            "attribution": deepcopy(event.get("attribution") or {}),
            "currency": deepcopy(event.get("currency") or currency),
            "qualified_buyer_leads": deepcopy(
                event.get("qualified_buyer_leads") or {}
            ),
            "orders": deepcopy(event.get("orders") or {}),
            "sales": deepcopy(event.get("sales") or {}),
            "revenue": deepcopy(event.get("revenue") or {}),
        }
        content_seed = {
            "logical_snapshot_key": logical_key,
            "evidence": _without_retrieval_times(evidence),
        }
        content_digest = _digest(content_seed)
        snapshot_key = "META-SNAPSHOT-" + content_digest[:32].upper()
        candidates.append({
            "logical_snapshot_key": logical_key,
            "source_snapshot_key": snapshot_key,
            "performance_event_id": "BEACON-PERF-" + content_digest[:24].upper(),
            "source_reference": str(event.get("source_reference") or ""),
            "retrieved_at": str(event.get("retrieved_at") or ""),
            "reporting_window": deepcopy(window),
            "level": str(event.get("level") or ""),
            "identity": deepcopy(identity),
            "currency": deepcopy(event.get("currency") or currency),
            "evidence": evidence,
            "content_digest": content_digest,
        })
    return candidates, exclusions


def _event_exclusion_reason(event):
    if not isinstance(event, dict):
        return "malformed_event"
    if event.get("source") != IMPORT_SOURCE:
        return "unaccepted_source"
    if not event.get("source_reference") or not _parse_time(event.get("retrieved_at")):
        return "provenance_incomplete"
    identity = event.get("identity") or {}
    if not event.get("level") or not any(identity.values()):
        return "identity_incomplete"
    attribution = event.get("attribution") or {}
    if attribution.get("status") not in {"verified", "unsupported", "missing"}:
        return "attribution_unusable"
    for name in _METRIC_NAMES:
        metric = (event.get("metrics") or {}).get(name) or {}
        if metric.get("status") not in _SAFE_EVIDENCE_STATES:
            return f"{name}_evidence_unusable"
        if metric.get("status") == "verified" and (
            metric.get("value") is None
            or not metric.get("source")
            or not metric.get("source_reference")
            or not _parse_time(metric.get("retrieved_at"))
        ):
            return f"{name}_provenance_incomplete"
    for name in ("spend", "reach", "impressions"):
        if ((event.get("metrics") or {}).get(name) or {}).get("status") != "verified":
            return f"{name}_required_scalar_evidence_not_verified"
    actions = event.get("actions") or {}
    if actions.get("status") not in {"verified", "missing"}:
        return "actions_evidence_unusable"
    for action in actions.get("items") or []:
        if (
            not isinstance(action, dict)
            or action.get("classification") != "meta_reported_action_only"
            or action.get("status") != "verified"
            or not action.get("action_type")
            or action.get("value") is None
        ):
            return "actions_evidence_unusable"
    for unsupported_name in (
        "qualified_buyer_leads", "orders", "sales", "revenue",
    ):
        if (event.get(unsupported_name) or {}).get("status") != "unsupported":
            return f"{unsupported_name}_must_remain_unsupported"
    return ""


def _existing_state(connection, logical_keys):
    existing = []
    with connection.cursor() as cursor:
        if logical_keys:
            cursor.execute(
                """
                select performance_event_id, source_snapshot_key,
                       supersedes_event_id, metric_evidence, created_at
                from public.beacon_campaign_performance_events
                where evidence_source = 'meta_ads_insights'
                  and metric_evidence->'spend_amount'->'meta_import'
                      ->>'logical_snapshot_key'
                      = any(%(logical_keys)s)
                order by created_at asc
                """,
                {"logical_keys": logical_keys},
            )
            existing = [
                {
                    "performance_event_id": row[0],
                    "source_snapshot_key": row[1],
                    "supersedes_event_id": row[2] or "",
                    "metric_evidence": row[3] or {},
                    "created_at": (
                        row[4].isoformat()
                        if hasattr(row[4], "isoformat") else str(row[4] or "")
                    ),
                }
                for row in cursor.fetchall()
            ]
        cursor.execute(
            "select count(*) from public.beacon_campaign_performance_events"
        )
        total_rows = int(cursor.fetchone()[0])
        cursor.execute(
            """
            select count(*) from public.beacon_campaign_performance_events
            where coalesce(evidence_source, 'legacy_unlabelled')
                  <> 'meta_ads_insights'
            """
        )
        legacy_rows = int(cursor.fetchone()[0])
    return existing, total_rows, legacy_rows


def _plan_dispositions(candidates, existing):
    by_logical = {}
    for row in existing:
        logical = (
            (
                (row.get("metric_evidence") or {}).get("spend_amount") or {}
            ).get("meta_import") or {}
        ).get("logical_snapshot_key")
        if logical:
            by_logical.setdefault(logical, []).append(row)
    planned = []
    for candidate in candidates:
        prior = by_logical.get(candidate["logical_snapshot_key"], [])
        exact = next(
            (
                row for row in prior
                if row.get("source_snapshot_key")
                == candidate["source_snapshot_key"]
            ),
            None,
        )
        item = deepcopy(candidate)
        if exact:
            item["disposition"] = "duplicate"
            item["existing_event_id"] = exact["performance_event_id"]
            item["supersedes_event_id"] = ""
        elif prior:
            superseded = {row.get("supersedes_event_id") for row in prior}
            leaf = next(
                (
                    row for row in reversed(prior)
                    if row.get("performance_event_id") not in superseded
                ),
                prior[-1],
            )
            item["disposition"] = "correction"
            item["existing_event_id"] = ""
            item["supersedes_event_id"] = leaf["performance_event_id"]
        else:
            item["disposition"] = "insert"
            item["existing_event_id"] = ""
            item["supersedes_event_id"] = ""
        planned.append(item)
    return planned


def _insert_params(item, batch_id, packet_hash):
    metrics = item["evidence"]["metrics"]
    meta_import = {
        "schema_version": "beacon_meta_import_evidence_v1",
        "batch_id": batch_id,
        "packet_hash": packet_hash,
        "logical_snapshot_key": item["logical_snapshot_key"],
        "content_digest": item["content_digest"],
        "level": item["level"],
        "identity": item["identity"],
        "reporting_window": item["reporting_window"],
        "disposition": item["disposition"],
    }
    event_evidence = item["evidence"]
    metrics = event_evidence["metrics"]
    evidence = {
        "spend_amount": deepcopy(metrics.get("spend") or {}),
        "reach": deepcopy(metrics.get("reach") or {}),
        "impressions": deepcopy(metrics.get("impressions") or {}),
        "clicks": deepcopy(metrics.get("clicks") or {}),
        "inline_link_clicks": deepcopy(
            metrics.get("inline_link_clicks") or {}
        ),
    }
    evidence["spend_amount"]["metric"] = "spend_amount"
    provenance = {
        "source": IMPORT_SOURCE,
        "source_reference": item["source_reference"],
        "retrieved_at": item["retrieved_at"],
    }
    for name in COMPATIBILITY_PLACEHOLDER_FIELDS:
        if name == "qualified_buyer_leads":
            placeholder_evidence = deepcopy(event_evidence.get(name) or {
                "status": "unsupported", "value": None,
            })
        else:
            placeholder_evidence = {"status": "missing", "value": None}
        evidence[name] = {
            **placeholder_evidence,
            **provenance,
            "compatibility_placeholder": {
                "scalar_column": name,
                "stored_value": 0,
                "evidentiary": False,
                "reason": "database_not_null_compatibility_only",
            },
        }
    for name in ("qualified_buyer_leads", "orders", "sales", "revenue"):
        if name not in evidence:
            evidence[name] = {
                **deepcopy(event_evidence.get(name) or {
                    "status": "unsupported", "value": None,
                }),
                **provenance,
            }
    # Non-metric Meta context is nested on one real metric so existing
    # per-metric consumers never mistake metadata/actions for rankable values.
    evidence["spend_amount"].update({
        "meta_import": meta_import,
        "meta_reported_actions": deepcopy(event_evidence["actions"]),
        "attribution": deepcopy(event_evidence["attribution"]),
        "currency": deepcopy(event_evidence["currency"]),
    })
    return {
        "performance_event_id": item["performance_event_id"],
        "measurement_window": (
            f"{item['reporting_window'].get('start')}/"
            f"{item['reporting_window'].get('end')} level={item['level']}"
        ),
        "spend_amount": _verified_value(metrics.get("spend"), 0),
        "spend_currency": item["currency"].get("value") or "",
        "reach": _verified_value(metrics.get("reach"), 0),
        "impressions": _verified_value(metrics.get("impressions"), 0),
        "metric_evidence_json": json.dumps(evidence, sort_keys=True),
        "source_reference": item["source_reference"],
        "retrieved_at": item["retrieved_at"],
        "source_snapshot_key": item["source_snapshot_key"],
        "supersedes_event_id": item.get("supersedes_event_id") or None,
        "recorded_by": batch_id[:120],
    }


_INSERT_SQL = """
insert into public.beacon_campaign_performance_events (
    performance_event_id, mode, manual_post_event_id, publish_packet_id,
    channel, measurement_window, spend_amount, spend_currency, reach,
    impressions, reactions, comments, shares, messages_to_sam,
    qualified_buyer_leads, booking_review_requests, notes,
    recommended_action, recommendation_reason, recommended_spend_amount,
    recommended_duration_days, max_spend_cap_amount, records_evidence,
    recommends_boost, boost_requires_owner_approval, sends_customer_message,
    posts_publicly, calls_chatwoot, calls_meta, calls_n8n, boosts_post,
    spends_money, creates_quote, creates_invoice, creates_order, changes_stock,
    reserves_stock, dispatch_enabled, changes_runtime_now, changes_prompt_now,
    physical_controls_enabled, customer_public_output_enabled,
    writes_farm_data, recorded_by, metric_evidence, evidence_source,
    source_reference, retrieved_at, source_snapshot_key, supersedes_event_id
) values (
    %(performance_event_id)s, 'beacon_campaign_performance_evidence_only',
    '', '', 'Facebook', %(measurement_window)s, %(spend_amount)s,
    %(spend_currency)s, %(reach)s, %(impressions)s, 0, 0, 0, 0, 0, 0,
    'Meta Ads evidence; actions are Meta-reported actions only.',
    'wait_for_more_data',
    'Qualified leads, orders, sales and revenue require SAM/order attribution.',
    0, 0, 500, true, false, true, false, false, false, false, false, false,
    false, false, false, false, false, false, false, false, false, false,
    false, false, %(recorded_by)s, %(metric_evidence_json)s::jsonb,
    'meta_ads_insights', %(source_reference)s, %(retrieved_at)s::timestamptz,
    %(source_snapshot_key)s, %(supersedes_event_id)s
)
on conflict (performance_event_id) do nothing
"""


def _packet_hash(packet):
    return sha256(_canonical(packet)).hexdigest()


def _packet_signature(packet_hash, expires_at, signing_key):
    digest = hmac.new(
        signing_key,
        f"{packet_hash}|{expires_at}".encode("utf-8"),
        sha256,
    ).digest()
    return urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _stable_signing_key(environ=None):
    source = environ if hasattr(environ, "get") else os.environ
    configured = str(
        source.get("OWNER_SESSION_SECRET") or source.get("SECRET_KEY") or ""
    ).strip()
    if not configured:
        return None
    return hmac.new(
        configured.encode("utf-8"),
        b"beacon-meta-import-packet-v1",
        sha256,
    ).digest()


def _valid_signature(packet_hash, expires_at, signature, signing_key):
    expected = _packet_signature(packet_hash, expires_at, signing_key)
    return bool(signature) and hmac.compare_digest(signature, expected)


def _packet_counts(items, exclusions):
    counts = {"insert": 0, "duplicate": 0, "correction": 0}
    for item in items:
        disposition = item.get("disposition")
        if disposition in counts:
            counts[disposition] += 1
    return {
        "proposed_insert_count": counts["insert"] + counts["correction"],
        "new_snapshot_count": counts["insert"],
        "existing_duplicate_count": counts["duplicate"],
        "correction_supersession_count": counts["correction"],
        "excluded_count": len(exclusions),
        "false_zero_exclusion_count": sum(
            str(item.get("reason") or "").endswith(
                "_required_scalar_evidence_not_verified"
            )
            for item in exclusions
        ),
    }


def _valid_planned_item(item):
    return (
        isinstance(item, dict)
        and item.get("disposition") in {"insert", "duplicate", "correction"}
        and bool(item.get("logical_snapshot_key"))
        and bool(item.get("source_snapshot_key"))
        and bool(item.get("performance_event_id"))
        and isinstance(item.get("evidence"), dict)
    )


def _candidate_from_planned(item):
    return {
        key: deepcopy(value)
        for key, value in item.items()
        if key not in {
            "disposition", "existing_event_id", "supersedes_event_id",
        }
    }


def _disposition_projection(items):
    return [
        {
            "performance_event_id": item.get("performance_event_id"),
            "source_snapshot_key": item.get("source_snapshot_key"),
            "disposition": item.get("disposition"),
            "existing_event_id": item.get("existing_event_id") or "",
            "supersedes_event_id": item.get("supersedes_event_id") or "",
        }
        for item in items
    ]


def _verified_value(metric, fallback):
    metric = metric if isinstance(metric, dict) else {}
    return metric.get("value") if metric.get("status") == "verified" else fallback


def _without_retrieval_times(value):
    if isinstance(value, dict):
        return {
            key: _without_retrieval_times(item)
            for key, item in value.items()
            if key != "retrieved_at"
        }
    if isinstance(value, list):
        return [_without_retrieval_times(item) for item in value]
    return value


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _now(value):
    parsed = _parse_time(value)
    return parsed or datetime.now(timezone.utc)


def _database_url(value):
    return str(
        value if value is not None else os.getenv(DATABASE_URL_ENV, "")
    ).strip()


def _connect(database_url, connect_factory):
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _unavailable(status):
    return {
        "success": False,
        "status": status,
        "packet_prepared": False,
        **AUTHORITY,
    }


def _database_failure(status, exc):
    return {
        "success": False,
        "status": status,
        "error_type": exc.__class__.__name__,
        "packet_prepared": False,
        **AUTHORITY,
    }


def _rejected(status):
    return {
        "success": False,
        "status": status,
        "created_count": 0,
        **AUTHORITY,
    }


def _signing_diagnostics(configured):
    return {
        **SIGNING_DIAGNOSTICS,
        "stable_signing_source_configured": bool(configured),
        "cross_worker_validation_supported": bool(configured),
    }


def _signing_unavailable():
    return {
        "success": False,
        "status": "stable_packet_signing_source_not_configured",
        "packet_prepared": False,
        "created_count": 0,
        "signing": _signing_diagnostics(False),
        **AUTHORITY,
    }


def incorrect_batch_exclusion_plan(batch_id, performance_event_ids):
    """Return the only valid rollback plan; this function performs no writes."""
    return {
        "status": "owner_approved_compensating_evidence_required",
        "incorrect_batch_id": str(batch_id or ""),
        "affected_event_count": len(list(performance_event_ids or [])),
        "updates_allowed": False,
        "deletes_allowed": False,
        "automatic_exclusion": False,
        "procedure": [
            "Freeze ranking use of the identified batch in owner review.",
            "Prepare verified corrected or exclusion evidence per affected event.",
            "Owner approves an exact correction packet and hash.",
            "Append corrections with supersedes_event_id lineage.",
            "Reconcile active leaf evidence; retain the original batch unchanged.",
        ],
    }
