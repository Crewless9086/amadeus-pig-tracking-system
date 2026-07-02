# Owner Operating Model

## Owner Authority

Charl is the owner and final decision authority. Every agent, workflow, dashboard, and automation exists to help Charl see, decide, and act with control.

Owner approval is not decoration. It is the boundary between suggestion/preparation and real-world action.

## Approval Levels

Use the CHARLIE mission approval levels:

- LEVEL 0: report only.
- LEVEL 1: read-only investigation and planning.
- LEVEL 2: docs/planning edits.
- LEVEL 3: code/test/PR build, no merge.
- LEVEL 4: release/merge/deploy handoff after final review.
- LEVEL 5: destructive or production data-changing work; requires exact explicit approval.

## Hard Owner Gates

No agent may bypass owner-approved rails for:

- customer sends;
- public posts;
- payment/deposit actions;
- reservations or stock allocation;
- order approval/rejection;
- farm lifecycle or purpose changes;
- medical, death, movement, litter, mating, or weight mutation outside approved paths;
- dispatch, transport promises, or delivery commitments;
- hardware control;
- migrations;
- production data writes;
- deploys/merges/releases;
- secrets or `.env` changes;
- destructive cleanup.

## Mission Intake

Owner input can be rough. CHARLIE must transform it into a mission contract with:

- raw request;
- title;
- desired outcome;
- urgency;
- mission type;
- allowed scope;
- forbidden scope;
- acceptance criteria;
- test/pressure-test plan;
- owner decisions needed;
- rollback/release plan.

Rough owner input must not be discarded. It should remain traceable through Supabase mission records, `planning/CODEX_CHAT.md`, or processed planning notes.

## Review Philosophy

Owner review should show the truth, not a sales pitch.

Every review packet should answer:

- What did the mission try to achieve?
- What was changed?
- What evidence proves it works?
- What risks remain?
- What was not done?
- What owner decision is required?

## Communication Rule

CHARLIE and agents must be clear when data is missing, stale, unverified, or blocked. They must not invent farm truth, business truth, customer truth, legal truth, or deployment truth.

## Source References

- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`
- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/README.md`
