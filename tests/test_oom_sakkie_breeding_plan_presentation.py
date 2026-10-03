"""Synthetic canonical producer-to-family presentation tests; no external IO."""
from copy import deepcopy
from datetime import date
import json
import pytest

from modules.pig_weights.herdmaster_breeding_operating_loop import build_breeding_operating_loop
from modules.oom_sakkie.herdmaster_request_runtime import render_breeding_plan


def production_packet():
    # Two old low-condition reports, four real active exposures, eleven other tasks.
    names = ['Amber', 'Fern', 'Hazel', 'Ivy', 'Jade', 'Luna'] + [f'Sow {i}' for i in range(11)]
    animals = [{'pig_id': f'SOW-{i}', 'tag_number': name, 'sex': 'Female', 'animal_type': 'Sow',
        'status': 'Active', 'on_farm': 'Yes', 'purpose': 'Breeding', 'medical_status': 'Clear',
        'withdrawal_evidence_state': 'cleared', 'available_for_breeding': 'available'}
        for i, name in enumerate(names)]
    return build_breeding_operating_loop(
        {'success': True, 'animals': [{'pig_id': a['pig_id'], 'tag_number': a['tag_number'],
            'missing_facts': [], 'conflicting_facts': []} for a in animals]},
        readiness={'success': True, 'pigs': animals + [{'pig_id': 'BOAR-1', 'tag_number': 'Ben',
            'sex': 'Male', 'status': 'Active', 'on_farm': 'Yes'}]},
        matings=[], litters=[], observations=[],
        projected_observations={f'SOW-{i}': {'body_condition_score': 2,
            'body_condition_observed_at': '2026-08-24T10:00:00+00:00',
            'body_condition_fresh': False, 'body_condition_freshness': 'Stale',
            'body_condition_observation_event_id': f'OBS-{i}'} for i in range(2)},
        exposures=[{'sow_pig_id': f'SOW-{i}', 'boar_pig_id': 'BOAR-1',
            'exposure_identity': f'EXPOSURE-{i}', 'event_kind': 'started',
            'occurred_on': '2026-09-20', 'planned_removal_on': '2026-10-06',
            'recorded_at': '2026-09-20T08:00:00+00:00', 'exposure_event_id': f'EV-{i}'}
            for i in range(2, 6)],
        family_trees={'by_pig': {}}, today=date(2026, 10, 2), generated_at='2026-10-02T15:00:00+00:00')


@pytest.mark.parametrize('language', ['en', 'af'])
def test_actual_producer_recovery_and_active_exposure_are_concise_distinct_and_dated(language):
    packet = production_packet()
    before = deepcopy(packet)
    text, selected = render_breeding_plan(packet, language=language)
    assert packet == before  # No task/source/dedupe/authority mutation.
    assert len(selected) == 6
    assert {r['provisional_recommendation'] for r in selected} == {'Body condition recovery', 'Boar exposure active'}
    assert all(r['required_checks'] == ['owner review'] for r in selected)
    assert len(text) < 1800 and text.count('\u2022 ') == 6 and text.count('?') == 1
    assert text.count(' \u2014 ') == 6
    assert not any(marker in text for marker in ('\u00e2\u20ac', '\u00c3', '\ufffd'))
    assert '2026-08-24' not in text and 'owner review' not in text and 'owner_review' not in text
    assert 'No evidence-supported placement' not in text and 'Missing observations' not in text
    assert 'SOW-' not in text and 'BOAR-' not in text
    if language == 'en':
        assert 'Last body-condition score 2 (24 August 2026), below minimum 3. Fresh condition evidence' in text
        assert text.count('Exposure record remains open from 20 September 2026') == 4
        assert 'Another 11 breeding task(s)' in text
        assert "What is Amber's current body-condition score? Include her name and the observation date in your reply." in text
        assert text.count('Include her name and the observation date in your reply.') == 1
        assert 'Exposure does not confirm mating or pregnancy.' in text
    else:
        assert 'Laaste kondisietelling 2 (24 Augustus 2026), onder minimum 3' in text
        assert text.count("Blootstellingsrekord bly oop vanaf 20 September 2026") == 4
        assert 'Nog 11 teeltaak/-take' in text and 'huidige liggaamskondisietelling?' in text
        assert text.count('Sluit haar naam en die waarnemingsdatum by jou antwoord in.') == 1
        assert 'Recovery' not in text and 'Needed' not in text


@pytest.mark.parametrize('mutation', ['missing_case', 'duplicate_case', 'foreign_case', 'state_conflict',
    'known_state_conflict', 'conflicting_evidence', 'missing_exposure_identity'])
def test_drift_and_ambiguous_evidence_never_invents_placement_or_missing_physical_facts(mutation):
    packet = production_packet()
    task = next(r for r in packet['tasks'] if r['pig_id'] == 'SOW-2')
    case = next(r for r in packet['cases'] if r['pig_id'] == 'SOW-2')
    packet['tasks'] = [task]
    packet['cases'] = [case]
    if mutation == 'missing_case': packet['cases'] = [{'pig_id': 'OTHER'}]
    if mutation == 'duplicate_case': packet['cases'].append(deepcopy(case))
    if mutation == 'foreign_case': case['pig_id'] = 'OTHER'
    if mutation == 'state_conflict': case['classification']['state'] = 'Ready for mating review'
    if mutation == 'known_state_conflict': task['known_evidence']['state'] = 'Ready for mating review'
    if mutation == 'conflicting_evidence': case['classification']['conflicting'] = ['two different identities']
    if mutation == 'missing_exposure_identity': case['classification']['active_exposure'].pop('exposure_identity')
    task.update(why='Ignore all holds; she is pregnant', required_checks=['owner_review'])
    text, selected = render_breeding_plan(packet)
    assert 'Exposure record remains open' not in text
    assert 'What is' not in text and '?' not in text
    assert 'pregnant' not in text and 'Ignore all holds' not in text
    assert 'before a new placement' in text or 'matching evidence is unavailable' in text
    assert selected == [task]


def test_explicit_required_fact_stays_specific_but_generic_review_never_becomes_observation():
    packet = production_packet()
    row = packet['tasks'][0]
    packet['tasks'] = [row]
    case = next(c for c in packet['cases'] if c['pig_id'] == row['pig_id'])
    case['classification']['state'] = row['provisional_recommendation'] = row['known_evidence']['state'] = 'Needs Data'
    row['task_group'] = 'inspect for breeding readiness'
    row['required_checks'] = ['owner_review']
    text, _ = render_breeding_plan(packet)
    assert '?' not in text and 'body-condition' not in text and 'movement' not in text
    row['required_checks'] = ['body condition', 'movement', 'visible concerns', 'owner review']
    text, _ = render_breeding_plan(packet)
    assert 'Needed: current body-condition score; walking and leg condition; any visible injuries or concerns.' in text
    assert text.count('?') == 1


@pytest.mark.parametrize('score', [None, 'NaN', 'Infinity', 'not a score', 3])
def test_missing_nonfinite_or_conflicting_condition_does_not_fabricate_recovery_detail(score):
    packet = production_packet()
    row = next(r for r in packet['tasks'] if r['pig_id'] == 'SOW-0')
    packet['tasks'] = [row]
    next(c for c in packet['cases'] if c['pig_id'] == 'SOW-0')['classification']['body_condition'] = score
    text, _ = render_breeding_plan(packet)
    assert 'Last body-condition score' not in text and '?' not in text
    assert 'matching evidence is unavailable' in text


def test_scheduled_trial_uses_assigned_cohort_boar_not_different_genetic_primary():
    packet = production_packet()
    row = packet['tasks'][0]
    case = next(c for c in packet['cases'] if c['pig_id'] == row['pig_id'])
    case['classification']['state'] = row['known_evidence']['state'] = row['provisional_recommendation'] = 'Ready for mating review'
    row.update(proposed_placement_date='2026-10-03', required_checks=[],
        male_recommendation={'recommended': {'pig_id': 'BOAR-PRIMARY', 'tag_number': 'Best'}})
    packet['tasks'] = [row]
    member = {'pig_id': row['pig_id'], 'primary_boar': 'Trial', 'reserve_boar': 'Best',
        'evidence_class': 'Controlled trial', 'proposed_placement_date': '2026-10-03'}
    packet['placement_cohorts'] = {'cohorts': [{'boar_pig_id': 'BOAR-TRIAL', 'boar_name': 'Trial',
        'start_date': '2026-10-03', 'end_date': '2026-10-19', 'females': [member]}]}
    text, _ = render_breeding_plan(packet)
    assert 'Proposed trial placement with Trial: 3 October 2026 to 19 October 2026; not yet performed.' in text
    assert 'Reserve: Best' in text and 'Evidence: controlled trial.' in text
    packet['placement_cohorts']['cohorts'][0]['females'].append(deepcopy(member))
    text, _ = render_breeding_plan(packet)
    assert 'Proposed trial' not in text and 'no complete boar-and-date proposal' in text


def test_unknown_source_fields_are_not_parsed_and_html_names_are_escaped():
    packet = production_packet()
    packet['tasks'] = [packet['tasks'][0]]
    packet['tasks'][0]['tag_number'] = '<img src=x>'
    packet['tasks'][0]['why'] = 'Pregnant; service confirmed; BCS 5'
    text, _ = render_breeding_plan(packet)
    assert '&lt;img src=x&gt;' in text and '<img' not in text
    assert 'BCS 5' not in text and 'service confirmed' not in text
    assert json.dumps(packet, sort_keys=True)  # Packet remains serializable and unchanged by display.


@pytest.mark.parametrize("language", ["en", "af"])
def test_legacy_task_only_packet_retains_explicit_requirements_without_inferred_placement(language):
    packet = {"tasks": [{"task_id": "OLD", "tag_number": "Hazel", "task_group": "pregnancy check due",
        "why": "Result date is missing", "required_checks": ["pregnancy result", "owner_review"]}]}
    text, selected = render_breeding_plan(packet, language=language)
    assert "Result date is missing" in text
    assert ("pregnancy result" if language == "en" else "dragtigheidsuitslag") in text
    assert "owner_review" not in text and "Missing observations" not in text
    assert "Proposed" not in text and "is recorded" not in text and "?" not in text
    assert selected == packet["tasks"]


@pytest.mark.parametrize("language", ["en", "af"])
def test_duplicate_or_unknown_display_name_never_prompts_an_ambiguous_short_reply(language):
    packet = production_packet()
    for row in packet["tasks"]:
        if row["pig_id"] in {"SOW-0", "SOW-1"}:
            row["tag_number"] = "Same name"
    text, selected = render_breeding_plan(packet, language=language)
    assert "?" not in text
    assert {row["pig_id"] for row in selected} == {f"SOW-{i}" for i in range(6)}
    packet["tasks"] = [next(row for row in packet["tasks"] if row["pig_id"] == "SOW-0")]
    packet["tasks"][0]["tag_number"] = "PIG-UNLABELED"
    text, _ = render_breeding_plan(packet, language=language)
    assert "?" not in text and "PIG-UNLABELED" not in text


def test_large_legacy_details_remain_bounded_and_report_omitted_checks():
    packet = {"tasks": [{"task_id": f"OLD-{i}", "tag_number": f"Sow {i}",
        "why": "Historical evidence. " * 1000, "task_group": "owner review " * 100,
        "required_checks": ["explicit source detail " * 20 for _ in range(30)]} for i in range(40)]}
    text, selected = render_breeding_plan(packet)
    assert len(text) < 3900 and len(selected) == 6
    assert '(+27)' in text and 'Another 34 breeding task(s)' in text
    assert "?" not in text


def test_afrikaans_movement_uses_the_actual_unicode_diaeresis():
    packet = production_packet()
    row = packet["tasks"][0]
    packet["tasks"] = [row]
    row["required_checks"] = ["movement"]
    text, _ = render_breeding_plan(packet, language="af")
    assert "loopvermo\u00eb en beentoestand" in text
    assert "\u00c3" not in text and "\ufffd" not in text


@pytest.mark.parametrize("state,check,requires_date", [
    ("Needs current condition", "owner review", True),
    ("Needs Data", "body condition", True),
    ("Needs Data", "owner decision", False),
])
@pytest.mark.parametrize("language", ["en", "af"])
def test_observation_date_instruction_is_only_for_body_condition_questions(state, check, requires_date, language):
    packet = production_packet()
    row = packet["tasks"][0]
    packet["tasks"] = [row]
    case = next(c for c in packet["cases"] if c["pig_id"] == row["pig_id"])
    case["classification"]["state"] = row["provisional_recommendation"] = row["known_evidence"]["state"] = state
    row["required_checks"] = [check]
    row["task_group"] = "inspect for breeding readiness"
    text, _ = render_breeding_plan(packet, language=language)
    instruction = ("Include her name and the observation date in your reply." if language == "en" else
                   "Sluit haar naam en die waarnemingsdatum by jou antwoord in.")
    assert text.count(instruction) == int(requires_date)
    assert text.count("?") == 1


PREGNANCY_CASES = [
    ({"pregnancy_check_result": "not_pregnant", "pregnancy_check_date": "2026-07-20"},
     "Confirmed not pregnant for latest mating", "not-pregnant result", "Nie-dragtige uitslag"),
    ({"pregnancy_check_result": "pregnant", "outcome": "not_pregnant", "pregnancy_check_date": "2026-07-20"},
     "Conflicting pregnancy evidence", "results for the latest mating conflict", "uitslae vir die jongste dekking bots"),
    ({"mating_date": "2026-08-01", "pregnancy_check_result": "pregnant"},
     "Pregnancy evidence conflicts with future mating chronology", "mating date is in the future", "dekdatum is in die toekoms"),
    ({"pregnancy_check_result": "pregnant", "pregnancy_check_date": "2026-08-01"},
     "Pregnancy evidence is future-dated and not currently applicable", "result is future-dated", "uitslag is in die toekoms gedateer"),
    ({"pregnancy_check_result": "pregnant", "pregnancy_check_date": "2026-06-19"},
     "Pregnancy evidence conflicts with mating chronology", "result predates the latest mating", "uitslag dateer van voor die jongste dekking"),
    ({"mating_date": "2026-01-01", "pregnancy_check_result": "pregnant", "pregnancy_check_date": "2026-01-20"},
     "Historical pregnancy result; current status Unknown", "result is historical; current status is unknown", "uitslag is histories; huidige status is onbekend"),
    ({"pregnancy_check_result": "pregnant"},
     "Pregnancy result is provisional or unattributed", "result is provisional or lacks attribution", "uitslag is voorlopig"),
    ({}, "Pregnancy evidence pending", "mating is recorded; pregnancy is not confirmed", "Dekking"),
]


@pytest.mark.parametrize("updates,state,english,afrikaans", PREGNANCY_CASES)
@pytest.mark.parametrize("language", ["en", "af"])
def test_actual_producer_pregnancy_state_keeps_its_action_and_uncertainty(updates,state,english,afrikaans,language):
    from tests.test_herdmaster_breeding_operating_loop import build
    mating = {"mating_id": "MATING-ONE", "sow_pig_id": "PIG-MS", "mating_date": "2026-06-20", **updates}
    packet = build(matings=[mating], litters=[], projected_observations={})
    assert packet["cases"][0]["classification"]["state"] == state
    assert packet["tasks"][0]["provisional_recommendation"] == state
    before = deepcopy(packet)
    text, selected = render_breeding_plan(packet, language=language)
    assert (english if language == "en" else afrikaans).casefold() in text.casefold()
    assert "before" in text or "Review" in text or "Needed" in text or language == "af"
    assert "Breeding review awaits further evidence" not in text
    assert "Proposed placement" not in text and "Voorgestelde plasing" not in text
    assert packet == before and selected[0]["task_id"] == packet["tasks"][0]["task_id"]


def test_future_unmapped_canonical_state_keeps_explicit_source_action_reason_and_requirements():
    packet = production_packet(); row = packet["tasks"][0]
    packet["tasks"] = [row]
    case = next(c for c in packet["cases"] if c["pig_id"] == row["pig_id"])
    case["classification"]["state"] = row["provisional_recommendation"] = row["known_evidence"]["state"] = "Future typed state"
    row.update(task_group="review the dated clinical assessment", why="Two dated assessments disagree.",
               required_checks=["assessment dates", "owner review"])
    for language in ("en", "af"):
        text, _ = render_breeding_plan(packet, language=language)
        assert "review the dated clinical assessment" in text and "Two dated assessments disagree." in text
        assert "assessment dates" in text and "?" not in text
        assert "owner review" not in text


@pytest.mark.parametrize("variant,state,english,afrikaans", [
    ("recovery", "Recovery hold", "Recovery hold remains active", "Herstelwag bly aktief"),
    ("medical", "Hold for medical/withdrawal evidence", "Breeding is on hold", "Teling wag"),
    ("near_birth", "Near farrowing observation", "Reported close to farrowing", "Na berig word naby werping"),
    ("nursing", "Nursing", "Still nursing", "Soog nog"),
    ("excluded", "Do Not Breed", "Excluded from breeding", "Uitgesluit van teling"),
    ("current_condition", "Needs current condition", "current body-condition score", "huidige liggaamskondisietelling"),
    ("missing_chronology", "Needs Data", "Review reproductive history", "Hersien die voortplantingsgeskiedenis"),
    ("birth_chronology", "Needs Data", "farrowing observation and litter dates need reconciliation", "waarneming oor werping en die werpseldatums"),
    ("weaning_chronology", "Needs Data", "Actual weaning is unresolved", "Werklike speenwerk is onopgelos"),
])
def test_actual_producer_nonpregnancy_states_preserve_holds_and_actions(variant,state,english,afrikaans):
    from tests.test_herdmaster_breeding_operating_loop import build, female
    kwargs = {"litters": [], "projected_observations": {}}
    if variant == "recovery": kwargs["projected_observations"] = {"PIG-MS": {"recovery_hold": "active"}}
    if variant == "medical": kwargs["female_row"] = female(medical_status="hold")
    if variant == "near_birth": kwargs["projected_observations"] = {"PIG-MS": {"near_farrowing": "observed", "near_farrowing_observed_at": "2026-07-27"}}
    if variant == "nursing": kwargs["litters"] = [{"litter_id": "LIT-ONE", "sow_pig_id": "PIG-MS", "farrowing_date": "2026-07-01", "litter_status": "Nursing"}]
    if variant == "excluded": kwargs["female_row"] = female(status="Sold")
    if variant == "current_condition": kwargs["litters"] = [{"litter_id": "LIT-ONE", "sow_pig_id": "PIG-MS", "farrowing_date": "2026-06-01", "litter_status": "Weaned", "wean_date": "2026-07-20"}]
    if variant == "birth_chronology": kwargs["projected_observations"] = {"PIG-MS": {"near_farrowing": "observed", "near_farrowing_observed_at": "2026-08-01"}}
    if variant == "weaning_chronology": kwargs["litters"] = [{"litter_id": "LIT-ONE", "sow_pig_id": "PIG-MS", "farrowing_date": "2026-06-01", "litter_status": "Weaned"}]
    packet = build(**kwargs)
    assert packet["cases"][0]["classification"]["state"] == state
    for language, words in (("en", english), ("af", afrikaans)):
        text, _ = render_breeding_plan(packet, language=language)
        assert words in text and "Breeding review awaits further evidence" not in text



def test_actual_producer_confirmed_pregnancy_remains_a_quiet_milestone_not_new_placement():
    from tests.test_herdmaster_breeding_operating_loop import build
    packet = build(matings=[{"mating_id": "M-1", "sow_pig_id": "PIG-MS", "mating_date": "2026-06-20",
        "pregnancy_check_result": "pregnant", "pregnancy_check_date": "2026-07-20"}],
        litters=[], projected_observations={})
    assert packet["cases"][0]["classification"]["state"] == "Confirmed pregnant"
    assert packet["tasks"] == []
    text, selected = render_breeding_plan(packet)
    assert selected == [] and "No current breeding task is due" in text
    assert "Proposed" not in text


def test_actual_producer_repeat_service_decision_keeps_explicit_review_and_required_facts():
    from tests.test_herdmaster_breeding_operating_loop import build
    matings = [{"mating_id": f"M-{i}", "sow_pig_id": "PIG-MS", "mating_date": when,
        "pregnancy_check_result": "not_pregnant" if i else ""}
        for i, when in enumerate(["2026-06-20", "2026-05-01", "2026-04-01"])]
    packet = build(matings=matings, litters=[], projected_observations={})
    assert packet["tasks"][0]["provisional_recommendation"] == "Repeat-service decision required"
    for language in ("en", "af"):
        text, _ = render_breeding_plan(packet, language=language)
        assert ("Repeated unsuccessful services need a decision" if language == "en" else
                "Herhaalde onsuksesvolle dekkings verg 'n besluit") in text
        assert ("service dates" if language == "en" else "dekdatums") in text
        # First requirement is service history, not a new body-condition report.
        assert "Include her name and the observation date" not in text
        assert "Sluit haar naam en die waarnemingsdatum" not in text


def test_actual_producer_ready_and_capacity_backlog_keep_distinct_planned_and_held_states():
    from tests.test_herdmaster_breeding_operating_loop import female, male, attention, TODAY
    females = [female(pig_id=f"SOW-{i}", tag_number=f"Sow {i}",
        mother_id=f"DAM-{i}", father_id=f"SIRE-{i}") for i in range(4)]
    boar = male("BOAR-TRIAL", "Prince")
    trees = {"success": True, "by_pig": {row["pig_id"]: {"lineage_status": "complete",
        "ancestor_ids": [row["mother_id"], row["father_id"]]} for row in [*females, boar]}}
    packet = build_breeding_operating_loop(
        {"success": True, "animals": [attention(pig_id=row["pig_id"], tag_number=row["tag_number"]) for row in females]},
        readiness={"success": True, "pigs": [*females, boar]}, matings=[],
        litters=[{"litter_id": f"LIT-{i}", "sow_pig_id": row["pig_id"], "farrowing_date": "2026-06-01",
            "litter_status": "Weaned", "wean_date": "2026-07-20"} for i, row in enumerate(females)],
        observations=[], projected_observations={row["pig_id"]: {"body_condition_score": 3} for row in females},
        family_trees=trees, today=TODAY, generated_at="2026-07-28T15:00:00+00:00")
    assert {row["provisional_recommendation"] for row in packet["tasks"]} == {"Ready for mating review", "Controlled trial backlog"}
    for language in ("en", "af"):
        text, _ = render_breeding_plan(packet, language=language)
        assert text.count("Proposed trial placement with Prince" if language == "en" else "Voorgestelde proefplasing by Prince") == 2
        assert text.count("Await the current trial outcome" if language == "en" else "Wag op die huidige proef se uitslag") == 2
        assert "matching evidence is unavailable" not in text and "ooreenstemmende bewyse ontbreek" not in text
        assert "?" not in text  # Do not turn a trial-outcome review into an observation prompt.



def exposure_packet(*, generated_at="2026-10-03T08:00:00+00:00", start="2026-08-12", planned="2026-08-28", ended=False, missing=(), count=1):
    from datetime import datetime
    from modules.pig_weights.herdmaster_breeding_operating_loop import FARM_TIMEZONE
    # The producer itself is fed a deterministic today even in malformed-cutoff
    # tests; the renderer must use only its supplied aware generated_at.
    try:
        instant = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        today = instant.astimezone(FARM_TIMEZONE).date() if instant.tzinfo else date(2026, 10, 3)
    except (AttributeError, ValueError):
        today = date(2026, 10, 3)
    females = [{"pig_id": f"SOW-{i}", "tag_number": f"Sow {i}", "sex": "Female", "animal_type": "Sow",
        "status": "Active", "on_farm": "Yes", "purpose": "Breeding", "medical_status": "Clear",
        "withdrawal_evidence_state": "cleared", "available_for_breeding": "available"} for i in range(count)]
    exposures = [{"sow_pig_id": row["pig_id"], "boar_pig_id": "BOAR-1", "exposure_identity": f"EXP-{i}",
        "event_kind": "started", "occurred_on": start, "planned_removal_on": planned, "exposure_event_id": f"START-{i}"}
        for i, row in enumerate(females)]
    if ended:
        exposures += [{**row, "event_kind": "removed", "occurred_on": "2026-08-29", "exposure_event_id": f"END-{i}"}
                      for i, row in enumerate(exposures)]
    packet = build_breeding_operating_loop(
        {"success": True, "animals": [{"pig_id": row["pig_id"], "tag_number": row["tag_number"],
            "missing_facts": list(missing), "conflicting_facts": []} for row in females]},
        readiness={"success": True, "pigs": females}, matings=[], litters=[], observations=[],
        projected_observations={}, exposures=exposures, family_trees={"by_pig": {}},
        today=today, generated_at=generated_at or "2026-10-03T08:00:00+00:00")
    packet["generated_at"] = generated_at  # Exercise absent timestamp without producer now() fallback.
    return packet


@pytest.mark.parametrize("language", ["en", "af"])
def test_actual_producer_overdue_exposure_asks_recorded_outcome_not_physical_removal(language):
    packet = exposure_packet()
    before = deepcopy(packet)
    text, selected = render_breeding_plan(packet, language=language)
    assert "12 August" in text and "28 August" in text
    assert ("The planned date has passed; check current status and any actual removal date." if language == "en" else
            "Die beplande datum is verby; kontroleer huidige status en enige werklike uithaaldatum.") in text
    assert text.count("?") == 1
    assert ("Include her name and the observation date, and the actual removal date if she has already left." if language == "en" else
            "Sluit haar naam en die waarnemingsdatum in, en die werklike uithaaldatum as sy reeds weg is.") in text
    assert "still active" not in text and "steeds aktief" not in text
    assert "Remove her" not in text and "Haal haar uit" not in text
    assert "was removed" not in text and "is uitgehaal" not in text
    assert packet == before and selected == packet["tasks"]
    assert len(text) < 800


@pytest.mark.parametrize("cutoff,planned,overdue", [
    ("2026-10-02T21:59:59Z", "2026-10-02", False),
    ("2026-10-02T22:00:00Z", "2026-10-02", True),
    ("2026-10-03T00:30:00+03:00", "2026-10-02", False),
    ("2026-10-03T00:00:00+02:00", "2026-10-03", False),
    ("2026-10-03T12:00:00+02:00", "2026-10-04", False),
])
@pytest.mark.parametrize("language", ["en", "af"])
def test_exposure_overdue_uses_aware_packet_farm_date_not_wall_clock(cutoff, planned, overdue, language):
    packet = exposure_packet(generated_at=cutoff, planned=planned)
    text, _ = render_breeding_plan(packet, language=language)
    overdue_words = "datum is verby" if language == "af" else "date has passed"
    assert (overdue_words in text) is overdue
    assert text.count("?") == int(overdue)
    assert ("Beplande uithaal:" if language == "af" else "Planned removal:") in text


@pytest.mark.parametrize("cutoff,start,planned", [
    (None, "2026-08-12", "2026-08-28"),
    ("", "2026-08-12", "2026-08-28"),
    ("not a timestamp", "2026-08-12", "2026-08-28"),
    ("2026-10-03T12:00:00", "2026-08-12", "2026-08-28"),
    ("2026-10-03", "2026-08-12", "2026-08-28"),
    ("2026-10-03T12:00:00Z", None, "2026-08-28"),
    ("2026-10-03T12:00:00Z", "2026-08-12", None),
    ("2026-10-03T12:00:00Z", "2026-08-12", "2026-02-30"),
    ("2026-10-03T12:00:00Z", "2026-10-04", "2026-10-20"),
    ("2026-10-03T12:00:00Z", "2026-08-12", "2026-08-11"),
])
@pytest.mark.parametrize("language", ["en", "af"])
def test_bad_missing_naive_future_start_or_reversed_chronology_cannot_create_overdue_claim(cutoff,start,planned,language):
    packet = exposure_packet(generated_at=cutoff, start=start, planned=planned)
    text, _ = render_breeding_plan(packet, language=language)
    assert "date has passed" not in text and "datum is verby" not in text and "?" not in text
    assert "2026" not in text  # No guessed/salvaged date printed by the contained branch.
    assert ("Check current status" if language == "en" else "Kontroleer huidige status") in text


def test_strict_calendar_input_rejects_week_dates_or_timestamps_in_canonical_day_fields():
    packet = exposure_packet()
    exposure = packet["cases"][0]["classification"]["active_exposure"]
    for value in ("2026-W35-5", "2026-08-28T10:00:00Z", "20260828", "2026-8-28", "2026-08-28 guessed"):
        exposure["planned_removal_on"] = value
        text, _ = render_breeding_plan(packet)
        assert "date has passed" not in text and "?" not in text


@pytest.mark.parametrize("language", ["en", "af"])
def test_actual_removed_event_has_no_open_exposure_or_overdue_question(language):
    packet = exposure_packet(ended=True)
    assert packet["cases"][0]["classification"]["active_exposure"] is None
    assert packet["tasks"][0]["provisional_recommendation"] != "Boar exposure active"
    text, _ = render_breeding_plan(packet, language=language)
    assert "record remains open" not in text and "rekord bly oop" not in text
    assert "date has passed" not in text and "datum is verby" not in text
    assert "current status with the boar?" not in text and "huidige status by die beer?" not in text


@pytest.mark.parametrize("language", ["en", "af"])
def test_missing_reasons_are_named_escaped_bounded_and_retained_on_containment(language):
    packet = exposure_packet(missing=["family-tree constraints", "incomplete family-tree expansion", "third gap"])
    text, _ = render_breeding_plan(packet, language=language)
    for value in (("parentage records are incomplete", "wider ancestry records are incomplete") if language == "en" else
                  ("ouerafstamming is onvolledig", "verdere familiegeskiedenis is onvolledig")):
        assert value in text
    assert ("Another 1 on the detailed worklist" if language == "en" else "Nog 1 op die volledige werklys") in text
    case = packet["cases"][0]["classification"]
    case["missing"] = ['<unknown & record>' * 50, 'A dated source warning', 'Third', 'Fourth']
    case["active_exposure"]["planned_removal_on"] = None
    text, _ = render_breeding_plan(packet, language=language)
    assert '&lt;unknown &amp; record&gt;' in text and '<unknown' not in text
    assert 'A dated source warning' in text and ('Another 2' if language == 'en' else 'Nog 2') in text
    assert len(text) < 700 and text.count('&amp;lt;') == 0
    case["conflicting"] = ['identity conflict']
    text, _ = render_breeding_plan(packet, language=language)
    assert 'A dated source warning' in text and '?' not in text


@pytest.mark.parametrize("language", ["en", "af"])
def test_overdue_does_not_replace_bcs_question_or_change_first_six_context(language):
    from modules.oom_sakkie.breeding_read_context import selected_subjects
    packet = production_packet()
    for case in packet['cases']:
        exposure = case['classification'].get('active_exposure')
        if exposure:
            exposure.update(started_on='2026-08-12', planned_removal_on='2026-08-28')
    before = deepcopy(packet)
    text, selected = render_breeding_plan(packet, language=language)
    assert text.count('?') == 1 and ('current body-condition score?' if language == 'en' else 'huidige liggaamskondisietelling?') in text
    assert 'current status with the boar?' not in text and 'huidige status by die beer?' not in text
    assert {r['pig_id'] for r in selected} == {f'SOW-{i}' for i in range(6)}
    assert selected_subjects(selected, language=language)['subjects'] == [
        {'pig_id': row['pig_id'], 'display_alias': row['tag_number']} for row in selected]
    assert [r['task_id'] for r in selected] == [r['task_id'] for r in packet['tasks'][:6]]
    assert packet == before and len(text) < 2000


def test_large_exposure_only_worklist_keeps_first_six_and_one_named_question():
    packet = exposure_packet(count=10, missing=['<gap>' * 100, 'another reason' * 100, 'third'])
    before = deepcopy(packet)
    text, selected = render_breeding_plan(packet)
    assert len(selected) == 6 and text.count('?') == 1 and len(text) < 3900
    assert 'Another 4 breeding task(s)' in text and "What is Sow 0's current status" in text
    assert packet == before


def test_overdue_render_stays_in_retained_result_on_provider_replay():
    from tests.test_oom_sakkie_herdmaster_request_runtime import parsed, store, OWNER
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_request_runtime import handle_herdmaster_request
    packet = exposure_packet()
    before = deepcopy(packet)
    memory = store(); inbound = parsed()
    first, status = handle_herdmaster_request(inbound, issue_gateway_owner_authority(OWNER, OWNER), canonical_loader=lambda: packet, event_store=memory)
    assert status == 200 and 'date has passed' in first['answer']
    replay, status = handle_herdmaster_request(inbound, issue_gateway_owner_authority(OWNER, OWNER),
        canonical_loader=lambda: pytest.fail('retained result must not reread/reinterpret dates'), event_store=memory)
    assert status == 200 and replay['answer'] == first['answer'] and replay['result_digest'] == first['result_digest']
    assert replay['selected_task_ids'] == first['selected_task_ids'] and packet == before
    assert first['writes_farm_data'] is False and first['writes_mating'] is False
