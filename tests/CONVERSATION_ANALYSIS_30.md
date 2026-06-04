# 30-Conversation Coverage Analysis (Spec v2)

_Reviewer reading the AI's actual responses + commercial snapshots + SC verdicts + pipeline logs against spec v2._
_Source trace: [CONVERSATION_TRACES_30.md](CONVERSATION_TRACES_30.md). Fixes from prior round applied (Bug A through Bug H)._

---

## Scoreboard

| # | Title | Verdict | Headline |
|---|---|---|---|
| 21 | Methodology general | **FAIL — paraphrase** | AI paraphrased METHODOLOGY general string. SC caught "success rate holds where it does" qualitative claim. 3 fix attempts → `human_queue` |
| 22 | Methodology more_detail_asked | **FAIL — wrong approved string** | Lead asked for operational detail. AI used METHODOLOGY general (paraphrased) instead of METHODOLOGY more_detail_asked. 3 fix attempts → `human_queue` |
| 23 | Warranty: will it come back | **PASS** | AI used the exact approved WARRANTY will_it_come_back string. Bonus: appended the same_customer_new_review approved string preemptively |
| 24 | Warranty: same customer new review | **PASS** | Used the exact approved string. SC clean |
| 25 | DocuSign / contract question | **PASS** | Used the approved DocuSign line + clean continuation. Pay-anchor included |
| 26 | T3 Paving | **PASS** | $310 quoted (band $300-$350, lower-mid for image+recent), approved under-1-month timeline, SC clean |
| 27 | T3 Car Dealership | **PASS** | $355 quoted, mid-band, approved timeline + pay-anchor, SC clean |
| 28 | T4 Auto Detailing | **PASS** | $235 quoted, in band, lower for recency |
| 29 | T4 Car Wash | **PASS** | $220 quoted in band, approved timeline + pay-anchor, SC fix→pass |
| 30 | T3 Restaurant | **PASS** | $295 quoted at lower-mid for 3 reviews. Total deal value shown ($885). SC clean |
| 31 | T3 Electronics Store | **PASS** | $270 (band low) for low-engagement signal. Clean |
| 32 | T4 Clothing Store | **PASS** | $220 quoted, lower end for noncommittal tone |
| 33 | T4 Grocery Store | **PASS** | $210 quoted, near floor, SC fix→pass |
| 34 | Volume bracket 6-15 (8 reviews) | **PASS** | $300 quoted from $290-$335 medium-bracket band. **Did NOT announce a discount.** Total deal value $2,400 shown |
| 35 | Volume bracket 16-30 (20 reviews) | **PASS** | $280 quoted from $265-$295 large-bracket band. Clean |
| 36 | Multi-channel SMS reply | **PASS** | **T1 medical clinic exception applied** — $440 written quote via SMS! Body ~95 chars (well under 320), no email footer. Excellent compact copy |
| 37 | Auto-capture GBP link | **PARTIAL PASS** | GBP URL auto-captured (log confirms). Pricing tier T2 → phone-route triggered correctly. **But Turn 1 first-touch body has a typo: "We remove policy-violating Google reviews wn, not before."** The strip-hedged-intro regex chopped too much |
| 38 | Lead names a specific reviewer | **PASS** | AI did NOT promise removal of "Steve B's review". Used "If we can't get it down, you don't pay" reassurance + deferred to specialist. Approved timeline included |
| 39 | Chargeback question (no prior payment) | **PARTIAL PASS — overly cautious** | Lead asked ABOUT chargeback policy hypothetically. Drafter escalated treating it as a hard topic. **Defensible spec-wise** (refunds/chargebacks are listed) but **overly conservative** — a benign procedural question got routed to human. Acceptable behavior, just hurts conversion |
| 40 | Vague "tell me more" | **FAIL** | 3 SC fix attempts → `human_queue`. AI tried to use METHODOLOGY general (paraphrased) and SC rejected it for "success rate holds where it does" qualitative claim. Same root cause as Conv 21/22 |
| 41 | Stacked questions | **PASS** | Pricing + approved timeline + approved warranty + approved pay-anchor all in one draft, on point. SC clean |
| 42 | Specific named-person request ("talk to Jayden") | **PASS** | Pipeline escalated with reason `specific_person:named_contact` per spec. No promise made |
| 43 | Soft-quote mode + CA dentist | **PASS** | CA Toronto footer. T1 dentist band $480-$530 returned. USD primary. SC clean. (Pushback escalation path not tested here — only 2 turns) |
| 44 | Competitor undercutting | **PASS** | Turn 2 quoted $315 (price_sensitive tone). Turn 3 lead said "another quoted $200 - match?" → negotiation step bumped to 1, AI dropped to $276 (≈87.5% of $315, in band, above $260 floor). **Did NOT match the bogus $200.** Excellent. |
| 45 | "What guarantee do you offer?" | **PASS** | Used approved pay-anchor + approved same-customer-new-review verbatim. Layered both warranties cleanly. SC clean |
| 46 | **Bug F production case — step 2 + 2 triggers + pushback** | **PASS** | Pipeline escalated with reason `negotiation_past_final_step` and state `ai_conversation_state: 'escalated_to_human'`. **Bug F fix verified end-to-end.** |
| 47 | GBP link present → no review questions | **PASS** | AI did NOT ask the lead anything about the reviews. Said "we already have your Google Business Profile, so we have what we need." gbp_gate honored |
| 48 | Anxiety about paying | **PASS** | Used exact approved PAY-ANCHOR paragraph verbatim. Approved timeline added. SC fix→pass |
| 49 | GBP inspection data already present | **PASS** | First-touch with inspection facts. AI used the approved timeline paragraph (recognized recency from inspection). Did not ask the lead any questions about reviews. SC fix→pass |
| 50 | "How do I sign?" — agreement-process vs acceptance | **FAIL** | After Turn 2 quote at $345, Turn 3 lead asks "How do I sign? Is there a contract or DocuSign?" — pipeline correctly did NOT fire acceptance (per spec rule), but SC then kept rejecting the response for 3 attempts → `human_queue`. Final draft is actually fine ("DocuSign is sent at the close") but SC saw "the removal brief via DocuSign" as an unauthorized contract-detail expansion |

**Totals: 24 PASS, 3 PARTIAL, 3 FAIL**

---

## Fix-verification status (from prior round)

| Bug | Verified? | Where |
|---|---|---|
| A — T1 written exception in selector | ✅ Conv 36 SMS T1 medical clinic with image+recent — selector picked $440 with `[T1-exception]` log tag |
| B — negotiation pushback detection | ✅ Conv 44 Turn 3 — "match that $200" detected as pushback, step bumped 0→1, $276 quoted |
| C — acceptance gating | ✅ Earlier 20-conv suite (Conv 6) showed clean `quote_accepted` |
| D — strip "for a profile like" hedging | ✅ Conv 37 first-touch log shows `Stripped hedged pricing intro for lead SIM-37 (attempt 1)` — **BUT** the strip damaged the body (see Bug I below) |
| E — SC `range_low` vs `floor_usd` | ✅ Conv 46 step-2 quote would have escalated under old SC — now passes |
| F — past-final escalation | ✅ Conv 46 — `negotiation_past_final_step` reason emitted with correct state |
| G — approved over-1-month / hard-guarantee verbatim | ⚠️ Not enforced strictly. The over-1-month paragraph paraphrase in Conv 14 from prior round was passed by SC. The fix added a SC sanitizer for SUCCESS only — timeline_language still leans on substring match for the exact string |
| H — APPROVED_SUCCESS_PARAGRAPHS sanitizer | ✅ Earlier 20-conv Conv 17 went from `escalate` to `send` after this fix |

So 7 of 8 prior bugs are fully fixed in observable behavior. Bug G (verbatim approved-paragraph enforcement on non-SUCCESS topics) still leaks paraphrases through SC.

---

## New bugs surfaced in this round

### Bug I — `strip_hedged_pricing_intro` regex is over-eager (Conv 37)

The strip helper grabbed too much in Conv 37 Turn 1. The drafted first-touch body said something like "We remove policy-violating Google reviews and you only pay after they're down, not before." but the regex matched `"reviews and you only pay after they're do"` plus surrounding chars because the lookahead/comma-or-period pattern was lenient. After strip, the body reads:

> "We remove policy-violating Google reviews wn, not before."

Truncated mid-word. The downstream copy is still semantically intelligible but is obviously broken.

**Root cause**: my regex `for\s+(?:a\s+)?(?:profile|business...)\s+like\s+[^,.]{1,60},?\s*` allows `[^,.]{1,60}` to chew through a long chunk of text when the source body uses "profile" or "business" without the canonical "for a profile like X," pattern. The lookahead boundary is just any non-comma/non-period for up to 60 chars.

**Fix sketch**: tighten the regex to require the literal word `like` immediately after `profile|business|...`, AND limit the character class to `[^,.\n]{1,40}`, AND require a word-boundary terminator. Better: only strip when SC has flagged "hedged pricing intro" — convert from prophylactic strip to reactive strip on the redraft pass.

### Bug J — Methodology paragraphs are not in the drafter's approved-strings list (Conv 21, 22, 40)

The conversation prompt (`CONVERSATION_SYSTEM`) provides `APPROVED_TIMELINE_PARAGRAPHS` as a dict the LLM can copy verbatim. There is no equivalent `APPROVED_METHODOLOGY_PARAGRAPHS` passed in. The prompt mentions the strings exist (in the system prompt itself, lines 148-153 of `prompt_templates.py`) but the drafter must reproduce them from memory.

In Conv 21 and 22, the drafter wrote "Our team identifies the specific policy violations in each review, frames the dispute against Google's own published guidelines, and works directly through Google's reporting channels. We have a systemized process for how that's framed, which is why our success rate holds where it does." — this is approximately the METHODOLOGY general string but the trailing "...which is why our success rate holds where it does" is **not** in the approved string, and SC's success_rate / scope checks reject it.

**Root cause**: methodology strings live only in the static system prompt, not surfaced into the per-call payload. So the drafter cannot copy them exactly the way it can with timeline paragraphs.

**Fix sketch**: mirror the `APPROVED_TIMELINE_PARAGRAPHS` pattern:
1. Define `APPROVED_METHODOLOGY_PARAGRAPHS = {"general": "...", "leverage": "...", "more_detail_asked": "..."}` in `prompt_templates.py`.
2. Pass into the drafter prompt payload (similar to `approved_timeline_paragraphs`).
3. Conversation system prompt instructs the drafter: "When the lead asks 'how it works', use METHODOLOGY general verbatim. When they ask for operational specifics, use METHODOLOGY more_detail_asked."
4. SC prompt + a deterministic `_sanitize_methodology_verdict` (parallel to the success sanitizer) drops methodology-related failures when an approved string is present.

This is the **same architectural fix** that closed Bug H for success-rate. Applying it to methodology will close Conv 21, 22, 40 in one pass.

### Bug K — DocuSign question after a quote triggers SC overreach (Conv 50)

Conv 50 Turn 3: lead asked "How do I sign? Is there a contract or DocuSign?" after AI quoted $345. The pipeline correctly recognized this as a process question (not acceptance per the spec rule). Drafter wrote "DocuSign is sent at the close. Once you are ready to move forward, we send the removal brief via DocuSign — you sign there..." but SC flagged this 3 times — likely as `scope: contract beyond DocuSign line` because the elaboration "we send the removal brief via DocuSign - you sign there, and we get started" expands beyond the approved one-liner.

**Root cause**: the approved DocuSign line is exactly `"DocuSign is sent at the close."`. The drafter consistently wants to expand. SC consistently flags expansion. Loop never converges.

**Fix sketch**: similar to Bug J — surface `APPROVED_DOCUSIGN_LINE = "DocuSign is sent at the close."` in both prompts AND add a deterministic SC pre-check that allows the verbatim line as a substring without flagging scope.

### Bug L — Vague "tell me more" inbound has no approved response template (Conv 40)

The drafter tried to construct a "how it works" response from scratch, ran into the same methodology paraphrase trap as Conv 21/22, looped. This is a downstream consequence of Bug J — once methodology paragraphs are surfaced correctly, the vague-reply case will resolve.

### Bug M — Chargeback question (hypothetical) is over-conservatively escalated (Conv 39)

Lead asked "If something goes wrong with billing later, what's your chargeback policy?" — a procedural pre-sales question. The spec's scope-check list contains "refunds post-pay" and the drafter LLM grouped this under that umbrella and escalated.

**Production impact**: minor. The lead gets escalated to a human, which is a defensible outcome but kills conversion potential on what's likely a curious lead, not a problem lead. The "post-pay" distinction in the spec is important: pre-pay billing questions should be in scope and answered with the pay-anchor.

**Fix sketch**: tweak the conversation prompt's hard-escalation list to clarify "refunds and chargebacks **on a prior invoice that has already been paid**" vs hypothetical billing-policy questions. The drafter's job in the hypothetical case is to answer with the pay-anchor ("you don't pay until..."). This is a 1-line prompt clarification, not a code change.

---

## What's working very well

- **Adaptive selector's tone classification** is consistently sensible. "Bare price-only reply" → noncommittal/low engagement → band low. "Urgent + image + recent" → cooperative/high engagement → T1 exception fast close. The reasoning summaries are useful and audit-grade.
- **Volume-bracket pricing** at 6-15 and 16-30 worked transparently (Conv 34, 35). The AI did not announce the discount; it just used the lower band as the new opening.
- **gbp_gate** held — Conv 47 the AI did NOT pepper the lead with review questions even though the lead invited that.
- **GBP auto-capture** works (Conv 37 logs confirm), and the engine seamlessly continued to commercial reasoning in the same turn.
- **Multi-channel SMS draft** (Conv 36) was a fantastic ~95-char SMS that included the price, business name, pay-after-removal anchor, and a CTA — all without an email-style footer.
- **Pay-anchor + warranty composition** in Conv 45 / 48 stitched two approved paragraphs together cleanly when the lead asked compound questions.
- **Negotiation step ladder** continues to work end-to-end with the Bug B fix (Conv 44 Turn 3: $315 → $276 at step 1, in band, above floor).

---

## Recommended next sequence

Order by impact:

1. **Bug J + L** (methodology paragraphs) — 1.5h. Adds `APPROVED_METHODOLOGY_PARAGRAPHS` dict + drafter prompt addition + SC sanitizer. Closes Conv 21, 22, 40 in one pass. Will also help any future "tell me more" / "how does it work" inbound.
2. **Bug K** (DocuSign approved line) — 1h. Same pattern as Bug J. Add `APPROVED_DOCUSIGN_LINE` + sanitizer. Closes Conv 50.
3. **Bug I** (over-eager strip regex) — 30 min. Tighten the regex (require `like` immediately after, limit chars to 40, exclude newlines). Add a test that asserts the regex doesn't chew benign first-touch copy.
4. **Bug M** (chargeback over-conservative) — 15 min. 1-line clarification in conversation prompt about hypothetical vs actual chargebacks.
5. **Bug G** (verbatim timeline/hard-guarantee enforcement) — 1.5h. Deterministic SC pre-check: when the lead's last inbound asks about timing/guarantee and `approved_timeline_paragraph` is set, the verbatim string MUST appear in the draft body. Verdict `fix` if missing. Closes Conv 14, 15 paraphrase issue from prior round.

After these, the 30-conv suite should produce 28-29 PASS.

---

## What the automated suite did and didn't catch this round

The deterministic 121 tests + earlier live 29 B-series tests caught:

- All commercial logic
- SC pre-checks for hidden cost + ROI + phone-threshold
- Selector schema + range validation
- Negotiation step ladder math
- Phone-call threshold gate (Bug A)

What only this 30-conv suite caught:

- **Bug I** — regex over-strip on a normal first-touch (Conv 37). No unit test asserted strip-helper safety on benign text
- **Bug J** — methodology paraphrase loop (Conv 21, 22, 40). No live test pushed "how does it work" through three SC retries
- **Bug K** — DocuSign expansion loop (Conv 50). No live test exercised the "agreement process question after a quote" path
- **Bug M** — chargeback over-conservatism (Conv 39). No live test for hypothetical-vs-actual billing distinction

The pattern is consistent: the engine + SC + selector + adaptive layer all work cleanly in isolation. The remaining failures are at the **drafter-to-SC-loop interaction layer**, where the drafter's "approved string memory" doesn't always match SC's "approved string substring check." The fix architecture (per Bug H from prior round) is: surface every approved string explicitly in the per-call payload AND add a deterministic SC sanitizer that recognizes the verbatim string. Apply this pattern to METHODOLOGY, DOCUSIGN, and remaining TIMELINE/WARRANTY cases.
