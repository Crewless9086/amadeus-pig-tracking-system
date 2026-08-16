import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from modules.oom_sakkie.family_access import resolve_family_principal
from modules.oom_sakkie.family_runtime import handle_family_runtime_message


OWNER = "5721652188"


def binding(user, role, family, permissions):
    return {"telegram_user_id": user, "role": role, "family_key": family,
        "permissions": permissions, "summary_domains": ["herd", "welfare", "breeding",
            "farrowing", "irrigation", "water", "weather", "power"], "language": "af",
        "authorization_id": "AUTH-" + family, "authorized_by_user_id": OWNER,
        "authorized_at": "2026-08-15T08:00:00+02:00"}


ANTON = binding("1002", "farm_manager", "dad", ["farm_observation", "active_follow_up",
    "explicit_summary", "welfare_hold", "welfare_escalation", "found_dead_observation",
    "herdmaster_management_input", "herdmaster_reassessment", "irrigation_start",
    "irrigation_reschedule", "irrigation_pause", "irrigation_stop"])
ANTOINETTE = binding("1003", "read_only_family_member", "mum", ["explicit_summary"])
ENV = {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
       "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([ANTON, ANTOINETTE])}


def parsed(user, text, **extra):
    return {"telegram_user_id": user, "telegram_chat_id": user,
        "telegram_chat_type": "private", "provider_message_id": "501",
        "provider_timestamp": "2026-08-15T10:00:00+00:00", "text": text, **extra}


def principal(user, text="varke"):
    item = parsed(user, text)
    return item, resolve_family_principal(item, ENV)


def claims():
    seen = set()
    def store(_action, identity, _payload):
        created = identity not in seen; seen.add(identity)
        return {"success": True, "created": created}
    return store


def test_authorizes_before_any_private_context_load_and_prevents_cross_family_context():
    item, anton = principal("1002", "Pig 11 is sick")
    calls = []
    denied, status = handle_family_runtime_message(item, anton,
        contextual_loader=lambda **_: calls.append("loaded"), contextual_adapter=lambda **_: {},
        replay_store=claims())
    assert status == 503 and denied["capability"] == "farm_observation" and calls == []
    reply = parsed("1002", "Dit is nou vol", reply_to_message_id="99")
    result, status = handle_family_runtime_message(reply, anton,
        contextual_loader=lambda **_: {"owner_user_id": "1003", "family_key": "mum",
                                        "binding_digest": anton.binding_digest},
        contextual_adapter=lambda **_: (_ for _ in ()).throw(AssertionError("cross-family dispatch")),
        replay_store=claims())
    assert status == 403 and result["status"] == "family_context_not_owned"


def test_antoinette_gets_filtered_read_only_summary_and_cannot_report_or_act():
    item, member = principal("1003", "Hoe lyk die water?")
    result, status = handle_family_runtime_message(item, member,
        summary_loader=lambda **_: {"available": True, "summary_lines": ["Reservoir is vol"]})
    assert status == 200 and "Familie-opdatering" in result["answer"]
    assert result["audit_trace_recorded"] is False
    for text in ("Pig 11 is sick", "Stop irrigation", "Confirm mortality"):
        request = parsed("1003", text)
        denied, status = handle_family_runtime_message(request, member,
            observation_adapter=lambda **_: (_ for _ in ()).throw(AssertionError("must not dispatch")),
            rootline_adapter=lambda **_: (_ for _ in ()).throw(AssertionError("must not dispatch")))
        assert status == 403 and denied["status"] == "family_capability_denied"


def test_anton_rootline_handoff_is_typed_and_requires_reviewed_action():
    item, anton = principal("1002", "Begin besproeiing")
    item["family_action"] = {"capability": "irrigation_start", "decision_id": "D1",
        "commissioned_path_id": "B-COMMISSIONED", "evidence_generation": "E1"}
    calls = []
    result, status = handle_family_runtime_message(item, anton,
        rootline_adapter=lambda **kwargs: calls.append(kwargs) or {
            "success": True, "status": "rootline_governed_handoff", "answer": "Besluit ontvang.",
            "writes_farm_data": False, "hardware_commands": 0}, replay_store=claims())
    assert status == 200 and result["capability"] == "irrigation_start"
    assert len(calls) == 1 and calls[0]["principal"].role.value == "farm_manager"
    assert result["hardware_commands"] == 0 and result["writes_farm_data"] is False


def test_typed_herdmaster_management_and_natural_welfare_escalation_are_reachable():
    _, anton=principal("1002","Pig 11 is sick")
    calls=[]
    adapter=lambda **kwargs:calls.append(kwargs["capability"]) or {
        "success":True,"status":"retained","answer":"Inset behou."}
    management=parsed("1002","Hersien die bestuursplan")
    management["family_action"]={"capability":"herdmaster_management_input",
        "decision_id":"H1","evidence_generation":"E1"}
    result,status=handle_family_runtime_message(management,anton,
        observation_adapter=adapter,replay_store=claims())
    assert status==200 and result["capability"]=="herdmaster_management_input"
    escalation=parsed("1002","Eskaleer die welstand")
    result,status=handle_family_runtime_message(escalation,anton,
        observation_adapter=adapter,replay_store=claims())
    assert status==200 and result["capability"]=="welfare_escalation"
    assert calls==["herdmaster_management_input","welfare_escalation"]


def test_exact_binding_and_replay_identity_are_stable_and_change_with_provider_identity():
    item, anton = principal("1002", "Pig 11 is sick")
    adapter = lambda **_: {"success": True, "status": "observation_handoff",
                           "answer": "Waarneming ontvang."}
    store = claims()
    first, _ = handle_family_runtime_message(item, anton, observation_adapter=adapter, replay_store=store)
    replay, _ = handle_family_runtime_message(item, anton, observation_adapter=adapter, replay_store=store)
    changed, _ = handle_family_runtime_message({**item, "provider_message_id": "502"}, anton,
                                                observation_adapter=adapter, replay_store=store)
    assert first["replay_identity"] == replay["replay_identity"]
    assert changed["replay_identity"] != first["replay_identity"]
    assert first["binding_digest"] == anton.binding_digest
    assert first["audit_trace_recorded"] is True
    assert replay["audit_trace_recorded"] is True


def test_afrikaans_protected_intents_and_ambiguous_text_never_reach_observation_adapter():
    _, anton = principal("1002", "Pig 11 is sick")
    for text in ("Bevestig die dood", "Behandel haar met medikasie", "Dek die sog",
                 "Verander die lewensiklus"):
        item = parsed("1002", text); calls = []
        result, status = handle_family_runtime_message(item, anton,
            observation_adapter=lambda **_: calls.append(1) or {}, replay_store=claims())
        assert status == 403 and calls == [] and result["status"] == "family_capability_denied"


def test_unclassified_manager_request_asks_one_precise_afrikaans_question_without_loading_context():
    item, anton = principal("1002", "Wat kort my aandag?")
    calls = []
    result, status = handle_family_runtime_message(item, anton,
        summary_loader=lambda **_: calls.append("summary"),
        observation_adapter=lambda **_: calls.append("observation"),
        contextual_loader=lambda **_: calls.append("context"),
        replay_store=lambda *_: calls.append("claim"))
    assert status == 200 and result["status"] == "family_clarification_required"
    assert result["language"] == "af" and result["audit_trace_recorded"] is False
    assert result["writes_farm_data"] is False and result["hardware_commands"] == 0
    assert result["answer"].count("?") == 1 and "plaaswaarneming" in result["answer"]
    assert calls == []


def test_faulty_adapter_cannot_cross_mutation_or_hardware_boundary():
    item, anton = principal("1002", "Pig 11 is sick")
    for bad in ({"writes_farm_data": True}, {"hardware_commands": 1},
                {"protected_actions_performed": True}, {"animal_mutations": 1}):
        result, status = handle_family_runtime_message(item, anton,
            observation_adapter=lambda **_: {"success": True, "answer": "unsafe", **bad},
            replay_store=claims())
        assert status == 503 and result["status"] == "family_adapter_authority_violation"
        assert result["writes_farm_data"] is False and result["hardware_commands"] == 0
    for bad in ({"writes_customer_data": True}, {"writes_payment_data": True},
                {"marketing_effects": 1}, {"configuration_changed": True},
                {"authority_changed": True}):
        result, status = handle_family_runtime_message(item, anton,
            observation_adapter=lambda **_: {"success": True, "answer": "unsafe", **bad},
            replay_store=claims())
        assert status == 503 and result["status"] == "family_adapter_authority_violation"


def test_only_a_valid_sealed_rootline_outcome_can_report_a_hardware_command():
    item, anton = principal("1002", "Begin besproeiing")
    item["family_action"] = {"capability": "irrigation_start", "decision_id": "D1",
        "commissioned_path_id": "B-COMMISSIONED", "evidence_generation": "E1"}
    material = {"contract_version": "rootline_delegated_outcome.v1",
        "status": "segment_started", "hardware_commands": 1, "provider_control_calls": 1,
        "owner_authority": False, "n8n_authority": False,
        "google_sheets_authority": False}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()
    sealed = {**material, "success": True, "outcome_sha256": digest}
    adapter = lambda **_: {"success": True, "status": "segment_started",
        "answer": "Veilig uitgevoer.", "hardware_commands": 1,
        "rootline_outcome": sealed}
    result, status = handle_family_runtime_message(item, anton,
        rootline_adapter=adapter, replay_store=claims())
    assert status == 200 and result["hardware_commands"] == 1
    assert result["rootline_outcome_sha256"] == digest
    forged = {**sealed, "outcome_sha256": "0" * 64}
    result, status = handle_family_runtime_message({**item, "provider_message_id": "502"}, anton,
        rootline_adapter=lambda **_: {"success": True, "hardware_commands": 1,
            "rootline_outcome": forged}, replay_store=claims())
    assert status == 503 and result["hardware_commands"] == 0


def test_concurrent_replay_invokes_typed_adapter_once():
    item, anton = principal("1002", "Pig 11 is sick")
    lock=Lock(); claimed=set(); calls=[]
    def store(_action, identity, _payload):
        with lock:
            created=identity not in claimed; claimed.add(identity)
            return {"success":True,"created":created}
    def adapter(**_):
        with lock: calls.append(1)
        return {"success":True,"status":"retained","answer":"Waarneming behou."}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:handle_family_runtime_message(item,anton,
            observation_adapter=adapter,replay_store=store),range(8)))
    assert len(calls)==1
    assert sum(result[0]["status"]=="family_replay_suppressed" for result in results)==7
