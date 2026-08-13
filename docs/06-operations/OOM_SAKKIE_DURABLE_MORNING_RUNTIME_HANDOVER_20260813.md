# Oom Sakkie durable morning runtime handover

Status: source prepared; no production or provider effect claimed.

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
6. retries pre-claim composition failure until 12:00 SAST only; and
7. after that deadline emits one stable provider-bound failure lifecycle.

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

Do not manually manufacture the missed 13 August plan. A same-day automatic
catch-up is policy-safe only if the exact correction is deployed before 12:00
SAST; otherwise wait for the next genuine farm morning.
