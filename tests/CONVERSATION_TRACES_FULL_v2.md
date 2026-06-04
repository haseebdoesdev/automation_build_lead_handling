# ReviewArmour v2 - Full AI Conversation Coverage (20 conversations)

_Generated 2026-06-02T17:21:13.559774+00:00_

Covers every observable behavior of the AI conversation module. Each conversation lists the expected behavior + per-turn commercial result, SC verdicts, draft body, and pipeline log highlights.

---
# Conversation 01 — CA T3 Hotel - first touch -> written quote -> acceptance
**Expected**: CA Toronto footer. T3 hotel small band $320-$370. Adaptive picks in band. SC accepts. Acceptance triggers quote_accepted state.

**Lead**: Amelia Wright / Maple Leaf Hotel (CA) | category=`hotel` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Maple Leaf Hotel - Google review removal

Hi Amelia,

Got your profile for Maple Leaf Hotel. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.

A specialist can walk you through pricing and next steps. Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 416-432-5439
2 Bloor St E Suite 3500, Toronto, Ontario, Canada M4W 1A8
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > Got your message. What does this cost per review?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 320, "range_high_usd": 370, "floor_usd": 260, "negotiation_step": 0, "authorized_quote_usd_per_review": 320, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 hotel, 2 reviews both under 1 month, text-only; recency bias to lower end, noncommittal/low-engagement tone on first reply drives floor of band at $320 to keep lead engaged.

**SC**: a1=fix(1 failed) a2=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Maple Leaf Hotel - Google review removal

Hi Amelia,

For Maple Leaf Hotel, the rate is $320 USD per review. You only pay after each review is confirmed down.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point - not before. That's how we structure every job.

Reply here to move forward or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 416-432-5439
2 Bloor St E Suite 3500, Toronto, Ontario, Canada M4W 1A8
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-01 tier=T3 band=$320-$370 -> $320 (noncommittal)
```

## Turn 3 — Lead reply (email, stage=reply)

**Lead**: > Sounds good, let's move forward.

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'ai_conversation_state': 'quote_accepted', 'negotiation_step': 0}`

**Draft**:
```
Subject: Confirmed for Maple Leaf Hotel

Confirmed. Your specialist will send the removal brief and the DocuSign within the hour. You'll pay only after the reviews are down.
Jayden Faris / ReviewArmour / +1 416-432-5439
2 Bloor St E Suite 3500, Toronto, Ontario, Canada M4W 1A8
```

---
# Conversation 02 — T4 Nail Salon - low-tier written quote
**Expected**: T4 nail salon band $210-$250, floor $200. Adaptive picks in range. AI quotes in writing.

**Lead**: Test Lead / Glamour Nail Salon (US) | category=`nail_salon` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Glamour Nail Salon - Google review removal

Hi Test,

We have your Google Business Profile for Glamour Nail Salon. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

Want to go over pricing or get a specialist on a quick call? Just reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > What's the price per review for these?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T4", "range_low_usd": 210, "range_high_usd": 250, "floor_usd": 200, "negotiation_step": 0, "authorized_quote_usd_per_review": 215, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T4 nail_salon, 2 reviews all under 1 month, text-only, recency bias toward lower end; lead asked price directly with no warmth, treated as noncommittal, landing at lower-midpoint $215.

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Glamour Nail Salon - Google review removal

For Glamour Nail Salon, the rate is $215 USD per review. You pay only after each review is confirmed down.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

Want to move forward or get a specialist on a quick call? Just reply here.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-02 tier=T4 band=$210-$250 -> $215 (noncommittal)
```

---
# Conversation 03 — T2 HVAC Contractor -> phone-call route
**Expected**: T2 HVAC band $400-$450 (above threshold, no T2 exception). Engine sets phone_call_threshold_triggered. AI pivots to phone.

**Lead**: Test Lead / Reliable HVAC Services (US) | category=`hvac_contractor` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Reliable HVAC Services - Google review removal

Hi Test,

Got your profile for Reliable HVAC Services. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.

Want to go over pricing or get a specialist on a call? Just reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > How much per review?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T2", "range_low_usd": 400, "range_high_usd": 450, "floor_usd": 350, "negotiation_step": 0, "can_quote": false, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": true, "salesman_recommended_opening_usd": 420, "escalate": false}```

_Adaptive reasoning_: T2 hvac_contractor, 2 reviews all under 1 month, text-only; recency bias toward lower end, noncommittal tone (direct price ask, no warmth) pulls to lower-midpoint, landing at $420.

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
I want to make sure I give you an accurate quote based on the full picture. Your specialist will walk you through the pricing on a quick call - I can get one on the calendar for first thing tomorrow morning.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-03 tier=T2 band=$400-$450 -> $420 (noncommittal)
```

---
# Conversation 04 — T1 Plastic Surgeon -> phone-call route (highest band)
**Expected**: T1 plastic surgeon band $520-$550, well above threshold, no exception because reviews are over-month text-only. Phone route.

**Lead**: Test Lead / Premier Plastic Surgery (US) | category=`plastic_surgeon` | reviews=2 all_over_1_month images=[False, False] recent=[False, False]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=fix(1 failed) a2=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Removing your Google reviews - Premier Plastic Surgery

Hi Test,

We have your Google Business Profile for Premier Plastic Surgery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actually down.

A specialist is ready to walk you through pricing and next steps. Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > Pricing info please?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T1", "range_low_usd": 520, "range_high_usd": 550, "floor_usd": 400, "negotiation_step": 0, "can_quote": false, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": true, "salesman_recommended_opening_usd": 545, "escalate": false}```

_Adaptive reasoning_: T1 plastic_surgeon, 2 reviews all-over-1-month (harder job), text-only reviews, noncommittal tone (pricing request only), medium engagement — upper band biased by recency, slight pull-back for noncommittal tone.

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Removing your Google reviews - Premier Plastic Surgery

Hi Test,

I want to make sure I give you an accurate quote based on the full picture. Your specialist will walk you through the pricing on a quick call. I can get one on the calendar for first thing tomorrow morning.

Just reply here with a time that works, or let me know if you prefer a different day.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-04 tier=T1 band=$520-$550 -> $545 (noncommittal)
```

---
# Conversation 05 — Soft-quote mode - band reply, pushback escalates
**Expected**: soft_quote_mode=True. Engine returns range. AI quotes a band ('typically $X-$Y'). Lead pushback escalates (no negotiation).

**Lead**: Test Lead / Smith Roofing (US) | category=`roofing_contractor` | reviews=2 mostly_under_1_month images=[True, False] recent=[True, True] soft_quote

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Smith Roofing - Google review removal

Got your profile for Smith Roofing. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

A specialist will be in touch shortly with pricing details. If you want to move faster, reply here and we can go over it now.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > What range are we looking at per review?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T2", "range_low_usd": 390, "range_high_usd": 440, "floor_usd": 350, "negotiation_step": 0, "authorized_quote_usd_per_review": 440, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "soft_quote_range": [390, 440], "escalate": false}```

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
For Smith Roofing, the range is typically $390-$440 USD per review. You only pay after each review comes down - no charge if it stays up.

Want to lock in the details? Reply here or we can set up a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 06 — Full negotiation ladder - 0 -> 1 -> 2 -> acceptance
**Expected**: T3 plumber. Each pushback bumps step. Step 2 quotes still in band above floor. Acceptance at step 2 triggers quote_accepted.

**Lead**: Test Lead / Acme Plumbing (US) | category=`plumber` | reviews=2 all_under_1_month images=[True, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Acme Plumbing - Google review removal

Hi Test,

Got your profile for Acme Plumbing. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

Want to go over pricing and next steps? Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > What's the rate per review?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 330, "range_high_usd": 370, "floor_usd": 260, "negotiation_step": 0, "authorized_quote_usd_per_review": 340, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 plumber, 2 reviews both under 1 month (one with image), recency biases lower end, noncommittal/low-engagement tone from minimal reply, priced at lower-midpoint $340 to keep lead engaged.

**SC**: a1=fix(2 failed) a2=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Acme Plumbing - Google review removal

For Acme Plumbing, the rate is $340 USD per review.

You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point, not before. That's how we structure every job.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

Want to move forward or have questions? Reply here.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-06 tier=T3 band=$330-$370 -> $340 (noncommittal)
```

## Turn 3 — Lead reply (email, stage=reply)

**Lead**: > That feels a bit steep for us. Any flexibility?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 330, "range_high_usd": 370, "floor_usd": 260, "negotiation_step": 1, "authorized_quote_usd_per_review": 298, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 plumber, 2 reviews all under 1 month (one with image), price_sensitive tone at step 1; recency+image bias lower end, holding $340 as defensible midpoint-low for discount application.

**SC**: a1=pass 

**State**: `{'negotiation_step': 1}`

**Draft**:
```
Subject: Re: Acme Plumbing - Google review removal

For Acme Plumbing, I can come down to $298 USD per review.

You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point, not before. That's how we structure every job.

Want to move forward? Reply here and I'll get the removal brief started.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Negotiation pushback: bumped negotiation_step to 1 for lead SIM-06
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-06 tier=T3 band=$330-$370 -> $340 (price_sensitive)
```

## Turn 4 — Lead reply (email, stage=reply)

**Lead**: > Hmm, still a stretch for our budget. Can you do better?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 330, "range_high_usd": 370, "floor_usd": 260, "negotiation_step": 2, "authorized_quote_usd_per_review": 260, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 plumber, 2 reviews both under-1-month (one with image), price_sensitive tone across two pushbacks, step 2 so output base position; recency+image bias floor of band at $330.

**SC**: a1=pass 

**State**: `{'negotiation_step': 2}`

**Draft**:
```
Subject: Re: Acme Plumbing - Google review removal

For Acme Plumbing, the best I can do is $260 USD per review.

You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point, not before. That's how we structure every job.

Want to move forward? Reply here and I'll get the removal brief started.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Negotiation pushback: bumped negotiation_step to 2 for lead SIM-06
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-06 tier=T3 band=$330-$370 -> $330 (price_sensitive)
```

## Turn 5 — Lead reply (email, stage=reply)

**Lead**: > Okay that works. Let's do it.

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'ai_conversation_state': 'quote_accepted', 'negotiation_step': 2}`

**Draft**:
```
Subject: Confirmed for Acme Plumbing

Confirmed. Your specialist will send the removal brief and the DocuSign within the hour. You'll pay only after the reviews are down.
Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 07 — Pushback past step 2 -> escalate to human
**Expected**: Lead already at step 2, pushes back again. Pipeline escalates with reason 'negotiation_past_final_step'.

**Lead**: Test Lead / Sunset Electric (US) | category=`electrician` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > Look, we really need this to be cheaper. Can you go any lower?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T3", "range_low_usd": 340, "range_high_usd": 380, "floor_usd": 260, "negotiation_step": 2, "authorized_quote_usd_per_review": 260, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 electrician, 2 reviews all under 1 month, text-only; price_sensitive tone at step 2 drives lower-midpoint, recency bias confirms lower end at band floor $340.

**SC**: a1=pass 

**State**: `{'negotiation_step': 2}`

**Draft**:
```
Subject: Updated pricing for Sunset Electric

For Sunset Electric, the rate is $260 USD per review. That is the lowest we can go on this.

You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point — not before. That's how we structure every job.

Want to move forward or get a specialist on a quick call?

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-07 tier=T3 band=$340-$380 -> $340 (price_sensitive)
```

---
# Conversation 08 — Missing GBP link -> AI asks for it before quoting
**Expected**: Engine returns request_gbp_first=True. AI asks for the link.

**Lead**: Test Lead / Quick Auto Repair (US) | category=`auto_repair` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > Hi, I want to know your pricing for review removal.

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T4", "range_low_usd": 240, "range_high_usd": 280, "floor_usd": 200, "negotiation_step": 0, "can_quote": false, "request_gbp_first": true, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Review removal pricing - Quick Auto Repair

Before I pull up pricing for Quick Auto Repair, I need your Google Business Profile link. That lets us confirm which reviews are in scope.

You can find it by searching your business on Google Maps and copying the URL from the address bar.

Once I have that, I can get you the exact per-review rate.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-08 tier=T4 band=$240-$280 -> $248 (noncommittal)
```

---
# Conversation 09 — GBP category unknown -> AI asks before quoting
**Expected**: gbp_category=None. Engine returns request_category_first=True. AI confirms business type before quoting.

**Lead**: Test Lead / Generic Widget Co (US) | category=`None` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > How much do you charge per review?

**Outcome**: `human_queue` | draft.action=`send`

**SC**: a1=fix(2 failed) a2=fix(3 failed) a3=fix(1 failed) 

**Draft**:
```
Subject: Re: Pricing for Generic Widget Co

Before I pull a number together for Generic Widget Co, I need one quick detail: what type of business is it? (For example: medical, legal, contractor, restaurant, etc.) That determines the rate.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 10 — ai_quote_allowed kill switch -> escalate
**Expected**: Pipeline escalates on first pricing turn. No quote in draft.

**Lead**: Test Lead / Test Business (US) | category=`plumber` | reviews=2 all_under_1_month images=[False, False] recent=[True, True] kill-switch

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > What does this cost?

**Outcome**: `escalate` | draft.action=`escalate` | reason=`ai_quote_allowed_kill_switch`

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Pipeline escalate: ai_quote_allowed=false for lead SIM-10
```

---
# Conversation 11 — Legal escalation phrase -> escalate immediately
**Expected**: Lead mentions 'my lawyer'. Pipeline returns escalate, draft.action=escalate.

**Lead**: Test Lead / Test Business (US) | category=`plumber` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > My lawyer told me to ask if you're really able to remove these.

**Outcome**: `escalate` | draft.action=`escalate` | reason=`legal_escalation:lawyer`

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: Pipeline escalate: legal_escalation:lawyer for lead SIM-11
```

---
# Conversation 12 — Refund/chargeback request -> escalate
**Expected**: Refund request triggers escalation per Section 11 escalation_trigger check.

**Lead**: Test Lead / Test Business (US) | category=`plumber` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — Lead reply (email, stage=reply)

**Lead**: > I want a refund on the last invoice. The review didn't come down and I'm filing a chargeback.

**Outcome**: `escalate` | draft.action=`escalate` | reason=`Lead is requesting a refund and threatening a chargeback on a prior invoice — this is a post-payment dispute and a hard escalation topic per spec.`

**Commercial**: ```{"tier": "T3", "range_low_usd": 330, "range_high_usd": 370, "floor_usd": 260, "negotiation_step": 0, "authorized_quote_usd_per_review": 330, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T3 plumber, 2 reviews all under 1 month (text-only), recency bias toward lower end; lead is threatening chargeback indicating price-sensitive/adversarial tone and low engagement, selecting band floor.

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-12 tier=T3 band=$330-$370 -> $330 (price_sensitive)
INFO reviewarmour.conversation: Pipeline escalate (drafter): Lead is requesting a refund and threatening a chargeback on a prior invoice — this is a post-payment dispute and a hard escalation topic per spec. for lead SIM-12
```

---
# Conversation 13 — Timing question for fresh reviews -> approved under_1_month paragraph
**Expected**: All reviews under 1 month. Lead asks how fast. AI uses exact approved 'two to four weeks' timeline paragraph.

**Lead**: Test Lead / Fresh Bakery (US) | category=`bakery` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Your Google reviews - Fresh Bakery

Hi Test,

Got your profile for Fresh Bakery. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.

A specialist can walk you through pricing and next steps. Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > How fast can these come down?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Your Google reviews - Fresh Bakery

Hi Test,

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

If you want to go over pricing and next steps, reply here or let me know a good time for a call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 14 — Timing question for older reviews -> approved over/mixed paragraph
**Expected**: Reviews are over 1 month. Lead asks timing. AI uses approved mixed/over_1_month timeline paragraph.

**Lead**: Test Lead / Heritage Furniture Store (US) | category=`furniture_store` | reviews=2 all_over_1_month images=[False, False] recent=[False, False]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Heritage Furniture Store - Google review removal

Hi Test,

Got your profile for Heritage Furniture Store. We remove policy-violating Google reviews for businesses across the US - you only pay after each review comes down, not before.

If you want to go over pricing or next steps, just reply here or we can set up a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > These have been up for a while. When can we expect them down?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Heritage Furniture Store - Google review removal

Hi Test,

For reviews this age, we typically see them come down within around two weeks, though it can take up to a month depending on the case.

If you want to go over pricing or get a specialist on a call, just reply here.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 15 — Lead demands a hard date -> approved hard_guarantee paragraph
**Expected**: Lead asks for a guaranteed calendar date. AI uses the approved hard_guarantee_asked paragraph; does NOT promise a specific date.

**Lead**: Test Lead / Sunshine Dental (US) | category=`dentist` | reviews=2 all_under_1_month images=[True, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Sunshine Dental - Google review removal

Hi Test,

We have your Google Business Profile for Sunshine Dental. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is confirmed down, not before.

Want to go over pricing or get a specialist on a quick call? Reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > I need a guarantee these come down by next Friday. Can you commit to that exact date?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Sunshine Dental - Google review removal

Hi Test,

I can't commit to a specific day. What I can tell you is the typical window. If anything looks like it will run past that, your specialist will reach out directly.

Want to get a specialist on a call to walk through the details and pricing for Sunshine Dental? Reply here and we can get that set up.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 16 — Pay-after-removal question -> approved pay-anchor
**Expected**: Lead asks what happens if the review doesn't come down. AI states the approved pay-anchor paragraph: no charge until removed.

**Lead**: Test Lead / Suburban Movers (US) | category=`moving_company` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Suburban Movers - Google review removal

Hi Test,

We have your Google Business Profile for Suburban Movers. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.

Want to go over pricing or get a specialist on a call? Just reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > What if you can't get them removed? Do I still pay anything?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=fix(1 failed) a2=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point - not before. That's how we structure every job.

Want to go over pricing or get a specialist on a call?

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 17 — Success-rate question -> approved success paragraph
**Expected**: Lead asks success rate. AI uses approved SUCCESS general or percentage_asked paragraph (no invented percentages).

**Lead**: Test Lead / Greenfield Med Spa (US) | category=`med_spa` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Greenfield Med Spa - Google review removal

Hi Test,

We received your submission for Greenfield Med Spa and have your Google Business Profile on file.

ReviewArmour removes policy-violating Google reviews - you only pay after each one comes down, not before.

Want to go over pricing or get a specialist on a call? Reply here or let me know a good time.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > What's your success rate on removals?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Greenfield Med Spa - Google review removal

Hi Test,

We have a high success rate on reviews that fall within Google's policy violation criteria, which is why we operate pay-after-removal. You only pay once a review is actually down. If we can't remove it, you don't pay for it.

Want to go over pricing or get a specialist on a call?

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 18 — Off-topic message -> brief redirect, stay in scope
**Expected**: Lead asks something unrelated. AI sends brief polite redirect back to review removal, does NOT escalate.

**Lead**: Test Lead / Sunny Day Cafe (US) | category=`coffee_shop` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Sunny Day Cafe - Google review removal

Hi Test,

Got your profile for Sunny Day Cafe. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.

Want to go over pricing or get a specialist on a quick call? Reply here and we can move forward.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > By the way, do you guys do SEO services too?

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
SEO is outside what we handle. On the review removal side, did you want to go over pricing or next steps for Sunny Day Cafe?

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

---
# Conversation 19 — SMS channel first touch -> compact body under length
**Expected**: First-touch via SMS. Draft body <320 chars (prefer <160). Uses SMS-style footer (compact).

**Lead**: Test Lead / Coastal Landscaping (US) | category=`landscaper` | reviews=2 all_under_1_month images=[False, False] recent=[True, True]

## Turn 1 — SMS first touch (sms, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Hi Test - this is Jayden from ReviewArmour. We have your Coastal Landscaping profile. We remove policy-violating Google reviews and you only pay after each one comes down. Want to go over pricing or set up a quick call?
```

---
# Conversation 20 — T1 dentist exception (1 review image+recent) -> written close
**Expected**: Single image+recent review, T1 dentist. T1 exception applies. Selector picks $400-$450 written close. NOT phone-routed.

**Lead**: Priya Singh / Bright Family Dental (US) | category=`dentist` | reviews=1 all_under_1_month images=[True] recent=[True]

## Turn 1 — First touch (outbound) (email, stage=first_touch)

**Outcome**: `send` | draft.action=`send`

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Bright Family Dental - Google review removal

Hi Priya,

We have your Google Business Profile for Bright Family Dental. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is confirmed down.

Want to go over pricing and next steps? Reply here or let me know a good time for a quick call.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

## Turn 2 — Lead reply (email, stage=reply)

**Lead**: > One nasty review with photos showed up last week. What's it cost to fix this?

**Outcome**: `send` | draft.action=`send`

**Commercial**: ```{"tier": "T1", "range_low_usd": 480, "range_high_usd": 530, "floor_usd": 400, "negotiation_step": 0, "authorized_quote_usd_per_review": 440, "can_quote": true, "request_gbp_first": false, "request_category_first": false, "phone_call_threshold_triggered": false, "escalate": false}```

_Adaptive reasoning_: T1 dentist, 1 review image+under-1-month, urgent tone (asked cost immediately), T1 written exception fast close at $440 — simple job, engaged lead, written close beats phone delay.

**SC**: a1=pass 

**State**: `{'negotiation_step': 0}`

**Draft**:
```
Subject: Re: Bright Family Dental - Google review removal

Hi Priya,

For Bright Family Dental, the rate is $440 USD per review. You don't pay until it's confirmed down.

Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.

Reply here to move forward and we'll get the removal brief over to you.

Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131
```

**Pipeline log highlights**:
```
INFO reviewarmour.conversation: AdaptivePriceSelector: lead SIM-20 tier=T1 band=$480-$530 -> $440 (urgent) [T1-exception]
```

---
