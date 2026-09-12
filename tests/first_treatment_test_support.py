"""Fresh synthetic fixtures for terminal-invoked first-treatment qualification."""
from datetime import datetime, timedelta
import os
import uuid
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import psycopg
import pytest


def database_url():
    url = os.environ.get('CHARLIE_DISPOSABLE_POSTGRES_URL', '')
    if not url:
        pytest.skip('Separate disposable first-treatment PostgreSQL is required')
    parsed = urlparse(url)
    assert parsed.hostname in {'127.0.0.1', 'localhost'} and 'first_treatment_test' in parsed.path
    return url


def seed():
    suffix = uuid.uuid4().hex[:10].upper()
    today = datetime.now(ZoneInfo('Africa/Johannesburg')).date()
    j = {'litter': 'LIT-FTTEST-' + suffix, 'sow': 'SOW-FTTEST-' + suffix,
        'name': 'Synthetic treatment sow ' + suffix, 'product': 'PROD-FTTEST-' + suffix,
        'product_name': 'Synthetic product ' + suffix,
        'date': (today - timedelta(days=1)).isoformat(), 'birth': (today - timedelta(days=22)).isoformat(),
        'pigs': ['PIG-FTTEST-' + suffix + '-' + str(i) for i in range(4)]}
    with psycopg.connect(database_url()) as db:
        db.execute("""insert into public.pigs(pig_id,pig_name,tag_number,status,on_farm,animal_type,sex,date_of_birth)
            values(%s,%s,%s,'Active',true,'Sow','Female','2024-01-01')""", (j['sow'],j['name'],j['sow']))
        db.execute("""insert into public.litters(litter_id,sow_pig_id,sow_tag_number,farrowing_date,
            total_born,born_alive,wean_date,litter_status,litter_notes) values(%s,%s,%s,%s,4,4,%s,'Active','Preserved synthetic birth history')""",
            (j['litter'],j['sow'],j['sow'],j['birth'],today + timedelta(days=14)))
        for i,pig in enumerate(j['pigs']):
            status,on_farm = ('Active',True) if i < 2 else ('Dead',False) if i == 2 else ('Sold',False)
            db.execute("""insert into public.pigs(pig_id,status,on_farm,animal_type,litter_id,mother_pig_id,date_of_birth,notes)
                values(%s,%s,%s,'Piglet',%s,%s,%s,'Preserved synthetic piglet history')""", (pig,status,on_farm,j['litter'],j['sow'],j['birth']))
        db.execute("""insert into public.farm_products(product_id,product_name,product_category,default_dose,dose_unit,default_withdrawal_days,is_active)
            values(%s,%s,'Antiparasitic',2,'ml',0,true)""", (j['product'],j['product_name']))
    return j


def facts(j, **extra):
    return {'sow_ref':j['sow'], 'action_date':j['date'], 'antiparasitic_product_ref':j['product'],
        'dose':'1 ml', 'route':'injection', 'batch_lot_number':'SYNTHETIC-LOT', 'notes':'Synthetic actual report',
        'male_count':1, 'female_count':1, 'total_count':2, 'earmarked':True, **extra}


def payload(j, **extra):
    return {'action_date_value':j['date'], 'changed_by':'synthetic-treatment-manager',
        'antiparasitic_product_id':j['product'], 'dose':'1 ml', 'route':'injection',
        'batch_lot_number':'SYNTHETIC-LOT', 'notes':'Synthetic actual report',
        'male_count':1, 'female_count':1, 'total_count':2, 'earmarked':True, 'dry_run':True, **extra}


def state(j):
    with psycopg.connect(database_url()) as db:
        return {
            'litter': db.execute('select * from public.litters where litter_id=%s',(j['litter'],)).fetchone(),
            'pigs': db.execute('select * from public.pigs where litter_id=%s order by pig_id',(j['litter'],)).fetchall(),
            'sow': db.execute('select * from public.pigs where pig_id=%s',(j['sow'],)).fetchone(),
            'medical': db.execute('select medical_event_id,pig_id,treatment_date,dose,dose_unit,route,given_by from public.pig_medical_events where pig_id=any(%s) order by pig_id',(j['pigs'],)).fetchall(),
            'receipts': db.execute("select event_id,payload_json from public.operational_events where event_type='litter.first_treatment_recorded' and aggregate_id=%s",(j['litter'],)).fetchall(),
        }


def cleanup(j):
    with psycopg.connect(database_url()) as db:
        db.execute("delete from public.operational_events where aggregate_id=%s and event_type='litter.first_treatment_recorded'", (j['litter'],))
        db.execute('delete from public.pig_medical_events where pig_id=any(%s)', (j['pigs'],))
        db.execute('delete from public.pigs where pig_id=any(%s)', (j['pigs'],))
        db.execute('delete from public.litters where litter_id=%s', (j['litter'],))
        db.execute('delete from public.pigs where pig_id=%s', (j['sow'],))
        db.execute('delete from public.farm_products where product_id=%s', (j['product'],))


def login(client, actor, bot_token):
    """Simulated Telegram signature, actual login verification and session."""
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode
    fields = {'auth_date':str(int(time.time())),
        'user':json.dumps({'id':int(actor),'first_name':'Synthetic treatment manager'})}
    key = hmac.new(b'WebAppData',bot_token.encode(),hashlib.sha256).digest()
    fields['hash'] = hmac.new(key,'\n'.join(f'{key}={fields[key]}' for key in sorted(fields)).encode(),hashlib.sha256).hexdigest()
    return client.post('/owner/telegram/login',headers={'X-Farm-Login':'telegram'},json={'init_data':urlencode(fields)})
