"""Conditional 31-day traffic qualification; no provider or wall-clock waiting.

Every HTTP edge executes production admission/pacing/hold/reserve logic; only
persistence, transport and time are synthetic. Source-path integration is in the
runtime, injector, manager/PostgreSQL tests. This is not a farm-demand forecast.
"""
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import heapq
import json
import time

from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure
from tests.test_rootline_ewelink_request_budget import MemoryBudget, Backend, ENV, fail

START = datetime(2026, 11, 1, tzinfo=timezone.utc)
DEVICES = {"parent": ("100204e9bc", 1, "irrigation_zone_valve"),
    "injector": ("100204d497", 1, "fertilizer_injection_valve"),
    "mixer": ("100204d497", 2, "fertilizer_mixer"),
    "borehole": ("1002851416", 1, "borehole_pump_power")}


class TraceBudget(MemoryBudget):
    def __init__(self, backend=None):
        super().__init__(backend)
        if not hasattr(self.backend, "month"):
            self.backend.now = START
            self.backend.month, self.backend.recent = deque(), deque()
            self.backend.totals = Counter()
            self.backend.by_purpose = Counter()
            self.backend.digest = hashlib.sha256()
            self.backend.max_recent = 0
            self.backend.max_reserved = 0
            self.backend.purpose = ""
            self.backend.last_send = None
            self.backend.minimum_spacing = float("inf")
    def _counts(self, connection, now, **kwargs):
        for rows, age in ((connection.month,timedelta(days=31)), (connection.recent,timedelta(minutes=5))):
            while rows and rows[0] < now-age:
                rows.popleft()
        return len(connection.month), len(connection.recent)
    def _append(self, state, *, action, attempt_units=0, detail=None):
        self.backend.state = deepcopy(state)
        self.backend.totals[action] += 1
        self.backend.digest.update(json.dumps({"at":self.backend.now.isoformat(), "action":action,
            "units":attempt_units, "purpose":self.backend.purpose},sort_keys=True).encode())
        if attempt_units:
            self.backend.month.append(self.backend.now)
            self.backend.recent.append(self.backend.now)
            self.backend.by_purpose[self.backend.purpose] += attempt_units
        self.backend.max_recent = max(self.backend.max_recent, self._counts(self.backend,self.backend.now)[1])
        self.backend.max_reserved = max(self.backend.max_reserved,
            sum(row["remaining"] for row in state["reserves"].values()))
    def dispatch(self, *, region, endpoint, send):
        def traced(timeout):
            if self.backend.last_send is not None:
                self.backend.minimum_spacing = min(self.backend.minimum_spacing,
                    (self.backend.now-self.backend.last_send).total_seconds())
            self.backend.last_send = self.backend.now
            return send(timeout)
        # The production worker wrapper is independently qualified with real
        # process races and slow bodies. This deterministic trace uses its body.
        return self._dispatch(region=region,endpoint=endpoint,send=traced,deadline=time.monotonic()+20)


def simulate_month():
    client = TraceBudget()
    queue, serial, active = [], [0], {}
    results = Counter()
    def schedule(day, minute, kind, **kw):
        serial[0] += 1
        heapq.heappush(queue,(START+timedelta(days=day,minutes=minute),serial[0],kind,kw))
    for day in range(31):
        for minute in range(1440):
            schedule(day,minute,"idle_eligibility")
        # Both real manager collection phases, including repeated refresh demand.
        for minute in range(2,1440,5):
            schedule(day,minute,"read",purpose="manager_initial",optional="mixer_readiness",device=DEVICES["mixer"][0])
            schedule(day,minute+0.1,"read",purpose="manager_refresh",optional="mixer_readiness_delivery",device=DEVICES["mixer"][0])
        for hour in range(24):
            identity=f"BH-{day}-{hour}"
            schedule(day,hour*60,"start",identity=identity,kind_name="borehole",pre=2)
            schedule(day,hour*60+58,"stop",identity=identity)
        for number, hour in enumerate((0,6,12,18)):
            parent=f"P-{day}-{number}"
            schedule(day,hour*60+1,"start",identity=parent,kind_name="parent",pre=3)
            for pulse, offset in enumerate((11,24)):
                identity=f"I-{day}-{number}-{pulse}"
                schedule(day,hour*60+offset,"read",identity=parent,purpose="injection_planning_parent",device=DEVICES["parent"][0])
                schedule(day,hour*60+offset+0.1,"start",identity=identity,kind_name="injector",pre=3,parent=parent)
                for minute in (1,2):
                    schedule(day,hour*60+offset+minute,"read",identity=parent,purpose="active_packet_parent",device=DEVICES["parent"][0])
                    for repeat in (0,.1):
                        schedule(day,hour*60+offset+minute+repeat,"read",identity=identity,purpose="active_injector_parent",device=DEVICES["parent"][0])
                schedule(day,hour*60+offset+3,"stop",identity=identity)
            schedule(day,hour*60+37,"read",identity=parent,purpose="final_flush",device=DEVICES["parent"][0])
            schedule(day,hour*60+59,"stop",identity=parent)
        for number, minute in enumerate((3,363,723)):
            identity=f"M-{day}-{number}"
            schedule(day,minute,"start",identity=identity,kind_name="mixer",pre=2)
            schedule(day,minute+10,"stop",identity=identity)
        # Twelve full manual/support reads daily: explicit conditional bound.
        purposes=("owner_api","delegated_preview","protected_preview","commissioning_reader",
            "parent_resolution","supported_diagnostic")
        for index in range(12):
            schedule(day,90+index*90,"read",purpose=purposes[index%6],device=DEVICES["parent"][0])
        # A sanitized transient error and recovery, while normal scheduled work
        # continues through the shared hold. No error-triggered token refresh.
        schedule(day,1430,"read",purpose="transient_fault",device=DEVICES["parent"][0],failure=True)
        schedule(day,1432,"read",purpose="due_recovery_probe",device=DEVICES["parent"][0])
    schedule(0,31,"read",purpose="oauth_callback",device=DEVICES["parent"][0],oauth=True)
    for day in (15,30):
        schedule(day,31,"read",purpose="genuine_expiry_refresh",device=DEVICES["parent"][0],refresh=True)

    def snapshot(device, purpose, identity=None, optional=None, failure=False, refresh=False, oauth=False):
        client.backend.purpose = purpose
        from contextlib import nullcontext
        try:
            with budget.execution_duty({"execution_id":identity} if identity else {}), \
                    (budget.optional_observation(optional) if optional else nullcontext()):
                with budget.snapshot_group(expected_device=device,environ=ENV,region="eu") as group:
                    if oauth or refresh:
                        client.dispatch(region="eu",endpoint="/v2/user/oauth/token" if oauth else "/v2/user/refresh",send=lambda _: {})
                    for endpoint in ("/v2/family","/v2/device/thing","/v2/device/thing/status"):
                        client.dispatch(region="eu",endpoint=endpoint,
                            send=fail(code=None,http=503) if failure else lambda _: {})
                    group["normalized_complete"] = True
            results["complete_snapshots"] += 1
            return True
        except (budget.RequestBudgetUnavailable,OAuthFailure) as exc:
            results["refusal:"+str(exc)] += 1
            return False
    prior_date = START.date()
    while queue:
        at,_,kind,kw=heapq.heappop(queue)
        if at.date() != prior_date:
            client = TraceBudget(client.backend)  # Fresh process projection.
            prior_date = at.date()
            results["restarts"] += 1
        client.backend.now=max(client.backend.now,at)
        if kind=="idle_eligibility":
            # Existing no-work semantic check must never require a device read.
            value=build_execution_eligibility(plan={"candidate_tasks":[]},evidence={},controller=None,
                now=client.backend.now,_provider_preflight=True)
            assert value["eligible"] is False and value.get("provider_read_required") is not True
            results["minute_ticks"] += 1
            continue
        identity=kw.get("identity")
        if kind=="start":
            device,channel,device_type=DEVICES[kw["kind_name"]]
            for step in range(kw["pre"]):
                if not snapshot(device if step<2 or kw["kind_name"]!="injector" else DEVICES["parent"][0],
                        kw["kind_name"]+"_preclaim"):
                    break
            else:
                try:
                    permit=client.reserve_for_on(execution_id=identity,device_id=device,channel=channel,
                        device_type=device_type,region="eu")
                    if kw["kind_name"]=="injector" and not snapshot(DEVICES["parent"][0],"injector_final_parent",identity):
                        continue
                    client.begin_on(execution_id=identity,permit=permit,device_id=device,channel=channel)
                    active[identity]=(device,channel)
                    results["on:"+kw["kind_name"]] += 1
                    snapshot(device,kw["kind_name"]+"_start_proof",identity)
                except budget.RequestBudgetUnavailable as exc:
                    results["start_deferred:"+str(exc)] += 1
            continue
        if kind=="stop":
            if identity not in active: continue
            device,channel=active[identity]
            results["off_commands"] += 1  # OFF never calls the eWeLink gate.
            if snapshot(device,"shutdown_proof",identity):
                client.release_after_off(identity,device_id=device,channel=channel,evidence={
                    "authoritative":True,"state":"OFF","device_id":device,"channel":channel,
                    "retrieved_at":client.backend.now.isoformat(),"response_digest":"f"*64})
                del active[identity]
            continue
        if identity and identity not in active: continue
        snapshot(**kw)
    assert not active, active
    assert not client.backend.state["reserves"], client.backend.state["reserves"]
    return {"scenario":"conditional31day_all_callers", "minute_ticks":results["minute_ticks"],
        "counted_attempts":sum(client.backend.by_purpose.values()),"by_purpose":dict(client.backend.by_purpose),
        "results":dict(results),"maximum_rolling_five_minutes":client.backend.max_recent,
        "maximum_unspent_reserved_capacity":client.backend.max_reserved,
        "minimum_actual_send_spacing_seconds":client.backend.minimum_spacing,
        "unresolved_reserves":0,"trace_sha256":client.backend.digest.hexdigest(),
        "unknowns":["provider entitlement","prior/provider usage","provider balance","external callers","actual farm demand"]}


def test_complete_conditional_31_day_all_caller_workload_fits():
    result=simulate_month()
    assert result["minute_ticks"]==31*1440
    assert result["counted_attempts"] < budget.LOCAL_ROLLING_LIMIT
    assert result["maximum_rolling_five_minutes"] <= budget.FIVE_MINUTE_LIMIT
    assert result["minimum_actual_send_spacing_seconds"] >= budget.MIN_DISPATCH_INTERVAL
    assert result["results"].get("start_deferred:ewelink_active_duty_capacity_unavailable",0)==0
    assert result["results"]["on:parent"] == 31*4
    assert result["results"]["on:injector"] == 31*8
    assert result["results"]["on:borehole"] == 31*24
    assert result["results"]["on:mixer"] == 31*3


def test_all_minutely_callers_under_31_day_quota_hold_send_only_hourly_probe():
    client=TraceBudget()
    for minute in range(31*1440):
        client.backend.now=START+timedelta(minutes=minute)
        # Two independent consumers on every minute, with durable state reused.
        for caller in ("automatic", "manual"):
            client.backend.purpose=caller
            try:
                with budget.snapshot_group(expected_device="100204e9bc",environ=ENV,region="eu"):
                    client.dispatch(region="eu",endpoint="/v2/family",send=fail())
            except (budget.RequestBudgetUnavailable,OAuthFailure):
                pass
        if minute % 1440 == 0:
            client=TraceBudget(client.backend)
    assert sum(client.backend.by_purpose.values()) == 31*24
    assert client.backend.state["scopes"][budget.scope_digest(ENV,"eu")]["category"] == "application_call_limit"
    assert client.backend.state["provider_remaining"] == "Unknown"


def test_routine_reserves_cover_all_supported_overlap_and_initial_recovery():
    client=TraceBudget()
    for kind,(device,channel,device_type) in DEVICES.items():
        permit=client.reserve_for_on(execution_id=kind,device_id=device,channel=channel,
            device_type=device_type,region="eu")
        client.begin_on(execution_id=kind,permit=permit,device_id=device,channel=channel)
    assert client.backend.max_reserved == 160
    # Every routine and allocated initial recovery snapshot consumes its own
    # reservation. Simultaneous optional pressure cannot borrow any of them.
    for kind,(device,channel,device_type) in DEVICES.items():
        with budget.execution_duty({"execution_id":kind}):
            for _ in range(sum(budget.DUTY_SNAPSHOTS[device_type])):
                with budget.snapshot_group(expected_device=device,environ=ENV,region="eu") as group:
                    for endpoint in ("/v2/family","/v2/device/thing","/v2/device/thing/status"):
                        client.dispatch(region="eu",endpoint=endpoint,send=lambda _: {})
                    group["normalized_complete"]=True
            with budget.snapshot_group(expected_device=device,environ=ENV,region="eu"):
                for _ in range(budget.DUTY_REFRESH_ALLOWANCE[device_type]):
                    client.dispatch(region="eu",endpoint="/v2/user/refresh",send=lambda _: {})
        assert client.backend.state["reserves"][kind]["remaining"]==0
    assert client._counts(client.backend,client.backend.now)[0]==160
