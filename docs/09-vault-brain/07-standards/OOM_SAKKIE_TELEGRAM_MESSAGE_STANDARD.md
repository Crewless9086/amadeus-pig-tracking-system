# Oom Sakkie Telegram Message Standard

Status: owner-approved interface standard

Purpose: make Oom Sakkie's Telegram communication clear, human, noticeable, concise, and useful without notification clutter or technical walls of text.

## Core experience

Telegram is an operating interface for Charl and later authorized family members. It must feel like a practical farm manager communicating, not a database, audit log, terminal, or developer console.

Every message must answer quickly:

1. What is this about?
2. What is the current state?
3. What happened or is planned?
4. Does the family need to do anything?

The LLM-assisted owner composer must translate typed specialist evidence into this structure. It may select wording, layout, language and emphasis, but it may not change facts, authority, decisions or safety boundaries. Raw deterministic summaries are evidence inputs, not owner-facing copy.

Routine technical identities, hashes, deployment details, execution IDs, internal modes, stack traces, raw JSON, and authority flags belong in durable backend evidence, not ordinary family messages. Show them only in a concise diagnostic message when they materially help resolve a failure.

## Visual hierarchy

Use Telegram HTML formatting with dynamic text safely escaped.

Routine messages should use:

- one semantic emoji;
- one short bold uppercase title;
- blank lines between sections;
- bold labels or important values;
- short bullets rather than one dense paragraph;
- one clear action or next update at the end;
- plain family language.

Capitals are for the short title or an urgent state, not entire paragraphs. Bold is for scannability, not decoration.

Preferred pattern:

```html
💧 <b>IRRIGATION STARTING</b>

<b>Camp:</b> B Camp
<b>Planned:</b> 20 minutes
<b>Status:</b> Starting now

I will confirm when it has stopped.
```

Do not send:

- a wall of text;
- five repeated headings;
- raw internal terminology without explanation;
- several approval buttons where no decision is required;
- repeated facts already visible in the current card;
- a silent edit when Charl needs to notice a live operational transition.
- raw specialist summaries joined into one long paragraph;
- duplicated reasons, repeated safety disclaimers or internal reassessment identifiers;
- stale questions that authoritative lifecycle evidence has already answered or superseded.

## Semantic and lifecycle requirements

- Natural questions and requests must remain distinct from physical observations, corrections, confirmations and commands.
- A plan question must reach the relevant read-only specialist plan; it must never be consumed as new farm evidence.
- A valid LLM semantic decision may not be overridden by a legacy keyword, regex, menu or sheet-era classifier.
- Short replies such as `Animals`, `Diere`, `Irrigation` or `Besproeiing` continue the preceding clarification when context supports it.
- English and Afrikaans receive the same evidence quality, lifecycle behavior and visual structure.
- Completed, superseded or answered lifecycle work must disappear from current briefs while remaining in durable history.
- Unchanged scheduled reassessment remains silent. A material decision or owner-action change creates one visible concise notification and updates the durable current card.

## Semantic emoji set

Use a small consistent set:

- 💧 water, tanks, pumps, irrigation;
- 🐷 herd, sow, litter, animal observation;
- 💬 customer or SAM sales activity;
- 📣 BEACON marketing or publication;
- ⚡ power, solar, battery, grid;
- ✅ completed or confirmed;
- ▶️ starting or active;
- ⏸️ hold or waiting;
- ⛔ stopped, contained, or unsafe to continue;
- ⚠️ attention or genuine exception;
- ❓ one owner fact or decision required.

Avoid decorative emoji that does not communicate state.

## Message types

### Daily management card

Send one new consolidated card when the day's plan or management round begins. It should notify once and remain the detailed current summary. Edit it in place for low-attention plan changes.

Maximum ordinary content:

- three current actions;
- one family question;
- one next reassessment;
- no completed or duplicated housekeeping.

### Live operational notification

Edits generally do not notify or move an old message to the bottom of Telegram. Therefore, send a new buttonless message for a live event Charl must notice:

- hardware or irrigation starting;
- hardware or irrigation completed;
- stopped early or failed;
- manual action required;
- meaningful customer/marketing/farm outcome where timely awareness matters.

For a normal hardware run:

1. send one new `Starting` notification;
2. update the daily card silently;
3. send one new `Completed` or `Stopped` notification;
4. after provider-confirmed completion, optionally delete the superseded temporary `Starting` notification while preserving durable backend evidence and the daily card.

Do not delete a protected-decision card, unresolved exception, or the only owner-visible evidence of an ambiguous outcome. Deletion is presentation cleanup, never audit deletion.

### Protected decision card

Send a new message with buttons only when Charl must make a genuine protected decision. The title must state the decision, the body must give the smallest sufficient evidence, and buttons must be exact, mutually clear, stale-safe, and removed or disabled after resolution.

### Question

Ask at most one consolidated owner question at a time where practical. Use natural wording, explain why it matters, and accept partial natural replies without forcing a form.

### Systemic exception

Send one stable buttonless alert stating:

- what is unavailable;
- what work is affected;
- what remains safe/working;
- whether Charl must cover anything manually;
- next automatic reassessment.

Deduplicate unchanged alerts.

## Domain examples

### Irrigation starting

```html
💧 <b>B CAMP STARTING</b>

<b>Runtime:</b> 120 minutes
<b>Weather:</b> Dry
<b>Power:</b> Supported

I will confirm when B Camp has stopped.
```

### Irrigation completed

```html
✅ <b>B CAMP COMPLETED</b>

<b>Runtime:</b> 120 minutes
<b>C Camp:</b> Remained off
<b>Next:</b> Recalculate the weekly irrigation plan
```

### Herd preview

```html
🐷 <b>SOW CHECK PREVIEW</b>

• <b>Baby:</b> Inconclusive
• <b>Mona:</b> Assumed Pregnant
• <b>Mysikind:</b> Assumed Pregnant

❓ Confirm these three visual observations?
```

### Marketing result

```html
📣 <b>FACEBOOK POST PUBLISHED</b>

<b>Post:</b> Bella and her 13 piglets
<b>Spend:</b> R0

I will report the 24-hour results tomorrow.
```

## Delivery and verification

- Use `parse_mode = HTML` and escape every dynamic value before rendering.
- Provider acceptance does not prove that a hardware action physically occurred.
- A new message must have an authoritative Telegram message identity before it is represented as delivered.
- Edits require the exact existing message identity and must fail closed on stale or mismatched cards.
- Retrying an ambiguous send is prohibited until authoritative reconciliation proves whether the message exists.
- Formatting failure must not remove or weaken the underlying safety/authority decision.

## Acceptance

The interface is successful when Charl can scan a message once, understand the domain and state, know whether action is required, receive a notification for live events, and avoid scrolling through duplicate technical cards. Browser/Telegram rendering tests must cover HTML escaping, bold headings, blank lines, emoji, button behavior, in-place edits, new-message notification events, cleanup, replay, stale chronology, and ambiguous provider outcomes.
