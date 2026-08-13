from copy import deepcopy

from modules.charlie import shadow_control_tower as shadow


def transaction():
    return {"feedback_transaction_id":"FTX-20260813-001","terminal_identity":"CORE development terminal",
        "terminal_state":"released","deployed_agent_identity":"deployed CORE runner",
        "existing_mission_id":"CMQ-20260813-05","business_status":"Phase A source preparation",
        "evidence":{"documented":["Mission Standard"],"runtime_loaded":["runner status"],
            "provider_verified":[],"physical":[]},"worktree_classification":"clean_retained",
        "collision_assessment":"no overlapping active source owner found",
        "proposed_next_terminal":"CORE development terminal","proposed_next_action":"CONTINUE",
        "proposed_continuation_prompt":"Continue the existing mission after human review.",
        "expected_owner_visible_result":"One reviewed source-only PR.","confidence":0.91,
        "reasons":["Exact mission and worktree evidence agree."]}


def actual():
    return {"human_decision_id":"HCT-1","actual_next_terminal":"CORE development terminal",
        "actual_next_action":"CONTINUE","actual_continuation_prompt":"Continue the existing mission after human review.",
        "actual_owner_visible_result":"One reviewed source-only PR."}


class EventDb:
    def __init__(self):self.rows={};self.last=("",{})
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self
    def execute(self,sql,params):
        self.last=(" ".join(sql.split()).lower(),params)
        if "insert into public.operational_events" in self.last[0]:
            key=params["idempotency_key"]
            self.created=key not in self.rows
            self.rows.setdefault(key,params["event_id"])
    def fetchone(self):
        sql,params=self.last
        if "insert into public.operational_events" in sql:return (params["event_id"],) if self.created else None
        if "select event_id" in sql:return (self.rows[params["key"]],)
        return None


def test_kill_switch_is_disabled_by_default_and_has_zero_authority(monkeypatch):
    monkeypatch.delenv(shadow.ENABLE_ENV,raising=False)
    result=shadow.propose_shadow_decision(transaction())
    assert result["status"]=="shadow_control_tower_disabled"
    assert result["dispatches"]==result["prompts_sent"]==result["missions_created"]==0
    assert result["release_authority_granted"] is False


def test_proposal_uses_exact_terminal_versus_deployed_agent_terminology():
    result=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})
    proposal=result["proposal"]
    assert proposal["terminal_identity"]=="CORE development terminal"
    assert proposal["deployed_agent_identity"]=="deployed CORE runner"
    assert proposal["authority"]=="non_authoritative_shadow_proposal"
    assert proposal["human_control_tower_is_sole_dispatcher"] is True
    assert proposal["dispatches"]==proposal["processes_spawned"]==0


def test_evidence_taxonomy_and_status_fail_closed():
    for mutation,status in (({"terminal_state":"running"},"shadow_terminal_state_invalid"),
        ({"evidence":{"documented":[]}},"shadow_evidence_classification_invalid")):
        payload={**transaction(),**mutation}
        result=shadow.propose_shadow_decision(payload,environ={shadow.ENABLE_ENV:"true"})
        assert result["status"]==status and result["success"] is False


def test_duplicate_proposal_replay_is_one_operational_event():
    db=EventDb(); env={shadow.ENABLE_ENV:"yes"}
    first,status1=shadow.record_shadow_proposal(transaction(),environ=env,connect_factory=lambda _url:db)
    second,status2=shadow.record_shadow_proposal(transaction(),environ=env,connect_factory=lambda _url:db)
    assert status1==201 and first["created"] is True
    assert status2==200 and second["created"] is False
    assert first["event_id"]==second["event_id"] and first["proposal_id"]==second["proposal_id"]


def test_comparison_is_deterministic_and_records_no_dispatch_effect(monkeypatch):
    proposal=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})["proposal"]
    monkeypatch.setattr(shadow,"load_operational_events",lambda **kwargs:({"success":True,"events":[{
        "event_type":"shadow_control_tower_proposal_recorded","aggregate_id":proposal["feedback_transaction_id"],
        "payload":{"record_type":"proposal","proposal":proposal}}]},200))
    db=EventDb(); env={shadow.ENABLE_ENV:"1"}
    first,status1=shadow.compare_human_decision(proposal,actual(),environ=env,connect_factory=lambda _url:db)
    second,status2=shadow.compare_human_decision(deepcopy(proposal),deepcopy(actual()),environ=env,connect_factory=lambda _url:db)
    assert status1==201 and status2==200
    assert first["comparison"]==second["comparison"]
    assert first["comparison"]["exact_match"] is True
    assert first["dispatches"]==first["prompts_sent"]==first["terminals_started"]==0


def test_comparison_rejects_fabricated_or_unrecorded_proposal(monkeypatch):
    proposal=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})["proposal"]
    monkeypatch.setattr(shadow,"load_operational_events",lambda **kwargs:({"success":True,"events":[]},200))
    result,status=shadow.compare_human_decision(proposal,actual(),environ={shadow.ENABLE_ENV:"1"},
        connect_factory=lambda _url:EventDb())
    assert status==409 and result["status"]=="persisted_shadow_proposal_not_found"


def test_comparison_rejects_tampered_proposal_with_same_identity(monkeypatch):
    proposal=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})["proposal"]
    monkeypatch.setattr(shadow,"load_operational_events",lambda **kwargs:({"success":True,"events":[{
        "event_type":"shadow_control_tower_proposal_recorded","aggregate_id":proposal["feedback_transaction_id"],
        "payload":{"proposal":proposal}}]},200))
    tampered={**proposal,"proposed_next_terminal":"hidden terminal"}
    result,status=shadow.compare_human_decision(tampered,actual(),environ={shadow.ENABLE_ENV:"1"},
        connect_factory=lambda _url:EventDb())
    assert status==409 and result["status"]=="shadow_proposal_content_mismatch"


def test_same_human_decision_identity_with_changed_actual_decision_fails_closed(monkeypatch):
    proposal=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})["proposal"]
    base_events=[{"event_type":"shadow_control_tower_proposal_recorded",
        "aggregate_id":proposal["feedback_transaction_id"],"payload":{"proposal":proposal}}]
    monkeypatch.setattr(shadow,"load_operational_events",lambda **kwargs:({"success":True,"events":base_events},200))
    db=EventDb(); env={shadow.ENABLE_ENV:"1"}
    first,status=shadow.compare_human_decision(proposal,actual(),environ=env,connect_factory=lambda _url:db)
    assert status==201
    base_events.append({"event_type":"shadow_control_tower_human_comparison_recorded",
        "aggregate_id":proposal["feedback_transaction_id"],"payload":first["comparison"]})
    changed={**actual(),"actual_next_action":"CLOSE"}
    result,status=shadow.compare_human_decision(proposal,changed,environ=env,connect_factory=lambda _url:db)
    assert status==409 and result["status"]=="human_decision_replay_conflict"


def test_readiness_counts_distinct_persisted_proposal_pairs_not_decision_revisions(monkeypatch):
    events=[]
    for index in range(2):
        proposal={**shadow.propose_shadow_decision({**transaction(),
            "feedback_transaction_id":f"FTX-{index}"},environ={shadow.ENABLE_ENV:"1"})["proposal"]}
        events.append({"event_type":"shadow_control_tower_proposal_recorded",
            "aggregate_id":proposal["feedback_transaction_id"],"payload":{"proposal":proposal}})
        for decision in range(7):
            events.append({"event_type":"shadow_control_tower_human_comparison_recorded",
                "aggregate_id":proposal["feedback_transaction_id"],"payload":{
                    "proposal_id":proposal["proposal_id"],"human_decision_id":f"D-{decision}"}})
    monkeypatch.setattr(shadow,"load_operational_events",lambda **kwargs:({"success":True,"events":events},200))
    result,status=shadow.comparison_readiness()
    assert status==200 and result["comparison_count"]==2
    assert result["target_reached"] is False and result["learning_success_claimed"] is False


def test_no_dispatch_process_mission_or_provider_dependencies_are_imported():
    source=open(shadow.__file__,encoding="utf-8").read()
    forbidden=("subprocess","create_mission","Start-Process","telegram","requests","n8n","google_sheets")
    assert all(token not in source for token in forbidden)
