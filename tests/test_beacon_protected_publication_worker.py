from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from unittest.mock import patch
import json

from modules.beacon.protected_publication_worker import (
    PostgresProtectedPublicationStore, run_protected_publication_cycle,
    validate_claimed_approval,
)
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.sales.beacon_campaign import _readback_facebook_page_post

NOW = datetime(2026, 8, 19, 8, tzinfo=timezone.utc)


def approval(caption="Molly is settling into the morning routine while her piglets stay close."):
    preview = {"contract_version":"beacon_campaign_owner_card_v1","packet_id":"PACKET-1",
        "target_page_id":"PAGE-1",
        "packet_generation":"G1","exact_post_copy":caption,
        "selected_media":[{"asset_id":"ASSET-1","content_sha256":"a"*64,
          "storage_readback_proof_id":"READBACK-1","library_accept_event_id":"ACCEPT-1",
          "public_use_event_id":"PUBLIC-1","public_use_authority":"approved",
          "litter_id":"LITTER-1","pig_ids":["PIG-1"],"event_id":"EVENT-1",
          "storage_bucket":"beacon-raw-intake","storage_path":"one.jpg"}],
        "media_evidence_exception":"","audience":"Farm followers","location":"Western Cape",
        "publication_time":(NOW+timedelta(hours=1)).isoformat(),"publication_timezone":"Africa/Johannesburg",
        "budget_cap":{"currency":"ZAR","total":"0.00","daily":"0.00"},"duration":{"days":0},
        "attribution_identity":"ATTR-1","stock_boundary":"","sam_boundary":"inbound only",
        "story_context":{"sow_name":"Molly","litter_id":"LITTER-1","event_id":"EVENT-1"},
        "stop_conditions":["authority_revoked"],"rollback":{},
        "approval_expires_at":(NOW+timedelta(hours=1)).isoformat()}
    preview["campaign_digest"] = canonical_preview_digest("beacon_campaign_review", preview)
    return {"consumer_id":"CONSUMER-1","callback_token":"TOKEN-1",
        "action_kind":"beacon_campaign_review","claim_status":"completed",
        "evidence_generation":preview["campaign_digest"],"preview_payload":preview,
        "approval_result":{"status":"beacon_campaign_review_approved"}}


class Store:
    def __init__(self, item=None): self.item=item; self.finished=[]
    def claim(self, worker, now):
        item,self.item=self.item,None
        return item
    def finish(self, consumer, status, outcome, now): self.finished.append((status,outcome)); return True


def confirmed_outcome(post_id="42_7"):
    return {"success":True,"status":"facebook_page_post_sent","facebook_post_id":post_id,
        "facebook_result":{"success":True,"provider_readback_confirmed":True,
            "provider_readback":{"success":True,"id":post_id}}}


def test_english_afrikaans_and_mixed_story_copy_are_eligible():
    for text in ("Molly and her piglets are enjoying the cool morning.",
                 "Molly en haar varkies geniet die koel oggend.",
                 "Molly and haar varkies geniet a quiet morning on the farm."):
        assert validate_claimed_approval(approval(text), now=NOW) == ""


def test_correction_decline_expiry_and_revocation_never_reach_executor():
    cases=[]
    corrected=approval(); corrected["claim_status"]="changed"; cases.append(corrected)
    declined=approval(); declined["approval_result"]={"status":"declined"}; cases.append(declined)
    expired=approval(); expired["preview_payload"]["approval_expires_at"]=(NOW-timedelta(seconds=1)).isoformat()
    expired["preview_payload"]["campaign_digest"]=canonical_preview_digest("beacon_campaign_review",
        {k:v for k,v in expired["preview_payload"].items() if k!="campaign_digest"})
    expired["evidence_generation"]=expired["preview_payload"]["campaign_digest"]; cases.append(expired)
    revoked=approval(); revoked["preview_payload"]["selected_media"][0]["public_use_authority"]="revoked"
    revoked["preview_payload"]["campaign_digest"]=canonical_preview_digest("beacon_campaign_review",
        {k:v for k,v in revoked["preview_payload"].items() if k!="campaign_digest"})
    revoked["evidence_generation"]=revoked["preview_payload"]["campaign_digest"]; cases.append(revoked)
    for item in cases:
        called=[]; run_protected_publication_cycle(store=Store(item), executor=lambda *a,**k: called.append(1), now=NOW)
        assert called == []


def test_altered_caption_or_media_is_contained():
    for mutate in (lambda p: p["preview_payload"].update(exact_post_copy="altered"),
                   lambda p: p["preview_payload"]["selected_media"][0].update(asset_id="ALTERED")):
        item=approval(); mutate(item); store=Store(item)
        result=run_protected_publication_cycle(store=store, executor=lambda *a,**k: (_ for _ in ()).throw(AssertionError()), now=NOW)
        assert result["status"] == "protected_campaign_binding_changed"


def test_definite_failure_and_ambiguous_provider_are_terminal_and_replay_silent():
    for response, expected in [(({"success":False,"status":"provider_rejected"},400),"contained_failed"),
                               (({"success":False,"status":"provider_timeout"},503),"contained_ambiguous")]:
        store=Store(approval()); result=run_protected_publication_cycle(store=store,
            executor=lambda *a,**k: response, now=NOW)
        assert result["consumer_status"] == expected and result["automatic_retry_allowed"] is False
        assert run_protected_publication_cycle(store=store, executor=lambda *a,**k: (_ for _ in ()).throw(AssertionError()), now=NOW)["status"] == "beacon_publication_cycle_silent"


def test_success_publishes_once_and_concurrent_or_restarted_cycle_is_silent():
    store=Store(approval()); calls=[]
    def execute(payload, **kwargs):
        calls.append(payload)
        return confirmed_outcome(),200
    first=run_protected_publication_cycle(store=store, executor=execute, now=NOW)
    second=run_protected_publication_cycle(store=store, executor=execute, now=NOW)
    assert first["consumer_status"] == "confirmed" and second["status"] == "beacon_publication_cycle_silent"
    assert len(calls)==1 and calls[0]["exact_text"].startswith("Molly")


def test_text_only_publishes_once_without_media_or_spend_authority():
    item=approval("A quiet farm-life update from Amadeus Farm.")
    item["preview_payload"]["selected_media"]={"mode":"text_only"}
    item["preview_payload"]["media_evidence_exception"] = \
        "Explicit text-only publication; no media is selected or implied."
    item["preview_payload"]["story_context"]={}
    item["preview_payload"]["campaign_digest"]=canonical_preview_digest(
        "beacon_campaign_review", {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
    item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
    calls=[]
    result=run_protected_publication_cycle(store=Store(item), executor=lambda payload,**kwargs: (
        calls.append(payload) or confirmed_outcome("PAGE-1_7"),200), now=NOW)
    assert result["consumer_status"]=="confirmed" and len(calls)==1
    assert calls[0]["selected_assets"] == [] and calls[0]["asset_id"] == ""
    assert calls[0]["zero_spend"] is True and calls[0]["target_page_id"] == "PAGE-1"


def test_text_only_requires_exact_class_and_target_page_binding():
    item=approval(); item["preview_payload"]["target_page_id"]=""
    item["preview_payload"]["campaign_digest"]=canonical_preview_digest(
        "beacon_campaign_review", {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
    item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
    assert validate_claimed_approval(item, now=NOW)=="protected_campaign_target_page_required"


def test_supported_enquiry_post_preserves_exact_lane_sam_identity_and_zero_spend():
    caption = ("Looking for live pigs? Amadeus Farm handles enquiries for piglets, weaners, "
        "growers and finishers. Message us with the type, number needed, intended use and your area. "
        "SAM will check current farm records before discussing any option; no stock, price, "
        "availability, delivery or reservation is promised.")
    item=approval(caption)
    item["preview_payload"].update({"selected_media":{"mode":"text_only"},
        "media_evidence_exception":"Explicit text-only publication; no media is selected or implied.",
        "story_context":{}, "campaign_lane":"live_stock_enquiry_capture",
        "campaign_objective":"qualified_livestock_enquiries",
        "sam_boundary":"SAM may qualify inbound only; no commitment."})
    item["preview_payload"]["campaign_digest"]=canonical_preview_digest(
        "beacon_campaign_review", {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
    item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
    calls=[]
    result=run_protected_publication_cycle(store=Store(item), executor=lambda payload,**kwargs: (
        calls.append(payload) or confirmed_outcome("PAGE-1_8"),200), now=NOW)
    assert result["consumer_status"] == "confirmed" and len(calls) == 1
    assert calls[0]["campaign_lane"] == "live_stock_enquiry_capture"
    assert calls[0]["objective"] == "qualified_livestock_enquiries"
    assert calls[0]["attribution_identity"] == "ATTR-1"
    assert calls[0]["selected_assets"] == [] and calls[0]["zero_spend"] is True


def test_concurrent_workers_atomically_publish_once():
    class ConcurrentStore(Store):
        def __init__(self, item):
            super().__init__(item); self.lock=Lock()
        def claim(self, worker, now):
            with self.lock:
                return super().claim(worker, now)
        def finish(self, consumer, status, outcome, now):
            with self.lock:
                return super().finish(consumer, status, outcome, now)
    store=ConcurrentStore(approval()); calls=[]; results=[]; call_lock=Lock()
    def execute(payload, **kwargs):
        with call_lock: calls.append(payload)
        return confirmed_outcome(),200
    workers=[Thread(target=lambda: results.append(run_protected_publication_cycle(
        store=store, executor=execute, now=NOW))) for _ in range(8)]
    for worker in workers: worker.start()
    for worker in workers: worker.join()
    assert len(calls)==1
    assert sum(result.get("consumer_status")=="confirmed" for result in results)==1
    assert sum(result.get("status")=="beacon_publication_cycle_silent" for result in results)==7


def test_restart_after_claim_is_terminal_ambiguous_and_never_retried():
    sql = PostgresProtectedPublicationStore.claim.__code__.co_consts
    joined = " ".join(value for value in sql if isinstance(value, str))
    assert "worker_restart_after_claim_ambiguous" in joined
    assert "claimed_at <" in joined and "contained_ambiguous" in joined


def test_scheduled_approval_must_still_be_the_current_manager_generation():
    sql = PostgresProtectedPublicationStore.claim.__code__.co_consts
    joined = " ".join(value for value in sql if isinstance(value, str))
    assert "app_private.oom_manager_cases" in joined
    assert "m.specialist='BEACON'" in joined
    assert "scheduled:" in joined and "m.generation::text" in joined
    assert "order by case_id for update" in joined


def test_success_without_provider_readback_is_contained_ambiguous():
    store=Store(approval())
    result=run_protected_publication_cycle(store=store, executor=lambda *a,**k: (
        {"success":True,"status":"facebook_page_post_sent","facebook_post_id":"42_7"},200), now=NOW)
    assert result["consumer_status"]=="contained_ambiguous"
    assert result["status"]=="meta_provider_readback_unproven_ambiguous"


def test_real_executor_nested_readback_shape_is_confirmed():
    store=Store(approval())
    result=run_protected_publication_cycle(store=store, executor=lambda *a,**k: (
        confirmed_outcome("PAGE-1_7"),200), now=NOW)
    assert result["consumer_status"] == "confirmed"


def test_legacy_or_contradictory_confirmation_cannot_bypass_nested_provider_identity():
    outcomes = [
        {"success":True,"status":"facebook_page_post_sent","facebook_post_id":"PAGE-1_7",
         "provider_readback_confirmed":True},
        {"success":True,"status":"facebook_page_post_sent","facebook_post_id":"PAGE-1_7",
         "provider_readback_confirmed":True,"facebook_result":{"success":True,
             "provider_readback_confirmed":False,"provider_readback":{"success":True,
                 "id":"PAGE-1_7"}}},
        {"success":True,"status":"facebook_page_post_sent","facebook_post_id":"PAGE-1_7",
         "facebook_result":{"success":True,"provider_readback_confirmed":True,
             "provider_readback":{"success":True,"id":"PAGE-1_OTHER"}}},
    ]
    for outcome in outcomes:
        result=run_protected_publication_cycle(store=Store(approval()),
            executor=lambda *a,_outcome=outcome,**k: (_outcome,200), now=NOW)
        assert result["consumer_status"] == "contained_ambiguous"
        assert result["status"] == "meta_provider_readback_unproven_ambiguous"


def test_nonzero_budget_or_duration_is_rejected_before_executor():
    for field,value in (("budget_cap",{"currency":"ZAR","total":"1.00","daily":"1.00"}),
                        ("duration",{"days":1})):
        item=approval(); item["preview_payload"][field]=value
        item["preview_payload"]["campaign_digest"]=canonical_preview_digest(
            "beacon_campaign_review", {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
        item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
        called=[]; result=run_protected_publication_cycle(store=Store(item),
            executor=lambda *a,**k: called.append(1), now=NOW)
        assert result["status"]=="protected_campaign_zero_spend_boundary_invalid"
        assert called == []
    assert result["automatic_retry_allowed"] is False


def test_malformed_expiry_is_contained_before_executor():
    for value in ("not-a-date", "2026-08-19T09:00:00"):
        item=approval(); item["preview_payload"]["approval_expires_at"]=value
        item["preview_payload"]["campaign_digest"]=canonical_preview_digest("beacon_campaign_review",
            {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
        item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
        called=[]
        result=run_protected_publication_cycle(store=Store(item),
            executor=lambda *a,**k: called.append(1), now=NOW)
        assert result["status"]=="protected_campaign_expiry_invalid" and called==[]


def test_sales_or_contact_copy_is_rejected():
    for text in ("Molly's piglets are available.", "Contact the farm about Molly's piglets.",
                 "Molly se varkies is te koop."):
        assert validate_claimed_approval(approval(text), now=NOW) in {
            "protected_campaign_public_policy_failed", "protected_campaign_story_only_cta_failed"}
    for text in ("Follow along with Molly and her piglets.", "Volg saam met Molly en haar varkies."):
        assert validate_claimed_approval(approval(text), now=NOW) == "protected_campaign_story_only_cta_failed"
    for text in ("Come see Molly and her piglets.", "Visit Molly and her piglets.",
                 "Share Molly and her piglets.", "Lees meer oor Molly en haar varkies.",
                 "Check out Molly and her piglets.", "See more about Molly and her piglets.",
                 "Kom loer na Molly en haar varkies.", "Gaan kyk na Molly en haar varkies."):
        assert validate_claimed_approval(approval(text), now=NOW) == "protected_campaign_story_only_cta_failed"


def test_media_must_match_bound_litter_and_event():
    item=approval(); item["preview_payload"]["selected_media"][0]["event_id"]="EVENT-OTHER"
    item["preview_payload"]["campaign_digest"]=canonical_preview_digest("beacon_campaign_review",
        {k:v for k,v in item["preview_payload"].items() if k!="campaign_digest"})
    item["evidence_generation"]=item["preview_payload"]["campaign_digest"]
    assert validate_claimed_approval(item,now=NOW)=="protected_campaign_litter_media_binding_failed"


def test_sow_name_is_required_and_internal_litter_id_is_forbidden():
    assert validate_claimed_approval(approval("A quiet morning with the piglets."), now=NOW) == \
        "protected_campaign_public_sow_identity_failed"
    assert validate_claimed_approval(approval("Molly and LITTER-1 had a quiet morning."), now=NOW) == \
        "protected_campaign_public_sow_identity_failed"


class Response:
    status=200
    payload={"id":"PAGE_7","message":"Molly and her piglets are enjoying the cool morning.",
             "created_time":"2026-08-19T08:00:00+0000"}
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.payload).encode()


def test_meta_readback_requires_exact_id_and_caption():
    with patch("modules.sales.beacon_campaign.urllib_request.urlopen", return_value=Response()):
        result,status=_readback_facebook_page_post("PAGE_7",
            {"exact_text":"Molly and her piglets are enjoying the cool morning."},
            environ={"BEACON_FACEBOOK_PAGE_ACCESS_TOKEN":"token","BEACON_FACEBOOK_GRAPH_VERSION":"v23.0"})
    assert status==200 and result["status"]=="meta_readback_confirmed"


def test_meta_readback_binds_exact_single_and_nested_multi_photo_ids():
    for expected,attachments in [
        (["PHOTO-1"],{"data":[{"target":{"id":"PHOTO-1"}}]}),
        (["PHOTO-1","PHOTO-2"],{"data":[{"subattachments":{"data":[
            {"target":{"id":"PHOTO-1"}},{"target":{"id":"PHOTO-2"}}]}}]})]:
        response=Response(); response.payload={**Response.payload,"attachments":attachments}
        with patch("modules.sales.beacon_campaign.urllib_request.urlopen",return_value=response):
            result,status=_readback_facebook_page_post("PAGE_7",
                {"exact_text":Response.payload["message"]},
                environ={"BEACON_FACEBOOK_PAGE_ACCESS_TOKEN":"token"},expected_media_ids=expected)
        assert status==200 and sorted(result["provider_media_ids"])==sorted(expected)
    response=Response(); response.payload={**Response.payload,"attachments":{"data":[
        {"target":{"id":"PHOTO-1"}},{"target":{"id":"UNAPPROVED"}}]}}
    with patch("modules.sales.beacon_campaign.urllib_request.urlopen",return_value=response):
        result,status=_readback_facebook_page_post("PAGE_7",{"exact_text":Response.payload["message"]},
            environ={"BEACON_FACEBOOK_PAGE_ACCESS_TOKEN":"token"},expected_media_ids=["PHOTO-1"])
    assert status==409 and result["status"]=="meta_readback_media_binding_mismatch"
