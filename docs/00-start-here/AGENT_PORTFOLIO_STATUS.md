# Amadeus Agent Portfolio Status

Evidence cut: **2026-07-25 21:10 UTC**

Repository revision:
[`fa9f64c`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/fa9f64cf6b1ac9a8a021a5bb0c625907410a5a09).

Current recorded Render deployment:
`dep-d9ii5mok1i2s73b7dnug`, live at the same revision.

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
| **CHARLIE / CORE** | Governed owner mission system. Doctrine: [`CHARLIE_CORE.md`](../09-vault-brain/01-identity/CHARLIE_CORE.md) and [`CHARLIE_MISSION_WORKFLOW.md`](../09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md). | `modules/charlie/*`, runner, supervisor, watchdog, mission store and execution bridge. | Yes / Yes / Yes / Yes / Partial / No. Durable final-artifact ingestion and invalid-artifact rejection-loop corrections are merged/deployed; mission outcomes remain evidence-specific. | Phase B adaptive orchestration is built locally only, has no PR, and is not deployed or operational. Its active claim includes CORE implementation/tests and the implementation source map. Old protected-pause PRs #453-#455 remain failed/conflicting candidates; #445 remains stale and unwired. | Source-map edits are actively owned by CORE and excluded from this reconciliation. Evidence date: 2026-07-25. |
| **CORE stage agents** | Idea Expander, Source Mapper, Product/Technical Architect, Risk, Council, Planner, Architect, Builder, Tester, QA, reviewers and Publisher are governed mission stages, not independent product capability. Registry: [`AGENT_REGISTRY.md`](../09-vault-brain/02-agents/AGENT_REGISTRY.md). | CORE workflow and artifact contracts under `modules/charlie/*`. | B/M/D follow CORE infrastructure; C/O/A are mission-specific, never inherited globally. | The active nested recovery exhausted its bounded correction budget at Tester. Artifact presence or a stage pass cannot authorize merge, migration or deployment. | Registry is current at role level. Mission evidence must supply exact candidate/test/revision bindings. |
| **Oom Sakkie** | Owner/farm-team read-only coordinator: [`OOM_SAKKIE.md`](../09-vault-brain/02-agents/farm/OOM_SAKKIE.md). | `modules/oom_sakkie/*`, owner routes/UI, Telegram and specialist runtime components. | Yes / Yes / Yes / Partial / Partial / No. Read-only coordinator surfaces are proven; broad specialist and write authority are not. | Cannot inherit customer-send, finance, farm-write or hardware authority. Telegram callback ownership remains split between backend SAM and legacy n8n GateKeeper handling. | Authority map covers Oom Sakkie indirectly. A dedicated operational source-map section is missing. Evidence date: 2026-07-25. |
| **SAM General** | General conversation governs until specialist graduation: [`SAM_GENERAL_CONVERSATION.md`](../09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md). | SAM router/context, `sales_transaction_routes.py`, specialist runtimes and shared delivery truth. | Yes / Yes / Yes / Partial / Partial / No. Owner-approved candidate-bound Send Reply is operationally approved after one real `provider_delivered` proof; broad AUTO_GENERAL remains disabled. | Delivery truth is operational only for the proved Send Reply path. Existing accepted-unverified messages remain unreconciled. Unknown intent alone does not authorize owner interruption or specialist tools. | General-conversation and shared-delivery source-map domains are current. Evidence date: 2026-07-25. |
| **SAM Livestock** | Supervised live-pig specialist: [`SAM_LIVE_STOCK_SALES_WORKFLOW.md`](../09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md). | SAM Livestock runtime/launch control, evaluation, sales routes and Herdmaster availability readers. | Yes / Yes / Yes / Partial / Partial / No. Exact matching and owner-approved Send Reply are operational; customer autoreply and protected actions remain disabled. | PR [#484](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/484) merged/deployed bounded HUMAN reassessment and an evidence-only response-class evaluator. Neither the deferred HUMAN backlog presenter nor an authority controller exists; inert canaries were not invoked. Tested exact requirements had no affirmatively eligible animals, not proven zero stock. | Source map remains current; merged evaluation code does not enable autonomous graduation. Evidence date: 2026-07-25. |
| **SAM Meat** | Owner-reviewed meat conversation and production path: [`SAM_MEAT_SALES_WORKFLOW.md`](../09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md). | SAM Meat runtime/readiness/control, bounded snapshot/deadline readers, meat production, fulfilment and owner UI. | Yes / Yes / Yes / Partial / Partial / No. Deadline and query-bounded snapshot work is merged/deployed; a real Meat customer-delivery canary is still absent. | Conversation `1978` remains NO-GO after timeout and wrong-lane Livestock invocation. PR [#485](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/485) is the current clean candidate for evidence-before-dispatch and a disabled timing probe; it is not merged truth. | Source map is current for merged implementation. Evidence date: 2026-07-25. |
| **Butcher / meat pipeline** | Advisory carcass, cut, yield and fulfilment evidence: [`BUTCHER.md`](../09-vault-brain/02-agents/sales/BUTCHER.md). | `modules/sales/meat_*`, `butcher_truth_board.py` and document services. | Yes / Yes / Yes / Partial / Partial / No. Read-only/pilot evidence exists; no autonomous slaughter, reservation or fulfilment authority. | Missing or stale price, capacity, slaughter or production evidence fails closed. No separate current candidate or active claim. | Covered under SAM Meat rather than a dedicated source-map section. Evidence date: 2026-07-25. |
| **Herdmaster** | Read-only herd intelligence and exact eligibility: [`HERDMASTER.md`](../09-vault-brain/02-agents/farm/HERDMASTER.md). | Pig-weight/readiness services, canonical readers, exact eligibility and Daily Brief service. | Yes / Yes / Yes / Partial / Partial / No. Exact matching is operational. The Daily Brief library is deployed/tested but has no caller or owner route, so it is not operational. | Observation/management-intent candidates overlap. PR [#466](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/466) is the newest open candidate. The protected migration remains unapplied. No active Herdmaster claim. | Purpose/eligibility source map is current; Data Model candidates are not current truth. Evidence date: 2026-07-25. |
| **Beacon** | Controlled marketing/media department: [`BEACON.md`](../09-vault-brain/02-agents/marketing/BEACON.md). | `modules/beacon/*`, `modules/sales/beacon_*`, Story Desk and owner APIs. | Yes / Yes / Yes / Partial / Partial / No. Story Desk, bounded read-only Meta preview and owner review surfaces are operational; publication is not. | Post 1 remains unpublished without exact owner approval and a confirmed Meta post identity. The exact-post/weekly packet approval UI is active local work, not merged truth. Binary upload remains live-unproven; Meta import remains zero verified imported rows. | Beacon source map remains implementation-current; active Beacon files are excluded. Evidence date: 2026-07-25. |
| **ROOTLINE** | Eventual water, irrigation, weather, power and infrastructure operator: [`ROOTLINE_CONTROL_ARCHITECTURE.md`](../09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md). | Daily Brief composer/owner route, telemetry readers and inactive legacy n8n/IFTTT controller. | Yes / Yes / Yes / Partial / Yes for Level 1 owner route / No. | Level 1 Daily Brief remains operational. Phase B command-ledger and hardware-inventory work is plan/documentation only. Telemetry is partial; forecast stale; tank/pump/borehole unavailable; all-zero power suspicious/unverified; no zone received `proceed`. Hardware control, IFTTT execution and autonomous irrigation are not operational. | Architecture and source map are current after PR #465; Phase B documentation does not grant hardware authority. Evidence date: 2026-07-25. |
| **Production Observer** | Read-only production/deployment evidence observer; it reports exact revisions and bounded checks without mutating runtime. | Procedures, deployment records and lane evidence; no independently callable agent is evidenced. | Procedure / N/A / N/A / N/A / Partial / No. | Coverage is incomplete where exact Render revisions, provider outcomes or live route proofs were not captured. An observer report cannot promote a merge, HTTP acceptance or documentation state into operational capability. | No dedicated canonical agent registry or implementation-source domain. Evidence date: 2026-07-25. |
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

## Amadeus StoryWorks

Evidence refreshed: **2026-07-25 21:10 UTC**

Authoritative integration:
[`750ec260`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/750ec260d8fed1dda0e920987b42ad656e4d047f),
merged through [PR #475](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/475)
from reviewed head `2e8d8910998e3110a12c46ae55ce51420dbf3965`.
Later owner-review and pre-production documentation merged through PRs #479
and #483; neither establishes a completed video or operating media business.

**Identity and ownership:** Amadeus StoryWorks is a separate, evidence-led
YouTube media enterprise intended to become commercially self-sustaining,
cover its own production and operating costs, later contribute toward CHARLIE
operating costs and—only through explicit owner-governed financial
allocation—help fund other Amadeus ventures. Its first validation property is
**The Chronicle Vault**, currently validating documentary/explainer content
about the systems, technologies and decisions that enabled societies to
function.

STORYWORKS is not BEACON, Amadeus Farm social media, a farm media library,
livestock marketing, customer support, a farm-operations agent, or presently
integrated into live CHARLIE/CORE. BEACON continues to own Amadeus Farm
marketing and distribution. STORYWORKS is an independent owned-media business
validation programme.

| Current STORYWORKS state | Evidence-bound value |
| --- | --- |
| Research and business doctrine | Integrated under `planning/storyworks/**` |
| Petra private pilot package | Partially produced; owner-review and provisional pre-production decisions merged; no completed video |
| Final rights/fact/quality approval | No; verification-boundary corrections remain active planning work |
| YouTube channel / publication | Not created / not published; no exact platform identity |
| Platform performance / YPP eligibility | Unknown / Unknown |
| YPP/AdSense / monetisation | Not activated / No |
| Revenue finalised / cash received | No / exactly R0 |
| Distributable profit / transfer | No / No |
| CHARLIE integration / operational media business | No / No |
| Deployment | Unverified and unnecessary for the documentation/private-validation state |

The authoritative business ladder keeps researched, privately produced,
rights/fact/quality approved, owner-approved for publication, published with
exact platform identity, performance observed, YPP eligible, monetisation
active, platform revenue estimated, platform revenue finalised, cash
received, direct costs reconciled, operating reserve funded, distributable
profit owner-approved, and transfer reconciled as separate states. A later
state is never inferred from an earlier one.

CHARLIE may later govern topic pipeline, budgets, schedules, production
stages, evidence, reviews and business reporting, but that integration is not
built or authorised. Owner approval remains mandatory for account/channel
creation, publishing, contracts, licences, spending, monetisation, banking,
tax, allocation and transfer of funds.

Authoritative STORYWORKS routing:

- [`README.md`](../../planning/storyworks/README.md)
- [`STATUS.md`](../../planning/storyworks/STATUS.md)
- [`STORYWORKS_BUSINESS_CHARTER.md`](../../planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md)
- [`BUSINESS_STATE_LADDER.md`](../../planning/storyworks/BUSINESS_STATE_LADDER.md)
- [`PHASE_0_EXECUTIVE_DECISION_PACK.md`](../../planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md)
- [`PHASE_0_VALIDATION_PLAN.md`](../../planning/storyworks/PHASE_0_VALIDATION_PLAN.md)
- [`UNIT_ECONOMICS.md`](../../planning/storyworks/UNIT_ECONOMICS.md)
- [`PRODUCTION_PLAYBOOK.md`](../../planning/storyworks/PRODUCTION_PLAYBOOK.md)
- [`CHRONICLE_VAULT_CHANNEL_BIBLE.md`](../../planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md)

Detailed doctrine changes occur under `planning/storyworks/**` first.
Portfolio documentation changes only when identity, ownership boundary, phase,
or material business state changes. This pointer must not become a second
charter, economics model, production playbook, or state ladder. Missing
current evidence remains `Unknown`.

## Current Fault And Candidate Register

- **SAM delivery truth:** owner-approved Send Reply has one controlled real
  provider-delivered proof. Broad AUTO_GENERAL remains disabled and historical
  accepted-unverified messages remain unreconciled.
- **SAM HUMAN/graduation:** PR #484 is merged/deployed. Its evaluator is
  evidence-only; backlog presentation and authority control remain deferred.
- **SAM Meat:** conversation `1978` remains stopped and unresolved.
- **SAM Meat snapshot/delivery:** bounded deadlines and query snapshot are
  merged/deployed. PR #485 is clean but unmerged; no real Meat delivery canary
  has passed.
- **Beacon Post 1:** owner-review workflow is operational, but no confirmed
  Meta post ID exists; the post is unpublished. Exact packet approval UI is
  active local work, not merged capability.
- **Beacon transport/import:** binary upload remains live-unproven. Meta import
  still has zero verified imported rows after `execute_append_failed`.
- **Herdmaster:** exact matching is operational. The Daily Brief is a deployed
  library without a caller. PR #466 and older overlapping Data Model/migration
  candidates are unmerged; the protected migration is unapplied.
- **ROOTLINE:** Level 1 owner route is operational. Valve control, IFTTT
  activation and autonomous irrigation are not.
- **CORE:** Phase B adaptive orchestration is a local-only candidate with no
  PR. PR-ready lifecycle evidence and old overlapping candidates are not
  product truth.

## Open Pull Request Register

This dated triage is not merge authority. Textual mergeability does not
override current-main, CI, migration, claim or operational-evidence gates.

| Classification | Open PRs at this evidence cut | Current meaning |
| --- | --- | --- |
| **Current and actionable** | [#485](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/485), [#477](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/477) | #485 is clean SAM Meat candidate work; #477 is this documentation-only reconciliation. |
| **Blocked** | [#466](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/466) | Textually clean, but blocked on owner lineage selection, protected-migration authority and duplicate reconciliation. |
| **Stale** | [#445](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/445), [#413](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/413), [#383](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/383), [#361](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/361), [#306](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/306), [#278](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/278), [#234](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/234), [#188](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/188), [#130](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/130), [#118](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/118) | May be textually clean, but scope and evidence predate substantial main changes. Refresh or close; historical CI is insufficient. |
| **Superseded or duplicate** | [#447](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/447), [#439](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/439), [#422](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/422), [#393](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/393), [#382](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/382), [#381](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/381), [#140](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/140), [#139](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/139), [#132](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/132), [#129](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/129), [#121](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/121), [#120](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/120), [#119](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/119), [#117](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/117), [#114](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/114), [#82](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/82) | Duplicate Herdmaster data/capture/stock/allocation, purpose-review or CORE UI lineages. Retain unique evidence, then close/supersede. |
| **Unsafe to merge as-is** | #455, #454, #453, #434, #384, #368, #363, #344, #315, #307, #276, #271, #262, #244, #240, #227, #223, #218, #217, #197, #195, #189, #186, #160, #141, #137, #135, #134, #125, #124, #115, #96, #94, #92, #83 | Conflicting, dirty, non-main-based or failing governed CI. None is safe to integrate as-is. |

## Active Claim Ownership At This Cut

- CORE Phase B owns its adaptive implementation/tests, CORE runner guide and
  implementation source map.
- Beacon owns its exact weekly owner-decision route, service, Story Desk,
  migration design and focused tests.
- StoryWorks owns only named `planning/storyworks/**` verification files.
- This document candidate:
  this file and `docs/00-start-here/README.md`.
- SAM Meat PR #485 and ROOTLINE inventory claims are released.

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
