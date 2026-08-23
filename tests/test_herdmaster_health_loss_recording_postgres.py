"""Production-shaped disposable PostgreSQL proof for mortality coordination."""
import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg

from modules.pig_weights.herdmaster_health_loss_recording import confirm_health_loss_preview


DATABASE_URL = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()


@unittest.skipUnless(DATABASE_URL, "CHARLIE_DISPOSABLE_POSTGRES_URL is required")
class HealthLossRecordingPostgresTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex
        self.pig_id = "PIG-HL-" + self.suffix
        self.pen_id = "PEN-HL-" + self.suffix
        self.mission_id = "MISSION-HL-" + self.suffix
        self.case_id = "WELFARE-EXISTING-" + self.suffix
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("insert into public.pens(pen_id,pen_name) values(%s,%s)",
                       (self.pen_id, "Health loss test pen"))
            db.execute("""insert into public.pigs(
                pig_id,tag_number,pig_name,status,on_farm,initial_pen_id,purpose)
                values(%s,%s,'Postgres proof','Active',true,%s,'Sale')""",
                (self.pig_id, self.pig_id, self.pen_id))
            db.execute("""insert into public.pig_active_outlets(
                outlet_assignment_id,pig_id,outlet_type,source_record_id,evidence_json)
                values(%s,%s,'customer_sale',%s,'{}')""",
                ("OUTLET-" + self.suffix, self.pig_id, "SOURCE-" + self.suffix))
            self._open_case(db, occurred="2026-08-23 07:00+00")

    def _open_case(self, db, *, occurred):
        db.execute("""insert into public.pig_welfare_cases(
            welfare_case_id,pig_id,episode_key,concern_key,episode_started_at,
            first_reported_at,created_by,source_system,source_reference,
            provenance_json,idempotency_key)
            values(%s,%s,%s,'reported-death',%s::timestamptz,%s::timestamptz,
                   'owner:anton','oom_sakkie',%s,'{}',%s)""",
            (self.case_id, self.pig_id, self.mission_id, occurred, occurred,
             "telegram:" + self.suffix, "case:" + self.mission_id))
        db.execute("""insert into public.pig_welfare_case_events(
            welfare_case_event_id,welfare_case_id,sequence_no,event_type,case_state,
            urgency,responsible_owner,occurred_at,actor_reference,source_system,
            source_reference,provenance_json,idempotency_key)
            values(%s,%s,1,'opened','open','urgent','HERDMASTER',%s::timestamptz,
                   'owner:anton','oom_sakkie',%s,'{}',%s)""",
            ("WELFARE-OPEN-" + self.suffix, self.case_id, occurred,
             "telegram:" + self.suffix, "open:" + self.suffix))

    def _packet(self, operation=None, timestamp="2026-08-23T08:00:00+00:00"):
        operation = operation or "HERD-HL-" + self.suffix
        return {"owner_user_id": "anton", "mission_id": self.mission_id,
            "provider_timestamp": timestamp, "provider_message_id": "tg-" + self.suffix,
            "preview": {"confirmation_ready": True,
                "confirmation_binding": {"operation_id": operation,
                    "confirmation_ready": True, "authenticated_principal_id": "anton",
                    "provider_message_id": "tg-" + self.suffix,
                    "preview_sha256": "a" * 64, "evidence_generation": "GEN-PG"},
                "evaluator": {"identity": {"pig_id": self.pig_id,
                    "tag_number": self.pig_id, "name": "Postgres proof"},
                    "canonical_effects": [
                        {"area": "lifecycle", "action": "record_death", "supported": True,
                         "facts": {"date": "2026-08-23", "time": "Unknown"}},
                        {"area": "availability", "supported": True, "facts": {}},
                        {"area": "movement_pen", "supported": True,
                         "facts": {"owner_reported_outcome": "removed and buried"}},
                        {"area": "downstream_work", "supported": True, "facts": {}},
                    ]}}}

    def _confirm(self, packet):
        operation = packet["preview"]["confirmation_binding"]["operation_id"]
        return confirm_health_loss_preview(packet, "CONFIRM " + operation,
            actor_id="anton", evidence_loader=lambda: {"evidence_generation": "GEN-PG"},
            connect_factory=lambda: psycopg.connect(DATABASE_URL))

    def test_existing_attributable_case_closes_with_positive_sequence_and_canonical_readback(self):
        with patch.dict(os.environ, {"PIG_WELFARE_CASE_RUNTIME_ENABLED": "true"}):
            result, status = self._confirm(self._packet())
        self.assertEqual((status, result["status"]), (201, "mortality_lifecycle_recorded"), result)
        self.assertEqual(result["welfare_case_id"], self.case_id)
        self.assertTrue(result["canonical_readback"]["excluded_from_active_pen_and_availability_projections"])
        with psycopg.connect(DATABASE_URL) as db:
            rows = db.execute("""select sequence_no,event_type,case_state,closure_kind
                from public.pig_welfare_case_events where welfare_case_id=%s
                order by sequence_no""", (self.case_id,)).fetchall()
            self.assertEqual(rows, [(1, "opened", "open", None), (2, "closed", "closed", "death")])
            self.assertEqual(db.execute("select count(*) from public.pig_welfare_cases where pig_id=%s",
                                        (self.pig_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("select count(*) from public.pig_active_outlets where pig_id=%s and active",
                                        (self.pig_id,)).fetchone()[0], 0)

    def test_concurrent_same_operation_is_idempotent(self):
        packet = self._packet()
        with patch.dict(os.environ, {"PIG_WELFARE_CASE_RUNTIME_ENABLED": "true"}):
            results = list(ThreadPoolExecutor(max_workers=2).map(lambda _: self._confirm(packet), range(2)))
        self.assertEqual(sorted(status for _, status in results), [200, 201], results)
        with psycopg.connect(DATABASE_URL) as db:
            self.assertEqual(db.execute("select count(*) from public.pig_lifecycle_events where pig_id=%s",
                                        (self.pig_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("select count(*) from public.pig_welfare_case_events where welfare_case_id=%s",
                                        (self.case_id,)).fetchone()[0], 2)

    def test_welfare_chronology_failure_rolls_back_lifecycle_outlet_and_pig(self):
        with patch.dict(os.environ, {"PIG_WELFARE_CASE_RUNTIME_ENABLED": "true"}):
            result, status = self._confirm(self._packet(timestamp="2026-08-23T06:00:00+00:00"))
        self.assertEqual((status, result["status"]), (503, "mortality_lifecycle_recording_unavailable"))
        with psycopg.connect(DATABASE_URL) as db:
            self.assertEqual(db.execute("select status,on_farm from public.pigs where pig_id=%s",
                                        (self.pig_id,)).fetchone(), ("Active", True))
            self.assertEqual(db.execute("select count(*) from public.pig_lifecycle_events where pig_id=%s",
                                        (self.pig_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from public.pig_active_outlets where pig_id=%s and active",
                                        (self.pig_id,)).fetchone()[0], 1)
