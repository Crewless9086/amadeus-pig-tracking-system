from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights import pig_weights_service


class FarmSupabaseReadServiceTests(unittest.TestCase):
    class _Column:
        def __init__(self, name):
            self.name = name

    class _SnapshotCursor:
        def __init__(self, fail_fragment=None):
            self.fail_fragment = fail_fragment
            self.description = [FarmSupabaseReadServiceTests._Column("placeholder")]
            self.rows = []
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=()):
            text = str(sql).lower()
            self.last_sql = text
            if self.fail_fragment and self.fail_fragment in text:
                raise TimeoutError("bounded statement timeout")
            self.rows = []
            return self

        def fetchall(self):
            return self.rows

        def fetchone(self):
            if "transaction_timestamp()" in self.last_sql:
                return (datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc),)
            return self.rows[0] if self.rows else None

    class _SnapshotConnection:
        def __init__(self, fail_fragment=None):
            self.fail_fragment = fail_fragment
            self.cursor_count = 0
            self.exit_count = 0
            self.exit_exception = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, _exc, _tb):
            self.exit_count += 1
            self.exit_exception = exc_type
            return False

        def cursor(self):
            self.cursor_count += 1
            return FarmSupabaseReadServiceTests._SnapshotCursor(self.fail_fragment)

    def test_allocation_readiness_uses_one_bounded_consistent_snapshot(self):
        connection = self._SnapshotConnection()
        calls = []

        def factory(_url):
            calls.append(connection)
            return connection

        result = farm_supabase_read_service.get_allocation_input_rows(
            connect_factory=factory, deadline_seconds=20,
        )
        progress = result["read_progress"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(progress["shared_snapshot"])
        self.assertEqual(progress["connection_count"], 1)
        self.assertEqual(progress["query_count"], 6)
        self.assertEqual(progress["status"], "complete")
        self.assertTrue(all(stage["state"] == "complete" for stage in progress["stages"]))
        self.assertEqual(connection.exit_count, 1)
        self.assertIsNone(connection.exit_exception)

    def test_breeding_attention_snapshot_uses_one_connection_and_nine_queries(self):
        connection = self._SnapshotConnection()
        calls = []

        result = farm_supabase_read_service.get_breeding_attention_source_snapshot(
            connect_factory=lambda _url: calls.append(connection) or connection,
            deadline_seconds=20,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(result["read_progress"]["connection_count"], 1)
        self.assertEqual(result["read_progress"]["query_count"], 9)
        self.assertIn("exposure_rows", result)
        self.assertEqual(result["read_progress"]["status"], "complete")
        self.assertEqual(
            [stage["stage"] for stage in result["read_progress"]["stages"]],
            list(farm_supabase_read_service.BREEDING_ATTENTION_READ_STAGES),
        )
        self.assertEqual(connection.exit_count, 1)

    def test_breeding_attention_snapshot_fails_whole_inventory_on_slow_supporting_stage(self):
        connection = self._SnapshotConnection("from public.mating_events")
        with self.assertRaises(TimeoutError):
            farm_supabase_read_service.get_breeding_attention_source_snapshot(
                connect_factory=lambda _url: connection,
            )
        self.assertEqual(connection.exit_count, 1)
        self.assertIs(connection.exit_exception, TimeoutError)

    def test_allocation_snapshot_connection_failure_fails_closed(self):
        def factory(_url):
            raise ConnectionError("unavailable")

        with self.assertRaises(ConnectionError):
            farm_supabase_read_service.get_allocation_input_rows(connect_factory=factory)

    def test_allocation_snapshot_exposes_slow_connection_acquisition(self):
        connection = self._SnapshotConnection()
        clock = [0.0]

        def factory(_url):
            clock[0] = 0.5
            return connection

        result = farm_supabase_read_service.get_allocation_input_rows(
            connect_factory=factory,
            now_fn=lambda: clock[0],
        )
        first = result["read_progress"]["stages"][0]
        self.assertEqual(first["connection_acquisition_seconds"], 0.5)
        self.assertEqual(result["read_progress"]["connection_count"], 1)

    def test_allocation_snapshot_individual_statement_timeout_fails_closed(self):
        connection = self._SnapshotConnection("from public.pig_medical_events")
        with self.assertRaises(TimeoutError):
            farm_supabase_read_service.get_allocation_input_rows(
                connect_factory=lambda _url: connection,
            )
        self.assertEqual(connection.exit_count, 1)
        self.assertIs(connection.exit_exception, TimeoutError)

    def test_allocation_snapshot_total_deadline_exhaustion_fails_closed(self):
        connection = self._SnapshotConnection()
        clock = iter([0.0, 0.0, 0.0, 2.0, 2.0, 2.0])
        with self.assertRaises(TimeoutError):
            farm_supabase_read_service.get_allocation_input_rows(
                connect_factory=lambda _url: connection,
                deadline_seconds=1.0,
                now_fn=lambda: next(clock),
            )

    def test_allocation_snapshot_connection_acquisition_consumes_total_deadline(self):
        connection = self._SnapshotConnection()
        clock = iter([0.0, 2.0, 2.0])
        with self.assertRaisesRegex(TimeoutError, "connection acquisition"):
            farm_supabase_read_service.get_allocation_input_rows(
                connect_factory=lambda _url: connection,
                deadline_seconds=1.0,
                now_fn=lambda: next(clock),
            )
        self.assertEqual(connection.exit_count, 1)

    def test_allocation_snapshot_final_fetch_overrun_fails_closed(self):
        snapshot = farm_supabase_read_service._AllocationSnapshot(
            self._SnapshotConnection(),
            0.0,
            deadline_seconds=1.0,
            now_fn=lambda: 2.0,
            started_at=0.0,
        )
        with self.assertRaises(TimeoutError):
            snapshot.finish_rows("pens", 20)
        self.assertEqual(snapshot.records["pens"]["state"], "total_deadline_exhausted")

    def test_allocation_snapshot_preserves_managed_transaction_ownership(self):
        connection = self._SnapshotConnection()
        factory = pig_weights_service._ManagedReadFactory(connection)
        result = farm_supabase_read_service.get_allocation_input_rows(connect_factory=factory)
        self.assertEqual(result["read_progress"]["connection_count"], 1)
        self.assertEqual(result["read_progress"]["query_count"], 6)
        self.assertEqual(connection.exit_count, 0)

    def test_allocation_inputs_join_active_order_assignments(self):
        calls = []
        def fetch(sql, params=(), connect_factory=None):
            calls.append(sql)
            if "from public.order_lines line" in sql:
                return [{"pig_id": "PIG-1", "order_id": "ORD-1", "line_status": "Draft"}]
            if "from public.pig_medical_events" in sql:
                return []
            if "from public.pig_weight_events" in sql:
                return []
            if (
                "from public.current_canonical_litters" in sql
                or "from public.pens" in sql
            ):
                return []
            return []
        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=[{"pig_id": "PIG-1"}]), patch.object(
            farm_supabase_read_service, "_fetch_all", side_effect=fetch,
        ):
            result = farm_supabase_read_service.get_allocation_input_rows()
        self.assertEqual(result["overview_rows"][0]["Reserved_Status"], "Allocated")
        self.assertEqual(result["overview_rows"][0]["Reserved_For_Order_ID"], "ORD-1")
        self.assertEqual(result["overview_rows"][0]["Allocation_Evidence_State"], "allocated")
        self.assertEqual(result["allocation_query_status"], "known")
        self.assertTrue(any("customer_order.order_status" in sql for sql in calls))
        allocation_sql = next(sql for sql in calls if "from public.order_lines line" in sql)
        self.assertIn("lower(btrim(line.line_status))", allocation_sql)
        self.assertIn("lower(btrim(customer_order.order_status))", allocation_sql)
        self.assertIn("'cancelled', 'collected'", allocation_sql)
        self.assertIn("'cancelled', 'completed', 'rejected'", allocation_sql)

    def test_allocation_inputs_model_withdrawal_evidence_states(self):
        current = [
            {"pig_id": "PIG-NONE"},
            {"pig_id": "PIG-NA"},
            {"pig_id": "PIG-CLEAR"},
            {"pig_id": "PIG-HOLD"},
            {"pig_id": "PIG-UNKNOWN"},
        ]
        medical = [
            {"pig_id": "PIG-NA", "withdrawal_days": 0},
            {"pig_id": "PIG-CLEAR", "withdrawal_days": 7, "withdrawal_end_date": date.today() - timedelta(days=1)},
            {"pig_id": "PIG-HOLD", "withdrawal_days": 7, "withdrawal_end_date": date.today() + timedelta(days=1)},
            {"pig_id": "PIG-UNKNOWN", "withdrawal_days": None, "withdrawal_end_date": None},
        ]

        def fetch(sql, params=(), connect_factory=None):
            if "from public.order_lines line" in sql:
                return []
            if "from public.pig_medical_events" in sql:
                return medical
            return []

        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=current), patch.object(
            farm_supabase_read_service, "_fetch_all", side_effect=fetch,
        ):
            result = farm_supabase_read_service.get_allocation_input_rows()

        states = {row["Pig_ID"]: row["Withdrawal_Evidence_State"] for row in result["overview_rows"]}
        self.assertEqual(states, {
            "PIG-NONE": "unknown",
            "PIG-NA": "not_applicable",
            "PIG-CLEAR": "cleared",
            "PIG-HOLD": "hold",
            "PIG-UNKNOWN": "unknown",
        })

    def test_allocation_read_failure_fails_closed(self):
        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=[{"pig_id": "PIG-1"}]), patch.object(
            farm_supabase_read_service, "_fetch_all", side_effect=RuntimeError("order table unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "order table unavailable"):
                farm_supabase_read_service.get_allocation_input_rows()

    def test_pig_summary_maps_current_state_to_existing_frontend_shape(self):
        row = {
            "pig_id": "PIG-1",
            "tag_number": "101",
            "pig_name": "Pig One",
            "status": "Active",
            "on_farm": True,
            "animal_type": "Grower",
            "sex": "Female",
            "date_of_birth": date(2026, 1, 1),
            "litter_id": "LIT-1",
            "purpose": "Grow_Out",
            "current_weight_kg": 61.5,
            "last_weight_date": date(2026, 6, 22),
            "current_pen_id": "PEN-1",
            "current_pen_name": "Grower Pen",
        }

        summary = farm_supabase_read_service._pig_summary(row)

        self.assertEqual(summary["pig_id"], "PIG-1")
        self.assertEqual(summary["tag_number"], "101")
        self.assertEqual(summary["on_farm"], "Yes")
        self.assertEqual(summary["current_weight_kg"], 61.5)
        self.assertEqual(summary["last_weight_date"], "2026-06-22")
        self.assertEqual(summary["current_pen_name"], "Grower Pen")
        self.assertEqual(summary["weight_band"], "60-<80 kg")

    def test_weight_history_calculates_differences_from_supabase_rows(self):
        rows_by_sql = []

        def fake_fetch_all(sql, params=(), connect_factory=None):
            rows_by_sql.append(sql)
            if "from public.pig_weight_events" in sql:
                return [
                    {
                        "weight_event_id": "WGT-2",
                        "pig_id": "PIG-1",
                        "weight_date": date(2026, 6, 22),
                        "weight_kg": 62.0,
                        "weighed_by": "Owner",
                        "condition_notes": "",
                    },
                    {
                        "weight_event_id": "WGT-1",
                        "pig_id": "PIG-1",
                        "weight_date": date(2026, 6, 15),
                        "weight_kg": 60.0,
                        "weighed_by": "Owner",
                        "condition_notes": "",
                    },
                ]
            if "select tag_number" in sql:
                return [{"tag_number": "101"}]
            return []

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            result = farm_supabase_read_service.get_weight_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["tag_number"], "101")
        self.assertEqual(result["history"][0]["difference_kg"], 2.0)
        self.assertEqual(result["history"][0]["days_since_previous"], 7)
        self.assertEqual(result["history"][0]["growth_rate_kg_day"], 0.286)

    def test_pig_detail_maps_supabase_current_state_with_parent_tags(self):
        def fake_fetch_one(sql, params=(), connect_factory=None):
            self.assertEqual(params, ("PIG-1",))
            return {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "pig_name": "Pig One",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Female",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "purpose": "Grow_Out",
                "current_weight_kg": 61.5,
                "last_weight_date": date(2026, 6, 22),
                "current_pen_id": "PEN-1",
                "current_pen_name": "Grower Pen",
                "mother_pig_id": "SOW-1",
                "mother_tag_number": "M1",
                "father_pig_id": "BOAR-1",
                "father_tag_number": "F1",
                "notes": "Healthy",
            }

        with patch.object(farm_supabase_read_service, "_fetch_one", side_effect=fake_fetch_one):
            detail = farm_supabase_read_service.get_pig_detail("PIG-1")

        self.assertEqual(detail["pig_id"], "PIG-1")
        self.assertEqual(detail["current_pen_name"], "Grower Pen")
        self.assertEqual(detail["mother_tag_number"], "M1")
        self.assertEqual(detail["father_tag_number"], "F1")
        self.assertEqual(detail["general_notes"], "Healthy")
        self.assertEqual(detail["source"], "supabase_canonical")

    def test_movement_history_maps_pen_names_and_current_pen(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            self.assertEqual(params, ("PIG-1",))
            return [{
                "location_event_id": "MOVE-1",
                "pig_id": "PIG-1",
                "move_date": date(2026, 6, 22),
                "from_pen_id": "PEN-1",
                "to_pen_id": "PEN-2",
                "from_pen_name": "Old Pen",
                "to_pen_name": "New Pen",
                "reason_for_move": "Growth",
                "moved_by": "Owner",
                "move_notes": "Moved after weighing",
            }]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all), \
             patch.object(farm_supabase_read_service, "get_pig_detail", return_value={
                 "tag_number": "101",
                 "current_pen_id": "PEN-2",
             }):
            result = farm_supabase_read_service.get_movement_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["current_pen_id"], "PEN-2")
        self.assertEqual(result["history"][0]["to_pen_name"], "New Pen")
        self.assertEqual(result["history"][0]["move_date_display"], "2026-06-22")

    def test_treatment_history_maps_supabase_medical_events(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.pig_medical_events" in sql:
                return [{
                    "medical_event_id": "MED-1",
                    "pig_id": "PIG-1",
                    "treatment_date": date(2026, 6, 22),
                    "treatment_type": "Deworming",
                    "product_id": "PRD-1",
                    "product_name": "Dewormer",
                    "dose": 2,
                    "dose_unit": "ml",
                    "route": "Oral",
                    "reason_for_treatment": "Routine",
                    "batch_lot_number": "B1",
                    "withdrawal_days": 7,
                    "withdrawal_end_date": date(2026, 6, 29),
                    "given_by": "Owner",
                    "follow_up_required": False,
                    "follow_up_date": None,
                    "medical_notes": "No issue",
                }]
            return [{"tag_number": "101"}]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            result = farm_supabase_read_service.get_treatment_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["history"][0]["treatment_type"], "Deworming")
        self.assertEqual(result["history"][0]["withdrawal_end_date"], "2026-06-29")
        self.assertEqual(result["history"][0]["follow_up_required"], "No")

    def test_latest_weight_and_weights_by_date_map_supabase_rows(self):
        def fake_fetch_one(sql, params=(), connect_factory=None):
            return {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "current_weight_kg": 62,
                "last_weight_date": date(2026, 6, 22),
            }

        def fake_fetch_all(sql, params=(), connect_factory=None):
            return [{
                "weight_event_id": "WGT-1",
                "pig_id": "PIG-1",
                "tag_number": "101",
                "current_pen_id": "PEN-1",
                "weight_date": date(2026, 6, 22),
                "weight_kg": 62,
                "weighed_by": "Owner",
                "condition_notes": "",
            }]

        with patch.object(farm_supabase_read_service, "_fetch_one", side_effect=fake_fetch_one):
            latest = farm_supabase_read_service.get_latest_weight_for_pig("PIG-1")
        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            entries = farm_supabase_read_service.get_weight_entries_by_date(date(2026, 6, 22))

        self.assertEqual(latest["previous_weight_kg"], 62.0)
        self.assertEqual(latest["previous_weight_date"], "2026-06-22")
        self.assertEqual(entries["count"], 1)
        self.assertEqual(entries["history"][0]["current_pen_id"], "PEN-1")

    def test_parent_options_maps_breeding_pigs_from_supabase(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            return [
                {
                    "pig_id": "SOW-1",
                    "tag_number": "M1",
                    "sex": "Female",
                    "status": "Active",
                    "purpose": "Breeding",
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Sow Pen",
                },
                {
                    "pig_id": "BOAR-1",
                    "tag_number": "F1",
                    "sex": "Male",
                    "status": "Active",
                    "purpose": "Breeding",
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Boar Pen",
                },
            ]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            options = farm_supabase_read_service.get_parent_options()

        self.assertEqual(options["mothers"][0]["pig_id"], "Unknown")
        self.assertEqual(options["fathers"][0]["pig_id"], "Unknown")
        self.assertEqual(options["mothers"][1]["pig_id"], "SOW-1")
        self.assertEqual(options["mothers"][1]["current_pen_name"], "Sow Pen")
        self.assertEqual(options["fathers"][1]["pig_id"], "BOAR-1")

    def test_weight_report_maps_supabase_events_and_summary(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            self.assertEqual(params, (date(2026, 5, 20),))
            return [
                {
                    "weight_event_id": "WGT-OLD",
                    "pig_id": "PIG-1",
                    "weight_date": date(2026, 5, 18),
                    "weight_kg": 40,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "001",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Camp 1",
                    "animal_type": "Grower",
                    "current_weight_kg": 42,
                },
                {
                    "weight_event_id": "WGT-1",
                    "pig_id": "PIG-1",
                    "weight_date": date(2026, 5, 20),
                    "weight_kg": 42,
                    "weighed_by": "Tester",
                    "condition_notes": "Good",
                    "tag_number": "001",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Camp 1",
                    "animal_type": "Grower",
                    "current_weight_kg": 42,
                },
                {
                    "weight_event_id": "WGT-2-OLD",
                    "pig_id": "PIG-2",
                    "weight_date": date(2026, 5, 18),
                    "weight_kg": 36,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "002",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Camp 2",
                    "animal_type": "Grower",
                    "current_weight_kg": 35,
                },
                {
                    "weight_event_id": "WGT-2",
                    "pig_id": "PIG-2",
                    "weight_date": date(2026, 5, 20),
                    "weight_kg": 35,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "002",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Camp 2",
                    "animal_type": "Grower",
                    "current_weight_kg": 35,
                },
            ]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            report = farm_supabase_read_service.get_weight_report(date(2026, 5, 20), date(2026, 5, 20))

        self.assertTrue(report["success"])
        self.assertEqual(report["source"], "supabase_canonical")
        self.assertEqual(report["summary"]["total_entries"], 2)
        self.assertEqual(report["summary"]["average_difference_kg"], 0.5)
        self.assertEqual(report["summary"]["weight_loss_count"], 1)
        self.assertEqual(report["loss_flags"][0]["pig_id"], "PIG-2")

    def test_family_tree_maps_current_pig_parents_and_siblings(self):
        rows = [
            {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Female",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "purpose": "Grow_Out",
                "current_weight_kg": 61.5,
                "last_weight_date": date(2026, 6, 22),
                "current_pen_id": "PEN-1",
                "current_pen_name": "Grower Pen",
                "mother_pig_id": "SOW-1",
                "father_pig_id": "BOAR-1",
            },
            {
                "pig_id": "PIG-2",
                "tag_number": "102",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Male",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "current_weight_kg": 60.0,
                "current_pen_id": "PEN-1",
            },
            {
                "pig_id": "SOW-1",
                "tag_number": "M1",
                "status": "Active",
                "on_farm": True,
                "sex": "Female",
                "purpose": "Breeding",
            },
            {
                "pig_id": "BOAR-1",
                "tag_number": "F1",
                "status": "Active",
                "on_farm": True,
                "sex": "Male",
                "purpose": "Breeding",
            },
        ]

        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=rows):
            tree = farm_supabase_read_service.get_family_tree("PIG-1")

        self.assertEqual(tree["pig_id"], "PIG-1")
        self.assertEqual(tree["current_pig"]["tag_number"], "101")
        self.assertEqual(tree["mother"]["pig_id"], "SOW-1")
        self.assertEqual(tree["father"]["pig_id"], "BOAR-1")
        self.assertEqual(tree["sibling_count"], 1)
        self.assertEqual(tree["siblings"][0]["pig_id"], "PIG-2")
        self.assertEqual(tree["source"], "supabase_canonical")

    def test_allocation_input_rows_maps_supabase_to_sheet_like_rows(self):
        current_rows = [{
            "pig_id": "PIG-1",
            "tag_number": "101",
            "status": "Active",
            "on_farm": True,
            "animal_type": "Grower",
            "sex": "Female",
            "date_of_birth": date(2026, 1, 1),
            "litter_id": "LIT-1",
            "purpose": "Grow_Out",
            "current_weight_kg": 61.5,
            "last_weight_date": date(2026, 6, 22),
            "wean_date": date(2026, 5, 10),
            "wean_weight_kg": 9.5,
            "current_pen_id": "PEN-1",
            "current_pen_name": "Grower Pen",
            "mother_pig_id": "SOW-1",
            "father_pig_id": "BOAR-1",
        }]

        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.pig_weight_events" in sql:
                return [{"pig_id": "PIG-1", "weight_date": date(2026, 6, 22), "weight_kg": 61.5}]
            if "from public.current_canonical_litters" in sql:
                return [{
                    "litter_id": "LIT-1",
                    "sow_pig_id": "SOW-1",
                    "boar_pig_id": "BOAR-1",
                    "sow_tag_number": "M1",
                    "boar_tag_number": "F1",
                    "born_alive": 10,
                    "weaned_count": 9,
                    "litter_status": "Active",
                }]
            if "from public.pens" in sql:
                return [{"pen_id": "PEN-1", "pen_name": "Grower Pen", "pen_type": "Grower"}]
            return []

        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=current_rows), \
             patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            inputs = farm_supabase_read_service.get_allocation_input_rows()

        self.assertEqual(inputs["source"], "supabase_canonical")
        self.assertEqual(inputs["overview_rows"][0]["Pig_ID"], "PIG-1")
        self.assertEqual(inputs["overview_rows"][0]["On_Farm"], "Yes")
        self.assertEqual(inputs["overview_rows"][0]["Wean_Date"], "2026-05-10")
        self.assertEqual(inputs["overview_rows"][0]["Wean_Weight_Kg"], 9.5)
        self.assertEqual(inputs["weight_rows"][0]["Weight_Kg"], 61.5)
        self.assertEqual(inputs["litter_rows"][0]["Born_Alive"], 10.0)
        self.assertEqual(inputs["pen_lookup"]["PEN-1"]["pen_name"], "Grower Pen")

    def test_litter_overview_and_detail_map_supabase_rows(self):
        litters = [{
            "litter_id": "LIT-1",
            "farrowing_date": date(2026, 6, 1),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "sow_tag_number": "M1",
            "boar_tag_number": "F1",
            "born_alive": 2,
            "total_born": 2,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-1": [
                {
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-1",
                    "current_weight_kg": 5.0,
                    "current_pen_id": "PEN-1",
                },
                {
                    "pig_id": "PIG-2",
                    "tag_number": "102",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-1",
                    "current_weight_kg": 6.0,
                    "current_pen_id": "PEN-1",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()
            detail = farm_supabase_read_service.get_litter_detail("LIT-1")

        self.assertTrue(overview["success"])
        self.assertEqual(overview["count"], 1)
        self.assertEqual(overview["litters"][0]["linked_pig_records"], 2)
        self.assertEqual(overview["litters"][0]["average_current_weight_kg"], 5.5)
        self.assertEqual(detail["count"], 2)
        self.assertEqual(detail["male_count"], 1)
        self.assertEqual(detail["female_count"], 1)
        self.assertEqual(detail["average_weight_kg"], 5.5)
        self.assertEqual(detail["birth_date"], "2026-06-01")
        self.assertEqual(detail["estimated_wean_date"], "2026-07-01")
        self.assertEqual(detail["wean_tag_attention_start_date"], "2026-06-28")
        self.assertEqual(detail["wean_planning_monday"], "2026-06-29")
        self.assertEqual(detail["days_until_estimated_wean"], (date(2026, 7, 1) - date.today()).days)
        self.assertEqual(detail["default_wean_age_days"], 30)
        self.assertEqual(detail["attention_window_days"], 3)
        self.assertEqual(detail["source"], "supabase_canonical")

    def test_litter_detail_includes_latest_attributable_mating_dates(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.current_canonical_litters" in sql:
                return [{
                    "litter_id": "LIT-MATING",
                    "farrowing_date": date(2026, 8, 1),
                    "sow_pig_id": "SOW-1",
                    "boar_pig_id": "BOAR-1",
                    "litter_status": "Active",
                }]
            if "from public.mating_events" in sql:
                return [{
                    "mating_id": "MAT-LATEST",
                    "related_litter_id": "LIT-MATING",
                    "mating_date": date(2026, 4, 10),
                    "expected_farrowing_date": date(2026, 8, 2),
                }]
            return []

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all), \
             patch.object(farm_supabase_read_service, "_current_state_rows", return_value=[]):
            detail = farm_supabase_read_service.get_litter_detail("LIT-MATING")

        self.assertEqual(detail["mating_id"], "MAT-LATEST")
        self.assertEqual(detail["mating_date"], "2026-04-10")
        self.assertEqual(detail["expected_farrowing_date"], "2026-08-02")

    def test_litter_detail_derives_114_day_date_from_one_exact_historical_mating(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.current_canonical_litters" in sql:
                return [{
                    "litter_id": "LIT-DERIVED",
                    "farrowing_date": date(2026, 8, 2),
                    "sow_pig_id": "SOW-1",
                    "boar_pig_id": "BOAR-1",
                    "litter_status": "Active",
                }]
            if "from public.mating_events" in sql:
                return [{
                    "mating_id": "MAT-ATTRIBUTABLE",
                    "related_litter_id": None,
                    "sow_pig_id": "SOW-1",
                    "boar_pig_id": "BOAR-1",
                    "mating_date": date(2026, 4, 10),
                    "expected_farrowing_date": None,
                }]
            return []

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all), \
             patch.object(farm_supabase_read_service, "_current_state_rows", return_value=[]):
            detail = farm_supabase_read_service.get_litter_detail("LIT-DERIVED")

        self.assertEqual(detail["mating_id"], "MAT-ATTRIBUTABLE")
        self.assertEqual(detail["mating_date"], "2026-04-10")
        self.assertEqual(detail["expected_farrowing_date"], "2026-08-02")

    def test_active_litter_inside_wean_window_becomes_attention_item(self):
        birth_date = date.today() - timedelta(days=27)
        estimated_wean_date = birth_date + timedelta(days=30)
        litters = [{
            "litter_id": "LIT-WEAN-DUE",
            "farrowing_date": birth_date,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "sow_tag_number": "M1",
            "boar_tag_number": "F1",
            "born_alive": 2,
            "total_born": 2,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
            "wean_date": None,
            "weaned_count": None,
        }]
        pigs_by_litter = {
            "LIT-WEAN-DUE": [
                {
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-WEAN-DUE",
                },
                {
                    "pig_id": "PIG-2",
                    "tag_number": "102",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-WEAN-DUE",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()
            detail = farm_supabase_read_service.get_litter_detail("LIT-WEAN-DUE")
            summary = farm_supabase_read_service.get_litter_attention_summary()

        litter = overview["litters"][0]
        self.assertEqual(overview["attention_count"], 1)
        self.assertEqual(litter["needs_attention"], "Yes")
        self.assertEqual(litter["action_type"], "mark_weaned")
        self.assertEqual(litter["estimated_wean_date"], estimated_wean_date.isoformat())
        self.assertEqual(litter["wean_tag_attention_start_date"], date.today().isoformat())
        self.assertEqual(litter["days_until_estimated_wean"], 3)
        self.assertEqual(detail["attention"]["action_type"], "mark_weaned")
        self.assertIn("3 day(s) from the estimated wean date", detail["attention"]["reason"])
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["items"][0]["action_type"], "mark_weaned")

    def test_active_litter_past_estimated_wean_date_becomes_attention_item(self):
        birth_date = date.today() - timedelta(days=40)
        estimated_wean_date = birth_date + timedelta(days=30)
        litters = [{
            "litter_id": "LIT-WEAN-OVERDUE",
            "farrowing_date": birth_date,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "sow_tag_number": "M1",
            "boar_tag_number": "F1",
            "born_alive": 1,
            "total_born": 1,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
            "wean_date": None,
            "weaned_count": None,
        }]
        pigs_by_litter = {
            "LIT-WEAN-OVERDUE": [{
                "pig_id": "PIG-1",
                "tag_number": "101",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Piglet",
                "sex": "Female",
                "date_of_birth": birth_date,
                "litter_id": "LIT-WEAN-OVERDUE",
            }],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-WEAN-OVERDUE")
            summary = farm_supabase_read_service.get_litter_attention_summary()

        self.assertEqual(detail["estimated_wean_date"], estimated_wean_date.isoformat())
        self.assertEqual(detail["days_until_estimated_wean"], -10)
        self.assertEqual(detail["attention"]["action_type"], "mark_weaned")
        self.assertIn("10 day(s) past the estimated wean date", detail["attention"]["reason"])
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["items"][0]["days_until_estimated_wean"], -10)

    def test_recorded_wean_date_does_not_hide_incomplete_active_lifecycle(self):
        birth_date = date.today() - timedelta(days=39)
        litters = [{
            "litter_id": "LIT-INCOMPLETE-WEAN",
            "farrowing_date": birth_date,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 1,
            "total_born": 1,
            "litter_status": "Active",
            "wean_date": date.today() - timedelta(days=4),
            "weaned_count": 1,
        }]
        pigs_by_litter = {"LIT-INCOMPLETE-WEAN": [{
            "pig_id": "PIG-1",
            "status": "Active",
            "on_farm": True,
            "date_of_birth": birth_date,
            "litter_id": "LIT-INCOMPLETE-WEAN",
        }]}

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-INCOMPLETE-WEAN")

        self.assertEqual(detail["attention"]["action_type"], "complete_weaning")
        self.assertIn("1 piglet(s) remain active and on-farm", detail["attention"]["reason"])
        self.assertEqual(detail["estimated_wean_date"], (birth_date + timedelta(days=30)).isoformat())

    def test_future_legacy_planned_wean_date_is_not_actual_weaning(self):
        litters = [{
            "litter_id": "LIT-2026-5C36", "farrowing_date": date(2026, 8, 12),
            "sow_pig_id": "SOW-MOLLY", "sow_tag_number": "Molly",
            "born_alive": 8, "total_born": 8, "litter_status": "Active",
            "wean_date": date(2026, 9, 11), "weaned_count": 0,
        }]
        pigs = [{"pig_id": f"MOLLY-{index}", "status": "Active", "on_farm": True,
                 "animal_type": "Piglet", "litter_id": "LIT-2026-5C36",
                 "date_of_birth": date(2026, 8, 12)} for index in range(8)]
        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, {"LIT-2026-5C36": pigs})):
            overview = farm_supabase_read_service.list_litter_overview()
            summary = farm_supabase_read_service.get_litter_attention_summary()
        litter = overview["litters"][0]
        self.assertNotEqual(litter["action_type"], "complete_weaning")
        self.assertFalse(litter["weaning_evidence"]["actual_weaning_recorded"])
        self.assertEqual(litter["weaning_evidence"]["planned_wean_date"], "2026-09-11")
        if summary["items"]:
            self.assertEqual(summary["items"][0]["sow_name"], "Molly")

    def test_completed_lifecycle_has_no_incomplete_weaning_warning(self):
        litters = [{"litter_id": "LIT-DONE", "farrowing_date": date(2026, 6, 1),
                    "litter_status": "Completed", "wean_date": date(2026, 7, 1),
                    "weaned_count": 1, "born_alive": 1, "total_born": 1}]
        pigs = [{"pig_id": "DONE-1", "status": "Sold", "on_farm": False,
                 "wean_date": date(2026, 7, 1), "animal_type": "Weaner",
                 "litter_id": "LIT-DONE"}]
        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, {"LIT-DONE": pigs})):
            detail = farm_supabase_read_service.get_litter_detail("LIT-DONE")
        self.assertNotEqual((detail.get("attention") or {}).get("action_type"), "complete_weaning")

    def test_litter_detail_uses_piglet_birth_date_when_litter_farrowing_date_missing(self):
        litters = [{
            "litter_id": "LIT-FALLBACK",
            "farrowing_date": None,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "sow_tag_number": "M1",
            "boar_tag_number": "F1",
            "born_alive": 2,
            "total_born": 2,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-FALLBACK": [
                {
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 2),
                    "litter_id": "LIT-FALLBACK",
                    "current_weight_kg": None,
                    "current_pen_id": "PEN-1",
                },
                {
                    "pig_id": "PIG-2",
                    "tag_number": "102",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-FALLBACK",
                    "current_weight_kg": None,
                    "current_pen_id": "PEN-1",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-FALLBACK")

        self.assertEqual(detail["birth_date"], "2026-06-01")
        self.assertEqual(detail["estimated_wean_date"], "2026-07-01")
        self.assertEqual(detail["wean_tag_attention_start_date"], "2026-06-28")
        self.assertEqual(detail["average_weight_kg"], None)

    def test_litter_overview_derives_status_when_supabase_status_is_unknown(self):
        litters = [{
            "litter_id": "LIT-ACTIVE",
            "farrowing_date": date(2026, 6, 1),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 1,
            "total_born": 1,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "",
        }]
        pigs_by_litter = {
            "LIT-ACTIVE": [{
                "pig_id": "PIG-ACTIVE",
                "tag_number": "101",
                "status": "active",
                "on_farm": True,
                "animal_type": "Piglet",
                "sex": "Female",
                "date_of_birth": date(2026, 6, 1),
                "litter_id": "LIT-ACTIVE",
                "current_weight_kg": 5.0,
                "current_pen_id": "PEN-1",
            }],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()
            detail = farm_supabase_read_service.get_litter_detail("LIT-ACTIVE")

        self.assertEqual(overview["litters"][0]["litter_status"], "Active")
        self.assertEqual(detail["litter_status"], "Active")
        self.assertEqual(detail["active_count"], 1)
        self.assertEqual(detail["lifecycle_outcomes"]["active"], 1)

    def test_litter_detail_counts_terminal_lifecycle_outcomes_from_supabase_rows(self):
        litters = [{
            "litter_id": "LIT-DONE",
            "farrowing_date": date(2026, 6, 1),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 4,
            "total_born": 4,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Unknown",
        }]
        pigs_by_litter = {
            "LIT-DONE": [
                {
                    "pig_id": "PIG-SOLD",
                    "tag_number": "101",
                    "status": "Sold",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-DONE",
                    "exit_reason": "livestock_sale",
                },
                {
                    "pig_id": "PIG-SLAUGHTER",
                    "tag_number": "102",
                    "status": "Slaughtered",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-DONE",
                    "exit_reason": "abattoir",
                },
                {
                    "pig_id": "PIG-DEAD",
                    "tag_number": "103",
                    "status": "Died",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-DONE",
                    "exit_reason": None,
                },
                {
                    "pig_id": "PIG-REMOVED",
                    "tag_number": "104",
                    "status": "Removed",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-DONE",
                    "exit_reason": "other",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()
            detail = farm_supabase_read_service.get_litter_detail("LIT-DONE")

        outcomes = detail["lifecycle_outcomes"]
        self.assertEqual(overview["litters"][0]["litter_status"], "Completed")
        self.assertEqual(detail["litter_status"], "Completed")
        self.assertEqual(detail["active_count"], 0)
        self.assertEqual(outcomes["active"], 0)
        self.assertEqual(outcomes["sold"], 1)
        self.assertEqual(outcomes["slaughtered"], 1)
        self.assertEqual(outcomes["dead"], 1)
        self.assertEqual(outcomes["removed"], 1)
        self.assertEqual(outcomes["other"], 0)
        self.assertEqual(detail["detail_state"], "completed")
        self.assertEqual(detail["estimated_wean_date"], "")
        self.assertIsNone(detail["days_until_estimated_wean"])

    def test_weaned_litter_detail_uses_wean_weight_and_closes_wean_countdown(self):
        litters = [{
            "litter_id": "LIT-WEANED",
            "farrowing_date": date(2026, 5, 1),
            "wean_date": date(2026, 6, 5),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 3,
            "total_born": 3,
            "stillborn_count": 0,
            "mummified_count": 0,
            "weaned_count": 3,
            "litter_status": "Weaned",
        }]
        pigs_by_litter = {
            "LIT-WEANED": [
                {
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Weaner",
                    "sex": "Female",
                    "date_of_birth": date(2026, 5, 1),
                    "litter_id": "LIT-WEANED",
                    "current_weight_kg": 24.0,
                    "wean_weight_kg": 8.0,
                    "wean_date": date(2026, 6, 5),
                    "current_pen_id": "PEN-1",
                },
                {
                    "pig_id": "PIG-2",
                    "tag_number": "102",
                    "status": "Sold",
                    "on_farm": False,
                    "animal_type": "Weaner",
                    "sex": "Male",
                    "date_of_birth": date(2026, 5, 1),
                    "litter_id": "LIT-WEANED",
                    "current_weight_kg": 28.0,
                    "wean_weight_kg": 10.0,
                    "wean_date": date(2026, 6, 5),
                    "exit_reason": "livestock_sale",
                    "current_pen_id": "",
                },
                {
                    "pig_id": "PIG-3",
                    "tag_number": "103",
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Weaner",
                    "sex": "Female",
                    "date_of_birth": date(2026, 5, 1),
                    "litter_id": "LIT-WEANED",
                    "current_weight_kg": 26.0,
                    "wean_weight_kg": 9.0,
                    "wean_date": date(2026, 6, 5),
                    "current_pen_id": "PEN-1",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-WEANED")

        self.assertEqual(detail["litter_status"], "Weaned")
        self.assertEqual(detail["detail_state"], "weaned")
        self.assertEqual(detail["wean_status"], "Complete")
        self.assertEqual(detail["wean_date"], "2026-06-05")
        self.assertEqual(detail["average_weight_source"], "wean_weight")
        self.assertEqual(detail["average_weight_kg"], 9.0)
        self.assertEqual(detail["average_current_weight_kg"], 26.0)
        self.assertEqual(detail["piglets"][1]["exit_reason"], "livestock_sale")
        self.assertEqual(detail["estimated_wean_date"], "")
        self.assertEqual(detail["wean_tag_attention_start_date"], "")
        self.assertIsNone(detail["days_until_estimated_wean"])
        self.assertIsNone(detail["attention"])

    def test_litter_detail_returns_attention_reason_when_counts_need_review(self):
        litters = [{
            "litter_id": "LIT-ATTENTION",
            "farrowing_date": date(2026, 6, 1),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 4,
            "total_born": 4,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-ATTENTION": [{
                "pig_id": "PIG-1",
                "tag_number": "101",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Piglet",
                "sex": "Female",
                "date_of_birth": date(2026, 6, 1),
                "litter_id": "LIT-ATTENTION",
                "current_weight_kg": 5.0,
                "current_pen_id": "PEN-1",
            }],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-ATTENTION")

        self.assertEqual(detail["attention"]["action_type"], "review_litter_counts")
        self.assertEqual(detail["attention"]["reason"], detail["attention"]["recommended_action"])
        self.assertEqual(detail["attention"]["linked_pig_records"], 1)
        self.assertIn("Review", detail["attention"]["recommended_action"])

    def test_litter_overview_does_not_flag_sold_disposed_or_completed_sale_piglets_as_missing(self):
        birth_date = date.today() - timedelta(days=10)
        litters = [{
            "litter_id": "LIT-SOLD",
            "farrowing_date": birth_date,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 6,
            "total_born": 7,
            "stillborn_count": 1,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-SOLD": [
                {
                    "pig_id": f"PIG-ACTIVE-{index}",
                    "tag_number": str(100 + index),
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-SOLD",
                    "current_weight_kg": 5.0,
                    "current_pen_id": "PEN-1",
                }
                for index in range(3)
            ] + [
                {
                    "pig_id": "PIG-SOLD",
                    "tag_number": "201",
                    "status": "Sold",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-SOLD",
                    "exit_reason": "livestock_sale",
                },
                {
                    "pig_id": "PIG-DISPOSED",
                    "tag_number": "202",
                    "status": "Disposed",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-SOLD",
                    "exit_reason": "disposed",
                },
                {
                    "pig_id": "PIG-COMPLETED",
                    "tag_number": "203",
                    "status": "Completed Sale",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-SOLD",
                    "exit_reason": "completed sale",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()
            detail = farm_supabase_read_service.get_litter_detail("LIT-SOLD")

        self.assertEqual(overview["attention_count"], 0)
        self.assertEqual(overview["mismatch_count"], 0)
        reconciliation = overview["litters"][0]["reconciliation"]
        self.assertFalse(reconciliation["mismatch"])
        self.assertEqual(reconciliation["live_linked_pig_records"], 6)
        self.assertEqual(reconciliation["accounted_terminal_live_pig_records"], 3)
        self.assertTrue(reconciliation["non_live_source_accounted"])
        self.assertIsNone(detail["attention"])
        self.assertEqual(detail["lifecycle_outcomes"]["sold"], 2)
        self.assertEqual(detail["lifecycle_outcomes"]["removed"], 1)

    def test_litter_overview_keeps_attention_for_true_missing_live_born_history(self):
        litters = [{
            "litter_id": "LIT-MISSING",
            "farrowing_date": date(2026, 6, 1),
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "born_alive": 6,
            "total_born": 6,
            "stillborn_count": 0,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-MISSING": [
                {
                    "pig_id": f"PIG-ACTIVE-{index}",
                    "tag_number": str(100 + index),
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-MISSING",
                    "current_weight_kg": 5.0,
                    "current_pen_id": "PEN-1",
                }
                for index in range(3)
            ] + [
                {
                    "pig_id": "PIG-SOLD",
                    "tag_number": "201",
                    "status": "Sold",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Male",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-MISSING",
                    "exit_reason": "livestock_sale",
                },
                {
                    "pig_id": "PIG-DISPOSED",
                    "tag_number": "202",
                    "status": "Disposed",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": date(2026, 6, 1),
                    "litter_id": "LIT-MISSING",
                    "exit_reason": "disposed",
                },
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            detail = farm_supabase_read_service.get_litter_detail("LIT-MISSING")

        self.assertEqual(detail["attention"]["action_type"], "review_litter_counts")
        self.assertEqual(detail["reconciliation"]["live_linked_pig_records"], 5)
        self.assertEqual(detail["reconciliation"]["accounted_terminal_live_pig_records"], 2)
        self.assertTrue(detail["reconciliation"]["mismatch"])
        self.assertIn("missing or extra live-born piglet history", detail["attention"]["recommended_action"])

    def test_litter_overview_does_not_flag_stillborn_rows_as_born_alive_mismatch(self):
        birth_date = date.today() - timedelta(days=10)
        litters = [{
            "litter_id": "LIT-2026-1025",
            "farrowing_date": birth_date,
            "sow_pig_id": "SOW-1",
            "boar_pig_id": "BOAR-1",
            "sow_tag_number": "M1",
            "boar_tag_number": "F1",
            "born_alive": 7,
            "total_born": 9,
            "stillborn_count": 2,
            "mummified_count": 0,
            "litter_status": "Active",
        }]
        pigs_by_litter = {
            "LIT-2026-1025": [
                {
                    "pig_id": f"PIG-LIVE-{index}",
                    "tag_number": str(100 + index),
                    "status": "Active",
                    "on_farm": True,
                    "animal_type": "Piglet",
                    "sex": "Female",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-2026-1025",
                    "current_weight_kg": 5.0,
                    "current_pen_id": "PEN-1",
                }
                for index in range(7)
            ] + [
                {
                    "pig_id": f"PIG-STILL-{index}",
                    "tag_number": "",
                    "status": "Dead",
                    "on_farm": False,
                    "animal_type": "Piglet",
                    "sex": "",
                    "date_of_birth": birth_date,
                    "litter_id": "LIT-2026-1025",
                    "current_weight_kg": None,
                    "current_pen_id": "",
                    "exit_reason": "Stillborn",
                }
                for index in range(2)
            ],
        }

        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs_by_litter)):
            overview = farm_supabase_read_service.list_litter_overview()

        self.assertTrue(overview["success"])
        self.assertEqual(overview["attention_count"], 1)
        self.assertEqual(overview["mismatch_count"], 0)
        litter = overview["litters"][0]
        self.assertEqual(litter["litter_id"], "LIT-2026-1025")
        self.assertEqual(litter["linked_pig_records"], 9)
        self.assertEqual(litter["active_pig_records"], 7)
        self.assertEqual(litter["exited_pig_records"], 2)
        self.assertEqual(litter["action_type"], "record_litter_newborn_health")
        reconciliation = litter["reconciliation"]
        self.assertFalse(reconciliation["mismatch"])
        self.assertEqual(reconciliation["live_linked_pig_records"], 7)
        self.assertEqual(reconciliation["stillborn_history_count"], 2)
        self.assertTrue(reconciliation["source_counts_consistent"])
        self.assertEqual(reconciliation["recommended_action"], "No birth-count correction needed.")

    def test_litter_attention_summary_maps_supabase_count_review(self):
        overview = {
            "success": True,
            "count": 1,
            "litters": [{
                "litter_id": "LIT-1",
                "sow_tag_number": "M1",
                "farrowing_date": "2026-06-01",
                "wean_date": "",
                "litter_status": "Active",
                "needs_attention": "Yes",
                "attention_reason": "Review litter counts.",
                "active_pig_records": 2,
                "reconciliation": {
                    "recommended_action": "Review litter counts.",
                },
            }],
        }

        with patch.object(farm_supabase_read_service, "list_litter_overview", return_value=overview):
            summary = farm_supabase_read_service.get_litter_attention_summary()

        self.assertEqual(summary["source"], "supabase_canonical")
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["items"][0]["litter_id"], "LIT-1")
        self.assertEqual(summary["items"][0]["action_type"], "review_litter_counts")
        self.assertEqual(summary["items"][0]["reason"], "Review litter counts.")

    def test_pig_master_rows_explicitly_mark_unwired_breeding_safety_facts_unknown(self):
        canonical_row = {
            "pig_id": "SOW-1", "tag_number": "M1", "status": "Active", "on_farm": True,
            "litter_id": "LIT-1", "sex": "Female", "current_weight_kg": 120.0,
            "last_weight_date": date(2026, 7, 23), "current_pen_id": "PEN-SOW",
            "pig_name": "Sow One", "animal_type": "Sow", "date_of_birth": date(2024, 1, 1),
            "mother_pig_id": "DAM-1", "father_pig_id": "SIRE-1",
            "purpose": "Breeding", "notes": "good condition", "exit_date": None,
            "exit_reason": "", "exit_order_id": "", "litter_size_born": 10,
            "litter_size_weaned": 9, "wean_date": None, "wean_weight_kg": None,
            "earmarked": False, "earmark_date": None,
        }

        with patch.object(farm_supabase_read_service, "_fetch_all", return_value=[canonical_row]):
            row = farm_supabase_read_service.get_pig_master_rows()[0]

        self.assertEqual(row["Genetics"], "")
        self.assertEqual(row["Available_For_Breeding"], "Unknown")
        self.assertEqual(row["Reserved_Status"], "Unknown")
        self.assertEqual(row["Source_Conflict"], "Unknown")
        self.assertEqual(row["Mother_Pig_ID"], "DAM-1")
        self.assertEqual(row["Father_Pig_ID"], "SIRE-1")
        self.assertEqual(row["source"], "supabase_canonical")

    def test_breeding_reads_map_supabase_mating_and_litter_data(self):
        current_rows = [
            {
                "pig_id": "SOW-1",
                "tag_number": "M1",
                "status": "Active",
                "on_farm": True,
                "purpose": "Breeding",
                "sex": "Female",
                "current_pen_id": "PEN-SOW",
                "current_pen_name": "Sow Pen",
            },
            {
                "pig_id": "BOAR-1",
                "tag_number": "B1",
                "status": "Active",
                "on_farm": True,
                "purpose": "Breeding",
                "sex": "Male",
                "current_pen_id": "PEN-BOAR",
                "current_pen_name": "Boar Pen",
            },
        ]
        mating_rows = [{
            "mating_id": "MAT-1",
            "sow_pig_id": "SOW-1",
            "sow_tag_number": "M1",
            "boar_pig_id": "BOAR-1",
            "boar_tag_number": "B1",
            "mating_date": date(2026, 5, 1),
            "mating_method": "Natural",
            "mating_pen_id": "PEN-MATING",
            "mating_pen_name": "Mating Pen",
            "exposure_group": "G1",
            "expected_pregnancy_check_date": date(2026, 5, 22),
            "pregnancy_check_date": date(2026, 5, 22),
            "pregnancy_check_result": "Pregnant",
            "expected_farrowing_date": date(2026, 8, 23),
            "farrowing_date": date(2026, 8, 22),
            "outcome": "Farrowed",
            "related_litter_id": "LIT-1",
            "mating_notes": "OK",
            "created_at": date(2026, 5, 1),
            "updated_at": date(2026, 5, 2),
        }]
        litter_overview = {
            "success": True,
            "count": 1,
            "litters": [{
                "litter_id": "LIT-1",
                "sow_pig_id": "SOW-1",
                "sow_tag_number": "M1",
                "boar_pig_id": "BOAR-1",
                "boar_tag_number": "B1",
                "born_alive": 10,
                "weaned_count": 9,
            }],
        }

        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=current_rows), \
             patch.object(farm_supabase_read_service, "_fetch_all", return_value=mating_rows), \
             patch.object(farm_supabase_read_service, "list_litter_overview", return_value=litter_overview):
            options = farm_supabase_read_service.get_breeding_options()
            matings = farm_supabase_read_service.get_mating_overview()
            analytics = farm_supabase_read_service.get_breeding_analytics()

        self.assertEqual(options["sows"][0]["pig_id"], "SOW-1")
        self.assertEqual(options["boars"][0]["current_pen_name"], "Boar Pen")
        self.assertEqual(matings[0]["mating_id"], "MAT-1")
        self.assertEqual(matings[0]["mating_status"], "Farrowed")
        self.assertEqual(matings[0]["sow_current_pen_name"], "Sow Pen")
        self.assertEqual(matings[0]["mating_pen_id"], "PEN-MATING")
        self.assertEqual(matings[0]["mating_pen_name"], "Mating Pen")
        self.assertEqual(analytics["source"]["mating_source"], "supabase_canonical")
        self.assertEqual(analytics["summary"]["mating_count"], 1)
        self.assertEqual(analytics["sows"][0]["average_born_alive"], 10.0)

    def test_active_exposure_cycle_enriches_blank_names_and_preserves_windows(self):
        current_rows = [
            {"pig_id":"SOW-1","pig_name":"Sophie","tag_number":"Sophie",
             "current_pen_id":"PEN-3","current_pen_name":"Kraam Saal 03"},
            {"pig_id":"BOAR-1","pig_name":"Bola","tag_number":"Bola",
             "current_pen_id":"PEN-3","current_pen_name":"Kraam Saal 03"},
        ]
        mating_rows = [{"mating_id":"MAT-EXPOSURE-1","sow_pig_id":"SOW-1",
            "sow_tag_number":"","boar_pig_id":"BOAR-1","boar_tag_number":"",
            "source_exposure_identity":"EXPOSURE-1","breeding_cycle_state":"Exposure Active",
            "service_window_start":date(2026,8,12),"service_window_end":date(2026,8,28),
            "exposure_planned_removal_on":date(2026,8,28),"exposure_actual_removal_on":None,
            "expected_farrowing_window_start":date(2026,12,4),
            "expected_farrowing_window_end":date(2026,12,20),"mating_date":None,
            "pregnancy_check_result":None,"outcome":None}]
        records=farm_supabase_read_service.project_mating_overview(
            mating_rows,current_rows,today=date(2026,8,12))
        row=records[0]
        self.assertEqual((row["sow_name"],row["sow_pig_id"]),("Sophie","SOW-1"))
        self.assertEqual((row["boar_name"],row["boar_pig_id"]),("Bola","BOAR-1"))
        self.assertEqual(row["owner_facing_cycle_meaning"],"By beer")
        self.assertEqual(row["exposure_planned_removal_status"],"Upcoming")
        self.assertEqual(row["expected_farrowing_window_start"],"2026-12-04")
        self.assertEqual(row["pregnancy_status"],"Unknown")

    def test_mating_pen_projection_uses_only_attributable_exposure_placement(self):
        rows = [{"mating_id":"MAT-1","sow_pig_id":"SOW-1",
                 "mating_pen_id":"PEN-4","mating_pen_name":"Paringshok 4"},
                {"mating_id":"MAT-2","sow_pig_id":"SOW-2"}]
        state = [{"pig_id":"SOW-1","current_pen_id":"LIVE-1","current_pen_name":"Live 1"},
                 {"pig_id":"SOW-2","current_pen_id":"LIVE-2","current_pen_name":"Live 2"}]
        projected = farm_supabase_read_service.project_mating_overview(rows, state)
        self.assertEqual(projected[0]["mating_pen_name"], "Paringshok 4")
        self.assertEqual(projected[1]["mating_pen_name"], "")
        with patch.object(farm_supabase_read_service, "_fetch_all", return_value=[] ) as fetch, \
             patch.object(farm_supabase_read_service, "_current_state_rows", return_value=[]):
            farm_supabase_read_service.get_mating_overview()
        sql = fetch.call_args.args[0]
        self.assertIn("exposure.exposure_identity = mating.source_exposure_identity", sql)
        self.assertIn("location.move_date = exposure.occurred_on", sql)
        self.assertIn("location.group_batch_id = exposure.exposure_group_identity", sql)
        self.assertIn("location.reason_for_move = 'Breeding exposure placement'", sql)
        self.assertIn("location.source = 'herdmaster_breeding_placement'", sql)

    def test_canonical_name_wins_but_historical_name_conflict_is_explicit(self):
        row={"mating_id":"MAT-1","sow_pig_id":"PIG-2026-069E","sow_tag_number":"Olivia",
             "boar_pig_id":"BOAR-1","boar_tag_number":"Tyson"}
        states=[{"pig_id":"PIG-2026-069E","tag_number":"Olive"},
                {"pig_id":"BOAR-1","tag_number":"Tyson"}]
        result=farm_supabase_read_service.project_mating_overview([row],states,today=date(2026,8,12))[0]
        self.assertEqual(result["sow_name"],"Olive")
        self.assertEqual(result["sow_pig_id"],"PIG-2026-069E")
        self.assertEqual(result["sow_historical_name"],"Olivia")
        self.assertEqual(result["sow_name_conflict"],"canonical_tag:Olive|historical_tag:Olivia")

    def test_legacy_exact_date_mating_semantics_remain_unchanged(self):
        row={"mating_id":"MAT-LEGACY","sow_pig_id":"SOW-1","sow_tag_number":"M1",
             "boar_pig_id":"BOAR-1","boar_tag_number":"B1","mating_date":date(2026,5,1),
             "expected_farrowing_date":date(2026,8,23),"pregnancy_check_result":"Pregnant"}
        result=farm_supabase_read_service.project_mating_overview([row],[],today=date(2026,8,12))[0]
        self.assertEqual(result["mating_date"],"2026-05-01")
        self.assertEqual(result["mating_status"],"Confirmed_Pregnant")
        self.assertEqual(result["owner_facing_cycle_meaning"],"")
        self.assertEqual(result["sow_name"],"M1")

    def test_canonical_name_and_matching_tag_do_not_create_false_conflict(self):
        row={"mating_id":"MAT-1","sow_pig_id":"SOW-1","sow_tag_number":"SOW-17",
             "boar_pig_id":"BOAR-1","boar_tag_number":"BOAR-2"}
        states=[{"pig_id":"SOW-1","pig_name":"Sophie","tag_number":"SOW-17"},
                {"pig_id":"BOAR-1","pig_name":"Bola","tag_number":"BOAR-2"}]
        result=farm_supabase_read_service.project_mating_overview([row],states,today=date(2026,8,12))[0]
        self.assertEqual(result["sow_name"],"Sophie")
        self.assertEqual(result["sow_tag_number"],"SOW-17")
        self.assertEqual(result["sow_canonical_tag_number"],"SOW-17")
        self.assertEqual(result["sow_name_conflict"],"")

    def test_name_fallback_and_planned_uit_status_do_not_claim_removal(self):
        base={"mating_id":"MAT-EXPOSURE","sow_pig_id":"SOW-1","sow_tag_number":"History Sow",
              "boar_pig_id":"BOAR-1","boar_tag_number":"","breeding_cycle_state":"Exposure Active",
              "exposure_actual_removal_on":None}
        for planned,expected in ((date(2026,8,11),"Overdue"),(date(2026,8,12),"Due")):
            row={**base,"exposure_planned_removal_on":planned}
            result=farm_supabase_read_service.project_mating_overview([row],[],today=date(2026,8,12))[0]
            self.assertEqual(result["sow_name"],"History Sow")
            self.assertEqual(result["boar_name"],"BOAR-1")
            self.assertEqual(result["exposure_planned_removal_status"],expected)
            self.assertEqual(result["exposure_actual_removal_on"],"")

    def test_pig_weights_service_prefers_supabase_when_available(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_pens", return_value=[{"pen_id": "PEN-1"}]):
            self.assertEqual(pig_weights_service.get_pens(), [{"pen_id": "PEN-1"}])

    def test_pen_lookup_uses_supabase_first_pens(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_pens", return_value=[{
                 "pen_id": "PEN-1",
                 "pen_name": "Grower Pen",
                 "pen_type": "Grower",
             }]) as read_pens, \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")):
            result = pig_weights_service._build_pen_lookup()

        self.assertEqual(result["PEN-1"]["pen_name"], "Grower Pen")
        read_pens.assert_called_once()

    def test_pig_weights_service_prefers_supabase_parent_options_when_available(self):
        expected = {"mothers": [{"pig_id": "SOW-1"}], "fathers": [{"pig_id": "BOAR-1"}]}
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_parent_options", return_value=expected):
            self.assertEqual(pig_weights_service.get_parent_options(), expected)

    def test_pig_weights_service_falls_back_when_supabase_unavailable(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", return_value=[
                 {"Pen_ID": "PEN-1", "Pen_Name": "Grower", "Pen_Type": "Grower", "Capacity": "10", "Is_Active": "Yes"}
             ]):
            result = pig_weights_service.get_pens()

        self.assertEqual(result[0]["pen_id"], "PEN-1")
        self.assertEqual(result[0]["pen_name"], "Grower")


    def test_closed_litter_detail_exposes_weaning_performance_and_exact_outcomes(self):
        litters = [{
            "litter_id": "LIT-CLOSED", "farrowing_date": date(2026, 5, 5),
            "wean_date": date(2026, 6, 10), "weaned_count": 2,
            "born_alive": 3, "total_born": 3, "litter_status": "Weaned",
        }]
        pigs = {"LIT-CLOSED": [
            {"pig_id": "PIG-A", "tag_number": "101", "sex": "Female", "status": "Sold", "on_farm": False,
             "litter_id": "LIT-CLOSED", "wean_date": date(2026, 6, 10), "wean_weight_kg": 5.0,
             "sale_channel": "Auction", "sale_stream": "Livestock", "sale_id": "SALE-1", "sale_date": date(2026, 8, 5)},
            {"pig_id": "PIG-B", "tag_number": "102", "sex": "Male", "status": "Active", "on_farm": True,
             "purpose": "Breeding", "litter_id": "LIT-CLOSED", "wean_date": date(2026, 6, 10), "wean_weight_kg": 7.0},
            {"pig_id": "PIG-C", "tag_number": "", "sex": "", "status": "Died", "on_farm": False,
             "litter_id": "LIT-CLOSED", "wean_date": None, "wean_weight_kg": None},
        ]}
        with patch.object(farm_supabase_read_service, "_litter_rows_with_pigs", return_value=(litters, pigs)), \
             patch.object(farm_supabase_read_service, "_fetch_all", return_value=[]):
            detail = farm_supabase_read_service.get_litter_detail("LIT-CLOSED")

        self.assertEqual(detail["weaned_count"], 2.0)
        self.assertEqual(detail["average_wean_weight_kg"], 6.0)
        self.assertEqual(detail["weaned_male_count"], 1)
        self.assertEqual(detail["weaned_female_count"], 1)
        self.assertEqual(detail["outcome_breakdown"]["auction_sale"], 1)
        self.assertEqual(detail["outcome_breakdown"]["breeding"], 1)
        self.assertEqual(detail["outcome_breakdown"]["dead"], 1)
        self.assertEqual(detail["piglets"][0]["outcome_label"], "Veilingsverkoop")


if __name__ == "__main__":
    unittest.main()
