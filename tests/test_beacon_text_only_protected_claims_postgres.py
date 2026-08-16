import os
import threading
import uuid
from unittest.mock import patch

import pytest

from modules.beacon.text_only_organic_review import load_text_only_owner_review
from modules.oom_sakkie.beacon_request_runtime import _event_store
from modules.oom_sakkie.beacon_text_publication_review_runtime import (
    execute_text_only_publication_review, present_text_only_publication_review,
)
from modules.oom_sakkie.protected_action_claims import (
    bind_claim_card, claim_callback, complete_claim,
)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="disposable PostgreSQL required")
def test_real_text_only_claim_concurrent_callback_decision_and_replay():
    suffix=uuid.uuid4().hex
    owner="test-owner-"+suffix
    mission="OOM-BEACON-REQUEST-"+suffix.upper()
    binding={"owner":owner,"chat":owner,"provider_message_id":"proposal-"+suffix,
      "provider_timestamp":"2026-08-16T10:00:00+00:00","content_digest":"b"*64,
      "semantic_domain":"beacon","semantic_intent":"live_stock_awareness",
      "contract_version":"oom_sakkie_beacon_request_v1"}
    proposal={"packet_id":"BEACON-AWARENESS-"+suffix.upper(),
      "packet_type":"live_stock_awareness_proposal","locale":"en-ZA",
      "objective":"Farm awareness without availability","audience":"Local farm followers",
      "intended_channel":"Facebook Page organic","draft_caption":"Daily care on Amadeus Farm.",
      "media":{"status":"text_only"},
      "capacity_context":{"herdmaster_safe_fulfilment_capacity":"Unknown",
        "sam_quantified_buyer_demand":"Unknown","sale_availability_inferred":False},
      "sam_routing":"Attribute enquiries to this packet and route buying enquiries to SAM."}
    result={"handled":True,"success":True,"binding":binding,"proposal":proposal,
      "result_digest":"c"*64}
    recorded=_event_store("record",mission,{"binding":binding,"result":result})
    assert recorded["success"] is True
    env={**os.environ,"FACEBOOK_PAGE_ID":"PAGE-TEST",
         "BEACON_FACEBOOK_PAGE_NAME":"Amadeus Farm Test"}
    with patch.dict(os.environ,env,clear=True):
        packet=load_text_only_owner_review("")
        assert packet["review_status"]=="awaiting_exact_owner_review"
        parsed={"telegram_user_id":owner,"telegram_chat_id":owner,
          "provider_message_id":"review-"+suffix,"provider_timestamp":"2026-08-16T10:05:00+00:00",
          "semantic":{"language":"en"}}
        preview,status=present_text_only_publication_review(packet,parsed)
        assert status==200 and bind_claim_card(preview["callback_token"],"700")
        data=f"oompa:{preview['callback_token']}:confirm"
        outcomes=[]
        def click():
            outcomes.append(claim_callback(data,owner_user_id=owner,private_chat_id=owner,
              provider_message_id="callback-"+suffix,
              provider_timestamp="2026-08-16T10:06:00+00:00",
              source_card_message_id="700"))
        threads=[threading.Thread(target=click) for _ in range(2)]
        [thread.start() for thread in threads];[thread.join() for thread in threads]
        claims=[item[0] for item in outcomes]
        assert {item["status"] for item in claims}=={
          "protected_callback_claimed","protected_callback_recovered"}
        first,first_status=execute_text_only_publication_review(claims[0],parsed)
        second,second_status=execute_text_only_publication_review(claims[1],parsed)
        assert first_status in {200,201} and second_status in {200,201}
        assert first["decision_event_id"]==second["decision_event_id"]
        completed=complete_claim(preview["callback_token"],first)
        replayed=complete_claim(preview["callback_token"],second)
        assert completed["completed"] is True
        assert replayed["replayed"] is True
        assert first["posts_publicly"] is second["posts_publicly"] is False
