from datetime import datetime, timezone
import copy
import unittest
from unittest.mock import patch

from modules.beacon.text_only_organic_review import build_text_only_owner_review
from modules.oom_sakkie.beacon_text_publication_review_runtime import (
    execute_text_only_publication_review, present_text_only_publication_review,
)


def packet():
    return build_text_only_owner_review({
        "result_digest":"a"*64,
        "binding":{"owner":"42","chat":"42","provider_message_id":"500"},
        "proposal":{"proposal_id":"P1","recommended_copy":"Daily care on Amadeus Farm.",
          "locale":"en-ZA","audience":"Local farm followers",
          "campaign_purpose":"Farm awareness without availability",
          "channel":"Facebook Page organic","timing":"owner_selection_required",
          "evidence":{"safe_capacity":"Unknown","sale_availability_inferred":False},
          "evidence_boundary":"No price, stock, availability, reservation or sale claim.",
          "sale_availability_inferred":False,
          "sam_routing":"Attribute enquiries to this packet and route buying enquiries to SAM.",
          "media":[],"selected_media":[]}},
        page_id="PAGE-1",page_name="Amadeus Farm",
        now=datetime(2099,1,1,tzinfo=timezone.utc))


class TextPublicationReviewRuntimeTests(unittest.TestCase):
    def parsed(self, owner="42", chat="42"):
        return {"telegram_user_id":owner,"telegram_chat_id":chat,
                "provider_message_id":"700","provider_timestamp":"2026-08-16T10:00:00+00:00"}

    def test_present_binds_actor_chat_packet_expiry_and_visible_choices(self):
        claim={"callback_token":"opaque","preview_digest":"d"*64,
               "expires_at":"2099-01-08T00:00:00+00:00"}
        with patch("modules.oom_sakkie.beacon_text_publication_review_runtime.create_claim", return_value=claim) as create:
            result,status=present_text_only_publication_review(packet(),self.parsed())
        self.assertEqual(status,200)
        labels=[b["text"] for b in result["reply_markup"]["inline_keyboard"][0]]
        self.assertEqual(labels,["Approve","Correct","Decline"])
        kwargs=create.call_args.kwargs
        self.assertEqual((kwargs["owner_user_id"],kwargs["private_chat_id"]),("42","42"))
        self.assertEqual(kwargs["evidence_generation"],packet()["canonical_sha256"])
        self.assertIn("No post, schedule, boost, spend", result["answer"])

    def test_wrong_owner_or_chat_fails_before_claim(self):
        for parsed in (self.parsed("99","99"),self.parsed("42","99")):
            with patch("modules.oom_sakkie.beacon_text_publication_review_runtime.create_claim") as create:
                result,status=present_text_only_publication_review(packet(),parsed)
            self.assertIn(status,{403})
            create.assert_not_called()

    def test_afrikaans_and_mixed_requests_localize_chrome_not_exact_copy(self):
        for language in ("af","mixed"):
            parsed={**self.parsed(),"semantic":{"language":language}}
            claim={"callback_token":"opaque","preview_digest":"d"*64,
                   "expires_at":"2099-01-08T00:00:00+00:00"}
            with patch("modules.oom_sakkie.beacon_text_publication_review_runtime.create_claim", return_value=claim):
                result,status=present_text_only_publication_review(packet(),parsed)
            labels=[b["text"] for b in result["reply_markup"]["inline_keyboard"][0]]
            self.assertEqual(labels,["Keur goed","Korrigeer","Wys af"])
            self.assertIn("Besluit-sperdatum",result["answer"])
            self.assertIn(packet()["caption"],result["answer"])

    def test_approve_and_decline_record_only_weekly_decision(self):
        for selected,expected in (("approve","approve"),("decline","reject")):
            calls=[]
            def recorder(payload,**kwargs):
                calls.append((payload,kwargs));return {"success":True,"decision_event_id":"D1"},201
            p=packet();preview={"contract_version":p["packet_class"],"packet_id":p["packet_id"],
              "canonical_sha256":p["canonical_sha256"],"proposal_id":p["proposal_id"],
              "proposal_result_digest":p["proposal_result_digest"],"page_id":p["page_id"],
              "page_name":p["page_name"],"channel":p["channel"],"caption":p["caption"],
              "caption_sha256":p["caption_sha256"],"campaign_purpose":p["campaign_purpose"],
              "review_expires_at":p["review_expires_at"],"approval_replay_identity":p["approval_replay_identity"],
              "owner_user_id":"42","private_chat_id":"42","media":[]}
            claimed={"preview_payload":preview,"evidence_generation":p["canonical_sha256"],
                     "mission_id":p["packet_id"],"selected_action":selected}
            result,status=execute_text_only_publication_review(claimed,self.parsed(),decision_recorder=recorder)
            self.assertEqual(status,201);self.assertEqual(calls[0][0]["decision"],expected)
            self.assertFalse(result["posts_publicly"]);self.assertFalse(result["calls_meta"])
            self.assertFalse(result["spends_money"]);self.assertFalse(result["writes_farm_data"])

    def test_missing_or_correct_execution_selection_fails_closed(self):
        p=packet();base={"contract_version":p["packet_class"],"packet_id":p["packet_id"],
          "canonical_sha256":p["canonical_sha256"],"owner_user_id":"42",
          "private_chat_id":"42","media":[]}
        for selected in (None,"correct"):
            claimed={"preview_payload":copy.deepcopy(base),"evidence_generation":p["canonical_sha256"],
              "mission_id":p["packet_id"],"selected_action":selected}
            calls=[]
            result,status=execute_text_only_publication_review(claimed,self.parsed(),
              decision_recorder=lambda *a,**k:calls.append(1))
            self.assertEqual(status,400);self.assertEqual(calls,[])

    def test_substituted_digest_or_media_fails_without_decision(self):
        p=packet();preview={"contract_version":p["packet_class"],"packet_id":p["packet_id"],
          "canonical_sha256":p["canonical_sha256"],"owner_user_id":"42","private_chat_id":"42","media":[]}
        for mutation in (lambda c:c.update(evidence_generation="b"*64),
                         lambda c:c["preview_payload"].update(media=["x"])):
            claimed={"preview_payload":copy.deepcopy(preview),"evidence_generation":p["canonical_sha256"],
                     "mission_id":p["packet_id"]};mutation(claimed)
            calls=[]
            result,status=execute_text_only_publication_review(claimed,self.parsed(),decision_recorder=lambda *a,**k:calls.append(1))
            self.assertEqual(status,409);self.assertEqual(calls,[])


if __name__=="__main__":unittest.main()
