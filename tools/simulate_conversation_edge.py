"""10 edge-case conversations not covered by the prior 53.

Each one targets a specific boundary where the spec or implementation could
plausibly mis-route:

  E1 — Accept-mid-negotiation: lead at step 1, says "$298 works for me" — must
       fire quote_accepted via the LLM acceptance classifier, NOT just on the
       phrase "works for me".
  E2 — Angry inbound + valid question: lead uses profanity but asks a normal
       pricing question. AI must answer the question, NOT escalate on tone alone.
  E3 — Actual post-pay chargeback: lead says they paid last month and want a
       refund. This is the real escalation path (Conv 39 was hypothetical).
  E4 — Bot suspicion: "are you a bot? is this AI?" — AI should answer
       transparently without escalating.
  E5 — Bare "ok" / "go ahead" with NO quote in transcript — must NOT fire
       acceptance (per spec: "agreeing to something else the assistant just
       said without tying it to a dollar quote").
  E6 — Spanish-language inbound mid-flow: lead replies in Spanish. No spec
       rule for multilingual; observe whether AI handles or paraphrases poorly.
  E7 — Pricing question + legal threat in same message: legal escalation
       MUST win over the pricing turn.
  E8 — Single-word first name + empty last name: edge of lead schema.
  E9 — Wrong-platform URL: lead pastes a Yelp URL when asked for GBP.
       Auto-capture must NOT fire on non-Google-Maps URLs; AI should ask again.
  E10 — Very long multi-topic inbound (history + urgency + pricing + timing +
        warranty stacked). AI must triage to the top priorities cleanly.

Run::
    python tools/simulate_conversation_edge.py --out tests/CONVERSATION_TRACES_EDGE.md
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_BUFFER = io.StringIO()
_log_handler = logging.StreamHandler(LOG_BUFFER)
_log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
logging.getLogger("reviewarmour").addHandler(_log_handler)
logging.getLogger("reviewarmour").setLevel(logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from reviewarmour.conversation import (  # noqa: E402
    AdaptivePriceSelector,
    ConversationModule,
    OutboundPipeline,
    PipelineResult,
)
from reviewarmour.models import (  # noqa: E402
    Channel,
    Country,
    GBPCategory,
    LeadRecord,
    NegotiationTriggerLogEntry,
    RecencyProfile,
)
from reviewarmour.self_correction import (  # noqa: E402
    SelfCorrectionModule,
    make_anthropic_client,
)
from reviewarmour.settings import LLMRuntime  # noqa: E402


def _lead(**kw) -> LeadRecord:
    defaults = dict(
        lead_id="EDGE",
        first_name="Test",
        last_name="Lead",
        business_name="Test Business",
        country=Country.US,
        phone="+15551234567",
        email="test@example.com",
        gbp_link="https://maps.google.com/place/test",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="general",
        gbp_category=GBPCategory.PLUMBER,
        reviews_image_content=[False, False],
        reviews_under_one_month=[True, True],
        lead_source="website_form",
    )
    defaults.update(kw)
    return LeadRecord(**defaults)


def conversations() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    return [
        # E1 — accept mid-negotiation
        {
            "id": "E1",
            "title": "Accept mid-negotiation: 'works for me' after step-1 quote",
            "expectation": (
                "Lead at step=1 with a prior quote of $298 in transcript; lead "
                "says '$298 works for me'. Acceptance LLM must classify as accept "
                "(price-anchored) and fire quote_accepted state."
            ),
            "lead": _lead(
                lead_id="EDGE-E1",
                first_name="Joe",
                business_name="Acme Plumbing",
                gbp_category=GBPCategory.PLUMBER,
                negotiation_step=1,
                negotiation_triggers=[
                    NegotiationTriggerLogEntry(
                        step_after=1,
                        lead_message_exact="too expensive",
                        at=now,
                    ),
                ],
            ),
            "preseed_transcript": [
                {
                    "role": "lead",
                    "channel": "email",
                    "content": "What's the rate per review?",
                },
                {
                    "role": "assistant",
                    "channel": "email",
                    "content": (
                        "Hi Joe, for Acme Plumbing the rate is $340 USD per review. "
                        "You only pay after each one comes down."
                    ),
                },
                {
                    "role": "lead",
                    "channel": "email",
                    "content": "Too expensive. Any flexibility?",
                },
                {
                    "role": "assistant",
                    "channel": "email",
                    "content": (
                        "For Acme Plumbing, I can bring it down to $298 USD per "
                        "review. Still pay-after-removal."
                    ),
                },
            ],
            "turns": [
                {
                    "label": "Lead accepts the negotiated price",
                    "inbound": "$298 works for me. Let's do it.",
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": False,
                },
            ],
        },
        # E2 — angry inbound + valid question
        {
            "id": "E2",
            "title": "Angry tone + valid pricing question — answer, do NOT escalate on tone",
            "expectation": (
                "Lead uses sharp/angry tone but asks a normal pricing question. "
                "Pipeline should not escalate just because of tone. AI answers "
                "the question with the authorized quote."
            ),
            "lead": _lead(
                lead_id="EDGE-E2",
                first_name="Sam",
                business_name="Sam Auto Body",
                gbp_category=GBPCategory.AUTO_REPAIR,
                business_category="auto_repair",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Angry pricing ask",
                    "inbound": (
                        "Look I'm sick of these fake reviews killing my business. "
                        "Just tell me what the hell it costs already."
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": True,
                },
            ],
        },
        # E3 — REAL post-pay chargeback (not hypothetical)
        {
            "id": "E3",
            "title": "Actual post-pay chargeback — must escalate (vs Conv 39 hypothetical)",
            "expectation": (
                "Lead describes an ACTUAL paid invoice with no removal. This is "
                "the real refund/chargeback escalation path. Pipeline must escalate."
            ),
            "lead": _lead(
                lead_id="EDGE-E3",
                first_name="Maria",
                business_name="Maria's Salon",
                gbp_category=GBPCategory.BEAUTY_SALON,
                business_category="beauty",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "Real chargeback complaint",
                    "inbound": (
                        "I paid $450 last month for a removal that never happened. "
                        "I want a refund or I'm filing a chargeback with my bank tomorrow."
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": False,
                },
            ],
        },
        # E4 — bot suspicion
        {
            "id": "E4",
            "title": "Bot suspicion: 'is this AI?'",
            "expectation": (
                "Lead asks if they're talking to a bot/AI. AI should respond "
                "without confirming or denying AI identity (per spec: don't "
                "make false claims). Should not escalate. Should redirect to value."
            ),
            "lead": _lead(
                lead_id="EDGE-E4",
                first_name="Priya",
                business_name="Priya Dental Care",
                gbp_category=GBPCategory.DENTIST,
                business_category="dental",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Bot suspicion",
                    "inbound": "Wait, am I talking to a bot? Is this AI?",
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": False,
                },
            ],
        },
        # E5 — bare "ok" with no quote
        {
            "id": "E5",
            "title": "Bare 'ok' with NO prior quote — must NOT fire acceptance",
            "expectation": (
                "First touch goes out. Lead replies just 'ok'. There is NO USD "
                "quote in the transcript. Per spec: 'generic ok / go ahead right "
                "after non-pricing assistant text' is NOT acceptance. State must "
                "NOT contain ai_conversation_state=quote_accepted."
            ),
            "lead": _lead(
                lead_id="EDGE-E5",
                first_name="Alex",
                business_name="Alex Bakery",
                gbp_category=GBPCategory.BAKERY,
                business_category="bakery",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Bare 'ok' reply",
                    "inbound": "ok",
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": False,
                },
            ],
        },
        # E6 — Spanish reply mid-flow
        {
            "id": "E6",
            "title": "Spanish-language inbound mid-flow",
            "expectation": (
                "After an English first touch, lead replies in Spanish. No spec "
                "rule for multilingual. Observe: does AI respond in English "
                "(staying on script) or attempt Spanish? Either may be acceptable "
                "but the AI must NOT escalate just because language switched."
            ),
            "lead": _lead(
                lead_id="EDGE-E6",
                first_name="Carlos",
                business_name="Carlos Landscaping",
                gbp_category=GBPCategory.LANDSCAPER,
                business_category="landscaping",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch (English)",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Spanish reply",
                    "inbound": (
                        "Hola, gracias por escribir. Cuanto cuesta por reseña? "
                        "Tenemos dos reseñas malas."
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": True,
                },
            ],
        },
        # E7 — pricing question + legal threat in same message
        {
            "id": "E7",
            "title": "Pricing ask + lawyer mention in same message — legal escalation wins",
            "expectation": (
                "Lead asks for price AND mentions their lawyer in one message. "
                "Hard-trigger legal escalation must win — pipeline returns "
                "escalate, NO pricing draft fires."
            ),
            "lead": _lead(
                lead_id="EDGE-E7",
                first_name="Robert",
                business_name="Robert Roofing",
                gbp_category=GBPCategory.ROOFING_CONTRACTOR,
                business_category="roofing",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "Pricing + legal in one message",
                    "inbound": (
                        "What's your rate per review? My lawyer said I should "
                        "ask about your refund policy before signing anything."
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": True,
                },
            ],
        },
        # E8 — single-word first name, empty last name
        {
            "id": "E8",
            "title": "Single-word first name + empty last name",
            "expectation": (
                "Lead record has first_name='Madonna', last_name=''. AI must "
                "address by first name only without leaving 'Hi Madonna ,' or "
                "empty trailing comma. Footer / draft normal."
            ),
            "lead": _lead(
                lead_id="EDGE-E8",
                first_name="Madonna",
                last_name="",
                business_name="Madonna Med Spa",
                gbp_category=GBPCategory.MED_SPA,
                business_category="med_spa",
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch with single-name lead",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
            ],
        },
        # E9 — wrong-platform URL (Yelp)
        {
            "id": "E9",
            "title": "Lead pastes Yelp URL instead of Google Maps",
            "expectation": (
                "GBP missing on lead. Lead pastes a Yelp URL when asked. Auto-"
                "capture must NOT fire (URL doesn't match Maps pattern). AI "
                "should ask again for the GBP link specifically."
            ),
            "lead": _lead(
                lead_id="EDGE-E9",
                first_name="David",
                business_name="David's Restaurant",
                gbp_category=GBPCategory.RESTAURANT,
                business_category="restaurant",
                gbp_link=None,
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch (no GBP)",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Lead pastes Yelp URL",
                    "inbound": (
                        "Sure, here's our page: https://www.yelp.com/biz/davids-restaurant-newyork "
                        "What's the pricing?"
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": True,
                },
            ],
        },
        # E10 — very long multi-topic inbound
        {
            "id": "E10",
            "title": "Long multi-topic inbound — must triage cleanly",
            "expectation": (
                "Lead sends a 5-paragraph message covering history, urgency, "
                "pricing, timing, and warranty all at once. AI should answer the "
                "top 2-3 priorities (price + timing or pay-anchor) cleanly without "
                "trying to address everything and losing focus."
            ),
            "lead": _lead(
                lead_id="EDGE-E10",
                first_name="Jennifer",
                business_name="Jennifer Hotel Group",
                gbp_category=GBPCategory.HOTEL,
                business_category="hotel",
                review_count=4,
                recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
                reviews_image_content=[True, False, False, True],
                reviews_under_one_month=[True, True, True, False],
            ),
            "preseed_transcript": [],
            "turns": [
                {
                    "label": "First touch",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
                {
                    "label": "Long multi-topic message",
                    "inbound": (
                        "Hi - thanks for reaching out. Let me give you the full picture.\n\n"
                        "We've been operating for 8 years and never had review issues until a "
                        "former employee left and started a smear campaign. We've gotten 4 "
                        "really bad reviews in the past 2 months, two with photos of food that "
                        "we don't even serve.\n\n"
                        "We have a wedding event hosting weekend coming up in 3 weeks and these "
                        "reviews are seriously hurting our bookings. The wedding party is asking "
                        "questions and we may lose the contract.\n\n"
                        "So my questions: what does it cost per review, how fast can these come "
                        "down, what happens if you can't get them removed, and what's your "
                        "guarantee they don't come back later?\n\n"
                        "Also someone mentioned you offer some kind of warranty? Tell me about that."
                    ),
                    "channel": Channel.EMAIL,
                    "sequence_stage": "reply",
                    "wants_price": True,
                },
            ],
        },
    ]


def _commercial_snapshot(result: PipelineResult) -> dict[str, Any]:
    if result.commercial is None:
        return {}
    c = result.commercial
    return {
        "tier": c.tier.value,
        "gbp_category": c.gbp_category.value if c.gbp_category else None,
        "volume_bracket": c.volume_bracket.value,
        "range_low_usd": c.range_low_usd,
        "range_high_usd": c.range_high_usd,
        "floor_usd": c.floor_usd,
        "negotiation_step": c.negotiation_step,
        "authorized_quote_usd_per_review": c.authorized_quote_usd_per_review,
        "can_quote": c.can_quote,
        "request_gbp_first": c.request_gbp_first,
        "request_category_first": c.request_category_first,
        "phone_call_threshold_triggered": c.phone_call_threshold_triggered,
        "salesman_recommended_opening_usd": c.salesman_recommended_opening_usd,
        "reasoning_summary": c.reasoning_summary,
        "soft_quote_range": c.soft_quote_range,
        "escalate": c.escalate,
        "escalation_reason": c.escalation_reason,
    }


def run_conversation(conv: dict[str, Any], pipeline: OutboundPipeline) -> list[dict[str, Any]]:
    lead = conv["lead"]
    transcript: list[dict[str, Any]] = list(conv.get("preseed_transcript", []))
    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for idx, turn in enumerate(conv["turns"], start=1):
        LOG_BUFFER.seek(0)
        LOG_BUFFER.truncate(0)

        if turn["inbound"]:
            transcript.append(
                {
                    "role": "lead",
                    "channel": turn["channel"].value,
                    "content": turn["inbound"],
                }
            )

        kwargs: dict[str, Any] = dict(
            lead=lead,
            transcript=list(transcript),
            channel=turn["channel"],
            sequence_stage=turn["sequence_stage"],
            inbound_message=turn["inbound"],
            wants_price=turn["wants_price"],
            now_override=now,
        )
        if turn.get("quoted_previously"):
            kwargs["quoted_previously"] = turn["quoted_previously"]

        result = pipeline.run(**kwargs)
        logs = LOG_BUFFER.getvalue()

        ai_subject = None
        ai_body = None
        if result.draft and result.draft.action == "send" and result.draft.body:
            ai_subject = result.draft.subject
            ai_body = result.draft.body
            transcript.append(
                {
                    "role": "assistant",
                    "channel": turn["channel"].value,
                    "subject": ai_subject,
                    "content": ai_body,
                }
            )

        if result.state_updates:
            step = result.state_updates.get("negotiation_step")
            if isinstance(step, int):
                lead = replace(lead, negotiation_step=step)

        results.append(
            {
                "turn_num": idx,
                "label": turn["label"],
                "inbound": turn["inbound"],
                "channel": turn["channel"].value,
                "sequence_stage": turn["sequence_stage"],
                "wants_price": turn["wants_price"],
                "outcome": result.outcome,
                "draft_action": result.draft.action if result.draft else None,
                "draft_subject": ai_subject,
                "draft_body": ai_body,
                "draft_reason": result.draft.reason if result.draft else None,
                "commercial": _commercial_snapshot(result),
                "state_updates": result.state_updates or {},
                "sc_attempts": [a.to_dict() for a in (result.self_correction_logs or [])],
                "logs": logs,
            }
        )

    return results


def format_trace_md(conv: dict[str, Any], turns: list[dict[str, Any]]) -> str:
    out: list[str] = []
    out.append(f"# {conv['id']} — {conv['title']}\n")
    out.append(f"**Expected**: {conv['expectation']}\n")
    lead = conv["lead"]
    out.append(
        f"\n**Lead**: {lead.first_name!r} / {lead.last_name!r} / {lead.business_name} "
        f"({lead.country.value}) | category=`{lead.gbp_category.value if lead.gbp_category else 'None'}` "
        f"| reviews={lead.review_count} {lead.recency_profile.value} "
        f"images={lead.reviews_image_content} recent={lead.reviews_under_one_month}"
        f"{' soft_quote' if lead.soft_quote_mode else ''}"
        f"{' kill-switch' if not lead.ai_quote_allowed else ''}"
        f" step={lead.negotiation_step}\n"
    )
    if conv.get("preseed_transcript"):
        out.append(f"\n_Pre-seeded transcript with {len(conv['preseed_transcript'])} turns._\n")

    for t in turns:
        out.append(f"\n## Turn {t['turn_num']} — {t['label']} ({t['channel']}, stage={t['sequence_stage']})\n")
        if t["inbound"]:
            inbound_short = t["inbound"][:300] + ("..." if len(t["inbound"]) > 300 else "")
            out.append(f"\n**Lead**: > {inbound_short}\n")
        out.append(f"\n**Outcome**: `{t['outcome']}` | draft.action=`{t['draft_action']}`")
        if t["draft_reason"]:
            out.append(f" | reason=`{t['draft_reason']}`")
        out.append("\n")
        if t["commercial"]:
            c = t["commercial"]
            keys = [
                "tier", "range_low_usd", "range_high_usd", "floor_usd",
                "negotiation_step", "authorized_quote_usd_per_review",
                "can_quote", "request_gbp_first", "request_category_first",
                "phone_call_threshold_triggered",
                "salesman_recommended_opening_usd",
                "soft_quote_range", "escalate", "escalation_reason",
            ]
            short = {k: c.get(k) for k in keys if c.get(k) is not None}
            out.append("\n**Commercial**: ```")
            out.append(json.dumps(short, default=str))
            out.append("```\n")
            if c.get("reasoning_summary"):
                out.append(f"\n_Adaptive reasoning_: {c['reasoning_summary']}\n")
        if t["sc_attempts"]:
            out.append("\n**SC**: ")
            for a in t["sc_attempts"]:
                out.append(f"a{a.get('attempt')}={a.get('verdict')}")
                if a.get("failed_checks"):
                    out.append(f"({len(a['failed_checks'])} failed)")
                out.append(" ")
            out.append("\n")
        if t["state_updates"]:
            interesting = {
                k: v for k, v in t["state_updates"].items()
                if k in ("ai_conversation_state", "negotiation_step", "escalation_reason")
            }
            if interesting:
                out.append(f"\n**State**: `{interesting}`\n")
        if t["draft_body"]:
            out.append("\n**Draft**:\n```")
            if t["draft_subject"]:
                out.append(f"\nSubject: {t['draft_subject']}\n")
            out.append(f"\n{t['draft_body']}\n```\n")
        if t["logs"].strip():
            relevant = [
                line for line in t["logs"].splitlines()
                if any(k in line for k in (
                    "AdaptivePriceSelector", "Negotiation pushback", "escalate",
                    "Quote acceptance", "T1-exception", "phone-call", "Stripped",
                    "Auto-captured", "_handle_acceptance",
                ))
            ]
            if relevant:
                out.append("\n**Pipeline log highlights**:\n```\n")
                out.append("\n".join(relevant))
                out.append("\n```\n")

    out.append("\n---\n")
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default=str(REPO_ROOT / "tests" / "CONVERSATION_TRACES_EDGE.md")
    )
    parser.add_argument("--only", type=str, default=None)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = make_anthropic_client()
    runtime = LLMRuntime()
    pipeline = OutboundPipeline(
        conversation=ConversationModule(client, runtime=runtime),
        self_correction=SelfCorrectionModule(client, runtime=runtime),
        adaptive_price_selector=AdaptivePriceSelector(client, runtime=runtime),
    )

    convs = conversations()
    if args.only is not None:
        convs = [c for c in convs if c["id"] == args.only]

    chunks: list[str] = []
    chunks.append(
        "# ReviewArmour v2 - 10 Edge Cases\n\n"
        f"_Generated {datetime.now(timezone.utc).isoformat()}_\n\n"
        "Targets boundaries not exercised by the prior 53 conversations: "
        "accept mid-negotiation, angry-but-valid inbound, real (not hypothetical) "
        "chargeback, bot suspicion, false-acceptance prevention, multilingual, "
        "competing priorities (pricing + legal), schema edges (empty last name), "
        "wrong-platform URL, multi-topic long inbound.\n\n---\n"
    )

    for conv in convs:
        print(f"=== Running {conv['id']}: {conv['title']} ===")
        try:
            turns = run_conversation(conv, pipeline)
            chunks.append(format_trace_md(conv, turns))
            outcomes = [t["outcome"] for t in turns]
            print(f"  -> {len(turns)} turns, outcomes: {outcomes}")
        except Exception as e:
            import traceback
            print(f"  !! exception: {e}")
            traceback.print_exc()
            chunks.append(f"# {conv['id']} - {conv['title']}\nEXCEPTION: {e}\n\n---\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(chunks), encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
