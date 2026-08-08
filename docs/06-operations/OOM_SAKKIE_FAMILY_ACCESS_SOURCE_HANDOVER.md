# Oom Sakkie Family Access And Afrikaans — Source Handover

Date: 2026-08-08  
Stage: Source-ready; not integrated, deployed, configured, or operationally proven  
Production owner during preparation: ROOTLINE

## Current truth

The branch was reconciled again after ROOTLINE advanced: production deployment `dep-d9rp1mrncjis739d3bh0` and `origin/main` were both verified at `1e89cbb43c6a47f5d158044b208efbcc7e92633c`. The current Telegram allow-list and all reviewed operational documentation identify exactly one authorized human Telegram identity: Charl, provider user/private-chat ID `5721652188`. Mum and Dad are **not** configured or authorized. Display names and language provide no identity authority.

The 5 August mortality-intelligence handover is completed historical evidence and was not resumed, polled, or used to manufacture a proof.

## Prepared contract

`modules/oom_sakkie/family_access.py` defines the closed roles and permission checks:

- `owner`: Charl; existing protected authority remains unchanged.
- `trusted_family_reporter`: may submit attributable observations and answer an active question owned by that same Telegram identity, only when those permissions were explicitly granted.
- `read_only_family_member`: may receive only explicitly listed summary domains.
- `unknown_sender`: receives no private context and gains no mutation or confirmation authority.

Every non-owner binding requires an exact Telegram user/private-chat identity, `family_key` (`mum` or `dad`), role, separate permission list, summary-domain list, authorization identity and time, and `authorized_by_user_id=5721652188`. Invalid, incomplete, non-owner-authorized, group-chat, or cross-family bindings fail closed. The contract preserves reporter user ID, provider message ID, provider timestamp, authorization identity, and a deterministic binding digest. It grants zero send, dispatch, farm-write, customer, publication, or hardware authority.

The existing semantic prompt now explicitly handles English, Afrikaans and mixed language while being forbidden to infer identity or permission. The public gateway policy reports only contract availability and the owner-only boundary; it exposes no family keys, identities, binding counts, or permission inventory. Owner authority is issued only when the resolved role is Owner. A configured family identity currently fails closed as `telegram_family_lifecycle_not_enabled` until the typed lifecycle integration below is reviewed; it can never fall through into owner handlers. No Mum/Dad binding has been added.

## Later onboarding (protected owner change)

1. Charl supplies or confirms Mum's or Dad's exact Telegram numeric user ID through the governed owner-permission lifecycle. A display name, forwarded message, phone contact, or language is insufficient.
2. Show Charl one preview containing that one identity, `mum` or `dad`, the selected role, individual reporting permissions, individual readable summary domains, effective time, and revocation path.
3. Require Charl's exact confirmation. Persist an immutable authorization event and configure the matching record in `OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON`; add the same exact identity to the gateway allow-list through normal reviewed configuration.
4. Run identity-bound preflight. Send no private summary during identity testing. Prove an unknown identity, cross-family reply, protected confirmation, and replay all fail closed.
5. Only then enable the existing gateway/lifecycle consumption path in a serialized production window. Do not create another bot, router, queue, or direct specialist Telegram path.
6. Revocation is another Charl-only protected change and must remove access without erasing historical reporter attribution.

Example records are intentionally omitted because Mum and Dad have not been identified or authorized. Configuration must never guess their IDs.

## Shared integration handover

No active specialist file was changed. Before family access becomes operational, the existing Oom Sakkie gateway/lifecycle integration must:

1. Resolve `FamilyPrincipal` immediately after bearer authentication and Telegram payload parsing, before loading any private context.
2. Keep `GatewayOwnerAuthority` issuance Owner-only.
3. Permit a Trusted Family Reporter only through typed observation/follow-up adapters after `authorize_family_message`; bind lifecycle context to that reporter identity. Never pass reporter input to owner confirmation handlers.
4. Permit a Read-only Family Member only through the explicitly scoped summary composer. Apply the existing maximum-three-priorities/one-question presentation rule.
5. Return a privacy-safe denial for Unknown Sender without revealing configured identities, cases, animals, or domains.
6. Store the attribution block alongside specialist evidence and consume the prepared deterministic replay identity exactly once. The identity binds user, chat, provider message/time, content hash, capability, and authorization binding.

Required integration tests: gateway ordering; owner regression; Mum/Dad independent configuration; Afrikaans and mixed-language semantic journeys; later contextual reply; unknown sender; cross-family context; protected confirmation; replay; privacy-safe denial; zero farm/customer/hardware writes.

## Acceptance evidence

Focused tests prove Charl-only default, independently scoped Mum/Dad bindings, language-neutral authorization (the same English/Afrikaans/mixed text receives the same identity policy), principal-to-current-message binding, duplicate/malformed binding rejection, context-owner isolation, exact attribution, unknown-sender privacy, owner-only protected actions, read-only domain scoping, deterministic replay identity construction, and the three-action/one-question result bound. Existing semantic-front-door regressions cover Afrikaans classification and short contextual domain replies; durable replay consumption and an end-to-end family semantic/context journey remain part of the shared integration and later production proof rather than being claimed here.

No Telegram call, runtime acquisition, merge, deployment, farm/customer/hardware write, or ROOTLINE/HERDMASTER change was performed.

## Later production proof

After Control Tower assigns a production window and Charl authorizes one real family identity:

1. Deploy an exact reviewed merge and verify exact lineage.
2. Submit one natural Afrikaans observation from that exact authorized identity.
3. Verify one provider-confirmed acknowledgement, exact attribution/timestamp/provenance, correct specialist routing, and no protected action or farm write.
4. Submit one short contextual reply (for example, `Hy eet nog nie`) and prove it advances only that identity's active question.
5. Replay both provider updates and prove zero duplicate messages, questions, lifecycle rows, packets, or writes.
6. Attempt the same data access and a protected confirmation from an unknown/differently scoped identity; verify privacy-safe denial and zero disclosure/mutation.

Expected measurable family outcome: after separate authorization, each enabled family member can report one farm observation naturally in Afrikaans and receive one relevant response without Charl relaying it, while 100% of protected confirmations remain Charl-only.
