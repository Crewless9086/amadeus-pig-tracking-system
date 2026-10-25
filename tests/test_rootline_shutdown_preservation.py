"""Exact-run shutdown evidence through canonical readers and owner suppression.

All evidence/provider/store boundaries are synthetic. No database, external
message, device, authority, or fresh operational outcome is created here.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

from modules.telemetry.rootline_irrigation_history import (
    read_canonical_irrigation_history, _attach_latest_zone_executions,
)
from modules.telemetry.rootline_irrigation_lifecycle import (
    project_execution_shutdown_exceptions, project_zone_lifecycle,
)
from modules.telemetry.rootline_specialist_result import (
    build_rootline_specialist_result, project_water_energy_plan,
)
from modules.oom_sakkie.rootline_material import rootline_material_digest, rootline_exception_material
from modules.oom_sakkie.rootline_daily_presentation import (
    owner_notification_required, compose_daily_rootline_plan, compose_daily_rootline_manager_item,
)
from modules.oom_sakkie.rootline_reassessment_lifecycle import (
    reassess_rootline, record_reassessment_delivery,
)

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
CLAIM = NOW - timedelta(hours=2)
START = CLAIM + timedelta(seconds=2)
STOP = CLAIM + timedelta(minutes=50)
DEADLINE = CLAIM + timedelta(minutes=59)


def run(identity="OLD", zone="B12345", **extra):
    return {"execution_id": identity, "zone_id": zone, "action": "mark_active", "state": "Active",
        "claimed_at": CLAIM.isoformat(), "primary_stop_deadline": DEADLINE.isoformat(),
        "native_fail_stop_deadline": (DEADLINE + timedelta(seconds=1)).isoformat(),
        "start_evidence": {"authoritative": True, "state": "ON", "retrieved_at": START.isoformat(),
                           "evidence_id": identity + "-ON"}, **extra}


def terminal(identity="OLD", zone="B12345", *, stopped=STOP, **extra):
    return run(identity, zone, action="record_completed", state="Completed", shutdown_verified=True,
        objective_satisfied=True, completed_at=stopped.isoformat(),
        shutdown_evidence={"authoritative": True, "state": "OFF", "retrieved_at": stopped.isoformat(),
                           "evidence_id": identity + "-OFF-" + stopped.isoformat()}, **extra)


def contained(identity="OLD", zone="B12345"):
    return run(identity, zone, action="contain_zone", state="ambiguous", shutdown_verified=False)


def read(rows, irrigation_rows=()):
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, params=None): self.query=query; calls.append((query, params))
        def fetchone(self): return (NOW,)
        def fetchall(self):
            if "sam_live_stock_conversation_review_events" in self.query: return [(deepcopy(row),) for row in rows]
            if "from public.irrigation_events" in self.query: return deepcopy(irrigation_rows)
            return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()
    history = read_canonical_irrigation_history(connect=Connection, now=NOW)
    assert history["status"] == "Available"
    assert len(calls) == 4
    return history


def exceptions(rows, **kwargs):
    return project_execution_shutdown_exceptions(rows, evidence_cutoff=NOW, **kwargs)


def kinds(value): return {row["kind"] for row in value}


def test_older_unresolved_survives_new_success_and_raw_unknown_metadata_is_unchanged():
    new = terminal("NEW", mystery={"untouched": [1, {"future": True}]})
    original = deepcopy(new)
    history = read([run(), contained(), new])
    zone = history["zones"]["B12345"]
    assert zone["latest_execution"] == original
    assert new == original
    assert [(r["execution_id"], r["kind"]) for r in zone["execution_exceptions"]] == [("OLD", "shutdown_unverified")]
    lifecycle = project_zone_lifecycle(zone_id="B12345", recommendation={"status": "Hold"},
        history=zone, execution=zone["latest_execution"], evidence_cutoff=NOW)
    assert lifecycle["state"] == "Held"
    assert lifecycle["execution_exceptions"] == zone["execution_exceptions"]


def test_same_identifier_in_another_zone_cannot_resolve_or_replace_raw_display():
    b, c = contained("SAME"), terminal("SAME", "C12345")
    h = read([b, c])
    assert h["zones"]["B12345"]["latest_execution"] == b
    assert h["zones"]["C12345"]["latest_execution"] == c
    assert kinds(h["zones"]["B12345"]["execution_exceptions"]) == {"shutdown_unverified"}
    assert h["zones"]["C12345"]["execution_exceptions"] == []


def test_production_reader_uses_canonical_order_for_untimed_resolution_only():
    good, bad, other = terminal(), contained(), terminal("OTHER", "C12345")
    assert read([bad, other, good])["zones"]["B12345"]["execution_exceptions"] == []
    assert kinds(read([good, other, bad])["zones"]["B12345"]["execution_exceptions"]) == {"shutdown_unverified"}
    assert kinds(exceptions([bad, good])) == {"shutdown_unverified"}
    assert kinds(exceptions([good, bad])) == {"shutdown_unverified"}


def test_canonical_reader_replay_duplicates_do_not_manufacture_resolution_or_loss():
    for rows in ([contained(), contained(), terminal(), terminal()], [terminal(), terminal(), contained(), contained()]):
        actual = read(rows)["zones"]["B12345"]["execution_exceptions"]
        expected = read([rows[0], rows[-1]])["zones"]["B12345"]["execution_exceptions"]
        assert actual == expected


@pytest.mark.parametrize("seconds", [0, 60])
def test_later_false_terminal_on_evidence_overrides_earlier_off(seconds):
    bad = run(action="record_claim_recovery", shutdown_verified=False,
        shutdown_evidence={"authoritative": True, "state": "ON", "retrieved_at": (STOP+timedelta(seconds=seconds)).isoformat()})
    for rows in permutations([terminal(), bad]):
        assert kinds(exceptions(rows)) == {"shutdown_unverified"}
    assert kinds(read([terminal(), bad])["zones"]["B12345"]["execution_exceptions"]) == {"shutdown_unverified"}


@pytest.mark.parametrize("change", [
    {"authoritative": False}, {"authoritative": "true"}, {"state": "ON"},
    {"retrieved_at": None}, {"retrieved_at": "bad"}, {"retrieved_at": "2026-10-14T10:50:00"},
    {"retrieved_at": (NOW+timedelta(seconds=1)).isoformat()},
    {"retrieved_at": (CLAIM-timedelta(seconds=1)).isoformat()},
    {"observed_at": (STOP+timedelta(seconds=1)).isoformat()},
    {"execution_id": "OTHER"}, {"zone_id": "C12345"}, {"device_id": "OTHER"}, {"channel": 99},
])
def test_invalid_or_unrelated_off_is_not_own_run_proof(change):
    row = terminal(); row["shutdown_evidence"].update(change)
    assert kinds(exceptions([row])) == {"shutdown_unverified"}


@pytest.mark.parametrize("key,value", [("shutdown_verified", "true"), ("shutdown_verified", False),
                                      ("shutdown_evidence", []), ("shutdown_evidence", "OFF")])
def test_flags_and_malformed_envelopes_fail_closed(key, value):
    row=terminal(); row[key]=value
    assert kinds(exceptions([row])) == {"shutdown_unverified"}


def test_boolean_and_off_from_different_rows_cannot_be_blended():
    flag=terminal(); flag.pop("shutdown_evidence")
    proof=terminal(); proof["shutdown_verified"]=False
    for rows in permutations([flag, proof]):
        assert kinds(exceptions(rows)) == {"shutdown_unverified"}


@pytest.mark.parametrize("cutoff", [None, "bad", "2026-10-14T12:00:00"])
def test_no_trusted_cutoff_cannot_verify_a_future_or_other_off(cutoff):
    value=project_execution_shutdown_exceptions([terminal(stopped=datetime(2099,1,1,tzinfo=timezone.utc))], evidence_cutoff=cutoff)
    assert kinds(value)=={"shutdown_unverified"}
    assert value[0]["controller_off_verified"] is False


@pytest.mark.parametrize("field", ["primary_stop_deadline", "native_fail_stop_deadline"])
@pytest.mark.parametrize("value", [None, "bad", "2026-10-14T11:00:00", "2026-10-14T09:00:00+00:00"])
def test_original_missing_invalid_or_conflicting_deadline_remains_unknown(field, value):
    original=run(); original[field]=value
    for rows in permutations([original, terminal()]):
        assert "shutdown_deadline_unavailable" in kinds(exceptions(rows))


def test_inverted_deadlines_are_not_repaired_by_later_consistent_event():
    original=run(primary_stop_deadline=(DEADLINE+timedelta(minutes=2)).isoformat())
    assert "shutdown_deadline_unavailable" in kinds(exceptions([original, terminal()]))


def test_overdue_claim_only_does_not_disappear_after_possible_on_before_mark_active():
    claim=run(action="claim_before_on", state="claimed"); claim.pop("start_evidence")
    assert kinds(exceptions([claim]))=={"shutdown_unverified"}
    assert project_execution_shutdown_exceptions([claim], evidence_cutoff=CLAIM+timedelta(minutes=1))==[]


def test_late_off_is_durable_under_permutation_replay_and_later_earlier_looking_off():
    late=terminal(stopped=DEADLINE+timedelta(minutes=5)); early=terminal()
    expected=exceptions([run(),late,early])
    assert kinds(expected)=={"off_readback_after_deadline"}
    for rows in permutations([run(),late,early]):
        assert exceptions(list(rows)+[late,early])==expected
    assert read([run(),late,early])["zones"]["B12345"]["execution_exceptions"]==expected


def test_same_provider_evidence_identity_with_conflicting_times_keeps_uncertainty():
    early,late=terminal(),terminal(stopped=DEADLINE+timedelta(minutes=2))
    late["shutdown_evidence"]["evidence_id"]=early["shutdown_evidence"]["evidence_id"]
    for rows in permutations([early,late]):
        assert "shutdown_unverified" in kinds(exceptions(rows))


@pytest.mark.parametrize("value", [[], {}, None, "unknown_action"])
def test_malformed_action_retains_raw_metadata_without_new_proof(value):
    row=run(action=value)
    assert kinds(exceptions([row]))=={"shutdown_unverified"}


def test_actual_transport_proof_shape_and_legacy_timestamp_alias_are_supported():
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    transport=object.__new__(RootlineIFTTTTransport)
    transport._snapshot=lambda device,channel:{"current_outputs_authoritative":True,
        "retrieved_at":STOP.isoformat(),"response_digest":"OFF-READ"}
    transport._channel=lambda snapshot,channel:{"output_state":"OFF"}
    proof=transport.read_output_state(device_id="synthetic",channel=1)
    row=terminal(); row["shutdown_evidence"]=proof
    assert exceptions([row])==[]
    row["shutdown_evidence"]["observed_at"]=row["shutdown_evidence"].pop("retrieved_at")
    assert exceptions([row])==[]


def specialist(rows):
    return build_rootline_specialist_result({"irrigation_history":read(rows)}, NOW.date().isoformat(), now=NOW)


def test_actual_specialist_normal_and_persisted_paths_bind_exception_identity():
    old,new=specialist([contained("OLD"),terminal("NEW")]),specialist([contained("OTHER"),terminal("NEW")])
    assert old["result_id"]!=new["result_id"]
    assert rootline_exception_material(old)[0]["execution_id"]=="OLD"
    base={"success":True,"operating_date":NOW.date().isoformat(),"evidence_generation":"SAME",
          "evidence_observed_at":NOW.isoformat(),"candidate_tasks":[]}
    first=project_water_energy_plan({**base,"recent_irrigation_history":read([contained("OLD")])},now=NOW)
    second=project_water_energy_plan({**base,"recent_irrigation_history":read([contained("OTHER")])},now=NOW)
    assert first["generation"]!=second["generation"]
    assert project_water_energy_plan(base,now=NOW)["generation"]=="SAME"


def owner_result(identity="OLD", *, late=False, state="Held"):
    row=terminal(identity,stopped=DEADLINE+timedelta(minutes=5)) if late else contained(identity)
    result=specialist([row])
    result["irrigation_lifecycle"]["B12345"]["state"]=state
    result["owner_brief"]["family_fact_needed"]=""
    result["next_reassessment"]={"trigger":"canonical_plan_reassessment","at":NOW.isoformat()}
    return result


@pytest.mark.parametrize("state", ["Held","Revalidating","Completed","Started"])
@pytest.mark.parametrize("language", ["en","af"])
def test_owner_warning_overrides_ordinary_safe_completion_and_flows_to_manager(state,language):
    result=owner_result(state=state)
    assert owner_notification_required(result) is True
    text=compose_daily_rootline_plan(result,language=language)
    manager=compose_daily_rootline_manager_item(result,language=language)
    expected="unverified shutdown" if language=="en" else "onbevestig"
    assert expected in text
    assert expected in str(manager)
    assert "Held safely" not in text and "Veilig teruggehou" not in text
    assert "controller_off_at" not in text and "OLD" not in text


@pytest.mark.parametrize("language", ["en","af"])
def test_late_off_warning_is_not_duration_or_delivered_volume_claim(language):
    text=compose_daily_rootline_plan(owner_result(late=True),language=language)
    assert ("after its deadline" if language=="en" else "ná sy sperdatum") in text
    assert "minutes" not in text and "litres" not in text


def memory():
    rows={}
    def store(action,identity,payload):
        if action=="load_identity":return rows.get(identity)
        if action=="load_delivered":return next((v for v in reversed(list(rows.values())) if v.get("delivery_state")=="delivered"),None)
        if action in {"record_observation","claim_pending"}:
            created=identity not in rows;rows.setdefault(identity,deepcopy(payload));return {"success":True,"created":created}
        if action=="mark_delivered":rows[identity].update(deepcopy(payload));return {"success":True}
        raise AssertionError(action)
    return rows,store


def reassess(result,store):
    return reassess_rootline(owner_user_id="42",chat_id="42",trigger="fresh_evidence",
        specialist_loader=lambda:result,state_store=store)


def deliver(result,store):
    assert record_reassessment_delivery(identity=result["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=result["material_digest"],delivery={"provider_delivery_confirmed":True,"provider_message_id":"synthetic"},
        state_store=store)["success"]


def test_same_prose_different_run_not_suppressed_and_identical_exception_replay_quiet():
    rows,store=memory();first=owner_result();second=owner_result("OTHER")
    assert compose_daily_rootline_plan(first)==compose_daily_rootline_plan(second)
    a=reassess(first,store);assert a["notify_owner"];deliver(a,store)
    assert reassess(first,store)["notify_owner"] is False
    b=reassess(second,store);assert b["notify_owner"];deliver(b,store)
    assert reassess(second,store)["notify_owner"] is False


@pytest.mark.parametrize("change", ["stop_deadline","controller_off_at"])
def test_same_prose_changed_material_proof_is_not_suppressed(change):
    rows,store=memory();first=owner_result(late=True);second=deepcopy(first)
    item=second["irrigation_lifecycle"]["B12345"]["execution_exceptions"][0]
    item[change]=(datetime.fromisoformat(item[change])+timedelta(seconds=1)).isoformat()
    assert compose_daily_rootline_plan(first)==compose_daily_rootline_plan(second)
    a=reassess(first,store);deliver(a,store)
    assert reassess(second,store)["notify_owner"] is True


def test_legacy_text_only_delivery_cannot_hide_current_exception():
    rows,store=memory();result=owner_result();a=reassess(result,store);deliver(a,store)
    previous=rows[a["notification_identity"]]
    for key in ("zones","owner_plan_fingerprint","owner_plan_fingerprint_version","owner_plan_reassessment"):
        previous.pop(key,None)
    previous["material_digest"]="legacy-material"
    # Separate old binding so the existing exact pending identity is not reused.
    rows["legacy"]={**rows.pop(a["notification_identity"]),"identity":"legacy"}
    assert reassess(result,store)["notify_owner"] is True


def test_exception_permutation_and_duplicates_are_stable_material():
    first=owner_result();second=deepcopy(first)
    ex=second["irrigation_lifecycle"]["B12345"]["execution_exceptions"][0]
    second["irrigation_lifecycle"]["B12345"]["execution_exceptions"]=[deepcopy(ex),deepcopy(ex)]
    assert rootline_material_digest(first)==rootline_material_digest(second)


@pytest.mark.parametrize("bad", [None,"bad",{},[None],[[1]],[{"kind":[]}],
    [{"zone_id":"B12345","execution_id":{},"kind":"shutdown_unverified"}]])
def test_malformed_exception_shapes_neither_crash_nor_invent_off_proof(bad):
    result=owner_result();result["irrigation_lifecycle"]["B12345"]["execution_exceptions"]=bad
    assert rootline_exception_material(result)==[]
    assert owner_notification_required(result) is False
    assert "OFF verified" not in compose_daily_rootline_plan(result)
    rootline_material_digest(result)


def test_specialist_persisted_duplicate_exception_order_does_not_churn_identity():
    history=read([contained("OLD"),contained("OTHER")])
    base={"success":True,"operating_date":NOW.date().isoformat(),"evidence_generation":"SAME",
        "evidence_observed_at":NOW.isoformat(),"candidate_tasks":[],"recent_irrigation_history":history}
    changed=deepcopy(base)
    items=changed["recent_irrigation_history"]["zones"]["B12345"]["execution_exceptions"]
    items[:]=list(reversed(items))+deepcopy(items)
    assert project_water_energy_plan(base,now=NOW)["result_id"]==project_water_energy_plan(changed,now=NOW)["result_id"]


@pytest.mark.parametrize("late", [False, True])
def test_actual_ambiguous_on_coordinator_off_proof_is_not_false_shutdown_uncertainty(late):
    from tests.test_rootline_irrigation_coordinator import (
        Store, Transport, run as advance, NOW as coordinator_now,
    )
    class Readback(Transport):
        def read_output_state(self, **kwargs):
            return {"authoritative":True,"state":"OFF","evidence_id":"synthetic-recovery-off",
                "retrieved_at":(coordinator_now+timedelta(seconds=4000 if late else 2)).isoformat()}
    store=Store();transport=Readback(on="ambiguous");notices=[]
    outcome=advance(store,transport,notices)
    assert outcome["status"]=="ambiguous_on_contained"
    rows=[{**value,"action":action} for action,value in store.rows
          if action in {"claim_before_on","contain_zone","record_ambiguous_shutdown"}]
    assert [row["action"] for row in rows]==["claim_before_on","contain_zone","record_ambiguous_shutdown"]
    assert all("start_evidence" not in row for row in rows)
    history=read(rows);zone=history["zones"]["B12345"]
    assert zone["latest_execution"]==rows[-1]
    assert kinds(zone["execution_exceptions"])==({"off_readback_after_deadline"} if late else set())
    result=build_rootline_specialist_result({"irrigation_history":history},NOW.date().isoformat(),now=NOW)
    assert result["irrigation_lifecycle"]["B12345"]["state"]=="Failed"
    assert "completion_evidence" not in result["irrigation_lifecycle"]["B12345"]
    for language in ("en","af"):
        rendered=compose_daily_rootline_plan(result,language=language)
        assert "unverified shutdown" not in rendered
        assert "afskakeling nog nie bevestig" not in rendered.lower()
        assert "Held safely" not in rendered and "Veilig teruggehou" not in rendered
    assert result["authority"]["command_authority"] is False


def _planning_initial(history):
    return {"plan":{"operating_date":NOW.date().isoformat(),"evidence_generation":"SAME",
        "candidate_tasks":[{"task_id":"irrigation_"+zone,"zone_decision":"Hold",
            "recommendation":"Hold","reason":"contained parent"} for zone in ("B12345","C12345")]},
        "evidence":{"weather":{"observed_at":NOW.isoformat()},"irrigation_history":history},
        "artifact":{"eligible":False,"status":"contained_parent_unresolved"}}


def test_final_planning_observation_keeps_both_zones_and_old_unresolved_exceptions():
    from modules.telemetry.rootline_execution_runtime import _planning_observation
    history=read([contained("B-OLD"),terminal("B-NEW"),contained("C-OLD","C12345")])
    before=deepcopy(history)
    observation=_planning_observation(_planning_initial(history),"42","42",NOW.isoformat())
    zones={row["zone_id"]:row for row in observation["zones"]}
    assert zones["B12345"]["lifecycle"]["state"]=="Held"
    assert zones["C12345"]["lifecycle"]["state"]=="Failed"
    assert [(row["execution_id"],row["kind"]) for row in
        zones["B12345"]["lifecycle"]["execution_exceptions"]]==[("B-OLD","shutdown_unverified")]
    assert [(row["execution_id"],row["kind"]) for row in
        zones["C12345"]["lifecycle"]["execution_exceptions"]]==[("C-OLD","shutdown_unverified")]
    assert history==before and observation["delivery_state"]=="observation_only"
    assert "completion_evidence" not in zones["C12345"]["lifecycle"]


def test_final_planning_observation_identity_changes_only_with_material_lifecycle_evidence():
    from modules.telemetry.rootline_execution_runtime import _planning_observation
    unresolved=_planning_initial(read([contained("B-OLD")]))
    resolved=_planning_initial(read([contained("B-OLD"),terminal("B-OLD")]))
    first=_planning_observation(unresolved,"42","42",NOW.isoformat())
    replay=_planning_observation(deepcopy(unresolved),"42","42",(NOW+timedelta(minutes=30)).isoformat())
    changed=_planning_observation(resolved,"42","42",NOW.isoformat())
    assert first["identity"]==replay["identity"]
    assert first["material_digest"]==replay["material_digest"]
    assert first["identity"]!=changed["identity"]
    assert first["material_digest"]!=changed["material_digest"]


def test_execution_cycle_persists_full_lifecycle_without_a_command_or_notification(monkeypatch):
    from modules.telemetry import rootline_execution_runtime as runtime
    initial=_planning_initial(read([contained("B-OLD"),contained("C-OLD","C12345")]))
    monkeypatch.setattr(runtime,"_current",lambda *_:initial)
    records=[]
    def record(action,identity,payload):
        assert action=="record_observation" and identity==payload["identity"]
        records.append(deepcopy(payload)); return {"success":True,"created":True}
    def store(action,payload):
        assert action=="load_active"; return None
    result=runtime.run_rootline_execution_cycle(
        notify=lambda *_:pytest.fail("this observation must not send a message"),
        environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=store,
        token_store=object(),transport=object(),owner_user_id="42",chat_id="42",
        observation_store=record)
    assert len(records)==1 and result["hardware_commands"]==0
    assert result["status"]=="contained_parent_unresolved"
    assert all(row["lifecycle"]["state"]=="Failed" for row in records[0]["zones"])
    assert {item["execution_id"] for row in records[0]["zones"]
        for item in row["lifecycle"]["execution_exceptions"]}=={"B-OLD","C-OLD"}

def parent_history_rows(zone, *, stale=False):
    """Synthetic canonical job/segment shape; no live identity or receipt."""
    from modules.telemetry.rootline_irrigation_job_contract import (
        build_irrigation_job, project_next_segment,
    )
    job = build_irrigation_job(zone_id=zone,
        operating_date=(NOW-timedelta(days=2)).date().isoformat(),
        requested_total_seconds=7200, requested_total_minutes=120,
        maximum_segment_seconds=3599, expected_segment_count=2,
        plan_identity="SYNTHETIC-PARENT-"+zone)
    segment = project_next_segment(job, [])
    identity = "SYNTHETIC-SEGMENT-"+zone
    claimed, stopped = CLAIM-timedelta(days=2), STOP-timedelta(days=2)
    deadline = DEADLINE-timedelta(days=2)
    common = {"execution_id": identity, "zone_id": zone, "job_id": job["job_id"],
        "segment_number": 1, "segment_identity": segment["segment_identity"],
        "eligibility_id": "SYNTHETIC-OLD-ELIGIBILITY-"+zone,
        "claimed_at": claimed.isoformat(), "primary_stop_deadline": deadline.isoformat(),
        "native_fail_stop_deadline": (deadline+timedelta(seconds=1)).isoformat()}
    rows = [{**common, **job, "action": "record_eligibility",
        "requested_total_duration_seconds": 7200, "requested_total_duration_minutes": 120,
        "governed_executable_duration_seconds": 7198, "plan_generation": job["plan_identity"]},
        {**common, "action": "claim_before_on", "state": "claimed"}]
    if stale:
        rows.append({**common, "action": "record_completed", "state": "Completed",
            "shutdown_verified": True, "objective_satisfied": True,
            "verified_runtime_seconds": 3599,
            "completed_at": stopped.isoformat(),
            "shutdown_evidence": {"authoritative": True, "state": "OFF",
                "retrieved_at": stopped.isoformat(), "evidence_id": identity+"-OFF"}})
    else:
        rows.extend([{**common, "action": "contain_zone", "state": "ambiguous",
            "shutdown_verified": False, "reason": "restart_after_pre_on_claim"},
            {**common, "action": "record_claim_recovery", "state": "claimed_recovery_required",
             "shutdown_verified": True,
             "shutdown_evidence": {"authoritative": True, "state": "OFF",
                "retrieved_at": stopped.isoformat(), "evidence_id": identity+"-OFF"}}])
    return rows


@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("newer_complete", [False, True])
def test_unresolved_parent_truth_survives_final_observation_and_owner_status(
        monkeypatch, stale, newer_complete):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_owner_status as owner
    rows = [contained("UNRELATED-OLD-B"), contained("UNRELATED-OLD-C", "C12345")]
    for zone in ("B12345", "C12345"):
        rows.extend(parent_history_rows(zone, stale=stale))
        if newer_complete:
            rows.append(terminal("UNRELATED-NEW-"+zone, zone))
    history = read(rows)
    key = "stale_incomplete_parent_jobs" if stale else "contained_parent_jobs"
    for zone in ("B12345", "C12345"):
        parent = history["zones"][zone][key][0]
        assert parent["remaining_seconds"] == (3599 if stale else 7198)
        assert parent["completed_segment_count"] == (1 if stale else 0)
    initial = _planning_initial(history)
    for task in initial["plan"]["candidate_tasks"]:
        task.update(zone_decision="recovery required", recommendation="Do Not Run",
            dispatchable=False, reason="The unresolved parent must be reconciled before another run.")
    before = deepcopy(initial)
    monkeypatch.setattr(runtime, "_current", lambda *_: initial)
    observations = []
    def record(action, identity, payload):
        assert action == "record_observation" and identity == payload["identity"]
        observations.append(deepcopy(payload))
        return {"success": True, "created": True}
    def store(action, payload):
        assert action == "load_active"
        return None
    result = runtime.run_rootline_execution_cycle(
        notify=lambda *_: pytest.fail("no lifecycle projection may send a message"),
        environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}, now=NOW,
        store=store, token_store=object(), transport=object(), owner_user_id="42", chat_id="42",
        observation_store=record)
    assert result["hardware_commands"] == 0 and result["telegram_messages"] == 0
    assert len(observations) == 1 and initial == before
    observation = observations[0]
    for item in observation["zones"]:
        lifecycle = item["lifecycle"]
        assert lifecycle["state"] == "Held"
        assert "reconcile" in lifecycle["next_action"].lower()
        assert "before another run" in lifecycle["next_action"].lower()
        assert "claim" not in lifecycle["next_action"].lower()
        assert lifecycle["next_action_owner"] == "ROOTLINE"
        assert "completion_evidence" not in lifecycle
        assert lifecycle["execution_exceptions"] == history["zones"][item["zone_id"]]["execution_exceptions"]
        assert lifecycle["execution_exceptions"]

    # Actual owner composition consumes the persisted observation and canonical
    # history independently; an old stored lifecycle cannot become authority.
    persisted = deepcopy(observation)
    for item in persisted["zones"]:
        item["lifecycle"].update(state="Eligible", next_action="stale claim text")
    monkeypatch.setattr(owner, "_canonical_evidence", lambda *_: {
        "operating_date": NOW.date().isoformat(), "weather": {}, "reassessment": persisted})
    monkeypatch.setattr(owner, "read_latest_zone_water_balances", lambda *_a, **_kw: {})
    monkeypatch.setattr(owner, "read_canonical_irrigation_history", lambda *_a, **_kw: deepcopy(history))
    monkeypatch.setattr(owner, "_runtime_and_notification", lambda *_: owner._project_runtime(
        [(NOW, deepcopy(row)) for row in reversed(rows)]))
    status, code = owner.get_rootline_owner_status(NOW.date().isoformat(), "synthetic-unused", now=NOW)
    assert code == 200 and status["safety"]["can_control"] is False
    assert status["source"]["writes_to_supabase"] is False
    for item in status["zones"]:
        assert item["lifecycle"] == next(row["lifecycle"] for row in observation["zones"]
                                        if row["zone_id"] == item["zone_id"])
        assert item["water_credit"]["delivered_volume_litres"] == "Unknown"
    assert initial == before


@pytest.mark.parametrize("parent_key", ["contained_parent_jobs", "stale_incomplete_parent_jobs"])
@pytest.mark.parametrize("source", ["history", "recommendation"])
def test_unresolved_parent_blocks_stale_recommendation_even_with_eligible_artifact(parent_key, source):
    values = {"history": {}, "recommendation": {"status": "Recommend"}}
    values[source][parent_key] = [{"job": {"job_id": "SYNTHETIC-UNRESOLVED"}}]
    value = project_zone_lifecycle(zone_id="B12345", **values,
        eligibility={"eligible": True}, execution=terminal("OTHER"))
    assert value["state"] == "Held" and "completion_evidence" not in value
    assert "reconcile" in value["next_action"].lower()



@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_current_canonical_eligibility_artifact_remains_eligible_in_stored_observation(zone):
    from modules.telemetry.rootline_execution_authority import build_execution_eligibility
    from modules.telemetry.rootline_execution_runtime import _planning_observation
    from tests.test_rootline_execution_authority import inputs, NOW as eligibility_now
    plan, evidence, controller = inputs(zone=zone)
    artifact = build_execution_eligibility(plan=plan, evidence=evidence,
        controller=controller, now=eligibility_now)
    assert artifact["eligible"] is True and artifact["zone_id"] == zone
    evidence["irrigation_history"] = {"zones": {zone: {"latest_execution": {
        "action": "record_claim_recovery", "state": "claimed", "shutdown_verified": True,
        "eligibility_id": "SYNTHETIC-OLD-RESOLVED", "execution_id": "SYNTHETIC-OLD-RESOLVED",
        "zone_id": zone}}}}
    before = deepcopy((plan, evidence, artifact))
    value = _planning_observation({"plan": plan, "evidence": evidence, "artifact": artifact},
        "42", "42", eligibility_now.isoformat())
    selected = next(row for row in value["zones"] if row["zone_id"] == zone)
    assert selected["lifecycle"]["state"] == "Eligible" and not selected["eligibility_blocker"]
    assert selected["lifecycle"]["next_action_owner"] == "ROOTLINE"
    assert (plan, evidence, artifact) == before


@pytest.mark.parametrize("blocker", ["planner_hold_or_no_dispatchable_zone", "zone_decision_not_run_now"])
def test_typed_fulfilled_objective_keeps_completion_through_actual_owner_composition(monkeypatch, blocker):
    from modules.telemetry import rootline_owner_status as owner
    from modules.telemetry.rootline_execution_runtime import _planning_observation
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event
    rows, typed = [], []
    for zone in ("B12345", "C12345"):
        job = build_irrigation_job(zone_id=zone, operating_date=NOW.date().isoformat(),
            requested_total_seconds=7200, requested_total_minutes=120,
            maximum_segment_seconds=3599, expected_segment_count=2, plan_identity="SYNTHETIC-FULFILLED")
        events = [{**job, "action": "record_eligibility",
            "requested_total_duration_seconds": 7200, "requested_total_duration_minutes": 120,
            "governed_executable_duration_seconds": 7198, "plan_generation": job["plan_identity"]}]
        for number in (1, 2):
            segment = project_next_segment(job, events, rearm_readback_off=True)
            claimed = CLAIM-timedelta(hours=2-number)
            stopped = claimed+timedelta(seconds=3599)
            events.append({**terminal("SYNTHETIC-FULFILLED-"+zone+str(number), zone, stopped=stopped),
                "claimed_at": claimed.isoformat(), "primary_stop_deadline": stopped.isoformat(),
                "native_fail_stop_deadline": stopped.isoformat(),
                "start_evidence": {"authoritative": True, "state": "ON",
                    "retrieved_at": claimed.isoformat(), "evidence_id": "SYNTHETIC-ON-"+str(number)},
                "job_id": job["job_id"], "operating_date": job["operating_date"],
                "segment_number": number, "segment_identity": segment["segment_identity"],
                "verified_runtime_seconds": 3599, "objective_satisfied": number == 2})
        assert project_next_segment(job, events)["status"] == "job_completed"
        rows.extend(events)
        final = events[-1]
        typed.append(build_typed_history_event(event_id="SYNTHETIC-COMPLETION-"+zone,
            event_at=datetime.fromisoformat(final["completed_at"]), event_type="COMPLETED", zone_id=zone,
            planned_minutes=3599/60, actual_minutes=3599/60,
            details={"execution_id": final["execution_id"], "start_evidence_id": "SYNTHETIC-ON",
                "shutdown_evidence_id": "SYNTHETIC-OFF", "maximum_runtime_minutes": 3599/60,
                "verified_runtime_minutes": 3599/60, "shutdown_verified": True,
                "objective_satisfied": True, "evidence_cutoff": NOW.isoformat(),
                "provenance": "synthetic_canonical_completion"}))
    # psycopg returns timestamptz columns as aware datetime instances.
    typed = [{**row, "event_at": datetime.fromisoformat(row["event_at"])} for row in typed]
    history = read(rows, typed)
    assert all(zone["events"][-1]["qualifies_as_completed_watering"] is True
               for zone in history["zones"].values())
    initial = _planning_initial(history)
    initial["artifact"].update(status=blocker)
    for task in initial["plan"]["candidate_tasks"]:
        task.update(zone_decision="Completed", recommendation="Do Not Run",
                    reason="The current objective was fulfilled.")
    observation = _planning_observation(initial, "42", "42", NOW.isoformat())
    specialist = project_water_energy_plan({**initial["plan"], "success": True,
        "recent_irrigation_history": history}, now=NOW)
    for item in observation["zones"]:
        assert item["decision"] == "Not Due" and item["zone_decision"] == "Completed"
        assert item["lifecycle"]["state"] == "Completed"
        assert item["lifecycle"]["completion_evidence"]["objective_satisfied"] is True
        assert specialist["irrigation_lifecycle"][item["zone_id"]]["state"] == "Completed"
    monkeypatch.setattr(owner, "_canonical_evidence", lambda *_: {
        "operating_date": NOW.date().isoformat(), "weather": {}, "reassessment": observation})
    monkeypatch.setattr(owner, "read_latest_zone_water_balances", lambda *_a, **_kw: {})
    monkeypatch.setattr(owner, "read_canonical_irrigation_history", lambda *_a, **_kw: deepcopy(history))
    # The owner runtime reader selects only one latest outcome; the other zone
    # must retain its verified completion from its canonical history as well.
    latest = next(row for row in reversed(rows) if row.get("action") == "record_completed")
    monkeypatch.setattr(owner, "_runtime_and_notification", lambda *_: ({}, latest, {}))
    status, code = owner.get_rootline_owner_status(NOW.date().isoformat(), "synthetic-unused", now=NOW)
    assert code == 200
    for item in status["zones"]:
        assert item["decision"] == "Not Due"
        assert item["lifecycle"]["state"] == "Completed"
        assert item["lifecycle"]["completion_evidence"]["objective_satisfied"] is True
        assert item["water_credit"]["delivered_volume_litres"] == "Unknown"
