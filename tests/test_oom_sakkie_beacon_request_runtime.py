import threading
from unittest.mock import patch

from modules.oom_sakkie.beacon_request_runtime import (
    build_current_beacon_proposal, handle_beacon_request, render_beacon_packet)
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.telegram_gateway import (
    _delivery_disabled_internal_proof, handle_telegram_gateway_message)
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation


def opportunity(ready=True):
    return {"success": True, "generated_at": "2026-08-14T08:00:00+00:00", "cards": [{
        "card_id": "BEACON-CURRENT", "status": "ready_for_owner_review" if ready else "blocked",
        "lane": "live_stock", "category": "weaner", "unit": "animals",
        "opportunity_reason": "Verified eligible supply and quantified uncommitted demand overlap." if ready else "Evidence is incomplete.",
        "capacity_calculation": {"demand_cap": 3 if ready else 0},
        "provenance": {"observed_at": "2026-08-14T08:00:00+00:00"}}]}


def media(accepted=True, public=False):
    return {"success": True, "items": [{"binary_asset_id": "BEACON-BINARY-1",
        "content_sha256": "a" * 64, "latest_library_event": "library_accepted" if accepted else "",
        "latest_review_event_id": "REVIEW-1", "effective_public_use_approved": public,
        "current_library_accept_event_id": "REVIEW-1", "private_storage_proof_id": "STORAGE-1",
        "thumbnail_url": "/private/thumb", "observation": {"tags": ["live_stock", "weaner"]}}]}


def parsed(text="Please prepare the current marketing proposal", language="en"):
    return {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_message_id": "9001",
        "provider_timestamp": "2026-08-14T08:01:00+00:00", "text": text,
        "semantic": {"domain": "beacon", "intent": "current_marketing_proposal", "message_kind": "request",
            "language": language, "needs_clarification": False}}


def memory_store():
    rows, lock = {}, threading.Lock()
    def store(action, identity, payload):
        with lock:
            if action == "load":
                return rows.get(identity)
            if identity in rows:
                return {"success": True, "created": False}
            rows[identity] = payload
            return {"success": True, "created": True}
    return store, rows


def test_current_proposal_contains_commercial_decision_and_keeps_private_media_private():
    packet = build_current_beacon_proposal(opportunity(), media(public=True))
    assert packet["packet_type"] == "marketing_proposal"
    assert packet["expected_commercial_value"].startswith("Create enquiries for up to 3")
    assert packet["exact_media"][0]["public_use_approved"] is False
    assert packet["authority"]["publishes"] is False
    answer = render_beacon_packet(packet)
    assert "One protected decision" in answer
    assert "public use is not approved" in answer
    assert "Measure later" in answer


def test_missing_media_is_precise_and_afrikaans_rendered():
    packet = build_current_beacon_proposal(opportunity(), media(accepted=False))
    assert packet["packet_type"] == "missing_media_request"
    answer = render_beacon_packet(packet, language="af")
    assert "PRESIESE MEDIA-VERSOEK" in answer
    assert "portretfoto" in answer
    assert "Een besluit" in answer
    assert "Teikengehoor:" in answer and "Bewyse:" in answer
    assert "Aanbevole kanaal/kopie:" in answer and "Meet later:" in answer


def test_provider_replay_is_returned_without_second_owner_delivery():
    store, rows = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    first, first_status = handle_beacon_request(parsed(), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    second, second_status = handle_beacon_request(parsed(), authority,
        opportunity_loader=lambda: (_ for _ in ()).throw(AssertionError("must not reload")),
        media_loader=lambda: (_ for _ in ()).throw(AssertionError("must not reload")), event_store=store)
    assert first_status == second_status == 200
    assert first["status"] == "beacon_request_ready"
    assert second["status"] == "beacon_request_replay_recovered"
    assert second.get("suppress_owner_delivery") is not True
    assert len(rows) == 1


def test_provider_identity_conflict_fails_closed():
    store, _ = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    handle_beacon_request(parsed("English request"), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    conflict, status = handle_beacon_request(parsed("Afrikaanse ander inhoud"), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    assert status == 409
    assert conflict["status"] == "beacon_request_provider_binding_conflict"
    assert conflict["publishes"] is False


def test_semantic_paraphrase_not_keywords_controls_dispatch():
    p = parsed("Kan Oom Sakkie vandag iets winsgewend vir ons bemarking voorstel?", "af")
    store, _ = memory_store()
    result, status = handle_beacon_request(p, issue_gateway_owner_authority("42", "42"),
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    assert status == 200
    assert result["specialist_identity"] == "BEACON"
    assert "BEMARKINGSVOORSTEL" in result["answer"]


def test_concurrent_duplicate_requests_create_one_result_and_both_reach_delivery_lifecycle():
    store, rows = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    results = []
    def run():
        results.append(handle_beacon_request(parsed(), authority,
            opportunity_loader=opportunity, media_loader=media, event_store=store)[0])
    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert len(rows) == 1
    assert all(result.get("suppress_owner_delivery") is not True for result in results)
    assert {result["status"] for result in results} <= {"beacon_request_ready", "beacon_request_replay_recovered"}


def test_delivery_disabled_proof_requires_both_authenticated_mode_shape_and_bmq_identity():
    headers = {"X-Oom-Sakkie-Delivery-Mode": "disabled-internal-proof"}
    assert _delivery_disabled_internal_proof({"internal_proof_identity": "BMQ-20260813-04-PROOF"}, headers)
    assert not _delivery_disabled_internal_proof({}, headers)
    assert not _delivery_disabled_internal_proof({"internal_proof_identity": "BMQ-20260813-04-PROOF"}, {})


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message")
def test_delivery_disabled_proof_contains_unresolved_semantics_before_any_delivery(interpret, deliver):
    interpret.return_value = SemanticInterpretation(domain="general", intent="unclear",
        message_kind="request", needs_clarification=True)
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
        "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"}
    payload = {"internal_proof_identity": "BMQ-20260813-04-PROOF",
        "message": {"message_id": 99, "date": 1785790000, "text": "marketing",
            "from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
    with patch.dict("os.environ", env, clear=True), patch(
            "modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay", return_value=None):
        result, status = handle_telegram_gateway_message(payload,
            headers={"Authorization": "Bearer " + "g" * 40,
                "X-Oom-Sakkie-Delivery-Mode": "disabled-internal-proof"})
    assert status == 422 and result["delivery"]["telegram_sends"] == 0
    deliver.assert_not_called()
