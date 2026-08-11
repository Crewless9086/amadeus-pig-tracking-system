# Pig Profile Life Record UI Plan

Status: Owner-approved design plan; local acceptance sample required before integration.

## Owner outcome

`/pig/<pig_id>` must become the authoritative, understandable life record for one animal. A farm user must be able to open one profile and understand who the animal is, where it is, what has happened to it, what currently needs attention, and its breeding, production, health and commercial outcomes without visiting several disconnected pages.

The accepted visual system is the current Amadeus operational dashboard: full-width workspace, farm navigation, green/cream/earth palette, strong identity, compact current-state cards, responsive layout and progressive disclosure for administrative tools.

## Canonical data rule

The profile creates no parallel animal database. It composes existing canonical Supabase-backed reads for current pig state, weights, treatments, movements, family tree, matings, litters, breeding observations and attributable sale/lifecycle outcomes. Unknown evidence remains Unknown. Associated evidence is labelled and never promoted to a diagnosis, pedigree fact, service result or financial fact.

The older OP-006 statement that Google Sheets is the profile source is stale. Supabase canonical reads are authoritative; compatibility fallbacks must not be presented as a second truth.

## First viewport

1. Animal identity: name/tag, canonical ID, sex/type, status, on-farm state, current pen and purpose.
2. Evidence-backed attention strip: only current weight, withdrawal, breeding/litter, location, reservation or lifecycle exceptions. No generic warnings.
3. Current snapshot: weight/date, age, pen, purpose, withdrawal and availability/reservation.
4. Routine actions: record weight, treatment and movement. History links remain available but do not dominate.

## Life record sections

1. **Life timeline:** birth, weaning, weights, movements, treatments, matings, pregnancy/farrowing, linked litters and terminal sale/slaughter/removal/mortality outcomes in chronological order.
2. **Weight and growth:** latest change, comparable history, growth rate where supported, notes, full history and record-weight action.
3. **Breeding and offspring:** role-adaptive sow/boar evidence, matings, partners, outcomes, linked litters, born-alive/survival/weaning evidence and current holds or plans where attributable.
4. **Health and treatments:** current withdrawal state, last treatment, full treatment history and explicit empty state.
5. **Movement and housing:** current pen, move chronology, reasons and explicit empty state.
6. **Family and pedigree:** parents, birth litter, siblings and descendants where known; founder ancestry remains explicitly Unknown.
7. **Commercial and lifecycle:** purpose, availability/reservation, attributable sale/order/auction/slaughter outcome, exit facts and preserved historical identity.
8. **Notes and evidence quality:** factual notes, provenance and missing evidence without repeating generic system language.

## Role adaptation

- Sow: mating, pregnancy, farrowing, litter and offspring performance are prominent.
- Boar: services across sows and attributable offspring outcomes are prominent.
- Grower/sale pig: origin, weight trajectory, health, location and commercial readiness are prominent.
- Terminal animal: current-action controls are replaced by a clear historical outcome summary.

## Protected actions

Death/removal and other terminal lifecycle mutations remain governed by the existing protected route. They are placed in a collapsed, clearly separated lifecycle-action area. This mission does not weaken confirmation, replay, authority, medical, sale or lifecycle controls and adds no write shortcut.

## Acceptance sample

Bonnie (`PIG-2026-5376`) is the first local acceptance profile because current canonical evidence exercises the required sections: breeding sow, current D3 location, weight history including a material change, movement history, completed Tyson mating and linked litter `LIT-2026-812B`, no treatment history and unknown founder parentage.

## Success measurement

- Charl can understand Bonnie's current state and life history from one profile without opening separate history pages.
- Current facts, associated facts and Unknowns remain visually distinct.
- Existing record-weight, treatment, movement, family and protected lifecycle flows retain their exact routes and authority.
- Desktop, tablet and mobile layouts have no overlap or horizontal clipping.
- Missing endpoint data degrades by section rather than failing the whole profile.
- No farm record, customer record or external provider state changes during UI acceptance.

## Implementation boundary

Allowed: pig-detail template, dedicated profile CSS/JS, read-only profile composition where necessary, route-contract/browser tests and this plan.

Not allowed without separate authority: pig writes, lifecycle semantics, migrations, sales commitments, medical inference, pedigree invention or production deployment before owner approval.
