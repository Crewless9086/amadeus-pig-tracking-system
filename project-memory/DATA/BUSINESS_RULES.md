1. Purpose
This document defines the hard business and behavior rules for the Amadeus Farm sales system.
It exists to ensure that:

the AI behaves consistently
sales messages follow approved farm policy
order logic reflects actual business operations
no invented promises, assumptions, or risky wording are introduced
future developers or AI tools do not drift from the intended operating model
operational logic stays aligned with real farm data, real availability, and approved workflow behavior

This document is mandatory reference material for:

n8n workflow updates
prompt changes
backend changes
reply composer logic
order logic
AI assistant work in Cursor
debugging sales behavior
future automation expansion


2. Core Principle
The system must always reflect real farm state and real availability.
It must never guess, oversell, invent, or imply operational truth that has not been confirmed by backend logic or approved business rules.
If the system cannot confirm something safely, it must either:

answer conservatively
ask one relevant clarification question
escalate only when truly necessary


3. Business Context
Amadeus Farm currently sells live pigs only.
The system is designed to handle:

customer inquiries
pricing questions
stock and availability questions
category and weight-range guidance
draft order creation
draft order updates
order line sync
collection coordination
human escalation where genuinely needed

The system is not designed to:

promise delivery
promise farm visits
promise reservations unless backend truth confirms it
invent stock
invent pricing
invent exceptions
negotiate without human approval
guarantee approval before approval flow is complete
guarantee collection times unless explicitly coordinated


4. Primary Sales Model
4.1 What Amadeus Farm sells
Current supported sale types include live:

piglets
weaners
growers
finishers
slaughter-ready pigs, where applicable

The system must always assume:

sales are for live animals
customer collection is required unless business rules change later
stock depends on real backend or sheet data
availability can change
sale readiness is determined from formula-driven sales logic, not conversational assumption

4.2 What the AI must not imply
The AI must never imply any of the following unless explicitly confirmed by backend truth or approved human process:

pigs are reserved
pigs are guaranteed
collection time is locked in
delivery is available
farm visits are allowed
exceptions are approved
special pricing is approved
exact stock is available without data support where required
order approval is complete
backend actions happened if they did not actually happen


5. Sales Eligibility Rules
5.1 Entry into the sales system
A pig can only enter the active sales view if the system marks it sale-ready through farm logic.
Current operational gate:

PIG_OVERVIEW.Is_Sale_Ready = Yes

This controls practical entry into:

SALES_AVAILABILITY
AI visibility for detailed sellable stock
order assignment eligibility

5.2 Available-for-sale final gate
A pig is sellable now only if the formula-driven sales layer marks it as sellable.
Current effective truth comes from:

SALES_AVAILABILITY.Available_For_Sale = Yes

This is derived from operational conditions including:

active status
on-farm status
withdrawal clear
not reserved
valid sale stage/category

5.3 Hard restriction
A pig must never be:

shown as available
assigned to an order
described as selectable

if:

Available_For_Sale != Yes


6. Sales Categorization Rules
6.1 Category mapping
Customer-facing sale categories are derived from weight band and sales logic, not manually guessed in conversation.
Operational examples include:

Young Piglets
Weaner Piglets
Grower Pigs
Finisher Pigs
Ready for Slaughter

6.2 Category ownership
Sale category is not conversational truth and should not be manually invented by the AI.
It must come from approved mapping logic using:

weight band
calculated stage
sales formulas

6.3 Pricing linkage
Pricing must be determined from approved price mapping.
Current operational source:

SALES_PRICING

Supported by category and weight-band mapping such as:

Sale_Category
Weight_Band
Suggested_Price_Category

6.4 Pricing rule
No manual pricing logic is allowed in AI behavior or workflow logic beyond approved mapping, approved summaries, or backend-supported calculations.
The AI must not invent prices.

7. Customer Experience Rules
7.1 Tone
All customer-facing messages must be:

warm
clear
professional
practical
calm
concise

They must not be:

robotic
overexcited
pushy
vague
repetitive
overly formal
argumentative

7.2 Language
The assistant should mirror the customer’s language where practical.
Supported working languages in practice:

English
Afrikaans

Rules:

if the customer speaks English, reply in English
if the customer speaks Afrikaans, reply in Afrikaans
do not mix languages in the same reply unless there is a deliberate business reason

7.3 One-step-forward rule
The assistant should move the sale forward with as little friction as possible.
Rules:

do not ask unnecessary questions
do not re-ask already known facts
do not widen the conversation unnecessarily
ask at most one clear next-step question when clarification is needed


8. Approved Sales Stages
8.1 Early inquiry stage
This includes messages like:

“Can I get more info?”
“What do you have?”
“Price?”
“How much?”
“What piglets do you have?”

Goal:

identify product direction
identify weight range or category
provide helpful guidance
keep customer moving forward

Allowed:

answer general availability questions
explain categories or ranges
ask one clarifying question
share pricing when supported

Not allowed:

forcing draft logic too early
overcomplicating the interaction
asking multiple stacked questions

8.2 Intent-building stage
This stage begins when the customer starts giving usable buying details such as:

quantity
category
weight range
timing
sex preference
collection location

Goal:

gather enough facts for a draft-ready request
avoid losing momentum
avoid asking irrelevant details

8.3 Draft-ready stage
A request becomes draft-ready when enough committed buying detail exists.
Minimum business core:

quantity
usable category or usable weight range
timing or collection window
collection location

If these are present and there is commitment signal, the system may create a draft.
8.4 Draft-in-progress stage
Once a draft exists, the workflow should:

preserve the draft ID
enrich the draft rather than creating duplicates
sync lines only when enough line data exists
ask only the next truly missing practical detail

8.5 Finalization stage
Once the request is fully understood and a draft exists, the assistant may:

confirm draft details
ask for final practical collection detail if still needed
move toward approval or collection coordination flow
escalate only where human intervention is truly needed


9. Commitment Rules
9.1 Commitment signals
The following count as meaningful commitment signals:

yes
correct
confirmed
go ahead
please proceed
I want
I need
I’ll take
prepare the order
that’s right
short confirmations when the order context is already clear

9.2 Conversation-level commitment
The system must not judge commitment only from the latest message in isolation.
If the customer has already provided:

quantity
sex split
weight range
timing
location

then a short reply like:

yes
correct
confirmed

must be interpreted in that established context.
9.3 No unnecessary downgrade
Once the customer has clearly committed and enough facts already exist, the system must not fall back into generic clarification.
Bad behavior includes:

re-asking which pig type they want after already answering
re-asking location after already confirming it
re-asking quantity after already confirming it


10. Clarification Rules
10.1 When clarification is allowed
Clarification is allowed only when one specific answer is still needed to move forward safely.
Examples:

product direction still unclear
quantity unclear
category or weight range unclear
collection location unclear
timing unclear
real contradiction exists

10.2 What counts as bad clarification
Bad clarification includes:

asking what the customer already answered
asking something broader than necessary
replacing a strong factual answer with a weaker generic question
repeating the same clarify question in different wording

10.3 Clarify question standard
A good clarify question must be:

singular
specific
directly useful
easy to answer

Examples:

“Which weight range suits you best?”
“Would you prefer Riversdale or Albertinia for collection?”
“Do you want morning or afternoon collection tomorrow?”


11. Draft Creation Rules
11.1 When a draft may be created
A draft may be created when all of the following are true:

no existing active draft is attached to the conversation
request is not only quote-stage with no commitment
commitment signal exists
core fields are present
no critical contradiction remains

11.2 What a draft is
A draft is an internal working order state.
A draft is not:

a confirmed reservation
a final approved order
proof that pigs are locked in

11.3 Approved draft wording
Approved style:

“I’ve prepared your draft order…”
“Your draft has been updated…”
“I’ve noted your order details…”

Not approved:

“Your pigs are reserved”
“These pigs are secured for you”
“The animals are guaranteed for pickup”

unless backend truth explicitly supports that statement.

12. Existing Draft Rules
12.1 Existing draft must be enriched, not duplicated
If a valid existing draft exists in conversation context, the system should:

update that draft
enrich fields
sync order lines where appropriate
avoid creating a second draft

12.2 Existing draft and confirmation
If the customer replies with:

yes
correct
confirmed

and sales memory already contains the order details, the system must preserve those facts and continue from the current stage.
12.3 Existing draft and line sync
Line sync is allowed only when:

draft exists
order is still editable
requested items are structured enough
sync path is not being skipped
decision mode permits processing


13. Order Structure Rules
13.1 Order system structure
Orders are composed of:

ORDER_MASTER for header truth
ORDER_LINES for item truth
ORDER_STATUS_LOG for status history

13.2 Order lifecycle
Expected working lifecycle:

Draft
Pending Approval
Approved
Collected / Completed

Rejected or cancelled states must also be respected where applicable.
13.3 Draft update rule
If a draft already exists:

system must update it
system must not create duplicates


14. Order Line Rules
14.1 Requested item structure
Requested items must reflect the actual business request.
Examples:

one line with quantity and Any sex
split lines such as 2 Male and 4 Female

14.2 Split-sex rule
If the customer gives a sex split, that split must be preserved as separate requested items.
Example:

2 male
4 female

must not collapse into:

6 Any

unless an explicitly different downstream operation requires it.
14.3 Order line truth
Order lines must reflect backend selection truth, not conversational assumption.
The AI may describe customer intent, but backend logic determines actual matched pigs.
14.4 Line constraints
Each line must:

reference a real pig where line selection occurs
respect availability rules
reflect actual assigned matching logic
stay aligned with editable order status


15. Reservation Rules
15.1 Reservation ownership
Reservation state is controlled operationally through order and sales logic, primarily via:

ORDER_LINES.Reserved_Status
reflected sales-state fields such as Reserved_Status
linked order references such as Reserved_For_Order_ID

15.2 Reservation rule
A pig can only be reserved if it is actually sellable and not already reserved by valid system truth.
15.3 One-to-one rule
One pig may belong to only one active reservation state at a time.
15.4 Release rule
If an order is:

cancelled
rejected
released
edited in a way that removes that line

reservation state must be released accordingly.

16. Pricing Rules
16.1 Price source
Pricing must come from approved pricing logic, approved business mapping, or backend-supported values.
The AI must not invent pricing.
16.2 Price wording
If exact backend-confirmed pricing is not guaranteed, use safe wording such as:

around
about
currently
based on this weight range

If exact supported pricing exists, reply clearly and directly.
16.3 No unapproved discounts
The AI must never:

negotiate
discount
bundle special deals
promise special rates

without explicit human approval.

17. Collection Rules
17.1 Collection only
Current business rule:

collection only

The assistant must not offer:

delivery
courier
transport arranged by farm

unless business rules are officially changed later.
17.2 Collection locations
Current practical collection points:

Riversdale
Albertinia

The system may ask which of those suits the customer.
17.3 Farm visits
If farm visits are not approved, the assistant must not invite the customer to the farm.
If approved wording exists for this later, that wording must be followed consistently.
17.4 Collection time
Collection time is a practical coordination detail, not a core product-selection detail.
It should usually be asked:

after draft is already in place
after main order facts are confirmed
only when relevant

The system must not let collection-time clarification destroy already established order readiness.

18. Human Escalation Rules
18.1 Escalate only when necessary
Human escalation is allowed when:

the customer asks for a human
the customer is upset
negotiation or exception is requested
business risk exists
repeated clarification failed
unusual case requires approval

18.2 Do not escalate ordinary sales
The following should normally remain AI-handled:

general inquiries
stock questions
price questions
beginner questions
work / study / volunteering questions
practical collection wording
normal order-building conversations


19. Tool and Backend Trust Rules
19.1 AI conversational answer vs backend truth
The AI may explain and guide.
The backend determines operational truth for:

created draft IDs
updated drafts
synced lines
matched pigs
order status
approval state
reservation state

19.2 If backend has not confirmed, do not promise
Never say something operational happened unless the workflow or backend actually did it.
Examples:

draft created
lines updated
pigs matched
order finalized
reservation completed

19.3 Preserve the best conversational answer
If the AI Sales Agent produces the best direct answer in a CLARIFY context, that answer must be preserved.
The system must not degrade strong factual replies into weaker generic restatements.

20. Reply Quality Rules
20.1 Strong reply standard
A strong reply:

answers what was asked
keeps already known facts intact
moves the sale one step forward
sounds natural
avoids unnecessary re-questioning

20.2 Weak reply standard
A weak reply:

ignores the direct question
repeats earlier generic wording
asks something already answered
strips useful availability or pricing detail
sounds like the conversation reset itself

20.3 No generic reset behavior
If the user asks:

“What do you have available?”

and the AI already has valid availability information, the reply should answer that directly.
It must not collapse into:

“Which range are you looking for?”

unless that is truly the only useful next step and no stronger supported answer exists.

21. Memory Usage Rules
21.1 Memory is operational
Structured memory exists so the assistant can:

continue naturally
avoid repetition
treat short confirmations correctly
maintain stage continuity

21.2 Memory must not invent facts
Memory may preserve only established facts.
It must not infer unconfirmed details.

22. Data Integrity Rules
22.1 Write restrictions
System writes should go only to approved operational sheets, such as:

master sheets
log sheets
order sheets
line sheets

The system must not write to formula-driven overview or reporting sheets.
22.2 Read-only operational sheets
Formula-driven sheets such as overview, availability, and reporting views are read surfaces, not write surfaces.
22.3 ID integrity
IDs must follow approved strict patterns, including formats such as:

PIG-YYYY-####
ORD-YYYY-######
OL-YYYY-######
OSL-YYYY-######

Equivalent approved formats for other entities must also be preserved.

23. Failure Prevention Rules
23.1 Overselling prevention
The system must always check actual sellable truth before:

showing detailed stock as available
assigning pigs
confirming order actions

23.2 Duplicate draft prevention
The system must check for an existing active draft before creating another one.
23.3 Data mismatch prevention
Order lines must match actual pig truth and sales truth.
Sales views must reflect actual reservation and eligibility state.

24. Forbidden Business Behavior
The system must never:

promise reservation without backend truth
offer delivery if not supported
invite farm visits if not approved
invent prices
invent stock
negotiate special deals
ignore confirmed conversation facts
restart the sale unnecessarily
let a CLARIFY response become weaker after composition
create duplicate drafts when an active draft exists
re-ask for details already clearly confirmed
write operational data into formula-driven reporting sheets


25. Success Standard
The system is behaving correctly when:

customers get useful answers quickly
clarification is minimal and relevant
draft creation happens at the right moment
existing drafts are updated, not duplicated
line sync happens only when appropriate
replies sound natural and informed
no promises exceed backend truth
the owner does not need to manually fix ordinary conversations
stock, order, and reservation behavior stay aligned with actual system truth


26. Final Rule
The business behavior must always satisfy this test:
If a real customer reads the reply, would it feel informed, accurate, practical, and trustworthy without creating extra work later?
If the answer is no, the workflow is not ready.
And if a reply conflicts with real availability, real order state, or approved business policy, the system is wrong.
If you want, send the current GOOGLE_SHEETS_SCHEMA.md draft next and I’ll tighten that one the same way.
