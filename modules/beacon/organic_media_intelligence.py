"""Reusable, evidence-bound organic media learning and graduation."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re


MODE = "beacon_organic_media_intelligence_recommendation_only/v2"
WINDOWS = {"publication_baseline", "approximately_24_hours", "72_hours", "7_days"}
METRIC_STATES = {
    "verified", "missing", "unsupported", "permission_denied", "malformed",
    "api_failed", "partial", "not_yet_requested", "unavailable",
}
AUTHORITY = {
    "recommendation_only": True,
    "owner_review_candidate_only": True,
    "publish": False, "retry": False, "schedule": False, "meta_write": False,
    "boost": False, "advertise": False, "spend": False, "send": False,
    "business_data_mutation": False,
}
THRESHOLDS = {
    "minimum_confirmed_real_posts": 3,
    "minimum_distinct_posts_with_compatible_72h_or_7d_windows": 3,
    "minimum_distinct_owner_usefulness_ratings": 3,
    "minimum_distinct_reliable_publication_runs": 3,
    "minimum_policy_pass_rate": 1.0,
}


def build_organic_learning_report(publication, ordered_media, observations,
                                  evidence_events=None, now=None,
                                  case_label="Organic learning case"):
    publication = publication if isinstance(publication, dict) else {}
    ordered_media = ordered_media if isinstance(ordered_media, list) else []
    observations = observations if isinstance(observations, list) else []
    evidence_events = evidence_events if isinstance(evidence_events, list) else []
    publication_check = _publication_contract(publication, ordered_media)
    packets = _qualified_media_packets(ordered_media, observations)
    media_status = (
        "media_understanding_ready"
        if packets and len(packets) == len(ordered_media)
        else "media_understanding_unavailable"
    )
    snapshots = _performance_snapshots(
        evidence_events,
        publication_check.get("post_identity", ""),
        publication_check.get("channel", ""),
        publication_check.get("objective", ""),
    )
    graduation = evaluate_graduation()
    return {
        "success": publication_check["valid"],
        "status": (
            "organic_media_learning_foundation_ready"
            if publication_check["valid"] else publication_check["status"]
        ),
        "mode": MODE,
        "case_label": str(case_label or "Organic learning case")[:160],
        "generated_at": _iso(now),
        "publication": publication_check,
        "media_understanding": {
            "status": media_status,
            "packets": packets if media_status == "media_understanding_ready" else [],
            "unavailable_asset_ids": [
                row.get("asset_id", "") for row in ordered_media
                if row.get("asset_id") not in {item["asset_id"] for item in packets}
            ],
            "identity_rule": (
                "Visual observations never establish canonical animal identity; "
                "owner/canonical facts remain separate."
            ),
        },
        "post_understanding": _post_understanding(publication_check, packets),
        "performance_learning": {
            "required_windows": sorted(WINDOWS),
            "snapshots": snapshots,
            "available_snapshot_count": len(snapshots),
            "comparison_rule": (
                "Only identical channel, objective and compatible windows are "
                "compared. Missing is not zero; engagement is not revenue or attribution."
            ),
            "recommendations": _recommendations(snapshots),
        },
        "graduation": graduation,
        "authority": deepcopy(AUTHORITY),
    }


def evaluate_graduation(database_url=None):
    events, persistence_available = _load_persisted_events(database_url)
    confirmed = {
        _post_id(row) for row in events
        if row.get("event_kind") == "confirmed_publication"
        and row["payload"].get("delivery_verified") is True and _post_id(row)
    }
    eligible_policy = [
        row for row in events
        if row.get("event_kind") == "policy_evaluation" and _post_id(row) in confirmed
    ]
    policy_by_post = {}
    for row in eligible_policy:
        policy_by_post.setdefault(_post_id(row), []).append(
            row["payload"].get("policy_passed") is True
        )
    policy_passes = {
        post_id for post_id in confirmed
        if policy_by_post.get(post_id) and all(policy_by_post[post_id])
    }
    policy_failures = {
        post_id for post_id in confirmed
        if any(value is False for value in policy_by_post.get(post_id, []))
    }
    compatible_posts = {
        _post_id(row) for row in events
        if row.get("event_kind") == "performance_snapshot"
        and _post_id(row) in confirmed
        and row.get("measurement_window") in {"72_hours", "7_days"}
        and _compatible_snapshot(row)
    }
    rated_posts = {
        _post_id(row) for row in events
        if row.get("event_kind") == "owner_usefulness_rating"
        and _post_id(row) in confirmed and _stable(row["payload"].get("rating_id"))
    }
    reliability_event_runs = {
        (_post_id(row), str(row["payload"].get("publication_run_id") or ""))
        for row in events
        if row.get("event_kind") == "publication_reliability"
        and row["payload"].get("reliable") is True and _post_id(row) in confirmed
        and _stable(row["payload"].get("publication_run_id"))
    }
    confirmed_delivery_runs = {
        (_post_id(row), str(row["payload"].get("publication_run_id") or ""))
        for row in events
        if row.get("event_kind") == "confirmed_publication"
        and row["payload"].get("delivery_verified") is True
        and row["payload"].get("reliable") is True
        and _post_id(row) in confirmed
        and _stable(row["payload"].get("publication_run_id"))
    }
    reliable_run_posts = reliability_event_runs | confirmed_delivery_runs
    reliable_posts = {post_id for post_id, _ in reliable_run_posts}
    pass_rate = (
        len(policy_passes) / len(confirmed)
        if confirmed and len(policy_by_post) == len(confirmed) else 0.0
    )
    observed = {
        "distinct_confirmed_posts": len(confirmed),
        "distinct_posts_with_compatible_windows": len(compatible_posts),
        "distinct_owner_usefulness_ratings": len(rated_posts),
        "distinct_reliable_publication_runs": len(reliable_run_posts),
        "distinct_posts_with_reliable_publication_runs": len(reliable_posts),
        "policy_pass_rate": pass_rate,
        "policy_failure_count": len(policy_failures),
    }
    eligible = (
        observed["distinct_confirmed_posts"] >= THRESHOLDS["minimum_confirmed_real_posts"]
        and observed["distinct_posts_with_compatible_windows"]
        >= THRESHOLDS["minimum_distinct_posts_with_compatible_72h_or_7d_windows"]
        and observed["distinct_owner_usefulness_ratings"]
        >= THRESHOLDS["minimum_distinct_owner_usefulness_ratings"]
        and observed["distinct_reliable_publication_runs"]
        >= THRESHOLDS["minimum_distinct_reliable_publication_runs"]
        and len(reliable_posts) >= THRESHOLDS["minimum_distinct_reliable_publication_runs"]
        and pass_rate == THRESHOLDS["minimum_policy_pass_rate"]
        and not policy_failures
    )
    return {
        "status": "owner_review_candidate_ready" if eligible else "not_eligible",
        "eligible_for_owner_review_candidate": eligible,
        "automatic_authority_granted": False,
        "persistence_available": persistence_available,
        "thresholds": deepcopy(THRESHOLDS),
        "observed": observed,
        "reason": (
            "Minimum evidence met; owner review remains mandatory."
            if eligible else
            "Distinct persisted evidence does not yet meet every threshold."
            if persistence_available else
            "Persisted graduation evidence is unavailable."
        ),
    }


def append_learning_event(event, database_url=None):
    event = event if isinstance(event, dict) else {}
    database_url = str(
        database_url if database_url is not None else os.getenv("DATABASE_URL", "")
    ).strip()
    status = _validate_event(event)
    if status:
        return _failure(status, 409 if status.endswith(("conflict", "incompatible", "prohibited")) else 400)
    if not database_url:
        return _failure("organic_learning_persistence_unavailable", 503)
    try:
        import psycopg
        payload = _canonical_event_payload(event)
        digest = _hash(payload)
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select event_id,payload_sha256,facebook_post_id
                       from public.beacon_organic_media_learning_events
                       where event_id=%s or evidence_key=%s limit 1""",
                    (event["event_id"], event["evidence_key"]),
                )
                row = cursor.fetchone()
                if row:
                    if row == (event["event_id"], digest, event["facebook_post_id"]):
                        return _result("organic_learning_replay_withheld", 0), 200
                    return _failure("organic_learning_identity_conflict", 409)
                cursor.execute(
                    """insert into public.beacon_organic_media_learning_events
                       (event_id,event_kind,facebook_post_id,channel,objective,
                        measurement_window,evidence_key,payload_sha256,payload_json)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (
                        event["event_id"], event["event_kind"],
                        event["facebook_post_id"], event["channel"],
                        event["objective"], event.get("measurement_window", ""),
                        event["evidence_key"], digest,
                        json.dumps(payload, sort_keys=True, default=str),
                    ),
                )
        return _result("organic_learning_event_created", 1), 201
    except Exception as exc:
        result, code = _failure("organic_learning_append_failed", 503)
        result["error_type"] = exc.__class__.__name__
        return result, code


def _publication_contract(publication, media):
    post_id = _stable(publication.get("facebook_post_id"))
    caption = publication.get("caption") if isinstance(publication.get("caption"), str) else ""
    expected_caption = _sha(publication.get("caption_sha256"))
    expected_order = _sha(publication.get("media_order_sha256"))
    expected_payload = _sha(publication.get("media_payload_sha256"))
    media_order = [row.get("asset_id") for row in media if isinstance(row, dict)]
    media_hashes = [row.get("content_sha256") for row in media if isinstance(row, dict)]
    calculated = {
        "caption_sha256": sha256(caption.encode("utf-8")).hexdigest(),
        "media_order_sha256": _hash(media_order),
        "media_payload_sha256": _hash([
            {"asset_id": asset_id, "content_sha256": content_hash}
            for asset_id, content_hash in zip(media_order, media_hashes)
        ]),
    }
    valid = bool(
        post_id and caption and expected_caption and expected_order and expected_payload
        and calculated["caption_sha256"] == expected_caption
        and calculated["media_order_sha256"] == expected_order
        and calculated["media_payload_sha256"] == expected_payload
        and media_order and len(media_order) == len(set(media_order))
        and all(_sha(value) for value in media_hashes)
        and publication.get("confirmed") is True
        and publication.get("channel") == "Facebook"
        and publication.get("objective") == "farm_awareness"
        and publication.get("policy_passed") is True
    )
    return {
        "valid": valid,
        "status": "publication_identity_verified" if valid else "publication_identity_invalid",
        "post_identity": post_id,
        "facebook_post_id": post_id,
        "packet_id": _stable(publication.get("packet_id")),
        "caption": caption,
        "channel": _stable(publication.get("channel")),
        "objective": _stable(publication.get("objective")),
        "policy_passed": publication.get("policy_passed") is True,
        "exact_media_order": media_order,
        **calculated,
    }


def _qualified_media_packets(media, observations):
    packets = []
    for asset in media:
        asset_id = _stable(asset.get("asset_id"))
        asset_hash = _sha(asset.get("content_sha256"))
        qualified = [
            row for row in observations
            if row.get("asset_id") == asset_id
            and row.get("asset_sha256") == asset_hash
            and row.get("evidence_state") in {"qualified_visual_observation", "owner_confirmed_observation"}
            and _provenance_valid(row.get("provenance"))
            and _observation_valid(row.get("observation"))
        ]
        if len(qualified) != 1:
            continue
        observation = qualified[0]
        packets.append({
            "asset_id": asset_id,
            "asset_sha256": asset_hash,
            "observation": deepcopy(observation.get("observation") or {}),
            "position": len(packets) + 1,
            "visible_subject": str(
                (observation.get("observation") or {}).get("visible_subject") or ""
            ),
            "composition_quality": str(
                (observation.get("observation") or {}).get("composition") or ""
            ),
            "does_not_support": deepcopy(
                (observation.get("observation") or {}).get("does_not_support") or []
            ),
            "provenance": deepcopy(observation["provenance"]),
            "evidence_state": observation["evidence_state"],
        })
    return packets


def _provenance_valid(value):
    return bool(
        isinstance(value, dict)
        and value.get("source_type") in {"human_visual_review", "model_visual_review"}
        and _stable(value.get("observer_identity"))
        and _stable(value.get("observer_version"))
        and _valid_timestamp(value.get("observed_at"))
        and value.get("confidence") in {"high", "medium", "owner_confirmed"}
    )


def _observation_valid(value):
    return bool(
        isinstance(value, dict)
        and _stable(value.get("visible_subject"))
        and any(_stable(value.get(key)) for key in (
            "setting", "composition", "story_value", "educational_value",
            "commercial_relevance", "risks",
        ))
        and isinstance(value.get("supports"), list)
        and isinstance(value.get("does_not_support"), list)
    )


def _post_understanding(publication, packets):
    if not publication["valid"] or not packets:
        return {"status": "post_understanding_unavailable", "hypotheses": [], "observed_results": []}
    return {
        "status": "post_understanding_ready",
        "opening_hook": "",
        "caption_media_alignment": "owner_review_required",
        "intent": "farm_awareness",
        "awareness_not_sales": publication["objective"] == "farm_awareness",
        "hypotheses": [],
        "observed_results": [],
        "rule": "Hypotheses and observed results are stored separately.",
    }


def _performance_snapshots(events, post_id, channel, objective):
    seen = set()
    snapshots = []
    for row in events:
        if (
            row.get("event_kind") != "performance_snapshot"
            or _post_id(row) != post_id
            or row.get("channel") != channel
            or row.get("objective") != objective
            or row.get("measurement_window") not in WINDOWS
            or not _compatible_snapshot(row)
        ):
            continue
        key = (post_id, row["measurement_window"], _stable(row.get("evidence_key")))
        if not key[2] or key in seen:
            continue
        seen.add(key)
        snapshots.append(deepcopy(row))
    return snapshots


def _compatible_snapshot(row):
    metrics = row.get("metrics")
    if metrics is None and isinstance(row.get("payload"), dict):
        metrics = row["payload"].get("metrics")
    return bool(
        isinstance(metrics, dict) and metrics
        and all(
            isinstance(item, dict)
            and item.get("status") in METRIC_STATES
            and (item.get("status") == "verified" or item.get("value") is None)
            for item in metrics.values()
        )
    )


def _recommendations(snapshots):
    return {
        "evidence_state": (
            "compatible_evidence_available" if snapshots else "more_evidence_required"
        ),
        "optimization_claimed": False,
        "next_action": (
            "Compare only matching windows across additional confirmed posts."
        ),
    }


def _validate_event(event):
    required = ("event_id", "event_kind", "facebook_post_id", "channel",
                "objective", "evidence_key", "payload")
    if any(not event.get(key) for key in required):
        return "organic_learning_event_invalid"
    if event["event_kind"] not in {
        "media_understanding", "post_understanding", "performance_snapshot",
        "graduation_evaluation", "confirmed_publication", "policy_evaluation",
        "owner_usefulness_rating", "publication_reliability",
    }:
        return "organic_learning_event_kind_invalid"
    if event["channel"] != "Facebook" or event["objective"] != "farm_awareness":
        return "organic_learning_channel_objective_incompatible"
    if not all(_bounded_identity(event.get(key)) for key in (
        "event_id", "facebook_post_id", "evidence_key",
    )):
        return "organic_learning_identity_invalid"
    if event.get("measurement_window", "") not in WINDOWS | {""}:
        return "organic_learning_window_incompatible"
    if (
        event["event_kind"] == "performance_snapshot"
        and event.get("measurement_window") not in WINDOWS
    ) or (
        event["event_kind"] != "performance_snapshot"
        and event.get("measurement_window", "") != ""
    ):
        return "organic_learning_window_incompatible"
    if any(event.get(key) is True for key in (
        "publish", "retry", "schedule", "meta_write", "boost", "advertise",
        "spend", "send",
    )):
        return "organic_learning_authority_prohibited"
    payload = event["payload"] if isinstance(event["payload"], dict) else {}
    if not payload:
        return "organic_learning_payload_invalid"
    for key, expected in (
        ("facebook_post_id", event["facebook_post_id"]),
        ("channel", event["channel"]),
        ("objective", event["objective"]),
        ("event_kind", event["event_kind"]),
        ("measurement_window", event.get("measurement_window", "")),
    ):
        if key in payload and payload[key] != expected:
            return "organic_learning_cross_post_evidence_conflict"
    if any(payload.get(key) is True for key in (
        "publish", "retry", "schedule", "meta_write", "boost", "advertise",
        "spend", "send", "business_data_mutation",
    )):
        return "organic_learning_authority_prohibited"
    if event["event_kind"] == "performance_snapshot":
        if not _compatible_snapshot({"metrics": payload.get("metrics")}):
            return "organic_learning_metric_evidence_invalid"
    if event["event_kind"] == "confirmed_publication":
        ordered_assets = payload.get("exact_ordered_assets")
        if not (
            payload.get("delivery_verified") is True
            and payload.get("reliable") is True
            and _bounded_identity(payload.get("publication_run_id"))
            and _bounded_identity(payload.get("weekly_packet_id"))
            and _bounded_identity(payload.get("owner_decision_event_id"))
            and _bounded_identity(payload.get("publication_binding_id"))
            and _bounded_identity(payload.get("authorization_generation_id"))
            and _bounded_identity(payload.get("confirmed_authorization_event_id"))
            and _bounded_identity(payload.get("execution_publish_packet_id"))
            and _bounded_identity(payload.get("execution_attempt_identity"))
            and _bounded_identity(payload.get("confirmed_execution_event_id"))
            and payload.get("confirmed_facebook_post_id")
            == event["facebook_post_id"]
            and _sha(payload.get("caption_sha256"))
            and _sha(payload.get("media_order_sha256"))
            and _sha(payload.get("media_payload_sha256"))
            and _sha(payload.get("transport_sha256"))
            and _sha(payload.get("execution_payload_sha256"))
            and isinstance(ordered_assets, list) and ordered_assets
            and len(ordered_assets) == len({
                item.get("asset_id") for item in ordered_assets
                if isinstance(item, dict)
            })
            and all(
                isinstance(item, dict)
                and _bounded_identity(item.get("asset_id"))
                and _sha(item.get("asset_sha256"))
                for item in ordered_assets
            )
        ):
            return "organic_learning_payload_invalid"
    if (
        event["event_kind"] == "policy_evaluation"
        and not isinstance(payload.get("policy_passed"), bool)
    ):
        return "organic_learning_payload_invalid"
    if (
        event["event_kind"] == "owner_usefulness_rating"
        and not _bounded_identity(payload.get("rating_id"))
    ):
        return "organic_learning_payload_invalid"
    if event["event_kind"] == "publication_reliability" and not (
        _bounded_identity(payload.get("publication_run_id"))
        and isinstance(payload.get("reliable"), bool)
    ):
        return "organic_learning_payload_invalid"
    if (
        event["event_kind"] == "graduation_evaluation"
        and event["payload"].get("automatic_authority_granted") is not False
    ):
        return "organic_learning_authority_prohibited"
    return ""


def _post_id(row):
    return _stable(row.get("facebook_post_id"))


def _load_persisted_events(database_url=None):
    database_url = str(
        database_url if database_url is not None else os.getenv("DATABASE_URL", "")
    ).strip()
    if not database_url:
        return [], False
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select event_id,event_kind,facebook_post_id,channel,
                              objective,measurement_window,evidence_key,
                              payload_sha256,payload_json
                       from public.beacon_organic_media_learning_events"""
                )
                columns = [item.name for item in cursor.description]
                values = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return _validated_repository_rows(values), True
    except Exception:
        return [], False


def _validated_repository_rows(values):
    result = []
    for row in values if isinstance(values, list) else []:
        if not isinstance(row, dict):
            continue
        row = {**row, "payload": row.get("payload_json")}
        payload = row.get("payload")
        if (
            _validate_event(row)
            or not _sha(row.get("payload_sha256"))
            or _hash(_canonical_event_payload(row)) != row["payload_sha256"]
            or payload != _canonical_event_payload(row)
        ):
            continue
        result.append(row)
    return result


def _canonical_event_payload(event):
    payload = deepcopy(event.get("payload") or {})
    payload.update({
        "event_kind": event["event_kind"],
        "facebook_post_id": event["facebook_post_id"],
        "channel": event["channel"],
        "objective": event["objective"],
        "measurement_window": event.get("measurement_window", ""),
        **{key: False for key in (
            "publish", "retry", "schedule", "meta_write", "boost",
            "advertise", "spend", "send", "business_data_mutation",
        )},
    })
    return payload


def _stable(value):
    value = str(value or "")
    return value if value and value == value.strip() and "\x00" not in value else ""


def _bounded_identity(value):
    value = _stable(value)
    return bool(
        value and len(value) <= 200
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value)
    )


def _valid_timestamp(value):
    value = _stable(value)
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _sha(value):
    value = str(value or "").lower()
    return value if len(value) == 64 and all(char in "0123456789abcdef" for char in value) else ""


def _hash(value):
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _iso(value):
    return (
        value.astimezone(timezone.utc).isoformat()
        if isinstance(value, datetime) else datetime.now(timezone.utc).isoformat()
    )


def _result(status, count):
    return {"success": True, "status": status, "created_count": count, **deepcopy(AUTHORITY)}


def _failure(status, code):
    return {"success": False, "status": status, **deepcopy(AUTHORITY)}, code
