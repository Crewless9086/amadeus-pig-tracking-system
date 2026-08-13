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


def test_comparison_is_deterministic_and_records_no_dispatch_effect():
    proposal=shadow.propose_shadow_decision(transaction(),environ={shadow.ENABLE_ENV:"1"})["proposal"]
    db=EventDb(); env={shadow.ENABLE_ENV:"1"}
    first,status1=shadow.compare_human_decision(proposal,actual(),environ=env,connect_factory=lambda _url:db)
    second,status2=shadow.compare_human_decision(deepcopy(proposal),deepcopy(actual()),environ=env,connect_factory=lambda _url:db)
    assert status1==201 and status2==200
    assert first["comparison"]==second["comparison"]
    assert first["comparison"]["exact_match"] is True
    assert first["dispatches"]==first["prompts_sent"]==first["terminals_started"]==0


def test_no_dispatch_process_mission_or_provider_dependencies_are_imported():
    source=open(shadow.__file__,encoding="utf-8").read()
    forbidden=("subprocess","create_mission","Start-Process","telegram","requests","n8n","google_sheets")
    assert all(token not in source for token in forbidden)
