# HERDMASTER Open Mission Register

## Purpose

Concise owner tracking register prepared on 2026-08-12 and maintained by Control Tower. This is a planning view, not execution authority. Reconcile authoritative main, the target worktree, the last delivered instruction and terminal/runtime ownership before dispatching any item.

Charl does not schedule this register manually. He may report observations and paste terminal feedback at any time. Control Tower records new work here, preserves its acceptance contract, and dispatches it only when the owning terminal is proven available.

## Dispatch control

| Terminal | Visible-terminal state | Current mission | Last delivery truth | Next Control Tower decision |
|---|---|---|---|---|
| HERDMASTER | **RUNNING** by Charl's latest report; exact fresh terminal acknowledgement still required in its next feedback | Individual piglet observations at weaning, including the unresolved independent livestock and data-integrity findings | Current mission was delivered by Charl; later defects are queued here and have **not** been delivered | Reconcile the next complete terminal feedback. Issue no new full mission while it remains running. Use an addendum only when the new fact is essential to the active mission and cannot safely wait. |

Allowed dispatch decisions are `CONTINUE - SEND NOTHING`, `ADDENDUM`, `NEW MISSION`, `PARALLEL MISSION`, or `WAIT FOR INPUT`. A prepared prompt remains `prompt_prepared`; it is not `delivered`, `acknowledged`, or `started` until evidence proves each transition.

## Queued owner observations and defects

| Queue order | Mission identity | Status | Dependency | Preserved owner-visible acceptance |
|---|---|---|---|---|
| HMQ-20260813-01 | Breeding Attention canonical truth: future planned weaning and recognisable litter label | `queued_not_dispatched` | Current HERDMASTER weaning-observation mission must release or explicitly absorb this as a reviewed successor without overlapping work | Molly's future planned 2026-09-11 weaning does not trigger `complete_weaning`; actual-weaning evidence remains authoritative; the dashboard tile shows Molly first and `LIT-2026-5C36` second. |
| HMQ-20260813-02 | Breeding Attention protected-page login journey | `queued_not_dispatched` | HMQ-20260813-01 or a proven disjoint successor boundary; current main and shared auth contract must be reconciled | Logged-out dashboard navigation redirects to `/owner/login?next=/api/pig-weights/breeding-attention/view`, successful login returns to the page, expired sessions redirect cleanly, and real JSON endpoints retain API-style 403 denial. |

Neither queued item authorizes source work, deployment, production access or interruption of the running terminal. Their complete continuation contracts remain in the Control Tower conversation until the next dispatch reconciliation.

## Ordered register

| Priority | Mission | Current status | Dependency | Next genuine trigger |
|---|---|---|---|---|
| 1 | Individual piglet observations at weaning | Active development mission; exact current terminal status must be reconciled from its next feedback | Preserve the existing dirty/unique mission worktree and close independent livestock and data-integrity findings | Complete reviewed integration, then retain the mission for one genuine exact-pig observation and visible HERDMASTER consumption |
| 2 | Breeding Attention canonical truth and protected-page access | Two bounded defects are registered as HMQ-20260813-01 and HMQ-20260813-02; neither has been dispatched | Current HERDMASTER mission release and authoritative-main reconciliation | Correct future planned-weaning semantics and owner-login return journey without weakening JSON endpoint privacy |
| 3 | Breeding Attention and `/matings` current-truth correction | `/matings` names, pens and windows deployed and live-proven on 2026-08-13; other lifecycle and readiness corrections remain pending | Authoritative production/read contract | Prove active-exposure exclusion, Molly nursing and body-condition holds on the real Breeding Attention page |
| 4 | `/matings` UI simplification | Ready for isolated Codex/UI work against the deployed read contract; existing dirty facelift work remains preserved | Stable, live-proven HERDMASTER read contract | Reconcile the preserved facelift and build a faithful local preview for Charl |
| 5 | Full-lifecycle genetic merit | Substantial unmerged branch work; not authoritative | Reconcile `docs/herdmaster-lifetime-genetic-merit` and `feat/herdmaster-lifetime-genetic-merit-evidence` without rebuilding blindly | Reviewed integration of mating-to-financial outcome evidence |
| 6 | Weight-batch intelligence | Implemented and merged; real-world acceptance pending | Next genuine completed weight batch | Printable report plus one concise provider-confirmed Afrikaans summary and zero-effect replay |
| 7 | Active exposure actual UIT | Event-bound, not due now | Genuine physical separation of the current group | Owner reports actual separation date, expected around 2026-08-28 |
| 8 | Lifetime evidence used in pairing recommendations | Dependent outcome | Piglet observations and full-lifecycle merit provide attributable evidence | New recommendation explains lifecycle evidence without inventing proof |

## Other historical queue entries requiring reconciliation

The repository contains older HERDMASTER auction, mortality, health/loss and breeding-attention entries and many retained worktrees. Do not automatically revive their old “next” wording. Before scheduling them, reconcile current production outcome, merged ancestry, owner need and whether the mission has already been completed or superseded.

## Evidence classification

- **Documented:** plans, branches, handovers and this register.
- **Runtime-loaded:** facts an authoritative deployed loader supplies to HERDMASTER.
- **Provider/production verified:** authenticated live responses, canonical database readback and provider delivery/readback.

A documented branch or handover is not deployed HERDMASTER knowledge until authoritative integration and loading are proven.
