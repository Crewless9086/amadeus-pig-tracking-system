"""Inventory errors remain contained while bounded cause metadata survives."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import pytest
import psycopg
from modules.telemetry import rootline_irrigation_execution_store as execution
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry.rootline_failure_diagnostics import exception_failure
from modules.oom_sakkie.automatic_reassessment_scheduler import _managed_outcomes
from modules.telemetry.rootline_cycle_budget import cycle_budget,work_deadline

@pytest.mark.parametrize('phase',['connect','query'])
@pytest.mark.parametrize('error,expected',[(psycopg.errors.QueryCanceled('private SQL text'),{'cause_type':'QueryCanceled','sqlstate':'57014'}),(psycopg.OperationalError('private database URL'),{'cause_type':'OperationalError'})])
def test_real_store_wrapper_retains_only_typed_database_cause(monkeypatch,phase,error,expected):
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):raise error
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect(action):
        assert action=='load_active_auxiliaries'
        if phase=='connect':raise error
        yield Connection()
    monkeypatch.setattr(execution,'_load_connection',connect)
    with pytest.raises(execution.RootlineExecutionStoreUnavailable) as caught:
        execution.rootline_irrigation_execution_store('load_active_auxiliaries',None)
    assert caught.value.__cause__ is error
    assert exception_failure(caught.value)=={'error_type':'RootlineExecutionStoreUnavailable','store_action':'load_active_auxiliaries',**expected}
    assert 'private' not in json.dumps(exception_failure(caught.value))

@pytest.mark.parametrize('kind',['wrapped','cycle','malformed','unknown'])
def test_inventory_failure_survives_scheduler_without_enabling_commands(kind):
    calls=[]
    def store(action,payload):
        calls.append(action)
        # Mandatory owned-device inventory is not subject to optional cycle expiry.
        assert work_deadline() is None
        if action=='load_active_auxiliaries':
            if kind=='wrapped':
                exc=execution.RootlineExecutionStoreUnavailable(action)
                exc.failure_diagnostics={'cause_type':'QueryCanceled','sqlstate':'57014','secret':'must not leak'}
                raise exc
            if kind=='cycle':
                from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded
                raise RootlineCycleDeadlineExceeded('private arbitrary text')
            if kind=='malformed':return None
            class SensitiveCustomError(Exception):pass
            raise SensitiveCustomError('private arbitrary text')
        assert action=='load_active_borehole'
        return None
    class Transport:
        def __getattr__(self,name):pytest.fail('No hardware/provider access permitted: '+name)
    with cycle_budget(1):
        result=managed._supervise_owned_devices(store=store,transport=Transport(),energy_reader=None,
            borehole_safety_reader=None,clock=lambda:datetime(2026,11,26,tzinfo=timezone.utc))
    assert calls==['load_active_auxiliaries','load_active_borehole']
    assert result['auxiliary_inventory_proven'] is False and result['borehole_inventory_proven'] is True
    row=result['outcomes'][0]
    assert row['status']=='auxiliary_inventory_unproven' and row['success'] is False and row['blocks_bc'] is True
    projected=_managed_outcomes({'outcomes':result['outcomes']})[-1]['current_failure']
    assert projected['store_action']=='load_active_auxiliaries'
    assert projected['error_type']=={'wrapped':'RootlineExecutionStoreUnavailable','cycle':'RootlineCycleDeadlineExceeded','malformed':'RootlineExecutionStoreUnavailable','unknown':'UnknownError'}[kind]
    if kind=='wrapped':assert projected['cause_type']=='QueryCanceled' and projected['sqlstate']=='57014'
    assert 'private' not in json.dumps(result) and 'secret' not in json.dumps(result)
