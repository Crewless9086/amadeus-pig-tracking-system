# Oom Sakkie Voice Operating Agent PRD

Date: 2026-06-06

## Status

Planning document.

This PRD defines the long-term voice operating agent for the Amadeus Farm Operations Platform. The working name is **Oom Sakkie**, but the name can still change.

Two reference videos were provided for interaction inspiration:

- `screenshots/WhatsApp Video 2026-06-06 at 14.08.10.mp4` - local metadata shows length about `00:02:55`.
- `screenshots/WhatsApp Video 2026-06-06 at 14.11.47.mp4` - local metadata shows length about `00:01:05`.

The local environment could read file metadata but could not decode/transcribe the MP4s because `ffprobe`/media tooling is not installed. The interaction style should be reviewed manually from the videos before hardware/UI finalization.

## Executive Summary

The goal is to build a farm "Jarvis": a live voice assistant in the house that can be spoken to naturally and can coordinate the farm operating system.

The correct architecture is not one giant chatbot that directly changes everything. The correct architecture is:

```text
Voice / Chat Interface
  |
  v
Oom Sakkie Orchestrator
  |
  v
Backend APIs and Read Models
  |
  v
Database / Google Sheets / Supabase / Event Logs
  |
  v
Specialist Agents and Automation Workers
```

Oom Sakkie should become the conversational control layer. The backend remains the source of truth. Specialist agents do focused work. The system should start with read-only answers and guarded actions, then slowly expand into controlled operations.

## Inspiration: Trillion Pattern

The Trillion public site was reviewed on 2026-06-06. Useful ideas to borrow conceptually:

- voice-first interaction
- a visible screen/UI layer
- live monitoring across important systems
- specialized sub-agents reporting to one main persona
- concise, opinionated answers based on live data
- local wake-word detection for hands-free use
- state in a real database
- FastAPI/WebSockets-style live UI layer
- browser automation only as a tool, not as the source of truth

Trillion says its current stack includes a Python async harness, Claude for reasoning, Deepgram for streaming speech-to-text, ElevenLabs for text-to-speech, local wake-word detection, Postgres for state, FastAPI/WebSockets for UI, real browser automation for research, and a future Tauri/Next.js desktop shell.

How this maps to Amadeus:

| Trillion idea | Amadeus version |
| --- | --- |
| Revenue/code/customers/data/comms/intel | Pigs, litters, sales, weather, power, irrigation, orders, meat planning |
| AI co-founder | Farm operating partner |
| Sub-agents | Pig, health, sales, weather, power, irrigation, reporting agents |
| Postgres state | Supabase/Postgres event state plus existing backend read models |
| FastAPI/WebSockets UI | Flask now; possible WebSocket/local kiosk layer later |
| Desktop shell | Local farm PC kiosk first; possible Tauri shell later |
| Wake-word | Later; push-to-talk or click-to-talk first |

Important difference: Oom Sakkie is operating a real farm. It must be more conservative than a founder dashboard. It can be witty and useful, but operational writes, public posts, customer messages, and hardware actions need explicit guards.

## Product Vision

Oom Sakkie should eventually let the farm owner say things like:

- "Oom Sakkie, what needs attention today?"
- "How many pigs are ready for meat?"
- "Which litters are close to weaning?"
- "What happened with the power last night?"
- "Remind me to weigh Pen 3 tomorrow morning."
- "Show me the slaughter sales this month."
- "Prepare a quote for the latest approved order, but do not send it yet."
- "Which pigs are growing too slowly?"
- "What should we sell this week?"

The assistant should respond naturally by voice, but it should also leave an auditable trace in the app where needed.

## Main Principle

Oom Sakkie must not become the database.

Good:

```text
User speaks
Oom Sakkie understands intent
Backend reads trusted data
Backend returns answer/action plan
Oom Sakkie explains it
Backend logs actions
```

Bad:

```text
User speaks
Oom Sakkie guesses
Agent writes directly to Sheets/Supabase
No approval, no audit, no rollback path
```

## Product Goals

1. Give the owner a natural voice interface to the farm.
2. Make farm data easier to use without opening many screens.
3. Coordinate smaller agents without letting them own truth.
4. Support local in-house voice interaction later.
5. Keep Telegram/Oom Sakkie working while the house voice system is built.
6. Build safely: read-only first, then confirmation-based actions, then limited automation.

## Non-Goals

Oom Sakkie should not initially:

- run the whole farm without approval
- directly write to Google Sheets or Supabase
- auto-post to Meta/Facebook
- auto-spend money
- auto-approve customer orders
- auto-control irrigation or hardware without command guards
- replace the web app
- replace audit logs
- rely on chat history as source of truth

## Users

Primary:

- Charl / farm owner

Future:

- family members
- farm managers
- sales operators
- delivery personnel
- future staff

## Interaction Channels

### Current Channels

- Telegram Oom Sakkie
- n8n GateKeeper
- backend APIs
- web app

### Future Channels

- in-house voice device
- local farm PC kiosk with always-on screen
- mobile PWA voice button
- desktop/browser voice mode
- optional notification channels such as email or Slack later

## Recommended Build Path

## Claude Architecture Review - 2026-06-06

Claude reviewed the PRD and recommended: **revise first, then build a narrow OS-1 + OS-4 slice**.

The review agreed with the safety posture, but flagged a key architecture risk: the farm already has `2.0 - OOM SAKKIE` in n8n, with deterministic sub-agent routing for weather (`2.1`), power (`2.2`), and irrigation status (`2.3.3`). A new Flask endpoint can become a second brain if it has its own prompt/tool catalog and answers the same questions differently.

### Orchestrator Decision

Decision confirmed by owner on 2026-06-06:

**Flask/backend becomes the single long-term Oom Sakkie brain.**

- n8n/GateKeeper remains Telegram I/O, callback routing, and scheduled-work infrastructure.
- Telegram messages eventually forward to `/api/oom-sakkie/message`.
- Backend owns typed tools, risk levels, ACL, trace IDs, stale-data handling, confirmation payloads, and future write guards.
- `2.0 - OOM SAKKIE` routing should eventually become a thin forwarder instead of a second routing brain.
- This avoids split-brain behavior across kiosk, web, Telegram, mobile PWA, and future voice channels.

Implementation sequence:

- First implementation leaves live Telegram routing unchanged.
- The kiosk/backend endpoint must be proven first.
- Telegram cutover must use a parallel-run window before `2.0` routing is replaced.

Long-term OS-1 rule:

```text
Backend is the single Oom Sakkie brain.
n8n GateKeeper remains Telegram I/O and scheduled work.
Once /api/oom-sakkie/message is trusted, 2.0's routing layer is replaced by a forwarder.
Cutover requires a parallel-run window.
```

### Determinism During Migration

The current Telegram power/weather behavior is deterministic. The backend endpoint must preserve that when Telegram is later routed through it.

Classifier policy:

- Use exact-match/rule routing before any LLM classifier.
- Known live phrasings for power/weather/farm-attention skip the LLM and go straight to the matching tool.
- The LLM classifier only runs when deterministic rules do not match.
- Low confidence returns `needs_clarification = true`; it must not guess.

This keeps the proven Telegram behavior stable while still allowing the backend brain to become more flexible over time.

### Telegram Migration Sequence

Do not cut Telegram over immediately.

1. Build `/api/oom-sakkie/message` and `/oom-sakkie`; leave Telegram unchanged.
2. Use the kiosk daily for about two weeks; log every trace and watch for wrong tool selection, dropped stale warnings, and ambiguity.
3. Add a parallel Telegram route to `/api/oom-sakkie/message`, feature-flagged and limited to Charl's chat ID first.
4. Run parallel for about one week; compare old n8n path answers against backend path answers. Any disagreement is treated as a new-path bug until proven otherwise.
5. Cut over `2.0` to a thin forwarder only after the parallel run is clean.
6. Keep `2.1`, `2.2`, and `2.3.3` exports in the repo as references for about 30 days after cutover, then archive.

### Revised First Slice

Build only **Phase 10.6A / OS-1 + OS-4: Oom Sakkie Kiosk MVP - read-only text**:

- `GET /oom-sakkie` - local kiosk page, text-only, no microphone, no TTS, no wake word.
- `POST /api/oom-sakkie/message` - text-only orchestrator endpoint.
- Three read-only tools only:
  - `farm_attention_summary`
  - `power_current`
  - `weather_today`
- Response shape:

```json
{
  "answer": "",
  "tool_used": "",
  "trace_id": "",
  "risk_level": 0,
  "links": [],
  "stale_warnings": [],
  "needs_clarification": false
}
```

- Kiosk displays only:
  - user text
  - checking status
  - answer
  - trace ID, collapsed by default
  - links
  - stale-data warnings

Defer everything else until the loop is stable: push-to-talk, transcription, TTS, wake word, more agents, more tools, writes, public posting, customer messages, and hardware control.

### Runtime Requirements From Review

The first backend slice must include:

- typed tool registry in code, not only markdown
- tool input schema, output schema, risk level, confirmation requirement, and handler
- typed risk enum
- confidence floor for tool selection
- `needs_clarification = true` when confidence is low
- stale-data fields surfaced in the final answer
- trace ID threaded through classifier, tool call, answer, and response
- append-only trace store
- no multi-turn memory promise yet
- no writes

Trace store target:

- preferred: Supabase table `oom_sakkie_traces`
- fallback only if needed: a temporary sheet tab

Trace fields:

- `trace_id`
- `channel`
- `session_id`
- `user_text`
- `intent`
- `confidence`
- `tool_name`
- `tool_args_json`
- `tool_result_summary`
- `tool_result_hash`
- `answer`
- `risk_level`
- `stale_warnings_json`
- `links_json`
- `created_at`

### First Kiosk UX Rules

- Use large readable text for a room screen: roughly `18px` body and `32px` answer baseline.
- Avoid 3D, avatars, particles, or decorative complexity in the MVP.
- Use a simple status dot or subtle waveform later.
- Trace ID is visible but collapsed by default.
- Confirmation UI pattern should be designed now for future writes: exact backend payload preview, not paraphrased text.
- Kiosk access must be LAN/IP/device controlled before it is treated as trusted.
- Current local review endpoints rely on Flask `request.remote_addr`. That is acceptable only while Flask is directly reachable without a reverse proxy in front. If nginx, Caddy, Cloudflare, Render, Waitress behind a proxy, or any other proxy is introduced, configure trusted proxy handling first and make review access checks use the validated client IP, not the proxy loopback address.
- `POST /api/oom-sakkie/message` is intentionally reachable wherever the local Flask app is reachable during the kiosk MVP. It is not an admin/review endpoint. Keep Flask bound to trusted local/LAN surfaces until channel auth or a device policy is added.

### First Hardware Sequence

Do not buy hardware until the text loop is proven.

Recommended order:

1. Make backend reachable on the LAN over HTTPS.
2. Run the kiosk page in Chrome/Edge kiosk mode on the Windows farm PC.
3. Use text-only daily for at least a week.
4. Add USB conference mic and speaker only after text use is stable.
5. Add browser push-to-talk.
6. Add browser SpeechSynthesis TTS.
7. Add UPS.
8. Consider wake word only after push-to-talk is used daily for weeks.

### Do Not Build Yet

- always-on wake word
- always-on room microphone
- 3D avatar or animated character
- Afrikaans/multi-language behavior
- customer-facing messages
- Meta/Facebook posts
- auto purpose-classification writes
- irrigation start/stop or `2.3.2` activation
- direct Google Sheets/Supabase writes from the orchestrator
- autonomous loops
- new Telegram trigger workflows

### Phase OS-0: Architecture And PRD

Outcome:

- this PRD
- Claude review prompt
- chosen MVP route
- safety policy
- first tool catalog

No code required.

### Phase OS-0B: External Playbook Intake

The owner provided a Trillion-inspired prompt pack on 2026-06-06. It has been adapted into:

- `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md`

Captured playbooks:

- voice-first kiosk visual language
- code/repo monitoring
- cloud/local memory
- read-only Supabase connector
- Chief of Staff/north-star helper
- context handoff workflow
- mobile voice PWA
- personality persistence
- voice latency streaming
- agent security hardening
- head-of-design sub-agent
- living self-knowledge
- cost dashboard
- sub-agent factory

Build rule:

These are now part of the Oom Sakkie architecture backlog, but they are not all MVP scope. The immediate build remains the narrowed read-only orchestrator API and local kiosk page. Security, self-knowledge, cost tracking, and agent factory work must come only after the tool catalog and runtime architecture are real enough to support them.

### Phase OS-1: Oom Sakkie Orchestrator API

Create a backend-owned orchestrator endpoint:

```text
POST /api/oom-sakkie/message
```

Input:

- user text
- channel: telegram, web, voice_home, mobile
- user identity
- session id
- optional audio transcript metadata

Output:

- answer text
- optional voice response text
- proposed action
- action risk level
- confirmation required yes/no
- trace id
- links to relevant app pages

This endpoint should route to existing read models before adding any new agent complexity.

### Phase OS-2: Tool Catalog

Create an explicit tool catalog. Oom Sakkie may only use approved backend tools.

First read-only tools:

| Tool | Purpose |
| --- | --- |
| `farm_attention_summary` | What needs attention today. |
| `dashboard_summary` | Current farm operating snapshot. |
| `pig_allocation_readiness` | Livestock/meat/slaughter/breeding readiness. |
| `meat_planning` | Meat pipeline and demand scenario. |
| `sales_dashboard` | Sales overview and revenue summary. |
| `weather_current` | Current weather. |
| `weather_forecast` | Forecast. |
| `power_current` | Current Sunsynk/power status. |
| `power_recent` | Recent power profile. |
| `order_lookup` | Find/summarize orders. |

First guarded write tools later:

| Tool | Risk | Guard |
| --- | --- | --- |
| `mark_litter_weaned` | Medium | explicit confirmation |
| `record_weight` | Medium | confirmation and duplicate check |
| `record_treatment` | Medium | product/date/pig confirmation |
| `prepare_quote_send` | Medium | button/voice confirmation |
| `send_quote_to_customer` | High | explicit operator approval |
| `record_slaughter_sale` | High | web form preferred first |
| `classify_pig_purpose` | High | batch preview and explicit apply |

### Phase OS-3: Text First, Voice Later

Before always-on voice hardware, build the Oom Sakkie brain as text:

- Telegram message in
- web app text input
- backend orchestrator
- tool routing
- answer with trace

Reason: if the text brain is wrong, voice only makes it faster to do wrong things.

### Phase OS-4: Farm PC Kiosk MVP

Build the first visible "Oom Sakkie in the house" interface on the local farm PC.

This should be a full-screen/kiosk page, not just a hidden backend service.

Route idea:

```text
/oom-sakkie
```

First screen should show:

- wake/listening status
- last thing Oom Sakkie heard
- what it is thinking/checking
- which tool or agent it called
- answer text
- voice/speech status
- cards for current farm attention, meat planning, weather, power, sales, and litters
- links/buttons to open the exact farm app pages it is using
- visible trace ID for debugging
- clear confirmation panel when an action is proposed

This is the "screen that opens and shows what it is seeing/finding" part.

The screen should make the invisible agent visible:

```text
You asked: "What needs attention today?"
Oom Sakkie is checking: Farm Attention Summary
Result: 2 litter items, 1 order item
Open: Dashboard / Litter LIT-...
Trace: OSK-...
```

Do not start with 3D animation, decorative visuals, or complicated avatars. Start with a clear operational console. A voice orb/waveform can be added, but the useful part is the live reasoning/tool/result display.

### Phase OS-5: Push-To-Talk Voice MVP

Add voice without always-on house microphones:

- web app/PWA push-to-talk
- microphone records user speech
- speech-to-text/transcription
- orchestrator handles text
- response can be spoken back

This is the lowest-risk voice MVP.

### Phase OS-6: Always-On In-House Voice Device

Only after OS-1 to OS-5 are trusted, add local house voice.

Possible setups:

#### Option A: Home Assistant Voice Path

Use Home Assistant as the in-house voice/speaker layer.

Pros:

- strong local smart-home ecosystem
- supports voice satellites
- good fit for house devices, wake words, speakers, and future local automations
- can call webhooks/backend APIs

Cons:

- another platform to maintain
- still needs careful backend command guards
- custom personality/agent behavior needs integration work

#### Option B: Custom Local Voice Gateway

Run a small local service on the home computer or mini PC:

```text
microphone/speaker
local wake word or push button
speech-to-text
Oom Sakkie backend call
text-to-speech
speaker output
```

Pros:

- maximum control
- can be tightly integrated with the farm backend
- less smart-home platform complexity

Cons:

- more custom engineering
- more audio/device maintenance
- harder to get reliable always-on wake word and room audio

#### Option C: Telegram Voice Notes First

Use Telegram voice messages as the first voice-like channel.

Pros:

- uses existing Oom Sakkie channel
- no hardware required
- easy to audit
- good first test of spoken farm commands

Cons:

- not a room assistant
- not hands-free
- not as magical as always-on voice

Recommended route:

```text
Telegram/web text -> farm PC kiosk -> Telegram voice notes / web push-to-talk -> Home Assistant or custom in-house voice
```

### Phase OS-7: Mobile Voice PWA

After the kiosk and push-to-talk voice path work, add a phone PWA companion.

Important constraints from the playbook:

- serve over HTTPS
- use the same backend brain and conversation/session model
- push-to-talk first
- MP3 audio playback through `<audio>` for iOS reliability
- non-evicting TTS lookup by turn/segment ID
- token auth via header and query param where browser APIs require it
- no-store shell and versioned JS imports
- action chips for tool calls and confirmation requests

### Phase OS-8: Voice Latency Optimization

After voice exists, optimize the delay between user speech and Oom Sakkie's first audible word.

Target pattern:

- stream LLM text by sentence
- emit `speak_segment` events
- use a client-side audio queue
- support interruption cleanly
- measure first-audio latency

Do not optimize latency before basic voice correctness is proven.

### Phase OS-9: Security And Observability Layers

Before write tools, public/customer actions, browser automation, or physical controls, add:

- log redaction
- untrusted-content gating
- subprocess environment stripping
- auth rate-limit/lockout
- dev-mode public-bind startup guard
- token rotation support
- security headers/CSP
- pre-commit secret scanning
- tiered tool approval
- kill switch
- security shield/audit endpoint
- incident runbook

Cost dashboard and LLM usage capture belong here once Oom Sakkie makes direct backend LLM calls.

### Phase OS-10: Self-Knowledge And Agent Factory

After Oom Sakkie has a real tool registry and specialist-agent runtime:

- add living self-knowledge generated from the actual registry
- inject a slim self-knowledge summary into the prompt
- add drift checks
- only then consider a sub-agent factory

The factory must keep spawned agents as reviewed configuration, not generated code. Human approval is mandatory before any generated agent becomes active.

## Local Home Setup Recommendation

For the first physical home setup, use a small always-on machine:

- mini PC or existing home computer
- screen that can stay on in kiosk/full-screen mode
- stable internet
- UPS if possible
- good USB or conference-room microphone
- reliable speaker or small soundbar
- Python/Node service for the voice gateway if not using Home Assistant

Suggested minimum local roles:

| Component | Role |
| --- | --- |
| Farm backend | Owns API, data, and safety rules. |
| Oom Sakkie orchestrator | Understands requests and selects tools. |
| Farm PC kiosk | Shows what Oom Sakkie heard, checked, and answered. |
| Voice gateway | Captures speech and plays response. |
| Home Assistant or custom service | Manages local microphone/speaker devices. |
| n8n | Thin integration layer for Telegram, schedules, and delivery. |

Recommended first local setup:

```text
Windows farm PC
Chrome/Edge full-screen kiosk page at /oom-sakkie
USB microphone/speaker
Push-to-talk button on screen or keyboard shortcut
Backend orchestrator endpoint
Text-to-speech response
```

Always-on wake word should come later, because room audio is harder than it looks. Background noise, multiple people, fans, animals, and distance from the microphone can all reduce reliability.

## Agent Architecture

Oom Sakkie is the conductor. Specialist agents are workers.

```text
Oom Sakkie Orchestrator
  |
  +--> Farm Attention Agent
  +--> Pig Management Agent
  +--> Breeding Agent
  +--> Health/Treatment Agent
  +--> Sales/Orders Agent
  +--> Pork Business Agent
  +--> Weather Agent
  +--> Power Agent
  +--> Irrigation Agent
  +--> Finance/Reporting Agent
```

Specialist agents should not directly mutate source data. They should call approved backend actions or return recommendations.

## Action Risk Levels

| Level | Description | Examples | Confirmation |
| --- | --- | --- | --- |
| 0 | Read-only | summaries, reports, lookups | no |
| 1 | Draft only | prepare message, draft quote, draft task | maybe |
| 2 | Low-risk write | create internal reminder | yes |
| 3 | Operational write | mark weaned, record treatment, record weight | yes, with preview |
| 4 | External/customer action | send quote, message customer, public post | explicit approval |
| 5 | Physical/high-risk action | irrigation control, gate/device control, financial transfer | explicit approval plus policy |

MVP should stay at level 0 and selected level 1.

## Memory Model

Oom Sakkie needs memory, but memory must be structured.

Use:

- user profile/preferences
- session summary
- recent conversation trace
- backend event log
- explicit task/reminder records

Do not use:

- raw chat history as truth
- Slack/Telegram messages as agent state
- hidden memory for operational decisions

Trace correction policy:

- Oom Sakkie traces and feedback are append-only audit records.
- Corrections must be represented by new rows or new feedback entries, not by editing or deleting the original trace.
- If a trace captures an embarrassing mistranscription, accidental private data, or a later-corrected answer, the normal correction path is a superseding record/feedback note that explains the correction.
- Any future legal/privacy deletion process must be designed explicitly; do not quietly weaken the append-only trigger model in application code.

## PRD Requirements

### Functional Requirements

1. User can ask Oom Sakkie a farm question.
2. Oom Sakkie can route to approved read-only tools.
3. Oom Sakkie gives concise, useful answers.
4. Oom Sakkie links to the relevant app page when a screen is better than speech.
5. Oom Sakkie asks for confirmation before any write.
6. Every write action must be backend-owned and auditable.
7. Oom Sakkie can decline or defer unsafe/unclear actions.
8. Oom Sakkie can hand off to specialist agents or deterministic backend workers.
9. Oom Sakkie can operate across Telegram, web, and future voice channels.
10. Oom Sakkie can support English first, and later Afrikaans/farm-specific phrasing if desired.

### Non-Functional Requirements

- Fast enough for conversation.
- Reliable enough for farm operations.
- Clear when data is stale or missing.
- No hidden writes.
- No duplicate active Telegram triggers.
- Works even if one sub-agent fails.
- Logs trace IDs for debugging.
- Can run locally at home for voice capture.
- Does not expose secrets in chat or logs.

## First MVP

The first useful MVP should be:

```text
Telegram/web text -> Oom Sakkie orchestrator -> backend tools -> answer
```

Initial commands:

- "What needs attention today?"
- "What pigs are ready for meat?"
- "What is the weather today?"
- "What is the power like now?"
- "Show me sales this month."
- "Which litters are close to weaning?"
- "Find order ORD-..."

Do not start with:

- always-on wake word
- buying voice hardware before the text/kiosk path works
- public posting
- direct hardware control
- auto-classification writes
- complex multi-agent autonomy

## Voice Technology Direction

There are two broad voice choices:

### Cloud Realtime Voice

Use a low-latency speech-to-speech model and tool calls for natural conversation.

Useful when the priority is natural voice interaction.

### Local/Home Assistant Voice

Use local wake word/microphone/speaker infrastructure, then call Oom Sakkie backend.

Useful when the priority is a physical voice in the house.

Likely final architecture combines both:

```text
Local voice satellite
  |
  v
Voice gateway / Home Assistant
  |
  v
Oom Sakkie backend orchestrator
  |
  v
Tools / Agents / Farm APIs
```

## Hardware Notes

Possible later hardware:

- Home Assistant Voice device or compatible voice satellite.
- ESP32-S3 voice satellite hardware.
- Small mini PC or home server.
- USB conference microphone/speaker for first prototype.
- Existing Windows computer for early testing.
- wall-mounted monitor or existing PC screen in the house/farm office.

Do not buy hardware until OS-1 to OS-3 are working.

For the user-stated farm setup, the practical order is:

1. Use the existing PC and screen.
2. Build `/oom-sakkie` kiosk UI.
3. Add text input and response display.
4. Add push-to-talk on that page.
5. Add text-to-speech output.
6. Add wake word only after the room/microphone setup is proven.

## Safety And Approval Rules

Before enabling real writes:

- every tool must declare risk level
- every write must have preview text
- every write must log actor/channel/time
- every external message must be previewed
- every high-risk action must require explicit confirmation
- every automation must have dry-run mode
- every physical device action must have a manual override

## Build Roles

Recommended ownership:

| Work | Best builder/reviewer |
| --- | --- |
| Backend orchestrator/API/tool contracts | Codex |
| Web app text/voice UI | Codex |
| n8n Telegram/GateKeeper integration | Codex with careful workflow testing |
| Architecture review | Claude review |
| PRD/business rules | Owner + Codex |
| Voice hardware/local setup | Owner + Codex plan; manual home setup likely needed |
| Safety review before writes | Claude review + tests |

## Claude Review Prompt

Use this prompt when ready for a second architecture pass:

```text
You are reviewing the Amadeus Farm Operations Platform plan for a live voice operating agent called Oom Sakkie.

Primary goal:
Build a Jarvis-like farm assistant that the owner can talk to from Telegram, the web app, and eventually a local voice device in the house.

Critical constraints:
- Backend/database/read models must remain source of truth.
- Oom Sakkie may orchestrate tools but must not directly write to Google Sheets, Supabase, or hardware.
- Specialist agents must use approved backend APIs.
- Start read-only, then guarded actions, then limited automation.
- Telegram/Oom Sakkie already exists through n8n GateKeeper and must not be broken.
- Avoid duplicate Telegram triggers.
- No public posting, customer messaging, operational writes, or hardware control without explicit approval and audit logging.

Please review:
1. Is the architecture sound?
2. What should be MVP, and what should be deferred?
3. What are the biggest safety risks?
4. What tool contracts are missing?
5. What should the first local-home voice setup be?
6. Should Home Assistant be used as the first physical voice layer, or should the team build a custom local voice gateway?
7. What would you change before implementation?

Return:
- executive recommendation
- architecture risks
- revised implementation sequence
- first 5 backend tools to expose
- first 5 commands to test
- explicit no-go items
```

Prompt library:

- `docs/01-architecture/OOM_SAKKIE_AGENT_PROMPT_LIBRARY.md`

Use the prompt library for the Oom Sakkie master prompt, kiosk prompt, tool-selection prompt, and specialist farm-agent prompts.

## Open Questions

1. Should the first trace store be Supabase `oom_sakkie_traces`, or should a temporary sheet tab be used if the Supabase migration is too much for the first slice? Current recommendation: Supabase.
2. What LAN/device access guard should protect the kiosk MVP before it is trusted? Options: local-only during development, LAN/IP allowlist, or device cookie.
3. Should the public/final name remain `Oom Sakkie`, or should the house voice have another name?
4. Should the assistant speak English only first, or English and Afrikaans? Current recommendation: English first.
5. Should the first voice test be Telegram voice notes, web push-to-talk, or a local speaker/mic? Current recommendation: web push-to-talk after text kiosk is stable.
6. Is the home computer always on and reliable enough, or should a mini PC be used?
7. Should Home Assistant be introduced now, or only after the backend orchestrator works? Current recommendation: later.
8. What actions should Oom Sakkie be allowed to perform first, if any? Current recommendation: no writes in MVP.
9. Who besides Charl may talk to Oom Sakkie?
10. Should household/farm voice access require a spoken PIN for sensitive actions?

## Recommended Immediate Next Step

Build **Phase 10.6A / OS-1 + OS-4 foundation: Oom Sakkie Kiosk MVP - read-only text**.

First endpoint:

```text
POST /api/oom-sakkie/message
```

First page:

```text
GET /oom-sakkie
```

First behavior:

- receive text
- identify intent
- if low confidence, return `needs_clarification = true`
- call exactly one approved read-only backend tool
- return answer, tool used, trace id, and relevant link
- surface stale-data warnings
- write append-only trace
- no writes
- no voice hardware yet

First tools:

- `farm_attention_summary`
- `power_current`
- `weather_today`

Implementation must not change live Telegram routing yet. Telegram can move to the backend endpoint later once the kiosk path is proven.

This creates the brain and the visible in-house interface before adding the microphone.

## Source Links To Recheck Before Implementation

- OpenAI Realtime / voice models: https://developers.openai.com/api/docs/models/gpt-realtime
- OpenAI tools/function calling: https://developers.openai.com/api/docs/guides/tools
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- Home Assistant voice assistants: https://www.home-assistant.io/voice_control/
- ESPHome voice assistant: https://esphome.io/components/voice_assistant.html
- Trillion inspiration site: https://hellotrillion.ai/
