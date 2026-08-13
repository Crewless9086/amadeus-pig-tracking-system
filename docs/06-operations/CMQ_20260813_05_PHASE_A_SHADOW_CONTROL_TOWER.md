# CMQ-20260813-05 Phase A Shadow Control Tower

Status: source-prepared; disabled by default; not deployed

Owner and sole authority: human Control Tower

## Reconciliation

The existing durable CORE backend already provides the authoritative Supabase
mission queue, mission events, runner state, operational event fabric and
source/vault evidence. The canonical owner-facing terminal board and feedback
rules remain in `CONTROL_TOWER_MISSION_REGISTER.md`. A visible development
terminal is not a deployed specialist agent or the CORE runner.

Phase A therefore adds no agent, terminal fleet, scheduler, process, mission
queue or ledger. `modules/charlie/shadow_control_tower.py` records observe-tier
proposal and comparison events in the existing `operational_events` fabric.
No schema change is required.

## Shadow feedback transaction

For a later genuine terminal-feedback transaction, the caller supplies the
existing mission and separately classified documented, runtime-loaded,
provider-verified and physical evidence. The deterministic proposal records:

- visible terminal identity and state;
- deployed-agent identity;
- existing mission and business status;
- four-part evidence classification;
- worktree and collision classification;
- proposed next terminal, next action and continuation prompt;
- expected owner-visible result; and
- confidence and reasons.

The proposal is explicitly non-authoritative. A later human Control Tower
decision can be compared only after the exact proposal is loaded from durable
storage and its content identity matches the caller's reference. It is stored
as a second event and compared deterministically across next terminal, action,
prompt and expected result. Duplicate receipts reuse stable proposal/human
decision identity; a changed replay fails closed. Readiness counts distinct
durably paired feedback transactions, so repeated decisions cannot inflate the
ten later real comparisons. It never manufactures them or claims learning
success.

## Kill switch and zero authority

`CHARLIE_SHADOW_CONTROL_TOWER_ENABLED` is absent/false by default. While false,
proposal generation and persistence fail closed. Even when deliberately
enabled for a later reviewed observation, the module can only construct and
append observe-tier events. It cannot send a prompt, start/control a terminal,
spawn a process/window, create a mission, merge, deploy, message a provider,
write farm data or grant release authority. It exposes no route or scheduler.

The human Control Tower remains the sole dispatcher and decision authority.
This source preparation did not fabricate any of the ten comparison events and
does not authorize deployment or Phase A learning claims.
