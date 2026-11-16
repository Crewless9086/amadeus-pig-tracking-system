import pytest
from unittest.mock import Mock
from modules.telemetry.rootline_failure_diagnostics import sanitize_failure,exception_failure
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.telemetry import rootline_borehole_commissioning as bh
from modules.oom_sakkie.automatic_reassessment_scheduler import _managed_outcomes

def test_finite_fields_reject_unknown_nonfinite_bool_and_secrets():
    assert sanitize_failure({"statement_timeout_ms":3000,"query_elapsed_ms":2,
        "dispatch_remaining_ms":False,"group_remaining_ms":float("inf"),
        "cycle_remaining_ms":-1,"sql":"secret"})=={"statement_timeout_ms":3000,"query_elapsed_ms":2}

@pytest.mark.parametrize("routine",[False,True])
def test_borehole_read_only_opt_in_and_failure_survives_projection(routine):
    exc=budget.RequestBudgetUnavailable("ewelink_request_accounting_unavailable",
        failure_diagnostics={"statement_timeout_ms":2999,"query_elapsed_ms":3001,"sql":"secret"})
    transport=Mock();transport.read_output_state.side_effect=exc
    result=bh._read_borehole(transport,routine_read=routine)
    transport.read_output_state.assert_called_once_with(device_id="1002851416",channel=1,
        **({"routine_read":True} if routine else {}))
    row=_managed_outcomes({"current_failure":result["current_failure"]})[0]
    assert row["current_failure"]["statement_timeout_ms"]==2999
    assert "secret" not in str(row)

def test_acknowledged_timeout_measured_without_extra_query(monkeypatch):
    import psycopg
    raw=Mock();raw.execute.side_effect=[None,psycopg.errors.QueryCanceled("secret SQL")]
    monkeypatch.setattr(bounded.time,"monotonic",lambda:100.0)
    cursor=bounded._CycleBudgetCursor(raw,110.0)
    with pytest.raises(psycopg.errors.QueryCanceled) as caught:cursor.execute("sensitive SQL")
    assert raw.execute.call_count==2
    assert exception_failure(caught.value)=={"error_type":"QueryCanceled","statement_timeout_ms":3000,"query_elapsed_ms":0}

def test_failed_setting_does_not_claim_acknowledgement(monkeypatch):
    import psycopg
    raw=Mock();raw.execute.side_effect=psycopg.errors.QueryCanceled("secret")
    monkeypatch.setattr(bounded.time,"monotonic",lambda:100.0)
    with pytest.raises(psycopg.errors.QueryCanceled) as caught:bounded._CycleBudgetCursor(raw,110).execute("sql")
    assert "statement_timeout_ms" not in exception_failure(caught.value)

def test_original_deadlines_sampled_before_admission(monkeypatch):
    from modules.telemetry import rootline_cycle_budget as cycle
    monkeypatch.setattr(budget.time,"monotonic",lambda:100.0)
    monkeypatch.setattr(budget,"scope_digest",lambda *args:"scope")
    client=budget.RequestBudget({});exc=ValueError("secret")
    client._admission_preimage=Mock(side_effect=exc)
    group={"scope":"scope","region":"eu","deadline":130.0}
    g=budget._group.set(group);a=budget._dispatch_audit.set({})
    try:
        with cycle.cycle_budget(deadline=140):
            with cycle.mandatory_safety():
                with pytest.raises(ValueError):client._dispatch_fenced(object(),region="eu",endpoint="x",send=None,deadline=112.0)
            assert cycle.on_deadline()==140 and cycle.work_deadline()==140
        assert exc.failure_diagnostics=={"dispatch_remaining_ms":12000,"group_remaining_ms":30000,"cycle_remaining_ms":40000}
    finally:budget._group.reset(g);budget._dispatch_audit.reset(a)

def test_routine_and_full_borehole_proof_are_equal():
    from tests.test_rootline_commissioned_device_classes import actual_shape,NOW
    from modules.telemetry.rootline_ewelink_readback import read_registered_device
    from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
    proofs=[];counts=[]
    for routine in (False,True):
        source,tokens,request,calls=actual_shape("1002851416")
        snap=read_registered_device("1002851416",token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=routine)
        proofs.append(output_evidence_from_snapshot(snap,device_id="1002851416",channel=1));counts.append(len(calls))
    assert proofs[0]==proofs[1] and counts==[3,2]
    assert bh._continuous_borehole_off(proofs[1],now=NOW)


def test_reused_actual_timeout_and_elapsed_are_preserved(monkeypatch):
    import psycopg,hashlib
    from types import SimpleNamespace
    from psycopg.pq import TransactionStatus
    raw=Mock();raw.execute.side_effect=psycopg.errors.QueryCanceled("secret")
    connection=SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.INTRANS))
    owner=bounded._CycleBudgetConnection(connection,200,reuse_local_settings=True,
        installed_timeout=1250,installed_lock_timeout=1000,read_committed=True)
    monkeypatch.setattr(bounded,"_ROOTLINE_PRIVATE_SQL_SHA256",{hashlib.sha256(b"query").hexdigest()})
    ticks=iter([100,100,100,101.25])
    monkeypatch.setattr(bounded.time,"monotonic",lambda:next(ticks))
    with pytest.raises(psycopg.errors.QueryCanceled) as caught:
        bounded._CycleBudgetCursor(raw,200,owner=owner).execute("query")
    assert raw.execute.call_count==1
    assert exception_failure(caught.value)["statement_timeout_ms"]==1250
    assert exception_failure(caught.value)["query_elapsed_ms"]==1250
    assert owner._installed_timeout is None
