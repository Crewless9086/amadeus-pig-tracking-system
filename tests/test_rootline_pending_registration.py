"""Production-shaped synthetic pending state from the ordinary five-write path."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from scripts import reconcile_rootline_pending_registration as pending
from scripts import reconcile_oom_desktop_candidate as ordinary
from modules.charlie import mission_store as store
from modules.charlie.mission_control import build_mission_control_event
from tests import test_oom_desktop_candidate_reconciliation as old

OWNER, PRINCIPAL = old.OWNER, old.PRINCIPAL


def fixture():
    past=datetime.now(timezone.utc)-timedelta(hours=2)
    with patch.object(old,'NOW',past), patch.object(ordinary,'_now',return_value=past):
        db=old.MemoryDB()
        receipt=db.rows[pending.MISSION_ID]['metadata_json']['mission_admission']
        receipt['signed_receipt']={'mission':{'mission_id':pending.MISSION_ID,'root_mission_id':pending.PARENT_ID,'generation':receipt['generation']},
            'candidate':{'base_sha':receipt['base_sha'],'head_sha':receipt['head_sha']},
            **{k:receipt[k] for k in ('receipt_id','content_sha256','authority_key_sha256')},
            'owner_instruction_chain':{'latest_correction_digest':receipt['latest_correction_digest']},
            'collision_snapshot':{'snapshot_sha256':receipt['collision_snapshot_sha256']},
            'synthetic_shape_only':'not signed or issued'}
        args=old.arguments(db.rows[pending.MISSION_ID],db.rows[pending.PARENT_ID])
        with patch.object(store,'build_mission_control_event',side_effect=lambda *a,**kw:build_mission_control_event(*a,**kw,now=past)):
            old.apply(args,lambda _:db)
    h_id=ordinary.prepare_reconciliation(**args,now=past)['event_id']
    return arguments_from_history(db,h_id)


def arguments_from_history(db,h_id):
    history,actor,kind=db.events[h_id]
    now=datetime.now(timezone.utc)
    child,parent=deepcopy(db.rows[pending.MISSION_ID]),deepcopy(db.rows[pending.PARENT_ID])
    prior=child['metadata_json']['mission_admission_contract']
    candidate={'pr_number':pending.CANDIDATE_PR,'branch':pending.BRANCH,'base_sha':pending.BASE,
        'head_sha':pending.HEAD,'tree_sha':pending.TREE,'changed_files':pending.PATHS,'diff_sha256':'a'*64}
    generation='synthetic-rootline-pending-20261025'
    manifest={'version':pending.VERSION,'mission_id':pending.MISSION_ID,'parent_mission_id':pending.PARENT_ID,
        'candidate':candidate,'generation':generation,'desktop':deepcopy(history['manifest']['desktop']),
        'idempotency_key':'synthetic-rootline-pending-successor','expires_at':(now+timedelta(hours=1)).isoformat(),
        'expected_child_record':child,'expected_child_sha256':pending.digest(pending.canonical(child)),
        'expected_parent_record':parent,'expected_parent_sha256':pending.digest(pending.canonical(parent)),
        'expected_correction':{'event_id':history['correction']['event_id'],'metadata':deepcopy(history['correction']),'recorded_by':actor},
        'expected_registration':{'event_id':h_id,'metadata':deepcopy(history),'recorded_by':actor},
        'implementation':{'base_revision':pending.BASE,'adapter_sha256':'0'*64,'helper_files':{p:'1'*64 for p in pending.HELPERS}},
        'contract':{**deepcopy(prior),'generation':generation,'base_sha':pending.BASE,'branch':pending.BRANCH,
            'allowed_files':pending.PATHS,'allowed_effects':sorted(set(prior['allowed_effects'])-pending.REMOVED_EFFECTS),
            'forbidden_effects':sorted(set(prior['forbidden_effects'])-pending.REMOVED_FORBIDDEN_EFFECTS|pending.ADDED_FORBIDDEN_EFFECTS),
            'operational_acceptance':sorted(pending.REQUIRED_ACCEPTANCE)}}
    approval=deepcopy(history['approval'])
    approval.update(version=pending.VERSION,decision=pending.DECISION,approval_id='synthetic-rootline-owner-approval',
        issued_at=now.isoformat(),expires_at=manifest['expires_at'],instruction_text='SYNTHETIC exact pending ROOTLINE succession, not owner authority.')
    approval['source']['observed_at']=now.isoformat()
    return manifest,approval,db


def encoded(m,a):
    return old.encode(m,a)


class MemoryDB(old.MemoryDB):
    def __init__(self,db):
        self.__dict__.update(deepcopy(db.__dict__))
        self.fail_write=0; self.write_count=0; self.hold=False; self.corrupt=False
    def cursor(self): return MemoryCursor(self)


class MemoryCursor(old.MemoryCursor):
    def execute(self,sql,params=None):
        q=' '.join(sql.split())
        if q.startswith('select pg_advisory_xact_lock'):
            self.results=[(None,)]; return
        if q==pending.OWNER_HOLD_QUERY:
            self.results=[('synthetic-hold',)] if self.db.hold else []; return
        if q.startswith(('insert into ','update public.')):
            self.db.write_count+=1
            if self.db.write_count==self.db.fail_write: raise RuntimeError('injected_write_failure')
        if "values(%s,%s,'owner_correction_recorded'" in q:
            params={'event_id':params[0],'metadata':params[4],'principal':params[3]}
        super().execute(sql,params)
        if self.db.corrupt and self.db.write_count==3:
            self.db.rows[pending.MISSION_ID]['metadata_json']['mission_admission']['head_sha']='0'*40


def apply(args,db):
    with patch.object(pending,'verify_source_and_candidate'):
        return pending.reconcile_pending_succession(**args,dry_run=False,authenticated_owner_principal=OWNER,
            authenticated_desktop_principal=PRINCIPAL,connect_factory=lambda _:db)


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.m,self.a,db=fixture(); self.db=MemoryDB(db)
    def snapshot(self): return deepcopy((self.db.rows,self.db.events,self.db.ops))
    def test_preparation_never_connects_and_ordinary_entry_still_refuses(self):
        args=encoded(self.m,self.a)
        result=pending.reconcile_pending_succession(**args,connect_factory=lambda _:self.fail('connection'))
        self.assertEqual(result['writes'],0)
        with self.assertRaises(ordinary.ReconciliationError): ordinary.prepare_reconciliation(**args)
        old_m,old_a=json.loads(old.arguments()['manifest_bytes']),json.loads(old.arguments()['approval_bytes'])
        old_m['expected_child_record']['metadata_json']['mission_admission']['status']='invalidated'
        old_m['expected_child_sha256']=ordinary.digest(ordinary.canonical(old_m['expected_child_record']))
        with self.assertRaisesRegex(ordinary.ReconciliationError,'predecessor_binding_invalid'):
            ordinary.prepare_reconciliation(**old.encode(old_m,old_a))
    def test_three_writes_preserve_parent_admission_history_and_replay(self):
        before=self.snapshot(); args=encoded(self.m,self.a);result=apply(args,self.db)
        self.assertEqual(result['writes'],3); self.assertFalse(result['admission_issued'])
        self.assertEqual(self.db.write_count,3)
        self.assertEqual(self.db.rows[pending.PARENT_ID],before[0][pending.PARENT_ID])
        self.assertEqual(self.db.rows[pending.MISSION_ID]['metadata_json']['mission_admission'],before[0][pending.MISSION_ID]['metadata_json']['mission_admission'])
        for key,value in before[1].items(): self.assertEqual(self.db.events[key],value)
        self.assertEqual(self.db.ops,before[2]); after=self.snapshot()
        self.assertEqual(apply(args,self.db)['writes'],0); self.assertEqual(self.snapshot(),after)
    def test_each_write_failure_rolls_back_everything(self):
        for step in (1,2,3):
            self.db.fail_write=step; self.db.write_count=0; before=self.snapshot()
            with self.subTest(step=step), self.assertRaisesRegex(RuntimeError,'injected_write_failure'):apply(encoded(self.m,self.a),self.db)
            self.assertEqual(self.snapshot(),before)
    def test_final_semantic_readback_rolls_back(self):
        before=self.snapshot();self.db.corrupt=True
        with self.assertRaisesRegex(ordinary.ReconciliationError,'final_readback_mismatch'):apply(encoded(self.m,self.a),self.db)
        self.assertEqual(self.snapshot(),before)
    def test_wrong_owner_fails_before_source_or_connection(self):
        with patch.object(pending,'verify_source_and_candidate') as source:
            with self.assertRaisesRegex(ordinary.ReconciliationError,'independent_authentication_required'):
                pending.reconcile_pending_succession(**encoded(self.m,self.a),dry_run=False,
                    authenticated_owner_principal='wrong',authenticated_desktop_principal=PRINCIPAL,connect_factory=lambda _:self.fail('connection'))
            source.assert_not_called()
    def test_wrong_history_receipt_scope_generation_or_execution_is_refused(self):
        mutations=[lambda m:m['expected_registration']['metadata'].update(manifest_sha256='0'*64),
            lambda m:m['expected_registration'].update(recorded_by='other-owner'),
            lambda m:m['expected_child_record']['metadata_json']['mission_admission'].update(status='valid'),
            lambda m:m['expected_child_record']['metadata_json']['mission_admission'].update(signed_receipt={'fabricated':True}),
            lambda m:m['contract']['allowed_effects'].append(next(iter(pending.REMOVED_EFFECTS))),
            lambda m:m['contract']['forbidden_effects'].remove('service_deploy_outside:'+pending.WEB_SERVICE),
            lambda m:m.update(generation=m['expected_registration']['metadata']['manifest']['generation']),
            lambda m:m['expected_child_record']['metadata_json'].update(execution_lease={'active':True}),
            lambda m:m['expected_child_record']['metadata_json'].update(dispatch_authorization={'status':'valid'}),
            lambda m:m['expected_child_record']['metadata_json'].update(hermes_native_execution={'status':'valid'})]
        for mutate in mutations:
            m=deepcopy(self.m);mutate(m);m['expected_child_sha256']=pending.digest(pending.canonical(m['expected_child_record']))
            with self.subTest(mutation=mutate),self.assertRaises(ordinary.ReconciliationError):pending.prepare_pending_succession(**encoded(m,self.a))
    def test_current_history_correction_parent_and_hold_are_checked_under_lock(self):
        for kind in ('history','correction','parent','hold'):
            m,a,db=fixture(); self.db=MemoryDB(db)
            if kind=='history':self.db.events[m['expected_registration']['event_id']][0]['version']='changed'
            elif kind=='correction':self.db.events[m['expected_correction']['event_id']][0]['summary']='newer'
            elif kind=='parent':self.db.rows[pending.PARENT_ID]['title']='changed'
            else:self.db.hold=True
            before=self.snapshot()
            with self.subTest(kind=kind),self.assertRaises(ordinary.ReconciliationError):apply(encoded(m,a),self.db)
            self.assertEqual(self.snapshot(),before)
    def test_replay_preserves_later_matching_admission_but_rejects_drift(self):
        args=encoded(self.m,self.a);apply(args,self.db);md=self.db.rows[pending.MISSION_ID]['metadata_json']
        md['mission_admission']={'status':'valid','mission_id':pending.MISSION_ID,'root_mission_id':pending.PARENT_ID,
            'generation':self.m['generation'],'base_sha':pending.BASE,'head_sha':pending.HEAD,
            'receipt_id':'MAR-SYNTHETIC-LATER','content_sha256':'a'*64,'authority_key_sha256':'b'*64}
        md['mission_admission']['signed_receipt']={'mission':{k:md['mission_admission'][k] for k in ('mission_id','root_mission_id','generation')},'candidate':{'head_sha':pending.HEAD,'base_sha':pending.BASE},**{k:md['mission_admission'][k] for k in ('receipt_id','content_sha256','authority_key_sha256')},'synthetic_shape_only':'not signed or issued'}
        before=self.snapshot()
        self.assertEqual(apply(args,self.db)['writes'],0);self.assertEqual(self.snapshot(),before)
        md['mission_admission']['head_sha']=pending.PREDECESSOR_HEAD
        with self.assertRaisesRegex(ordinary.ReconciliationError,'replay_binding_conflict'):apply(args,self.db)
    def test_replay_refuses_added_metadata_and_changed_approval(self):
        args=encoded(self.m,self.a);apply(args,self.db)
        md=self.db.rows[pending.MISSION_ID]['metadata_json'];md['unapproved_extra']={'data':'changed'}
        before=self.snapshot()
        with self.assertRaisesRegex(ordinary.ReconciliationError,'replay_binding_conflict'):apply(args,self.db)
        self.assertEqual(self.snapshot(),before);md.pop('unapproved_extra')
        altered=deepcopy(self.a);altered['instruction_text']='SYNTHETIC changed owner approval'
        before=self.snapshot()
        with self.assertRaisesRegex(ordinary.ReconciliationError,'replay_history_conflict'):apply(encoded(self.m,altered),self.db)
        self.assertEqual(self.snapshot(),before)
    def test_current_contract_and_correction_remain_available_to_existing_reader(self):
        apply(encoded(self.m,self.a),self.db)
        # The existing reader is exercised below using its actual read protocol.
        with patch.object(store,'_database_url',return_value='synthetic'),patch.object(store,'_connect',return_value=self.db):
            result,status=store.read_current_mission_admission_authority(pending.MISSION_ID)
        self.assertEqual(status,200)
        self.assertEqual(result['admission']['status'],'invalidated')
        self.assertNotEqual(result['latest_owner_correction_event_id'],self.m['expected_correction']['event_id'])
        claim=next(c for c in result['active_claims'] if c['mission_id']==pending.MISSION_ID)
        self.assertEqual(claim['paths'],pending.PATHS)


if __name__=='__main__':unittest.main()
