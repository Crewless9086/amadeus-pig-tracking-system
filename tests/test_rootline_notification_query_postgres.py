"""Exact SQL equivalence using session-local tables on an explicit disposable database."""
ORIGINAL = "select e.review_json->'rootline_execution',\n                        n.review_json->'rootline_execution', e.review_event_id\n                    from public.sam_live_stock_conversation_review_events e\n                    left join lateral (\n                        select r.review_json from public.sam_live_stock_conversation_review_events r\n                        where r.event_source=%s\n                          and r.review_json->'rootline_execution'->>'action'='record_notification_delivery'\n                          and r.review_json->'rootline_execution'->>'transition_event_id'=e.review_event_id\n                        order by (coalesce(r.review_json->'rootline_execution'->>'delivery_confirmed','false')='true') desc,\n                            r.created_at desc,r.review_event_id desc limit 1\n                    ) n on true\n                    where e.event_source=%s and e.created_at >= %s and e.created_at <= clock_timestamp()\n                      and e.review_json->'rootline_execution'->>'action' in\n                        ('mark_active','record_completed','mark_auxiliary_active',\n                         'record_auxiliary_completed','record_auxiliary_control_pulse_stopped',\n                         'mark_borehole_active','record_borehole_completed','record_eskom_completed')\n                      and coalesce(n.review_json->'rootline_execution'->>'delivery_confirmed','false') != 'true'\n                      and coalesce(n.review_json->'rootline_execution'->>'delivery_ambiguous','false') != 'true'\n                      and coalesce(n.review_json->'rootline_execution'->>'notification_projection_rejected','false') != 'true'\n                    order by e.created_at,e.review_event_id limit 8"
from datetime import datetime,timedelta,timezone
import os
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse
import psycopg
from psycopg.types.json import Jsonb
import pytest
from modules.telemetry import rootline_irrigation_execution_store as store
URL=os.getenv('ROOTLINE_NOTIFICATION_QUERY_TEST_URL','')
pytestmark=pytest.mark.skipif(not URL or os.getenv('ROOTLINE_NOTIFICATION_QUERY_TEST_LEASE')!='notice46',reason='Explicit isolated notice46 database lease required')
TABLE='public.sam_live_stock_conversation_review_events'
TEMP='pg_temp.notice46_events'
SINCE=datetime(2020,1,1,tzinfo=timezone.utc)

def _server_identity_allowed(parsed_url, identity, *, github_actions):
    database, address, port = identity
    if database != parsed_url.path[1:] or port != parsed_url.port:
        return False
    if address == '127.0.0.1':
        return True
    if (github_actions != 'true' or parsed_url.hostname != '127.0.0.1'
            or parsed_url.username != 'postgres'
            or (parsed_url.port, parsed_url.path) != (5432, '/rootline_notification_query_test')):
        return False
    try:
        return ip_address(address) in ip_network('172.16.0.0/12')
    except ValueError:
        return False

@pytest.fixture
def db():
    p=urlparse(URL)
    assert p.scheme in {'postgres','postgresql'} and p.hostname=='127.0.0.1' and p.username=='postgres'
    assert (p.port,p.path) in {(55485,'/rootline_ha_command_mode_test'),(5432,'/rootline_notification_query_test')}
    assert not p.query and not p.fragment
    with psycopg.connect(URL,connect_timeout=5,options='-c statement_timeout=3000 -c lock_timeout=1000') as c:
        c.execute('set transaction isolation level repeatable read')
        assert _server_identity_allowed(p, c.execute('select current_database(),host(inet_server_addr()),inet_server_port()').fetchone(), github_actions=os.getenv('GITHUB_ACTIONS', ''))
        c.execute('create temporary table notice46_events(review_event_id text primary key,event_source text not null,created_at timestamptz not null,review_json jsonb not null) on commit drop')
        calls=[]
        class Cursor:
            def __enter__(self):self.inner=c.cursor();self.inner.__enter__();return self
            def __exit__(self,*a):return self.inner.__exit__(*a)
            def execute(self,q,args):
                assert TABLE in q and q.lstrip().lower().startswith(('select','with'))
                calls.append((q,args));return self.inner.execute(q.replace(TABLE,TEMP),args)
            def fetchone(self):return self.inner.fetchone()
            def fetchall(self):return self.inner.fetchall()
        class Read:
            def cursor(self):return Cursor()
        yield c,Read(),calls

def add(db,key,seconds=0,body=None,source=None):
    db[0].execute('insert into '+TEMP+' values(%s,%s,%s,%s)',(key,source or store.EVENT_SOURCE,SINCE+timedelta(seconds=seconds),Jsonb({'rootline_execution':body if body is not None else {'action':'mark_active'}})))

def epoch(db):
    key=store._event_id('claim_notification_recovery_epoch',{'execution_id':store._NOTIFICATION_EPOCH_ID})
    add(db,key,-100,{'since':SINCE.isoformat()})

def notice(db,key,target,seconds=100,**flags):
    add(db,key,seconds,{'action':'record_notification_delivery','transition_event_id':target,**flags})

def equal(db):
    old=db[0].execute(ORIGINAL.replace(TABLE,TEMP),(store.EVENT_SOURCE,store.EVENT_SOURCE,SINCE)).fetchall()
    before=len(db[2]);actual=store._load('load_notification_transitions',{},connection=db[1])
    assert len(db[2])==before+2 and 'with notices as materialized' in db[2][-1][0].lower()
    expected=[{'transition':r[0],'notification':r[1] or {},'review_event_id':r[2]} for r in old]
    assert actual['transitions']==expected
    return expected

def test_missing_epoch_and_empty(db):
    assert store._load('load_notification_transitions',{},connection=db[1])=={'epoch':None,'transitions':[]}
    epoch(db);assert equal(db)==[]

@pytest.mark.parametrize('flag',['delivery_confirmed','delivery_ambiguous','notification_projection_rejected'])
@pytest.mark.parametrize('value,suppressed',[(True,True),('true',True),(False,False),(None,False),('True',False)])
def test_flags(db,flag,value,suppressed):
    epoch(db);add(db,'edge');notice(db,'notice','edge',**{flag:value})
    assert bool(equal(db)) is not suppressed

def test_confirmed_precedence_and_nonconfirmed_ties(db):
    epoch(db);add(db,'confirmed-edge');add(db,'pending-edge',1)
    notice(db,'old-confirmed','confirmed-edge',2,delivery_confirmed=True)
    notice(db,'new-unsent','confirmed-edge',3,delivery_definitely_not_sent=True)
    notice(db,'A','pending-edge',4,delivery_ambiguous=True)
    notice(db,'B','pending-edge',4,delivery_definitely_not_sent=True)
    rows=equal(db);assert [r['review_event_id'] for r in rows]==['pending-edge']
    assert rows[0]['notification']['delivery_definitely_not_sent'] is True
    notice(db,'C','pending-edge',4,notification_projection_rejected=True);assert equal(db)==[]
    notice(db,'D','pending-edge',5,delivery_ambiguous=True);assert equal(db)==[]

def test_source_epoch_future_null_action_and_chronological_limit(db):
    epoch(db);add(db,'pre',-.000001);add(db,'future',10**10);add(db,'wrong-source',source='other');add(db,'wrong-action',body={'action':'claim_before_on'})
    actions=['mark_active','record_completed','mark_auxiliary_active','record_auxiliary_completed','record_auxiliary_control_pulse_stopped','mark_borehole_active','record_borehole_completed','record_eskom_completed']
    for i in reversed(range(16)):add(db,f'edge-{i:02}',i//2,{'action':actions[i%8]})
    notice(db,'null-target',None,delivery_confirmed=True)
    add(db,'wrong-notice-source',body={'action':'record_notification_delivery','transition_event_id':'edge-02','delivery_confirmed':True},source='other')
    add(db,'wrong-notice-action',body={'action':'other','transition_event_id':'edge-02','delivery_confirmed':True})
    notice(db,'closed0','edge-00',delivery_confirmed=True);notice(db,'closed1','edge-01',delivery_ambiguous=True)
    assert [r['review_event_id'] for r in equal(db)]==[f'edge-{i:02}' for i in range(2,10)]


@pytest.mark.parametrize('url,identity,github,expected', [
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','172.18.0.2',5432),'true',True),
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('wrong_database','172.18.0.2',5432),'true',False),
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','172.18.0.2',55485),'true',False),
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','8.8.8.8',5432),'true',False),
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','10.0.0.2',5432),'true',False),
    ('postgresql://postgres@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','172.18.0.2',5432),'',False),
    ('postgresql://postgres@127.0.0.1:55485/rootline_ha_command_mode_test', ('rootline_ha_command_mode_test','172.18.0.2',55485),'true',False),
    ('postgresql://postgres@127.0.0.1:55485/rootline_ha_command_mode_test', ('rootline_ha_command_mode_test','127.0.0.1',55485),'',True),
    ('postgresql://postgres@172.18.0.2:5432/rootline_notification_query_test', ('rootline_notification_query_test','172.18.0.2',5432),'true',False),
    ('postgresql://other@127.0.0.1:5432/rootline_notification_query_test', ('rootline_notification_query_test','172.18.0.2',5432),'true',False),
])
def test_server_identity_guard(url, identity, github, expected):
    assert _server_identity_allowed(urlparse(url), identity, github_actions=github) is expected
