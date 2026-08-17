import os, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import psycopg
from modules.oom_sakkie.protected_delivery_lifecycle import recover_protected_card

URL=os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL","").strip()
@unittest.skipUnless(URL,"disposable PostgreSQL URL is required")
class ProtectedDeliveryPostgresTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    with psycopg.connect(URL) as db:
      db.execute("create schema if not exists app_private")
      db.execute("""create table if not exists app_private.oom_protected_action_claims(
       callback_token text primary key,action_kind text not null,owner_user_id text not null,
       private_chat_id text not null,mission_id text not null,provider_message_id text not null,
       preview_card_message_id text,preview_digest text not null,evidence_generation text not null,
       preview_payload jsonb not null,status text not null default 'active',expires_at timestamptz not null,
       delivery_state text not null default 'claim_created',delivery_attempt_id text,
       delivery_attempted_at timestamptz,provider_accepted_at timestamptz,delivery_confirmed_at timestamptz,
       delivery_ambiguous_at timestamptz,delivery_result jsonb)""")
      db.execute("""alter table app_private.oom_protected_action_claims
       add column if not exists delivery_state text not null default 'claim_created',
       add column if not exists delivery_attempt_id text,
       add column if not exists delivery_attempted_at timestamptz,
       add column if not exists provider_accepted_at timestamptz,
       add column if not exists delivery_confirmed_at timestamptz,
       add column if not exists delivery_ambiguous_at timestamptz,
       add column if not exists delivery_result jsonb""")
  def connect(self):return psycopg.connect(URL)
  def setUp(self):
    self.token="D"+uuid.uuid4().hex;self.digest="G"+uuid.uuid4().hex
    with self.connect() as db:db.execute("""insert into app_private.oom_protected_action_claims
      (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
       preview_digest,evidence_generation,preview_payload,expires_at) values
      (%s,'rootline_fertilizer_mixer_presence_refresh','42','42','M','IN',%s,'E','{}',%s)""",
      (self.token,self.digest,datetime.now(timezone.utc)+timedelta(minutes=5)))
  def tearDown(self):
    with self.connect() as db:db.execute("delete from app_private.oom_protected_action_claims where callback_token=%s",(self.token,))
  def call(self,send):return recover_protected_card(callback_token=self.token,preview_digest=self.digest,
    owner_user_id="42",private_chat_id="42",action_kind="rootline_fertilizer_mixer_presence_refresh",
    deliver=send,connect_factory=self.connect)
  def test_concurrent_and_restart_replay_send_once(self):
    calls=[]
    def send():calls.append(1);return {"success":True,"telegram_message_id":"3688","telegram_sends":1}
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:self.call(send),(1,2)))
    replay=self.call(send)
    self.assertEqual(len(calls),1);self.assertTrue(any(r.get("delivery_confirmed") for r in results))
    self.assertEqual(replay["status"],"protected_delivery_replayed_noop")
    with self.connect() as db: row=db.execute("select delivery_state,preview_card_message_id from app_private.oom_protected_action_claims where callback_token=%s",(self.token,)).fetchone()
    self.assertEqual(row,("delivery_confirmed","3688"))
  def test_interrupted_or_ambiguous_delivery_is_not_retried(self):
    with self.connect() as db:db.execute("update app_private.oom_protected_action_claims set delivery_state='delivery_pending',delivery_attempted_at=now()-interval '31 seconds' where callback_token=%s",(self.token,))
    calls=[];result=self.call(lambda:calls.append(1))
    self.assertEqual(calls,[]);self.assertTrue(result["provider_outcome_ambiguous"])
  def test_wrong_binding_and_expired_claim_make_zero_calls(self):
    calls=[]
    wrong=recover_protected_card(callback_token=self.token,preview_digest="wrong",owner_user_id="42",
      private_chat_id="42",action_kind="rootline_fertilizer_mixer_presence_refresh",
      deliver=lambda:calls.append(1),connect_factory=self.connect)
    self.assertEqual((wrong["status"],calls),("protected_delivery_binding_mismatch",[]))
    with self.connect() as db:db.execute("update app_private.oom_protected_action_claims set expires_at=now()-interval '1 second' where callback_token=%s",(self.token,))
    expired=self.call(lambda:calls.append(1));self.assertEqual((expired["status"],calls),("protected_delivery_terminal_noop",[]))
