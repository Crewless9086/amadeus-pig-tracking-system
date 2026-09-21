import json
from unittest.mock import patch
import pytest

from modules.oom_sakkie.telegram_direct import handle_telegram_direct_webhook
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.telegram_gateway import parse_telegram_gateway_payload


OWNER = "9001"
ANTON = "9002"
SECRET = "family-direct-secret-value-32-characters"
TOKEN = "family-gateway-token-value-32-characters"


def binding():
    return {"telegram_user_id": ANTON, "role": "farm_manager", "family_key": "dad",
        "permissions": ["explicit_summary", "farm_observation", "active_follow_up",
            "irrigation_start", "irrigation_continue"],
        "summary_domains": ["water", "weather", "irrigation", "herd", "welfare"],
        "language": "af", "authorization_id": "AUTH-ANTON",
        "authorized_by_user_id": OWNER, "authorized_at": "2026-08-15T08:00:00+02:00"}


def env():
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": f"{OWNER},{ANTON}",
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([binding()]),
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "123456789:" + "x" * 40,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": SECRET,
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TOKEN}


def payload(text="Hoe lyk die weer?"):
    return {"update_id": 7001, "message": {"message_id": 7002,
        "date": 1786880000, "text": text, "from": {"id": int(ANTON)},
        "chat": {"id": int(ANTON), "type": "private"}}}


def callback(data):
    return {"update_id": 7100, "callback_query": {"id": "CB-1", "data": data,
        "from": {"id": int(ANTON)}, "message": {"message_id": 7101,
            "chat": {"id": int(ANTON), "type": "private"}}}}


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.load_family_summary")
def test_direct_text_preserves_farm_manager_principal_and_matches_gateway_authorization(summary, deliver):
    summary.return_value = {"available": True, "summary_lines": ["Weerbewyse: fresh"]}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    direct, direct_status = handle_telegram_direct_webhook(payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert direct_status == 200 and direct["family_role"] == "farm_manager"
    assert direct["language"] == "af" and direct["message"]["capability"] == "explicit_summary"
    assert direct["message"]["summary_domain"] == "weather"
    assert direct["authorization_id"] == "AUTH-ANTON"
    assert direct["writes"] is False and direct["hardware_commands"] == 0
    assert deliver.call_count == 1


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_direct_unclassified_manager_text_asks_precise_question_without_owner_fallback(deliver):
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    with patch("modules.oom_sakkie.telegram_direct.handle_owner_task_input") as owner_handler, \
            patch("modules.oom_sakkie.telegram_direct.handle_message") as generic:
        result, status = handle_telegram_direct_webhook(payload("Wat kort my aandag?"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["status"] == "family_clarification_required"
    assert result["answer"].count("?") == 1 and result["language"] == "af"
    assert result["records_audit_trace"] is False
    owner_handler.assert_not_called(); generic.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.load_family_summary")
def test_gateway_and_direct_select_same_role_capability_domain(summary, deliver):
    summary.return_value = {"available": True, "summary_lines": ["Weerbewyse: fresh"]}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    gateway, status = handle_telegram_gateway_message(payload(),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 200
    assert gateway["message"]["family_role"] == "farm_manager"
    assert gateway["message"]["capability"] == "explicit_summary"
    assert gateway["message"]["summary_domain"] == "weather"
    assert gateway["message"]["authorization_id"] == "AUTH-ANTON"


@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
def test_gateway_routes_manager_afrikaans_mortality_through_shared_operational_lifecycle(
        health, deliver, family_runtime):
    health.return_value = ({"handled": True, "success": True,
        "status": "waiting_for_input", "answer": "Een vraag: Op watter datum?",
        "records_audit_trace": True, "writes_farm_data": False}, 200)
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    result, status = handle_telegram_gateway_message(
        payload("Vark 126 is dood, ons het hom verwyder en begrawe."),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 200 and result["message"]["status"] == "waiting_for_input"
    inbound = health.call_args.args[0]
    assert inbound["output_language"] == "af"
    assert inbound["text"].startswith("Vark 126 is dood")
    family_runtime.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.herdmaster_family_observation")
@patch("modules.oom_sakkie.telegram_gateway.handle_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
def test_manager_can_never_fall_back_to_legacy_observation_only_mortality_branch(
        health, deliver, owner_task, generic_core_or_charlie, legacy_observation, family_runtime):
    health.return_value = ({"handled": False, "status": "health_loss_intake_not_applicable"}, 200)
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    def invoke_selected_adapter(parsed, principal, *, observation_adapter, **_kwargs):
        return observation_adapter(parsed=parsed, principal=principal,
            capability="found_dead_observation", replay_identity="manager-fallback"), 200
    family_runtime.side_effect = invoke_selected_adapter
    manager_env = env()
    manager_binding = binding()
    manager_binding["permissions"] += ["found_dead_observation", "mortality_confirmation"]
    manager_env["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"] = json.dumps([manager_binding])
    result, status = handle_telegram_gateway_message(
        payload("Vark 126 is dood, ons het hom verwyder en begrawe."),
        headers={"Authorization": "Bearer " + TOKEN}, environ=manager_env)
    assert status == 200
    assert result["message"]["status"] == "farm_manager_operational_clarification_required"
    assert result["message"]["legacy_observation_path_used"] is False
    assert "Charl se afsonderlike bevestiging" not in result["answer"]
    legacy_observation.assert_not_called()
    generic_core_or_charlie.assert_not_called()
    owner_task.assert_not_called()


@pytest.mark.parametrize("request_text", [
    "CORE, verander die produksiekode en ontplooi dit nou.",
    "CHARLIE, begin 'n ontwikkelingstaak en stuur dit aan die agent.",
])
@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_manager_core_and_charlie_requests_have_zero_dispatch_or_owner_task_effects(
        deliver, owner_task, generic, family_runtime, request_text):
    family_runtime.return_value = ({"success": False,
        "status": "family_private_capability_denied", "answer": "",
        "writes_farm_data": False, "hardware_commands": 0}, 403)
    result, status = handle_telegram_gateway_message(payload(request_text),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 403
    assert result["writes"] is False and result["hardware_commands"] == 0
    assert result["sends_telegram"] is False
    owner_task.assert_not_called()
    generic.assert_not_called()
    deliver.assert_not_called()


def test_family_principals_cannot_enter_sam_owner_callbacks_or_owner_media():
    with patch("modules.oom_sakkie.telegram_direct.process_owner_attention_callback") as attention, \
            patch("modules.oom_sakkie.telegram_direct.process_sam_live_stock_owner_callback") as sam:
        result, status = handle_telegram_direct_webhook(callback("sam_live_owner_decision:x"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    attention.assert_not_called(); sam.assert_not_called()
    media = payload("")
    media["message"].pop("text")
    media["message"]["photo"] = [{"file_id": "FILE", "file_unique_id": "UNIQUE",
                                    "width": 10, "height": 10}]
    with patch("modules.oom_sakkie.telegram_direct.handle_telegram_media_intake") as intake:
        result, status = handle_telegram_direct_webhook(media,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    intake.assert_not_called()


def test_sam_callback_requires_exact_private_owner_chat():
    owner_env = env(); owner_env["OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"] = f"{OWNER},{ANTON}"
    item = callback("sam_live_owner_decision:x")
    item["callback_query"]["from"]["id"] = int(OWNER)
    item["callback_query"]["message"]["chat"]["id"] = 9999
    with patch("modules.oom_sakkie.telegram_direct.process_owner_attention_callback") as attention:
        result, status = handle_telegram_direct_webhook(item,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=owner_env)
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    attention.assert_not_called()


def test_owner_text_requires_exact_private_chat_before_owner_handlers():
    owner_env = env()
    for chat_id, chat_type in ((9999, "private"), (int(OWNER), "group")):
        item = payload("Wat kort aandag?")
        item["message"]["from"]["id"] = int(OWNER)
        item["message"]["chat"] = {"id": chat_id, "type": chat_type}
        with patch("modules.oom_sakkie.telegram_direct.handle_owner_task_input") as owner_handler, \
                patch("modules.oom_sakkie.telegram_direct.handle_message") as generic:
            result, status = handle_telegram_direct_webhook(item,
                headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=owner_env)
        assert status == 403 and result["status"] == "telegram_family_identity_not_authorized"
        owner_handler.assert_not_called(); generic.assert_not_called()


@patch("modules.oom_sakkie.telegram_direct.acknowledge_telegram_callback")
@patch("modules.oom_sakkie.telegram_direct.handle_family_rootline_callback")
def test_direct_delegated_callback_resolves_anton_and_acknowledges_once(handler, acknowledge):
    handler.return_value = ({"success": True, "status": "delegated_callback_retained",
        "answer": "", "hardware_commands": 0, "suppress_family_delivery": True}, 200)
    acknowledge.return_value = ({"success": True, "status": "telegram_callback_acknowledged"}, 200)
    result, status = handle_telegram_direct_webhook(callback("oomfm:TOKEN:confirm"),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["status"] == "delegated_callback_retained"
    assert handler.call_count == 1 and handler.call_args.args[1].role.value == "farm_manager"
    acknowledge.assert_called_once()


@patch("modules.oom_sakkie.telegram_direct.acknowledge_telegram_callback")
@patch("modules.oom_sakkie.telegram_direct.handle_family_rootline_callback")
def test_family_callback_wrong_chat_or_antoinette_never_reaches_contract(handler, acknowledge):
    acknowledge.return_value = ({"success": True}, 200)
    bad = callback("oomfm:TOKEN:confirm")
    bad["callback_query"]["message"]["chat"]["id"] = 9999
    result, status = handle_telegram_direct_webhook(bad,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "family_rootline_callback_unauthorized"
    handler.assert_not_called(); acknowledge.assert_called_once()


@patch("modules.oom_sakkie.family_rootline_callback.bind_claim_card", return_value=True)
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_direct_webhook_derives_zero_effect_rootline_preview_and_binds_card(deliver, _bind):
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    auth = {"active": True, "revoked_at": None, "owner_authority": False,
        "principal_id": ANTON, "private_chat_id": ANTON, "role": "farm_manager",
        "capabilities": ["routine_irrigation_execute"], "zones": ["B"],
        "commissioned_paths": ["PATH-B"], "authorization_digest": "a" * 64}
    eligibility = {"status": "execution_eligible", "zone_id": "B",
        "commissioned_path_id": "PATH-B", "maximum_duration_seconds": 300,
        "plan_generation": "GEN-1", "job_id": "JOB-1", "job_sha256": "b" * 64,
        "segment_identity": "SEG-1", "current_segment": 1, "execution_id": "EX-1",
        "eligibility_sha256": "c" * 64, "consumption_key": "CONSUME-1"}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0,
                            "provider_message_id": "CARD-1"}
    def claim(**kwargs):
        return {"success": True, "callback_token": "TOKEN",
            "preview_digest": canonical_preview_digest("rootline_delegated_family",
                                                        kwargs["preview_payload"])}
    with patch("modules.telemetry.rootline_delegated_principal.load_delegated_authorization",
               return_value=auth), \
            patch("modules.oom_sakkie.family_specialist_adapters._load_rootline_eligibility",
                  return_value=eligibility), \
            patch("modules.telemetry.rootline_execution_authority.validate_execution_eligibility",
                  return_value=eligibility), \
            patch("modules.oom_sakkie.family_rootline_callback.create_claim", side_effect=claim), \
            patch("modules.oom_sakkie.telegram_gateway.family_replay_store",
                  return_value={"success": True, "created": True}):
        result, status = handle_telegram_direct_webhook(payload("Begin besproeiing"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["message"]["status"] == "family_rootline_preview_ready"
    assert result["preview_card_bound"] is True
    assert result["hardware_commands"] == 0 and result["writes"] is False


def test_gateway_callback_uses_authenticated_receipt_time_not_old_card_time():
    item = callback("oomfm:TOKEN:confirm")
    item["callback_query"]["message"]["date"] = 1_700_000_000
    parsed = parse_telegram_gateway_payload(item)
    assert parsed["source_card_timestamp"].startswith("2023-")
    assert parsed["provider_timestamp"] != parsed["source_card_timestamp"]
    assert parsed["provider_message_id"] == "CB-1"
    assert parsed["reply_to_message_id"] == "7101"
    assert parsed["callback_query_id"] == "CB-1"


# First convergence slice: real authenticated wrappers and family delivery, with
# synthetic specialist results and inert stores/providers. No cutover claim.
@pytest.fixture
def shared_ingress(monkeypatch):
    from copy import deepcopy
    from threading import Lock
    from unittest.mock import Mock
    from modules.oom_sakkie import telegram_direct as direct, telegram_gateway as gateway
    from modules.oom_sakkie import family_message_lifecycle as family
    for name in ("handle_owner_task_input", "handle_auction_confirmation", "handle_protected_action_input",
        "handle_litter_first_treatment_message", "handle_documents_green_request",
        "handle_grouped_weight_message", "handle_grouped_breeding_message", "handle_manager_question_reply",
        "handle_owner_operational_continuation", "handle_operational_specialist_message",
        "handle_authenticated_health_loss_message", "handle_farrowing_litter_message",
        "handle_herdmaster_request", "handle_beacon_request"):
        monkeypatch.setattr(gateway, name, Mock(return_value=({"handled": False}, 200)))
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_litter_weaning_runtime.handle_litter_weaning_message",
                        Mock(return_value=({"handled": False}, 200)))
    for name in ("recover_contextual_specialist_replay", "load_active_manager_question", "interpret_owner_message"):
        monkeypatch.setattr(gateway, name, Mock(return_value=None))
    farm = Mock(side_effect=lambda parsed, authority: ({"handled": True, "success": True,
        "status": "farm_manager_round_ready", "answer": (
            "Die plaas is veilig; geen aksie word nou benodig nie." if parsed["output_language"] == "af"
            else "The current farm review is ready."), "records_audit_trace": True,
        "writes_farm_data": False, "hardware_commands": 0}, 200))
    monkeypatch.setattr(gateway, "handle_farm_manager_round", farm)
    for name in ("send_owner_telegram_reply", "handle_message", "approve_first_waiting_sales_campaign"):
        monkeypatch.setattr(direct, name, Mock(side_effect=AssertionError("legacy fallback used")))
    rows, calls, lock = {}, [], Lock()
    behavior = {"send": {"success": True, "telegram_message_id": "90001"}, "fail_state": ""}
    def store(action, identity, value):
        with lock:
            if action == "load":
                return [deepcopy(row) for row in rows.values() if row["card_mission_id"] == identity]
            if value["state"] == behavior["fail_state"]:
                return {"success": False, "created": None}
            created = identity not in rows
            if created: rows[identity] = deepcopy(value)
            return {"success": True, "created": created}
    def send(*args, **kwargs):
        calls.append((args, kwargs)); return dict(behavior["send"])
    monkeypatch.setattr(family, "_event_store", store)
    monkeypatch.setattr(family, "_send_telegram", send)
    monkeypatch.setattr(family, "_edit_telegram", Mock(side_effect=AssertionError("unexpected edit")))
    def invoke(transport, item, *, source=None, extra_headers=None, bad_auth=False):
        source = env() if source is None else source
        headers = ({"Authorization": "Bearer " + source["OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN"]}
                   if transport == "relay" else {"X-Telegram-Bot-Api-Secret-Token": source["OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET"]})
        if bad_auth: headers = {key: "wrong" for key in headers}
        headers.update(extra_headers or {})
        fn = handle_telegram_gateway_message if transport == "relay" else handle_telegram_direct_webhook
        return fn(item, headers=headers, environ=source)
    return invoke, farm, rows, calls, behavior


@pytest.mark.parametrize("order", [("relay", "direct"), ("direct", "relay")])
@pytest.mark.parametrize("actor", [OWNER, ANTON])
def test_native_text_cross_ingress_has_same_identity_language_and_one_delivery(shared_ingress, order, actor):
    from copy import deepcopy
    invoke, farm, rows, calls, _ = shared_ingress
    item = payload("Gee vandag se plaasprioriteite.")
    item["message"]["from"]["id"] = int(actor)
    item["message"]["chat"]["id"] = int(actor)
    item["message"]["reply_to_message"] = {"message_id": 6123}
    original = deepcopy(item)
    first, first_code = invoke(order[0], item)
    second, second_code = invoke(order[1], item)
    assert first_code == second_code == 200
    assert first["sends_telegram"] is True and second["sends_telegram"] is False
    assert len(calls) == 1 and len(rows) == 2 and item == original
    left, right = [call.args[0] for call in farm.call_args_list]
    assert left == right
    assert left["provider_message_id"] == "7002" and left["reply_to_message_id"] == "6123"
    assert left["session_id"] == "telegram-" + actor
    assert left["output_language"] == ("en" if actor == OWNER else "af")
    assert {row["state"] for row in rows.values()} == {"delivery_attempted", "delivered"}
    assert first["telegram_intake"] != second["telegram_intake"]
    assert all(not body["writes"] for body in (first, second))


@pytest.mark.parametrize("transport", ["relay", "direct"])
@pytest.mark.parametrize("change", [
    {"telegram_user_id": OWNER}, {"from_user_id": OWNER}, {"telegram_chat_id": OWNER},
    {"chat_id": OWNER}, {"telegram_chat_type": "group"}, {"text": "approve campaign"},
    {"session_id": OWNER}, {"provider_message_id": "999"}, {"message_id": "999"},
    {"reply_to_message_id": "999"}, {"callback_data": "oom:fake:confirm"},
    {"provider_timestamp": "2026-01-01T00:00:00+00:00"}])
def test_native_flat_conflicts_fail_before_authority_or_delivery(shared_ingress, transport, change):
    invoke, farm, rows, calls, _ = shared_ingress
    body, code = invoke(transport, {**payload(), **change})
    assert code == 400 and body["success"] is False
    assert body["status"] == "telegram_native_flat_conflict"
    farm.assert_not_called(); assert not rows and not calls


@pytest.mark.parametrize("transport", ["relay", "direct"])
@pytest.mark.parametrize("invalid", ["auth", "unknown", "bot", "group", "wrong_chat", "mixed", "edited", "malformed"])
def test_invalid_native_identity_never_dispatches_or_transcribes(shared_ingress, monkeypatch, transport, invalid):
    from unittest.mock import Mock
    from modules.oom_sakkie import telegram_gateway as gateway
    invoke, farm, rows, calls, _ = shared_ingress
    voice = Mock(side_effect=AssertionError("unauthorized STT"))
    monkeypatch.setattr(gateway, "prepare_telegram_voice_input", voice)
    item = payload()
    if invalid == "unknown": item["message"]["from"]["id"] = 999
    if invalid == "bot": item["message"]["from"]["is_bot"] = True
    if invalid == "group": item["message"]["chat"]["type"] = "group"
    if invalid == "wrong_chat": item["message"]["chat"]["id"] = 999
    if invalid == "mixed": item["callback_query"] = callback("oomfm:X:confirm")["callback_query"]
    if invalid == "edited": item["edited_message"] = item.pop("message")
    if invalid == "malformed": item["message"]["from"] = []
    body, code = invoke(transport, item, bad_auth=invalid == "auth")
    assert code >= 400 and body["success"] is False
    farm.assert_not_called(); voice.assert_not_called(); assert not rows and not calls


@pytest.mark.parametrize("failure,expected_sends", [("delivery_attempted", 0), ("delivered", 1), ("ambiguous", 1)])
def test_cross_ingress_failed_claim_or_uncertain_result_never_falls_back(shared_ingress, failure, expected_sends):
    invoke, _, _, calls, behavior = shared_ingress
    if failure == "ambiguous": behavior["send"] = {"success": False}
    else: behavior["fail_state"] = failure
    first, first_code = invoke("direct", payload())
    second, _ = invoke("relay", payload())
    assert first["success"] is False and first_code >= 202
    assert first["delivery"]["success"] is False and second["delivery"]["success"] is False
    assert len(calls) == expected_sends


def test_direct_missing_durable_generic_delivery_is_unavailable_without_legacy_sender(shared_ingress, monkeypatch):
    from unittest.mock import Mock
    from modules.oom_sakkie import telegram_gateway as gateway
    invoke, farm, _, calls, _ = shared_ingress
    farm.return_value = ({"handled": False}, 200); farm.side_effect = None
    monkeypatch.setattr(gateway, "handle_message", Mock(return_value=({"success": True, "answer": "Prepared answer"}, 200)))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    item = payload("Ordinary owner request")
    item["message"]["from"]["id"] = int(OWNER); item["message"]["chat"]["id"] = int(OWNER)
    body, code = invoke("direct", item)
    assert code == 503 and body["status"] == "telegram_direct_durable_delivery_unavailable"
    assert body["success"] is False and not calls
    relay, relay_code = invoke("relay", item)
    assert relay_code == 200 and relay["reply_transport"] == "caller_handles_telegram_send"


def test_direct_cannot_select_relay_internal_proof_delivery_suppression(shared_ingress, monkeypatch):
    from unittest.mock import Mock
    from modules.oom_sakkie import telegram_gateway as gateway
    invoke, _, _, calls, _ = shared_ingress
    monkeypatch.setattr(gateway, "handle_beacon_request", Mock(return_value=({"handled": True,
        "success": True, "status": "beacon_review_ready", "answer": "Die voorstel is gereed; bevestig die hersiening."}, 200)))
    item = {**payload(), "internal_proof_identity": "BMQ-SYNTHETIC"}
    headers = {"X-Oom-Sakkie-Delivery-Mode": "disabled-internal-proof"}
    relay, _ = invoke("relay", item, extra_headers=headers)
    assert relay["delivery_disabled_internal_proof"] is True and not calls
    direct, _ = invoke("direct", item, extra_headers=headers)
    assert direct["delivery_disabled_internal_proof"] is False and len(calls) == 1


@pytest.mark.parametrize("order", [("relay", "direct"), ("direct", "relay")])
def test_native_voice_cross_ingress_retains_transcript_once_and_uses_shared_dispatch(shared_ingress, monkeypatch, order):
    from copy import deepcopy
    from modules.oom_sakkie import telegram_voice as voice
    from tests.telegram_voice_test_support import CannedVoiceProvider, environment, voice_payload
    invoke, farm, _, sends, _ = shared_ingress
    source = environment(); item = voice_payload(reply="7011"); original = deepcopy(item)
    provider = CannedVoiceProvider(item, "approve campaign")
    retained, bindings = {}, {}
    def claim(identity, binding, _source):
        if identity in bindings: assert bindings[identity] == binding
        bindings[identity] = deepcopy(binding)
        return "SYNTHETIC-ATTEMPT", retained.get(identity)
    def retain(identity, binding, attempt, result, _source):
        assert bindings[identity] == binding
        retained[identity] = deepcopy(result); return retained[identity]
    monkeypatch.setattr(voice, "_claim_input", claim)
    monkeypatch.setattr(voice, "_retain_input", retain)
    monkeypatch.setattr(voice.urllib.request, "build_opener", lambda *args: provider)
    for transport in order:
        body, code = invoke(transport, item, source=source)
        assert code == 200
    assert len(provider.requests) == 3 and len(retained) == 1 and len(sends) == 1
    assert item == original
    left, right = [call.args[0] for call in farm.call_args_list]
    assert left == right and left["text"] == "approve campaign"
    assert left["reply_to_message_id"] == "7011"
    assert left["input_provenance"]["source_kind"] == "telegram_voice"
    assert left["input_provenance"]["reported_input_only"] is True
    bound = next(iter(bindings.values()))
    import hashlib
    assert bound["file_id_sha256"] == hashlib.sha256(item["message"]["voice"]["file_id"].encode()).hexdigest()
    assert bound["file_unique_id"] == item["message"]["voice"]["file_unique_id"]


@pytest.mark.parametrize("transport", ["relay", "direct"])
def test_matching_flat_aliases_do_not_replace_native_string_id_envelope(shared_ingress, transport):
    from datetime import datetime, timezone
    invoke, farm, _, calls, _ = shared_ingress
    item = payload("  Gee die huidige plaasplan.  ")
    item["message"]["from"]["id"] = ANTON
    item["message"]["chat"]["id"] = ANTON
    item.update({"text": item["message"]["text"].strip(), "telegram_user_id": ANTON,
        "telegram_chat_id": ANTON, "telegram_chat_type": "private", "session_id": "telegram-" + ANTON,
        "provider_timestamp": datetime.fromtimestamp(item["message"]["date"], timezone.utc).isoformat().replace("+00:00", "Z")})
    body, code = invoke(transport, item)
    assert code == 200 and body["success"] is True and len(calls) == 1
    received = farm.call_args.args[0]
    assert received["session_id"] == "telegram-" + ANTON
    assert received["text"] == item["message"]["text"].strip()


def test_direct_text_requires_only_its_own_enabled_credential_gate(shared_ingress):
    invoke, farm, _, sends, _ = shared_ingress
    source = env()
    source.pop("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN")
    source["OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED"] = "0"
    item = payload()
    item["message"]["from"]["id"] = ANTON; item["message"]["chat"]["id"] = ANTON
    body, code = invoke("direct", item, source=source)
    assert code == 200 and body["success"] is True and len(sends) == 1
    farm.assert_called_once()
    assert "telegram_gateway" not in body
    assert body["telegram_intake"] == "authenticated_direct_webhook"


def test_native_callback_flat_card_conflict_cannot_reach_compatibility_action_or_acknowledgement():
    item = callback("oomfm:TOKEN:confirm")
    item["telegram_message_id"] = "9999"
    with patch("modules.oom_sakkie.telegram_direct.handle_family_rootline_callback") as action, \
            patch("modules.oom_sakkie.telegram_direct.acknowledge_telegram_callback") as ack:
        body, code = handle_telegram_direct_webhook(item,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert code == 400 and body["status"] == "telegram_native_flat_conflict"
    action.assert_not_called(); ack.assert_not_called()


@pytest.mark.parametrize("identity", ["²", "9" * 5000, True, [], 0, -1])
def test_malformed_native_message_identity_fails_closed_without_dispatch(shared_ingress, identity):
    invoke, farm, _, sends, _ = shared_ingress
    item = payload(); item["message"]["message_id"] = identity
    for transport in ("relay", "direct"):
        body, code = invoke(transport, item)
        assert code == 400 and body["status"] == "telegram_native_provider_identity_malformed"
    farm.assert_not_called(); assert not sends
