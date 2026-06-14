from modules.oom_sakkie.access import LLM_MESSAGE_GUARD_ENVS, is_llm_message_guard_active
from modules.oom_sakkie.llm_answer import llm_answer_policy
from modules.oom_sakkie.llm_router import llm_router_policy
from modules.oom_sakkie.ledger_agent import ledger_agent_policy
from modules.oom_sakkie.sentinel_single_shot_runner import specialist_dry_run_policy
from modules.oom_sakkie.telegram_direct import telegram_direct_policy
from modules.oom_sakkie.telegram_gateway import telegram_gateway_policy
from modules.oom_sakkie.tools import TOOL_REGISTRY, RiskLevel
from modules.oom_sakkie.voice_stt import backend_voice_stt_policy


def get_runtime_policy():
    tools = list(TOOL_REGISTRY.values())
    llm_answer = llm_answer_policy()
    llm_router = llm_router_policy()
    ledger_agent = ledger_agent_policy()
    specialist_dry_run = specialist_dry_run_policy()
    backend_voice_stt = backend_voice_stt_policy()
    telegram_gateway = telegram_gateway_policy()
    telegram_direct = telegram_direct_policy()
    llm_message_guard_active = is_llm_message_guard_active()
    draft_tools = [
        tool.name
        for tool in tools
        if tool.risk_level == RiskLevel.DRAFT_ONLY and not tool.requires_confirmation
    ]
    write_tools = [
        tool.name
        for tool in tools
        if tool.risk_level > RiskLevel.DRAFT_ONLY or tool.requires_confirmation
    ]
    confirmation_tools = [
        tool.name
        for tool in tools
        if tool.requires_confirmation
    ]
    read_only_tools = [
        tool.name
        for tool in tools
        if tool.risk_level == RiskLevel.READ_ONLY and not tool.requires_confirmation
    ]
    blocked_capabilities = [
        "Telegram direct bot cutover",
        "write tools",
        "physical controls",
        "backend TTS vendors",
        "wake word",
        "always-on microphone",
        "Ungated LLM router",
        "customer-facing messages",
    ]
    if not backend_voice_stt["enabled"]:
        blocked_capabilities.insert(3, "backend STT vendors")
    if not telegram_gateway["enabled"]:
        blocked_capabilities.append("Telegram read-only gateway")
    if not telegram_direct["enabled"]:
        blocked_capabilities.append("Telegram direct owner bot")
    return {
        "success": True,
        "mode": "local_kiosk_read_only",
        "backend_as_brain": True,
        "telegram_cutover_enabled": telegram_direct["direct_bot_cutover_enabled"],
        "telegram_gateway_enabled": telegram_gateway["enabled"],
        "telegram_gateway": telegram_gateway,
        "telegram_direct_enabled": telegram_direct["enabled"],
        "telegram_direct": telegram_direct,
        "llm_answer_enabled": llm_answer["enabled"],
        "llm_answer": llm_answer,
        "llm_router_enabled": llm_router["enabled"],
        "llm_router": llm_router,
        "ledger_sales_agent_enabled": ledger_agent["enabled"],
        "ledger_sales_agent": ledger_agent,
        "specialist_dry_run_enabled": specialist_dry_run["enabled"],
        "specialist_dry_run": specialist_dry_run,
        "write_tools_enabled": False,
        "physical_controls_enabled": False,
        "backend_voice_vendors_enabled": backend_voice_stt["enabled"],
        "backend_voice_stt": backend_voice_stt,
        "always_on_mic_enabled": False,
        "browser_speech_mode": "push_to_talk_with_backend_stt_fallback" if backend_voice_stt["enabled"] else "push_to_talk_only",
        "continue_conversation_enabled": True,
        "continue_conversation_max_turns": 5,
        "voice_auto_send_ms": 2000,
        "trace_writes_enabled": True,
        "review_endpoints_access": {
            "default": "loopback_only",
            "private_lan_env": "OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN",
            "reverse_proxy_assumption": "remote_addr_must_be_the_real_client_ip",
            "reverse_proxy_caveat": "If Flask sits behind nginx, Caddy, Cloudflare, Render, or another proxy, configure trusted proxy handling before relying on loopback review protection.",
        },
        "message_endpoint_access": {
            "default": "local_guard_required_when_llm_enabled" if llm_message_guard_active else "reachable_wherever_flask_is_reachable",
            "route": "POST /api/oom-sakkie/message",
            "llm_guard_active": llm_message_guard_active,
            "llm_guard_envs": list(LLM_MESSAGE_GUARD_ENVS),
            "llm_guard_rule": "When LLM router, answer composer, or learning analyst is enabled, /message must pass the same loopback/private-LAN guard before outbound API calls can occur.",
            "note": "This is the local brain endpoint, not an admin/review endpoint. Keep Flask bound to trusted local/LAN surfaces until channel auth is added.",
        },
        "kiosk_policy": {
            "channel": "kiosk",
            "max_risk_level": int(RiskLevel.DRAFT_ONLY),
            "allowed_risk_label": RiskLevel.DRAFT_ONLY.name,
            "requires_confirmation_tools": confirmation_tools,
        },
        "tool_counts": {
            "total": len(tools),
            "read_only": len(read_only_tools),
            "draft_only": len(draft_tools),
            "write_or_confirmation": len(write_tools),
        },
        "blocked_capabilities": blocked_capabilities,
    }
