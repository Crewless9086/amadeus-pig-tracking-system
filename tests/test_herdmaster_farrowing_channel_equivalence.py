from datetime import date

import pytest

from modules.pig_weights import pig_weights_service as service
from modules.pig_weights.farm_supabase_write_service import create_governed_farrowing_litter


def cleaned():
    return {
        "mother_pig_id": "SOW-1", "father_pig_id": "", "mating_id": "",
        "farrowing_date": date(2026, 8, 22), "total_born": 9,
        "born_alive": 8, "stillborn_count": 0, "mummified_count": 1,
        "male_count": None, "female_count": None, "fostered_in_count": None,
        "fostered_out_count": None, "weaned_count": None, "wean_date": None,
        "average_wean_weight_kg": None, "notes": "", "current_pen_id": "PEN-1",
    }


def test_application_uses_same_governed_litter_transaction(monkeypatch):
    monkeypatch.setattr(service, "_try_supabase_read", lambda *args, **kwargs: [{"Pig_ID": "SOW-1"}])
    monkeypatch.setattr(service, "_build_pig_lookup", lambda *args, **kwargs: {"SOW-1": {}})
    monkeypatch.setattr(service.farm_supabase_write_service,
        "farm_supabase_writes_available", lambda: True)
    captured = {}
    def canonical(preview, *, actor_id):
        captured.update(preview)
        assert actor_id == "authenticated_application"
        return {"litter_id": "LIT-CANONICAL", "pig_ids": [f"PIG-{i}" for i in range(8)],
                "follow_up_case_id": "OOM-MANAGER-1"}
    monkeypatch.setattr(service.farm_supabase_write_service,
        "create_governed_farrowing_litter", canonical)
    result = service.save_new_litter(cleaned())
    assert result["litter_id"] == "LIT-CANONICAL"
    assert result["pig_rows_created"] == 8
    assert result["follow_up_case_id"] == "OOM-MANAGER-1"
    assert captured["counts"] == {"total_born": 9, "born_alive": 8,
        "stillborn": 0, "mummified": 1, "died_after_live_birth": 0}


def test_canonical_failure_never_falls_through_to_legacy_sheet_writer(monkeypatch):
    monkeypatch.setattr(service, "_try_supabase_read", lambda *args, **kwargs: [{"Pig_ID": "SOW-1"}])
    monkeypatch.setattr(service, "_build_pig_lookup", lambda *args, **kwargs: {"SOW-1": {}})
    monkeypatch.setattr(service.farm_supabase_write_service,
        "farm_supabase_writes_available", lambda: True)
    monkeypatch.setattr(service.farm_supabase_write_service,
        "create_governed_farrowing_litter", lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("canonical_conflict")))
    monkeypatch.setattr(service, "append_row", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy writer forbidden")))
    with pytest.raises(RuntimeError, match="canonical_conflict"):
        service.save_new_litter(cleaned())


class _SharedCanonicalDb:
    def __init__(self):
        self.litters = []
        self.lock_keys = []
        self.current = None
        self.rowcount = 0
    def connection(self, *_args): return _Connection(self)


class _Connection:
    def __init__(self, db): self.db = db
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return _Cursor(self.db)


class _Cursor:
    def __init__(self, db): self.db = db; self.rowcount = 0
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.rowcount = 0
        if "pg_advisory_xact_lock" in normalized:
            self.db.lock_keys.append(params[0]); self.db.current = None
        elif "from public.litters" in normalized and "for update" in normalized:
            self.db.current = list(self.db.litters)
        elif "from public.current_canonical_pigs pig" in normalized:
            self.db.current = ("Active", True, "Linda", "PEN-1", "Female", "Sow")
        elif "insert into public.litters" in normalized:
            self.db.litters.append((params[0], params[6], params[7], params[8], params[9],
                                    params[3], "Active", params[10]))
            self.rowcount = 1; self.db.current = None
        else:
            self.rowcount = 1; self.db.current = None
    def fetchall(self): return list(self.db.current or [])
    def fetchone(self): return self.db.current


def _preview(operation_id):
    return {"contract_version": "herdmaster_farrowing_litter_preview_v1",
        "operation_id": operation_id, "sow_pig_id": "SOW-1",
        "father_pig_id": None, "mating_id": None, "farrowing_date": "2026-08-22",
        "counts": {"total_born": 9, "born_alive": 8, "stillborn": 0,
                   "mummified": 1, "died_after_live_birth": 0}}


def test_two_channels_share_sow_date_lock_and_cannot_create_two_litters():
    db = _SharedCanonicalDb()
    first = create_governed_farrowing_litter(_preview("TELEGRAM-1"), actor_id="telegram",
                                             connect_factory=db.connection)
    assert first["success"] is True and first["follow_up_case_id"]
    with pytest.raises(ValueError, match="farrowing_litter_duplicate_or_idempotency_conflict"):
        create_governed_farrowing_litter(_preview("APPLICATION-2"), actor_id="application",
                                         connect_factory=db.connection)
    assert len(db.litters) == 1
    assert db.lock_keys == ["herdmaster-farrowing:SOW-1:2026-08-22"] * 2


def test_governed_correction_creates_superseding_identity_without_overwriting_old_counts():
    db = _SharedCanonicalDb()
    db.litters.append(("LIT-OLD", 8, 7, 0, 1, None, "Active", "Original evidence"))
    preview = _preview("CORRECTION-1")
    preview.update({"correction_of_litter_id": "LIT-OLD",
                    "correction_reason": "Owner corrected total and born-alive counts"})
    result = create_governed_farrowing_litter(preview, actor_id="owner_correction",
                                              connect_factory=db.connection)
    assert result["success"] is True
    assert result["correction_of_litter_id"] == "LIT-OLD"
    assert len(db.litters) == 2
    assert db.litters[0][1:5] == (8, 7, 0, 1)
    assert db.litters[1][1:5] == (9, 8, 0, 1)
