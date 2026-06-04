"""Full AI-conversation coverage simulator (20 conversations).

Covers every observable behavior of the AI conversation module:
  - First-touch (US, CA, variations)
  - All 4 tiers (T1/T2/T3/T4) on the written-quote path
  - Phone-call threshold T1/T2 leads
  - T1 written exception
  - Soft-quote mode
  - Negotiation ladder (steps 0/1/2/3)
  - Acceptance → invoice handoff
  - GBP missing → request_gbp_first
  - GBP category missing → request_category_first
  - ai_quote_allowed kill switch
  - Hard escalation triggers (legal/refund)
  - Timeline questions (under-1-month + over-1-month framing)
  - Hard-guarantee timeline ask
  - Pay-after-removal anchor
  - Success-rate question
  - Off-topic redirect (Flow 10)
  - Stall detection on commercial turn
  - Customer review request (post-removal)

Requires: ANTHROPIC_API_KEY.

Run::
    python tools/simulate_conversation_full.py --out tests/CONVERSATION_TRACES_FULL.md
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
    RecencyProfile,
)
from reviewarmour.self_correction import (  # noqa: E402
    SelfCorrectionModule,
    make_anthropic_client,
)
from reviewarmour.settings import LLMRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Lead builders
# ---------------------------------------------------------------------------


def _us_lead(**kw) -> LeadRecord:
    defaults = dict(
        lead_id="SIM",
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


# ---------------------------------------------------------------------------
# 20 conversation definitions
# ---------------------------------------------------------------------------


def conversations() -> list[dict[str, Any]]:
    return [
        # 1. CA T3 hotel: first-touch + price ask + accept (Canadian footer)
        {
            "id": 1,
            "title": "CA T3 Hotel - first touch -> written quote -> acceptance",
            "expectation": (
                "CA Toronto footer. T3 hotel small band $320-$370. Adaptive picks "
                "in band. SC accepts. Acceptance triggers quote_accepted state."
            ),
            "lead": _us_lead(
                lead_id="SIM-01",
                first_name="Amelia",
                last_name="Wright",
                business_name="Maple Leaf Hotel",
                country=Country.CA,
                phone="+14165550101",
                email="amelia@mapleleafhotel.ca",
                gbp_category=GBPCategory.HOTEL,
                business_category="hotel",
                review_count=2,
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("Got your message. What does this cost per review?", wants_price=True),
                _lead_says("Sounds good, let's move forward.", wants_price=False),
            ],
        },
        # 2. T4 nail salon: lowest tier, written quote, floor enforcement
        {
            "id": 2,
            "title": "T4 Nail Salon - low-tier written quote",
            "expectation": (
                "T4 nail salon band $210-$250, floor $200. Adaptive picks in range. "
                "AI quotes in writing."
            ),
            "lead": _us_lead(
                lead_id="SIM-02",
                business_name="Glamour Nail Salon",
                gbp_category=GBPCategory.NAIL_SALON,
                business_category="nail",
                review_count=2,
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("What's the price per review for these?", wants_price=True),
            ],
        },
        # 3. T2 HVAC over $400 -> phone route
        {
            "id": 3,
            "title": "T2 HVAC Contractor -> phone-call route",
            "expectation": (
                "T2 HVAC band $400-$450 (above threshold, no T2 exception). "
                "Engine sets phone_call_threshold_triggered. AI pivots to phone."
            ),
            "lead": _us_lead(
                lead_id="SIM-03",
                business_name="Reliable HVAC Services",
                gbp_category=GBPCategory.HVAC_CONTRACTOR,
                business_category="hvac",
                review_count=2,
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("How much per review?", wants_price=True),
            ],
        },
        # 4. T1 plastic surgeon -> phone route (highest tier)
        {
            "id": 4,
            "title": "T1 Plastic Surgeon -> phone-call route (highest band)",
            "expectation": (
                "T1 plastic surgeon band $520-$550, well above threshold, no exception "
                "because reviews are over-month text-only. Phone route."
            ),
            "lead": _us_lead(
                lead_id="SIM-04",
                business_name="Premier Plastic Surgery",
                gbp_category=GBPCategory.PLASTIC_SURGEON,
                business_category="plastic_surgeon",
                review_count=2,
                recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
                reviews_image_content=[False, False],
                reviews_under_one_month=[False, False],
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("Pricing info please?", wants_price=True),
            ],
        },
        # 5. Soft-quote mode: returns band, no negotiation
        {
            "id": 5,
            "title": "Soft-quote mode - band reply, pushback escalates",
            "expectation": (
                "soft_quote_mode=True. Engine returns range. AI quotes a band "
                "('typically $X-$Y'). Lead pushback escalates (no negotiation)."
            ),
            "lead": _us_lead(
                lead_id="SIM-05",
                business_name="Smith Roofing",
                gbp_category=GBPCategory.ROOFING_CONTRACTOR,
                business_category="roofing",
                review_count=2,
                recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
                soft_quote_mode=True,
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("What range are we looking at per review?", wants_price=True),
            ],
        },
        # 6. Full negotiation ladder - step 0 -> 1 -> 2 -> accept at step 2
        {
            "id": 6,
            "title": "Full negotiation ladder - 0 -> 1 -> 2 -> acceptance",
            "expectation": (
                "T3 plumber. Each pushback bumps step. Step 2 quotes still in band "
                "above floor. Acceptance at step 2 triggers quote_accepted."
            ),
            "lead": _us_lead(
                lead_id="SIM-06",
                business_name="Acme Plumbing",
                gbp_category=GBPCategory.PLUMBER,
                business_category="plumber",
                review_count=2,
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("What's the rate per review?", wants_price=True),
                _lead_says("That feels a bit steep for us. Any flexibility?", wants_price=True),
                _lead_says("Hmm, still a stretch for our budget. Can you do better?", wants_price=True),
                _lead_says("Okay that works. Let's do it.", wants_price=False),
            ],
        },
        # 7. Step 3 pushback -> escalate
        {
            "id": 7,
            "title": "Pushback past step 2 -> escalate to human",
            "expectation": (
                "Lead already at step 2, pushes back again. Pipeline escalates with "
                "reason 'negotiation_past_final_step'."
            ),
            "lead": _us_lead(
                lead_id="SIM-07",
                business_name="Sunset Electric",
                gbp_category=GBPCategory.ELECTRICIAN,
                business_category="electrician",
                review_count=2,
                negotiation_step=2,
            ),
            "turns": [
                _lead_says(
                    "Look, we really need this to be cheaper. Can you go any lower?",
                    wants_price=True,
                ),
            ],
        },
        # 8. GBP link missing -> request first
        {
            "id": 8,
            "title": "Missing GBP link -> AI asks for it before quoting",
            "expectation": "Engine returns request_gbp_first=True. AI asks for the link.",
            "lead": _us_lead(
                lead_id="SIM-08",
                business_name="Quick Auto Repair",
                gbp_category=GBPCategory.AUTO_REPAIR,
                business_category="auto_repair",
                gbp_link=None,
            ),
            "turns": [
                _lead_says("Hi, I want to know your pricing for review removal.", wants_price=True),
            ],
        },
        # 9. GBP category unknown -> ask first
        {
            "id": 9,
            "title": "GBP category unknown -> AI asks before quoting",
            "expectation": (
                "gbp_category=None. Engine returns request_category_first=True. "
                "AI confirms business type before quoting."
            ),
            "lead": _us_lead(
                lead_id="SIM-09",
                business_name="Generic Widget Co",
                business_category="",
                gbp_category=None,
            ),
            "turns": [
                _lead_says("How much do you charge per review?", wants_price=True),
            ],
        },
        # 10. ai_quote_allowed=False -> escalate
        {
            "id": 10,
            "title": "ai_quote_allowed kill switch -> escalate",
            "expectation": "Pipeline escalates on first pricing turn. No quote in draft.",
            "lead": _us_lead(
                lead_id="SIM-10",
                ai_quote_allowed=False,
            ),
            "turns": [
                _lead_says("What does this cost?", wants_price=True),
            ],
        },
        # 11. Hard escalation - legal trigger
        {
            "id": 11,
            "title": "Legal escalation phrase -> escalate immediately",
            "expectation": (
                "Lead mentions 'my lawyer'. Pipeline returns escalate, draft.action=escalate."
            ),
            "lead": _us_lead(lead_id="SIM-11"),
            "turns": [
                _lead_says(
                    "My lawyer told me to ask if you're really able to remove these.",
                    wants_price=False,
                ),
            ],
        },
        # 12. Hard escalation - refund dispute
        {
            "id": 12,
            "title": "Refund/chargeback request -> escalate",
            "expectation": "Refund request triggers escalation per Section 11 escalation_trigger check.",
            "lead": _us_lead(lead_id="SIM-12"),
            "turns": [
                _lead_says(
                    "I want a refund on the last invoice. The review didn't come down "
                    "and I'm filing a chargeback.",
                    wants_price=False,
                ),
            ],
        },
        # 13. Timeline question - under 1 month
        {
            "id": 13,
            "title": "Timing question for fresh reviews -> approved under_1_month paragraph",
            "expectation": (
                "All reviews under 1 month. Lead asks how fast. AI uses exact "
                "approved 'two to four weeks' timeline paragraph."
            ),
            "lead": _us_lead(
                lead_id="SIM-13",
                business_name="Fresh Bakery",
                gbp_category=GBPCategory.BAKERY,
                business_category="bakery",
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("How fast can these come down?", wants_price=False),
            ],
        },
        # 14. Timeline question - over 1 month (mixed)
        {
            "id": 14,
            "title": "Timing question for older reviews -> approved over/mixed paragraph",
            "expectation": (
                "Reviews are over 1 month. Lead asks timing. AI uses approved mixed/over_1_month "
                "timeline paragraph."
            ),
            "lead": _us_lead(
                lead_id="SIM-14",
                business_name="Heritage Furniture Store",
                gbp_category=GBPCategory.FURNITURE_STORE,
                business_category="furniture",
                recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
                reviews_image_content=[False, False],
                reviews_under_one_month=[False, False],
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("These have been up for a while. When can we expect them down?", wants_price=False),
            ],
        },
        # 15. Hard guarantee asked - approved hard_guarantee paragraph
        {
            "id": 15,
            "title": "Lead demands a hard date -> approved hard_guarantee paragraph",
            "expectation": (
                "Lead asks for a guaranteed calendar date. AI uses the approved "
                "hard_guarantee_asked paragraph; does NOT promise a specific date."
            ),
            "lead": _us_lead(
                lead_id="SIM-15",
                business_name="Sunshine Dental",
                gbp_category=GBPCategory.DENTIST,
                business_category="dentist",
                review_count=2,
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says(
                    "I need a guarantee these come down by next Friday. Can you commit to that exact date?",
                    wants_price=False,
                ),
            ],
        },
        # 16. Pay-after-removal anchor question
        {
            "id": 16,
            "title": "Pay-after-removal question -> approved pay-anchor",
            "expectation": (
                "Lead asks what happens if the review doesn't come down. AI states the "
                "approved pay-anchor paragraph: no charge until removed."
            ),
            "lead": _us_lead(
                lead_id="SIM-16",
                business_name="Suburban Movers",
                gbp_category=GBPCategory.MOVING_COMPANY,
                business_category="moving",
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says(
                    "What if you can't get them removed? Do I still pay anything?",
                    wants_price=False,
                ),
            ],
        },
        # 17. Success-rate question - approved SUCCESS paragraphs
        {
            "id": 17,
            "title": "Success-rate question -> approved success paragraph",
            "expectation": (
                "Lead asks success rate. AI uses approved SUCCESS general or "
                "percentage_asked paragraph (no invented percentages)."
            ),
            "lead": _us_lead(
                lead_id="SIM-17",
                business_name="Greenfield Med Spa",
                gbp_category=GBPCategory.MED_SPA,
                business_category="med_spa",
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says("What's your success rate on removals?", wants_price=False),
            ],
        },
        # 18. Off-topic redirect (Flow 10)
        {
            "id": 18,
            "title": "Off-topic message -> brief redirect, stay in scope",
            "expectation": (
                "Lead asks something unrelated. AI sends brief polite redirect back "
                "to review removal, does NOT escalate."
            ),
            "lead": _us_lead(
                lead_id="SIM-18",
                business_name="Sunny Day Cafe",
                gbp_category=GBPCategory.COFFEE_SHOP,
                business_category="coffee_shop",
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says(
                    "By the way, do you guys do SEO services too?",
                    wants_price=False,
                ),
            ],
        },
        # 19. SMS first touch
        {
            "id": 19,
            "title": "SMS channel first touch -> compact body under length",
            "expectation": (
                "First-touch via SMS. Draft body <320 chars (prefer <160). "
                "Uses SMS-style footer (compact)."
            ),
            "lead": _us_lead(
                lead_id="SIM-19",
                business_name="Coastal Landscaping",
                gbp_category=GBPCategory.LANDSCAPER,
                business_category="landscaping",
            ),
            "turns": [
                {
                    "label": "SMS first touch",
                    "inbound": None,
                    "channel": Channel.SMS,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                },
            ],
        },
        # 20. T1 exception case at $440 (verify Bug A fix path one more time)
        {
            "id": 20,
            "title": "T1 dentist exception (1 review image+recent) -> written close",
            "expectation": (
                "Single image+recent review, T1 dentist. T1 exception applies. "
                "Selector picks $400-$450 written close. NOT phone-routed."
            ),
            "lead": _us_lead(
                lead_id="SIM-20",
                first_name="Priya",
                last_name="Singh",
                business_name="Bright Family Dental",
                gbp_category=GBPCategory.DENTIST,
                business_category="dentist",
                review_count=1,
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
                reviews_image_content=[True],
                reviews_under_one_month=[True],
            ),
            "turns": [
                _outbound_first_touch(),
                _lead_says(
                    "One nasty review with photos showed up last week. What's it cost to fix this?",
                    wants_price=True,
                ),
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outbound_first_touch() -> dict[str, Any]:
    return {
        "label": "First touch (outbound)",
        "inbound": None,
        "channel": Channel.EMAIL,
        "sequence_stage": "first_touch",
        "wants_price": False,
    }


def _lead_says(msg: str, *, wants_price: bool = False, channel: Channel = Channel.EMAIL) -> dict[str, Any]:
    return {
        "label": "Lead reply",
        "inbound": msg,
        "channel": channel,
        "sequence_stage": "reply",
        "wants_price": wants_price,
    }


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
        "salesman_recommended_range": c.salesman_recommended_range,
        "salesman_recommended_opening_usd": c.salesman_recommended_opening_usd,
        "reasoning_summary": c.reasoning_summary,
        "soft_quote_mode": c.soft_quote_mode,
        "soft_quote_range": c.soft_quote_range,
        "escalate": c.escalate,
        "escalation_reason": c.escalation_reason,
    }


def run_conversation(conv: dict[str, Any], pipeline: OutboundPipeline) -> list[dict[str, Any]]:
    lead = conv["lead"]
    transcript: list[dict[str, Any]] = []
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

        result = pipeline.run(
            lead=lead,
            transcript=list(transcript),
            channel=turn["channel"],
            sequence_stage=turn["sequence_stage"],
            inbound_message=turn["inbound"],
            wants_price=turn["wants_price"],
            now_override=now,
        )

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

        # Apply state updates to lead so the next turn sees the new state.
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
    out.append(f"# Conversation {conv['id']:02d} — {conv['title']}\n")
    out.append(f"**Expected**: {conv['expectation']}\n")
    lead = conv["lead"]
    out.append(
        f"\n**Lead**: {lead.first_name} {lead.last_name} / {lead.business_name} ({lead.country.value}) "
        f"| category=`{lead.gbp_category.value if lead.gbp_category else 'None'}` "
        f"| reviews={lead.review_count} {lead.recency_profile.value} "
        f"images={lead.reviews_image_content} recent={lead.reviews_under_one_month}"
        f"{' soft_quote' if lead.soft_quote_mode else ''}"
        f"{' kill-switch' if not lead.ai_quote_allowed else ''}\n"
    )

    for t in turns:
        out.append(f"\n## Turn {t['turn_num']} — {t['label']} ({t['channel']}, stage={t['sequence_stage']})\n")
        if t["inbound"]:
            out.append(f"\n**Lead**: > {t['inbound']}\n")
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
                if k in ("ai_conversation_state", "negotiation_step")
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
                    "Quote acceptance", "T1-exception", "phone-call",
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
        "--out", default=str(REPO_ROOT / "tests" / "CONVERSATION_TRACES_FULL.md")
    )
    parser.add_argument("--only", type=int, default=None)
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
        "# ReviewArmour v2 - Full AI Conversation Coverage (20 conversations)\n\n"
        f"_Generated {datetime.now(timezone.utc).isoformat()}_\n\n"
        "Covers every observable behavior of the AI conversation module. Each "
        "conversation lists the expected behavior + per-turn commercial result, "
        "SC verdicts, draft body, and pipeline log highlights.\n\n---\n"
    )

    for conv in convs:
        print(f"=== Running {conv['id']:02d}: {conv['title']} ===")
        try:
            turns = run_conversation(conv, pipeline)
            chunks.append(format_trace_md(conv, turns))
            outcomes = [t["outcome"] for t in turns]
            print(f"  -> {len(turns)} turns, outcomes: {outcomes}")
        except Exception as e:
            print(f"  !! exception: {e}")
            chunks.append(f"# Conversation {conv['id']:02d} - {conv['title']}\nEXCEPTION: {e}\n\n---\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(chunks), encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
