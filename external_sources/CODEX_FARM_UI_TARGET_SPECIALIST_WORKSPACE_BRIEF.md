# Codex Brief: Oom Sakkie Farm UI Target + Specialist Workspace Mode

## Purpose

The current `/oom-sakkie` implementation is close in structure but still misses the intended look and interaction model. The target is a warm, practical South African farm command center, not a dark AI dashboard and not a sci-fi command console.

Use the provided farm command center concept image as the visual target. The key traits are:

- warm cream/sand/khaki/olive colour palette
- Oom Sakkie as the central human presence
- actual portrait, not abstract initials or an orb
- all eight agents visible in one dock without page scrolling
- simple farm cards with readable text
- no dark sci-fi background
- no neon-glass command panels
- no page-level vertical scroll on desktop

## Reference Images

Attach these to the design/build prompt:

1. `a_detailed_ui_dashboard_concept_illustration_scr(1).png`  
   Target home screen: warm farm command center, Oom Sakkie central, left summary, right priorities, all agents visible.

2. `a_clean_high_detail_ui_design_mockup_dashboard.png`  
   Target explanation for specialist workspace behavior: agents open as farm-style specialist workspaces while Oom Sakkie remains accessible and the system stays one-page.

3. `image.png`  
   Current implementation screenshot: use only as a list of things to fix, not as the style target.

## Core Correction

Do not interpret "Oom Sakkie in the middle" as an abstract AI hub or a text label.

Oom Sakkie must be the central human character and farm command presence:

- Use his portrait as the hero identity.
- Place him inside a warm farm landscape/stage.
- Show a short daily brief bubble beside him.
- Add listening/speaking state around him using subtle farm-friendly UI, not sci-fi rings.
- Arrange the rest of the interface around him.

## Current Problems to Fix

The current screenshot has these issues:

1. The active specialist panel overlays the center stage and covers Oom Sakkie.
2. The specialist panel creates visible internal browser-style scrollbars in the main hero area.
3. The Oom Sakkie portrait is too small and trapped behind overlays.
4. The agent dock uses initials instead of portraits.
5. The agent dock sits on a dark strip that feels heavy and wrong for the farm theme.
6. The command input appears below the dock, which risks pushing the page into scrolling.
7. The layout does not feel as polished, spacious, and warm as the target concept.
8. The active agent state is visually noisy and hard to read because it is transparent over the hero.
9. The target screen should feel like a farm operating kiosk, not a web page with panels fighting for space.

## Required Home Screen Layout

Build the `/oom-sakkie` home screen as a fixed one-page viewport.

At desktop size, the owner must see all of this without vertical page scroll:

- header
- farm status chips
- Oom Sakkie center stage
- left “At a glance” cards
- right “Priority today” cards
- command bar
- all eight agents in the dock
- small safety footer

Suggested grid:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Header: farm name | weather | date | irrigation | gatekeeper | online │
├──────────────────────────────────────────────────────────────────────┤
│ Left glance cards |      Oom Sakkie center stage      | priorities   │
│                   | portrait + farm background + brief |              │
│                   | command bar overlays bottom center |              │
├──────────────────────────────────────────────────────────────────────┤
│ Ledger | Herdmaster | Beacon | Sam | Gatekeeper | Rootline | Butcher | QM │
├──────────────────────────────────────────────────────────────────────┤
│ Safety footer: no send/payment/post/hardware control without approval │
└──────────────────────────────────────────────────────────────────────┘
```

## Desktop Layout CSS Direction

Use a fixed viewport grid.

```css
.oom-sakkie-page {
  height: 100dvh;
  min-height: 100dvh;
  overflow: hidden;
  display: grid;
  grid-template-rows: 72px minmax(0, 1fr) 150px 32px;
  background: var(--farm-bg);
  color: var(--farm-text);
}

.oom-header {
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  align-items: center;
  gap: 16px;
  padding: 10px 18px;
  background: var(--farm-surface-header);
  border-bottom: 1px solid var(--farm-border);
}

.oom-main {
  min-height: 0;
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr) 300px;
  gap: 14px;
  padding: 14px 18px 8px;
  overflow: hidden;
}

.oom-center-stage {
  min-height: 0;
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  background:
    linear-gradient(90deg, rgba(251, 241, 218, 0.78), rgba(251, 241, 218, 0.28), rgba(251, 241, 218, 0.72)),
    url('/assets/farm/farm-command-bg.jpg');
  background-size: cover;
  background-position: center;
  box-shadow: var(--farm-shadow-soft);
}

.oom-portrait {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: clamp(300px, 31vw, 520px);
  max-height: 100%;
  object-fit: contain;
  object-position: center bottom;
}

.oom-command-bar {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  width: min(720px, calc(100% - 80px));
  z-index: 3;
}

.agent-dock {
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(8, minmax(112px, 1fr));
  gap: 10px;
  padding: 8px 18px 10px;
  overflow: hidden;
  background: var(--farm-bg-dock);
  border-top: 1px solid var(--farm-border);
}

.safety-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  font-size: 12px;
  background: var(--farm-surface-footer);
  border-top: 1px solid var(--farm-border);
}
```

## Farm Colour Tokens

Use these tokens or close equivalents:

```css
:root {
  --farm-bg: #efe1c5;
  --farm-bg-soft: #f7ecd6;
  --farm-bg-dock: #e3d1ad;
  --farm-surface: #fff6e7;
  --farm-surface-header: #f4e6cc;
  --farm-surface-footer: #ead8b8;
  --farm-card: #fff8ec;
  --farm-border: rgba(95, 74, 42, 0.18);
  --farm-text: #2a2419;
  --farm-text-muted: #6d614e;
  --farm-green: #4f7d35;
  --farm-green-dark: #2f5a2d;
  --farm-amber: #df8f22;
  --farm-red: #c8523f;
  --farm-blue: #5b82aa;
  --farm-purple: #8357a4;
  --farm-shadow-soft: 0 18px 42px rgba(66, 47, 22, 0.18);
}
```

## Agent Dock Requirements

The agent dock is mandatory and always visible.

Agents in order:

1. Ledger
2. Herdmaster
3. Beacon
4. Sam
5. Gatekeeper
6. Rootline
7. Butcher
8. Quartermaster

Each dock tile must show:

- portrait image from the asset registry when available
- initials only as fallback
- status ring around portrait
- badge count when relevant
- agent name
- short role label
- status text and dot

Use these labels:

- Ledger — Sales & Money
- Herdmaster — Pigs & Herd
- Beacon — Public & Content
- Sam — Customers & Orders
- Gatekeeper — Approvals & Safety
- Rootline — Weather & Water
- Butcher — Meat Pipeline
- Quartermaster — Supplies & Ops

The dock must not be a dark strip. It should be warm cream/sand with soft farm-card tiles.

## Agent Open Behavior

When the owner clicks an agent, do not navigate away, do not open a full page, and do not place a transparent panel over Oom Sakkie with ugly scrollbars.

Use a one-page specialist workspace mode.

### Preferred behavior

- Oom Sakkie remains accessible.
- The chosen agent opens in a warm farm-card workspace.
- The page does not scroll.
- The agent dock remains visible.
- The owner can return to Oom Sakkie with one click.
- Long specialist detail may scroll inside the workspace only, never the full page.

### Open agent layout

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Header remains the same                                               │
├──────────────────────────────────────────────────────────────────────┤
│ Left: small Oom Sakkie coordinator | Main: selected agent workspace   │
│                                    | Right: needs decision / actions  │
├──────────────────────────────────────────────────────────────────────┤
│ All eight agents still visible in the dock                            │
├──────────────────────────────────────────────────────────────────────┤
│ Safety footer remains visible                                         │
└──────────────────────────────────────────────────────────────────────┘
```

### Specialist workspace content

Every specialist workspace should have:

- Back to Oom Sakkie
- agent portrait
- agent name and short role
- current status
- short greeting
- “I am watching” list
- live summary cards
- needs-your-decision cards
- suggestions
- prepared-but-not-executed cards
- workflow buttons
- authority boundary note

## Example: Ledger Workspace

Ledger should show:

- Business Snapshot
- New leads
- Deposits received
- Follow-ups due
- Projected profit
- Needs your decision
- Approve quote
- Confirm delivery
- Approve discount
- Suggestions
- Prepared but not executed
- Go to Leads / Go to Orders / Go to Invoices / Reports

Ledger must not send quotes, allocate stock, create orders, or record money unless the approved rails exist.

## Example: Herdmaster Workspace

Herdmaster should show:

- Herd Snapshot
- Litters needing attention
- Weanings due
- Health alerts
- Purpose review
- Recheck weight
- Health alert
- Suggestions
- Prepared but not executed
- Go to Litters / Go to Pigs / Health Log / Growth Charts

Herdmaster must not change purpose, death, health, movement, or lifecycle records without owner approval and source-of-truth workflow.

## Example: Rootline Workspace

Rootline should show:

- Weather & Irrigation
- Current temperature
- rain chance
- irrigation window
- next rain
- start irrigation decision card
- adjust run time decision card
- water budget review
- suggestions
- prepared irrigation plan
- Go to Irrigation / Weather Map / Water Usage / Soil Moisture

Rootline must not start/stop hardware unless a separate hardware-control safety gate is approved.

## What Not To Do

Do not:

- use an abstract “OS” orb as the main Oom Sakkie identity
- hide agents below the fold
- create page-level scrolling
- show all specialist details in transparent overlays over Oom Sakkie
- use black, charcoal, neon, cyberpunk, glassmorphism, or sci-fi command styling
- put the typed command box below the agent dock
- make the System Workbench the main daily workflow
- hard-code voice IDs or image paths into components when metadata exists

## Acceptance Tests

The build is accepted only if:

1. At 1366x768, no vertical body/page scroll exists on `/oom-sakkie` home.
2. Oom Sakkie’s actual portrait is clearly visible and central.
3. The screen feels warm, farm-like, and practical.
4. All eight agents are visible in one row.
5. The agent dock uses portraits when available, initials only as fallback.
6. The agent dock does not use a dark strip.
7. Clicking an agent opens a specialist workspace without navigating away.
8. Opening an agent does not cover Oom Sakkie with a transparent unreadable panel.
9. The selected specialist workspace has live summary, needs decision, suggestions, prepared actions, and authority boundary.
10. The System Workbench remains a small secondary audit/admin button or drawer.
11. Risky actions stay blocked unless an owner approval workflow exists.
12. The page matches the reference concept closer than the current implementation.

## One-Sentence North Star

Oom Sakkie is a warm farm command uncle at the center of the operating kiosk, with all specialist farm agents visible and ready around him; the owner stays in control without scrolling through a technical dashboard.
