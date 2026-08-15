import json
from datetime import datetime, timezone

from scripts.rootline_reassessment_cron import build_payload, run

NOW=datetime(2026,8,15,7,28,41,tzinfo=timezone.utc)
ENV={"ROOTLINE_REASSESSMENT_SCHEDULER_URL":"https://example.test/api/oom-sakkie/management/rootline/reassess",
     "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*32,
     "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"41,42,43",
     "ROOTLINE_REASSESSMENT_OWNER_USER_ID":"42"}

class Response:
    def __init__(self,payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def read(self): return json.dumps(self.payload).encode()

def test_payload_is_stable_current_bucket_and_owner_private_chat_bound():
    value=build_payload(NOW,"42")
    assert value["due_at"]=="2026-08-15T07:15:00+00:00"
    assert value["trigger_id"]=="ROOTLINE-AUTO-20260815T071500Z"
    assert value["owner_user_id"]==value["chat_id"]=="42"
    assert value["specialist"]=="ROOTLINE"

def test_cron_calls_only_authenticated_existing_application_spine():
    seen={}
    def open_(request,timeout):
        seen.update({"url":request.full_url,"auth":request.headers["Authorization"],
                     "payload":json.loads(request.data),"timeout":timeout})
        return Response({"success":True,"status":"rootline_reassessment_unchanged",
                         "schedule_identity":"OOM-SCHEDULE-ROOTLINE-X","next_due_at":"later",
                         "hardware_commands":0,"telegram_sends":0})
    result=run(environ=ENV,now=NOW,opener=open_)
    assert result["success"] is True and result["hardware_commands"]==0
    assert seen["url"].endswith("/api/oom-sakkie/management/rootline/reassess")
    assert seen["auth"].startswith("Bearer ") and seen["timeout"]==115

def test_missing_or_ambiguous_identity_fails_without_network():
    for changes in ({"ROOTLINE_REASSESSMENT_SCHEDULER_URL":"http://bad"},
                    {"OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"short"},
                    {"ROOTLINE_REASSESSMENT_OWNER_USER_ID":""},
                    {"ROOTLINE_REASSESSMENT_OWNER_USER_ID":"99"}):
        result=run(environ={**ENV,**changes},now=NOW,
                   opener=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError("network")))
        assert result=={"success":False,"status":"rootline_scheduler_configuration_invalid",
                       "hardware_commands":0,"telegram_sends":0}

def test_endpoint_failure_is_bounded_and_command_inert():
    result=run(environ=ENV,now=NOW,
               opener=lambda *_a,**_k: (_ for _ in ()).throw(TimeoutError()))
    assert result=={"success":False,"status":"rootline_scheduler_endpoint_unavailable",
                   "hardware_commands":0,"telegram_sends":0}
