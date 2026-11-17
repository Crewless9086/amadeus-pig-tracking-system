"""Real scheduled gateway/runtime/coordinator/sender; I/O-only synthetic delays."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import datetime as datetime_module
import json
import pytest
from modules.telemetry import rootline_cycle_budget as budget
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_ewelink_readback as provider
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_ewelink_request_budget import RequestBudget
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from tests.test_rootline_final_bc_snapshot import Journey
from tests.test_rootline_execution_runtime import NOW, controller
from tests.test_rootline_ifttt_transport import Response
from tests.test_rootline_active_supervision import ENV, HEADERS, ScheduleStore, payload
from tests.rootline_four_camp_budget_fixture import ALL_FLAGS


class ScheduledJourney(Journey):
    def __init__(self, monkeypatch, zone="B12345", *, full_seconds=35):
        super().__init__(monkeypatch, zone)
        self.source.update(ALL_FLAGS, ROOTLINE_IFTTT_MAKER_KEY="offline-only")
        self.channel = {"B12345":1,"C12345":2,"E12345":3,"A12345":4}[zone]
        self.elapsed = 0.0
        self.events = []
        self.full_seconds = full_seconds
        self.final_delay = 0
        self.begin_delay = 0
        self.output = "OFF"
        self.controls = []
        self.evidence_reads = 0
        self.schedules = ScheduleStore()
        self.schedules.rows["prior:outcome"] = {"specialist":"ROOTLINE", "status":"completed",
            "next_due_at":(NOW+timedelta(minutes=30)).isoformat()}
        monkeypatch.setattr(budget.time, "monotonic", lambda: self.elapsed)
        journey = self
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                value = NOW + timedelta(seconds=journey.elapsed)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        monkeypatch.setattr(datetime_module, "datetime", Clock)
        import socket
        monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))
        monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("network forbidden"))
        def read(**kwargs):
            self.spend("routine_snapshot" if kwargs.get("routine_read") else "full_snapshot",
                16 if kwargs.get("routine_read") else self.full_seconds)
            budget.remaining_seconds()
            value = controller("READ-" + str(len(self.reads)+1))
            value.update(retrieved_at=self.now.isoformat(), trusted_receipt_at=self.now.isoformat(),
                current_outputs_authoritative=True, actuation_configuration_safe=False,
                timers_enabled=True, commissioned_baseline_id=None)
            for row in value["channels"]:
                row.update(native_auto_off_enabled=False, native_auto_off_seconds=0)
            self.reads.append(deepcopy(value))
            if len(self.reads) == 2:
                self.final_change(value)
                self.spend("final_read_extra", self.final_delay)
                budget.remaining_seconds()
            if self.output == "ON":
                value["channels"][self.channel-1]["output_state"] = "ON"
            return value
        monkeypatch.setattr(provider, "_read_bound_device", read)
        # Restore the real set_state -> bound sender path; replace only HTTP I/O.
        monkeypatch.delattr(self.transport, "set_state")
        def http_open(req, **kwargs):
            state = "OFF" if "_off/" in req.full_url else "ON"
            self.calls.append({"state":state, "body":json.loads(req.data)})
            self.output=state
            self.spend("HTTP "+state, 1)
            return Response()
        self.transport.http_open = http_open
        def begin(_budget, **kwargs):
            self.spend("locked ON admission", self.begin_delay)
            return self.elapsed + 10
        monkeypatch.setattr(RequestBudget, "begin_on", begin)
        original_store = self.store
        self.backing = original_store
        def store(action, item):
            self.spend("store "+action, .7)
            return original_store(action,item)
        self.store = store

    def spend(self, kind, seconds):
        self.events.append((kind, self.elapsed, seconds))
        self.elapsed += seconds
        self.now = NOW + timedelta(seconds=self.elapsed)

    def loader(self, **kwargs):
        self.spend("fresh evidence", 10)
        self.evidence_reads += 1
        return super().loader(**kwargs)

    def authority(self, *args):
        self.spend("fresh authority", 4)
        return super().authority(*args)

    def cycle(self, **kwargs):
        self.transport.environ = kwargs["environ"]
        value = self.run(**kwargs)
        self.controls.append(value)
        return value

    def gateway(self):
        source = {**ENV, **self.source}
        def managed(**kwargs):
            assert budget.work_deadline() == budget.on_deadline() == 140
            with budget.mandatory_safety():
                self.spend("owned safety", 22)
            return {"success":True,"status":"no_active_managed_devices","hardware_commands":0}
        return handle_rootline_reassessment_trigger(
            payload(due_at=NOW.isoformat(), trigger_timestamp=NOW.isoformat(),
                evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat()), HEADERS, source,
            specialist_loader=lambda **k: pytest.fail("optional report unexpectedly run"),
            state_store=lambda *a:{"success":True}, schedule_store=self.schedules,
            scheduler_now=NOW, family_delivery=lambda *a, **k:{"success":True},
            active_supervision_cycle=lambda **k:{"success":True,"status":"no_active_irrigation",
                "active_execution_found":False}, managed_device_cycle=managed,
            execution_cycle=self.cycle)

    def assert_no_claim(self):
        assert not self.calls and not self.capacities
        assert not any(action=="claim_before_on" for action,_ in self.backing.rows)


@pytest.mark.parametrize("zone", ["B12345", "C12345", "A12345", "E12345"])
def test_scheduled_gateway_one_fresh_final_snapshot_real_sender_and_replay(monkeypatch, zone):
    j=ScheduledJourney(monkeypatch,zone)
    result,status=j.gateway()
    assert j.controls[0]["status"]=="segment_started", j.controls
    assert [c["state"] for c in j.calls]==["ON"]
    assert len(j.reads)==3  # routine initial, full final, post-ON receipt
    assert j.evidence_reads==j.authority_calls==2
    assert len(j.capacities)==1
    assert sum(a=="claim_before_on" for a,_ in j.backing.rows)==1
    assert j.backing.active["stop_mode"]=="scheduled"
    assert j.backing.active["native_fail_stop_deadline"] is None
    assert next(t for k,t,_ in j.events if k=="HTTP ON")<140
    replay,_=j.gateway()
    assert replay["status"]=="scheduled_reassessment_replayed_noop"
    assert len(j.calls)==1


@pytest.mark.parametrize("change", [
    lambda s:s.update(device_id="wrong"), lambda s:s.update(online=False),
    lambda s:s.update(current_outputs_authoritative=False),
    lambda s:s.update(response_digest=""), lambda s:s.update(provider_control_calls=False),
    lambda s:s["channels"][0].update(channel=True),
    lambda s:s["channels"][1].update(channel=1),
    lambda s:s["channels"][3].update(output_state="ON"),
    lambda s:s.update(retrieved_at=(NOW-timedelta(minutes=6)).isoformat()),
    lambda s:s.update(trusted_receipt_at=(NOW+timedelta(minutes=10)).isoformat()),
])
def test_scheduled_final_unknown_changed_or_manual_output_refuses_on(monkeypatch,change):
    j=ScheduledJourney(monkeypatch);j.final_change=change
    j.gateway();j.assert_no_claim()
    assert len(j.reads)==2


@pytest.mark.parametrize("case", ["rain", "revoked", "authority_error", "deadline", "offline"])
def test_scheduled_fresh_weather_authority_and_deadline_still_fail_closed(monkeypatch,case):
    j=ScheduledJourney(monkeypatch)
    if case=="rain":j.evidence_change=lambda e:e["weather"].update(rain_rate_mm_h=5,rain_today_mm=5)
    elif case=="revoked":j.revoke=True
    elif case=="authority_error":j.authority_error=True
    elif case=="deadline":j.final_delay=100
    else:
        def fail(s):raise RuntimeError("provider unavailable")
        j.final_change=fail
    j.gateway();j.assert_no_claim()
    assert len(j.reads)<=2


@pytest.mark.parametrize("field,value", [("scheduled_generation","wrong"),
    ("scheduled_authoritative",False),("response_digest","wrong"),("channel",True)])
def test_scheduled_safety_binding_cannot_be_substituted(monkeypatch,field,value):
    j=ScheduledJourney(monkeypatch)
    j.check_change=lambda c:replace(c,safety={**c.safety,field:value})
    j.gateway();j.assert_no_claim()


@pytest.mark.parametrize("field,value", [("controller_safety_generation","wrong"),
    ("stop_mode","native"),("controller_response_digest","wrong"),("channel",True)])
def test_scheduled_artifact_binding_cannot_be_substituted(monkeypatch,field,value):
    j=ScheduledJourney(monkeypatch)
    j.check_change=lambda c:replace(c,artifact={**c.artifact,field:value})
    j.gateway();j.assert_no_claim()


def test_expired_final_sender_never_issues_on_and_scheduled_off_still_works(monkeypatch):
    from modules.telemetry.rootline_ewelink_request_budget import bind_execution_transport
    j=ScheduledJourney(monkeypatch);j.begin_delay=141
    j.gateway()
    assert not any(c["state"]=="ON" for c in j.calls)
    claim=next(item for action,item in j.backing.rows if action=="claim_before_on")
    with budget.cycle_budget(deadline=1):
        with budget.mandatory_safety():
            off=bind_execution_transport(j.transport,claim).set_state(device_id=claim["device_id"],
                channel=claim["channel"],state="OFF",idempotency_key=claim["execution_id"]+":OFF:1")
    assert off["accepted_unambiguous"] is True
    assert j.calls[-1]["state"]=="OFF"
