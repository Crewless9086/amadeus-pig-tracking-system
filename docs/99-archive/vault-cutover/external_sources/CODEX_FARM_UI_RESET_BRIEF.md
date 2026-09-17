# Codex Brief: Rebuild `/oom-sakkie` As A Farm Command Center

## Purpose

The current `/oom-sakkie` screen has drifted toward a dark sci-fi AI dashboard. That is not the product direction.

Rebuild the first screen as a warm, practical farm command center where Oom Sakkie is the central farm presence, the owner can see all specialist agents without scrolling, and the System Workbench remains secondary.

## Non-Negotiable Product Direction

1. Oom Sakkie must be the main center of the screen.
2. Use the Oom Sakkie portrait, not an abstract OS orb or initials as the main identity.
3. The design must feel like a South African farm operating kiosk, not a sci-fi control room.
4. The entire owner-facing daily screen must fit in one viewport.
5. No document/body vertical scroll for the normal `/oom-sakkie` home screen.
6. All specialist agents must be visible on the first screen.
7. The agents must appear as portrait/profile tiles in a dock, not hidden below the fold.
8. The System Workbench must be a small secondary drawer/button, not the main experience.
9. Dangerous actions remain blocked unless owner-approved workflows exist.
10. Gatekeeper must always be visible in the agent dock.

## What Is Wrong With The Current Screen

The current screen uses:

- dark/black background
- sci-fi green circular hub
- `OS` initials instead of Oom Sakkie's face
- right-side grey panels that do not match the farm app
- no visible specialist agent dock in the first viewport
- too much empty dashboard space
- chat-app feeling instead of farm command center feeling

Replace this direction completely.

## Target Visual Language

Use:

- warm cream backgrounds
- khaki and sand surfaces
- olive green farm accents
- muted orange/amber for attention
- clean red only for urgent/blocking states
- soft shadows
- practical card borders
- farm landscape or subtle field texture behind Oom Sakkie
- readable dark brown/charcoal text
- physical/rural warmth

Avoid:

- black sci-fi backgrounds
- neon glow overload
- glassmorphism as the main style
- abstract AI orbs
- cyberpunk panels
- Iron Man/JARVIS imitation
- generic SaaS dashboard look
- hidden agent lists below the fold

## Required One-Screen Layout

Build the desktop layout as a fixed viewport command screen.

Use:

```css
.oom-sakkie-page {
  min-height: 100dvh;
  height: 100dvh;
  overflow: hidden;
  display: grid;
  grid-template-rows: 76px minmax(0, 1fr) 176px 36px;
  background: var(--farm-bg);
}
```

Suggested layout:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Header: Amadeus Farm | Weather | Today | Irrigation | Gatekeeper | Online │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Left: At A Glance       Center: OOM SAKKIE          Right: Priority Today │
│  - needs attention       large portrait/farm scene   - wean date due       │
│  - approvals waiting     daily brief bubble           - approvals           │
│  - tasks prepared        speak/type controls          - order/deposit       │
│  - info updates          listening/speaking state     - irrigation window   │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│ Agent Dock: Ledger | Herdmaster | Beacon | Sam | Gatekeeper | Rootline     │
│             Butcher | Quartermaster                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ Safety footer: no send / no payments / no hardware control without approval│
└────────────────────────────────────────────────────────────────────────────┘
```

## Center Stage Requirements

The center area must contain:

- actual Oom Sakkie portrait
- name/logo text: `Oom Sakkie`
- current speaking/listening/thinking state
- compact daily brief bubble
- primary controls: `Speak`, `Type`, `Ask Anything`, `Daily Brief`

Do not use the circular `OS` hub as the main identity.

Recommended center stage sizing:

```css
.oom-center-stage {
  min-width: 0;
  min-height: 0;
  display: grid;
  place-items: center;
  position: relative;
  border-radius: 28px;
  overflow: hidden;
  background:
    linear-gradient(rgba(255, 248, 232, 0.62), rgba(255, 248, 232, 0.82)),
    url('/assets/farm/farm-command-bg.jpg');
}

.oom-portrait {
  width: clamp(260px, 26vw, 430px);
  max-height: min(56vh, 460px);
  object-fit: contain;
  object-position: center bottom;
}
```

## Agent Dock Requirements

The dock must show all eight specialist agents on the first screen:

1. Ledger
2. Herdmaster
3. Beacon
4. Sam
5. Gatekeeper
6. Rootline
7. Butcher
8. Quartermaster

Each tile must show:

- portrait/avatar
- name
- role label
- status dot or ring
- count badge when relevant

Use the asset registry where possible:

```text
static/assets/agents/agent_registry.json
```

Each tile should load:

```text
/assets/agents/{agent_id}/portraits/{agent_id}_portrait_dock_neutral_v01.png
```

If an image is missing, fall back to initials only inside that agent tile. Do not use initials for the main Oom Sakkie center stage if his portrait exists.

## Specialist Open Behavior

When the owner clicks or calls an agent:

- do not navigate away to a long table page
- keep Oom Sakkie visible
- open a compact specialist workspace overlay or right-side drawer
- show the agent portrait, greeting, summary cards, queue, suggestions, approvals, and blocked items
- the dock remains visible

## CSS Tokens

Use tokens like:

```css
:root {
  --farm-bg: #efe3ce;
  --farm-surface: #fff7e8;
  --farm-surface-strong: #f8ead2;
  --farm-border: #d9c29d;
  --farm-text: #2c261d;
  --farm-muted: #756a5a;
  --farm-green: #5f7d3a;
  --farm-green-dark: #36512a;
  --farm-amber: #d8892f;
  --farm-red: #b84a36;
  --farm-blue: #5b7fa7;
}
```

## Acceptance Criteria

The rebuild is acceptable only when all of these are true:

- At 1366x768, the owner can see Oom Sakkie and all eight agents without scrolling.
- At 1920x1080, the screen still looks like a single command center, not a stretched dashboard.
- The browser body does not scroll vertically on the `/oom-sakkie` home screen.
- Oom Sakkie is visually centered and is the largest human/agent identity on the screen.
- The main center uses the Oom Sakkie portrait.
- The color system is farm-warm, not black/neon sci-fi.
- The agent dock is always visible.
- Gatekeeper is always visible.
- The System Workbench is secondary.
- No risky action appears as executable without owner approval.

## Implementation Instruction For Codex

Start by replacing the current `/oom-sakkie` route shell and CSS. Do not patch the existing dark sci-fi screen. Create a new farm-first layout shell with fixed viewport rows, visible agent dock, centered Oom Sakkie portrait, left summary cards, right priority cards, and a secondary audit/workbench button.

Do not overbuild agent logic yet. First make the layout correct.

