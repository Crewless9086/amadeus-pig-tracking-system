import hashlib
import json
import os
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from modules.sales.beacon_campaign import (
    record_beacon_campaign_performance_event,
    record_beacon_manual_post_evidence,
)


GRAPH_VERSION_ENV = "BEACON_FACEBOOK_GRAPH_VERSION"
PAGE_ID_ENV = "BEACON_FACEBOOK_PAGE_ID"
PAGE_TOKEN_ENV = "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN"
DEFAULT_GRAPH_VERSION = "v23.0"


def import_beacon_facebook_history(
    max_posts=5000,
    environ=None,
    fetch_page=None,
    manual_recorder=None,
    performance_recorder=None,
):
    source = environ if environ is not None else os.environ
    page_id = str(source.get(PAGE_ID_ENV) or "").strip()
    token = str(source.get(PAGE_TOKEN_ENV) or "").strip()
    version = str(source.get(GRAPH_VERSION_ENV) or DEFAULT_GRAPH_VERSION).strip()
    if not page_id or not token:
        return _result(False, "facebook_history_not_configured", 0, 0, 0), 503

    try:
        max_posts = max(1, min(int(max_posts), 5000))
    except (TypeError, ValueError):
        max_posts = 5000
    fetcher = fetch_page or _fetch_json
    manual_writer = manual_recorder or record_beacon_manual_post_evidence
    performance_writer = performance_recorder or record_beacon_campaign_performance_event
    url = _first_page_url(version, page_id, token)
    imported = existing = failed = fetched = performance_imported = performance_existing = 0
    failures = []
    seen_urls = set()

    while url and fetched < max_posts and url not in seen_urls:
        seen_urls.add(url)
        page, page_status = fetcher(url)
        if page_status >= 400 or not isinstance(page, dict):
            return {
                **_result(False, "facebook_history_fetch_failed", fetched, imported, existing),
                "failed_count": failed + 1,
                "error": str((page or {}).get("error") or "Meta history read failed")[:300],
            }, 502
        for post in page.get("data") or []:
            if fetched >= max_posts:
                break
            fetched += 1
            payloads = _evidence_payloads(post)
            manual, manual_status = manual_writer(payloads["manual"])
            if manual_status >= 400:
                failed += 1
                failures.append({"facebook_post_id": payloads["facebook_post_id"], "status": manual.get("status")})
                continue
            created = int(manual.get("created_count") or 0)
            imported += created
            existing += 0 if created else 1
            performance, performance_status = performance_writer(payloads["performance"])
            if performance_status >= 400:
                failed += 1
                failures.append({"facebook_post_id": payloads["facebook_post_id"], "status": performance.get("status")})
            else:
                performance_created = int(performance.get("created_count") or 0)
                performance_imported += performance_created
                performance_existing += 0 if performance_created else 1
        url = str(((page.get("paging") or {}).get("next")) or "").strip()

    return {
        **_result(failed == 0, "facebook_history_import_complete" if failed == 0 else "facebook_history_import_partial", fetched, imported, existing),
        "failed_count": failed,
        "failures": failures[:20],
        "performance_imported_count": performance_imported,
        "performance_already_imported_count": performance_existing,
    }, 200 if failed == 0 else 207


def _first_page_url(version, page_id, token):
    fields = ",".join((
        "id", "message", "created_time", "permalink_url", "full_picture",
        "reactions.limit(0).summary(true)", "comments.limit(0).summary(true)", "shares",
    ))
    query = urllib_parse.urlencode({"fields": fields, "limit": 100, "access_token": token})
    return f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/posts?{query}"


def _fetch_json(url):
    try:
        with urllib_request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), int(response.status)
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        try:
            body = json.loads(detail)
        except json.JSONDecodeError:
            body = {"error": "Meta returned a non-JSON error"}
        return body, int(exc.code)
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return {"error": exc.__class__.__name__}, 502


def _evidence_payloads(post):
    post = post if isinstance(post, dict) else {}
    facebook_post_id = str(post.get("id") or "").strip()
    identity = hashlib.sha256(facebook_post_id.encode("utf-8")).hexdigest()[:20].upper()
    packet_id = f"META-HISTORY-{identity}"
    message = str(post.get("message") or "").strip()
    media_url = str(post.get("full_picture") or "").strip()
    label = _campaign_label(message)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    metric_evidence = {
        "reactions": _metric_evidence("reactions", post.get("reactions"), facebook_post_id, retrieved_at, summary=True),
        "comments": _metric_evidence("comments", post.get("comments"), facebook_post_id, retrieved_at, summary=True),
        "shares": _metric_evidence("shares", post.get("shares"), facebook_post_id, retrieved_at, key="count"),
    }
    for name in ("reach", "impressions", "messages_to_sam", "qualified_buyer_leads", "sales", "revenue"):
        metric_evidence[name] = _unavailable_metric(name, facebook_post_id, retrieved_at, "unsupported")
    metrics = {name: item["value"] for name, item in metric_evidence.items() if item["status"] == "verified"}
    notes = f"Imported read-only from Meta post {facebook_post_id}. Text: {message or '[no message]'}"
    if media_url:
        notes += f" Media reference: {media_url}"
    return {
        "facebook_post_id": facebook_post_id,
        "manual": {
            "manual_post_event_id": f"BEACON-META-{identity}",
            "publish_packet_id": packet_id,
            "channel": "Facebook",
            "post_url": str(post.get("permalink_url") or "").strip(),
            "posted_at": str(post.get("created_time") or "").strip(),
            "posted_by": "beacon_meta_history_import",
            "campaign_label": label,
            "evidence_notes": notes[:2000],
            "initial_metrics": metrics,
        },
        "performance": {
            "manual_post_event_id": f"BEACON-META-{identity}",
            "publish_packet_id": packet_id,
            "channel": "Facebook",
            "measurement_window": "historical_meta_import_snapshot",
            **metrics,
            "metric_evidence": metric_evidence,
            "evidence_source": "meta_graph_api",
            "source_reference": facebook_post_id,
            "retrieved_at": retrieved_at,
            "notes": f"Read-only Meta history import for {facebook_post_id}; reach, impressions, messages and sales remain unverified.",
            "recorded_by": "beacon_meta_history_import",
        },
    }


def _metric_evidence(name, container, source_reference, retrieved_at, key=None, summary=False):
    raw = ((container or {}).get("summary") or {}).get("total_count") if summary and isinstance(container, dict) else (container or {}).get(key) if isinstance(container, dict) else None
    if raw is None:
        return _unavailable_metric(name, source_reference, retrieved_at, "missing")
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _unavailable_metric(name, source_reference, retrieved_at, "malformed")
    return {"value": value, "status": "verified", "source": "meta_graph_api", "source_reference": source_reference, "retrieved_at": retrieved_at}


def _unavailable_metric(name, source_reference, retrieved_at, status):
    return {"value": None, "status": status, "source": "meta_graph_api", "source_reference": source_reference, "retrieved_at": retrieved_at, "metric": name}


def _campaign_label(message):
    text = str(message or "").lower()
    if any(term in text for term in ("piglet", "piglets", "live pig", "boar", "sow")):
        return "Imported - Live Stock"
    if any(term in text for term in ("pork", "meat", "freezer", "butcher")):
        return "Imported - Meat"
    return "Imported - Farm Awareness"


def _result(success, status, fetched, imported, existing):
    return {
        "success": success,
        "status": status,
        "fetched_count": fetched,
        "imported_count": imported,
        "already_imported_count": existing,
        "read_only_meta_import": True,
        "calls_meta": True,
        "posts_publicly": False,
        "boosts_post": False,
        "spends_money": False,
        "sends_customer_message": False,
        "changes_stock": False,
    }
