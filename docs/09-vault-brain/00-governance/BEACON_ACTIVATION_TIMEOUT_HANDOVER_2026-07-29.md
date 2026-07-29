# BEACON private-photo activation timeout handover

Status: source correction prepared; production ownership remains with the
serialized SAM Livestock → HERDMASTER queue.

## Business outcome

No business outcome occurred. BEACON did not send READY, request a photo, ingest
media, or perform any public or paid action.

## Exact contained attempt

- Integrated/live revision:
  `c755ba26e1c709314f7bf4a6f151f7770cfd2002`
- Stable deployment before the attempt:
  `dep-d9l1l67avr4c73ao7r5g`
- Activation process started: 2026-07-29 15:26:41 UTC
- GateKeeper authoritative update: 2026-07-29 15:27:17.462 UTC
- Terminal command deadline: 604 seconds
- Render chronology throughout the attempt contained no deployment newer than
  `dep-d9l1l67avr4c73ao7r5g`.
- The timeout reconciliation found the intake flag false, activation-only
  Render keys restored/removed, the new GateKeeper branch and two attributable
  projections still present, one Telegram trigger, ordinary Oom Sakkie and SAM
  callback routes present, zero pending Telegram updates, all eight intake
  tables at zero, and the private bucket unchanged at nine objects.
- The exact activation process was stopped by verified PID and command line.
  The two projections and two activation-only keys were then removed, with
  intake remaining false. No media mutation occurred.

## Exact cause

The activation runner performed key-specific Render environment PUTs, created
the two n8n projections, installed and read back the reviewed GateKeeper
workflow, verified zero pending Telegram updates, and changed the intake flag.

It then called `wait_for_latest_render_stable`, which required a Render
deployment ID different from the stable baseline. Key-specific environment
updates did not create a deployment. The function exhausted 60 polls at
six-second intervals and raised `render_latest_deployment_not_stable`.

The exception entered rollback. Rollback restored the Render activation values,
then called the same deployment-ID wait before restoring the workflow and
projections. Because no deployment existed, the rollback wait also exhausted
60 six-second polls. The terminal's 604-second command deadline interrupted
this second wait before n8n rollback could run.

Classification:

- Slow successful provider operation: **no** — no new deployment identity ever
  appeared.
- Polling defect: **yes** — polling waited for an event the preceding operations
  did not request.
- Stale deployment binding: **no** — revision and baseline deployment bindings
  were exact and remained live.
- Network timeout: **no evidence** — key-specific readbacks, n8n readbacks,
  Telegram checks, health, and provider list calls succeeded.
- Workflow execution timeout: **no** — this was an API orchestration operation,
  not an n8n workflow execution.
- Genuine activation failure: **yes, at deployment orchestration** — changed
  environment values were never bound to one explicitly requested runtime
  deployment, so READY could not be proven.

## Prepared reusable correction

`scripts/beacon_render_activation.py` introduces one explicit Render deploy
request after all key-specific environment changes:

1. capture the exact stable baseline deployment IDs and request timestamp;
2. issue exactly one `POST /deploys` bound to the expected revision;
3. if the POST response is slow or ambiguous, do not retry it;
4. reconcile the deployment by exact revision, post-request provider timestamp,
   and exclusion of every baseline deployment ID;
5. fail closed if zero or multiple candidates remain;
6. poll only the adopted deployment ID to live, exact-revision completion;
7. on bounded completion timeout, cancel once and prove that exact deployment
   terminal (`canceled`, failed, deactivated, or late-live) before rollback;
   if an ambiguous create has no attributable identity or any known deployment
   remains unsettled, do not start a rollback deployment or claim containment;
8. distinguish rejection, provider failure, unknown state, revision mismatch,
   unsettled late-deploy risk, and bounded completion timeout;
9. use the same primitive after exact config restoration during rollback;
10. verify the rollback deployment is causally later and the final contained
   configuration/topology authoritatively before reporting containment.

`scripts/beacon_private_photo_activation.py` wires the coordinator into the
bounded activation state machine. It invokes each key-specific config update,
projection pair creation, canonical workflow PUT, flag enablement, activation
deployment, exact config restoration, rollback deployment, workflow
restoration, and attributable projection removal at most once. Rollback
continues safe cleanup after an individual stage failure and cannot report
containment unless the injected authoritative verifier succeeds.

This correction does not lengthen the old blind wait and does not create a
second activation attempt.

## Verification

`tests/test_beacon_render_activation.py` covers:

- immediate success;
- delayed success;
- genuine bounded timeout;
- ambiguous POST followed by one provider candidate;
- ambiguous HTTP gateway timeout followed by one provider candidate;
- ambiguous POST with no candidate;
- multiple ambiguous candidates;
- provider clock skew/precision inside the bounded tolerance;
- stale deployment identity returned by a nominally successful POST;
- explicit provider failure;
- exact-revision mismatch;
- activation deploy late-live terminalization before rollback;
- unsettled activation deployment blocking containment;
- deterministic rollback deployment;
- activation verification mismatch and containment;
- rollback ambiguity that must not claim containment;
- containment-verification exception wrapping;
- success without rollback.

`tests/test_beacon_private_photo_activation.py` additionally proves the concrete
activation seam invokes protected config, projection, workflow, flag and deploy
mutations once; preserves one-trigger and ordinary Oom Sakkie/SAM/HERDMASTER
route invariants through enforced boolean verification; rejects false or
exceptional pre-enable checks before flag/deploy mutation; emits only allowlisted
summaries rather than raw callback/provider payloads; and performs one causally
later rollback deploy before exact workflow/projection containment.

Focused source verification:

- 22 Render activation reconciliation tests passed.
- 6 bounded activation integration tests passed.
- 25 BEACON intake/route tests passed.
- 73 GateKeeper/n8n contract tests passed.

## Next production window

Do not deploy or activate from this handover while SAM Livestock or HERDMASTER
owns the serialized lane. After HERDMASTER explicitly releases:

1. acquire the lane durably;
2. reconcile current main and current live production;
3. integrate this reviewed correction normally and require exact-head/exact-
   merge CI;
4. deploy the exact merged revision and wait for a stable baseline;
5. create one fresh activation identity and use the explicit, reconciled deploy
   primitive for activation and rollback;
6. release runtime immediately after READY verification or exact containment.
