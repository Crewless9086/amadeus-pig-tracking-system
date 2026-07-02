# Mission Type Playbooks

## Universal Mission Flow

Every mission must pass through:

1. Intake.
2. Scope.
3. Source-of-truth check.
4. Risk and authority check.
5. Implementation or analysis.
6. Tests and pressure tests.
7. Review packet.
8. Owner decision.
9. Release/closeout.
10. Vault Brain update check.

## Feature Build

Required stages:

- planner: define user outcome and acceptance criteria;
- architect: identify files, routes, data contracts, risks;
- builder: implement only scoped changes;
- tester: run focused tests and pressure tests;
- reviewer: inspect diff, evidence, and owner review packet.

Must include:

- changed files;
- screenshots or UI proof if visual;
- test commands and results;
- known risks;
- rollback/release plan.

## Bugfix / P0 Operational Issue

Required stages:

- reproduce or explain failure;
- identify current live/branch/deploy state;
- patch narrowly;
- verify with regression test;
- deploy only under approved rule.

Must not:

- refactor unrelated code;
- hide technical failure from owner;
- leave stale local process/deploy mismatch unresolved.

## Dashboard / UI Mission

Must use `07_UI_DASHBOARD_STANDARD.md`.

Required evidence:

- visible controls;
- no hidden approval action;
- desktop/mobile check when practical;
- text does not overflow;
- critical buttons are accessible without opening fragile modals;
- source data and loaded state are clear.

## CHARLIE CORE Workflow Mission

Must use:

- `01_CHARLIE_IDENTITY.md`;
- `02_OWNER_OPERATING_MODEL.md`;
- `04_AGENT_CHARTERS.md`;
- `06_EVIDENCE_AND_REVIEW_STANDARD.md`;
- `08_DATA_AND_SUPABASE_CONTRACTS.md`.

Required extra checks:

- mission status transitions are correct;
- review queue is usable;
- owner comments persist;
- send-back carries context;
- release approval is separate from build approval;
- runner/local/Render visibility is not misleading.

## Agent Build

Before building or changing an agent:

- update or create its charter;
- define watches, inputs, outputs, authority, and forbidden actions;
- define source-of-truth data;
- define review packet shape;
- define owner gates;
- define dashboard placement.

No new agent should be created as a vague "smart bot." It must be a department with boundaries.

## Income Stream / Business Build

Required docs before build:

- business model;
- customer path;
- pricing and payment rules;
- operational fulfilment rules;
- legal/privacy/marketing constraints;
- source-of-truth tables;
- approval gates;
- launch evidence plan.

Current money-first lane: meat sales. FRED/private transfers is planned but needs its own business brain before automation.

## Marketing / Beacon Mission

Required checks:

- media approval status;
- campaign channel;
- exact copy;
- stock/fulfilment readiness;
- public claim safety;
- spend cap;
- owner approval phrase when posting is enabled.

Beacon must optimize for qualified sales the farm can fulfil, not vanity metrics.

## Customer/SAM Mission

Required checks:

- no invented price, availability, timing, payment, or booking;
- one useful follow-up when clarifying;
- backend gate validates facts;
- WhatsApp service-window/template rules are respected;
- customer-facing wording is preserved if already good.

## Farm Record Mission

Required checks:

- source-of-truth table/view identified;
- backend-owned write path exists;
- audit/event logging exists or is explicitly designed;
- owner approval required for lifecycle/purpose/death/movement/medical changes;
- no direct sheet/Supabase write bypass.

## Data/Migration Mission

Required checks:

- additive migration plan;
- backup/rollback strategy;
- dry-run/import verification;
- no production write unless approved;
- Supabase vs Google Sheets ownership stated;
- tests and live verification plan.

## Source References

- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`
- `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`
- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`
