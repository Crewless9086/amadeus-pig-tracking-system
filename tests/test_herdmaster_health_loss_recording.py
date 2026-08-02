from contextlib import nullcontext
from unittest.mock import patch

from modules.pig_weights.herdmaster_health_loss_recording import confirm_health_loss_preview


class Cursor:
    def __init__(self, rows):self.rows=rows;self.one=None
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def execute(self,sql,params=()):
        compact=" ".join(sql.split()).lower()
        if compact.startswith("select pg_advisory_xact_lock"):self.one=(1,)
        elif "from public.pig_observation_events where idempotency_key" in compact:
            row=self.rows.get(params[0]);self.one=(row["event_id"],row["digest"]) if row else None
        elif "select 1 from public.pigs" in compact:self.one=(1,) if params[0]=="PIG-11" else None
        elif compact.startswith("insert into public.pig_observation_events"):
            event_id,pig_id,_observed,_actor,_severity,_note,_measurements,digest,operation=params
            self.rows[operation]={"event_id":event_id,"pig_id":pig_id,"digest":digest};self.one=(event_id,)
        else:raise AssertionError(compact)
    def fetchone(self):return self.one


class Connection:
    def __init__(self,rows):self.rows=rows
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def cursor(self):return Cursor(self.rows)


def lifecycle():
    operation="HERD-HEALTH-LOSS-ABC"
    return {"provider_timestamp":"2026-08-02T07:10:00+00:00","owner_user_id":"42","preview":{
        "confirmation_ready":True,
        "confirmation_binding":{"operation_id":operation,"confirmation_ready":True,
            "evidence_generation":"GEN-11","provider_message_id":"3172","preview_sha256":"p"*64,
            "authenticated_principal_id":"42"},
        "evaluator":{"identity":{"pig_id":"PIG-11"},
            "immediate_welfare_priority":{"level":"urgent_follow_up"},
            "canonical_effects":[{"area":"medical_observation","supported":True,
                "facts":{"observed":[{"fact":"not_eating","value":True}],
                    "owner_suspected":[],"veterinary_evidence":[],"diagnosis_inferred":False}}]}}}


def test_exact_confirmation_records_once_and_replay_writes_zero():
    rows={};packet=lifecycle();confirm="CONFIRM HERD-HEALTH-LOSS-ABC"
    first,status=confirm_health_loss_preview(packet,confirm,actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection(rows))
    replay,replay_status=confirm_health_loss_preview(packet,confirm,actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection(rows))
    assert status==201 and first["rows_created"]==1
    assert replay_status==200 and replay["rows_created"]==0
    assert len(rows)==1 and first["treatment_recorded"] is False and first["diagnosis_inferred"] is False


def test_stale_evidence_and_non_observation_effects_fail_closed():
    packet=lifecycle();confirm="CONFIRM HERD-HEALTH-LOSS-ABC"
    stale,status=confirm_health_loss_preview(packet,confirm,actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-12"},connect_factory=lambda:Connection({}))
    assert status==409 and stale["status"]=="canonical_evidence_changed_repreview_required"
    packet["preview"]["evaluator"]["canonical_effects"].append({"area":"lifecycle","supported":True})
    blocked,status=confirm_health_loss_preview(packet,confirm,actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection({}))
    assert status==409 and blocked["status"]=="canonical_effect_coordinator_unavailable"


def test_confirmation_must_match_exact_operation():
    result,status=confirm_health_loss_preview(lifecycle(),"CONFIRM SOMETHING-ELSE",actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection({}))
    assert status==409 and result["writes_farm_data"] is False


def test_confirmation_rejects_empty_or_different_authenticated_actor():
    for actor in ("", "99"):
        result,status=confirm_health_loss_preview(lifecycle(),"CONFIRM HERD-HEALTH-LOSS-ABC",actor_id=actor,
            evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection({}))
        assert status==403 and result["status"]=="authenticated_owner_confirmation_required"


def test_multiple_medical_effects_fail_closed_without_partial_write():
    packet=lifecycle()
    packet["preview"]["evaluator"]["canonical_effects"].append(
        {"area":"medical_observation","supported":True,"facts":{"observed":[]}})
    result,status=confirm_health_loss_preview(packet,"CONFIRM HERD-HEALTH-LOSS-ABC",actor_id="42",
        evidence_loader=lambda:{"evidence_generation":"GEN-11"},connect_factory=lambda:Connection({}))
    assert status==409 and result["status"]=="canonical_effect_coordinator_unavailable"
    assert result["writes_farm_data"] is False


class MortalityCursor:
    def __init__(self, state): self.state=state; self.one=None; self.rowcount=0
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def execute(self, sql, params=()):
        compact=" ".join(sql.split()).lower(); self.rowcount=0
        if compact.startswith("select pg_advisory_xact_lock"): self.one=(1,)
        elif "from public.pig_lifecycle_events where idempotency_key" in compact:
            event=self.state.get("event"); self.one=(event["id"],event["pig_id"],event["payload"]) if event else None
        elif "select status,on_farm,notes from public.pigs" in compact:
            pig=self.state["pig"]; self.one=(pig["status"],pig["on_farm"],pig["notes"])
        elif compact.startswith("update public.pigs"):
            pig=self.state["pig"]
            if pig["status"]=="Active" and pig["on_farm"] is True:
                pig.update(status="Dead",on_farm=False,notes=params[1]);self.rowcount=1
        elif compact.startswith("insert into public.pig_lifecycle_events"):
            self.state["event"]={"id":params[0],"pig_id":params[1],"payload":__import__("json").loads(params[6])}
        else: raise AssertionError(compact)
    def fetchone(self): return self.one


class MortalityConnection:
    def __init__(self,state): self.state=state
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def cursor(self): return MortalityCursor(self.state)


def mortality_lifecycle():
    packet = lifecycle()
    packet["preview"]["confirmation_binding"]["provider_message_id"] = "3189"
    packet["preview"]["evaluator"]["canonical_effects"] = [
        {"area": "lifecycle", "action": "record_death", "supported": True,
         "facts": {"date": "2026-08-02", "time": "Unknown"}},
        {"area": "availability", "action": "remove_from_current_active_sale_and_breeding_projections", "supported": True, "facts": {}},
        {"area": "movement_pen", "action": "record_reported_removal_or_disposal_context", "supported": True,
         "facts": {"owner_reported_outcome": "removed and buried"}},
        {"area": "downstream_work", "action": "close_or_replace_future_animal_tasks", "supported": True, "facts": {}},
    ]
    return packet


def test_confirmed_mortality_transaction_and_concurrent_replay_write_once():
    packet=mortality_lifecycle();state={"pig":{"status":"Active","on_farm":True,"notes":"history"}}
    result, status = confirm_health_loss_preview(
        packet, "CONFIRM HERD-HEALTH-LOSS-ABC", actor_id="42",
        evidence_loader=lambda: {"evidence_generation": "GEN-11"},
        connect_factory=lambda: MortalityConnection(state))
    replay, replay_status = confirm_health_loss_preview(
        packet, "CONFIRM HERD-HEALTH-LOSS-ABC", actor_id="42",
        evidence_loader=lambda: (_ for _ in ()).throw(AssertionError("replay does not reload stale evidence")),
        connect_factory=lambda: MortalityConnection(state))
    assert status == 201 and result["status"] == "mortality_lifecycle_recorded"
    assert result["rows_created"] == 1 and result["on_farm"] is False
    assert result["exact_time_of_death"] == "Unknown"
    assert replay_status == 200 and replay["rows_created"] == 0
    assert state["pig"]["status"] == "Dead" and state["pig"]["on_farm"] is False
    assert state["event"]["payload"]["resulting_status"] == "Dead"
    assert "body removed and buried" in state["pig"]["notes"]


def test_completed_mortality_confirmation_replay_calls_no_store():
    packet = lifecycle()
    packet["recording_result"] = {"success": True,
        "operation_id": "HERD-HEALTH-LOSS-ABC", "rows_created": 1}
    result, status = confirm_health_loss_preview(
        packet, "CONFIRM HERD-HEALTH-LOSS-ABC", actor_id="42",
        evidence_loader=lambda: (_ for _ in ()).throw(AssertionError("no reload")))
    assert status == 200 and result["rows_created"] == 0
