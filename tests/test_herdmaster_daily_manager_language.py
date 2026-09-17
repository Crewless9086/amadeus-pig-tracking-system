"""Recipient presentation must preserve the actual canonical adapter semantics."""
from copy import deepcopy
from dataclasses import fields
import re

import pytest

from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence
from tests.test_herdmaster_daily_manager_evidence import NOW, build, mortality, pig, weight


def branch_packet(branch):
    if branch == "invalid":
        return None
    if branch == "missing":
        return build(pigs=[pig("P1", "11"), pig("P2", "22")], weights=[weight()])
    if branch == "unknown":
        return build(pigs=[pig("X1", "33", animal_type=None)])
    if branch == "conflict":
        return build(weights=[weight(kg=10, event="A"), weight(kg=12, event="B")])
    if branch == "complete":
        return build(weights=[weight()])
    if branch == "findings":
        return build(weights=[weight(kg=12)], prior=[weight(kg=10, day="2026-08-03")])
    if branch == "individual":
        return build(pigs=[pig("S1", "Maya", animal_type="Sow", purpose="Breeding")],
                     lifecycle=[{"pig_id": "S1", "event_type": "individual_weighing_due",
                                 "effective_at": "2026-08-11T06:00:00+02:00"}])
    packet = build(weights=[weight()], mortality=mortality())
    if branch == "mortality_unavailable":
        packet["mortality"]["materiality_state"] = "database_window_exhausted"
    return packet


@pytest.mark.parametrize("branch,title,meaning,action", [
    ("invalid", "Weeklikse weegbewyse is nie beskikbaar nie", "begrensde bewysvenster", "moenie elke aktiewe vark weeg nie"),
    ("missing", "Weging: 1 van 2 aangeteken; 1 oormerk(e) se status moet nagegaan word", "1/2", "oormerke 22"),
    ("unknown", "Weeklikse weegbewyse is nie beskikbaar nie", "kan nie", "moenie elke aktiewe vark weeg nie"),
    ("conflict", "Weeklikse weegbewyse bots", "1 toepaslike gemerkte vark(e)", "moenie 'n biologiese verklaring kies nie"),
    ("complete", "Weeklikse weging gedek: 1/1 toepaslike gemerkte varke", "2026-08-11 tot 2026-08-12 bly Onbekend", "Geen verdere opdrag"),
    ("findings", "Weeklikse weging gedek: 1/1 toepaslike gemerkte varke", "+2 kg (+20%)", "slegs die beskrywende veranderinge"),
    ("individual", "Vark Maya se individuele weging is nou nodig", "uitdruklik", "Weeg Vark Maya nou"),
    ("mortality_new", "Sterfteopvolging — P1", "2026-08-14 aangeteken", "nie 'n diagnose raai nie"),
    ("mortality_open", "Sterfteopvolging — P1", "steeds oop", "slegs een duidelike vraag"),
    ("mortality_unavailable", "Bewyse vir sterfteopvolging is nie beskikbaar nie", "duursaam verwerk", "dieselfde duursame identiteit"),
])
def test_actual_adapter_localizes_every_generated_branch_without_changing_evidence(branch, title, meaning, action):
    packet = branch_packet(branch)
    before = deepcopy(packet)
    active = [{"pig_id": "P1", "state": "working"}] if branch == "mortality_open" else []
    results = {language: consume_daily_manager_evidence(packet, observed_at=NOW,
               language=language, active_lifecycles=active) for language in ("en", "af-ZA")}
    assert packet == before
    assert results["en"].result_id == results["af-ZA"].result_id
    assert len(results["en"].work_items) == len(results["af-ZA"].work_items)
    for english, afrikaans in zip(results["en"].work_items, results["af-ZA"].work_items):
        en = {field.name: getattr(english, field.name) for field in fields(english)}
        af = {field.name: getattr(afrikaans, field.name) for field in fields(afrikaans)}
        for field in ("title", "why", "next_action"):
            assert en.pop(field) != af.pop(field), (branch, field)
        en["metadata"] = {key: value for key, value in en["metadata"].items() if key != "owner_followup"}
        af["metadata"] = {key: value for key, value in af["metadata"].items() if key != "owner_followup"}
        assert en == af  # IDs, all provenance, state, authority and mortality fingerprints.
        generated = " ".join((afrikaans.title, afrikaans.why, afrikaans.next_action))
        assert not re.search(r"\b(the|and|recorded|weekly|weighing|unknown|follow-up|diagnosis)\b", generated, re.I)
    selected = next(item for item in results["af-ZA"].work_items if item.title == title)
    assert meaning in selected.why and action in selected.next_action
    if branch == "findings":
        assert "Geen oorsaak of diagnose word afgelei nie" in selected.why
    if branch == "missing":
        assert "2026-08-11 tot 2026-08-12" in selected.why
        assert "voordat daardie bewyse bestaan nie" in selected.next_action


def test_localized_closed_mortality_stays_closed_and_does_not_create_owner_work():
    packet = branch_packet("mortality_new")
    active = [{"pig_id": "P1", "state": "completed", "mortality_closed": True}]
    for language in ("en", "af"):
        result = consume_daily_manager_evidence(packet, observed_at=NOW, language=language,
                                               active_lifecycles=active)
        assert not any("mortality" in item.dedupe_key for item in result.work_items)
        assert all(not item.genuine_question for item in result.work_items)
        assert result.work_items[0].metadata["mortality_fingerprints"]
