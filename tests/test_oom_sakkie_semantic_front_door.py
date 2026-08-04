import json
from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import _resolve_active_context
from modules.oom_sakkie.semantic_front_door import (
    SemanticInterpretation, interpret_owner_message, parse_semantic_response,
    semantic_front_door_policy,
)
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.service import handle_message


def _response(value):
    return json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]})


class _HttpResponse:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return self.body.encode()


def _semantic(domain, intent, **extra):
    return {"domain": domain, "intent": intent, "message_kind": extra.get("message_kind", "general"),
        "entity_refs": extra.get("entity_refs", []),
        "continuation": extra.get("continuation", False), "observation": extra.get("observation", ""),
        "requested_action": extra.get("requested_action", ""), "language": extra.get("language", "en"),
        "confidence": extra.get("confidence", .98), "needs_clarification": False,
        "clarification_question": ""}


def test_semantic_front_door_is_llm_first_but_has_zero_authority():
    policy = semantic_front_door_policy({"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"})
    assert policy["enabled"] and policy["configured"]
    assert not policy["can_execute"] and not policy["can_write"]
    assert not policy["can_send"] and not policy["can_control_hardware"]


def test_english_death_update_is_typed_as_herd_evidence():
    result = parse_semantic_response(_response(_semantic("herd_health", "death_report",
        entity_refs=["Pig 127"], continuation=True,
        observation="Pig 127 is reported dead and buried.")))
    assert result.domain == "herd_health" and result.continuation
    assert result.entity_refs == ("Pig 127",)
    assert "dead" in result.observation


def test_afrikaans_death_update_preserves_entity_and_meaning():
    result = parse_semantic_response(_response(_semantic("herd_health", "death_report",
        entity_refs=["Vark 127"], continuation=True, language="af",
        observation="Pig 127 is reported dead and buried.")))
    assert result.language == "af" and result.domain == "herd_health"
    assert result.entity_refs == ("Vark 127",)


def test_irrigation_shutdown_is_evidence_not_legacy_status_lookup():
    result = parse_semantic_response(_response(_semantic("rootline", "irrigation_shutdown_observed",
        entity_refs=["C Camp"], continuation=True,
        observation="C Camp irrigation physically stopped.")))
    assert result.domain == "rootline" and result.continuation
    assert result.intent == "irrigation_shutdown_observed"


def test_afrikaans_irrigation_followup_is_understood():
    result = parse_semantic_response(_response(_semantic("rootline", "irrigation_shutdown_observed",
        entity_refs=["C-kamp"], continuation=True, language="af",
        observation="C Camp irrigation physically stopped.")))
    assert result.language == "af" and result.domain == "rootline"


def test_active_health_context_can_resolve_afrikaans_semantic_entity():
    context = {"status": "waiting_for_input", "mission_id": "OOM-PIG127",
        "provider_message_id": "3202", "provider_timestamp": "2026-08-03T03:51:20+00:00",
        "preview": {"evaluator": {"identity": {"tag_number": "127"}}}}
    active, ambiguous, _ = _resolve_active_context(
        "Hy het dit nie gemaak nie", [context], "3210",
        provider_timestamp="2026-08-03T18:00:00+00:00", entity_refs=["Vark 127"])
    assert not ambiguous and active["mission_id"] == "OOM-PIG127"


def test_interpreter_receives_bounded_active_context():
    captured = {}
    def opener(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("herd_health", "welfare_update",
            entity_refs=["Pig 127"], continuation=True, observation="Pig 127 is weak.")))
    parsed = {"text": "Hy is baie swak", "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9", "reply_to_message_id": "8"}
    result = interpret_owner_message(parsed, environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"},
        context_loader=lambda _parsed: {"active_cases": [{"tag": str(i)} for i in range(20)],
                                        "recent_turns": [{"text": str(i)} for i in range(20)]},
        http_open=opener)
    assert result.domain == "herd_health"
    sent = json.loads(captured["messages"][1]["content"])["context"]
    assert len(sent["active_cases"]) == 8 and len(sent["recent_turns"]) == 8


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result",
       return_value={"success": True, "telegram_sends": 0, "telegram_edits": 1})
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message")
def test_gateway_attaches_semantic_hint_before_specialist_routing(interpret, operational, _deliver):
    interpret.return_value = SemanticInterpretation(domain="rootline",
        intent="irrigation_shutdown_observed", message_kind="observation",
        entity_refs=("C Camp",), continuation=True,
        observation="C Camp irrigation physically stopped.", confidence=.99)
    operational.return_value = ({"handled": True, "success": True, "status": "working",
        "answer": "ROOTLINE received shutdown evidence", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-1", "writes_farm_data": False}, 200)
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"}
    payload = {"message": {"message_id": 3219, "date": 1785790000, "text": "C Camp has stopped",
        "from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
    with patch.dict("os.environ", env, clear=True):
        result, status = handle_telegram_gateway_message(payload,
            headers={"Authorization": "Bearer " + "g" * 40})
    assert status == 200 and result["message"]["specialist_identity"] == "ROOTLINE"
    routed = operational.call_args.args[0]
    assert routed["semantic"]["intent"] == "irrigation_shutdown_observed"


@patch("modules.oom_sakkie.service.classify_intent",
       side_effect=AssertionError("legacy classifier must not run"))
@patch("modules.oom_sakkie.service.route_with_llm",
       side_effect=AssertionError("second router must not reinterpret owner meaning"))
@patch("modules.oom_sakkie.service.get_tool")
@patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
@patch("modules.oom_sakkie.service._write_tool_trace",
       return_value={"stored": False, "status": "test"})
def test_authenticated_owner_semantics_bypass_legacy_irrigation_classifier(
        _trace, _compose, get_tool, _second_router, _legacy):
    tool = get_tool.return_value
    tool.name = "rootline_water_energy_plan"
    tool.risk_level = 0
    tool.handler.return_value = {"success": True, "summary": "Adaptive B/C plan"}
    result, status = handle_message({
        "text": "What is today's irrigation plan for B and C Camps?",
        "channel": "telegram_read_only",
        "semantic_authoritative": True,
        "semantic": _semantic("rootline", "daily_irrigation_plan"),
    })
    assert status == 200
    assert result["tool_used"] == "rootline_water_energy_plan"
    assert result["intent"]["reason"] == "semantic:rootline_read_plan"


@patch("modules.oom_sakkie.service.classify_intent",
       side_effect=AssertionError("legacy classifier must not run"))
@patch("modules.oom_sakkie.service.route_with_llm",
       side_effect=AssertionError("second router must not reinterpret owner meaning"))
def test_authenticated_owner_clarification_never_falls_back_to_keyword_code(
        _second_router, _legacy):
    semantic = _semantic("general", "unclear_followup")
    semantic["needs_clarification"] = True
    semantic["clarification_question"] = "Which animals do you mean?"
    result, status = handle_message({
        "text": "Animals",
        "channel": "telegram_read_only",
        "semantic_authoritative": True,
        "semantic": semantic,
    })
    assert status == 200
    assert result["needs_clarification"] is True
    assert result["tool_used"] == ""
