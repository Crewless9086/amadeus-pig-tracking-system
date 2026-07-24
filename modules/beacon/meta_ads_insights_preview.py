"""Bounded, secret-safe, GET-only Meta Ads Insights preview for owner review."""

from datetime import date, datetime, timezone
from copy import deepcopy
from hashlib import sha256
import json
import os
import threading
import time as time_module
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
DEFAULT_TOTAL_TIMEOUT_SECONDS = 25.0
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_RECORDS = 500
SUCCESS_CACHE_SECONDS = 15.0
FAILURE_COOLDOWN_SECONDS = 2.0
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
_PREVIEW_FLIGHTS = {}
_PREVIEW_FLIGHTS_LOCK = threading.Lock()


class MetaPreviewError(Exception):
    """Safe adapter error that never stores a URL, token, or response body."""

    def __init__(
        self,
        status,
        *,
        http_status=None,
        meta_code=None,
        meta_subcode=None,
        meta_type="",
        optional_field="",
    ):
        super().__init__(status)
        self.status = status
        self.http_status = http_status
        self.meta_code = meta_code
        self.meta_subcode = meta_subcode
        self.meta_type = meta_type
        self.optional_field = optional_field


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
    total_timeout_seconds=DEFAULT_TOTAL_TIMEOUT_SECONDS,
    max_pages=DEFAULT_MAX_PAGES,
    max_records=DEFAULT_MAX_RECORDS,
    singleflight=True,
    clock=None,
):
    """Run one equivalent preview per process, with short cache/cooldown."""
    source = environ if hasattr(environ, "get") else os.environ
    clock = clock or time_module.monotonic
    if not singleflight:
        return _build_meta_ads_insights_preview(
            environ=source,
            start_date=start_date,
            end_date=end_date,
            level=level,
            http_get=http_get,
            now=now,
            timeout_seconds=timeout_seconds,
            total_timeout_seconds=total_timeout_seconds,
            max_pages=max_pages,
            max_records=max_records,
            clock=clock,
        )
    fingerprint = _safe_request_fingerprint(
        source,
        start_date=start_date,
        end_date=end_date,
        level=level,
        timeout_seconds=timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
        max_pages=max_pages,
        max_records=max_records,
    )
    current = clock()
    with _PREVIEW_FLIGHTS_LOCK:
        _prune_preview_flights(current)
        state = _PREVIEW_FLIGHTS.get(fingerprint)
        if state and state.get("active"):
            return _concurrency_only_result(
                source, start_date, end_date, "in_progress"
            ), 202
        if state and state.get("result") and current < state.get("expires_at", 0):
            cached = deepcopy(state["result"])
            cached[0]["concurrency"] = _concurrency_diagnostic("cached")
            return cached
        if state and state.get("result") and current < state.get("cooldown_until", 0):
            cooled = deepcopy(state["result"])
            cooled[0]["source_preview_status"] = cooled[0].get("status")
            cooled[0]["status"] = "cooling_down"
            cooled[0]["success"] = False
            cooled[0]["concurrency"] = _concurrency_diagnostic("cooling_down")
            return cooled
        _PREVIEW_FLIGHTS[fingerprint] = {"active": True}
    try:
        result = _build_meta_ads_insights_preview(
            environ=source,
            start_date=start_date,
            end_date=end_date,
            level=level,
            http_get=http_get,
            now=now,
            timeout_seconds=timeout_seconds,
            total_timeout_seconds=total_timeout_seconds,
            max_pages=max_pages,
            max_records=max_records,
            clock=clock,
        )
        result[0]["concurrency"] = _concurrency_diagnostic("executed")
    except Exception:
        configuration = meta_ads_preview_configuration(source)
        window, _ = _reporting_window(start_date, end_date)
        result = (
            _failure(
                "meta_ads_preview_failed",
                configuration,
                window,
                blockers=["secret_safe_internal_failure"],
            ),
            500,
        )
        result[0]["concurrency"] = _concurrency_diagnostic("failed")
    completed = clock()
    with _PREVIEW_FLIGHTS_LOCK:
        if result[0].get("status") == "preview_ready" and result[1] == 200:
            _PREVIEW_FLIGHTS[fingerprint] = {
                "active": False,
                "result": deepcopy(result),
                "expires_at": completed + SUCCESS_CACHE_SECONDS,
                "cooldown_until": 0,
            }
        else:
            _PREVIEW_FLIGHTS[fingerprint] = {
                "active": False,
                "result": deepcopy(result),
                "expires_at": 0,
                "cooldown_until": completed + FAILURE_COOLDOWN_SECONDS,
            }
    return result


def _build_meta_ads_insights_preview(
    *,
    environ=None,
    start_date=None,
    end_date=None,
    level="ad",
    http_get=None,
    now=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    total_timeout_seconds=DEFAULT_TOTAL_TIMEOUT_SECONDS,
    max_pages=DEFAULT_MAX_PAGES,
    max_records=DEFAULT_MAX_RECORDS,
    clock=None,
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
        total_timeout = max(
            1.0, min(float(total_timeout_seconds), 60.0)
        )
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
    clock = clock or time_module.monotonic
    operation_started = clock()
    deadline = operation_started + total_timeout
    retrieved_at = _iso(now) or datetime.now(timezone.utc).isoformat()
    base = f"https://{GRAPH_HOST}/{version}/act_{account_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resources = {}
    blockers = []
    partial = False
    attribution_status_override = ""

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
        if _remaining_seconds(deadline, clock) <= 0:
            resources[name] = _deadline_resource(
                "not_attempted_due_to_total_deadline"
            )
            blockers.append(f"{name}:not_attempted_due_to_total_deadline")
            partial = True
            continue
        try:
            result = _bounded_get_pages(
                endpoint,
                params,
                headers=headers,
                getter=getter,
                timeout=timeout,
                deadline=deadline,
                clock=clock,
                max_pages=page_cap,
                max_records=cap,
                singleton=name == "account",
            )
        except MetaPreviewError as exc:
            if (
                name == "insights"
                and exc.status == "invalid_optional_field"
                and exc.optional_field == "attribution_setting"
                and _remaining_seconds(deadline, clock) > 0
            ):
                fallback_params = dict(params)
                fallback_params["fields"] = ",".join(
                    field
                    for field in str(params["fields"]).split(",")
                    if field != "attribution_setting"
                )
                try:
                    result = _bounded_get_pages(
                        endpoint,
                        fallback_params,
                        headers=headers,
                        getter=getter,
                        timeout=timeout,
                        deadline=deadline,
                        clock=clock,
                        max_pages=page_cap,
                        max_records=cap,
                        singleton=False,
                    )
                    result["optional_field_retry_performed"] = True
                    attribution_status_override = "unsupported"
                    if result["status"] in {"verified", "partial"}:
                        result["status"] = "partial"
                        result["partial"] = True
                        result["blocker"] = "attribution_setting_unsupported"
                except MetaPreviewError as fallback_exc:
                    result = _error_resource(fallback_exc)
                except Exception:
                    result = _deadline_resource("API_failed")
                    result["blocker"] = "api_failed"
            else:
                result = _error_resource(exc)
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
            attribution_status_override=attribution_status_override,
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
            "configured_ad_account_identifier_exposed": False,
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
            "total_timeout_seconds": total_timeout,
            "total_elapsed_seconds": round(
                max(0.0, clock() - operation_started), 6
            ),
            "total_deadline_exhausted": (
                _remaining_seconds(deadline, clock) <= 0
            ),
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
    deadline,
    clock,
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
        remaining = _remaining_seconds(deadline, clock)
        if remaining <= 0:
            partial = True
            blocker = "timed_out"
            break
        safe_url = _redacted_url(url)
        if safe_url in seen:
            partial = True
            blocker = "repeated_paging_url"
            break
        seen.add(safe_url)
        payload = getter(
            url,
            headers=dict(headers),
            timeout=max(0.01, min(timeout, remaining)),
        )
        if _remaining_seconds(deadline, clock) <= 0:
            partial = True
            blocker = "timed_out"
            break
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
        "status": (
            "timed_out" if blocker == "timed_out"
            else "partial" if partial else "verified"
        ),
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
        error_data = {}
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            error_data = (
                payload.get("error", {})
                if isinstance(payload, dict)
                and isinstance(payload.get("error"), dict)
                else {}
            )
        except Exception:
            pass
        classification = _classify_meta_error(exc.code, error_data)
        raise MetaPreviewError(
            classification["status"],
            http_status=exc.code,
            meta_code=classification["meta_code"],
            meta_subcode=classification["meta_subcode"],
            meta_type=classification["meta_type"],
            optional_field=classification["optional_field"],
        ) from None
    except TimeoutError:
        raise MetaPreviewError("timed_out") from None
    except urllib_error.URLError as exc:
        status = (
            "timed_out"
            if isinstance(getattr(exc, "reason", None), TimeoutError)
            else "api_failed"
        )
        raise MetaPreviewError(status) from None
    except OSError:
        raise MetaPreviewError("api_failed") from None
    except (ValueError, json.JSONDecodeError):
        raise MetaPreviewError("malformed_response") from None


def _proposed_event(
    row,
    *,
    level,
    currency,
    retrieved_at,
    window,
    attribution_status_override="",
):
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
                attribution_status_override
                or ("verified" if row.get("attribution_setting") else "missing")
            ),
            "setting": (
                None
                if attribution_status_override else row.get("attribution_setting")
            ),
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
            state = _metric_status_for_resource(resource_status)
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


def _classify_meta_error(http_status, error):
    """Classify safe structured fields; never return Meta's message/body."""
    error = error if isinstance(error, dict) else {}
    code = _safe_meta_int(error.get("code"))
    subcode = _safe_meta_int(error.get("error_subcode"))
    meta_type = _safe_meta_type(error.get("type"))
    message = str(error.get("message") or "").lower()
    optional_field = ""
    if (
        http_status == 400
        and code == 100
        and "attribution_setting" in message
        and any(phrase in message for phrase in (
            "nonexisting field", "unknown field", "not valid",
            "cannot query field", "unsupported field",
        ))
    ):
        status = "invalid_optional_field"
        optional_field = "attribution_setting"
    elif code == 190 or subcode in {458, 459, 460, 463, 464, 467}:
        status = "invalid_or_expired_token"
    elif http_status == 429 or code in {4, 17, 32, 613}:
        status = "rate_limited"
    elif code in {10, 200, 299} or http_status == 403:
        status = "permission_denied"
    elif http_status == 401:
        status = "invalid_or_expired_token"
    elif code == 100 or http_status == 400:
        status = "invalid_field_or_request"
    else:
        status = "api_failed"
    return {
        "status": status,
        "meta_code": code,
        "meta_subcode": subcode,
        "meta_type": meta_type,
        "optional_field": optional_field,
    }


def _error_resource(exc):
    return {
        "status": exc.status,
        "records": [],
        "record_count": 0,
        "pages_read": 0,
        "partial": False,
        "blocker": exc.status,
        "http_status": exc.http_status,
        "meta_code": exc.meta_code,
        "meta_subcode": exc.meta_subcode,
        "meta_type": exc.meta_type,
    }


def _deadline_resource(status):
    return {
        "status": status,
        "records": [],
        "record_count": 0,
        "pages_read": 0,
        "partial": status == "timed_out",
        "blocker": status,
        "http_status": None,
        "meta_code": None,
        "meta_subcode": None,
        "meta_type": "",
    }


def _remaining_seconds(deadline, clock):
    return max(0.0, deadline - clock())


def _safe_meta_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_meta_type(value):
    text = str(value or "").strip()
    return text if text in {
        "OAuthException", "GraphMethodException", "GraphAPIException",
    } else ""


def _metric_status_for_resource(resource_status):
    if resource_status in {"permission_denied", "invalid_or_expired_token"}:
        return "permission_denied"
    if resource_status in {
        "rate_limited", "invalid_field_or_request", "API_failed", "api_failed",
    }:
        return "API_failed"
    if resource_status in {"malformed", "malformed_response"}:
        return "malformed"
    if resource_status in {
        "partial", "timed_out", "not_attempted_due_to_total_deadline",
        "not_yet_requested",
    }:
        return resource_status
    return "missing"


def _safe_request_fingerprint(
    source,
    *,
    start_date,
    end_date,
    level,
    timeout_seconds,
    total_timeout_seconds,
    max_pages,
    max_records,
):
    window, _ = _reporting_window(start_date, end_date)
    configuration = meta_ads_preview_configuration(source)
    version = _normalized_graph_version(
        source.get(GRAPH_VERSION_ENV) or DEFAULT_GRAPH_VERSION
    )
    safe_dimensions = {
        "adapter": "beacon_meta_ads_preview_v2",
        "configured": configuration["configured"],
        "graph_version": version,
        "start": window.get("start"),
        "end": window.get("end"),
        "level": str(level or "ad").strip().lower(),
        "request_timeout": str(timeout_seconds),
        "total_timeout": str(total_timeout_seconds),
        "max_pages": str(max_pages),
        "max_records": str(max_records),
    }
    return sha256(
        json.dumps(safe_dimensions, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _prune_preview_flights(current):
    expired = [
        key for key, state in _PREVIEW_FLIGHTS.items()
        if not state.get("active")
        and current >= max(
            state.get("expires_at", 0), state.get("cooldown_until", 0)
        )
    ]
    for key in expired:
        _PREVIEW_FLIGHTS.pop(key, None)


def _concurrency_diagnostic(status):
    return {
        "status": status,
        "single_flight": True,
        "queued": False,
        "success_cache_seconds": SUCCESS_CACHE_SECONDS,
        "failure_cooldown_seconds": FAILURE_COOLDOWN_SECONDS,
        "fingerprint_exposed": False,
        "configured_ad_account_identifier_in_fingerprint": False,
        "token_in_fingerprint": False,
    }


def _concurrency_only_result(source, start, end, status):
    configuration = meta_ads_preview_configuration(source)
    window, _ = _reporting_window(start, end)
    result = _failure(
        status,
        configuration,
        window,
        blockers=["equivalent_preview_already_in_progress"],
    )
    result["concurrency"] = _concurrency_diagnostic(status)
    return result


def _reset_meta_preview_singleflight_for_tests():
    with _PREVIEW_FLIGHTS_LOCK:
        _PREVIEW_FLIGHTS.clear()


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
    raw_start = str(start or "").strip()
    raw_end = str(end or "").strip()
    start = _date_text(raw_start) if raw_start else DEFAULT_START_DATE
    end = _date_text(raw_end) if raw_end else DEFAULT_END_DATE
    if not start or not end:
        return {
            "start": raw_start or DEFAULT_START_DATE,
            "end": raw_end or DEFAULT_END_DATE,
        }, "invalid_reporting_date"
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
