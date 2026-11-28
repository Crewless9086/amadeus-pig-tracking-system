"""Full-body first-candidate inventory parity on an isolated real PostgreSQL schema."""
import json
from datetime import timedelta
import pytest
from modules.telemetry import rootline_irrigation_execution_store as es
from tests.test_rootline_camp_inventory_index import db, connection, NOW


def event(identity, action='mark_borehole_active', **fields):
    return {'execution_id': identity, 'action': action, 'state': 'Active', **fields}


def add(db, events):
    db.add([(f'{n:05}', NOW+timedelta(seconds=n), {'rootline_execution':body})
            for n,body in enumerate(events)])


def run(db, fast):
    calls=[]
    class Cursor:
        def __init__(self,c): self.c=c
        def __enter__(self): return self
        def __exit__(self,*a): self.c.close()
        def execute(self,q,params=None):
            calls.append(q); self.c.execute(db.query(q),params)
        def fetchall(self): return self.c.fetchall()
    class Conn:
        def __init__(self,c): self.c=c
        def cursor(self): return Cursor(self.c.cursor())
    with connection() as c:
        c.execute('set transaction read only')
        try:
            if fast: result=es._load('load_active_borehole',None,connection=Conn(c))
            else:
                with Conn(c).cursor() as cur:
                    result=es._active_borehole(es._borehole_state_rows(cur))
            return ('value',result),calls
        except Exception as exc: return ('error',type(exc).__name__),calls


def test_newest_unresolved_complete_body_and_no_cross_execution_transfer(db):
    add(db,[event('old'),event('new',details={'full':'x'*8192}),
            event('new','claim_borehole_off_attempt',attempt=1)])
    expected,_=run(db,False); actual,calls=run(db,True)
    assert actual==expected and actual[1]['execution_id']=='new'
    assert len(calls)==1 and actual[1]['details']['full']=='x'*8192
    with connection() as c:
        selected=c.execute(db.query(es._BOREHOLE_CANDIDATE_SQL),
            (es.EVENT_SOURCE,sorted(es._BOREHOLE_STATE_ACTIONS))).fetchall()
    assert len(selected)==2 and all(row[1]['execution_id']=='new' for row in selected)


def completion(identity):
    value=event(identity,'record_borehole_completed',shutdown_verified=True,
        operational_proof='provider_app_on_to_off',
        canonical_completion_evidence={'execution_id':identity,'evidence_id':'canonical','final_state':'OFF'},
        provider_final_off_evidence={'execution_id':identity,'evidence_id':'provider','state':'OFF','authoritative':True},
        provider_start_evidence={'state':'ON','authoritative':True})
    assert es._verified_borehole_completion(value)
    return value


def test_closed_newest_falls_back_to_older_unresolved(db):
    add(db,[event('old'),event('new'),completion('new')])
    original,_=run(db,False); candidate,calls=run(db,True)
    assert candidate==original and candidate[1]['execution_id']=='old'
    assert len(calls)==2


@pytest.mark.parametrize('body',[None,[],False,2,'bad',
    json.dumps(event('legacy')),{'action':[]},{'action':None},
    event(None),event(3),{'action':'mark_borehole_active','state':'Active'}])
def test_malformed_and_legacy_preserve_original_result_or_error(db,body):
    add(db,[event('old'),body])
    assert run(db,True)[0]==run(db,False)[0]
    assert len(run(db,True)[1])==2


def test_empty_and_all_closed_use_complete_fallback(db):
    assert run(db,True)[0]==('value',None)
    add(db,[event('closed'),completion('closed')])
    value,calls=run(db,True)
    assert value==run(db,False)[0]==('value',None) and len(calls)==2


def test_tie_order_and_fresh_insert_are_preserved(db):
    db.add([('a',NOW,{'rootline_execution':event('first')}),
            ('z',NOW,{'rootline_execution':event('second')})])
    assert run(db,True)[0]==run(db,False)[0]
    assert run(db,True)[0][1]['execution_id']=='first'
    db.add([('fresh',NOW+timedelta(seconds=1),{'rootline_execution':event('fresh')})])
    assert run(db,True)[0]==run(db,False)[0]
    assert run(db,True)[0][1]['execution_id']=='fresh'
@pytest.mark.parametrize('identity',['', 'continuous'])
def test_continuous_stop_barrier_is_preserved(db,identity):
    from tests.test_rootline_continuous_borehole import eligibility
    active={**eligibility(), **event(identity)}
    add(db,[event('older'),active,
        event(identity,'claim_borehole_off_attempt',attempt=1,stop_reason='owner_stop')])
    expected,_=run(db,False); result,calls=run(db,True)
    assert result==expected and len(calls)==1
    assert result[1]['stop_requested'] is True and result[1]['stop_reason']=='owner_stop'


def test_older_unrelated_malformed_action_still_fails(db):
    add(db,[{'execution_id':'bad','action':[]},event('new')])
    assert run(db,True)[0]==run(db,False)[0]==('error','RootlineExecutionStoreUnavailable')
    assert len(run(db,True)[1])==2


def test_valid_no_send_terminal_falls_back_to_older_duty(db):
    identity='not-sent'
    claim=event(identity,'claim_borehole_before_on',provider_capacity_permit={'permit':'test'},
        device_id='1002851416',channel=1)
    claim['event_id']=es._event_id(claim['action'],claim)
    outcome=event(identity,'record_borehole_on_outcome',on_outcome={
        'provider_command_attempted':False,'accepted_unambiguous':False})
    outcome['event_id']=es._event_id(outcome['action'],outcome)
    terminal=event(identity,'record_execution_not_dispatched',
        terminal_contract='rootline_proven_no_send.v1',not_dispatched_verified=True,
        claim_event_id=claim['event_id'],claim_sha256=es._event_digest(claim),
        outcome_event_id=outcome['event_id'],outcome_sha256=es._event_digest(outcome),
        read_started_at=NOW.isoformat(),retired_at=NOW.isoformat(),
        shutdown_evidence={'authoritative':True,'state':'OFF','device_id':'1002851416',
            'channel':1,'evidence_id':'a'*64,'retrieved_at':NOW.isoformat()})
    terminal['event_id']=es._event_id(terminal['action'],terminal)
    assert es._verified_not_dispatched(terminal,[claim,outcome,terminal])
    add(db,[event('old'),claim,outcome,terminal])
    assert run(db,True)[0]==run(db,False)[0]
    assert run(db,True)[0][1]['execution_id']=='old'


def test_wide_history_transfer_and_plan_measurement(db,tmp_path):
    import hashlib,time
    ballast=''.join(hashlib.sha256(str(n).encode()).hexdigest() for n in range(128))
    add(db,[event('old-'+str(n),details=ballast+str(n)) for n in range(1012)]
        +[event('current',details=ballast)])
    with connection() as c:
        c.execute('set transaction read only')
        start=time.perf_counter()
        with c.cursor() as cur:
            class Wrapper:
                def execute(self,q,p):cur.execute(db.query(q),p)
                def fetchall(self):return cur.fetchall()
            full=es._borehole_state_rows(Wrapper())
        old_seconds=time.perf_counter()-start
        start=time.perf_counter()
        narrow=c.execute(db.query(es._BOREHOLE_CANDIDATE_SQL),
            (es.EVENT_SOURCE,sorted(es._BOREHOLE_STATE_ACTIONS))).fetchall()
        new_seconds=time.perf_counter()-start
        plan=c.execute('explain (analyze true,buffers true,timing false,format json) '+
            db.query(es._BOREHOLE_CANDIDATE_SQL),
            (es.EVENT_SOURCE,sorted(es._BOREHOLE_STATE_ACTIONS))).fetchone()[0]
    selected=[row[1] for row in narrow]
    assert es._active_borehole(full)==es._active_borehole(selected)
    full_bytes=len(json.dumps(full).encode()); narrow_bytes=len(json.dumps(selected).encode())
    assert len(full)==1013 and len(selected)==1 and narrow_bytes < full_bytes/100
    (tmp_path/'transfer-measurement.json').write_text(json.dumps({
        'classification':'synthetic loopback, not live performance',
        'full_rows':len(full),'selected_rows':len(selected),'full_json_bytes':full_bytes,
        'selected_json_bytes':narrow_bytes,'full_client_seconds':old_seconds,
        'selected_client_seconds':new_seconds,'candidate_explain':plan},indent=2))