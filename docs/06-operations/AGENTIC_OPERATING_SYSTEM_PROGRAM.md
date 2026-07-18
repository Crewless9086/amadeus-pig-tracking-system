# Amadeus Agentic Operating System Program

Status: owner-approved architecture and active implementation baseline.

## Target

Amadeus is an agent-led operating system. CHARLIE is Charl's private executive. Oom Sakkie commands farm operations. Department leaders own their business semantics. CORE builds and repairs capabilities but may not replace operational agents with question-specific code. ANALYST measures whether changes improve real outcomes.

## Organisational Graph

```text
Charl
  -> CHARLIE (private executive and cross-business coordinator)
       -> Oom Sakkie (farm command)
            -> Herdmaster (animals, breeding, growth, welfare)
            -> Quartermaster (feed, supplies, stock)
            -> Rootline (weather, crops, irrigation)
            -> Gatekeeper (farm safety and authority)
       -> SAM (sales conversations and commercial preparation)
            -> Herdmaster (livestock truth)
            -> Butcher (meat truth)
            -> Ledger (price, cost and payment evidence)
            -> FRED (future transport truth)
       -> Beacon (marketing)
       -> CORE (software delivery)
            -> ANALYST (observation, proposals and validation)
```

CHARLIE may delegate directly to any specialist for a bounded precise question. Oom Sakkie remains responsible for multi-discipline farm coordination and farm-manager interaction. SAM remains responsible for customer communication while consulting domain specialists.

## Four-Layer Classification

Every capability must be classified before build:

1. Domain reasoning belongs to the owning operational agent.
2. Deterministic calculation belongs to tested canonical services.
3. Governed action belongs to audited execution rails.
4. Cross-domain coordination belongs to CHARLIE or the relevant department commander.

Code is required for canonical reads, calculations, validation, permissions, audit, idempotency and safe execution. It must not become a hidden substitute for agent reasoning.

## Two Brains

### Doctrine Vault

Stable identity, authority, business rules, agent ownership, source-of-truth definitions and architecture standards. Evidence cannot silently rewrite Doctrine.

### Evidence Memory

Agent runs, source evidence, owner corrections, test outcomes, escaped defects, latency, false escalations and proposal validation. Evidence may propose doctrine or implementation changes through CORE; it cannot promote itself.

## Shared Agent Bus

All operational agents use the shared request/evidence contract. Requests identify goal, question, capability, subject, context, authority and freshness. Evidence returns a direct answer, facts, metrics, anomalies, provenance, freshness, confidence, recommendations, unresolved questions and explicit authority.

The bus performs bounded delegation, evidence sufficiency assessment, one repair pass, telemetry and capability trust recording. It does not grant write authority.

## CORE Enforcement

Every mission freezes an Agentic Architecture Packet before Builder. The packet records business outcome, owning/coordinating/supporting agents, canonical sources, deterministic code roles, agent reasoning roles, prohibited designs, evidence contract, authority and learning signals.

Every CORE stage receives this packet. Builder and reviewers must return an architecture compliance verdict. Brain Guard blocks missing/stale packets and any reported non-compliance. Adjacent discoveries become linked missions rather than leaf branches inside the current scope.

The five mandatory mission questions are:

1. Which operational agent becomes more capable?
2. What canonical evidence does that agent use?
3. What reasoning belongs to the agent?
4. What deterministic code is genuinely required?
5. How is generalisation beyond the original example proven?

## ANALYST Loop

ANALYST watches mission evidence for question-specific handlers, business reasoning in routes/UI/regex, agent bypass, shadow truth and repeated owner corrections. Proposals require recurrence evidence, an expected measurable improvement and post-deployment validation. Unproven proposals do not increase trust.

## Operational Rollout

- Herdmaster Operational V1: active read-only reference agent.
- Oom Sakkie Operational V1: active read-only farm coordinator over shared-agent evidence.
- Ledger Operational V1: active read-only price-evidence validator.
- SAM livestock: production availability is delegated to Herdmaster; deterministic price calculation is checked by Ledger; customer sends, reservations and commitments remain gated.
- Next migrations: Quartermaster/Rootline farm evidence, Butcher, SAM Meat, Beacon and FRED.

## Success Measures

- fewer question-specific branches;
- increasing adjacent-question pass rate;
- clean evidence rate above 95%;
- owner correction and false escalation rates falling over time;
- cross-agent reuse increasing;
- zero unauthorized actions;
- deterministic required tests passing;
- every architecture proposal measured after deployment.
