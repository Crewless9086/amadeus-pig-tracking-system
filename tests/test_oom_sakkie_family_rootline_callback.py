import json
from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.family_access import resolve_family_principal
from modules.oom_sakkie.family_rootline_callback import (
    CALLBACK_PREFIX, bind_family_rootline_preview_card, create_family_rootline_preview,
    handle_family_rootline_callback, prepare_family_rootline_preview,
)


OWNER, ANTON, ANTOINETTE = "1", "2", "3"


def binding(user, role, family, permissions):
    return {"telegram_user_id": user, "role": role, "family_key": family,
        "permissions": permissions, "summary_domains": ["water"], "language": "af",
        "authorization_id": "AUTH-" + family, "authorized_by_user_id": OWNER,
        "authorized_at": "2026-08-15T08:00:00+02:00"}


ENV = {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
    "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([
        binding(ANTON, "farm_manager", "dad", ["irrigation_start", "irrigation_continue"]),
        binding(ANTOINETTE, "read_only_family_member", "mum", ["explicit_summary"])])}


def parsed(user=ANTON, message="P1"):
    return {"telegram_user_id": user, "telegram_chat_id": user,
        "telegram_chat_type": "private", "provider_message_id": message,
        "provider_timestamp": datetime.now(timezone.utc).isoformat(), "text": "",
        "family_action": {"capability": "irrigation_start", "decision_id": "D1",
            "authorization_digest": "a" * 64, "commissioned_path_id": "PATH-B",
            "zone_id": "B", "bounded_duration_seconds": 300,
            "evidence_generation": "GEN-1", "job_id": "JOB-1", "job_sha256": "b" * 64,
            "segment_identity": "SEG-1", "current_segment": 1, "execution_id": "EX-1",
            "eligibility_sha256": "c" * 64, "consumption_key": "CONSUME-1"}}


class MemoryCursor:
    def __init__(self, db): self.db, self.rowcount, self._row = db, 0, None
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params):
        token = params[0] if sql.lstrip().startswith("select action_kind") else params[-1]
        row = self.db.rows.get(token)
        if sql.lstrip().startswith("select action_kind"):
            self._row = None if not row else (row["action_kind"], row["owner_user_id"],
                row["private_chat_id"], row["mission_id"], row["preview_digest"],
                row["evidence_generation"], row["preview_payload"], row["status"],
                row["expires_at"], row.get("result_payload"), row.get("preview_card_message_id"))
        elif "set status='executing'" in sql and row and row["status"] == "active":
            row["status"] = "executing"; self.rowcount = 1
        elif "set status='cancelled'" in sql and row and row["status"] == "active":
            row["status"] = "cancelled"; self.rowcount = 1
        elif "set status='expired'" in sql and row: row["status"] = "expired"; self.rowcount = 1
    def fetchone(self): return self._row


class MemoryDB:
    def __init__(self): self.rows = {}
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return MemoryCursor(self)


def principal(user=ANTON):
    item = parsed(user)
    return resolve_family_principal(item, ENV)


def stored_preview(db, *, actor=ANTON, status="active"):
    item, actor_principal = parsed(actor), principal(actor)
    with patch("modules.oom_sakkie.family_rootline_callback.create_claim") as create:
        create.return_value = {"success": True, "callback_token": "TOKEN", "preview_digest": "ignored"}
        result = create_family_rootline_preview(parsed=item, principal=actor_principal,
            capability="irrigation_start", replay_identity="R1")
    payload = result["preview_payload"]
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    digest = canonical_preview_digest("rootline_delegated_family", payload)
    result["preview_digest"] = digest
    db.rows["TOKEN"] = {"action_kind": "rootline_delegated_family", "owner_user_id": actor,
        "private_chat_id": actor, "mission_id": result["mission_id"], "preview_digest": digest,
        "evidence_generation": "GEN-1", "preview_payload": payload, "status": status,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "preview_card_message_id": "CARD"}
    return result


def callback_parsed(user=ANTON, message="CB"):
    value = parsed(user, message); value["reply_to_message_id"] = "CARD"; return value


def test_preview_is_zero_effect_and_uses_distinct_afrikaans_buttons():
    db = MemoryDB(); result = stored_preview(db)
    buttons = result["reply_markup"]["inline_keyboard"][0]
    assert result["hardware_commands"] == 0 and result["writes_farm_data"] is False
    assert [button["text"] for button in buttons] == ["Begin veilig", "Kanselleer"]
    assert all(button["callback_data"].startswith(CALLBACK_PREFIX) for button in buttons)


def test_post_authorization_selector_builds_preview_only_from_current_rootline_truth():
    item = parsed(); item.pop("family_action")
    auth = {"active": True, "revoked_at": None, "owner_authority": False,
        "principal_id": ANTON, "private_chat_id": ANTON, "role": "farm_manager",
        "capabilities": ["routine_irrigation_execute"], "zones": ["B"],
        "commissioned_paths": ["PATH-B"], "authorization_digest": "a" * 64}
    eligibility = {"contract_version": "rootline_execution_eligibility.v5",
        "status": "execution_eligible", "authority_source": "owner_approved_routine_irrigation_v1",
        "zone_id": "B", "commissioned_path_id": "PATH-B", "maximum_duration_seconds": 300,
        "plan_generation": "GEN-1", "job_id": "JOB-1", "job_sha256": "b" * 64,
        "segment_identity": "SEG-1", "current_segment": 1, "execution_id": "EX-1",
        "eligibility_sha256": "c" * 64, "consumption_key": "CONSUME-1",
        "command_authority": True, "hardware_control": True}
    with patch("modules.oom_sakkie.family_rootline_callback.create_claim") as create, \
            patch("modules.telemetry.rootline_execution_authority.validate_execution_eligibility",
                  return_value=eligibility):
        create.return_value = {"success": True, "callback_token": "TOKEN",
            "preview_digest": "placeholder"}
        result = prepare_family_rootline_preview(parsed=item, principal=principal(),
            capability="irrigation_start", replay_identity="R1",
            authorization_loader=lambda _: auth, eligibility_loader=lambda: eligibility)
    assert result["success"] and result["preview_payload"]["zone_id"] == "B"
    assert result["preview_payload"]["provider_message_id"] == item["provider_message_id"]


def test_exact_callback_executes_adapter_once_and_replay_is_silent():
    db = MemoryDB(); result = stored_preview(db); calls = []
    adapter = lambda **_: calls.append(1) or {"success": True, "status": "segment_ready",
        "answer": "Gereed.", "hardware_commands": 0, "writes_farm_data": False}
    claims = lambda *_: {"success": True, "created": True}
    with patch("modules.oom_sakkie.family_rootline_callback.complete_claim") as complete:
        first, status = handle_family_rootline_callback(callback_parsed(), principal(),
            callback_data=f"{CALLBACK_PREFIX}TOKEN:confirm", rootline_adapter=adapter,
            replay_store=claims, connect_factory=lambda: db)
        db.rows["TOKEN"]["status"] = "completed"; db.rows["TOKEN"]["result_payload"] = {"status": "segment_ready"}
        replay, replay_status = handle_family_rootline_callback(callback_parsed(message="CB2"), principal(),
            callback_data=f"{CALLBACK_PREFIX}TOKEN:confirm", rootline_adapter=adapter,
            replay_store=claims, connect_factory=lambda: db)
    assert status == 200 and first["status"] == "segment_ready" and len(calls) == 1
    assert replay_status == 200 and replay["suppress_family_delivery"] is True and len(calls) == 1
    complete.assert_called_once()


def test_wrong_actor_card_forgery_and_ambiguous_execution_make_zero_calls():
    for mutation, expected in (("wrong_actor", "family_rootline_callback_unauthorized"),
                               ("wrong_card", "family_rootline_callback_card_mismatch"),
                               ("changed_binding", "family_rootline_callback_binding_changed"),
                               ("executing", "family_rootline_callback_execution_ambiguous")):
        db = MemoryDB(); stored_preview(db); item = callback_parsed(); who = principal(); calls = []
        if mutation == "wrong_actor": who = principal(ANTOINETTE); item = callback_parsed(ANTOINETTE)
        if mutation == "wrong_card": item["reply_to_message_id"] = "OTHER"
        if mutation == "changed_binding": db.rows["TOKEN"]["preview_payload"]["family_binding_digest"] = "0" * 64
        if mutation == "executing": db.rows["TOKEN"]["status"] = "executing"
        result, status = handle_family_rootline_callback(item, who,
            callback_data=f"{CALLBACK_PREFIX}TOKEN:confirm",
            rootline_adapter=lambda **_: calls.append(1), replay_store=lambda *_: {},
            connect_factory=lambda: db)
        assert status >= 400 and result["status"] == expected and calls == []


def test_terminal_persistence_failure_preserves_known_effect_and_marks_ambiguity():
    db = MemoryDB(); stored_preview(db)
    material = {"contract_version": "rootline_delegated_outcome.v1", "status": "segment_started",
        "hardware_commands": 1, "provider_control_calls": 1, "owner_authority": False,
        "n8n_authority": False, "google_sheets_authority": False}
    import hashlib, json
    sealed = {**material, "success": True, "outcome_sha256": hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    adapter = lambda **_: {"success": True, "status": "segment_started",
        "answer": "", "hardware_commands": 1, "provider_control_calls": 1,
        "writes_farm_data": False, "rootline_outcome": sealed}
    with patch("modules.oom_sakkie.family_rootline_callback.complete_claim",
               side_effect=RuntimeError("db unavailable")):
        result, status = handle_family_rootline_callback(callback_parsed(), principal(),
            callback_data=f"{CALLBACK_PREFIX}TOKEN:confirm", rootline_adapter=adapter,
            replay_store=lambda *_: {"success": True, "created": True},
            connect_factory=lambda: db)
    assert status == 503 and result["provider_outcome_ambiguous"] is True
    assert result["suppress_automatic_retry"] is True
