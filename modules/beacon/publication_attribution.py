"""Read-only canonical BEACON publication binding for Meta inbound context."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import os


DATABASE_URL_ENV = "DATABASE_URL"
FACEBOOK_PAGE_ID_ENV = "BEACON_FACEBOOK_PAGE_ID"
CONTRACT_VERSION = "beacon_meta_publication_binding_v1"


def resolve_canonical_meta_publication_binding(
    payload,
    *,
    database_url=None,
    expected_page_id=None,
    connector=None,
):
    """Resolve one provider post to its immutable BEACON publication evidence.

    Values carried by the inbound referral are lookup candidates only.  They do
    not become trusted campaign context unless the canonical publication and
    provider-result rails return one exact binding.
    """
    payload = payload if isinstance(payload, Mapping) else {}
    post_id = _candidate_post_id(payload)
    page_id = _text(
        expected_page_id
        if expected_page_id is not None
        else os.getenv(FACEBOOK_PAGE_ID_ENV, ""),
        180,
    )
    database_url = str(
        database_url
        if database_url is not None
        else os.getenv(DATABASE_URL_ENV, "")
    ).strip()
    if not post_id:
        return _unresolved("source_post_identity_absent")
    if not database_url or not page_id:
        return _unresolved("canonical_publication_binding_configuration_missing")
    if _post_page_id(post_id) != page_id:
        return _unresolved("source_post_page_identity_mismatch", status="rejected")

    if connector is None:
        try:
            import psycopg
        except ImportError:
            return _unresolved("canonical_publication_binding_dependency_missing")
        connector = psycopg.connect

    try:
        with connector(
            database_url,
            connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    _PUBLICATION_BINDING_SQL,
                    (post_id, page_id, page_id),
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            **_unresolved("canonical_publication_binding_read_failed"),
            "error_type": exc.__class__.__name__,
        }

    if not rows:
        return _unresolved("canonical_publication_binding_not_found")
    if len(rows) != 1:
        return _unresolved("canonical_publication_binding_conflict", status="rejected")

    keys = (
        "attribution_identity",
        "post_id",
        "target_page_id",
        "publication_time",
        "sam_boundary",
        "post_text",
        "publish_packet_id",
        "publication_binding_id",
        "binding_source",
    )
    binding = dict(zip(keys, rows[0]))
    for key in keys:
        binding[key] = _text(binding.get(key), 1800 if key == "post_text" else 500)
    published = _instant(binding.get("publication_time"))
    required = (
        "attribution_identity",
        "post_id",
        "target_page_id",
        "publication_time",
        "publish_packet_id",
        "publication_binding_id",
        "binding_source",
    )
    if not published or not all(binding.get(key) for key in required):
        return _unresolved("canonical_publication_binding_incomplete")
    if binding["post_id"] != post_id or binding["target_page_id"] != page_id:
        return _unresolved("canonical_publication_binding_identity_mismatch", status="rejected")
    binding["publication_time"] = published.isoformat()
    return {
        "success": True,
        "status": "resolved",
        "reason": "canonical_beacon_publication_binding_resolved",
        "contract_version": CONTRACT_VERSION,
        "binding": binding,
        **_no_action(),
    }


_PUBLICATION_BINDING_SQL = """
with exact_execution as (
    select e.publish_packet_id, e.exact_text, e.facebook_post_id, e.created_at,
           e.facebook_response_json
      from public.beacon_facebook_post_execution_events e
     where e.facebook_post_id = %s
       and e.execution_status = 'facebook_page_post_sent'
), protected_binding as (
    select c.preview_payload ->> 'attribution_identity' as attribution_identity,
           e.facebook_post_id as post_id,
           %s::text as target_page_id,
           coalesce(
             p.outcome_json #>> '{facebook_result,provider_readback,created_time}',
             e.created_at::text
           ) as publication_time,
           coalesce(c.preview_payload ->> 'sam_boundary', '') as sam_boundary,
           e.exact_text as post_text,
           e.publish_packet_id,
           p.consumer_id as publication_binding_id,
           'protected_publication_consumer'::text as binding_source
      from exact_execution e
      join app_private.beacon_protected_publication_consumers p
        on p.status = 'confirmed'
       and p.outcome_json ->> 'facebook_post_id' = e.facebook_post_id
       and p.outcome_json ->> 'status' = 'facebook_page_post_sent'
       and p.outcome_json #>> '{facebook_result,provider_readback,id}' = e.facebook_post_id
       and p.outcome_json #>> '{facebook_result,provider_readback_confirmed}' = 'true'
      join app_private.oom_protected_action_claims c
        on c.callback_token = p.callback_token
       and c.action_kind = 'beacon_campaign_review'
       and c.status = 'completed'
       and c.preview_payload ->> 'packet_id' = e.publish_packet_id
       and coalesce(c.preview_payload ->> 'attribution_identity', '') <> ''
), organic_binding as (
    select b.binding_id as attribution_identity,
           e.facebook_post_id as post_id,
           b.target_page_id,
           e.created_at::text as publication_time,
           ''::text as sam_boundary,
           e.exact_text as post_text,
           e.publish_packet_id,
           b.binding_id as publication_binding_id,
           'organic_publication_binding'::text as binding_source
      from exact_execution e
      join public.beacon_organic_publication_bindings b
        on b.execution_publish_packet_id = e.publish_packet_id
       and b.target_page_id = %s::text
)
select * from protected_binding
union all
select * from organic_binding
limit 2
"""


def _candidate_post_id(payload):
    conversation = _mapping(payload.get("conversation"))
    content = _mapping(payload.get("content_attributes"))
    referral = _mapping(content.get("referral"))
    rows = (
        referral,
        content,
        _mapping(conversation.get("custom_attributes")),
        _mapping(conversation.get("additional_attributes")),
        payload,
    )
    return _first(rows, "post_id", "source_post_id", "source_id")


def _post_page_id(post_id):
    value = _text(post_id, 500)
    return value.split("_", 1)[0] if "_" in value else ""


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _first(rows, *keys):
    for row in rows:
        for key in keys:
            value = _text(row.get(key), 500)
            if value:
                return value
    return ""


def _instant(value):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _text(value, limit):
    return str(value or "").strip()[:limit]


def _unresolved(reason, *, status="unavailable"):
    return {
        "success": False,
        "status": status,
        "reason": reason,
        "contract_version": CONTRACT_VERSION,
        "binding": {},
        **_no_action(),
    }


def _no_action():
    return {
        "read_only": True,
        "customer_response_authority_granted": False,
        "creates_lead": False,
        "creates_order": False,
        "sends_message": False,
    }
