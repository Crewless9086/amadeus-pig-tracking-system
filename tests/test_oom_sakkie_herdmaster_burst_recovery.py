from modules.oom_sakkie.herdmaster_burst_recovery import (
    CanonicalSubject,
    ExistingLifecycle,
    ProviderReport,
    bind_reply,
    plan_anton_burst,
)


def _report(message_id, text, second):
    return ProviderReport(str(message_id), "anton", "farm", text, f"2026-08-26T08:06:{second:02d}+02:00")


def _untagged_previewer(litter_id, event_date, reason, **kwargs):
    count = kwargs["count"]
    return ({
        "success": True, "dry_run": True, "litter_id": litter_id,
        "event_date": event_date, "reason": reason, "piglet_count": count,
        "pig_ids": [f"pig-{n}" for n in range(count)], "rows_updated": 0,
    }, 200)


def _tagged_previewer(litter_id, event_date, reason, **kwargs):
    return ({"success": False, "errors": ["Tagged piglets must be selected specifically before recording a death."]}, 409)


def _burst(previewer=_untagged_previewer):
    reports = [
        _report(4057, "Vark nr 138 dood op 26 Aug; verwyder en begrawe", 7),
        _report(4054, "Linda kleintjies dood op 26 Aug", 4),
        _report(4050, "Vark nr 146 dood op 23 Aug 2026", 0),
        _report(4052, "Linds 3 kleintjies dood", 2),
        _report(4051, "Mona 12 kleintjies. 1 dood gebore op 26 Aug", 1),
    ]
    return plan_anton_burst(
        reports,
        [CanonicalSubject("Linda", "PIG-LINDA", "LITTER-LINDA")],
        [ExistingLifecycle("4051", "expired", "old-mona"), ExistingLifecycle("4057", "completed", "done-138")],
        previewer=previewer,
    )


def test_burst_order_preserves_independent_lifecycles_and_terminal_138():
    items = _burst()
    assert {item.subject for item in items} == {"146", "138", "Linda", "Mona"}
    assert len({item.operation_key for item in items}) == 4
    assert next(item for item in items if item.subject == "138").state == "already_completed"
    mona = next(item for item in items if item.subject == "Mona")
    assert mona.state == "repreview_required"
    assert mona.known == {"total_born": 12, "stillborn": 1, "event_date": "2026-08-26"}
    pig146 = next(item for item in items if item.subject == "146")
    assert pig146.known["death_date"] == "2026-08-23"
    assert pig146.missing == ("removed_disposal",)


def test_linds_typo_corroborates_linda_without_duplicate_deaths():
    linda = next(item for item in _burst() if item.subject == "Linda")
    assert linda.provider_message_ids == ("4052", "4054")
    assert linda.known["count"] == 3
    assert linda.known["preview"]["piglet_count"] == 3
    assert linda.known["preview"]["rows_updated"] == 0
    assert len([item for item in _burst() if item.action == "mark_litter_piglets_dead"]) == 1


def test_tagged_litter_requests_only_missing_selector():
    linda = next(item for item in _burst(_tagged_previewer) if item.subject == "Linda")
    assert linda.state == "needs_fact"
    assert linda.missing == ("pig_ids_or_sex_counts",)
    assert linda.known["count"] == 3
    assert linda.known["event_date"] == "2026-08-26"


def test_entity_free_reply_is_ambiguous_but_explicit_tag_binds():
    items = _burst()
    assert bind_reply(items, "Ja") is None
    assert bind_reply(items, "Ja, 146 is verwyder en begrawe") .subject == "146"
    assert bind_reply(items, "Bevestig Linda") .subject == "Linda"
    assert bind_reply(items, "2138 is verwyder") is None
    assert bind_reply(items, "Lindale is reg") is None


def test_provider_retry_order_is_stable_and_does_not_duplicate():
    first = _burst()
    second = _burst()
    assert [(item.subject, item.operation_key) for item in first] == [
        (item.subject, item.operation_key) for item in second
    ]


def test_incremental_correction_retains_operation_identity():
    subjects = [CanonicalSubject("Linda", "PIG-LINDA", "LITTER-LINDA")]
    initial = plan_anton_burst(
        [_report(4052, "Linds 3 kleintjies dood op 26 Aug", 2)], subjects, [],
        previewer=_untagged_previewer,
    )
    corrected = plan_anton_burst(
        [
            _report(4052, "Linds 3 kleintjies dood op 26 Aug", 2),
            _report(4054, "Linda kleintjies dood op 26 Aug", 4),
        ], subjects, [], previewer=_untagged_previewer,
    )
    assert len(initial) == len(corrected) == 1
    assert initial[0].operation_key == corrected[0].operation_key
    assert corrected[0].provider_message_ids == ("4052", "4054")


def test_linda_chronology_never_combines_cross_owner_or_chat():
    reports = [
        _report(4052, "Linds 3 kleintjies dood op 26 Aug", 2),
        ProviderReport("other-owner", "someone-else", "farm", "Linda 3 kleintjies dood op 26 Aug", "2026-08-26T08:06:03+02:00"),
        ProviderReport("other-chat", "anton", "group-chat", "Linda 3 kleintjies dood op 26 Aug", "2026-08-26T08:06:04+02:00"),
    ]
    items = plan_anton_burst(
        reports, [CanonicalSubject("Linda", "PIG-LINDA", "LITTER-LINDA")], [],
        previewer=_untagged_previewer,
    )
    linda_items = [item for item in items if item.subject == "Linda"]
    assert len(linda_items) == 3
    assert all(len(item.provider_message_ids) == 1 for item in linda_items)
    assert len({item.operation_key for item in linda_items}) == 3
