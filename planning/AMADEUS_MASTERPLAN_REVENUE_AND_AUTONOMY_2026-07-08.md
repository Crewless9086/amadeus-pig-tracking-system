# AMADEUS MASTERPLAN — Revenue First, Autonomy Second, Jarvis Third

**Date:** 2026-07-08
**Author:** Cursor deep-dive (full repo audit: income streams, agent teams, CHARLIE CORE, deployment, planning docs)
**Status:** Owner review — no code changed by this document
**Supersedes nothing** — this plan slots into the existing `docs/00-start-here/NEXT_STEPS.md` P0–P4 queue and does not contradict active gates.

---

## 0. Honest Confidence Statement (read this first)

You asked for a plan with 99% confidence and a 100% pass rate that the system will be autonomous and make money. **No honest engineer can promise that, and any plan that does is lying to you.** Here is what I *can* say with high confidence after auditing every layer of this repo:

| Claim | Confidence |
|---|---|
| The farm can generate meaningful revenue in July 2026 **with you and Anton in the loop**, using tools that already work | **~90%** |
| The system can reach **owner-approved semi-autonomous selling** (AI drafts, you tap approve) within 2–3 weeks | **~85%** |
| CHARLIE CORE can reliably build small missions overnight **after the emergency fixes** in Section 7 | **~80%** |
| Fully autonomous selling with zero human touch this month | **~15% — do not bet the farm on this** |

The single most important reframe: **this month, the system's job is to make YOU faster at selling, not to replace you.** Every day the 217 pigs eat feed, margin dies. The 39 sale-available pigs are cash sitting in pens. Automation that ships in August does not pay July's feed bill.

---

## 1. The Vision, Restated (so we build toward it, not around it)

The target hierarchy — agreed, and the architecture already anticipates it:

```
CHARL (Owner)
 └── CHARLIE — personal CEO / digital you. Voice + living UI. Sees everything. Only you.
      ├── CHARLIE CORE — agentic build/workflow engine. Self-learning. Does the heavy lifting.
      ├── AMADEUS (farm) — OOM SAKKIE, farm CEO → talks to Anton (voice + windows)
      │    ├── HERDMASTER — herd intelligence, alerts, allocation
      │    ├── SAM — sales CEO (live stock, meat, slaughter lanes)
      │    ├── BUTCHER — meat pipeline, carcass matching
      │    ├── LEDGER — money truth
      │    ├── ROOTLINE / GATEKEEPER / QUARTERMASTER — water, safety, feed
      │    └── FRED — transport (future)
      ├── BEACON — marketing department (own sub-agents, own dashboard)
      └── Future business modules
```

**What the audit found:** this hierarchy is already *documented* in `docs/09-vault-brain/01-identity/AGENT_ORGANOGRAM.md` and partially *built*. The vision is right. The sequencing has been wrong: doctrine and governance shells were built ahead of the money engine. This plan reverses that for 90 days.

---

## 2. Where We Actually Are — The Percentage Scorecard

### 2.1 Income streams (% to "customer pays, money arrives")

| Income stream | Readiness | Verdict |
|---|---|---|
| **Live pig sales** (weaner → slaughter-ready, via n8n 1.0 + orders backend) | **~60%** | Closest to cash. Conversation → draft → quote → approve → reserve all work. Payment confirmation is manual (by design, fine for now). |
| **Meat sales pilot** (SAM Meat, deposit-gated) | **~40% system / ~25% money** | Strongest new code (44/44 stress tests) but blocked on *operations*: WhatsApp templates, bank details, zero confirmed deposits, zero approved media. |
| **Slaughter/abattoir fallback** | **~35%** | Internal tool works. Use it to move 80kg+ animals off feed when direct sales lag. |
| **Breeding/replacement stock** | ~5% | Rules only. Not a July play. |
| **Beacon demand generation** | ~20% | Draft packets exist; Facebook posting correctly disabled; zero approved media. |
| **Custom cuts / FRED transport** | 0–5% | Not built. Ignore until Q4. |

### 2.2 Platform layers

| Layer | Readiness | Notes |
|---|---|---|
| Farm ops app (Flask, 40+ pages) | **~80%** | Mature, heavily tested. Wounds: bulk weight P0, slaughter↔exit desync. |
| Data layer (Supabase canonical, Sheets fallback) | **~90%** | GS-MIG complete through PR #39. 217 pigs, 1,190 weights, 26 orders imported. 9 weight conflicts quarantined awaiting your review. |
| Order lifecycle backend | **~75%** | Draft/lines/reserve/approve/complete solid. No in-system payment status API for live orders. |
| Pricing & availability truth | **~70% / ~40%** | Logic sound; **degraded until bulk weight P0 is fixed** because stale weights = wrong allocation. |
| n8n customer pipeline (Chatwoot → 1.0 → 1.2) | **~65%** | Live-verified through Phase 5.9. Known drift risks at order capture, split-item sync. |
| Deployment (Render + Supabase + n8n Cloud) | **~85%** | Stable. Auto-deploy from main. CI runs Oom Sakkie tests only — no CHARLIE CI. |

### 2.3 Agent teams (% toward their vision role)

| Agent | Today | Vision gap |
|---|---|---|
| **CHARLIE** | **65%** — mission queue, Telegram relay, `/charlie` cockpit | Not yet your voice-first life CEO; is a *build* orchestrator, not an *operations* overseer |
| **CHARLIE CORE** | **~55%** — real pipeline, real artifacts, but blocked its last overnight mission | Five concrete defects (Section 7) stand between it and reliable overnight throughput |
| **OOM SAKKIE** | **60%** — command kiosk, read-only farm intelligence, Telegram, STT voice input | No TTS/voice-out, no live specialist dispatch, no Anton-facing autonomy |
| **SAM** | **70%** — the most mature agent; meat + live-stock runtimes + n8n hub | Customer auto-send correctly gated; needs the owner-approved reply loop finished (already the active CODEX mission) |
| **BEACON** | **50%** — media library, draft campaigns, gated FB posting | No approved media, no sub-agents, no autonomous scheduling |
| **HERDMASTER** | **35%** — allocation + purpose review pages work | No alert engine (rules are a design pack), no agent runtime |
| **BUTCHER** | **40%** — match engine + fulfillment slots work | No booking automation |
| **LEDGER** | **25%** — Telegram `/ledger` advisory only | No SQL ledger, no money dashboard |
| ROOTLINE / GATEKEEPER / QUARTERMASTER / FRED | 45% / 20% / 5% / 0% | Data rails exist for Rootline; rest is doctrine |

### 2.4 Overall: **the empire is ~45% built, but the 45% is unevenly distributed.**
The governance/doctrine layer is at ~85% while the money-confirmation layer is at ~15%. That inversion is *the* strategic problem this plan fixes.

---

## 3. The Money Math (why the sequencing below is what it is)

From canonical Supabase data and the price book (`sales_pricing`, ex-VAT, EFT +15% VAT):

- **217 pigs on feed. 39 rows currently sale-available.** Every week of delay is feed cost across all 217.
- Price bands: Weaner R450–600 · Grower R800–1,800 · Finisher R2,200–2,700 · Slaughter-ready R2,800–3,000.
- **Illustrative July target:** selling ~30 of the 39 available at blended ~R1,200–1,800 ≈ **R36,000–R54,000**, plus a 1–2 carcass meat pilot per the pilot cap. Confirm bands are current before quoting — the price book was flagged for owner confirmation in `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md`.
- Meat margin is better per kg but has more launch gates. **Live sales move volume now; meat pilot proves the premium lane.**
- Pigs crossing 80kg+ that don't sell direct should go the abattoir/slaughter lane rather than eating margin — the internal tool for this works today.

**Rule for July: every pig either has a sales plan or a slaughter plan. No passengers.**

---

## 4. The Plan — Three Horizons

### Horizon R — REVENUE (Weeks 1–2) · human-led, system-assisted
### Horizon A — AUTONOMY (Weeks 2–6) · approve-only selling + CHARLIE CORE reliability
### Horizon V — VISION (Weeks 6–12+) · Jarvis UI, voice, departments

Each horizon below lists exact steps, what each improves, and the % it moves.

---

## 5. HORIZON R — Money This Month (Days 1–14)

> Goal: Rands in the bank within 14 days. Nothing in this horizon waits for new automation.

### R1. Restore stock truth (Days 1–2) — *the* prerequisite
- **What:** Finish the P0 one-button bulk weight flow (`p0-bulk-one-button-owner-flow` branch is active), clear the stuck batch (10 processing / 32 staged / 31 recorded), and review the 9 quarantined weight conflicts.
- **Why it makes money:** SAM and the availability pages quote from allocation-derived weights. Stale weights = quoting pigs that don't exist or missing sellable ones. **This single fix moves pricing/availability truth from ~40% → ~85%.**
- **Who:** One focused Cursor/Codex session + your live retest. This is already top of `NEXT_STEPS.md` P0.

### R2. Confirm the price book (Day 1, 30 minutes of your time)
- **What:** You confirm/adjust the R300–R3,000 bands in `/sales/sam-pricing` and the meat price book. Set them once, correctly.
- **Why:** Every quote, every SAM reply, every Beacon draft inherits these numbers. Wrong prices = margin leaks silently at scale.

### R3. Sell the 39 (Days 2–10) — human blitz with system assist
- **What:** You + Anton run a deliberate sales push on the 39 available pigs:
  1. Pull the list from `/sales-availability` (post-R1 it will be trustworthy).
  2. WhatsApp your existing buyer list directly (the repo's own launch-readiness doc recommends exactly this over public posting: known buyers first).
  3. Every enquiry flows through the existing pipeline: Chatwoot → n8n 1.0 → draft order → quote PDF → your approve → auto-reserve → collection + EFT/cash.
  4. Record payment on collection; complete order (pig exits update).
- **Why:** This is the only path that produces revenue in week one. The system does draft, quote, reserve, and paper-trail work — its actual current strength.
- **Anything ≥80kg with no buyer by Day 10 → slaughter lane** via `/sales/slaughter`.

### R4. Meat pilot: 1–2 carcasses, fully supervised (Days 3–14)
- **What:** Execute the existing pilot playbook: configure the 5 missing WhatsApp template env vars, put real bank details in the policy, pick 2–3 warm leads from the 31 in the system, you personally send the quotes, deposits confirmed **in bank** (not POP) before any slaughter, record deposit events, fulfil via the Butcher match engine.
- **Why:** Proves the premium lane end-to-end with real money, generating the evidence the system needs before any meat automation is trusted. Moves meat readiness ~40% → ~65%.
- **Hard rule (already doctrine):** no pig slaughtered for meat unless pre-sold with bank-confirmed deposit.

### R5. Close the payment-truth gap (Days 3–5, small build)
- **What:** One small mission: add a payment-status update path for live-pig orders (mirror of what slaughter transactions already have) + a "paid/unpaid" column on the orders page. Manual entry — you check the bank, you tap Paid.
- **Why:** Right now the system cannot even *record* that money arrived on a live order. This is the cheapest possible step toward Ledger truth and makes the daily summary meaningful. Moves "money arrives" visibility 0% → 70% with ~1 day of build.

### R6. Daily money brief (Days 5–7, small build)
- **What:** Extend the existing 16:00 n8n Daily Order Summary to include: Rands quoted, Rands approved, Rands collected, pigs reserved, pigs aging past 80kg without a plan. To your Telegram and Anton's.
- **Why:** You asked for a system that alerts the right person. This is that, on the money metric that matters, using rails that already run.

**Horizon R exit criteria:** ≥ R30k collected or firmly reserved · stock truth green · meat pilot has ≥1 bank-confirmed deposit · payment status visible in-app.

---

## 6. HORIZON A — Approve-Only Autonomy (Weeks 2–6)

> Goal: the selling machine runs itself; you and Anton only approve. This is where "autonomous income" honestly begins.

### A1. Finish the SAM Live Stock owner-approved reply loop (already the active mission)
- The mission in `planning/CODEX_CHAT.md` is exactly right: SAM classifies leads, drafts replies, you get a review card, you tap send. Complete it, run it gated for 2 weeks, measure how often you edit the drafts.
- **Graduation rule:** when 20 consecutive drafts need no edits, enable auto-send for *availability/pricing answers only* (never reservations or promises) — flip `SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED` scope gradually. This is how trust is earned with evidence, matching the repo's own 96%-gate philosophy.

### A2. Same ratchet for SAM Meat
- After the pilot's first 2–3 paid carcasses, enable backend auto-reply for intake questions; keep quotes and anything money-adjacent owner-approved. Fix OP-009 (readiness endpoint 500) first — it's build-ready at 96%.

### A3. Ship the P1 money-path tickets (all already spec'd at 96%+)
- **OP-001** meat lead qualification (stop junk leads) · **OP-003** meat/abattoir weight windows (60–80kg meat, 80kg+ abattoir) · **OP-007** meat-ready stock on the sales dashboard · **OP-008** current stock value model.
- **Why:** OP-008 especially — it gives you a live "Rands standing in pens" number, the single most motivating metric for the whole family.

### A4. Herdmaster alert engine v1 (from design pack to running code)
- Implement the top 4 of the 10 documented alert rules as a daily job: missing weight data, meat-window entry, slow grower, purpose unassigned. Deliver into the existing Farm Attention Digest → Anton's Telegram.
- **Why:** This converts Herdmaster from 35% docs to ~60% working agent, and directly feeds the sales funnel (pigs entering the sellable window get flagged the day it happens, not when someone remembers to look).

### A5. Beacon: approved-media pipeline + weekly cadence
- You approve an initial batch of 10–15 photos/videos in `/sales/beacon-media` (one afternoon on the farm). Beacon drafts one weekly availability-awareness post + one meat post; you approve via the existing gate; post manually or via the gated FB rail.
- **Why:** Demand generation compounds. Zero approved media is currently the #1 Beacon blocker and it's a *you* task, not a build task.

### A6. Ledger v1 (money truth)
- Small build: a `sales_ledger` view over orders + slaughter transactions + meat deposits, one dashboard page, and `/ledger` Telegram answers backed by it.
- **Why:** "Are we profitable this month?" should be a query, not a feeling. Feed cost tracking (Quartermaster) comes later; revenue truth comes now.

**Horizon A exit criteria:** SAM handles ≥80% of enquiries with approve-only touches · alerts run daily to Anton · weekly Beacon post cadence · ledger answers "money in this month" accurately.

---

## 7. CHARLIE CORE — Make the Builder Trustworthy (parallel track, Weeks 1–3)

You want to plug this plan into CHARLIE CORE and have it build overnight. **It cannot do that today** — its last overnight mission blocked in 13 minutes on a provider-routing bug. The full diagnosis is in the previous review; here is the distilled repair queue. **Do these as supervised sessions first, not overnight missions** (the builder can't fix itself while broken):

| # | Fix | Effort |
|---|---|---|
| 1 | v2 provider routing: `execution_bridge.py` line 387 must use `_run_agent_model_process` (like v1), so Claude-routed agents stop being sent through Codex CLI | Hours |
| 2 | Watch-loop crash shield: daemon must survive `KeyError`/`ValueError`/`PermissionError`, notify, and continue | Hours |
| 3 | Never re-execute a stuck `in_progress` mission; convert expired runs to blocked packets (execution lease) | 1–2 days |
| 4 | Progress-based supervision instead of the fixed 20-min no-artifact kill (builders doing real work keep getting shot) | 1 day |
| 5 | Stuck-mission Telegram watchdog + notify retry | Hours |
| 6 | Default pipeline cut to 4 stages (planner → builder → tester → reviewer); big councils opt-in only | 1 day |
| 7 | Move `.charlie_runner/` (ideally the whole working copy) **out of OneDrive** — the sync locks are causing real crashes | 30 min |
| 8 | CI workflow running the ~298 CHARLIE tests | Hours |

**Mission sizing law (this is what has been killing overnight runs):** one mission = one module, ≤5 files, ≤1 evening of work. The P0 income mission currently in CODEX_CHAT.md is too big — split it into 3–4 missions. Every item in Horizons R and A above is deliberately sized to be a valid single mission.

**After fixes 1–5 land and two small missions complete overnight cleanly, CHARLIE CORE graduates to running the Horizon A backlog autonomously.** Self-learning already has a home (`improvement_analyst.py`) — keep it advisory until the spine is stable.

---

## 8. HORIZON V — The Jarvis Layer (Weeks 6–12+)

Build this only after money flows and CHARLIE CORE ships missions reliably. In order of value:

### V1. CHARLIE as operations overseer (not just build orchestrator)
- Feed CHARLIE the ledger, farm attention, sales pipeline, and CHARLIE CORE mission states into one owner command view — the `/charlie` cockpit grows a "business" tab beside "missions". One daily voice-note-style Telegram brief: money, herd, missions, decisions needed.

### V2. Voice — recommended stack
- **Speech-to-text:** already have Whisper STT in Oom Sakkie — extend to CHARLIE.
- **Text-to-speech / conversational voice:** OpenAI Realtime API (lowest integration effort given the existing OpenAI usage) or ElevenLabs (best voice quality, distinct voices per agent — Oom Sakkie *should* sound like an oom).
- Sequence: CHARLIE voice for you first, then Oom Sakkie voice for Anton. Push-to-talk before wake-word. Voice is a UI upgrade on working agents, never a replacement for the approval gates.

### V3. The living UI ("opens windows, shows what's happening")
- The honest version of this: agent replies carry *UI directives* — "open litter L-2026-07", "show this quote PDF", "display meat-ready list" — and the dashboard executes them. The dock/panel architecture in `oomSakkie.js` and the `/charlie` cockpit already point this direction. Build it as a thin directive protocol over existing pages rather than a new front-end platform.
- If a richer canvas is wanted later, evaluate a dedicated React front-end then — not now.

### V4. Oom Sakkie ↔ Anton autonomy
- Herdmaster alerts (A4) + voice (V2) + task acknowledgement ("Anton, 4 pigs entered the meat window; reply DONE when moved") = the real farm-CEO loop. Add the Farm Calendar (already planned in `FARM_CALENDAR_PLAN.md`) as the task backbone.

### V5. Beacon department build-out
- Only after 8+ weeks of post-performance data: add the Strategy/Creative/Performance sub-agents as CHARLIE CORE missions, each reading the campaign performance tables that already exist in Supabase.

### V6. Quartermaster (feed costs) then FRED (transport)
- Feed cost capture unlocks true profit-per-pig (currently the biggest blind spot in the money model — OP-008 values stock but nothing tracks cost). FRED remains parked until sales volume demands delivery logistics.

---

## 9. What NOT To Do (scope discipline — this is where past months went)

1. **No new agent doctrine files** until every documented agent ≤50% built gets code or gets archived. The Vault is at 88–92% polish while payment recording is at 0% — stop polishing the library while the till is broken.
2. **No payment gateway integration in July.** Manual EFT + in-app payment status (R5) is enough for current volume. Revisit Yoco/PayFast when >20 transactions/month make reconciliation painful.
3. **No public Facebook automation** until the pilot cap has been paid twice. The existing gates are correct.
4. **No LangGraph/Temporal migration for CHARLIE CORE.** The audit shows five fixable defects, not a broken architecture.
5. **No voice/UI spend before Horizon A exit criteria.** Jarvis with no revenue underneath is a demo, not a company.
6. **No mission >5 files into CHARLIE CORE.** Oversized missions are its #1 documented failure correlate.

---

## 10. The Complete Mission Backlog (CHARLIE CORE intake format)

Sized, sequenced, and safe to queue once Section 7 fixes 1–5 are done. Supervised sessions until then.

| # | Mission | Horizon | Size | Depends on |
|---|---|---|---|---|
| M1 | Fix CHARLIE CORE v2 provider routing + crash shield | Core | S | — |
| M2 | Execution lease + stuck-mission conversion + watchdog notify | Core | M | M1 |
| M3 | Progress-based stage supervision + 4-stage default pipeline | Core | M | M2 |
| M4 | Bulk weight one-button flow completion + stuck batch recovery | R1 | M | — (P0, do now, supervised) |
| M5 | Live-order payment status API + orders page paid column | R5 | S | — |
| M6 | Daily money brief extension to order summary workflow | R6 | S | M5 |
| M7 | OP-009 pilot readiness 500 fix | A2 | S | — |
| M8 | OP-001 meat lead qualification | A3 | S | M7 |
| M9 | OP-003 meat/abattoir weight windows | A3 | S | M4 |
| M10 | OP-007 sales dashboard meat-ready stock | A3 | S | M9 |
| M11 | OP-008 current stock value model | A3 | M | M4 |
| M12 | SAM Live Stock reply-loop completion (split from current oversized mission) | A1 | M | — |
| M13 | SAM Live Stock graduation: scoped auto-answer for availability/pricing | A1 | S | M12 + 2wk evidence |
| M14 | Herdmaster alert engine v1 (4 rules → attention digest) | A4 | M | M4 |
| M15 | Ledger v1: sales_ledger view + dashboard page + /ledger backing | A6 | M | M5 |
| M16 | Slaughter ↔ pig exit lifecycle sync | R/A | S | — |
| M17 | CHARLIE CI workflow (all charlie tests on push) | Core | S | — |
| M18 | CHARLIE cockpit business tab (ledger + attention + pipeline) | V1 | M | M14, M15 |
| M19 | CHARLIE voice v1 (STT reuse + TTS via Realtime API) | V2 | M | M18 |
| M20 | UI directive protocol (agent replies open pages/panels) | V3 | M | M18 |
| M21 | Oom Sakkie voice + task acknowledgement loop for Anton | V4 | M | M19 |
| M22 | Farm Calendar v1 (from existing plan) | V4 | M | — |
| M23 | Beacon performance-fed weekly campaign automation | V5 | M | 8wk data |
| M24 | Quartermaster feed cost capture v1 | V6 | M | M15 |

Owner tasks that are NOT missions (only you can do these): confirm price book (R2) · sell/WhatsApp blitz (R3) · approve media batch (A5) · check bank + mark paid (R5, daily 2 min) · review 9 weight conflicts (R1).

---

## 11. Operating Rhythm (how you run this without babysitting)

**Daily (you, ~10 min):** 16:00 money brief on Telegram → approve pending SAM cards → mark payments received.
**Daily (Anton, ~10 min):** Farm attention digest → acknowledge alerts → record collections/weights.
**Weekly (30 min):** Review ledger page · approve Beacon post · review CHARLIE CORE mission queue and approve next 3–5 missions · check exit criteria progress.
**When a mission blocks:** you get one Telegram with the reason; the runner moves to the next mission. Morning: send-back or re-approve with one tap. Nothing waits silently — that's what the Section 7 fixes guarantee.

---

## 12. 90-Day Scoreboard (how we know it's working)

| Metric | Now | Day 30 | Day 60 | Day 90 |
|---|---|---|---|---|
| Revenue banked (cumulative) | R0 tracked | ≥R30k | ≥R80k | ≥R150k |
| Pigs sold / moved off feed | 0 | ≥30 | ≥55 | ≥80 |
| Meat carcasses paid | 0 | 1–2 | 4–6 | 8+ |
| Enquiries handled approve-only | 0% | 50% | 80% | 90% |
| CHARLIE CORE overnight mission success rate | ~0% | 60% | 80% | 90% |
| Owner minutes/day on system | ~120 | 30 | 15 | 10 |
| Stock truth (weights ≤14 days old) | ~40% | 90% | 95% | 95% |

If Day-30 revenue is on track but autonomy lags: fine, keep selling manually and fix the builder. If autonomy is on track but revenue lags: the problem is demand — shift energy to Beacon media and the buyer list, not more code. **Revenue is the master metric; everything else serves it.**

---

## 13. Final Word

You have built far more than you think: a real farm data platform, the most complete small-scale AI sales runtime I've seen in a repo this size, and a governance culture (gates, evidence, owner approval) that most companies never achieve. The gap is not capability — it is **sequencing and finishing**. The doctrine got 90% polish while payment recording got 0%.

For the next 30 days: sell pigs with the tools that work, fix the five CHARLIE CORE defects, ship the small money-path missions, and let the evidence — not the ambition — open each next gate. Do that, and the Jarvis layer stops being a dream and becomes a UI on top of a business that is already running itself.
