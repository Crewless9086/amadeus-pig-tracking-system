from datetime import date, datetime, timezone

from modules.pig_weights.herdmaster_daily_manager_evidence import (
    PACKET_TYPE, build_daily_manager_evidence, load_daily_manager_evidence)
from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence

NOW = datetime(2026, 8, 14, 4, 45, tzinfo=timezone.utc)


def pig(pid="P1", tag="1", *, status="Active", on_farm=True,
        animal_type="Grower", purpose="Grow_Out"):
    return {"pig_id": pid, "tag_number": tag, "pig_name": tag,
            "status": status, "on_farm": on_farm,
            "animal_type": animal_type, "purpose": purpose}


def weight(pid="P1", kg=10, day="2026-08-11", event="W1"):
    return {"weight_event_id": event, "pig_id": pid,
            "weight_date": day, "weight_kg": kg}


def build(*, pigs=None, weights=None, prior=(), lifecycle=(), mortality=None,
          prior_mortality=""):
    return build_daily_manager_evidence(pigs=pigs or [pig()],
        window_weights=weights or [], prior_weights=prior,
        lifecycle_events=lifecycle, mortality_packet=mortality,
        prior_mortality_digest=prior_mortality, analysis_date=date(2026, 8, 14))


def test_complete_current_snapshot_is_not_historical_completion():
    packet = build(weights=[weight()])
    evidence = packet["weight"]
    assert packet["packet_type"] == PACKET_TYPE
    assert evidence["historical_eligible_denominator"] is None
    assert evidence["historical_completion_percentage"] is None
    assert evidence["current_snapshot"] == {
        "eligible_tagged": 1, "covered": 1,
        "coverage_percentage": 100.0, "status": "complete"}
    result = consume_daily_manager_evidence(packet, observed_at=NOW)
    item = result.work_items[0]
    assert "covered: 1/1" in item.title
    assert "No further cohort weighing instruction" in item.next_action
    assert "historical" in item.why


def test_partial_lists_only_missing_eligible_tagged_pigs():
    packet = build(pigs=[pig("P1", "1"), pig("P2", "2")],
                   weights=[weight("P1")])
    result = consume_daily_manager_evidence(packet, observed_at=NOW)
    assert packet["weight"]["current_snapshot"]["covered"] == 1
    assert [row["tag"] for row in packet["weight"]["missing_eligible_tagged"]] == ["2"]
    assert result.work_items[0].next_action == "Weigh only these missing eligible tags: 2."


def test_breeding_animals_are_excluded_unless_individually_scheduled():
    sow = pig("S1", "Maya", animal_type="Sow", purpose="Breeding")
    excluded = build(pigs=[sow])
    assert len(excluded["weight"]["breeding_excluded"]) == 1
    assert excluded["weight"]["current_snapshot"]["eligible_tagged"] == 0
    scheduled = build(pigs=[sow], lifecycle=[{
        "pig_id": "S1", "event_type": "individual_weighing_due",
        "effective_at": "2026-08-11T06:00:00+02:00"}])
    assert scheduled["weight"]["breeding_excluded"] == []
    assert scheduled["weight"]["current_snapshot"]["eligible_tagged"] == 1


def test_scheduled_breeder_without_usable_tag_remains_untagged_excluded():
    packet = build(pigs=[pig("S1", "", animal_type="Sow", purpose="Breeding")],
        lifecycle=[{"pig_id": "S1", "event_type": "individual_weighing_due",
                    "effective_at": "2026-08-11T06:00:00+02:00"}])
    assert packet["weight"]["current_snapshot"]["eligible_tagged"] == 0
    assert [row["pig_id"] for row in packet["weight"]["untagged_excluded"]] == ["S1"]


def test_untagged_inactive_and_unknown_remain_separate():
    packet = build(pigs=[pig("U1", ""), pig("I1", "9", status="Inactive"),
        pig("X1", "10", animal_type=None)])
    evidence = packet["weight"]
    assert [row["pig_id"] for row in evidence["untagged_excluded"]] == ["U1"]
    assert [row["pig_id"] for row in evidence["inactive_off_farm"]] == ["I1"]
    assert [row["pig_id"] for row in evidence["unknown_eligibility"]] == ["X1"]


def test_conflicting_same_day_values_fail_closed():
    packet = build(weights=[weight(kg=10, event="A"), weight(kg=12, event="B")])
    assert packet["weight"]["current_snapshot"]["status"] == "conflicting"
    assert packet["weight"]["current_snapshot"]["covered"] == 0
    result = consume_daily_manager_evidence(packet, observed_at=NOW)
    assert "conflicts" in result.work_items[0].title.lower()
    assert "biological interpretation" in result.work_items[0].next_action


def test_material_weight_change_is_descriptive_not_diagnostic():
    packet = build(weights=[weight(kg=12)], prior=[weight(kg=10, day="2026-08-03")])
    finding = packet["weight"]["material_weight_findings"][0]
    assert finding["change_pct"] == 20.0
    assert "cause or abnormality is not established" in finding["interpretation"]
    item = consume_daily_manager_evidence(packet, observed_at=NOW).work_items[0]
    assert "No cause or diagnosis is inferred" in item.why


def test_unavailable_packet_is_bounded_and_never_requests_all_active_pigs():
    item = consume_daily_manager_evidence(None, observed_at=NOW).work_items[0]
    assert item.title == "Weekly weighing evidence unavailable"
    assert "do not weigh every active pig" in item.next_action


def mortality(digest="NEW"):
    return {"evidence_digest": digest,
        "rolling_counts": {"7": {"total": 1}, "30": {"total": 2}, "90": {"total": 3}},
        "proven_facts": [{"event_id": "D1", "pig_id": "P1",
                          "effective_date": "2026-08-14", "event_kind": "individual_death"}]}


def test_unchanged_mortality_digest_creates_no_mortality_item():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="NEW")
    result = consume_daily_manager_evidence(packet, observed_at=NOW,
        active_lifecycles=[{"pig_id": "P1", "state": "working"}])
    assert packet["mortality"]["digest_changed"] is False
    assert all("mortality:" not in item.dedupe_key for item in result.work_items)


def test_new_mortality_opens_one_attributable_active_followup():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="OLD")
    result = consume_daily_manager_evidence(packet, observed_at=NOW,
        active_lifecycles=[{"pig_id": "P1", "state": "working"}])
    mortality_items = [item for item in result.work_items if "mortality:" in item.dedupe_key]
    assert len(mortality_items) == 1
    assert "associations, not diagnoses" in mortality_items[0].next_action


def test_new_canonical_death_opens_one_followup_without_preexisting_lifecycle():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="OLD")
    result = consume_daily_manager_evidence(packet, observed_at=NOW, active_lifecycles=[])
    mortality_items = [item for item in result.work_items if "mortality:" in item.dedupe_key]
    assert len(mortality_items) == 1
    assert "opened this attributable individual follow-up" in mortality_items[0].why


def test_completed_mortality_followup_stays_closed_even_when_digest_changed():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="OLD")
    result = consume_daily_manager_evidence(packet, observed_at=NOW,
        active_lifecycles=[{"pig_id": "P1", "state": "completed"}])
    assert all("mortality:" not in item.dedupe_key for item in result.work_items)


def test_mortality_state_is_normalized_and_missing_state_fails_closed():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="OLD")
    result = consume_daily_manager_evidence(packet, observed_at=NOW,
        active_lifecycles=[{"pig_id": "P1", "state": " Completed "},
                           {"pig_id": "P1"}])
    assert all("mortality:" not in item.dedupe_key for item in result.work_items)


def test_mortality_persistence_unavailable_is_visible_and_bounded():
    packet = build(weights=[weight()], mortality=mortality(), prior_mortality="OLD")
    packet["mortality"]["materiality_state"] = "persistence_unavailable"
    result = consume_daily_manager_evidence(packet, observed_at=NOW,
        active_lifecycles=[{"pig_id": "P1", "state": "working"}])
    items = [item for item in result.work_items if "mortality" in item.dedupe_key]
    assert len(items) == 1
    assert items[0].title == "Mortality follow-up evidence unavailable"
    assert "duplicate" in items[0].next_action


def test_loader_uses_bounded_read_only_queries_and_latest_prior_day_only():
    calls = {"queries": []}
    class Column:
        def __init__(self, name): self.name = name
    class Cursor:
        description = ()
        current = []
        one = None
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=()):
            normalized = " ".join(sql.split()); calls["queries"].append((normalized, params))
            if "from public.current_canonical_pigs" in normalized:
                self.description = [Column(value) for value in
                    ("pig_id", "tag_number", "pig_name", "status", "on_farm", "animal_type", "purpose")]
                self.current = [("P1", "1", "1", "Active", True, "Grower", "Grow_Out")]
            elif "weight_date between" in normalized:
                self.description = [Column(value) for value in
                    ("weight_event_id", "pig_id", "weight_date", "weight_kg")]
                self.current = [("W1", "P1", date(2026, 8, 11), 12)]
            elif "with latest_day" in normalized:
                self.description = [Column(value) for value in
                    ("weight_event_id", "pig_id", "weight_date", "weight_kg")]
                self.current = [("W0", "P1", date(2026, 8, 3), 10)]
            elif "from public.pig_lifecycle_events" in normalized:
                self.description = [Column(value) for value in ("pig_id", "event_type", "effective_at")]
                self.current = []
            else:
                self.current = []; self.one = ({"evidence_digest": "D"},)
            return self
        def fetchall(self): return self.current
        def fetchone(self): return self.one
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()
    def connect(url, **kwargs):
        calls["url"] = url; calls["kwargs"] = kwargs; return Connection()
    mortality_packet = mortality("D")
    packet = load_daily_manager_evidence(analysis_date=date(2026, 8, 14),
        database_url="postgres://example", connect=connect,
        mortality_evidence_loader=lambda **kwargs: {},
        mortality_packet_builder=lambda evidence, **kwargs: mortality_packet)
    assert "default_transaction_read_only=on" in calls["kwargs"]["options"]
    assert calls["kwargs"]["connect_timeout"] == 3
    assert any("weight_date between" in sql for sql, _ in calls["queries"])
    assert any("with latest_day" in sql for sql, _ in calls["queries"])
    assert all(sql.lstrip().casefold().startswith(("select", "with")) for sql, _ in calls["queries"])
    assert packet["weight"]["current_snapshot"]["status"] == "complete"
    assert packet["mortality"]["digest_changed"] is False
