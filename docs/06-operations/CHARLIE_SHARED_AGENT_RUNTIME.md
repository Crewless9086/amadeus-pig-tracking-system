# CHARLIE Shared Agent Runtime

## Operating Model

CHARLIE is Charl's private executive and the only layer expected to combine evidence across departments. Domain agents interpret their own business truth. The shared runtime supplies registration, bounded delegation, evidence sufficiency checks, one repair pass, telemetry and an explicit authority envelope.

The operational path is:

```text
Charl -> CHARLIE intent and outcome plan -> domain agent delegation
      -> canonical domain services -> structured evidence
      -> evidence sufficiency check -> CHARLIE executive synthesis
      -> governed action rail only when separately authorized
```

## Herdmaster Operational V1

Herdmaster is the first reference agent. It reads the canonical pig master view and, when required, pen, litter and reservation evidence. Its V1 capabilities are herd inventory, herd overview, pen occupancy, weight attention, breeding inventory, litter attention and individual pig profile.

Herdmaster does not write lifecycle, movement, weight, health, purpose, breeding or reservation state. Pre-wean piglets remain litter-managed and are not falsely flagged because an individual tag or weight has not yet been assigned.

## Evidence Contract

Every successful operational result must include a direct answer, provenance, freshness and calibrated confidence. It may also include facts, metrics, breakdowns, anomalies, inferences, recommendations and unresolved questions. Missing evidence triggers one bounded repair attempt; the runtime then reports the gap honestly.

Agent confidence flows into CHARLIE's response packet. A successful tool call alone is not treated as 100% evidence confidence.

## Performance

Inventory questions use one canonical pig-master snapshot and a 30-second in-process cache. The cache reduces repeated executive questions without changing the authoritative source or persisting stale business state.

## Extension Rule

New business questions must be added to the owning domain agent through this request/evidence contract. Do not add a question-specific CHARLIE handler when a domain agent can own the outcome. Deterministic code remains appropriate for authoritative calculations, validation, permissions, idempotency, audit and safe execution.

## Acceptance Gate

An agent capability is operational only when deterministic tests pass and a real delegated run proves source access, evidence quality, executive synthesis, latency and telemetry. Authority does not expand automatically from readiness evidence.
