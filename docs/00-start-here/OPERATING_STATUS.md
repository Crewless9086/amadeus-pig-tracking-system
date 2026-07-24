# Current System Operating Status

Evidence cut: **2026-07-24 21:00 UTC**

Repository revision: [`fd8b6185eec808f15e06773d146d3c661777e81b`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/fd8b6185eec808f15e06773d146d3c661777e81b) (`origin/main`)

This is the concise owner entry point for what the system can safely be treated
as doing now. It distinguishes code, release and live proof. It does not replace
Supabase runtime state, GitHub, Render or an owner decision.

## Owner summary

- Production is live at the evidence revision above and its post-merge CI and
  public health check passed.
- CHARLIE/CORE is healthy enough to run governed missions, but its latest
  recovery correction is only partly operationally proven. One Herdmaster
  Frontend mission was active at the evidence cut and one lifecycle canary
  mission was waiting for owner review.
- SAM Livestock and SAM Meat remain supervised, fail-closed paths. Global
  autoreplies are disabled. Protected sends, orders, reservations, allocations,
  payments and farm writes remain separately gated.
- The SAM Meat real canary is stopped after a Meat request also entered the
  Livestock lane. Do not resume it until single-lane routing and bounded truth
  reads are corrected and proven.
- Beacon public livestock content is restricted to non-commercial awareness,
  education, welfare, husbandry and farm stories. Public livestock commerce
  content remains prohibited even with owner approval.
- Open Herdmaster Data Model candidates and their protected migration are not
  current capability. Do not apply the migration or build Frontend assumptions
  on an unmerged candidate.

## Capability matrix

`Built` means a candidate passed its recorded build checks. `Operational` is
deliberately narrower than deployed.

| Area | Built | Merged | Deployed | Operational evidence and present limit |
| --- | --- | --- | --- | --- |
| CHARLIE / CORE | Yes | Yes | Yes | Runtime, execution worktrees and manifest were promoted to [`5f35c21`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/5f35c2116bb309eed6769477173b207183933ba6); runner, supervisor and watchdog health and natural child scheduling were observed. Exact targeted-recovery override and stable recovery-deduplication behavior were not yet naturally observed on the promoted process. |
| SAM Livestock | Yes | Yes | Yes | Policy/auth guards and fail-closed exact-animal contract are live. Exact-animal matching is implemented, but the last bounded production-shaped requests selected no affirmatively eligible animals; a later deployed read used the wrong response envelope and cannot prove current inventory. Global/canary autoreply is off. The HUMAN audit correction is built locally but not merged or deployed, and recovery is not operationally proven. |
| SAM Meat | Yes | Yes | Yes | Owner-only review UI, policy and fail-closed empty state are proven. Real conversation processing is **NO-GO** after conversation `1978` timed out in Meat and was independently routed into Livestock. No reply or protected business action occurred. |
| Beacon | Yes | Yes | Yes | Story Desk policy, read-only Meta preview, authoritative opportunity adapter and binary transport code are deployed. Real binary upload was deliberately not exercised, so transport is merged/deployed rather than operationally proven. Meta evidence import has zero verified imported rows after `execute_append_failed`. No post, boost, spend or send is implied. |
| Herdmaster | Partial | Partial | Partial | Existing read-only herd reasoning and the fail-closed exact-animal eligibility contract are operational. Observation/management-intent Data Model, capture and Frontend candidates remain split across open PRs; their protected migration is unapplied, so that programme is not an operational capability. |
| Production Observer | Procedure only | Not applicable | Not applicable | The observer lane is read-only evidence reconciliation. Its reports do not deploy code, mutate state or establish business-operation proof by themselves. |
| Documentation governance | Yes | Pending this PR | No | This status entry point and the temporary lane ledger follow the claim protocol. Repository docs remain guidance; they are not runtime truth. |

## Known faults and containment

| Fault / evidence | Current containment | Next proof gate |
| --- | --- | --- |
| **SAM Meat conversation `1978` wrong-lane incident.** Meat processing timed out after 30.696 seconds before review persistence; a separate webhook then invoked Livestock, which continued readers, matching, pricing and an owner card despite current-message Meat classification. | Canary stopped after step 1. No reply, retry, reset, resolution, order, payment, reservation, allocation, stock or farm write. Autoreply and dispatch remain disabled. | One authoritative lane decision; Livestock must return before readers/cards on wrong-lane input; blank category must produce no match, price or private animal sample; bound slow Meat truth reads; prove duplicate delivery creates only the Meat review identity. |
| **SAM Livestock HUMAN audit N+1 timeout and unstructured 500.** The configured audit opened one review query per HUMAN conversation, exceeded Gunicorn timeout and allowed `SystemExit` to escape as generic HTML 500. | Do not retry the production audit. Local candidate [`908dfbf`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/908dfbfb61dea9d832d665968d755e440d509888) batches the latest-review read and returns structured unavailable evidence. It is not merged or deployed. | Review, PR, exact-head CI, merge and exact-revision deploy; then one neutral-login, owner-authenticated GET. Until that succeeds, HUMAN recovery counts and classifications are unknown and recovery is not operationally proven. |
| **SAM Livestock exact-animal availability remains bounded.** The versioned eligibility contract is deployed, but current tested requests have no affirmatively eligible animals. A post-deploy response-envelope extraction error prevented a fresh inventory proof. | Treat proposals as owner-only and fail closed. Do not expose private animal details, promise availability, reserve, assign or write stock/farm state. | One bounded owner-authorized read using the canonical `pigs` envelope, followed by candidate-bound matching proof. No eligible result must be reported as a shortfall, not as unavailable inventory or zero stock. |
| **Beacon Meta evidence import failed.** A fresh approved execution returned HTTP 500 `execute_append_failed`; the append transaction committed no Meta rows. | Do not retry or reuse the packet. The 64 legacy rows remain; verified Meta import count is zero. Ranking must not treat preview data as imported evidence. | Add sanitized operation-stage/exception-class/SQLSTATE diagnostics and prove transactional rollback in disposable Postgres; prepare a fresh packet and obtain separate owner append authority. |
| **Beacon image transport proof is incomplete.** PR [#451](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/451) is merged and deployed at the evidence revision; exact-deployed routes and policy report server binary multipart transport. | Do not describe upload/posting as operational. The failed historical packet is non-retryable. Public livestock policy remains the final pre-upload gate. | Separately authorized one-shot transport proof with exact asset/caption identity, no automatic retry, append-only stage evidence and immediate stop on ambiguous outcome. |
| **CHARLIE owner-handoff audit binding is unresolved.** Available read-only mission evidence proves the lifecycle canary reached `pr_ready`; the active CORE correction now scopes the fault to the durable `pr_ready` transaction, executive fallback, outbox delivery state and candidate-bound Telegram callbacks. Existing mission/card/outbox state remains untouched. | Treat owner-card/review snapshots as advisory; re-read current mission state and deterministic readiness on every owner action. Do not infer release authority from `pr_ready`. The correction branch is active but is not yet built, merged, deployed or operational. | Complete the bounded candidate, reconcile exact mission events, and prove atomic/replayed/delayed delivery behavior with candidate-bound callbacks before integration. |
| **PR #445 lifecycle canary is stale and unwired.** The open PR adds only a pure module and tests; its own description states there is no route/runtime wiring. Its mission `CHARLIE-SCOPE-40BD1F16C18050B9` is `pr_ready`, so the owner card remains a pending decision, not current capability. | Do not run it as a production canary or call it operational. No lifecycle write is authorized. | Owner reviews the exact current-head diff and decides whether to refresh/rebase, wire through a separately scoped read-only surface, or close/supersede it. |
| **Older lifecycle candidates remain open.** PR [#413](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/413) is an older safe-order lifecycle canary candidate and PR #434 is an older pig-lifecycle presentation candidate. Neither is merged current capability. | Do not combine or operationalize them by implication. | Owner closes, refreshes or supersedes each against current main after checking overlap with #445 and active Herdmaster work. |
| **Herdmaster Data Model and migration gates conflict across open candidates.** PRs [#422](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/422), [#439](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/439) and [#447](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/447) overlap the same model docs and protected migration; PR [#434](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/434) also overlaps the farm-model docs. | Use none as operational truth. The migration `202607220001_complete_pig_observation_and_management_intent_events.sql` remains unapplied and the public capture tables/routes are not established by merged main. | Owner selects one lineage, closes/supersedes stale duplicates, reconciles capture prerequisites, obtains candidate-bound Risk/QA review and separately approves migration application. |
| **Active Herdmaster Frontend mission lacks a merged backend prerequisite.** At 20:56 UTC, `CHARLIE-SCOPE-DE10163AB1453469` had a healthy lease but its Architect blocked Builder because capture/read routes were absent from current main. | Preserve the block; do not invent a UI contract or edit active Data Model/source-map docs. | Merge or otherwise owner-accept the correct backend/data lineage first, without applying the protected migration implicitly; then re-plan Frontend against current main. |

## Overnight and morning handoff

Owner actions, in order:

1. Keep SAM Meat conversation `1978` and all autoreply/canary switches stopped.
   Authorize correction work only after shared-route ownership is explicit.
2. Review the small SAM Livestock HUMAN-audit batching candidate. If accepted,
   require a PR, exact-head CI and exact-revision deploy before authorizing one
   owner-authenticated audit GET. Do not interpret prior 500s as zero HUMAN
   conversations.
3. Choose a single Herdmaster observation/management-intent lineage among open
   PRs #422, #439 and #447; reconcile or close the others. Treat #434 as an
   adjacent overlap. Do not apply the protected migration from any candidate.
4. Decide PR #445 separately. It is a read-only pure canary module with green
   historical CI, but is stale against current main and not runtime-wired.
5. Keep Beacon livestock output non-commercial. Decide whether to fund a fresh,
   instrumented Meta evidence-import diagnostic; do not retry the failed packet.
6. Authorize real Beacon binary upload proof only as a separate protected
   operation. Merged/deployed transport code and GET-only route proof are not a
   successful Facebook upload.
7. Review CORE's active `fix/core-atomic-owner-handoff` candidate only after its
   exact diff and tests are recorded. Do not rely on delayed owner cards for
   release authority before candidate-bound atomic and replay proof.

## Source-of-truth and evidence rules

When records disagree, retain both and use the weaker operational state until
authoritative evidence resolves the conflict.

| Source | What it proves | What it does not prove |
| --- | --- | --- |
| Git commit on `origin/main` | Code is merged into repository main. | Render deployed it, a migration ran, or a business path works live. |
| GitHub PR and exact-head CI | Reviewed candidate scope and tests at the named SHA. | Merge, deployment, live smoke or protected operation. |
| Render exact-revision deployment and `/health` | The named revision is live and the service answered the health route. | A specific route, integration, customer flow or data operation succeeded. |
| Controlled operational evidence | Only the exact observed route/action, identity, timestamp and safety boundary. | Adjacent capabilities, autonomy or future repeatability. |
| Supabase CORE mission and lease records | Current durable mission, workflow, review and lease state. | Repository merge/deploy truth or owner authorization beyond the recorded gate. |
| Temporary `C:/tmp/amadeus-parallel-control/CLAIMS/*.md` ledgers | Lane-scoped coordination, candidate evidence and stated limitations to reconcile. | Permanent doctrine or authority to strengthen an unmerged/unproven claim. |
| Repository documentation | Durable guidance and reconciled operating context. | Live collaboration, queue, lease, deployment or production-data state. |

Tests are not a live smoke. Deployment is not operational proof. A disabled
safeguard is not a customer capability. Pending/unmerged work remains in this
fault and handoff register until stronger evidence is accepted.

## Evidence index

- Merged PR sequence reviewed: [#423](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/423)
  through [#451](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/451),
  with non-contiguous numbers and open candidates kept separate.
- Exact live revision evidence: PR #451 merge
  [`fd8b618`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/fd8b6185eec808f15e06773d146d3c661777e81b),
  post-merge CI runs `30124372366`, `30124372273`, `30124372502`, Render
  deployment `dep-d9hsn3poagis73an38eg`, and public health HTTP 200.
- CORE correction: PR [#440](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/440),
  merge [`5f35c21`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/5f35c2116bb309eed6769477173b207183933ba6).
- SAM Meat launch and diagnostics: PRs
  [#441](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/441) and
  [#450](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/450).
- SAM Livestock owner lifecycle, audit and eligibility: PRs
  [#444](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/444),
  [#446](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/446),
  [#448](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/448) and
  [#449](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/449).
- Beacon evidence, policy and transport: PRs
  [#438](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/438),
  [#442](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/442),
  [#443](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/443) and
  [#451](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/451).
- Temporary lane evidence reconciled:
  `BEACON.md`, `CORE_CHARLIE.md`, `HERDMASTER_READINESS.md`,
  `SAM_LIVESTOCK.md`, `SAM_MEAT.md` and the claim protocol under
  `C:/tmp/amadeus-parallel-control/CLAIMS/`. Sensitive runtime and customer
  details are intentionally omitted.
