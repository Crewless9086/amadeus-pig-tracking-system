import hashlib
import os
import re
import time
import unittest
import uuid
from collections import Counter
from dataclasses import dataclass, field

import psycopg

from modules.sales.sam_meat_database_deadline import SamMeatDatabaseDeadline
from modules.sales.sam_meat_launch_readiness import build_sam_meat_launch_packet
from modules.sales.sam_meat_truth_snapshot import load_sam_meat_truth_snapshot


DATABASE_URL = os.getenv("SAM_MEAT_DEADLINE_POSTGRES_URL", "").strip()
VOLUMES = {"small": 3, "expected": 80, "elevated": 320}


@dataclass
class Metrics:
    statements: list = field(default_factory=list)
    rows_loaded: int = 0
    connections: int = 0
    transactions: int = 0


class CountingCursor:
    def __init__(self, cursor, metrics):
        self._cursor = cursor
        self._metrics = metrics

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def execute(self, query, params=None):
        shape = re.sub(r"\s+", " ", str(query)).strip().lower()
        self._metrics.statements.append(hashlib.sha256(shape.encode()).hexdigest()[:12])
        return self._cursor.execute(query, params)

    def fetchone(self):
        row = self._cursor.fetchone()
        self._metrics.rows_loaded += int(row is not None)
        return row

    def fetchall(self):
        rows = self._cursor.fetchall()
        self._metrics.rows_loaded += len(rows)
        return rows

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class CountingConnection:
    def __init__(self, connection, metrics):
        self._connection = connection
        self._metrics = metrics

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def cursor(self, *args, **kwargs):
        return CountingCursor(self._connection.cursor(*args, **kwargs), self._metrics)

    def close(self):
        return self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


class CountingDeadline:
    def __init__(self, metrics):
        self.metrics = metrics
        self.inner = SamMeatDatabaseDeadline()

    def connect(self, database_url, **kwargs):
        def connect(url, **connect_kwargs):
            self.metrics.connections += 1
            return CountingConnection(psycopg.connect(url, **connect_kwargs), self.metrics)
        return self.inner.connect(database_url, connect_callable=connect, **kwargs)


@unittest.skipUnless(DATABASE_URL, "SAM_MEAT_DEADLINE_POSTGRES_URL is required")
class SamMeatTruthSnapshotPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = {name: cls._seed(name, size) for name, size in VOLUMES.items()}

    @classmethod
    def _seed(cls, label, size):
        token = uuid.uuid4().hex[:10]
        target = f"SM-{label}-{token}"
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                leads = [(target, "target")] + [
                    (f"SM-{label}-{token}-{index}", f"synthetic-{index}")
                    for index in range(size - 1)
                ]
                cursor.executemany(
                    """insert into public.oom_sakkie_sales_leads
                       (lead_id,status,mode,campaign_source,lead_label,whatsapp_window_state)
                       values (%s,'interested','sales_lead_tracking_only','inbound_chatwoot',%s,'open')""",
                    leads,
                )
                reservations = []
                for index, (lead_id, _) in enumerate(leads):
                    reservations.append((f"RS-{token}-{index}", lead_id, f"SYN-{token}-{index}"))
                cursor.executemany(
                    """insert into public.oom_sakkie_meat_carcass_reservations
                       (reservation_id,lead_id,pig_id,product_type,carcass_side,status)
                       values (%s,%s,%s,'half_carcass','half_a','deposit_pending')""",
                    reservations,
                )
                target_reservation = reservations[0][0]
                cursor.execute(
                    """insert into public.oom_sakkie_meat_fulfillment_events
                       (fulfillment_event_id,lead_id,reservation_id,event_type)
                       values (%s,%s,%s,'delivery_required')""",
                    (f"FF-{token}", target, target_reservation),
                )
                cursor.execute(
                    """insert into public.oom_sakkie_meat_reconciliation_events
                       (reconciliation_event_id,lead_id,reservation_id,event_type)
                       values (%s,%s,%s,'balance_note')""",
                    (f"RC-{token}", target, target_reservation),
                )
                cursor.executemany(
                    "insert into public.meat_processing_batches (batch_id,status) values (%s,'Draft')",
                    [(f"BT-{token}-{index}",) for index in range(size)],
                )
                cursor.executemany(
                    "insert into public.meat_processing_batch_pigs (batch_pig_id,batch_id,pig_id) values (%s,%s,%s)",
                    [(f"BP-{token}-{index}", f"BT-{token}-{index}", reservations[index][2]) for index in range(size)],
                )
        return target

    def test_small_expected_elevated_are_query_bounded_and_under_five_seconds(self):
        for label, size in VOLUMES.items():
            with self.subTest(volume=label, rows=size):
                metrics = Metrics()
                started = time.monotonic()
                snapshot = load_sam_meat_truth_snapshot(
                    self.fixtures[label], database_deadline=CountingDeadline(metrics),
                    database_url=DATABASE_URL,
                )
                elapsed = time.monotonic() - started
                self.assertLessEqual(len(metrics.statements), 10)
                self.assertLessEqual(len(set(metrics.statements)), 10)
                self.assertEqual(metrics.connections, 1)
                self.assertEqual(metrics.transactions, 0)
                self.assertLess(elapsed, 5.0)
                self.assertLessEqual(max(Counter(metrics.statements).values()), 1)
                print(f"SAM_MEAT_SNAPSHOT volume={label} synthetic_rows={size} statements={len(metrics.statements)} unique_shapes={len(set(metrics.statements))} rows_loaded={metrics.rows_loaded} connections={metrics.connections} transactions={metrics.transactions} elapsed_ms={elapsed * 1000:.1f}")
                self.assertTrue(snapshot["pricing"])
                self.assertIn("assembly", snapshot["availability"])
                self.assertIn("fulfillment", snapshot["fulfilment"])
                self.assertIn("truth_status", snapshot["butcher"])

    def test_bounded_query_plans_are_read_only(self):
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "explain (format json) select lead_id from public.oom_sakkie_sales_leads where lead_id = %s",
                    (self.fixtures["expected"],),
                )
                lead_plan = cursor.fetchone()[0][0]["Plan"]
                cursor.execute(
                    """explain (format json)
                       select b.batch_id, b.status, array_agg(bp.pig_id order by bp.pig_id)
                       from public.meat_processing_batch_pigs bp
                       join public.meat_processing_batches b on b.batch_id = bp.batch_id
                       where bp.pig_id = any(%s)
                       group by b.batch_id, b.status order by b.batch_id""",
                    (["synthetic-plan-key"],),
                )
                batch_plan = cursor.fetchone()[0][0]["Plan"]
        nodes = sorted(_plan_nodes(lead_plan) | _plan_nodes(batch_plan))
        self.assertNotIn("ModifyTable", nodes)
        self.assertTrue({"Index Scan", "Index Only Scan"} & set(_plan_nodes(lead_plan)))
        print("SAM_MEAT_SNAPSHOT_PLANS nodes=" + ",".join(nodes))
    def test_complete_packet_is_healthy_under_expected_and_elevated_volume(self):
        previous = os.environ.get("SUPABASE_DB_URL")
        os.environ["SUPABASE_DB_URL"] = DATABASE_URL
        try:
            for label in ("expected", "elevated"):
                started = time.monotonic()
                packet = build_sam_meat_launch_packet(
                    [{"message_id": f"MSG-{label}", "content": "I want a half carcass, Set A."}],
                    conversation_ref=f"SYN-{label}", inbound_event_id=f"MSG-{label}",
                    lead_id=self.fixtures[label],
                )
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 5.0)
                self.assertTrue(packet["truth"]["pricing"]["usable"])
                self.assertTrue(packet["truth"]["availability"]["usable"])
                self.assertTrue(packet["truth"]["fulfilment"]["usable"])
                self.assertTrue(packet["truth"]["butcher"]["usable"])
        finally:
            if previous is None:
                os.environ.pop("SUPABASE_DB_URL", None)
            else:
                os.environ["SUPABASE_DB_URL"] = previous



def _plan_nodes(plan):
    nodes = {str(plan.get("Node Type") or "")}
    for child in plan.get("Plans") or []:
        nodes.update(_plan_nodes(child))
    return nodes
if __name__ == "__main__":
    unittest.main()
