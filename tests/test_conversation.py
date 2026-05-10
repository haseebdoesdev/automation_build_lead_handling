from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from reviewarmour.conversation import (
    CustomerReviewRequestModule,
    ConversationModule,
    ConversationState,
    OutboundPipeline,
    SelfCorrectionModule,
    check_stall,
    evaluate_post_quote_stall,
    is_price_question_escalation,
    should_escalate_inbound,
    stall_page_payload,
)
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.self_correction import extract_json_object
from reviewarmour.scheduling import defer_sunday_touch_to_monday_8am_est


class _TB:
    __slots__ = ("type", "text")

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class FakeMessagesAPI:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        if not self._responses:
            raise RuntimeError("FakeMessagesAPI: no scripted responses left")
        return SimpleNamespace(content=[_TB(self._responses.pop(0))])


@pytest.fixture
def sample_lead() -> LeadRecord:
    return LeadRecord(
        lead_id="L1",
        first_name="Sam",
        last_name="Lee",
        business_name="Lee Plumbing",
        country=Country.US,
        phone="+15550002",
        email="sam@example.com",
        gbp_link="https://g.page/lee",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )


def test_extract_json_object_strips_fence() -> None:
    raw = '```json\n{"verdict": "pass", "failed_checks": [], "suggested_fixes": [], "escalation_reason": null}\n```'
    d = extract_json_object(raw)
    assert d["verdict"] == "pass"


def test_price_question_escalates(sample_lead: LeadRecord) -> None:
    assert is_price_question_escalation("Hi, how much is this?")


def test_lawsuit_escalates() -> None:
    assert should_escalate_inbound("We may file a lawsuit") is not None


def test_pipeline_how_much_escalates_no_draft(sample_lead: LeadRecord) -> None:
    conv = ConversationModule(FakeMessagesAPI([]))
    sc = SelfCorrectionModule(FakeMessagesAPI([]))
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    res = pipe.run(
        lead=sample_lead,
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="How much would this run?",
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.action == "escalate"


def test_acceptance_sets_quote_accepted(sample_lead: LeadRecord) -> None:
    conv = ConversationModule(FakeMessagesAPI([]))
    pass_json = json.dumps(
        {
            "verdict": "pass",
            "failed_checks": [],
            "suggested_fixes": [],
            "escalation_reason": None,
        }
    )
    sc = SelfCorrectionModule(FakeMessagesAPI([pass_json]))
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    res = pipe.run(
        lead=sample_lead,
        transcript=[{"role": "assistant", "body": "Our price is 450 USD per review."}],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="Let's do it.",
        quoted_previously=True,
    )
    assert res.outcome == "send"
    assert res.state_updates.get("ai_conversation_state") == "quote_accepted"
    assert res.handoff_payload and res.handoff_payload.get("type") == "quote_to_invoice"


def test_stall_after_six_hours(sample_lead: LeadRecord) -> None:
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=7)
    assert check_stall(last_commercial_turn_at=t0, now=t1, soft_quote_mode=False)
    assert not check_stall(last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=False)


def test_stall_soft_mode_two_hours(sample_lead: LeadRecord) -> None:
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    assert check_stall(last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=True)


def test_stall_payload_fields(sample_lead: LeadRecord) -> None:
    payload = stall_page_payload(sample_lead, [{"role": "lead", "body": "ok"}], 425)
    assert payload["last_quote_offered"] == 425
    assert payload["business"] == sample_lead.business_name


def test_stalled_post_quote_state_payload(sample_lead: LeadRecord) -> None:
    est = ZoneInfo("America/New_York")
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=est)
    now = t0 + timedelta(hours=7)
    payload = evaluate_post_quote_stall(
        lead=sample_lead,
        transcript=[{"role": "lead", "body": "Sounds good"}],
        last_commercial_turn_at=t0,
        now=now,
        last_quote=425,
    )
    assert payload is not None
    assert payload["ai_conversation_state"] == "stalled_post_quote"
    assert payload["salesman_page"]["last_quote_offered"] == 425


def test_three_failed_redrafts_human_queue(sample_lead: LeadRecord) -> None:
    draft = json.dumps({"action": "send", "channel": "email", "subject": "s", "body": "bad draft"})
    fix = json.dumps(
        {
            "verdict": "fix",
            "failed_checks": ["copy_rules: em dash"],
            "suggested_fixes": ["remove em dash"],
            "escalation_reason": None,
        }
    )
    conv = ConversationModule(FakeMessagesAPI([draft, draft, draft]))
    sc = SelfCorrectionModule(FakeMessagesAPI([fix, fix, fix]))
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    res = pipe.run(
        lead=sample_lead,
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        wants_price=True,
    )
    assert res.outcome == "human_queue"
    assert res.human_queue_payload is not None


def test_three_no_progress_escalates(sample_lead: LeadRecord) -> None:
    conv = ConversationModule(FakeMessagesAPI([]))
    sc = SelfCorrectionModule(FakeMessagesAPI([]))
    pipe = OutboundPipeline(conversation=conv, self_correction=sc)
    st = ConversationState(consecutive_no_progress_turns=2)
    res = pipe.run(
        lead=sample_lead,
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="still thinking",
        meaningful_progress=False,
        conversation_state=st,
    )
    assert res.outcome == "escalate"
    assert res.draft and "no_progress" in (res.draft.reason or "")


def test_review_request_star_ask_escalates_via_self_correction() -> None:
    customer = {
        "first_name": "Ann",
        "business_name": "Ann Co",
        "completed_job_summary": "removed the 1-star review on your profile",
    }
    bad = json.dumps(
        {"action": "send", "channel": "sms", "subject": None, "body": "Please leave us 5 stars at https://g.page/x"}
    )
    esc = json.dumps(
        {
            "verdict": "escalate",
            "failed_checks": ["scope: star rating request"],
            "suggested_fixes": [],
            "escalation_reason": "forbidden star ask",
        }
    )
    mod = CustomerReviewRequestModule(FakeMessagesAPI([bad]))
    draft = mod.draft(
        customer=customer,
        touch_number=1,
        channel=Channel.SMS,
        gbp_review_link="https://g.page/review-armour",
    )
    sc = SelfCorrectionModule(FakeMessagesAPI([esc]))
    v = sc.review(
        draft_subject=None,
        draft_body=draft.body or "",
        channel="sms",
        lead_record={
            "first_name": customer["first_name"],
            "business_name": customer["business_name"],
            "country": "US",
        },
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "escalate"


def test_review_request_discount_escalates() -> None:
    customer = {
        "first_name": "Ann",
        "business_name": "Ann Co",
        "completed_job_summary": "removed the targeted review",
    }
    bad = json.dumps(
        {
            "action": "send",
            "channel": "email",
            "subject": "Hi",
            "body": "Leave a review for $50 off your next removal.",
        }
    )
    esc = json.dumps(
        {
            "verdict": "escalate",
            "failed_checks": ["scope: incentive language"],
            "suggested_fixes": [],
            "escalation_reason": "incentive",
        }
    )
    mod = CustomerReviewRequestModule(FakeMessagesAPI([bad]))
    draft = mod.draft(customer=customer, touch_number=2, channel=Channel.EMAIL, gbp_review_link="https://g.page/x")
    sc = SelfCorrectionModule(FakeMessagesAPI([esc]))
    v = sc.review(
        draft_subject=draft.subject,
        draft_body=draft.body or "",
        channel="email",
        lead_record={"first_name": "Ann", "business_name": "Ann Co", "country": "US"},
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "escalate"


def test_sunday_defer_moves_to_monday_8am() -> None:
    sunday_utc = datetime(2026, 5, 10, 10, 30, tzinfo=timezone.utc)
    out = defer_sunday_touch_to_monday_8am_est(sunday_utc)
    local = out.astimezone(ZoneInfo("America/New_York"))
    assert local.weekday() == 0
    assert local.hour == 8
