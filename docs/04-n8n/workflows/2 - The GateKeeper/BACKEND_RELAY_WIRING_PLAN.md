# GateKeeper Backend Relay Wiring Plan

Phase: 10.9DM

Purpose: route owner Telegram messages through the Flask Oom Sakkie backend relay while keeping `2 - The GateKeeper` as the only Telegram listener and the only workflow that sends the reply.

## What To Upload

Upload this workflow first:

- `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/workflow.json`

Import it inactive. Do not add a Telegram Trigger. Do not add a Telegram send node.

Do not upload or replace `2 - The GateKeeper` from the repo for this step. Edit the live GateKeeper manually in the n8n UI after exporting a backup.

## Required Backend Env

The Flask/backend environment must have:

- `OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED=1`
- `OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN=<32+ char random token>`
- `OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS=<Charl Telegram user id>`

The n8n `2.0B` workflow must have these configured as n8n Variables, not Code-node `$env` values:

- `OOM_SAKKIE_GATEWAY_BASE_URL=<https backend URL or http://127.0.0.1:5000 for local>`
- `OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN=<same token as Flask>`

Reason: n8n Cloud can deny Code node access to environment variables with `access to env vars denied`; the relay reads `$vars.OOM_SAKKIE_GATEWAY_BASE_URL` and `$vars.OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN` instead.

For Render, set `OOM_SAKKIE_GATEWAY_BASE_URL` to `https://amadeus-pig-tracking-system.onrender.com`. Do not use a bare domain and do not wrap the value in quotes.

## Preflight Before Wiring

Run from the repo:

```powershell
.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_contract_check.py
.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py
.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_manual_test.py --payload
```

Expected:

- relay contract status is `ok`
- private preflight is ready
- gateway returns a reply payload with `sends_telegram = false`
- gateway returns `can_trigger_outbound_llm = false`
- gateway returns `writes = false`
- gateway returns `records_audit_trace = true`
- manual payload prints no token and includes `message_text`, `user_id`, `chat_id`, `message_id`, and `user_name`

## Manual 2.0B Execution Test

Before wiring GateKeeper:

1. Run:

   ```powershell
   .\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_manual_test.py --payload
   ```

2. Paste the printed JSON into a manual execution of imported `2.0B - Oom Sakkie Backend Read-Only Relay`.
3. Copy the 2.0B output JSON into a local temporary file, for example `tmp\n8n-2-0b-output.json`.
4. Validate it:

   ```powershell
   .\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_manual_test.py --validate-output tmp\n8n-2-0b-output.json
   ```

Expected:

- `relay_manual_output_status: ok`
- `success = true`
- `send_allowed = true`
- `reply_transport = caller_handles_telegram_send`
- `sends_telegram = false`
- `can_trigger_outbound_llm = false`
- `writes = false`
- `dispatch_enabled = false`
- `changes_runtime_now = false`
- `changes_prompt_now = false`

## Manual GateKeeper Edit

In n8n UI:

1. Export/download a backup of the live `2 - The GateKeeper` workflow.
2. Keep the existing `Telegram Trigger`.
3. Keep `Get User Info`, `Normalize Auth Check`, `Security Check`, and callback routing unchanged.
4. In the normal `message` branch, replace the current call to `2.0 - OOM SAKKIE - Amadeus Assistant Agent` with a call to imported `2.0B - Oom Sakkie Backend Read-Only Relay`.
5. Pass these fields into `2.0B`:
   - `message_text`
   - `user_id`
   - `chat_id`
   - `message_id`
   - `user_name`
6. Add a small validation node after `2.0B` that refuses to send unless all are true:
   - `success === true`
   - `send_allowed === true`
   - `reply_transport === "caller_handles_telegram_send"`
   - `sends_telegram === false`
   - `can_trigger_outbound_llm === false`
   - `writes === false`
   - `dispatch_enabled === false`
   - `changes_runtime_now === false`
   - `changes_prompt_now === false`
   - `physical_controls_enabled === false`
   - `customer_public_output_enabled === false`
7. Connect the success output to the existing GateKeeper-owned Telegram credential and send:
   - chat id: `{{$json.chat_id}}`
   - text: `{{$json.telegram_text}}`
8. Connect the failure output to a safe owner-only fallback reply:
   - `Oom Sakkie backend relay blocked the reply safely. No action was taken.`

## Post-Wiring Live Test

Send from Charl's Telegram account:

```text
What needs attention today?
```

Confirm in n8n executions:

- GateKeeper receives the message.
- GateKeeper authorizes Charl.
- GateKeeper calls `2.0B`.
- `2.0B` calls Flask `/api/oom-sakkie/channels/telegram/message`.
- GateKeeper sends exactly one reply.
- No other workflow becomes a Telegram listener.
- Callback routes to `2.4` and `2.4.5` remain unchanged.

Confirm in backend response/audit:

- `reply_transport = caller_handles_telegram_send`
- `sends_telegram = false`
- `can_trigger_outbound_llm = false`
- `writes = false`
- `records_audit_trace = true`

## Rollback

If Telegram goes silent or replies are wrong:

1. In n8n UI, restore the exported GateKeeper backup.
2. Deactivate and reactivate GateKeeper only if Telegram webhook registration needs refresh.
3. Run Telegram `getWebhookInfo` and confirm the bot webhook points to GateKeeper.
4. Leave `2.0B` inactive or unwired until the backend relay path is fixed.

## Still Not Allowed

- No second Telegram Trigger.
- No direct Telegram send inside `2.0B`.
- No Telegram callback route changes.
- No write tools.
- No specialist dispatch.
- No prompt, route, runtime, or farm-data mutation.
- No public/customer broadcast beyond Charl's owner reply.
- No physical control or financial action.
