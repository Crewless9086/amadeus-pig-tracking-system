# CHARLIE CORE UI Mission Standard

This standard controls CHARLIE CORE missions that build or change owner-facing UI, dashboards, pages, overlays, approval flows, or visual layouts.

## Non-Negotiable Rule

UI missions are not ready for owner review because strings exist in the DOM or routes return HTTP 200. They are ready only when the actual screen is usable, visually coherent, and checked against the owner's request and any attached reference media.

## Required Inputs

For every UI mission, agents must identify:

- the target page or route;
- the primary owner workflow;
- visible owner actions;
- required responsive viewports;
- attached screenshots, sketches, or reference images;
- the Vault Brain UI standards used.

If the mission includes attached media, Builder, Tester, QA/Red-Team, and Reviewer must explicitly cite the media reference path or URL and describe how it affected the implementation or review.

## Builder Requirements

Builder must provide:

- changed UI files;
- local preview URL for the actual changed page, not only the CHARLIE control dashboard;
- visual reference analysis when reference media exists;
- viewport plan covering desktop/laptop and mobile;
- notes on owner actions, buttons, overlays, and overflow handling;
- PR evidence for LEVEL 3+ releaseable changes.

Builder must not mark a UI build complete if approval buttons, review controls, mission details, or core navigation are hidden, overlapped, clipped, or only reachable through a broken modal.

## Tester Requirements

Tester must provide:

- browser-level checks for the actual changed route;
- desktop/laptop and mobile viewport evidence;
- proof that owner actions are visible and clickable;
- no-overlap/no-horizontal-overflow evidence;
- screenshot evidence or a clear reason capture failed;
- fallback command evidence if the normal browser test framework is unavailable.

String-only tests are insufficient for UI missions.

## QA/Red-Team Requirements

QA/Red-Team must actively challenge:

- whether the screen matches the owner's stated intent;
- whether attached reference media was used;
- whether buttons are visible and usable;
- whether the approval flow can actually be completed;
- whether the design is cramped, messy, unreadable, or visually misleading;
- whether mobile/desktop layouts overflow or hide important controls.

QA/Red-Team must send the mission back if the UI is merely technically present but owner-unusable.

## Reviewer Requirements

Reviewer must provide:

- final visual acceptance decision: `approve`, `send_back`, or `pause`;
- PR link;
- test evidence;
- captured visual review media;
- direct owner-facing release notes;
- any remaining visual concerns.

Reviewer must not recommend final owner approval when visual review media is missing, generated only from a fallback packet, unrelated to the actual changed page, or lacking desktop/mobile coverage.

## Runner Gate

CHARLIE CORE must block UI missions before owner review unless:

- a real local preview URL for the changed page is captured;
- desktop/laptop and mobile screenshot artifacts exist;
- attached reference media is cited when provided;
- Builder, Tester, QA/Red-Team, and Reviewer include UI-specific evidence;
- the review packet exposes visual media clearly to the owner.

Generated fallback packets are useful diagnostics, but they do not satisfy the UI mission visual gate.
