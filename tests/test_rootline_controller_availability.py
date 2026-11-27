from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch
import pytest
from modules.telemetry import rootline_controller_availability as a

NOW=datetime(2026,11,27,8,tzinfo=timezone.utc)
DEVICE="100204e9bc"
def observation(state,at=NOW,source=None):
    return {"state":state,"checked_at":at.isoformat(),"source":source or ("controller_query_unanswered" if state=="offline" else "correlated_controller_query"),"output_state":"Unknown"}

def test_episode_survives_unknown_and_recovers_once_without_relay_claim():
    first=a.project_availability(DEVICE,observation("offline"),now=NOW)
    later=NOW+timedelta(minutes=2)
    unknown=a.project_availability(DEVICE,observation("unknown",later),first,now=later)
    assert unknown["offline_since"]==first["offline_since"] and unknown["transition"] is None
    recovered=a.project_availability(DEVICE,observation("online",later+timedelta(minutes=3)),unknown,now=later+timedelta(minutes=3))
    assert recovered["recovery_duration_seconds"]==300 and recovered["transition"]=="ControllerRecovered"
    assert recovered["output_state"]=="Unknown"
    again=a.project_availability(DEVICE,observation("online",later+timedelta(minutes=4)),recovered,now=later+timedelta(minutes=4))
    assert again["transition"] is None and again["incident_id"]==first["incident_id"]

def test_unknown_and_online_off_report_do_not_invent_offline():
    unknown=a.project_availability(DEVICE,observation("unknown"),now=NOW)
    assert unknown["offline_since"] is None
    online=a.project_availability(DEVICE,{**observation("online"),"relay_state":"OFF"},now=NOW)
    assert online["offline_since"] is None and online["state"]=="online"

@pytest.mark.parametrize("field,value",[("source","home_assistant_mqtt_subscription"),("source","ha_entity"),("output_state","OFF"),("checked_at","2026-11-27T08:00:00"),("checked_at","2026-11-27T08:01:00+00:00")])
def test_rejects_wrong_provenance_and_clocks(field,value):
    with pytest.raises(ValueError):a.project_availability(DEVICE,{**observation("offline"),field:value},now=NOW)

def test_out_of_order_replay_and_other_controller_are_independent():
    first=a.project_availability(DEVICE,observation("offline"),now=NOW)
    assert a.project_availability(DEVICE,observation("online"),first,now=NOW)["changed"] is False
    other=a.project_availability("100204d497",observation("online"),now=NOW)
    assert other["incident_id"] is None and other["state"]=="online"
    with pytest.raises(ValueError):a.project_availability("ESKOM",observation("offline"),now=NOW)

class Database:
    def __init__(self):self.rows=[];self.locks=0
    def connect(self,**kwargs):return Connection(self)
class Connection:
    def __init__(self,db):self.db=db
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return Cursor(self.db)
class Cursor:
    def __init__(self,db):self.db=db;self.result=None;self.rowcount=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args):
        if 'pg_advisory_xact_lock' in sql:self.db.locks+=1;return
        if sql.lstrip().startswith('insert'):
            row=json.loads(args[-1])["rootline_execution"]
            self.db.rows.append(row);self.rowcount=1;return
        action=args[1] if len(args)>1 else 'record_notification_delivery'
        rows=[r for r in self.db.rows if r['execution_id']==args[0] and r['action']==action]
        self.result=(rows[-1],) if rows else None
    def fetchone(self):return self.result

def test_persisted_episode_restart_replay_and_stale_display():
    db=Database()
    first=a.reconcile_controller_availability(DEVICE,observation('offline'),now=NOW,connect=db.connect)
    a.reconcile_controller_availability(DEVICE,observation('offline'),now=NOW,connect=db.connect)
    assert len(db.rows)==1 and db.locks==2
    late=NOW+timedelta(minutes=10)
    current=a.read_controller_availability(now=late,connect=db.connect)[DEVICE]
    assert current['state']=='unknown' and current['offline_elapsed_seconds']==600
    recovered=a.reconcile_controller_availability(DEVICE,observation('online',late),now=late,connect=db.connect)
    assert recovered['incident_id']==first['incident_id'] and recovered['recovery_duration_seconds']==600

@pytest.mark.parametrize('ambiguous',[False,True])
def test_notice_dedup_and_ambiguous_delivery_never_resends(ambiguous):
    db=Database();a.reconcile_controller_availability(DEVICE,observation('offline'),now=NOW,connect=db.connect)
    calls=[]
    def notify(state,payload,**kwargs):
        calls.append((state,payload));return {'provider_delivery_confirmed':not ambiguous,'provider_message_id':'1' if not ambiguous else '', 'telegram_sends':1}
    def store(action,payload):
        db.rows.append({**payload,'action':action,'event_id':'notice-receipt'});return {'success':True}
    with patch('modules.telemetry.rootline_cycle_budget.remaining_seconds'):
        a.notify_controller_availability(notify=notify,store=store,now=NOW,connect=db.connect)
        a.notify_controller_availability(notify=notify,store=store,now=NOW,connect=db.connect)
    assert len(calls)==1 and calls[0][0]=='ControllerOffline'

def test_notices_are_clean_and_do_not_claim_running():
    from modules.oom_sakkie.rootline_transition_notifications import compose_controller_notice
    text=compose_controller_notice('ControllerRecovered',{'controller_label':'Mixer & injection','recovery_duration_seconds':650})
    assert '10 min' in text and '&amp;' in text and 'SAST' not in text and 'running' not in text


def test_all_four_camp_tiles_share_controller_outage_but_other_devices_do_not():
    from modules.telemetry.rootline_owner_control_projection import build_owner_control_projection
    devices=[{'id':key,'state':'on_command_accepted','summary':'ON command accepted'} for key in
        ('camp_a','camp_b','camp_c','camp_e','mixer','injection','borehole','eskom')]
    offline=a.project_availability(DEVICE,observation('offline'),now=NOW)
    with patch('modules.telemetry.rootline_owner_control_projection.read_execution_projection',return_value={'events':[],'plan':{},'truncated':False}), patch('modules.telemetry.rootline_owner_control_projection.project_devices',return_value=devices), patch.object(a,'read_controller_availability',return_value={DEVICE:offline}):
        result=build_owner_control_projection('devices',control_state={},now=NOW)['devices']
    assert all(d['state']=='controller_offline' for d in result[:4])
    assert all(d['state']=='on_command_accepted' for d in result[4:])
    assert 'controller_availability' not in result[-1]


def test_definitely_unsent_notice_uses_existing_retry_proof_then_recovers_once():
    db=Database();a.reconcile_controller_availability(DEVICE,observation('offline'),now=NOW,connect=db.connect)
    calls=[]
    def notify(state,payload,**kwargs):
        calls.append((state,kwargs))
        if len(calls)==1:return {'delivery_definitely_not_sent':True,'telegram_sends':0}
        return {'provider_delivery_confirmed':True,'provider_message_id':str(len(calls)),'telegram_sends':1}
    def store(action,payload):
        db.rows.append({**payload,'action':action,'event_id':'receipt-'+str(len(calls))});return {'success':True}
    with patch('modules.telemetry.rootline_cycle_budget.remaining_seconds'):
        for _ in range(3):a.notify_controller_availability(notify=notify,store=store,now=NOW,connect=db.connect)
        late=NOW+timedelta(minutes=10)
        a.reconcile_controller_availability(DEVICE,observation('online',late),now=late,connect=db.connect)
        for _ in range(2):a.notify_controller_availability(notify=notify,store=store,now=late,connect=db.connect)
    assert [c[0] for c in calls]==['ControllerOffline','ControllerOffline','ControllerRecovered']
    assert calls[1][1]['retry_proof_identity']=='receipt-1'
