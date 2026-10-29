from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib, hmac, json
import pytest
from modules.telemetry.rootline_tuya_readback import read_eskom_switch
from modules.telemetry.rootline_eskom_runtime import run_eskom_cycle, EskomObservationCache

NOW=datetime(2026,10,29,8,tzinfo=timezone.utc)
CONFIG={"ROOTLINE_ESKOM_DEVICE_ID":"synthetic-grid-001","ROOTLINE_ESKOM_SWITCH_CODE":"switch_1",
    "ROOTLINE_ESKOM_ENABLED":"true","ROOTLINE_ESKOM_ON_EVENT":"eskom_grid_on",
    "ROOTLINE_ESKOM_OFF_EVENT":"eskom_grid_off","ROOTLINE_IFTTT_MAKER_KEY":"fake-maker",
    "TUYA_CLIENT_ID":"fake-client","TUYA_CLIENT_SECRET":"fake-secret","TUYA_REGION":"eu"}

def power(**extra):
    return {"observed_at":NOW.isoformat(),"battery_soc_pct":29,"solar_power_w":0,
        "load_power_w":1000,"grid_power_w":0,"battery_power_w":1000,"battery_state":"discharging",**extra}

def canonical():
    return {"evidence_digest":"a"*64,"device_record":{"device_id":CONFIG["ROOTLINE_ESKOM_DEVICE_ID"],
        "channel":1,"provider":"ifttt_smartlife","provider_account_binding":"smartlife_owner_account",
        "device_type":"breaker","commissioning_stage":"standing_active","standing_authority":True,
        "adapter_profile":"smartlife_eskom_hysteresis_v1","safe_state":"UNCHANGED",
        "maximum_runtime_seconds":0,"native_fail_stop_seconds":0,
        "manual_isolation":"synthetic labelled isolator",
        "independent_physical_identity_proven":True,"independent_electrical_protection_proven":True,"authority_envelope":{
            "eskom_policy":"owner_30_on_35_solar_recovery_off","switch_code":"switch_1"}}}

class Store:
    def __init__(self):self.rows=[];self.fail=None
    def __call__(self,action,payload):
        if action==self.fail:raise RuntimeError('synthetic persistence failure')
        if action=="load_eskom_events":return deepcopy(self.rows)
        if action=="dispatch_eskom_command_edge":
            payload=dict(payload);sender=payload.pop("dispatch")
            outcome=sender()
            if self.fail=="record_eskom_command_outcome":raise RuntimeError("synthetic outcome failure")
            saved=self("record_eskom_command_outcome",{**payload,"outcome":outcome})
            return {**saved,"dispatched":outcome.get("command_not_sent") is not True}
        if action=="claim_eskom_before_command":
            completed=[row for row in self.rows if row["action"]=="record_eskom_completed"]
            latest=completed[-1]["execution_id"] if completed else None
            if latest!=payload.get("expected_transition_id"):
                return {"success":True,"created":False,"status":"eskom_observation_version_changed"}
        if any(row["execution_id"]==payload["execution_id"] and row["action"]==action for row in self.rows):
            return {"success":True,"created":False}
        self.rows.append({**deepcopy(payload),"action":action})
        return {"success":True,"created":True}

class Switch:
    def __init__(self):self.state="OFF";self.calls=[];self.ambiguous=False
    def read(self):return {"authoritative":True,"device_id":CONFIG["ROOTLINE_ESKOM_DEVICE_ID"],
        "online":True,"switch_code":"switch_1","state":self.state,"retrieved_at":NOW.isoformat(),
        "evidence_id":"synthetic-"+self.state}
    def send(self,state,identity):
        self.calls.append((state,identity))
        if not self.ambiguous:self.state=state
        return {"accepted_unambiguous":not self.ambiguous}

def run(store,switch,**kwargs):
    return run_eskom_cycle(power=kwargs.pop("power",power()),configuration=kwargs.pop("configuration",CONFIG),
        canonical=kwargs.pop("canonical",canonical()),store=store,now=kwargs.pop("now",NOW),readback=switch.read,
        observation_cache=kwargs.pop("observation_cache",EskomObservationCache()),
        dispatch=switch.send,**kwargs)

def test_actual_claim_command_readback_replay_and_solar_recovery():
    store,switch=Store(),Switch()
    assert run(store,switch)["status"]=="eskom_state_verified"
    assert run(store,switch)["status"]=="eskom_current_state_retained"
    grid_only=power(battery_soc_pct=36,grid_power_w=2000,battery_power_w=-1000,battery_state="charging")
    assert run(store,switch,power=grid_only)["hardware_commands"]==0
    solar=power(battery_soc_pct=35,solar_power_w=3000,battery_power_w=-2000,battery_state="charging")
    assert run(store,switch,power=solar)["status"]=="eskom_state_verified"
    assert [state for state,_ in switch.calls]==["ON","OFF"]

def test_ambiguous_dispatch_is_never_replayed_and_later_readback_reconciles():
    store,switch=Store(),Switch();switch.ambiguous=True
    assert not run(store,switch)["success"]
    assert not run(store,switch)["success"] and len(switch.calls)==1
    switch.state="ON"
    assert run(store,switch)["status"]=="eskom_command_reconciled"
    assert len(switch.calls)==1

def test_failure_after_command_keeps_effect_accounting_and_pending_claim():
    store,switch=Store(),Switch();store.fail="record_eskom_command_outcome"
    result=run(store,switch)
    assert not result["success"] and result["hardware_commands"]==1 and result["effects_unknown"]
    store.fail=None
    assert run(store,switch)["status"]=="eskom_command_reconciliation_required"
    assert len(switch.calls)==1


def test_external_matching_state_cannot_complete_a_sender_before_it_returns():
    store,switch=Store(),Switch();original=switch.send
    def interleaved(state,identity):
        switch.state=state
        nested=run(store,switch)
        assert nested["status"]=="eskom_command_reconciliation_required"
        assert not any(row["action"]=="record_eskom_completed" for row in store.rows)
        return original(state,identity)
    switch.send=interleaved
    assert run(store,switch)["status"]=="eskom_state_verified"
    assert len(switch.calls)==1


def test_stale_observer_cannot_claim_after_an_intervening_completed_transition():
    store,switch=Store(),Switch();original=store.__call__
    def racing_store(action,payload):
        if action=="claim_eskom_before_command" and not store.rows:
            store.rows.append({"action":"record_eskom_completed","execution_id":"intervening"})
        return original(action,payload)
    result=run(racing_store,switch)
    assert result["status"]=="eskom_claim_already_owned" and not switch.calls


def test_energy_expires_while_waiting_for_dispatch_edge():
    store,switch=Store(),Switch();times=iter([NOW,NOW,NOW+timedelta(seconds=2)])
    result=run(store,switch,power=power(observed_at=(NOW-timedelta(minutes=14,seconds=59)).isoformat()),
        clock=lambda:next(times))
    assert result["hardware_commands"]==0 and not switch.calls
    assert result["status"]=="eskom_command_reconciliation_required"

@pytest.mark.parametrize("change",[{"ROOTLINE_ESKOM_ENABLED":"false"},
    {"ROOTLINE_ESKOM_ON_EVENT":"wrong"},{"ROOTLINE_ESKOM_DEVICE_ID":"wrong-device"}])
def test_unconfigured_grid_has_no_reads_commands_or_bc_hold(change):
    store,switch=Store(),Switch()
    result=run(store,switch,configuration={**CONFIG,**change})
    assert result["hardware_commands"]==0 and not result["blocks_bc"] and not store.rows

def test_readback_wrong_binding_or_stale_cannot_actuate():
    store,switch=Store(),Switch();original=switch.read
    for change in ({"device_id":"other"},{"online":False},{"switch_code":"switch_2"},
            {"retrieved_at":(NOW-timedelta(minutes=3)).isoformat()}):
        switch.read=lambda:{**original(),**change}
        assert run(store,switch)["hardware_commands"]==0
    assert not store.rows and not switch.calls

class Response:
    def __init__(self,url,result):self.url=url;self.result=result
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def geturl(self):return self.url
    def getcode(self):return 200
    def read(self,_):return json.dumps({"success":True,"t":int(NOW.timestamp()*1000),"result":self.result}).encode()

def provider(*,detail=None,status=None):
    calls=[]
    def open_(req,timeout):
        assert timeout==5 and req.method=="GET" and req.full_url.startswith("https://openapi.tuyaeu.com/")
        path=req.full_url.removeprefix("https://openapi.tuyaeu.com")
        headers={k.lower():v for k,v in req.header_items()}
        token="" if path.startswith("/v1.0/token?") else "synthetic-token"
        signed="GET\n"+hashlib.sha256(b"").hexdigest()+"\n\n"+path
        expected=hmac.new(b"fake-secret",("fake-client"+token+str(int(NOW.timestamp()*1000))+signed).encode(),hashlib.sha256).hexdigest().upper()
        assert headers["sign"]==expected
        calls.append(path)
        value=({"access_token":"synthetic-token"} if not token else
            status if path.endswith("/status") and status is not None else
            [{"code":"switch_1","value":True}] if path.endswith("/status") else
            detail if detail is not None else {"id":CONFIG["ROOTLINE_ESKOM_DEVICE_ID"],"name":"Eskom Grid","online":True,
                "local_key":"MUST-NOT-LEAVE-ADAPTER"})
        return Response(req.full_url,value)
    return open_,calls

def test_tuya_signed_exact_three_gets_return_only_switch_projection():
    http,calls=provider();result=read_eskom_switch(configuration=CONFIG,now=NOW,http_open=http)
    assert result["authoritative"] and result["state"]=="ON" and len(calls)==3
    assert "local_key" not in json.dumps(result) and "token" not in json.dumps(result)

@pytest.mark.parametrize("status",[[{"code":"switch_1","value":"true"}],
    [{"code":"switch_2","value":True}],[{"code":"switch_1","value":True}]*2])
def test_tuya_wrong_duplicate_or_nonboolean_dp_is_unknown(status):
    http,_=provider(status=status)
    assert not read_eskom_switch(configuration=CONFIG,now=NOW,http_open=http)["authoritative"]

def test_tuya_wrong_device_and_host_override_are_refused():
    http,calls=provider(detail={"id":"other","name":"Eskom Grid","online":True})
    assert not read_eskom_switch(configuration=CONFIG,now=NOW,http_open=http)["authoritative"]
    assert len(calls)==2
    assert not read_eskom_switch(configuration={**CONFIG,"TUYA_REGION":"https://evil.invalid"},
        now=NOW,http_open=lambda *_:pytest.fail("no request permitted"))["authoritative"]


def test_expired_tuya_plan_has_sanitized_actionable_reason():
    class Refused(Response):
        def read(self,_):
            return json.dumps({"success":False,"code":28841002,
                "msg":"PRIVATE PROVIDER CONTENT"}).encode()
    result=read_eskom_switch(configuration=CONFIG,now=NOW,
        http_open=lambda req,**_:Refused(req.full_url,None))
    assert result["status"]=="eskom_tuya_plan_renewal_required"
    assert "PRIVATE" not in json.dumps(result)


def test_unchanged_daily_polling_is_bounded_and_cached_state_never_commands():
    store,switch,cache=Store(),Switch(),EskomObservationCache()
    switch.state="ON"; reads=[]; tick=[NOW]
    def read():
        reads.append(tick[0]); return {**Switch.read(switch),"retrieved_at":tick[0].isoformat()}
    switch.read=read
    for minute in range(24*60):
        tick[0]=NOW+timedelta(minutes=minute)
        result=run(store,switch,observation_cache=cache,now=tick[0],
            power=power(observed_at=tick[0].isoformat()))
        assert result["hardware_commands"]==0
        if minute%15:
            assert result["current_controller_state"]=="Unknown"
    assert len(reads)==96 and not switch.calls
    # A changed requested state bypasses the optimization, with fresh pre/post
    # reads and the ordinary durable command-edge checks.
    tick[0]+=timedelta(seconds=1)
    result=run(store,switch,observation_cache=cache,now=tick[0],power=power(
        observed_at=tick[0].isoformat(),battery_soc_pct=35,solar_power_w=3000,
        battery_power_w=-2000,battery_state="charging"))
    assert result["status"]=="eskom_state_verified" and len(reads)==98
    assert len(switch.calls)==1 and switch.calls[0][0]=="OFF"


def test_deadband_needs_no_provider_read_and_failed_plan_reason_survives_throttle():
    store,switch,cache=Store(),Switch(),EskomObservationCache();reads=[]
    def refused():
        reads.append(1)
        return {"authoritative":False,"status":"eskom_tuya_plan_renewal_required"}
    switch.read=refused
    deadband=run(store,switch,observation_cache=cache,power=power(battery_soc_pct=33))
    assert deadband["readback_not_requested"] and not reads
    first=run(store,switch,observation_cache=cache)
    second=run(store,switch,observation_cache=cache,now=NOW+timedelta(minutes=1))
    assert first["status"]==second["readback_status"]=="eskom_tuya_plan_renewal_required"
    assert not second["success"] and len(reads)==1 and not store.rows


def test_concurrent_same_decision_cannot_duplicate_read_or_use_cached_evidence():
    store,switch,cache=Store(),Switch(),EskomObservationCache();original=switch.read;reads=[]
    def read():
        if not reads:
            reads.append(1)
            nested=run(store,switch,observation_cache=cache)
            assert nested["status"]=="eskom_readback_poll_deferred"
            assert not nested["success"] and nested["hardware_commands"]==0
        return original()
    switch.read=read
    assert run(store,switch,observation_cache=cache)["status"]=="eskom_state_verified"
    assert len(switch.calls)==1
