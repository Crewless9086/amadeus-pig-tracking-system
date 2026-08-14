import os,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import psycopg
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
from modules.oom_sakkie.protected_action_claims import bind_claim_card,claim_callback,complete_claim,contain_unbound_preview_claim,create_claim
URL=os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL","").strip()
@unittest.skipUnless(URL,"disposable PostgreSQL URL is required")
class RootlineProtectedIrrigationPostgresTests(unittest.TestCase):
 def connect(self):return psycopg.connect(URL)
 def setUp(self):self.suffix=uuid.uuid4().hex;self.mission="RMQ-20260813-04"
 def tearDown(self):
  with self.connect() as db:db.execute("delete from app_private.oom_protected_action_claims where mission_id=%s",(self.mission,))
 def create(self,ttl=15):
  payload={"mission_id":self.mission,"zone_id":"B12345","channel":1,"job_id":"JOB-"+self.suffix,"job_sha256":"a"*64,"segment_identity":"SEG-1","current_segment":1,"segment_requested_seconds":3599,"requested_total_duration_seconds":7200,"governed_executable_duration_seconds":7198,"plan_generation":"PLAN-1","evidence_generation":"PLAN-1","controller_safety_generation":"SAFE-1","eligibility_sha256":"b"*64,"expected_segment_count":2,"maximum_duration_seconds":3599}
  return create_claim(action_kind="rootline_irrigation_segment",owner_user_id="1",private_chat_id="1",mission_id=self.mission,provider_message_id="PREVIEW-1",evidence_generation="PLAN-1",preview_payload=payload,ttl_minutes=ttl,connect_factory=self.connect)
 def test_concurrent_callbacks_claim_once_restart_and_completion_replay(self):
  row=self.create();self.assertTrue(bind_claim_card(row["callback_token"],"4000",connect_factory=self.connect));callback=f"oompa:{row['callback_token']}:confirm";stamp=datetime.now(timezone.utc).isoformat()
  def invoke(index):return claim_callback(callback,owner_user_id="1",private_chat_id="1",provider_message_id=f"CB-{index}",provider_timestamp=stamp,source_card_message_id="4000",connect_factory=self.connect)
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,(1,2)))
  self.assertEqual(sum(result[0].get("status")=="protected_callback_claimed" for result in results),1)
  self.assertEqual(sum(result[0].get("status")=="protected_callback_stale" for result in results),1)
  winner=next(result[0] for result in results if result[0].get("status")=="protected_callback_claimed")
  winner_index=next(index for index,result in enumerate(results,1) if result[0].get("status")=="protected_callback_claimed")
  recovered,recovered_status=claim_callback(callback,owner_user_id="1",private_chat_id="1",provider_message_id=f"CB-{winner_index}",provider_timestamp=datetime.now(timezone.utc).isoformat(),source_card_message_id="4000",connect_factory=self.connect)
  self.assertEqual((recovered_status,recovered["status"]),(200,"protected_callback_recovered"))
  complete_claim(row["callback_token"],{"success":True,"status":"segment_started"},connect_factory=self.connect)
  replay,status=claim_callback(callback,owner_user_id="1",private_chat_id="1",provider_message_id="CB-REPLAY",provider_timestamp=stamp,source_card_message_id="4000",connect_factory=self.connect)
  self.assertEqual((status,replay["status"],replay["telegram_sends"]),(200,"protected_callback_completed_delivery_retry",0))
  self.assertEqual((replay["action_kind"],replay["mission_id"]),("rootline_irrigation_segment",self.mission))
 def test_wrong_owner_card_and_expired_claim_fail_closed(self):
  row=self.create();self.assertTrue(bind_claim_card(row["callback_token"],"4001",connect_factory=self.connect));callback=f"oompa:{row['callback_token']}:confirm";stamp=datetime.now(timezone.utc).isoformat()
  for owner,card,expected in (("2","4001","protected_callback_unauthorized"),("1","wrong","protected_callback_card_mismatch")):
   result,status=claim_callback(callback,owner_user_id=owner,private_chat_id=owner,provider_message_id="CB",provider_timestamp=stamp,source_card_message_id=card,connect_factory=self.connect);self.assertGreaterEqual(status,400);self.assertEqual(result["status"],expected)
  with self.connect() as db:
   db.execute("update app_private.oom_protected_action_claims set expires_at=now()-interval '1 second' where callback_token=%s",(row["callback_token"],))
  result,status=claim_callback(callback,owner_user_id="1",private_chat_id="1",provider_message_id="CB-EXPIRED",provider_timestamp=stamp,source_card_message_id="4001",connect_factory=self.connect)
  self.assertEqual((status,result["status"]),(409,"protected_callback_expired"))
 def test_unbound_preview_is_contained_but_bound_preview_is_not(self):
  unbound=self.create()
  callback=f"oompa:{unbound['callback_token']}:confirm"
  result,status=claim_callback(callback,owner_user_id="1",private_chat_id="1",provider_message_id="CB-RACE",provider_timestamp=datetime.now(timezone.utc).isoformat(),source_card_message_id="4002",connect_factory=self.connect)
  self.assertEqual((status,result["status"]),(409,"protected_callback_card_unbound"))
  self.assertTrue(contain_unbound_preview_claim(unbound["callback_token"],{"status":"delivery_failed"},connect_factory=self.connect))
  self.suffix=uuid.uuid4().hex
  bound=self.create()
  self.assertTrue(bind_claim_card(bound["callback_token"],"4002",connect_factory=self.connect))
  self.assertFalse(contain_unbound_preview_claim(bound["callback_token"],{"status":"delivery_failed"},connect_factory=self.connect))
 def test_concurrent_degraded_callbacks_contain_once_with_zero_controls(self):
  row=self.create();self.assertTrue(bind_claim_card(row["callback_token"],"4003",connect_factory=self.connect))
  callback=f"oompa:{row['callback_token']}:confirm";calls=[]
  def invoke(index):
   return handle_protected_action_input({"telegram_user_id":"1","telegram_chat_id":"1",
    "provider_message_id":f"DB-HOLD-{index}","provider_timestamp":datetime.now(timezone.utc).isoformat(),
    "reply_to_message_id":"4003","callback_data":callback},issue_gateway_owner_authority("1","1"),
    irrigation_handler=lambda *args,**kwargs:(calls.append(index) or ({"success":True,
     "status":"execution_store_degraded_hold","hardware_commands":0,"provider_control_calls":0,
     "writes_farm_data":False},200)),connect_factory=self.connect)
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,(1,2)))
  self.assertEqual(len(calls),1)
  self.assertEqual(sum(result[0].get("status")=="execution_store_degraded_hold" for result in results),1)
  self.assertTrue(all(int(result[0].get("hardware_commands") or 0)==0 for result in results))
  with self.connect() as db:
   status=db.execute("select status from app_private.oom_protected_action_claims where callback_token=%s",(row["callback_token"],)).fetchone()[0]
  self.assertEqual(status,"contained")
