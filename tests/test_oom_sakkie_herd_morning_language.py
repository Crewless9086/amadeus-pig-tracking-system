"""Real HERDMASTER producer -> daily plan -> family delivery language contract.

The factual shape retains the Sep13 morning's two named sows, 34 attributable
deaths, 0/74 weekly coverage and Molly's overdue weaning. Missing canonical row
identities are synthetic; all collectors, stores and transports are inert.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
import socket
from urllib import request as urllib_request

import pytest

from modules.oom_sakkie import daily_farm_manager as daily
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import farm_manager_runtime as runtime
from modules.oom_sakkie.farm_manager_loop import Authority, WorkState


NOW = datetime(2026, 9, 13, 4, 45, 16, 700392, tzinfo=timezone.utc)
RAW_AF_QUESTION = "Staan Prince nou en drink hy water?"
RAW_EN_QUESTION = "Is Prince standing and drinking now?"
TAGS = (
    "10, 103, 105, 106, 11, 111, 124, 128, 129, 13, 131, 132, 133, 134, 135, 136, "
    "137, 139, 14, 140, 141, 142, 143, 144, 145, 146, 147, 148, 15, 150, 152, "
    "153, 154, 155, 156, 157, 158, 160, 162, 163, 164, 165, 166, 167, 168, 169, "
    "17, 170, 171, 172, 174, 18, 19, 2, 20, 21, 22, 23, 25, 26, 3, 36, 39, 4, "
    "5, 56, 6, 61, 7, 83, 86, 89, 9, 98"
).split(", ")

EXPECTED = {'en': "<b>TODAY'S FARM PLAN</b>\n"
       '<b>ACTION NEEDED</b>\n'
       '1. <b>Weaning overdue — Molly</b>\n'
       'Molly&#x27;s litter was due for weaning on 2026-09-11 and is 2 days overdue; the canonical litter is '
       'still Active and no weaned count proves completion.\n'
       'Has Molly&#x27;s litter been weaned? If so, give the date and count; I will ask for missing details '
       'and prepare the confirmation.\n'
       '2. <b>Current farrowing status — Mysikind and Mona</b>\n'
       'The projected window 2026-08-22 to 2026-08-26 has passed. Current records do not confirm the outcome '
       'of these matings.\n'
       'Tell me the current outcome; if there was a litter, I will ask for its date and birth counts and '
       'prepare the confirmation.\n'
       '\n'
       '<b>OOM SAKKIE IS CHECKING AUTOMATICALLY</b>\n'
       '• <b>Mortality records — 34 deaths for review</b>\n'
       'Recorded deaths: 2026-09-13. HERDMASTER is reviewing these records for unresolved current follow-up; '
       'this total does not report new deaths today.\n'
       'HERDMASTER will check the related records and reopen a follow-up only when new or unresolved '
       'evidence requires it.\n'
       '• <b>Weighing: 0 of 74 recorded; 74 tag(s) need status reconciliation</b>\n'
       'For 2026-09-07 to 2026-09-13, 0/74 pigs in the current cohort have weights. Missing weights first '
       'require a check of sale, order and current farm status.\n'
       'HERDMASTER will reconcile the cohort&#x27;s current status before any new weighing instruction.\n'
       '\n'
       '<b>ONE QUESTION</b>\n'
       'What is the current status of Mysikind and Mona: already farrowed, returned to heat, or no clear '
       'change yet?',
 'af': '<b>VANDAG SE PLAASPLAN</b>\n'
       '<b>AKSIE NODIG</b>\n'
       '1. <b>Speenwerk laat — Molly</b>\n'
       'Molly se werpsel moes op 2026-09-11 gespeen word en is 2 dae laat; die huidige werpsel is steeds '
       'Aktief en geen gespeende telling bewys voltooiing nie.\n'
       'Is Molly se werpsel reeds gespeen? Indien wel, gee die datum en aantal; ek sal die ontbrekende '
       'besonderhede vra en die bevestiging voorberei.\n'
       '2. <b>Huidige werpstatus — Mysikind en Mona</b>\n'
       'Die verwagte tydperk 2026-08-22 tot 2026-08-26 is verby. Die huidige rekords bevestig nie die '
       'uitkoms van hierdie parings nie.\n'
       'Gee die huidige uitkoms; as daar &#x27;n werpsel was, sal ek die datum en geboortetellings vra en '
       'die bevestiging voorberei.\n'
       '\n'
       '<b>OOM SAKKIE KONTROLEER OUTOMATIES</b>\n'
       '• <b>Sterfterekords — 34 sterftes vir hersiening</b>\n'
       'Aangetekende sterftes: 2026-09-13. HERDMASTER hersien hierdie rekords vir enige onopgeloste huidige '
       'opvolg; die totaal is nie &#x27;n verslag van nuwe sterftes vandag nie.\n'
       'HERDMASTER gaan die verwante rekords na en heropen slegs &#x27;n opvolg wanneer nuwe of onopgeloste '
       'bewyse dit vereis.\n'
       '• <b>Weging: 0 van 74 aangeteken; 74 oormerk(e) se status moet nagegaan word</b>\n'
       'Vir 2026-09-07 tot 2026-09-13 het 0/74 varke in die huidige groep gewigte. Ontbrekende gewigte '
       'vereis eers &#x27;n kontrole van verkoop-, bestel- en huidige plaasstatus.\n'
       'HERDMASTER kontroleer die groep se huidige status voor enige nuwe weegopdrag.\n'
       '\n'
       '<b>EEN VRAAG</b>\n'
       'Wat is Mysikind en Mona se huidige status: reeds gewerp, weer op hitte, of nog geen duidelike '
       'verandering nie?'}

EXPECTED_REPLACEMENT = {'en': "<b>TODAY'S FARM PLAN</b>\n"
       '<b>ACTION NEEDED</b>\n'
       '1. <b>Current farrowing status — Mysikind and Mona</b>\n'
       'The projected window 2026-08-22 to 2026-08-26 has passed. Current records do not confirm the outcome '
       'of these matings.\n'
       'Tell me the current outcome; if there was a litter, I will ask for its date and birth counts and '
       'prepare the confirmation.\n'
       '\n'
       '<b>OOM SAKKIE IS CHECKING AUTOMATICALLY</b>\n'
       '• <b>Mortality records — 34 deaths for review</b>\n'
       'Recorded deaths: 2026-09-13. HERDMASTER is reviewing these records for unresolved current follow-up; '
       'this total does not report new deaths today.\n'
       'HERDMASTER will check the related records and reopen a follow-up only when new or unresolved '
       'evidence requires it.\n'
       '• <b>Weighing: 0 of 74 recorded; 74 tag(s) need status reconciliation</b>\n'
       'For 2026-09-07 to 2026-09-13, 0/74 pigs in the current cohort have weights. Missing weights first '
       'require a check of sale, order and current farm status.\n'
       'HERDMASTER will reconcile the cohort&#x27;s current status before any new weighing instruction.\n'
       '\n'
       '<b>ONE QUESTION</b>\n'
       'What is the current status of Mysikind and Mona: already farrowed, returned to heat, or no clear '
       'change yet?',
 'af': '<b>VANDAG SE PLAASPLAN</b>\n'
       '<b>AKSIE NODIG</b>\n'
       '1. <b>Huidige werpstatus — Mysikind en Mona</b>\n'
       'Die verwagte tydperk 2026-08-22 tot 2026-08-26 is verby. Die huidige rekords bevestig nie die '
       'uitkoms van hierdie parings nie.\n'
       'Gee die huidige uitkoms; as daar &#x27;n werpsel was, sal ek die datum en geboortetellings vra en '
       'die bevestiging voorberei.\n'
       '\n'
       '<b>OOM SAKKIE KONTROLEER OUTOMATIES</b>\n'
       '• <b>Sterfterekords — 34 sterftes vir hersiening</b>\n'
       'Aangetekende sterftes: 2026-09-13. HERDMASTER hersien hierdie rekords vir enige onopgeloste huidige '
       'opvolg; die totaal is nie &#x27;n verslag van nuwe sterftes vandag nie.\n'
       'HERDMASTER gaan die verwante rekords na en heropen slegs &#x27;n opvolg wanneer nuwe of onopgeloste '
       'bewyse dit vereis.\n'
       '• <b>Weging: 0 van 74 aangeteken; 74 oormerk(e) se status moet nagegaan word</b>\n'
       'Vir 2026-09-07 tot 2026-09-13 het 0/74 varke in die huidige groep gewigte. Ontbrekende gewigte '
       'vereis eers &#x27;n kontrole van verkoop-, bestel- en huidige plaasstatus.\n'
       'HERDMASTER kontroleer die groep se huidige status voor enige nuwe weegopdrag.\n'
       '\n'
       '<b>EEN VRAAG</b>\n'
       'Wat is Mysikind en Mona se huidige status: reeds gewerp, weer op hitte, of nog geen duidelike '
       'verandering nie?'}


def forbidden(*_args, **_kwargs):
    pytest.fail("The morning language regression attempted external I/O")


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    # The test runner also clears external credentials before collection.
    for name in tuple(os.environ):
        if any(token in name.upper() for token in (
            "DATABASE", "SUPABASE", "TELEGRAM", "CHATWOOT", "OPENAI", "API_KEY",
            "API_TOKEN", "RENDER", "OOM_SAKKIE_SEMANTIC", "LLM_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(urllib_request, "urlopen", forbidden)
    import requests
    import psycopg
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    for module, names in (
        (runtime, ("_load_active_lifecycles", "_load_observations",
                   "load_current_breeding_operating_loop", "load_daily_manager_evidence",
                   "build_current_rootline_specialist_result", "consume_current_mortality_packet",
                   "connect_bounded_postgres", "connect_bounded_read")),
        (daily, ("connect_bounded_read", "_semantic_prioritize")),
        (family, ("_event_store", "_send_telegram", "_edit_telegram", "_delete_telegram")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)


def daily_packet():
    assert len(TAGS) == 74
    return {
        "packet_type": "herdmaster.daily_manager_evidence.v1",
        "material_digest": "OFFLINE-MORNING-34-DEATHS-74-TAGS",
        "authority": {"read_only": True, "writes_farm_data": False,
                      "hardware_commands": 0, "sends_messages": False},
        "weight": {
            "window": {"start": "2026-09-07", "end": "2026-09-13"},
            "current_snapshot": {"covered": 0, "eligible_tagged": 74, "status": "partial"},
            "missing_eligible_tagged": [{"pig_id": f"OFFLINE-PIG-{index}", "tag": tag}
                                       for index, tag in enumerate(TAGS)],
            "breeding_excluded": [], "untagged_excluded": [], "inactive_off_farm": [],
            "unknown_eligibility": [], "conflicting_weight_evidence": [],
            "material_weight_findings": [], "historical_completion_percentage": None,
        },
        "mortality": {
            "digest_changed": True,
            "candidate_deaths": [{"pig_id": f"OFFLINE-DEATH-{index}",
                                  "event_id": f"OFFLINE-DEATH-EVENT-{index:02d}",
                                  "effective_date": "2026-09-13"} for index in range(34)],
            "durable_death_event_fingerprints": {
                f"OFFLINE-DEATH-EVENT-{index:02d}": f"OFFLINE-FINGERPRINT-{index}"
                for index in range(34)},
        },
    }


def snapshot(*, active=(), failed=False):
    tasks, observations = [], []
    for index, name in enumerate(("Mysikind", "Mona")):
        pig_id, mating_id = f"OFFLINE-SOW-{index}", f"OFFLINE-MATING-{index}"
        tasks.append({"pig_id": pig_id, "tag_number": name,
                      "known_evidence": {"current_mating_id": mating_id,
                                         "current_mating_date": "2026-05-02"}})
        observations.append({"pig_id": pig_id, "mating_id": mating_id,
                             "mating_date": "2026-05-02", "operational_result": "Assumed Pregnant",
                             "observed_signs": "OFFLINE-RETAINED-SHAPE",
                             "observed_at": "2026-08-10T04:45:00+00:00",
                             "source_identity": f"OFFLINE-OBSERVATION-{index}"})
    return {"failed": failed,
            "canonical": {"generated_at": NOW.isoformat(), "worklist_id": "OFFLINE-WORKLIST",
                          "tasks": tasks},
            "observations": observations, "active": list(active), "active_current": list(active),
            "daily_packet": daily_packet()}


def project(language, value=None):
    value = snapshot() if value is None else value
    before = deepcopy(value)
    result = runtime._project_herdmaster_snapshot(value, None, "OFFLINE-OWNER", NOW, language)
    assert value == before
    return result


def molly():
    return [{"Litter_ID": "OFFLINE-MOLLY-LITTER", "Sow_Pig_ID": "OFFLINE-MOLLY",
             "Sow_Tag_Number": "Molly", "Litter_Status": "Active",
             "Wean_Date": "2026-09-11", "Weaned_Count": None}]


def structural_item(item):
    structural = {key: value for key, value in item.__dict__.items()
            if key not in {"title", "why", "next_action", "genuine_question"}}
    structural["metadata"] = {key: value for key, value in item.metadata.items() if key != "owner_followup"}
    return structural


class MemoryDelivery:
    """Insert-once fake stores with the same recipient/status projection shape."""
    def __init__(self, monkeypatch, *, provider_confirms=True):
        self.daily_rows, self.family_rows = {}, {}
        self.family_calls, self.sends, self.deliveries = [], [], []
        self.replacements, self.deletions, self.lock_calls = [], [], []
        self.provider_confirms = provider_confirms
        # run_daily_farm_manager distinguishes its real store identity from
        # legacy injected test stores. Patch that identity to exercise replay.
        monkeypatch.setattr(daily, "daily_farm_manager_store", self.store_daily)

    def store_daily(self, action, identity, payload):
        if action == "load_daily":
            candidates = [row for row in self.daily_rows.values()
                          if row.get("daily_identity") == identity
                          and row.get("owner_user_id") == payload.get("owner_user_id")
                          and row.get("chat_id") == payload.get("chat_id")
                          and row.get("status") in {"presented", "unchanged", "provider_ambiguous"}]
            return deepcopy(candidates[-1]) if candidates else None
        if action == "load_answered_questions":
            return ()
        created = identity not in self.daily_rows
        if created:
            self.daily_rows[identity] = deepcopy(payload)
        return {"success": True, "created": created}

    def store_family(self, action, identity, payload):
        self.family_calls.append((action, identity))
        if action == "load":
            return [deepcopy(row) for row in self.family_rows.values()
                    if row.get("card_mission_id") == identity]
        created = identity not in self.family_rows
        if created:
            self.family_rows[identity] = deepcopy(payload)
        return {"success": True, "created": created}

    def sender(self, chat, text, **_kwargs):
        self.sends.append((chat, text))
        return ({"success": True, "telegram_message_id": f"OFFLINE-CARD-{len(self.sends)}"}
                if self.provider_confirms else {"success": False, "status": "offline_transport_unconfirmed"})

    def deliver(self, parsed, result, **kwargs):
        delivery = family.deliver_family_result(parsed, result, event_store=self.store_family,
            sender=self.sender, editor=forbidden, **kwargs)
        self.deliveries.append({"parsed": deepcopy(parsed), "input": deepcopy(result),
                                "kwargs": deepcopy(kwargs), "outcome": deepcopy(delivery)})
        return delivery

    @contextmanager
    def projection_lock(self, identity):
        self.lock_calls.append(("enter", identity))
        try:
            yield
        finally:
            self.lock_calls.append(("exit", identity))

    def delete(self, chat, message_id):
        # Cleanup must follow provider confirmation and durable supersession.
        assert any(row.get("state") == "brief_generation_delivered"
                   and row.get("chat_id") == chat for row in self.family_rows.values())
        assert any(row.get("state") == "brief_generation_superseded"
                   and row.get("superseded_telegram_message_id") == message_id
                   and row.get("chat_id") == chat for row in self.family_rows.values())
        self.deletions.append((chat, message_id))
        return {"success": True}

    def replace(self, parsed, result, **kwargs):
        value = family.replace_current_brief(parsed, result, event_store=self.store_family,
            sender=self.sender, deleter=self.delete, projection_lock=self.projection_lock, **kwargs)
        self.replacements.append({"parsed": deepcopy(parsed), "input": deepcopy(result),
                                   "kwargs": deepcopy(kwargs), "outcome": deepcopy(value)})
        return value

    def run(self, language, result, *, litters=()):
        return daily.run_daily_farm_manager(owner_user_id="OFFLINE-" + language,
            chat_id="OFFLINE-" + language, specialist_results=[result], litter_rows=litters,
            now=NOW, language=language, deliver=self.deliver,
            replace_brief=self.replace,
            semantic_prioritizer=lambda rows, **_kwargs: list(rows))

    def outcomes(self):
        return {key: row for key, row in self.daily_rows.items() if key.endswith((":OUTCOME", ":PRESENTED"))}


@pytest.mark.parametrize("failure", [TimeoutError, ValueError])
def test_rootline_refresh_failure_localizes_mixed_daily_brief_without_changing_authority(monkeypatch, failure):
    class FailedFuture:
        cancelled = False

        def result(self, *, timeout):
            assert timeout == 7.0
            raise failure("OFFLINE-ROOTLINE-REFRESH-UNAVAILABLE")

        def cancel(self):
            self.cancelled = True

    future = FailedFuture()

    class FailedExecutor:
        def submit(self, fn, *, operating_date, now):
            assert fn is runtime.build_current_rootline_specialist_result
            assert operating_date == NOW.date().isoformat() and now == NOW
            return future

    monkeypatch.setattr(runtime, "_ROOTLINE_REFRESH_EXECUTOR", FailedExecutor())
    captured = runtime._load_rootline_snapshot(NOW)
    original = repr(captured)
    projections = {language: runtime._project_rootline_snapshot(captured, NOW, language)
                   for language in ("en", "af")}
    assert repr(captured) == original and future.cancelled is True
    english, afrikaans = [projections[language].work_items[0] for language in ("en", "af")]
    assert structural_item(english) == structural_item(afrikaans)
    assert english.title == "Refresh today's irrigation decision"
    assert "do not start irrigation or commissioning" in english.next_action
    for item in (english, afrikaans):
        assert item.state is WorkState.WAITING_EVIDENCE and item.authority is Authority.ADVISORY
        assert item.genuine_question == "" and item.question_for == ""
        assert item.provenance.source_refs == (
            "canonical_rootline_refresh_not_available_within_manager_deadline",)

    memory = MemoryDelivery(monkeypatch)
    for language in ("en", "af"):
        def run():
            return daily.run_daily_farm_manager(owner_user_id="OFFLINE-" + language,
                chat_id="OFFLINE-" + language,
                specialist_results=[project(language), projections[language]], litter_rows=molly(),
                now=NOW, language=language, deliver=memory.deliver, replace_brief=memory.replace,
                semantic_prioritizer=lambda rows, **_kwargs: list(rows))
        first, replay = run(), run()
        assert first["status"] == "daily_manager_presented" and first["telegram_sends"] == 1
        assert replay["status"] == "daily_manager_unchanged_silent" and replay["telegram_sends"] == 0
        assert first["writes_farm_data"] is False and first["hardware_commands"] == 0
        assert first["protected_actions_performed"] is False
        delivery = memory.deliveries[-1]
        assert delivery["input"]["status"] == "daily_farm_manager_ready"
        assert not family.localize_recipient_result(
            delivery["parsed"], delivery["input"], specialist="OOM_SAKKIE"
        ).get("recipient_language_render_unrecognized")
        answer = delivery["input"]["answer"]
        assert projections[language].work_items[0].why in answer
        assert ("EEN VRAAG" if language == "af" else "ONE QUESTION") in answer
        assert ("Mysikind en Mona" if language == "af" else "Mysikind and Mona") in answer
    assert afrikaans.title == "Werk vandag se besproeiingsbesluit by"
    assert afrikaans.why == (
        "Die huidige krag-, weervoorspelling- en waterlesings kon nie almal betyds "
        "bygewerk word om besproeiing veilig aan te beveel nie.")
    assert "moenie besproeiing of ingebruikneming" in afrikaans.next_action
    assert len(memory.sends) == 2 and len(memory.family_rows) == 4
    assert len(memory.outcomes()) == 2


def test_real_retained_shape_projects_recipient_wording_with_same_facts_and_bindings():
    en, af = project("en"), project("af")
    assert en.result_id == af.result_id and en.observed_at == af.observed_at
    assert [structural_item(row) for row in en.work_items] == [structural_item(row) for row in af.work_items]
    far = next(row for row in af.work_items if row.dedupe_key.startswith("herdmaster:reproductive-status:"))
    assert far.title == "Huidige werpstatus — Mysikind en Mona"
    assert far.why == (
        "Die verwagte tydperk 2026-08-22 tot 2026-08-26 is verby. Die huidige rekords bevestig nie die uitkoms van hierdie parings nie."
    )
    assert "Gee die huidige uitkoms" in far.next_action
    assert "reeds gewerp" in far.genuine_question
    assert far.authority is Authority.ADVISORY and far.state is WorkState.DUE_TODAY
    weights = next(row for row in af.work_items if row.dedupe_key == "herdmaster:weekly-weight-evidence")
    assert weights.title == "Weging: 0 van 74 aangeteken; 74 oormerk(e) se status moet nagegaan word"
    assert "0/74" in weights.why and "2026-09-07 tot 2026-09-13" in weights.why
    assert ", ".join(TAGS) in weights.next_action
    assert "moenie hulle vir herweging aanwys voordat daardie bewyse bestaan nie" in weights.next_action
    assert weights.authority is Authority.READ_ONLY and weights.metadata["routine_weekly_weighing"] is True
    deaths = next(row for row in af.work_items if ":mortality-cluster:" in row.dedupe_key)
    assert deaths.title == "Sterfterekords — 34 sterftes vir hersiening"
    assert "2026-09-13" in deaths.why and "nie 'n verslag van nuwe sterftes vandag nie" in deaths.why
    assert deaths.next_action.endswith("Patrone bly verbande, nie diagnoses nie.")
    assert len(deaths.metadata["mortality_fingerprints"]) == 34
    assert deaths.metadata["welfare_exception"] is True and deaths.authority is Authority.ADVISORY


def test_real_herd_morning_en_af_full_messages_cross_family_once_per_recipient(monkeypatch):
    memory = MemoryDelivery(monkeypatch)
    for language in ("en", "af"):
        result = project(language)
        first = memory.run(language, result, litters=molly())
        replay = memory.run(language, result, litters=molly())
        assert first["status"] == "daily_manager_presented" and first["telegram_sends"] == 1
        assert first["writes_farm_data"] is False and first["hardware_commands"] == 0
        assert first["protected_actions_performed"] is False
        assert replay["status"] == "daily_manager_unchanged_silent" and replay["telegram_sends"] == 0
    assert memory.sends == [("OFFLINE-en", EXPECTED["en"]), ("OFFLINE-af", EXPECTED["af"])]
    assert len(memory.deliveries) == 2 and len(memory.family_rows) == 4
    assert len(memory.outcomes()) == 2
    assert len({row["kwargs"]["mission_id"] for row in memory.deliveries}) == 2
    assert len({row["kwargs"]["card_mission_id"] for row in memory.deliveries}) == 2
    for row in memory.deliveries:
        language = row["parsed"]["output_language"]
        card = row["kwargs"]["card_mission_id"]
        events = [event for event in memory.family_rows.values() if event["card_mission_id"] == card]
        assert {event["state"] for event in events} == {"delivery_attempted", "delivered"}
        assert all(event["text_sha256"] == hashlib.sha256(EXPECTED[language].encode()).hexdigest() for event in events)
        assert all(event["owner_user_id"] == event["chat_id"] == "OFFLINE-" + language for event in events)


@pytest.mark.parametrize("language", ["en", "af"])
def test_true_transport_ambiguity_keeps_one_attempt_across_production_shaped_replay(monkeypatch, language):
    memory = MemoryDelivery(monkeypatch, provider_confirms=False)
    result = project(language)
    first = memory.run(language, result, litters=molly())
    replay = memory.run(language, result, litters=molly())
    assert first["status"] == replay["status"] == "daily_manager_delivery_ambiguous"
    assert memory.sends == [("OFFLINE-" + language, EXPECTED[language])]
    assert {row["state"] for row in memory.family_rows.values()} == {"delivery_attempted", "contained"}
    assert memory.deliveries[1]["outcome"]["status"] == "family_message_delivery_ambiguous"
    assert all(row["kwargs"]["delivery_retry_authority"] is None for row in memory.deliveries)
    outcome, = memory.outcomes().values()
    assert outcome["status"] == "provider_ambiguous" and outcome["delivery_definitely_not_sent"] is False


def active_welfare(question=RAW_AF_QUESTION, *, reported_dead=False):
    return [{"pig_id": "OFFLINE-PRINCE", "tag_number": "Prince", "lifecycle_id": "OFFLINE-WELFARE",
             "state": "waiting_for_input", "card_message_id": "OFFLINE-EXISTING-WELFARE-CARD",
             "provider_timestamp": NOW.isoformat(), "current_question": question,
             "owner_text": "EXACT RETAINED OWNER FACT — do not translate or rewrite this field",
             "reported_dead": reported_dead}]


@pytest.mark.parametrize("failed", [False, True], ids=["successful_snapshot", "failed_snapshot"])
def test_both_welfare_projection_paths_preserve_exact_af_question_and_localize_generated_text(monkeypatch, failed):
    value = snapshot(active=active_welfare(), failed=failed)
    en, af = project("en", value), project("af", value)
    en_welfare = next(row for row in en.work_items if row.dedupe_key == "herdmaster:OFFLINE-PRINCE")
    welfare = next(row for row in af.work_items if row.dedupe_key == "herdmaster:OFFLINE-PRINCE")
    assert structural_item(welfare) == structural_item(en_welfare)
    assert welfare.genuine_question == welfare.next_action == RAW_AF_QUESTION
    assert welfare.title == "Vark Prince se welstandsopvolging"
    assert welfare.why == "'n Bestaande welstandsaak wag op een fisiese waarneming voordat HERDMASTER die rekordvoorskou kan voorberei."
    assert welfare.question_for == "charl" and welfare.authority is Authority.ADVISORY
    memory = MemoryDelivery(monkeypatch)
    first = memory.run("af", af)
    replay = memory.run("af", af)
    assert first["status"] == "daily_manager_presented" and replay["status"] == "daily_manager_unchanged_silent"
    assert len(memory.sends) == 1
    text = memory.sends[0][1]
    assert "<b>Vark Prince se welstandsopvolging</b>\n" in text
    assert "\n" + RAW_AF_QUESTION in text
    assert text.endswith("<b>EEN VRAAG</b>\n" + RAW_AF_QUESTION)
    assert "Pig Prince" not in text and "standing and drinking" not in text
    assert family._looks_afrikaans(text) is True


@pytest.mark.parametrize("failed", [False, True], ids=["successful_snapshot", "failed_snapshot"])
def test_unsupported_raw_english_question_stays_exact_and_is_truthfully_rejected_before_delivery(monkeypatch, failed):
    result = project("af", snapshot(active=active_welfare(RAW_EN_QUESTION), failed=failed))
    welfare = next(row for row in result.work_items if row.dedupe_key == "herdmaster:OFFLINE-PRINCE")
    assert welfare.genuine_question == welfare.next_action == RAW_EN_QUESTION
    memory = MemoryDelivery(monkeypatch)
    first = memory.run("af", result)
    replay = memory.run("af", result)
    for outcome in (first, replay):
        assert outcome["status"] == "daily_manager_recipient_language_rejected"
        assert outcome["delivery_failure_reason"] == "recipient_language_render_unrecognized"
        assert outcome["delivery_definitely_not_sent"] is True
        assert outcome["telegram_sends"] == outcome["telegram_edits"] == 0
    assert not memory.sends and not memory.family_calls and not memory.family_rows
    assert all(row["outcome"]["status"] == "recipient_language_render_unrecognized" for row in memory.deliveries)
    assert all(row["outcome"]["delivery_definitely_not_sent"] is True for row in memory.deliveries)
    assert all(row["kwargs"]["delivery_retry_authority"] is None for row in memory.deliveries)
    retained, = memory.outcomes().values()
    assert retained["status"] == "recipient_language_render_unrecognized"
    assert retained["delivery_definitely_not_sent"] is True
    assert len([key for key in memory.daily_rows if ":DELIVERY" in key]) == 2


@pytest.mark.parametrize("failed", [False, True], ids=["successful_snapshot", "failed_snapshot"])
def test_reported_dead_suppresses_stale_live_question_without_changing_followup_authority(monkeypatch, failed):
    result = project("af", snapshot(active=active_welfare(RAW_EN_QUESTION, reported_dead=True), failed=failed))
    welfare = next(row for row in result.work_items if row.dedupe_key == "herdmaster:OFFLINE-PRINCE")
    assert welfare.genuine_question == ""
    assert welfare.title == "Vark Prince se sterfterekordopvolging"
    assert welfare.why == "Die eienaar het aangemeld dat hierdie vark dood is; die beheerde sterftelewensiklus bly die enigste huidige opvolg."
    assert welfare.next_action == "Hersien die behoue sterftevoorskou en bevestig slegs wanneer die voorgestelde gevolge korrek is."
    assert welfare.state is WorkState.URGENT and welfare.authority is Authority.ADVISORY
    memory = MemoryDelivery(monkeypatch)
    outcome = memory.run("af", result)
    assert outcome["status"] == "daily_manager_presented" and len(memory.sends) == 1
    text = memory.sends[0][1]
    assert "Vark Prince se sterfterekordopvolging" in text
    assert RAW_EN_QUESTION not in text and RAW_AF_QUESTION not in text
    assert ("EEN VRAAG" not in text) if failed else ("Wat is Mysikind en Mona se huidige status" in text)
    assert "welstandsopvolging" not in text
    assert outcome["writes_farm_data"] is False and outcome["hardware_commands"] == 0


def test_language_rejected_replacement_preserves_old_card_before_lock_store_send_or_delete(monkeypatch):
    memory = MemoryDelivery(monkeypatch)
    original = memory.run("af", project("af"), litters=molly())
    assert original["status"] == "daily_manager_presented"
    old_rows = deepcopy(memory.family_rows)
    old_calls = list(memory.family_calls)
    old_sends = list(memory.sends)
    result = project("af", snapshot(active=active_welfare(RAW_EN_QUESTION)))
    rejected = memory.run("af", result, litters=molly())
    assert rejected["status"] == "daily_manager_recipient_language_rejected"
    assert rejected["delivery_definitely_not_sent"] is True
    assert rejected["delivery_failure_reason"] == "recipient_language_render_unrecognized"
    assert memory.family_rows == old_rows and memory.family_calls == old_calls
    assert memory.sends == old_sends and not memory.deletions and not memory.lock_calls
    replacement, = memory.replacements
    assert replacement["kwargs"]["previous_message_id"] == original["telegram_message_id"]
    assert replacement["outcome"]["status"] == "recipient_language_render_unrecognized"
    assert replacement["outcome"]["telegram_sends"] == replacement["outcome"]["telegram_deletes"] == 0
    assert replacement["outcome"]["delivery_definitely_not_sent"] is True
    retained = list(memory.outcomes().values())[-1]
    assert retained["status"] == "recipient_language_render_unrecognized"
    assert retained["delivery_definitely_not_sent"] is True


@pytest.mark.parametrize("language", ["en", "af"])
def test_recipient_language_replacement_is_confirmed_before_old_card_cleanup_then_replay_is_silent(monkeypatch, language):
    memory = MemoryDelivery(monkeypatch)
    result = project(language)
    first = memory.run(language, result, litters=molly())
    # A changed canonical watcher snapshot removes this completed work from
    # the current plan. The specialist facts remain identical.
    completed_litters = [{**molly()[0], "Litter_Status": "Weaned", "Weaned_Count": 9}]
    refreshed = memory.run(language, result, litters=completed_litters)
    replay = memory.run(language, result, litters=completed_litters)
    assert first["status"] == refreshed["status"] == "daily_manager_presented"
    assert list(memory.outcomes().values())[-1]["previous_telegram_message_id"] == first["telegram_message_id"]
    assert refreshed["telegram_message_id"] != first["telegram_message_id"]
    assert replay["status"] == "daily_manager_unchanged_silent" and replay["telegram_sends"] == 0
    assert memory.sends == [("OFFLINE-" + language, EXPECTED[language]),
                            ("OFFLINE-" + language, EXPECTED_REPLACEMENT[language])]
    assert memory.deletions == [("OFFLINE-" + language, first["telegram_message_id"])]
    replacement, = memory.replacements
    assert replacement["outcome"]["status"] == "brief_replaced"
    assert replacement["outcome"]["telegram_sends"] == replacement["outcome"]["telegram_deletes"] == 1
    card = replacement["kwargs"]["card_mission_id"]
    assert memory.lock_calls == [("enter", card), ("exit", card)]
    assert {row["state"] for row in memory.family_rows.values()} == {
        "delivery_attempted", "delivered", "brief_generation_delivery_attempted",
        "brief_generation_delivered", "brief_generation_superseded", "brief_previous_deleted"}
    assert len(memory.outcomes()) == 2


def test_a_valid_changed_plan_after_rejected_replacement_cannot_claim_the_old_card_as_new_delivery(monkeypatch):
    memory = MemoryDelivery(monkeypatch)
    original = memory.run("af", project("af"), litters=molly())
    rejected_result = project("af", snapshot(active=active_welfare(RAW_EN_QUESTION)))
    rejected = memory.run("af", rejected_result, litters=molly())
    assert rejected["status"] == "daily_manager_recipient_language_rejected"
    completed_litters = [{**molly()[0], "Litter_Status": "Weaned", "Weaned_Count": 9}]
    resumed = memory.run("af", project("af"), litters=completed_litters)
    # A later readable plan must either be held explicitly or be confirmed as
    # a new replacement. Replaying the first card is not delivery of this text.
    if resumed["status"] == "daily_manager_presented":
        assert memory.sends[-1] == ("OFFLINE-af", EXPECTED_REPLACEMENT["af"])
        assert resumed["telegram_message_id"] != original["telegram_message_id"]
    else:
        assert memory.sends == [("OFFLINE-af", EXPECTED["af"])]
        assert not memory.deletions
