"""Real shared services and canonical PostgreSQL, with synthetic farm identities."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

import psycopg
import pytest

from modules.pig_weights import pig_weights_service as service
from modules.pig_weights import farm_supabase_write_service as writer
from tests.weaning_test_support import database_url, seed, state, payload


def preview(j, p):
    result, code = service.process_litter_weaning_day(j['litter'], p)
    assert code == 200, result
    return result


def confirmation(p, result):
    return {**p, 'dry_run': False, 'confirmed': True, 'confirmation_binding': result['confirmation_binding']}


def test_basic_commit_and_replay_preserve_unknowns_sow_herd_and_terminal_history():
    j = seed(); p = payload(); before = state(j)
    proposed = preview(j, p)
    assert state(j) == before
    result, code = service.process_litter_weaning_day(j['litter'], confirmation(p, proposed))
    assert code == 200, result
    after = state(j)
    assert after['receipts'] == 1 and after['litter'][1:4] == (date(2026,9,10), 2, 'Weaned')
    assert after['sow'] == before['sow'] and after['active_herd'] == before['active_herd']
    assert after['pigs'][2:] == before['pigs'][2:]
    assert all(row[5:8] == (None, None, None) for row in after['pigs'][:2])
    again, code = service.process_litter_weaning_day(j['litter'], confirmation(p, proposed))
    assert code == 200 and again['replay_withheld'] and state(j) == after


@pytest.mark.parametrize('change', [
    {'wean_date': '2099-01-01'}, {'wean_date': '2026-01-01'}, {'wean_date': ''},
    {'wean_date':'20260910'}, {'wean_date':'2026-09-10','action_date':'2026-09-09'},
    {'total_count': 1}, {'male_count': 1}, {'male_count': 2, 'female_count': 1},
])
def test_invalid_date_and_reported_counts_do_not_write(change):
    j = seed(); before = state(j)
    result, code = service.process_litter_weaning_day(j['litter'], payload(**change))
    assert code in (400,409), result
    assert state(j) == before


def test_drift_partial_cohort_and_cross_actor_are_rejected():
    j = seed(); p = payload(); proposed = preview(j, p)
    packet = copy.deepcopy(proposed['confirmation_binding']['packet'])
    packet['piglets'].pop()
    with pytest.raises(ValueError, match='exact_current_weaning_cohort'):
        writer.apply_litter_weaning_day_packet(packet)
    tampered = confirmation(p, proposed); tampered['changed_by'] = 'another-manager'
    assert service.process_litter_weaning_day(j['litter'], tampered)[1] == 409
    with psycopg.connect(database_url()) as db:
        db.execute("update public.pigs set status='Sold',on_farm=false where pig_id=%s", (j['pigs'][1],))
    before = state(j)
    result, code = service.process_litter_weaning_day(j['litter'], confirmation(p, proposed))
    assert code == 409 and result['errors'] == ['weaning_preview_evidence_changed']
    assert state(j) == before


def test_real_transaction_rolls_back_after_first_pig_update():
    j = seed(); p = payload(assignments=[{'pig_id': j['pigs'][1], 'tag_number': j['sow']}])
    proposed = preview(j, p); before = state(j)
    result, code = service.process_litter_weaning_day(j['litter'], confirmation(p, proposed))
    assert code == 409 and result['errors'] == ['duplicate_tag_number']
    assert state(j) == before


def test_lost_commit_response_and_concurrent_confirmation_recover_one_receipt():
    j = seed(); p = payload(); proposed = preview(j, p); confirmed = confirmation(p, proposed)
    original = writer.apply_litter_weaning_day_packet
    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError('SIMULATED lost response after real commit')
    with patch.object(writer, 'apply_litter_weaning_day_packet', side_effect=lose_response):
        result, code = service.process_litter_weaning_day(j['litter'], confirmed)
    assert code == 200 and result['replay_withheld'], result
    j = seed(); p = payload(); proposed = preview(j, p); confirmed = confirmation(p, proposed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.process_litter_weaning_day(j['litter'], confirmed), range(2)))
    assert all(code == 200 for _, code in results), results
    assert sum(not result['replay_withheld'] for result, _ in results) == 1
    assert state(j)['receipts'] == 1


@pytest.mark.parametrize('status', ['Dead', 'Sold'])
def test_off_farm_sow_and_later_piglet_exit_are_preserved_on_replay(status):
    j = seed()
    with psycopg.connect(database_url()) as db:
        db.execute('update public.pigs set status=%s,on_farm=false where pig_id=%s', (status,j['sow']))
    p = payload(); proposed = preview(j,p); before = state(j)
    result, code = service.process_litter_weaning_day(j['litter'], confirmation(p,proposed))
    assert code == 200 and result['sow_readback']['status'] == status
    assert state(j)['sow'] == before['sow']
    with psycopg.connect(database_url()) as db:
        db.execute("update public.pigs set status='Sold',on_farm=false,exit_date='2026-09-11' where pig_id=%s",(j['pigs'][0],))
    after = state(j)
    replay, code = service.process_litter_weaning_day(j['litter'], confirmation(p,proposed))
    assert code == 200 and replay['replay_withheld'] and state(j) == after
    assert replay['weaned_count'] == 2 and replay['active_herd_count'] == after['active_herd']


def test_supplied_optional_facts_commit_together_without_catalogue_dose_invention():
    j = seed(); product = 'PRODUCT-' + j['litter']; target = 'TARGET-' + j['pen']
    with psycopg.connect(database_url()) as db:
        db.execute('insert into public.pens(pen_id,pen_name) values(%s,%s)',(target,'Synthetic destination'))
        db.execute("""insert into public.farm_products(product_id,product_name,product_category,
            default_dose,dose_unit,default_withdrawal_days) values(%s,'Synthetic only','Dewormer','999','ml',3)""",(product,))
    p = payload(notes='Both eating.',male_count=1,female_count=1,target_pen_id=target,
        assignments=[{'pig_id':j['pigs'][0],'wean_weight_kg':7.2,'sex':'Male','tag_number':'TAG-'+j['pigs'][0],
            'earmarked':True,'observation':{'factual_note':'Eating well.','traits':['good_build']}}],
        medicine={'deworming_product_id':product,'dose':1.5,'route':'Oral','batch_lot_number':'SYNTHETIC-BATCH'})
    proposed = preview(j,p); before = state(j)
    result, code = service.process_litter_weaning_day(j['litter'], confirmation(p,proposed))
    assert code == 200, result
    with psycopg.connect(database_url()) as db:
        medical = db.execute('select dose,dose_unit,route,batch_lot_number from public.pig_medical_events where pig_id=any(%s)',(j['pigs'],)).fetchall()
        assert len(medical) == 2 and all(float(row[0]) == 1.5 and row[1:] == ('ml','Oral','SYNTHETIC-BATCH') for row in medical)
        assert db.execute('select count(*) from public.pig_weight_events where pig_id=any(%s)',(j['pigs'],)).fetchone()[0] == 1
        assert db.execute('select count(*) from public.pig_location_events where pig_id=any(%s)',(j['pigs'],)).fetchone()[0] == 2
        assert db.execute('select count(*) from public.pig_observation_events where pig_id=any(%s)',(j['pigs'],)).fetchone()[0] == 1
    after = state(j)
    assert after['pigs'][0][6:8] == ('Male',True) and after['pigs'][1][5:8] == (None,None,None)
    assert after['pigs'][2:] == before['pigs'][2:] and after['active_herd'] == before['active_herd']
    assert service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))[0]['replay_withheld']
    assert state(j) == after


@pytest.mark.parametrize('change', [
    {'medicine':{'dose':1}}, {'medicine':{'deworming_product_id':'unknown'}},
    {'assignments':[{'pig_id':'unknown','wean_weight_kg':7}]},
    {'unknown_fact':'must not disappear'}, {'total_count':True},
])
def test_partial_or_unsupported_supplied_facts_are_not_silently_dropped(change):
    j=seed(); before=state(j)
    assert service.process_litter_weaning_day(j['litter'],payload(**change))[1] in (400,409)
    assert state(j) == before


def test_added_member_and_canonical_readback_corruption_fail_closed():
    j=seed(); p=payload(); proposed=preview(j,p)
    with psycopg.connect(database_url()) as db:
        db.execute("update public.pigs set status='Active',on_farm=true where pig_id=%s",(j['pigs'][3],))
    before=state(j)
    assert service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))[1] == 409
    assert state(j) == before
    j=seed(); proposed=preview(j,p)
    assert service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))[1] == 200
    with psycopg.connect(database_url()) as db:
        db.execute('update public.pigs set wean_date=null where pig_id=%s',(j['pigs'][0],))
    before=state(j)
    result, code = service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))
    assert code == 503 and result['operation_committed'] and not result['success'] and state(j) == before


@pytest.mark.parametrize('mutation', ['sow', 'product', 'pen'])
def test_preview_locks_sow_treatment_and_destination_evidence(mutation):
    j=seed(); product='PRODUCT-'+j['litter']; target='TARGET-'+j['pen']
    with psycopg.connect(database_url()) as db:
        db.execute('insert into public.pens(pen_id,pen_name) values(%s,%s)',(target,'Synthetic destination'))
        db.execute("insert into public.farm_products(product_id,product_name,dose_unit) values(%s,'Synthetic','ml')",(product,))
    p=payload(target_pen_id=target,medicine={'deworming_product_id':product,'dose':1,'route':'Oral','batch_lot_number':'TEST'})
    proposed=preview(j,p)
    with psycopg.connect(database_url()) as db:
        if mutation == 'sow':
            db.execute("update public.pigs set status='Sold',on_farm=false where pig_id=%s",(j['sow'],))
        elif mutation == 'product':
            db.execute('update public.farm_products set is_active=false where product_id=%s',(product,))
        else:
            db.execute('update public.pens set is_active=false where pen_id=%s',(target,))
    before=state(j)
    result,code=service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))
    assert code == 409 and state(j) == before, result


def test_protected_constraint_migration_replays_and_rejects_relaxed_structure():
    from pathlib import Path
    sql=Path('supabase/migrations/202609110001_allow_herdmaster_weaning_protected_claims.sql').read_text()
    with psycopg.connect(database_url()) as db:
        db.execute(sql); db.execute(sql)
        original=db.execute("select pg_get_constraintdef(oid) from pg_constraint where conname='oom_protected_action_claims_action_kind_check'").fetchone()[0]
        # The outer transaction always restores the real disposable schema.
        try:
            with db.transaction():
                db.execute('alter table app_private.oom_protected_action_claims drop constraint oom_protected_action_claims_action_kind_check')
                db.execute('alter table app_private.oom_protected_action_claims add constraint oom_protected_action_claims_action_kind_check '+original[:-1]+' OR true)')
                db.execute(sql)
        except psycopg.errors.RaiseException as exc:
            assert 'mismatch' in str(exc)
        else:
            raise AssertionError('Relaxed action-kind structure must not be accepted')
        assert db.execute("select pg_get_constraintdef(oid) from pg_constraint where conname='oom_protected_action_claims_action_kind_check'").fetchone()[0] == original


def test_effective_litter_supersession_invalidates_old_weaning_preview():
    import json
    j=seed(); kept=seed(); boar='BOAR-'+j['litter']; mating='MAT-'+j['litter']; op='SUPER-'+j['litter']
    with psycopg.connect(database_url()) as db:
        db.execute("insert into public.pigs(pig_id,status,on_farm,sex) values(%s,'Active',true,'Male')",(boar,))
        db.execute('update public.litters set sow_pig_id=%s,boar_pig_id=%s where litter_id=any(%s)',(j['sow'],boar,[j['litter'],kept['litter']]))
        db.execute('update public.pigs set mother_pig_id=%s where litter_id=%s',(j['sow'],kept['litter']))
        db.execute("insert into public.mating_events(mating_id,sow_pig_id,boar_pig_id,mating_date,related_litter_id) values(%s,%s,%s,'2026-03-20',%s)",(mating,j['sow'],boar,kept['litter']))
    p=payload(); proposed=preview(j,p)
    # Fresh synthetic fixture on the real append-only supersession rail.
    # This qualifies weaning's canonical selection, not a live correction.
    with psycopg.connect(database_url()) as db:
        db.execute("insert into public.litter_correction_authorizations(authorization_id,operation_id,preview_sha256,owner_principal,decision_status,confirmed_at) values(%s,%s,%s,'SYNTHETIC-ONLY','confirmed',now())",(op,op,'a'*64))
        db.execute("""insert into public.litter_supersessions(operation_id,retained_litter_id,superseded_litter_id,authorization_id,
            mating_id,preview_sha256,reason,superseded_child_ids,retained_child_ids,reference_allowlist_sha256,skipped_audit_rows_sha256,input_sha256)
            values(%s,%s,%s,%s,%s,%s,'duplicate_creation_same_farrowing',%s::jsonb,%s::jsonb,%s,%s,%s)""",
            (op,kept['litter'],j['litter'],op,mating,'a'*64,json.dumps(j['pigs']),json.dumps(kept['pigs']),'b'*64,'c'*64,'d'*64))
        for pig in j['pigs']:
            db.execute("insert into public.litter_cohort_dispositions(operation_id,pig_id,source_litter_id,disposition) values(%s,%s,%s,'superseded_duplicate_representation')",(op,pig,j['litter']))
    before=state(j)
    assert service.process_litter_weaning_day(j['litter'],confirmation(p,proposed))[1] == 409
    assert service.process_litter_weaning_day(j['litter'],p)[1] == 409
    assert state(j) == before and state(kept)['receipts'] == 0
