# Oom Sakkie owner-request agent lifecycle handover

Status: SOURCE CANDIDATE / NOT YET INTEGRATED OR DEPLOYED
Date: 2026-08-01 Africa/Johannesburg

## Business outcome

The existing authenticated Oom Sakkie Telegram ingress can now recognize an
answer to an active owner request, retain one durable task, acknowledge receipt
once, distinguish deployed specialist-agent execution from development-terminal
work, and return one result to the originating task. It creates no bot, route,
queue, decision ledger, workflow family, or specialist service.

Terminology is strict:

- **agent**: deployed cloud/runtime operational service;
- **terminal**: manually prompted development session;
- **specialist role**: complete intended business responsibility.

A release row never implies agent receipt or execution. Agent health never
proves terminal delivery. Source work in a terminal is never represented as
deployed-agent activity.

## Reused production surfaces

- authenticated `handle_telegram_direct_webhook` and active
  `handle_telegram_gateway_message` ingress with the existing owner allowlist;
- existing Telegram `sendMessage` transport;
- existing BEACON private Telegram-media download, validation and readback
  primitives;
- existing `sam_live_stock_conversation_review_events` append-only evidence
  rail;
- PR #649's pure specialist dispatch acknowledgement reducer.

The lifecycle records `received`, `assigned`, `working`,
`waiting_for_input`, `completed`, `failed`, or `contained`. Dispatch completion
requires exact mission/worker/release bindings, delivery acknowledgement, fresh
task activity and an outcome artifact. Missing acknowledgement/start becomes
one stable systemic exception rather than an invisible stall.

Production preflight found the direct route intentionally disabled. The active
GateKeeper therefore keeps its single trigger, leaves ordinary text and BEACON
single-photo routing unchanged, and forwards only a private-owner,
unforwarded, stable photo album through a dedicated authenticated gateway
output. Rejected or unsupported media remains terminal. The gateway uses the
existing SAM/Oom owner bot as one explicit canonical identity for both media
download and owner-task delivery, requires a Telegram provider message ID, and
never retries ambiguous delivery.

## ROOTLINE request 3156 recovery binding

Recovery is fail-closed on all of these facts:

- durable delivered request identity
  `OOM-ROOTLINE-SMARTLIFE-CAPABILITY-REQUEST-20260801-DELIVERED`;
- Telegram request message `3156` and its durable delivery timestamp;
- authenticated private owner/chat binding;
- album `14284829442614404`;
- provider messages `3157` through `3162` and their exact Telegram
  `file_unique_id` values;
- the six exact Telegram provider message/file identities and the byte hashes
  of the authenticated provider JPEGs after private storage readback;
- the six original screenshot hashes listed in
  `C:\tmp\rootline-ewelink-controller-evidence-20260801.md`, retained as
  distinct source provenance rather than asserted to equal Telegram's
  normalized JPEG bytes;
- prepared ROOTLINE result
  `ROOTLINE-BC-AUTONOMOUS-CONTROL-CLOSURE-20260801`, SHA-256
  `0747FFE0DBF3CDAEB0BADD6DE3B2DF43174B855616BDAC3881585FAE00BF1A50`.

The prepared result was produced through manual specialist-role work; the
adapter truthfully records that no deployed ROOTLINE agent was dispatched and
no development terminal was started by Oom Sakkie. The deployed Oom Sakkie
agent only reconciles the already-authoritative artifact to the recovered task.

The result tells Charl that independent native per-channel auto-OFF is limited
to 60 minutes. Separately authorized, commissioned runs may therefore be at
most 60 minutes; one uninterrupted 120-minute run needs an independent interval
safety relay. It changes no controller setting and performs no hardware action.

## Replay and delivery contract

Media item identity, task identity, acknowledgement, exception and result
events are deterministic. Media replay is checked before download/upload, and
the aggregate is reloaded after each atomic item claim so concurrent album
arrivals cannot strand completion. Album retries, duplicate updates and
repeated callbacks therefore create no second task, media write,
acknowledgement, exception or result. Prepared-result completion requires exact
cardinality, provider item identities and byte hashes.

The first bounded recovery proved Telegram had recompressed the six images.
Oom Sakkie correctly recorded the six received items, delivered one receipt
acknowledgement, then delivered one truthful no-adapter exception instead of
claiming the prepared conclusion against unequal bytes. Visual reconciliation
of the private readbacks proved the exact provider set contains the same
device/channel map, SONOFF 4CH Pro R3 identity, firmware 3.8.2, safe power-on
states and independent inching controls as the authoritative ROOTLINE
evidence. The corrected binding uses these provider-readback SHA-256 values:

- `4278abdce3e6f85d517498c40a44686cb4f3d35551f34851da8b85a5bdb977d1`
- `30c15c19a5c80932aaceb4ab8547441a5ce0eec7b9ce144cb1cf67c9a9dfa31b`
- `ae54b7832a8f3f7094c294d73e035c2a433732e0de9949f8941676adb4a24b1a`
- `496e79ac9b9c67066e3d6366eade68003e154c8f3c6e20ac285c9efa96856834`
- `101c52f258d8cca94092a3d7b8ccd62e32f1708c367b5f73bf0085be6c11e0cb`
- `7c8489400d3c8c4d1d2d2109d9374f683c1b21509e136545dca52aab58e324c6`

The retained task may now advance from its historical containment to the one
prepared completion. Existing acknowledgement and exception delivery events
remain immutable; recovery must send no second acknowledgement or exception.

Every Telegram acknowledgement, result and exception has separate attempted
and provider-delivered evidence. Delivery requires a non-empty Telegram message
identity. An attempted delivery with no confirmation is never blindly retried:
a bounded recovery must first prove either the existing provider message or
that it is conclusively absent. Ambiguity produces zero sends. Timeout wording
separately identifies a missing deployed-agent acknowledgement or a missing
fresh start; only the true no-adapter path says no deployed adapter exists.

Specialist-agent delivery uses the same boundary: a dispatch attempt is not a
delivery receipt, accepted-but-response-lost remains pending, ambiguous status
creates no redispatch, and retry is allowed only after conclusive absence.
Later status reconciliation can advance the exact task through acknowledgement,
fresh activity and completion. The request's dispatch binding also includes the
SHA-256 of the exact UTF-8 owner result; altered presentation bytes are rejected
even when artifact metadata otherwise matches.

## Verification and production proof still required

Source acceptance:

```powershell
C:\Users\charl\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_owner_task_lifecycle tests.test_oom_sakkie_specialist_dispatch_ack -v
```

Later production proof must bind exact merge and deployed revisions, prove the
existing webhook remains singular and healthy, then recover the authoritative
six-message album once. Required evidence is one provider-confirmed receipt
acknowledgement, one provider-confirmed completion, one completed task artifact,
and a second bounded replay with zero rows, zero messages, zero specialist
dispatches and zero hardware actions. Preserve SAM, ROOTLINE planning, BEACON,
HERDMASTER and all existing Telegram cards. Release the serialized runtime lane
immediately after proof or exact containment.
