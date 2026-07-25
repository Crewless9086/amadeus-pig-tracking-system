# Current System Operating Status

Evidence cut: **2026-07-25 07:35 UTC**

Repository revision: [`fd8b6185eec808f15e06773d146d3c661777e81b`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/fd8b6185eec808f15e06773d146d3c661777e81b) (`origin/main`)

This is the concise owner entry point for what the system can safely be treated
as doing now. It distinguishes code, release and live proof. It does not replace
Supabase runtime state, GitHub, Render or an owner decision.

## Owner summary

- Production is live at the evidence revision above and its post-merge CI and
  public health check passed.
- CHARLIE/CORE remains active, but overnight recovery is not converging. Three
  approved recovery missions have no lease, overlapping PRs #453-#455 fail
  `charlie-core`, and PR #445 still waits for owner review. This does not by
  itself imply a dead runner.
- SAM Livestock and SAM Meat remain supervised, fail-closed paths. Global
  autoreplies are disabled. Protected sends, orders, reservations, allocations,
  payments and farm writes remain separately gated.
- SAM Telegram callback ownership is split between backend-native Livestock
  callback data and the live n8n Telegram trigger. The tested return-to-SAM
  callback was intercepted by legacy Orders logic and performed no lifecycle
  action or cleanup; Telegram lifecycle cleanup is not operational.
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
| CHARLIE / CORE | Yes | Yes | Yes | Runtime, execution worktrees and manifest were promoted to [`5f35c21`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/5f35c2116bb309eed6769477173b207183933ba6); runner, supervisor and watchdog health and natural child scheduling were observed. CORE is active but the current protected-pause recovery is multiplying missions/candidates rather than converging. This is not evidence of a dead runner. |
| SAM Livestock | Yes | Yes | Yes | Policy/auth guards and the fail-closed exact-animal contract are live. One corrected owner-authenticated GET using the canonical `pigs` envelope observed 213 animals with source/observation timestamps, known allocation-query state and `herdmaster_exact_animal_eligibility_v1` on every row. Deployed SAM → Herdmaster exact matching is operationally proven; the three tested requirements selected none and reported shortfalls 1/2/3 because no animals were affirmatively eligible. This is not zero-physical-stock proof. Global/canary autoreply is off. The HUMAN audit correction is built locally but not merged or deployed. Telegram callback delivery and lifecycle cleanup are not operational because live webhook ownership remains split with legacy n8n handling. |
| SAM Meat | Yes | Yes | Yes | Owner-only review UI, policy and fail-closed empty state are proven. Real conversation processing is **NO-GO** after conversation `1978` timed out in Meat and was independently routed into Livestock. No reply or protected business action occurred. |
| Beacon | Yes | Yes | Yes | Story Desk policy, read-only Meta preview, authoritative opportunity adapter and binary transport code are deployed. Real binary upload was deliberately not exercised, so transport is merged/deployed rather than operationally proven. Meta evidence import has zero verified imported rows after `execute_append_failed`. No post, boost, spend or send is implied. |
| Herdmaster | Partial | Partial | Partial | Existing read-only herd reasoning and deployed SAM → Herdmaster exact-animal matching are operationally proven. Exact availability still requires complete current evidence; the tested requirements had no affirmatively eligible animals and do not prove zero physical stock. Observation/management-intent Data Model, capture and Frontend candidates remain split across open PRs; their protected migration is unapplied, so that programme is not an operational capability. |
| Production Observer | Procedure only | Not applicable | Not applicable | The observer lane is read-only evidence reconciliation. Its reports do not deploy code, mutate state or establish business-operation proof by themselves. |
| Documentation governance | Yes | Pending this PR | No | This status entry point and the temporary lane ledger follow the claim protocol. Repository docs remain guidance; they are not runtime truth. |

## Known faults and containment

| Fault / evidence | Current containment | Next proof gate |
| --- | --- | --- |
| **SAM Meat conversation `1978` wrong-lane incident.** Meat processing timed out after 30.696 seconds before review persistence; a separate webhook then invoked Livestock, which continued readers, matching, pricing and an owner card despite current-message Meat classification. | Canary stopped after step 1. No reply, retry, reset, resolution, order, payment, reservation, allocation, stock or farm write. Autoreply and dispatch remain disabled. | One authoritative lane decision; Livestock must return before readers/cards on wrong-lane input; blank category must produce no match, price or private animal sample; bound slow Meat truth reads; prove duplicate delivery creates only the Meat review identity. |
| **SAM Telegram callback ownership is split-brain.** Backend-native SAM Livestock creates `callback_data` using `sam_live_review_*`, while the live Telegram trigger remains owned by active n8n workflow `2 - The GateKeeper`. Pressing `Done - Return to SAM` was intercepted by legacy n8n Orders Sub Agent logic, whose exact workflow contains `Invalid approval button data received. No action was taken.` The callback therefore performed no SAM lifecycle action, no HUMAN-to-AUTO transition and no exact-card cleanup. This is separate from conversation `1978`, where definitive Meat input was also delivered to the Livestock inbound lane. | Do not claim Telegram lifecycle cleanup, return-to-SAM handling or callback delivery as operational. Treat `calls_n8n=false` as backend-call behavior only; it does not prove Telegram webhook ownership. Do not retry or mutate the affected card/conversation as part of documentation reconciliation. | Establish one authoritative callback owner and route `sam_live_review_*` to the backend-native lifecycle with exact-card identity, authorization and replay protection; then prove HUMAN-to-AUTO and exact cleanup in one controlled smoke. Separately correct the definitive-Meat-to-Livestock handoff for conversation `1978`. |
| **SAM Livestock HUMAN audit N+1 timeout and unstructured 500.** The configured audit opened one review query per HUMAN conversation, exceeded Gunicorn timeout and allowed `SystemExit` to escape as generic HTML 500. | Do not retry the production audit. Local candidate [`908dfbf`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/908dfbfb61dea9d832d665968d755e440d509888) batches the latest-review read and returns structured unavailable evidence. It is not merged or deployed. | Review, PR, exact-head CI, merge and exact-revision deploy; then one neutral-login, owner-authenticated GET. Until that succeeds, HUMAN recovery counts and classifications are unknown and recovery is not operationally proven. |
| **SAM Livestock exact matching is operational; tested availability remains bounded.** A corrected owner-authenticated GET used the canonical `pigs` envelope and observed 213 animals. Source and observation timestamps were present, allocation-query state was known, and every row carried `herdmaster_exact_animal_eligibility_v1`. Requests for one male grower at 25-29 kg, two male growers at 25-29 kg, and three male growers around 30 kg selected 0 and reported shortfalls 1/2/3. | Treat exact matching as operational, but do not translate those shortfalls into zero physical stock. No animal was affirmatively eligible for the tested requirements. Do not expose private animal evidence, promise availability, reserve, assign or write stock/farm state. No private evidence or protected mutation occurred during proof. | Require complete, current evidence on every new exact-availability decision. Missing, stale or incomplete evidence must continue to fail closed. |
| **Beacon Meta evidence import failed.** A fresh approved execution returned HTTP 500 `execute_append_failed`; the append transaction committed no Meta rows. | Do not retry or reuse the packet. The 64 legacy rows remain; verified Meta import count is zero. Ranking must not treat preview data as imported evidence. | Add sanitized operation-stage/exception-class/SQLSTATE diagnostics and prove transactional rollback in disposable Postgres; prepare a fresh packet and obtain separate owner append authority. |
| **Beacon image transport proof is incomplete.** PR [#451](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/451) is merged and deployed at the evidence revision; exact-deployed routes and policy report server binary multipart transport. | Do not describe upload/posting as operational. The failed historical packet is non-retryable. Public livestock policy remains the final pre-upload gate. | Separately authorized one-shot transport proof with exact asset/caption identity, no automatic retry, append-only stage evidence and immediate stop on ambiguous outcome. |
| **CHARLIE owner-handoff audit binding is unresolved in production.** Local candidate `585972f5291544dd7164d1695628cc7d70df7cf4` binds the durable `pr_ready` transaction, outbox state and candidate-bound callbacks and passed its recorded tests. Existing mission/card/outbox state remained untouched. | Treat owner-card/review snapshots as advisory; re-read current mission state and deterministic readiness on every owner action. Do not infer release authority from `pr_ready`. The correction is built locally but not merged, deployed or operational. | Review and integrate the bounded candidate separately, then prove atomic, replayed and delayed delivery behavior at its exact deployed revision. |
| **PR #445 lifecycle canary is stale and unwired.** The open PR adds only a pure module and tests; its own description states there is no route/runtime wiring. Its mission `CHARLIE-SCOPE-40BD1F16C18050B9` is `pr_ready`, so the owner card remains a pending decision, not current capability. | Do not run it as a production canary or call it operational. No lifecycle write is authorized. | Owner reviews the exact current-head diff and decides whether to refresh/rebase, wire through a separately scoped read-only surface, or close/supersede it. |
| **Older lifecycle candidates remain open.** PR [#413](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/413) is an older safe-order lifecycle canary candidate and PR #434 is an older pig-lifecycle presentation candidate. Neither is merged current capability. | Do not combine or operationalize them by implication. | Owner closes, refreshes or supersedes each against current main after checking overlap with #445 and active Herdmaster work. |
| **Herdmaster Data Model and migration gates conflict across open candidates.** PRs [#422](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/422), [#439](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/439) and [#447](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/447) overlap the same model docs and protected migration; PR [#434](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/434) also overlaps the farm-model docs. | Use none as operational truth. The migration `202607220001_complete_pig_observation_and_management_intent_events.sql` remains unapplied and the public capture tables/routes are not established by merged main. | Owner selects one lineage, closes/supersedes stale duplicates, reconciles capture prerequisites, obtains candidate-bound Risk/QA review and separately approves migration application. |
| **Herdmaster Frontend mission lacks a merged backend prerequisite.** Mission `CHARLIE-SCOPE-DE10163AB1453469` is now `approved` / `internal_recovery_queued` with no lease. Its retained Architect evidence blocks Builder because capture/read routes are absent from current main. | Preserve the block; do not invent a UI contract or edit active Data Model/source-map docs. | Merge or otherwise owner-accept the correct backend/data lineage first, without applying the protected migration implicitly; then re-plan Frontend against current main. |
| **Overnight CORE protected-pause recovery is not converging.** Nested recovery mission `CHARLIE-SCOPE-5D9241AECABB3216-RI86AFDCB2-RIF7F50339-RIE9C8F888` is `approved`, current agent `idea_expander`, with no lease. Frontend mission `CHARLIE-SCOPE-DE10163AB1453469` and queue-filter mission `CHARLIE-SCOPE-BDC9DE4E2E6FF629` are `approved` / `internal_recovery_queued`, also with no lease. PR #445 remains `pr_ready` and owner-review pending. | Do not infer a dead runner from these snapshots. The containment problem is recovery multiplication and overlapping candidates, not proven process death. Do not create another recovery or apply a migration. | Reconcile the recovery family to one authoritative candidate and one next stage; preserve PR #445 as a separate owner decision. |
| **Protected-pause candidates #453-#455 overlap and fail governed CI.** PR [#453](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/453) at `26a29ab`, [#454](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/454) at `a9c304d`, and [#455](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/455) at `19444fc` all address protected-pause revision binding. PRs #454 and #455 repeat Data Model, source-map and protected-migration scope. The newest `charlie-core` run fails `test_product_protected_pause_accepts_explicit_preexisting_scope_aliases` and `test_product_reviewer_migration_application_pause_is_not_builder_backflow` because the protected pause is classified as non-passing `recommended_owner_decision=pause`. | None is mergeable in the governed sense while required `charlie-core` fails, even where GitHub reports textual mergeability. No migration is authorized. Do not combine green audit/browser checks with failed CORE CI into a passing claim. | Select one lineage, remove duplicated Data Model/migration scope, reconcile the two protected-pause expectations, and require fresh exact-head `charlie-core` success before owner release review. |

## Overnight and morning handoff

Owner actions, in order:

1. Keep SAM Meat conversation `1978` and all autoreply/canary switches stopped.
   Authorize correction work only after shared-route ownership is explicit.
2. Resolve SAM Telegram callback ownership before treating owner cards as a
   working lifecycle. `calls_n8n=false` is not webhook-delivery proof. Keep the
   conversation `1978` routing correction separate from callback ownership.
3. Review the small SAM Livestock HUMAN-audit batching candidate. If accepted,
   require a PR, exact-head CI and exact-revision deploy before authorizing one
   owner-authenticated audit GET. Do not interpret prior 500s as zero HUMAN
   conversations.
4. Choose a single Herdmaster observation/management-intent lineage among open
   PRs #422, #439, #447, #454 and #455; reconcile or close the others. Treat
   #434 as an adjacent overlap. Do not apply the protected migration from any
   candidate.
5. Decide PR #445 separately. It is a read-only pure canary module with green
   historical CI, but is stale against current main and not runtime-wired.
6. Keep Beacon livestock output non-commercial. Decide whether to fund a fresh,
   instrumented Meta evidence-import diagnostic; do not retry the failed packet.
7. Authorize real Beacon binary upload proof only as a separate protected
   operation. Merged/deployed transport code and GET-only route proof are not a
   successful Facebook upload.
8. Stop CORE recovery multiplication. Select one protected-pause candidate,
   resolve both failing `charlie-core` expectations, and require fresh
   exact-head CI before owner review. Separately review the built
   `fix/core-atomic-owner-handoff` candidate; do not rely on delayed owner cards
   before deployed candidate-bound atomic and replay proof.

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
- Current CORE protected-pause candidates: PRs
  [#453](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/453),
  [#454](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/454) and
  [#455](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/455);
  newest failing `charlie-core` run `30135097113`.
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
