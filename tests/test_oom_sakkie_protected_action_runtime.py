from modules.oom_sakkie import protected_action_runtime as runtime
from modules.oom_sakkie.protected_action_claims import build_buttons, canonical_preview_digest, create_claim
from datetime import datetime, timedelta, timezone
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie import telegram_direct
from modules.oom_sakkie.telegram_direct import handle_telegram_direct_webhook
import json
import pytest


def parsed(text="I confirm this"):
    return {"text": text, "telegram_user_id": "5721652188", "telegram_chat_id": "5721652188",
            "provider_message_id": "3523", "provider_timestamp": "2026-08-11T14:42:14Z"}


def authority():
    return issue_gateway_owner_authority("5721652188", "5721652188")


def manager_authority():
    return issue_gateway_owner_authority("5721652188", "5721652188",
        principal_role="farm_manager", capabilities=("farm_observation",))


@pytest.mark.parametrize("action_kind", [
    "mortality", "herdmaster_breeding_grouped", "rootline_irrigation_segment",
    "sam_sale_payment", "beacon_campaign_review", "beacon_media_review",
    "documents_green_print",
])
def test_manager_callback_uses_explicit_full_oom_specialist_action_envelope(monkeypatch, action_kind):
    observed = {}
    def claim(*args, **kwargs):
        observed.update(kwargs)
        return {"success": False, "status": "protected_callback_unknown"}, 404
    monkeypatch.setattr(runtime, "claim_callback", claim)
    runtime.handle_protected_action_input(
        {**parsed(""), "callback_data": "oompa:opaque:confirm"}, manager_authority())
    assert action_kind in observed["allowed_action_kinds"]
    assert "core" not in observed["allowed_action_kinds"]
    assert "charlie" not in observed["allowed_action_kinds"]


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


def test_documents_confirmation_dispatches_server_producer_and_completes_claim(monkeypatch):
    claim={"success":True,"status":"protected_callback_claimed",
        "callback_token":"AUTH-GREEN-1","action_kind":"documents_green_print",
        "mission_id":"DMQ-20260816-01","preview_payload":{"bound":True}}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:(claim,200))
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:{
        "completed":True,"result":args[1]})
    producer=lambda claimed,owner:{"job_id":"JOB-GREEN-1","state":"authorized"}
    result,status=runtime.handle_protected_action_input(
        {**parsed(""),"callback_data":"oompa:AUTH-GREEN-1:confirm"},authority(),
        documents_handler=producer)
    assert status==200 and result["job_id"]=="JOB-GREEN-1"
    assert result["status"]=="documents_green_print_authorized"
    assert result["printer_calls"]==0 and result["suppress_owner_delivery"] is True


def test_documents_producer_failure_remains_recoverable(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
        "success":True,"status":"protected_callback_recovered",
        "callback_token":"AUTH-GREEN-1","action_kind":"documents_green_print",
        "mission_id":"DMQ-20260816-01","preview_payload":{"bound":True}},200))
    def fail(*args,**kwargs): raise RuntimeError("database unavailable")
    result,status=runtime.handle_protected_action_input(
        {**parsed(""),"callback_data":"oompa:AUTH-GREEN-1:confirm"},authority(),
        documents_handler=fail)
    assert status==503 and result["recovery_required"] is True
    assert result["canonical_job_created"] is False and result["printer_calls"]==0


@pytest.mark.parametrize("selected_action,confirmed,expected_status", [
    ("incorrect",False,"documents_physical_page_exception_owned"),
    ("uncertain",False,"documents_physical_page_exception_owned"),
])
def test_documents_physical_exception_callback_is_canonical_and_no_reprint(
        monkeypatch,selected_action,confirmed,expected_status):
    claim={"success":True,"status":"protected_callback_claimed",
        "callback_token":"PHYSICAL-1","action_kind":"documents_green_physical_acceptance",
        "mission_id":"DMQ-20260816-01:PHYSICAL:JOB-1","selected_action":selected_action,
        "preview_payload":{"contract_version":"documents_green_physical_acceptance_v1"}}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:(claim,200))
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:{
        "completed":True,"result":args[1]})
    import modules.documents.green_print_api as api
    monkeypatch.setattr(api,"execute_claimed_physical_page_acceptance",
        lambda claimed,owner,connect_factory=None:{
            "physical_page_confirmed":confirmed,
            "physical_observation_result":claimed["selected_action"],
            "follow_up_state":"exception_owned","automatic_reprint":False})
    result,status=runtime.handle_protected_action_input(
        {**parsed(""),"callback_data":"oompa:PHYSICAL-1:change"},authority())
    assert status==200 and result["status"]==expected_status
    assert result["physical_observation_result"]==selected_action
    assert result["automatic_reprint"] is False and result["printer_calls"]==0


def test_beacon_finish_callback_returns_private_summary_and_separate_later_actions(monkeypatch):
    preview={"contract_version":"beacon_private_album_finish_v1",
        "intake_group_id":"BEACON-INTAKE-GROUP-ONE","canonical_digest":"d"*64,
        "stored_count":4,"completion_code":"INTERNAL","owner_context":"Molly, litter size eight"}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
        "success":True,"status":"protected_callback_claimed","callback_token":"opaque",
        "action_kind":"beacon_private_album_finish","mission_id":"BEACON-INTAKE-GROUP-ONE",
        "preview_payload":preview},200))
    import modules.beacon.media_intake as intake
    monkeypatch.setattr(intake,"complete_claimed_telegram_album",lambda *args,**kwargs:({
        "success":True,"status":"album_completed","received_count":4,"attention_count":0,
        "owner_context":"Molly, litter size eight","contact_sheet_available":True},201))
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:{
        "completed":True,"replayed":False,"result":args[1]})
    result,status=runtime.handle_protected_action_input(
        {**parsed(""),"reply_to_message_id":"4001","callback_data":"oompa:opaque:confirm"},authority())
    assert status==201 and result["specialist"]=="BEACON_MEDIA"
    assert "4 stored photographs" in result["answer"] and "Molly" in result["answer"]
    assert "Accept to Library" in result["answer"] and "Approve Public Use" in result["answer"]
    assert result["reply_markup"]=={"inline_keyboard":[]}


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


def test_irrigation_confirmation_uses_existing_protected_callback_once(monkeypatch):
    payload={"mission_id":"RMQ-20260813-04","job_id":"JOB-1"}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_claimed","callback_token":"opaque",
      "action_kind":"rootline_irrigation_segment","mission_id":"RMQ-20260813-04",
      "preview_digest":"d"*64,"preview_payload":payload},200))
    completed=[]
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:completed.append(args) or {
      "completed":True,"replayed":False,"result":args[1]})
    calls=[]
    def handler(claim,**kwargs):
        calls.append((claim,kwargs));return {"success":True,"status":"segment_started",
          "hardware_commands":1,"provider_control_calls":1},200
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),irrigation_handler=handler)
    assert status==200 and result["status"]=="segment_started"
    assert len(calls)==1 and len(completed)==1
    assert result["mission_id"]=="RMQ-20260813-04"
    assert result["card_mission_id"].startswith("RMQ-20260813-04:PROTECTED:")
    assert result["reply_markup"]=={"inline_keyboard":[]}
    assert result["owner_visible_completion_policy"]=="verified_edit_or_new_message"


def test_completed_irrigation_callback_retries_delivery_without_execution(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_completed_delivery_retry",
      "action_kind":"rootline_irrigation_segment","mission_id":"RMQ-20260813-04",
      "preview_digest":"d"*64,"result":{"success":True,"status":"segment_started",
        "hardware_commands":1,"provider_control_calls":1}},200))
    calls=[]
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:calls.append(args))
    assert status==200 and calls==[]
    assert result["hardware_commands"]==0 and result["provider_control_calls"]==0
    assert result["reply_markup"]=={"inline_keyboard":[]}


def test_completed_beacon_media_callback_retries_delivery_without_decision_write(monkeypatch):
    prior={"success":True,"status":"private_media_review_recorded",
      "answer":"Library decision recorded once.","mission_id":"GROUP:LIBRARY",
      "card_mission_id":"GROUP:LIBRARY","callback_token":"followup",
      "reply_markup":{"inline_keyboard":[[{"text":"Approve Public Use",
        "callback_data":"oompa:followup:confirm"}]]}}
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_completed_delivery_retry",
      "action_kind":"beacon_media_review","mission_id":"GROUP:LIBRARY",
      "preview_digest":"d"*64,"result":prior},200))
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority())
    assert status==200 and result["delivery_recovery_required"] is True
    assert result["callback_token"]=="followup" and result["writes_farm_data"] is False
    assert result["answer"]=="Library decision recorded once."


def test_irrigation_exception_retains_executing_claim_for_provider_retry(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_claimed","callback_token":"opaque",
      "action_kind":"rootline_irrigation_segment","mission_id":"RMQ-20260813-04",
      "preview_digest":"d"*64,"preview_payload":{}},200))
    contained=[]
    monkeypatch.setattr(runtime,"contain_claim",lambda *args,**kwargs:contained.append(args))
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:(_ for _ in ()).throw(ConnectionError("restart")))
    assert status==503 and result["recovery_required"] is True
    assert result["hardware_commands"] is None and result["provider_control_calls"] is None
    assert contained==[]


def test_retried_provider_receipt_recovers_irrigation_after_restart(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_recovered","callback_token":"opaque",
      "action_kind":"rootline_irrigation_segment","mission_id":"RMQ-20260813-04",
      "preview_digest":"d"*64,"preview_payload":{}},200))
    completed=[]
    monkeypatch.setattr(runtime,"complete_claim",lambda *args,**kwargs:completed.append(args) or {
      "completed":True,"result":args[1]})
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:({"success":True,"status":"active_segment_owned",
        "hardware_commands":0,"provider_control_calls":0},200))
    assert status==200 and result["status"]=="active_segment_owned" and len(completed)==1


def test_stale_irrigation_confirmation_never_reaches_runner(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":False,"status":"protected_callback_expired"},409))
    calls=[]
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:calls.append(args))
    assert status==409 and result["status"]=="protected_callback_expired" and calls==[]


def test_callback_claim_lock_timeout_returns_bounded_hold_without_dispatch(monkeypatch):
    QueryCanceled=type("QueryCanceled",(Exception,),{"__module__":"psycopg.errors"})
    monkeypatch.setattr(runtime,"claim_callback",
      lambda *args,**kwargs:(_ for _ in ()).throw(QueryCanceled("statement timeout")))
    calls=[]
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:calls.append(args))
    assert status==503 and result["status"]=="protected_claim_store_degraded_hold"
    assert result["hardware_commands"]==result["provider_control_calls"]==0
    assert result["current_segment_consumed"] is None
    assert result["segment_consumption_proven"] is False and calls==[]


def test_irrigation_database_degraded_hold_contains_claim_and_clears_card(monkeypatch):
    monkeypatch.setattr(runtime,"claim_callback",lambda *args,**kwargs:({
      "success":True,"status":"protected_callback_claimed","callback_token":"opaque",
      "action_kind":"rootline_irrigation_segment","mission_id":"RMQ-20260813-04",
      "preview_digest":"d"*64,"preview_payload":{}},200))
    contained=[]
    monkeypatch.setattr(runtime,"contain_claim",lambda *args,**kwargs:contained.append(args))
    result,status=runtime.handle_protected_action_input(
      {**parsed(""),"callback_data":"oompa:opaque:confirm"},authority(),
      irrigation_handler=lambda *args,**kwargs:({"success":True,
        "status":"execution_store_degraded_hold","hardware_commands":0,
        "provider_control_calls":0,"writes_farm_data":False},200))
    assert status==200 and len(contained)==1
    assert result["status"]=="execution_store_degraded_hold"
    assert result["reply_markup"]=={"inline_keyboard":[]}
    assert result["hardware_commands"]==result["provider_control_calls"]==0
    assert "No controller command" in result["answer"]


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


def test_direct_callback_preserves_digest_scoped_card_lifecycle(monkeypatch):
    owner="5721652188";secret="s"*48
    env={"OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED":"1","OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED":"1",
      "OOM_SAKKIE_TELEGRAM_BOT_TOKEN":"123456789:"+"A"*40,
      "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET":secret,"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":owner,
      "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID":owner}
    card_id="RMQ-20260813-04:PROTECTED:"+"D"*24
    monkeypatch.setattr(telegram_direct,"handle_protected_action_input",lambda *args,**kwargs:({
      "success":True,"status":"segment_started","answer":"Started","specialist":"ROOTLINE",
      "mission_id":"RMQ-20260813-04","card_mission_id":card_id},200))
    delivered=[]
    monkeypatch.setattr(telegram_direct,"deliver_family_result",lambda *args,**kwargs:delivered.append(kwargs) or {"success":True,"telegram_sends":0,"telegram_edits":1})
    monkeypatch.setattr(telegram_direct,"acknowledge_telegram_callback",lambda *args,**kwargs:({"success":True},200))
    payload={"callback_query":{"id":"cb-stable","data":"oompa:opaque:confirm","from":{"id":int(owner)},
      "message":{"message_id":700,"chat":{"id":int(owner),"type":"private"}}}}
    result,status=handle_telegram_direct_webhook(payload,headers={"X-Telegram-Bot-Api-Secret-Token":secret},environ=env)
    assert status==200 and delivered==[{"specialist":"ROOTLINE","mission_id":"RMQ-20260813-04","card_mission_id":card_id}]


def test_direct_callback_requests_provider_retry_when_completion_edit_fails(monkeypatch):
    owner="5721652188";secret="s"*48
    env={"OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED":"1","OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED":"1",
      "OOM_SAKKIE_TELEGRAM_BOT_TOKEN":"123456789:"+"A"*40,
      "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET":secret,"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":owner,
      "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID":owner}
    monkeypatch.setattr(telegram_direct,"handle_protected_action_input",lambda *args,**kwargs:({
      "success":True,"status":"segment_started","answer":"Started","specialist":"ROOTLINE",
      "mission_id":"RMQ-20260813-04","card_mission_id":"CARD"},200))
    monkeypatch.setattr(telegram_direct,"deliver_family_result",lambda *args,**kwargs:{"success":False,"telegram_sends":0,"telegram_edits":0})
    monkeypatch.setattr(telegram_direct,"acknowledge_telegram_callback",lambda *args,**kwargs:({"success":True},200))
    payload={"callback_query":{"id":"cb-retry","data":"oompa:opaque:confirm","from":{"id":int(owner)},
      "message":{"message_id":700,"chat":{"id":int(owner),"type":"private"}}}}
    result,status=handle_telegram_direct_webhook(payload,headers={"X-Telegram-Bot-Api-Secret-Token":secret},environ=env)
    assert status==503 and result["success"] is False


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


def test_farrowing_claim_uses_dedicated_executor_and_completes_once(monkeypatch):
    claim = {"success": True, "status": "protected_callback_claimed",
        "callback_token": "LITTER-CLAIM", "action_kind": "herdmaster_record_farrowing_litter",
        "mission_id": "OOM-HERD-LITTER-1", "preview_payload": {"operation_id": "HERD-LITTER-1"}}
    monkeypatch.setattr(runtime, "claim_callback", lambda *args, **kwargs: (claim, 200))
    from modules.oom_sakkie import herdmaster_farrowing_runtime as litter_runtime
    monkeypatch.setattr(litter_runtime, "execute_claimed_farrowing_litter",
        lambda *args, **kwargs: ({"success": True, "status": "farrowing_litter_recorded",
            "litter_id": "LIT-OOM-1", "writes_farm_data": True}, 201))
    monkeypatch.setattr(runtime, "complete_claim", lambda *args, **kwargs: {
        "completed": True, "result": args[1]})
    result, status = runtime.handle_protected_action_input(
        {**parsed(""), "callback_data": "oompa:LITTER-CLAIM:confirm"}, authority())
    assert status == 201
    assert result["status"] == "farrowing_litter_recorded"
    assert result["litter_id"] == "LIT-OOM-1"


def test_completed_farrowing_result_is_returned_for_provider_delivery_recovery(monkeypatch):
    completed = {"success": True, "status": "protected_callback_completed_delivery_retry",
        "action_kind": "herdmaster_record_farrowing_litter", "mission_id": "OOM-LITTER-1",
        "result": {"success": True, "status": "farrowing_litter_recorded",
            "litter_id": "LIT-1", "answer": "Litter recorded and read back."}}
    monkeypatch.setattr(runtime, "claim_callback", lambda *args, **kwargs: (completed, 200))
    result, status = runtime.handle_protected_action_input(
        {**parsed(""), "callback_data": "oompa:LITTER-CLAIM:confirm"}, authority())
    assert status == 200
    assert result["delivery_recovery_required"] is True
    assert result["answer"] == "Litter recorded and read back."
    assert result["writes_farm_data"] is False
