"""Actual shared-service PostgreSQL proof for atomic treatment and recovery."""
import copy
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
import pytest

from modules.pig_weights import farm_supabase_write_service as writer, pig_weights_service as service
from tests.first_treatment_test_support import database_url, seed, cleanup, payload, state


@pytest.fixture
def litter():
    j = seed()
    yield j
    cleanup(j)


def confirmed(j, **extra):
    p = payload(j, **extra)
    preview, code = service.record_litter_newborn_health(j['litter'], **p)
    assert code == 200, preview
    return {**p, 'dry_run':False, 'confirmed':True, 'confirmation_binding':preview['confirmation_binding']}


def test_crash_after_commit_replay_is_noop_with_same_rows(litter,monkeypatch):
    j = litter
    p = confirmed(j)
    real = writer.apply_litter_first_treatment_packet
    def lost_response(*args,**kwargs):
        real(*args,**kwargs)
        raise ConnectionError('SIMULATED response lost after a real PostgreSQL commit')
    with monkeypatch.context() as patch:
        patch.setattr(writer,'apply_litter_first_treatment_packet',lost_response)
        first, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200 and first['replay_withheld'], first
    after = state(j)
    replay, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200 and replay['replay_withheld'] and replay['treatment_rows_created'] == 0
    assert state(j) == after and len(after['medical']) == 2 and len(after['receipts']) == 1


def test_concurrent_same_claim_commits_each_medical_effect_once(litter):
    j = litter
    p = confirmed(j)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.record_litter_newborn_health(j['litter'],**p),range(2)))
    assert all(code == 200 for _,code in results), results
    assert sorted(result['treatment_rows_created'] for result,_ in results) == [0,2]
    assert len(state(j)['medical']) == 2 and len(state(j)['receipts']) == 1


def test_different_actors_concurrently_cannot_treat_same_litter_twice(litter):
    j = litter
    inputs = [confirmed(j,changed_by=actor) for actor in ('synthetic-manager-a','synthetic-manager-b')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda p: service.record_litter_newborn_health(j['litter'],**p),inputs))
    assert sorted(code for _,code in results) == [200,409], results
    assert len(state(j)['medical']) == 2 and len(state(j)['receipts']) == 1


def test_real_failure_after_earmark_and_first_medical_insert_rolls_back(litter):
    j = litter
    p = confirmed(j)
    before = state(j)
    constraint = 'fttest_rollback_' + j['litter'].split('-')[-1].lower()
    with psycopg.connect(database_url()) as db:
        db.execute(sql.SQL('alter table public.pig_medical_events add constraint {} check(pig_id <> {}) not valid').format(
            sql.Identifier(constraint),sql.Literal(j['pigs'][1])))
    try:
        result, code = service.record_litter_newborn_health(j['litter'],**p)
        assert code == 503 and result['recovery_required'], result
        assert state(j) == before
    finally:
        with psycopg.connect(database_url()) as db:
            db.execute(sql.SQL('alter table public.pig_medical_events drop constraint {}').format(sql.Identifier(constraint)))
    result, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200 and result['treatment_rows_created'] == 2


@pytest.mark.parametrize('drift',['exit','new_member','product','birth_count','earmark'])
def test_membership_and_evidence_drift_require_new_preview(litter,drift):
    j = litter
    p = confirmed(j)
    with psycopg.connect(database_url()) as db:
        if drift == 'exit':
            db.execute("update public.pigs set status='Sold',on_farm=false where pig_id=%s",(j['pigs'][1],))
        elif drift == 'new_member':
            new_id = j['pigs'][0] + '-NEW'
            j['pigs'].append(new_id)
            db.execute("insert into public.pigs(pig_id,status,on_farm,animal_type,litter_id,mother_pig_id,date_of_birth) values(%s,'Active',true,'Piglet',%s,%s,%s)",(new_id,j['litter'],j['sow'],j['birth']))
        elif drift == 'product':
            db.execute('update public.farm_products set is_active=false where product_id=%s',(j['product'],))
        elif drift == 'birth_count':
            db.execute('update public.litters set born_alive=5,total_born=5 where litter_id=%s',(j['litter'],))
        elif drift == 'earmark':
            db.execute('update public.pigs set earmarked=true,earmark_date=%s where pig_id=%s',(j['date'],j['pigs'][0]))
    before = state(j)
    result, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 409 and not result['success'], result
    assert state(j) == before


def test_raw_incomplete_or_changed_packet_cannot_bypass_shared_validation(litter):
    j = litter
    p = confirmed(j)
    before = state(j)
    packet = copy.deepcopy(p['confirmation_binding']['packet'])
    packet['treatment_rows'].pop()
    with pytest.raises(ValueError):
        writer.apply_litter_first_treatment_packet(packet)
    assert state(j) == before
    result, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200
    after = state(j)
    packet = copy.deepcopy(p['confirmation_binding']['packet'])
    packet['operation_id'] += '-DIFFERENT'
    with pytest.raises(ValueError):
        writer.apply_litter_first_treatment_packet(packet)
    assert state(j) == after


def test_committed_receipt_recovery_preserves_later_exit_and_earmark_history(litter):
    j = litter
    with psycopg.connect(database_url()) as db:
        db.execute('update public.pigs set earmarked=true,earmark_date=%s where pig_id=%s',(j['birth'],j['pigs'][0]))
    p = confirmed(j)
    assert service.record_litter_newborn_health(j['litter'],**p)[1] == 200
    with psycopg.connect(database_url()) as db:
        db.execute("update public.pigs set status='Sold',on_farm=false where pig_id=%s",(j['pigs'][1],))
        assert db.execute('select earmark_date from public.pigs where pig_id=%s',(j['pigs'][0],)).fetchone()[0].isoformat() == j['birth']
    after = state(j)
    result, code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200 and result['replay_withheld'] and state(j) == after


def test_expired_binding_cannot_write_but_can_recover_its_committed_operation(litter):
    import time
    j = litter
    p = confirmed(j)
    expired = {**p, 'confirmation_binding':service._first_treatment_binding(
        p['confirmation_binding']['packet'], issued_at=int(time.time())-service.WEANING_PREVIEW_TTL_SECONDS-1)}
    before = state(j)
    result,code = service.record_litter_newborn_health(j['litter'],**expired)
    assert code == 409 and result['status'] == 'first_treatment_preview_expired'
    assert state(j) == before
    assert service.record_litter_newborn_health(j['litter'],**p)[1] == 200
    after = state(j)
    result,code = service.record_litter_newborn_health(j['litter'],**expired)
    assert code == 200 and result['replay_withheld'] and state(j) == after


def test_application_readback_loss_after_commit_retains_recovery(litter,monkeypatch):
    j = litter
    p = confirmed(j)
    with monkeypatch.context() as patch:
        patch.setattr(service.farm_supabase_read_service,'get_litter_detail',
            lambda *args,**kwargs: (_ for _ in ()).throw(ConnectionError('SIMULATED readback outage')))
        result,code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 503 and result['operation_committed'] is True and result['recovery_required']
    after = state(j)
    assert len(after['medical']) == 2 and len(after['receipts']) == 1
    result,code = service.record_litter_newborn_health(j['litter'],**p)
    assert code == 200 and result['replay_withheld'] and state(j) == after
