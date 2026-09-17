# Parings- en Werpsel Lifecycle Redesign Plan

Status: Owner-approved successor mission  
Owner approval: Charl approved this redesign on 2026-08-10 and authorized implementation without another plan-approval round.  
Execution owner: Codex/Cursor terminal in a clean successor worktree.  
Production authority: Not granted by this plan; Charl must visually review the completed interface before deployment.

## Owner-visible outcome

Replace the complicated litter operating surface with one simple Afrikaans lifecycle page that follows the printed **Parings- en Werpselrekord** from mating through weaning. Preserve the existing canonical records, validations, previews, confirmations, replay protection, history, treatment evidence and atomic writes underneath the simpler interface.

The working experience must be:

1. open one litter;
2. see the current lifecycle stage and next useful action;
3. complete the relevant paper-like section;
4. preview and confirm the grouped effect once;
5. see that section completed and the next stage clearly presented.

## Five-section page

### 1. Paring en identiteit

Show canonical sow and boar names, mating date, Litter ID, expected farrowing date and actual farrowing date. Known facts are prefilled and are not requested again.

### 2. Geboorte

Show total born, born alive, stillborn and deaths after birth. Provide one grouped preview/save action. Explain any mismatch inside this section instead of sending the user to another visible workflow.

### 3. Eerste behandeling

Show date, male/female counts, deworming, Ecomectin and an explicit `Nie gedoen nie` option. This stage is optional and may not block supported later work. Known canonical products should be selected where defensible; advanced medicine evidence belongs behind progressive disclosure.

### 4. Speen en tweede behandeling

Provide one piglet table with tag, sex and weight, plus shared weaning date, destination pen, earmarking, tag, deworming and Ecomectin fields. Reuse the existing combined weaning-day backend so tags, weights, medicine, movement and weaning are previewed and confirmed as one coherent operation.

### 5. Vrektes en notas

Show a simple dated chronology supporting tagged and untagged piglets. Provide one compact `Voeg vrekte of nota by` action.

## Interaction rules

- Each section shows one state: `Nog nie begin nie`, `Besig`, `Voltooi`, `Oorgeslaan`, or `Aandag nodig`.
- The page names the single best next action at the top.
- The current section stays open; completed sections collapse to concise summaries and remain reopenable.
- Missing evidence blocks only the unsupported field or action.
- Existing canonical facts are never requested again merely because another workflow needs them.
- Use the same Afrikaans terminology as the printed record.
- Preserve English/internal data values where required by existing contracts; translate only the owner-facing presentation.
- Do not create a second litter ledger, duplicate data model or competing write path.

## Corrections and history

Move exceptional tools into a collapsed `Regstellings en geskiedenis` area:

- birth-count reconciliation;
- stillborn reclassification;
- manual tag correction;
- historical treatment evidence;
- lifecycle outcomes and audit history;
- exceptional manual actions.

Open or highlight this area automatically only when canonical evidence identifies a genuine contradiction requiring attention.

## Shared lifecycle view

Create one read-only litter lifecycle presentation model over the existing mating, litter, piglet, treatment, movement and lifecycle services. Both the printable record and application must consume compatible terminology and facts from this view. The presentation model must not gain write authority.

## Delivery sequence

1. Keep printable-form PR #772 bounded and reviewable.
2. Start the application redesign in a separate clean successor branch based on current governed main.
3. Add the shared read-only litter lifecycle view.
4. Recompose the existing litter page into the five approved sections.
5. Reuse existing preview/confirmation endpoints and the combined weaning-day service.
6. Move exceptional tools behind `Regstellings en geskiedenis` without deleting them.
7. Add regression coverage for active, newborn, first-treatment-skipped, overdue-weaning, weaned/completed and contradictory litters.
8. Exercise `LIT-2026-C9D3` read-only as the primary visual acceptance example without changing its records.
9. Obtain Charl's visual review of the completed page.
10. Merge and deploy only after that visual approval and normal integration gates.

## Success measurement

Charl can open `LIT-2026-C9D3`, understand the litter's current state and next action immediately, and complete an ordinary birth, treatment or weaning stage from the matching paper-style section without navigating among disconnected technical forms. Existing safety and audit behavior remains intact, and no litter data is changed during visual acceptance.

## Stop conditions

Return to Charl only for:

- a material workflow choice not covered here;
- a protected production/deployment decision;
- a genuine contradiction in canonical business meaning;
- the completed visual-review candidate.

Do not request approval of this redesign plan again.
