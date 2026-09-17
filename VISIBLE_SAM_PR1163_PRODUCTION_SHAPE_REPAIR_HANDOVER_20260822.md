# CONTROL TOWER FEEDBACK HANDOVER — SAM PR #1163 production-shape repair

```json
{
  "contract_version": "core_mission_outcome_handover_v1",
  "handover_id": "SAM-PR1163-PRODUCTION-SHAPE-REPAIR-20260822",
  "mission_id": "existing SAM five-customer livestock recovery mission",
  "terminal_disposition": "source_repaired_tests_passed_awaiting_different_agent_review",
  "requested_lifecycle": "REVIEW_HOLD",
  "technical_milestones": ["production_shape_repaired", "tests_passed", "pr_updated"],
  "owner_outcome": "NONE"
}
```

## Exact scope and state

- Existing PR: `#1163`, branch `fix/sam-five-customer-recovery-20260822`.
- Rejected head repaired: `87a53a2aeb05eaef14e42af74d80186a20fa0d5c`.
- Authoritative base: `origin/main=d149e8009c164de95dce16db42d340bf5dead05c`.
- Implementation commit: `309fd8e7c0a09c43450e0fabbf0898e539777a08`.
- Worktree: `C:/tmp/sam-five-customer-recovery-20260822`.
- Merge, deployment, customer/provider send, production mutation and authority enablement: not performed.
- Business result: `NO BUSINESS OUTCOME`; this remains source evidence only.

## Independent-review defect reproduced

The rejected evaluator required invented referral fields (`attribution_identity`,
`target_page_id`, and `publication_time`) before accepting a successful canonical
binding. The production Chatwoot Meta referral parser exposes only the standard
referral fields, including `source_id`. A production-shaped referral therefore
returned `absent / attribution_identity_absent` despite an exact canonical
resolution.

## Repair

- `content_attributes.referral.source_id` is now the only BEACON post lookup
  candidate. Top-level provider/message `source_id` and invented post fields are
  not accepted as publication identity.
- `binding_resolution.binding` is the sole source of campaign identity, page,
  publication time, canonical text, SAM boundary, packet identity and binding
  identity. The compatibility `expected_binding` argument cannot override it.
- Payload assertions for campaign, page, publication time, text or authority
  boundary are ignored.
- Provider inbound `created_at` is compared to the canonical publication time:
  it must not precede publication, be in the future, or exceed the governed
  30-day attribution window. Later re-evaluation does not make a historically
  valid inbound stale.
- Both protected-consumer and organic canonical binding shapes propagate through
  the real parser and front-door packet. `binding_source` is retained for audit.
- Missing, conflicting, invalid or stale canonical attribution clears only the
  campaign-derived context. Ordinary supported Facebook processing remains
  available through its independent provider identity and chronology rail.
- No new store, queue, scheduler, provider adapter or authority rail was added.

## Evidence

- Wider focused SAM/BEACON suite: `351 passed`, `150 subtests passed`, one
  existing ReportLab deprecation warning.
- Covered: Meta inbound, provider identity, customer front door, live-stock
  runtime, organic binding, protected publication worker and BEACON campaign.
- Brain Guard: `python scripts/audit_vault_alignment.py` passed with zero findings.
- Diff hygiene: `git diff --check` passed.
- Production/customer evidence: none; exact loaded revision and genuine Meta
  customer behavior remain Unknown until governed release and acceptance.

## Collision and dependency reconciliation

- PR `#1148` remains an obsolete duplicate and was not modified.
- The separately logged BEACON producer/consumer `provider_readback_confirmed`
  shape mismatch remains outside this PR. The repaired SAM path correctly refuses
  protected attribution when that canonical consumer proof is absent while
  preserving ordinary Facebook processing.
- Automatic customer sending remains OFF and unchanged.

## Acceptance still required

1. Different-agent exact-head independent review and exact-head CI.
2. Serialized Control Tower merge/deploy decision.
3. Exact loaded revision proof.
4. Genuine customer-created Meta referral with canonical readback.
5. Provider-delivered supported response and automatic follow-up.
6. Five genuine customer outcomes and a later terminal-independent cycle.

## Closeout

- Owner action: none.
- Lifecycle: `REVIEW_HOLD`.
- Control Tower classification: continue the existing SAM mission; do not create
  or reprioritize a new mission.
- Next safe action: different-agent independent review of the exact final PR head.
- Expected future business result: SAM retains trustworthy canonical campaign
  context for supported Facebook livestock enquiries while ordinary enquiries
  remain usable when attribution cannot be proven.

Decision: YES — send the exact final PR head to independent review.

Why: the production-shape blocker is repaired without trusting inbound payload
authority and without coupling ordinary Facebook processing to attribution.

Send this exact prompt to SAM LIVESTOCK INDEPENDENT REVIEW TERMINAL: Review PR
#1163 at the exact final head reported by Control Tower. In a fresh isolated
worktree, prove a standard Chatwoot Meta referral using only referral source_id
can acquire campaign/page/publication/text/boundary context solely from one exact
canonical protected-consumer or organic binding. Challenge payload and caller
assertions, missing/conflicting bindings, invalid/prepublication/future/stale
inbound chronology, production handler/front-door propagation, and ordinary
Facebook preservation. Keep the separate BEACON readback-shape dependency out of
scope. Run exact-current focused and appropriate wider tests and return the full
Control Tower handover. Do not merge, deploy, send, mutate production or enable
automatic customer authority.

Expected business result: after later governed release and genuine acceptance,
SAM answers supported Facebook livestock enquiries with canonical context only
when proven and without disabling ordinary handling when attribution is absent.
