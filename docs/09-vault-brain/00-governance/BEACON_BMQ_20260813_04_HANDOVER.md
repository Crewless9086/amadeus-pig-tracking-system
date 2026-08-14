# BEACON BMQ-20260813-04 handover

Mission lifecycle state: WORKING

Owner-visible outcome: an authenticated natural Oom Sakkie request returns one
current evidence-backed BEACON proposal or one precise media request exactly
once, ready for one protected owner decision.

## Reconciled implementation

The preserved `f61cce0a` source was reviewed and cherry-picked; its historical
worktree remains unchanged. The pure proposal contract is now called through
the existing authenticated Telegram gateway after the semantic LLM front door
selects the BEACON domain. No keyword classifier was added.

`modules/oom_sakkie/beacon_request_runtime.py` reads:

- current commercial priority from the existing BEACON opportunity scanner,
  whose supply side is the versioned Herdmaster/Supabase availability rail and
  whose demand side is SAM's canonical open-intake evidence;
- retained private media from the BEACON intake read model, accepting only the
  latest `library_accepted` state and retaining private preview semantics.

It stores one provider-message-bound result in the existing durable Supabase
review-event rail. Exact replay returns the stored result to the existing
family-message lifecycle, which owns safe exactly-once delivery suppression or
recovery from provider chronology; changed content under the same provider
identity conflicts closed.
Library Accept remains distinct from public-use approval, and even a media row
whose public-use state is true is projected into this internal proposal with
no public-use, publication, customer-send, spend, or farm-write authority.

The response names the objective, audience, evidence, available or missing
media, channel, copy and CTA, expected value, later measurement, and one owner
decision. Missing suitable media produces one subject/angle/orientation/purpose
request rather than a generic wait.

## Evidence classification

- Documented: this handover, BEACON doctrine, workflow and implementation
  source map.
- Runtime-loaded: only facts returned by the deployed opportunity scanner and
  private media-intake read model at request time.
- Provider-verified: inbound Telegram identity/timestamp and the family
  delivery lifecycle after deployment.
- Physical: none claimed. Media content and sale outcomes are not inferred.

## Authority and proof boundary

Production proof must use the authenticated deployed Oom Sakkie gateway with
delivery disabled/non-public, record one result exactly once, and read it back
from canonical storage. It must cause zero public posts, customer messages,
spend, media/public-use changes, farm writes or provider mutations. Publishing,
spend, customer commitment and private-media public use remain protected owner
boundaries.

Technical stage reached: source implementation and focused/broader regressions
green; independent reviews, PR/CI, exact-head integration, deployment and fresh
authenticated production proof remain.

Deployed-agent state: unchanged until reviewed integration and deployment.

Provider/canonical/physical evidence: no production request has yet been made;
no business outcome is claimed.

Remaining acceptance journey: reviewed PR and CI; wait for ROOTLINE's P0
serialized lane if occupied; integrate/deploy at exact head; invoke one
delivery-disabled genuine authenticated internal request; prove one useful
canonical result and zero replay duplication/effects; reconcile closeout.

Exact hold and unblock condition: none while source/review work remains.

Safe work exhausted before hold: not applicable.

Owner repetition requested: no.

Terminal/worktree closeout: active; preserve until operational proof and final
reconciliation.
