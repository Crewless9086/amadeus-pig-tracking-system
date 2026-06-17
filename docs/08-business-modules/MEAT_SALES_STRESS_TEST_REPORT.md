# Sam Meat Sales Stress-Test Run

- Scenarios: 40
- Passed: 40
- Failed: 0
- Known improvement opportunities: 6

## Category Coverage

- `assisted_slaughter`: 1
- `authority_pressure`: 1
- `budget`: 1
- `butcher_match`: 2
- `change_mind`: 1
- `channel`: 3
- `custom_cut`: 1
- `cut_set_question`: 3
- `delivery`: 2
- `document_request`: 1
- `followup`: 1
- `frustration`: 1
- `full_carcass`: 1
- `happy_path`: 2
- `ignore`: 2
- `language`: 1
- `location_pin`: 2
- `missing_fact`: 4
- `payment`: 3
- `price_objection`: 1
- `test_cleanup`: 1
- `typos`: 1
- `vague_interest`: 1
- `whatsapp_window`: 1
- `wrong_product`: 2

## Recommendations

- P2: Deterministic parser does not yet understand Afrikaans meat terms without LLM help. Scenarios: afrikaans_short.
- P2: Heavy typo recovery currently depends on LLM extraction. Scenarios: typo_heavy.
- P2: Plain-text Google Maps links are not yet parsed into coordinates without Chatwoot location metadata. Scenarios: google_maps_url.
- P3: Runtime currently treats inbound messages as an open service window; closed-window handling is fulfilment/journey-side. Scenarios: closed_window.
- P3: Sam does not yet add a softer frustration-specific acknowledgement. Scenarios: angry_price.
- P3: Sam does not yet explicitly reject non-pork products; it redirects into pork options. Scenarios: wrong_product_beef.

## Failures

- No launch-blocking stress assertions failed.
