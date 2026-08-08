import json

from modules.oom_sakkie.family_access import (
    FamilyRole, authorize_family_message, bound_family_manager_result, family_access_policy,
    resolve_family_principal,
)


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
    assert first.may_write_farm_data is second.may_write_farm_data is False


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
