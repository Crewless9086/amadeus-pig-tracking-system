# Meat Launch Campaign Packet

## Status

- Mode: `beacon_meat_launch_campaign_draft_only`
- Agent: Beacon
- Campaign: First pork freezer preorder pilot
- Status: draft_only_owner_review_required
- Next gate: `owner_reviews_campaign_before_any_public_or_customer_send`

This packet is draft-only. It does not post publicly, send customer messages, create quotes or invoices, create orders, reserve carcasses, change stock, book slaughter, book a butcher slot, or confirm payments.

## Campaign Goal

Generate controlled inbound demand for Sam Meat without overpromising stock, price, timing, or delivery.

## Campaign Angles

### Controlled Freezer Preorder

Position Amadeus Farm pork as a limited, pre-booked freezer run for households that want to plan ahead instead of buying anonymous supermarket meat.

- Best channel: WhatsApp status and Facebook
- Sam handoff: Ask whether the buyer wants half carcass, full carcass, or cut-set guidance.

### Set A Family Freezer Pack

Explain Set A as the practical family freezer option while keeping price, timing, and final packed weight for the farm confirmation step.

- Best channel: Facebook and direct known buyers
- Sam handoff: Answer what Set A includes, then collect town, delivery/collection, timing, and payment preference.

### Farm To Freezer Story

Show the journey from farm planning to packed pork, with limited availability and pre-booking as part of the story rather than a pressure tactic.

- Best channel: Instagram story and WhatsApp status
- Sam handoff: Invite replies from people who want Sam to check the best fit for their freezer, budget, or target kg.

### Local Route Pilot

Keep the first run focused around Riversdale and nearby routes, so delivery and collection promises stay controlled while demand is measured.

- Best channel: WhatsApp status and known-buyer share
- Sam handoff: Capture address or shared location when delivery is requested.

## Channel Drafts

### WhatsApp Status 1

- Channel: WhatsApp status
- Intent: Soft interest check

```text
Amadeus Farm is preparing a limited pork freezer preorder run for Riversdale and nearby routes. Half carcass Set A and full carcass options are pre-booked only; price, timing, and final packed weight are confirmed before booking. Reply if you want Sam to note your interest.
```

### WhatsApp Status 2

- Channel: WhatsApp status
- Intent: Explain the offer simply

```text
Limited pork freezer preorders are opening. This is not ready-shelf stock; it is pre-booked farm pork, packed after processing, with final weight confirmed once known. Ask Sam about half carcass Set A, full carcass, delivery, or collection.
```

### WhatsApp Channel Draft

- Channel: WhatsApp channel or broadcast draft
- Intent: First owner-approved announcement

```text
We are testing a limited Amadeus Farm pork freezer preorder run. The focus is half carcass Set A and full carcass pork freezer options. Orders are pre-booked, and the farm confirms price, available timing, deposit steps, and final packed weight before anything is booked. Message Sam if you want to be added to the review list.
```

### Facebook Post Draft

- Channel: Facebook
- Intent: Public demand generation

```text
Amadeus Farm is preparing a limited pork freezer preorder pilot for Riversdale and nearby routes. We are starting small so that every booking can be handled properly. The first focus is half carcass Set A and full carcass pork freezer options. This is pre-booked farm pork, not unlimited shop stock: price, timing, delivery/collection, deposit steps, and final packed weight are confirmed before the booking is accepted. If you want pork for your freezer, send us a message and Sam will collect the details.
```

### Instagram Caption Draft

- Channel: Instagram
- Intent: Story-led launch caption

```text
A small farm run, planned properly. Amadeus Farm is opening limited pork freezer preorders, starting with half carcass Set A and full carcass interest. Every order is pre-booked, with price, timing, deposit steps, and final packed weight confirmed before booking. Message Sam if you want to join the first review list.
```

### Customer Education Draft

- Channel: Facebook/WhatsApp explainer
- Intent: Reduce confusion about final weight

```text
How the freezer preorder works: availability is limited, so interest is captured first. The farm then confirms price/kg, timing, delivery or collection, and deposit steps. Packed weight is estimated early, but the final amount is only confirmed after processing, because real carcass and cut yield can vary.
```

## Story Updates

### Story Slide 1

```text
Limited pork freezer preorders are opening soon from Amadeus Farm. Pre-booked only, starting with the first controlled pilot around Riversdale and nearby routes.
```

### Story Slide 2

```text
Half carcass Set A is for families who want practical freezer pork. Limited availability, pre-booked, with final packed weight confirmed after processing.
```

### Story Slide 3

```text
Sam will collect the details: half or full carcass, town, delivery or collection, timing, payment preference, and any budget or freezer-size target. Limited pre-booked run only.
```

### Story Slide 4

```text
Want to join the limited preorder review list? Reply and Sam will capture your interest. No booking is final until the farm confirms price, timing, and deposit steps.
```

## Owner Review Checklist

- Choose which channel goes first: WhatsApp status, WhatsApp channel, Facebook, Instagram, or direct known buyers.
- Confirm whether public copy may mention Riversdale delivery/collection or should keep the area broad.
- Confirm whether public copy may mention a price/kg or should keep price on request until the pilot is proven.
- Choose the approved farm photo or video set before any public post is prepared.
- Confirm the first pilot target: how many halves/full carcasses should Sam try to fill before pausing demand.
- Confirm who handles delivery-day customer updates for the first pilot run.

## Authority Boundary

- `books_butcher`: `false`
- `books_slaughter`: `false`
- `calls_chatwoot`: `false`
- `calls_meta`: `false`
- `calls_n8n`: `false`
- `changes_stock`: `false`
- `confirms_payment`: `false`
- `creates_invoice`: `false`
- `creates_order`: `false`
- `creates_quote`: `false`
- `customer_public_output_enabled`: `false`
- `draft_only`: `true`
- `posts_publicly`: `false`
- `reserves_carcass`: `false`
- `sends_customer_message`: `false`
- `writes_farm_data`: `false`

## Forbidden Actions

- `no_public_post`
- `no_customer_dm`
- `no_chatwoot_send`
- `no_whatsapp_template`
- `no_meta_api_call`
- `no_order_create`
- `no_quote_invoice_create`
- `no_stock_reservation`
- `no_price_promise`
- `no_timing_promise`
- `no_slaughter_booking`
- `no_butcher_booking`
- `no_bank_confirmation`

## Validation

- Success: `true`
- Checked drafts: `10`
