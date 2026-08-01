import hashlib
import unittest
from datetime import datetime, timezone

from modules.oom_sakkie.owner_task_lifecycle import (
    ROOTLINE_MEDIA_SHA256,
    handle_owner_task_input,
    monitor_owner_task_dispatch,
    owner_task_input,
)


ENV={"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
NOW=datetime(2026,8,1,17,5,tzinfo=timezone.utc)
RESULT_HTML="✅ <b>DONE</b>"


def photo(message_id, unique, group="album", stamp=1785603680):
    return {"update_id":message_id+1000,"message":{"message_id":message_id,"date":stamp,
        "from":{"id":42},"chat":{"id":42,"type":"private"},"media_group_id":group,
        "photo":[{"file_id":"small","file_unique_id":"s"+unique,"file_size":10},
                 {"file_id":"file-"+unique,"file_unique_id":unique,"file_size":100}]}}


def request(count=1, hashes=()):
    return {"request_id":"REQUEST-1","request_delivered_at":"2026-08-01T16:55:00+00:00",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "expected_item_count":count,"expected_media_sha256":tuple(hashes),
        "prepared_result_id":"RESULT-1","prepared_result_sha256":"a"*64,
        "dispatch_binding":{"mission_id":"M1","target_worker_id":"rootline-agent","release_digest":"d"*64,
            "outcome_artifact_id":"o1","outcome_artifact_sha256":"e"*64,
            "owner_result_sha256":hashlib.sha256(RESULT_HTML.encode("utf-8")).hexdigest()}}


class Rail:
    def __init__(self): self.events={};self.messages=[]
    def record(self,event):
        created=event["event_id"] not in self.events
        if created:self.events[event["event_id"]]=dict(event)
        return {"success":True,"created":created}
    def load(self,task_id): return [row for row in self.events.values() if row["task_id"]==task_id]
    def send(self,chat,text,purpose):
        self.messages.append((chat,text,purpose));return {"success":True,"telegram_message_id":str(900+len(self.messages))}


class OwnerTaskLifecycleTests(unittest.TestCase):
    def test_normalizes_text_photo_video_and_rejects_non_message(self):
        self.assertIsNone(owner_task_input({"callback_query":{}}))
        self.assertEqual(owner_task_input(photo(1,"u"))["item_kind"],"photo")
        text={"message":{"message_id":2,"date":1785603680,"from":{"id":42},"chat":{"id":42,"type":"private"},"text":"done"}}
        self.assertEqual(owner_task_input(text)["item_kind"],"text")
        video={"message":{"message_id":3,"date":1785603680,"from":{"id":42},"chat":{"id":42,"type":"private"},"video":{"file_id":"v","file_unique_id":"vu","file_size":4}}}
        self.assertEqual(owner_task_input(video)["item_kind"],"video")

    def test_six_photo_album_acknowledges_and_completes_once(self):
        rail=Rail();hashes=sorted(ROOTLINE_MEDIA_SHA256);req=request(6,hashes)
        last=None
        for index,digest in enumerate(hashes,1):
            last,status=handle_owner_task_input(photo(index,"u"+str(index)),environ=ENV,
                request_loader=lambda _:req,event_loader=rail.load,event_recorder=rail.record,
                media_reader=lambda envelope,task,d=digest:{"content_sha256":d,"readback_verified":True,"storage_path":"private/"+d},
                telegram_sender=rail.send,now=NOW)
        self.assertEqual((status,last["status"]),(200,"owner_task_completed_from_prepared_specialist_result"))
        self.assertEqual([m[2] for m in rail.messages],["acknowledgement","completion"])
        self.assertIn("6",rail.messages[0][1]);self.assertIn("60 minutes",rail.messages[1][1])
        delivered=[row for row in rail.events.values() if row.get("detail",{}).get("telegram_message_id")]
        self.assertEqual([row["detail"]["telegram_message_id"] for row in delivered],["901","902"])
        self.assertFalse(last["specialist_agent_dispatched"]);self.assertEqual(last["hardware_actions"],0)
        before=(len(rail.events),len(rail.messages))
        replay,_=handle_owner_task_input(photo(6,"u6"),environ=ENV,request_loader=lambda _:req,
            event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:self.fail("replay must not read media"),telegram_sender=rail.send,now=NOW)
        self.assertEqual(replay["status"],"owner_task_completed_from_prepared_specialist_result")
        self.assertEqual((len(rail.events),len(rail.messages)),before)

    def test_no_deployed_adapter_creates_one_truthful_exception(self):
        rail=Rail();digest="b"*64;req=request(1,[digest]);req.pop("prepared_result_sha256")
        result,status=handle_owner_task_input(photo(4,"u4"),environ=ENV,request_loader=lambda _:req,
            event_loader=rail.load,event_recorder=rail.record,media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True},
            telegram_sender=rail.send,now=NOW)
        self.assertEqual(status,202);self.assertTrue(result["development_terminal_required"])
        self.assertFalse(result["automatic_execution_claimed"])
        self.assertEqual([m[2] for m in rail.messages],["acknowledgement","no-adapter"])

    def test_deployed_adapter_requires_ack_start_and_artifact_for_completion(self):
        rail=Rail();digest="c"*64;req=request(1,[digest]);req.pop("prepared_result_sha256")
        base={"mission_id":"M1","target_worker_id":"rootline-agent","release_digest":"d"*64}
        events=[
            {**base,"event_id":"e1","state":"release_requested","occurred_at":"2026-08-01T17:00:00+00:00"},
            {**base,"event_id":"e2","state":"released","occurred_at":"2026-08-01T17:00:01+00:00","acknowledgement_deadline_at":"2026-08-01T17:01:00+00:00","start_deadline_at":"2026-08-01T17:02:00+00:00"},
            {**base,"event_id":"e3","state":"delivery_acknowledged","occurred_at":"2026-08-01T17:00:02+00:00","delivery_receipt_id":"r1"},
            {**base,"event_id":"e4","state":"started","occurred_at":"2026-08-01T17:00:03+00:00","heartbeat_at":"2026-08-01T17:00:03+00:00","activity_observed_at":"2026-08-01T17:00:03+00:00","activity_id":"a1"},
            {**base,"event_id":"e5","state":"completed","occurred_at":"2026-08-01T17:00:04+00:00","outcome_artifact_id":"o1","outcome_artifact_sha256":"e"*64,"outcome_status":"completed"},]
        result,status=handle_owner_task_input(photo(5,"u5"),environ=ENV,request_loader=lambda _:req,
            event_loader=rail.load,event_recorder=rail.record,media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True},
            telegram_sender=rail.send,specialist_dispatcher=lambda _: {"delivery_receipt_id":"receipt-1",
                "events":events,"owner_result_html":RESULT_HTML},now=NOW)
        self.assertEqual((status,result["dispatch_state"],result["results"]),(200,"completed",1))

    def test_stale_or_missing_ack_becomes_one_deduplicated_exception(self):
        rail=Rail();base={"mission_id":"M2","target_worker_id":"rootline-agent","release_digest":"f"*64}
        events=[{**base,"event_id":"r1","state":"release_requested","occurred_at":"2026-08-01T16:00:00+00:00"},
            {**base,"event_id":"r2","state":"released","occurred_at":"2026-08-01T16:00:01+00:00","acknowledgement_deadline_at":"2026-08-01T16:01:00+00:00","start_deadline_at":"2026-08-01T16:02:00+00:00"}]
        task={"task_id":"T1","request":request(),"envelope":owner_task_input(photo(1,"u"))}
        first=monitor_owner_task_dispatch(task,events,now=NOW,event_recorder=rail.record,telegram_sender=rail.send)
        second=monitor_owner_task_dispatch(task,events,now=NOW,event_recorder=rail.record,telegram_sender=rail.send,
            lifecycle_events=rail.load("T1"))
        self.assertEqual(first["systemic_exceptions"],1);self.assertEqual(second["systemic_exceptions"],0)
        self.assertFalse(first["automatic_execution_claimed"])

    def test_wrong_owner_or_old_chronology_blocks_only_task_binding(self):
        result,status=handle_owner_task_input(photo(1,"u"),environ={"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"99"})
        self.assertFalse(result["handled"]);self.assertEqual(status,200)
        old=request();old["request_delivered_at"]="2026-08-01T18:00:00+00:00"
        result,status=handle_owner_task_input(photo(1,"u"),environ=ENV,request_loader=lambda _:old)
        self.assertEqual((result["status"],status),("owner_task_response_predates_request",409))

    def test_exact_provider_media_identity_is_bound_when_request_supplies_it(self):
        req=request();req["expected_provider_items"]={"1":"expected-unique"}
        result,status=handle_owner_task_input(photo(1,"wrong-unique"),environ=ENV,request_loader=lambda _:req)
        self.assertEqual((result["status"],status),("owner_task_provider_media_identity_mismatch",409))

    def test_failed_ack_requires_provider_reconciliation_before_bounded_retry(self):
        rail=Rail();digest="f"*64;req=request(1,[digest]);calls=[]
        def fail(chat,text,purpose): calls.append(purpose);return {"success":False}
        kwargs=dict(environ=ENV,request_loader=lambda _:req,event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True})
        first,status=handle_owner_task_input(photo(7,"u7"),telegram_sender=fail,**kwargs)
        self.assertEqual((status,first["status"]),(202,"owner_task_acknowledgement_delivery_unresolved"))
        ambiguous,_=handle_owner_task_input(photo(7,"u7"),telegram_sender=rail.send,
            delivery_reconciler=lambda _: {"status":"ambiguous"},**kwargs)
        self.assertTrue(ambiguous["provider_reconciliation_required"]);self.assertEqual(calls,["acknowledgement"])
        repaired,_=handle_owner_task_input(photo(7,"u7"),telegram_sender=rail.send,
            delivery_reconciler=lambda _: {"status":"conclusively_absent"},**kwargs)
        self.assertNotIn("unresolved",repaired["status"])

    def test_video_is_contained_without_media_io(self):
        rail=Rail();called=[]
        payload={"message":{"message_id":8,"date":1785603680,"from":{"id":42},
            "chat":{"id":42,"type":"private"},"video":{"file_id":"v","file_unique_id":"vu","file_size":4}}}
        result,status=handle_owner_task_input(payload,environ=ENV,request_loader=lambda _:request(),
            event_loader=rail.load,event_recorder=rail.record,media_reader=lambda *_:called.append(True))
        self.assertEqual((status,result["status"],called),(415,"owner_task_video_intake_contained",[]))

    def test_completion_send_failure_is_repaired_only_after_absence_proof(self):
        rail=Rail();digest="1"*64;req=request(1,[digest]);calls=[]
        def partial(chat,text,purpose):
            calls.append(purpose)
            return ({"success":True,"telegram_message_id":"ack-1"} if purpose=="acknowledgement"
                    else {"success":False})
        kwargs=dict(environ=ENV,request_loader=lambda _:req,event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True})
        first,status=handle_owner_task_input(photo(9,"u9"),telegram_sender=partial,**kwargs)
        self.assertEqual((status,first["status"]),(202,"owner_task_completion_delivery_unresolved"))
        repaired,status=handle_owner_task_input(photo(9,"u9"),telegram_sender=rail.send,
            delivery_reconciler=lambda packet:{"status":"conclusively_absent"}
                if packet["purpose"]=="completion" else {"status":"delivered","telegram_message_id":"ack-1"},**kwargs)
        self.assertEqual((status,repaired["task_state"],repaired["results"]),(200,"completed",1))

    def test_dispatch_completion_must_match_exact_request_binding(self):
        rail=Rail();digest="2"*64;req=request(1,[digest]);req.pop("prepared_result_sha256")
        bad={"mission_id":"OTHER","target_worker_id":"rootline-agent","release_digest":"d"*64,
            "event_id":"x","state":"release_requested","occurred_at":"2026-08-01T17:00:00+00:00"}
        result,status=handle_owner_task_input(photo(10,"u10"),environ=ENV,request_loader=lambda _:req,
            event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True},telegram_sender=rail.send,
            specialist_dispatcher=lambda _:{"delivery_receipt_id":"receipt-bad","events":[bad]},now=NOW)
        self.assertEqual((status,result["status"]),(409,"owner_task_dispatch_binding_mismatch"))

    def test_timeout_alert_failure_is_not_blindly_retried(self):
        rail=Rail();base={"mission_id":"M3","target_worker_id":"rootline-agent","release_digest":"3"*64}
        events=[{**base,"event_id":"q1","state":"release_requested","occurred_at":"2026-08-01T16:00:00+00:00"},
            {**base,"event_id":"q2","state":"released","occurred_at":"2026-08-01T16:00:01+00:00",
             "acknowledgement_deadline_at":"2026-08-01T16:01:00+00:00","start_deadline_at":"2026-08-01T16:02:00+00:00"}]
        task={"task_id":"T3","request":request(),"envelope":owner_task_input(photo(1,"u"))}
        failed=monitor_owner_task_dispatch(task,events,now=NOW,event_recorder=rail.record,
            telegram_sender=lambda *_:{"success":False})
        self.assertTrue(failed["provider_reconciliation_required"])
        ambiguous=monitor_owner_task_dispatch(task,events,now=NOW,event_recorder=rail.record,
            telegram_sender=rail.send,lifecycle_events=rail.load("T3"),delivery_reconciler=lambda _:{"status":"ambiguous"})
        self.assertEqual((ambiguous["systemic_exceptions"],len(rail.messages)),(0,0))

    def test_accepted_but_response_lost_dispatch_requires_reconciliation(self):
        rail=Rail();digest="4"*64;req=request(1,[digest]);req.pop("prepared_result_sha256");calls=[]
        kwargs=dict(environ=ENV,request_loader=lambda _:req,event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True},telegram_sender=rail.send,now=NOW)
        def lost(_): calls.append("lost");raise TimeoutError()
        first,status=handle_owner_task_input(photo(11,"u11"),specialist_dispatcher=lost,**kwargs)
        self.assertEqual((status,first["status"]),(202,"owner_task_dispatch_delivery_unresolved"))
        ambiguous,_=handle_owner_task_input(photo(11,"u11"),specialist_dispatcher=lambda _:calls.append("retry"),
            dispatch_reconciler=lambda _:{"status":"ambiguous"},**kwargs)
        self.assertTrue(ambiguous["provider_reconciliation_required"]);self.assertEqual(calls,["lost"])
        base={"mission_id":"M1","target_worker_id":"rootline-agent","release_digest":"d"*64}
        release=[{**base,"event_id":"z1","state":"release_requested","occurred_at":"2026-08-01T17:00:00+00:00"}]
        repaired,status=handle_owner_task_input(photo(11,"u11"),
            specialist_dispatcher=lambda _:{"delivery_receipt_id":"receipt-2","events":release},
            dispatch_reconciler=lambda _:{"status":"conclusively_absent"},**kwargs)
        self.assertEqual((status,repaired["dispatches"]),(202,1))

    def test_altered_owner_result_bytes_are_never_delivered(self):
        rail=Rail();digest="5"*64;req=request(1,[digest]);req.pop("prepared_result_sha256")
        base={"mission_id":"M1","target_worker_id":"rootline-agent","release_digest":"d"*64}
        events=[{**base,"event_id":"b1","state":"release_requested","occurred_at":"2026-08-01T17:00:00+00:00"},
            {**base,"event_id":"b2","state":"released","occurred_at":"2026-08-01T17:00:01+00:00",
             "acknowledgement_deadline_at":"2026-08-01T17:01:00+00:00","start_deadline_at":"2026-08-01T17:02:00+00:00"},
            {**base,"event_id":"b3","state":"delivery_acknowledged","occurred_at":"2026-08-01T17:00:02+00:00","delivery_receipt_id":"r"},
            {**base,"event_id":"b4","state":"started","occurred_at":"2026-08-01T17:00:03+00:00","heartbeat_at":"2026-08-01T17:00:03+00:00","activity_observed_at":"2026-08-01T17:00:03+00:00","activity_id":"a"},
            {**base,"event_id":"b5","state":"completed","occurred_at":"2026-08-01T17:00:04+00:00",
             "outcome_artifact_id":"o1","outcome_artifact_sha256":"e"*64,"outcome_status":"completed"}]
        result,status=handle_owner_task_input(photo(12,"u12"),environ=ENV,request_loader=lambda _:req,
            event_loader=rail.load,event_recorder=rail.record,
            media_reader=lambda *_:{"content_sha256":digest,"readback_verified":True},telegram_sender=rail.send,
            specialist_dispatcher=lambda _:{"delivery_receipt_id":"receipt-3","events":events,
                "owner_result_html":RESULT_HTML+" changed"},now=NOW)
        self.assertEqual((status,result["status"]),(409,"owner_task_result_bytes_mismatch"))
        self.assertEqual([message[2] for message in rail.messages],["acknowledgement"])


if __name__=="__main__": unittest.main()
