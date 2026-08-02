# Oom Sakkie withdrawal relay recovery handover

Status: SOURCE_ONLY_BLOCKED_ON_SERIALIZED_RUNTIME_RELEASE

Date: 2026-07-30

## Business result

NO BUSINESS OUTCOME. The authenticated owner message remains preserved in
GateKeeper execution `61267` and relay execution `61268`. It was not printed,
resent, replayed, answered, or converted into any farm or medical fact.

## Read-only diagnosis

- Execution `61268` normalized successfully, then failed closed in
  `Code - Build Backend Gateway Request` with `relay_env_not_ready`; the HTTP
  gateway node and Telegram send path did not run.
- The current n8n variable is exactly the approved HTTPS origin
  `https://amadeus-pig-tracking-system.onrender.com`, and the gateway token is
  present. This proves current configuration, not the exact historical value
  observed by `61268`.
- The live relay workflow is active but its Build-node source hash differs
  from the reviewed committed export. It lacks `normalizeBaseUrl` and
  `base_url_diagnostic`; its `updatedAt` remains 2026-06-14.
- Current `origin/main` and Render both identify commit
  `0d7892d1fbd91559fcbc30d1ef416f6f1a7e4019`, and Render reports live.
- Render currently has the Oom Sakkie gateway disabled and lacks the gateway
  token and allowed-owner configuration. A corrected n8n request would
  therefore still not be recoverable now.
- SAM remains contained: autonomy level `0`, live-stock Level 1 disabled, and
  cohort mode disabled.

Classification: a proven historical transport-validation failure,
live-workflow/source drift, and a current Render gateway configuration
mismatch. The exact historical value seen by `61268` is unavailable in its
safe output, so whether that value was stale, malformed, or later corrected
remains unproven. There is no evidence that the reviewed committed HTTPS/local
validator rejects the approved origin. Do not describe the current n8n value
as the value seen by execution `61268`.

## Prepared source

`modules/oom_sakkie/withdrawal_relay_recovery.py` is a pure, zero-I/O
coordination contract. It binds recovery to executions `61267/61268`, requires
the approved origin, reviewed relay parity, Render gateway readiness, SAM
containment, explicit serialized-lane release, original-message identity
verification, fresh pinned source/deployment evidence, exact owner identity,
and an acquired, unconsumed replay guard bound to the message hash and recovery
key. Even when all gates pass it permits only one canonical preview; recording
and SAM notification remain false.

The required 40-hex Render commit and Charl's privacy-safe 64-hex identity
digest enter through trusted recovery authority, not through the observed
runtime snapshot. The observed deploy, reviewed deploy, authenticated sender,
configured owner, and replay guard must all match those independent pins.
`ReplayGuard` is the typed output expected from the later durable atomic guard
adapter; validating its acquisition receipt against that store remains a
production integration proof, not an authority invented by this pure kernel.

`tests/test_oom_sakkie_withdrawal_relay_recovery.py` proves incident
classification, exact-execution binding, every readiness gate, no premature
replay/send/write, preview-only authority, and SAM containment.

## Shared-runtime handover

No shared workflow, adapter, route, registry, configuration, Render service, or
n8n variable was changed. After the serialized owner explicitly releases the
lane:

1. Preserve immutable exports and hashes of executions `61267` and `61268`,
   including a privacy-safe identity hash of the normalized original message.
2. Reconcile current `origin/main`; import/update only workflow
   `TlKy9kUgJJE0msU4` from
   `docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/workflow.json`.
   Require exact Build-node hash parity, the request-ready branch,
   `normalizeBaseUrl`, `base_url_diagnostic`, no Telegram Trigger, and no
   Telegram send node.
3. Change only `OOM_SAKKIE_GATEWAY_BASE_URL` if its readback is no longer the
   exact approved HTTPS origin. Do not touch unrelated n8n variables.
4. Enable the existing Render gateway only through its governed deployment
   procedure, setting only the required gateway enable/token/allowed-owner
   values. Prove the deployed commit equals current reviewed main, health is
   green, SAM remains disabled, and unrelated routes/config are unchanged.
5. Acquire one durable replay key:
   `gatekeeper:61267/relay:61268/withdrawal-preview:v1`. Reconstruct input from
   the preserved execution record; never ask Charl to resend it.
6. Invoke the reviewed relay exactly once. Require one canonical withdrawal
   preview addressed only to Charl, with all write/dispatch/customer/public
   authority flags false.
7. A second attempt with the same replay key must produce no gateway call, no
   Telegram send, and no fact.
8. Await Charl's explicit confirmation of the exact preview. Only the existing
   governed medical/withdrawal workflow may then record supported facts exactly
   once. Regenerate HERDMASTER eligibility and notify SAM read-only only if
   supported inventory changes.
9. Preserve the existing 38 eligible pigs, make no reservation or customer
   promise, and release runtime promptly.

## Required production proof

Exact workflow-source hash, exact Render commit, three key-specific Render
readbacks, exact n8n origin readback, immutable execution hashes, one acquired
replay key, one preview send receipt, replay yielding zero additional sends,
pre-confirmation zero farm/medical facts, SAM containment readback, unchanged
unrelated workflow/route fingerprints, and post-confirmation fact idempotency.
