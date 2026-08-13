# Oom Sakkie durable morning runtime handover

Status: production lineage proven; replay and startup catch-up defects repaired
in follow-up source; next genuine scheduled provider result remains required.

## Startup timing policy

- The genuine scheduled boundary is 06:45 Africa/Johannesburg.
- A plan may start only from 06:45:00 through 06:59:59. This 15-minute window
  allows ordinary process jitter or a narrowly bounded restart without turning
  an arbitrary later deployment into a stale plan trigger.
- From 07:00 onward, plan evidence loaders are not called. A genuinely missed
  day competes for the same date-stable `:DELIVERY` claim and may produce only
  the existing concise bounded failure notice; concurrent or repeated startup
  is silent after the first claim.
- If that date already has a plan or failure claim, later startup performs no
  send, edit, plan construction or farm write. Missed days are never rolled
  forward or silently manufactured as plans.
- The 13 August startup catch-up, durable claim and provider delivery remain
  immutable defect evidence. They must not be deleted, rewritten or replayed.

## Production proof and follow-up defect

- Render deployed PR #865 merge
  `c735a34d1a37a35e71223999cc4b0cc37459ffb1` as
  `dep-d9ulrj3bc2fs739i8evg`, then deployed descendant `origin/main`
  `6c03d1e1a7719e2c847ce440fab5afb7bce394a2` as live deployment
  `dep-d9ulsem7bikc73b1afi0`.
- Authorized read-only Render and database inspection found no 13 August daily
  lifecycle row. The missed brief was not triggered, replayed or manufactured.
- Production history for 12 August proved one initial provider send followed by
  same-day changed-evidence recompositions against the same provider card.
  Source inspection found the cause: the delivery claim included the material
  digest, so changed evidence after restart could obtain another daily claim;
  the failure path also used a separate provider-card identity.
- Follow-up source makes `OOM-DAILY-FARM-MANAGER-YYYY-MM-DD:DELIVERY` the one
  date-stable claim shared by useful-plan and visible-failure outcomes. Material
  digest remains evidence, not claim identity. A restart, changed evidence,
  concurrent worker, later failure or ambiguous provider outcome cannot obtain
  a second send or edit for that date.
- Focused regression proof covers changed-evidence restart, repeated failure,
  success-then-failure collision and existing family lifecycle replay safety.

## Incident trace

- Intended boundary: 06:45 Africa/Johannesburg, identity
  `OOM-DAILY-FARM-MANAGER-2026-08-13`.
- Documented implementation before this correction: the daily manager was
  invoked only inside `handle_rootline_reassessment_trigger` after a request
  carrying the existing ROOTLINE scheduler identity.
- Runtime-loaded source at `42aa9bc1b9ec98b5359ef36ec931d66dfd6be5d1`
  had no backend startup loop, worker, cron manifest or independent daily route
  that could wake that lifecycle.
- Provider reconciliation supplied to the mission found no Render request and
  no active n8n workflow dedicated to the daily manager. This terminal could
  not independently open provider dashboards because no operator credentials
  were exposed to the shell and the signed-in browser surface was unavailable.
- Therefore the proven source cause is missing invocation ownership. With no
  request, authentication, manager composition, durable daily claim and
  Telegram delivery were never reached. Absence of the latter provider effects
  is consistent with, but does not strengthen, the provider evidence supplied.

## Prepared lifecycle

`modules/oom_sakkie/morning_runtime.py` starts only when Render identifies the
production process (or the explicit enable flag is set). Every process may wake,
but the existing database daily claim and provider-bound family delivery create
one logical daily lifecycle across workers and restarts. The cycle:

1. uses `ZoneInfo("Africa/Johannesburg")` and becomes due at 06:45;
2. resolves one explicitly configured owner, or the single existing allowed
   owner when unambiguous;
3. loads HERDMASTER, ROOTLINE, litter and sale evidence concurrently, read-only;
4. composes through the existing concise three-plus-three/one-question manager;
5. claims before delivery and treats provider ambiguity as terminal quarantine;
6. retries pre-claim composition failure only inside the 15-minute plan window;
   and
7. at or after 07:00 emits at most one stable provider-bound failure lifecycle
   when the date has no prior plan/failure claim.

The runtime never calls the ROOTLINE reassessment/execution coordinator and has
zero irrigation, fertilizer, borehole, farm-write, customer-send or payment
authority. n8n is unnecessary for this lifecycle.

## Workstation reconciliation

Read-only inspection found PID 9920 launching PID 10996 for
`scripts.charlie_telegram_relay`; the parent/child relationship is one observed
launch chain, not proof of two independent logical relays. The direct relay task
is disabled; the separate watchdog task is Ready and periodically active. No
process or scheduled task was stopped or changed. The production morning runtime
does not import or depend on either local relay component.

## Acceptance remaining

1. Independent review and exact-head CI.
2. Normal merge, exact-merge CI and exact-revision Render deployment.
3. Read back a fresh backend-owned invocation after deployment.
4. Observe one genuine provider-confirmed morning plan (or the policy-bounded
   provider-confirmed failure notice) and one later replay with zero send/edit.
5. Record provider identity and lifecycle evidence without copying message
   content, credentials or private family data into the repository.

Do not manually manufacture or replay the 13 August plan. The preserved late
startup delivery is defect evidence, not an accepted catch-up precedent.
