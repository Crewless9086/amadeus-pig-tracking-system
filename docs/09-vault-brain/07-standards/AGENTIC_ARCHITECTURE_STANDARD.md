# Agentic Architecture Standard

Status: owner-approved and mandatory.

## Purpose

Amadeus builds operational agents, not a growing collection of question-specific chatbot handlers. CHARLIE is Charl's private executive. Domain agents own business semantics, read authoritative raw data, reason within their domain, return structured evidence, and use governed execution rails. CORE builds and repairs software; it is not the business reasoning layer.

## Mandatory Architecture

```text
Charl -> CHARLIE -> shared agent runtime -> domain agent -> canonical data
                 -> evidence assessment -> follow-up/reconciliation -> executive synthesis
                 -> governed action rail when authority permits
```

CHARLIE owns outcome understanding, delegation, cross-domain reconciliation, executive synthesis, commitments, and escalation. CHARLIE must not absorb every domain calculation.

Domain agents own their semantics. Herdmaster owns herd inventory, lifecycle, locations, litters, breeding, growth, health and welfare. SAM owns sales conversations and commercial preparation. Beacon owns marketing. Oom Sakkie coordinates farm operations. ANALYST observes and validates improvement. CORE implements bounded software missions.

## Anti-Drift Rule

Before adding a new CHARLIE intent, route or tool for an owner question, the builder and Brain Guard must ask:

1. Which domain agent owns this outcome?
2. Can the shared agent request/evidence contract express it?
3. Is canonical data already available to that agent?
4. Is the proposed code deterministic safety, calculation or verification, or is it conversational/domain reasoning that belongs to an agent?

A question-specific CHARLIE handler is prohibited when a domain agent can own the capability. New deterministic code remains appropriate for authoritative calculations, validation, permissions, idempotency, audit and execution safety.

## Shared Agent Contract

Requests contain goal, question, capability, subject, known context, read/prepare authority and freshness requirement. Results contain a direct answer, facts, metrics, breakdowns, anomalies, inferences, recommendations, unresolved questions, source provenance, freshness, confidence and explicit authority.

An answer is insufficient when it lacks a direct answer, provenance, freshness or calibrated confidence. The runtime performs one bounded evidence repair pass before CHARLIE reports a gap. A model may synthesize evidence but may not invent facts, grant authority or approve its own work.

## Full Access Meaning

Full access means CHARLIE can discover and delegate reads across every approved business domain. It does not mean unrestricted SQL or unrestricted writes. Reads use canonical services and provenance. Writes use existing audited domain rails and owner/delegation policy. Red-zone actions remain owner-gated.

## Completion Evidence

Agent readiness is measured through real delegated runs, clean evidence rate, owner corrections, escaped defects, latency and source coverage. A workforce label or unit test alone does not prove an agent operational. Production evidence grows capability trust but never silently expands authority.

## Two-Brain Boundary

Doctrine Vault stores stable identity, authority, ownership, business rules and source-of-truth contracts. Evidence Memory stores runs, corrections, outcomes, failures, latency and proposal validation. Evidence may recommend a Doctrine change but cannot apply or promote one without a bounded CORE mission, deterministic proof and the required owner gate.

## CORE Mission Gate

Every new CORE mission must freeze an `Agentic Architecture Packet` before Builder. The packet identifies the owning, coordinating and supporting agents and separates agent reasoning from deterministic code and governed actions. Every stage must preserve the packet; Brain Guard blocks a missing/stale packet or explicit non-compliance.

## Shared Bus

Agent-to-agent requests use the same governed runtime as CHARLIE delegation. Direct specialist access is permitted for bounded questions. Department commanders remain responsible for broad multi-discipline outcomes. The bus carries evidence and authority; it never grants authority.
