"""ROOTLINE notification bookkeeping on the existing manager lifecycle."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import hashlib
from zoneinfo import ZoneInfo

import pytest

from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import general_manager_worker as worker

NOW = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
MATERIAL = hashlib.sha256(b'synthetic-rootline-material').hexdigest()


@pytest.fixture(autouse=True)
def configured_owner(monkeypatch):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','42')
    monkeypatch.setenv('ROOTLINE_REASSESSMENT_OWNER_USER_ID','42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','42')


def evidence(now=NOW):
    common = {'owner_user_id': '42', 'chat_id': '42', 'operating_date': now.astimezone(ZoneInfo('Africa/Johannesburg')).date().isoformat(),
        'material_digest': MATERIAL, 'result_id': 'ROOTLINE-RESULT-SYNTHETIC', 'evidence_generation': 'GEN-SYNTHETIC'}
    observation = {**common, 'identity': 'OOM-ROOTLINE-OBS-SYNTHETIC',
        'event_id': 'OOM-ROOTLINE-OBS-SYNTHETIC-RECORD_OBSERVATION', 'delivery_state': 'observation_only'}
    delivery = {**common, 'identity': 'OOM-ROOTLINE-REASSESS-SYNTHETIC',
        'event_id': 'OOM-ROOTLINE-REASSESS-SYNTHETIC-MARK_DELIVERED', 'delivery_state': 'delivered',
        'provider_message_id': '12345', 'provider_timestamp': (now-timedelta(seconds=1)).isoformat()}
    return (observation['event_id'], now-timedelta(seconds=2), observation), (delivery['event_id'], now-timedelta(seconds=1), delivery)


class Cursor:
    def __init__(self, rows): self.rows=iter(rows); self.commands=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,params=None): self.commands.append((sql,params))
    def fetchone(self): return next(self.rows)


class Connection:
    def __init__(self,cur): self.cur=cur
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def cursor(self): return self.cur


def collect(monkeypatch, observation, delivery=None, retained=None, now=NOW):
    cursor=Cursor([observation, delivery, retained] if observation else [None])
    monkeypatch.setattr(sources,'connect_bounded_read',lambda:Connection(cursor))
    return sources._rootline(now),cursor


@pytest.mark.parametrize('has_observation',[False,True])
def test_actual_collector_retry_clock_does_not_change_material(monkeypatch,has_observation):
    observation,_=evidence()
    observation=observation if has_observation else None
    first,_=collect(monkeypatch,observation)
    later,_=collect(monkeypatch,observation,now=NOW+timedelta(minutes=5))
    a=worker.normalize_candidate(first[0],now=NOW)
    b=worker.normalize_candidate(later[0],now=NOW+timedelta(minutes=5))
    assert a['evidence_digest']==b['evidence_digest']
    assert a['next_reassessment_at']!=b['next_reassessment_at']


def test_exact_delivery_is_explicit_terminal_evidence_not_absence(monkeypatch):
    observation,delivery=evidence()
    rows,_=collect(monkeypatch,observation,delivery)
    assert len(rows)==1
    assert rows[0]['terminal_state']=='completed'
    assert rows[0]['dedupe_key']=='rootline:current-plan'


def retained(observation=None, generation=2):
    observation=observation or evidence()[0]
    return ('OOM-CASE-SYNTHETIC', 'rootline:current-plan', 'ROOTLINE', generation, 'a'*64,
        ['event:'+observation[0], 'material:'+MATERIAL, 'owner:42','chat:42',
         'observed:'+observation[1].isoformat()])


def test_fresher_same_material_observation_reuses_actual_receipt_and_stays_stable():
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence()
    first=completion_candidate(observation,delivery,retained(observation),now=NOW)
    fresh=deepcopy(observation[2])
    fresh.update(identity='OOM-ROOTLINE-OBS-FRESH',event_id='OOM-ROOTLINE-OBS-FRESH-RECORD_OBSERVATION',
        result_id='ROOTLINE-RESULT-FRESH',evidence_generation='GEN-FRESH')
    later=completion_candidate((fresh['event_id'],NOW,fresh),delivery,retained(observation),now=NOW+timedelta(seconds=1))
    assert later['_rootline_delivery_proof']['delivery']==first['_rootline_delivery_proof']['delivery']
    assert later['_rootline_delivery_proof']['observation']['result_id']=='ROOTLINE-RESULT-FRESH'
    assert worker.normalize_candidate(first,now=NOW)['evidence_digest']==worker.normalize_candidate(later,now=NOW+timedelta(seconds=1))['evidence_digest']


@pytest.mark.parametrize('change',['missing_delivery','ambiguous','pending','failed','wrong_material','wrong_owner','wrong_chat',
    'wrong_date','missing_provider','future_receipt','future_provider','future_observation','naive_time','missing_observation_identity',
    'wrong_event','missing_generation','bad_payload','bad_retained','different_retained_owner','different_retained_chat'])
def test_incomplete_or_conflicting_canonical_proof_cannot_complete(change):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence(); observation=list(observation); delivery=list(delivery); prior=retained()
    if change=='missing_delivery': delivery=None
    elif change in {'ambiguous','pending','failed'}: delivery[2]['delivery_state']=change
    elif change=='wrong_material': delivery[2]['material_digest']='b'*64
    elif change=='wrong_owner': delivery[2]['owner_user_id']='43'
    elif change=='wrong_chat': delivery[2]['chat_id']='43'
    elif change=='wrong_date': delivery[2]['operating_date']='2026-10-05'
    elif change=='missing_provider': delivery[2]['provider_message_id']=''
    elif change=='future_receipt': delivery[1]=NOW+timedelta(seconds=1)
    elif change=='future_provider': delivery[2]['provider_timestamp']=(NOW+timedelta(seconds=1)).isoformat()
    elif change=='future_observation': observation[1]=NOW+timedelta(seconds=1)
    elif change=='naive_time': observation[1]=NOW.replace(tzinfo=None)
    elif change=='missing_observation_identity': observation[2]['identity']=''
    elif change=='wrong_event': delivery[0]='FOREIGN'
    elif change=='missing_generation': delivery[2]['evidence_generation']=''
    elif change=='bad_payload': observation[2]=[]
    elif change=='bad_retained': prior=prior[:3]
    elif change=='different_retained_owner': prior=(*prior[:5],['owner:43'])
    elif change=='different_retained_chat': prior=(*prior[:5],['chat:43'])
    assert completion_candidate(observation,delivery,prior,now=NOW) is None


@pytest.mark.parametrize('change',['key','specialist','terminal','family','proof','provider','refs','unknowns'])
def test_normalizer_refuses_transplanted_or_tampered_completion(change):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence(); raw=completion_candidate(observation,delivery,retained(),now=NOW)
    if change=='key': raw['dedupe_key']='rootline:shutdown'
    elif change=='specialist': raw['specialist']='HERDMASTER'
    elif change=='terminal': raw['terminal_state']=''
    elif change=='family': raw['message_family']='other'
    elif change=='proof': raw.pop('_rootline_delivery_proof')
    elif change=='provider': raw['_rootline_delivery_proof']['delivery']['provider_message_id']='changed'
    elif change=='refs': raw['evidence_refs'].append('borrowed:proof')
    elif change=='unknowns': raw['unknowns']=['unresolved']
    with pytest.raises(worker.ManagerCaseError,match='rootline_delivery_proof_invalid'):
        worker.normalize_candidate(raw,now=NOW)


def test_absent_receipt_does_not_invent_silent_or_fingerprint_completion(monkeypatch):
    observation,_=evidence()
    observation[2].update(zones=[], owner_plan_fingerprint='synthetic-same-plan')
    rows,_=collect(monkeypatch,observation,None)
    assert rows[0].get('terminal_state') is None
    assert rows[0]['unknowns']


def test_read_failure_propagates_instead_of_empty_success(monkeypatch):
    class Failed(Cursor):
        def execute(self,*args): raise TimeoutError('synthetic read failure')
    monkeypatch.setattr(sources,'connect_bounded_read',lambda:Connection(Failed([])))
    with pytest.raises(TimeoutError): sources._rootline(NOW)


def test_exact_completion_normalizes_again_without_losing_proof():
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence(); raw=completion_candidate(observation,delivery,retained(),now=NOW)
    first=worker.normalize_candidate(raw,now=NOW)
    second=worker.normalize_candidate(first,now=NOW)
    assert first==second


@pytest.mark.parametrize('change',['new_owner','removed_allowance','conflicting_scheduler','missing_owner','ambiguous_allowlist'])
def test_current_recipient_configuration_is_required(monkeypatch,change):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence()
    if change=='new_owner':monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','43')
    elif change=='removed_allowance':monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','43')
    elif change=='conflicting_scheduler':monkeypatch.setenv('ROOTLINE_REASSESSMENT_OWNER_USER_ID','43')
    elif change in {'missing_owner','ambiguous_allowlist'}:
        monkeypatch.delenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID')
        monkeypatch.delenv('ROOTLINE_REASSESSMENT_OWNER_USER_ID')
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','' if change=='missing_owner' else '42,43')
    assert completion_candidate(observation,delivery,retained(),now=NOW) is None


def test_foreign_consistent_recipient_pair_cannot_close_legacy_unbound_case(monkeypatch):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence()
    for row in (observation,delivery):row[2].update(owner_user_id='43',chat_id='43')
    prior=retained();prior=(*prior[:5],[ref for ref in prior[5] if not ref.startswith(('owner:','chat:'))])
    assert completion_candidate(observation,delivery,prior,now=NOW) is None


def test_current_principal_policy_keeps_single_allowlist_compatibility(monkeypatch):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    monkeypatch.delenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID')
    observation,delivery=evidence()
    assert completion_candidate(observation,delivery,retained(),now=NOW) is not None


def test_source_observation_select_binds_current_private_recipient(monkeypatch):
    _,cursor=collect(monkeypatch,None)
    params=next(params for sql,params in cursor.commands if "delivery_state'='observation_only'" in sql)
    assert params==('2026-10-06','42','42')


def test_fresh_pending_observation_keeps_material_but_full_latest_refs(monkeypatch):
    observation,_=evidence()
    first,_=collect(monkeypatch,observation)
    changed=deepcopy(observation[2]);changed.update(identity='FRESH',event_id='FRESH-RECORD_OBSERVATION',
        result_id='FRESH-RESULT',evidence_generation='FRESH-GENERATION',evidence_cutoff=NOW.isoformat())
    second,_=collect(monkeypatch,(changed['event_id'],NOW,changed),now=NOW+timedelta(minutes=5))
    a=worker.normalize_candidate(first[0],now=NOW);b=worker.normalize_candidate(second[0],now=NOW+timedelta(minutes=5))
    assert a['evidence_digest']==b['evidence_digest'] and a['evidence_refs']!=b['evidence_refs']
    assert 'result:FRESH-RESULT' in b['evidence_refs'] and 'event:FRESH-RECORD_OBSERVATION' in b['evidence_refs']


@pytest.mark.parametrize('change',['other_key','other_family','missing_material','bad_material','missing_owner','extra_ref','unknown_identity'])
def test_snapshot_material_exception_never_applies_outside_complete_exact_family(monkeypatch,change):
    observation,_=evidence();rows,_=collect(monkeypatch,observation);raw=rows[0]
    if change=='other_key':raw['dedupe_key']='rootline:shutdown'
    elif change=='other_family':raw['message_family']='other'
    elif change=='missing_material':raw['evidence_refs']=[r for r in raw['evidence_refs'] if not r.startswith('material:')]
    elif change=='bad_material':raw['evidence_refs']=[r if not r.startswith('material:') else 'material:unknown' for r in raw['evidence_refs']]
    elif change=='missing_owner':raw['evidence_refs']=[r for r in raw['evidence_refs'] if not r.startswith('owner:')]
    elif change=='extra_ref':raw['evidence_refs'].append('unexpected:obligation')
    else:raw['unknowns'].append('current_plan_result_identity')
    newer={**raw,'evidence_refs':['event:NEW' if r.startswith('event:') else r for r in raw['evidence_refs']]}
    assert worker.normalize_candidate(raw,now=NOW)['evidence_digest']!=worker.normalize_candidate(newer,now=NOW)['evidence_digest']


def test_conflicting_generic_manager_recipient_refuses_terminal(monkeypatch):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence();monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','43,42')
    assert completion_candidate(observation,delivery,retained(),now=NOW) is None


@pytest.mark.parametrize('material',['unknown','a'*63,'A'*64,'g'*64,' ',''])
def test_matching_malformed_material_never_becomes_completion(material):
    from modules.oom_sakkie.rootline_notification_disposition import completion_candidate
    observation,delivery=evidence()
    observation[2]['material_digest']=delivery[2]['material_digest']=material
    assert completion_candidate(observation,delivery,retained(),now=NOW) is None
