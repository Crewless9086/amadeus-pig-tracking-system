from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

from modules.oom_sakkie.farm_manager_loop import (
    Authority,
    CoordinationSignal,
    FollowUp,
    Provenance,
    SpecialistAvailability,
    SpecialistResult,
    SpecialistWorkItem,
    SupportedAnswer,
    WorkState,
    answer_supported_question,
    build_family_brief,
    render_consolidated_brief,
    render_family_brief,
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
