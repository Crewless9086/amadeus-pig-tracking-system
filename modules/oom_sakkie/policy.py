from modules.oom_sakkie.llm_router import llm_router_policy
from modules.oom_sakkie.tools import TOOL_REGISTRY, RiskLevel


def get_runtime_policy():
    tools = list(TOOL_REGISTRY.values())
    write_tools = [
        tool.name
        for tool in tools
        if tool.risk_level > RiskLevel.READ_ONLY or tool.requires_confirmation
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
    return {
        "success": True,
        "mode": "local_kiosk_read_only",
        "backend_as_brain": True,
        "telegram_cutover_enabled": False,
        "llm_router_enabled": llm_router_policy()["enabled"],
        "llm_router": llm_router_policy(),
        "write_tools_enabled": False,
        "physical_controls_enabled": False,
        "backend_voice_vendors_enabled": False,
        "always_on_mic_enabled": False,
        "browser_speech_mode": "push_to_talk_only",
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
            "default": "reachable_wherever_flask_is_reachable",
            "route": "POST /api/oom-sakkie/message",
            "note": "This is the local brain endpoint, not an admin/review endpoint. Keep Flask bound to trusted local/LAN surfaces until channel auth is added.",
        },
        "kiosk_policy": {
            "channel": "kiosk",
            "max_risk_level": int(RiskLevel.READ_ONLY),
            "allowed_risk_label": RiskLevel.READ_ONLY.name,
            "requires_confirmation_tools": confirmation_tools,
        },
        "tool_counts": {
            "total": len(tools),
            "read_only": len(read_only_tools),
            "write_or_confirmation": len(write_tools),
        },
        "blocked_capabilities": [
            "Telegram cutover",
            "write tools",
            "physical controls",
            "backend STT/TTS vendors",
            "wake word",
            "always-on microphone",
            "Ungated LLM router",
            "customer-facing messages",
        ],
    }
