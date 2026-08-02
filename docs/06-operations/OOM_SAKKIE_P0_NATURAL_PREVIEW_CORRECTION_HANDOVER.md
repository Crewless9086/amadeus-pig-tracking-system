# Oom Sakkie P0 natural preview correction handover

Date: 2026-08-02
Scope: Pig 125 operational spine only

## Authoritative defect evidence

- Original mission: `OOM-HERDMASTER-7F3E42E3FD65581696E065D8`
- Existing lifecycle card: Telegram `3184`
- Removal report: Telegram `3188`
- Natural correction: Telegram `3189`
- GateKeeper execution: `61949`
- Relay execution: `61950`
- Provider epoch: `1785695602`
- Exact correction SHA-256:
  `9d7e471689c814ea3edad3eb639e5451ccb9fe0353df69c37b8029b9ceae53a9`
- Execution 61950 returned `preview_ready` but treated the correction as additional
  context, retained Active/no-change semantics and delivered no visible corrected
  card. It wrote zero farm rows.

## Prepared generic behavior

The existing authenticated HERDMASTER lifecycle now classifies an owner message
against an active preview as confirmation, natural correction, added evidence,
decline or question. A correction first records a durable invalidation event,
preserves the entire previous preview and digest as immutable history, and then
generates a new deterministic preview from retained chronology and fresh
canonical evidence. Process interruption can resume from
`preview_correction_pending`.

Old operation identities are retained in `invalidated_operation_ids`; an exact
stale confirmation fails closed with zero writes. Exact correction replay returns
the existing corrected lifecycle without creating another preview, operation
identity, send or edit. Multiple active cases retain the existing precise
identity/ambiguity boundary.

The evaluator now treats authenticated `found dead` as sufficient evidence to
propose, after confirmation:

- lifecycle `Deceased`, effective date `2026-08-02` for this case;
- exact time of death `Unknown`;
- current on-farm false;
- removal from current pen occupancy and current availability projections;
- preservation of historical movements, weights, health, withdrawal, sales and
  breeding history;
- closure/reassessment of future work while retaining justified mortality
  follow-up.

Owner wording about spraying with `LAB` remains in the immutable report and is
labelled unverified owner wording, not a canonical biosecurity effect. It does
not create another owner question.

The existing canonical `pigs` state and append-only `pig_lifecycle_events` rail
form one PostgreSQL transaction after exact confirmation. The confirmation
adapter takes an operation-bound advisory lock, checks the lifecycle-event
idempotency key, locks the exact active/on-farm pig, changes the canonical row
and inserts the immutable lifecycle event atomically. It allows only the closed
mortality effect set, rejects mixed unsupported effects, requires unchanged
canonical evidence and exact owner/operation binding, and proves a single
canonical pig-row transition. Concurrent confirmation and replay return the
existing lifecycle event with zero additional rows. If later Oom Sakkie card
state persistence fails, replay recovers from that canonical event without
repeating the farm mutation. No write occurs during correction or preview.

## Production continuation

After exact-head review, CI, normal merge, exact-merge CI and exact Render
lineage, recover Telegram 3189 with a distinct consumed guard. Require one edit
of card 3184 (or the established visible material-update delivery), zero sends,
zero farm rows and zero delivery on replay. The new preview must bind Pig
`PIG-2026-BCEB`, propose Deceased/not-on-farm/current PEN-012 removal, retain
death time/cause/diagnosis/treatment/veterinary evidence as Unknown, and expose
one new exact confirmation identity.

Release runtime while waiting. Only Charl's exact authenticated confirmation of
that corrected preview may invoke the governed lifecycle service. Business
completion still requires canonical projection verification, replay proof,
HERDMASTER and manager-status refresh, and visible completion on card 3184.
