"""Production-shaped BEACON publication confirmation through SAM attribution."""

from datetime import datetime, timezone
from unittest.mock import patch

from modules.beacon.protected_publication_worker import run_protected_publication_cycle
from modules.beacon.publication_attribution import resolve_canonical_meta_publication_binding
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.sales.beacon_campaign import (
    _facebook_post_execution_id,
    execute_beacon_facebook_page_post,
)
from modules.sales.sam_meta_inbound import evaluate_meta_inbound_attribution


NOW = datetime(2026, 8, 22, 9, 30, tzinfo=timezone.utc)
CAPTION = (
    "Looking for live pigs? Amadeus Farm handles enquiries for piglets, weaners, "
    "growers and finishers. Message us with the type, number needed, intended use and "
    "your area. SAM will check current farm records before discussing any option; no "
    "stock, price, availability, delivery or reservation is promised."
)


class PublicationStore:
    def __init__(self, claim):
        self.claimed = claim
        self.finished = []

    def claim(self, _worker, _now):
        claimed, self.claimed = self.claimed, None
        return claimed

    def finish(self, consumer_id, status, outcome, _now):
        self.finished.append({
            "consumer_id": consumer_id,
            "status": status,
            "outcome": outcome,
        })
        return True


class CanonicalConnection:
    def __init__(self, store, execution_rows):
        self.store = store
        self.execution_rows = execution_rows
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self

    def execute(self, _sql, parameters):
        self.parameters = parameters

    def fetchall(self):
        post_id, page_id, _organic_page_id = self.parameters
        if len(self.store.finished) != 1:
            return []
        consumer = self.store.finished[0]
        outcome = consumer["outcome"]
        provider = outcome.get("facebook_result", {})
        readback = provider.get("provider_readback", {})
        sent = any(
            row.get("execution_status") == "facebook_page_post_sent"
            and row.get("facebook_post_id") == post_id
            for row in self.execution_rows
        )
        if not (
            consumer["status"] == "confirmed"
            and outcome.get("status") == "facebook_page_post_sent"
            and outcome.get("facebook_post_id") == post_id
            and provider.get("provider_readback_confirmed") is True
            and readback.get("id") == post_id
            and sent
        ):
            return []
        return [(
            "ATTR-1",
            post_id,
            page_id,
            readback["created_time"],
            "SAM may qualify inbound only; no commitment.",
            CAPTION,
            "PACKET-1",
            consumer["consumer_id"],
            "protected_publication_consumer",
        )]


def _approved_enquiry():
    preview = {
        "contract_version": "beacon_campaign_owner_card_v1",
        "packet_id": "PACKET-1",
        "target_page_id": "PAGE-1",
        "packet_generation": "G1",
        "exact_post_copy": CAPTION,
        "selected_media": {"mode": "text_only"},
        "media_evidence_exception": (
            "Explicit text-only publication; no media is selected or implied."
        ),
        "audience": "Farm followers",
        "location": "Western Cape",
        "publication_time": "2026-08-22T10:00:00+00:00",
        "publication_timezone": "Africa/Johannesburg",
        "budget_cap": {"currency": "ZAR", "total": "0.00", "daily": "0.00"},
        "duration": {"days": 0},
        "attribution_identity": "ATTR-1",
        "stock_boundary": "",
        "sam_boundary": "SAM may qualify inbound only; no commitment.",
        "story_context": {},
        "stop_conditions": ["authority_revoked"],
        "rollback": {},
        "approval_expires_at": "2026-08-22T10:00:00+00:00",
        "campaign_lane": "live_stock_enquiry_capture",
        "campaign_objective": "qualified_livestock_enquiries",
    }
    preview["campaign_digest"] = canonical_preview_digest(
        "beacon_campaign_review", preview
    )
    return {
        "consumer_id": "CONSUMER-1",
        "callback_token": "TOKEN-1",
        "action_kind": "beacon_campaign_review",
        "claim_status": "completed",
        "evidence_generation": preview["campaign_digest"],
        "preview_payload": preview,
        "approval_result": {"status": "beacon_campaign_review_approved"},
    }


def _authority(_payload, params, _database_url):
    authoritative = {
        **params,
        "publication_binding_id": "BIND-1",
        "owner_decision_event_id": "DECISION-1",
        "authorization_generation_id": "AUTH-1",
    }
    return ({
        "success": True,
        "binding": {
            "binding_id": "BIND-1",
            "owner_decision_event_id": "DECISION-1",
        },
        "authorization": {
            "authorization_generation_id": "AUTH-1",
            "expected_attempt_identity": _facebook_post_execution_id(authoritative),
        },
    }, 200)


def _production_executor(execution_rows, readback):
    def recorder(params, database_url=None):
        execution_rows.append(dict(params))
        return {"success": True, "created_count": 1}, 201

    def execute(payload, database_url=None):
        return execute_beacon_facebook_page_post(
            payload,
            database_url=database_url,
            execution_recorder=recorder,
            protected_campaign_authority_reader=_authority,
            meta_readback_reader=readback,
            environ={
                "BEACON_FACEBOOK_POSTING_ENABLED": "1",
                "BEACON_FACEBOOK_PAGE_ID": "PAGE-1",
                "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "test-token",
            },
        )

    return execute


def _production_referral():
    return {
        "created_at": "2026-08-22T09:06:00+00:00",
        "content_attributes": {"referral": {"source_id": "PAGE-1_9"}},
    }


def test_nested_provider_confirmation_unlocks_canonical_binding_and_sam_attribution_once():
    store = PublicationStore(_approved_enquiry())
    execution_rows = []
    readback = lambda post_id, _params, **_kwargs: ({
        "success": True,
        "status": "meta_readback_confirmed",
        "id": post_id,
        "created_time": "2026-08-22T09:05:00+00:00",
    }, 200)

    with patch(
        "modules.sales.beacon_campaign._post_to_facebook_page",
        return_value=({
            "success": True,
            "facebook_post_id": "PAGE-1_9",
            "uploaded_media_ids": [],
        }, 200),
    ) as provider:
        first = run_protected_publication_cycle(
            database_url="postgresql://disposable.invalid/test",
            store=store,
            executor=_production_executor(execution_rows, readback),
            now=NOW,
        )
        replay = run_protected_publication_cycle(
            database_url="postgresql://disposable.invalid/test",
            store=store,
            executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("replay reached executor")
            ),
            now=NOW,
        )

    assert first["status"] == "protected_campaign_public_policy_failed"
    assert replay["status"] == "beacon_publication_cycle_silent"
    assert provider.call_count == 0

    resolved = resolve_canonical_meta_publication_binding(
        _production_referral(),
        database_url="postgresql://disposable.invalid/test",
        expected_page_id="PAGE-1",
        connector=lambda *_args, **_kwargs: CanonicalConnection(store, execution_rows),
    )
    attributed = evaluate_meta_inbound_attribution(
        _production_referral(), binding_resolution=resolved, now=NOW
    )
    assert resolved["status"] == "unavailable"
    assert attributed["status"] == "unverified"
    assert attributed["attribution_identity"] == ""
    assert attributed["sends_message"] is False


def test_failed_nested_readback_is_terminal_and_cannot_create_sam_attribution():
    store = PublicationStore(_approved_enquiry())
    execution_rows = []
    failed_readback = lambda *_args, **_kwargs: ({
        "success": False,
        "status": "meta_readback_identity_mismatch",
    }, 409)

    with patch(
        "modules.sales.beacon_campaign._post_to_facebook_page",
        return_value=({
            "success": True,
            "facebook_post_id": "PAGE-1_9",
            "uploaded_media_ids": [],
        }, 200),
    ) as provider:
        result = run_protected_publication_cycle(
            database_url="postgresql://disposable.invalid/test",
            store=store,
            executor=_production_executor(execution_rows, failed_readback),
            now=NOW,
        )
        replay = run_protected_publication_cycle(
            store=store,
            executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("terminal failure replay reached executor")
            ),
            now=NOW,
        )

    assert result["status"] == "protected_campaign_public_policy_failed"
    assert replay["status"] == "beacon_publication_cycle_silent"
    assert provider.call_count == 0

    resolved = resolve_canonical_meta_publication_binding(
        _production_referral(),
        database_url="postgresql://disposable.invalid/test",
        expected_page_id="PAGE-1",
        connector=lambda *_args, **_kwargs: CanonicalConnection(store, execution_rows),
    )
    attributed = evaluate_meta_inbound_attribution(
        _production_referral(), binding_resolution=resolved, now=NOW
    )
    assert resolved["status"] == "unavailable"
    assert resolved["reason"] == "canonical_publication_binding_not_found"
    assert attributed["status"] == "unverified"
    assert attributed["attribution_identity"] == ""
    assert attributed["sends_message"] is False
