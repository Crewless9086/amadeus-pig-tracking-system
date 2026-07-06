# SAM Live Stock Sales Build Plan

Status: planning/debrief. No live customer automation, order creation, reservation, payment, or sales transaction changes are approved by this document.

Date: 2026-07-06

## Goal

Build SAM Live Stock Sales as a backend-native, Chatwoot/WhatsApp-capable sales lane under SAM, using current app/Supabase truth and preserving the proven behavior from the legacy n8n `1.0 - SAM - Sales Agent - Chatwoot` workflow.

The business goal is urgent: sell suitable live pigs before feed cost destroys margin, without creating wrong stock promises, duplicate reservations, unsafe customer messages, or data drift.

## Honest Current State

SAM Meat Sales has a modern backend-native runtime in `modules/sales/sam_meat_runtime.py`, with lead memory, Chatwoot gates, policy checks, LLM/agent flags, owner/money-path controls, and tests.

SAM Live Stock Sales does not yet have an equivalent backend-native runtime. The Vault Brain currently marks the Live Pig Sales Agent as planned, not active.

The old n8n workflow already contains valuable live-pig sales intelligence:

- customer intent parsing for piglets, weaners, growers, finishers, and slaughter pigs;
- quantity, sex, weight range, timing, location, and payment extraction;
- price-point mapping from weight bands;
- split male/female requests;
- adjacent-band offers;
- Chatwoot state preservation;
- intake state and draft order handoff;
- order steward separation;
- quote/send gates.

The old workflow must not be copied blindly because it was built around legacy workflow/sheet assumptions. Current truth must come from the app/Supabase-backed backend APIs.

## Current Source Truth

### Strategy And Agent Doctrine

- `docs/09-vault-brain/02-agents/sales/SAM.md`
- `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
- `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`
- `docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md`
- `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`
- `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`

### Current Backend/App Truth

- `modules/pig_weights/pig_weights_service.py`
- `modules/orders/order_intake_service.py`
- `modules/orders/order_service.py`
- `modules/orders/order_write.py`
- `modules/orders/order_routes.py`
- `modules/sales/sales_transaction_*`
- `templates/sales-availability.html`
- `templates/sales-dashboard.html`
- `templates/orders.html`
- `templates/order-detail.html`
- `templates/pig-allocation.html`

### Current API Surfaces To Reuse

- `/api/order-intake/context`
- `/api/order-intake/update`
- `/api/orders/active-customer-context`
- `/api/orders/available-pigs`
- `/api/master/orders`
- `/api/master/order-lines`
- `/api/orders/<order_id>/reserve`
- `/api/orders/<order_id>/send-for-approval`
- `/api/sales-transactions`
- `/api/sales-transactions/dry-run`
- `/api/pig-weights/sales-dashboard`
- `/api/pig-weights/pig-allocation-readiness`
- `/api/pig-weights/purpose-review`

### Legacy References To Mine, Not Trust Blindly

- `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`
- `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json`
- `docs/03-google-sheets/sheets/SALES_PRICING.md`
- `docs/03-google-sheets/sheets/SALES_AVAILABILITY.md`
- `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`
- `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`

## Build Principle

Do not create a second sales truth.

SAM Live Stock Sales should be an agent/runtime layer that uses the existing order intake, order, availability, reservation, and sales transaction rails. It should not write directly to sheets, bypass backend validation, or create its own private stock ledger.

## Proposed Architecture

### 1. SAM Sales Router

Add a shared SAM sales-lane router that classifies customer messages into:

- `meat_sales`;
- `live_stock_sales`;
- `slaughter_abattoir_sales`;
- `farm_general_question`;
- `owner_handoff`;
- `unclear`.

This prevents meat leads from becoming live-pig orders and live-pig leads from entering meat preorder rails.

### 2. SAM Live Stock Runtime

Create a backend-native module, likely:

- `modules/sales/sam_live_stock_runtime.py`

Responsibilities:

- authorize Chatwoot/WhatsApp inbound webhook with its own env gate;
- parse customer message and prior context;
- extract quantity, category, weight band, sex, timing, location, payment preference, and notes;
- call/read order intake context;
- update order intake state only through backend rails;
- read available pigs from current backend truth;
- produce safe customer reply;
- prepare owner/order actions only when gates pass.

### 3. Live Stock Conversation Memory

Use the current `ORDER_INTAKE_STATE` / `ORDER_INTAKE_ITEMS` path for live-pig sales memory.

Required fields:

- conversation id;
- contact id;
- customer name;
- phone;
- category;
- weight range;
- sex preference;
- quantity;
- collection location;
- timing;
- payment method;
- commitment state;
- linked draft order id;
- missing fields;
- ready-for-draft / ready-for-quote state.

Do not create a parallel memory table unless the existing intake rails are proven insufficient.

### 4. Availability And Matching

SAM must not invent stock.

Live stock availability should come from:

1. Supabase-backed `get_sales_availability()` / `get_pig_allocation_readiness()` where available.
2. Existing availability fallback only when Supabase is unavailable.

Matching rules:

- exact category/weight/sex first;
- if exact stock is short, offer adjacent bands only as options;
- never over-offer quantity;
- exclude reserved, off-farm, terminal, sold/exited, withdrawal-blocked, or source-conflicted pigs;
- slow growers and live-sale candidates should be prioritized when suitable;
- breeding candidates must not be offered without owner approval.

### 5. Pricing

Initial pricing should use current sales pricing bands from existing docs/rails:

- Piglet 2-4 kg: 350
- Piglet 5-6 kg: 400
- Weaner 7-9 kg: 450
- Weaner 10-14 kg: 500
- Weaner 15-19 kg: 600
- Grower 20-24 kg: 800
- Grower 25-29 kg: 1000
- Grower 30-34 kg: 1200
- Grower 35-39 kg: 1400
- Grower 40-44 kg: 1600
- Grower 45-49 kg: 1800
- Finisher 50-54 kg: 2200
- Finisher 55-59 kg: 2300
- Finisher 60-64 kg: 2400
- Finisher 65-69 kg: 2500
- Finisher 70-74 kg: 2600
- Finisher 75-79 kg: 2700
- Ready for Slaughter 80-84 kg: 2800
- Ready for Slaughter 85-89 kg: 2900
- Ready for Slaughter 90-94 kg: 3000

Before live launch, owner must confirm whether these prices are still correct.

### 6. Draft Order Flow

SAM may prepare a draft order only when:

- customer identity/phone is known;
- product lane is definitely live stock;
- requested item facts are complete enough;
- backend availability can satisfy at least part of the request;
- no active conflicting order exists, or customer clearly wants a new order;
- backend validation passes.

Draft order creation must use existing backend order APIs.

SAM must not reserve animals automatically unless a later owner-approved rule says so.

Recommended first live version:

- create/update intake;
- when ready, create draft order with lines;
- show owner/admin review packet;
- owner approves reservation/send/quote path.

### 7. Reservation And Quote Gates

First safe version:

- draft order can be created when data is complete;
- reservation stays owner-gated;
- formal quote/send stays backend-gated;
- SAM may tell the customer the farm is checking availability or preparing the next step;
- SAM may not say animals are held/reserved unless backend reservation succeeds.

### 8. Chatwoot/WhatsApp Transport

SAM Live Stock must use a separate policy gate from Meat Sales.

Suggested envs:

- `SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED`
- `SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN`
- `SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED`
- `SAM_LIVE_STOCK_BACKEND_LLM_ENABLED`
- `SAM_LIVE_STOCK_BACKEND_AGENT_V3_ENABLED`
- `SAM_LIVE_STOCK_BACKEND_LLM_MODEL`
- `SAM_LIVE_STOCK_BACKEND_AGENT_V3_MODEL`

Do not run Meat Sales and Live Stock Sales on the same unrestricted webhook without a router that prevents cross-lane contamination.

### 9. Human/Agentic SAM Behavior

SAM must sound human, local, and practical:

- ask one useful question at a time;
- remember facts already captured;
- offer close alternatives when stock is short;
- avoid sounding like a form;
- never pressure with cheap/discount language;
- explain honestly when owner confirmation is needed;
- escalate uncertainty instead of guessing.

Add a Live Stock personality/playbook/golden examples set:

- `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
- `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`
- `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
- `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`

### 10. Owner Command Room

Add dashboard visibility before live launch:

- live-stock leads/intakes;
- requested category/weight/sex/qty;
- matched availability;
- draft order id;
- missing fields;
- owner action required;
- blocked reason;
- suggested reply;
- linked Chatwoot conversation;
- no-write policy evidence.

This can either extend the existing order/sales dashboard or add a specific SAM Live Stock command panel.

## Staged Build Plan

### Stage 1: Vault And Rules Pack

Create the Live Stock Sales Vault authority:

- agent file update;
- workflow doc;
- business rules doc;
- source-map update;
- golden reply examples;
- open questions for pricing, reservation timing, and transport.

Acceptance:

- no code writes;
- owner review required;
- exact current backend/source references listed.

### Stage 2: Source Map And Router Contract

Add machine source-map section for SAM Live Stock Sales.

Build/test a pure classifier/router contract:

- meat vs live stock vs slaughter vs unclear;
- negation handling;
- mixed intent clarification;
- no backend writes.

Acceptance:

- unit tests for lane classification;
- no customer sends;
- no order writes.

### Stage 3: Backend Runtime V1, Read-Only

Create `sam_live_stock_runtime.py` with:

- auth policy;
- inbound parser;
- fact extractor;
- prior context merge;
- availability read;
- safe decision packet;
- reply draft only.

Acceptance:

- disabled by default;
- token gated;
- no writes to orders/sales/pigs;
- tests for auth, parse, lane, facts, availability, and safe replies.

### Stage 4: Intake Write Rail

Connect live-stock facts to existing `order_intake_service`.

Acceptance:

- append/update intake only through backend service;
- preserves Chatwoot/order context fields;
- captures split sex/adjacent band offers without duplicate items;
- tests cover Supabase path and fallback.

### Stage 5: Matching And Draft Order Gate

Build candidate matching and draft order packet:

- exact match;
- adjacent alternatives;
- stock shortage response;
- owner/admin review packet;
- draft order creation only when ready and enabled.

Acceptance:

- no reservation yet;
- no final quote promise;
- no duplicate active order surprise;
- tests for partial matches and no-stock replies.

### Stage 6: Owner-Gated Reservation/Quote Flow

Connect draft order to existing order approval/reservation/document rails.

Acceptance:

- reservation only after owner/backend gate;
- quote/send only after backend quote/doc gate;
- customer wording cannot claim success unless backend success is true.

### Stage 7: Chatwoot Live Smoke

Private smoke with Charl's test WhatsApp/Chatwoot conversation:

- vague enquiry;
- exact request;
- sex split;
- unavailable band;
- mixed meat/live-pig intent;
- returning customer with active order;
- quote request;
- cancel/change request.

Acceptance:

- no wrong lane;
- no invented stock;
- no accidental reservation;
- no duplicate order without clear customer intent;
- owner can pause/override.

### Stage 8: Dashboard/Command Room

Add a SAM Live Stock command view:

- all active intakes/leads;
- stock match;
- draft order status;
- blocked actions;
- owner next action;
- chat link;
- test evidence.

Acceptance:

- owner can understand what SAM is doing without opening raw logs.

### Stage 9: Controlled Go-Live

Enable live webhook but keep auto-send conservative:

- first mode: draft reply / owner review;
- second mode: autoreply only for safe fact collection;
- third mode: backend-gated quote/order/reservation messages.

Acceptance:

- launch checklist complete;
- Telegram/Oom Sakkie notification active;
- rollback env switch tested.

## Testing Standard

Minimum required before go-live:

- `tests/test_sam_live_stock_runtime.py`
- `tests/test_sam_live_stock_router.py`
- `tests/test_order_intake_service.py`
- `tests/test_order_routes.py`
- `tests/test_pig_allocation_readiness_service.py`
- `tests/test_sales_transaction_read.py`
- `tests/test_sales_transaction_create.py` where transaction writes are introduced
- Chatwoot remote smoke with fake sender
- one real WhatsApp/Chatwoot controlled test

Stress cases:

- customer asks for pigs but means meat;
- customer asks for meat but says not live pig;
- customer wants 3 female weaners but only 1 female and 2 male are available;
- customer changes from 2 to 4 pigs;
- customer asks for cheap/discount wording;
- customer asks if pigs are reserved;
- customer sends payment proof;
- customer has active draft order;
- customer wants a completed/cancelled order changed;
- stock becomes unavailable between quote and reservation.

## Main Risks

1. Meat and live-stock lanes can contaminate each other if routing is weak.
2. Old n8n logic can create false confidence if treated as current truth.
3. Pricing may be outdated and must be owner-confirmed.
4. Order creation/reservation can create real business consequences, so first go-live must be owner-gated.
5. Chatwoot/WhatsApp send windows/templates need explicit policy checks.
6. Current sales transaction create supports Slaughter only, so Livestock income posting may need a separate approved build if not already handled through orders.
7. Local repo/worktree pollution has already caused PR review issues; this build should run from a clean branch/worktree.

## Confidence Assessment

Planning confidence: 92%.

Implementation confidence can reach 98% only after:

- owner confirms live-stock price bands;
- owner confirms whether first live launch may create draft orders automatically or only owner-reviewed drafts;
- router tests prove meat/live/slaughter separation;
- backend runtime tests pass;
- order-intake and availability tests pass;
- one controlled Chatwoot/WhatsApp live smoke passes;
- owner command room makes every action visible and pausable.

I would not claim 98% live readiness today from the current system alone. The repo has enough foundation to build it properly, but SAM Live Stock Sales is not already perfect or launch-ready.

## Recommended Immediate Next Mission

Build Stage 1 and Stage 2 together:

1. Create the Live Stock Sales Vault rules/workflow/playbook/examples.
2. Add a SAM Live Stock source-map section.
3. Add a pure router/classifier module and tests proving lane separation.

Then stop at owner review before any backend writes or customer automation.

## Stage 1/2 Completion Evidence

Status: implemented for owner review on 2026-07-06.

Delivered:

- Live Stock Sales Vault authority:
  - `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`
  - `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`
  - `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`
  - `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`
  - `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`
  - `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`
- SAM and Vault index/source-map updates.
- Open questions for owner launch settings.
- No-write deterministic router:
  - `modules/sales/sam_sales_router.py`
- Source-map routing for SAM Live Stock Sales:
  - `modules/charlie/source_map.py`
  - `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`
- Vault retrieval keyword hooks for live-stock missions:
  - `modules/charlie/vault_retrieval.py`
- Tests:
  - `tests/test_sam_sales_router.py`
  - `tests/test_charlie_source_map.py`

Verification passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_sam_sales_router tests.test_charlie_source_map`
- `.\venv\Scripts\python.exe -m unittest tests.test_order_intake_service tests.test_order_routes tests.test_order_service_reservation tests.test_sales_transaction_read tests.test_pig_allocation_readiness_service`
- `.\venv\Scripts\python.exe -m py_compile modules\sales\sam_sales_router.py modules\charlie\source_map.py modules\charlie\vault_retrieval.py`
- `node --check static\js\salesDashboard.js`

Result:

- Stage 1/2 is ready for owner review at 98% confidence for the approved scope.
- The approved scope is Vault authority plus no-write lane classification only.
- This does not make SAM Live Stock live-ready yet.
- Backend runtime, intake writes, stock matching, draft order gate, reservation gate, Chatwoot smoke, and command-room visibility remain future stages requiring owner approval.

## Stage 3 Completion Evidence

Status: implemented for owner review on 2026-07-06.

Approved Stage 3 scope:

- create backend-native read-only runtime;
- add auth policy;
- parse Chatwoot inbound payloads;
- extract live-stock facts deterministically;
- merge prior order-intake context without writing;
- read current sales availability without writing;
- produce a safe decision packet;
- remain disabled/default-off and read-only;
- no customer sends;
- no order writes;
- no stock reservations;
- no sales transaction writes.

Delivered:

- `modules/sales/sam_live_stock_runtime.py`
- `tests/test_sam_live_stock_runtime.py`
- source-map updates to include the Stage 3 runtime and tests.

Verification passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_sam_live_stock_runtime tests.test_sam_sales_router tests.test_charlie_source_map`
- `.\venv\Scripts\python.exe -m unittest tests.test_order_intake_service tests.test_order_routes tests.test_order_service_reservation tests.test_sales_transaction_read tests.test_pig_allocation_readiness_service`
- `.\venv\Scripts\python.exe -m py_compile modules\sales\sam_live_stock_runtime.py modules\sales\sam_sales_router.py modules\charlie\source_map.py modules\charlie\vault_retrieval.py`
- `node --check static\js\salesDashboard.js`

Result:

- Stage 3 is ready for owner review at 98% confidence for the approved read-only scope.
- Runtime remains disabled/default-off unless `SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED=1` and a valid token are configured.
- Even if autoreply/LLM envs are enabled, Stage 3 policy keeps customer sends and LLM/agent execution off.
- Decision packets can classify, extract facts, read existing intake/availability context, summarize safe matching evidence, and draft a suggested reply for review only.
- Stage 3 does not add a public route, write intake, write orders, reserve stock, send customer messages, or create sales transactions.

## Stage 4 Completion Evidence

Status: implemented for owner review on 2026-07-06.

Approved Stage 4 scope:

- connect live-stock facts to existing `order_intake_service`;
- write only through backend intake validation/update rails;
- preserve Chatwoot/customer context fields;
- normalize SAM facts to backend enums;
- remain env-gated;
- no customer sends;
- no order creation;
- no stock reservation;
- no quote/document send;
- no sales transaction writes.

Delivered:

- `SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED` env gate.
- `build_live_stock_intake_payload(...)`.
- `validate_live_stock_intake_payload(...)`.
- `write_live_stock_intake_if_enabled(...)`.
- Runtime integration that reports intake-write evidence in the decision packet.
- Tests for disabled/default mode, enabled write mode, wrong-lane block, breeding-stock owner gate, backend validation normalization, and no order/reservation/customer-send authority.

Verification passed:

- `.\venv\Scripts\python.exe -m unittest tests.test_sam_live_stock_runtime tests.test_sam_sales_router tests.test_charlie_source_map`
- `.\venv\Scripts\python.exe -m unittest tests.test_order_intake_service tests.test_order_routes tests.test_order_service_reservation tests.test_sales_transaction_read tests.test_pig_allocation_readiness_service`
- `.\venv\Scripts\python.exe -m py_compile modules\sales\sam_live_stock_runtime.py modules\sales\sam_sales_router.py modules\charlie\source_map.py modules\charlie\vault_retrieval.py`
- `node --check static\js\salesDashboard.js`

Result:

- Stage 4 is ready for owner review at 98% confidence for the approved controlled intake-write scope.
- Intake writes are off unless `SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED=1`.
- Writes are limited to existing order-intake state/items via `update_intake_state`.
- Invalid facts fail closed before write.
- Wrong lane and breeding/replacement-stock cases do not write.
- This stage still does not make SAM Live Stock live-ready; Stage 5 matching/draft order gate is still required.
