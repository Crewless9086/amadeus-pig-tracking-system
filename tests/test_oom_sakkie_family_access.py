import json
from unittest.mock import patch

from modules.oom_sakkie.family_access import (
    FamilyRole, authorize_family_message, bound_family_manager_result, family_access_policy,
    resolve_family_principal,
)
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message


OWNER = "5721652188"


def _env(bindings=()):
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
            "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": OWNER,
            "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps(list(bindings))}


def _parsed(user, text="Hy eet nog nie", message="4001"):
    return {"telegram_user_id": user, "telegram_chat_id": user,
            "telegram_chat_type": "private", "text": text,
            "provider_message_id": message,
            "provider_timestamp": "2026-08-08T06:15:00+00:00"}


def _binding(user="1002", role="trusted_family_reporter", family="dad", permissions=None):
    return {"telegram_user_id": user, "role": role, "family_key": family,
            "permissions": permissions or ["farm_observation", "active_follow_up"],
            "summary_domains": ["herd", "rootline"],
            "authorization_id": "CHARL-FAMILY-AUTH-001",
            "authorized_by_user_id": OWNER, "authorized_at": "2026-08-08T08:00:00+02:00"}


def test_current_configuration_is_charl_only_when_no_family_bindings_exist():
    policy = family_access_policy(_env())
    assert policy["authorized_identity_count"] == 1
    assert policy["family_bindings_count"] == 0
    assert resolve_family_principal(_parsed(OWNER), _env()).role is FamilyRole.OWNER


def test_afrikaans_and_mixed_observations_preserve_exact_reporter_provenance():
    env = _env([_binding()])
    for text in ("Hy eet nog nie", "Die reservoir is vol", "Pig 11 eet nog nie today"):
        parsed = _parsed("1002", text=text)
        decision = authorize_family_message(resolve_family_principal(parsed, env), parsed,
                                             capability="farm_observation")
        assert decision.allowed is True
        assert decision.reporter_attribution["reporter_user_id"] == "1002"
        assert decision.reporter_attribution["provider_message_id"] == "4001"
        assert decision.reporter_attribution["provider_timestamp"] == "2026-08-08T06:15:00+00:00"


def test_contextual_reply_is_identity_bound_not_cross_family():
    env = _env([_binding(), _binding("1003", family="mum")])
    dad = resolve_family_principal(_parsed("1002", "Animals"), env)
    mum = resolve_family_principal(_parsed("1003", "Diere"), env)
    assert authorize_family_message(dad, _parsed("1002"), capability="active_follow_up",
                                    context_owner_user_id="1002").allowed
    denied = authorize_family_message(mum, _parsed("1003"), capability="active_follow_up",
                                      context_owner_user_id="1002")
    assert denied.allowed is False


def test_principal_cannot_be_reused_for_another_family_message():
    env = _env([_binding(), _binding("1003", family="mum")])
    dad = resolve_family_principal(_parsed("1002"), env)
    result = authorize_family_message(dad, _parsed("1003"), capability="farm_observation")
    assert result.allowed is False
    assert result.status == "family_principal_message_binding_mismatch"
    assert result.reporter_attribution["reporter_user_id"] == "1003"
    assert result.reporter_attribution["family_key"] == ""


def test_unknown_sender_and_display_name_impersonation_disclose_nothing():
    parsed = {**_parsed("9999"), "display_name": "Charl", "language": "af"}
    principal = resolve_family_principal(parsed, _env())
    decision = authorize_family_message(principal, parsed, capability="explicit_summary",
                                        summary_domain="herd")
    assert principal.role is FamilyRole.UNKNOWN_SENDER
    assert decision.allowed is False and decision.may_read_private_context is False


def test_family_cannot_confirm_or_escalate_protected_authority():
    env = _env([_binding(permissions=["farm_observation", "active_follow_up", "explicit_summary"])])
    principal = resolve_family_principal(_parsed("1002"), env)
    for capability in ("mortality_confirmation", "sales_decision", "reservation", "payment",
                       "mating_execution", "treatment", "hardware_exception", "permission_change"):
        decision = authorize_family_message(principal, _parsed("1002"), capability=capability)
        assert decision.allowed is False
        assert decision.may_confirm_protected_action is False


def test_read_only_member_gets_only_explicitly_scoped_summary():
    binding = _binding(role="read_only_family_member", family="mum",
                       permissions=["explicit_summary"])
    principal = resolve_family_principal(_parsed("1002"), _env([binding]))
    assert authorize_family_message(principal, _parsed("1002"), capability="explicit_summary",
                                    summary_domain="herd").allowed
    assert not authorize_family_message(principal, _parsed("1002"), capability="explicit_summary",
                                        summary_domain="sales").allowed
    assert not authorize_family_message(principal, _parsed("1002"), capability="farm_observation").allowed


def test_invalid_or_non_owner_authorization_fails_closed():
    binding = _binding()
    binding["authorized_by_user_id"] = "1003"
    assert resolve_family_principal(_parsed("1002"), _env([binding])).role is FamilyRole.UNKNOWN_SENDER


def test_replay_binding_is_deterministic_and_grants_zero_write_authority():
    env = _env([_binding()]); parsed = _parsed("1002")
    first = authorize_family_message(resolve_family_principal(parsed, env), parsed,
                                     capability="farm_observation")
    second = authorize_family_message(resolve_family_principal(parsed, env), parsed,
                                      capability="farm_observation")
    assert first.reporter_attribution == second.reporter_attribution
    assert first.replay_identity == second.replay_identity
    assert first.may_write_farm_data is second.may_write_farm_data is False

    changed = authorize_family_message(resolve_family_principal(parsed, env),
        {**parsed, "text": "Die reservoir is halfvol"}, capability="farm_observation")
    assert changed.replay_identity != first.replay_identity
    prefix = "x" * 200
    long_a = {**parsed, "text": prefix + " reservoir full"}
    long_b = {**parsed, "text": prefix + " reservoir empty"}
    assert authorize_family_message(resolve_family_principal(long_a, env), long_a,
        capability="farm_observation").replay_identity != authorize_family_message(
            resolve_family_principal(long_b, env), long_b,
            capability="farm_observation").replay_identity


def test_duplicate_or_malformed_authorization_configuration_fails_closed():
    duplicate = [_binding(), _binding(role="read_only_family_member",
                                      permissions=["explicit_summary"])]
    assert family_access_policy(_env(duplicate))["configuration_valid"] is False
    assert resolve_family_principal(_parsed("1002"), _env(duplicate)).role is FamilyRole.UNKNOWN_SENDER
    malformed = _binding(); malformed["authorized_at"] = "someday"
    assert resolve_family_principal(_parsed("1002"), _env([malformed])).role is FamilyRole.UNKNOWN_SENDER


def test_gateway_never_issues_owner_task_or_owner_lifecycle_to_family_identity():
    env = {**_env([_binding()]), "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": f"{OWNER},1002",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
           "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40}
    payload = {"message": {"message_id": 4001, "date": 1786176000,
        "text": "Hy eet nog nie", "from": {"id": 1002, "first_name": "Charl"},
        "chat": {"id": 1002, "type": "private"}}}
    with patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input") as owner_task:
        result, status = handle_telegram_gateway_message(
            payload, headers={"Authorization": "Bearer " + "g" * 40}, environ=env)
    assert status == 503 and result["status"] == "telegram_family_lifecycle_not_enabled"
    assert result["writes"] is False and result["dispatch_enabled"] is False
    assert "family_keys" not in result["telegram_gateway"]["family_access"]
    owner_task.assert_not_called()


def test_family_manager_output_is_three_priorities_one_question_and_suppresses_closed_work():
    result = bound_family_manager_result([
        {"identity": "welfare", "priority": 100},
        {"identity": "water", "priority": 80},
        {"identity": "water", "priority": 79},
        {"identity": "weigh", "priority": 70},
        {"identity": "old", "priority": 99, "completed": True},
        {"identity": "stale", "priority": 98, "stale": True},
        {"identity": "marketing", "priority": 20},
    ], ["Een gegroepeerde vraag?", "Tweede vraag?"])
    assert [item["identity"] for item in result["actions"]] == ["welfare", "water", "weigh"]
    assert result["question"] == "Een gegroepeerde vraag?" and result["question_count"] == 1
    assert result["farm_writes"] == result["telegram_sends"] == 0
