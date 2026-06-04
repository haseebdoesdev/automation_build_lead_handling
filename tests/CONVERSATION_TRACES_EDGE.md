# ReviewArmour v2 - 10 Edge Cases

_Generated 2026-06-03T00:16:55.451972+00:00_

Targets boundaries not exercised by the prior 53 conversations: accept mid-negotiation, angry-but-valid inbound, real (not hypothetical) chargeback, bot suspicion, false-acceptance prevention, multilingual, competing priorities (pricing + legal), schema edges (empty last name), wrong-platform URL, multi-topic long inbound.

---
# E1 — Accept mid-negotiation: 'works for me' after step-1 quote
**Expected**: Lead at step=1 with a prior quote of $298 in transcript; lead says '$298 works for me'. Acceptance LLM must classify as accept (price-anchored) and fire quote_accepted state.

**Lead**: 'Joe' / 'Lead' / Acme Plumbing (US) | category=`plumber` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=1

_Pre-seeded transcript with 4 turns._

## Turn 1 — Lead accepts the negotiated price (email, stage=reply)

**Lead**: > $298 works for me. Let's do it.

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'ai_conversation_state': 'quote_accepted', 'negotiation_step': 1}`

**Draft**:
```
Subject: Confirmed for Acme Plumbing

Confirmed. Your specialist will send the removal brief and the DocuSign within the hour. You'll pay only after the reviews are down.
Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# E2 — Angry tone + valid pricing question — answer, do NOT escalate on tone
**Expected**: Lead uses sharp/angry tone but asks a normal pricing question. Pipeline should not escalate just because of tone. AI answers the question with the authorized quote.

**Lead**: 'Sam' / 'Lead' / Sam Auto Body (US) | category=`auto_repair` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch (email, stage=first_touch)

**Outcome**: `human_queue` | draft.action=`send`

**SC**: a1=fix(3 failed) a2=fix(1 failed) a3=fix(2 failed) 

**Draft**:
```
Subject: Removing those Google reviews for Sam Auto Body

Hi Sam,

Got your profile for Sam Auto Body. We remove policy-violating Google reviews on a pay-after-removal basis — no charge unless the review actually comes down.

With two recent reviews, this is a straightforward case to assess. Reply here to go over pricing, or I can get a specialist on a quick call with you.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Angry pricing ask (email, stage=reply)

**Lead**: > Look I'm sick of these fake reviews killing my business. Just tell me what the hell it costs already.

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T4", "range_low_usd": 240, "range_high_usd": 280, "floor_usd": 200, "negotiation_step": 0, "authorized_quote_usd_per_review": 258, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T4 auto_repair, 2 text-only reviews both under 1 month biasing lower, offset by urgent frustrated tone and high engagement; settled at $258 near upper-mid band.

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: RE: Removing those Google reviews for Sam Auto Body

Sam,

For Sam Auto Body, the rate is $258 USD per review. Two reviews means $516 total, and you pay nothing until each one is confirmed down.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

Reply here to move forward or to get a specialist on a call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead EDGE-E2 tier=T4 band=$240-$280 -> $258 (urgent)
```

---
# E3 — Actual post-pay chargeback — must escalate (vs Conv 39 hypothetical)
**Expected**: Lead describes an ACTUAL paid invoice with no removal. This is the real refund/chargeback escalation path. Pipeline must escalate.

**Lead**: 'Maria' / 'Lead' / Maria's Salon (US) | category=`beauty_salon` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — Real chargeback complaint (email, stage=reply)

**Lead**: > I paid $450 last month for a removal that never happened. I want a refund or I'm filing a chargeback with my bank tomorrow.

**Outcome**: `escalate` | draft.action=`escalate` | reason=`Lead is reporting an actual prior paid transaction ($450) where the service was not delivered and is threatening a chargeback — this is a live billing dispute requiring human intervention, not a pre-sales hypothetical.`

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Drafter escalated with no commercial_result on non-pricing turn; retrying once for lead EDGE-E3
INFO reviewarmour.conversation: Pipeline escalate (drafter): Lead is reporting an actual prior paid transaction ($450) where the service was not delivered and is threatening a chargeback — this is a live billing dispute requiring human intervention, not a pre-sales hypothetical. for lead EDGE-E3
```

---
# E4 — Bot suspicion: 'is this AI?'
**Expected**: Lead asks if they're talking to a bot/AI. AI should respond without confirming or denying AI identity (per spec: don't make false claims). Should not escalate. Should redirect to value.

**Lead**: 'Priya' / 'Lead' / Priya Dental Care (US) | category=`dentist` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Priya Dental Care - Google review removal

Hi Priya,

We received your submission for Priya Dental Care and have your Google Business Profile on file.

ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is confirmed down, not before.

Reply here to go over pricing and next steps, or I can get a specialist on a call with you at a time that works.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Bot suspicion (email, stage=reply)

**Lead**: > Wait, am I talking to a bot? Is this AI?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
This is an AI-assisted messaging layer, yes. A human specialist at ReviewArmour reviews every account and handles the actual removal work.

If you'd prefer to speak directly with someone, reply here and I'll get a specialist on a call with you.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# E5 — Bare 'ok' with NO prior quote — must NOT fire acceptance
**Expected**: First touch goes out. Lead replies just 'ok'. There is NO USD quote in the transcript. Per spec: 'generic ok / go ahead right after non-pricing assistant text' is NOT acceptance. State must NOT contain ai_conversation_state=quote_accepted.

**Lead**: 'Alex' / 'Lead' / Alex Bakery (US) | category=`bakery` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - Alex Bakery

Hi Alex,

We have your Google Business Profile for Alex Bakery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

Want to go over pricing or get a specialist on a call? Just reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Bare 'ok' reply (email, stage=reply)

**Lead**: > ok

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Removing your Google reviews - Alex Bakery

Hi Alex,

Glad to hear it. A specialist can walk you through pricing for Alex Bakery on a quick call, or if you prefer to handle it over email, just say the word and we can go from there.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# E6 — Spanish-language inbound mid-flow
**Expected**: After an English first touch, lead replies in Spanish. No spec rule for multilingual. Observe: does AI respond in English (staying on script) or attempt Spanish? Either may be acceptable but the AI must NOT escalate just because language switched.

**Lead**: 'Carlos' / 'Lead' / Carlos Landscaping (US) | category=`landscaper` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch (English) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - Carlos Landscaping

Hi Carlos,

We have your Google Business Profile for Carlos Landscaping. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

Want to go over pricing or get a specialist on a call? Reply here or let me know a good time.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Spanish reply (email, stage=reply)

**Lead**: > Hola, gracias por escribir. Cuanto cuesta por reseña? Tenemos dos reseñas malas.

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 290, "range_high_usd": 340, "floor_usd": 260, "negotiation_step": 0, "authorized_quote_usd_per_review": 300, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 landscaper, 2 reviews both under 1 month, text-only; recency bias toward lower end, cooperative tone inferred from polite direct inquiry, no image modifier; opening at lower-mid band.

**SC**: a1=fix(1 failed) a2=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Removing your Google reviews - Carlos Landscaping

Hi Carlos,

For Carlos Landscaping, the rate is $300 USD per review. You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point - not before. That's how we structure every job.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

Reply here to move forward or let me know a good time for a call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead EDGE-E6 tier=T3 band=$290-$340 -> $300 (cooperative)
```

---
# E7 — Pricing ask + lawyer mention in same message — legal escalation wins
**Expected**: Lead asks for price AND mentions their lawyer in one message. Hard-trigger legal escalation must win — pipeline returns escalate, NO pricing draft fires.

**Lead**: 'Robert' / 'Lead' / Robert Roofing (US) | category=`roofing_contractor` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — Pricing + legal in one message (email, stage=reply)

**Lead**: > What's your rate per review? My lawyer said I should ask about your refund policy before signing anything.

**Outcome**: `escalate` | draft.action=`escalate` | reason=`legal_escalation:lawyer`

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Pipeline escalate: legal_escalation:lawyer for lead EDGE-E7
```

---
# E8 — Single-word first name + empty last name
**Expected**: Lead record has first_name='Madonna', last_name=''. AI must address by first name only without leaving 'Hi Madonna ,' or empty trailing comma. Footer / draft normal.

**Lead**: 'Madonna' / '' / Madonna Med Spa (US) | category=`med_spa` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch with single-name lead (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - Madonna Med Spa

Hi Madonna,

Got your profile for Madonna Med Spa. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.

A specialist is ready to walk you through pricing and next steps. Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# E9 — Lead pastes Yelp URL instead of Google Maps
**Expected**: GBP missing on lead. Lead pastes a Yelp URL when asked. Auto-capture must NOT fire (URL doesn't match Maps pattern). AI should ask again for the GBP link specifically.

**Lead**: 'David' / 'Lead' / David's Restaurant (US) | category=`restaurant` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] step=0

## Turn 1 — First touch (no GBP) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - David's Restaurant

Hi David,

We received your inquiry about David's Restaurant. Before we can look at pricing, we need your Google Business Profile link.

Can you share the URL for David's Restaurant on Google Maps or Google Search?

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead pastes Yelp URL (email, stage=reply)

**Lead**: > Sure, here's our page: https://www.yelp.com/biz/davids-restaurant-newyork What's the pricing?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 270, "range_high_usd": 320, "floor_usd": 260, "negotiation_step": 0, "can_quote": false, "request_gbp_first": true, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Removing your Google reviews - David's Restaurant

Hi David,

That link goes to Yelp - we work on Google reviews specifically. To pull up pricing for David's Restaurant, I need the Google Business Profile link.

You can find it by searching "David's Restaurant" on Google Maps and copying the URL from your browser.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead EDGE-E9 tier=T3 band=$270-$320 -> $285 (noncommittal)
```

---
# E10 — Long multi-topic inbound — must triage cleanly
**Expected**: Lead sends a 5-paragraph message covering history, urgency, pricing, timing, and warranty all at once. AI should answer the top 2-3 priorities (price + timing or pay-anchor) cleanly without trying to address everything and losing focus.

**Lead**: 'Jennifer' / 'Lead' / Jennifer Hotel Group (US) | category=`hotel` | reviews=4 mostly_under_1_month images=[True, False, False, True] recent=[True, True, True, False] step=0

## Turn 1 — First touch (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - Jennifer Hotel Group

Hi Jennifer,

We received your submission for Jennifer Hotel Group and have your Google Business Profile on file.

ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is confirmed down, not before.

A specialist is reviewing your profile and will follow up shortly with pricing details. If you want to move faster, reply here and we can get that conversation going now.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Long multi-topic message (email, stage=reply)

**Lead**: > Hi - thanks for reaching out. Let me give you the full picture.

We've been operating for 8 years and never had review issues until a former employee left and started a smear campaign. We've gotten 4 really bad reviews in the past 2 months, two with photos of food that we don't even serve.

We have ...

**Outcome**: `escalate` | draft.action=`escalate` | reason=`legal_escalation:sue`

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Pipeline escalate: legal_escalation:sue for lead EDGE-E10
```

---
