# Amadeus Agent Portfolio Status

Evidence cut: **2026-07-25 15:55 UTC**

Repository revision:
[`cf4cf60`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/cf4cf6047798dcd4d3653394f4b9a2a5e23fe1fd).

Current recorded Render deployment:
`dep-d9idl3bhl9gs7394im70`, live at the same revision.

This is a currency index, not a grant of authority. It reconciles permanent
doctrine, implementation ownership, merge/deployment evidence, operational
proof, open candidates, CORE state, and temporary lane ledgers. Missing
evidence remains `Unknown` or `Unavailable`.

## State Key

- **B / M / D**: built / merged / deployed.
- **C**: required configuration is evidenced.
- **O**: the stated bounded capability has operational proof.
- **A**: autonomous authority is enabled.
- `Partial` means only the limitation stated in that row is proven.

Code presence is not deployment. Merge is not deployment. Deployment is not
configuration or real-world proof. HTTP acceptance is not provider delivery,
physical actuation, water flow, payment, publication, or customer completion.

## Portfolio Matrix

| Agent or domain | Intended role and permanent doctrine | Implementation source | B / M / D / C / O / A | Safety, faults, candidates and claims | Source-map and evidence currency |
| --- | --- | --- | --- | --- | --- |
| **CHARLIE / CORE** | Governed owner mission system. Doctrine: [`CHARLIE_CORE.md`](../09-vault-brain/01-identity/CHARLIE_CORE.md) and [`CHARLIE_MISSION_WORKFLOW.md`](../09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md). | `modules/charlie/*`, runner, supervisor, watchdog, mission store and execution bridge. | Yes / Yes / Yes / Yes / Partial / No. Runtime promotion, restart and watchdog health are proven at [`8548d90`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/8548d9077cb0e264a31ab4b40e57c7b3ba71d595); protected-pause behavior was not naturally exercised in that proof. | Current nested recovery is `blocked` at Tester with no lease. Frontend and queue-filter missions are approved/internal-recovery-queued with no leases. Lifecycle mission is `pr_ready`. PRs [#453](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/453)-[#455](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/455) and [#445](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/445) remain unmerged. Active CORE claim owns four factory/test files, not docs in this status scope. | Source-map coverage is current for dashboard, memory, mission recall and authority. Previous operating-status CORE state is stale after restart and the newest blocked mission transition. Evidence date: 2026-07-25. |
| **CORE stage agents** | Idea Expander, Source Mapper, Product/Technical Architect, Risk, Council, Planner, Architect, Builder, Tester, QA, reviewers and Publisher are governed mission stages, not independent product capability. Registry: [`AGENT_REGISTRY.md`](../09-vault-brain/02-agents/AGENT_REGISTRY.md). | CORE workflow and artifact contracts under `modules/charlie/*`. | B/M/D follow CORE infrastructure; C/O/A are mission-specific, never inherited globally. | The active nested recovery exhausted its bounded correction budget at Tester. Artifact presence or a stage pass cannot authorize merge, migration or deployment. | Registry is current at role level. Mission evidence must supply exact candidate/test/revision bindings. |
| **Oom Sakkie** | Owner/farm-team read-only coordinator: [`OOM_SAKKIE.md`](../09-vault-brain/02-agents/farm/OOM_SAKKIE.md). | `modules/oom_sakkie/*`, owner routes/UI, Telegram and specialist runtime components. | Yes / Yes / Yes / Partial / Partial / No. Read-only coordinator surfaces are proven; broad specialist and write authority are not. | Cannot inherit customer-send, finance, farm-write or hardware authority. Telegram callback ownership remains split between backend SAM and legacy n8n GateKeeper handling. | Authority map covers Oom Sakkie indirectly. A dedicated operational source-map section is missing. Evidence date: 2026-07-25. |
| **SAM General** | General conversation governs until specialist graduation: [`SAM_GENERAL_CONVERSATION.md`](../09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md). | SAM router/context, `sales_transaction_routes.py`, specialist runtimes and shared delivery truth. | Yes / Yes / Yes / Partial / No / No. The bounded AUTO_GENERAL canary was configured, then disabled after its first delivery-truth failure. | Delivery-runtime correction PR [#469](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/469) is merged and deployed, but no real provider delivered/read canary or existing-message reconciliation exists. | General-conversation and shared-delivery source-map domains are current. Evidence date: 2026-07-25. |
| **SAM Livestock** | Supervised live-pig specialist: [`SAM_LIVE_STOCK_SALES_WORKFLOW.md`](../09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md). | SAM Livestock runtime/launch control, sales routes and Herdmaster availability readers. | Yes / Yes / Yes / Partial / Partial / No. Exact matching is operational; customer autoreply and protected actions remain disabled. | Tested exact requirements had no affirmatively eligible animals; this is not zero physical stock. HUMAN recovery remains operationally unproven. PR [#458](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/458) is open and card-only cleanup is not operational. Telegram ownership remains split. No active SAM claim. | Source map is current for Stage 4 and exact truth boundaries. Evidence date: 2026-07-25. |
| **SAM Meat** | Owner-reviewed meat conversation and production path: [`SAM_MEAT_SALES_WORKFLOW.md`](../09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md). | SAM Meat runtime/readiness/control, meat production, matching, fulfilment, reconciliation and owner UI. | Yes / Yes / Yes / Partial / Partial / No. Owner-review and fail-closed surfaces are proven; real conversation progression is not. | Conversation `1978` remains NO-GO after timeout and separate wrong-lane Livestock invocation. No reply or protected action occurred. No active SAM Meat file claim. | Source map is current for SAM Meat implementation; latest canary fault remains unresolved. Evidence date: 2026-07-25. |
| **Butcher / meat pipeline** | Advisory carcass, cut, yield and fulfilment evidence: [`BUTCHER.md`](../09-vault-brain/02-agents/sales/BUTCHER.md). | `modules/sales/meat_*`, `butcher_truth_board.py` and document services. | Yes / Yes / Yes / Partial / Partial / No. Read-only/pilot evidence exists; no autonomous slaughter, reservation or fulfilment authority. | Missing or stale price, capacity, slaughter or production evidence fails closed. No separate current candidate or active claim. | Covered under SAM Meat rather than a dedicated source-map section. Evidence date: 2026-07-25. |
| **Herdmaster** | Read-only herd intelligence and exact eligibility: [`HERDMASTER.md`](../09-vault-brain/02-agents/farm/HERDMASTER.md). | Pig-weight/readiness services, canonical readers, exact eligibility and Daily Brief service. | Yes / Yes / Yes / Partial / Partial / No. Exact matching is operational. The Daily Brief library is deployed/tested but has no caller or owner route, so it is not operational. | Observation/management-intent candidates overlap. PR [#466](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/466) is the newest open candidate. The protected migration remains unapplied. No active Herdmaster claim. | Purpose/eligibility source map is current; Data Model candidates are not current truth. Evidence date: 2026-07-25. |
| **Beacon** | Controlled marketing/media department: [`BEACON.md`](../09-vault-brain/02-agents/marketing/BEACON.md). | `modules/beacon/*`, `modules/sales/beacon_*`, Story Desk and owner APIs. | Yes / Yes / Yes / Partial / Partial / No. Story Desk and Post 1 owner-review are operational; publication and live transport are not. | PR [#468](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/468) is merged/deployed. Post 1 has no owner approval or confirmed Meta post ID and remains unpublished. Binary upload remains live-unproven. Meta evidence import has zero verified imported rows. No active Beacon claim. | Beacon source map is implementation-current but does not yet record Post 1 delivery status. Evidence date: 2026-07-25. |
| **ROOTLINE** | Eventual water, irrigation, weather, power and infrastructure operator: [`ROOTLINE_CONTROL_ARCHITECTURE.md`](../09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md). | Daily Brief composer/owner route, telemetry readers and inactive legacy n8n/IFTTT controller. | Yes / Yes / Yes / Partial / Yes for Level 1 owner route / No. | Telemetry is partial; forecast stale; tank/pump/borehole unavailable; all-zero power suspicious/unverified; no zone received `proceed`. Hardware control and autonomous irrigation are not operational. IFTTT is inactive and unauthorized. Active ROOTLINE claim owns only the new Phase B hardware-inventory document. | Architecture and source map are current after PR [#465](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/465). Evidence date: 2026-07-25. |
| **Quartermaster** | Feed, supplies, expenses, stock and purchasing planning: [`QUARTERMASTER.md`](../09-vault-brain/02-agents/farm/QUARTERMASTER.md). | No dedicated operational implementation evidenced. | No / No / No / No / No / No. | Expense/supply tables, approval flows and owner rules remain missing. No active claim or open current candidate. | Registry correctly says Planned. Dedicated source-map domain and permanent operational evidence are missing. |
| **Future Crop Specialist** | Supplies crop/water-demand intent to ROOTLINE but cannot command valves. Current authority appears only in ROOTLINE architecture. | No dedicated implementation evidenced. | No / No / No / No / No / No. | No canonical agent file, approved crop data model or current candidate. | Missing doctrine and source-map domain. Older Oom Sakkie roster wording that calls Rootline the crop specialist is stale against the current ROOTLINE architecture. |
| **Ledger / finance** | Read-only pipeline, price, margin and payment evidence: [`LEDGER.md`](../09-vault-brain/02-agents/sales/LEDGER.md). | Sales/order readers, controlled transaction services and Oom Sakkie ledger component. | Yes / Yes / Yes / Partial / Partial / No. Read-only price/business evidence is proven; broader finance authority is not. | Cannot create invoices, change prices, confirm payment or alter financial records without money-path gates. No active claim. | Covered indirectly by authority/orders maps; a dedicated finance source-map status is missing. Evidence date: 2026-07-25. |
| **Sentinel / security** | Owner-operated security and safety advisory component under the [`Agent Authority Matrix`](../09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md). | Oom Sakkie Sentinel single-shot runner/contract and review surfaces. | Yes / Yes / Yes / Partial / Partial / No. Component proof does not establish a standalone autonomous agent. | No permanent enablement, write authority or independent canonical agent registration. No active claim. | Registry correctly treats Sentinel as a runtime component; the older planning roster can be misread as a future standalone agent. |
| **Documents / quotes / invoices / attachments** | Governed generation and shared delivery truth: [`QUOTE_INVOICE_DESIGN.md`](../02-backend/QUOTE_INVOICE_DESIGN.md) and [`OUTBOUND_DELIVERY_TRUTH_STANDARD.md`](../09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md). | `modules/documents/*` and sales delivery integration. | Yes / Yes / Yes / Partial / Partial / No. Generation/acceptance paths exist; real provider delivered/read graduation is unproven. | Conversations `2013`, `2009`, `2008`, `2007`, `875`, `2005` and `2006` remain `accepted_unverified` absent newer provider evidence. No automatic retry or existing-message reconciliation occurred. | Shared delivery source map is current; a dedicated documents implementation domain is missing. Evidence date: 2026-07-25. |
| **Gatekeeper** | Approval/routing policy specialist: [`GATEKEEPER.md`](../09-vault-brain/02-agents/farm/GATEKEEPER.md). | Backend gates plus live legacy n8n workflow `2 - The GateKeeper`. | Partial / Partial / Partial / Partial / No as authoritative SAM lifecycle owner / No. | n8n remains integration glue, not backend truth. Telegram callback split-brain is unresolved. | Permanent docs do not yet reconcile exact live webhook ownership end to end. |
| **Beacon sub-agents** | Strategy, Creative, Media Librarian and Performance Analyst have dedicated future doctrine files under `02-agents/marketing/`. | Some functions exist inside Beacon modules, not as independently proven agents. | Partial components / Yes inside Beacon / Yes inside Beacon / Partial / No independent proof / No. | Must not infer independent agents from department code. | Registry correctly marks these as future modules. |
| **Forge / Prism / Atlas** | Planned advisory specialists in the Oom Sakkie roster; authority matrix treats Forge/Atlas as runtime components rather than canonical independent agents. | Some Forge and generic specialist components exist under `modules/oom_sakkie/`; no independent Prism implementation was evidenced. | Partial components / Partial / Partial / Unknown / No independent proof / No. | No independent canonical agent registration or autonomous enablement. | Missing dedicated canonical files; code presence must not be promoted to operational status. |
| **FRED and sales specialist agents** | FRED, Meat Sales, Live Pig Sales, Slaughter/Abattoir and Custom Cuts remain planned or advisory registry roles. | Some sales behavior is implemented under shared SAM/Meat services, not as independently proven agents. | Mixed shared components / Mixed / Mixed / Unknown / No independent proof / No. | Shared runtime evidence does not establish separate agent authority. | Registry and dedicated planning files remain the weaker current truth. |
| **Research Engine, Business Intelligence and Compliance Reviewer** | Named future registry roles. | No dedicated canonical implementation or agent document evidenced. | No / No / No / No / No / No. | No active claim or current candidate. | Explicit documentation gaps; status remains Not designed/Planned. |

## Current Fault And Candidate Register

- **SAM delivery truth:** doctrine and runtime correction are merged/deployed.
  Real provider delivered/read proof, broad AUTO_GENERAL graduation, and
  reconciliation of existing ambiguous messages remain incomplete.
- **SAM card cleanup:** PR #458 remains open. Card-only cleanup and Telegram
  lifecycle completion are not operational.
- **SAM Meat:** conversation `1978` remains stopped and unresolved.
- **Beacon Post 1:** owner-review workflow is operational, but no confirmed
  Meta post ID exists; the post is unpublished.
- **Beacon transport/import:** binary upload remains live-unproven. Meta import
  still has zero verified imported rows after `execute_append_failed`.
- **Herdmaster:** exact matching is operational. The Daily Brief is a deployed
  library without a caller. PR #466 and older overlapping Data Model/migration
  candidates are unmerged; the protected migration is unapplied.
- **ROOTLINE:** Level 1 owner route is operational. Valve control, IFTTT
  activation and autonomous irrigation are not.
- **CORE:** the newest nested recovery is blocked at Tester with no lease.
  Frontend and queue-filter recoveries are queued with no leases. PR-ready
  lifecycle evidence and old overlapping candidates are not product truth.

## Active Claim Ownership At This Cut

- ROOTLINE Phase B:
  `docs/06-operations/ROOTLINE_PHASE_B_HARDWARE_INVENTORY.md` only.
- CORE artifact ingestion:
  `modules/charlie/mission_store.py`,
  `modules/charlie/execution_bridge.py` and their two focused tests.
- This document candidate:
  this file and `docs/00-start-here/README.md`.
- Other lane ledgers record released claims at this evidence cut.

Temporary claims are evidence ledgers, not permanent authority. Before editing
any file named here, re-read every ledger under
`C:/tmp/amadeus-parallel-control/CLAIMS/`.

## Missing Permanent Evidence And Next Documentation Slices

1. Reconcile the old crop-specialist roster wording with the mature ROOTLINE
   architecture and create dedicated crop doctrine only after owner review.
2. Add dedicated documents and finance implementation source-map domains
   without changing runtime authority.
3. Add a dedicated Oom Sakkie operational source-map section.
4. Update the main operating-status evidence cut after the fast-moving CORE,
   SAM delivery, Beacon and Herdmaster candidates settle.
5. Keep overlapping Herdmaster Data Model/changelog/migration files out of
   documentation work until their owner selects one lineage.

## Evidence Sources

- [Current operating status](OPERATING_STATUS.md)
- [Implementation source map](../09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md)
- [Agent registry](../09-vault-brain/02-agents/AGENT_REGISTRY.md)
- [Agent authority matrix](../09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md)
- [ROOTLINE control architecture](../09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md)
- [Outbound delivery truth standard](../09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md)
- [PR #465](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/465)
- [PR #468](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/468)
- [PR #469](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/469)
