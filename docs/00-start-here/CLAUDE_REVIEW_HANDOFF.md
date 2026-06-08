# Claude Review Handoff

## How Charl Should Use This

In Claude Code, say exactly:

```text
Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.
```

Claude should not need any extra pasted prompt. The current review scope, files, questions, commands, and output format are all listed below.

## Instructions For Claude

You are working in the **Amadeus Pig Tracking & Sales** repo.

If the user asks you to read this file and review, do this:

1. Read `CLAUDE.md` first.
2. Read the **Current Review Packet** below.
3. Inspect the files listed in **Files/folders to inspect**.
4. Run or recommend the verification commands listed in **Known verification from Codex** as appropriate for your environment.
5. Answer every item in **Design checks**.
6. Use the exact **Deliverable format**.
7. Treat the **Archive / reusable templates** section as background only. Do not review old archived examples unless the user explicitly asks.

## Current Review Packet - Oom Sakkie Local Kiosk And Specialist Roster

## Authority and scope

- **Build order:** `docs/00-start-here/NEXT_STEPS.md`
- **Explicit scope:** Phase 10.6 Oom Sakkie local kiosk/backend-as-brain work through `10.6Z`, plus Phase 10.7A-Z, 10.8A-P, and 10.9A-H specialist manifest, advisory trace-review, access caveat hardening, kiosk review-advisor panel, advisor wording/proxy-test tightening, advisor trace-read consolidation, advisor SQL/test hardening, kiosk advisor-window/voice-loop counter polish, trace-driven router/power-answer tightening, capability-fallback precedence fix, bounded LLM fallback router, LLM fallback privacy/failure-mode hardening, LLM smoke harness, verified local LLM smoke, env-gated LLM answer composer, Usejarvis external-reference review, kiosk alive-state/provenance strip, stronger spoken answer voice, animated presence orb, capped context briefing composer, read-only operating brief tool, operating brief required-section fix, top voice controls, human-approved Learning Queue, explicit LLM Learning Analyst, trace-driven composer lane guard, deterministic Learning Build Brief packet, human-approved Implementation Queue, Approve For Build gate, persistent build request queue, build request event log, Forge Handoff packet, Forge Handoff persisted-ID hardening, Patch Proposal Gate, Patch Gate review nits, Deploy Approval Gate, Workbench simplification, Forge prompt copy button, read-only system work status tool, Workbench pipeline clarity, deploy-ready instructions, read-only Business Advisor seed, Workbench Next Action card, Business quick action, Work Status honesty fix, Business Advisor context upgrade, role-specific spoken composer rules, internal-only Business Offer Outline, Agent Runtime Foundation, Agent Crew Status Tool, Agent Activity Stage, Agent Handoff Lane, Agent Crew Brief, Visible Crew Sequence, Agent Activation Plan, and Sentinel Dry-Run Review.

Out of scope unless explicitly asked:

- Telegram cutover
- write tools
- physical controls
- backend STT/TTS vendors
- always-on mic
- wake word
- live LLM delegation to specialists
- Agent Factory
- public posting/customer messaging

## Goal

Review the current Oom Sakkie local-only read path and planning scaffolding before daily kiosk use continues:

- Local `/oom-sakkie` kiosk
- Backend-owned `/api/oom-sakkie/message`
- Typed read-only tool registry
- Trace/review/feedback flow
- Browser-only speech controls
- Safety policy and review packet
- Loopback-only review endpoint guard
- DB append-only trace guards
- Planned-only specialist manifest roster
- Advisory-only trace review advisor
- Message/review access policy split and reverse-proxy caveat
- User-action-triggered kiosk Review Advisor panel
- Combined advisor trace reader
- Advisor trace time-window and SQL/test hardening
- Visible Review Advisor time window and Continue Conversation turn counter
- Trace-driven routing aliases, capability answer, control-phrase guard, and richer current-power answer
- Capability/help fallback precedence so domain-specific help prompts route to the right read-only tool
- Env-gated bounded LLM fallback router that can only select approved read-only tools or ask for clarification
- LLM fallback privacy visibility plus env-gate/network/parse/low-confidence tests
- LLM router smoke scripts and verified local smoke with `gpt-5.4-mini`
- Env-gated LLM answer composer that rewrites only the final answer after read-only tool execution
- Usejarvis external-reference review: ideas logged, source ignored, nothing installed or run
- Kiosk answer pipeline/provenance strip and stateful status display
- Kiosk animated presence orb and stronger answer-composer voice
- Capped structured read-only tool context sent to the answer composer when enabled
- `farm_operating_brief` composite read-only tool and kiosk `Brief` quick action
- Required operating-brief sections: attention/priority, power, weather, irrigation
- Top `Talk` / `Talk & Ask` placement inside the presence panel
- Human-approved Learning Queue from reviewed trace feedback
- Explicit `Analyze` action for env-gated LLM Learning Analyst
- Trace-driven composer lane guard for single-tool answers
- `Build Brief` action for proposal-specific review packets
- Auto-prepared Implementation Queue for strong learning signals
- `Approve for Build` gate that creates a non-applying build request object
- Persistent append-only approved build request queue
- Append-only build request event log for ignore/review-note corrections
- Forge Handoff packet for future Builder/Forge execution review
- Forge Handoff now looks up persisted build requests by ID before generating packets
- Patch Proposal Gate for recording Builder/Forge proposals and owner review decisions before any manual patch application
- Patch Gate review-nit cleanup: current Forge Handoff test payload, frontend advisor-window assertion, and clean patch-proposal event `404` for missing proposal IDs
- Deploy Approval Gate for append-only manual-deploy decisions after an approved patch proposal
- Kiosk `System Workbench` simplification so trace/build/patch/deploy controls are not first-screen clutter
- `Copy Forge Prompt` button for explicit owner-triggered clipboard copy
- Read-only `system_work_status` tool and `Approvals` quick action so Oom Sakkie can answer what needs owner approval
- Workbench pipeline grouping so active build/patch/deploy items move between clear buckets instead of staying in one flat list
- Deploy-ready instruction card that explains the manual patch/verification/deploy-decision step
- Read-only `business_growth_brief` Business Advisor seed across sales stock and meat pipeline
- Workbench `Next action` card and stronger section/card visual separation
- `Business` quick action for `What should we sell next?`
- Work-status stale warning/degraded status when build/patch/deploy stores are unavailable
- Richer read-only Business Advisor context: marketable stock, young/not-ready stock, ready meat candidates, and owner follow-up question
- Role-specific answer-composer rules for Business Advisor and work-status answers
- Internal-only Business Offer Outline from read-only sales/meat-planning context
- Agent Runtime Foundation for planned specialist personalities, tool allowlists, routing hints, and recommendation-only dispatch
- `agent_crew_status` read-only tool and `Agents` quick action for recommendation-only crew questions
- Agent Activity Stage that visually opens the current planned specialist workspace and changes color by selected agent without enabling live dispatch
- Agent Handoff Lane that shows controller -> specialist workspace -> read-only tool -> owner gate for each successful tool answer
- Agent Crew Brief that returns a plan-only multi-specialist sequence for broad requests without dispatching agents
- Visible Crew Sequence that renders crew-plan specialists as cards on the Agent Activity Stage
- Agent Activation Plan that exposes the locked path from planned agents to future live agents without enabling runtime flags
- Sentinel Dry-Run Review that rehearses the first specialist candidate as an advisory-only safety/readiness review without enabling dispatch, specialist LLM execution, specialist tool execution, autonomous loops, or writes

## Files/folders to inspect

- `modules/oom_sakkie/`
- `modules/oom_sakkie/learning_advisor.py`
- `modules/oom_sakkie/learning_llm.py`
- `modules/oom_sakkie/learning_packet.py`
- `modules/oom_sakkie/forge_handoff.py`
- `modules/oom_sakkie/agent_runtime.py`
- `modules/oom_sakkie/patch_proposal_store.py`
- `modules/oom_sakkie/deploy_decision_store.py`
- `templates/oom-sakkie.html`
- `static/js/oomSakkie.js`
- `static/css/main.css`
- `tests/test_oom_sakkie_service.py`
- `tests/test_oom_sakkie_routes.py`
- `tests/test_frontend_route_contracts.py`
- `scripts/oom_sakkie_llm_router_diagnostic.py`
- `scripts/oom_sakkie_llm_router_smoke.py`
- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`
- `docs/01-architecture/JARVIS_EXTERNAL_REFERENCE_REVIEW.md`
- `screenshots/Jarvis screen layout.mp4` (owner-provided visual reference; if local video tooling is unavailable, use the documented design intent in `NEXT_STEPS.md`)
- `supabase/migrations/202606060001_create_oom_sakkie_traces.sql`
- `supabase/migrations/202606060002_create_oom_sakkie_trace_feedback.sql`
- `supabase/migrations/202606060003_add_oom_sakkie_safety_notes.sql`
- `supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql`
- `supabase/migrations/202606070001_create_oom_sakkie_build_requests.sql`
- `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`
- `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`
- `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`
- `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`
- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`

## What changed

Summary:

- Flask/backend is confirmed as the long-term Oom Sakkie brain.
- n8n/GateKeeper remains Telegram I/O and scheduled workflow; Telegram is not cut over.
- Added local `/oom-sakkie` kiosk and `/api/oom-sakkie/message`.
- Added read-only Oom Sakkie tool registry and deterministic routing.
- Added trace storage, feedback, review summary, filters, search, detail expanders, and review packet.
- Added browser-only speech draft/TTS/continue-conversation controls with stop/cap guards.
- Added quick checks and expanded read-only telemetry/status tools.
- Added safety notes split from stale warnings.
- Added runtime policy, tool catalog, local-access review guard, append-only DB triggers.
- Added planned-only specialist manifests and `/api/oom-sakkie/specialists`.
- Added advisory-only `/api/oom-sakkie/review-advisor`; it prepares a queue and suggestions but does not mark feedback or run autonomously.
- Added explicit `message_endpoint_access` policy and reverse-proxy caveat for review endpoint IP checks.
- Added a user-action-triggered kiosk Review Advisor panel that renders the advisor queue/suggestions without timer polling or marking anything.
- Updated advisor wording from `manual refresh only` to `user-action-triggered, no auto-polling`, matching the implementation.
- Added the inverse forwarded-header test: public `REMOTE_ADDR` plus loopback `X-Forwarded-For` still denies review access.
- Added `list_review_advisor_traces()` so the advisor reads issue traces and unreviewed traces in one combined ranked trace query instead of two separate trace-list reads.
- Added `days` windowing to `list_review_advisor_traces()` so advisor trace reads default to the same 14-day window as the review summary.
- Added `_trace_row` positional mapping coverage and replaced the advisor SQL compiled-constant test with a mocked `psycopg.connect` SQL-capture test.
- Added a visible `last 14 days` label to the kiosk Review Advisor guard line.
- Added a `Voice loop 0 of 5` counter that appears only when Continue Conversation is enabled and updates during continued spoken turns.
- Added trace-driven deterministic aliases from owner test traces:
  - slaughter wording -> `meat_planning`
  - sales issue wording -> `sales_dashboard`
  - water/pump wording -> read-only `irrigation_status`
  - worry/anything-today wording -> `farm_attention_summary`
  - broad animal/pig-on-farm wording -> `dashboard_summary`
- Added a read-only `what can you do` capabilities answer that states current checks and blocked actions.
- Hardened dynamic control phrase detection for separated wording such as `turn the pump on`.
- Enriched `power_current` wording with battery state, grid watts/state, and data age from the existing power backend response.
- Moved capability/help handling after deterministic tool classification and unsupported-action blocking.
- Added domain-specific help routing coverage:
  - `help me with the weather` -> `weather_today`
  - `I need help with the power` -> `power_current`
  - `can you help me check irrigation` -> `irrigation_status`
  - `help me understand sales` -> `sales_dashboard`
- Kept bare `what can you do` on the capability answer path.
- Added `modules/oom_sakkie/llm_router.py`.
- LLM fallback is off by default and requires `OOM_SAKKIE_LLM_ROUTER_ENABLED`, `OPENAI_API_KEY`, and `OOM_SAKKIE_LLM_ROUTER_MODEL`.
- LLM fallback runs only after deterministic rules, unsupported-action blocking, and capability/help fallback have declined.
- LLM output is JSON-validated and may only select existing read-only registry tools or ask for clarification.
- Unknown/write tool names are rejected.
- `/api/oom-sakkie/policy` exposes `llm_router` status and `can_write = false`.
- `/api/oom-sakkie/policy` and the kiosk Safety Status now expose the outbound endpoint and whether user text would be sent when the LLM router is enabled.
- Added tests for env-gating without network calls, network failure, invalid JSON, and low-confidence LLM tool selection.
- Added `scripts/oom_sakkie_llm_router_diagnostic.py` for a minimal OpenAI-compatible API check that reports URL/model/key presence/status without printing the key.
- Added `scripts/oom_sakkie_llm_router_smoke.py` for a full Oom Sakkie `handle_message()` smoke using channel `kiosk_llm_smoke`.
- Verified the owner-provided router env locally:
  - `OOM_SAKKIE_LLM_ROUTER_ENABLED=true`
  - `OOM_SAKKIE_LLM_ROUTER_MODEL=gpt-5.4-mini`
  - direct diagnostic returned HTTP 200 and resolved to `gpt-5.4-mini-2026-03-17`
- Verified smoke prompts:
  - `give me the energy situation` -> `power_current`
  - `check if the outside conditions are a problem` -> `weather_now`
  - `which farm area should I inspect first` -> `farm_attention_summary`
  - `delete a pig record` -> action-blocked, no tool
  - `what can you do` -> local capability answer, no tool
- Added `modules/oom_sakkie/llm_answer.py` behind independent env gate `OOM_SAKKIE_LLM_ANSWER_ENABLED`.
- The answer composer runs only after a read-only tool returns a deterministic answer; it cannot choose tools, call tools, write records, send messages, or perform controls.
- Runtime policy and kiosk Safety Status expose composer enabled/configured/can-write state and whether user text/tool summary are sent outbound when enabled.
- Invalid composer output or output claiming actions such as saved/sent/started/stopped is rejected; deterministic wording is used instead.
- Smoke with `OOM_SAKKIE_LLM_ANSWER_ENABLED=true` showed visible wording improvement while preserving safety:
  - power/weather answers were smoother while preserving facts,
  - farm-attention answer changed from a raw list into `Start with litter attention...`,
  - unsafe delete request and local capability answer remained off the composer path.
- Inspected Usejarvis source under `external_sources/jarvis-main/jarvis-main` read-only. Documented hard no items and useful ideas at `docs/01-architecture/JARVIS_EXTERNAL_REFERENCE_REVIEW.md`; added `external_sources/jarvis-main/` to `.gitignore` so the third-party source tree is not committed.
- Added `pipeline` metadata to `/api/oom-sakkie/message` responses: route source, answer source, state, LLM-router-used flag, LLM-answer-used flag, and tool-checked flag.
- Added a visible `/oom-sakkie` pipeline strip showing Route / Answer / State, plus Trace confidence and reason.
- Made the top status pill visually stateful for listening, checking, speaking, answered, blocked, and error.
- Strengthened `modules/oom_sakkie/llm_answer.py` so the answer composer:
  - identifies as Oom Sakkie, the farm operating co-pilot,
  - avoids generic assistant/table-reader wording,
  - leads with operational meaning before facts,
  - preserves the hard fact boundary to backend answer, stale warnings, and safety notes,
  - still rejects output claiming actions such as saved/sent/started/stopped/changed,
  - uses temperature `0.55` instead of `0.2` for less flat wording.
- Added a central `/oom-sakkie` agent presence panel:
  - `oom_presence_orb`,
  - ring/core/scan layers,
  - `oom_presence_line`,
  - state-specific behavior for idle, listening, checking, answered, speaking, blocked, and error.
- Wired the presence orb to the existing status state machine; it does not open the mic, call tools, or run independently.
- Added frontend contract tests for the presence markup, JS state wiring, and CSS animation hooks.
- Added a backend prompt contract test so the answer composer does not drift back to generic/read-the-table wording.
- Added capped context briefing composer behavior:
  - `compose_answer_with_llm()` accepts `raw_context`,
  - `handle_message()` passes `tool_result["raw"]` or the tool result after read-only tool execution,
  - `_safe_json_excerpt()` serializes context with `default=str`, ASCII-safe JSON, and a 3000-character cap,
  - prompt tells the composer to prioritize what the owner should inspect first when multiple items exist,
  - prompt tells the composer not to recite every ID unless useful for inspection,
  - runtime policy and kiosk Safety Status disclose `sends_capped_tool_context_when_enabled`.
- Added `farm_operating_brief`:
  - read-only registry tool,
  - calls existing read-only wrappers for farm attention, current power, today's weather, and irrigation status,
  - combines summaries, links, stale warnings, safety notes, and raw per-section context,
  - deterministic routing for brief/status-report/bring-me-up-to-speed prompts,
  - LLM-router guidance for broad briefing prompts,
  - kiosk `Brief` quick action,
  - answer-composer rule to keep operating briefs to at most three short spoken sentences.
- Added operating brief required-section hardening:
  - `farm_operating_brief` returns compact `llm_context` with `required_sections = ["attention", "power", "weather", "irrigation"]`,
  - compact context includes per-section status, summary, stale warnings, and safety notes,
  - `handle_message()` prefers `tool_result["llm_context"]` over verbose raw payload for the composer,
  - answer-composer prompt explicitly requires attention/priority, power, weather, and irrigation for `farm_operating_brief`,
  - unsafe-output filter still rejects positive action claims but allows negated safety statements such as `No start or stop command was sent`.
- Moved kiosk voice controls:
  - `Talk` and `Talk & Ask` now live inside the top `oom-presence-panel`,
  - bottom `oom_form` keeps text input and `Ask`,
  - `.oom-presence-actions` provides touch-friendly first-viewport controls,
  - frontend contract asserts the voice buttons stay in the presence panel and not the bottom form.
- Added human-approved Learning Queue:
  - `modules/oom_sakkie/learning_advisor.py`,
  - protected `GET /api/oom-sakkie/learning-advisor`,
  - kiosk `Learning Queue` panel,
  - deterministic proposals from reviewed issue feedback,
  - no LLM call,
  - no code write,
  - no feedback write,
  - no prompt/tool/farm-data mutation,
  - human approval required for follow-up implementation.
- Added explicit LLM Learning Analyst:
  - `modules/oom_sakkie/learning_llm.py`,
  - env gate `OOM_SAKKIE_LLM_LEARNING_ENABLED`,
  - protected `POST /api/oom-sakkie/learning-advisor/analyze`,
  - kiosk `Analyze` button,
  - sends capped reviewed issue trace excerpts and deterministic proposals only when explicitly triggered,
  - validates allowed proposal kinds,
  - forces `approval_required = true`,
  - does not write code, feedback, prompts, tools, routes, or farm data.
- Added deterministic Learning Build Brief packet:
  - `modules/oom_sakkie/learning_packet.py`,
  - protected `POST /api/oom-sakkie/learning-advisor/build-packet`,
  - `Build Brief` buttons on Learning Queue proposals,
  - text-only kiosk packet render target,
  - no LLM call,
  - no code write or patch application,
  - no feedback write,
  - no prompt/tool/farm-data mutation,
  - human approval required before implementation.
- Added human-approved Implementation Queue:
  - protected `GET /api/oom-sakkie/learning-advisor/implementation-queue`,
  - kiosk `Implementation Queue` panel,
  - deterministic auto-preparation from strong Learning Queue signals,
  - threshold: high priority, repeated tool pattern, or evidence with two or more issue traces,
  - `Open Brief` displays an in-memory packet in the text-only build-brief panel,
  - no LLM call,
  - no code write or patch application,
  - no feedback write,
  - no prompt/tool/farm-data mutation,
  - human approval required before implementation.
- Added Approve For Build gate:
  - protected `POST /api/oom-sakkie/learning-advisor/approve-build`,
  - `Approve for Build` button on generated build briefs,
  - returns a structured `build_request_only` object,
  - `builder_enabled = false`,
  - `writes_code_now = false`,
  - `applies_changes_now = false`,
  - next gate is `builder_agent_review_and_patch_approval`,
  - no builder run, file edit, patch application, deploy, prompt/tool mutation, feedback write, or farm-data write.
- Added persistent build request queue:
  - `modules/oom_sakkie/build_request_store.py`,
  - migration `supabase/migrations/202606070001_create_oom_sakkie_build_requests.sql`,
  - protected `GET /api/oom-sakkie/build-requests`,
  - kiosk `Approved Build Requests` panel,
  - `approve-build` attempts to persist approved build requests,
  - table is append-only with update/delete blockers,
  - DB constraints keep `builder_enabled`, `writes_code_now`, and `applies_changes_now` false.
- Added build request event log:
  - migration `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`,
  - `record_build_request_event()` in `modules/oom_sakkie/build_request_store.py`,
  - protected `POST /api/oom-sakkie/build-requests/<build_request_id>/events`,
  - build request list returns latest event,
  - kiosk `Ignore` action records an append-only `ignored` event,
  - allowed event types are `approved`, `ignored`, and `review_note`.
- Added Forge Handoff packet:
  - `modules/oom_sakkie/forge_handoff.py`,
  - protected `POST /api/oom-sakkie/build-requests/forge-handoff`,
  - kiosk `Forge Handoff` button and text-only panel,
  - returns objective, evidence, approved scope, verification, no-go rules, original brief, and required pre-patch output,
  - `runs_builder = false`,
  - `writes_code = false`,
  - `applies_changes = false`,
  - `deploys = false`,
  - requires owner to explicitly run Builder/Forge later,
  - requires separate patch review and deploy approval.
- Added Forge Handoff persisted-ID hardening:
  - `get_build_request()` in `modules/oom_sakkie/build_request_store.py`,
  - Forge Handoff route now accepts `build_request_id` only,
  - route loads the persisted build request before generating the packet,
  - kiosk sends only `build_request_id`,
  - closes Claude's L-3 synthetic payload finding.
- Added Patch Proposal Gate:
  - `modules/oom_sakkie/patch_proposal_store.py`,
  - migration `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`,
  - protected `POST /api/oom-sakkie/build-requests/<build_request_id>/patch-proposals`,
  - protected `GET /api/oom-sakkie/patch-proposals`,
  - protected `POST /api/oom-sakkie/patch-proposals/<patch_proposal_id>/events`,
  - kiosk `Patch Proposal Gate` panel under Approved Build Requests,
  - `Record Patch Proposal` action on build request rows,
  - append-only patch proposal rows,
  - append-only patch proposal review events,
  - event types `approved_for_patch`, `rejected`, and `review_note`,
  - DB and application constraints keep `applies_patch = false` and `deploys = false`,
  - `Approve Patch` records approval for manual patch application outside the kiosk; it does not apply a patch.
- Added Patch Gate review-nit cleanup:
  - `get_patch_proposal()` in `modules/oom_sakkie/patch_proposal_store.py`,
  - patch proposal event writes now return `404 patch_proposal_not_found` before insert when the target proposal is missing,
  - Forge Handoff non-local-access test now uses the current `build_request_id` payload,
  - frontend route contract pins the Review Advisor `last ${data.days || 14} days` guard string.
- Added Deploy Approval Gate:
  - `modules/oom_sakkie/deploy_decision_store.py`,
  - migration `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`,
  - protected `POST /api/oom-sakkie/patch-proposals/<patch_proposal_id>/deploy-decisions`,
  - protected `GET /api/oom-sakkie/deploy-decisions`,
  - kiosk `Deploy Approval Gate` panel,
  - append-only deploy decision rows,
  - decision types `approved_for_manual_deploy`, `rejected`, `deferred`, and `review_note`,
  - DB and application constraints keep `runs_deploy = false` and `deploys_now = false`,
  - `approved_for_manual_deploy` requires the target patch proposal's latest event to be `approved_for_patch`,
  - this records deploy approval only; no deploy is run by the kiosk/backend.
- Added Workbench simplification and work-status tool:
  - `templates/oom-sakkie.html` wraps the heavy review/build/patch/deploy controls in a collapsed `System Workbench`,
  - `static/css/main.css` styles the workbench summary/content without changing backend behavior,
  - `static/js/oomSakkie.js` adds explicit-click `Copy Forge Prompt` clipboard support,
  - `templates/oom-sakkie.html` adds `Approvals` quick action,
  - `modules/oom_sakkie/tools.py` adds read-only `system_work_status`,
  - `modules/oom_sakkie/service.py` routes approval/build/patch/deploy status wording to `system_work_status`,
  - the tool summarizes approved build requests, patch proposals, and deploy decisions from existing stores,
  - this is status-only and does not run Builder/Forge, edit files, apply patches, deploy, or mutate prompts/tools/farm data.
- Added Workbench pipeline clarity:
  - Approved Build Requests split into `Needs Forge Handoff / Builder Plan` and `Already Moved Or Closed`,
  - Patch Proposal Gate splits into `Needs Patch Review`, `Approved - Ready For Deploy Decision`, and `Rejected / Closed`,
  - patch-proposal recording now adds append-only build-request `review_note` so the source build request moves out of the active bucket,
  - patch/deploy actions refresh adjacent queues so items do not look stuck in the prior step,
  - added `Use This Build Request In Patch Gate` next to Forge Handoff,
  - added work-stage badges/action grouping in CSS,
  - still no Builder/Forge execution, file edit, patch application, deploy, prompt/tool mutation, or farm-data mutation.
- Added deploy-ready instructions and Business Advisor seed:
  - approved patch rows show `What this needs now`,
  - deploy verification placeholder asks for the actual verification result,
  - `system_work_status` counts only active handoff work and patch proposals still waiting for deploy decision,
  - `business_growth_brief` combines read-only `sales_dashboard` and `meat_planning`,
  - broad commercial prompts route to `business_growth_brief`,
  - tool returns read-only commercial focus and counts in `llm_context`,
  - it does not draft, post, message, sell, reserve, mutate stock, run Builder/Forge, apply patches, or deploy.
- Added Workbench Next Action and visual separation:
  - `System Workbench` now starts with a `Next action` card,
  - card shows build/patch/deploy counts and recommends the next item to handle,
  - section headings and work records have stronger visual separation,
  - added `Business` quick action for `What should we sell next?`,
  - guidance only; no Builder/Forge execution, patch application, deploy, prompt/tool mutation, or farm-data mutation.
- Added Work Status honesty fix:
  - `system_work_status` now adds stale warnings for unavailable build/patch/deploy stores,
  - returns `not_configured` or `degraded` instead of a confident empty queue when stores fail,
  - still reports best-effort counts from readable stores,
  - `record_deploy_decision()` checks local `psycopg` availability before loading a patch proposal,
  - no behavior widens beyond read-only/status-only reporting.
- Added Business Advisor context upgrade:
  - separates total listed stock from marketable stock and young/not-ready stock,
  - excludes `Not For Sale` and `Out of Stock` rows from marketable stock,
  - includes ready meat candidates by pig/tag/pen/weight/action,
  - includes owner follow-up question for the next approved business step,
  - live read-only smoke showed 21 marketable pigs, 34 young/not-ready pigs, and ready D1 candidates tag 2/tag 3,
  - still does not draft, post, message, sell, reserve, invoice, mutate stock, run Builder/Forge, apply patches, or deploy.
- Added internal-only Business Offer Outline:
  - `business_growth_brief` now returns `llm_context.offer_brief_outline`,
  - the outline is `mode = internal_outline_only`,
  - it may name the opportunity, target buyer type, stock basis, evidence, approval-needed next step, and no-action list,
  - it explicitly does not draft customer copy, draft public posts, create quotes, sell, reserve stock, or mutate farm data,
  - deterministic routing maps `offer brief`, `commercial brief`, and `prepare ... offer` to the same read-only Business Advisor tool,
  - kiosk quick checks include `Offer Brief` with prompt `Prepare an internal offer brief.`,
  - answer-composer prompt says any summary must stay internal-only and not customer-facing copy.
- Added Agent Runtime Foundation:
  - `modules/oom_sakkie/agent_runtime.py`,
  - `AgentRuntimeManifest` wraps planned specialist manifests with personality, memory sources, allowed tools, risk limit, output contract, approval rules, and routing hints,
  - `GET /api/oom-sakkie/agents` returns `mode = advisory_runtime_foundation`,
  - `runtime_enabled = false`, `dispatch_enabled = false`, `autonomous_loops_enabled = false`, and `writes_enabled = false`,
  - `POST /api/oom-sakkie/agents/recommend` returns only which planned agent would handle the text and why,
  - recommendation output has `mode = dispatch_recommendation_only`, `runs_agent = false`, and `writes = false`,
  - review packet includes `agent_runtime`,
  - kiosk `Agent Crew Foundation` panel renders personalities, roles, allowed tools, and an explicit off/off/off runtime guard.
- Added Agent Crew Status Tool:
  - `agent_crew_status` is in the read-only tool registry,
  - deterministic routing catches agent/crew/specialist questions,
  - `handle_message()` passes bounded `user_text` into tool handlers as context,
  - `agent_crew_status` uses the recommendation-only runtime helper to choose a planned agent,
  - output states no specialist was dispatched, no specialist tool ran, and no write was performed,
  - kiosk quick checks include `Agents` with prompt `Which agent should handle this?`.
- Added Agent Activity Stage:
  - owner-provided visual reference retained at `screenshots/Jarvis screen layout.mp4`,
  - target design intent is Oom Sakkie as controller with specialist workspaces opening visibly and colors changing by active agent,
  - `build_agent_activity()` maps successful read-only tool results to a visual-only active planned agent/workspace payload,
  - `/api/oom-sakkie/message` includes `agent_activity` on successful tool responses,
  - payload safety flags remain `runs_agent = false`, `dispatch_enabled = false`, `autonomous_loops_enabled = false`, and `writes = false`,
  - kiosk adds first-viewport `Agent Activity Stage` with controller state, active specialist name/personality, workspace title/detail, and guard text,
  - presence orb and workspace border color shift by active specialist,
  - CSS stacks the controller/workspace cleanly on narrow screens,
  - this is visual coordination only: no live specialist dispatch, no specialist LLM call, no autonomous loop, and no new authority.
- Added Agent Handoff Lane:
  - `agent_activity.handoff_lane` returns controller, specialist workspace, read-only tool, and owner gate steps,
  - the lane explicitly says no write, post, sale, control, patch, or deploy can run here,
  - kiosk renders the lane as process cards under the active specialist workspace,
  - dynamic lane content is rendered with DOM nodes and `.textContent`,
  - responsive CSS stacks lane cards on narrow screens,
  - this is visual process explanation only and does not dispatch specialists or grant any action authority.
- Added Agent Crew Brief:
  - `build_agent_crew_brief(text)` selects a plan-only crew scenario from broad owner text,
  - scenarios include commercial growth, farm operations, pig pipeline, system build, weather/irrigation, and general fallback,
  - added read-only `agent_crew_brief`,
  - deterministic routing catches crew/team/multi-agent plan phrasing,
  - kiosk quick checks include `Team Brief`,
  - output is `mode = crew_plan_only`,
  - every planned sequence item has `runs_agent = false` and `writes = false`,
  - no specialist dispatch, specialist LLM call, specialist tool execution, autonomous loop, or write authority was added.
- Added Visible Crew Sequence:
  - `agent_activity.crew_sequence` is included when `agent_crew_brief` returns a crew plan,
  - sequence is bounded to six planned agents,
  - kiosk renders sequence cards under the Agent Activity Stage,
  - cards show order, name/personality, what the planned specialist would inspect, and `runs no | writes no`,
  - sequence area is hidden for normal single-tool checks,
  - dynamic sequence content is rendered with DOM nodes and `.textContent`,
  - no live dispatch, specialist LLM call, specialist tool execution, autonomous loop, or write authority was added.
- Added Agent Activation Plan:
  - `get_agent_activation_plan()` returns `mode = activation_plan_only`,
  - runtime/dispatch/autonomous-loop/write flags remain false,
  - activation stages are foundation visible, read-only dry-run, human-approved dispatch, draft-only outputs, and controlled writes,
  - recommended next stage is `read_only_dry_run`,
  - recommended first candidate is Sentinel,
  - added read-only `agent_activation_plan`,
  - deterministic routing catches activation/roadmap/live-agent phrasing,
  - kiosk quick checks include `Agent Roadmap`,
  - no specialist dispatch, specialist LLM call, runtime flag enablement, autonomous loop, specialist tool execution, or write authority was added.
- Added Sentinel Dry-Run Review:
  - `build_sentinel_dry_run_review(tool_catalog)` returns `mode = sentinel_dry_run_review_only`,
  - selected agent is Sentinel,
  - runtime/dispatch/autonomous-loop/write/specialist-LLM flags remain false,
  - current tool registry is audited for read-only, non-read-only, and confirmation-required tools,
  - blockers before any live specialist dry-run are listed,
  - added read-only `sentinel_dry_run_review`,
  - deterministic routing catches Sentinel/safety/first-agent/specialist dry-run phrasing,
  - kiosk quick checks include `Sentinel Dry Run`,
  - Agent Activity Stage maps the tool to Sentinel,
  - no specialist dispatch, specialist LLM call, runtime flag enablement, autonomous loop, specialist tool execution, or write authority was added.
- Added role-specific spoken composer rules:
  - `business_growth_brief` answers should lead with the commercial move, name supporting stock/ready pigs, and ask one approval-style follow-up question,
  - `system_work_status` answers should lead with the next owner action before counts,
  - composer remains env-gated and unable to choose/call tools or perform actions.
- Added trace-driven composer lane guard:
  - live feedback showed single-tool answers mentioning unrelated systems,
  - prompt now tells non-brief tools to stay in their own lane,
  - prompt bans filler such as `no stale warning` when there is no warning,
  - post-composer guard rejects off-topic disclaimer fragments for non-brief tools,
  - smart apostrophes are normalized before checking,
  - `farm_operating_brief` is exempt because it intentionally covers multiple systems,
  - rejected composed answers fall back to deterministic wording.

Known verification from Codex:

- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes`
- `node --check static/js/oomSakkie.js`
- `python -m unittest tests.test_frontend_route_contracts`
- `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 74 tests OK
- Full local unittest suite: `399 tests OK`
- `python -c "from scripts.oom_sakkie_llm_router_diagnostic import main; raise SystemExit(main())"` -> HTTP 200, model `gpt-5.4-mini-2026-03-17`, response `{"ok":true}`
- `python -c "from scripts.oom_sakkie_llm_router_smoke import main; raise SystemExit(main())"` -> read-only smart routing smoke passed as listed above
- `OOM_SAKKIE_LLM_ANSWER_ENABLED=true` for a smoke process showed improved final answers while preserving read-only safety
- Full local unittest suite after answer composer: `402 tests OK`
- Full local unittest suite after provenance strip: `402 tests OK`
- `node --check static/js/oomSakkie.js` passed after provenance strip
- Focused service/frontend tests after presence/voice slice: `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 68 tests OK, 1 skipped
- `node --check static/js/oomSakkie.js` passed after presence/voice slice
- Focused service/frontend tests after capped context composer: `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 68 tests OK, 1 skipped
- `node --check static/js/oomSakkie.js` passed after capped context composer
- Local smoke after capped context composer with `OOM_SAKKIE_LLM_ANSWER_ENABLED=true`:
  - `what needs attention today?` -> `answer_source = llm_composer`, prioritizes litter queue,
  - `which farm area should I inspect first?` -> `route_source = llm_router`, `answer_source = llm_composer`, identifies litter area and most urgent litter from structured context,
  - `what is the power doing now?` -> concise LLM-composed power briefing,
  - `what happened with the weather today?` -> LLM-composed weather briefing using structured context.
- Focused service/frontend tests after operating brief tool: `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 69 tests OK, 1 skipped
- `node --check static/js/oomSakkie.js` passed after operating brief tool
- Local smoke after operating brief tool with `OOM_SAKKIE_LLM_ANSWER_ENABLED=true`:
  - `give me the farm operating brief` -> `tool = farm_operating_brief`, `answer_source = llm_composer`,
  - `bring me up to speed` -> `tool = farm_operating_brief`, `answer_source = llm_composer`,
  - `what should i know before i go outside` -> `tool = farm_operating_brief`, `answer_source = llm_composer`.
- Focused service/frontend tests after required-section hardening: `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts` -> 70 tests OK, 1 skipped
- `node --check static/js/oomSakkie.js` passed after required-section hardening
- Direct repeated live diagnostic hit Google Sheets quota `429`; avoid repeated live operating-brief smokes until the quota cools down.
- Top voice control verification pending current full-suite run in this batch.
- Learning Queue focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 83 tests OK
- `node --check static/js/oomSakkie.js` passed after Learning Queue
- LLM Learning Analyst focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 87 tests OK
- `node --check static/js/oomSakkie.js` passed after LLM Learning Analyst
- Composer lane guard focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 88 tests OK
- `node --check static/js/oomSakkie.js` passed after composer lane guard
- Learning Build Brief packet focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 92 tests OK
- `node --check static/js/oomSakkie.js` passed after Learning Build Brief packet
- Full local unittest suite after Learning Build Brief packet: `417 tests OK`
- Implementation Queue focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 95 tests OK
- `node --check static/js/oomSakkie.js` passed after Implementation Queue
- Full local unittest suite after Implementation Queue: `420 tests OK`
- Approve For Build focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 99 tests OK
- `node --check static/js/oomSakkie.js` passed after Approve For Build
- Full local unittest suite after Approve For Build: `424 tests OK`
- Persistent build request queue focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 105 tests OK
- `node --check static/js/oomSakkie.js` passed after persistent build request queue
- Full local unittest suite after persistent build request queue: `430 tests OK`
- Build request event log focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 109 tests OK
- `node --check static/js/oomSakkie.js` passed after build request event log
- Applied migration `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`
- Marked synthetic persistence smoke request `OSK-BUILD-7073A29F701E` as `ignored` through append-only event route
- Full local unittest suite after build request event log: `434 tests OK`
- Forge Handoff focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 113 tests OK
- `node --check static/js/oomSakkie.js` passed after Forge Handoff
- Full local unittest suite after Forge Handoff: `438 tests OK`
- Forge Handoff persisted-ID hardening focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 114 tests OK
- `node --check static/js/oomSakkie.js` passed after persisted-ID hardening
- Full local unittest suite after persisted-ID hardening: `439 tests OK`
- Patch Proposal Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 124 tests OK
- `node --check static/js/oomSakkie.js` passed after Patch Proposal Gate
- Applied migration `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`
- Full local unittest suite after Patch Proposal Gate: `449 tests OK`
- Patch Gate review-nit focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 125 tests OK
- `node --check static/js/oomSakkie.js` passed after Patch Gate review nits
- Full local unittest suite after Patch Gate review nits: `450 tests OK`
- Deploy Approval Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 135 tests OK
- `node --check static/js/oomSakkie.js` passed after Deploy Approval Gate
- Applied migration `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`
- Full local unittest suite after Deploy Approval Gate: `460 tests OK`
- Workbench/work-status focused verification: `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_routes tests.test_oom_sakkie_service` -> 136 tests OK
- `node --check static/js/oomSakkie.js` passed after Workbench/work-status slice
- Full local unittest suite after Workbench/work-status slice: `461 tests OK`
- Workbench pipeline clarity focused verification: `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_routes tests.test_oom_sakkie_service` -> 136 tests OK
- `node --check static/js/oomSakkie.js` passed after Workbench pipeline clarity
- Full local unittest suite after Workbench pipeline clarity: `461 tests OK`
- Deploy instructions / Business Advisor seed focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_frontend_route_contracts tests.test_oom_sakkie_routes` -> 138 tests OK
- `node --check static/js/oomSakkie.js` passed after deploy instructions / Business Advisor seed
- Full local unittest suite after deploy instructions / Business Advisor seed: `463 tests OK`
- Workbench Next Action focused verification: `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 138 tests OK
- `node --check static/js/oomSakkie.js` passed after Workbench Next Action
- Full local unittest suite after Workbench Next Action: `463 tests OK`
- Work Status honesty focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK
- `node --check static/js/oomSakkie.js` passed after Work Status honesty
- Full local unittest suite after Work Status honesty: `464 tests OK`
- Business Advisor context focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK
- `node --check static/js/oomSakkie.js` passed after Business Advisor context upgrade
- Full local unittest suite after Business Advisor context upgrade: `464 tests OK`
- Role-specific composer focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK
- `node --check static/js/oomSakkie.js` passed after role-specific composer rules
- Full local unittest suite after role-specific composer rules: `464 tests OK`
- Business Offer Outline focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 139 tests OK
- `node --check static/js/oomSakkie.js` passed after Business Offer Outline
- Full local unittest suite after Business Offer Outline: `464 tests OK`
- Agent Runtime Foundation focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 145 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Runtime Foundation
- Full local unittest suite after Agent Runtime Foundation: `470 tests OK`
- Agent Crew Status Tool focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 147 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Crew Status Tool
- Full local unittest suite after Agent Crew Status Tool: `472 tests OK`
- Agent Activity Stage focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 149 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Activity Stage
- Full local unittest suite after Agent Activity Stage: `474 tests OK`
- Agent Handoff Lane focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 149 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Handoff Lane
- Full local unittest suite after Agent Handoff Lane: `474 tests OK`
- Agent Crew Brief focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 151 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Crew Brief
- Full local unittest suite after Agent Crew Brief: `476 tests OK`
- Visible Crew Sequence focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 152 tests OK
- `node --check static/js/oomSakkie.js` passed after Visible Crew Sequence
- Full local unittest suite after Visible Crew Sequence: `477 tests OK`
- Agent Activation Plan focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 154 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Activation Plan
- Full local unittest suite after Agent Activation Plan: `479 tests OK`
- Sentinel Dry-Run Review focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 155 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Dry-Run Review
- Full local unittest suite after Sentinel Dry-Run Review: `480 tests OK`
- Applied Supabase migrations through `202606060004_lock_oom_sakkie_trace_append_only.sql`.
- Route smokes confirmed:
  - `/api/oom-sakkie/message` stores traces.
  - `/api/oom-sakkie/tools`, `/policy`, `/review-packet`, `/specialists`, `/review-advisor` work locally.
  - review/admin endpoints deny non-local requests with `403 review_access_denied`.
  - `/api/oom-sakkie/message` is not blocked by the review endpoint guard.
  - `send weather to John` answers the read-only weather check and returns a safety note.
  - `start irrigation` remains read-only and does not issue control.
  - `/api/oom-sakkie/review-advisor` returns `mode = advisory_only`, `writes_feedback = false`, and denies non-local requests.

## Design checks

Please inspect specifically:

1. **Split-brain:** Does the implementation preserve backend-as-brain without changing Telegram/n8n routing?
2. **Read-only tools:** Are all current Oom Sakkie tools truly read-only?
3. **Action safety:** Do unsupported write/control/message requests fail closed or produce safety notes?
4. **Irrigation safety:** Does control wording such as `start irrigation` stay read-only and never invoke physical control?
5. **Voice safety:** Is browser voice still opt-in, browser-local, half-duplex enough, and not always-on?
6. **Review endpoint protection:** Is the loopback/private-LAN guard appropriate for `/tools`, `/policy`, `/review-packet`, `/review-advisor`, `/traces`, feedback, and `/specialists`?
7. **Trace audit:** Are trace and feedback tables sufficiently append-only after the DB triggers?
8. **Safety/stale split:** Are `stale_warnings` and `safety_notes` separated cleanly through tools, API response, trace storage, and UI?
9. **Specialist roster:** Is Phase 10.7A safely planned-only, with no live delegation, autonomous loops, or second user-facing brain?
10. **Review advisor:** Is Phase 10.7B advisory-only, with no automatic feedback marking, no hidden write path, no model call, and no autonomous loop?
11. **Access policy:** Does Phase 10.7C document the message endpoint and reverse-proxy assumptions clearly enough, and are the tests honest about current `remote_addr` behavior?
12. **Kiosk advisor panel:** Is Phase 10.7D/E useful and still safe: user-action-triggered only, no timed/background polling, no auto-marking, no HTML injection from trace text, no hidden writes?
13. **Advisor trace reader:** Does Phase 10.7F/G preserve the advisor response shape while reducing duplicate trace-list reads, adding the days window, and avoiding SQL footguns?
14. **Trace row mapping:** Is the positional `_trace_row` mapping sufficiently guarded by tests?
15. **Kiosk honesty polish:** Does Phase 10.7H accurately surface the Review Advisor's 14-day window and the 5-turn continue-conversation cap without changing behavior?
16. **Trace-driven router tightening:** Does Phase 10.7I improve only deterministic read-only routing/wording from real traces, and does `turn the pump on` stay safe?
17. **Capability fallback precedence:** Does Phase 10.7J prevent `help me with <domain>` prompts from being swallowed by the generic capability answer while keeping bare `what can you do` useful?
18. **Bounded LLM fallback:** Does Phase 10.7K keep the LLM behind deterministic rules/action guards/capability fallback, validate tool names against read-only registry, reject unknown/write tools, and expose honest policy state?
19. **LLM privacy/failure hardening:** Does Phase 10.7L make outbound user-text behavior visible before enablement, and do the new tests pin env-gating, network failure, parse failure, and low-confidence clarification?
20. **LLM local smoke:** Does Phase 10.7M/N prove the configured router works as a bounded read-only fallback without weakening action/capability guards?
21. **LLM answer composer:** Does Phase 10.7O improve wording only after read-only tool execution, preserve safety/stale notes, reject unsafe action-claiming output, and expose outbound text/summary behavior honestly?
22. **Usejarvis reference:** Does the review correctly avoid installing/running/copying the external source while extracting safe architecture lessons only?
23. **Alive/provenance UI:** Does Phase 10.7P surface route source, answer source, pipeline state, confidence, and reason honestly without adding autonomy or unsafe behavior?
24. **Presence/voice layer:** Does Phase 10.7Q make the kiosk feel more like a live agent and improve answer tone while keeping all authority, facts, and safety boundaries unchanged?
25. **Capped context composer:** Does Phase 10.7R improve briefing quality by giving the composer structured read-only context while keeping context capped, disclosed, post-tool-only, and unable to choose actions/tools?
26. **Operating brief tool:** Does Phase 10.7S safely aggregate existing read-only checks into one user-initiated brief without adding autonomy, writes, controls, or hidden tool authority?
27. **Operating brief required sections:** Does Phase 10.7T prevent weather/irrigation/power/attention from being silently dropped while keeping context compact and the safety filter honest?
28. **Top voice controls:** Does Phase 10.7U improve first-viewport usability without changing mic safety, always-on behavior, or voice authority?
29. **Learning Queue:** Does Phase 10.7V create useful human-approved improvement proposals from reviewed traces without self-editing, hidden writes, LLM calls, or prompt/tool mutation?
30. **LLM Learning Analyst:** Does Phase 10.7W keep LLM trace analysis explicit, env-gated, protected, capped, proposal-only, and unable to write or apply changes?
31. **Composer lane guard:** Does Phase 10.7X correctly stop single-tool answers from discussing unrelated systems while preserving operating-brief multi-system behavior?
32. **Learning Build Brief:** Does Phase 10.7Y create useful implementation packets from learning proposals while remaining review-only: no LLM call, no code write, no prompt/tool mutation, no feedback write, protected route only?
33. **Implementation Queue:** Does Phase 10.7Z safely auto-prepare review briefs only from strong signals while remaining review-only: no LLM call, no code write, no prompt/tool mutation, no feedback write, protected route only, and human approval still required?
34. **Approve For Build:** Does Phase 10.8A create a clear build-request object without running a builder, editing files, applying patches, deploying, or weakening the later patch/deploy approval gates?
35. **Persistent Build Requests:** Does Phase 10.8B persist approved build requests append-only, preserve no-builder/no-write flags at DB and application layers, and expose history without triggering a Builder/Forge step?
36. **Build Request Events:** Does Phase 10.8C provide an append-only correction/review path for build requests without editing/deleting requests or creating any builder/deploy authority?
37. **Forge Handoff:** Does Phase 10.8D prepare a useful Builder/Forge instruction packet while still not running a builder, editing files, applying patches, deploying, or weakening the future patch/deploy approval gates?
38. **Forge Handoff persisted-ID hardening:** Does Phase 10.8E close the synthetic-payload gap by requiring a stored `build_request_id` lookup before handoff generation?
39. **Patch Proposal Gate:** Does Phase 10.8F record Builder/Forge patch proposals and owner review decisions append-only while still not applying patches, editing files, running subprocesses, deploying, or weakening the later manual approval gates?
40. **Patch Gate review nits:** Does Phase 10.8G close Claude's minor follow-ups: current Forge Handoff test payload, frontend advisor-window assertion, and clean `404 patch_proposal_not_found` behavior before recording patch proposal events?
41. **Deploy Approval Gate:** Does Phase 10.8H record manual deploy decisions append-only, require an approved patch proposal before manual deploy approval, and still not run deploys, edit files, run subprocesses, mutate prompts/tools, or touch farm data?
42. **Workbench simplification:** Does Phase 10.8I make the kiosk less busy by collapsing the heavy audit/build controls while keeping the audit trail available?
43. **Work status tool:** Is `system_work_status` truly read-only, and can Oom Sakkie answer `what needs my approval?` without running Builder/Forge, applying patches, deploying, mutating prompts/tools, or touching farm data?
44. **Clipboard behavior:** Is the `Copy Forge Prompt` button explicit owner-triggered copy only, with no automatic external tool call or hidden execution?
45. **Workbench pipeline clarity:** Does Phase 10.8J make active vs moved/closed work clear, and do items move between visible buckets through append-only review/deploy records rather than hidden mutation?
46. **Deploy-ready instructions:** Does Phase 10.8K explain the approved-patch/deploy-decision step clearly without implying the kiosk applies patches or deploys?
47. **Business Advisor seed:** Is `business_growth_brief` read-only, commercially useful, and safely blocked from drafting/posting/messaging/selling/reserving/changing stock?
48. **Workbench Next Action:** Does Phase 10.8L reduce owner confusion by surfacing the next action and visually separating sections without hiding audit data or adding hidden execution?
49. **Work Status honesty:** Does Phase 10.8M close the outage-honesty gap so `system_work_status` never confidently reports no approval work when a build/patch/deploy store is unavailable?
50. **Business Advisor context:** Does Phase 10.8N make `business_growth_brief` materially more useful while staying read-only and approval-safe?
51. **Role-specific composer:** Does Phase 10.8O improve Business Advisor and work-status delivery without giving the LLM tool-selection, write, send, sell, patch, or deploy authority?
52. **Business Offer Outline:** Does Phase 10.8P provide a useful internal commercial outline while still not drafting customer/public copy, creating quotes, selling, reserving stock, mutating data, or bypassing owner approval?
53. **Agent Runtime Foundation:** Does Phase 10.9A create a useful platform for named specialist agents while keeping live runtime, dispatch, autonomous loops, writes, tool execution, specialist LLM calls, customer/public output, Builder/Forge execution, patch application, and deploy disabled?
54. **Agent Crew Status Tool:** Does Phase 10.9B make crew recommendations available through normal Oom Sakkie chat while still not dispatching specialists, running specialist LLM calls, executing specialist tools, writing data, or bypassing owner approval?
55. **Agent Activity Stage:** Does Phase 10.9C move the kiosk toward the controller/specialist-workspace visual model while staying display-only: no live dispatch, no specialist LLM, no autonomous loop, no new tool authority, no writes, and honest visible guard text?
56. **Agent Handoff Lane:** Does Phase 10.9D make the controller -> specialist -> read-only tool -> owner-gate process clearer without implying live agent execution, hidden delegation, writes, customer/public output, physical control, Builder/Forge execution, patch application, or deploy?
57. **Agent Crew Brief:** Does Phase 10.9E provide a useful plan-only multi-specialist sequence while keeping live dispatch, specialist LLM calls, specialist tool execution, autonomous loops, writes, customer/public output, Builder/Forge execution, patch application, and deploy disabled?
58. **Visible Crew Sequence:** Does Phase 10.9F render the crew plan visibly and safely on the kiosk while keeping normal single-tool checks uncluttered and preserving all `runs no` / `writes no` guardrails?
59. **Agent Activation Plan:** Does Phase 10.9G make the future live-agent path explicit while keeping runtime/dispatch/autonomous-loop/write flags false and preserving all owner approval/audit gates before any dry-run or live dispatch?
60. **Sentinel Dry-Run Review:** Does Phase 10.9H rehearse the first specialist candidate as deterministic/read-only/advisory-only review while keeping live dispatch, specialist LLM execution, specialist tool execution, autonomous loops, writes, customer/public output, Builder/Forge execution, patch application, and deploy disabled?
61. **Tests:** What missing tests or browser checks should happen before this is considered daily-use ready?

## Deliverable format

- **Verdict:** pass / pass-with-nits / block.
- **Findings first:** severity ordered, with file/line references where possible.
- **Open questions:** only if a decision is required before continuing.
- **Recommended next slice:** keep it safe and local; do not recommend Telegram cutover, writes, physical controls, always-on mic, wake word, or live specialist delegation unless you explicitly justify why the current daily-use trial is insufficient.

---

## Archive / Reusable Templates

The sections below are older reusable prompt templates and examples for other review types.

For the current Oom Sakkie review, Claude should use only the **Current Review Packet** above unless Charl explicitly asks for another review scope.

## Before you paste anything

1. Open **`docs/00-start-here/NEXT_STEPS.md`** and note the **single phase / subsection** that is in scope (e.g. **Phase 4.1**). Everything outside that is **out of scope** for this review unless you explicitly widen it.
2. Ensure **`CLAUDE.md`** in the repo root is up to date (Claude Code reads it first).

---

## Prompt template — replace `{{PLACEHOLDERS}}`

Paste into Claude Code:

```markdown
You are working in the **Amadeus Pig Tracking & Sales** repo. Read **CLAUDE.md** first, then the files I name below.

## Authority and scope

- **Build order**: `docs/00-start-here/NEXT_STEPS.md` — my **explicit scope for this task** is: **{{1.8 Approval Auto-Reservation}}** only.
- Do **not** propose new phases or widen scope unless I ask — if you find unrelated issues, list them briefly under "**Out of scope**" with one-line rationale each.

## What Cursor / I changed or plan to change

**Summary**: {{SHORT_DESCRIPTION_OF_THE_WORK}}

**Branches / commits / PR**: {{GIT_REF_OR_NONE}}

## Files changed (paths)

{{LIST_FILES_OR_DIFF_SUMMARY}}

## Design checks (answer each)

Work through these **in order**:

1. **Architecture**: Does the change respect `docs/01-architecture/SYSTEM_ARCHITECTURE.md` and boundaries in `CLAUDE.md` (Chatwoot → n8n → Steward/agent → Flask → Sheets)?
2. **DATA_FLOW / ownership**: Does every mutated field trace to `docs/04-n8n/DATA_FLOW.md` and `BUSINESS_RULES` / `SHEET_SCHEMA` as appropriate — no duplicated sources of truth?
3. **n8n workflows**: Is `WORKFLOW_RULES.md` respected? Confirm **formula-driven sheets** stay read-only; confirm **routing** vs **truth** — customer-facing wording must align with **backend / `get_order_context`** for availability and drafts, not only LLM narration.
4. **Order logic**: Does `ORDER_LOGIC.md` still hold for draft/create/sync/reserve/reserve-cancel paths touched?
5. **Regression**: Against `NEXT_STEPS.md` subsection **{{PHASE_AND_SUBSECTION}}**, what is **still missing** for "**Required outcome**" to pass?

## Deliverable format

- **Verdict**: pass / pass-with-nits / block — one sentence each for **risk** and **next concrete step**.
- **Findings**: bullet list grouped by severity (blocking / nit / suggestion).
- **Out of scope** (optional): rabbits we are **not** chasing in this pass.

Extra context dump (payloads / logs):

{{PASTE_LOGS_OPTIONAL}}

```

---

## When to run this (not every change)

Use the handoff for **big or cross-cutting** work. Skip it for tiny, local edits unless you want assurance. Triggers and philosophy: **`docs/00-start-here/HOW_WE_WORK.md` §3**.

Typical triggers:

- Large **`workflow.json`** edits (e.g. `1.0 - Sam-sales-agent-chatwoot`, `1.2 - order-steward`).
- Anything that mixes **routing**, **prompt text**, **Steward payloads**, and **backend** in one change set.
- When you suspect **truth vs narration** mismatch (availability, drafts, reservations).

**When not to bother:** one-file bugfix, typo, comment-only, isolated tiny Code node — unless you are unsure.

## Cursor’s conductor rule

Cursor should **remind you** when a session crosses the “big enough for Claude review” bar; you still **choose** whether to paste into Claude Code. Always scope: "**`NEXT_STEPS.md` §X.Y only.**"

---

## Filled handoff — Phase 1.8: Approval Auto-Reservation (paste everything in the block below)

*Built from `NEXT_STEPS.md` §1.8, `CLAUDE.md`, `ORDER_LOGIC.md`, and current `modules/orders/order_service.py`. Update the “Optional / after implementation” lines with your branch and diff before sending to Claude Code.*

```markdown
You are working in the **Amadeus Pig Tracking & Sales** repo. Read **`CLAUDE.md`** first, then the files listed under **Read first**.

## Authority and scope

- **Build order:** `docs/00-start-here/NEXT_STEPS.md`
- **Explicit scope:** **Phase 1 — §1.8 Approval Auto-Reservation** only.

**Out of scope for this review** (unless I explicitly ask): **§1.9** outbound approval/rejection notifications; **Phase 2+** quotes/invoices; **Phase 4** split-line sync; Sam **`1.0`** prompt copy — unless my diff touches them.

If you find unrelated bugs, list them under **Out of scope** with one line each.

## Goal (from NEXT_STEPS — Required outcome)

Deliver **reserve-on-approve**:

1. **`approve_order`** must set approval state **first** (order becomes **Approved** / approval flags updated as today).
2. **Then** call into the existing **reserve** path for **active** `ORDER_LINES` (reuse **`reserve_order_lines`** semantics from Phase 1.6 — cancelled/collected skipped, no `Pig_ID` skipped, idempotent reserve).
3. If **reservation fails entirely** or **only partially** succeeds:
   - **Do not roll back** the approval in the database/sheets.
   - Surface a **`reserve_warning`** (and/or equivalent structured warning) in the API response for the **web app** to show manual follow-up.
   - Write an appropriate entry to **`ORDER_STATUS_LOG`** documenting the partial/total reserve failure after approval.
4. Per-line outcomes must remain **clear** in the API (align with existing **`reserve_order_lines`** `line_results` / `warning` patterns where possible).

## Current baseline (for you to verify in code)

- **`approve_order`** in `modules/orders/order_service.py` currently: validates **`Pending_Approval`**, updates **`ORDER_MASTER`** to Approved, writes **`ORDER_STATUS_LOG`**, returns `{ success, message, order_id }` — **it does not invoke reservation today**.
- **`reserve_order_lines(order_id)`** in the same module: batch reserve eligible lines; returns **`success`**, **`line_results`**, **`changed_count`**, **`warning`**, **`reserved_pig_count`** — hardened under **Phase 1.6**.
- **HTTP:** `POST /api/orders/<order_id>/approve` in `modules/orders/order_routes.py` returns whatever `approve_order` returns.

Your review should check that the **implementation plan or diff** chains these correctly without breaking lifecycle rules in `docs/02-backend/ORDER_LOGIC.md` and sheet rules in `docs/03-google-sheets/BUSINESS_RULES.md` / `SHEET_SCHEMA.md`.

## What changed / what to review (fill in by human, or paste `git diff --stat`)

**Summary:** _Describe planned or implemented §1.8 work (e.g. “After `approve_order` header update, call `reserve_order_lines`, merge warnings into response, log partial failure”)._

**Branches / commits / PR:** _e.g. branch name, commit SHAs, or “planning only — no commits yet”._

**Files changed (paths):**

_read from `git diff --stat` or list manually, e.g._

- `modules/orders/order_service.py`
- `modules/orders/order_routes.py`
- _Web app order detail component if API contract changes_
- `docs/02-backend/ORDER_LOGIC.md` (if behavior documented)

## Read first

1. `docs/00-start-here/NEXT_STEPS.md` — **§1.8** only
2. `docs/02-backend/ORDER_LOGIC.md` — approval, reserve, release
3. `docs/04-n8n/DATA_FLOW.md` — only if the diff changes Steward or order API contracts
4. `modules/orders/order_service.py` — `approve_order`, `reserve_order_lines`
5. `modules/orders/order_routes.py` — `/approve`

## Design checks (answer each)

1. **Architecture:** Does the change respect Chatwoot → n8n → Steward/agent → Flask → Sheets and keep **formula-driven sheets** read-only?
2. **Approval vs inventory:** Is **approval** still a single, atomic header transition, with **reservation** as a **second phase** that can fail without undoing approval?
3. **Observability:** Will ops see **log + API** evidence when pigs did not all reserve (per **`ORDER_STATUS_LOG`** and response body)?
4. **UI contract:** Does the **web app** receive enough structured fields (`reserve_warning`, `line_results`, counts) to match **Phase 1.6**–style messaging?
5. **Regression:** Against **§1.8 Required outcome**, list anything **still missing**.

## Deliverable format

- **Verdict:** pass / pass-with-nits / block — one sentence **risk** + one **next concrete step**.
- **Findings:** bullets by severity (blocking / nit / suggestion).
- **Out of scope:** optional.

**Optional — paste API response sample or execution log after a test approve:**

_(paste here)_

```
```

### How to use

1. Copy everything from the line **`You are working in the Amadeus…`** down to **`(paste here)_`** (inclusive), i.e. the full prompt inside the fenced block above — **do not** copy the wrapper sections titled “Filled handoff” / “How to use”.
2. Fill in **Summary**, **git ref**, and **files changed** (or write *planning only — no commits yet*).
3. Paste into **Claude Code** with this repo open.
