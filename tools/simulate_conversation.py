"""Live multi-turn conversation simulator for spec v2 review.

Drives the full OutboundPipeline (ConversationModule + SelfCorrectionModule +
AdaptivePriceSelector) turn-by-turn against the real Anthropic API and writes
a human-readable trace to stdout AND a markdown report. Used for end-to-end
spec v2 manual verification — there are no auto-assertions; the reviewer
reads the trace and decides if the AI is "on the mark."

Requires: ANTHROPIC_API_KEY in the environment.

Usage::

    python tools/simulate_conversation.py [--out tests/CONVERSATION_TRACES.md]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Capture pipeline logger output for the trace.
import io

LOG_BUFFER = io.StringIO()
_log_handler = logging.StreamHandler(LOG_BUFFER)
_log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
logging.getLogger("reviewarmour").addHandler(_log_handler)
logging.getLogger("reviewarmour").setLevel(logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Force UTF-8 stdout on Windows so the AI's unicode (em dashes, quotes, etc.)
# in printed status lines does not crash with cp1252.
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
    EngagementLevel,
    GBPCategory,
    LeadRecord,
    LeadTone,
    RecencyProfile,
)
from reviewarmour.self_correction import (  # noqa: E402
    SelfCorrectionModule,
    make_anthropic_client,
)
from reviewarmour.settings import LLMRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Conversation definitions
# ---------------------------------------------------------------------------


def conversation_1_t1_phone_route() -> dict[str, Any]:
    """T1 Dentist, 2 over-month text-only reviews -- phone-call threshold should
    trigger. AI must NOT quote a dollar figure; should pivot to phone call."""
    lead = LeadRecord(
        lead_id="SIM-1",
        first_name="Sarah",
        last_name="Chen",
        business_name="Bright Smile Dental Group",
        country=Country.US,
        phone="+15551234567",
        email="sarah@brightsmile.example",
        gbp_link="https://maps.google.com/place/bright-smile-dental",
        review_count=2,
        recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
        business_category="dental",
        gbp_category=GBPCategory.DENTIST,
        reviews_image_content=[False, False],
        reviews_under_one_month=[False, False],
        lead_source="website_form",
    )
    turns = [
        # Turn 1: first touch (no inbound)
        {
            "label": "T1 first touch (outbound)",
            "inbound": None,
            "channel": Channel.EMAIL,
            "sequence_stage": "first_touch",
            "wants_price": False,
        },
        # Turn 2: lead asks for price
        {
            "label": "T2 lead asks for price",
            "inbound": (
                "Hi, thanks for reaching out. We do have a couple of bad reviews "
                "that are clearly unfair. What does it cost to get them removed?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": True,
        },
        # Turn 3: lead pushes for a number
        {
            "label": "T3 lead presses for a written number",
            "inbound": (
                "I appreciate that, but I'd really like a ballpark figure before "
                "setting up a call. Can you just tell me what to expect?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": True,
        },
    ]
    return {
        "id": 1,
        "title": "T1 Dentist over-month -> phone-call threshold",
        "expectation": (
            "Engine sets phone_call_threshold_triggered=true; pipeline produces "
            "send draft with NO dollar figure; AI pivots to scheduling a call "
            "with the specialist. Turn 1 is first-touch (no pricing). Turn 2 "
            "and Turn 3 must contain NO USD figure."
        ),
        "lead": lead,
        "turns": turns,
    }


def conversation_2_t3_negotiation() -> dict[str, Any]:
    """T3 Plumber, 3 image+recent reviews -- written quote ~$330-$370. Lead
    pushes back once -- step 1 (~12.5% off). Lead accepts at neg_1."""
    lead = LeadRecord(
        lead_id="SIM-2",
        first_name="Joe",
        last_name="Martinez",
        business_name="Acme Plumbing Co",
        country=Country.US,
        phone="+15559876543",
        email="joe@acmeplumbing.example",
        gbp_link="https://maps.google.com/place/acme-plumbing",
        review_count=3,
        recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
        business_category="plumber",
        gbp_category=GBPCategory.PLUMBER,
        reviews_image_content=[True, False, True],
        reviews_under_one_month=[True, True, False],
        lead_source="website_form",
    )
    turns = [
        {
            "label": "T1 first touch (outbound)",
            "inbound": None,
            "channel": Channel.EMAIL,
            "sequence_stage": "first_touch",
            "wants_price": False,
        },
        {
            "label": "T2 lead asks the price",
            "inbound": (
                "Thanks. There are 3 reviews on our profile that are pretty unfair. "
                "What's your price per review?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": True,
        },
        {
            "label": "T3 lead pushes back (negotiation step 1)",
            "inbound": (
                "That feels a bit steep for us. Is there any flexibility on the per-review rate?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": True,
        },
        {
            "label": "T4 lead accepts the negotiated price",
            "inbound": (
                "Okay, that works. Let's move forward at that rate. What's the next step?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": False,
        },
    ]
    return {
        "id": 2,
        "title": "T3 Plumber -> written quote -> negotiation step 1 -> acceptance",
        "expectation": (
            "Turn 2: written quote in $330-$370 range (lower end given image+recent). "
            "Turn 3: negotiation step bumps to 1, new price ≈ 87.5% of step 0, still in band. "
            "Turn 4: pipeline detects quote acceptance, signals invoice handoff via state_updates."
        ),
        "lead": lead,
        "turns": turns,
    }


def conversation_3_t1_exception() -> dict[str, Any]:
    """T1 Dentist, 2 image+under-1-month reviews -- T1 written exception
    applies. AI may quote up to $450 in writing."""
    lead = LeadRecord(
        lead_id="SIM-3",
        first_name="Maria",
        last_name="Lopez",
        business_name="Sunshine Family Dentistry",
        country=Country.US,
        phone="+15553334444",
        email="maria@sunshinedental.example",
        gbp_link="https://maps.google.com/place/sunshine-family-dentistry",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="dental",
        gbp_category=GBPCategory.DENTIST,
        reviews_image_content=[True, True],
        reviews_under_one_month=[True, True],
        lead_source="website_form",
    )
    turns = [
        {
            "label": "T1 first touch (outbound)",
            "inbound": None,
            "channel": Channel.EMAIL,
            "sequence_stage": "first_touch",
            "wants_price": False,
        },
        {
            "label": "T2 lead asks about timing first",
            "inbound": (
                "Thanks for reaching out. Two reviews showed up last week with photos "
                "of food we don't even serve. How fast can these come down?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": False,
        },
        {
            "label": "T3 lead asks the price",
            "inbound": (
                "Okay, that timeline sounds reasonable. What's the cost per review?"
            ),
            "channel": Channel.EMAIL,
            "sequence_stage": "reply",
            "wants_price": True,
        },
    ]
    return {
        "id": 3,
        "title": "T1 Dentist exception -> written quote up to $450",
        "expectation": (
            "Turn 2: timeline answer using the approved under-1-month paragraph. "
            "Turn 3: engine recognizes T1 exception (≤2 reviews, all image+recent), "
            "allows written quote at $400-$450. Draft contains a USD figure ≤$450."
        ),
        "lead": lead,
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


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
        "adaptive_inputs": c.adaptive_inputs,
        "escalate": c.escalate,
        "escalation_reason": c.escalation_reason,
    }


def run_conversation(conv: dict[str, Any], pipeline: OutboundPipeline) -> list[dict[str, Any]]:
    """Run all turns; return per-turn trace dicts."""
    lead = conv["lead"]
    transcript: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for idx, turn in enumerate(conv["turns"], start=1):
        # Clear log buffer before this turn so per-turn logs are clean.
        LOG_BUFFER.seek(0)
        LOG_BUFFER.truncate(0)

        # If there's an inbound message, append it to transcript.
        if turn["inbound"]:
            transcript.append(
                {
                    "role": "lead",
                    "channel": turn["channel"].value,
                    "content": turn["inbound"],
                }
            )

        # Run pipeline.
        result = pipeline.run(
            lead=lead,
            transcript=list(transcript),
            channel=turn["channel"],
            sequence_stage=turn["sequence_stage"],
            inbound_message=turn["inbound"],
            wants_price=turn["wants_price"],
            now_override=now,
        )

        # Capture logs from this turn.
        logs = LOG_BUFFER.getvalue()

        # If the pipeline sent a draft, append the AI's outbound to transcript.
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

        # Apply state_updates the pipeline returned (for negotiation_step etc).
        # In production CRM would persist these; here we just sync onto the lead.
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
                "lead_negotiation_step_before": (
                    lead.negotiation_step
                    if (result.state_updates or {}).get("negotiation_step") is None
                    else result.state_updates.get("negotiation_step")
                ),
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


# ---------------------------------------------------------------------------
# Trace formatter
# ---------------------------------------------------------------------------


def format_trace_md(conv: dict[str, Any], turns: list[dict[str, Any]]) -> str:
    out: list[str] = []
    out.append(f"# Conversation {conv['id']} — {conv['title']}\n")
    out.append(f"**Expected behavior**: {conv['expectation']}\n")
    lead = conv["lead"]
    out.append("\n## Lead context\n")
    out.append(
        f"- **Lead**: {lead.first_name} {lead.last_name} / {lead.business_name} ({lead.country.value})\n"
        f"- **Category**: `{lead.gbp_category.value if lead.gbp_category else 'None'}`\n"
        f"- **Reviews**: {lead.review_count} total; recency={lead.recency_profile.value}; "
        f"images={lead.reviews_image_content}; under_1mo={lead.reviews_under_one_month}\n"
        f"- **GBP link**: {lead.gbp_link or 'None'}\n"
    )
    out.append("\n---\n")

    for t in turns:
        out.append(f"\n## Turn {t['turn_num']} — {t['label']}\n")
        out.append(f"_(channel={t['channel']}, stage={t['sequence_stage']}, wants_price={t['wants_price']})_\n")

        if t["inbound"]:
            out.append(f"\n### Lead message\n> {t['inbound']}\n")
        else:
            out.append("\n_(no inbound — outbound-only turn)_\n")

        out.append("\n### Pipeline outcome\n")
        out.append(f"- **outcome**: `{t['outcome']}`\n")
        out.append(f"- **draft.action**: `{t['draft_action']}`\n")
        if t["draft_reason"]:
            out.append(f"- **draft.reason**: `{t['draft_reason']}`\n")

        if t["commercial"]:
            c = t["commercial"]
            out.append("\n### Commercial result\n")
            out.append("```json\n")
            out.append(json.dumps(c, indent=2, default=str))
            out.append("\n```\n")

        if t["sc_attempts"]:
            out.append("\n### Self-correction attempts\n")
            for a in t["sc_attempts"]:
                out.append(
                    f"- attempt {a.get('attempt')}: verdict=`{a.get('verdict')}` "
                    f"failed=`{a.get('failed_checks')}`\n"
                )

        if t["state_updates"]:
            out.append("\n### State updates\n")
            out.append("```json\n")
            out.append(json.dumps(t["state_updates"], indent=2, default=str))
            out.append("\n```\n")

        if t["draft_body"]:
            out.append("\n### AI draft\n")
            if t["draft_subject"]:
                out.append(f"**Subject**: {t['draft_subject']}\n\n")
            out.append("```\n")
            out.append(t["draft_body"])
            out.append("\n```\n")

        if t["logs"].strip():
            out.append("\n### Pipeline logs\n")
            out.append("```\n")
            out.append(t["logs"].strip())
            out.append("\n```\n")

        out.append("\n---\n")

    return "".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default=str(REPO_ROOT / "tests" / "CONVERSATION_TRACES.md")
    )
    parser.add_argument(
        "--only",
        type=int,
        default=None,
        help="Only run conversation 1, 2, or 3",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = make_anthropic_client()
    runtime = LLMRuntime()
    conv_module = ConversationModule(client, runtime=runtime)
    sc_module = SelfCorrectionModule(client, runtime=runtime)
    adaptive = AdaptivePriceSelector(client, runtime=runtime)
    pipeline = OutboundPipeline(
        conversation=conv_module,
        self_correction=sc_module,
        adaptive_price_selector=adaptive,
    )

    convs = [
        conversation_1_t1_phone_route(),
        conversation_2_t3_negotiation(),
        conversation_3_t1_exception(),
    ]
    if args.only is not None:
        convs = [c for c in convs if c["id"] == args.only]

    all_traces: list[str] = []
    all_traces.append(
        "# ReviewArmour v2 Live Conversation Traces\n\n"
        f"_Generated {datetime.now(timezone.utc).isoformat()}_\n\n"
        "These three conversations exercise the full production pipeline "
        "(ConversationModule + SelfCorrectionModule + AdaptivePriceSelector) "
        "against the real Anthropic API. No auto-assertions — these traces "
        "are for human review against spec v2 expected behavior.\n\n"
        "---\n"
    )

    for conv in convs:
        print(f"=== Running conversation {conv['id']}: {conv['title']} ===")
        turns = run_conversation(conv, pipeline)
        trace = format_trace_md(conv, turns)
        all_traces.append(trace)
        print(f"  -> {len(turns)} turns, outcomes: {[t['outcome'] for t in turns]}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(all_traces), encoding="utf-8")
    print(f"\nTrace written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
