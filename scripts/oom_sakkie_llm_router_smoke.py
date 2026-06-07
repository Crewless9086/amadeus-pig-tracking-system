from pathlib import Path

from dotenv import load_dotenv

from modules.oom_sakkie.llm_answer import llm_answer_policy
from modules.oom_sakkie.llm_router import llm_router_policy
from modules.oom_sakkie.service import handle_message


PROMPTS = [
    "give me the energy situation",
    "check if the outside conditions are a problem",
    "which farm area should I inspect first",
    "delete a pig record",
    "what can you do",
]


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    policy = llm_router_policy()
    answer_policy = llm_answer_policy()
    print("LLM router enabled:", policy["enabled"])
    print("LLM router configured:", policy["configured"])
    print("LLM router can write:", policy["can_write"])
    print("LLM answer enabled:", answer_policy["enabled"])
    print("LLM answer configured:", answer_policy["configured"])
    print("LLM answer can write:", answer_policy["can_write"])
    print("LLM answer sends tool summary:", answer_policy["sends_tool_summary_when_enabled"])
    print("Outbound endpoint when enabled:", policy["outbound_endpoint_when_enabled"])
    print("Sends user text when enabled:", policy["sends_user_text_when_enabled"])
    print("Allowed tool count:", len(policy["allowed_tools"]))

    if not policy["enabled"] or not policy["configured"]:
        print("SKIP: set OOM_SAKKIE_LLM_ROUTER_ENABLED=true, OPENAI_API_KEY, and OOM_SAKKIE_LLM_ROUTER_MODEL in .env.")
        return 2

    for prompt in PROMPTS:
        result, status_code = handle_message({
            "text": prompt,
            "channel": "kiosk_llm_smoke",
            "session_id": "llm-router-smoke",
        })
        intent = result.get("intent") or {}
        print("---")
        print("prompt:", prompt)
        print("status:", status_code)
        print("tool:", result.get("tool_used") or "(none)")
        print("needs_clarification:", result.get("needs_clarification"))
        print("action_blocked:", result.get("action_blocked", False))
        print("intent:", intent.get("name"), intent.get("confidence"), intent.get("reason"))
        print("answer:", result.get("answer"))
        print("safety_notes:", result.get("safety_notes") or [])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
