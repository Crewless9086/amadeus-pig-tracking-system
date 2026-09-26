"""Production-shaped private Telegram questions through the real semantic/read/delivery path."""
import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from modules.oom_sakkie import semantic_front_door as semantic
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import farm_manager_runtime as manager
from modules.oom_sakkie import service, tools
from modules.oom_sakkie.farm_manager_loop import Authority, Provenance, SpecialistResult, SpecialistWorkItem, WorkState
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

NOW = datetime.now(timezone.utc).replace(microsecond=0)
MODEL_ENV = {"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1", "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-4.1-mini", "OPENAI_API_KEY": "inert"}


def interpretation(kind=None, language="en", **query):
    return {"domain": "herd_management" if kind == "animal_status" else "manager_round",
        "intent": kind or "farm_brief", "message_kind": "question", "confidence": .99,
        "language": language, "needs_clarification": False,
        "read_query": {"kind": kind, **query} if kind else None}


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self, size=-1): return json.dumps({"choices": [{"message": {"content": json.dumps(self.value)}}]}).encode()


class ReadConnection:
    def __init__(self):
        self.calls = []
        self.rows = [{"pig_id": "PIG-SYNTHETIC-702", "tag_number": "702", "pig_name": "Hazel",
            "status": "Active", "on_farm": True, "sex": "Female", "purpose": "Breeding",
            "current_weight_kg": 87, "last_weight_date": NOW.date(), "current_pen_id": "PEN-4"}]
        self.fail = False
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self
    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        if self.fail: raise RuntimeError("canonical_read_down")
        assert sql.strip().lower().startswith(("select", "set transaction"))
        if "lower(state.pig_id)" in sql:
            self.result = [row for row in self.rows if args[0].casefold() in {str(row.get(k) or "").casefold() for k in ("pig_id", "tag_number", "pig_name")}][:3]
        elif "where state.pig_id = %s" in sql:
            self.result = [row for row in self.rows if row["pig_id"] == args[0]]
        elif "from public.mating_events" in sql:
            assert "where sow_pig_id=%s or boar_pig_id=%s" in sql and "limit 65" in sql
            self.result = []
        else:
            self.result = []
        self.names = list(self.result[0]) if self.result else ["pig_id"]
        self.description = [SimpleNamespace(name=k) for k in self.names]
    def fetchall(self): return [tuple(row.get(k) for k in self.names) for row in self.result]


@pytest.fixture
def journey(monkeypatch):
    for key, value in {**MODEL_ENV, "DATABASE_URL": "inert", "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g"*40, "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}.items():
        monkeypatch.setenv(key, value)
    from modules.oom_sakkie import herdmaster_health_loss_runtime
    monkeypatch.setattr(herdmaster_health_loss_runtime, "_load_active_contexts", lambda *_a, **_kw: [])
    from modules.oom_sakkie import owner_task_lifecycle
    monkeypatch.setattr(owner_task_lifecycle, "_load_active_request", lambda *_a: None)
    state = SimpleNamespace(model=None, payloads=[], family={}, rounds={}, sends=[], connection=ReadConnection())
    monkeypatch.setattr(gateway, "recover_contextual_specialist_replay", lambda *_a, **_kw: None)
    pending = {"daily_identity": "DAILY-SYNTHETIC", "question": "What is Hazel's farrowing status?",
        "presented_at": (NOW-timedelta(minutes=4)).isoformat(), "telegram_message_id": "9001",
        "question_binding": {"domain": "herd", "dedupe_key": "herdmaster:PIG-SYNTHETIC-OTHER"}}
    monkeypatch.setattr(gateway, "load_active_manager_question", lambda parsed: pending)
    from modules.oom_sakkie import manager_question_runtime as question_runtime
    monkeypatch.setattr(question_runtime, "_load_manager_provider_reply", lambda *_a: None)
    monkeypatch.setattr(semantic, "load_bounded_owner_context", lambda parsed: {
        "conversation_turns": semantic._eligible_conversation_context(list(reversed(list(state.family.values()))), parsed),
        "recent_turns": semantic._eligible_clarification_context(list(reversed(list(state.family.values()))), parsed)})
    def opener(request, **_kw):
        state.payloads.append(json.loads(request.data))
        return Response(state.model)
    monkeypatch.setattr(semantic.urllib_request, "urlopen", opener)
    from modules.oom_sakkie import bounded_postgres_read
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres", lambda **_kw: state.connection)
    monkeypatch.setattr(service, "write_trace", lambda *_a: {"stored": True, "status": "stored"})
    monkeypatch.setattr(service, "_write_tool_trace", lambda *_a: {"stored": True, "status": "stored"})
    monkeypatch.setattr(tools, "_current_herdmaster_breeding_loop", lambda: pytest.fail("no whole-herd fanout for an explicit animal"))
    def packet(name, **_kw):
        af = _kw.get("language") == "af"
        question = "Wat is Hazel se huidige status: reeds gewerp, weer op hitte, of nog geen duidelike verandering nie?" if af else "What is Hazel's current farrowing status?"
        proof = Provenance(name, name+"-current", (name+":canonical",), NOW, 1)
        items = () if name != "herdmaster" else (SpecialistWorkItem("HERD-I", "herdmaster:farrowing:SYNTHETIC", "herd",
            ("Opvolg van Hazel se werpsaak" if af else "Hazel farrowing follow-up"),
            ("Die verwagte tyd het verstryk; die uitkoms is nog nie aangeteken nie." if af else "The projected window passed; an outcome is not recorded."),
            question, "charl", WorkState.WAITING_EVIDENCE, Authority.READ_ONLY, proof,
            genuine_question=question, question_for="charl"),)
        return SpecialistResult(name, name+"-current", NOW, work_items=items)
    monkeypatch.setattr(manager, "_load_herdmaster", lambda *_a, **_kw: packet("herdmaster", **_kw))
    monkeypatch.setattr(manager, "_load_rootline", lambda *_a, **_kw: packet("rootline"))
    state.cases = [{"case_id": "CASE-SYNTHETIC", "dedupe_key": "herdmaster:weights:SYNTHETIC", "specialist": "HERDMASTER",
        "status": "exception", "summary": "Canonical tag reconciliation", "lease_until": None}]
    monkeypatch.setattr(manager, "_load_enquiry_cases", lambda query=None: state.cases)
    def round_store(action, identity, payload):
        if action == "load": return state.rounds.get(identity)
        created = identity not in state.rounds
        if created: state.rounds[identity] = payload
        return {"success": True, "created": created}
    monkeypatch.setattr(manager, "_event_store", round_store)
    def family_store(action, identity, payload):
        if action == "load": return [row for row in state.family.values() if row["card_mission_id"] == identity]
        created = identity not in state.family
        if created: state.family[identity] = dict(payload)
        return {"success": True, "created": created}
    monkeypatch.setattr(family, "_event_store", family_store)
    def sender(chat, text, *_a, **_kw):
        state.sends.append((chat, text))
        return {"success": True, "telegram_message_id": str(9500+len(state.sends)), "provider_timestamp": NOW.isoformat()}
    monkeypatch.setattr(family, "_send_telegram", sender)
    state.claim = Mock(side_effect=AssertionError("read must not create protected claim"))
    monkeypatch.setattr(gateway, "create_claim", state.claim)
    from modules.oom_sakkie import protected_action_claims
    monkeypatch.setattr(protected_action_claims, "create_claim", state.claim)
    def send(text, model, ident=8001):
        state.model = model
        monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE", model.get("language", "en"))
        return gateway.handle_telegram_gateway_message({"message": {"message_id": ident,
            "date": int(NOW.timestamp())+1, "text": text,
            "from": {"id": "42"}, "chat": {"id": "42", "type": "private"}}},
            headers={"Authorization": "Bearer "+"g"*40})
    state.send = send
    return state


@pytest.mark.parametrize("language", ["en", "af"])
def test_complete_question_family_uses_real_gateway_readers_and_family_delivery(journey, language):
    j = journey
    broad, code = j.send("Farm priorities today", interpretation(language=language))
    assert code == 200 and len(j.sends) == 1, broad
    first = j.sends[-1][1]
    split, code = j.send("What are you handling and what do you need from me?", interpretation("work_split", language, context_message_id="9001"), 8002)
    assert code == 200 and len(j.sends) == 2
    assert j.sends[-1][1] != first and ("Canonical tag reconciliation" if language == "en" else "Gewigsversoening") in split["answer"]
    assert ("technical exception" if language == "en" else "tegnies geblokkeer") in split["answer"]
    assert "Hazel" in split["answer"]
    details, code = j.send("What did HERDMASTER find about those issues?", interpretation("specialist_detail", language, specialist="HERDMASTER"), 8003)
    assert code == 200 and ("projected window passed" if language == "en" else "Die verwagte tyd het verstryk") in details["answer"]
    assert "ROOTLINE" not in details["answer"] and details["answer"] != first
    farewell, code = j.send("Any open farewell case?", interpretation("case_status", language), 8004)
    assert code == 200 and ("farrowing" if language == "en" else "werpsaak") in farewell["answer"]
    assert ("death/farewell" if language == "en" else "sterfte-/afskeidsaak") in farewell["answer"]
    pig, code = j.send("What is the status of Pig702?", interpretation("animal_status", language, subject="702", case_kind="farrowing", context_message_id="9001"), 8005)
    assert code == 200 and "PIG-SYNTHETIC-702" in pig["answer"] and ("Active" if language == "en" else "Aktief") in pig["answer"] and "87 kg" in pig["answer"]
    assert "current farrowing status" not in pig["answer"] and len(j.sends) == 5
    replay, code = j.send("What is the status of Pig702?", interpretation("animal_status", language, subject="702"), 8005)
    assert len(j.sends) == 5 and replay["delivery"]["telegram_sends"] == 0
    assert j.claim.call_count == 0
    delivered = [row for row in j.family.values() if row["state"] == "delivered"]
    assert delivered[0]["clarification_question"] == ("What is Hazel's current farrowing status?" if language == "en" else "Wat is Hazel se huidige status: reeds gewerp, weer op hitte, of nog geen duidelike verandering nie?")
    assert delivered[0]["conversation_answer"] != delivered[0]["clarification_question"]
    context = json.loads(j.payloads[1]["messages"][1]["content"])["context"]
    assert context["conversation_turns"][0]["telegram_message_id"] == "9501"
    assert "TODAY" in context["conversation_turns"][0]["assistant_answer"] or "VANDAG" in context["conversation_turns"][0]["assistant_answer"]
    assert context["recent_turns"][-1]["semantic_intent"] == "pending_manager_question"


@pytest.mark.parametrize("status,on_farm", [("Active", True), ("Sold", False), ("Dead", False)])
def test_explicit_animal_does_not_filter_terminal_identity_or_inherit_question(journey, status, on_farm):
    journey.connection.rows[0].update(status=status, on_farm=on_farm)
    result, code = journey.send("Hoe gaan dit met vark702?", interpretation("animal_status", "af", subject="702"))
    assert code == 200 and {"Active": "Aktief", "Sold": "Verkoop", "Dead": "Dood"}[status] in result["answer"]
    assert ("Ja" if on_farm else "Nee") in result["answer"]
    assert journey.claim.call_count == 0


@pytest.mark.parametrize("failure", ["unknown", "ambiguous", "unavailable"])
def test_animal_negative_is_specific_visible_and_never_proves_absence(journey, failure):
    if failure == "unknown": journey.connection.rows = []
    elif failure == "ambiguous": journey.connection.rows.append({**journey.connection.rows[0], "pig_id": "PIG-OTHER"})
    else: journey.connection.fail = True
    result, code = journey.send("Status of Pig702?", interpretation("animal_status", subject="702"))
    assert code == 200 and len(journey.sends) == 1
    expected = {"unknown": "could not match", "ambiguous": "More than one", "unavailable": "evidence is unavailable"}[failure]
    assert expected in result["answer"]
    assert "Which current farm item" not in result["answer"]
    assert journey.claim.call_count == 0


def test_no_canonical_reader_or_provider_for_unallowed_private_principal(journey):
    journey.model = interpretation("animal_status", subject="702")
    result, code = gateway.handle_telegram_gateway_message({"message": {"message_id": 8001,
        "date": int(NOW.timestamp()), "text": "Pig702 status", "from": {"id": "666"},
        "chat": {"id": "666", "type": "private"}}}, headers={"Authorization": "Bearer "+"g"*40})
    assert code == 403 and journey.connection.calls == [] and journey.sends == []


@pytest.mark.parametrize("override", [{"chat_id": "99"}, {"owner_user_id": "99"}, {"state": "send_claimed"},
    {"state": "superseded"}, {"delivery_provider_timestamp": (NOW-timedelta(hours=8)).isoformat()}, {"telegram_message_id": ""}])
def test_context_requires_exact_private_confirmed_current_card(override):
    row = {"owner_user_id": "42", "chat_id": "42", "state": "delivered", "card_mission_id": "C",
        "telegram_message_id": "9501", "delivery_provider_timestamp": NOW.isoformat(), "conversation_answer": "Hazel follow-up", **override}
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_timestamp": (NOW+timedelta(seconds=1)).isoformat()}
    assert semantic._eligible_conversation_context([row], parsed) == []


def test_legacy_brief_opening_is_not_a_clarification_and_pending_supersedes_context():
    row = {"owner_user_id": "42", "chat_id": "42", "state": "delivered", "task_state": "farm_manager_round_ready",
        "card_mission_id": "C", "telegram_message_id": "9501", "delivery_provider_timestamp": NOW.isoformat(),
        "clarification_question": "<b>OOM SAKKIE — TODAY'S FARM BRIEF</b>", "conversation_answer": "Hazel"}
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_timestamp": (NOW+timedelta(seconds=1)).isoformat()}
    assert semantic._eligible_clarification_context([row], parsed) == []
    assert semantic._eligible_conversation_context([{**row, "state": "superseded"}, row], parsed) == []


def test_unverified_context_subject_clarifies_without_reader(journey):
    result, code = journey.send("How is she doing?", interpretation("animal_status", subject="Hazel", context_message_id="9001"))
    assert code == 200 and "Which animal or case" in result["answer"]
    assert journey.connection.calls == []


@pytest.mark.parametrize("kind", ["observation", "correction", "confirmation", "command"])
def test_read_contract_cannot_reclassify_an_effectful_message(kind):
    value = {**interpretation("animal_status", subject="702"), "message_kind": kind}
    assert semantic.parse_semantic_response(Response(value).read().decode()) is None


def test_real_context_loader_includes_confirmed_dialogue_in_model_payload(monkeypatch):
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie import herdmaster_litter_weaning_runtime as weaning
    from modules.oom_sakkie import herdmaster_litter_first_treatment_runtime as treatment
    from modules.oom_sakkie import herdmaster_farrowing_runtime as farrowing
    import psycopg
    row = {"owner_user_id": "42", "chat_id": "42", "state": "delivered", "task_state": "farm_manager_round_ready",
        "card_mission_id": "C", "telegram_message_id": "9501", "delivery_provider_timestamp": NOW.isoformat(),
        "conversation_question": "Farm priorities", "conversation_answer": "Hazel farrowing follow-up",
        "clarification_question": "What is Hazel's current farrowing status?", "clarification_contract": "explicit_question_v1"}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_a): pass
        def execute(self, sql, args):
            assert "owner_user_id" in sql and "chat_id" in sql
            assert args == ("42", "42", semantic.MAX_CONTEXT_SCAN_ITEMS)
        def fetchall(self): return [(row,)]
    class Connection(Cursor):
        def cursor(self): return Cursor()
    monkeypatch.setenv("DATABASE_URL", "inert")
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_kw: Connection())
    monkeypatch.setattr(health, "_load_active_contexts", lambda *_a, **_kw: [])
    monkeypatch.setattr(weaning, "load_weaning_context", lambda *_a: None)
    monkeypatch.setattr(treatment, "load_first_treatment_context", lambda *_a: None)
    monkeypatch.setattr(farrowing, "load_farrowing_context", lambda *_a: None)
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_timestamp": (NOW+timedelta(seconds=1)).isoformat()}
    context = semantic.load_bounded_owner_context(parsed)
    payload = semantic._payload(parsed, semantic._bounded_context(context), MODEL_ENV)
    actual = json.loads(payload["messages"][1]["content"])["context"]
    assert actual["conversation_turns"][0]["assistant_answer"] == row["conversation_answer"]
    assert actual["conversation_turns"][0]["telegram_message_id"] == "9501"
    assert actual["recent_turns"][0]["clarification_question"] == row["clarification_question"]


def test_targeted_case_question_is_recorded_for_the_next_short_answer(journey):
    result, code = journey.send("An open farewell case?", interpretation("case_status"))
    assert code == 200 and result["message"]["question_count"] == 1
    assert "farrowing" in result["message"]["clarification_question"]
    answered, code = journey.send("Farrowing", interpretation("case_status", case_kind="farrowing"), 8002)
    assert code == 200
    context = json.loads(journey.payloads[-1]["messages"][1]["content"])["context"]
    assert any(turn["clarification_question"] == result["message"]["clarification_question"] for turn in context["recent_turns"])
    assert any(turn["telegram_message_id"] == "9501" for turn in context["recent_turns"])


@pytest.mark.parametrize("kind", ["case_status", "specialist_detail"])
def test_animal_specific_case_request_never_returns_unrelated_cases(journey, monkeypatch, kind):
    reader = Mock(side_effect=AssertionError("unscoped case read forbidden"))
    monkeypatch.setattr(manager, "_load_enquiry_cases", reader)
    result, code = journey.send("Mortality case for Pig702?", interpretation(kind, subject="702", case_kind="mortality", specialist="HERDMASTER"))
    assert code == 200 and "cannot yet bind an individual case" in result["answer"] and "Which view" in result["answer"]
    assert "Canonical tag reconciliation" not in result["answer"] and reader.call_count == 0
    assert result["message"]["question_count"] == 1 and journey.claim.call_count == 0
    followup, code = journey.send("Its current status please", interpretation("animal_status", subject="702", context_message_id="9501"), 8002)
    assert code == 200 and "PIG-SYNTHETIC-702" in journey.sends[-1][1]
    assert reader.call_count == 0 and journey.claim.call_count == 0


def test_valid_semantic_animal_read_overrides_farm_status_phrase(journey):
    result, code = journey.send("Farm status: specifically Pig702", interpretation("animal_status", subject="702"))
    assert code == 200 and "PIG-SYNTHETIC-702" in result["answer"]
    assert not journey.rounds and len(journey.sends) == 1


def test_work_split_does_not_promote_recommendation_or_expired_lease_to_execution(journey):
    journey.cases = {"cases": [{"specialist": "HERDMASTER", "summary": "Canonical tag reconciliation", "dedupe_key": "herdmaster:weights:X",
        "status": "delegated", "lease_until": (NOW-timedelta(minutes=1)).isoformat()}], "truncated": True}
    result, code = journey.send("Which jobs are yours and mine?", interpretation("work_split"))
    assert code == 200 and "worker lease expired; execution unconfirmed" in result["answer"]
    assert "bounded partial case snapshot" in result["answer"]
    owner_part = result["answer"].split("What I need from you", 1)[1]
    assert "tag reconciliation" not in owner_part


def test_afrikaans_recipient_never_receives_unlocalized_specialist_prose(journey, monkeypatch):
    proof = Provenance("herdmaster", "current", ("canonical",), NOW, 1)
    item = SpecialistWorkItem("I", "K", "herd", "Review unlocalized work", "Unexpected English farm instruction",
        "Move the unrelated animal", "charl", WorkState.WAITING_EVIDENCE, Authority.READ_ONLY, proof)
    monkeypatch.setattr(manager, "_load_herdmaster", lambda *_a, **_kw: SpecialistResult("herdmaster", "current", NOW, work_items=(item,)))
    result, code = journey.send("Wat het HERDMASTER gevind?", interpretation("specialist_detail", "af", specialist="HERDMASTER"))
    assert code == 200 and "Unexpected English" not in journey.sends[0][1]
    assert "nog nie in jou taal beskikbaar" in result["answer"]
    assert "Move the unrelated animal" not in result["answer"]


@pytest.mark.parametrize("field,value", [("welfare_observation", {"eating": "no"}), ("protected_preview_required", True), ("confirmation_facts", {"interlock_off": True})])
def test_read_contract_rejects_simultaneous_protected_payload(field, value):
    raw = {**interpretation("animal_status", subject="702"), field: value}
    assert semantic.parse_semantic_response(Response(raw).read().decode()) is None


@pytest.mark.parametrize("language", ["en", "af"])
def test_real_bilingual_herd_producer_keeps_identity_dates_and_next_step(journey, monkeypatch, language):
    pig, mating = "PIG-SYNTHETIC-702", "MATING-SYNTHETIC-702"
    canonical = {"generated_at": NOW.isoformat(), "worklist_id": "SYNTHETIC-READ",
        "tasks": [{"pig_id": pig, "tag_number": "Hazel", "known_evidence": {
            "current_mating_id": mating, "current_mating_date": "2026-01-02"}}]}
    observations = [{"pig_id": pig, "mating_id": mating, "mating_date": "2026-01-02",
        "operational_result": "Assumed Pregnant", "observed_signs": "synthetic retained observation",
        "observed_at": "2026-04-10T04:45:00+00:00", "source_identity": "SYNTHETIC-OBSERVATION"}]
    actual = manager._whole_herd_specialist_result(canonical, observations, [], NOW, language)
    assert actual.work_items and "Hazel" in actual.work_items[0].title
    monkeypatch.setattr(manager, "_load_herdmaster", lambda *_a, **_kw: actual)
    result, code = journey.send("HERDMASTER findings?", interpretation("specialist_detail", language, specialist="HERDMASTER"))
    assert code == 200 and len(journey.sends) == 1
    visible = journey.sends[0][1]
    assert "Hazel" in visible and "2026-04-24" in visible and "2026-04-28" in visible
    assert ("projected window" if language == "en" else "Die verwagte tydperk") in visible
    assert ("birth counts" if language == "en" else "geboortetellings") in visible
    assert "nog nie in jou taal beskikbaar" not in visible
    assert journey.claim.call_count == 0


@pytest.mark.parametrize("language", ["en", "af"])
def test_delivered_animal_context_resolves_followup_and_explicit_subject_overrides_it(journey, language):
    first, code = journey.send("Status Pig702", interpretation("animal_status", language, subject="702"))
    assert code == 200
    followup, code = journey.send("When was it weighed?", interpretation("animal_status", language, subject="702", context_message_id="9501"), 8002)
    assert code == 200 and "87 kg" in journey.sends[-1][1] and NOW.date().isoformat() in journey.sends[-1][1]
    journey.connection.rows.append({**journey.connection.rows[0], "pig_id": "PIG-SYNTHETIC-703", "tag_number": "703"})
    new, code = journey.send("Now show Pig703", interpretation("animal_status", language, subject="703", context_message_id="9501"), 8003)
    assert code == 200 and "PIG-SYNTHETIC-703" in journey.sends[-1][1]
    assert "PIG-SYNTHETIC-702" not in journey.sends[-1][1]
    assert journey.claim.call_count == 0


def test_qualified_model_full_shape_stays_read_only_through_gateway(journey):
    # Shape captured from the configured model qualification; all identities
    # and provider values here are synthetic, with no private evidence fixture.
    raw = {"domain": "herd_management", "intent": "animal_status", "message_kind": "question",
        "entity_refs": ["Pig702"], "continuation": True, "observation": None,
        "welfare_observation": None, "clinical_observation": None, "observation_facts": [],
        "water_observation_context": None, "irrigation_observation": None, "breeding_actions": [],
        "farrowing_litter": None, "litter_first_treatment": None, "litter_weaning": None,
        "confirmation_facts": None, "commissioning_facts": None,
        "protected_preview_required": False, "recording_prohibited": False,
        "read_query": {"kind": "animal_status", "subject": "702"}, "requested_action": "",
        "language": "en", "confidence": .99, "needs_clarification": False, "clarification_question": ""}
    result, code = journey.send("What is the status of Pig702?", raw)
    assert code == 200 and "PIG-SYNTHETIC-702" in journey.sends[-1][1]
    assert journey.claim.call_count == 0


@pytest.mark.parametrize("language", ["en", "af"])
def test_model_case_ambiguity_uses_typed_recipient_question_and_delivered_context(journey, language):
    raw = {**interpretation("case_status", language), "needs_clarification": True,
        "clarification_question": ("Bedoel jy werping of afskeid?" if language == "af" else "Do you mean farrowing or farewell?")}
    result, code = journey.send("Open farewell case?", raw)
    assert code == 200 and len(journey.sends) == 1
    assert ("sterfte-/afskeidsaak" if language == "af" else "death/farewell") in journey.sends[0][1]
    delivered = [row for row in journey.family.values() if row["state"] == "delivered"]
    assert len(delivered) == 1 and delivered[0]["clarification_contract"] == "explicit_question_v1"
    assert delivered[0]["clarification_question"] in journey.sends[0][1]
    assert journey.claim.call_count == 0


def setUpModule():
    from tests.farm_model_test_support import isolated_model_budget
    global _model_budget_test_scope
    _model_budget_test_scope = isolated_model_budget()


def tearDownModule():
    _model_budget_test_scope.close()
