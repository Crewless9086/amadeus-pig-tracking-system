# Amadeus Private Transfers

Status: planned, not built. Owner concept captured from the 2026-07-01 family proposal and converted into Vault structure for review.

## Executive Direction

Start with the OMODA as a low-risk proof vehicle. Do not buy another vehicle yet.

First goal: prove the car can generate at least `R13,000` net contribution per month after operating costs. If it can do that consistently, the vehicle stops being only a household cost and becomes a farm-supporting asset.

This is not a taxi business. It is a premium, pre-booked, private-driver service for the right clients.

## Target Clients

- holiday-home owners;
- older residents;
- families arranging transport for parents;
- business travellers;
- tourists;
- guest farms;
- accommodation partners;
- estate agents;
- doctors, pharmacies, and appointment-based local partners.

## Market Positioning

Use premium wording:

- private transfer;
- private local driver;
- door-to-door;
- pre-booked;
- premium vehicle;
- flight-monitored airport collection;
- family-run Garden Route service.

Avoid cheap positioning:

- taxi;
- budget;
- cheap lift;
- shuttle bus;
- Uber alternative.

The opening is a premium, family-run, WhatsApp-first private transfer service with a clean luxury SUV, human-level service, and simple booking.

## Revenue Lanes

| Lane | Service | Description | Priority |
| --- | --- | --- | --- |
| 1 | Premium Airport Transfers | George Airport, Still Bay, Riversdale, Albertinia, Mossel Bay, Knysna, Plett, and special long-distance quotes. | High-value and strong brand signal. |
| 2 | Private Local Driver | Appointments, shopping, pharmacy, errands, senior-friendly door-to-door transport. | Recurring weekday income and lower seasonality. |
| 3 | Bespoke Private Driver / Day Hire | Half-day or full-day driver for tours, weddings, lunches, shopping days, medical days, and special events. | Premium add-on once trust grows. |
| 4 | Courier / Deliveries | Only if it fits the route or a future farm vehicle model. | Later only; protect OMODA premium positioning. |

## Launch Price Menu

### Premium Airport Transfers

| Route | Launch rate | Internal note |
| --- | ---: | --- |
| George Airport - Albertinia/Farm Area | R2,500 | Good core airport route. |
| George Airport - Riversdale | R2,700 | Good core airport route. |
| George Airport - Still Bay/Jongensfontein | R2,900 | Important premium holiday market. |
| George Airport - Mossel Bay | R2,600+ special quote | Accept only when profitable or linked to another route. |
| George Airport - Knysna | R4,500 | Good high-ticket route if price is protected. |
| George Airport - Plettenberg Bay | R5,500 | Good high-ticket route, but more time and kilometres. |
| Cape Town / Port Elizabeth / Other | Quote only | Only if price is very strong. |

### Private Local Driver

| Service | Launch rate | Rule |
| --- | ---: | --- |
| Drop-and-go | From R950 | Avoid cheap-lift positioning. |
| Appointment Return | From R1,550 | Strong product for older clients and families. |
| Shopping Companion | From R1,950 | Best local margin if sold as care and convenience. |
| Half-day Private Driver | From R4,500 | Up to 4 hours; quote by route. |
| Full-day Private Driver | From R7,500 | Up to 8 hours; premium visitors/tours only. |

### Extras

| Item | Planning rate | Rule |
| --- | ---: | --- |
| After-hours surcharge | +R500 | Before 06:00, after 20:00, or late-night flight work. |
| Public holiday surcharge | +R600 | Protect family time. |
| Extra waiting | R300/hour | Charged after included waiting period. |
| Extra stop | From R350 | Pharmacy, bank, second pickup, shop stop, etc. |
| Cleaning fee | R500+ | Mess, spills, sand, pet hair, or damage. |
| Deposit | 50% recommended | Required for new clients and all airport/long-distance bookings. |

Non-negotiable pricing rule: never wait for free. Waiting is one of the most valuable parts of the private-driver service and must be packaged, time-limited, and charged.

## Financial Planning Assumptions

| Assumption | Value |
| --- | ---: |
| OMODA C9 planning fuel consumption | 8.2L/100km |
| July 2026 coastal 95 petrol planning price | R25.23/L |
| Fuel-only planning cost | R2.07/km |
| Conservative all-in planning reserve | R6.00/km |
| Future driver cost planning | R120/hour |
| First monthly contribution target | R13,000 |

Profit in the family proposal means contribution after vehicle operating cost, before tax and before paying a separate driver.

## Target Scenarios

| Target | Practical meaning |
| --- | --- |
| R13,000/month | The OMODA materially contributes to its own cost. Planning mix: about 8 quality bookings, depending on route mix. |
| R20,000/month | Proper side-business that can support feed, farm expenses, debt repayment, or setup costs. |
| R30,000/month | Strategically important business, but still not automatic approval to buy another vehicle. |

Vehicle decision rule:

- Stage 1: OMODA only. Get first 10 paid bookings and track every trip.
- Stage 2: R13,000/month profit. Continue with no new debt.
- Stage 3: R20,000/month profit. Support farm expenses and marketing, still avoid new debt.
- Stage 4: R30,000/month profit for 3-6 months. Consider part-time driver or stronger automation, not necessarily a vehicle.
- Stage 5: R40,000-R50,000/month profit for 6-12 months. Only then consider Maxus/dedicated vehicle.

## Brand And Channel Setup

- Brand: Amadeus Private Transfers.
- WhatsApp: separate new number from day one.
- Website: one-page premium landing page with OMODA photos, routes, service promises, WhatsApp quote button, reviews, and partner enquiry form.
- Facebook/Instagram: separate pages.
- Google Business Profile: essential.
- Partners: accommodation owners/managers, estate agents, holiday rentals, guest farms, doctors, pharmacies.
- Reviews: request immediately after happy trips.

## FRED Build Requirements

FRED is the dedicated transfer sales and booking agent. FRED should not be mixed into SAM.

Required behaviour:

- collect name, phone, pickup, drop-off, date, time, passengers, luggage, flight number, waiting time, and special needs;
- price only from an approved `pricing_rules` source;
- check shared calendar, farm events, driver availability, vehicle availability, and buffer time;
- create pending bookings for human approval;
- show pending booking cards with Approve, Decline, Edit, Message Client, and Mark Deposit Paid actions;
- track deposit requested, deposit paid, paid in full, unpaid, and refunded;
- send confirmation, driver prep reminders, pickup reminders, and post-trip review requests only after approved gates exist.

## Launch Plan

| Timing | Action |
| --- | --- |
| Week 1 | Legal and insurance check before taking paying passengers. |
| Week 1 | Brand setup: WhatsApp Business profile, Google Business Profile, one-page website, social pages. |
| Week 2 | Load service menu, pricing, rules, and scripts into FRED/manual booking workflow. |
| Week 2 | Contact 20 accommodation owners/managers, estate agents, guest farms, doctors/pharmacies, and holiday-rental contacts. |
| Month 1 | First 10 bookings. Track booking, real km, real time, fuel, client type, profit, and feedback. |
| Month 2 | Adjust weak route prices, remove low-margin work, keep high-margin appointment/shopping packages. |
| Month 3 | Connect FRED to booking dashboard/API workflow if enquiry flow exists. |

## Do Not Do

- Do not compete on cheap price.
- Do not accept unpaid bookings.
- Do not wait for free.
- Do not buy the Maxus early.
- Do not let FRED confirm alone.
- Do not mix farm WhatsApp and private transfer clients.

## Compliance Checklist

Before public launch:

- commercial passenger insurance confirmed in writing;
- public operating licence requirements checked;
- PrDP requirements checked;
- vehicle roadworthy/licensing clean;
- liability wording drafted;
- cancellation/refund wording drafted;
- tax record process ready;
- passenger privacy/data handling rule ready.

## Source References

- Owner-added family proposal in this Vault file, reviewed 2026-07-02.
- OMODA C9 planning fuel consumption source: `https://www.omoda.co.za/models/omoda-c9`
- July 2026 coastal petrol planning source: `https://businesstech.co.za/news/energy/864824/here-is-the-official-petrol-price-for-july-8/`
- Local market references in owner proposal: Smook Vervoerdienste, StillMovin, Woober, Garden Route Express Shuttle, Gecko Tours, U-Go.
- Compliance references in owner proposal: Western Cape public operating licence service page and South African Government PrDP guidance.
