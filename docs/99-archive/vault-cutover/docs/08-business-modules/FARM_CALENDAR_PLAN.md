# Farm Calendar Plan

## Status

Planning complete through Prompt 4. No calendar runtime has been built yet.

This document is the source of truth for the first farm-wide calendar build. It should stay short and operational. Detailed implementation notes belong in the code, migrations, and tests once the build starts.

## Goal

Build one farm-wide calendar that helps the owner see what matters this month without opening every module.

The calendar must combine:

- manual tasks, events, and reminders stored in Supabase
- system-generated farm dates from breeding, litters, medical records, meat sales, and fulfilment
- weather context for each day when forecast data is available
- direct links back to the source item, such as a litter, mating, pig, sale, or lead

The calendar is an owner-facing operating surface, not a data dump.

## Confirmed Decisions

- Use one farm-wide calendar first, not separate calendars per module.
- Month view is the first and most important view.
- Manual calendar items need a real Supabase table.
- System-generated farm events are read-only and generated from source records.
- Manual items are editable and deletable.
- Notifications are deferred until the calendar is stable.
- Weather should be visible at a glance through subtle day-tile styling and icons.
- Calendar entries must link back to their source detail page where possible.

## Prompt 4 UI Direction

PRISMA direction: the calendar must be calm, quick to scan, and useful on a phone or laptop.

The first build should use the smallest useful surface:

- top bar with month navigation, Today, Add, and simple filters
- desktop month grid with stable day tile sizes
- mobile month grid plus selected-day agenda, not a long scrolling workbench
- subtle weather layer in each day tile, faded behind the events
- maximum three event chips per day tile, then `+N more`
- selected-day detail panel with clear sections: needs attention, scheduled, done, blocked
- manual add/edit modal with only the fields required for a useful farm reminder
- system events show `Open source`; manual events show edit/delete controls

The UI must avoid:

- long pages
- nested cards
- repeated explanation text
- crowded day tiles
- vague labels
- noisy animation
- forcing the owner to scroll for normal month use

Weather motion, if added, must be subtle and respect reduced-motion preferences.

## Event Categories

Use these fixed category keys in the first build:

| Category | Purpose |
| --- | --- |
| `breeding` | Mating, pregnancy check, expected farrowing, actual farrowing. |
| `litter` | Litter born, estimated wean, actual wean, tag/wean attention. |
| `medical` | Treatment, follow-up, withdrawal end. |
| `sales` | Meat fulfilment, abattoir, butcher, delivery, collection, sales gates. |
| `weather` | Forecast/weather context for the day. |
| `manual_task` | Owner-created task. |
| `manual_event` | Owner-created event. |
| `manual_reminder` | Owner-created reminder. |

## Source Dates For First Build

Include dates that change owner action or planning:

- `MATING_OVERVIEW`: mating date, expected pregnancy check, pregnancy check, expected farrowing, actual farrowing.
- `LITTER_OVERVIEW` and litter detail data: litter born/farrowing, estimated wean, tag/wean attention start, actual wean.
- `MEDICAL_LOG`: treatment date, follow-up date, withdrawal end.
- Meat sales and fulfilment rails: abattoir requested/confirmed, butcher requested/confirmed, delivery scheduled, collection or delivery window.
- Meat planning: estimated meat-ready and abattoir-ready dates when available.
- Weather forecast data already stored in Supabase.
- Owner-created manual tasks, events, and reminders.

Exclude dates that do not help daily operations, such as row-created timestamps, row-updated timestamps, and normal audit log entries.

## Backend Shape

Add a Supabase table for manual items:

`farm_calendar_events`

Minimum fields:

- `id`
- `event_type`
- `category`
- `title`
- `description`
- `starts_at`
- `ends_at`
- `all_day`
- `priority`
- `status`
- `source_type`
- `source_id`
- `source_label`
- `href`
- `recurrence_rule`
- `expires_at`
- `created_by`
- `created_at`
- `updated_at`

Add one backend aggregation endpoint:

`GET /api/calendar/events?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`

The endpoint should:

- require a date range
- filter early by date range
- return manual Supabase items plus generated system events
- normalize every event into one response shape
- include `editable = true` only for manual items
- include `href` from the backend, not guessed in the frontend
- degrade cleanly when a source system is unavailable

## Normalized Event Shape

```json
{
  "id": "calendar-event-id",
  "event_type": "system_or_manual",
  "category": "litter",
  "title": "Estimated wean",
  "description": "LIT-2026-1025 estimated wean date",
  "date": "2026-06-22",
  "starts_at": "2026-06-22T00:00:00+02:00",
  "ends_at": null,
  "all_day": true,
  "priority": "normal",
  "status": "scheduled",
  "source_type": "litter",
  "source_id": "LIT-2026-1025",
  "source_label": "Litter LIT-2026-1025",
  "href": "/litter/LIT-2026-1025",
  "editable": false
}
```

## Product Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Calendar becomes noisy and useless. | Only include operational dates; use filters and max three chips per day tile. |
| Weather styling hides the farm events. | Keep weather faded behind content and use readable event chips. |
| Owner cannot tell what can be edited. | Manual items show edit/delete; system items show `Open source` only. |
| Backend aggregation gets slow. | Date range is required and each source filters early. |
| Recurrence becomes a half-built bug. | Store recurrence fields now, but first UI creates one-off items only. |
| Mobile month view becomes cramped. | Use compact month tiles and a selected-day agenda panel. |
| Links break when modules change. | Backend owns `href`, `source_type`, and `source_id`. |
| Weather data is missing or stale. | Show neutral day tile and continue loading events. |

## Build Phases

### Phase 12A - Calendar Backend Foundation

- Add Supabase migration for `farm_calendar_events`.
- Add manual calendar event CRUD endpoints.
- Add date-range event aggregation endpoint.
- Add unit tests for manual items, generated events, date filtering, and read-only/editable boundaries.

### Phase 12B - Farm Calendar UI

- Add `/calendar`.
- Build month view with weather-aware day tiles.
- Add filters, selected-day detail panel, and manual add/edit/delete.
- Keep source events read-only and linked.
- Verify desktop and phone layouts.

### Phase 12C - Dashboard Preview

- Add compact upcoming calendar preview to the Farm App/Oom Sakkie daily view.
- Show only the next few important items and a link to the full calendar.

## Explicit Non-Goals For First Build

- No notifications.
- No autonomous agent actions.
- No automatic customer messages.
- No public posts.
- No recurring-item editor beyond storing future-ready fields.
- No write-back to source records from the calendar.
- No calendar sync to Google Calendar, Outlook, Meta, or WhatsApp.

## Next Action

Build Phase 12A first, then Phase 12B. Do not start UI work until the backend event shape and manual Supabase table are in place.
