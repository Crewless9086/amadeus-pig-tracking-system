"""The real protected entry path keeps orphan preparation within one fresh read."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import time

from psycopg.types.json import Jsonb
import pytest

from tests.test_oom_sakkie_retained_mortality_orphan_postgres import (
    URL, base_store, legacy,
)
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as retained
from modules.oom_sakkie import herdmaster_health_loss_runtime as health
from modules.oom_sakkie import retained_mortality_orphan_recovery as orphan
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import retained_mortality_history as history

pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")


def _project(claim):
    delivery = {key: claim[key] for key in (*history.EMPTY_MARKERS,
        "callback_token", "preview_digest", "evidence_generation", "expires_at", "delivery_state")}
    return tuple(claim[key] for key in ("owner_user_id", "private_chat_id", "mission_id",
        "provider_message_id", "status", "action_kind", "preview_payload")) + (delivery,)


def _matching_predecessor(j, *, mutation=None):
    evidence = health.load_canonical_health_loss_evidence()
    preview = retained._prepare_retained_report(j.source, evidence)
    binding = preview["confirmation_binding"]
    identity = preview["evaluator"]["identity"]
    mission = "OOM-HERDMASTER-MORTALITY-" + hashlib.sha256(
        (j.source["provider_message_id"] + "|" + identity["pig_id"] + "|" + binding["operation_id"]).encode()).hexdigest()[:24].upper()
    payload = {"operation_id": binding["operation_id"], "preview_sha256": binding["preview_sha256"],
        "identity": identity, "event_family": "found_dead", "effect_kind": "mortality"}
    generation = evidence["evidence_generation"]
    if mutation == "mission": mission += "-OTHER"
    if mutation == "generation": generation += "-OTHER"
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims set mission_id=%s,
            evidence_generation=%s,preview_payload=%s,preview_digest=%s where callback_token=%s""",
            (mission, generation, Jsonb(payload), claims.canonical_preview_digest("mortality", payload), j.old["callback_token"]))


def test_real_entry_builds_once_inside_transaction_without_send(legacy, monkeypatch):
    j = legacy
    original = health.load_canonical_health_loss_evidence
    calls = []
    def fresh(**kwargs):
        assert kwargs.get("connect_factory") is not None, "no preliminary broad read"
        assert 0 < kwargs["deadline_seconds"] <= 6
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(health, "load_canonical_health_loss_evidence", fresh)
    result = retained.build_retained_protected_preview(j.case, deadline_monotonic=time.monotonic() + 48)
    assert result["success"] and result["status"] == "retained_mortality_prepared_not_presented", result
    assert len(calls) == 1 and not j.calls
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (2,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (orphan.EVENT,)) == (1,)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


def test_exact_claim_rolls_back_then_uses_existing_renewal_once(legacy, monkeypatch):
    j = legacy
    _matching_predecessor(j)
    old_token = j.old["callback_token"]
    original = retained._renew_unattempted_claim
    renewed = []
    def renew(*args):
        renewed.append(True)
        return original(*args)
    monkeypatch.setattr(retained, "_renew_unattempted_claim", renew)
    result = retained.build_retained_protected_preview(j.case)
    assert result["success"] and result["status"] == "retained_mortality_prepared_not_presented", result
    assert renewed == [True] and j.rail.claim()["callback_token"] == old_token
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (1,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (orphan.EVENT,)) == (0,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (retained._RENEWAL_EVENT,)) == (1,)
    assert not j.calls and j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


@pytest.mark.parametrize("mutation", ["mission", "generation"])
def test_equal_payload_with_other_identity_is_not_renewal_fallback(legacy, monkeypatch, mutation):
    j = legacy
    _matching_predecessor(j, mutation=mutation)
    before = j.rail.snapshot()
    def unexpected(*_args, **_kwargs):
        pytest.fail("partial equality must not enter ordinary renewal")
    monkeypatch.setattr(retained, "_renew_unattempted_claim", unexpected)
    result = retained.build_retained_protected_preview(j.case)
    assert not result["success"] and not j.calls
    assert j.rail.snapshot() == before


def test_preflight_is_only_routing_and_expiry_is_rechecked_under_lock(legacy, monkeypatch):
    j = legacy
    choose = orphan.prefer_transactional_preparation
    def race(source, projected):
        assert choose(source, projected)
        with j.rail.raw() as db, db.cursor() as cur:
            cur.execute("update app_private.oom_protected_action_claims set expires_at=now()+interval '1 hour'")
        return True
    monkeypatch.setattr(orphan, "prefer_transactional_preparation", race)
    result = retained.build_retained_protected_preview(j.case)
    assert not result["success"] and result["status"] == "retained_orphan_predecessor_not_unattempted_expired"
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (1,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (orphan.EVENT,)) == (0,)
    assert not j.calls


def test_selector_rejects_missing_attempt_markers_and_ambiguous_claims(legacy):
    j = legacy
    projected = _project(j.old)
    assert orphan.prefer_transactional_preparation(j.source, [projected])
    assert not orphan.prefer_transactional_preparation(j.source, [projected, projected])
    for key in history.EMPTY_MARKERS:
        missing = deepcopy(projected)
        del missing[7][key]
        assert not orphan.prefer_transactional_preparation(j.source, [missing]), key
        attempted = deepcopy(projected)
        attempted[7][key] = "attempt"
        assert not orphan.prefer_transactional_preparation(j.source, [attempted]), key
    for field, value in (("status", "cancelled"), ("status", "completed"),
        ("delivery_state", "delivery_pending"), ("owner_user_id", "other"),
        ("private_chat_id", "other"), ("provider_message_id", "other")):
        changed = {**j.old, field: value}
        assert not orphan.prefer_transactional_preparation(j.source, [_project(changed)]), field
    assert not orphan.prefer_transactional_preparation(j.source, [projected],
        now=datetime.now(timezone.utc)-timedelta(days=10))
