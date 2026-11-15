"""Bounded proposed local cap amendment; production admission, offline boundaries."""
from datetime import timedelta
import pytest
from modules.telemetry import rootline_ewelink_request_budget as budget
from tests.test_rootline_ewelink_request_budget import MemoryBudget, ENV, NOW, snapshot, fail


def seeded(used=40000,recent=0):
    value=MemoryBudget(); scope=budget.scope_digest(value.environ,"eu")
    value.backend.events.append({"at":NOW-timedelta(hours=1),"units":used-recent,
        "detail":{"scope":scope,"region":"eu"}})
    if recent:value.backend.events.append({"at":NOW,"units":recent,"detail":{"scope":scope,"region":"eu"}})
    return value


def charged(value):return sum(row["units"] for row in value.backend.events)


def reserve(value,identity="BH"):
    return value.reserve_for_on(execution_id=identity,device_id="1002851416",channel=1,
        device_type="borehole_pump_power",region="eu")


def test_exact_cap_and_original_limits_reserves_unchanged():
    assert budget.LOCAL_ROLLING_LIMIT==41000
    assert budget.FIVE_MINUTE_LIMIT==250 and budget.ROLLING_DAYS==31
    assert budget.DUTY_CAPACITY=={"irrigation_zone_valve":87,"borehole_pump_power":45,
        "fertilizer_mixer":24,"fertilizer_injection_valve":79}


@pytest.mark.parametrize("used",[40999,41000])
def test_each_attempt_obeys_new_exact_monthly_boundary_without_reset(used):
    value=seeded(used)
    if used==40999:
        value.dispatch(region="eu",endpoint="/v2/family",send=lambda _: {})
        assert charged(value)==41000
    with pytest.raises(budget.RequestBudgetUnavailable,match="rolling_capacity"):
        value.dispatch(region="eu",endpoint="/v2/family",send=lambda _: pytest.fail("past cap"))
    assert charged(value)==41000


def test_reserve_preserves_exact_capacity_and_final_proof_at_cap():
    value=seeded(40955);permit=reserve(value)
    assert value.backend.state["reserves"]["BH"]["remaining"]==45
    value.begin_on(execution_id="BH",permit=permit,device_id="1002851416",channel=1)
    with pytest.raises(budget.RequestBudgetUnavailable,match="rolling_capacity"):snapshot(value)
    with budget.execution_duty({"execution_id":"BH","device_id":"1002851416","channel":1}):
        assert len(snapshot(value,device="1002851416"))==3
    assert charged(value)==40958 and value.backend.state["reserves"]["BH"]["remaining"]==42
    with pytest.raises(budget.RequestBudgetUnavailable,match="capacity_unavailable"):reserve(value,"SECOND")
    assert charged(value)==40958


@pytest.mark.parametrize("recent",[249,250])
def test_original_burst_limit_still_refuses_new_reserve(recent):
    value=seeded(40000,recent)
    with pytest.raises(budget.RequestBudgetUnavailable,match="capacity_unavailable"):reserve(value)
    assert charged(value)==40000


@pytest.mark.parametrize("code",[403,412])
def test_provider_refusal_is_charged_and_cannot_be_overridden_by_new_cap(code):
    value=seeded()
    with pytest.raises(Exception,match="sanitized"):snapshot(value,send=fail(code=code))
    assert charged(value)==40001
    with pytest.raises(budget.RequestBudgetUnavailable):snapshot(value)
    with pytest.raises(budget.RequestBudgetUnavailable):reserve(value)
    assert charged(value)==40001


def test_actual_two_independent_four_hour_borehole_windows_after_changeover_reads(monkeypatch):
    from tests.test_rootline_continuous_demand import MinuteJourney
    journey=MinuteJourney(monkeypatch)
    journey.source.update(ROOTLINE_AUTONOMOUS_BC_ENABLED="false",ROOTLINE_A_ENABLED="false",
        ROOTLINE_E_ENABLED="false",ROOTLINE_FERTILIZER_MIXING_ENABLED="false",
        ROOTLINE_FERTILIZER_INJECTION_ENABLED="false",ROOTLINE_BOREHOLE_ENABLED="true")
    scope=budget.scope_digest(journey.source,"eu")
    journey.client.backend.events.append({"at":journey.start-timedelta(hours=1),"units":40000,
        "detail":{"scope":scope,"region":"eu"}})
    for _ in range(2):journey.transport.read_output_state(device_id="1002851416",channel=1)
    journey.tick(0,parent=False,allow_borehole=True)
    first=journey.borehole["execution_id"]
    for minute in range(1,242):journey.tick(minute,parent=False)
    assert journey.borehole is None
    journey.tick(242,parent=False,allow_borehole=True)
    second=journey.borehole["execution_id"]
    assert first!=second
    for minute in range(243,485):journey.tick(minute,parent=False)
    assert journey.borehole is None and journey.client.backend.state["reserves"]=={}
    assert [row["state"] for row in journey.commands]==["on","off","on","off"]
    assert len(journey.reads)==72 and charged(journey.client)==40072
    assert max(row["recent"]+row["remaining"] for row in journey.admissions)<=250
    print("TWO_BOREHOLE_WINDOWS",{"requests":72,"rolling_after":40072,"distinct_executions":2,
        "commands":journey.commands,"remaining_reserves":journey.client.backend.state["reserves"]})
