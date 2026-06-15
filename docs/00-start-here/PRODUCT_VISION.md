# Product Vision

## Purpose

This document describes the owner-facing product we are building, not the internal audit rails underneath it. Use it as the north star before adding new UI or agent behavior.

The goal is not to make the owner operate through long technical workbenches. The goal is a farm command system where Oom Sakkie is the central presence and specialist agents can be opened by voice or click when needed.

## Core Experience

Oom Sakkie is the home command center.

- The first screen should fit the normal owner workflow without long scrolling.
- The main visual should be a live Oom Sakkie presence that reacts when listening, checking, speaking, blocked, or idle.
- The owner can talk first, but every important action should also be available by click.
- Oom Sakkie should combine the important signals from the agents when asked broad questions such as `what needs attention today`.
- Specialist agents should not feel like database tables. They should feel like focused rooms with a clear role, queue, current suggestions, and owner actions.

## Home Screen

The Oom Sakkie home screen should show:

- live presence / face / animated identity
- current answer or operating brief
- urgent attention summary
- owner approval count
- agent dock at the bottom or side
- quick voice and typed input
- a small, deliberate path to the hidden system/audit workbench

The normal owner workflow should not require opening the long System Workbench.

## Agent Navigation

The owner should be able to open an agent by voice or click.

Examples:

- `Open Ledger`
- `Open Herdmaster`
- `Open Beacon`
- `Go back to Oom Sakkie`
- click the Ledger icon in the agent dock

When an agent opens:

- the agent identity becomes visible
- the agent greets or summarizes its current area
- the panel shows what it is watching
- it shows what it suggests
- it shows what needs owner approval
- it shows what it has prepared but not executed
- it clearly states what it cannot do yet

## Specialist Agents

Initial owner-facing agents:

| Agent | Role | First dashboard focus |
| --- | --- | --- |
| Oom Sakkie | Command center and owner interface | Combined farm brief, approvals, routing, voice |
| Ledger | Business, sales, money, opportunities | Campaigns, buyer leads, deposits, future expenses/profit |
| Herdmaster | Pigs, litters, breeding, growth, health | Litter attention, purpose review, growth/pig decisions |
| Beacon | Public content and demand generation | Draft posts/statuses, campaign wording, approval queue |
| Sam | Customer conversation and order intake | Chatwoot/WhatsApp conversations, orders, missing customer facts |
| Gatekeeper | Approval and safety | Actions waiting for owner approval, blocked actions, compliance checks |
| Rootline | Weather, irrigation, water planning | Forecast, irrigation plan, water risk, control-readiness |
| Butcher | Meat/slaughter pipeline | Meat candidates, slaughter fallback, carcass pipeline |
| Quartermaster | Supplies, expenses, operations | Feed, products, farm tasks, expense capture |

Agents can have personality, voice, and image assets later, but their authority must stay explicit.

## Workbench Rule

The System Workbench is an audit/admin surface.

It is useful for:

- trace review
- append-only proof
- dry-run requests
- migration/debug confirmation
- safety policy inspection
- developer verification

It is not the main owner workflow.

Owner-facing agent dashboards should summarize and guide. They should not expose every internal rail unless the owner chooses to open the audit view.

## Two-Week Live Target

The desired direction for a two-week live test is:

- Oom Sakkie gives a combined daily operating brief.
- Herdmaster alerts about animals, litters, growth, weaning, health, and purpose review.
- Ledger tracks sales opportunities, buyer leads, deposits, and business follow-up.
- Beacon prepares public post/status drafts for owner approval.
- Sam can support customer conversations only where the approved Chatwoot/WhatsApp flow allows it.
- Rootline can suggest irrigation plans and flag weather/water risks.
- Quartermaster begins tracking expenses/supplies once the data model is approved.

Live action boundaries:

- Public posts require owner approval before publishing.
- Customer messages require owner-approved channel rules, WhatsApp window/template handling, and opt-in logic.
- Irrigation control requires a separate hardware-control safety gate before anything can start/stop water.
- Orders, deposits, stock/allocation, and expenses must have source-of-truth records before agents can write them.
- Agent suggestions can become smart before agent actions become autonomous.

## Agent Personality And Assets

Each agent should eventually have:

- name
- role
- short personality description
- visual identity or face
- voice profile
- greeting style
- dashboard tone
- authority boundary

Asset direction:

- Use consistent portraits or symbols for the agent dock.
- Keep Oom Sakkie visually central and more alive than the specialists.
- Specialist images should be distinct, but not cartoonish unless explicitly chosen.
- Voice should be practical and recognizable, not theatrical.

Suggested future asset prompts can be added under each agent once the owner chooses the style. Until then, the UI should use initials and color-coded agent tiles.

## Build Direction

Immediate UI direction:

1. Keep `/oom-sakkie` as the command center.
2. Add a visible agent dock.
3. Let click and voice open a specialist panel.
4. Move the current long workbench further into an audit drawer.
5. Convert each internal rail into a simple agent dashboard summary.
6. Keep all dangerous actions blocked until each channel has a reviewed approval flow.

