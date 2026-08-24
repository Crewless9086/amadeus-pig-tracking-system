import os, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import psycopg
from modules.oom_sakkie.protected_delivery_lifecycle import recover_protected_card
from modules.oom_sakkie.protected_action_claims import create_claim

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
      db.execute("""alter table app_private.oom_protected_action_claims
       drop constraint if exists oom_protected_action_claims_delivery_state_check""")
      db.execute("""alter table app_private.oom_protected_action_claims add constraint
       oom_protected_action_claims_delivery_state_check check (delivery_state in
       ('claim_created','delivery_pending','provider_accepted','delivery_confirmed',
        'delivery_ambiguous','completed','contained','cancelled','expired'))""")
      db.execute("""create unique index if not exists oom_protected_action_delivery_attempt_unique
       on app_private.oom_protected_action_claims(delivery_attempt_id)
       where delivery_attempt_id is not null""")
      db.execute("""create unique index if not exists oom_protected_action_one_active_mission
       on app_private.oom_protected_action_claims(mission_id) where status='active'""")
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
  def test_migrated_constraints_reject_invalid_state_and_duplicate_attempt(self):
    with self.assertRaises(psycopg.errors.CheckViolation):
      with self.connect() as db:db.execute("update app_private.oom_protected_action_claims set delivery_state='invalid' where callback_token=%s",(self.token,))
    with self.connect() as db:
      db.execute("update app_private.oom_protected_action_claims set delivery_attempt_id='A' where callback_token=%s",(self.token,))
    other='D'+uuid.uuid4().hex
    with self.assertRaises(psycopg.errors.UniqueViolation):
      with self.connect() as conflicting:
        conflicting.execute("""insert into app_private.oom_protected_action_claims
         (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
          preview_digest,evidence_generation,preview_payload,expires_at,delivery_attempt_id)
         values(%s,'rootline_fertilizer_mixer_presence_refresh','42','42','M2','IN2','G2','E','{}',%s,'A')""",
         (other,datetime.now(timezone.utc)+timedelta(minutes=5)))

  def test_expired_unbound_presence_claim_does_not_block_fresh_governed_preview(self):
    mission="MIXER-"+uuid.uuid4().hex
    stale="D"+uuid.uuid4().hex
    with self.connect() as db:
      db.execute("""insert into app_private.oom_protected_action_claims
       (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
        provider_message_id,preview_digest,evidence_generation,preview_payload,expires_at)
       values(%s,'rootline_fertilizer_mixer_presence_refresh','42','42',%s,
        'OLD','OLD-DIGEST','OLD-EVIDENCE','{}',now()-interval '1 day')""",
        (stale,mission))
    payload={"mission_id":mission,"owner_user_id":"42","private_chat_id":"42",
      "contract_version":"oom_rootline_mixer_presence_refresh.v1"}
    created=create_claim(action_kind="rootline_fertilizer_mixer_presence_refresh",
      owner_user_id="42",private_chat_id="42",mission_id=mission,
      provider_message_id="NEW",evidence_generation="NEW-EVIDENCE",
      preview_payload=payload,ttl_minutes=5,connect_factory=self.connect,
      supersede_active=False)
    self.assertEqual(created["status"],"protected_claim_created")
    with self.connect() as db:
      rows=db.execute("""select provider_message_id,status from
       app_private.oom_protected_action_claims where mission_id=%s
       order by provider_message_id""",(mission,)).fetchall()
      db.execute("delete from app_private.oom_protected_action_claims where mission_id=%s",(mission,))
    self.assertEqual(rows,[("NEW","active"),("OLD","expired")])

  def test_stale_recovery_is_serialized_replay_safe_and_preserves_other_claims(self):
    mission="MIXER-"+uuid.uuid4().hex
    foreign_mission="FOREIGN-"+uuid.uuid4().hex
    tokens=["D"+uuid.uuid4().hex for _ in range(5)]
    def insert(token, action, target, provider, expires, card=None):
      with self.connect() as db:
        db.execute("""insert into app_private.oom_protected_action_claims
         (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
          provider_message_id,preview_card_message_id,preview_digest,
          evidence_generation,preview_payload,expires_at)
         values(%s,%s,'42','42',%s,%s,%s,%s,'OLD','{}',%s)""",
          (token,action,target,provider,card,"G"+uuid.uuid4().hex,expires))
    expired=datetime.now(timezone.utc)-timedelta(days=1)
    live=datetime.now(timezone.utc)+timedelta(minutes=5)
    insert(tokens[0],"rootline_fertilizer_mixer_presence_refresh",mission,"STALE",expired)
    insert(tokens[1],"foreign_action",foreign_mission,"FOREIGN-MISSION",expired)
    def create(provider):
      payload={"mission_id":mission,"provider":provider}
      return create_claim(action_kind="rootline_fertilizer_mixer_presence_refresh",
        owner_user_id="42",private_chat_id="42",mission_id=mission,
        provider_message_id=provider,evidence_generation=provider,
        preview_payload=payload,ttl_minutes=5,connect_factory=self.connect,
        supersede_active=False)
    outcomes=[]
    def attempt(provider):
      try: outcomes.append((provider,create(provider)["status"]))
      except RuntimeError as exc: outcomes.append((provider,str(exc)))
    with ThreadPoolExecutor(max_workers=2) as pool:
      list(pool.map(attempt,("NEW-A","NEW-B")))
    winners=[row for row in outcomes if row[1]=="protected_claim_created"]
    self.assertEqual(len(winners),1)
    self.assertEqual(sorted(row[1] for row in outcomes),
      ["protected_claim_active_preview_conflict","protected_claim_created"])
    winner=winners[0][0]
    self.assertEqual(create(winner)["status"],"protected_claim_existing")
    with self.connect() as db:
      rows=db.execute("""select mission_id,provider_message_id,status from
       app_private.oom_protected_action_claims where mission_id in (%s,%s)
       order by mission_id,provider_message_id""",(mission,foreign_mission)).fetchall()
      db.execute("delete from app_private.oom_protected_action_claims where mission_id in (%s,%s)",
        (mission,foreign_mission))
    self.assertIn((mission,"STALE","expired"),rows)
    self.assertIn((mission,winner,"active"),rows)
    self.assertIn((foreign_mission,"FOREIGN-MISSION","active"),rows)

    for action, is_live, bound in (
        ("rootline_fertilizer_mixer_presence_refresh",False,True),
        ("rootline_fertilizer_mixer_presence_refresh",True,False),
        ("foreign_action",False,False)):
      target="NEG-"+uuid.uuid4().hex
      token="D"+uuid.uuid4().hex
      insert(token,action,target,"BLOCKER",live if is_live else expired,
        "CARD" if bound else None)
      with self.assertRaisesRegex(RuntimeError,"protected_claim_active_preview_conflict"):
        create_claim(action_kind="rootline_fertilizer_mixer_presence_refresh",
          owner_user_id="42",private_chat_id="42",mission_id=target,
          provider_message_id="NEW",evidence_generation="NEW",
          preview_payload={"mission_id":target},ttl_minutes=5,
          connect_factory=self.connect,supersede_active=False)
      with self.connect() as db:
        state=db.execute("select status from app_private.oom_protected_action_claims where callback_token=%s",
          (token,)).fetchone()[0]
        db.execute("delete from app_private.oom_protected_action_claims where mission_id=%s",(target,))
      self.assertEqual(state,"active")
