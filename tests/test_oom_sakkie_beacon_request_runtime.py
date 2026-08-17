import threading
from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.beacon_request_runtime import (
    build_current_beacon_proposal, build_live_stock_awareness_proposal,
    build_scheduled_sale_ready_stock_result, handle_beacon_request,
    render_beacon_packet)
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


def public_awareness_media(trusted=True):
    return {"success": True, "items": [{"binary_asset_id": "BEACON-BINARY-1",
        "beacon_asset_id": "BEACON-ASSET-1", "content_sha256": ("b" * 64 if trusted else "not-a-hash"),
        "observed_mime_type": "image/jpeg", "latest_library_event": "library_accepted",
        "current_library_accept_event_id": "LIBRARY-ACCEPT-1",
        "current_public_use_event_id": "PUBLIC-USE-1", "effective_public_use_approved": True,
        "private_storage_proof_id": "BEACON-BINARY-1:readback:" + "b" * 64,
        "observation": {"tags": ["live_stock", "piglets"]}}]}


def parsed(text="Please prepare the current marketing proposal", language="en"):
    return {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_message_id": "9001",
        "provider_timestamp": "2026-08-14T08:01:00+00:00", "text": text,
        "semantic": {"domain": "beacon", "intent": "current_marketing_proposal", "message_kind": "request",
            "language": language, "needs_clarification": False}}


def awareness_candidate(media_status="media_gap"):
    media_value = ({"status": "approved_media_selected", "asset_id": "PUBLIC-ASSET-1",
        "media_type": "image", "content_sha256": "b" * 64,
        "content_hash_provenance": "server_computed_on_upload", "public_use_approved": True}
        if media_status == "approved" else {"status": "media_gap"})
    return {"success": True, "owner_review_packet": {"packet_id": "SOURCE-PACKET",
        "audience": "People interested in responsible local livestock and farm life",
        "draft_copy": ("A small moment from life at Amadeus Farm. Patient daily care matters.\n\n"
            "Follow the farm journey for more honest moments from behind the scenes."),
        "media": media_value, "public_livestock_policy": {
            "policy_version": "beacon_public_livestock_awareness_only_v1"}}}


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


def test_scheduled_result_binds_material_stock_and_media_evidence():
    fixed = {"content_evidence_loader": lambda **kwargs: kwargs,
        "content_candidate_builder": lambda evidence: awareness_candidate(),
        "now": datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)}
    first = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(), media_loader=lambda: public_awareness_media(), **fixed)
    changed = opportunity()
    changed["cards"][0]["demand_summary"] = {"qualified_units": 2}
    changed_stock = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: changed, media_loader=lambda: public_awareness_media(), **fixed)
    changed_media = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(),
        media_loader=lambda: public_awareness_media(trusted=False), **fixed)
    assert first["proposal"]["packet_id"]
    assert first["result_digest"] != changed_stock["result_digest"]
    assert first["result_digest"] != changed_media["result_digest"]
    assert first["publishes"] is False and first["customer_sends"] is False
    package = first["proposal"]["protected_campaign_package"]
    assert package["delivery_due_policy"] == "same_cycle_on_new_or_changed_evidence"
    assert package["publication_time"] == "2026-08-18T18:00:00+02:00"
    assert package["approval_expires_at"] == package["publication_time"]
    assert package["budget_cap"] == {"currency": "ZAR", "total": "300.00", "daily": "100.00"}
    assert package["duration"] == {"days": 3}
    assert package["authority"]["publication_authorized"] is False
    assert package["authority"]["boost_authorized"] is False
    assert package["attribution_identity"].startswith("BEACON-CAMPAIGN-")
    assert "EXACT PROTECTED FACEBOOK CAMPAIGN" in first["answer"]


def test_scheduled_missing_media_request_keeps_publication_separate():
    result = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(),
        media_loader=lambda: media(accepted=False),
        content_evidence_loader=lambda **kwargs: kwargs,
        content_candidate_builder=lambda evidence: awareness_candidate(),
        now=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc))
    assert result["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert result["proposal"]["authority"]["publishes"] is False
    assert result["proposal"]["protected_campaign_package"]["selected_approved_media"] == {"mode": "text_only"}
    assert "Text-only is suitable" in result["answer"]


def test_missing_commercial_evidence_returns_precise_decision_packet_not_error():
    packet = build_current_beacon_proposal(opportunity(ready=False), media())
    assert packet["packet_type"] == "marketing_evidence_request"
    assert "no_quantified" not in " ".join(packet["missing_evidence"]) or packet["missing_evidence"]
    answer = render_beacon_packet(packet)
    assert "CURRENT EVIDENCE REQUEST" in answer
    assert "One protected decision" in answer
    assert packet["authority"]["publishes"] is False


def test_blocked_evidence_identity_ignores_scheduler_observation_time():
    first = opportunity(ready=False)
    later = {**opportunity(ready=False), "generated_at":"2026-08-14T09:00:00+00:00"}
    assert build_current_beacon_proposal(first, media())["packet_id"] == \
        build_current_beacon_proposal(later, media())["packet_id"]


def test_exact_failed_awareness_instruction_survives_semantics_and_zero_demand():
    exact_failed_instruction = "Prepare a non-availability farm-awareness campaign."
    request = parsed(exact_failed_instruction)
    request["semantic"]["intent"] = "live_stock_awareness"
    store, _ = memory_store()
    result, status = handle_beacon_request(request, issue_gateway_owner_authority("42", "42"),
        opportunity_loader=lambda: opportunity(ready=False),
        content_evidence_loader=lambda **kwargs: {"canonical": kwargs["opportunity_result"]},
        content_candidate_builder=lambda evidence: awareness_candidate(), event_store=store)
    assert status == 200
    assert result["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert result["proposal"]["capacity_context"]["sam_quantified_buyer_demand"] == 0
    assert result["proposal"]["capacity_context"]["sale_availability_inferred"] is False
    assert "Safe draft copy" in result["answer"]
    assert "Approve / Correct / Decline" in result["answer"]
    assert "no_quantified_uncommitted_live_stock_demand" not in result["answer"]
    assert "{" not in result["answer"]


def test_awareness_selects_only_public_hash_verified_media_or_text_only():
    approved = build_live_stock_awareness_proposal(
        opportunity(ready=False), awareness_candidate("approved"), public_awareness_media())
    assert approved["media"]["status"] == "approved_public_media_selected"
    assert approved["media"]["content_sha256"] == "b" * 64
    text_only = build_live_stock_awareness_proposal(opportunity(ready=False), awareness_candidate(), media())
    assert text_only["media"]["status"] == "text_only"
    assert "portrait photo or short vertical video" in text_only["media"]["request"]
    assert text_only["authority"]["publishes"] is False


def test_awareness_afrikaans_response_is_natural_and_hides_internal_media_ids():
    packet = build_live_stock_awareness_proposal(opportunity(False), awareness_candidate(),
        public_awareness_media(), language="af")
    answer = render_beacon_packet(packet, language="af")
    assert "PLAASBEWUSTHEIDSVOORSTEL" in answer
    assert "Teikengehoor" in answer and "Veilige konsepkopie" in answer
    assert "Keur goed / Korrigeer / Wys af" in answer
    assert "Volg die plaas se reis" in answer
    assert "BEACON-ASSET-1" not in answer and "SHA-256" not in answer


def test_invalid_public_media_lineage_falls_back_to_safe_text_only():
    packet = build_live_stock_awareness_proposal(
        opportunity(False), awareness_candidate("approved"), public_awareness_media(trusted=False))
    assert packet["media"]["status"] == "text_only"


def test_incomplete_demand_and_demand_shaped_capacity_preserve_unknown():
    evidence = opportunity(False)
    evidence["cards"][0]["capacity_calculation"].update({"available_after_buffers": 7})
    evidence["cards"][0]["demand_summary"] = {"qualified_units": 0, "unknown_quantity_records": 1}
    evidence["cards"][0]["blockers"] = ["unknown_live_stock_demand_quantity"]
    packet = build_live_stock_awareness_proposal(evidence, awareness_candidate(), media())
    assert packet["capacity_context"]["herdmaster_safe_fulfilment_capacity"] == "Unknown"
    assert packet["capacity_context"]["sam_quantified_buyer_demand"] == "Unknown"


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
