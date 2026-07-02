# Vault Readiness Scorecard

Status: owner review ready, 2026-07-02.

Purpose: give CHARLIE, Brain Guard, and Charl a clear view of how complete the Vault Brain is and what still blocks full trust.

## Current Estimate

Vault Brain readiness: `88-92%`

This means the Vault is now strong enough to guide CHARLIE CORE missions and has runtime retrieval, source-coverage checks, owner preference context, Brain Guard blocking, and best-effort normalized write-through. It still needs owner-reviewed gold standards and more real missions before it should be treated as fully bulletproof.

## Area Scores

| Area | Score | Notes |
| --- | ---: | --- |
| Governance | 94% | Brain Guard, update rules, source-of-truth rules, owner decisions, open questions, review gates, runtime blocking, and source-coverage checks exist. |
| Identity / hierarchy | 90% | Charl, CHARLIE, CHARLIE CORE, Oom Sakkie, organogram, and system hierarchy are separated. |
| Agent structure | 85% | Agent files and registry exist; runtime asset rule added; some future departments still not designed. |
| Business doctrine | 80% | Meat Sales, Amadeus Farm, BEACON, FRED/Transfers are structured; owner still needs to review details. |
| Workflows | 90% | CHARLIE, n8n, SAM Meat, Beacon, Herdmaster, release, send-back, migration workflows are documented; CHARLIE runner now loads ranked Vault context and records Brain Guard/source coverage results. |
| Data doctrine | 85% | Order, farm, Sheets legacy, Supabase, telemetry, Beacon, Vault data rules are much stronger. |
| Standards | 90% | Testing, deployment, evidence, security, customer response, UI standards now have enforceable rules. |
| Playbooks | 80% | Bugfix, live operations, data migration, agent build, income stream, feature, dashboard, marketing playbooks exist. |
| Source map / cleanup | 82% | Migration inventory, archive queue, cleanup status, active source map exist. Runtime retrieval now depends on the clean Vault structure. Physical cleanup remains cautious. |
| Examples / gold standards | 70% | Gold-standard files exist but need more real approved examples from future missions. |

## What Still Blocks 95-100%

- Owner review of the business docs, especially Meat Sales and Amadeus Private Transfers.
- Final decisions in `OPEN_QUESTIONS.md`.
- More real mission examples converted into gold-standard packets.
- Compression of large operation evidence logs into durable lessons.
- External source review and cleanup.
- Owner-reviewed gold standard mission packets across dashboard, bugfix, income stream, agent build, n8n, and business-plan mission types.
- Richer semantic contradiction detection between artifacts and cited Vault docs.
- More production proof that normalized Vault write-through succeeds for every expected table.

## Current CHARLIE CORE Use Recommendation

CHARLIE CORE can now be used for controlled serious missions if:

- the mission identifies environment and shared departments;
- Brain Guard checks relevant Vault files before review-ready;
- tests and evidence are required;
- owner review remains mandatory before release, public posting, customer sends, payments, reservations, migrations, or lifecycle changes.

It is not yet safe to let CHARLIE CORE self-approve or run broad money/customer/public actions without owner review.
