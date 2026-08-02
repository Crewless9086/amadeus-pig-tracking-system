from contextlib import nullcontext

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
    return {"provider_timestamp":"2026-08-02T07:10:00+00:00","preview":{
        "confirmation_ready":True,
        "confirmation_binding":{"operation_id":operation,"confirmation_ready":True,
            "evidence_generation":"GEN-11","provider_message_id":"3172","preview_sha256":"p"*64},
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
