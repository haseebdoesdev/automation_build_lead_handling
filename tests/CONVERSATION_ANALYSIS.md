# Conversation Trace Analysis — Spec v2 Live Review

_Reviewer reading the AI's actual responses + pipeline logs against spec v2_
_Source trace: [CONVERSATION_TRACES.md](CONVERSATION_TRACES.md)_

---

## TL;DR

| Conversation | Verdict | Headline finding |
|---|---|---|
| **1. T1 Dentist → phone route** | PASS with one weakness | Phone-call threshold gate works. AI pivots correctly. Turn 3 draft is verbatim identical to Turn 2 — AI ignored the lead's escalating pressure for a number. |
| **2. T3 Plumber → negotiation → acceptance** | **FAIL — real bug** | Turn 2 quote is correct ($345). **Turn 3 negotiation pushback was NOT detected**: step stayed at 0, AI held firm at $345 instead of stepping to neg_1 (~$302). Acceptance on Turn 4 also didn't flag `quote_accepted` for Slack handoff. |
| **3. T1 Dentist exception** | **FAIL — real bug** | Engine + selector together missed the T1 written-quote exception. Selector picked $490 (in band, but >$450), so the engine phone-routed. Spec says this lead should have gotten a $400-$450 written quote. |

Net: **1 of 3 conversations passes** on spec-critical behavior. Two bugs exposed that the 150-test suite did not catch because:
- The negotiation tests test the engine in isolation with `negotiation_step` pre-set. They don't test the classifier that's supposed to bump the step.
- The T1 exception tests pass `adaptive_price_usd=450` directly to the engine. They never tested the selector's awareness of the exception range.

---

## Conversation 1 — T1 Dentist (over-month, text-only) → phone-call route

**Lead**: Sarah Chen / Bright Smile Dental Group, 2 reviews, both text-only, both over 1 month old.
**Expected**: All pricing turns route to phone, no $ figure in any draft, AI pivots to "specialist will call".

### What the AI produced

**Turn 1 first-touch** (no inbound):
> Hi Sarah,
>
> We have your Google Business Profile for Bright Smile Dental Group. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is confirmed down.
>
> Would you like to go over pricing, or would a quick call with a specialist work better?

**Verdict**: Clean. Identifies the business, states the pay-after-removal anchor, offers two next steps without pre-committing to anything. SC passed first attempt.

**Turn 2 lead asks "What does it cost?"**:
- Commercial result: `phone_call_threshold_triggered=True`, `authorized_quote=null`, `salesman_recommended_range=(480, 530)`, `salesman_recommended_opening=$520`.
- Adaptive selector reasoning: "T1 dentist, 2 text-only reviews both over 1 month old, cooperative tone, biasing toward upper band for harder older reviews at $520."
- SC caught two issues on attempt 1 ("hedged pricing intro 'for a profile like ...'" + body too long), fixed on attempt 2.

Final draft:
> Hi Sarah,
>
> For Bright Smile Dental Group, I want to make sure I give you an accurate quote based on the full picture. Your specialist will walk you through the pricing on a quick call - I can get one on the calendar for first thing tomorrow morning.
>
> What I can confirm: you only pay after each review is confirmed down. No removal, no charge.
>
> Does tomorrow morning work, or is there a better time?

**Verdict**: This is almost verbatim the spec's prescribed pivot copy ("Your specialist will walk you through the pricing on a quick call. I can get one on the calendar for first thing tomorrow morning."). Zero dollar figures. Pay-after-removal reinforced. **Solid pass.**

**Turn 3 lead presses harder: "I'd really like a ballpark figure before setting up a call. Can you just tell me what to expect?"**:
- Commercial: same phone-routed result, adaptive picked $525 this time (still upper end).
- SC caught the hedged "for a profile like" again, fixed on attempt 2.

Final draft:
> Hi Sarah,
>
> For Bright Smile Dental Group, I want to make sure I give you an accurate quote based on the full picture. Your specialist will walk you through the pricing on a quick call - I can get one on the calendar for first thing tomorrow morning.
>
> What I can confirm: you only pay after each review is confirmed down. No removal, no charge.
>
> Does tomorrow morning work, or is there a better time?

**Verdict**: **This is identical to Turn 2's body — word for word.** The lead explicitly escalated ("I'd really like a ballpark figure") and the AI sent the exact same template. A human reviewer would read this and ghost. The threshold gate held, but the AI failed to acknowledge the lead's pressure. Spec v2 Section 4 says "qualifies the lead, builds engagement, expresses confidence in the removal, and pushes toward a phone call" — Turn 3 needed an extra confidence/urgency beat ("I genuinely can't give you an accurate number without seeing the review content with you — I'd be doing you a disservice. 8am or 9am tomorrow?"). The current copy just repeats itself.

**Conversation 1 final**: **Pass on the most important behavior (no $ in writing).** Weakness: repetitive copy when the lead pushes back twice. Not spec-failing but a real product gap.

---

## Conversation 2 — T3 Plumber → written quote → negotiation → acceptance

**Lead**: Joe Martinez / Acme Plumbing Co, 3 reviews, 2 of which are image+recent, 1 is text+over-month.
**Expected**: Turn 2 written quote ~$330-$370 (lower-mid for image+recent), Turn 3 pushback bumps to step 1 (≈87.5% off, ~$302), Turn 4 detects acceptance and signals invoice handoff.

### What happened

**Turn 1 first-touch**:
> Hi Joe,
>
> Got your profile for Acme Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down.
>
> Want to go over pricing and next steps? Reply here or let me know a good time for a quick call.

**Verdict**: Tight, direct, no fluff. Pass.

**Turn 2 lead asks price**:
- Commercial: `authorized_quote=$345`, `can_quote=True`, `phone_call_triggered=False`.
- Adaptive selector picked $345: "T3 plumber, 3 reviews with 2 images and mostly-under-1-month recency, cooperative tone, image+recency modifiers bias lower, landing at $345 near lower-mid of band."
- SC passed first attempt.

Final draft:
> Hi Joe,
>
> For Acme Plumbing Co, the rate is $345 USD per review. You only pay after each one comes down - no charge if a review doesn't get removed.
>
> Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.
>
> Want to move forward on all three? Reply here or let me know a good time to talk.

**Verdict**: **Excellent.** Direct naming (not hedged), USD primary, pay-after-removal, exact approved under-1-month timeline paragraph verbatim, soft close. Adaptive selector's reasoning matches what spec v2 Section 5 asks for (image+recency biases lower in band). Pass.

**Turn 3 lead pushes back: "That feels a bit steep for us. Is there any flexibility on the per-review rate?"**

**This is where it breaks.**

The commercial result shows `negotiation_step=0` (still!) and `authorized_quote=$345`. The adaptive selector did re-classify the tone as "price_sensitive" but the pipeline did **not** bump the negotiation step. Expected behavior per spec v2 Section 7: pushback 1 → step 1 → drop ~10-15%. The engine's step ladder works (`apply_negotiation_step` was tested green) — but the pipeline upstream never told it the step had changed.

Final draft:
> Hi Joe,
>
> $345 USD per review is the rate for Acme Plumbing Co. That holds firm - and you only pay after each review is actually down, so there is no upfront risk.

**Verdict**: **Spec violation.** The AI held firm at $345 instead of stepping to ~$302 (87.5% × 345). The pipeline's pushback classifier (`is_negotiation_pushback` and the LLM `classify_commercial_engine_turn_llm`) did not flag "Is there any flexibility on the per-review rate?" as pushback. This is a real bug — that phrasing is textbook negotiation pushback.

**Production impact**: leads who say "any flexibility?" get the same firm price instead of an authorized discount. Deals that could close at $302 are being held at $345, increasing ghost rate.

**Turn 4 lead accepts: "Okay, that works. Let's move forward at that rate."**:
- State updates: `negotiation_step=0`, no `ai_conversation_state=quote_accepted`.
- Pipeline did NOT signal quote acceptance.

Final draft:
> Hi Joe,
>
> Great - let's get started. DocuSign is sent at the close. Your specialist will reach out shortly to finalize the removal brief for all three reviews and get things moving.

**Verdict on copy**: Spot-on. Uses the spec's exact DocuSign line ("DocuSign is sent at the close."), references the removal brief (not "contract"), commits to specialist handoff. **But the integration layer never received a `quote_accepted` signal**, so:
- No `lead_status="quote_accepted"` write to DB
- No `send_invoice_handoff` Slack message fires
- The lead is left in `ai_engaged` status

Looking at why: the pipeline only runs `detect_quote_acceptance_llm` when `wants_price=True` AND `quoted_previously_flag=True`. The simulator set `wants_price=False` on Turn 4 (a deliberate choice — the lead isn't asking about price), so the acceptance check was skipped. **In production this would also skip** because the inbound message doesn't ask for a price.

**Conversation 2 final**: **Two real bugs.**
1. Pushback classifier misses common phrasings like "any flexibility on the rate?" → negotiation step never bumps → AI holds firm at opening price.
2. Acceptance detection is gated on `wants_price=True`, but acceptance messages typically have `wants_price=False`. The trigger logic is inverted.

---

## Conversation 3 — T1 Dentist exception (2 image+recent reviews)

**Lead**: Maria Lopez / Sunshine Family Dentistry, 2 reviews, both image+under-1-month.
**Expected**: Turn 3 engine recognizes T1 exception, allows AI to quote $400-$450 IN WRITING (not phone-route).

### What happened

**Turn 1 first-touch**:
- SC caught em-dash on attempt 1, fixed on attempt 2. Good.

Final draft:
> Hi Maria,
>
> We have your Google Business Profile for Sunshine Family Dentistry. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actually down.
>
> We can walk you through pricing and next steps on a quick call, or you can reply here and we will get the details over to you.

**Verdict**: Clean. Pass.

**Turn 2 lead asks "How fast can these come down?"**:
- SC logs show a JSON repair retry on attempt 1 (the SC LLM returned malformed JSON), repaired on retry. Not great but recovered.

Final draft:
> Hi Maria,
>
> Reviews with photos of items you don't serve are a strong policy violation signal - that works in your favor.
>
> Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window.
>
> You only pay once a review is actually down - no charge if it doesn't come down. Reply here or let me know a good time for a quick call and we can go over pricing for both reviews.

**Verdict**: Recognizes the image-photo angle as a policy violation signal (spec v2 Section 12 approved framing addition). Uses the exact under-1-month timeline paragraph verbatim. Pay-after-removal anchored. **Pass.**

**Turn 3 lead asks "What's the cost per review?"**

**This is the second real bug.**

Commercial result:
```
phone_call_threshold_triggered: true
authorized_quote: null
salesman_recommended_range: [480, 530]
salesman_recommended_opening_usd: 490
```

The adaptive selector picked **$490** with reasoning: "T1 dentist, 2 reviews both image+under-1-month, urgent tone, high engagement; image+recency modifiers bias lower end of band, landing at $490 for fast close."

Then the engine runs `phone_call_threshold_applies($490, T1, review_count=2, all_image_or_recent=True)`:
- $490 > $400 → check exception
- T1 ✓, review_count ≤ 2 ✓, all_image_or_recent ✓
- price ≤ $450? **$490 > $450 → exception does NOT apply**
- → threshold triggers → phone route

**The selector and the engine are talking past each other.** Spec v2 Section 4 says T1 leads with 2 image+recent reviews "may quote up to $450 maximum via text or email." The selector picked $490 because it doesn't know about the exception's $400-$450 corridor — it just lower-end-biased the standard $480-$530 band. The engine then correctly applies the rule it knows, which kicks $490 into phone-route.

Final draft the lead saw:
> Hi Maria,
>
> For Sunshine Family Dentistry, I want to make sure I give you an accurate quote based on the full picture. Your specialist will walk you through the pricing on a quick call. I can get one on the calendar for first thing tomorrow morning.

**Verdict**: **Spec violation.** This is exactly the kind of lead the spec wanted to capture with a fast written close — 2 fresh image reviews, urgent tone, high engagement. The spec's rationale was explicit: "these are simple, high-margin jobs where the lead's profile makes the removal straightforward, and a fast written close at $400-$450 is better than waiting for a morning call." Instead the AI delayed to a phone call. Deal momentum potentially lost.

**Production impact**: every T1 lead with 1-2 image+recent reviews gets phone-routed instead of written-closed. The narrow but high-value exception path is dead code.

---

## Root-cause summary

### Bug A: Adaptive selector unaware of T1 written exception (Conversation 3)

**Where**: `reviewarmour/conversation.py::AdaptivePriceSelector._run_adaptive_selector_if_eligible` passes the standard band ($480-$530) to the selector regardless of whether T1 exception conditions are met.

**Fix sketch**: Before calling the selector, check `lead.all_reviews_image_or_recent() and lead.review_count <= 2 and config.tier == T1`. If true, expand the lower bound of the range passed to the selector down to `floor_usd` ($400) and add a hint to the prompt explaining the exception ("you may quote $400-$450 in writing for fast close"). The selector then has a real choice between $400-$450 (written close) and $480-$530 (phone route).

### Bug B: Negotiation pushback classifier misses "any flexibility?" phrasings (Conversation 2 Turn 3)

**Where**: `reviewarmour/conversation.py::is_negotiation_pushback` (deterministic phrase list) AND `classify_commercial_engine_turn_llm` (LLM classifier).

**Fix sketch**: Add common pushback phrasings to the deterministic list ("flexibility", "wiggle room", "best price", "can you do better", "anything you can do", "give a discount"). The LLM classifier prompt should explicitly include "flexibility / wiggle room / can you do better" as pushback examples.

### Bug C: Quote acceptance detection gated on `wants_price=True` (Conversation 2 Turn 4)

**Where**: `OutboundPipeline.run` — the acceptance classifier is only invoked when the inbound turn is classified as a pricing turn. Acceptance ("ok, let's do it") doesn't look like a pricing question, so it's never checked.

**Fix sketch**: Run the acceptance classifier whenever the lead has a previous authorized quote in transcript, regardless of `wants_price` on the current turn. This is roughly: `if quoted_previously: try_acceptance_classifier_before_routing`.

### Weakness D: Identical draft on repeated phone-route turns (Conversation 1 Turn 3)

**Where**: `ConversationModule.draft` — produces near-identical output when the commercial snapshot and lead state are unchanged across turns, even though the lead is escalating pressure.

**Fix sketch**: Include the assistant's previous outbound (`transcript[-1]` when `role=assistant`) in the prompt with a directive: "DO NOT repeat your last outbound verbatim. If the lead is pressing for the same information you've already declined to give in writing, acknowledge their pressure and increase confidence/urgency on the phone-call ask. Suggest a specific time."

---

## What the auto-test suite missed (and why)

The 121 deterministic + 29 live tests gave high confidence the engine, SC pre-checks, and adaptive selector each work in isolation. But:

- **Bug A** was missed because the live B22 test (T1 exception writes $450) passes `adaptive_price_usd=450` directly into the engine, bypassing the selector. The selector itself was never asked to find a $450-tier exception price.
- **Bug B** was missed because the live B4/B5 tests pre-set `negotiation_step=1` or `2` on the lead. They test that the engine discounts correctly given a step. They never test that the pipeline correctly bumps the step in response to a real lead message.
- **Bug C** was missed because there's no live test for the acceptance → invoice handoff loop. The deterministic suite checks `acceptance_signal()` but never runs the full pipeline through a `quote → "ok let's go"` sequence.
- **Weakness D** was missed because no test compares two consecutive phone-route drafts to confirm they're meaningfully different.

These are exactly the kinds of multi-turn behaviors a hand-driven conversation surfaces that a per-test fixture can't. The fix: add a small handful of multi-turn live tests in `test_live_flows_v2.py` modeled after these three conversations, with assertions on (1) draft uniqueness across turns, (2) negotiation step actually bumping, (3) acceptance triggering `state_updates["ai_conversation_state"]="quote_accepted"`.

---

## Recommendation

Three follow-up commits, smallest first:

1. **Bug B** (negotiation phrasing) — 30-minute fix. Add 6 phrases to the deterministic pushback list + sentence in classifier prompt. Add a regression test that runs "any flexibility" through `is_negotiation_pushback` and through a live pipeline turn.
2. **Bug C** (acceptance gating) — 1-hour fix. Move acceptance classifier call to fire whenever a quote is in the transcript, not gated on `wants_price`. Add a multi-turn live test.
3. **Bug A** (T1 exception in selector) — 2-hour fix. Pass the expanded $400-$530 range to the selector when T1 exception conditions are met, with prompt hint. Add multi-turn live test for an exception-eligible lead asking for the price.

**Weakness D** can wait — it's a quality issue, not a spec violation, and depends on the conversation history being passed into the draft prompt (which may need a structural change).
