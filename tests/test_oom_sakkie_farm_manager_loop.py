from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

from modules.oom_sakkie.farm_manager_loop import (
    Authority,
    CoordinationSignal,
    CustomerDemandEvidence,
    FollowUp,
    Provenance,
    SpecialistAvailability,
    SpecialistResult,
    SpecialistWorkItem,
    SaleInventoryEvidence,
    SupportedAnswer,
    WorkState,
    answer_supported_question,
    build_family_brief,
    build_sales_weighing_packet,
    render_consolidated_brief,
    render_family_brief,
    render_sales_weighing_packet,
)


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


def _provenance(specialist, result_id, hours=1):
    return Provenance(
        specialist=specialist,
        result_id=result_id,
        source_refs=(f"{specialist}:structured-result",),
        observed_at=NOW - timedelta(hours=hours),
        confidence=0.96,
    )


def _item(
    specialist,
    result_id,
    item_id,
    dedupe_key,
    domain,
    state,
    assignee,
    *,
    authority=Authority.ADVISORY,
    value=50,
    hours=1,
    question="",
    question_for="",
    media_usable=None,
    metadata=None,
):
    return SpecialistWorkItem(
        item_id=item_id,
        dedupe_key=dedupe_key,
        domain=domain,
        title=f"{domain} priority",
        why=f"{domain} outcome is at risk",
        next_action=f"review {domain} evidence",
        assignee=assignee,
        state=state,
        authority=authority,
        provenance=_provenance(specialist, result_id, hours),
        business_value=value,
        stale_after_hours=24,
        genuine_question=question,
        question_for=question_for,
        media_usable=media_usable,
        metadata=metadata or {},
    )


def _result(specialist, result_id, *items, answers=()):
    return SpecialistResult(
        specialist=specialist,
        result_id=result_id,
        observed_at=NOW,
        work_items=tuple(items),
        supported_answers=tuple(answers),
    )


def test_consolidated_brief_prioritises_customer_then_herd_water_and_usable_marketing():
    sales = _item(
        "sam_livestock", "sam-1", "sales", "lead-42", "sales",
        WorkState.DUE_TODAY, "charl", value=100,
        metadata={"customer_or_exception": True},
    )
    herd = _item(
        "herdmaster", "herd-1", "herd", "overdue-weight", "herd",
        WorkState.URGENT, "dad", value=80,
    )
    water = _item(
        "rootline", "root-1", "water", "tank-continuity", "water_energy",
        WorkState.DUE_TODAY, "dad", value=70,
    )
    marketing = _item(
        "beacon", "beacon-1", "media", "fresh-sale-media", "marketing",
        WorkState.PLANNED, "mom", value=60, media_usable=True,
    )
    brief = build_family_brief(
        [
            _result("sam_livestock", "sam-1", sales),
            _result("herdmaster", "herd-1", herd),
            _result("rootline", "root-1", water),
            _result("beacon", "beacon-1", marketing),
        ],
        now=NOW,
    )
    assert [item.item_id for item in brief.queue] == ["sales", "herd", "water", "media"]
    assert brief.writes_performed == 0


def test_suppresses_completed_stale_duplicate_and_unusable_marketing_work():
    current = _item(
        "sam_livestock", "sam-2", "current", "same-work", "sales",
        WorkState.DUE_TODAY, "charl", value=90,
    )
    duplicate = _item(
        "sam_meat", "meat-1", "duplicate", "same-work", "sales",
        WorkState.PLANNED, "charl", value=20,
    )
    completed = _item(
        "herdmaster", "herd-2", "done", "done-work", "herd",
        WorkState.COMPLETED, "dad",
    )
    stale = _item(
        "rootline", "root-2", "stale", "old-water", "water_energy",
        WorkState.URGENT, "dad", hours=30,
    )
    unusable = _item(
        "beacon", "beacon-2", "unusable", "media", "marketing",
        WorkState.PLANNED, "mom", media_usable=False,
        metadata={"requests_media": True},
    )
    brief = build_family_brief(
        [
            _result("sam_livestock", "sam-2", current),
            _result("sam_meat", "meat-1", duplicate),
            _result("herdmaster", "herd-2", completed),
            _result("rootline", "root-2", stale),
            _result("beacon", "beacon-2", unusable),
        ],
        now=NOW,
    )
    assert [item.item_id for item in brief.queue] == ["current", "stale"]
    assert brief.queue[1].state is WorkState.WAITING_EVIDENCE
    assert brief.suppressed == {
        "completed_or_handled": ("done",),
        "stale_refreshed": ("stale",),
        "duplicate": ("duplicate",),
        "unusable_marketing_request": ("unusable",),
        "lower_ranked": (),
    }


def test_preserves_specialist_provenance_and_family_specific_presentation():
    charl = _item(
        "sam_livestock", "sam-3", "charl-task", "sales-task", "sales",
        WorkState.DUE_TODAY, "charl",
    )
    dad = _item(
        "herdmaster", "herd-3", "dad-task", "herd-task", "herd",
        WorkState.URGENT, "dad",
    )
    mom = _item(
        "beacon", "beacon-3", "mom-task", "media-task", "marketing",
        WorkState.PLANNED, "mom", media_usable=True,
    )
    brief = build_family_brief(
        [
            _result("sam_livestock", "sam-3", charl),
            _result("herdmaster", "herd-3", dad),
            _result("beacon", "beacon-3", mom),
        ],
        now=NOW,
    )
    dad_text = render_family_brief(brief, "dad")
    assert "dad-task" not in dad_text  # presentation uses meaning, not internal IDs
    assert "herd priority" in dad_text
    assert "sam_livestock" not in dad_text
    assert "Source: herdmaster/herd-3" in dad_text
    assert tuple(item.item_id for item in brief.by_family_member["mom"]) == ("mom-task",)


def test_supported_answer_is_conversational_provenanced_and_read_only():
    answer = SupportedAnswer(
        question_key="water_status",
        answer="The latest Rootline evidence says hold irrigation until the tank reading is confirmed.",
        provenance=_provenance("rootline", "root-3"),
    )
    response = answer_supported_question(
        "water_status", [_result("rootline", "root-3", answers=(answer,))], now=NOW
    )
    assert response["status"] == "supported"
    assert response["provenance"]["specialist"] == "rootline"
    assert response["writes_performed"] == 0


def test_unsupported_answer_asks_one_bounded_evidence_question():
    response = answer_supported_question("unknown", [], now=NOW)
    assert response == {
        "status": "needs_evidence",
        "answer": "",
        "question": "Which exact farm fact should the relevant specialist verify?",
        "writes_performed": 0,
    }


def test_asks_at_most_one_highest_priority_genuine_question_per_family_member():
    urgent = _item(
        "herdmaster", "herd-4", "urgent-q", "urgent-q", "herd",
        WorkState.WAITING_EVIDENCE, "dad", question="Did sow A eat this morning?", question_for="dad",
    )
    planned = _item(
        "rootline", "root-4", "planned-q", "planned-q", "water_energy",
        WorkState.PLANNED, "dad", question="What is the seasonal window?", question_for="dad",
    )
    brief = build_family_brief(
        [_result("herdmaster", "herd-4", urgent), _result("rootline", "root-4", planned)],
        now=NOW,
    )
    assert brief.questions["dad"] == ("Did sow A eat this morning?",)
    assert brief.questions["charl"] == ()
    assert brief.questions["mom"] == ()


def test_protected_actions_are_demoted_to_owner_decisions_and_never_executed():
    for authority in (
        Authority.CUSTOMER_COMMITMENT,
        Authority.OWNER_DECISION,
        Authority.MONEY_ACTION,
        Authority.FARM_WRITE,
        Authority.PUBLICATION,
        Authority.HARDWARE_COMMAND,
    ):
        item = _item(
            "sam_livestock", f"protected-{authority.value}", authority.value,
            authority.value, "sales", WorkState.URGENT, "charl", authority=authority,
        )
        brief = build_family_brief(
            [_result("sam_livestock", f"protected-{authority.value}", item)],
            now=NOW,
        )
        assert brief.queue[0].state is WorkState.URGENT
        assert brief.writes_performed == 0
        rendered = render_family_brief(brief, "charl")
        assert "Nothing has been executed" in rendered
        assert "review sales evidence" not in rendered


def test_promised_follow_up_is_reassessed_when_new_structured_evidence_arrives():
    follow_up = FollowUp("fu-1", "tank-check", "dad", "promised", "rootline")
    new_evidence = _item(
        "rootline", "root-5", "tank", "tank-check", "water_energy",
        WorkState.DUE_TODAY, "dad",
    )
    brief = build_family_brief(
        [_result("rootline", "root-5", new_evidence)],
        now=NOW,
        existing_follow_ups=(follow_up,),
    )
    assert brief.follow_ups[0].status == "reassessed_open"
    assert brief.follow_ups[0].evidence_result_ids == ("rootline:root-5",)


def test_answer_provenance_must_bind_to_enclosing_result():
    answer = SupportedAnswer(
        question_key="water_status",
        answer="Forged",
        provenance=_provenance("beacon", "beacon-forgery"),
    )
    try:
        _result("rootline", "root-6", answers=(answer,))
    except ValueError as exc:
        assert "answer provenance" in str(exc)
    else:
        raise AssertionError("forged answer provenance was accepted")


def test_cross_domain_dependency_waits_and_consolidated_family_brief_renders():
    marketing = _item(
        "beacon", "beacon-7", "campaign", "campaign", "marketing",
        WorkState.PLANNED, "mom", media_usable=True,
        metadata={"depends_on": ("sale-ready-stock",), "requests_media": True},
    )
    brief = build_family_brief([_result("beacon", "beacon-7", marketing)], now=NOW)
    assert brief.queue[0].state is WorkState.WAITING_EVIDENCE
    rendered = render_consolidated_brief(brief)
    assert "OOM SAKKIE FAMILY BRIEF" in rendered
    assert "coordination is waiting for sale-ready-stock" in rendered


def test_follow_up_closes_only_from_explicit_resolution():
    follow_up = FollowUp("fu-2", "tank-check", "dad", "promised", "rootline")
    resolved = SpecialistResult(
        specialist="rootline",
        result_id="root-resolved",
        observed_at=NOW,
        resolved_dedupe_keys=("tank-check",),
    )
    brief = build_family_brief([resolved], now=NOW, existing_follow_ups=(follow_up,))
    assert brief.follow_ups[0].status == "closed_by_explicit_resolution"
    assert brief.follow_ups[0].evidence_result_ids == ("rootline:root-resolved",)


def test_future_supported_answer_is_not_accepted():
    future = NOW + timedelta(hours=1)
    provenance = Provenance(
        specialist="rootline",
        result_id="root-future",
        source_refs=("rootline:future",),
        observed_at=future,
        confidence=1,
    )
    result = SpecialistResult(
        specialist="rootline",
        result_id="root-future",
        observed_at=future,
        supported_answers=(SupportedAnswer("water_status", "Future claim", provenance),),
    )
    response = answer_supported_question("water_status", [result], now=NOW)
    assert response["status"] == "needs_evidence"


def test_wrong_specialist_cannot_close_owned_follow_up():
    follow_up = FollowUp("fu-3", "tank-check", "dad", "promised", "rootline")
    spoof = SpecialistResult(
        specialist="beacon",
        result_id="beacon-spoof",
        observed_at=NOW,
        resolved_dedupe_keys=("tank-check",),
    )
    brief = build_family_brief([spoof], now=NOW, existing_follow_ups=(follow_up,))
    assert brief.follow_ups[0].status == "promised"


def test_waiting_prerequisite_does_not_satisfy_cross_domain_dependency():
    stock = _item(
        "herdmaster", "herd-wait", "stock", "sale-ready-stock", "herd",
        WorkState.WAITING_EVIDENCE, "dad",
    )
    marketing = _item(
        "beacon", "beacon-wait", "campaign-wait", "campaign-wait", "marketing",
        WorkState.PLANNED, "mom", media_usable=True,
        metadata={"depends_on": ("sale-ready-stock",), "requests_media": True},
    )
    brief = build_family_brief(
        [
            _result("herdmaster", "herd-wait", stock),
            _result("beacon", "beacon-wait", marketing),
        ],
        now=NOW,
    )
    campaign = next(item for item in brief.queue if item.item_id == "campaign-wait")
    assert campaign.state is WorkState.WAITING_EVIDENCE


def test_rootline_priority_explains_multi_factor_coordination():
    water = _item(
        "rootline", "root-balance", "water-balance", "water-balance",
        "water_energy", WorkState.DUE_TODAY, "dad",
        metadata={"depends_on": ("weather-ready", "solar-ready", "grid-ready")},
    )
    prerequisites = [
        _item(
            "rootline", "root-balance", key, key, "water_energy",
            WorkState.DUE_TODAY, "dad",
        )
        for key in ("weather-ready", "solar-ready", "grid-ready")
    ]
    result = _result("rootline", "root-balance", water, *prerequisites)
    result = SpecialistResult(
        specialist=result.specialist,
        result_id=result.result_id,
        observed_at=result.observed_at,
        work_items=result.work_items,
        coordination_signals=tuple(
            CoordinationSignal(kind, value, _provenance("rootline", "root-balance"))
            for kind, value in (
                ("water_continuity", "needs_water"),
                ("forecast_rain", "none_material"),
                ("solar_reserve", "sufficient"),
                ("grid_cost", "peak"),
            )
        ),
    )
    brief = build_family_brief([result], now=NOW)
    balanced = next(item for item in brief.queue if item.item_id == "water-balance")
    assert "material rain is not forecast" in balanced.why
    assert "safe solar window" in balanced.next_action


def test_dependency_waiting_propagates_transitively():
    a = _item(
        "beacon", "chain", "a", "a", "marketing", WorkState.PLANNED, "mom",
        media_usable=True, metadata={"depends_on": ("missing",)},
    )
    b = _item(
        "sam_meat", "chain-meat", "b", "b", "sales", WorkState.PLANNED, "charl",
        metadata={"depends_on": ("a",)},
    )
    brief = build_family_brief(
        [_result("sam_meat", "chain-meat", b), _result("beacon", "chain", a)],
        now=NOW,
    )
    assert {item.item_id: item.state for item in brief.queue} == {
        "a": WorkState.WAITING_EVIDENCE,
        "b": WorkState.WAITING_EVIDENCE,
    }


def test_future_resolution_result_is_isolated():
    future = SpecialistResult(
        specialist="rootline",
        result_id="future-resolution",
        observed_at=NOW + timedelta(minutes=1),
        resolved_dedupe_keys=("tank-check",),
    )
    supported = _item(
        "herdmaster", "herd-future-isolation", "herd-safe", "herd-safe",
        "herd", WorkState.DUE_TODAY, "dad",
    )
    brief = build_family_brief(
        [_result("herdmaster", "herd-future-isolation", supported), future],
        now=NOW,
        existing_follow_ups=(
            FollowUp("future-fu", "tank-check", "dad", "promised", "rootline"),
        ),
    )
    assert [item.item_id for item in brief.queue] == ["herd-safe"]
    assert brief.specialist_gaps["rootline"] == "invalid_future_evidence"
    assert brief.follow_ups[0].status == "promised"


def test_ranks_no_more_than_three_actions_per_family_member():
    items = tuple(
        _item(
            "herdmaster",
            "herd-cap",
            f"herd-{index}",
            f"herd-{index}",
            "herd",
            WorkState.PLANNED,
            "dad",
            value=100 - index,
        )
        for index in range(5)
    )
    brief = build_family_brief(
        [_result("herdmaster", "herd-cap", *items)], now=NOW
    )
    assert [item.item_id for item in brief.by_family_member["dad"]] == [
        "herd-0",
        "herd-1",
        "herd-2",
    ]
    assert brief.suppressed["lower_ranked"] == ("herd-3", "herd-4")


def test_unavailable_specialist_blocks_only_its_unsupported_conclusion():
    supported_sales = _item(
        "sam_livestock",
        "sam-supported",
        "sales-supported",
        "sales-supported",
        "sales",
        WorkState.DUE_TODAY,
        "charl",
        value=100,
        metadata={"customer_or_exception": True},
    )
    for availability in (
        SpecialistAvailability.DISABLED,
        SpecialistAvailability.MISSING,
        SpecialistAvailability.CONTAINED,
    ):
        unavailable = SpecialistResult(
            specialist="beacon",
            result_id=f"beacon-{availability.value}",
            observed_at=NOW,
            availability=availability,
        )
        brief = build_family_brief(
            [
                _result("sam_livestock", "sam-supported", supported_sales),
                unavailable,
            ],
            now=NOW,
        )
        assert [item.item_id for item in brief.queue] == ["sales-supported"]
        assert brief.specialist_gaps == {"beacon": availability.value}


def test_stale_specialist_blocks_only_its_conclusion_and_keeps_other_work():
    sales = _item(
        "sam_livestock",
        "sam-current",
        "sales-current",
        "sales-current",
        "sales",
        WorkState.DUE_TODAY,
        "charl",
    )
    water = _item(
        "rootline",
        "root-stale",
        "water-stale",
        "water-stale",
        "water_energy",
        WorkState.URGENT,
        "dad",
    )
    stale_rootline = SpecialistResult(
        specialist="rootline",
        result_id="root-stale",
        observed_at=NOW,
        availability=SpecialistAvailability.STALE,
        work_items=(water,),
    )
    brief = build_family_brief(
        [_result("sam_livestock", "sam-current", sales), stale_rootline], now=NOW
    )
    by_id = {item.item_id: item for item in brief.queue}
    assert by_id["sales-current"].state is WorkState.DUE_TODAY
    assert by_id["water-stale"].state is WorkState.WAITING_EVIDENCE


def test_unavailable_signals_cannot_change_supported_water_recommendation():
    water = _item(
        "rootline", "root-current", "water-current", "water-current",
        "water_energy", WorkState.DUE_TODAY, "dad",
    )
    current = _result("rootline", "root-current", water)
    contained_provenance = _provenance("rootline", "root-contained")
    contained = SpecialistResult(
        specialist="rootline",
        result_id="root-contained",
        observed_at=NOW,
        availability=SpecialistAvailability.CONTAINED,
        coordination_signals=tuple(
            CoordinationSignal(kind, value, contained_provenance)
            for kind, value in (
                ("water_continuity", "needs_water"),
                ("forecast_rain", "none_material"),
                ("solar_reserve", "sufficient"),
                ("grid_cost", "peak"),
            )
        ),
    )
    brief = build_family_brief([current, contained], now=NOW)
    assert brief.queue[0].next_action == "review water_energy evidence"


def test_stale_or_contained_result_cannot_close_follow_up():
    follow_up = FollowUp("fu-contained", "tank-check", "dad", "promised", "rootline")
    for availability in (
        SpecialistAvailability.STALE,
        SpecialistAvailability.CONTAINED,
    ):
        result = SpecialistResult(
            specialist="rootline",
            result_id=f"root-{availability.value}",
            observed_at=NOW,
            availability=availability,
            resolved_dedupe_keys=("tank-check",),
        )
        brief = build_family_brief(
            [result], now=NOW, existing_follow_ups=(follow_up,)
        )
        assert brief.follow_ups[0].status == "promised"


def test_signal_cannot_postdate_its_result():
    future_signal = CoordinationSignal(
        "grid_cost",
        "peak",
        Provenance(
            specialist="rootline",
            result_id="root-signal-time",
            source_refs=("rootline:signal",),
            observed_at=NOW + timedelta(minutes=1),
            confidence=0.96,
        ),
    )
    try:
        SpecialistResult(
            specialist="rootline",
            result_id="root-signal-time",
            observed_at=NOW,
            coordination_signals=(future_signal,),
        )
    except ValueError as exc:
        assert "coordination signal cannot postdate" in str(exc)
    else:
        raise AssertionError("future coordination signal was accepted")


def test_consolidated_renderer_lists_each_action_once():
    item = _item(
        "herdmaster", "herd-render", "render-once", "render-once", "herd",
        WorkState.DUE_TODAY, "dad",
    )
    brief = build_family_brief(
        [_result("herdmaster", "herd-render", item)], now=NOW
    )
    rendered = render_consolidated_brief(brief)
    assert rendered.count("herd priority") == 1


def test_stale_completed_work_is_not_resurrected():
    completed = _item(
        "rootline", "root-stale-done", "stale-done", "stale-done",
        "water_energy", WorkState.COMPLETED, "dad",
    )
    result = SpecialistResult(
        specialist="rootline",
        result_id="root-stale-done",
        observed_at=NOW,
        availability=SpecialistAvailability.STALE,
        work_items=(completed,),
    )
    brief = build_family_brief([result], now=NOW)
    assert brief.queue == ()
    assert brief.suppressed["completed_or_handled"] == ("stale-done",)


def test_string_availability_is_rejected():
    try:
        SpecialistResult(
            specialist="beacon",
            result_id="beacon-string-state",
            observed_at=NOW,
            availability="contained",
        )
    except ValueError as exc:
        assert "SpecialistAvailability" in str(exc)
    else:
        raise AssertionError("string availability bypassed the typed contract")


def test_non_rootline_specialist_cannot_inject_water_energy_signal():
    signal = CoordinationSignal(
        "grid_cost", "peak", _provenance("beacon", "beacon-signal")
    )
    try:
        SpecialistResult(
            specialist="beacon",
            result_id="beacon-signal",
            observed_at=NOW,
            coordination_signals=(signal,),
        )
    except ValueError as exc:
        assert "not owned" in str(exc)
    else:
        raise AssertionError("BEACON injected a ROOTLINE coordination signal")


def _demand(demand_id, *, value, needed_hours, completed=False, hours=1):
    raw = "".join(ch for ch in demand_id.upper() if ch.isalnum()) or "A"
    safe = raw if len(raw) <= 8 else raw[:5] + raw[-3:]
    return CustomerDemandEvidence(
        demand_id=demand_id,
        family_label=f"Opportunity {safe}",
        quantity=2,
        sex="female",
        minimum_weight_kg=10,
        maximum_weight_kg=15,
        needed_by=NOW + timedelta(hours=needed_hours),
        commercial_value_score=value,
        provenance=_provenance("sam_livestock", f"sam-{demand_id}", hours),
        completed=completed,
    )


def _inventory(
    animal_ref,
    status,
    demand_ids,
    *,
    weight=None,
    eligible=True,
    completed=False,
    hours=1,
):
    raw = "".join(ch for ch in animal_ref.upper() if ch.isalnum()) or "A"
    safe = raw if len(raw) <= 8 else raw[:5] + raw[-3:]
    return SaleInventoryEvidence(
        animal_ref=animal_ref,
        family_label=f"Animal {safe}",
        sex="female",
        current_weight_kg=weight,
        weight_observed_at=NOW - timedelta(hours=hours) if weight else None,
        sale_eligible_without_weight=eligible,
        status=status,
        compatible_demand_ids=tuple(demand_ids),
        provenance=_provenance("herdmaster", f"herd-{animal_ref}", hours),
        completed=completed,
    )


def test_demand_to_weighing_ranks_measurements_by_supported_value_and_urgency():
    demands = (
        _demand("urgent-high", value=90, needed_hours=12),
        _demand("later", value=40, needed_hours=120),
    )
    inventory = (
        _inventory("A-opaque", "needs_fresh_weight", ("urgent-high", "later")),
        _inventory("B-opaque", "needs_fresh_weight", ("later",)),
        _inventory("C-opaque", "usable_now", ("urgent-high",), weight=12),
    )
    packet = build_sales_weighing_packet(demands, inventory, now=NOW)
    assert packet.status == "ready"
    assert [row["animal_ref"] for row in packet.weigh_next] == [
        "A-opaque",
        "B-opaque",
    ]
    assert packet.usable_inventory_now[0]["animal_ref"] == "C-opaque"
    assert packet.family_actions["dad"][0].startswith(
        "Observe the current weight for Animal AOPAQUE"
    )
    assert packet.family_question == ""
    assert packet.writes_performed == 0


def test_demand_to_weighing_suppresses_completed_stale_and_blocked_work():
    demands = (
        _demand("current", value=80, needed_hours=24),
        _demand("completed", value=100, needed_hours=1, completed=True),
        _demand("stale", value=100, needed_hours=1, hours=30),
    )
    inventory = (
        _inventory("current-animal", "needs_fresh_weight", ("current",)),
        _inventory(
            "completed-animal",
            "needs_fresh_weight",
            ("current",),
            completed=True,
        ),
        _inventory("blocked-animal", "blocked", ("current",), eligible=False),
        _inventory("stale-animal", "needs_fresh_weight", ("current",), hours=30),
    )
    packet = build_sales_weighing_packet(demands, inventory, now=NOW)
    assert [row["animal_ref"] for row in packet.weigh_next] == ["current-animal"]
    assert [row["demand_id"] for row in packet.customer_opportunity_unlocked] == [
        "current"
    ]


def test_demand_to_weighing_assigns_at_most_three_measurements():
    base = _demand("cap", value=50, needed_hours=48)
    demand = CustomerDemandEvidence(**{**base.__dict__, "quantity": 5})
    inventory = tuple(
        _inventory(f"animal-{index}", "needs_fresh_weight", ("cap",))
        for index in range(5)
    )
    packet = build_sales_weighing_packet((demand,), inventory, now=NOW)
    assert len(packet.weigh_next) == 3
    assert len(packet.family_actions["dad"]) == 3
    assert packet.family_actions["charl"] == ()
    assert packet.family_actions["mom"] == ()


def test_missing_herdmaster_handover_yields_narrow_waiting_packet():
    packet = build_sales_weighing_packet(
        (_demand("known-demand", value=80, needed_hours=24),),
        (),
        now=NOW,
    )
    assert packet.status == "waiting_for_evidence"
    assert packet.evidence_gaps == (
        "fresh_herdmaster_sale_inventory_reconciliation",
    )
    assert packet.weigh_next == ()
    assert packet.family_question == ""
    assert packet.automatic_follow_up_instruction["customer_send"] is False


def test_weighing_brief_separates_inventory_work_opportunity_and_protection():
    packet = build_sales_weighing_packet(
        (_demand("brief-demand", value=80, needed_hours=24),),
        (
            _inventory(
                "brief-animal",
                "needs_fresh_weight",
                ("brief-demand",),
            ),
        ),
        now=NOW,
    )
    rendered = render_sales_weighing_packet(packet)
    assert "Usable inventory now:" in rendered
    assert "Weigh next:" in rendered
    assert "Customer opportunity unlocked:" in rendered
    assert "Protected decisions:" in rendered
    assert "promise" not in rendered.casefold()


def test_newer_completed_or_overlapping_evidence_suppresses_older_work():
    older_demand = _demand("same-demand", value=90, needed_hours=12, hours=2)
    newer_completed_demand = CustomerDemandEvidence(
        **{
            **older_demand.__dict__,
            "provenance": _provenance(
                "sam_livestock", "sam-same-demand-completed", 1
            ),
            "completed": True,
        }
    )
    older_animal = _inventory(
        "same-animal", "needs_fresh_weight", ("same-demand",), hours=2
    )
    newer_completed_animal = SaleInventoryEvidence(
        **{
            **older_animal.__dict__,
            "provenance": _provenance(
                "herdmaster", "herd-same-animal-completed", 1
            ),
            "completed": True,
        }
    )
    packet = build_sales_weighing_packet(
        (older_demand, newer_completed_demand),
        (older_animal, newer_completed_animal),
        now=NOW,
    )
    assert packet.weigh_next == ()
    assert packet.customer_opportunity_unlocked == ()


def test_missing_sam_evidence_is_not_turned_into_family_administration():
    packet = build_sales_weighing_packet(
        (),
        (_inventory("waiting", "needs_fresh_weight", ("unknown-demand",)),),
        now=NOW,
    )
    assert packet.status == "waiting_for_evidence"
    assert packet.family_question == ""
    assert packet.evidence_gaps == ("fresh_sam_customer_demand",)


def test_usable_now_requires_fresh_matching_measurement():
    demand = _demand("match", value=80, needed_hours=24)
    stale = _inventory("stale-weight", "usable_now", ("match",), weight=12, hours=30)
    wrong_weight = _inventory("wrong-weight", "usable_now", ("match",), weight=100)
    wrong_sex = SaleInventoryEvidence(
        **{
            **_inventory(
                "wrong-sex", "usable_now", ("match",), weight=12
            ).__dict__,
            "sex": "male",
        }
    )
    packet = build_sales_weighing_packet(
        (demand,), (stale, wrong_weight, wrong_sex), now=NOW
    )
    assert packet.usable_inventory_now == ()
    assert packet.status == "no_action_supported"


def test_invalid_or_future_usable_weight_is_rejected():
    base = _inventory("invalid-weight", "usable_now", ("d",), weight=12)
    for changes in (
        {"current_weight_kg": -1},
        {"current_weight_kg": float("nan")},
        {"weight_observed_at": NOW},
    ):
        try:
            SaleInventoryEvidence(**{**base.__dict__, **changes})
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid usable weight accepted: {changes}")


def test_family_renderer_uses_safe_labels_not_internal_references():
    demand = _demand("CUSTOMER-SECRET-123", value=80, needed_hours=24)
    animal = _inventory(
        "CANONICAL-PIG-ID-999",
        "needs_fresh_weight",
        ("CUSTOMER-SECRET-123",),
    )
    rendered = render_sales_weighing_packet(
        build_sales_weighing_packet((demand,), (animal,), now=NOW)
    )
    assert "CUSTOMER-SECRET-123" not in rendered
    assert "CANONICAL-PIG-ID-999" not in rendered
    assert "Opportunity CUSTO123" in rendered
    assert "Animal CANON999" in rendered


def test_smallest_weighing_set_respects_remaining_demand_quantity():
    quantity_one = CustomerDemandEvidence(
        **{**_demand("one", value=80, needed_hours=24).__dict__, "quantity": 1}
    )
    candidates = tuple(
        _inventory(f"candidate-{index}", "needs_fresh_weight", ("one",))
        for index in range(5)
    )
    packet = build_sales_weighing_packet((quantity_one,), candidates, now=NOW)
    assert len(packet.weigh_next) == 1

    quantity_two = _demand("two", value=80, needed_hours=24)
    usable = _inventory("usable-one", "usable_now", ("two",), weight=12)
    candidates = tuple(
        _inventory(f"remaining-{index}", "needs_fresh_weight", ("two",))
        for index in range(3)
    )
    packet = build_sales_weighing_packet(
        (quantity_two,), (usable, *candidates), now=NOW
    )
    assert len(packet.usable_inventory_now) == 1
    assert len(packet.weigh_next) == 1


def test_overlapping_demand_value_is_not_double_counted_per_animal():
    first = CustomerDemandEvidence(
        **{**_demand("first", value=90, needed_hours=12).__dict__, "quantity": 1}
    )
    second = CustomerDemandEvidence(
        **{**_demand("second", value=80, needed_hours=12).__dict__, "quantity": 1}
    )
    shared = _inventory(
        "shared", "needs_fresh_weight", ("first", "second", "first")
    )
    second_only = _inventory("second-only", "needs_fresh_weight", ("second",))
    packet = build_sales_weighing_packet(
        (first, second), (shared, second_only), now=NOW
    )
    assert [row["target_demand_id"] for row in packet.weigh_next] == [
        "first",
        "second",
    ]
    assert packet.weigh_next[0]["unlock_score"] == 190


def test_family_safe_label_collisions_are_rejected():
    first = _inventory("animal-one", "needs_fresh_weight", ("d",))
    second = SaleInventoryEvidence(
        **{
            **_inventory("animal-two", "needs_fresh_weight", ("d",)).__dict__,
            "family_label": first.family_label,
        }
    )
    try:
        build_sales_weighing_packet(
            (_demand("d", value=50, needed_hours=24),),
            (first, second),
            now=NOW,
        )
    except ValueError as exc:
        assert "duplicate family-safe animal label" in str(exc)
    else:
        raise AssertionError("ambiguous animal labels were accepted")


def test_exact_provenance_duplicate_conflicts_are_rejected():
    first = _demand("conflict", value=50, needed_hours=24)
    second = CustomerDemandEvidence(
        **{**first.__dict__, "commercial_value_score": 80}
    )
    try:
        build_sales_weighing_packet((first, second), (), now=NOW)
    except ValueError as exc:
        assert "conflicting duplicate evidence identity" in str(exc)
    else:
        raise AssertionError("same-provenance conflict was input-order dependent")


def test_asymmetric_usable_matching_avoids_unnecessary_weighing():
    d1 = CustomerDemandEvidence(
        **{**_demand("d1", value=90, needed_hours=12).__dict__, "quantity": 1}
    )
    d2 = CustomerDemandEvidence(
        **{**_demand("d2", value=80, needed_hours=12).__dict__, "quantity": 1}
    )
    flexible = _inventory("a-flex", "usable_now", ("d1", "d2"), weight=12)
    d1_only = _inventory("z-d1-only", "usable_now", ("d1",), weight=12)
    d2_weigh = _inventory("d2-weigh", "needs_fresh_weight", ("d2",))
    for rows in (
        (flexible, d1_only, d2_weigh),
        (d2_weigh, d1_only, flexible),
    ):
        packet = build_sales_weighing_packet((d1, d2), rows, now=NOW)
        assert len(packet.usable_inventory_now) == 2
        assert packet.weigh_next == ()


def test_asymmetric_weighing_matching_covers_both_demands():
    d1 = CustomerDemandEvidence(
        **{**_demand("wd1", value=90, needed_hours=12).__dict__, "quantity": 1}
    )
    d2 = CustomerDemandEvidence(
        **{**_demand("wd2", value=80, needed_hours=12).__dict__, "quantity": 1}
    )
    flexible = _inventory(
        "a-weigh-flex", "needs_fresh_weight", ("wd1", "wd2")
    )
    d1_only = _inventory("z-weigh-d1", "needs_fresh_weight", ("wd1",))
    for rows in ((flexible, d1_only), (d1_only, flexible)):
        packet = build_sales_weighing_packet((d1, d2), rows, now=NOW)
        assert len(packet.weigh_next) == 2
        assert {row["target_demand_id"] for row in packet.weigh_next} == {
            "wd1",
            "wd2",
        }


def test_coordination_kernel_has_no_io_network_database_or_specialist_calls():
    source_path = (
        Path(__file__).parents[1]
        / "modules"
        / "oom_sakkie"
        / "farm_manager_loop.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imported_roots.isdisjoint(
        {"requests", "urllib", "http", "socket", "pathlib", "os", "subprocess",
         "psycopg", "psycopg2", "sqlalchemy", "modules"}
    )
