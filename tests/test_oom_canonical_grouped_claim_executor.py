from datetime import datetime, timedelta, timezone

import pytest

from modules.oom_sakkie import protected_action_claims as claims
from modules.pig_weights.canonical_grouped_preview import preview_application_typed


PIGS = [
    {"pig_id": "PIG-A", "tag_number": "A1", "status": "Active", "on_farm": "Yes", "current_pen_id": "PEN-OLD"},
    {"pig_id": "PIG-B", "tag_number": "B2", "status": "Active", "on_farm": "Yes", "current_pen_id": ""},
]
PENS = [{"pen_id": "PEN-D3", "pen_name": "D3", "active": True}]


def canonical_claim(destination="D3"):
    preview = preview_application_typed({"effective_date": "2026-08-13", "destination_pen": destination,
        "rows": [{"identity": "A1", "weight_kg": "47.2"}, {"identity": "B2", "weight_kg": "118"}]},
        pigs=PIGS, pens=PENS)
    payload = {key: preview[key] for key in
        ("contract_version", "effective_date", "rows", "confirmation_required")}
    return {"callback_token": "opaque", "preview_payload": payload,
        "preview_digest": preview["preview_digest"]}, preview


class ExecutionDb:
    def __init__(self, *, current=None, existing=None, active_pens=None, fail_on_weight=0,
                 claim_status="executing", claim_result=None):
        self.current = current or {"PIG-A": ("Active", True, "PEN-OLD"), "PIG-B": ("Active", True, None)}
        self.existing = set(existing or ())
        self.active_pens = set({"PEN-D3"} if active_pens is None else active_pens)
        self.fail_on_weight = fail_on_weight
        self.claim_status = claim_status
        self.claim_result = claim_result
        self.weight_inserts = 0
        self.statements = []
        self.last = (None, None)
        self.committed = False
        self.rolled_back = False

    def __enter__(self): return self
    def __exit__(self, exc_type, *_):
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None
        return False
    def cursor(self): return self
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.statements.append((normalized, params))
        self.last = (normalized, params)
        if "insert into public.pig_weight_events" in normalized:
            self.weight_inserts += 1
            if self.fail_on_weight == self.weight_inserts:
                raise RuntimeError("injected_partial_failure")
        self.rowcount = 1
    def fetchone(self):
        sql, params = self.last
        if "from public.current_canonical_pig_state" in sql:
            return self.current.get(params[0])
        if "from app_private.oom_protected_action_claims" in sql:
            return self.claim_status, self.claim_result
        if "from public.pig_weight_events" in sql:
            return (1,) if params[0] in self.existing else None
        if "from public.pens" in sql:
            return (1,) if params[0] in self.active_pens else None
        return None


def test_canonical_digest_payload_executes_exact_rows_date_movement_and_opaque_ids():
    claim, preview = canonical_claim()
    db = ExecutionDb()
    result, status = claims.execute_grouped_weight_claim(claim, actor_id="OWNER", connect_factory=lambda: db)
    assert status == 201 and result["success"] is True
    assert result["row_count"] == 2 and result["movement_count"] == 2
    assert [row["pig_id"] for row in result["rows"]] == ["PIG-A", "PIG-B"]
    assert {row["moved_to_pen_id"] for row in result["rows"]} == {"PEN-D3"}
    assert claim["preview_digest"] == preview["preview_digest"]
    assert db.committed and not db.rolled_back


def test_digest_mismatch_contains_before_any_farm_statement(monkeypatch):
    claim, _ = canonical_claim()
    claim["preview_digest"] = "0" * 64
    contained = []
    monkeypatch.setattr(claims, "contain_claim", lambda token, result, **kwargs: contained.append((token, result)))
    factory_calls = []
    result, status = claims.execute_grouped_weight_claim(
        claim, actor_id="OWNER", connect_factory=lambda: factory_calls.append(True))
    assert status == 409 and result["status"] == "protected_preview_binding_mismatch"
    assert contained and factory_calls == []


def test_stale_canonical_state_contains_with_zero_event_or_batch_inserts():
    claim, _ = canonical_claim()
    db = ExecutionDb(current={"PIG-A": ("Active", True, "PEN-CHANGED"), "PIG-B": ("Active", True, None)})
    result, status = claims.execute_grouped_weight_claim(claim, actor_id="OWNER", connect_factory=lambda: db)
    assert status == 409 and result["status"] == "protected_row_changed_repreview_required"
    assert not any("insert into public.bulk_weight_batches" in sql or "insert into public.pig_weight_events" in sql
        for sql, _ in db.statements)


def test_inactive_destination_is_revalidated_and_contained_before_writes():
    claim, _ = canonical_claim()
    db = ExecutionDb(active_pens=set())
    result, status = claims.execute_grouped_weight_claim(claim, actor_id="OWNER", connect_factory=lambda: db)
    assert status == 409 and result["status"] == "protected_destination_changed_repreview_required"
    assert not any("insert into public.bulk_weight_batches" in sql for sql, _ in db.statements)


def test_partial_failure_rolls_back_the_single_group_transaction():
    claim, _ = canonical_claim()
    db = ExecutionDb(fail_on_weight=2)
    with pytest.raises(RuntimeError, match="injected_partial_failure"):
        claims.execute_grouped_weight_claim(claim, actor_id="OWNER", connect_factory=lambda: db)
    assert db.rolled_back and not db.committed and db.weight_inserts == 2


class ClaimDb:
    def __init__(self, payload, digest, action_kind="grouped_weights"):
        self.payload, self.digest = payload, digest
        self.action_kind = action_kind
        self.status = "active"
        self.provider_id = None
        self.provider_time = None
        self.last = ""
        self.rowcount = 1
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self
    def execute(self, sql, params=()):
        self.last = " ".join(sql.split()).lower()
        if "set status='executing'" in self.last:
            self.status = "executing"; self.provider_id = params[0]
            self.provider_time = datetime.fromisoformat(params[1].replace("Z", "+00:00"))
    def fetchone(self):
        if "select confirmation_provider_message_id" in self.last:
            return self.provider_id, self.provider_time
        return (self.action_kind, "42", "42", "MISSION", self.digest, "GEN", self.payload,
            self.status, datetime.now(timezone.utc) + timedelta(minutes=5), None, "700")


def test_concurrent_confirmation_has_one_claim_and_exact_receipt_recovery_only():
    claim, _ = canonical_claim()
    db = ClaimDb(claim["preview_payload"], claim["preview_digest"])
    kwargs = dict(callback_data="oompa:opaque:confirm", owner_user_id="42", private_chat_id="42",
        provider_message_id="900", provider_timestamp="2026-08-13T12:00:00Z",
        source_card_message_id="700", connect_factory=lambda: db)
    first, first_status = claims.claim_callback(**kwargs)
    second, second_status = claims.claim_callback(**kwargs)
    competing, competing_status = claims.claim_callback(**{**kwargs, "provider_message_id": "901"})
    assert (first_status, first["status"]) == (200, "protected_callback_claimed")
    assert (second_status, second["status"]) == (200, "protected_callback_recovered")
    assert (competing_status, competing["status"]) == (409, "protected_callback_stale")


def test_media_decline_exact_receipt_recovers_with_same_decision_only():
    payload = {"contract_version": "beacon_private_album_review_v1"}
    digest = claims.canonical_preview_digest("beacon_media_review", payload)
    db = ClaimDb(payload, digest, action_kind="beacon_media_review")
    kwargs = dict(callback_data="oompa:opaque:cancel", owner_user_id="42", private_chat_id="42",
        provider_message_id="MEDIA-CALLBACK", provider_timestamp="2026-08-15T12:00:00Z",
        source_card_message_id="700", connect_factory=lambda: db)
    first, first_status = claims.claim_callback(**kwargs)
    recovered, recovered_status = claims.claim_callback(**kwargs)
    competing, competing_status = claims.claim_callback(
        **{**kwargs, "provider_message_id": "OTHER-CALLBACK"})
    assert (first_status, first["status"], first["selected_action"]) == (
        200, "protected_callback_claimed", "decline")
    assert (recovered_status, recovered["status"], recovered["selected_action"]) == (
        200, "protected_callback_recovered", "decline")
    assert (competing_status, competing["status"]) == (409, "protected_callback_stale")


def test_completed_exact_replay_is_noop_before_executor():
    claim, _ = canonical_claim()
    db = ClaimDb(claim["preview_payload"], claim["preview_digest"])
    db.status = "completed"
    result, status = claims.claim_callback("oompa:opaque:confirm", owner_user_id="42", private_chat_id="42",
        provider_message_id="902", provider_timestamp="2026-08-13T12:01:00Z",
        source_card_message_id="700", connect_factory=lambda: db)
    assert status == 200 and result["status"] == "protected_callback_replayed_noop"
    assert result["telegram_sends"] == result["telegram_edits"] == 0


def test_recovered_executor_reads_completed_result_under_lock_and_performs_no_writes():
    claim, _ = canonical_claim()
    prior={"success":True,"status":"grouped_weights_completed","batch_id":"BATCH-1",
        "row_count":2,"movement_count":2,"rows":[],"writes_farm_data":True}
    db=ExecutionDb(claim_status="completed",claim_result=prior)
    result,status=claims.execute_grouped_weight_claim(claim,actor_id="OWNER",connect_factory=lambda:db)
    assert status==200 and result["status"]=="grouped_weights_replayed_noop"
    assert result["writes_farm_data"] is False
    assert result["telegram_sends"]==result["telegram_edits"]==0
    assert not any("insert into public." in sql for sql,_ in db.statements)


def test_preexisting_legacy_claim_remains_execution_compatible():
    payload = {"contract_version": "herdmaster_telegram_grouped_weight_preview_v1",
        "weight_date": "2026-08-13", "row_count": 1,
        "rows": [{"pig_id": "PIG-A", "tag_number": "A1", "label": "A1", "weight_kg": 47.2,
            "current_pen_id": "PEN-OLD", "moved_to_pen_id": "", "moved_to_pen_label": ""}],
        "movement_pen_id": "", "movement_pen_label": ""}
    claim = {"callback_token": "legacy", "preview_payload": payload,
        "preview_digest": claims.canonical_preview_digest("grouped_weights", payload)}
    db = ExecutionDb()
    result, status = claims.execute_grouped_weight_claim(claim, actor_id="OWNER", connect_factory=lambda: db)
    assert status == 201 and result["status"] == "grouped_weights_completed"
    assert result["movement_count"] == 0 and db.committed
