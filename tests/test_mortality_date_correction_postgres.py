"""Disposable-Postgres proof for the governed mortality-date correction."""
import os,uuid,unittest
from datetime import date
import psycopg
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority,issue_mortality_correction_authority
from modules.pig_weights.mortality_date_correction import correct_mortality_effective_date,mortality_correction_preview_digest


class MortalityDateCorrectionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL","").strip()
        if not cls.url:raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")

    def test_success_projection_supersession_and_replay(self):
        suffix=uuid.uuid4().hex; pig_id="PIG-CORR-"+suffix; prior_op="PRIOR-"+suffix
        prior_event="LIFE-PRIOR-"+suffix; operation="CORR-"+suffix
        with psycopg.connect(self.url) as db:
          with db.cursor() as cur:
            cur.execute("""insert into public.pigs(pig_id,status,on_farm,exit_date,exit_reason,notes)
              values(%s,'Dead',false,'2026-08-11','Died','immutable original note')""",(pig_id,))
            cur.execute("""insert into public.pig_lifecycle_events(lifecycle_event_id,pig_id,
              lifecycle_event_type,effective_at,actor_reference,source_system,source_reference,
              event_note,event_payload,idempotency_key) values(%s,%s,'exited_farm',
              '2026-08-11'::date::timestamptz,'owner','owner','test','original',
              '{\"immutable\":true}'::jsonb,%s)""",(prior_event,pig_id,prior_op))
        packet={"operation_id":operation,"pig_id":pig_id,"supersedes_operation_id":prior_op,
          "prior_date":"2026-08-11","corrected_date":"2026-08-06","actor_reference":"owner",
          "owner_evidence":{"removed_and_buried":True},"evidence_generation":"GEN-1","preview_digest":""}
        packet["preview_digest"]=mortality_correction_preview_digest(packet)
        base=issue_gateway_owner_authority("owner","owner")
        authority=issue_mortality_correction_authority(base,operation_id=operation,
          evidence_generation="GEN-1",preview_digest=packet["preview_digest"])
        result,status=correct_mortality_effective_date(packet,authority,
          connect_factory=lambda:psycopg.connect(self.url))
        self.assertEqual((status,result["corrected_date"]),(201,"2026-08-06"))
        replay,replay_status=correct_mortality_effective_date(packet,authority,
          connect_factory=lambda:psycopg.connect(self.url))
        self.assertEqual((replay_status,replay["rows_changed"]),(200,0))
        with psycopg.connect(self.url) as db:
          with db.cursor() as cur:
            cur.execute("select exit_date,status,on_farm from public.pigs where pig_id=%s",(pig_id,))
            self.assertEqual(cur.fetchone(),(date(2026,8,6),'Dead',False))
            cur.execute("select count(*) from public.pig_lifecycle_events where lifecycle_event_id=%s",(prior_event,))
            self.assertEqual(cur.fetchone()[0],1)
            cur.execute("select count(*) from public.pig_lifecycle_corrections where source_operation_id=%s",(operation,))
            self.assertEqual(cur.fetchone()[0],1)
