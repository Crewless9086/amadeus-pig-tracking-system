"""Bounded, secret-safe, GET-only Meta Ads Insights preview for owner review."""

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


AD_ACCOUNT_ID_ENV = "BEACON_META_AD_ACCOUNT_ID"
ADS_READ_TOKEN_ENV = "BEACON_META_ADS_READ_TOKEN"
GRAPH_VERSION_ENV = "BEACON_FACEBOOK_GRAPH_VERSION"
DEFAULT_GRAPH_VERSION = "v23.0"
DEFAULT_START_DATE = "2025-11-10"
DEFAULT_END_DATE = "2026-07-14"
ALLOWED_LEVELS = {"campaign", "adset", "ad"}
MAX_RANGE_DAYS = 730
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_RECORDS = 500
GRAPH_HOST = "graph.facebook.com"
METRIC_NAMES = (
    "spend", "reach", "impressions", "clicks", "inline_link_clicks",
)
AUTHORITY = {
    "read_only": True,
    "http_get_only": True,
    "calls_meta_read": True,
    "calls_meta_write": False,
    "imports_evidence": False,
    "writes_performed": False,
    "writes_database": False,
    "creates_or_updates_campaigns": False,
    "creates_or_updates_ads": False,
    "publishes_content": False,
    "downloads_leads": False,
    "sends_customer_messages": False,
    "spends_money": False,
    "changes_budget_or_payment": False,
    "writes_business_or_farm_data": False,
}


class MetaPreviewError(Exception):
    """Safe adapter error that never stores a URL, token, or response body."""

    def __init__(self, status, *, http_status=None, meta_code=None):
        super().__init__(status)
        self.status = status
        self.http_status = http_status
        self.meta_code = meta_code


def meta_ads_preview_configuration(environ=None):
    """Return canonical names and booleans only; never return configuration values."""
    source = environ if hasattr(environ, "get") else os.environ
    account_configured = bool(str(source.get(AD_ACCOUNT_ID_ENV) or "").strip())
    token_configured = bool(str(source.get(ADS_READ_TOKEN_ENV) or "").strip())
    version_configured = bool(str(source.get(GRAPH_VERSION_ENV) or "").strip())
    return {
        "configured": account_configured and token_configured,
        "ad_account_id_configured": account_configured,
        "ads_read_token_configured": token_configured,
        "graph_version_configured": version_configured,
        "uses_default_graph_version": not version_configured,
        "contains_secret_values": False,
        "environment_variables": {
            "ad_account_id": AD_ACCOUNT_ID_ENV,
            "ads_read_token": ADS_READ_TOKEN_ENV,
            "graph_version": GRAPH_VERSION_ENV,
        },
        "page_token_reused": False,
    }


def build_meta_ads_insights_preview(
    *,
    environ=None,
    start_date=None,
    end_date=None,
    level="ad",
    http_get=None,
    now=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    max_pages=DEFAULT_MAX_PAGES,
    max_records=DEFAULT_MAX_RECORDS,
):
    """Read Meta evidence and return a proposed append-only import without writing."""
    source = environ if hasattr(environ, "get") else os.environ
    configuration = meta_ads_preview_configuration(source)
    window, window_error = _reporting_window(start_date, end_date)
    normalized_level = str(level or "ad").strip().lower()
    if normalized_level not in ALLOWED_LEVELS:
        return _failure(
            "invalid_insights_level", configuration, window,
            blockers=["level_must_be_campaign_adset_or_ad"],
        ), 400
    if window_error:
        return _failure(
            window_error, configuration, window, blockers=[window_error]
        ), 400
    if not configuration["configured"]:
        return _failure(
            "meta_ads_preview_not_configured",
            configuration,
            window,
            blockers=["private_ads_read_configuration_required"],
        ), 503

    account_id = _normalized_account_id(source.get(AD_ACCOUNT_ID_ENV))
    token = str(source.get(ADS_READ_TOKEN_ENV) or "").strip()
    version = _normalized_graph_version(
        source.get(GRAPH_VERSION_ENV) or DEFAULT_GRAPH_VERSION
    )
    if not account_id or not version:
        return _failure(
            "meta_ads_preview_configuration_malformed",
            configuration,
            window,
            blockers=["configured_identifier_or_graph_version_malformed"],
        ), 400

    try:
        timeout = max(1.0, min(float(timeout_seconds), 30.0))
        page_cap = max(1, min(int(max_pages), 25))
        record_cap = max(1, min(int(max_records), 2000))
    except (TypeError, ValueError):
        return _failure(
            "meta_ads_preview_bounds_malformed",
            configuration,
            window,
            blockers=["request_bounds_malformed"],
        ), 400

    getter = http_get or _http_get
    retrieved_at = _iso(now) or datetime.now(timezone.utc).isoformat()
    base = f"https://{GRAPH_HOST}/{version}/act_{account_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resources = {}
    blockers = []
    partial = False

    requests = {
        "account": (
            base,
            {"fields": "id,name,currency,account_status"},
            1,
        ),
        "campaigns": (
            f"{base}/campaigns",
            {
                "fields": "id,name,status,effective_status,objective,start_time,stop_time",
                "limit": min(100, record_cap),
            },
            record_cap,
        ),
        "adsets": (
            f"{base}/adsets",
            {
                "fields": "id,name,campaign_id,status,effective_status,attribution_spec,start_time,end_time",
                "limit": min(100, record_cap),
            },
            record_cap,
        ),
        "ads": (
            f"{base}/ads",
            {
                "fields": "id,name,campaign_id,adset_id,status,effective_status",
                "limit": min(100, record_cap),
            },
            record_cap,
        ),
        "insights": (
            f"{base}/insights",
            {
                "level": normalized_level,
                "time_range": json.dumps(
                    {"since": window["start"], "until": window["end"]},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "time_increment": "all_days",
                "fields": (
                    "account_id,campaign_id,campaign_name,adset_id,adset_name,"
                    "ad_id,ad_name,date_start,date_stop,spend,reach,impressions,"
                    "clicks,inline_link_clicks,actions,attribution_setting"
                ),
                "limit": min(100, record_cap),
            },
            record_cap,
        ),
    }

    for name, (endpoint, params, cap) in requests.items():
        try:
            result = _bounded_get_pages(
                endpoint,
                params,
                headers=headers,
                getter=getter,
                timeout=timeout,
                max_pages=page_cap,
                max_records=cap,
                singleton=name == "account",
            )
        except MetaPreviewError as exc:
            result = {
                "status": _error_evidence_status(exc),
                "records": [],
                "record_count": 0,
                "pages_read": 0,
                "partial": False,
                "blocker": exc.status,
                "http_status": exc.http_status,
                "meta_code": exc.meta_code,
            }
            blockers.append(f"{name}:{exc.status}")
        except Exception:
            result = {
                "status": "API_failed",
                "records": [],
                "record_count": 0,
                "pages_read": 0,
                "partial": False,
                "blocker": "api_failed",
                "http_status": None,
                "meta_code": None,
            }
            blockers.append(f"{name}:api_failed")
        resources[name] = result
        partial = partial or result.get("partial", False)
        if result.get("blocker"):
            blockers.append(f"{name}:{result['blocker']}")

    account_records = resources["account"].get("records", [])
    account = account_records[0] if account_records else {}
    currency = _safe_currency(account.get("currency"))
    insights = resources["insights"].get("records", [])
    proposed = [
        _proposed_event(
            row,
            level=normalized_level,
            currency=currency,
            retrieved_at=retrieved_at,
            window=window,
        )
        for row in insights
        if isinstance(row, dict)
    ]
    keys = [item["idempotency_key"] for item in proposed]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    metric_summary = _metric_summary(proposed, resources["insights"]["status"])
    status = (
        "partial"
        if partial or blockers or duplicate_keys else
        "preview_ready"
    )
    return {
        "success": status == "preview_ready",
        "status": status,
        "mode": "beacon_meta_ads_insights_read_only_preview",
        "banner": "Preview only — nothing imported",
        "configuration": configuration,
        "connection": {
            "configured": configuration["configured"],
            "account_read_status": resources["account"]["status"],
            "identifiers_exposed": False,
            "token_exposed": False,
        },
        "reporting_window": {**window, "level": normalized_level},
        "retrieved_at": retrieved_at,
        "account_currency": {
            "status": "verified" if currency else resources["account"]["status"],
            "value": currency if currency else None,
        },
        "resource_counts": {
            "campaigns": resources["campaigns"]["record_count"],
            "adsets": resources["adsets"]["record_count"],
            "ads": resources["ads"]["record_count"],
            "insight_rows": len(insights),
        },
        "resource_diagnostics": {
            name: {
                key: value
                for key, value in result.items()
                if key not in {"records"}
            }
            for name, result in resources.items()
        },
        "metric_summary": metric_summary,
        "action_results": _action_summary(proposed),
        "proposed_append_only_events": proposed,
        "proposed_append_only_event_count": len(proposed),
        "idempotency_preview": {
            "algorithm": "sha256_of_non_secret_stable_source_dimensions",
            "keys": keys,
            "duplicate_key_count": len(duplicate_keys),
            "duplicate_keys": duplicate_keys,
            "existing_database_duplicate_check": "not_performed_in_read_only_meta_preview",
        },
        "blockers": sorted(set(blockers)),
        "limits": {
            "timeout_seconds": timeout,
            "max_pages_per_resource": page_cap,
            "max_records_per_resource": record_cap,
            "partial": partial,
        },
        "future_backfill": _future_backfill_contract(),
        "authority": dict(AUTHORITY),
    }, 200


def _bounded_get_pages(
    endpoint,
    params,
    *,
    headers,
    getter,
    timeout,
    max_pages,
    max_records,
    singleton=False,
):
    url = _url(endpoint, params)
    records = []
    seen = set()
    seen_cursors = set()
    pages = 0
    partial = False
    blocker = ""
    while url and pages < max_pages and len(records) < max_records:
        safe_url = _redacted_url(url)
        if safe_url in seen:
            partial = True
            blocker = "repeated_paging_url"
            break
        seen.add(safe_url)
        payload = getter(url, headers=dict(headers), timeout=timeout)
        if not isinstance(payload, dict):
            raise MetaPreviewError("malformed_response")
        page_rows = (
            [payload]
            if singleton and "data" not in payload else
            payload.get("data", [])
        )
        if not isinstance(page_rows, list):
            raise MetaPreviewError("malformed_response")
        records.extend(row for row in page_rows if isinstance(row, dict))
        pages += 1
        if len(records) >= max_records:
            if payload.get("paging", {}).get("next"):
                partial = True
                blocker = "record_limit_reached"
            records = records[:max_records]
            break
        paging = payload.get("paging")
        cursor = _paging_cursor(paging)
        if cursor and cursor in seen_cursors:
            partial = True
            blocker = "repeated_paging_cursor"
            url = ""
            break
        if cursor:
            seen_cursors.add(cursor)
        url = _safe_next_url(paging, endpoint)
    if url and pages >= max_pages:
        partial = True
        blocker = "page_limit_reached"
    return {
        "status": "partial" if partial else "verified",
        "records": records,
        "record_count": len(records),
        "pages_read": pages,
        "partial": partial,
        "blocker": blocker,
    }


def _http_get(url, *, headers, timeout):
    request = urllib_request.Request(url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        meta_code = None
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            meta_code = payload.get("error", {}).get("code")
        except Exception:
            pass
        status = (
            "rate_limited" if exc.code == 429
            else "permission_denied" if exc.code in {401, 403}
            else "api_failed"
        )
        raise MetaPreviewError(
            status, http_status=exc.code, meta_code=meta_code
        ) from None
    except (urllib_error.URLError, TimeoutError, OSError):
        raise MetaPreviewError("api_failed") from None
    except (ValueError, json.JSONDecodeError):
        raise MetaPreviewError("malformed_response") from None


def _proposed_event(row, *, level, currency, retrieved_at, window):
    entity_id = str(
        row.get({"campaign": "campaign_id", "adset": "adset_id", "ad": "ad_id"}[level])
        or ""
    ).strip()
    start = _date_text(row.get("date_start")) or window["start"]
    end = _date_text(row.get("date_stop")) or window["end"]
    source_reference = f"meta_ads_insights/{level}/{entity_id}/{start}/{end}"
    metrics = {
        name: _metric_evidence(
            row.get(name),
            name=name,
            source_reference=source_reference,
            retrieved_at=retrieved_at,
        )
        for name in METRIC_NAMES
    }
    actions = []
    raw_actions = row.get("actions")
    if raw_actions is None:
        actions_status = "missing"
    elif not isinstance(raw_actions, list):
        actions_status = "malformed"
    else:
        actions_status = "verified"
        for action in raw_actions:
            if not isinstance(action, dict):
                actions_status = "partial"
                continue
            action_type = str(action.get("action_type") or "").strip()
            value = _number(action.get("value"))
            actions.append({
                "action_type": action_type,
                "value": value,
                "status": (
                    "verified" if action_type and value is not None else "malformed"
                ),
                "classification": "meta_reported_action_only",
            })
            if not action_type or value is None:
                actions_status = "partial"
    stable = "|".join([
        "meta_ads_insights", level, entity_id, start, end,
        str(row.get("attribution_setting") or ""),
    ])
    return {
        "idempotency_key": "BEACON-META-INSIGHTS-" + sha256(
            stable.encode("utf-8")
        ).hexdigest()[:24].upper(),
        "source": "meta_ads_insights",
        "source_reference": source_reference,
        "retrieved_at": retrieved_at,
        "reporting_window": {"start": start, "end": end},
        "level": level,
        "identity": {
            "campaign_id": str(row.get("campaign_id") or ""),
            "adset_id": str(row.get("adset_id") or ""),
            "ad_id": str(row.get("ad_id") or ""),
        },
        "currency": {
            "status": "verified" if currency else "missing",
            "value": currency if currency else None,
        },
        "attribution": {
            "status": (
                "verified" if row.get("attribution_setting") else "missing"
            ),
            "setting": row.get("attribution_setting"),
        },
        "metrics": metrics,
        "actions": {"status": actions_status, "items": actions},
        "qualified_buyer_leads": {
            "status": "unsupported",
            "value": None,
            "reason": "Meta actions are not qualified-lead attribution.",
        },
        "orders": {"status": "unsupported", "value": None},
        "sales": {"status": "unsupported", "value": None},
        "revenue": {"status": "unsupported", "value": None},
    }


def _metric_evidence(raw, *, name, source_reference, retrieved_at):
    if raw is None or str(raw).strip() == "":
        return {
            "status": "missing", "value": None, "source": "meta_ads_insights",
            "source_reference": source_reference, "retrieved_at": retrieved_at,
        }
    value = _number(raw)
    return {
        "status": "verified" if value is not None else "malformed",
        "value": value,
        "source": "meta_ads_insights",
        "source_reference": source_reference,
        "retrieved_at": retrieved_at,
        "metric": name,
    }


def _metric_summary(events, resource_status):
    summary = {}
    for name in METRIC_NAMES:
        states = {}
        values = []
        for event in events:
            metric = event["metrics"][name]
            states[metric["status"]] = states.get(metric["status"], 0) + 1
            if metric["status"] == "verified":
                values.append(metric["value"])
        if not events:
            state = (
                resource_status
                if resource_status in {
                    "permission_denied", "API_failed", "malformed", "partial",
                }
                else "not_yet_requested" if resource_status == "not_yet_requested"
                else "missing"
            )
            states[state] = 1
        summary[name] = {
            "status_counts": states,
            "verified_row_count": len(values),
            "verified_zero_row_count": sum(value == 0 for value in values),
            "aggregate_value": sum(values) if values else None,
            "aggregate_status": (
                "partial" if resource_status == "partial"
                else "verified" if values else next(iter(states))
            ),
        }
    for name in ("qualified_buyer_leads", "orders", "sales", "revenue"):
        summary[name] = {
            "status_counts": {"unsupported": max(1, len(events))},
            "verified_row_count": 0,
            "verified_zero_row_count": 0,
            "aggregate_value": None,
            "aggregate_status": "unsupported",
        }
    return summary


def _action_summary(events):
    counts = {}
    statuses = {}
    for event in events:
        status = event["actions"]["status"]
        statuses[status] = statuses.get(status, 0) + 1
        for action in event["actions"]["items"]:
            if action["status"] == "verified":
                name = action["action_type"]
                counts[name] = counts.get(name, 0) + action["value"]
    return {
        "classification": "meta_reported_actions_not_leads_sales_or_revenue",
        "status_counts": statuses,
        "totals_by_action_type": counts,
    }


def _future_backfill_contract():
    return {
        "mode": "append_only_owner_authorized_future_import",
        "executes_now": False,
        "stable_key_dimensions": [
            "source", "level", "entity_id", "reporting_start", "reporting_end",
            "attribution_setting",
        ],
        "preserves": [
            "reporting_window", "level", "campaign_id", "adset_id", "ad_id",
            "metric_provenance", "retrieved_at", "currency",
            "attribution_metadata",
        ],
        "legacy_reconciliation": (
            "Keep all 64 legacy rows unchanged. Append structured snapshots and "
            "exclude unproven legacy metrics from ranking."
        ),
        "correction_rule": (
            "Append a traceable correction or supersession event; never rewrite "
            "the original evidence row."
        ),
    }


def _failure(status, configuration, window, *, blockers):
    return {
        "success": False,
        "status": status,
        "mode": "beacon_meta_ads_insights_read_only_preview",
        "banner": "Preview only — nothing imported",
        "configuration": configuration,
        "reporting_window": window,
        "account_currency": {"status": "not_yet_requested", "value": None},
        "resource_counts": {
            "campaigns": 0, "adsets": 0, "ads": 0, "insight_rows": 0,
        },
        "metric_summary": {
            name: {
                "status_counts": {
                    (
                        "unsupported"
                        if name in {
                            "qualified_buyer_leads", "orders", "sales", "revenue",
                        }
                        else "not_yet_requested"
                    ): 1
                },
                "verified_row_count": 0,
                "verified_zero_row_count": 0,
                "aggregate_value": None,
                "aggregate_status": (
                    "unsupported"
                    if name in {
                        "qualified_buyer_leads", "orders", "sales", "revenue",
                    }
                    else "not_yet_requested"
                ),
            }
            for name in (
                *METRIC_NAMES,
                "qualified_buyer_leads", "orders", "sales", "revenue",
            )
        },
        "blockers": blockers,
        "proposed_append_only_events": [],
        "proposed_append_only_event_count": 0,
        "authority": dict(AUTHORITY),
    }


def _reporting_window(start, end):
    start = _date_text(start) or DEFAULT_START_DATE
    end = _date_text(end) or DEFAULT_END_DATE
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        return {"start": start, "end": end}, "invalid_reporting_date"
    if end_date < start_date:
        return {"start": start, "end": end}, "reporting_end_before_start"
    if (end_date - start_date).days > MAX_RANGE_DAYS:
        return {"start": start, "end": end}, "reporting_range_too_large"
    return {"start": start, "end": end}, ""


def _normalized_account_id(value):
    text = str(value or "").strip()
    if text.lower().startswith("act_"):
        text = text[4:]
    return text if text.isdigit() else ""


def _normalized_graph_version(value):
    text = str(value or "").strip()
    if not text.startswith("v"):
        text = "v" + text
    return text if text[1:].replace(".", "").isdigit() else ""


def _url(endpoint, params):
    return endpoint + "?" + urllib_parse.urlencode(params)


def _safe_next_url(paging, endpoint):
    if not isinstance(paging, dict):
        return ""
    next_url = str(paging.get("next") or "").strip()
    if not next_url:
        return ""
    parsed = urllib_parse.urlsplit(next_url)
    if parsed.scheme != "https" or parsed.hostname != GRAPH_HOST:
        raise MetaPreviewError("unsafe_paging_url")
    endpoint_path = urllib_parse.urlsplit(endpoint).path
    if parsed.path != endpoint_path:
        raise MetaPreviewError("unsafe_paging_url")
    query = [
        (key, value)
        for key, value in urllib_parse.parse_qsl(
            parsed.query, keep_blank_values=True
        )
        if key.lower() != "access_token"
    ]
    return urllib_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib_parse.urlencode(query), "")
    )


def _paging_cursor(paging):
    if not isinstance(paging, dict):
        return ""
    cursors = paging.get("cursors")
    if isinstance(cursors, dict) and str(cursors.get("after") or "").strip():
        return str(cursors["after"]).strip()
    next_url = str(paging.get("next") or "").strip()
    if not next_url:
        return ""
    query = dict(urllib_parse.parse_qsl(
        urllib_parse.urlsplit(next_url).query, keep_blank_values=True
    ))
    return str(query.get("after") or "").strip()


def _redacted_url(url):
    parsed = urllib_parse.urlsplit(str(url or ""))
    query = [
        (key, "[redacted]" if key.lower() == "access_token" else value)
        for key, value in urllib_parse.parse_qsl(
            parsed.query, keep_blank_values=True
        )
    ]
    return urllib_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib_parse.urlencode(query), "")
    )


def _safe_currency(value):
    text = str(value or "").strip().upper()
    return text if len(text) == 3 and text.isalpha() else ""


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number and abs(number) != float("inf")):
        return None
    return int(number) if number.is_integer() else number


def _date_text(value):
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _iso(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _error_evidence_status(exc):
    if exc.status == "permission_denied":
        return "permission_denied"
    if exc.status == "malformed_response":
        return "malformed"
    return "API_failed"
