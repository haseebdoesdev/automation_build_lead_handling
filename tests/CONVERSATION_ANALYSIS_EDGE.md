# 10 Edge-Case Conversations — Analysis

_Reviewer reading the AI's actual responses + pipeline logs against spec v2 boundary conditions._
_Source trace: [CONVERSATION_TRACES_EDGE.md](CONVERSATION_TRACES_EDGE.md). All prior fixes (Bug A through M + G) applied._

---

## Scoreboard

| # | Title | Verdict | Headline |
|---|---|---|---|
| **E1** | Accept mid-negotiation ($298 works for me) | **PASS** | LLM acceptance correctly identified price-anchored accept. State fires `quote_accepted`. Confirmation draft references DocuSign |
| **E2** | Angry tone + valid pricing question | **PARTIAL FAIL** | Turn 1 (first touch) → `human_queue` after 3 SC fix attempts. The drafter kept emitting `—` (em dash) and SC kept flagging it. Lead got NO first-touch response. Turn 2 (the actual angry message) handled correctly with $258 quote, "urgent" tone classification, full draft sent |
| **E3** | Actual post-pay chargeback | **PASS** | Drafter escalated with explicit reason naming "actual prior paid transaction" vs "pre-sales hypothetical". Bug M prompt fix verified |
| **E4** | Bot suspicion ("is this AI?") | **PASS** | AI was transparent: "This is an AI-assisted messaging layer, yes. A human specialist at ReviewArmour reviews every account and handles the actual removal work." Offered specialist handoff |
| **E5** | Bare "ok" with no quote in transcript | **PASS** | Acceptance correctly did NOT fire. State has no `quote_accepted`. Draft: "Glad to hear it. A specialist can walk you through pricing..." — graceful continuation |
| **E6** | Spanish-language reply mid-flow | **PARTIAL PASS** | AI responded in English with a valid $300 T3 landscaper quote + approved pay-anchor + timeline paragraph. Did NOT escalate (correct). Did NOT acknowledge in Spanish (missed engagement opportunity, not spec-violating) |
| **E7** | Pricing + legal threat in same message | **PASS** | Legal hard-trigger fired before pricing turn. `escalate` with `legal_escalation:lawyer`. NO pricing draft fired |
| **E8** | Single-word first name + empty last name | **PASS** | "Hi Madonna," — no empty trailing comma, no `Madonna ` with stray whitespace. Clean schema handling |
| **E9** | Yelp URL pasted instead of Google Maps | **PASS** | Auto-capture did NOT fire (correct — pattern matches `google.com/maps`, `maps.google.com`, `g.page` only). AI redirected: "That link goes to Yelp — we work on Google reviews specifically. To pull up pricing for David's Restaurant, I need the Google Business Profile link." Concrete instructions included |
| **E10** | Long multi-topic inbound | **FAIL — new bug** | Pipeline escalated with `legal_escalation:sue` even though the message contains NO legal threat. The lead message contains "review **issues**" — the deterministic LEGAL_ESCALATION pattern matches "sue" as a substring of "issues" without a word boundary |

**Totals: 6 PASS, 2 PARTIAL, 2 FAIL**

---

## Two new bugs surfaced

### Bug N — `LEGAL_ESCALATION` pattern matches "sue" as substring of "issues" (E10)

The deterministic legal-escalation phrase list includes `"sue"` as a literal substring without word-boundary guards. The lead message in E10 begins:

> "We've been operating for 8 years and never had review **issues** until a former employee left..."

The substring "sue" appears inside "issues". The escalation fired immediately with reason `legal_escalation:sue` — and the entire 5-paragraph message (pricing request, timing question, warranty question) got routed to human queue without any pricing turn.

**Production impact**: severe. Every lead message containing "issue", "issues", or "tissue" would false-trigger legal escalation. This is a common word in customer service contexts — leads talking about their "review issues", "policy violation issues", "billing issues" would all be misrouted.

**Fix**: wrap each phrase in `\b...\b` word boundaries when checking. Alternative: switch from naive substring search to a compiled regex with `\b` boundaries.

### Bug O — SC em-dash redraft loop doesn't converge (E2 Turn 1)

The drafter emitted "pay-after-removal basis — no charge..." with an `—` (em dash). The SC's deterministic em-dash check correctly flagged it. The LLM redrafter was told to fix it, but on retry it emitted essentially the same draft with the em dash again. Same on attempt 3. Pipeline gave up and routed to human_queue.

This is the same architectural pattern as Bug D ("for a profile like" hedge loop). The LLM has a strong habit of using em dashes and the SC verdict alone isn't enough to break it within the retry budget.

**Fix**: extend the deterministic strip helper. After SC flags em dashes, automatically replace `—` and `–` with `, ` (comma+space) outside the approved-string allowlist BEFORE the next SC retry. Pattern is identical to `strip_hedged_pricing_intro`.

**Production impact**: any first-touch draft where the LLM happens to use an em dash falls into human_queue. Looking at the prior 60+ conversations, the em-dash failure rate at first-touch was already ~10-15% — this just made it visible because E2's turn 1 had no other competing content for SC to focus on.

---

## What the edge cases proved is working

- **Acceptance LLM classifier** (E1): correctly distinguishes price-anchored "$298 works for me" from generic "ok" (E5). Both edge cases handled correctly. The Bug C fix (acceptance gating) holds.
- **Bug M prompt clarification** (E3 vs E2 from Conv 39): hypothetical chargeback question (Conv 39) was over-conservatively escalated in the prior round. After the prompt fix, **actual** chargeback (E3 with "$450 last month for a removal that never happened") correctly escalates with a precise reason. The hypothetical-vs-actual distinction now works.
- **Hard-trigger priority** (E7): legal escalation fires before the pricing turn runs. The deterministic check happens first and shortcircuits — no $ ever leaks into a draft for a legally-sensitive lead.
- **Auto-capture pattern** (E9): the GBP URL detector is correctly scoped to Google Maps / g.page only. Yelp / Facebook / Apple Maps URLs do NOT false-match. AI gracefully redirects with instructions.
- **Schema edge** (E8): single-name lead processed cleanly with no rendering artifacts.
- **Tone classification** (E2 Turn 2): adaptive selector correctly read the lead's angry tone as "urgent" (not "noncommittal"), biased toward upper-mid band ($258 of $240-$280), reasoning captured the signal.

---

## Recommended fix sequence

Both bugs share the same architectural template (deterministic strip helper after SC flag). Single PR can ship both.

1. **Bug N — word-boundary fix** (~10 min). Compile the LEGAL_ESCALATION / OPERATOR_ESCALATION tuples into a single regex with `\b...\b` boundaries. Add a regression test that asserts "review issues" / "tissue" / "issue" do NOT trigger escalation.

2. **Bug O — em-dash auto-strip** (~30 min). Add `strip_forbidden_em_dashes(draft_body)` in `self_correction.py` mirroring `strip_hedged_pricing_intro`. Call it on the redraft body before SC reruns. Preserve em dashes inside `APPROVED_COPY_ALLOWING_EMDASH` fragments. Tests: confirm benign body with `—` becomes `,`-separated; confirm approved-string em dashes are preserved.

After these fixes, the 10-conv edge suite should produce **8-9 PASS** (E6 Spanish-only response would still be PARTIAL — not a spec violation).

---

## Coverage summary

After 63 total conversations across 4 suites (3 + 20 + 30 + 10):

- **Pricing engine**: every tier, every volume bracket, every band edge, phone-call threshold + T1 exception — all covered
- **Negotiation**: step 0/1/2/3, pushback detection, acceptance mid-step, past-final escalation — all covered
- **Approved strings**: timeline (all 3 framings), success (both), methodology (all 3), warranty (all variants), pay-anchor, DocuSign — all covered with verbatim enforcement
- **Hard escalations**: legal, refund (post-pay actual + hypothetical), named-person, chargeback hypothetical vs actual — all covered, all routed correctly
- **Operator guardrails**: GBP missing, category missing, kill switch, ai_quote_allowed false — all covered
- **Schema edges**: empty last name, soft-quote mode, CA footer, missing transcript, pre-seeded triggers — all covered
- **Multi-turn flows**: full negotiation→accept, quote→stall→accept, repeat pricing turns — covered
- **Channel**: email first touch, SMS first touch, multi-channel (email→SMS), SMS draft length — all covered
- **Quality**: hedged intro stripping, methodology paraphrase recovery, DocuSign one-liner enforcement — all covered

**Remaining gaps after Bug N + Bug O fixes**: multilingual response (E6 acceptable but enhancement-worthy), and possibly stall-detection long-silence flows (covered in deterministic suite, not in conversation traces yet).
