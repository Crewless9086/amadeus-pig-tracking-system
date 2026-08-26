# Molly first-treatment Telegram parity handover

Status: `DURABLY LOGGED - NOT YET AN OWNER OUTCOME` after reviewable commit.

This is a bounded repair in the existing HERDMASTER continuous-husbandry
operating loop. It adds a distinct first-treatment semantic contract, resolves
one canonical active litter, retains explicit 4/4/8 facts, asks one question for
missing medical facts, creates one protected preview, and executes through the
existing litter-health operation with Supabase required. Farrowing and treatment
remain mutually exclusive. No heat evidence is introduced.

The source was recovered from the stale uncommitted worktree into a clean
current-main worktree at `6b51eb1984bb55bd63635354ad9f8e6bf4b9ad6a`.
The stale worktree and Molly's farm records were not changed. Focused semantic,
preview, protected-action and gateway tests pass. Review, exact-current CI,
merge, deployment, read-only production preflight, one fresh genuine report,
protected confirmation, canonical medical/tally readback and later follow-up are
still required. Do not resend Molly's prior message yet.

OWNER ACTION: NONE.

## Machine handover

```json
{
  "contract_version": "core_mission_outcome_handover_v1",
  "handover_id": "HERDMASTER-CONTINUOUS-HUSBANDRY-FIRST-TREATMENT-62531A6D-20260826T052427Z",
  "mission_id": "HERDMASTER-CONTINUOUS-HUSBANDRY",
  "reporting_actor_type": "terminal",
  "terminal_disposition": "review_candidate_exact_head_ci_pending",
  "requested_lifecycle": "REVIEW_HOLD",
  "technical_milestones": ["source_ready", "tests_passed", "pr_open"],
  "applicability": {
    "operational_actor": "required",
    "genuine_trigger": "required",
    "loaded_revision": "required",
    "canonical_readback": "required",
    "provider_result": "required",
    "physical_or_customer_result": "required",
    "later_independent_cycle": "required",
    "safe_final_state": "required",
    "replay_and_concurrency_containment": "required",
    "automatic_follow_up_or_unresolved_work_ownership": "required",
    "owner_work_removal": "required"
  },
  "evidence": {},
  "next_safe_stage": "exact-head CI and independent review, then serialized merge/deployment and read-only commissioning",
  "hold": {
    "type": "EXTERNAL_HOLD",
    "owner": "GitHub CI and independent reviewer",
    "reason": "exact-head gates for 62531a6d are still pending",
    "wake_condition": "all required exact-head checks and independent review pass",
    "automatic_continuation_trigger": "Control Tower rechecks PR #1291 and dispatches the same mission into the available serialized release lane"
  }
}
```

## Governance preflight

- Worktree, branch and HEAD: `.w/molly-first-treatment-current`; `fix/herdmaster-litter-first-treatment-current-20260825`; `62531a6df8dcf6320179b08ad4b236a638d7e2fd`.
- Upstream and ahead/behind current authoritative main: upstream `origin/fix/herdmaster-litter-first-treatment-current-20260825`; review head pushed; candidate is two mission commits ahead of `origin/main` `8144e572828d92955b44b5c691b8ce2bfa2477d6`.
- Mission Standard tracked blob, filesystem SHA-256, physical lines and read completely: blob `3002b94713e286c4eb2019419c438cc378c337fa`; SHA-256 `44E34C69145B83D2CD5B6A5322A6C2C124789FA647E19F19B3E39A7293A5202B`; 1127 lines; yes.
- Control Tower Protocol tracked blob, filesystem SHA-256, physical lines and read completely: blob `8fbd0b9c9160164e31a17a2cbfa51ab88792a909`; SHA-256 `D4EB4B54A660CE39DFC92CB0FA253B0F2E3D7314462984702602D0F4B66A7E0A`; 319 lines; yes.
- Canonical Runtime Programme tracked blob, filesystem SHA-256, physical lines and read completely: blob `fb44d7f86c47e605c283ed33c28ba2c4267d6edb`; SHA-256 `721281EEACC33AE11877CE610FE7A76BA06DE6B75DB4573F64933073FD358309`; 278 lines; yes.
- Feedback template tracked blob, filesystem SHA-256, physical lines and read completely: blob `1233aee625e45821a685614a33b1eb101c666ffd`; SHA-256 `6D81BDFD41770F30E7E2E9ACEA584E747E007FE3AB155D3427FB17599A26111F`; 266 lines; yes.
- Authoritative-main comparison: original local commit `827e9485` preserves the same mission patch as former PR head `499fb958`, rebased onto current main; `62531a6d` adds the atomic protected write.
- Worktree status and preservation classification: documentation changes pending this handover commit; unique source commits pushed; `released-retain` after handover commit/push.
- Feedback evidence observation time: `2026-08-26T07:24:27+02:00`.

## Mission identity and owner outcome

- Existing mission ID: `HERDMASTER-CONTINUOUS-HUSBANDRY`.
- Owner-visible outcome: a fresh genuine first-treatment report is understood through Oom Sakkie, previewed by HERDMASTER, confirmed once, committed atomically to canonical Supabase, read back, and followed up automatically.
- Explicit non-outcomes: source, tests, PR, merge, deploy, health, synthetic preview, terminal send, historical Molly replay.
- Lifecycle state: `REVIEW_HOLD` at technical review candidate; business lifecycle remains open.
- Remaining acceptance journey: exact-head CI/review -> merge -> deploy -> read-only preflight -> fresh genuine Telegram trigger -> deployed preview -> genuine protected confirmation -> atomic write -> canonical readback -> follow-up -> later terminal-independent cycle.
- Strategic class: `CURRENT_BLOCKER` within the existing operating spine.
- Recovery-mode WIP slot: existing HERDMASTER source lane; Control Tower assigns the global slot number.
- Exact recurring owner action this mission removes: manually navigating a separate litter form and reconciling treatment/tally records after reporting the work conversationally.
- Current owner manual steps and target manual steps: current count Unknown; target is one genuine conversational report plus one irreducible protected confirmation, with zero terminal relays or record reconciliation.
- Terminal-independent proof that closes the workload reduction: deployed runtime handles a later fresh due/reassessment cycle after this worktree is released.
- Why deployed-agent enablement: the terminal only changed source/tests; it did not create the owner-facing message, confirmation, farm write or follow-up.

## Terminal state

- Visible development terminal: active through handover commit; release after push.
- Last instruction actually delivered: recover `827e9485`, reconcile PR #1291/current main, and continue safe source/test/review/integration preparation without farm writes or Telegram sends.
- Delivery proof: delivered, acknowledged, started and progress observed through commit `62531a6d` and pushed PR head.
- Worktree, branch and current action: as in governance preflight; awaiting exact-head CI/review after durable handover.
- Last terminal-invoked production/test cycle: local pytest only; no production cycle.
- What stops when this terminal closes: only active engineering observation; no deployed loop is claimed.
- Fresh progress evidence: `62531a6d`, PR #1291 exact head, focused tests.
- Why any open process is active work: no background terminal process is asserted as active.

## Deployed agent operational reality

- Exact deployed revision: Unknown; `62531a6d` is not claimed deployed.
- Web/API runtime and health: Unknown for this exact capability.
- Background worker identity: Unknown.
- Autonomous trigger/provider: genuine authenticated Telegram webhook into deployed Oom Sakkie, but exact enabled production identity is unverified.
- Trigger enabled, heartbeat, supervisor/restart state: Unknown.
- Last independently triggered cycle and canonical result: none proven for this repaired first-treatment path.
- Next cycle: a fresh genuine eligible first-treatment report after deployment; must not be manufactured.
- Production authority mode: protected confirmation plus canonical Supabase-only write; exact loaded standing-authority identity Unknown.
- Terminal independence: unproven.
- Honest classification: `Unknown` / not yet commissioned.

## Agent execution ownership

- Operational actor: deployed Oom Sakkie authenticated Telegram gateway plus deployed HERDMASTER first-treatment runtime.
- Genuine trigger: a new owner-originated authenticated Telegram report; provider/canonical identity must be recorded and `created_by_terminal:false`.
- Owner channel: private Telegram.
- Terminal-permitted actions: source, tests, review, merge/deploy preparation, read-only inspection and observation.
- Terminal-forbidden substitutions: Telegram send, protected confirmation, farm/canonical write, trigger manufacture, physical treatment, or acceptance fabrication.
- Agent-origin proof required: deployed worker/revision, webhook identity, canonical claim/correlation, provider receipt, atomic readback, automatic follow-up and later independent cycle.
- Terminal-created output present: local test evidence only.
- If terminal were closed now: no genuine first-treatment outcome is proven; PR/CI continues independently.

## Evidence classification

- Documented facts: mission standard, protocol, programme, register, existing handover and PR metadata.
- Runtime-loaded facts: none established for `62531a6d`.
- Supabase/canonical facts: none read or changed this turn.
- Provider-verified facts: GitHub accepted pushed head; no Telegram/provider journey evidence.
- Physical/customer-visible facts: none.
- Unknown/contradictory: deployed revision, worker/heartbeat, release-lane owner, standing authority ID and fresh Molly/current litter facts.

## Fresh execution epoch

- Historical identities: prior Molly message remains evidence-only and must not be replayed.
- Reusable defect repaired: protected first-treatment writes now serialize and commit the litter packet atomically.
- Fresh current-world source/new identity: required from deployed authenticated Telegram after release; absent now.
- Replay distinction: no historical input was sent, confirmed or written this turn.
- Terminal-independent subsequent proof: still required.

## Effects and authority

- Database/farm/customer/provider/hardware changes: none.
- n8n/Google Sheets authority added: no.
- Protected authority used: none.
- Standing authority ID/version/scope: Unknown; source preserves protected confirmation and Supabase-only write.
- Current action inside standing authority: yes for reversible engineering/read-only work.
- Owner interactions requested: zero.
- Governed evidence replacing owner observation: repository/GitHub for engineering state; no farm claim made.
- Owner-burden systemic defect: no new owner burden introduced; terminal relay remains prohibited acceptance.
- Owner workload delta this turn: none; only technical preparation.
- New recurring owner labour: none.
- Replay/concurrency: exact mission patch preserved; protected write now uses serializable transaction, advisory lock, row locks, conflict checks and canonical readback.

## Closeout and next action

- Owner-facing dispatch banner: `DO NOT SEND - TERMINAL ACTIVE` until this handover commit/push; then no owner relay is needed because PR gates are automatic.
- Business result: `NO BUSINESS OUTCOME`.
- Exact blocker/owner: exact-head CI and independent review; GitHub/reviewer, then serialized release-lane owner.
- Safe work remaining: commit/push this handover; observe CI; prepare review/merge evidence.
- Terminal/worktree closeout: `released-retain` after clean pushed state; preserve until merge/deployment handoff.
- Control Tower classification: `CONTINUE` through review/release, never `CLOSE`.
- Exact next terminal: HERDMASTER release lane after green exact-head review; no owner prompt now.
- Expected owner-visible result: later deployed genuine first-treatment journey records once and returns canonical closure/follow-up.
- Serialized release lane: ownership Unknown to this terminal; Control Tower must verify current ledger before merge/deploy.
- Durable register update: appended in this branch under the 2026-08-26 heading.

## Mandatory forward mission pipeline

- Intended complete specialist role: continuous herd manager maintaining litter care, treatment, welfare, weighing, breeding and follow-through through Oom Sakkie.
- Operationally proven capabilities: historical bounded HERDMASTER paths only; this repaired first-treatment path is not yet proven operational.
- Current mission: first-treatment/current health-loss outcome-depth continuation in `HERDMASTER-CONTINUOUS-HUSBANDRY`.
- Next mission after current: continue the registered continuous-husbandry queue from the next proven canonical due item; Control Tower must select from current register after this journey reaches genuine acceptance or event wait.
- Later sequenced outcomes: terminal-independent scheduled treatment reassessment and consolidated Oom Sakkie manager status.
- Dependencies/collisions: exact-head review, current serialized release lane, deployed revision, fresh genuine event; avoid overlapping protected-action/runtime releases.
- Automatic promotion trigger: CI/review pass -> release lane free -> merge/deploy/read-only commissioning -> genuine trigger -> later independent follow-up -> next registered due husbandry outcome.
- Latest owner observation: repeated chat interruption is continuity evidence for CORE, not a reprioritization of this HERDMASTER mission.
- Register evidence: exact addendum committed with this handover.
