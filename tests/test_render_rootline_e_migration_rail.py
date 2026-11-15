"""Qualify the exact A-to-E history upgrade in the disposable migration database."""
import hashlib
import json
from unittest.mock import patch
import pytest
from scripts import run_render_production_migrations as rail
from tests import test_render_rootline_a_migration_rail as a
from tests.test_render_rootline_a_migration_rail import predecessor, purpose_predecessor
from tests import test_render_production_migration_rail as legacy

E_ITEM = next(item for item in rail.ALLOWLIST if item.migration_id == rail.ROOTLINE_E_MIGRATION_ID)
E_ALLOWLIST = rail.ALLOWLIST


def test_exact_e_append_preserves_a_prefix_and_digest():
    assert len(E_ALLOWLIST) == 10
    assert E_ALLOWLIST[:-1] == a.A_ALLOWLIST
    assert E_ITEM.sha256 == "69b73b82009a3a769d02920f75c9d43d04de8cb7d372551442f86abf0a4ff7dd"
    assert hashlib.sha256(rail._load_sql(E_ITEM).encode()).hexdigest() == E_ITEM.sha256
    assert E_ITEM.migration_id not in rail.BASELINE_ELIGIBLE_IDS
    assert E_ITEM.migration_id not in rail.LEGACY_ADOPTION_BASELINE_IDS
    assert E_ITEM.migration_id not in rail.LEGACY_ADOPTION_RECEIPT_IDS


@pytest.fixture
def a_applied(predecessor):
    with patch.object(rail,"ALLOWLIST",a.A_ALLOWLIST):
        rail.run(legacy.DATABASE_URL,legacy.ENV)
    with a._connect() as db:
        db.execute("insert into public.irrigation_zones(zone_id,source_id,zone_name,zone_type) values('E12345','irrigation-controller-main','Synthetic E','unknown')")
        assert rail._verify_migration_precondition(db,E_ITEM,already_applied=False)=="predecessor"
    return a._state()


def test_actual_nine_to_ten_upgrade_and_replay_preserve_a_and_history(a_applied):
    first=rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert [r['outcome'] for r in first['migrations']]==['already_applied']*9+['applied']
    after=a._state()
    assert after[1]==a_applied[1]
    assert after[2][:-1]==a_applied[2]
    assert after[3][:-1]==a_applied[3]
    second=rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert [r['outcome'] for r in second['migrations']]==['already_applied']*10
    assert second['migrations'][8]['receipt_id']==first['migrations'][8]['receipt_id']
    assert second['migrations'][8]['readback']['verified_e_successor_receipt_id']==first['migrations'][9]['receipt_id']
    assert a._state()==after
    with a._connect() as db:
        db.execute('set local role service_role')
        details=json.dumps({'contract_version':'rootline_irrigation_outcome_v1','event_sha256':'e'*64,'execution_id':'SYNTHETIC-E'})
        statement="select public.rootline_append_typed_irrigation_event('SYNTHETIC-E',now(),'PLANNED','E12345',120,null,%s::jsonb)"
        assert db.execute(statement,(details,)).fetchone()[0]
        assert not db.execute(statement,(details,)).fetchone()[0]
    with a._connect() as db:
        for role in ('anon','authenticated'):
            assert not db.execute("select has_function_privilege(%s,%s,'execute')",(role,a.FUNCTION)).fetchone()[0]
        import psycopg
        with pytest.raises(psycopg.Error,match='append-only'):
            with db.transaction():db.execute("delete from public.irrigation_events where irrigation_event_id='SYNTHETIC-E'")


@pytest.mark.parametrize('attack',[
    "grant execute on function "+a.FUNCTION+" to authenticated",
    "drop index public.irrigation_events_rootline_abc_zone_cutoff_idx",
    "create index irrigation_events_rootline_abce_zone_cutoff_idx on public.irrigation_events(zone_id)",
    "insert into app_private.migration_log(migration_id,description) values('20261115090517_extend_rootline_e_irrigation_history','fabricated')",
])
def test_e_predecessor_tamper_refuses_without_side_effects(a_applied,attack):
    with a._connect() as db:db.execute(attack)
    before=a._state()
    with pytest.raises(RuntimeError):rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert a._state()==before


def test_e_target_with_log_but_without_receipt_cannot_upgrade_a_claim(a_applied):
    with a._connect() as db:db.execute(rail._load_sql(E_ITEM))
    before=a._state()
    with a._connect() as db:
        with pytest.raises(RuntimeError,match='migration_rootline_function_definition_mismatch'):
            rail._verify_migration_readback(db,a.A_ITEM)
    with pytest.raises(RuntimeError):rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert a._state()==before


def test_failed_e_postcondition_rolls_back_entire_upgrade(a_applied):
    original=rail._verify_migration_readback
    def fail_e(db,item):
        result=original(db,item)
        if item.migration_id==E_ITEM.migration_id:raise RuntimeError('synthetic E postcondition failure')
        return result
    with patch.object(rail,'_verify_migration_readback',side_effect=fail_e):
        with pytest.raises(RuntimeError,match='migration_failed_and_rolled_back:'+E_ITEM.migration_id):
            rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert a._state()==a_applied


@pytest.mark.parametrize('attack',['ordinal','checksum','anchor_missing'])
def test_a_replay_requires_exact_anchored_e_receipt(a_applied,attack):
    rail.run(legacy.DATABASE_URL,legacy.ENV)
    with a._connect() as db:
        if attack=='anchor_missing':
            table='app_private.production_migration_receipt_identity_anchors'
            trigger='trg_guard_production_migration_receipt_identity_anchors'
            db.execute('alter table '+table+' disable trigger '+trigger)
            db.execute('delete from '+table+' where receipt_id=(select receipt_id from app_private.production_migration_receipts where migration_id=%s)',(E_ITEM.migration_id,))
        else:
            table='app_private.production_migration_receipts';trigger='trg_guard_production_migration_receipts'
            db.execute('alter table '+table+' disable trigger '+trigger)
            assignment="ordinal=9" if attack=='ordinal' else "migration_sha256=repeat('0',64)"
            db.execute('update '+table+' set '+assignment+' where migration_id=%s',(E_ITEM.migration_id,))
        db.execute('alter table '+table+' enable trigger '+trigger)
    before=a._state()
    with a._connect() as db:
        with pytest.raises(RuntimeError):rail._verify_migration_readback(db,a.A_ITEM)
    with pytest.raises(RuntimeError):rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert a._state()==before


def test_actual_purpose_eight_to_a_nine_to_e_ten_preserves_custody(purpose_predecessor, monkeypatch):
    import psycopg
    before = purpose_predecessor["state"]
    execute = psycopg.Connection.execute
    purpose_sql = rail._load_sql(rail.PURPOSE_MIGRATION)
    def forbid_reexecution(db, query, *args, **kwargs):
        assert query != purpose_sql
        return execute(db, query, *args, **kwargs)
    monkeypatch.setattr(psycopg.Connection, "execute", forbid_reexecution)
    with patch.object(rail, "ALLOWLIST", a.A_ALLOWLIST):
        first = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert first["prior_catalog_checkpoint"]["recorded_purpose_transition"]["original_checkpoint_preserved"]
    assert first["migrations"][-1]["outcome"] == "applied"
    nine = a._purpose_state()
    second = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert second["migrations"][-1]["outcome"] == "applied"
    assert second["migrations"][8]["receipt_id"] == first["migrations"][8]["receipt_id"]
    ten = a._purpose_state()
    assert ten[0][1] == before[0][1]
    assert ten[0][2][:-2] == before[0][2]
    assert ten[0][3][:-2] == before[0][3]
    assert ten[1] == before[1]
    assert all(row in ten[2] for row in before[2]) and len(ten[2]) == len(before[2])+2
    assert ten[0][3][:-1] == nine[0][3]
    replay = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert replay["migrations"][8]["readback"]["verified_e_successor_receipt_id"] == second["migrations"][9]["receipt_id"]
    assert all(row["outcome"] in {"already_applied", "baseline_verified"} for row in replay["migrations"])
    assert a._purpose_state() == ten


@pytest.mark.parametrize("fail_e", [False, True])
def test_direct_purpose_eight_to_ten_is_atomic(purpose_predecessor, monkeypatch, fail_e):
    before = purpose_predecessor["state"]
    readback = rail._verify_migration_readback
    def verify(db, item):
        value = readback(db, item)
        if fail_e and item == E_ITEM:
            raise RuntimeError("synthetic E failure after A upgrade")
        return value
    monkeypatch.setattr(rail, "_verify_migration_readback", verify)
    if fail_e:
        with pytest.raises(RuntimeError, match="migration_failed_and_rolled_back:"+E_ITEM.migration_id):
            rail.run(legacy.DATABASE_URL, legacy.ENV)
        assert a._purpose_state() == before
        return
    result = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert [row["outcome"] for row in result["migrations"]][-2:] == ["applied", "applied"]
    assert result["prior_catalog_checkpoint"]["recorded_purpose_transition"]["original_checkpoint_preserved"]
    after = a._purpose_state()
    assert after[0][1] == before[0][1]
    assert after[0][2][:-2] == before[0][2]
    assert after[0][3][:-1] == before[0][3]
    assert after[1] == before[1]
    assert all(row in after[2] for row in before[2]) and len(after[2]) == len(before[2])+2
    replay = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert replay["migrations"][8]["readback"]["verified_e_successor_receipt_id"] == result["migrations"][9]["receipt_id"]
    assert a._purpose_state() == after
