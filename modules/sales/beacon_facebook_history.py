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
    imported = existing = failed = fetched = 0
    failures = []
    seen_urls = set()

    while url and fetched < max_posts and url not in seen_urls:
        seen_urls.add(url)
        page, page_status = fetcher(url)
        if page_status >= 400 or not isinstance(page, dict):
            return {
                **_result(False, "facebook_history_fetch_failed", fetched, imported, existing),
                "failed_count": failed + 1,
                "error": "Meta history retrieval failed. Check the server-side provider configuration and retry.",
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
        url = str(((page.get("paging") or {}).get("next")) or "").strip()

    return {
        **_result(failed == 0, "facebook_history_import_complete" if failed == 0 else "facebook_history_import_partial", fetched, imported, existing),
        "failed_count": failed,
        "failures": failures[:20],
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
    metric_evidence = {
        "reactions": _provider_metric(post, "reactions", summary=True),
        "comments": _provider_metric(post, "comments", summary=True),
        "shares": _provider_metric(post, "shares", nested_key="count"),
    }
    for name in ("reach", "impressions", "messages_to_sam", "qualified_buyer_leads", "sales", "revenue"):
        metric_evidence[name] = {"value": None, "status": "unsupported", "source": "meta_graph_posts"}
    metrics = {name: evidence["value"] for name, evidence in metric_evidence.items() if evidence["status"] == "verified"}
    snapshot_seed = {"facebook_post_id": facebook_post_id, "metrics": metric_evidence}
    source_snapshot_id = "META-POST-" + hashlib.sha256(
        json.dumps(snapshot_seed, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24].upper()
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
            "source_snapshot_id": source_snapshot_id,
            "source_ref": facebook_post_id,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"Read-only Meta history import for {facebook_post_id}; reach, impressions, messages and sales remain unverified.",
            "recorded_by": "beacon_meta_history_import",
        },
    }


def _provider_metric(post, key, summary=False, nested_key=""):
    if key not in post or post.get(key) is None:
        return {"value": None, "status": "missing", "source": "meta_graph_posts"}
    raw = post.get(key)
    if summary:
        raw = ((raw or {}).get("summary") or {}).get("total_count")
    elif nested_key:
        raw = (raw or {}).get(nested_key)
    if raw is None:
        return {"value": None, "status": "missing", "source": "meta_graph_posts"}
    try:
        value = int(raw)
        if value < 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"value": None, "status": "malformed", "source": "meta_graph_posts"}
    return {"value": value, "status": "verified", "source": "meta_graph_posts"}


def _summary_total(value):
    try:
        return max(int(((value or {}).get("summary") or {}).get("total_count") or 0), 0)
    except (TypeError, ValueError):
        return 0


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
