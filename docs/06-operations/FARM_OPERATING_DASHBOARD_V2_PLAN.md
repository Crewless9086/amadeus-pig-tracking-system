# Farm Operating Dashboard V2

Status: owner-approved implementation plan

Owner approval: Charl approved this redesign on 2026-08-10 after reviewing the live dashboard.

## Outcome

The `/` route becomes a compact, useful farm operating overview. It answers what needs attention, what is happening now, what happens next, and where to open the detailed operation. It does not duplicate specialist engineering packets or replace the `/oom-sakkie` agent command room.

## Current defects confirmed

- Weather, power and irrigation are repeated in the alert strip, primary tiles and the oversized ROOTLINE packet.
- The ROOTLINE packet exposes advisor, policy, water/energy, plan, evidence gaps and zone recommendations on the home page and leaves large unused grid space.
- Herd, breeding, orders and sales are pushed below the normal first-screen workflow.
- Dashboard loading waits for every backend request before rendering any successful result; slow telemetry leaves the entire page showing `Loading`.
- Cards are inconsistently clickable, navigation differs between pages, and the action area is an unstructured wall of shortcuts.
- Weather, power and irrigation have API capability but no owner-friendly detail pages.

## Product boundary

- `/`: operational farm truth, priorities and workflow entry points.
- `/oom-sakkie`: manager conversation, agent command room, specialist dock and protected decisions.
- `/weather`, `/power`, `/irrigation`: detailed read-only operational pages.
- ROOTLINE technical provenance remains available on the irrigation detail page under secondary/collapsed detail.

## Approved information architecture

1. Reusable application navigation: Home, Herd, Breeding, Sales, Orders, Operations, Oom Sakkie and Print, with a compact mobile menu.
2. Slim live farm-status bar: time/date, weather symbol and temperature, observed rain, battery SOC, irrigation state and genuine attention count.
3. Owner attention rail: only current welfare, overdue herd/breeding work, sales/order decisions, and material irrigation exceptions.
4. Six fully clickable operational cards: Weather, Power, Irrigation, Herd, Breeding, Sales & Orders.
5. One compact Oom Sakkie card with at most three priorities and one route to the full command room.
6. A small structured workflow menu rather than sixteen equally weighted action buttons.

## Loading and truth rules

- Every panel loads independently and renders as soon as its own evidence arrives.
- Every request has a bounded timeout.
- One slow or unavailable source never blocks unrelated available information.
- Loading, unavailable, stale, empty and error states are distinct.
- No unavailable value is rendered as a manufactured zero.
- Every operational tile shows its source freshness where supported.
- Unchanged specialist technical packets are not copied into the home page.

## Detail pages

### Weather

Current observed conditions, meaningful weather symbol, rain today, three-day forecast, daily coverage, and freshness. Forecast remains distinct from observation.

### Power

Current battery SOC, solar/load/grid/generator state, reserve context, recent profile and daily rollup quality. Power is not presented as a gate for gravity-fed B/C valves.

### Irrigation

B/C current decision, active/recent execution, today's canonical plan, weekly obligation/debt, effective rainfall, history, controller state, fertilizer/mixer status and a collapsed evidence/authority section.

## Interaction and visual rules

- Entire summary cards are keyboard-accessible links.
- Symbols communicate state and retain accessible text labels.
- Important actions live beside the relevant decision.
- Technical identities and long evidence text stay secondary.
- Desktop, laptop and mobile layouts must be visually reviewed with populated, loading, unavailable and partial-failure states.
- The result should feel warm, practical and alive, not like a generic admin table or an engineering log.

## Delivery sequence

1. Correct independent loading and timeout behavior.
2. Replace the duplicate ROOTLINE home packet with compact operational summaries.
3. Build status, attention, six-card and manager hierarchy.
4. Add Weather, Power and Irrigation detail routes using existing read APIs.
5. Add reusable navigation and structured workflow links.
6. Verify browser behavior, responsive layout, errors, freshness and destinations.
7. Present a populated local preview to Charl.
8. Merge and deploy only after visual approval and a clean serialized production window.

## Success measurement

- Available farm information appears without waiting for unrelated slow endpoints.
- Normal desktop use exposes current status, attention and all six operating areas without the old ROOTLINE scroll wall.
- Weather, Power and Irrigation cards open useful detailed pages.
- ROOTLINE information appears once at the correct level of detail.
- Desktop and mobile views have no overflow, dead space or hidden primary actions.
- Production remains unchanged until Charl approves the real local preview.
