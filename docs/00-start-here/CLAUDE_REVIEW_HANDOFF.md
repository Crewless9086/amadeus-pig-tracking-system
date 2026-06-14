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
- **Explicit scope:** Phase 10.6 Oom Sakkie local kiosk/backend-as-brain work through `10.6Z`, plus Phase 10.7A-Z, 10.8A-P, and 10.9A-DM specialist manifest, advisory trace-review, access caveat hardening, kiosk review-advisor panel, advisor wording/proxy-test tightening, advisor trace-read consolidation, advisor SQL/test hardening, kiosk advisor-window/voice-loop counter polish, trace-driven router/power-answer tightening, capability-fallback precedence fix, bounded LLM fallback router, LLM fallback privacy/failure-mode hardening, LLM smoke harness, verified local LLM smoke, env-gated LLM answer composer, Usejarvis external-reference review, kiosk alive-state/provenance strip, stronger spoken answer voice, animated presence orb, capped context briefing composer, read-only operating brief tool, operating brief required-section fix, top voice controls, human-approved Learning Queue, explicit LLM Learning Analyst, trace-driven composer lane guard, deterministic Learning Build Brief packet, human-approved Implementation Queue, Approve For Build gate, persistent build request queue, build request event log, Forge Handoff packet, Forge Handoff persisted-ID hardening, Patch Proposal Gate, Patch Gate review nits, Deploy Approval Gate, Workbench simplification, Forge prompt copy button, read-only system work status tool, Workbench pipeline clarity, deploy-ready instructions, read-only Business Advisor seed, Workbench Next Action card, Business quick action, Work Status honesty fix, Business Advisor context upgrade, role-specific spoken composer rules, internal-only Business Offer Outline, agent runtime/readiness/authority/review rails, Sentinel single-shot advisory runner and first supervised smoke, Owner Cockpit UI, learning influence proposal rail/status/workbench/browser gates, cockpit decision feedback, exact accepted-result proposal preparation, owner review packet scope evidence, the `prepare Claude review` chat gate, live-PG closure for the learning-influence `from-result` rail, recorded-CI evidence policy, learning-consumption threat-model readiness, explicit provenance/blast-radius controls, read-only consumption audit-rail blueprint, append-only consumption audit rail implementation, pre-consumer static/design gate, hardened allow-consumed static guard, source-backed allow-consumed caller evidence, scanner resilience hardening, read-only consumer design agreement, consumed-once atomicity wording, owner-approved first review-note-only learning consumer, call-site-granular allow-consumed guard hardening, browser voice-capture fix, supervised live consumer smoke evidence, backend push-to-talk STT fallback, read-only Telegram gateway path, Telegram LLM-egress/token hardening, Telegram public-exposure hardening, Telegram exposure preflight, private Telegram relay smoke helper, smoke URL guard, inactive n8n backend read-only relay contract, relay transport guard, local relay import preflight, Workbench learning-backlog clarity, and owner-approved GateKeeper backend-relay wiring plan.
- **Latest additions in this review packet:** Phase 10.9DB-DM adds an env-gated backend STT fallback for the existing owner-clicked `Talk` / `Talk & Ask` controls, a token-gated read-only Telegram gateway endpoint, the follow-up hardening requested by Claude, a protected read-only exposure preflight, a local private relay smoke helper, a URL guard for that helper, an inactive callable n8n backend relay contract for GateKeeper review, a matching n8n base-URL transport guard, a local import preflight validator, kiosk Workbench clarity for learning/dry-run backlog, and an owner-approved manual GateKeeper backend-relay wiring plan. The STT fallback records only after an owner click, posts one short browser audio blob to the protected Flask route, stores no audio, leaves always-on mic/wake word off, and keeps writes/dispatch/runtime changes false; owner note: captured audio is sent to the configured OpenAI audio transcription endpoint when this fallback is enabled. The Telegram gateway accepts a Telegram-update-shaped payload only when `OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED=1`, `OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN` is at least 32 characters, and `OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS` is configured; token comparison uses `hmac.compare_digest`, repeated bad tokens trigger a fail-closed in-process auth lockout, and the `telegram_read_only` channel is deterministic-only with a true no-HTTP-egress regression test so it cannot trigger outbound LLM calls even if those env flags are enabled. Protected `GET /api/oom-sakkie/channels/telegram/exposure-preflight` separates automated private-test readiness from public-exposure readiness, records the in-process/global rate-limit caveat, and requires explicit TLS plus rate-limit-model confirmations before reporting public ready. `scripts/oom_sakkie_telegram_private_relay_smoke.py` checks preflight and one gateway reply payload without sending Telegram, and refuses non-local plain-HTTP smoke URLs before sending the token. `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/` adds a callable `Execute Workflow Trigger` template only: no Telegram Trigger, no Telegram send node, no hardcoded token/chat ID, and no second normal-message owner. The relay validates backend no-authority flags, refuses remote plain-HTTP base URLs before using the bearer token, and returns only a guarded `send_allowed` / `chat_id` / `telegram_text` payload for later GateKeeper wiring. `scripts/oom_sakkie_n8n_relay_contract_check.py` validates the committed workflow/README locally without calling n8n, Telegram, Flask, OpenAI, Google Sheets, or Supabase. The Workbench labels closed dry-runs, accepted evidence, and reviewed learning proposals as append-only audit backlog, and dry-run requests with recorded results no longer appear as active handoff work. `BACKEND_RELAY_WIRING_PLAN.md` says to import `2.0B` inactive, edit GateKeeper manually through n8n UI after backup, keep GateKeeper as the only Telegram Trigger owner and only reply sender, validate backend no-authority flags before sending exactly one owner reply, and preserve rollback. This does not add another learning consumer, apply learning, produce an applyable prompt/route/runtime diff, mutate prompts/routes/runtime/tools/farm data, create public/customer output directly, deploy, control hardware, or perform financial actions.

Out of scope unless explicitly asked:

- Telegram cutover
- write tools
- physical controls
- backend TTS vendors
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
- LLM Message Guard that keeps `/api/oom-sakkie/message` open for deterministic local use while LLM flags are off, but requires local/private-LAN access before outbound paid LLM calls can happen
- Agent Dry-Run Request Gate that records owner-approved Sentinel dry-run requests append-only while keeping dry-run execution, specialist dispatch, specialist LLM calls, specialist tool execution, and writes disabled
- Message Guard Policy Consistency so `/api/oom-sakkie/policy` reports the same router/answer/learning env set that the access layer enforces for `/message`
- Sentinel Dry-Run Handoff Packet that requires a persisted dry-run request ID and returns a prompt/packet only, still with no Sentinel execution, specialist LLM calls, specialist tool execution, or writes
- Sentinel Dry-Run Result Gate that records a future Sentinel dry-run result for owner review append-only, still with no specialist execution, runtime change, tool execution, or writes
- Sentinel Review Queue Status that makes request/result review state visible through the read-only `agent_dry_run_status` tool and `Dry-Run Queue` quick action
- Sentinel Dry-Run Result Review Packet that looks up persisted result records and returns review-only owner options without running Sentinel or changing runtime state
- Sentinel Result Review UI that opens result packets, records append-only accepted/rejected/review-note events, and keeps review-note-only results pending
- `agent_learning_evidence` read-only tool and `Agent Learning` quick action that summarize only accepted Sentinel learning evidence
- Agent Learning Ledger UI that displays accepted dry-run evidence separately from pending/rejected result reviews
- Accepted Learning Roadmap Link so the activation plan can reference accepted Sentinel evidence while keeping runtime/dispatch/write flags false
- Visible Agent Roadmap panel and protected activation-plan endpoint for locked, read-only agent activation planning
- Sentinel Dry-Run Request Button that creates an append-only Sentinel-only request from the roadmap while still not running Sentinel
- Sentinel Dry-Run Mini-Pipeline UI for opening Sentinel handoffs and recording reviewed result text/findings without executing specialist LLM, specialist tools, writes, runtime changes, Builder/Forge, patch, or deploy
- Workbench Sentinel Next Action card that prioritizes pending Sentinel handoff/result-review work before build/patch/deploy queues without implying automation or execution
- Live-PG Audit Rail Smoke that verifies append-only triggers and no-execution CHECK constraints on the Oom Sakkie audit rails when `DATABASE_URL` is configured
- Prism Dry-Run Request Gate that starts the second planned specialist on the same request -> handoff -> reviewed result rail while still not running Prism
- Generic Agent Dry-Run Workbench Labels so the shared dry-run queue/review UI covers Sentinel and Prism without implying live execution
- Agent Dry-Run Browser Behavior Contracts that pin no timer polling, explicit button-triggered dry-run/result/event actions, GET-only review packet loading, and render-only sections with no hidden fetches or event writes
- Approved Read-Only Dry-Run Cohort that lets Ledger, Atlas, Rootline, Herdmaster, Butcher, and Quartermaster create the same append-only no-execution dry-run request records while keeping Beacon, Forge, and Gatekeeper locked out
- Activation Roadmap Cohort Visibility that shows the same approved dry-run cohort in the Agent Roadmap with `dry_run_request_allowed = true` while keeping live runtime `allowed_now = false`
- Specialist Dry-Run Handoff Quality that adds role-specific focus questions, context needs, risk checks, and owner approval questions to each approved specialist handoff packet
- Specialist Result Evidence Boundaries that classify reviewed dry-run results by specialist and show what accepted evidence may influence and must not influence before the owner accepts it for learning
- Per-Specialist Dry-Run Queue Status that adds read-only `specialist_counts` to the dry-run queue status tool so Oom Sakkie can explain which planned specialists have request/result items waiting
- Generic Agent Learning Evidence that adds `accepted_by_specialist` and removes Sentinel-only accepted-learning wording now that the approved dry-run cohort is wider
- Roadmap Learning Counts that exposes the same `accepted_by_specialist` count through the protected activation-plan route and roadmap panel
- Audit Rail CI Workflow that runs the existing DATABASE_URL-gated append-only/no-execution tests against disposable Postgres in GitHub Actions
- Browser Behavior Checklist that gives the owner a repeatable multi-specialist Workbench and voice-control pass without adding Playwright yet
- Audit Rail CI Scope Hardening that scopes the disposable-Postgres workflow to Oom Sakkie service/routes/frontend tests so unrelated future DB tests do not fail this safety job for schema-coverage reasons
- Agent Runtime Readiness Tool that gives Oom Sakkie a read-only checklist answer for what still blocks live agents, while keeping every runtime/dispatch/write/public/control flag false
- Browser Behavior Smoke Gate that executes the real kiosk JS in a fake DOM and fails on startup background polling, startup hidden POSTs, or dry-run/result/message POSTs that are not owner-click-triggered
- Agent Operating Contracts that make each planned specialist's focus, allowed read-only tools, must-not-do list, owner gate, and dry-run request eligibility visible without creating runtime authority
- Agent Contracts Review Endpoint that exposes the same contracts through protected `GET /api/oom-sakkie/agents/contracts` with a false-all review guard for reviewers and future UI
- Agent Activation Preflight that combines readiness, contracts, activation plan, browser-smoke, and manual-review gates into one read-only not-ready-for-live-dispatch answer and protected endpoint
- Activation Preflight Wording Hardening that changes configured CI/smoke gates from `pass` to `configured` so preflight does not imply a live GitHub/manual-browser result
- Agent Authority Matrix that exposes every future authority area, risk level, locked reason, and required gates through a read-only tool and protected route while keeping `enabled_count = 0`
- Authority Lock Source Alignment that derives activation-plan blocked capabilities and preflight locked checks from the authority matrix source and adds drift tests
- Authority Unlock Readiness that reports the lowest-risk planning candidates and high-risk hard-no authorities without recommending or performing any unlock
- Runtime Inspection Invariant Test that asserts every authority flag present across all agent inspection surfaces remains false
- Dispatch Decision Rail Blueprint that exposes a protected, read-only design packet for a possible future append-only dispatch decision rail while keeping dispatch, specialist LLM/tool execution, writes, public output, and runtime changes disabled
- Agent Runtime Review Packet that bundles the current runtime status, readiness, contracts, preflight, authority matrix, unlock readiness, and dispatch rail blueprint into one protected read-only payload for bulk Claude review
- Playwright Browser Behavior Gate that adds a real-browser CI/manual test for `/oom-sakkie` startup no-hidden-POST/no-interval behavior and owner-click-only dry-run/result/message POSTs, with all `/api/oom-sakkie/**` calls stubbed as read-only JSON
- Dispatch Decision Rail that adds an append-only no-execution request/decision rail for future dispatch design review while forcing dispatch, specialist LLM/tool execution, writes, and runtime changes false in both app code and DB constraints
- Dispatch Decision Status Visibility that adds read-only `dispatch_decision_status` and folds dispatch design-review counts into `system_work_status` without adding any consumer that changes runtime behavior from decisions
- Dispatch Runtime Review Packet that combines the locked runtime-review packet with read-only dispatch design status for owner/Claude review before any future code consumes dispatch decisions
- Jarvis Product Progress that adds read-only `jarvis_product_progress` progress bars/percentages so the owner can ask where the Oom Sakkie/Jarvis product stands while all runtime authority remains locked
- Agent Command Center that adds read-only `agent_command_center` so the owner can ask who is working / what agents are doing and receive a control-tower view of lanes, queues, progress, and locked gates while every lane remains non-executing
- Command Center Quick Action that adds a kiosk quick-check button for `Show me the agent command center.` and maps command-center answers to Gatekeeper in the visible agent activity stage
- Future Financial Agent idea logged as research-only and hard-locked out of current scope: no trading, broker/exchange/account access, custody/funds/payment movement, model-driven orders, profit-share automation, or financial advice/recommendations without a separate legal/risk/owner/Claude-reviewed architecture later
- Playwright CI Startup Hardening that changes only the browser-behavior GitHub workflow startup path to Python 3.12 plus `python -m flask --app app run --host 127.0.0.1 --port 5000` with debug disabled; no runtime/app authority changed
- Daily Command Brief that adds read-only `jarvis_daily_command_brief`, routes daily-command/start-my-day phrasing, points the existing `Brief` quick action at that broader command brief, maps it visually to Gatekeeper, composes farm operating brief + business growth brief + Agent Command Center, and extracts read-only next actions while keeping all execution flags false
- Playwright CI Node 24 / Server URL Hardening that opts the browser workflow into Node 24 and separates Playwright test `baseURL` from `/oom-sakkie` webServer readiness URL; no app/runtime behavior changed
- Playwright Workbench Visibility Fix that opens the collapsed System Workbench in the real-browser spec before clicking dry-run/result controls and asserts the Sentinel dry-run button is visible; test-only, no app/runtime behavior changed
- Audit Rail CI Node 24 Warning Cleanup that opts the disposable-Postgres audit workflow into Node 24 to remove the remaining GitHub Actions deprecation warning; CI-only, no app/runtime behavior changed
- Safety Gate Board that adds read-only `jarvis_safety_gate_board`, routes safety-gate / CI-status wording, maps it visually to Sentinel, and folds it into Agent Command Center as a panel/source/snapshot while making no GitHub/network call and keeping all runtime authority locked
- Owner Review Packet that adds read-only `jarvis_owner_review_packet`, routes owner-review / Claude-handoff wording, maps it visually to Gatekeeper, and composes progress, command-center, safety-gate, and runtime-review surfaces without calling Claude/GitHub or approving authority
- Review Shortcuts that add explicit-click `Safety Gates` and `Review Packet` quick-action buttons using the existing `data-quick-ask` path; UI reachability only, no hidden POSTs, background polling, routes, stores, or authority
- Quick Checks Grouping that groups existing quick-action buttons into Farm, Business, and Agent Review clusters; UI clarity only, no prompt or JavaScript behavior change
- CI Green Evidence that uses portable GitHub CLI to confirm latest `Oom Sakkie Audit Rails` and `Oom Sakkie Browser Behavior` runs on `main` are green; operational evidence only, no app/runtime change
- Dispatch Execution Approval Rail that adds append-only Sentinel-only execution-approval records and events after an approved dispatch design review; approval rail only, all execution flags forced false, no runner/consumer/specialist LLM/tool/farm-write/public/deploy/Telegram/control path
- Sentinel Single-Shot Advisory Runner that adds a default-off env-gated, approval-gated, Sentinel-only one-shot LLM runner; it consumes one approval through a runner-only event, sends capped read-only context once, rejects unsafe action-claiming output, writes only to the append-only dry-run result rail, and still runs no tools/writes/public output/deploy/Telegram/physical controls
- Sentinel Runner Review Hardening that makes the authority matrix report `specialist_llm_loop` as `single_shot_advisory_only` while keeping `enabled = false`, all other authorities locked, and the default-off runner test proving no outbound HTTP call occurs when the env gate is off
- Effective Single-Shot Visibility that adds env/configured visibility fields to the `specialist_llm_loop` authority-matrix area so an operator can see whether the narrow Sentinel single-shot path is effectively on, while keeping general specialist LLM authority disabled
- Sentinel Single-Shot Runbook that documents the supervised first-run procedure, prerequisites, exact approval chain, short env-on window, expected result shape, replay-block verification, immediate env-off step, and outcome logging without enabling or running anything
- First Sentinel Smoke And Review Packet Fix that records the first owner-approved Sentinel single-shot result, verifies replay blocking, confirms the normal policy returns to `specialist_dry_run.enabled = false`, and narrowly updates result review packets to accept only the honest Sentinel single-shot mode while still rejecting tools/writes/dispatch/runtime-change flags
- Owner Approval Console that adds a first-screen `Needs Your Approval` panel above the detailed System Workbench, summarizing only current owner-decision items from existing queues and opening existing Workbench actions on explicit click; no endpoint/store/migration/authority change and the full audit Workbench remains intact
- Controller Board that adds a first-screen `Controller / Specialist / Owner Gate` board populated only from existing `agent_activity`, making the stage easier to understand without new endpoints, fetches, POSTs, stores, migrations, runner wiring, or authority changes
- Primary Command Deck that adds first-screen explicit-click read-only asks for daily brief, approvals, command center, and safety gates through the existing `data-quick-ask` path; no new fetch path or direct action buttons
- Quick Checks Drawer that collapses the larger farm/business/agent quick-action grid behind `More read-only checks` while preserving existing prompts and JavaScript binding; presentation only
- Command UI Browser Gate Hardening that extends the Playwright real-browser spec to assert the new command deck/drawer are visible, opening the drawer creates no hidden POST or interval polling, and command-deck clicks still use the explicit owner-triggered `/message` path; test-only
- Sentinel Single-Shot Contract Alignment that adds a Python source of truth for the Sentinel single-shot result identity/flag shape and uses it in the result store, review packet, runner, and tests while keeping migration SQL static and contract-tested
- Dispatch Execution Consumed-Once Live-PG Test that proves the partial unique index rejects a second `consumed_by_single_dry_run_result` event for one execution approval while still allowing normal review-note evidence
- Consumed-Once Migration Assertion that also pins the unique-index name in the normal migration-content test so the one-shot DB guard is visible even when live Postgres is not configured
- Learning Influence Proposal Rail that converts accepted agent learning evidence into append-only `learning_influence_proposal_only` records for owner review while forcing all apply/prompt/runtime/dispatch/write flags false
- Learning Influence Status Tool that lets Oom Sakkie answer self-learning / Sentinel suggestion questions by reading proposal counts only, without generating or applying proposals from chat
- Learning Influence Workbench UI that lets the owner explicitly prepare proposal records from accepted evidence, review pending proposals, and record append-only proposal events while keeping the first-screen approval console navigation-only
- Learning Influence Browser Gate Hardening that extends VM smoke and Playwright coverage so proposal preparation and proposal review events are explicit-owner-click actions with no interval polling
- Owner Cockpit UI and decision feedback that move only append-only agent-result/proposal review decisions to the first screen, keep the full System Workbench available as the audit trail, and show visible status after owner clicks
- Cockpit Accepted-Result Proposal Prep that calls `POST /api/oom-sakkie/agent-learning/influence-proposals/from-result` only after a successful `Accept For Learning` event, sends the exact clicked `source_result_id`, and prepares a proposal only if that result's latest event is `accepted_for_learning`
- Consumption Audit Rail Implementation that creates append-only request/event records only after a proposal is `approved_for_future_planning`, forces all apply/prompt/runtime/dispatch/write flags false, reserves `consumed_for_patch_proposal` for a later reviewed consumer path, and proves consumed-once behavior in live Postgres
- Pre-Consumer Static/Design Gate that adds a no-production-`allow_consumed=True` static guard and read-only consumer-design packet before any consumer code exists
- Hardened Allow-Consumed Static Guard that closes Claude's nit by detecting alias/module calls, positional fourth-argument overrides, `**kwargs`, and non-literal-false `allow_consumed` overrides
- Source-Backed Allow-Consumed Caller Evidence that makes the consumer-design packet derive `allow_consumed_production_callers` from the shared AST scanner instead of a hardcoded empty list
- Allow-Consumed Scanner Resilience that makes the source-backed scanner CWD-independent and parse-error tolerant while still adding no consumer
- Read-Only Consumer Design Agreement that makes the next owner/Claude design review explicit without implementing a consumer
- Consumed-Once Atomicity Wording that names the DB partial unique index as the consumer race guard before the 10.9CY consumer uses it
- Review-Note Consumer Implementation that adds exactly one reviewed `allow_consumed=True` caller and protected route for producing review-note artifacts only, with no prompt/route/runtime application
- Call-Site Guard Hardening that requires exactly one reviewed `allow_consumed=True` call site and avoids substring path allowlist matches
- Browser Voice Capture And Live Consumer Smoke that proves Talk/Talk & Ask transcript handling and records the owner-supervised route smoke against live Postgres

## Files/folders to inspect

- `modules/oom_sakkie/`
- `modules/oom_sakkie/learning_advisor.py`
- `modules/oom_sakkie/learning_llm.py`
- `modules/oom_sakkie/learning_packet.py`
- `modules/oom_sakkie/forge_handoff.py`
- `modules/oom_sakkie/agent_runtime.py`
- `modules/oom_sakkie/agent_dry_run_handoff.py`
- `modules/oom_sakkie/agent_dry_run_store.py`
- `modules/oom_sakkie/agent_dry_run_result_store.py`
- `modules/oom_sakkie/agent_dry_run_result_review.py`
- `modules/oom_sakkie/learning_influence_store.py`
- `modules/oom_sakkie/learning_influence_consumption_store.py`
- `modules/oom_sakkie/learning_influence_consumer.py`
- `modules/oom_sakkie/dispatch_execution_approval_store.py`
- `modules/oom_sakkie/sentinel_single_shot_runner.py`
- `modules/oom_sakkie/policy.py`
- `modules/oom_sakkie/patch_proposal_store.py`
- `modules/oom_sakkie/deploy_decision_store.py`
- `templates/oom-sakkie.html`
- `static/js/oomSakkie.js`
- `static/css/main.css`
- `tests/test_oom_sakkie_service.py`
- `tests/test_oom_sakkie_routes.py`
- `tests/test_frontend_route_contracts.py`
- `tests/oom_sakkie_browser_behavior_smoke.js`
- `tests/oom_sakkie_playwright_behavior.spec.js`
- `scripts/oom_sakkie_telegram_gateway_smoke.py`
- `scripts/oom_sakkie_telegram_private_relay_smoke.py`
- `scripts/oom_sakkie_n8n_relay_contract_check.py`
- `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/README.md`
- `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/workflow.json`
- `docs/04-n8n/WORKFLOW_MAP.md`
- `scripts/oom_sakkie_llm_router_diagnostic.py`
- `scripts/oom_sakkie_llm_router_smoke.py`
- `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`
- `docs/01-architecture/OOM_SAKKIE_VOICE_OPERATING_AGENT_PRD.md`
- `docs/01-architecture/JARVIS_EXTERNAL_REFERENCE_REVIEW.md`
- `docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md`
- `screenshots/Jarvis screen layout.mp4` (owner-provided visual reference; if local video tooling is unavailable, use the documented design intent in `NEXT_STEPS.md`)
- `supabase/migrations/202606060001_create_oom_sakkie_traces.sql`
- `supabase/migrations/202606060002_create_oom_sakkie_trace_feedback.sql`
- `supabase/migrations/202606060003_add_oom_sakkie_safety_notes.sql`
- `supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql`
- `supabase/migrations/202606070001_create_oom_sakkie_build_requests.sql`
- `supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql`
- `supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql`
- `supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql`
- `supabase/migrations/202606080001_create_oom_sakkie_agent_dry_runs.sql`
- `supabase/migrations/202606080002_create_oom_sakkie_agent_dry_run_results.sql`
- `supabase/migrations/202606090001_create_oom_sakkie_dispatch_decisions.sql`
- `supabase/migrations/202606090002_create_oom_sakkie_dispatch_execution_approvals.sql`
- `supabase/migrations/202606090003_allow_single_shot_sentinel_dry_run_results.sql`
- `supabase/migrations/202606100001_create_oom_sakkie_learning_influence_proposals.sql`
- `supabase/migrations/202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql`
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
- Added LLM Message Guard and safety follow-ups:
  - `/api/oom-sakkie/message` remains reachable wherever Flask is reachable while LLM router/answer features are off,
  - when an LLM surface is enabled, `/message` must pass the same loopback/private-LAN guard before outbound API calls can occur,
  - denied non-local LLM-enabled message requests return `status = message_access_denied`,
  - runtime policy exposes `message_endpoint_access.llm_guard_active` and `llm_guard_rule`,
  - the PRD now treats same-host reverse proxying in front of review routes as a hard deployment rule until trusted proxy handling is deliberately configured,
  - action guard now treats `irrigate` as a control verb and routes it to read-only `irrigation_status`,
  - added end-to-end `handle_message()` coverage proving unsafe LLM-composer output falls back to deterministic wording,
  - added DATABASE_URL-gated live Postgres CHECK-constraint coverage for build/patch/deploy no-action flags,
  - no write tools, live specialist dispatch, specialist LLM execution, autonomous loops, Builder/Forge execution, patch application, deploy, or farm-data mutation was added.
- Added Agent Dry-Run Request Gate:
  - migration `202606080001_create_oom_sakkie_agent_dry_runs.sql` creates `oom_sakkie_agent_dry_run_requests` and `oom_sakkie_agent_dry_run_events`,
  - DB constraints force `mode = read_only_dry_run_request_only`, `status = approved_for_read_only_dry_run`, and all execution flags false,
  - DB triggers make both dry-run tables append-only,
  - `modules/oom_sakkie/agent_dry_run_store.py` adds insert-only request/event recording and read-only queue listing,
  - only `sentinel` is approved for this first request-gate slice; other specialist slugs are rejected before any insert,
  - protected local-only routes expose `GET /api/oom-sakkie/agent-dry-runs`, `POST /api/oom-sakkie/agent-dry-runs`, and `POST /api/oom-sakkie/agent-dry-runs/<id>/events`,
  - read-only `agent_dry_run_status` lets Oom Sakkie answer dry-run queue/status questions,
  - kiosk quick action `Dry-Run Queue` asks `What is the agent dry-run queue status?`,
  - no specialist is dispatched, no specialist LLM is called, no specialist tool is executed, no autonomous loop is started, no farm data is written, and no Builder/Forge/patch/deploy action occurs.
- Added Message Guard Policy Consistency:
  - `modules/oom_sakkie/access.py` now exposes `is_llm_message_guard_active()`,
  - `is_message_request_allowed()` and runtime policy use the same guard source,
  - runtime policy exposes `message_endpoint_access.llm_guard_envs`,
  - guard wording now names router, answer composer, and learning analyst,
  - regression coverage proves `OOM_SAKKIE_LLM_LEARNING_ENABLED=true` makes policy report `message_endpoint_access.llm_guard_active = true`,
  - no route authority or safety boundary changed; this only makes the policy report match the already fail-safe access enforcement.
- Added Sentinel Dry-Run Handoff Packet:
  - `modules/oom_sakkie/agent_dry_run_handoff.py` builds `mode = agent_dry_run_handoff_only`,
  - `get_agent_dry_run_request()` loads dry-run requests by persisted ID,
  - protected `POST /api/oom-sakkie/agent-dry-runs/handoff` accepts only `dry_run_request_id`,
  - synthetic handoff payloads are not accepted by the route,
  - the builder rejects any request with truthy `dry_run_enabled`, `dispatch_enabled`, `runs_specialist_llm`, `runs_specialist_tools`, or `writes`,
  - the packet includes a Sentinel prompt that says not to claim inspection, not to call tools, not to produce code, and not to approve itself,
  - no specialist is run, no specialist LLM is called, no specialist tools are executed, no autonomous loop starts, no farm data is written, and no Builder/Forge/patch/deploy action occurs.
- Added Sentinel Dry-Run Result Gate:
  - migration `202606080002_create_oom_sakkie_agent_dry_run_results.sql` creates `oom_sakkie_agent_dry_run_results` and `oom_sakkie_agent_dry_run_result_events`,
  - DB constraints force `mode = dry_run_result_review_only`, `status = recorded_for_owner_review`, and all execution/runtime/write flags false,
  - DB triggers make both result tables append-only,
  - `modules/oom_sakkie/agent_dry_run_result_store.py` records result text and review events insert-only,
  - result recording requires a persisted Sentinel dry-run request,
  - protected routes expose result creation, result listing, and result review events,
  - result events are limited to `accepted_for_learning`, `rejected`, and `review_note`,
  - no specialist is run, no specialist LLM is called, no specialist tools are executed, no runtime change is applied, no farm data is written, and no Builder/Forge/patch/deploy action occurs.
- Added Sentinel Review Queue Status:
  - `agent_dry_run_status` now reads both dry-run requests and dry-run results,
  - summary reports request count, request review count, cancelled requests, result count, results waiting for owner review, and results accepted for learning,
  - unavailable request/result stores produce stale warnings instead of a confident empty queue,
  - runtime flags include `applies_runtime_change = false`,
  - deterministic routing catches Sentinel result/review queue phrasing,
  - the kiosk `Dry-Run Queue` quick action now asks for Sentinel dry-run result queue status,
  - no request/result/event is created by this tool and no specialist/runtime/write action occurs.
- Added Sentinel Dry-Run Result Review Packet:
  - `get_agent_dry_run_result()` looks up persisted dry-run result records by ID,
  - `modules/oom_sakkie/agent_dry_run_result_review.py` assembles a review-only packet with result text, findings, latest event, owner options, and guard flags,
  - `GET /api/oom-sakkie/agent-dry-run-results/<id>/review-packet` is loopback/private-LAN review-gated,
  - packet owner options are `accepted_for_learning`, `rejected`, and `review_note`,
  - all packet guard flags remain false for specialist execution, specialist LLM/tools, writes, runtime changes, Builder/Forge, patch, and deploy.
- Added Sentinel Result Review UI:
  - System Workbench now has a `Sentinel Result Review` panel,
  - the panel opens result review packets, renders packet fields with text-only DOM updates, and records append-only review events,
  - `review_note` remains pending; only `accepted_for_learning` and `rejected` close a result review row,
  - no review packet open or event button runs Sentinel, calls specialist LLM/tools, changes runtime, writes farm data, applies patches, or deploys.
- Added Agent Learning Evidence:
  - new read-only `agent_learning_evidence` tool summarizes accepted Sentinel result evidence only,
  - deterministic routing catches accepted-learning / Sentinel-learned phrasing,
  - kiosk quick checks include `Agent Learning`,
  - the tool reports accepted learning as planning evidence only and does not enable runtime, dispatch, tools, writes, or specialist LLM calls.
- Added Agent Learning Ledger UI:
  - System Workbench now has an `Agent Learning Ledger`,
  - the ledger displays accepted dry-run result evidence separately from pending/rejected/review-note-only results,
  - it is display-only and writes no review events by itself.
- Added Accepted Learning Roadmap Link:
  - `agent_activation_plan` now reads the same accepted-learning snapshot as `agent_learning_evidence`,
  - accepted Sentinel evidence can inform planning copy while the activation plan still reports runtime/dispatch/autonomous/write flags false,
  - tests cover that accepted learning is surfaced without unlocking runtime.
- Added Visible Agent Roadmap Panel:
  - protected `GET /api/oom-sakkie/agents/activation-plan` returns the locked activation plan plus accepted learning evidence,
  - kiosk `Agent Roadmap` panel renders the plan and guard flags,
  - the endpoint and panel remain read-only and review-gated.
- Added Sentinel Dry-Run Request Button:
  - roadmap panel includes `Request Sentinel Dry-Run`,
  - the button posts a fixed Sentinel-only, no-run payload to the existing append-only dry-run request endpoint,
  - the created request still has dry-run execution, dispatch, specialist LLM/tools, writes, patches, and deploys disabled.
- Added Sentinel Dry-Run Mini-Pipeline UI:
  - System Workbench now lists Sentinel dry-run requests,
  - request rows can open a persisted handoff packet and copy its prompt explicitly,
  - request rows can populate a result recorder form,
  - the result recorder stores owner-reviewed text/findings through the existing append-only result endpoint,
  - this UI still does not execute Sentinel, call specialist LLM/tools, change runtime, write farm data, invoke Builder/Forge, apply patches, or deploy.
- Added Workbench Sentinel Next Action:
  - Workbench `Next action` now includes pending Sentinel request handoffs and pending Sentinel result reviews,
  - Sentinel handoff/result-review items are prioritized before build/patch/deploy queues,
  - the card remains recommendation-only and does not trigger work by itself.
- Added Live-PG Audit Rail Smoke:
  - extended the DATABASE_URL-gated integration coverage for review-gate audit rails,
  - a real Postgres run can now insert a valid build/patch/deploy/agent dry-run audit chain,
  - the test asserts `UPDATE` and `DELETE` raise `append-only` on build request/event, patch proposal/event, deploy decision, agent dry-run request/event, agent dry-run result, and agent dry-run result event tables,
  - the no-execution CHECK test now also rejects `dry_run_enabled = true` on dry-run requests and `runs_specialist = true` on dry-run results,
  - normal local runs skip these checks when `DATABASE_URL` or `psycopg` is unavailable.
- Added Prism Dry-Run Request Gate:
  - approved dry-run request allowlist is now explicit: `sentinel`, `prism`,
  - Prism requests share the same append-only request -> handoff -> reviewed result rail,
  - Prism handoff prompt identifies Prism as the kiosk/interface design reviewer,
  - Prism results preserve `specialist_slug = prism` instead of being hard-coded as Sentinel,
  - Agent Roadmap includes `Request Prism Dry-Run`,
  - Prism still does not run, dispatch, call specialist LLM/tools, generate assets, edit code, write farm data, apply patches, or deploy.
- Added Generic Agent Dry-Run Workbench Labels:
  - live Workbench labels now read `Agent Dry-Run Requests`, `Record Agent Result`, and `Agent Result Review`,
  - next-action copy now says `agent handoff` / `agent result review`,
  - handoff cards use packet `specialist_name`, so Sentinel and Prism remain visible inside the shared rail,
  - this is UI wording only; no route, schema, write, dispatch, LLM, patch, or deploy authority changed.
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

- 10.9CR focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 318 OK, 1 DATABASE_URL-gated live test skipped in the no-dotenv run.
- 10.9CR migration apply: `.\venv\Scripts\python.exe scripts\apply_supabase_migration.py supabase\migrations\202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql` -> applied.
- 10.9CR live-PG audit suite with `.env` loaded: `.\venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); import unittest; ..."` -> 318 OK, including the new live Postgres consumption audit rail test.
- 10.9CR JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CR GitHub Actions after commit `0e64852`: `Oom Sakkie Browser Behavior` run `27332832970` success; `Oom Sakkie Audit Rails` run `27332832941` success.
- 10.9CS focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 323 OK.
- 10.9CS JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CS GitHub Actions after commit `a136d5f`: `Oom Sakkie Browser Behavior` run `27334034813` success; `Oom Sakkie Audit Rails` run `27334034805` success.
- 10.9CT focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 323 OK.
- 10.9CT JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CT live-gated focused audit suite with `.env` loaded -> 323 OK.
- 10.9CT browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CT full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 653 OK.
- 10.9CT GitHub Actions after commit `fbdcec0`: `Oom Sakkie Browser Behavior` run `27335044663` success; `Oom Sakkie Audit Rails` run `27335044655` success.
- 10.9CU focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 324 OK.
- 10.9CU JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CU live-gated focused audit suite with `.env` loaded -> 324 OK.
- 10.9CU browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CU full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 654 OK.
- 10.9CU GitHub Actions after commit `d6ca87b`: `Oom Sakkie Browser Behavior` run `27340979776` success; `Oom Sakkie Audit Rails` run `27340979805` success.
- 10.9CV focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 326 OK.
- 10.9CV JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CV live-gated focused audit suite with `.env` loaded -> 326 OK.
- 10.9CV browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CV full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 656 OK.
- 10.9CV GitHub Actions after commit `0db102a`: `Oom Sakkie Browser Behavior` run `27341856836` success; `Oom Sakkie Audit Rails` run `27341856819` success.
- 10.9CW focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 326 OK.
- 10.9CW JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CW live-gated focused audit suite with `.env` loaded -> 326 OK.
- 10.9CW browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CW full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 656 OK.
- 10.9CW GitHub Actions after commit `aaaa4a4`: `Oom Sakkie Browser Behavior` run `27345986022` success; `Oom Sakkie Audit Rails` run `27345985975` success.
- 10.9CX focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 326 OK.
- 10.9CX JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CX live-gated focused audit suite with `.env` loaded -> 326 OK.
- 10.9CX browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CX full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 656 OK.
- 10.9CX GitHub Actions after commit `049f37c`: `Oom Sakkie Browser Behavior` run `27354775052` success; `Oom Sakkie Audit Rails` run `27354774018` success.
- 10.9CY focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 330 OK.
- 10.9CY JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CY browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CY live-gated focused audit suite with `.env` loaded -> 330 OK.
- 10.9CY full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 660 OK.
- 10.9CY GitHub Actions after commit `7a2eaeb`: `Oom Sakkie Browser Behavior` run `27356904362` success; `Oom Sakkie Audit Rails` run `27356904836` success.
- 10.9CZ targeted guard tests: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service.OomSakkieServiceTests.test_learning_influence_consumption_has_no_production_allow_consumed_true_caller tests.test_oom_sakkie_service.OomSakkieServiceTests.test_learning_influence_consumer_design_packet_is_review_only` -> 2 OK.
- 10.9CZ focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 330 OK.
- 10.9CZ JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9CZ browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9CZ live-gated focused audit suite with `.env` loaded -> 330 OK.
- 10.9CZ full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 660 OK.
- 10.9CZ GitHub Actions after commit `d69ffdd`: `Oom Sakkie Browser Behavior` run `27361204620` success; `Oom Sakkie Audit Rails` run `27361204040` success.
- 10.9DA voice capture smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed with simulated Talk and Talk & Ask transcript paths.
- 10.9DA JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DA frontend route contracts: `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts` -> 28 OK.
- 10.9DA supervised live consumer smoke: route POST returned 201 `learning_influence_review_note_consumer_only`, replay returned 409 `already_consumed`, consumed marker count = 1, all apply/prompt/runtime/dispatch/write flags false.
- 10.9DA focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 330 OK.
- 10.9DA live-gated focused audit suite with `.env` loaded -> 330 OK.
- 10.9DA full local unittest suite: `.\venv\Scripts\python.exe -m unittest` -> 660 OK.
- 10.9DA GitHub Actions after commit `67f7add`: `Oom Sakkie Browser Behavior` run `27362607624` success; `Oom Sakkie Audit Rails` run `27362607693` success.
- 10.9DB/DC focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 344 OK.
- 10.9DB/DC JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DB/DC browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed, including backend STT fallback path.
- 10.9DC local gateway policy probe: `/api/oom-sakkie/policy` reports `telegram_gateway.enabled = true`, `sends_telegram = false`, `writes = false`, `direct_bot_cutover_enabled = false`, and backend voice STT enabled.
- 10.9DC live local Telegram gateway smoke: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_gateway_smoke.py` -> HTTP 200, `gateway_status = answered`, `sends_telegram = false`, `writes = false`, `dispatch_enabled = false`, tool `farm_attention_summary`.
- 10.9DD focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 347 OK.
- 10.9DD JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DD browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9DD route/service tests pin that `telegram_read_only` suppresses `route_with_llm` and `compose_answer_with_llm` while LLM env flags are enabled, and that gateway responses report `can_trigger_outbound_llm = false`.
- 10.9DD local policy probe with gateway + LLM router + LLM answer enabled: `telegram_gateway.enabled = true`, `allowed_user_ids_configured = true`, `deterministic_only = true`, `can_trigger_outbound_llm = false`, `llm_router.enabled = true`, `llm_answer.enabled = true`, `sends_telegram = false`, `writes = false`.
- 10.9DD live local Telegram gateway smoke with LLM surfaces enabled and allowlisted smoke user: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_gateway_smoke.py` -> HTTP 200, `gateway_status = answered`, `sends_telegram = false`, `can_trigger_outbound_llm = false`, `writes = false`, `dispatch_enabled = false`, tool `farm_attention_summary`.
- 10.9DD live local Telegram gateway smoke with non-allowlisted user: HTTP 403 `telegram_user_not_allowed`, `sends_telegram = false`, `can_trigger_outbound_llm = false`, `writes = false`.
- 10.9DE focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 353 OK.
- 10.9DE gateway hardening tests prove short configured tokens fail closed with `telegram_gateway_token_too_short`, missing `OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS` fails closed with `telegram_gateway_allowed_user_ids_required`, repeated bad tokens lock the endpoint with `telegram_gateway_auth_rate_limited`, the policy/result expose `records_audit_trace = true`, and a true no-HTTP-egress test patches `urllib.request.urlopen` while `telegram_read_only` handles a message with all LLM env flags enabled.
- 10.9DF focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 357 OK.
- 10.9DF preflight tests prove protected `GET /api/oom-sakkie/channels/telegram/exposure-preflight` is loopback/review-gated, reports `private_test_ready` from automated token/allowlist/no-egress/no-send/no-write checks, reports `public_exposure_ready` only after explicit TLS and rate-limit-model confirmations, and keeps all send/dispatch/write/runtime authority flags false.
- 10.9DG focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 357 OK.
- 10.9DG JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DG browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9DG private relay smoke helper: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py` -> preflight `private_test_ready = True`, `public_exposure_ready = False`; gateway HTTP 200 `answered`, `sends_telegram = False`, `can_trigger_outbound_llm = False`, `writes = False`, `records_audit_trace = True`, `reply_transport = caller_handles_telegram_send`.
- 10.9DH focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 357 OK.
- 10.9DH private relay smoke helper still passes on local HTTP: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py` -> preflight `private_test_ready = True`, `public_exposure_ready = False`; gateway HTTP 200 `answered`, no send/LLM/write authority.
- 10.9DH URL guard negative check: setting `OOM_SAKKIE_TELEGRAM_RELAY_SMOKE_BASE_URL=http://example.com` returns `ERROR: use localhost/127.0.0.1 for HTTP smoke URLs, or HTTPS for remote/private endpoints.` before sending the token.
- 10.9DI frontend route contracts: `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts` -> 29 OK, including the new n8n relay workflow JSON contract.
- 10.9DI focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 358 OK.
- 10.9DI JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DI browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9DI relay workflow JSON parse: `.\venv\Scripts\python.exe -m json.tool "docs\04-n8n\workflows\2.0B - Oom Sakkie Backend Read-Only Relay\workflow.json"` -> OK.
- 10.9DI local private relay smoke: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py` -> preflight `private_test_ready = True`, `public_exposure_ready = False`; gateway HTTP 200 `answered`, `sends_telegram = False`, `can_trigger_outbound_llm = False`, `writes = False`, `records_audit_trace = True`.
- 10.9DJ frontend route contracts: `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts` -> 29 OK.
- 10.9DJ focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 358 OK.
- 10.9DJ JavaScript syntax: `node --check static/js/oomSakkie.js` -> OK.
- 10.9DJ browser behavior smoke: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed.
- 10.9DJ relay workflow JSON parse: `.\venv\Scripts\python.exe -m json.tool "docs\04-n8n\workflows\2.0B - Oom Sakkie Backend Read-Only Relay\workflow.json"` -> OK.
- 10.9DJ local private relay smoke: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py` -> preflight `private_test_ready = True`, `public_exposure_ready = False`; gateway HTTP 200 `answered`, `sends_telegram = False`, `can_trigger_outbound_llm = False`, `writes = False`, `records_audit_trace = True`.
- 10.9DK relay import preflight: `.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_contract_check.py` -> `relay_contract_status: ok`, inactive, no Telegram trigger/send node, localhost-or-HTTPS transport guard, authority validation present.
- 10.9DK frontend route contracts: `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts` -> 29 OK.
- 10.9DK focused audit suite: `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 358 OK.
- 10.9DK local private relay smoke: `.\venv\Scripts\python.exe scripts\oom_sakkie_telegram_private_relay_smoke.py` -> preflight `private_test_ready = True`, `public_exposure_ready = False`; gateway HTTP 200 `answered`, `sends_telegram = False`, `can_trigger_outbound_llm = False`, `writes = False`, `records_audit_trace = True`.
- 10.9DL Workbench learning-backlog clarity: `node --check static/js/oomSakkie.js` -> OK; `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed; `.\venv\Scripts\python.exe -m unittest tests.test_frontend_route_contracts` -> 29 OK; `.\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 358 OK.
- 10.9DM GateKeeper backend-relay wiring plan: `.\venv\Scripts\python.exe scripts\oom_sakkie_n8n_relay_contract_check.py` -> `relay_contract_status: ok`; `.\venv\Scripts\python.exe -m unittest tests.test_workflow_contracts` -> 23 OK.
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
- LLM Message Guard focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 161 tests OK
- `node --check static/js/oomSakkie.js` passed after LLM Message Guard
- Full local unittest suite after LLM Message Guard: `486 tests OK`
- Agent Dry-Run Request Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 170 tests OK
- Applied migration `supabase/migrations/202606080001_create_oom_sakkie_agent_dry_runs.sql`
- Live-style dry-run gate smoke created request `OSK-AGENT-DRYRUN-B2E07585AD` and event `OSK-AGENT-DRYRUN-EVENT-0542A235E334`; returned `dry_run_enabled = false`, `dispatch_enabled = false`, `runs_specialist_llm = false`, `runs_specialist_tools = false`, and `writes = false`
- `node --check static/js/oomSakkie.js` passed after Agent Dry-Run Request Gate
- Full local unittest suite after Agent Dry-Run Request Gate: `495 tests OK`
- Message Guard Policy Consistency focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 171 tests OK
- `node --check static/js/oomSakkie.js` passed after Message Guard Policy Consistency
- Full local unittest suite after Message Guard Policy Consistency: `496 tests OK`
- Sentinel Dry-Run Handoff Packet focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 174 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Dry-Run Handoff Packet
- Full local unittest suite after Sentinel Dry-Run Handoff Packet: `499 tests OK`
- Sentinel Dry-Run Result Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 181 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Dry-Run Result Gate
- Applied migration `supabase/migrations/202606080002_create_oom_sakkie_agent_dry_run_results.sql`
- Live-style dry-run result smoke created result `OSK-AGENT-DRYRUN-RESULT-2FBFA47000FC` and event `OSK-AGENT-DRYRUN-RESULT-EVENT-4DADAE8AD1B3`; all execution/runtime/write flags were false
- Full local unittest suite after Sentinel Dry-Run Result Gate: `506 tests OK`
- Sentinel Review Queue Status focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 182 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Review Queue Status
- Full local unittest suite after Sentinel Review Queue Status: `507 tests OK`
- Sentinel Dry-Run Result Review Packet focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 184 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Dry-Run Result Review Packet
- Sentinel Result Review UI focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 185 tests OK
- `node --check static/js/oomSakkie.js` passed after Sentinel Result Review UI
- Full local unittest suite after Sentinel Result Review UI: `512 tests OK`
- Agent Learning Evidence focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 187 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Learning Evidence
- Agent Learning Ledger UI focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 187 tests OK
- Full local unittest suite after Agent Learning Ledger UI: `518 tests OK`
- Accepted Learning Roadmap Link focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 188 tests OK
- Full local unittest suite after Accepted Learning Roadmap Link: `518 tests OK`
- Visible Agent Roadmap Panel focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 190 tests OK
- Full local unittest suite after Visible Agent Roadmap Panel: `520 tests OK`
- Sentinel Dry-Run Request Button focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 191 tests OK
- Full local unittest suite after Sentinel Dry-Run Request Button: `521 tests OK`
- Sentinel Dry-Run Mini-Pipeline UI focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 191 tests OK
- Full local unittest suite after Sentinel Dry-Run Mini-Pipeline UI: `521 tests OK`
- Workbench Sentinel Next Action focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 191 tests OK
- `node --check static/js/oomSakkie.js` passed after Workbench Sentinel Next Action
- Full local unittest suite after Workbench Sentinel Next Action: `521 tests OK`
- Live-PG Audit Rail Smoke focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 192 tests OK (`DATABASE_URL`-gated live checks skip when not configured)
- `node --check static/js/oomSakkie.js` passed after Live-PG Audit Rail Smoke
- Prism Dry-Run Request Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 196 tests OK
- `node --check static/js/oomSakkie.js` passed after Prism Dry-Run Request Gate
- Generic Agent Dry-Run Workbench Labels focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 196 tests OK
- `node --check static/js/oomSakkie.js` passed after Generic Agent Dry-Run Workbench Labels
- Agent Dry-Run Browser Behavior Contracts focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 197 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Dry-Run Browser Behavior Contracts
- Approved Read-Only Dry-Run Cohort focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 200 tests OK
- `node --check static/js/oomSakkie.js` passed after Approved Read-Only Dry-Run Cohort
- Activation Roadmap Cohort Visibility focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 200 tests OK
- `node --check static/js/oomSakkie.js` passed after Activation Roadmap Cohort Visibility
- Specialist Dry-Run Handoff Quality focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 201 tests OK
- `node --check static/js/oomSakkie.js` passed after Specialist Dry-Run Handoff Quality
- Specialist Result Evidence Boundaries focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 203 tests OK
- `node --check static/js/oomSakkie.js` passed after Specialist Result Evidence Boundaries
- Per-Specialist Dry-Run Queue Status focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 203 tests OK
- `node --check static/js/oomSakkie.js` passed after Per-Specialist Dry-Run Queue Status
- Generic Agent Learning Evidence focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 203 tests OK
- `node --check static/js/oomSakkie.js` passed after Generic Agent Learning Evidence
- Roadmap Learning Counts focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 203 tests OK
- `node --check static/js/oomSakkie.js` passed after Roadmap Learning Counts
- Audit Rail CI Workflow / Browser Behavior Checklist focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 204 tests OK
- `node --check static/js/oomSakkie.js` passed after Audit Rail CI Workflow / Browser Behavior Checklist
- Audit Rail CI Scope Hardening focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 204 tests OK
- Audit Rail CI Scope Hardening full local verification: `python -m unittest` -> 534 tests OK
- `node --check static/js/oomSakkie.js` passed after Audit Rail CI Scope Hardening
- Agent Runtime Readiness Tool focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 206 tests OK
- `node --check static/js/oomSakkie.js` passed after Agent Runtime Readiness Tool
- Browser Behavior Smoke Gate local verification: `node tests/oom_sakkie_browser_behavior_smoke.js` -> passed
- Browser Behavior Smoke Gate focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 207 tests OK
- Browser Behavior Smoke Gate full local verification: `python -m unittest` -> 537 tests OK
- `node --check static/js/oomSakkie.js` passed after Browser Behavior Smoke Gate
- Agent Operating Contracts focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 209 tests OK
- Agent Contracts Review Endpoint focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 211 tests OK
- Agent Activation Preflight focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 215 tests OK
- Agent Authority Matrix focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 219 tests OK
- Authority Lock Source Alignment focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 220 tests OK
- Authority Unlock Readiness / Runtime Invariant focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 225 tests OK
- Dispatch Decision Rail Blueprint focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 229 tests OK
- Agent Runtime Review Packet focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 233 tests OK
- Playwright Browser Behavior Gate local verification: `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 233 tests OK; `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed; `node --check playwright.config.js` passed. Actual browser execution is expected in GitHub Actions or local environment after `npm install` / browser install.
- Dispatch Decision Rail focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 242 tests OK. Migration file is present and CI-wired, but not applied to the local/live database in this turn.
- Dispatch Decision Status Visibility focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 243 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed; full local `python -m unittest` -> 573 tests OK.
- Dispatch Runtime Review Packet focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 244 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed; full local `python -m unittest` -> 574 tests OK.
- Jarvis Product Progress focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 246 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed; full local `python -m unittest` -> 576 tests OK.
- Agent Command Center focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 248 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed; full local `python -m unittest` -> 578 tests OK.
- Command Center Quick Action focused verification: `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 249 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed; full local `python -m unittest` -> 579 tests OK.
- Playwright CI Startup Hardening focused verification: `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK; `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 249 tests OK; `node --check static/js/oomSakkie.js`, `node --check tests/oom_sakkie_playwright_behavior.spec.js`, `node --check playwright.config.js`, and `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Daily Command Brief focused verification: `python -m unittest tests.test_oom_sakkie_service` -> 149 tests OK, 3 skipped live-DB gates; `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK; `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 252 tests OK; `node --check static/js/oomSakkie.js` and `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Playwright CI Node 24 / Server URL Hardening focused verification: `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK; `node --check playwright.config.js` and `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
- Playwright Workbench Visibility Fix focused verification: `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK; `node --check tests/oom_sakkie_playwright_behavior.spec.js` and `node --check playwright.config.js` passed.
- Audit Rail CI Node 24 Warning Cleanup focused verification: `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
- Safety Gate Board focused verification:
  - `python -m unittest tests.test_oom_sakkie_service` -> 152 tests OK, 3 expected live-DB skips
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 255 tests OK
  - `node --check static/js/oomSakkie.js` passed
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed
- Owner Review Packet focused verification:
  - `python -m unittest tests.test_oom_sakkie_service` -> 155 tests OK, 3 expected live-DB skips
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK
  - `node --check static/js/oomSakkie.js` passed
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed
  - Full local unittest suite: `python -m unittest` -> 588 tests OK
  - Full local unittest suite: `python -m unittest` -> 588 tests OK
- Review Shortcuts focused verification:
  - `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK
  - `node --check static/js/oomSakkie.js` passed
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed
- Quick Checks Grouping focused verification:
  - `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 258 tests OK
  - `node --check static/js/oomSakkie.js` passed
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed
- CI Green Evidence verification:
  - Portable GitHub CLI installed under ignored local tooling path `.tools/gh/bin/gh.exe`; `.tools/` is ignored and is not part of the app/runtime.
  - `gh auth status` confirms authenticated GitHub account `Crewless9086` with `repo` and `workflow` scopes.
  - Latest `main` push workflow evidence from `.\.tools\gh\bin\gh.exe run list --branch main --limit 8` after commit `613085b`:
    - `Oom Sakkie Browser Behavior`, run `27278530296`, completed `success`, created `2026-06-10T13:09:04Z`.
    - `Oom Sakkie Audit Rails`, run `27278529740`, completed `success`, created `2026-06-10T13:09:03Z`.
  - Detailed `gh run view` confirms the successful jobs were `Playwright real-browser behavior gate` and `Unit tests with disposable Postgres audit rails`.
  - This is owner/operator evidence only. The runtime still does not call GitHub, trust remote CI automatically, add routes/stores/DB writes, dispatch agents, run specialist LLM/tools, write farm data, produce public output, deploy, cut over Telegram, or control hardware.
- Dispatch Execution Approval Rail focused verification:
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 267 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 597 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node --check playwright.config.js` passed.
  - The new migration is wired into the disposable-Postgres audit workflow, but the live CI run for this exact phase is pending until push.
- Sentinel Single-Shot Advisory Runner focused verification:
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 278 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 608 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node --check playwright.config.js` passed.
  - The new migrations `202606090002` and `202606090003` are wired into the disposable-Postgres audit workflow, but the live CI run for this exact phase is pending until push.
- Sentinel Runner Review Hardening focused verification:
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 278 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 608 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node --check playwright.config.js` passed.
  - The default-off Sentinel runner test now patches the outbound HTTP path and asserts no network call occurs while `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED` is off.
  - The authority-matrix tests now assert `specialist_llm_loop.current_state = single_shot_advisory_only`, `specialist_llm_loop.enabled = false`, top-level `specialist_llm_enabled = false`, and every other authority remains locked.
- Effective Single-Shot Visibility focused verification:
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 279 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 609 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node --check playwright.config.js` passed.
  - Tests now assert the matrix reports `effective_single_shot_enabled/configured` from the env/policy while keeping `specialist_llm_loop.enabled = false`, `enabled_count = 0`, and top-level `specialist_llm_enabled = false`.
- First Sentinel Smoke And Review Packet Fix verification:
  - Owner approved the supervised smoke.
  - Temporary smoke server ran with `OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED=1`; the normal kiosk was later verified with `specialist_dry_run.enabled = false`.
  - Smoke chain: dry-run request `OSK-AGENT-DRYRUN-499E983FAF`, dispatch request `OSK-DISPATCH-REQ-3234DBAB07`, execution approval `OSK-DISPATCH-EXEC-APPROVAL-SMOKE-20260609-CODEX1`, consumed event `OSK-DISPATCH-EXEC-EVENT-6D892274A9`, result `OSK-AGENT-DRYRUN-RESULT-C63AF980E948`.
  - First run returned `201` and advisory-only Sentinel text/findings.
  - Result review packet returned `200` after the narrow review-packet fix.
  - Replay returned `409 dispatch_execution_approval_already_consumed`.
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 281 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 611 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node --check playwright.config.js` passed.
- Owner Approval Console focused verification:
  - `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 254 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Controller Board / Primary Command Deck / Quick Checks Drawer focused verification:
  - `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 254 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Command UI Browser Gate Hardening focused verification:
  - `node --check static/js/oomSakkie.js` passed.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `python -m unittest tests.test_frontend_route_contracts` -> 27 tests OK.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
- Owner Cockpit UI focused verification:
  - `node --check static/js/oomSakkie.js` passed.
  - `node --check tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `python -m unittest tests.test_frontend_route_contracts` -> 28 tests OK.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts` -> 293 tests OK, 1 live-DB skip.
  - `python -m unittest` -> 623 tests OK, 1 live-DB skip.
  - The first-screen cockpit now shows one primary decision, ID search/jump, and a compact queue while the full System Workbench remains available through `Audit Trail`.
  - Direct cockpit actions are limited to append-only agent-result evidence events (`accepted_for_learning` / `rejected`) and append-only learning-proposal review events (`approved_for_future_planning` / `rejected`).
  - Build/patch/deploy/dry-run handoff/proposal generation actions still open detailed Workbench sections and do not run from the first-screen cockpit.
- Owner Cockpit Decision Feedback focused verification:
  - Local review packet for `OSK-AGENT-DRYRUN-RESULT-C63AF980E948` confirmed `latest_event.event_type = accepted_for_learning`, `recorded_by = owner`.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest tests.test_frontend_route_contracts` -> 28 tests OK.
  - Cockpit event handlers now await append-only event responses, refresh result/proposal queues, and write visible status messages that say evidence/planning only with no runtime change or learning application.
- Cockpit Accepted-Result Proposal Prep focused verification:
  - `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 297 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node --check tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - Full local unittest suite: `python -m unittest` -> 627 tests OK.
  - Browser smoke and Playwright spec now assert the `from-result` request includes the exact clicked `source_result_id`.
- Owner Review Packet Scope Evidence / Chat Gate focused verification:
  - `python -m unittest tests.test_frontend_route_contracts tests.test_oom_sakkie_service tests.test_oom_sakkie_routes` -> 298 tests OK.
  - `node --check static/js/oomSakkie.js` passed.
  - `node tests/oom_sakkie_browser_behavior_smoke.js` passed.
  - `python -m unittest` -> 628 tests OK.
  - `node --check tests/oom_sakkie_playwright_behavior.spec.js` passed.
  - GitHub Actions after commit `5de5d9d`: `Oom Sakkie Browser Behavior` run `27314056906` success, `Oom Sakkie Audit Rails` run `27314056931` success.
  - The read-only `jarvis_owner_review_packet` now exposes scope `Oom Sakkie 10.6 through 10.9CM`, the exact handoff prompt, latest green CI evidence, no learning influence consumer, and false apply/prompt/runtime flags.
  - The `prepare Claude review` service test proves deterministic routing to `jarvis_owner_review_packet`, answer scope naming, safety wording, visible Gatekeeper workspace, and no run/dispatch/write authority.
- Claude review response / Learning Influence Live-PG Closure:
  - Claude reviewed 10.9CA-CM and returned verdict `pass`, with no blocking findings.
  - Claude's concrete next step was to apply migration `202606100001_create_oom_sakkie_learning_influence_proposals.sql` to live Postgres and add live-PG coverage for the `from-result` 409 guard and `on conflict do nothing` idempotency.
  - Applied migration with `python scripts/apply_supabase_migration.py supabase/migrations/202606100001_create_oom_sakkie_learning_influence_proposals.sql` -> applied.
  - `python -c "from dotenv import load_dotenv; load_dotenv('.env'); ... test_live_pg_learning_influence_from_result_requires_acceptance_and_is_idempotent"` -> 1 live-PG test OK.
  - Existing plus new learning-influence live-PG tests -> 2 tests OK.
  - Route contract tests for `/agent-learning/influence-proposals/from-result` now cover success, 409 not-accepted guard propagation, and existing-proposal `created_count = 0` response, all with false apply/prompt/runtime/dispatch/write flags.
  - The read-only `jarvis_owner_review_packet` now exposes scope `Oom Sakkie 10.6 through 10.9CO`, with focus on the live-PG guard/idempotency proof and no learning influence consumer.
- Recorded CI Evidence / Learning Consumption Threat Model:
  - Claude reviewed 10.9CO and returned verdict `pass`; this cleared only the live-PG closure and did not authorize learning proposal consumption or runtime authority.
  - `CURRENT_CLAUDE_REVIEW_CI_EVIDENCE` now uses `recorded_commit` plus `ci_evidence_policy` (`mode = recorded_operator_evidence_only`, `runtime_calls_github = false`, `auto_trusts_ci = false`) so the packet is honest that green run IDs are recorded evidence and may trail newer commits.
  - Added read-only `get_learning_influence_consumption_readiness()`, tool `learning_influence_consumption_readiness`, and protected `GET /api/oom-sakkie/agent-learning/consumption-readiness`.
  - The readiness packet lists allowed future scope, hard no-go scope, threat scenarios for prompt/route poisoning, authority creep, stale evidence, replay/idempotency, and rollback gaps, plus required gates before any consumer design.
  - Tests pin that the readiness packet/tool/route keep `learning_influence_consumer_enabled`, `applies_learning_now`, `changes_prompt_now`, `changes_runtime_now`, dispatch, specialist LLM/tools, writes, public output, physical controls, and runtime flags false.
- Learning Consumption Threat Model Follow-Up / Audit Rail Blueprint:
  - Claude reviewed 10.9CO/10.9CP and returned verdict `pass`, clearing only the checkpoint and explicitly not authorizing a consumer.
  - Claude asked to carry two extra threat items into the next review: evidence provenance/integrity because proposal text may be LLM-produced untrusted input, and blast-radius bounds so one consumption touches at most one allowlisted target field with a size-capped reviewable diff.
  - The readiness packet now includes `evidence_provenance_and_integrity` and `oversized_or_multi_target_blast_radius` threat scenarios plus gates `untrusted_proposal_text_policy`, `one_target_field_per_consumption`, and `size_capped_reviewable_diff`.
  - Added read-only `get_learning_influence_consumption_audit_rail_blueprint()`, tool `learning_influence_consumption_audit_rail_blueprint`, deterministic routing, and protected `GET /api/oom-sakkie/agent-learning/consumption-audit-rail-blueprint`.
  - The blueprint proposes request/event table shapes, target-field allowlist contract, untrusted proposal-text handling, size-capped diff requirements, live-PG tests, and route tests for a future implementation slice.
  - This is blueprint-only: `creates_tables_now = false`, `adds_routes_now = false`, `learning_influence_consumer_enabled = false`, and all apply/prompt/runtime/dispatch/write flags remain false. No migration, store, event writer, or consumer was added.
- Learning Consumption Audit Rail Implementation:
  - Claude reviewed 10.9CQ and returned verdict `pass`, clearing implementation of the append-only audit rail only; Claude explicitly recommended no consumer, no diff application, and review-note-only records for this slice.
  - Added migration `202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql`.
  - Added `modules/oom_sakkie/learning_influence_consumption_store.py`.
  - Added protected routes:
    - `GET /api/oom-sakkie/agent-learning/consumption-requests`,
    - `POST /api/oom-sakkie/agent-learning/consumption-requests`,
    - `POST /api/oom-sakkie/agent-learning/consumption-requests/<consumption_request_id>/events`.
  - Request creation requires the source proposal's latest event to be `approved_for_future_planning`; otherwise it returns `409 proposal_not_approved_for_future_planning`.
  - Request records are limited to one allowlisted target kind/field and include a `review_note_only` artifact that treats proposal text as untrusted and preserves source provenance.
  - The generic event route rejects `consumed_for_patch_proposal` with `403 consumed_event_is_future_consumer_only`; that marker is DB-defined and tested for a later reviewed consumer path only.
  - The migration forces `applies_learning_now = false`, `changes_prompt_now = false`, `changes_runtime_now = false`, `dispatch_enabled = false`, and `writes = false` on both request and event tables, blocks update/delete, and enforces one consumed marker per request through partial unique index `idx_oom_sakkie_learning_consumption_consumed_once`.
  - The audit rail status now reports `creates_tables_now = true`, `adds_routes_now = true`, `review_note_only_first_slice = true`, and still reports `learning_influence_consumer_enabled = false` with no apply/prompt/runtime/dispatch/write authority.
  - New live-PG coverage proves: non-approved proposal rejects, approved proposal creates one request, repeated same target returns existing request with `created_count = 0`, review notes do not consume, second consumed marker fails, and update/delete on both new tables raises append-only errors.
  - GitHub Actions for commit `0e64852` are green: Browser Behavior run `27332832970`, Audit Rails run `27332832941`.
- Learning Consumer Design Static Guard:
  - Claude reviewed 10.9CR and returned verdict `pass`, with one next-slice recommendation before any consumer: add a regression test asserting no production module calls `record_learning_influence_consumption_event(..., allow_consumed=True)`.
  - Added a static AST test over `modules/**/*.py`; it fails if any production caller passes `allow_consumed=True` to the learning-consumption event writer.
  - Added read-only `get_learning_influence_consumer_design_packet()`, tool `learning_influence_consumer_design_packet`, deterministic routing for consumer-design / allow-consumed guard questions, and protected `GET /api/oom-sakkie/agent-learning/consumer-design-packet`.
  - The design packet answers the next consumer gate questions: only an approved-for-design-review request could later call the marker, first output must be `review_note_artifact_only`, proposal text remains untrusted, one target field is allowed, rollback/manual-application artifacts are required, and manual application stays outside the kiosk.
  - This is design/static-guard only: `allow_consumed_production_callers = []`, `learning_influence_consumer_enabled = false`, and no consumer or applyable diff exists.
  - GitHub Actions for commit `a136d5f` are green: Browser Behavior run `27334034813`, Audit Rails run `27334034805`.
- Hardened Allow-Consumed Static Guard:
  - Claude reviewed 10.9CS with verdict `pass` and one low-priority hardening nit: the guard should also catch aliased imports, positional fourth-argument `True`, and truthy variables.
  - The AST guard now tracks direct imports, aliased imports, module imports, and module-attribute calls to `record_learning_influence_consumption_event`.
  - The guard now flags positional fourth arguments, `**kwargs`, and any `allow_consumed` value that is not literal `False`.
  - The consumer-design packet's static guard wording now describes this stronger behavior.
  - GitHub Actions for commit `fbdcec0` are green: Browser Behavior run `27335044663`, Audit Rails run `27335044655`.
- Source-Backed Allow-Consumed Caller Evidence:
  - Claude's carried-forward nit that `allow_consumed_production_callers = []` was documentation-only is now closed defensively.
  - The consumer-design packet now calls `find_learning_influence_allow_consumed_callers()` so `allow_consumed_production_callers` is source-backed by the same AST scanner used by the static regression guard.
  - The scanner lives in `agent_runtime.py` and is unit-tested with synthetic direct/alias/module/positional/`**kwargs`/non-literal-false examples, while literal `allow_consumed=False` remains allowed.
  - This is evidence/test/packet hardening only: no consumer, no production `allow_consumed` caller, no applyable diff, and no authority was added.
  - GitHub Actions for commit `d6ca87b` are green: Browser Behavior run `27340979776`, Audit Rails run `27340979805`.
- Allow-Consumed Scanner Resilience:
  - Claude reviewed 10.9CU with verdict `pass` and two low-priority robustness nits: guard `ast.parse` and make the scanner independent of process CWD.
  - `find_learning_influence_allow_consumed_callers()` now resolves the default relative `modules` root from `agent_runtime.py`'s repo location instead of the live process CWD.
  - Syntax errors in scanned Python files now produce explicit `:parse_error` findings instead of raising from the packet route.
  - New regression tests prove the default scan still works after `os.chdir()` to a temporary directory and that a syntactically invalid scanned file returns a `:parse_error` marker.
  - This is scanner/test/packet hardening only: no consumer, no production `allow_consumed` caller, no applyable diff, and no authority was added.
  - GitHub Actions for commit `0db102a` are green: Browser Behavior run `27341856836`, Audit Rails run `27341856819`.
- Read-Only Consumer Design Agreement:
  - Claude reviewed 10.9CV with verdict `pass` and said the next step is consumer design review, not consumer code.
  - The existing read-only consumer design packet now includes `consumer_design_review_agreement` with `implementation_authorized_now = false` and `allow_consumed_true_authorized_now = false`.
  - The agreement pins the review-note artifact shape, required source provenance, forbidden patch/write/public-output fields, ordered `must_recheck_before_marker` sequence, failure behavior that writes no consumed marker, rollback artifact contract, and the required future static-guard update.
  - Route and service tests pin that the agreement is exposed only as read-only design data and still has no consumer, no production `allow_consumed` caller, no applyable diff, and no authority.
  - GitHub Actions for commit `aaaa4a4` are green: Browser Behavior run `27345986022`, Audit Rails run `27345985975`.
- Consumed-Once Atomicity Wording:
  - Claude reviewed 10.9CW with verdict `pass` and one spec refinement: do not let the future consumer treat the step-5 application read as the race guard.
  - The design agreement now says `idx_oom_sakkie_learning_consumption_consumed_once` is the authoritative atomic race guard for `consumed_for_patch_proposal`.
  - The agreement now requires unique-violation at marker write to return `already_consumed` and produce no second review-note artifact.
  - Route and service tests pin this TOCTOU wording while still asserting no consumer, no production `allow_consumed` caller, no applyable diff, and no authority.
  - GitHub Actions for commit `049f37c` are green: Browser Behavior run `27354775052`, Audit Rails run `27354774018`.
- Review-Note Consumer Implementation:
  - The owner explicitly approved the 10.9CW/CX consumer design agreement before this slice.
  - Added `modules/oom_sakkie/learning_influence_consumer.py` and protected `POST /api/oom-sakkie/agent-learning/consumption-requests/<consumption_request_id>/review-note-artifact`.
  - The consumer is the single reviewed `allow_consumed=True` caller; the shared AST scanner still reports unreviewed production callers as `[]` and separately lists the reviewed consumer call site.
  - The consumer requires the consumption request latest event to be `approved_for_design_review`, the source proposal latest event to still be `approved_for_future_planning`, the target kind/field to remain allowlisted, and no prior consumed marker.
  - The DB partial unique index remains the authoritative consumed-once race guard; a unique violation or repeat call returns `already_consumed` with no second artifact.
  - The output is `review_note_artifact_only` with source provenance, untrusted-proposal marking, rollback artifact, manual-application-outside-kiosk flag, and all apply/prompt/runtime/dispatch/write flags false.
  - This does not apply learning, produce an applyable prompt/route/runtime diff, mutate prompts/routes/runtime/tools/farm data, create public output, deploy, touch Telegram, control hardware, or perform financial actions.
- Call-Site Guard Hardening:
  - Claude reviewed 10.9CY with verdict `pass-with-nits` and asked to make the reviewed `allow_consumed=True` allowlist call-site granular.
  - `find_learning_influence_allow_consumed_callers()` now uses an internal all-call-site scan and filters only exact normalized reviewed paths, not arbitrary substring matches.
  - `find_reviewed_learning_influence_allow_consumed_callers()` exposes the reviewed call sites separately.
  - Tests assert unreviewed production callers are still `[]`, the reviewed set has exactly one call site, and a path containing the allowlisted string in the wrong location is not treated as reviewed.
  - This is static-guard/packet hardening only; it adds no second consumer and no applyable prompt/route/runtime diff or authority.
- Browser Voice Capture And Live Consumer Smoke:
  - Added browser smoke coverage with a fake Web Speech recognizer. `Talk` must put the recognized transcript in the input without POSTing, and `Talk & Ask` must POST only after recognized text plus the 2-second cancel window.
  - Kiosk voice errors now explain common causes: microphone permission blocked, unsupported browser, no speech, missing audio input, or network/service failure.
  - Ran the owner-approved supervised live consumer smoke against configured Postgres through the protected Flask route. It created isolated smoke records, approved design review, POSTed the review-note artifact route, replayed the same route, and counted consumed markers.
  - Evidence: `OSK-LEARNING-CONSUME-69FA189A6E4C` returned first status 201 / replay 409 / consumed marker count 1 / all authority flags false.
  - This is browser reliability and smoke evidence only; no Telegram path, no second consumer, and no applyable prompt/route/runtime diff or authority was added.
- Applied Supabase migrations through `202606090003_allow_single_shot_sentinel_dry_run_results.sql` for the local supervised Sentinel smoke.
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
61. **LLM Message Guard:** Does Phase 10.9I correctly keep `/api/oom-sakkie/message` open for deterministic local use while LLM flags are off, but require the local/private-LAN guard when LLM router/answer features are enabled so non-local unauthenticated callers cannot create outbound paid API calls?
62. **Agent Dry-Run Request Gate:** Does Phase 10.9J create an append-only owner-approved Sentinel dry-run request/event rail while keeping `dry_run_enabled`, `dispatch_enabled`, `runs_specialist_llm`, `runs_specialist_tools`, and `writes` false at both DB and application layers?
63. **Message Guard Policy Consistency:** Does Phase 10.9K make `/api/oom-sakkie/policy` report the same router/answer/learning env set that `access.py` uses to enforce `/api/oom-sakkie/message` local/private-LAN guarding?
64. **Sentinel Dry-Run Handoff Packet:** Does Phase 10.9L require a persisted `dry_run_request_id` before generating a handoff, reject unsafe execution flags, and remain packet/prompt-only with no Sentinel execution, specialist LLM calls, specialist tool execution, writes, Builder/Forge execution, patch application, or deploy?
65. **Sentinel Dry-Run Result Gate:** Does Phase 10.9M record future dry-run results append-only for owner review while keeping specialist execution, dispatch, specialist LLM calls, specialist tool execution, runtime changes, writes, Builder/Forge execution, patch application, and deploy disabled at DB and application layers?
66. **Sentinel Review Queue Status:** Does Phase 10.9N make dry-run request/result review state visible through read-only chat/quick-action status while avoiding hidden writes, result acceptance, specialist execution, LLM calls, specialist tool execution, runtime changes, Builder/Forge execution, patch application, or deploy?
67. **Sentinel Dry-Run Result Review Packet:** Does Phase 10.9O require a persisted result ID, return only review-packet data/owner options, and keep all specialist execution, specialist LLM/tool execution, writes, runtime changes, Builder/Forge, patch, and deploy flags false?
68. **Sentinel Result Review UI:** Does Phase 10.9P let the owner open result packets and record append-only accepted/rejected/review-note events while keeping `review_note` pending and avoiding hidden specialist execution, runtime changes, writes, patches, or deploys?
69. **Agent Learning Evidence:** Does Phase 10.9Q summarize only accepted Sentinel result evidence through a read-only tool/quick action while keeping accepted evidence as planning context only, not runtime activation?
70. **Agent Learning Ledger UI:** Does Phase 10.9R show accepted learning evidence separately from pending/rejected/review-note-only result reviews, and is the ledger display-only?
71. **Accepted Learning Roadmap Link:** Does Phase 10.9S let accepted Sentinel evidence inform the activation plan text while keeping runtime, dispatch, autonomous loop, specialist LLM/tool, write, patch, and deploy flags false?
72. **Visible Agent Roadmap Panel:** Does Phase 10.9T expose the activation plan through a protected read-only endpoint and kiosk panel without enabling live agents, dispatch, specialist LLM/tools, writes, Builder/Forge, patch, or deploy?
73. **Sentinel Dry-Run Request Button:** Does Phase 10.9U create only an append-only Sentinel dry-run request from the roadmap, with execution/dispatch/specialist LLM/tools/writes/patch/deploy still disabled?
74. **Sentinel Dry-Run Mini-Pipeline UI:** Does Phase 10.9V make the Sentinel request -> handoff -> reviewed result path usable while keeping handoff copy and result recording text-only/append-only, with no Sentinel execution, specialist LLM/tools, writes, runtime changes, Builder/Forge, patch, or deploy?
75. **Workbench Sentinel Next Action:** Does Phase 10.9W correctly prioritize Sentinel handoff/result-review work in the Workbench next-action card without implying automation or executing any step?
76. **Live-PG Audit Rail Smoke:** Does Phase 10.9X close the remaining database-level test gap by exercising append-only triggers and no-execution CHECK constraints on the review/audit rails without mutating farm operating data?
77. **Prism Dry-Run Request Gate:** Does Phase 10.9Y add Prism as a second approved dry-run specialist while preserving the same no-dispatch/no-specialist-LLM/no-specialist-tool/no-write/no-asset/no-patch/no-deploy boundary?
78. **Generic Agent Dry-Run Workbench Labels:** Does Phase 10.9Z make the shared dry-run request/result UI clear for Sentinel and Prism without implying live agent execution or hidden automation?
79. **Agent Dry-Run Browser Behavior Contracts:** Does Phase 10.9AA pin the shared dry-run/result UI behavior so there is no timer polling, request/result/event actions require explicit owner clicks, review packets are fetched read-only, and render-only sections do not perform hidden fetches or event writes?
80. **Approved Read-Only Dry-Run Cohort:** Does Phase 10.9AB safely expand dry-run request records to Ledger, Atlas, Rootline, Herdmaster, Butcher, and Quartermaster while preserving no-dispatch/no-specialist-LLM/no-specialist-tool/no-write/no-public-output/no-patch/no-deploy boundaries and keeping Beacon/Forge/Gatekeeper locked out?
81. **Activation Roadmap Cohort Visibility:** Does Phase 10.9AC make the owner-facing roadmap match the dry-run request gate while clearly separating dry-run request records from live runtime/dispatch authority?
82. **Specialist Dry-Run Handoff Quality:** Does Phase 10.9AD improve role-specific dry-run handoff packets without letting the kiosk run specialists, call specialist LLMs, execute specialist tools, write farm data, produce public/customer output, run Builder/Forge, apply patches, deploy, cut over Telegram, or control hardware?
83. **Specialist Result Evidence Boundaries:** Does Phase 10.9AE make accepted dry-run evidence safer by showing what it may influence and must not influence, without creating hidden runtime authority or any write/public-output/control path?
84. **Per-Specialist Dry-Run Queue Status:** Does Phase 10.9AF make the queue easier to understand through read-only per-specialist counts without creating or mutating any request/result/event, dispatch, runtime, write, public-output, Builder/Forge, patch, deploy, Telegram, or physical-control authority?
85. **Generic Agent Learning Evidence:** Does Phase 10.9AG make accepted-learning summaries generic and per-specialist without changing accepted evidence from planning context into runtime authority?
86. **Roadmap Learning Counts:** Does Phase 10.9AH expose accepted evidence counts by specialist through the roadmap route/UI without adding any mutation, runtime, dispatch, specialist LLM/tool, write, public-output, Builder/Forge, patch, deploy, Telegram, or physical-control authority?
87. **Audit Rail CI Workflow:** Does Phase 10.9AI correctly wire the existing DATABASE_URL-gated audit-rail tests into GitHub Actions with disposable Postgres, without touching production data or adding runtime authority?
88. **Browser Behavior Checklist:** Does Phase 10.9AJ adequately close the immediate browser-behavior review gap as a repeatable manual pass, or should Playwright be added before further runtime work?
89. **Audit Rail CI Scope Hardening:** Does Phase 10.9AK correctly scope the disposable-Postgres workflow to Oom Sakkie tests while still exercising the live-PG audit rail checks?
90. **Agent Runtime Readiness Tool:** Does Phase 10.9AL help the owner understand what still blocks live agents without introducing any live runtime, dispatch, specialist LLM/tool, write, public-output, Builder/Forge, patch, deploy, Telegram, or physical-control authority?
91. **Browser Behavior Smoke Gate:** Does Phase 10.9AM provide a useful automated local/CI guard against startup background polling and hidden startup POSTs while keeping agent dry-run/result/message POSTs explicit-owner-click-only?
92. **Agent Operating Contracts:** Does Phase 10.9AN expose useful per-specialist contracts while keeping Beacon/Forge/Gatekeeper locked out of dry-run request records and preserving no runtime, dispatch, specialist LLM/tool, write, public-output, Builder/Forge, patch, deploy, Telegram, or physical-control authority?
93. **Agent Contracts Review Endpoint:** Does Phase 10.9AO expose the operating contracts through a protected read-only route with a false-all review guard and no hidden runtime or mutation path?
94. **Agent Activation Preflight:** Does Phase 10.9AP correctly summarize ready/manual/locked gates and return `not_ready_for_live_dispatch` while keeping all live runtime, dispatch, specialist LLM/tool, write, public-output, Builder/Forge, patch, deploy, Telegram, and physical-control authority disabled?
95. **Activation Preflight Wording Hardening:** Does Phase 10.9AQ honestly distinguish configured gates from manually confirmed live/CI results?
96. **Agent Authority Matrix:** Does Phase 10.9AR correctly keep every future authority area disabled while making risk level, lock reason, and required gates inspectable through read-only chat and a protected route?
97. **Authority Lock Source Alignment:** Does Phase 10.9AS reduce drift by deriving activation-plan blocked capabilities and preflight locked checks from the same source as the authority matrix?
98. **Authority Unlock Readiness:** Does Phase 10.9AT remain planning-only, keep `enabled_count = 0`, and avoid recommending any unlock while showing the lowest-risk future design candidates and hard-no risk-4/5 authorities?
99. **Runtime Inspection Invariant:** Does Phase 10.9AU adequately guard every agent inspection surface against accidentally reporting an authority flag as enabled?
100. **Dispatch Decision Rail Blueprint:** Does Phase 10.9AV remain blueprint-only, keep all runtime/dispatch/specialist-LLM/specialist-tool/write/public/control flags false, and avoid creating the actual dispatch rail, store, event endpoint, migration, or runtime authority?
101. **Agent Runtime Review Packet:** Does Phase 10.9AW provide a useful protected bulk-review packet while remaining read-only and no-authority, and does it avoid implying that Claude review itself enables dispatch?
102. **Playwright Browser Behavior Gate:** Does Phase 10.9AX provide the real-browser safety gate needed before future dispatch-rail implementation work, while keeping all API calls stubbed/read-only and avoiding runtime authority?
103. **Dispatch Decision Rail:** Does Phase 10.9AY correctly implement only an append-only no-execution dispatch request/decision rail, with no live dispatch path, no specialist LLM/tool execution, no writes, no runtime flag changes, review-gated endpoints, DB CHECK constraints, and append-only triggers?
104. **Dispatch Decision Status Visibility:** Does Phase 10.9AZ expose dispatch design-review queue status through read-only `dispatch_decision_status` and `system_work_status` without consuming decisions to enable runtime behavior, dispatch specialists, run specialist LLMs/tools, write farm data, create public/customer output, patch, deploy, cut over Telegram, or control hardware?
105. **Dispatch Runtime Review Packet:** Does Phase 10.9BA remain review-assembly-only by combining the locked runtime review packet with read-only dispatch status, without creating a route/store/migration/event type/runtime flag or consuming dispatch decisions to enable behavior?
106. **Jarvis Product Progress:** Does Phase 10.9BB provide honest read-only progress/milestone visibility without making percentages into unlock criteria or enabling any runtime/dispatch/specialist/write/public/deploy/Telegram/control authority?
107. **Agent Command Center:** Does Phase 10.9BC provide useful control-tower visibility over lanes, queue snapshots, progress, and locked gates while keeping every lane non-executing and avoiding any runtime/dispatch/specialist LLM/tool/write/public/deploy/Telegram/control authority?
108. **Command Center Quick Action:** Does Phase 10.9BD make the command center easier to reach and map it to the visible Gatekeeper workspace without adding hidden POSTs, background polling, routes, stores, writes, dispatch, specialist LLM/tool execution, public output, deploy, Telegram, or physical-control authority?
109. **Future Financial Agent Parking Lot:** Is the logged Financial Agent idea safely treated as future research only, with no current trading, account access, custody/funds movement, orders, profit-share automation, or financial advice/recommendation path?
110. **Playwright CI Startup Hardening:** Does Phase 10.9BF only harden the GitHub browser-behavior workflow startup path without changing app runtime authority, routes, stores, or Oom Sakkie behavior?
111. **Daily Command Brief:** Does Phase 10.9BG provide a useful read-only owner command brief across farm, business, and command-center context while avoiding new routes/stores/writes/dispatch/specialist LLM-tool execution/public output/deploy/Telegram/physical-control authority?
112. **Playwright CI Node 24 / Server URL Hardening:** Does Phase 10.9BH correctly address the GitHub Actions Node 20 warning and make the Playwright server readiness URL point at `/oom-sakkie`, without changing app/runtime behavior?
113. **Playwright Workbench Visibility Fix:** Does Phase 10.9BI correctly make the real-browser spec match the collapsed System Workbench UI before clicking dry-run/result controls, while staying test-only and preserving the no-hidden-POST/no-background-polling invariants?
114. **Audit Rail CI Node 24 Warning Cleanup:** Does Phase 10.9BJ only clean up the disposable-Postgres audit workflow deprecation warning without changing the audit-rail guarantees or app/runtime behavior?
115. **Safety Gate Board:** Does Phase 10.9BK provide honest read-only safety/CI gate visibility, route CI-status questions to Sentinel, and fold the board into Agent Command Center without calling GitHub, adding routes/stores/DB writes, trusting CI automatically, or enabling runtime/dispatch/specialist/write/public/deploy/Telegram/control authority?
116. **Owner Review Packet:** Does Phase 10.9BL provide a useful batched owner/Claude review packet while remaining read-only, avoiding Claude/GitHub/network calls, and not approving or enabling runtime/dispatch/specialist/write/public/deploy/Telegram/control authority?
117. **Review Shortcuts:** Does Phase 10.9BM make Safety Gates and Review Packet easier to reach through explicit owner-click quick actions while avoiding hidden POSTs, background polling, new routes/stores/DB writes, or any runtime/dispatch/specialist/write/public/deploy/Telegram/control authority?
118. **Quick Checks Grouping:** Does Phase 10.9BN improve kiosk quick-action clarity by grouping existing buttons without changing prompts, JavaScript behavior, routes, stores, hidden POST/polling behavior, or runtime/dispatch/specialist/write/public/deploy/Telegram/control authority?
119. **CI Green Evidence:** Does Phase 10.9BO adequately resolve the carried-forward operational item by confirming the latest audit-rail and browser-behavior GitHub Actions runs are green, while keeping the runtime's no-GitHub-call/no-auto-trust design honest?
120. **Dispatch Execution Approval Rail:** Does Phase 10.9BP correctly implement only an append-only Sentinel-only approval rail for a future single-shot advisory dry-run, requiring an existing `approved_for_design_review` dispatch decision while forcing `executes_now`, dispatch, specialist LLM/tool execution, writes, runtime change, and further dispatch false, and without adding any runner/consumer that acts on approvals?
121. **Sentinel Single-Shot Advisory Runner:** Does Phase 10.9BQ correctly implement the first execution slice as default-off, review-gated, approval-gated, Sentinel-only, one-shot, no-tools/no-writes/no-public-output, with runner-only consumed-event idempotency, unsafe-output rejection, capped read-only context egress disclosure, and result persistence only to the append-only dry-run result rail?
122. **Single-Shot Result Constraint:** Does migration `202606090003` preserve the old no-execution result mode while narrowly allowing `runs_specialist = true` and `runs_specialist_llm = true` only for Sentinel's `single_shot_sentinel_advisory_result`, with specialist tools, dispatch, writes, and runtime changes still false?
123. **Sentinel Runner Review Hardening:** Does Phase 10.9BR honestly update the authority matrix so `specialist_llm_loop` is `single_shot_advisory_only` but still `enabled = false`, keeps top-level `specialist_llm_enabled = false`, keeps every other authority locked, and adds a default-off no-network assertion for the runner?
124. **Effective Single-Shot Visibility:** Does Phase 10.9BS make the authority matrix honest when the Sentinel env gate is on by exposing `effective_single_shot_enabled/configured` while still keeping `enabled = false`, `enabled_count = 0`, and top-level `specialist_llm_enabled = false`?
125. **Sentinel Single-Shot Runbook:** Does Phase 10.9BT give a safe, repeatable owner-operated smoke procedure that keeps the env flag off outside the supervised window, requires the full approval chain, verifies append-only result/replay blocking, and avoids implying automation or broader authority?
126. **First Sentinel Smoke And Review Packet Fix:** Does Phase 10.9BU preserve the safety envelope after the first real Sentinel call: result is advisory-only, replay is blocked, the normal policy is back to `specialist_dry_run.enabled = false`, and review packets now allow only the exact Sentinel single-shot result mode while still rejecting tool/write/dispatch/runtime-change flags?
127. **Owner Approval Console:** Does Phase 10.9BV reduce Workbench clutter by surfacing only current owner-decision items above the detailed audit Workbench, while reusing existing queues/actions, avoiding hidden POSTs/background polling/new endpoints/stores/migrations, filtering stale dry-run handoff noise when a result exists, and preserving all runtime/dispatch/specialist-tool/write/public/deploy/Telegram/control locks?
128. **Controller Board:** Does Phase 10.9BW make the visible agent stage clearer using only existing `agent_activity` data, with no new endpoint/fetch/POST/store/migration/runner wiring or runtime/dispatch/specialist-tool/write/public/deploy/Telegram/control authority?
129. **Primary Command Deck:** Does Phase 10.9BX make the most common read-only owner asks easier to reach through the existing explicit-click `data-quick-ask` path, without adding hidden POSTs, polling, direct approve/run/deploy/send/sell/trade/control buttons, or new authority?
130. **Quick Checks Drawer:** Does Phase 10.9BY reduce visual clutter by collapsing the larger quick-action grid while preserving existing prompts/bindings and adding no backend or authority surface?
131. **Command UI Browser Gate Hardening:** Does Phase 10.9BZ correctly extend the real-browser safety gate for the new command deck/drawer, proving drawer open does not POST/poll and command-deck clicks still require explicit owner action through `/message`, while staying test-only?
132. **Sentinel Single-Shot Contract Alignment:** Does Phase 10.9CA reduce drift risk by deriving the runner/store/review-packet/tests from one Sentinel single-shot contract, while keeping the migration SQL static and contract-tested against that source without widening the single-shot authority?
133. **Consumed-Once Live-PG Test:** Does Phase 10.9CB adequately prove the DB-level one-shot guard by asserting a second `consumed_by_single_dry_run_result` event is rejected for the same execution approval while normal review notes remain append-only evidence?
134. **Consumed-Once Migration Assertion:** Does Phase 10.9CC make the partial unique index visible in the offline migration-content test while leaving the live-PG test as the actual insert-level proof?
135. **Learning Influence Proposal Rail:** Does Phase 10.9CD correctly create an append-only proposal-only rail from accepted agent learning evidence, forcing `applies_learning_now`, `changes_prompt_now`, `changes_runtime_now`, `dispatch_enabled`, and `writes` false at DB and application layers, and avoiding any consumer that applies learning or changes behavior?
136. **Learning Influence Status Tool:** Does Phase 10.9CE give useful read-only self-learning / Sentinel suggestion status while avoiding proposal generation from chat, prompt changes, runtime changes, dispatch, tool execution, farm-data writes, public/customer output, deploy, Telegram, physical controls, and financial actions?
137. **Morning Decision Queue:** Is the owner gate now clear enough that the real pending decision is review of `OSK-AGENT-DRYRUN-RESULT-C63AF980E948` before any next authority design?
138. **Learning Influence Workbench UI:** Does Phase 10.9CF make learning proposals visible and reviewable without applying learning, changing prompts/routes/runtime, adding a proposal consumer, wiring the Sentinel runner into the UI, or adding first-screen approve/run/apply controls?
139. **Learning Influence Browser Gate:** Does Phase 10.9CG correctly extend VM smoke and Playwright coverage so learning proposal preparation and `approved_for_future_planning` event recording require explicit owner clicks, create no interval polling, and still do not apply learning or add any proposal consumer?
140. **Owner Cockpit UI:** Does Phase 10.9CH materially simplify the owner-facing decision flow while keeping the full Workbench audit trail available, limiting first-screen direct actions to append-only agent-result/proposal review events, and avoiding Sentinel runner UI, proposal consumers, prompt/runtime changes, patch/deploy/send/sell/trade/control buttons, hidden POSTs, interval polling, or any specialist/tool/write/public/deploy/Telegram/physical/financial authority?
141. **Owner Cockpit Decision Feedback:** Does Phase 10.9CI correctly make append-only cockpit decisions visibly confirm success/failure and refresh queues without adding any new authority, proposal consumer, Sentinel runner UI, hidden POST, polling, or apply-learning behavior?
142. **Cockpit Accepted-Result Proposal Prep:** Does Phase 10.9CJ correctly prepare a learning influence proposal only for the exact clicked result after a successful `accepted_for_learning` event, require that source result's latest event to be accepted before writing, keep the existing bulk Workbench prep deliberate, and avoid approving/applying learning or changing prompt/runtime/routing/tool/farm/public/deploy/Telegram/control/financial behavior?
143. **Owner Review Packet Scope Evidence:** Does Phase 10.9CL make Oom Sakkie's own read-only `jarvis_owner_review_packet` accurately expose the current review scope, handoff prompt, focus items, and green CI evidence while keeping no learning consumer and no prompt/runtime/learning application flags?
144. **Owner Review Packet Chat Gate:** Does Phase 10.9CM adequately prove `prepare Claude review` routes deterministically to the owner packet, names the current scope, says no runtime authority is approved, and keeps the visible Gatekeeper workspace at no run/dispatch/write?
145. **Learning Influence Live-PG Closure:** Does Phase 10.9CO adequately act on Claude's review by applying migration `202606100001`, proving the `from-result` path rejects non-accepted source results with 409 against live Postgres, proving an accepted source creates one proposal, and proving a repeated call returns the existing proposal with `created_count = 0` while all apply/prompt/runtime/dispatch/write flags stay false?
146. **Recorded CI Evidence Policy:** Does Phase 10.9CP resolve the recurring CI-evidence drift nit honestly by treating run IDs as recorded operator evidence, not live GitHub status or exact-current-HEAD proof, while still avoiding runtime GitHub calls and auto-trust?
147. **Learning Consumption Threat Model:** Does Phase 10.9CP provide a useful owner/Claude threat-model and gate checklist for any future learning proposal consumer while still adding no consumer, no apply path, no prompt/routing/runtime change, no hidden POST/polling, no dispatch, no tools, no farm write, and no public/deploy/Telegram/control/financial authority?
148. **Threat Model Follow-Up Items:** Does Phase 10.9CQ adequately fold in Claude's requested provenance/integrity and blast-radius controls by treating proposal text as untrusted LLM-derived input, requiring one allowlisted target field per consumption, and requiring a size-capped reviewable diff before any manual application?
149. **Consumption Audit Rail Blueprint:** Does Phase 10.9CQ provide a safe enough blueprint for the first future implementation slice: append-only request/event audit rail with consumed-once live-PG tests and route tests, while still adding no migration, store, event writer, consumer, prompt/routing/runtime change, hidden POST/polling, dispatch, tools, farm write, public/deploy/Telegram/control/financial authority?
150. **Consumption Audit Rail Implementation:** Does Phase 10.9CR implement only the append-only consumption request/event rail Claude cleared, requiring `approved_for_future_planning` before request insert, preserving one-target review-note-only artifacts with untrusted proposal provenance, rejecting manual `consumed_for_patch_proposal` writes, enforcing consumed-once via partial unique index, and proving append-only/no-apply behavior in live Postgres while still adding no consumer, prompt/route diff application, runtime change, dispatch, tool execution, farm write, public output, deploy, Telegram, physical-control, or financial authority?
151. **Learning Consumer Design Static Guard:** Does Phase 10.9CS adequately protect the `allow_consumed=True` hinge before any consumer exists by adding a production-code static guard, read-only consumer-design packet/tool/route, explicit owner-approval/recheck requirements, review-note-only first output, rollback/manual-application artifact contract, and deterministic routing, while still adding no consumer, no production `allow_consumed=True` caller, no applyable prompt/route diff, and no runtime/write/dispatch/tool/farm/public/deploy/Telegram/control/financial authority?
152. **Hardened Allow-Consumed Static Guard:** Does Phase 10.9CT close the 10.9CS nit by making the no-production-`allow_consumed` guard catch alias/module calls, positional fourth-argument overrides, `**kwargs`, and any non-literal-false `allow_consumed` value, while still adding no consumer, no production `allow_consumed` caller, no applyable diff, and no authority?
153. **Source-Backed Allow-Consumed Caller Evidence:** Does Phase 10.9CU close the documentation-only `allow_consumed_production_callers = []` weakness by deriving that field from the same conservative AST scanner used by the regression guard, while still adding no consumer, no production `allow_consumed` caller, no applyable diff, and no authority?
154. **Allow-Consumed Scanner Resilience:** Does Phase 10.9CV close Claude's two 10.9CU robustness nits by making the source-backed scanner CWD-independent and parse-error tolerant, while still adding no consumer, no production `allow_consumed` caller, no applyable diff, and no authority?
155. **Read-Only Consumer Design Agreement:** Does Phase 10.9CW make the next owner/Claude consumer-design review concrete enough by pinning the review-note artifact shape, ordered `must_recheck_before_marker` enforcement, rollback artifact contract, forbidden patch/write fields, and future static-guard update requirement, while still adding no consumer, no production `allow_consumed` caller, no applyable diff, and no authority?
156. **Consumed-Once Atomicity Wording:** Does Phase 10.9CX close Claude's TOCTOU wording refinement by making the DB partial unique index the explicit atomic race guard and requiring unique-violation to return safely with no second review-note artifact, while still adding no consumer, no production `allow_consumed` caller, no applyable diff, and no authority?
157. **Review-Note Consumer Implementation:** Does Phase 10.9CY implement exactly the owner-approved first consumer: one reviewed `allow_consumed=True` production caller, approved-request/proposal/target rechecks, DB-consumed-once race handling, repeat-call `already_consumed` behavior, and review-note artifact output only, while still avoiding prompt/route/runtime application, applyable diffs, dispatch, specialist tool/LLM execution, farm writes, public output, deploy, Telegram, physical-control, or financial authority?
158. **Call-Site Guard Hardening:** Does Phase 10.9CZ close the 10.9CY nit by making the reviewed `allow_consumed=True` permission call-site granular, proving exactly one reviewed call site, and avoiding substring path allowlist matches while preserving no extra consumer and no apply authority?
159. **Browser Voice Capture And Live Consumer Smoke:** Does Phase 10.9DA adequately fix the local Talk/Talk & Ask capture path by testing browser transcript handling and clearer microphone diagnostics, and does the supervised live consumer smoke prove the route returns one review-note artifact, replay fails as already consumed, and all authority flags remain false?
160. **n8n Backend Read-Only Relay Contract:** Does Phase 10.9DI provide a safe import-ready relay contract for GateKeeper review by staying inactive/callable, avoiding any Telegram Trigger or Telegram send node, using env-only token/base URL config, validating backend no-authority flags, and returning only a guarded caller-send payload without becoming a second Telegram owner or enabling cutover/public output/write/dispatch/runtime authority?
161. **n8n Relay Transport Guard:** Does Phase 10.9DJ close Claude's 10.9DI nit by refusing remote plain-HTTP `OOM_SAKKIE_GATEWAY_BASE_URL` values before the relay uses the bearer token, while still allowing HTTPS remotes and local HTTP for localhost/127.0.0.1/::1?
162. **n8n Relay Import Preflight:** Does Phase 10.9DK provide useful local import-safety tooling by validating the committed `2.0B` workflow/README without calling n8n, Telegram, Flask, OpenAI, Google Sheets, or Supabase, and without enabling any trigger/send/wire/cutover authority?
163. **Learning Backlog Clarity:** Does Phase 10.9DL make the kiosk clearer by labeling closed dry-run/result/learning records as append-only audit backlog and by moving dry-run requests with recorded results out of the active handoff list, without deleting/archive-writing records or adding any learning-apply, prompt/route/runtime, tool, farm-data, Telegram, dispatch, deploy, physical-control, public-output, or financial authority?
164. **GateKeeper Backend Relay Wiring Plan:** Does Phase 10.9DM provide a safe enough owner-approved manual n8n UI plan for a live Telegram reply test by importing `2.0B` inactive, keeping GateKeeper as the only Telegram Trigger owner and only reply sender, validating backend no-authority flags before send, preserving callback routes, requiring backup/rollback, and avoiding any live n8n API update, second listener, direct send in `2.0B`, write authority, dispatch, public/customer broadcast expansion, runtime mutation, deploy, physical-control, or financial action?
165. **Reverse proxy deployment rule:** Does the PRD now state strongly enough that same-host reverse proxying in front of review routes is forbidden until trusted proxy handling/auth is deliberately configured?
166. **Tests:** What missing tests or browser checks should happen before this is considered daily-use ready?

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
