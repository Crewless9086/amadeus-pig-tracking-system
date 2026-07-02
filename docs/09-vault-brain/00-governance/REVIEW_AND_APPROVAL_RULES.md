# Review And Approval Rules

## Owner Authority

Charl is the owner and final decision authority.

## Approval Levels

- LEVEL 0: report only.
- LEVEL 1: read-only investigation and planning.
- LEVEL 2: docs/planning edits.
- LEVEL 3: code/test/PR build, no merge.
- LEVEL 4: release/merge/deploy handoff after final review.
- LEVEL 5: destructive or production data-changing work; requires exact explicit approval.

## Hard Gates

No agent may bypass owner-approved rails for customer sends, public posts, payments, deposits, reservations, stock allocation, farm lifecycle changes, dispatch, hardware control, migrations, production data writes, deploys, secrets, or destructive cleanup.

## Review Philosophy

Owner review must show truth, not a sales pitch. The review packet must show what changed, why it works, what risks remain, and what decision is needed.
