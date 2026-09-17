import pathlib
import unittest

from modules.pig_weights.litter_supersession_service import (
    apply_litter_supersession,
    canonical_sha256,
    operation_identity,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/202607300001_create_litter_supersession_rail.sql"
HISTORY_MIGRATION = ROOT / (
    "supabase/migrations/"
    "202607310001_allow_immutable_sam_review_history_in_litter_supersession.sql"
)


class _Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, replay=False, factual_rows=None):
        self.replay = replay
        self.factual_rows = factual_rows or []
        self.calls = []
        self.executemany_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(str(query).split())
        self.calls.append((normalized, params))
        if "from public.litter_supersessions where operation_id" in normalized:
            packet = _packet()
            return _Cursor((
                "LIT-B", "LIT-A", "AUTH-1", "a" * 64, "MAT-1",
                ["A-1", "A-2"], ["B-1", "B-2"],
                packet["reference_allowlist_sha256"],
                packet["skipped_audit_rows_sha256"], packet["input_sha256"],
                packet["historical_reference_rows_sha256"],
                packet["historical_reference_row_count"],
                packet["historical_reference_row_ids"],
            ) if self.replay else None)
        if "from public.litter_cohort_dispositions" in normalized:
            return _Cursor(rows=[("A-1",), ("A-2",)])
        if "from public.litter_supersession_audit_rows" in normalized:
            return _Cursor(rows=[])
        if "from public.litter_correction_authorizations" in normalized:
            packet = _packet()
            return _Cursor((operation_identity(packet), "a" * 64, "confirmed"))
        if "from public.litters litter" in normalized:
            return _Cursor(rows=[
                ({"litter_id": "LIT-A", "sow_pig_id": "SOW-1",
                  "boar_pig_id": "BOAR-1", "farrowing_date": "2026-07-10"},),
                ({"litter_id": "LIT-B", "sow_pig_id": "SOW-1",
                  "boar_pig_id": "BOAR-1", "farrowing_date": "2026-07-10"},),
            ])
        if "from public.mating_events" in normalized:
            return _Cursor(("MAT-1", "SOW-1", "BOAR-1", "LIT-B"))
        if "mother_pig_id=any" in normalized:
            return _Cursor(rows=[])
        if "from public.pigs pig" in normalized:
            return _Cursor(rows=[
                ({"pig_id": "A-1", "litter_id": "LIT-A"},),
                ({"pig_id": "A-2", "litter_id": "LIT-A"},),
                ({"pig_id": "B-1", "litter_id": "LIT-B"},),
                ({"pig_id": "B-2", "litter_id": "LIT-B"},),
            ])
        if "from information_schema.columns" in normalized:
            return _Cursor(rows=(
                [("pig_weight_events", "pig_id")] if self.factual_rows else []
            ))
        if "pig_weight_events" in normalized and "ctid" in normalized:
            return _Cursor(rows=[("(1,1)",)] if self.factual_rows else [])
        if "from public.bulk_weight_batch_rows" in normalized:
            return _Cursor(rows=[])
        if "select (select count(*) from public.current_canonical_litters" in normalized:
            return _Cursor((1, 2, 2))
        return _Cursor()

    def executemany(self, query, params):
        self.executemany_calls.append((query, list(params)))


def _packet():
    packet = {
        "retained_litter_id": "LIT-B",
        "superseded_litter_id": "LIT-A",
        "superseded_child_ids": ["A-2", "A-1"],
        "retained_child_ids": ["B-2", "B-1"],
        "authorization_id": "AUTH-1",
        "mating_id": "MAT-1",
        "preview_sha256": "a" * 64,
        "reference_allowlist_sha256": canonical_sha256({
            "schema_inventory": [], "references": [],
            "historical_review_rows": [],
            "historical_review_guard": [],
        }),
        "historical_reference_rows_sha256": canonical_sha256([]),
        "historical_reference_row_count": 0,
        "historical_reference_rows": [],
        "historical_reference_guard": [],
        "historical_reference_row_ids": [],
        "skipped_audit_rows_sha256": canonical_sha256([]),
        "skipped_audit_row_count": 0,
        "skipped_audit_row_ids": [],
        "input_sha256": "",
    }
    packet["input_sha256"] = canonical_sha256({
        "litters": [
            ({"litter_id": "LIT-A", "sow_pig_id": "SOW-1",
              "boar_pig_id": "BOAR-1", "farrowing_date": "2026-07-10"},),
            ({"litter_id": "LIT-B", "sow_pig_id": "SOW-1",
              "boar_pig_id": "BOAR-1", "farrowing_date": "2026-07-10"},),
        ],
        "mating": ("MAT-1", "SOW-1", "BOAR-1", "LIT-B"),
        "children": [
            ({"pig_id": "A-1", "litter_id": "LIT-A"},),
            ({"pig_id": "A-2", "litter_id": "LIT-A"},),
            ({"pig_id": "B-1", "litter_id": "LIT-B"},),
            ({"pig_id": "B-2", "litter_id": "LIT-B"},),
        ],
        "references": {
            "reference_allowlist_sha256": canonical_sha256({
                "schema_inventory": [], "references": [],
                "historical_review_rows": [],
                "historical_review_guard": [],
            }),
            "historical_reference_rows_sha256": canonical_sha256([]),
            "historical_reference_row_count": 0,
            "historical_reference_rows": [],
            "historical_reference_guard": [],
            "historical_reference_row_ids": [],
            "skipped_audit_rows_sha256": canonical_sha256([]),
            "skipped_audit_row_count": 0,
            "skipped_audit_row_ids": [],
        },
    })
    return packet


class LitterSupersessionContractTests(unittest.TestCase):
    def test_migration_is_append_only_and_exposes_current_and_history_views(self):
        source = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("litter_supersessions", source)
        self.assertIn("litter_cohort_dispositions", source)
        self.assertIn("current_canonical_litters", source)
        self.assertIn("historical_litter_representations", source)
        self.assertIn("current_canonical_pigs", source)
        self.assertIn("current_canonical_pig_state", source)
        self.assertIn("append-only", source)
        self.assertIn("cross-sow or cross-farrowing", source)
        self.assertNotIn("delete from public.litters", source.lower())
        self.assertNotIn("update public.pigs", source.lower())
        history_source = HISTORY_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("current_actionable_sam_live_stock_review_events", history_source)
        self.assertIn("historical_reference_row_ids", history_source)
        self.assertNotIn(
            "update public.sam_live_stock_conversation_review_events",
            history_source.lower(),
        )

    def test_operation_identity_is_order_independent(self):
        first = _packet()
        second = _packet()
        second["superseded_child_ids"].reverse()
        second["retained_child_ids"].reverse()
        self.assertEqual(operation_identity(first), operation_identity(second))

    def test_service_rejects_non_service_authority(self):
        with self.assertRaises(PermissionError):
            apply_litter_supersession(
                _packet(), connect_factory=lambda: _Connection(),
                service_authority="owner",
            )

    def test_service_creates_metadata_only_and_exact_dispositions(self):
        connection = _Connection()
        result = apply_litter_supersession(
            _packet(), connect_factory=lambda: connection,
            service_authority="herdmaster_litter_correction_service",
        )
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["rows_created"], 3)
        sql = "\n".join(call[0] for call in connection.calls)
        self.assertIn("transaction isolation level serializable", sql)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("for update", sql)
        self.assertNotIn("delete ", sql.lower())
        self.assertNotIn("update public.", sql.lower())
        self.assertEqual(connection.executemany_calls, [])
        self.assertIn("apply_litter_supersession_metadata", sql)

    def test_replay_creates_zero_rows_after_poststate_match(self):
        connection = _Connection(replay=True)
        result = apply_litter_supersession(
            _packet(), connect_factory=lambda: connection,
            service_authority="herdmaster_litter_correction_service",
        )
        self.assertEqual(result["status"], "replayed")
        self.assertEqual(result["rows_created"], 0)
        self.assertFalse(result["writes_performed"])
        self.assertEqual(connection.executemany_calls, [])

    def test_overlap_and_changed_child_linkage_fail_closed(self):
        overlap = _packet()
        overlap["retained_child_ids"] = ["A-1", "B-1"]
        with self.assertRaises(ValueError):
            apply_litter_supersession(
                overlap, connect_factory=lambda: _Connection(),
                service_authority="herdmaster_litter_correction_service",
            )
        connection = _Connection()
        changed = _packet()
        changed["superseded_child_ids"] = ["A-1"]
        with self.assertRaises(RuntimeError):
            apply_litter_supersession(
                changed, connect_factory=lambda: connection,
                service_authority="herdmaster_litter_correction_service",
            )

    def test_new_downstream_reference_digest_mismatch_rolls_back(self):
        connection = _Connection(
            factual_rows=[("pig_weight_events", "WEIGHT-1", "A-1")]
        )
        with self.assertRaisesRegex(RuntimeError, "downstream factual reference"):
            apply_litter_supersession(
                _packet(), connect_factory=lambda: connection,
                service_authority="herdmaster_litter_correction_service",
            )
        self.assertEqual(connection.executemany_calls, [])


if __name__ == "__main__":
    unittest.main()
