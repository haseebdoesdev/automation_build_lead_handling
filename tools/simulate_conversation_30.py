"""30 NEW conversations covering untested AI conversation behaviors.

Distinct from the original 3 + 20 (43 turns total tested previously). This
suite drives areas not yet exercised:

  - Approved METHODOLOGY paragraphs (general / leverage / more_detail_asked)
  - Approved WARRANTY paragraphs (will_it_come_back / same_customer_new_review)
  - DocuSign-only-at-the-close approved line
  - Untested GBP categories (chiropractor, law firm, accounting, real estate,
    insurance, paving, car dealership, auto detailing, car wash, restaurant,
    electronics store, clothing store, grocery store)
  - Volume brackets 6-15 and 16-30
  - Multi-channel: lead emails first then replies via SMS
  - Lead provides GBP link mid-conversation (auto-capture)
  - Lead provides specific reviewer name
  - Lead asks about chargeback (lighter than refund)
  - Vague reply ("tell me more")
  - Question stacking (3 questions in one inbound)
  - Specific named-person request ("can I talk to Jayden directly?")
  - Soft-quote mode in Canadian context
  - Lead pushes for competitor comparison
  - Lead asks "what's your guarantee"
  - First-touch B variation
  - Operator directive in pipeline (sequence_stage variants)
  - Lead at step 2 + pushback (Bug F production-realistic case)
  - Image-content confirmation question
  - GBP missing + lead pastes URL in next turn
  - CRM-provided notes_images_observed flag
  - Anxiety about paying when nothing happens
  - GBP inspection data already present (inspection facts in prompt)
  - Soft-quote multi-turn
  - Lead misspells question (acceptance with typo)
  - Inbound asks about agreement / paperwork process (skip acceptance)

Run::
    python tools/simulate_conversation_30.py --out tests/CONVERSATION_TRACES_30.md
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


def _first_touch(channel: Channel = Channel.EMAIL) -> dict[str, Any]:
    return {
        "label": "First touch",
        "inbound": None,
        "channel": channel,
        "sequence_stage": "first_touch",
        "wants_price": False,
    }


def _says(msg: str, *, wants_price: bool = False, channel: Channel = Channel.EMAIL,
          stage: str = "reply") -> dict[str, Any]:
    return {
        "label": "Lead reply",
        "inbound": msg,
        "channel": channel,
        "sequence_stage": stage,
        "wants_price": wants_price,
    }


def conversations() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    return [
        # 21. Methodology general — leverage framing
        {
            "id": 21,
            "title": "Methodology general question (how does it work)",
            "expectation": "Lead asks how it works. AI uses approved METHODOLOGY general string.",
            "lead": _lead(
                lead_id="SIM-21",
                business_name="Pacific Chiropractic",
                gbp_category=GBPCategory.CHIROPRACTOR,
                business_category="chiropractor",
            ),
            "turns": [
                _first_touch(),
                _says("How does this actually work? What's your method?"),
            ],
        },
        # 22. Methodology more_detail_asked
        {
            "id": 22,
            "title": "Methodology - asks for operational detail",
            "expectation": "Lead presses for HOW exactly. AI uses approved METHODOLOGY more_detail_asked string (defers to specialist).",
            "lead": _lead(
                lead_id="SIM-22",
                business_name="Westside Law Group",
                gbp_category=GBPCategory.LAW_FIRM,
                business_category="law_firm",
                recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH,
                reviews_under_one_month=[False, False],
            ),
            "turns": [
                _first_touch(),
                _says("I want to understand the specific reporting process. How do you actually get them removed?"),
            ],
        },
        # 23. Warranty: will it come back?
        {
            "id": 23,
            "title": "Warranty - will the review come back?",
            "expectation": "AI uses approved WARRANTY will_it_come_back string.",
            "lead": _lead(
                lead_id="SIM-23",
                business_name="Premier Accounting Group",
                gbp_category=GBPCategory.ACCOUNTING_FIRM,
                business_category="accounting",
            ),
            "turns": [
                _first_touch(),
                _says("If you get them removed, can they come back later?"),
            ],
        },
        # 24. Warranty: same customer leaves new review
        {
            "id": 24,
            "title": "Warranty - same customer new review",
            "expectation": "AI uses approved WARRANTY same_customer_new_review string.",
            "lead": _lead(
                lead_id="SIM-24",
                business_name="Greenfield Insurance",
                gbp_category=GBPCategory.INSURANCE_AGENCY,
                business_category="insurance",
            ),
            "turns": [
                _first_touch(),
                _says("What if the same customer just leaves another bad review after you take theirs down?"),
            ],
        },
        # 25. DocuSign / contract question
        {
            "id": 25,
            "title": "DocuSign / contract question - approved one-liner",
            "expectation": "AI uses the approved 'DocuSign is sent at the close.' line and nothing more.",
            "lead": _lead(
                lead_id="SIM-25",
                business_name="Sunset Real Estate Group",
                gbp_category=GBPCategory.REAL_ESTATE_AGENCY,
                business_category="real_estate",
            ),
            "turns": [
                _first_touch(),
                _says("What does the contract look like? Do I have to sign anything upfront?"),
            ],
        },
        # 26. T3 Paving - written quote
        {
            "id": 26,
            "title": "T3 Paving Contractor - written quote",
            "expectation": "T3 paving band $300-$350. Adaptive picks in range. Written quote.",
            "lead": _lead(
                lead_id="SIM-26",
                business_name="Sunbelt Paving Co",
                gbp_category=GBPCategory.PAVING_CONTRACTOR,
                business_category="paving",
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                _first_touch(),
                _says("Quick question - what do you charge per review?", wants_price=True),
            ],
        },
        # 27. T3 Car Dealership - written quote at mid-band
        {
            "id": 27,
            "title": "T3 Car Dealership - written quote",
            "expectation": "T3 car dealership band $330-$380. Adaptive picks in range.",
            "lead": _lead(
                lead_id="SIM-27",
                business_name="Highway Motors Used Cars",
                gbp_category=GBPCategory.CAR_DEALERSHIP,
                business_category="car_dealership",
                recency_profile=RecencyProfile.MIXED,
                reviews_image_content=[False, False],
                reviews_under_one_month=[True, False],
            ),
            "turns": [
                _first_touch(),
                _says("Pricing per review?", wants_price=True),
            ],
        },
        # 28. T4 Auto Detailing
        {
            "id": 28,
            "title": "T4 Auto Detailing - lower-tier written quote",
            "expectation": "T4 auto detailing band $220-$260. Floor $200.",
            "lead": _lead(
                lead_id="SIM-28",
                business_name="ShineRight Auto Detailing",
                gbp_category=GBPCategory.AUTO_DETAILING,
                business_category="auto_detailing",
            ),
            "turns": [
                _first_touch(),
                _says("What's the rate?", wants_price=True),
            ],
        },
        # 29. T4 Car Wash
        {
            "id": 29,
            "title": "T4 Car Wash - band-floor pricing",
            "expectation": "T4 car wash $200-$240 band. Adaptive likely picks band low.",
            "lead": _lead(
                lead_id="SIM-29",
                business_name="Splash & Go Car Wash",
                gbp_category=GBPCategory.CAR_WASH,
                business_category="car_wash",
            ),
            "turns": [
                _first_touch(),
                _says("How much per review?", wants_price=True),
            ],
        },
        # 30. T3 Restaurant
        {
            "id": 30,
            "title": "T3/T4 Restaurant - written quote",
            "expectation": "Restaurant band $270-$320 (T3). Mid-band pick expected.",
            "lead": _lead(
                lead_id="SIM-30",
                business_name="Eastside Bistro",
                gbp_category=GBPCategory.RESTAURANT,
                business_category="restaurant",
                recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
                reviews_image_content=[True, False, False],
                reviews_under_one_month=[True, True, False],
                review_count=3,
            ),
            "turns": [
                _first_touch(),
                _says("Cost per review for our three reviews?", wants_price=True),
            ],
        },
        # 31. T4 Electronics
        {
            "id": 31,
            "title": "T3/T4 Electronics Store",
            "expectation": "Electronics band $260-$310. Written quote near low-mid.",
            "lead": _lead(
                lead_id="SIM-31",
                business_name="MegaTech Electronics Store",
                gbp_category=GBPCategory.ELECTRONICS_STORE,
                business_category="electronics",
            ),
            "turns": [
                _first_touch(),
                _says("Pricing?", wants_price=True),
            ],
        },
        # 32. T4 Clothing Store
        {
            "id": 32,
            "title": "T4 Clothing Store",
            "expectation": "Clothing band $220-$260. Written quote.",
            "lead": _lead(
                lead_id="SIM-32",
                business_name="Style Avenue Boutique",
                gbp_category=GBPCategory.CLOTHING_STORE,
                business_category="clothing",
            ),
            "turns": [
                _first_touch(),
                _says("What's the cost?", wants_price=True),
            ],
        },
        # 33. T4 Grocery Store
        {
            "id": 33,
            "title": "T4 Grocery Store - lowest tier",
            "expectation": "Grocery band $200-$240. Floor $200.",
            "lead": _lead(
                lead_id="SIM-33",
                business_name="Corner Grocery Store",
                gbp_category=GBPCategory.GROCERY_STORE,
                business_category="grocery",
            ),
            "turns": [
                _first_touch(),
                _says("How much?", wants_price=True),
            ],
        },
        # 34. Volume bracket 6-15 (8 reviews) on T3 Hotel
        {
            "id": 34,
            "title": "Volume bracket 6-15 - T3 Hotel with 8 reviews",
            "expectation": "Hotel medium bracket $290-$335. AI should NOT announce a discount.",
            "lead": _lead(
                lead_id="SIM-34",
                business_name="Skyline Hotel",
                gbp_category=GBPCategory.HOTEL,
                business_category="hotel",
                review_count=8,
                reviews_image_content=[False] * 8,
                reviews_under_one_month=[True] * 8,
            ),
            "turns": [
                _first_touch(),
                _says("We have 8 reviews to deal with. What's the rate?", wants_price=True),
            ],
        },
        # 35. Volume bracket 16-30 (20 reviews) on T3 Plumber - threshold-triggered?
        {
            "id": 35,
            "title": "Volume bracket 16-30 - T3 Plumber with 20 reviews",
            "expectation": "Plumber 16-30 band $265-$295. Still under threshold. Written quote.",
            "lead": _lead(
                lead_id="SIM-35",
                business_name="Industrial Plumbing Solutions",
                gbp_category=GBPCategory.PLUMBER,
                business_category="plumber",
                review_count=20,
                reviews_image_content=[False] * 20,
                reviews_under_one_month=[True] * 20,
            ),
            "turns": [
                _first_touch(),
                _says("We have 20 reviews. What's the per-review rate?", wants_price=True),
            ],
        },
        # 36. Multi-channel - email first touch then SMS reply
        {
            "id": 36,
            "title": "Multi-channel - email first touch then lead replies SMS",
            "expectation": "AI responds via SMS channel with short body, no email footer.",
            "lead": _lead(
                lead_id="SIM-36",
                business_name="Bayside Medical Clinic",
                gbp_category=GBPCategory.MEDICAL_CLINIC,
                business_category="medical_clinic",
                recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                _first_touch(),
                _says("What's the price?", wants_price=True, channel=Channel.SMS),
            ],
        },
        # 37. Auto-capture GBP link from inbound text
        {
            "id": 37,
            "title": "Lead pastes GBP link mid-conversation - auto-capture",
            "expectation": "Lead drops a Google Maps URL. Pipeline auto-captures it, engine can then quote.",
            "lead": _lead(
                lead_id="SIM-37",
                business_name="Twin Peaks Roofing",
                gbp_category=GBPCategory.ROOFING_CONTRACTOR,
                business_category="roofing",
                gbp_link=None,
            ),
            "turns": [
                _first_touch(),
                _says(
                    "Sure - here's the profile https://www.google.com/maps/place/Twin+Peaks+Roofing/@40.123,-74.456,17z. "
                    "What's the rate per review?",
                    wants_price=True,
                ),
            ],
        },
        # 38. Lead names a specific reviewer
        {
            "id": 38,
            "title": "Lead names a specific reviewer - AI must NOT promise removal of named review",
            "expectation": "Lead says 'a guy named Steve B'. AI must not guarantee removal of a named review (escalation_trigger check).",
            "lead": _lead(
                lead_id="SIM-38",
                business_name="Northwest Med Spa",
                gbp_category=GBPCategory.MED_SPA,
                business_category="med_spa",
            ),
            "turns": [
                _first_touch(),
                _says("Can you guarantee you'll remove the one from Steve B that posted last Tuesday?"),
            ],
        },
        # 39. Chargeback question (lighter than full refund)
        {
            "id": 39,
            "title": "Chargeback question (no prior payment context)",
            "expectation": "Lead asks ABOUT chargeback policy, not threatening. Should be in scope.",
            "lead": _lead(
                lead_id="SIM-39",
                business_name="Twin Cities Electric Co",
                gbp_category=GBPCategory.ELECTRICIAN,
                business_category="electrician",
            ),
            "turns": [
                _first_touch(),
                _says("If something goes wrong with billing later, what's your chargeback policy?"),
            ],
        },
        # 40. Vague reply - "tell me more"
        {
            "id": 40,
            "title": "Vague inbound 'tell me more'",
            "expectation": "AI should send a focused next-step message, not escalate.",
            "lead": _lead(
                lead_id="SIM-40",
                business_name="Bayview Landscaping",
                gbp_category=GBPCategory.LANDSCAPER,
                business_category="landscaping",
            ),
            "turns": [
                _first_touch(),
                _says("Tell me more."),
            ],
        },
        # 41. Question stacking - 3 questions in one message
        {
            "id": 41,
            "title": "Stacked questions (pricing + timing + warranty in one message)",
            "expectation": "AI handles multiple topics. Uses approved paragraphs for timing + warranty. Quotes if can_quote.",
            "lead": _lead(
                lead_id="SIM-41",
                business_name="Family Bakery",
                gbp_category=GBPCategory.BAKERY,
                business_category="bakery",
            ),
            "turns": [
                _first_touch(),
                _says(
                    "Quick few questions: what does it cost per review, how fast do they come down, "
                    "and can they come back later?",
                    wants_price=True,
                ),
            ],
        },
        # 42. Named person request - "can I talk to Jayden directly?"
        {
            "id": 42,
            "title": "Lead asks for specific named person",
            "expectation": "AI must NOT promise Jayden will call. Per spec: 'treat a draft that makes such a promise as escalation_trigger'.",
            "lead": _lead(
                lead_id="SIM-42",
                business_name="Riverside HVAC",
                gbp_category=GBPCategory.HVAC_CONTRACTOR,
                business_category="hvac",
            ),
            "turns": [
                _first_touch(),
                _says("Can I just talk to Jayden directly? He helped my buddy."),
            ],
        },
        # 43. Soft-quote mode + CA
        {
            "id": 43,
            "title": "Soft-quote mode + Canadian lead",
            "expectation": "CA Toronto footer. Band returned. USD primary.",
            "lead": _lead(
                lead_id="SIM-43",
                business_name="Maple Dental Group",
                gbp_category=GBPCategory.DENTIST,
                business_category="dentist",
                country=Country.CA,
                phone="+14165550143",
                email="info@mapledental.ca",
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
                soft_quote_mode=True,
            ),
            "turns": [
                _first_touch(),
                _says("What range are we looking at per review?", wants_price=True),
            ],
        },
        # 44. Competitor pricing push
        {
            "id": 44,
            "title": "Competitor undercutting",
            "expectation": "Lead says another firm quoted lower. AI may negotiate (pushback) or hold firm. Should not match arbitrary competitor.",
            "lead": _lead(
                lead_id="SIM-44",
                business_name="Quick Move Movers",
                gbp_category=GBPCategory.MOVING_COMPANY,
                business_category="moving",
            ),
            "turns": [
                _first_touch(),
                _says("Cost per review?", wants_price=True),
                _says(
                    "Hmm - another company quoted me $200 per review. Can you match that?",
                    wants_price=True,
                ),
            ],
        },
        # 45. "What's your guarantee" - approved warranty/pay-anchor pattern
        {
            "id": 45,
            "title": "Lead asks about guarantee",
            "expectation": "AI uses pay-anchor + warranty approved framing. No invented guarantees.",
            "lead": _lead(
                lead_id="SIM-45",
                business_name="Premier Furniture",
                gbp_category=GBPCategory.FURNITURE_STORE,
                business_category="furniture",
            ),
            "turns": [
                _first_touch(),
                _says("What guarantee do you offer?"),
            ],
        },
        # 46. Step-2 pushback (Bug F production-realistic case with seeded triggers)
        {
            "id": 46,
            "title": "Lead at step 2 with prior triggers - 3rd pushback escalates",
            "expectation": "Lead seeded at step=2 with 2 prior triggers, sends 3rd pushback. Pipeline escalates with reason 'negotiation_past_final_step'.",
            "lead": _lead(
                lead_id="SIM-46",
                business_name="Sunset Coffee Shop",
                gbp_category=GBPCategory.COFFEE_SHOP,
                business_category="coffee_shop",
                negotiation_step=2,
                negotiation_triggers=[
                    NegotiationTriggerLogEntry(
                        step_after=1, lead_message_exact="too expensive", at=now,
                    ),
                    NegotiationTriggerLogEntry(
                        step_after=2, lead_message_exact="still steep", at=now,
                    ),
                ],
            ),
            "turns": [
                _says(
                    "Look, that's still too high. Can you do better?",
                    wants_price=True,
                ),
            ],
        },
        # 47. Image-content confirmation question (AI asks about images)
        {
            "id": 47,
            "title": "GBP link missing - AI shouldn't ask about review images per gbp_gate",
            "expectation": "GBP link present, so AI must NOT ask the lead about reviews directly per gbp_gate check.",
            "lead": _lead(
                lead_id="SIM-47",
                business_name="Smile Center Dentistry",
                gbp_category=GBPCategory.DENTIST,
                business_category="dentist",
                reviews_image_content=[True, False],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                _first_touch(),
                _says("I want to remove some reviews. What info do you need from me?"),
            ],
        },
        # 48. Notes images observed - mention image angle
        {
            "id": 48,
            "title": "Lead anxiety about paying for nothing",
            "expectation": "AI uses approved PAY-ANCHOR paragraph to reassure.",
            "lead": _lead(
                lead_id="SIM-48",
                business_name="Westside Movers",
                gbp_category=GBPCategory.MOVING_COMPANY,
                business_category="moving",
            ),
            "turns": [
                _first_touch(),
                _says("I'm worried about paying you and nothing happening. What's the risk on my side?"),
            ],
        },
        # 49. GBP inspection data already present
        {
            "id": 49,
            "title": "GBP inspection facts available - AI uses them directly",
            "expectation": "gbp_inspection passed with image+recency facts. AI skips questions and moves to commercial.",
            "lead": _lead(
                lead_id="SIM-49",
                business_name="Heights Orthodontics",
                gbp_category=GBPCategory.DENTIST,
                business_category="dental",
                reviews_image_content=[True, True],
                reviews_under_one_month=[True, True],
            ),
            "turns": [
                {
                    "label": "First touch with GBP inspection facts",
                    "inbound": None,
                    "channel": Channel.EMAIL,
                    "sequence_stage": "first_touch",
                    "wants_price": False,
                    "gbp_inspection": {
                        "status": "success",
                        "business_name_extracted": "Heights Orthodontics",
                        "review_count_inferred": 2,
                        "any_review_has_images": True,
                        "inferred_recency_profile": "all_under_1_month",
                        "category_hints": ["dental"],
                    },
                },
            ],
        },
        # 50. Inbound asks about agreement/paperwork process - acceptance should NOT fire
        {
            "id": 50,
            "title": "Asking how-to-sign vs accepting the quote",
            "expectation": "Lead asks ABOUT the agreement, not accepting. Acceptance must NOT fire — should answer DocuSign-only line and continue selling.",
            "lead": _lead(
                lead_id="SIM-50",
                business_name="Coastal Plumbing",
                gbp_category=GBPCategory.PLUMBER,
                business_category="plumber",
            ),
            "turns": [
                _first_touch(),
                _says("What's the rate?", wants_price=True),
                _says("How do I sign? Is there a contract or DocuSign?"),
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

        kwargs: dict[str, Any] = dict(
            lead=lead,
            transcript=list(transcript),
            channel=turn["channel"],
            sequence_stage=turn["sequence_stage"],
            inbound_message=turn["inbound"],
            wants_price=turn["wants_price"],
            now_override=now,
        )
        if "gbp_inspection" in turn:
            kwargs["gbp_inspection"] = turn["gbp_inspection"]

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
    out.append(f"# Conversation {conv['id']:02d} — {conv['title']}\n")
    out.append(f"**Expected**: {conv['expectation']}\n")
    lead = conv["lead"]
    out.append(
        f"\n**Lead**: {lead.first_name} {lead.last_name} / {lead.business_name} ({lead.country.value}) "
        f"| category=`{lead.gbp_category.value if lead.gbp_category else 'None'}` "
        f"| reviews={lead.review_count} {lead.recency_profile.value} "
        f"images={lead.reviews_image_content} recent={lead.reviews_under_one_month}"
        f"{' soft_quote' if lead.soft_quote_mode else ''}"
        f"{' kill-switch' if not lead.ai_quote_allowed else ''}"
        f" step={lead.negotiation_step}\n"
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
                    "Auto-captured",
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
        "--out", default=str(REPO_ROOT / "tests" / "CONVERSATION_TRACES_30.md")
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
        "# ReviewArmour v2 - 30 More Conversations (Coverage Expansion)\n\n"
        f"_Generated {datetime.now(timezone.utc).isoformat()}_\n\n"
        "Distinct from the original 3 + 20. Drives untested behaviors: approved "
        "METHODOLOGY / WARRANTY / DocuSign strings, untested GBP categories, "
        "volume brackets 6-15 / 16-30, multi-channel, GBP auto-capture, "
        "named-person request, competitor pricing pushback, soft-quote + CA, "
        "GBP inspection data path, agreement-process question vs acceptance, "
        "Bug F production case (step=2 + triggers + pushback -> escalate).\n\n---\n"
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
