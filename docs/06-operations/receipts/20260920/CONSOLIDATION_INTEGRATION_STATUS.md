# Consolidation qualification and retention verification — 2026-09-20

Status: current-state evidence; NON_DOCTRINE. Mission
`REPOSITORY-CONSOLIDATION-20260918`; coordinator
`CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`, task
`01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`.

## Owner direction and sequence

Charl approved reconciling the original 18 commits before other application
work, then the general-manager worker and the five identified sources of drift.
The intended outcome remains a current family-to-farm journey through Oom
Sakkie and HERDMASTER, verified results and independent follow-up, while CORE
removes engineering relay work. This receipt does not claim that outcome.

Preserve the original commits. Do not enable SAM sends, replay historical farm
events, mutate production data, publish campaigns or operate hardware as an
incidental consequence of reconciliation. Existing admission and release
boundaries remain intact. No application implementation has started in this
continuation; admission repair is a prerequisite to integration.

## Final physical retention: verified

At 2026-09-20 10:54:37 UTC / 12:54:37 SAST, a read-only full native audit of
`C:\Amadeus\recovery\20260919\retained-originals\agents\amadeus-pig-tracking-system`
matched the preserved pre-move baseline. The old OneDrive source is absent.

- Same native volume `17629920732283616668`, inode `47850746040959140`,
  attributes49/tag0.
- 172,892 objects, 154,225 ordinary files, one opaque junction, zero Cloud
  dependencies. Content streams, identities, security, attributes and raw
  opaque-link data match; the junction target was not traversed.
- Stable digest, both baseline and retained:
  `45ff8ca2419db7308d58735de5cf9cf0e61163b5f35c93b9a0cf2122bc7cae42`.
- Manifest SHA256:
  `5f7e453f807487a6bf7bc10bed5c96f53940f0b6f4d61581d9f74c07abd6f055`.

The prior 556 retained source roots plus this final verified root make 557.
This audit moved/deleted nothing and changed no ACL. A non-administrator audit
first failed with Access is denied; the bounded administrator read-only audit
then passed. Earlier failures and manual handoff remain historical evidence.
Do not rerun the obsolete move or restart instructions.

## Exact source qualification

- Canonical checkout: `C:\Amadeus\repo`; only registered worktree at startup.
- Continuing branch: `codex/workspace-consolidation-20260919`.
- Original 18-commit candidate: `013a9ebe23c3fedeedb285a88ad5103aad1d6a97`.
- Candidate tree: `a6c2b1aef531d903d212f48b346356aa4ac025a5`.
- Fresh fetched main: `e46743cb3e8d224b60d17eb5920acb113f613a52`.
- Startup: clean, no upstream, 18 ahead/0 behind. Canonical workspace guard PASS.
- Governance preflight: common and CORE packs loaded; tracked standard blob
  `5fbcf11ebdfd171a286339de83a205df782dabd4`, unchanged from prior full read.
- 119 focused tests PASS, zero failures/errors/skips. Suites cover Vault
  retrieval/alignment, workspace archive/check/retirement/retention and SAM
  review-obligation capture regressions. Credential fallback removal was
  source-reviewed; those five SAM tests do not exercise credential loading. Network connections were blocked;
  test outputs were routed to the assigned sibling runtime.
- Independent source review found no actionable P1/P2 in the consolidation's
  Python changes. This is not hosted CI, admission, deployment or business proof.
- Older broader 302/332 qualification and its 30 offline-boundary failures
  remain preserved; no full-suite green claim is made.

This receipt and current-state documentation reconciliation are subsequent
documentation changes; they do not rewrite the original 18 commits or imply
that the earlier tests covered a later source revision.

## Integration blockers, reproduced

1. Read-only canonical SQL at 10:49:17 UTC returned no
   `public.charlie_missions` row for `REPOSITORY-CONSOLIDATION-20260918`.
   The transaction proved `transaction_read_only=on` and rolled back. Existing
   candidate binding requires a mission. A truthful Desktop first-registration
   path must be established; do not invent a Hermes identity or write metadata
   directly to bypass the contract. This is distinct from PR1340's older
   candidate-succession conflict.
2. `scripts/charlie_mission_admission_guard.py` issues governance identities from
   the PR base, while verification compares them with the candidate head. Five
   governed documents changed in this consolidation. The same base receipt
   passes against base and fails against head with `admission_governance_changed`.
   Local reproduction used no signatures or provider writes. A repair must
   preserve protected baseline authority and exact reviewed candidate identities.
3. Protected issuance/check workflows execute trusted main/base code. A change
   only inside this candidate cannot bootstrap its own authority. The supported
   maintainer repair path is under review; no bypass or false check is permitted.

Main protection requires strict checks: charlie-core, disposable Postgres audit
rails, closed Render migration rail, Playwright behavior, and mission-admission
from its designated App. Admin enforcement is enabled. No protection was changed.
No consolidation PR existed at initial readback. Hosted qualification and exact
signed admission remain required before integration. Verify actual web-service
auto-deploy settings before merge; worker Blueprint settings do not prove web
deployment behavior.

## Bounded admission repair preparation

A second isolated worktree was created from the same main at
`C:\Amadeus\.runtime\consolidation\integration-20260920\admission-repair`,
branch `codex/consolidation-admission-repair-20260920`. It prepares only the
issuer mismatch correction and a reviewed, dry-run-default, exact-mission
maintainer registration command. Production use of that new administrative
command requires its own concrete authorization after review. No database
write, signature, bypass, worker dispatch or protected workflow change follows
from preparing it. Keeping its required governance bytes identical to main
allows normal existing admission to validate the prerequisite repair once
truthful canonical registration is authorized and proven. Its code and tests
are still under review; this is not an integrated or operational capability.

## Public draft publication hold

Automatic approval review rejected the attempted branch push and draft PR
creation because the GitHub repository is public and explicit authorization
for this exact payload and destination was missing. The command did not execute;
no push or PR occurred. This does not block local repair preparation.
The reviewed payload contains the original 18 commits and one documentation
follow-up, including historical records, local paths and coordination/recovery
metadata. A bounded scan of all 19 commits and 68 changed blobs found no matches
for the tested credential patterns; that is not exhaustive secret assurance.
Public publication needs the owner's exact payload/destination decision, with
no merge, deployment, database write or worker activation included.

## Runtime truth and next gates

The 08:39 SAST readback found Docker processes absent and local n8n port5678
unavailable after restart; four CHARLIE tasks remained Disabled. Production web
revision was `3d321e4932cf205d03e759cc71a26edd411bc9d2`. These are dated
observations, not continuous health claims. Local cleanup does not start agents.

After consolidation integration, reconcile these bounded issues in existing
lineages: general-manager invocation/independent cycles; stale Sheets/n8n
architecture references; explicit canonical ownership instead of silent data
fallback; external CORE runtime output; truthful fleet status; truthful SAM
shadow-mode reporting. Shadow mode itself is not permission to send customers
messages. Prove the genuine Oom Sakkie/HERDMASTER journey only after its exact
deployed path, authority, readback, replay safety and later independent cycle.

Working evidence is under
`C:\Amadeus\.runtime\consolidation\integration-20260920\evidence`:
`manual-move-retained-result.json`, `manual-move-retained-audit.json`,
`consolidation-tests.json`, `consolidation-tests.log`,
`canonical-consolidation-readback.json`, and
`governance-admission-reproduction.json`. No secrets belong in Git.

Decision: WAIT for integration; physical retention PASS.
Why: source qualification cannot substitute for correct signed admission.
Send to exact terminal: CONTINUE—SEND NOTHING; this coordinator owns preparation.
Expected business result: a preserved, qualified source baseline before the
existing agents' operational defects are repaired. NO BUSINESS OUTCOME yet.
ACTION REQUIRED NOW: Decide whether to publish the reviewed consolidation
branch as a draft in the public Crewless9086/amadeus-pig-tracking-system
repository. The exact publication head is supplied in the owner-facing review;
this permits no merge, deployment or canonical registration.
