"""Attributable purpose corrections retire only their complete retained work."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from modules.oom_sakkie import herdmaster_purpose_completion as completion
from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie.owner_attention_projection import build_owner_attention_projection
from modules.pig_weights import purpose_correction_batch_service as correction
from tests.test_oom_sakkie_purpose_decision import candidate, pg
from tests.test_herdmaster_purpose_work import NOW, DAY, inputs
from modules.pig_weights.herdmaster_purpose_work import build_purpose_work


def proof_fixture():
    raw = candidate(now=NOW)
    case = {**worker.normalize_candidate(raw, now=NOW), "generation": 1,
        "generation_started_at": NOW, "status": "waiting_reassessment"}
    pigs, history = [], []
    for index, identity in enumerate(completion.retained_members(case)["pig_ids"]):
        decision = {"pig_id": identity, "purpose": "Sale", "reason": "Owner review", "note": ""}
        effect = {**decision, "tag_number": f"S{index:04d}", "old_purpose": "Unknown", "new_purpose": "Sale",
            "status": "Active", "on_farm": True, "latest_weight_date": DAY.isoformat(), "latest_weight_kg": 12.0}
        envelope = {"contract_version": correction.CONTRACT_VERSION, "decisions": [decision],
            "effects": [effect], "return_to": None,
            "preview_digest": correction._preview_digest([decision], [effect], "")}
        batch = {"batch_id": f"B-{index}", "status": "executed", "decisions_json": envelope,
            "decision_hash": correction._decision_hash([decision]), "created_by": "owner:test",
            "owner_approved_by": "owner:test", "executed_by": "owner:test",
            "owner_approved_at": NOW+timedelta(seconds=1), "executed_at": NOW+timedelta(seconds=2)}
        occurred = NOW+timedelta(seconds=3)
        event = {"event_id": f"E-{index}", "event_type": "pig.purpose_corrected", "domain": "animals",
            "aggregate_type": "pig", "aggregate_id": identity, "source_system": "herdmaster_purpose_correction",
            "authority_tier": "owner_approved", "actor_type": "owner", "actor_id": "owner:test",
            "privacy_class": "owner_private", "correlation_id": batch["batch_id"],
            "occurred_at": occurred, "recorded_at": occurred, "freshness_at": occurred,
            "payload_json": {"batch_id": batch["batch_id"], "old_purpose": "Unknown", "new_purpose": "Sale",
                "reason": decision["reason"], "note": "", "approved_by": "owner:test",
                "approved_at": batch["owner_approved_at"].isoformat()},
            "provenance_json": {"source_ref": "pig_current_state", "weight_date": DAY.isoformat()},
            "idempotency_key": hashlib.sha256(f"{batch['batch_id']}|{identity}|{batch['decision_hash']}".encode()).hexdigest()}
        pigs.append({"pig_id": identity, "tag_number": effect["tag_number"], "litter_id": "COHORT-A",
            "purpose": "Sale", "status": "Active", "on_farm": True})
        history.append((event, batch))
    return case, pigs, history


def project(case, pigs, history):
    return completion.completion_candidate(case, pigs, history, now=NOW+timedelta(minutes=1))


def test_real_producer_identity_complete_corrections_fenced_stable_and_no_messages():
    case, pigs, history = proof_fixture()
    row = project(case, pigs, history)
    assert row["dedupe_key"] == case["dedupe_key"]
    assert row["terminal_state"] == "completed" and row["message_family"] == "herdmaster_disposition"
    assert row["unknowns"] == []
    assert f"herdmaster_case_fence:1:{case['evidence_digest']}" in row["evidence_refs"]
    first = worker.normalize_candidate(row, now=NOW)
    later = completion.completion_candidate(case, pigs, history, now=NOW+timedelta(hours=1))
    assert worker.normalize_candidate(later, now=NOW)["evidence_digest"] == first["evidence_digest"]


@pytest.mark.parametrize("change", ["partial", "missing_pig", "wrong_litter", "tag_changed", "off_farm",
    "status", "duplicate_pig", "extra_unknown", "extra_held", "missing_event", "missing_batch", "unapproved",
    "wrong_owner", "wrong_source", "wrong_event_key", "wrong_pig", "wrong_purpose", "changed_payload",
    "decision_tampered", "effect_tampered", "older_epoch", "future_event", "future_execution", "same_time_conflict",
    "missing_epoch", "duplicate_ref", "conflicting_phase", "foreign_family", "wrong_cohort"])
def test_incomplete_or_conflicting_evidence_cannot_close(change):
    case, pigs, history = proof_fixture()
    event, batch = history[0]
    if change == "partial": pigs[0]["purpose"] = "Unknown"
    elif change == "missing_pig": pigs.pop()
    elif change == "wrong_litter": pigs[0]["litter_id"] = "OTHER"
    elif change == "tag_changed": pigs[0]["tag_number"] = "REUSED"
    elif change == "off_farm": pigs[0]["on_farm"] = False
    elif change == "status": pigs[0]["status"] = "Sold"
    elif change == "duplicate_pig": pigs.append(dict(pigs[0]))
    elif change in {"extra_unknown", "extra_held"}: pigs.append({**pigs[0], "pig_id": "PIG-EXTRA", "purpose": "Unknown", "status": "Active" if change == "extra_unknown" else "Sold"})
    elif change == "missing_event": history.pop()
    elif change == "missing_batch": history[0] = (event, None)
    elif change == "unapproved": batch["status"] = "draft"
    elif change == "wrong_owner": batch["executed_by"] = "other"
    elif change == "wrong_source": event["source_system"] = "foreign"
    elif change == "wrong_event_key": event["idempotency_key"] = "foreign"
    elif change == "wrong_pig": event["aggregate_id"] = "PIG-FOREIGN"
    elif change == "wrong_purpose": event["payload_json"]["new_purpose"] = "Meat"
    elif change == "changed_payload": event["payload_json"]["reason"] = "different"
    elif change == "decision_tampered": batch["decisions_json"]["decisions"][0]["note"] = "different"
    elif change == "effect_tampered": batch["decisions_json"]["effects"][0]["old_purpose"] = "Meat"
    elif change == "older_epoch": case["generation_started_at"] = NOW+timedelta(seconds=4)
    elif change == "future_event": event["occurred_at"] = NOW+timedelta(days=1)
    elif change == "future_execution": batch["executed_at"] = NOW+timedelta(days=1)
    elif change == "same_time_conflict": history.append(deepcopy(history[0]))
    elif change == "missing_epoch": case.pop("generation_started_at")
    elif change == "duplicate_ref": case["evidence_refs"].append(case["evidence_refs"][-1] if case["evidence_refs"][-1].startswith("pig:") else "pig:"+pigs[0]["pig_id"])
    elif change == "conflicting_phase": case["evidence_refs"].append("phase:held")
    elif change == "foreign_family": case["evidence_refs"] = [v.replace("manager_message_family:purpose_review", "manager_message_family:foreign") for v in case["evidence_refs"]]
    elif change == "wrong_cohort": case["dedupe_key"] += "-OTHER"
    assert project(case, pigs, history) is None


@pytest.mark.parametrize("count", [12, 13, 50])
def test_actual_capped_producer_membership_never_proves_complete(count):
    allocation, checks, _ = inputs(count=count, weight_day=DAY-timedelta(days=1))
    work = build_purpose_work(allocation, checks, analysis_date=DAY)
    raw = sources._purpose_review_candidates({"purpose_work": work}, now=NOW, today=DAY, observed_at=NOW)[0]
    normalized = worker.normalize_candidate(raw, now=NOW)
    assert len([v for v in normalized["evidence_refs"] if v.startswith("pig:")]) == 12
    assert completion.retained_members(normalized) is None


@pytest.mark.parametrize("status,expected", [("waiting_reassessment", "open"), ("exception", "open"), ("completed", "resolved")])
def test_attention_does_not_invent_resolution_from_successful_collector_omission(status, expected):
    row = candidate(now=NOW)
    result = build_owner_attention_projection([], generated_at=NOW, prior_cases=[{**row,
        "operational_status": status, "lifecycle": "resolved" if status == "completed" else "open"}])
    assert result["lifecycle_items"][0]["lifecycle"] == expected


@pytest.fixture
def purpose_db(pg):
    from tests.test_oom_sakkie_general_manager_postgres import _IsolatedConnection, _IsolatedCursor, URL
    import psycopg
    class Cursor(_IsolatedCursor):
        def execute(self, sql, params=None):
            return super().execute(sql.replace("public.", self.owner.schema+"."), params)
    class Connection(_IsolatedConnection):
        def cursor(self): return Cursor(self.connection.cursor(), self.owner)
    def connect(): return Connection(psycopg.connect(URL, options="-c statement_timeout=10000"), pg)
    with connect() as db:
        db.execute("""create table public.pigs(pig_id text primary key,tag_number text,litter_id text,
            purpose text,status text,on_farm boolean,updated_at timestamptz default now())""")
        db.execute("create view public.current_canonical_pigs as select * from public.pigs")
        db.execute("""create table public.pig_weight_events(weight_event_id text primary key,pig_id text,
            weight_date date,weight_kg numeric,created_at timestamptz default now())""")
        for name in ("202607190001_create_operational_event_fabric.sql", "202607220001_create_pig_purpose_correction_batches.sql"):
            db.execute((Path(__file__).parents[1]/"supabase"/"migrations"/name).read_text())
        for i in range(2):
            identity=f"PIG-SYNTHETIC-{i:04d}"
            db.execute("insert into public.pigs values(%s,%s,'COHORT-A','Unknown','Active',true,now())", (identity,f"S{i:04d}"))
            db.execute("insert into public.pig_weight_events values(%s,%s,current_date,12,now())", ("W-"+identity,identity))
    return pg, connect


def execute_real_correction(connect, monkeypatch, ids):
    monkeypatch.setenv("OWNER_SESSION_SECRET", "synthetic-purpose-completion")
    items=[{"pig_id":identity,"purpose":"Sale","reason":"Approved purpose","note":""} for identity in ids]
    kwargs={"actor_id":"owner:synthetic", "connect_factory":lambda _url: connect()}
    preview, status=correction.preview_correction_batch(items, **kwargs)
    assert status == 200, preview
    result,status=correction.create_correction_batch(items,idempotency_key="batch-"+"-".join(ids),
        confirmation_binding=preview["confirmation_binding"], **kwargs)
    assert status == 201, result
    batch=result["batch_id"]
    assert correction.approve_correction_batch(batch,**kwargs)[1] == 200
    result,status=correction.execute_correction_batch(batch,**kwargs)
    assert status == 200 and result["rows_updated"] == len(ids), result
    return batch


@pytest.mark.parametrize("delivered", [False, True])
def test_postgres_real_approved_writer_natural_reconciliation_closes_once_without_send(purpose_db, monkeypatch, delivered):
    pg, connect=purpose_db
    raw=candidate(now=pg.now);pg.seed([raw])
    if delivered:
        with pg.db() as db:db.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s,status='waiting_reassessment'",(pg.now,))
    with pg.db() as db:
        before=db.execute("select last_delivery_digest,last_delivery_at from app_private.oom_manager_cases").fetchone()
    batch=execute_real_correction(connect,monkeypatch,[f"PIG-SYNTHETIC-{i:04d}" for i in range(2)])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    monkeypatch.setattr(completion,"connect_bounded_read",connect)
    for name in ("_herdmaster_retained","_herdmaster_advisories","_rootline","_herdmaster","_sam","_beacon","_delivery_gaps","_runtime"):
        monkeypatch.setattr(sources,name,lambda _now: [])
    rows=sources.collect_manager_candidates(now=pg.now)
    assert len(rows)==1 and rows[0]["terminal_state"]=="completed",rows
    result=pg.cycle(rows,deliver=lambda *_a,**_k:pytest.fail("closure cannot send"))
    assert result["success"] and result["candidates_changed"]==1,result
    assert completion.collect_purpose_completions(pg.now,connect=connect)==[]
    pg.now+=timedelta(minutes=6)
    repeated=pg.cycle(rows,deliver=lambda *_a,**_k:pytest.fail("replay cannot send"))
    assert repeated["success"]
    with connect() as db:
        case=db.execute("select status,generation,last_delivery_digest from app_private.oom_manager_cases").fetchone()
        assert case[0:2]==('completed',2)
        assert bool(case[2]) is delivered
        assert db.execute("select last_delivery_digest,last_delivery_at from app_private.oom_manager_cases").fetchone()==before
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]==1
        assert db.execute("select count(*) from public.operational_events").fetchone()[0]==2
        assert db.execute("select count(*) from public.pig_purpose_correction_batches where status='executed'").fetchone()[0]==1
    replay,status=correction.execute_correction_batch(batch,actor_id="owner:synthetic",connect_factory=lambda _url:connect())
    assert status==200 and replay['rows_updated']==0


@pytest.mark.parametrize("guard", ["generation", "digest", "lease", "expired_delegated"])
def test_postgres_completion_respects_current_case_fences(purpose_db,monkeypatch,guard):
    pg,connect=purpose_db;pg.seed([candidate(now=pg.now)])
    execute_real_correction(connect,monkeypatch,[f"PIG-SYNTHETIC-{i:04d}" for i in range(2)])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    terminal=completion.collect_purpose_completions(pg.now,connect=connect)[0]
    with pg.db() as db:
        if guard=='generation':db.execute("update app_private.oom_manager_cases set generation=generation+1")
        elif guard=='digest':db.execute("update app_private.oom_manager_cases set evidence_digest=repeat('a',64)")
        else:db.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='OTHER',lease_until=%s",(pg.now+timedelta(minutes=1 if guard=='lease' else -1),))
        with db.cursor() as cur:
            result=pg.store._reconcile(cur,worker.normalize_candidate(terminal,now=pg.now),pg.now)
        assert result in {'stale','deferred','replayed'}
        assert db.execute("select status from app_private.oom_manager_cases").fetchone()[0]!='completed'


def test_postgres_partial_correction_preserves_same_work_and_extra_unknown_blocks(purpose_db,monkeypatch):
    pg,connect=purpose_db;raw=candidate(now=pg.now);pg.seed([raw])
    execute_real_correction(connect,monkeypatch,['PIG-SYNTHETIC-0000'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    assert completion.collect_purpose_completions(pg.now,connect=connect)==[]
    pg.now=datetime.now(timezone.utc)
    allocation,checks,_=inputs(weight_day=DAY-timedelta(days=1))
    allocation['pigs'][0]['purpose']='Sale';checks['rows'][0]['canonical']['purpose']='Sale'
    remaining=sources._purpose_review_candidates({'purpose_work':build_purpose_work(allocation,checks,analysis_date=DAY)},now=pg.now,today=DAY,observed_at=pg.now)[0]
    assert remaining['dedupe_key']==raw['dedupe_key']
    assert [v for v in remaining['evidence_refs'] if v.startswith('pig:')]==['pig:PIG-SYNTHETIC-0001']
    pg.seed([remaining])
    execute_real_correction(connect,monkeypatch,['PIG-SYNTHETIC-0001'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=2)
    completed=completion.collect_purpose_completions(pg.now,connect=connect)
    assert len(completed)==1
    with connect() as db:db.execute("insert into public.pigs values('PIG-EXTRA','EXTRA','COHORT-A','Unknown','Active',true,now())")
    assert completion.collect_purpose_completions(pg.now,connect=connect)==[]

    # Current unresolved membership outside the retained refs blocks closure.
    with connect() as db:db.execute("delete from public.pigs where pig_id='PIG-EXTRA'")
    final=completion.collect_purpose_completions(pg.now,connect=connect)
    assert len(final)==1
    result=pg.cycle(final,deliver=lambda *_a,**_k:pytest.fail("no completion notice"))
    assert result['success'] and result['candidates_changed']==1
    with pg.db() as db:
        case_id,generation=db.execute("select case_id,generation from app_private.oom_manager_cases").fetchone()
    # A later genuine Unknown candidate is new work with the same owning key.
    with connect() as db:db.execute("update public.pigs set purpose='Unknown' where pig_id='PIG-SYNTHETIC-0001'")
    pg.now+=timedelta(minutes=6)
    remaining={**remaining,'evidence_refs':[v for v in remaining['evidence_refs'] if not v.startswith('observed:')]+['observed:'+pg.now.isoformat()]}
    pg.seed([remaining]);pg.seed([remaining])
    with pg.db() as db:
        assert db.execute("select case_id,generation,status from app_private.oom_manager_cases").fetchone()==(case_id,generation+1,'open')
    assert completion.collect_purpose_completions(pg.now,connect=connect)==[]


@pytest.mark.parametrize("unknown", sorted(completion.UNKNOWN))
def test_every_canonical_unknown_alias_in_extra_cohort_member_blocks(unknown):
    case,pigs,history=proof_fixture()
    pigs.append({**pigs[0], "pig_id":"PIG-EXTRA", "purpose":unknown})
    assert project(case,pigs,history) is None


@pytest.mark.parametrize("field,value", [("privacy_class","public"),("recorded_at",None),
    ("freshness_at",None),("event_id",None),("provenance_json",{} )])
def test_correction_event_provenance_is_not_optional(field,value):
    case,pigs,history=proof_fixture();history[0][0][field]=value
    assert project(case,pigs,history) is None


class Snapshot:
    def __init__(self, groups, fail=None):
        self.groups=iter(groups);self.rows=[];self.selects=[];self.fail=fail
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def cursor(self):return self
    def execute(self,sql,params=None):
        if sql.startswith("set transaction") or sql.startswith("select set_config"):
            return self
        self.selects.append(sql)
        if self.fail==len(self.selects):raise TimeoutError("synthetic source unavailable")
        self.rows=next(self.groups);return self
    def fetchall(self):return self.rows


def snapshot_groups():
    case,pigs,history=proof_fixture()
    case['case_id']='CASE-SYNTHETIC'
    return [
        [(case['case_id'],case['dedupe_key'],case['generation'],case['evidence_digest'],case['evidence_refs'])],
        [(case['case_id'],case['generation'],case['generation_started_at'],{},'created')],
        [tuple(p[k] for k in ('pig_id','tag_number','litter_id','purpose','status','on_farm')) for p in pigs],
        history]


def test_collector_uses_one_fixed_bounded_read_snapshot_and_never_writes():
    snapshot=Snapshot(snapshot_groups())
    result=completion.collect_purpose_completions(NOW+timedelta(minutes=1),connect=lambda:snapshot)
    assert len(result)==1 and len(snapshot.selects)==4
    assert all(sql.lstrip().startswith('select ') for sql in snapshot.selects)
    assert [int(sql.rsplit('limit ',1)[1]) for sql in snapshot.selects]==[65,129,10001,10001]


@pytest.mark.parametrize('stage,limit', [(0,64),(1,128),(2,10000),(3,10000)])
def test_any_snapshot_overflow_refuses_partial_completion(stage,limit):
    groups=snapshot_groups();groups[stage]=[groups[stage][0]]*(limit+1)
    with pytest.raises(ValueError,match='bound_exceeded'):
        completion.collect_purpose_completions(NOW+timedelta(minutes=1),connect=lambda:Snapshot(groups))


@pytest.mark.parametrize('stage',[1,2,3,4])
def test_source_failure_never_emits_terminal_or_resolves_omitted_case(monkeypatch,stage):
    snapshot=Snapshot(snapshot_groups(),fail=stage)
    monkeypatch.setattr(completion,'connect_bounded_read',lambda:snapshot)
    rows=sources.collect_manager_candidates(now=NOW,collectors=(sources._herdmaster_purpose_completions,))
    assert len(rows)==1 and rows[0]['specialist']=='RUNTIME'
    assert not rows[0].get('terminal_state')


def test_current_work_wins_over_complete_snapshot_even_when_returned_later():
    case,pigs,history=proof_fixture();terminal=project(case,pigs,history)
    rows=sources.collect_manager_candidates(now=NOW,collectors=(lambda _: [terminal],lambda _: [candidate(now=NOW)]))
    assert len(rows)==1 and not rows[0].get('terminal_state')


def one_member_retained_proof():
    """Production-shaped adopted one-member generation; all identities synthetic."""
    from modules.oom_sakkie import herdmaster_purpose_membership as membership
    allocation, checks, _ = inputs(count=1, weight_day=DAY-timedelta(days=1))
    allocation['pigs'][0]['tag_number']='106'
    checks['rows'][0]['canonical']['tag_number']='106'
    raw=sources._purpose_review_candidates({'purpose_work':build_purpose_work(allocation,checks,analysis_date=DAY)},
        now=NOW,today=DAY,observed_at=NOW)[0]
    case={**worker.normalize_candidate(raw,now=NOW),'generation':4,'generation_started_at':NOW,
        'status':'waiting_reassessment','_purpose_membership':raw['_purpose_membership']}
    case['purpose_membership']=membership.build_record(case,generation=4,now=NOW,legacy_epoch=NOW)
    _,pigs,history=proof_fixture();pigs=pigs[:1];history=history[:1]
    pigs[0]['tag_number']='106';envelope=history[0][1]['decisions_json'];envelope['effects'][0]['tag_number']='106'
    envelope['preview_digest']=correction._preview_digest(envelope['decisions'],envelope['effects'],'')
    return case,pigs,history


@pytest.mark.parametrize('status',['Died','Dead','Deceased','Sold','Culled'])
def test_departed_non_obligation_unknown_extras_do_not_block_proven_completion(status):
    case,pigs,history=one_member_retained_proof()
    for number in range(2):
        pigs.append({'pig_id':f'PIG-HISTORICAL-{number}','tag_number':None,'litter_id':'COHORT-A',
            'purpose':'Unknown','status':status,'on_farm':False})
    before=deepcopy(pigs)
    result=project(case,pigs,history)
    assert result and result['terminal_state']=='completed'
    assert result['dedupe_key']==case['dedupe_key']
    assert f"herdmaster_case_fence:4:{case['evidence_digest']}" in result['evidence_refs']
    assert 'purpose_membership_snapshot:'+case['purpose_membership']['snapshot_digest'] in result['evidence_refs']
    assert pigs==before


@pytest.mark.parametrize('status,on_farm',[('Active',True),('Active',False),('Died',True),('Died',None),
    ('Unknown',False),('',False),('Held',True),('Inactive',False),('Died','False'),('Died',0)])
def test_uncertain_or_current_unknown_extras_still_block(status,on_farm):
    case,pigs,history=one_member_retained_proof()
    pigs.append({'pig_id':'PIG-EXTRA','tag_number':None,'litter_id':'COHORT-A','purpose':'Unknown',
        'status':status,'on_farm':on_farm})
    assert project(case,pigs,history) is None


@pytest.mark.parametrize('status',['Died','Dead','Deceased','Sold','Culled'])
def test_departed_recorded_obligation_is_never_waived(status):
    case,pigs,history=one_member_retained_proof()
    pigs[0].update(status=status,on_farm=False)
    assert project(case,pigs,history) is None


@pytest.mark.parametrize('extra_status,extra_on_farm,completed',[('Died',False,True),('Active',True,False),('Died',True,False)])
def test_postgres_one_member_correction_with_historical_litter_rows(purpose_db,monkeypatch,extra_status,extra_on_farm,completed):
    pg,connect=purpose_db
    allocation,checks,_=inputs(count=1,weight_day=DAY-timedelta(days=1))
    allocation['pigs'][0]['tag_number']='106';checks['rows'][0]['canonical']['tag_number']='106'
    raw=sources._purpose_review_candidates({'purpose_work':build_purpose_work(allocation,checks,analysis_date=DAY)},
        now=pg.now,today=DAY,observed_at=pg.now)[0]
    pg.seed([raw])
    with connect() as db:
        db.execute("update public.pigs set tag_number='106' where pig_id='PIG-SYNTHETIC-0000'")
        db.execute("update public.pigs set purpose='Sale' where pig_id='PIG-SYNTHETIC-0001'")
        for i in range(2):
            db.execute("insert into public.pigs values(%s,null,'COHORT-A','Unknown',%s,%s,now())",
                (f'PIG-HISTORICAL-{i}',extra_status,extra_on_farm))
        db.execute("update app_private.oom_manager_cases set status='waiting_reassessment',last_delivery_digest=evidence_digest,last_delivery_at=%s",(pg.now,))
        before=db.execute('select case_id,generation,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases').fetchone()
        other_rows=db.execute("select * from public.pigs where pig_id<>'PIG-SYNTHETIC-0000' order by pig_id").fetchall()
        record=db.execute("select event_payload->'purpose_membership' from app_private.oom_manager_case_events where event_payload ? 'purpose_membership'").fetchone()[0]
        assert record['member_ids']==['PIG-SYNTHETIC-0000'] and len(record['obligations'])==1
    execute_real_correction(connect,monkeypatch,['PIG-SYNTHETIC-0000'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    monkeypatch.setattr(completion,'connect_bounded_read',connect)
    for name in ('_herdmaster_retained','_herdmaster_advisories','_rootline','_herdmaster','_sam','_beacon','_delivery_gaps','_runtime'):
        monkeypatch.setattr(sources,name,lambda _now:[])
    rows=sources.collect_manager_candidates(now=pg.now)
    assert len(rows)==int(completed)
    if completed:
        assert rows[0]['terminal_state']=='completed'
        result=pg.cycle(rows,deliver=lambda *_a,**_k:pytest.fail('completion cannot send'))
        assert result['success'] and result['candidates_changed']==1
        assert completion.collect_purpose_completions(pg.now,connect=connect)==[]
        pg.now+=timedelta(minutes=6)
        assert pg.cycle(rows,deliver=lambda *_a,**_k:pytest.fail('replay cannot send'))['success']
    with connect() as db:
        actual=db.execute('select case_id,generation,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases').fetchone()
        assert actual==(before[0],before[1]+int(completed),before[2],before[3])
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]==int(completed)
        assert db.execute("select purpose from public.pigs where pig_id='PIG-SYNTHETIC-0000'").fetchone()[0]=='Sale'
        assert db.execute("select * from public.pigs where pig_id<>'PIG-SYNTHETIC-0000' order by pig_id").fetchall()==other_rows
        assert db.execute('select count(*) from public.operational_events').fetchone()[0]==1
        assert db.execute("select count(*) from public.pig_purpose_correction_batches where status='executed'").fetchone()[0]==1
