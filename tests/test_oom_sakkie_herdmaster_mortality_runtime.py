from datetime import date,datetime,timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_mortality_runtime import consume_current_mortality_packet
from modules.pig_weights.herdmaster_mortality_intelligence import build_oom_sakkie_mortality_packet

NOW=datetime(2026,8,5,7,0,tzinfo=timezone.utc);OWNER="42"


def packet(events=1):
    rows=[{"event_id":f"E{i}","pig_id":f"P{i}","effective_date":"2026-08-04",
           "event_kind":"individual_death","confirmation":"confirmed","canonical_status":"current"}
          for i in range(events)]
    return build_oom_sakkie_mortality_packet({"mortality_events":rows},analysis_end=date(2026,8,5))


def memory_store():
    rows={}
    def store(action,identity,payload):
        if action=="load":return rows.get(identity)
        key=identity+":"+payload["evidence_digest"]
        created=key not in rows
        if created:rows[key]=dict(payload);rows[identity]=dict(payload)
        return {"success":True,"created":created}
    return rows,store


def test_authenticated_consumption_records_once_and_replay_is_silent():
    rows,store=memory_store();authority=issue_gateway_owner_authority(OWNER,OWNER)
    first_result,first=consume_current_mortality_packet(packet=packet(),authority=authority,
        owner_user_id=OWNER,observed_at=NOW,state_store=store)
    replay_result,replay=consume_current_mortality_packet(packet=packet(),authority=authority,
        owner_user_id=OWNER,observed_at=NOW,state_store=store)
    assert first["status"]=="mortality_consumption_ready" and first["notify_owner"] is True
    assert replay["status"]=="mortality_consumption_replay_suppressed" and replay["notify_owner"] is False
    assert first_result.work_items==replay_result.work_items and len(rows)==2
    assert not first["writes_farm_data"] and not first["sends_telegram"]


def test_material_change_refreshes_same_review_lifecycle():
    rows,store=memory_store();authority=issue_gateway_owner_authority(OWNER,OWNER)
    _,first=consume_current_mortality_packet(packet=packet(),authority=authority,
        owner_user_id=OWNER,observed_at=NOW,state_store=store)
    _,changed=consume_current_mortality_packet(packet=packet(2),authority=authority,
        owner_user_id=OWNER,observed_at=NOW,state_store=store)
    assert changed["status"]=="mortality_consumption_material_refresh"
    assert changed["review_identity"]==first["review_identity"]=="HERDMASTER-MORTALITY-CURRENT"
    assert changed["prior_evidence_digest"]==first["evidence_digest"]


def test_anonymous_or_mismatched_owner_is_denied_before_persistence():
    rows,store=memory_store()
    result,meta=consume_current_mortality_packet(packet=packet(),authority=None,
        owner_user_id=OWNER,observed_at=NOW,state_store=store)
    assert result is None and meta["status"]=="mortality_consumption_auth_denied" and rows=={}


def test_persistence_failure_contains_result_and_grants_no_delivery():
    result,meta=consume_current_mortality_packet(packet=packet(),
        authority=issue_gateway_owner_authority(OWNER,OWNER),owner_user_id=OWNER,observed_at=NOW,
        state_store=lambda action,identity,payload: None)
    assert result is None and meta["status"]=="mortality_consumption_persistence_unproven"
    assert not meta["writes_farm_data"] and not meta["sends_telegram"]


def test_concurrent_loser_created_false_is_verified_and_suppressed():
    rows,store=memory_store();authority=issue_gateway_owner_authority(OWNER,OWNER);value=packet()
    _,first=consume_current_mortality_packet(packet=value,authority=authority,owner_user_id=OWNER,
        observed_at=NOW,state_store=store)
    # Simulate a second worker whose initial read raced before the winner, but
    # whose deterministic insert loses after the winner becomes visible.
    calls=iter((None,rows["HERDMASTER-MORTALITY-CURRENT"]))
    def loser(action,identity,payload):
        if action=="load":return next(calls)
        return {"success":True,"created":False}
    _,second=consume_current_mortality_packet(packet=value,authority=authority,owner_user_id=OWNER,
        observed_at=NOW,state_store=loser)
    assert first["notify_owner"] is True
    assert second["status"]=="mortality_consumption_replay_suppressed" and second["notify_owner"] is False
