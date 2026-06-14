# 2.0B - Oom Sakkie Backend Read-Only Relay

Callable relay contract for testing the Flask-owned Oom Sakkie backend from the existing Telegram GateKeeper.

Status: import-ready / inactive by default  
Created for docs: 2026-06-14  
Phase: 10.9DM private Telegram relay contract

## Role

This workflow is a thin n8n adapter. It does not contain an Oom Sakkie brain.

The backend owns:

- message interpretation
- read-only tool routing
- deterministic-only Telegram channel behavior
- token and allowed-user checks
- no-LLM-egress/no-write/no-send flags
- audit trace recording

n8n owns only:

- receiving an already-authorized Telegram message from `2 - The GateKeeper`
- calling the backend read-only gateway
- validating the backend authority flags
- returning a caller-send reply payload to the caller

## Trigger

`Execute Workflow Trigger`

Do not add a Telegram Trigger to this workflow. `2 - The GateKeeper` remains the only normal Telegram `message` owner.

## Required n8n Variables

n8n Cloud can block Code node access to environment variables. Configure these as n8n **Variables** and access them through `$vars`, not `$env`.

- `OOM_SAKKIE_GATEWAY_BASE_URL`
  - Example private/local value: `http://127.0.0.1:5000`
  - Example HTTPS value: `https://amadeus-pig-tracking-system.onrender.com`
  - Include the `https://` scheme for Render. Do not paste quotes around the value.
  - The Build node strips common wrapping quotes and extracts a pasted `https://...` URL when possible, then reports `base_url_diagnostic` if validation still fails.
  - Remote plain HTTP is rejected before the bearer token is used. Use HTTPS for remote/private endpoints, or local HTTP only on localhost/127.0.0.1/::1.
- `OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN`
  - Must match the Flask `OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN`
  - Must be at least 32 characters
  - Do not hardcode it in the workflow export
  - The HTTP Request node reads it directly from `$vars`; the Build node validates length but does not copy the token into item JSON.

The backend must also have:

- `OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED=1`
- `OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS=<approved Telegram user id list>`

## Input Contract

Expected from `2 - The GateKeeper`:

```json
{
  "message_text": "what needs attention today",
  "user_id": "12345",
  "chat_id": "67890",
  "message_id": "123",
  "user_name": "Charl"
}
```

The workflow also accepts `text`, `telegram_user_id`, and `telegram_chat_id` as fallback field names for smoke tests.

## Output Contract

On a safe backend response, this workflow returns:

```json
{
  "success": true,
  "send_allowed": true,
  "chat_id": "67890",
  "telegram_text": "No current farm attention items are showing.",
  "backend_status": "answered",
  "sends_telegram": false,
  "reply_transport": "caller_handles_telegram_send",
  "can_trigger_outbound_llm": false,
  "writes": false,
  "records_audit_trace": true
}
```

The backend still sends no Telegram message. `send_allowed = true` means the caller has a safe text payload it may send using the existing GateKeeper-owned Telegram delivery path.

## Safety Rules

- Workflow export stays inactive by default.
- No Telegram Trigger.
- No Telegram send node.
- No OpenAI, LLM, Google Sheets, Supabase, shell, or code execution outside n8n JavaScript nodes.
- Backend token comes only from n8n Variables.
- Do not use `$env` in this workflow; Cloud Code nodes may throw `access to env vars denied`.
- `IF - Gateway Request Ready` must stay between the Build node and HTTP node so fail-closed setup errors do not continue into an undefined URL call.
- Refuse remote plain HTTP base URLs before using the bearer token.
- Do not continue when backend says `sends_telegram = true`.
- Do not continue when backend says `can_trigger_outbound_llm = true`.
- Do not continue when backend says `writes = true`, `dispatch_enabled = true`, `changes_runtime_now = true`, or `changes_prompt_now = true`.
- Do not add callback handling here. Button callbacks stay with the existing callback workflows.
- Do not activate or wire into GateKeeper before the backend preflight and private smoke pass.

## Manual Test Plan

1. Import inactive.
2. Configure n8n Variables with the private/local backend URL and token.
3. Keep the Flask backend private or HTTPS-protected.
4. Run `GET /api/oom-sakkie/channels/telegram/exposure-preflight` and confirm `private_test_ready = true`.
5. Execute this workflow manually with a test payload whose `user_id` is in the backend allowlist.
6. Confirm `success = true`, `send_allowed = true`, `sends_telegram = false`, `can_trigger_outbound_llm = false`, `writes = false`, and `records_audit_trace = true`.
7. Execute again with a non-allowlisted `user_id` and confirm it fails closed.
8. After owner approval, follow `../2 - The GateKeeper/BACKEND_RELAY_WIRING_PLAN.md` to wire `2 - The GateKeeper` for a narrow private test.

Helper command for step 5:

```powershell
.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_manual_test.py --payload
```

After copying the manual execution output to a local JSON file:

```powershell
.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_manual_test.py --validate-output tmp\n8n-2-0b-output.json
```

## Local Contract Check

Before importing the workflow export, run:

```powershell
.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_contract_check.py
```

Expected result:

- `relay_contract_status: ok`
- `active: false`
- `telegram_trigger: absent`
- `telegram_send_node: absent`
- `transport_guard: localhost_or_https`
- `authority_validation: present`

This check reads the committed workflow JSON and README only. It does not call n8n, Telegram, Flask, OpenAI, Google Sheets, or Supabase.

## Common Setup Errors

- `access to env vars denied`: the live workflow is still using `$env`; re-import this workflow export and configure n8n Variables.
- `URL parameter must be a string, got undefined`: the HTTP node is being reached without `gateway_url`; re-import this workflow export with `IF - Gateway Request Ready`.
- `OOM_SAKKIE_GATEWAY_BASE_URL must use https...`: set the n8n Variable to `https://amadeus-pig-tracking-system.onrender.com` or another full HTTPS URL. Do not use a bare domain and do not wrap the value in quotes.

## Not In This Slice

- No direct bot cutover.
- No second Telegram listener.
- No Telegram send authority inside this workflow.
- No customer/public channel expansion.
- No write tools.
- No specialist dispatch.
- No prompt, route, runtime, or farm-data mutation.
