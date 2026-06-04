# Full Coverage Analysis — 20 Live Conversations (Spec v2)

_Reviewer reading the AI's actual responses + commercial snapshots + SC verdicts + pipeline logs against spec v2._
_Source trace: [CONVERSATION_TRACES_FULL.md](CONVERSATION_TRACES_FULL.md). Bug fixes applied: A (T1 exception selector), B (negotiation pushback transcript-key fix), C (acceptance gating)._

---

## Scoreboard

| # | Title | Verdict | One-line finding |
|---|---|---|---|
| 01 | CA T3 Hotel → quote → acceptance | **PASS** | CA Toronto footer, $320 quoted, `quote_accepted` fired, DocuSign-style confirmation |
| 02 | T4 Nail Salon written quote | **PASS** | T4 $210 quoted (band-low), floor honored, clean copy |
| 03 | T2 HVAC phone route | **PASS** | No $ in draft, exact spec-prescribed pivot copy |
| 04 | T1 Plastic Surgeon phone route | **FAIL — new bug exposed** | Pipeline outcome `human_queue` after 3 SC fix attempts — SC keeps flagging hedged "for a profile like" but the LLM redrafter can't shake it. Same pattern hit Conv 1 Turn 3 originally |
| 05 | Soft-quote mode band reply | **PARTIAL PASS** | Returned a band ($390-$440) — but the band is the T2 ROOFING band, not the spec's "best within tier range" framing; missing the `for {business_name}` direct-naming rule was about to fire but the copy chose "the range is typically $X-$Y" — only **2 turns**, no pushback test. Inconclusive on negotiation escalation. |
| 06 | Full negotiation ladder | **MOSTLY PASS — one mid-failure** | Steps 0→1 worked ($340 → $298). **Step 2 failed**: SC escalated because the adaptive selector picked band-floor $330 but then the engine clamp produced $260 which is below `range_low_usd=$330`, and SC's pricing check flagged it. Acceptance on Turn 5 fired correctly via the post-quote acceptance path. |
| 07 | Pushback past step 2 → escalate | **FAIL — wrong escalation reason** | Pipeline outcome `escalate` but the reason was SC's copy_rules ("lowest we can go" disclosed floor), not the spec's `negotiation_past_final_step`. Lead is at step 2 but `wants_price=True` with no prior quoted_previously context — the pushback detector never gated. |
| 08 | Missing GBP link | **PASS** | `request_gbp_first=true`, AI asks for the link with concrete instructions ("search your business on Google Maps and copy the URL") |
| 09 | Unknown category | **PASS** | `request_category_first=true`, AI asks for business type with examples (dental/legal/etc.) |
| 10 | ai_quote_allowed kill switch | **PASS** | Pipeline escalates immediately with `reason=ai_quote_allowed_kill_switch`. Draft action=escalate. |
| 11 | Legal escalation | **PASS** | Pipeline escalates with `reason=legal_escalation:lawyer`. Hard-trigger working. |
| 12 | Refund/chargeback escalation | **PASS** | Pipeline escalates from the drafter (LLM-routed), reason mentions "post-payment dispute requiring human handling" |
| 13 | Timing question (under 1 month) | **PASS** | AI used exact approved paragraph verbatim: "Reviews this recent typically come down within two to four weeks. Some take a bit longer, but that is the standard window." |
| 14 | Timing question (over 1 month) | **PARTIAL PASS — near-miss on verbatim** | AI used "For reviews this age, we typically see them come down within around two weeks, though it can take up to a month depending on the case." This is **semantically right but NOT verbatim** the approved over_1_month paragraph. The SC let it through (a1=pass) but that's only because the LLM's wording was close enough — strict spec compliance would require the exact spec string. |
| 15 | Hard guarantee request | **PASS** | AI did NOT promise a date. "I can't commit to a specific day. What I can tell you is the typical window." Approved hard_guarantee framing semantics intact. |
| 16 | Pay-after-removal question | **PASS** | AI used the exact approved pay-anchor paragraph verbatim: "You don't pay until the review is actually down. We send you a screenshot link confirming the removal, and your invoice goes out at that point — not before. That's how we structure every job." |
| 17 | Success-rate question | **FAIL** | After 3 SC attempts the pipeline escalated. AI couldn't produce a draft that uses the verbatim approved SUCCESS paragraph. Final draft contains "We have a high success rate" — qualitative claim outside approved strings — SC correctly caught this and escalated. But spec wanted the AI to use the approved SUCCESS paragraph and stay in scope. This is a drafter-side gap, not an SC gap. |
| 18 | Off-topic redirect | **PASS** | AI sent brief polite redirect: "That is outside what we handle - we focus exclusively on Google review removal. On the review side, did you want to go over pricing or next steps for Sunny Day Cafe?" Did NOT escalate. |
| 19 | SMS first touch | **PASS** | 184 chars (well under 320), no email-style footer, direct ask. |
| 20 | T1 exception (1 review image+recent) | **PASS** | **Bug A fix verified again**: `phone_call_threshold_triggered=false`, AI quoted **$440** in writing, reasoning contains "T1 written exception fast close" tag. Approved under-1-month timeline paragraph included verbatim. |

**Totals**: 13 PASS, 3 PARTIAL PASS, 4 FAIL/regressed paths.

---

## Detailed findings

### What's working (well)

- **Spec v2 phone-call threshold** held on every T1/T2 lead where it was supposed to (Conv 3 HVAC, Conv 4 plastic surgeon, Conv 6 negotiation). Zero leaked dollar figures in phone-routed drafts.
- **Bug A fix** (T1 written exception in the selector) is verified end-to-end in Conv 20: `[T1-exception]` log tag, $440 in draft, no phone-route. Adaptive reasoning explicitly mentions the exception path.
- **Bug B fix** (negotiation pushback): Conv 6 Turn 3 shows the pipeline correctly bumped `negotiation_step` from 0 → 1 in response to "That feels a bit steep for us. Any flexibility?" and the AI dropped from $340 → $298 (≈87.5% off — exactly the spec's step-1 ladder).
- **Bug C fix** (acceptance gating): Conv 1 Turn 3 and Conv 6 Turn 5 both fired `ai_conversation_state: 'quote_accepted'` and the AI's confirmation draft references DocuSign correctly. The Slack invoice handoff would now actually fire.
- **Footer routing** works: CA leads get Toronto address, US leads get Miami. Both observed.
- **Hard escalations** (legal, refund) fire deterministically with the right reason codes.
- **Operator guardrails** (kill switch, GBP missing, category missing) all behaved correctly without LLM intervention.
- **SMS channel** produced a 184-char body without an email-style footer — adaptive length handling is good.

### What's not working

#### Bug D: SC redraft loop can't shake "for a profile like" hedging (Conv 4)

Conv 4 (T1 plastic surgeon → phone route) ended in `human_queue` after 3 SC fix attempts. Every attempt produced "For a profile like Premier Plastic Surgery's, I want to make sure I give you an accurate quote..." Every attempt failed SC on `copy_rules: hedged pricing intro`.

This is the same hedging pattern that hit the original Conv 1 Turn 3. The LLM seems to *like* the "for a profile like X" intro on phone-route copy and falls back to it after a redraft. **Three retries isn't enough to break the pattern.**

**Production impact**: every high-value T1 plastic surgeon / lawyer / similar lead falls into the human queue instead of being phone-routed cleanly. That's exactly the wrong tradeoff — the spec wanted these leads engaged immediately.

**Fix sketch**: Add a deterministic post-check that catches "for a profile like" / "a profile like" / "businesses like" and either (a) hard-strips them from the draft body before sending or (b) injects an operator_directive on the next redraft attempt with the explicit forbidden phrase and a replacement template. The current SC mechanism reports the violation but the redrafter doesn't internalize it.

#### Bug E: Step-2 quote can fall below `range_low_usd` and SC then escalates the quote it asked for (Conv 6 Turn 4)

Conv 6 Turn 4: lead pushed back twice. Negotiation step bumped to 2. Adaptive selector picked $330 (band floor). Engine applied step-2 multiplier (~0.766) and clamped to tier floor $260. Result: `authorized_quote_usd_per_review=260` with `range_low_usd=330`. SC ran and **correctly** flagged: "draft price $260 is below the authorized floor of $330 set by range_low".

So the SC and the engine disagree about what "in band" means at negotiation step 2. The engine intentionally goes below `range_low_usd` toward the tier floor (per spec v2 Section 7's discount ladder). The SC prompt thinks `range_low_usd` is a hard floor for any quote.

The escalation here was technically wrong — the $260 quote is actually authorized — but the SC's check is what blocked it. From the lead's perspective the conversation died at step 2 instead of closing at $260.

**Fix sketch**: SC prompt and `_floor_breach_check` need to use `floor_usd` (the absolute tier floor) for the "below floor" check, not `range_low_usd` (which is just the band's lower edge at step 0). The deterministic `_floor_breach_check` I added in the spec v2 commit already does this right; the LLM-side SC prompt does not. Update `SELF_CORRECTION_SYSTEM` to explicitly say: "step 1/2 discounts are authorized and may fall below range_low_usd but never below floor_usd."

#### Bug F: `effective_quote_context` still won't fire on a fresh inbound when there's no prior quote in transcript (Conv 7)

Conv 7's expected behavior was "lead at step 2 pushes back again → escalate with reason `negotiation_past_final_step`." Instead the pipeline escalated for a different reason: SC caught "lowest we can go" as floor-disclosure language.

The negotiation_past_final_step path requires the pushback detector to fire, which requires `effective_quote_context(quoted_previously=False, transcript=[])` to return True. With no transcript and `quoted_previously=False`, it's False, so the pushback gate never opens. The step-already-2 lead just goes into the normal pricing flow.

This is a test-setup issue more than a production bug — in production the lead would have a transcript with prior quotes. But it does mean the **negotiation_past_final_step escalation path is not currently exercised by anything**. The escalation route in conversation.py line 1325-1340 is only reachable through paths that pre-populate transcript.

**Fix sketch**: Either (a) make the simulator inject a fake assistant quote into transcript when the lead has `negotiation_step >= 1`, or (b) re-examine whether `effective_quote_context` should treat `lead.negotiation_step > 0` as implicit context. Option (b) is the cleaner production fix.

#### Bug G: Approved timeline paragraphs are not enforced verbatim on the over_1_month / hard_guarantee paths (Conv 14, 15)

Conv 14 (over-1-month timing): AI wrote "For reviews this age, we typically see them come down within around two weeks, though it can take up to a month depending on the case." — close to spec but not the exact approved string.

Conv 15 (hard guarantee): AI wrote "I can't commit to a specific day. What I can tell you is the typical window. If anything looks like it will run past that, your specialist will reach out directly." — also close but not verbatim.

The SC let both through (`a1=pass`). The SC's deterministic `_sanitize_timeline_verdict` helper allows the LLM verdict to skip timeline_language failures **when the approved paragraph is present as a substring**. If the AI paraphrases, the substring match fails and the LLM SC verdict decides. In both Conv 14 and Conv 15, the LLM accepted the paraphrase.

The spec requires verbatim use — `SELF_CORRECTION_SYSTEM` line 261 says "that exact string ... must appear in the draft with no paraphrase." The LLM SC is being lenient here.

**Fix sketch**: Add a deterministic SC pre-check that fails any draft addressing timing/guarantee topics without the verbatim approved paragraph. The check would mirror `_phone_call_threshold_violation_check`: keyword-detect timing topics ("how fast", "when", "guarantee", "by", "deadline") in the lead's most recent inbound, then verify the approved paragraph string appears in the draft body. Fail-to-fix if not.

#### Bug H: Success-rate question doesn't terminate in a sendable draft (Conv 17)

Conv 17 escalated after 3 SC attempts. The AI kept writing variations like "We have a high success rate on reviews that fall within Google's policy violation criteria" — every variation got flagged for "invented success-rate claim outside approved SUCCESS paragraphs."

The drafter clearly doesn't have the approved SUCCESS paragraphs accessible in the conversation prompt the way it has the timeline paragraphs (lines 135-142 of CONVERSATION_SYSTEM). Spec v2 says success-rate questions should use the SUCCESS general or SUCCESS percentage_asked verbatim string — but the drafter never sees those exact strings.

**Fix sketch**: Add `APPROVED_SUCCESS_PARAGRAPHS` to `prompt_templates.py` (parallel to `APPROVED_TIMELINE_PARAGRAPHS`), include them in the `ConversationModule.draft` payload, and update the conversation prompt to require verbatim insertion when success topics appear (similar to timeline_class handling).

---

## Pattern summary across the 20

**What the AI consistently does well:**
- Direct business naming when commercial allows it ("For Acme Plumbing, the rate is...")
- Pay-after-removal anchor present in nearly every relevant draft
- Approved under_1_month timeline paragraph used verbatim (Conv 1, 13, 20)
- Footer routing US vs CA
- Hard escalations (legal, refund) routed correctly
- Quote acceptance triggers the integration handoff
- Negotiation steps bump correctly post-fix

**What the AI struggles with:**
- "For a profile like X" hedging on phone-route copy — LLM falls back to this even after SC catches it (Bug D)
- Over-1-month / hard-guarantee / success-rate verbatim paragraphs — LLM paraphrases and SC sometimes accepts (Bugs G, H)
- Edge case where `range_low_usd` and `authorized_quote_usd_per_review` disagree at step 2 (Bug E)

---

## Recommended follow-up sequence (smallest first)

1. **Bug E (SC `range_low` vs `floor_usd` mix-up)** — 30 min. One line in `SELF_CORRECTION_SYSTEM` prompt + the deterministic `_floor_breach_check` already uses the right variable, so just align prompt language. Unblocks Conv 6's step-2 close.

2. **Bug D ("for a profile like" hedging)** — 1h. Add a deterministic post-check or strip pattern. Pattern: `re.sub(r"for a profile like [^,]+,?\s*", "", body, flags=re.IGNORECASE)`. Verify Conv 4 reruns to `outcome=send`.

3. **Bug F (negotiation_past_final_step unreachable)** — 1h. Update `effective_quote_context` to treat `lead.negotiation_step > 0` as implicit context. Add a regression test.

4. **Bug G + H (approved paragraphs not enforced verbatim)** — 2h. Add `APPROVED_SUCCESS_PARAGRAPHS` + verbatim deterministic SC check. Loop in a few of these conversations as live regression tests.

After these, this same 20-conversation suite should produce **17-19 PASS** instead of 13.

---

## What the auto-test suite did vs didn't catch

Tests caught:
- All deterministic engine behavior (tier matrix, volume brackets, phone-call threshold gate, T1 exception engine-side)
- Selector schema validation (B25)
- SC pre-check logic for hidden cost + ROI + phone-threshold

Tests didn't catch:
- **Bug D** (hedging redraft loop) — no test pushes the same SC failure mode 3+ times and asserts the loop terminates
- **Bug E** (SC `range_low` confusion) — no test runs a real step-2 quote through SC with the actual prompt
- **Bug F** (negotiation_past_final_step unreachable without transcript) — no test exercises that escalation path end-to-end
- **Bug G / H** (verbatim paragraph enforcement) — the SC LLM is lenient; we never asserted the AI's draft body equals the approved string

The fix is to add ~5-10 multi-turn live tests modeled on Conv 4, 6, 14, 15, 17 that lock in the verbatim-paragraph requirement and the SC retry-loop terminator.
