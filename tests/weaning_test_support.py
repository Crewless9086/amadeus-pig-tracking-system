"""Fresh synthetic fixtures; terminal-invoked evidence, never owner acceptance."""
import os
import uuid
from urllib.parse import urlparse

import psycopg
import pytest


def database_url():
    url = os.environ.get('CHARLIE_DISPOSABLE_POSTGRES_URL', '')
    if not url:
        pytest.skip('Separate disposable weaning PostgreSQL is required')
    parsed = urlparse(url)
    assert parsed.hostname in {'127.0.0.1', 'localhost'} and 'weaning_test' in parsed.path
    return url


def seed():
    suffix = uuid.uuid4().hex[:10].upper()
    j = {'litter': 'LIT-WTEST-' + suffix, 'sow': 'SOW-WTEST-' + suffix,
         'name': 'Synthetic sow ' + suffix, 'pen': 'PEN-WTEST-' + suffix,
         'pigs': ['PIG-WTEST-' + suffix + '-' + str(i) for i in range(4)]}
    with psycopg.connect(database_url()) as db:
        db.execute('insert into public.pens(pen_id,pen_name) values(%s,%s)', (j['pen'], 'Synthetic weaning pen'))
        db.execute("""insert into public.pigs(pig_id,pig_name,tag_number,status,on_farm,
            animal_type,sex,purpose,date_of_birth,initial_pen_id,notes)
            values(%s,%s,%s,'Active',true,'Sow','Female','Breeding','2024-01-01',%s,'Preserved synthetic sow history')""",
            (j['sow'],j['name'],j['sow'],j['pen']))
        db.execute("""insert into public.litters(litter_id,sow_pig_id,sow_tag_number,
            farrowing_date,total_born,born_alive,wean_date,litter_status,litter_notes)
            values(%s,%s,%s,'2026-07-15',4,4,'2026-08-26','Active','Preserved synthetic birth history')""",
            (j['litter'],j['sow'],j['sow']))
        for i, pig in enumerate(j['pigs']):
            status, on_farm = ('Active', True) if i < 2 else ('Dead', False) if i == 2 else ('Sold', False)
            db.execute("""insert into public.pigs(pig_id,status,on_farm,animal_type,
                litter_id,mother_pig_id,initial_pen_id,date_of_birth,notes)
                values(%s,%s,%s,'Piglet',%s,%s,%s,'2026-07-15','Preserved synthetic piglet history')""",
                (pig,status,on_farm,j['litter'],j['sow'],j['pen']))
    return j


def state(j):
    with psycopg.connect(database_url()) as db:
        return {'litter': db.execute('select litter_id,wean_date,weaned_count,litter_status,litter_notes from public.litters where litter_id=%s',(j['litter'],)).fetchone(),
                'pigs': db.execute('select pig_id,status,on_farm,animal_type,wean_date,wean_weight_kg,sex,earmarked,exit_date,notes from public.pigs where litter_id=%s order by pig_id',(j['litter'],)).fetchall(),
                'sow': db.execute('select status,on_farm,animal_type,notes from public.pigs where pig_id=%s',(j['sow'],)).fetchone(),
                'active_herd': db.execute("select count(*) from public.current_canonical_pigs where status='Active' and on_farm").fetchone()[0],
                'receipts': db.execute("select count(*) from public.operational_events where event_type='litter.weaned' and aggregate_id=%s",(j['litter'],)).fetchone()[0]}


def payload(**extra):
    return {'dry_run': True, 'wean_date': '2026-09-10', 'changed_by': 'synthetic-manager', **extra}
