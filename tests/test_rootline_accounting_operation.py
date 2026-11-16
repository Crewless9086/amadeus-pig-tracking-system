"""Failure attribution over unchanged production request and recorder rails."""
from contextlib import nullcontext
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import ast,hashlib,json,os,uuid
import pytest
import psycopg
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_failure_diagnostics import exception_failure,sanitize_failure
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure
from modules.sales import sam_live_stock_launch_control as recorder
NOW=datetime.now(timezone.utc)

class Connection:
    def __init__(self,fail=None):self.fail=fail;self.row=None;self.calls=[];self.closed=False
    def __enter__(self):return self
    def __exit__(self,*args):
        if self.fail=='close':raise psycopg.errors.QueryCanceled('secret SQL parameters')
    def execute(self,sql,params=None):
        self.calls.append(sql)
        if self.fail and self.fail in sql:raise psycopg.errors.QueryCanceled('secret SQL parameters')
        if 'pg_try_advisory_xact_lock' in sql:self.row=(True,'read committed',42)
        elif 'clock_timestamp' in sql:self.row=(NOW,42,True)
        return self
    def fetchone(self):return self.row
    def fetchall(self):return []

def durable(exc):
    converted=OAuthFailure('ewelink_request_accounting_unavailable',failure_diagnostics=exc.failure_diagnostics)
    return exception_failure(converted)

@pytest.mark.parametrize('method,fragment,operation',[
    ('preimage','with stamp as materialized','admission_preimage'),
    ('load',"select review_json->'ewelink_request_budget'",'ledger_load'),
    ('counts','coalesce(sum','counts_fallback'),
    ('terminal','with ranked as','reserve_terminal_read'),
    ('clock','select clock_timestamp()','clock_read'),
    ('acquire','pg_try_advisory_xact_lock','fence_acquire'),
    ('setup','set transaction isolation','fence_setup'),
    ('close','close','fence_close'),
])
def test_exact_statement_survives_locked_oauth_and_durable_sanitization(method,fragment,operation):
    connection=Connection(fragment);client=budget.RequestBudget({},connect_factory=lambda:connection)
    with pytest.raises(budget.RequestBudgetUnavailable) as caught:
        with client._locked(read_committed=method=='setup') as db:
            if method=='preimage':client._admission_preimage(db,scope='s',region='eu')
            elif method=='load':client._load(db)
            elif method=='counts':client._counts(db,NOW,scope='s',region='eu')
            elif method=='terminal':client._terminal_rows(db,['e'])
            elif method=='clock':client._now(db)
    result=durable(caught.value)
    assert result['accounting_operation']==operation
    assert result['accounting_stage']=='locked' and result['sqlstate']=='57014'
    assert result['cause_type']=='QueryCanceled' and 'secret' not in str(result)


def test_connection_acquisition_failure_is_not_mislabeled_as_lock():
    def fail():raise psycopg.errors.QueryCanceled('secret')
    with pytest.raises(budget.RequestBudgetUnavailable) as caught:
        with budget.RequestBudget({},connect_factory=fail)._locked():pass
    assert durable(caught.value)['accounting_operation']=='connection_acquire'


def test_private_fence_clock_preserves_backend_checks_and_inner_failure():
    db=Connection('exists(select 1 from pg_locks');client=budget.RequestBudget({},connect_factory=lambda:db)
    pair=SimpleNamespace(owner=client,fence=None,backend=None)
    token=budget._private_pair.set(pair)
    try:
        with pytest.raises(budget.RequestBudgetUnavailable) as caught:
            with client._locked() as connection:client._now(connection)
        assert durable(caught.value)['accounting_operation']=='fence_clock'
    finally:budget._private_pair.reset(token)


class RecorderConnection:
    def __init__(self,fail=None,durable=False):self.fail=fail;self.durable=durable;self.calls=[];self.rowcount=0 if durable else 1
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self
    def execute(self,sql,params=None):
        self.calls.append(sql)
        if self.fail and self.fail in sql:raise psycopg.errors.QueryCanceled('sensitive SQL text')
    def fetchone(self):return (1,)

@pytest.mark.parametrize('fragment,receipt,operation',[
    ('insert into',False,'review_event_insert'),
    ('select count(*)',False,'review_event_count'),
    ('select review_event_id,review_json,created_at',True,'review_event_receipt_read'),
])
def test_recorder_does_not_swallow_exact_statement_or_sqlstate(fragment,receipt,operation):
    db=RecorderConnection(fragment,receipt)
    result,status=recorder.record_sam_live_stock_review_event({'review_event_id':'TEST'},
        database_url='synthetic',connect_factory=lambda:db,durable_receipt=receipt)
    assert status==500 and result['accounting_operation']==operation and result['sqlstate']=='57014'
    # _append deliberately copies only these safe fields, not the legacy error text.
    safe=sanitize_failure(result)
    assert safe['accounting_operation']==operation and 'sensitive' not in str(safe)


def test_append_preserves_recorder_operation_through_audit_and_outer_lock(monkeypatch):
    db=Connection();client=budget.RequestBudget({},connect_factory=lambda:db)
    monkeypatch.setattr(client,'_audit_transaction',lambda action:nullcontext(db))
    monkeypatch.setattr(recorder,'record_sam_live_stock_review_event',lambda *a,**k:({'success':False,
        'status':'sam_live_stock_review_event_write_failed','error_type':'QueryCanceled',
        'accounting_operation':'review_event_count','sqlstate':'57014','error':'secret'},500))
    with pytest.raises(budget.RequestBudgetUnavailable) as caught:
        with client._locked():client._append({'version':1},action='request_attempt_reserved')
    result=durable(caught.value)
    assert result['accounting_operation']=='review_event_count' and result['sqlstate']=='57014'
    assert result['accounting_stage']=='append' and 'secret' not in str(result)


def test_success_recorder_shape_and_sql_match_immutable_prechange_contract():
    # Captured from the prechange recorder; requires no developer checkout.
    db=RecorderConnection()
    event={'review_event_id':'SYNTHETIC','chatwoot_conversation_id':'TEST'}
    actual=recorder.record_sam_live_stock_review_event(event,database_url='synthetic',connect_factory=lambda:db)
    assert actual == ({'success': True, 'status': 'sam_live_stock_review_event_recorded', 'review_event_id': 'SYNTHETIC', 'created': True, 'chatwoot_conversation_id': 'TEST', 'conversation_event_count': 1, 'sends_customer_message': False, 'calls_chatwoot': False, 'calls_telegram': False, 'calls_n8n': False, 'creates_order': False, 'creates_quote': False, 'reserves_stock': False, 'releases_stock': False, 'changes_stock': False, 'writes_farm_data': False, 'dispatch_enabled': False, 'customer_public_output_enabled': False},201)
    assert [hashlib.sha256(sql.encode()).hexdigest() for sql in db.calls] == ['d1c2bc8dc9b56ccf49c12ad55196c2481e4b31de68ac1709bdbd414b9d728ef7', 'b5996a6c961e9e421adce2f8bc54959e7aeaf65e401651fe2fc06ac202e3bdf9']


def test_unknown_operation_and_values_are_discarded():
    assert sanitize_failure({'accounting_operation':'secret sql','url':'secret','sqlstate':'not-safe'})=={}


def test_sql_bytes_and_private_fingerprints_match_qualified_contract():
    def digest(path):
        values=sorted(n.value for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.Constant)
            and isinstance(n.value,str) and n.value.lstrip().lower().startswith(('select ','with ','insert ','set ')))
        return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()
    assert digest(Path(budget.__file__)) == '7b4e9b5b1efaa3bab773770b49c630eb087018d8ff55429fe73b2b5635ff598d'
    assert digest(Path(recorder.__file__)) == '08da6bc36305914aad464bc8cc2a4448248b5af904becc54ce0de531a7025885'



@pytest.mark.parametrize('failure,private,operation',[
    ('set_config',False,'audit_setup'),('configure',True,'audit_setup'),('commit',False,'audit_commit')])
def test_audit_setup_and_commit_keep_exact_operation(failure,private,operation):
    import threading
    from psycopg.pq import TransactionStatus
    class Audit(Connection):
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        def configure_transaction_timeouts(self,*a,**k):
            if failure=='configure':raise psycopg.errors.QueryCanceled('secret')
        def commit(self):
            if failure=='commit':raise psycopg.errors.QueryCanceled('secret')
        def close(self):self.closed=True
    audit=Audit(failure);fence=Connection();client=budget.RequestBudget({},connect_factory=lambda:fence)
    session={'owner':client,'thread':threading.get_ident(),'connection':audit,'fence':fence,'poisoned':False}
    token=budget._dispatch_audit.set(session)
    pair_token=budget._private_pair.set(SimpleNamespace(owner=client,fence=None,backend=None)) if private else None
    try:
        with pytest.raises(budget.RequestBudgetUnavailable) as caught:
            with client._locked():
                with client._audit_transaction('request_attempt_reserved'):pass
        assert durable(caught.value)['accounting_operation']==operation
        assert session['poisoned'] is True and audit.closed
    finally:
        budget._dispatch_audit.reset(token)
        if pair_token is not None:budget._private_pair.reset(pair_token)


def test_audit_readback_failure_not_lost_in_append(monkeypatch):
    db=Connection('where review_event_id=');client=budget.RequestBudget({},connect_factory=lambda:db)
    monkeypatch.setattr(client,'_audit_transaction',lambda action:nullcontext(db))
    monkeypatch.setattr(recorder,'record_sam_live_stock_review_event',lambda *a,**k:({'success':True},201))
    with pytest.raises(budget.RequestBudgetUnavailable) as caught:
        with client._locked():client._append({'version':1},action='request_attempt_reserved')
    assert durable(caught.value)['accounting_operation']=='audit_readback'


def test_recorder_transaction_exit_attribution():
    class CloseFailure(RecorderConnection):
        def __exit__(self,*args):
            if len(self.calls)==2:raise psycopg.errors.QueryCanceled('secret')
            return False
    result,status=recorder.record_sam_live_stock_review_event({'review_event_id':'TEST'},database_url='synthetic',connect_factory=CloseFailure)
    assert status==500 and result['sqlstate']=='57014'
    assert result['accounting_operation']=='review_event_transaction'
