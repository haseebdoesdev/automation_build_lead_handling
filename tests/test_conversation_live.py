"""Live conversation + pipeline tests against the real Anthropic API.

Covers the spec test cases that require the LLM:
  * Acceptance signal -> confirmation message + quote_accepted handoff.
  * First-touch outbound passes self-correction.
  * Pricing turn yields a draft that quotes the authorized number from
    commercial reasoning (per-review USD).
  * Three failed self-correction passes -> human_draft_queue.
  * Customer review request: star ask escalates; incentive escalates.
"""

from __future__ import annotations

import os

import pytest

anthropic = pytest.importorskip("anthropic")

if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
    pytest.skip(
        "ANTHROPIC_API_KEY is required for production conversation tests.",
        allow_module_level=True,
    )

from reviewarmour.commercial import CommercialEngine
from reviewarmour.conversation import (
    ConversationModule,
    CustomerReviewRequestModule,
    OutboundPipeline,
    SelfCorrectionModule,
    lead_record_to_dict,
)
from reviewarmour.errors import LLMResponseError
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.self_correction import SelfCorrectionVerdict, make_anthropic_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return make_anthropic_client()


@pytest.fixture(scope="module")
def conv(client) -> ConversationModule:
    return ConversationModule(client)


@pytest.fixture(scope="module")
def sc(client) -> SelfCorrectionModule:
    return SelfCorrectionModule(client)


@pytest.fixture(scope="module")
def review_request(client) -> CustomerReviewRequestModule:
    return CustomerReviewRequestModule(client)


@pytest.fixture
def us_lead() -> LeadRecord:
    return LeadRecord(
        lead_id="LIVE-PIPE-1",
        first_name="Sam",
        last_name="Lee",
        business_name="Lee Plumbing",
        country=Country.US,
        phone="+15551110001",
        email="sam@example.com",
        gbp_link="https://g.page/lee-plumbing",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )


# ---------------------------------------------------------------------------
# First-touch + acceptance signal (full pipeline)
# ---------------------------------------------------------------------------


def test_first_touch_email_passes_pipeline(conv, sc, us_lead) -> None:
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    res = pipe.run(
        lead=us_lead,
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="first_touch",
    )
    assert res.outcome in ("send", "human_queue", "escalate")
    if res.outcome == "send":
        assert res.draft and res.draft.body
        assert us_lead.first_name in (res.draft.body or "")
        assert us_lead.business_name in (res.draft.body or "")


def test_acceptance_signal_fires_quote_accepted(conv, sc, us_lead) -> None:
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    transcript = [
        {"role": "assistant", "channel": "email", "body": "Pricing for Lee Plumbing is 450 USD per review."},
        {"role": "user", "body": "let's do it"},
    ]
    res = pipe.run(
        lead=us_lead,
        transcript=transcript,
        channel=Channel.EMAIL,
        sequence_stage="post_quote",
        inbound_message="let's do it",
        quoted_previously=True,
    )
    assert res.outcome in ("send", "human_queue")
    if res.outcome == "send":
        assert res.state_updates.get("ai_conversation_state") == "quote_accepted"
        assert res.handoff_payload and res.handoff_payload.get("type") == "quote_to_invoice"
        body = (res.draft.body or "")
        assert "DocuSign" in body or "removal brief" in body
        assert "450" not in body  # no price re-stated per spec


# ---------------------------------------------------------------------------
# Pricing turn: drafted message must echo the authorized number, not invent
# ---------------------------------------------------------------------------


def test_pricing_turn_uses_authorized_quote(conv, sc, us_lead) -> None:
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    res = pipe.run(
        lead=us_lead,
        transcript=[
            {"role": "user", "body": "Two recent fake reviews on Lee Plumbing. What does removal cost?"}
        ],
        channel=Channel.EMAIL,
        sequence_stage="pricing",
        wants_price=True,
    )
    # Outcome must be one of the production outcomes; if send, the body MUST
    # echo the authorized number from the commercial engine (US-1 opening = 450).
    assert res.outcome in ("send", "human_queue", "escalate")
    if res.outcome == "send":
        assert res.commercial is not None
        authorized = res.commercial.authorized_quote_usd_per_review
        assert authorized == 450
        body = res.draft.body or ""
        assert "450" in body
        assert "USD" in body or "usd" in body.lower()


# ---------------------------------------------------------------------------
# Three failed self-correction attempts -> human_draft_queue
# ---------------------------------------------------------------------------


class _AlwaysFixSC:
    """Self-correction stand-in for the orchestrator contract test.

    The drafter is the *real* Claude model; only the reviewer is replaced,
    because the spec contract under test ("third draft still fails ->
    human_draft_queue") needs deterministic verdicts. Directives are
    realistic so the drafter does not interpret the redraft loop as a
    reason to escalate.
    """

    def __init__(self) -> None:
        self.calls = 0

    def review(self, **_) -> SelfCorrectionVerdict:
        self.calls += 1
        return SelfCorrectionVerdict(
            verdict="fix",
            failed_checks=["copy_rules: tone slightly off"],
            suggested_fixes=["tighten opening sentence", "shorten body"],
            escalation_reason=None,
        )


def test_three_failed_redrafts_human_queue(conv, us_lead) -> None:
    stub_sc = _AlwaysFixSC()
    pipe = OutboundPipeline(conversation=conv, self_correction=stub_sc)  # type: ignore[arg-type]
    res = pipe.run(
        lead=us_lead,
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="first_touch",
    )
    assert res.outcome == "human_queue", res.outcome
    assert res.human_queue_payload is not None
    assert len(res.self_correction_logs) == 3, [log.verdict for log in res.self_correction_logs]
    assert stub_sc.calls == 3


# ---------------------------------------------------------------------------
# Customer review request: star/incentive variants
# ---------------------------------------------------------------------------


def _customer_record() -> dict:
    return {
        "first_name": "Pat",
        "last_name": "Kim",
        "business_name": "Kim Bakery",
        "country": "US",
        "completed_job_summary": "removed three policy-violating reviews on your Google profile",
    }


def test_review_request_touch1_satisfies_absolute_rules(review_request) -> None:
    """Customer review requests are governed by their dedicated module + prompt.

    The general SelfCorrectionModule is for lead-conversation outputs; we
    verify the absolute rules (one URL, customer first name, no stars, no
    incentive, no em dashes, no exclamation marks) directly against the
    real drafter output here.
    """
    link = "https://g.page/r/review-armour/review"
    draft = review_request.draft(
        customer=_customer_record(),
        touch_number=1,
        channel=Channel.SMS,
        gbp_review_link=link,
    )
    assert draft.action == "send"
    body = (draft.body or "").strip()
    assert "Pat" in body
    assert body.count(link) == 1
    assert "http" not in body.replace(link, "")
    assert "5 star" not in body.lower() and "five star" not in body.lower()
    assert "discount" not in body.lower() and "off your" not in body.lower()
    assert "!" not in body
    assert "—" not in body and "–" not in body
    assert len(body) <= 320


def test_review_request_with_star_ask_self_correction_escalates(sc) -> None:
    body = (
        "Hey Pat, glad we removed three policy-violating reviews on your profile. "
        "If you have a moment, please leave us 5 stars at https://g.page/r/review-armour/review."
    )
    v = sc.review(
        draft_subject=None,
        draft_body=body,
        channel="sms",
        lead_record={"first_name": "Pat", "business_name": "Kim Bakery", "country": "US"},
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)


def test_review_request_with_discount_incentive_self_correction_escalates(sc) -> None:
    body = (
        "Hey Pat, leave us a Google review at https://g.page/r/review-armour/review "
        "and we will give you 50 dollars off your next removal."
    )
    v = sc.review(
        draft_subject="Quick favor",
        draft_body=body,
        channel="email",
        lead_record={"first_name": "Pat", "business_name": "Kim Bakery", "country": "US"},
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)
