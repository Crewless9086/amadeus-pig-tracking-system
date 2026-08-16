import pytest

from modules.oom_sakkie.beacon_media_review_runtime import (
    execute_private_media_review,
    present_private_media_review,
)


@pytest.fixture(autouse=True)
def review_url(monkeypatch):
    monkeypatch.setenv("AMADEUS_BACKEND_URL","https://farm.example.test")


def packet(*, library="pending_or_mixed", eligible=True):
    return {"success":True,"status":"private_album_review_ready",
        "contract_version":"beacon_private_album_review_v1","intake_group_id":"GROUP-BELLA",
        "album_digest":"d"*64,"album_completed_at":"2026-08-15T12:44:52+00:00","stored_count":8,
        "owner_context":"Bellas litter growing fast and coming along well",
        "library_state":library,"public_use_state":"not_approved","public_use_eligible":eligible,
        "later_actions":{"campaign_review":False,"publication":False},
        "ordered_media":[{"album_position":i,"binary_asset_id":f"B-{i}",
          "content_sha256":str(i)*64,"understanding_event_id":f"U-{i}",
          "library_event_id":"" if library!="accepted" else f"L-{i}"}
          for i in range(1,9)]}


PARSED={"telegram_user_id":"100","telegram_chat_id":"100","provider_message_id":"500",
    "semantic":{"language":"en"}}


def loader(value):
    def load(**binding):
        assert binding=={"owner_user_id":"100","private_chat_id":"100"}
        return value,200
    return load


def claim_creator(**kwargs):
    assert kwargs["action_kind"]=="beacon_media_review"
    assert len(kwargs["preview_payload"]["ordered_assets"])==8
    assert kwargs["ttl_minutes"]==10080
    return {"callback_token":"opaque","preview_digest":"p"*64}


def test_library_review_is_owner_friendly_and_grants_no_public_authority():
    result,status=present_private_media_review(PARSED,
        album_loader=loader(packet()),claim_creator=claim_creator)
    assert status==200 and result["status"]=="private_media_review_presented"
    assert "Accept into Private Library" in result["answer"] and "Public Use" in result["answer"]
    assert "digest" not in result["answer"].casefold() and "token" not in result["answer"].casefold()
    assert result["publishes"] is False and result["spends_money"] is False
    assert [b["text"] for b in result["reply_markup"]["inline_keyboard"][0]]==[
        "Accept into Private Library","Decline album for Private Library"]
    assert result["reply_markup"]["inline_keyboard"][1][0]["text"]=="View private contact sheet"


def test_public_use_is_separate_and_withheld_until_compliance_passes():
    blocked,status=present_private_media_review(PARSED,
        album_loader=loader(packet(library="accepted",eligible=False)),claim_creator=claim_creator)
    assert status==200 and blocked["status"]=="private_media_public_use_checks_pending"
    assert blocked["reply_markup"]=={"inline_keyboard":[]}
    ready,status=present_private_media_review(PARSED,
        album_loader=loader(packet(library="accepted",eligible=True)),claim_creator=claim_creator)
    assert status==200 and "Approve Public Use" in ready["answer"]
    assert "campaign approval" in ready["answer"] and ready["publishes"] is False


def test_afrikaans_review_is_natural_and_reason_is_owner_selected():
    parsed={**PARSED,"semantic":{"language":"af"}}
    result,status=present_private_media_review(parsed,
        album_loader=loader(packet()),claim_creator=claim_creator)
    assert status==200
    assert "PRIVAAT MEDIA-HERSIENING" in result["answer"]
    assert "Behoue konteks" in result["answer"] and "Niks" not in result["answer"]
    labels=[button["text"] for row in result["reply_markup"]["inline_keyboard"] for button in row]
    assert labels==["Aanvaar in Privaat Biblioteek","Weier album vir Privaat Biblioteek","Bekyk privaat kontakblad"]
    assert result["review_packet"]["later_actions"]=={"campaign_review":False,"publication":False}


def test_bound_decline_records_reason_and_exact_snapshot_without_other_effects(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.beacon_media_review_runtime.telegram_media_owner_binding",
        lambda owner,chat:{"owner_principal":"telegram-owner:HASH","chat_hmac":"h"*64})
    calls=[]
    claimed={"callback_token":"opaque","preview_digest":"p"*64,"mission_id":"GROUP-BELLA:LIBRARY",
        "evidence_generation":"d"*64,
        "selected_action":"decline","preview_payload":{
          "contract_version":"beacon_private_album_review_v1","decision_type":"library",
          "intake_group_id":"GROUP-BELLA","album_digest":"d"*64,"stored_count":8,
          "approve_event":"library_accepted","decline_event":"library_rejected",
          "decline_reason":"Owner selected: not suitable for the private Library.",
          "ordered_assets":[{"position":i,"binary_asset_id":f"B-{i}",
            "content_sha256":str(i)*64,"understanding_event_id":f"U-{i}",
            "library_event_id":""} for i in range(1,9)]}}
    result,status=execute_private_media_review(claimed,PARSED,
        recorder=lambda group,decision,owner:(calls.append((group,decision,owner)) or
          ({"success":True,"status":"media_group_review_recorded","created_count":8},201)),
        packet_loader=lambda group:(packet(),200),claim_creator=claim_creator)
    assert status==201 and len(calls)==1
    assert calls[0][1]["event_type"]=="library_rejected" and calls[0][1]["notes"]
    assert calls[0][1]["album_digest"]=="d"*64 and len(calls[0][1]["expected_predecessors"])==8
    assert result["publishes"] is False and result["customer_sends"] is False


def test_claim_store_failure_is_contained_without_owner_decision():
    result,status=present_private_media_review(PARSED,
        album_loader=loader(packet()),
        claim_creator=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("store")))
    assert status==503 and result["status"]=="private_media_review_claim_contained"
    assert result["publishes"] is False and "Nothing was approved" in result["answer"]


def test_library_accept_survives_followup_claim_failure_and_keeps_public_use_undecided(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.beacon_media_review_runtime.telegram_media_owner_binding",
        lambda owner,chat:{"owner_principal":"telegram-owner:HASH","chat_hmac":"h"*64})
    claimed={"callback_token":"opaque","preview_digest":"p"*64,"mission_id":"GROUP-BELLA:LIBRARY",
        "evidence_generation":"d"*64,
        "selected_action":"approve","preview_payload":{
          "contract_version":"beacon_private_album_review_v1","decision_type":"library",
          "intake_group_id":"GROUP-BELLA","album_digest":"d"*64,"stored_count":8,
          "approve_event":"library_accepted","decline_event":"library_rejected",
          "ordered_assets":[{"position":i,"binary_asset_id":f"B-{i}",
            "content_sha256":str(i)*64,"understanding_event_id":f"U-{i}",
            "library_event_id":""} for i in range(1,9)]}}
    result,status=execute_private_media_review(claimed,PARSED,
        recorder=lambda *args:({"success":True,"status":"media_group_review_recorded","created_count":8},201),
        packet_loader=lambda group:(packet(library="accepted"),200),
        claim_creator=lambda **kwargs: (_ for _ in ()).throw(ConnectionError("store")))
    assert status==201 and result["success"] is True
    assert "Public Use remains undecided" in result["answer"]
    assert result["publishes"] is False
