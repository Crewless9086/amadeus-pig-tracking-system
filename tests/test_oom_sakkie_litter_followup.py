"""Offline regression for the canonical writer's retained follow-up identity."""
from datetime import datetime, timezone

from modules.oom_sakkie import manager_case_sources as sources
from contextlib import contextmanager

import pytest

NOW = datetime(2026, 9, 14, 10, 33, tzinfo=timezone.utc)
CASE_ID = "OOM-MANAGER-HERD-LITTER-OFFLINE1"
KEY = "herdmaster-litter-follow-up:LIT-OFFLINE1"


def test_saved_litter_followup_refresh_uses_its_existing_herdmaster_owner():
    expected = {"case_id": CASE_ID, "dedupe_key": KEY, "specialist": "HERDMASTER"}
    calls = []

    def _herdmaster(now):
        calls.append(now)
        return [expected]

    assert sources.collect_manager_candidate(now=NOW, dedupe_key=KEY,
        specialist="HERDMASTER", collectors=(_herdmaster,)) == expected
    assert calls == [NOW]
    assert sources.collect_manager_candidate(now=NOW, dedupe_key=KEY,
        specialist="ROOTLINE", collectors=(_herdmaster,)) is None


@pytest.mark.parametrize("rows, expected_unknown", [
    ([{"Litter_ID": "LIT-OFFLINE1", "Litter_Status": "Active", "Active_Pig_Count": 8,
       "Wean_Date": "2026-09-01", "first_treatment_evidence_state": "due"}], False),
    ([], True),
    ([{"Litter_ID": "LIT-OFFLINE1", "Litter_Status": "Weaned", "Weaned_Count": 8}], True),
    ([{"Litter_ID": "LIT-OFFLINE1", "Litter_Status": "Active", "Active_Pig_Count": 0}], True),
])
def test_retained_task_uses_current_litter_and_never_infers_closure(rows, expected_unknown):
    class Cursor:
        def execute(self, sql):
            assert "specialist='HERDMASTER'" in sql and "status<>'completed'" in sql
        def fetchall(self):
            return [(KEY,)]
    @contextmanager
    def cursor():
        yield Cursor()
    @contextmanager
    def connect():
        yield type("Connection", (), {"cursor": staticmethod(cursor)})()
    actual, = sources._retained_litter_followup_candidates(NOW, rows, connect=connect)
    assert actual["dedupe_key"] == KEY
    assert actual["specialist"] == "HERDMASTER"
    assert bool(actual["unknowns"]) is expected_unknown
    assert "terminal_state" not in actual
    assert actual["next_reassessment_at"] == "2026-09-14T11:03:00+00:00"
    if not expected_unknown:
        assert "8 active piglets" in actual["summary"] and "2026-09-01" in actual["summary"]


def test_saved_litter_followup_is_in_the_same_batched_owner_refresh():
    expected = {"case_id": CASE_ID, "dedupe_key": KEY, "specialist": "HERDMASTER"}
    calls = []

    def _herdmaster(now):
        calls.append(now)
        return [expected]

    snapshot = sources.collect_manager_refresh_snapshot(now=NOW,
        cases=[expected], collectors=(_herdmaster,))
    assert snapshot == {(KEY, "HERDMASTER"): expected}
    assert calls == [NOW]
