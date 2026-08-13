from modules.oom_sakkie import protected_action_runtime as runtime
from modules.oom_sakkie.protected_action_claims import build_buttons, canonical_preview_digest, create_claim
from datetime import datetime, timedelta, timezone
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.telegram_direct import handle_telegram_direct_webhook
import json


def parsed(text="I confirm this"):
    return {"text": text, "telegram_user_id": "5721652188", "telegram_chat_id": "5721652188",
            "provider_message_id": "3523", "provider_timestamp": "2026-08-11T14:42:14Z"}


def authority():
    return issue_gateway_owner_authority("5721652188", "5721652188")


def test_buttons_are_short_opaque_and_have_required_afrikaans_labels():
    mortality = build_buttons("abc123", grouped=False)["inline_keyboard"][0]
    grouped = build_buttons("abc123", grouped=True)["inline_keyboard"][0]
    assert [item["text"] for item in mortality] == ["Bevestig", "Verander", "Kanselleer"]
    assert [item["text"] for item in grouped] == ["Bevestig alles", "Verander", "Kanselleer"]
    assert all(len(item["callback_data"].encode()) <= 64 for item in mortality + grouped)
    assert all("HERD-" not in item["callback_data"] for item in mortality + grouped)


def test_new_manager_question_is_not_claimed_as_protected_confirmation():
    result, status = runtime.handle_protected_action_input(parsed("What is today's plan?"), authority())
    assert status == 200 and result["handled"] is False


def test_natural_confirmation_advances_exact_active_grouped_claim(monkeypatch):
    payload = {"weight_date": "2026-08-11", "row_count": 1,
               "rows": [{"pig_id": "PIG-1", "weight_kg": 64.4}]}
    digest = canonical_preview_digest("grouped_weights", payload)
    monkeypatch.setattr(runtime, "resolve_natural_confirmation", lambda **kwargs: {
        "callback_token": "opaque", "mission_id": "MISSION", "preview_payload": payload})
    monkeypatch.setattr(runtime, "claim_callback", lambda *args, **kwargs: ({
        "success": True, "status": "protected_callback_claimed", "action_kind": "grouped_weights",
        "mission_id": "MISSION", "preview_digest": digest, "preview_payload": payload}, 200))
    monkeypatch.setattr(runtime, "execute_grouped_weight_claim", lambda claim, **kwargs: ({
        "success": True, "status": "grouped_weights_completed", "row_count": 1,
        "movement_count": 0, "rows": payload["rows"], "writes_farm_data": True}, 201))
    result, status = runtime.handle_protected_action_input(parsed(), authority())
    assert status == 201 and result["status"] == "grouped_weights_completed"
    assert result["owner_visible_completion_policy"] == "verified_edit_or_new_message"


def test_proven_replay_is_silent_and_has_no_effects(monkeypatch):
    monkeypatch.setattr(runtime, "claim_callback", lambda *args, **kwargs: ({
        "success": True, "status": "protected_callback_replayed_noop",
        "telegram_sends": 0, "telegram_edits": 0}, 200))
    result, status = runtime.handle_protected_action_input(
        {**parsed(""), "callback_data": "oompa:opaque:confirm"}, authority())
    assert status == 200 and result["suppress_owner_delivery"] is True
    assert result["writes_farm_data"] is False


def test_recovered_grouped_executor_completed_replay_is_silent(monkeypatch):
    payload={"contract_version":"canonical_grouped_weight_movement_preview_v1",
        "effective_date":"2026-08-13","rows":[{"pig_id":"PIG-1","weight_kg":"64.4"}],
        "confirmation_required":True}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
        "success":True,"status":"protected_callback_recovered","callback_token":"opaque",
        "action_kind":"grouped_weights","mission_id":"MISSION","preview_digest":"DIGEST",
        "preview_payload":payload},200))
    monkeypatch.setattr(runtime,"execute_grouped_weight_claim",lambda *args,**kwargs:({
        "success":True,"status":"grouped_weights_replayed_noop","writes_farm_data":False,
        "telegram_sends":0,"telegram_edits":0},200))
    result,status=runtime.handle_protected_action_input(
        {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority())
    assert status==200 and result["suppress_owner_delivery"] is True and result["answer"]==""
    assert result["writes_farm_data"] is False


def test_connection_failure_after_claim_is_retained_for_exact_recovery(monkeypatch):
    payload={"preview":{"row_count":7},"preview_sha256":"DIGEST"}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_claimed","callback_token":"opaque",
      "action_kind":"herdmaster_breeding_grouped","mission_id":"MISSION",
      "preview_digest":"DIGEST","preview_payload":payload},200))
    monkeypatch.setattr(
      "modules.oom_sakkie.herdmaster_breeding_exposure_runtime.execute_claimed_group",
      lambda *args,**kwargs:(_ for _ in ()).throw(ConnectionError("offline")))
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority())
    assert status==503 and result["status"]=="protected_execution_recovery_pending"
    assert result["recovery_required"] is True and result["writes_farm_data"] is False
    assert "do not confirm again" in result["answer"]


def test_recovered_execution_after_domain_commit_completes_without_duplicate_result(monkeypatch):
    payload={"preview":{"row_count":7},"preview_sha256":"DIGEST"}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_recovered","callback_token":"opaque",
      "action_kind":"herdmaster_breeding_grouped","mission_id":"MISSION",
      "preview_digest":"DIGEST","preview_payload":payload},200))
    monkeypatch.setattr(
      "modules.oom_sakkie.herdmaster_breeding_exposure_runtime.execute_claimed_group",
      lambda *args,**kwargs:({"success":True,"status":"grouped_operation_replayed_noop",
        "rows_changed":0},200))
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:{
      "completed":True,"replayed":False,"result":{"success":True,
        "status":"grouped_operation_replayed_noop","rows_changed":0}})
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority())
    assert status==200 and result["rows_changed"]==0
    assert result["answer"]=="Recorded the confirmed facts for 7 animals exactly once."


def test_allowed_family_reporter_cannot_use_protected_callback():
    owner="5721652188";reporter="1002";secret="s"*48
    env={"OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED":"1","OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED":"1",
      "OOM_SAKKIE_TELEGRAM_BOT_TOKEN":"123456789:"+"A"*40,
      "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET":secret,
      "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":owner+","+reporter,
      "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID":owner,
      "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON":json.dumps([{"telegram_user_id":reporter,
        "role":"trusted_family_reporter","family_key":"dad","permissions":["farm_observation"],
        "summary_domains":["herd"],"authorization_id":"AUTH-1","authorized_by_user_id":owner,
        "authorized_at":"2026-08-08T08:00:00+02:00"}])}
    payload={"callback_query":{"id":"cb-1","data":"oompa:opaque:confirm","from":{"id":int(reporter)},
      "message":{"message_id":700,"chat":{"id":int(reporter),"type":"private"}}}}
    result,status=handle_telegram_direct_webhook(payload,
      headers={"X-Telegram-Bot-Api-Secret-Token":secret},environ=env)
    assert status==403 and result["status"]=="telegram_protected_action_owner_required"


class PriorClaimDb:
    def __init__(self,row):self.row=row
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self
    def execute(self,*args):pass
    def fetchone(self):return self.row


def test_expired_or_cross_bound_claim_is_never_represented_with_dead_buttons():
    payload={"row_count":1,"rows":[{"pig_id":"PIG-1","weight_kg":10.0}]}
    digest=canonical_preview_digest("grouped_weights",payload)
    expired=("old","expired",datetime.now(timezone.utc)-timedelta(seconds=1),
      "42","42","500","GEN",payload,None)
    for prior in (expired,("old","active",datetime.now(timezone.utc)+timedelta(minutes=5),
                           "99","99","500","GEN",payload,None)):
        try:
            create_claim(action_kind="grouped_weights",owner_user_id="42",private_chat_id="42",
              mission_id="MISSION",provider_message_id="500",evidence_generation="GEN",
              preview_payload=payload,connect_factory=lambda row=prior:PriorClaimDb(row))
        except RuntimeError as exc:
            assert str(exc)=="protected_claim_identity_or_state_conflict"
        else:
            raise AssertionError("stale/cross-bound claim was reused")


def test_natural_confirmation_cannot_resolve_before_provider_card_binding():
    class ResolveDb:
        read_only=False
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def cursor(self):return self
        def execute(self,sql,params):
            assert "preview_card_message_id is not null" in " ".join(sql.split()).lower()
        def fetchall(self):return []
    monkey_result=runtime.resolve_natural_confirmation(owner_user_id="5721652188",
      private_chat_id="5721652188",connect_factory=ResolveDb)
    assert monkey_result is None
