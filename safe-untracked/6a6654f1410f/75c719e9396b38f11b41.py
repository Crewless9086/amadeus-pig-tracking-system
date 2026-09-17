import io, json
from modules.telemetry.rootline_borehole_contract import build_preview, classify_fail_stop_capabilities
from modules.telemetry.rootline_tuya_provider import TuyaProvider

ENV={"TUYA_CLIENT_ID":"id","TUYA_CLIENT_SECRET":"secret","TUYA_EXPECTED_BOREHOLE1_DEVICE_ID":"device","TUYA_REGION":"EU"}
def response(value):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*_): pass
    return R(json.dumps(value).encode())
def opener(req,timeout=0):
    if "token?" in req.full_url:return response({"success":True,"result":{"access_token":"token"}})
    if req.method=="POST":return response({"success":True,"result":True,"t":1})
    if req.full_url.endswith("/specification"):return response({"success":True,"result":{"functions":[{"code":"switch_1"},{"code":"countdown_1"}],"status":[]},"t":2})
    if req.full_url.endswith("/status"):return response({"success":True,"result":[{"code":"switch_1","value":False},{"code":"countdown_1","value":0},{"code":"cur_current","value":0},{"code":"cur_power","value":0},{"code":"fault","value":0}],"t":3})
    return response({"success":True,"result":{"id":"device","name":"Borehole 1 Pump","online":True},"t":1})

def test_zero_command_discovery_and_safe_preview():
    read=TuyaProvider(ENV,http_open=opener).discover(); preview=build_preview(read,
      ifttt_mapping_owner_verified=True,physical_owner_present=True,
      restoration_setting_unavailable=True,electrical_isolation_immediately_available=True)
    assert read["switch"]=="OFF" and read["provider_commands"]==0
    assert preview["blockers"]==[] and preview["command_authority"] is False
    assert preview["power_restoration_state"]=="Unknown" and preview["maximum_seconds"]==300

def test_adapter_has_no_command_surface():
    provider=TuyaProvider(ENV,http_open=opener)
    assert not hasattr(provider,"set_on_with_countdown") and not hasattr(provider,"set_off")

def test_preview_fails_closed_on_wrong_state_or_power():
    read=TuyaProvider(ENV,http_open=opener).discover(); read.update(switch="ON",current_ma=2)
    value=build_preview(read,ifttt_mapping_owner_verified=True,physical_owner_present=True)
    assert set(value["blockers"])=={"initial_state_not_off","initial_power_not_idle","power_restoration_risk_uncontained"}

def test_unknown_restoration_never_grants_autonomy():
    read=TuyaProvider(ENV,http_open=opener).discover()
    value=build_preview(read,ifttt_mapping_owner_verified=True,physical_owner_present=True,
      restoration_setting_unavailable=True,electrical_isolation_immediately_available=True)
    assert value["autonomous_authority_after_test"] is False
    assert value["power_restoration_containment"].startswith("supervised_test_only")

def test_cloud_off_schedule_without_independent_backup_is_not_fail_stop():
    value=classify_fail_stop_capabilities(countdown_semantics="toggle_current_state",
      timer_service={"absolute_off":True,"provider_readback":True,
                     "device_local_enforcement_proven":False},
      independent_device_backup={"automatic_fail_off":False,
                                 "independent_of_cloud_and_worker":False})
    assert value["durable_cloud_off_workflow_available"] is True
    assert value["device_native_paired_off_qualified"] is False
    assert value["supervised_on_permitted"] is False
    assert "normally-off contactor" in value["minimum_hardware_requirement"]

def test_enabled_on_schedule_blocks_preview():
    read=TuyaProvider(ENV,http_open=opener).discover()
    read["timers"]=[{"status":1,"functions":[{"code":"switch_1","value":True}]}]
    value=build_preview(read,ifttt_mapping_owner_verified=True,physical_owner_present=True,
      restoration_setting_unavailable=True,electrical_isolation_immediately_available=True)
    assert "enabled_provider_on_schedule" in value["blockers"]
