# CMQ-20260813-05 CORE Bootstrap Commissioning Packet

Status: `PROTECTED_BOUNDARY / ACTIVATION_NOT_AUTHORIZED`

Observed: 2026-08-26T00:00:00+02:00 (reconciled after authoritative-main
advance; runtime evidence re-read 2026-08-26)

## Governance preflight

- Worktree: `C:\tmp\cmq05-core-bootstrap-20260825`; branch
  `fix/cmq05-core-bootstrap-20260825`; clean base
  `6b51eb1984bb55bd63635354ad9f8e6bf4b9ad6a`.
- The tracked Mission Standard was present and read completely from blob
  `3002b94713e286c4eb2019419c438cc378c337fa` (filesystem SHA-256
  `44e34c69145b83d2cd5b6a5322a6c2c124789fa647e19f19b3e39a7293a5202b`,
  1,127 physical lines).
- The tracked Control Tower protocol was present and read completely from blob
  `8fbd0b9c9160164e31a17a2cbfa51ab88792a909` (filesystem SHA-256
  `d4eb4b54a660ce39dfc92cb0fa253b0f2e3d7314462984702602d0f4b66a7e0a`,
  319 physical lines).
- The tracked Runtime Programme was present and read completely from blob
  `fb44d7f86c47e605c283ed33c28ba2c4267d6edb` (filesystem SHA-256
  `721281eeacc33ae11877ce610fe7a76ba06de6b75db4573f64933073fd358309`,
  278 physical lines).
- The tracked feedback template was present and read completely from blob
  `1233aee625e45821a685614a33b1eb101c666ffd` (filesystem SHA-256
  `6d81bdfd41770f30e7e2e9acea584e747e007fe3ab155d3427fb17599a26111f`,
  266 physical lines).
- The dirty owner checkout and every pre-existing worktree were preserved.

## Exact current truth

- Authoritative `origin/main`: `8144e572828d92955b44b5c691b8ce2bfa2477d6`,
  committed `2026-08-25T23:57:14+02:00`. The four-commit advance from the
  original audit changes only the GREEN 0.3.11 release-order artifact and the
  durable register. It changes no CORE runtime, staging, activation, watchdog,
  queue or test source. Its register finding is preserved without priority
  change when this packet branch reconciles current main.
- Governed stop marker exists at `.charlie_runner/supervisor.stop`, SHA-256
  `8887c0c06d040b60fef580c0135761019fe7e416d594538cf86fcf18d1e594b1`.
- Supervisor and runner are stopped. The last heartbeat is stale; PID `52052`
  is not alive; last result is `runner_startup_refused` for
  `governed_stop_active`.
- Staged runtime and execution revision are both
  `3961411236fca3329abaac2d34cfb863167c1c73`; manifest version is
  `charlie_core_runtime_v1`, validation receipt SHA-256
  `ff64d3f410b0878da0a7dc619d4a850116ea919082c4f72f1210fd2a84c7332b`,
  release lane `581ee9ccd81b4e25bbf9403a49fa6e49`. They do not equal current main.
- Scheduled task `\CHARLIE CORE Runner Watchdog` is disabled. Watchdog
  projection is `governed_stop_active`.
- Historical activation `4ee5c3545bb84873b8f65581736a3caf` is recovered,
  sealed evidence and must never be reused.
- Queue readback reports zero runnable approved missions. No pickup was
  attempted by this audit.
- Open CORE PRs #693, #700, #713, #1032 and #1036 are historical/stale evidence,
  not current activation authority. None was merged or closed by this work.

## Minimum engineering-loop capability matrix

`Source/test` describes repository capability only. `Commissioned/natural`
requires fresh runtime evidence and is never inferred from code.

| # | Journey row | Source/test truth | Commissioned / naturally proven | Smallest next gate |
|---:|---|---|---|---|
| 1 | Owner instruction enters canonical mission path | Exists / tested | No | Authorized canary insertion |
| 2 | Existing mission found before create | Exists / tested | No | Canary readback |
| 3 | Owner approval recorded | Exists / tested | No | Exact canary approval |
| 4 | Mission execution eligibility | Exists / tested | No | Canary admission |
| 5 | Supervisor controller ownership | Exists / tested | No | Fresh activation |
| 6 | Runner same-generation ownership | Exists / tested | No | Fresh activation |
| 7 | Exact loaded-revision heartbeat | Exists / tested | No; staged revision stale | Restage exact candidate |
| 8 | One canonical queue watched | Exists / tested | No | Fresh activation |
| 9 | Exactly-once claim | Exists / tested | No | Natural canary pickup |
| 10 | Collision/worktree guards | Exists / tested | No | Canary evidence |
| 11 | Existing Codex bridge invocation | Exists / tested | No | Canary execution |
| 12 | Mission-owned workspace only | Exists / tested | No | Canary evidence |
| 13 | Structured final artifact | Exists / tested | No | Canary artifact |
| 14 | Tests and Brain Guard | Exists / tested | No | Canary results |
| 15 | Branch push | Exists / tested | No | Canary result |
| 16 | PR create/update | Exists / tested | No | Canary result |
| 17 | Stop at owner review | Exists / tested | No | Canary owner-review state |
| 18 | Concise Telegram/dashboard decision | Exists / tested | No | Owner-visible canary result |
| 19 | Merge/deploy exact release gate | Exists / tested; release bridge requires `release_approved` | No | Preserve separate approval |
| 20 | Bounded idempotent restart | Exists / tested | No | Restart acceptance |
| 21 | Terminal-close continuity | Source contract exists | No | Close terminal during canary |
| 22 | Later independent cycle | Source contract exists | No | Observe next scheduled cycle |

No current-main source defect was established by this audit. The first blocker
is protected commissioning of the exact current candidate; no replacement
queue, runner, supervisor, database, agent framework or release system is
justified.

The authoritative-main advance does not change this conclusion. It also does
not establish the immutable commissioning candidate: this documentation receipt
must first integrate, after which a fresh signed validation/staging packet must
bind the resulting exact 40-character `origin/main` revision. Consequently the
approval sentence below is unchanged, but it is not actionable against
`8144e572...` or any present staging artifact.

## Exact non-activating commissioning packet

- Lineage: `CMQ-20260813-05`.
- Source candidate: the future exact `origin/main` revision after this receipt
  is integrated; activation authority must bind that immutable 40-character SHA.
- Runtime/execution: must be freshly validated and staged from that same SHA;
  the present `396141...` staging is ineligible.
- Required identities: new single-use 32-lowercase-hex activation ID, new
  signed validation receipt, staged manifest and task-instance evidence. No
  historical identity is reusable.
- Stop state: marker and digest above remain unchanged until the exact later
  authorization is consumed.
- Task: `\CHARLIE CORE Runner Watchdog`, currently disabled. No task mutation is
  authorized by this packet.
- Supervisor command: staged `scripts/charlie_runner_supervisor.py` through the
  existing watchdog action.
- Runner command/profile: ordinary existing pickup/Codex command; one worker;
  release watching may observe but merge/deploy remains impossible until the
  canonical mission reaches exact candidate-bound `release_approved`.
- Execution mode: ordinary repository-only T1 canary, deny production,
  provider, customer, farm, money, hardware, printer, migration and secret
  effects.
- Expiry: 30 minutes after the future signed activation authority is issued.
- Canary: exactly one already-approved harmless repository-only mission,
  dedicated source/test surface, one mission identity, one worker, one branch,
  one PR, frozen acceptance matrix; stop at owner review.
- Containment: on revision/generation/ownership/heartbeat/mission/worktree,
  artifact, test, replay or duplicate contradiction, restore governed stop,
  disable the exact task instance, preserve evidence and make no release.
- Rollback: terminate only the controller-owned process tree, restore the exact
  stop marker, disable the exact task, archive the single-use activation epoch,
  preserve mission/worktree/PR evidence and verify no provider/farm effects.
- Expected process tree: Task Scheduler watchdog -> one supervisor -> one
  same-generation runner -> bounded Codex child only while executing.
- Expected mission transitions: approved/eligible -> exactly-once claim ->
  in-progress staged agents -> tested/reviewed -> PR-ready/owner-review; never
  `release_approved`, merged or deployed in the canary journey.
- Expected result: structured final artifact, passing checks, isolated pushed
  branch and exactly one PR bound to the mission and candidate revision.
- Terminal-close acceptance: after startup evidence is captured, close the
  visible development terminal; heartbeat, worker ownership and mission
  progress must remain fresh, then a later independent observation cycle must
  occur without terminal support.

Exact later authorization sentence:

> I authorize commissioning CMQ-20260813-05 for the single revision-bound repository-only canary identified in the signed packet: consume its fresh one-time activation identity, remove only its governed stop marker, enable and run only the exact registered CHARLIE CORE Runner Watchdog task for one worker, and automatically contain without merge, deployment, migration, provider, customer, farm, hardware, printer or secret effects on any mismatch.

## Feedback handover transaction

```json
{
  "contract_version": "core_mission_outcome_handover_v1",
  "handover_id": "CMQ-20260813-05-CORE-BOOTSTRAP-20260825",
  "mission_id": "CMQ-20260813-05",
  "reporting_actor_type": "terminal",
  "terminal_disposition": "source_audit_complete_protected_commissioning_boundary",
  "requested_lifecycle": "PROTECTED_BOUNDARY",
  "technical_milestones": ["current_truth_recorded", "commissioning_packet_prepared"],
  "applicability": {
    "operational_actor": {"state":"not_applicable","reason_code":"not_activated","reason":"CORE remained governed-stopped","authority":"owner packet","audit_ref":"CMQ-20260813-05-CORE-BOOTSTRAP-20260825"}
  },
  "evidence": {},
  "next_safe_stage": "owner_authorized_revision_bound_commissioning",
  "hold": {
    "type": "PROTECTED_BOUNDARY",
    "owner": "Charl",
    "reason": "activation, stop-marker removal and Task Scheduler enablement require exact later authority",
    "wake_condition": "owner supplies the exact sentence against a fresh signed packet",
    "automatic_continuation_trigger": "consume the fresh single-use activation authority and run the bounded canary"
  }
}
```

Business result: **NO BUSINESS OUTCOME**. This packet is prepared evidence; CORE
is not commissioned, activated, operational or terminal-independent.
