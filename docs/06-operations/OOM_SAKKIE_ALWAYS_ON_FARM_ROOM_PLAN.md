# Oom Sakkie Always-On Farm Room Plan

Status: owner-approved product direction; implementation in local review

Owner decision date: 2026-08-11

## Owner-visible outcome

Oom Sakkie becomes the always-on farm manager in the Amadeus Farm office: a
calm ambient farm display when nobody needs him and a natural, conversational,
visually alive manager when the family calls him. Charl, his mum and his dad
must be able to walk past the display and understand the farm's current
position, or speak naturally and receive the same canonical facts, retained
context, recommendations and protected decisions that Oom Sakkie uses through
Telegram.

The browser and Telegram are two interfaces to one Oom Sakkie. They must never
become separate brains, separate memories or competing farm managers.

## Product principles

1. The screen is a living farm room, not another dense administration page.
2. Idle information is glanceable from across the office.
3. Oom Sakkie appears only when called or when a genuinely important exception
   warrants attention.
4. Information appears once in the most useful place; shortcut cards must not
   repeat the same status in several areas.
5. Technical traces, audit tools and specialist implementation detail remain
   available but secondary.
6. Browser, Telegram and later approved channels share one authenticated
   conversation spine, canonical evidence packet, retained context,
   personality, specialist dispatch and authority policy.
7. Channel presentation may differ; farm truth and decisions may not.
8. The experience must reduce Charl's mental load and should never require him
   to translate internal agent names, IDs, lifecycle states or technical
   blockers.

## Experience states

### 1. Ambient idle mode

The ordinary always-on state should:

- fit within the available browser viewport above the operating-system taskbar;
- show an approved farm photograph as the main visual canvas;
- rotate approved farm photographs slowly with a calm cross-fade;
- keep the complete photograph visible without accidental clipping;
- show compact, live, source-labelled overlays for weather, power, irrigation
  and genuine farm attention;
- show only current, actionable alerts;
- show a compact specialist dock with meaningful state rather than eight large
  duplicate cards;
- avoid permanent speech bubbles, command cards or technical panels over the
  photograph;
- remain useful when viewed from several metres away.

The current approved idle reference is:

`screenshots/ChatGPT Image Jun 16, 2026, 12_02_31 AM.png`

The implementation asset prepared for the local prototype is:

`static/assets/agents/oom-sakkie/portraits/oom-sakkie_command_room_idle_v01.png`

Future slideshow images must come from an owner-approved private farm-photo
library. A missing or unavailable image must fall back to the approved Oom
Sakkie farm-room visual without breaking the status display.

### 2. Awake conversational mode

Oom Sakkie wakes when an authenticated user presses Speak, uses the approved
wake interaction, or begins an explicit text conversation. The screen should:

- pause and soften the ambient slideshow;
- transition to Oom Sakkie's visual presence;
- clearly show `Listening`, `Thinking`, `Speaking` and `Waiting` states;
- preserve natural conversational context across turns;
- allow the user to interrupt or stop speech;
- display the answer without covering Oom Sakkie's face;
- show supporting plans, tables, photographs or confirmation buttons only when
  relevant to the current conversation;
- return to ambient mode after a configurable period of inactivity.

The first release may use a still portrait with subtle state animation. The
visual boundary must permit a later animated or lip-synchronised avatar without
rebuilding the conversation and specialist architecture.

### 3. Specialist focus mode

The specialist dock is an orientation and navigation rail, not a second
dashboard. Each specialist shows one concise current state, for example:

- `HERDMASTER — breeding plan current`;
- `ROOTLINE — next dry reassessment pending`;
- `SAM — owner decision required`;
- `BEACON — no active work`.

Selecting a specialist opens one full operational workspace. Other specialists
collapse back into the compact dock. Hidden command decks, technical panels and
answer controls must never overlap the selected workspace.

### 4. Important exception mode

Oom Sakkie may interrupt ambient mode only for a genuine, material exception
inside approved notification policy. Examples include a welfare emergency, a
failed irrigation shutdown, a protected customer decision nearing expiry or
another owner-approved urgent class. Routine unchanged Holds, repeated stale
tasks and generic analytics must not commandeer the display.

## Shared browser and Telegram spine

The intended architecture is:

```text
Browser voice/text ----\
                        > authenticated Oom Sakkie conversation spine
Telegram text/voice ---/                    |
                                             +-- retained conversation context
                                             +-- canonical farm evidence
                                             +-- Oom Sakkie personality and language
                                             +-- HERDMASTER / ROOTLINE / SAM / BEACON
                                             +-- protected previews and confirmations
                                             +-- provider/channel delivery adapters
```

Both channels must share:

- authenticated family identity and role;
- canonical farm and business evidence;
- retained owner facts and current conversation context;
- semantic interpretation and Oom Sakkie's personality;
- specialist selection and response composition;
- protected-action policies, preview identity and confirmation state;
- replay, concurrency and audit protections;
- current task retirement and follow-up ownership.

Channel-specific behavior remains appropriate:

- Telegram is asynchronous, portable and provider-message-bound.
- The browser supports persistent sessions, richer visual evidence, low-friction
  buttons, continuous voice interaction and interruption.
- A protected decision initiated on one channel may be completed on another
  only when identity, preview, current evidence and confirmation binding remain
  exact and the transition is explicitly supported.
- Neither channel may silently claim a delivery or action performed by the
  other.

## Personality and voice requirements

Oom Sakkie should feel like a trusted, experienced farm manager who knows the
farm and works alongside the family. He should be warm, practical, concise and
comfortable in Afrikaans, English and natural mixed language.

The personality must not be a decorative prompt applied after deterministic
output. The semantic conversation layer should understand intent and context;
deterministic services remain authoritative for identity, facts,
calculations, specialist dispatch, protected actions and hardware safety.

Required conversational behavior includes:

- remember the current subject across natural follow-ups;
- answer the requested question before offering broader context;
- use names and ordinary farm language instead of unnecessary IDs;
- ask at most one grouped question when a genuine fact is missing;
- distinguish advice, plans, completed records and physical actions;
- speak concise answers while allowing richer supporting detail on screen;
- never resurrect completed or superseded tasks as current work;
- preserve the same answer quality and facts across browser and Telegram.

## Live ambient data

The initial persistent rail uses the same canonical sources as the operational
dashboard:

- weather: local farm weather station current observation;
- power: current Sunsynk/provider telemetry;
- irrigation: ROOTLINE canonical current execution and B/C plan;
- farm attention: current herd/litter attention from canonical projections.

Each item must show source freshness or an honest `Unavailable`. It must never
fall back to stale Google Sheet or placeholder data while presenting it as
current. Authentication failure must be distinguished from missing telemetry.

Later additions should be evidence-led and space-limited. Candidate rotating
facts include the next farrowing, the next breeding placement, sales requiring
an owner decision and today's completed work. These should replace—not
duplicate—less valuable information.

## Viewport and layout contract

The always-on view must be tested at the actual office display resolution and
browser chrome height. The idle composition must fit without requiring a
scroll to see the main photograph, live rail or speaking control.

The final kiosk composition should use:

1. one compact identity/navigation rail;
2. one large farm-photo or awake-avatar canvas sized from remaining viewport
   height;
3. compact glass status overlays on the canvas;
4. one compact conversation control;
5. one collapsible specialist dock.

The current local prototype still places status tiles above the image and
therefore exceeds the available height on Charl's 1920x1080 browser viewport.
That is a known local-review defect, not an accepted layout.

## Implementation phases

### Phase A — viewport-correct ambient room

- Recompose the page as a single viewport-aware kiosk.
- Move live status into compact overlays.
- Make the approved image fully visible at the actual office resolution.
- Collapse the specialist team into a compact dock.
- Remove every hidden or duplicate layer that can overlap the canvas or an open
  specialist.
- Prove desktop, actual office viewport and mobile fallback visually.

### Phase B — approved farm-photo slideshow

- Define an owner-approved private slideshow manifest.
- Add cross-fade, pause, resume and deterministic fallback behavior.
- Do not expose private images publicly or send them to another channel.
- Keep status and controls legible across bright and dark photographs.

### Phase C — conversational awake state

- Bind browser text and voice to the same deployed Oom Sakkie semantic spine as
  Telegram.
- Add explicit listening/thinking/speaking/waiting transitions.
- Preserve conversational context and support interruption.
- Separate spoken summary from richer visual detail.
- Prove English, Afrikaans and mixed-language conversations.

### Phase D — visually alive Oom Sakkie

- Select an approved animation approach and voice.
- Start with subtle presence animation if full lip synchronisation is not yet
  reliable.
- Avoid uncanny, distracting or misleading animation.
- Keep the still-image fallback operational.

### Phase E — real-world office acceptance

- Run the screen continuously in the office.
- Complete genuine weather, power, irrigation, herd and specialist checks.
- Complete one natural multi-turn browser voice conversation.
- Resume the same subject through Telegram without lost or contradicted facts.
- Complete one protected preview/confirmation journey without duplicate
  effects.
- Verify return to ambient mode and continued automatic refresh.

## Definition of done

This mission is not complete when the page merely looks attractive, passes CI
or plays speech. Completion requires all of the following:

1. The actual office display shows the complete intended idle composition with
   no cropped primary canvas, overlap or hidden specialist content.
2. Live weather, power, irrigation and farm attention load from authenticated,
   canonical sources and show honest freshness.
3. Approved farm photographs rotate safely while Oom Sakkie is idle.
4. Calling Oom Sakkie produces a clear awake state and a natural multi-turn
   spoken conversation.
5. The same question through browser and Telegram uses the same current facts,
   retained context and specialist reasoning.
6. A cross-channel follow-up preserves the subject without asking the family to
   repeat known facts.
7. One protected action is previewed and confirmed through the approved rail
   with zero duplicate effects.
8. Oom Sakkie returns to ambient mode and continues operating without terminal
   assistance.
9. The relevant identity, workflow, source map, tests and operational handover
   reflect the proven implementation.

## Current local implementation status

Prepared locally in isolated worktree `C:\tmp\oom-sakkie-command-center-ui`:

- dashboard-aligned colour and navigation treatment;
- approved Oom Sakkie reference image asset;
- first ambient live-data rail for weather, power, irrigation and herd;
- retained browser speech and specialist behavior;
- removal of several duplicate shortcut panels;
- route and browser regression coverage passing at the last local check.

Not approved or deployed:

- final viewport-aware kiosk composition;
- slideshow;
- compact specialist dock;
- finished awake interaction composition;
- animated avatar;
- shared browser/Telegram real-world conversational proof.

Resume from Phase A after Charl's next visual review. Do not deploy the current
prototype as the final always-on interface.
