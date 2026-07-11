# CHARLIE Mission Loop Contract

Last updated: 2026-07-11

This contract defines the foundation rules for running CHARLIE mission-loop work around the existing Amadeus/Codex workflow. It is not a Fable clone, not a Claude replacement, and not a new autonomous production operator.

## Operating Model

- Codex is the primary builder.
- CHARLIE CORE and the Supabase `charlie_missions` store are the authoritative mission system.
- CHARLIE Build Relay is the owner remote-control layer for CHARLIE CORE, not a parallel mission system.
- Telegram is the owner remote-control channel.
- `docs/00-start-here/NEXT_STEPS.md` is planning backlog and fallback menu only when Supabase is unavailable or empty.
- `planning/CODEX_CHAT.md` is manual/local/debug handoff only, not the primary mission state.
- `docs/00-start-here/CURRENT_STATE.md` is current truth.
- Scripts and tests are the final gate. No model may claim a mission is done unless the verify gate passes.
- Mission Loop must not create a parallel mission system. Supabase CHARLIE CORE mission state is authoritative.
- File-based mission handoffs are fallback/manual only and may not be used as the default action path once Supabase mission context is available.

## Authority Levels

### GREEN

Codex may do these alone inside an approved mission:

- inspect code, docs, tests, logs, and local artifacts;
- edit scoped docs, scripts, tests, and application code allowed by the mission;
- run local deterministic tests and smoke checks that do not need secrets;
- commit and push an approved branch when tests pass and the diff stays in scope;
- prepare a PR for owner review.

### YELLOW

Codex may continue, but must report clearly in the final report:

- tests are slow but pass;
- fallback behavior was used;
- low-risk docs or test updates were needed to explain the change;
- a non-production optional check could not run because a local dependency is missing;
- a mission required a narrower interpretation than the initial prompt.

### RED

Codex must stop and wake the owner before continuing:

- destructive migration is needed;
- production data deletion or cleanup is needed;
- secrets, API keys, or live credentials are missing or would be exposed;
- customer messages, public posts, payments, deposits, reservations, stock lifecycle, or animal purpose writes would be affected;
- tests cannot be made to pass honestly;
- confidence is below 98%;
- a migration was not already approved;
- the diff expands outside the approved mission files;
- Claude/Fable/OpenRouter/GLM live API usage would be required;
- Phase 3A.6, CHARLIE UI, FRED, or ledger SQL would be touched without explicit mission approval.

## Hard Stops

Stop and report only if one of these occurs:

- deterministic tests cannot be made to pass;
- final confidence is below 98%;
- a destructive migration or production data update is required;
- a secret, token, or customer credential is needed;
- customer sends, payments, deposits, reservations, public posts, stock lifecycle, or purpose writes are affected;
- forbidden files are required;
- paid or external model API calls are needed;
- a real owner decision is needed.

## Forbidden Files By Default

These files or paths must not be staged unless the mission explicitly approves them:

- `.env` and `.env.*`;
- `.claude/`;
- `external_sources/`;
- `screenshots/`;
- `static/assets/`;
- `test-results/`;
- `planning/Prompts.md`;
- generated media, exported documents, and local credentials.

## Verification Rules

- `scripts/verify_mission.ps1` is the local final gate for mission-loop work.
- The verify script must select focused checks based on changed files.
- A mission fails verification if no relevant tests or checks run.
- Tests must not be edited to fake a pass.
- Secrets must not be printed, committed, or sent to a model.
- No broad Claude API spending is permitted by default.
- Cheap models may be added later only as read-only triage or low-risk workers behind budget gates.
- Future model integrations must pass `scripts/model_budget_guard.py` before any provider call is attempted.
- If the budget file is missing, disabled, or over cap, model work must stop before any Claude/Fable/GLM/OpenRouter request.

## GPT-5.6 Family Alignment

GPT-5.6 routing is planned but disabled. Sol, Terra, and Luna are future support modules behind the budget gate and trust ledger. Loop 6.5 performs alignment only; no live model calls are allowed.

- GPT-5.6 Luna is the future cheap triage/summariser for docs summaries, log compression, mission triage, and low-risk status classification.
- GPT-5.6 Terra is the future balanced planner/reviewer for normal mission planning, normal PR review, and medium-risk implementation guidance.
- GPT-5.6 Sol is reserved for high-value reasoning: architecture, security/auth review, Supabase migration review, repeated P0 failure analysis, and complex code review.
- Codex remains the primary builder.
- Supabase CHARLIE CORE remains the source of truth.
- Telegram remains the owner remote-control channel.
- No model may approve its own work.
- The verify script remains the final gate.
- Trust ledger tier and budget guard approval are required before any future live model call.
- Red-zone tasks still require owner approval regardless of model recommendation.
- No full-repo prompt is sent to GPT-5.6 by default; future calls must use scoped mission specs, relevant files, diffs, logs, and exact questions.

## Confidence Gate

The owner requested a 98% confidence gate for this foundation layer. A mission may be recommended for merge only when:

- tests pass;
- the verify gate passes;
- the diff is inside the approved scope;
- no hard stop occurred;
- no secrets, production writes, model calls, or live Telegram sends occurred;
- remaining risks are documented.

If confidence is below 98%, report `NO-GO` with exact blockers.
