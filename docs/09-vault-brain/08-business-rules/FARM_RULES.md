# Farm Rules

One pig should have one operational truth.

Farm lifecycle and animal records require approved backend paths and owner approval where needed.

## Farm Calendar Contract

- One farm-wide calendar combines owner-created reminders with read-only dates projected from canonical breeding, litter, medical, sales, fulfilment and weather sources.
- Manual calendar items require their own canonical record and may be edited only through the approved owner path. Projected source events remain read-only and link back to their canonical source.
- Calendar queries require a bounded date range and normalize source identity, date, status, priority and destination link. Created/updated timestamps and ordinary audit rows are not farm events.
- Missing or stale weather degrades to a neutral display; it does not hide otherwise valid farm events.
- Month view is the primary owner surface. Normal use must remain calm on desktop and mobile: at most three visible chips per day, a selected-day agenda, simple filters and no notification or source write-back authority inferred from the calendar.
