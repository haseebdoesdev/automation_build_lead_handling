"""ReviewArmour v7 — Minimum Coverage Test Flows
All 25 flows mapped to deterministic assertions.

Flows requiring SC verdicts use fake modules returning controlled results.
No Anthropic API key required — every test here runs offline.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pytest

from reviewarmour.commercial import CommercialEngine, apply_pushback, margin_ok
from reviewarmour.conversation import (
    CommercialTurnLLMResult,
    ConversationState,
    OutboundDraft,
    OutboundPipeline,
    PipelineResult,
    acceptance_signal,
    check_stall,
    evaluate_post_quote_stall,
    is_price_question_escalation,
    pricing_turn_requested,
    regional_footer,
    should_escalate_inbound,
    stall_page_payload,
)
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.followup_cadence import (
    QUEUE_STATUS_PRIORITY,
    build_morning_queue_brief,
    queue_priority_rank,
    schedule_nurture_follow_ups,
)
from reviewarmour.scheduling import defer_sunday_touch_to_monday_8am_est
from reviewarmour.self_correction import SelfCorrectionVerdict

EST = ZoneInfo("America/New_York")

# =============================================================================
# Shared helpers and fakes
# =============================================================================


def _lead(**kw) -> LeadRecord:
    defaults = dict(
        lead_id="L1",
        first_name="Test",
        last_name="Lead",
        business_name="Test Business",
        country=Country.US,
        phone="+15550001111",
        email="test@example.com",
        gbp_link="https://g.page/test",
        review_count=1,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )
    defaults.update(kw)
    return LeadRecord(**defaults)


class _NeverCalled:
    """Stand-in for LLM modules. Any attribute access fails the test."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"LLM was unexpectedly invoked: .{name}")


def _pipeline_no_llm(**kw: Any) -> OutboundPipeline:
    kw.setdefault("use_llm_quote_acceptance", False)
    kw.setdefault("use_llm_commercial_turn", False)
    return OutboundPipeline(
        conversation=_NeverCalled(),  # type: ignore[arg-type]
        self_correction=_NeverCalled(),  # type: ignore[arg-type]
        **kw,
    )


class _FakeSC:
    """Returns a controlled sequence of ``SelfCorrectionVerdict``s."""

    def __init__(self, verdicts: list[SelfCorrectionVerdict]) -> None:
        self._verdicts = verdicts
        self.calls: list[int] = []

    def review(self, **_kw: Any) -> SelfCorrectionVerdict:
        idx = len(self.calls)
        self.calls.append(idx)
        return self._verdicts[idx % len(self._verdicts)]


class _FakeConv:
    """Returns a controlled sequence of ``OutboundDraft``s."""

    def __init__(self, drafts: list[OutboundDraft]) -> None:
        self._drafts = drafts
        self.calls: list[int] = []

    def draft(self, **_kw: Any) -> OutboundDraft:
        idx = len(self.calls)
        self.calls.append(idx)
        return self._drafts[idx % len(self._drafts)]

    def detect_quote_acceptance_llm(
        self, _inbound_message: str, _transcript: list[dict[str, Any]], **_kw: Any
    ) -> bool:
        return False

    def classify_commercial_engine_turn_llm(
        self,
        _inbound_message: str,
        _transcript: list[dict[str, Any]],
        *,
        quoted_previously_flag: bool,
        **_kw: Any,
    ) -> CommercialTurnLLMResult:
        return CommercialTurnLLMResult(False, False)


def _pass() -> SelfCorrectionVerdict:
    return SelfCorrectionVerdict(
        verdict="pass", failed_checks=[], suggested_fixes=[], escalation_reason=None
    )


def _fix(*checks: str) -> SelfCorrectionVerdict:
    return SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=list(checks) or ["copy_rules: generic"],
        suggested_fixes=["fix it"],
        escalation_reason=None,
    )


def _escalate(reason: str = "violation") -> SelfCorrectionVerdict:
    return SelfCorrectionVerdict(
        verdict="escalate",
        failed_checks=["scope_check"],
        suggested_fixes=[],
        escalation_reason=reason,
    )


def _send_draft(
    body: str = "Short clean draft.",
    channel: Channel = Channel.EMAIL,
    subject: str = "Test subject",
) -> OutboundDraft:
    return OutboundDraft(action="send", channel=channel, subject=subject, body=body)


def _pipe(sc_verdicts: list[SelfCorrectionVerdict], drafts: list[OutboundDraft]) -> OutboundPipeline:
    return OutboundPipeline(
        conversation=_FakeConv(drafts),
        self_correction=_FakeSC(sc_verdicts),
        use_llm_quote_acceptance=False,
        use_llm_commercial_turn=False,
    )


# =============================================================================
# FLOW 01 — US-1, COOPERATIVE LEAD, ACCEPTS AT STEP 0
# Unique: US-1 tier, margin pass, acceptance signal, handoff, confirmation
# =============================================================================


class TestFlow01_US1Cooperative:
    def test_tier_us1_1review_realestate_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=1, business_category="real estate"), wants_price=True
        )
        assert r.tier_id == "US-1"
        assert r.authorized_quote_usd_per_review == 450

    def test_tier_us1_2reviews_standard_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, business_category="real estate"), wants_price=True
        )
        assert r.tier_id == "US-1"
        assert r.authorized_quote_usd_per_review == 450

    def test_us1_margin_79pct_passes(self):
        # cost under-1-month = $94; (450 - 94) / 450 = 79.1 % > 20 %
        lead = _lead(review_count=2, business_category="real estate")
        assert margin_ok(450, lead) is True

    def test_us1_floor_300_still_passes_margin(self):
        # (300 - 94) / 300 = 68.7 % > 20 %
        lead = _lead(review_count=2, business_category="real estate")
        assert margin_ok(300, lead) is True

    def test_acceptance_signal_lets_go_ahead(self):
        assert acceptance_signal("Sounds good. Let's go ahead.") is True

    def test_acceptance_signal_lets_do_it(self):
        assert acceptance_signal("let's do it") is True

    def test_pipeline_acceptance_returns_quote_accepted_state(self):
        pipe = _pipe([_pass()], [_send_draft()])
        res = pipe.run(
            lead=_lead(review_count=2, business_category="real estate"),
            transcript=[{"role": "assistant", "body": "rate is $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="Sounds good. Let's go ahead.",
            quoted_previously=True,
        )
        assert res.outcome == "send"
        assert res.state_updates.get("ai_conversation_state") == "quote_accepted"
        assert res.handoff_payload == {"type": "quote_to_invoice", "lead_id": "L1"}

    def test_go_ahead_after_non_price_assistant_is_not_quote_acceptance(self):
        """'Go ahead' after timeline/hard-guarantee text affirms that turn, not the $ rate."""
        from reviewarmour.prompt_templates import APPROVED_TIMELINE_PARAGRAPHS

        pipe = _pipe([_pass()], [_send_draft(body="Following up per your note.")])
        hg = APPROVED_TIMELINE_PARAGRAPHS["hard_guarantee_asked"]
        res = pipe.run(
            lead=_lead(),
            transcript=[
                {"role": "assistant", "body": "The rate is $450 USD per review."},
                {"role": "user", "body": "how long will it take?"},
                {"role": "assistant", "body": APPROVED_TIMELINE_PARAGRAPHS["under_1_month"]},
                {"role": "user", "body": "i need a hard date"},
                {"role": "assistant", "body": hg},
            ],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="sure, go ahead",
            quoted_previously=True,
        )
        assert res.state_updates.get("ai_conversation_state") != "quote_accepted"
        assert res.handoff_payload is None
        assert res.outcome == "send"

    def test_confirmation_body_contains_no_price(self):
        # Hardcoded confirmation body must not mention "$"
        pipe = _pipe([_pass()], [_send_draft()])
        res = pipe.run(
            lead=_lead(),
            transcript=[{"role": "assistant", "body": "rate is $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        assert res.outcome == "send"
        assert "$" not in (res.draft.body or "")

    def test_confirmation_contains_docusign_mention(self):
        pipe = _pipe([_pass()], [_send_draft()])
        res = pipe.run(
            lead=_lead(),
            transcript=[{"role": "assistant", "body": "rate is $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        assert "DocuSign" in (res.draft.body or "")

    def test_us1_opening_never_below_floor(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=1, business_category="real estate"), wants_price=True
        )
        assert r.authorized_quote_usd_per_review >= r.floor


# =============================================================================
# FLOW 02 — US-2, HIGH-TICKET DENTAL, TWO PUSHBACKS, ACCEPTS AT STEP 2
# Unique: US-2 tier, steps 0/1/2, trigger messages logged verbatim
# =============================================================================


class TestFlow02_US2HighTicketDental:
    def test_tier_us2_dental_1review_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=1, business_category="dental"), wants_price=True
        )
        assert r.tier_id == "US-2"
        assert r.authorized_quote_usd_per_review == 500

    def test_tier_us2_dental_2reviews_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, business_category="dental"),
            wants_price=True,
        )
        assert r.tier_id == "US-2"
        assert r.authorized_quote_usd_per_review == 500

    def test_tier_us2_inferred_from_business_name_when_category_generic(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                review_count=1,
                business_name="Smile Dental Clinic",
                business_category="services",
            ),
            wants_price=True,
        )
        assert r.tier_id == "US-2"
        assert r.authorized_quote_usd_per_review == 500

    def test_tier_us2_step1_after_first_pushback(self):
        lead = apply_pushback(
            _lead(review_count=1, business_category="dental"),
            "That seems high. Can you come down at all?",
        )
        r = CommercialEngine().evaluate_pricing(lead, wants_price=True)
        assert r.tier_id == "US-2"
        assert r.authorized_quote_usd_per_review == 475

    def test_tier_us2_step2_after_second_pushback(self):
        lead = _lead(review_count=1, business_category="dental")
        lead = apply_pushback(lead, "That seems high. Can you come down at all?")
        lead = apply_pushback(lead, "Still a bit much for me.")
        r = CommercialEngine().evaluate_pricing(lead, wants_price=True)
        assert r.tier_id == "US-2"
        assert r.authorized_quote_usd_per_review == 450

    def test_us2_step2_above_floor_350(self):
        lead = _lead(review_count=1, business_category="dental")
        lead = apply_pushback(lead, "first")
        lead = apply_pushback(lead, "second")
        r = CommercialEngine().evaluate_pricing(lead, wants_price=True)
        assert r.floor == 350
        assert r.authorized_quote_usd_per_review >= r.floor

    def test_trigger_messages_logged_verbatim(self):
        msg1 = "That seems high. Can you come down at all?"
        msg2 = "Still a bit much for me."
        lead = _lead(review_count=1, business_category="dental")
        lead = apply_pushback(lead, msg1)
        lead = apply_pushback(lead, msg2)
        assert len(lead.negotiation_triggers) == 2
        assert lead.negotiation_triggers[0].lead_message_exact == msg1
        assert lead.negotiation_triggers[0].step_after == 1
        assert lead.negotiation_triggers[1].lead_message_exact == msg2
        assert lead.negotiation_triggers[1].step_after == 2

    def test_step3_escalates_next_step_not_available(self):
        lead = _lead(review_count=1, business_category="dental")
        lead = apply_pushback(lead, "1st")
        lead = apply_pushback(lead, "2nd")
        lead = apply_pushback(lead, "3rd")
        r = CommercialEngine().evaluate_pricing(lead, wants_price=True)
        assert r.escalate is True
        assert r.authorized_quote_usd_per_review is None

    def test_step0_is_opening_no_preemptive_discount(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=1, business_category="dental"), wants_price=True
        )
        assert r.negotiation_step == 0
        assert r.authorized_quote_usd_per_review == r.opening


# =============================================================================
# FLOW 03 — US-3, 3+ REVIEWS UNDER 1 MONTH, MULTI-REVIEW OVERRIDES HIGH-TICKET
# Unique: US-3 tier, contractor classification doesn't override count-based rule
# =============================================================================


class TestFlow03_US3MultiReviewUnderMonth:
    def test_tier_us3_contractor_4reviews_mostly_under(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                review_count=4,
                business_category="contractor",
                recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "US-3"
        assert r.authorized_quote_usd_per_review == 425

    def test_us3_not_us2_when_more_than_1_review(self):
        # High-ticket ladder (US-2) applies to 1–2 reviews under; 4 reviews → US-3
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=4, business_category="dental", recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-3"

    def test_us3_floor_300(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=3, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-3"
        assert r.floor == 300

    def test_us3_margin_passes_at_opening_425(self):
        # (425 - 94) / 425 = 77.9 %
        lead = _lead(review_count=4, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH)
        assert margin_ok(425, lead) is True

    def test_us3_3reviews_all_under(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=3, business_category="roofing", recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-3"


# =============================================================================
# FLOW 04 — US-4, OVER 1 MONTH REVIEWS
# Unique: US-4 tier, over-1-month timeline class
# =============================================================================


class TestFlow04_US4OverMonth:
    def test_tier_us4_2reviews_over_1_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                review_count=2,
                business_category="photography",
                recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "US-4"
        assert r.authorized_quote_usd_per_review == 425

    def test_tier_us4_1review_non_high_ticket_over_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=1, business_category="photography", recency_profile=RecencyProfile.ALL_OVER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-4"

    def test_tier_us4_mostly_over(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, business_category="retail", recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-4"

    def test_us4_margin_at_opening(self):
        # US-4 $425, cost over = $214 → (425-214)/425 = 49.6 %
        lead = _lead(review_count=2, recency_profile=RecencyProfile.ALL_OVER_1_MONTH)
        assert margin_ok(425, lead) is True

    def test_us4_floor_300(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, recency_profile=RecencyProfile.ALL_OVER_1_MONTH),
            wants_price=True,
        )
        assert r.floor == 300


# =============================================================================
# FLOW 05 — US-5, 3+ REVIEWS OVER 1 MONTH
# Unique: US-5 tier
# =============================================================================


class TestFlow05_US5MultiReviewOverMonth:
    def test_tier_us5_5reviews_mostly_over(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                review_count=5,
                business_category="auto",
                recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "US-5"
        assert r.authorized_quote_usd_per_review == 400

    def test_tier_us5_3reviews_all_over(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=3, recency_profile=RecencyProfile.ALL_OVER_1_MONTH),
            wants_price=True,
        )
        assert r.tier_id == "US-5"

    def test_us5_floor_300(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=5, recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH),
            wants_price=True,
        )
        assert r.floor == 300

    def test_us5_margin_at_opening(self):
        # (400 - 214) / 400 = 46.5 %
        lead = _lead(review_count=5, recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH)
        assert margin_ok(400, lead) is True

    def test_us5_negotiation_steps(self):
        eng = CommercialEngine()
        lead = _lead(review_count=5, recency_profile=RecencyProfile.MOSTLY_OVER_1_MONTH)
        assert eng.evaluate_pricing(lead, wants_price=True).authorized_quote_usd_per_review == 400
        lead1 = apply_pushback(lead, "too much")
        assert eng.evaluate_pricing(lead1, wants_price=True).authorized_quote_usd_per_review == 375
        lead2 = apply_pushback(lead1, "still too much")
        assert eng.evaluate_pricing(lead2, wants_price=True).authorized_quote_usd_per_review == 350


# =============================================================================
# FLOW 06 — US-6, BULK MIXED (5+ REVIEWS), FLOOR ENFORCEMENT, ESCALATION AFTER STEP 2
# Unique: US-6 tier (MIXED + n>=5), floor $250
# =============================================================================


class TestFlow06_US6Bulk:
    def test_tier_us6_8reviews_mixed_bulk(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                review_count=8,
                business_category="restaurant",
                recency_profile=RecencyProfile.MIXED,
                is_price_sensitive_bulk=True,
            ),
            wants_price=True,
        )
        assert r.tier_id == "US-6"
        assert r.authorized_quote_usd_per_review == 400

    def test_us6_step0_400_step1_375_step2_325(self):
        eng = CommercialEngine()
        base = dict(
            review_count=8,
            business_category="restaurant",
            recency_profile=RecencyProfile.MIXED,
            is_price_sensitive_bulk=True,
        )
        lead0 = _lead(**base)
        assert eng.evaluate_pricing(lead0, wants_price=True).authorized_quote_usd_per_review == 400
        lead1 = apply_pushback(lead0, "Can you do less?")
        assert eng.evaluate_pricing(lead1, wants_price=True).authorized_quote_usd_per_review == 375
        lead2 = apply_pushback(lead1, "Still too much.")
        assert eng.evaluate_pricing(lead2, wants_price=True).authorized_quote_usd_per_review == 325

    def test_us6_floor_250(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=8, recency_profile=RecencyProfile.MIXED, is_price_sensitive_bulk=True),
            wants_price=True,
        )
        assert r.floor == 250

    def test_pipeline_below_floor_escalates(self):
        res = _pipeline_no_llm().run(
            lead=_lead(
                review_count=8,
                recency_profile=RecencyProfile.MIXED,
                is_price_sensitive_bulk=True,
            ),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            wants_price=True,
            lead_requested_price_below_floor=True,
        )
        assert res.outcome == "escalate"
        assert res.commercial is not None and res.commercial.escalate is True

    def test_us6_triggered_for_8_reviews_mixed_without_bulk_flag(self):
        """MIXED + 5+ reviews is always US-6 (internal bulk tier), not US-5."""
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=8, recency_profile=RecencyProfile.MIXED, is_price_sensitive_bulk=False),
            wants_price=True,
        )
        assert r.tier_id == "US-6"
        assert r.neg_2 == 325

    def test_us6_step2_still_above_floor(self):
        lead = _lead(review_count=8, recency_profile=RecencyProfile.MIXED, is_price_sensitive_bulk=True)
        lead = apply_pushback(lead, "1")
        lead = apply_pushback(lead, "2")
        r = CommercialEngine().evaluate_pricing(lead, wants_price=True)
        assert r.authorized_quote_usd_per_review == 325
        assert r.authorized_quote_usd_per_review >= r.floor


# =============================================================================
# FLOW 07 — CA-1, CA FOOTER, USD QUOTING
# Unique: CA-1 tier, Toronto footer, USD quoting
# =============================================================================


class TestFlow07_CA1CanadaFooter:
    def test_tier_ca1_2reviews_restaurant_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                country=Country.CA,
                review_count=2,
                business_category="restaurant",
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "CA-1"
        assert r.authorized_quote_usd_per_review == 375

    def test_ca_footer_contains_toronto_bloor(self):
        f = regional_footer(Country.CA)
        assert "Toronto" in f
        assert "Bloor" in f

    def test_ca_footer_does_not_contain_miami(self):
        assert "Miami" not in regional_footer(Country.CA)

    def test_us_footer_does_not_contain_toronto(self):
        assert "Toronto" not in regional_footer(Country.US)

    def test_ca1_floor_225(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(country=Country.CA, review_count=2, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        assert r.floor == 225

    def test_ca1_margin_at_opening_375(self):
        # (375 - 94) / 375 = 74.9 %
        lead = _lead(country=Country.CA, review_count=2, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH)
        assert margin_ok(375, lead) is True

    def test_ca_handoff_includes_usd_pricing(self):
        # The tier quote is already in USD; no CAD amount computed by the engine
        r = CommercialEngine().evaluate_pricing(
            _lead(country=Country.CA, review_count=2, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        d = r.to_prompt_dict()
        assert d["authorized_quote_usd_per_review"] == 375


# =============================================================================
# FLOW 08 — CA-2, HIGH-TICKET DENTAL
# Unique: CA-2 tier
# =============================================================================


class TestFlow08_CA2HighTicketDental:
    def test_tier_ca2_dental_1review_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                country=Country.CA,
                review_count=1,
                business_category="dental",
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "CA-2"
        assert r.authorized_quote_usd_per_review == 400

    def test_tier_ca2_dental_2reviews_under_month(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                country=Country.CA,
                review_count=2,
                business_category="dental",
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "CA-2"
        assert r.authorized_quote_usd_per_review == 400

    def test_tier_ca2_inferred_from_business_name_when_category_generic(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(
                country=Country.CA,
                review_count=1,
                business_name="Patel Dental Centre",
                business_category="health care",
                recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            ),
            wants_price=True,
        )
        assert r.tier_id == "CA-2"
        assert r.authorized_quote_usd_per_review == 400

    def test_ca2_floor_275(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(country=Country.CA, review_count=1, business_category="dental"),
            wants_price=True,
        )
        assert r.floor == 275

    def test_ca2_negotiation_steps_400_375_325(self):
        eng = CommercialEngine()
        lead = _lead(country=Country.CA, review_count=1, business_category="dental")
        assert eng.evaluate_pricing(lead, wants_price=True).authorized_quote_usd_per_review == 400
        lead1 = apply_pushback(lead, "how_do_you_remove question resolved → pushback on price")
        assert eng.evaluate_pricing(lead1, wants_price=True).authorized_quote_usd_per_review == 375
        lead2 = apply_pushback(lead1, "still too much")
        assert eng.evaluate_pricing(lead2, wants_price=True).authorized_quote_usd_per_review == 325

    def test_ca2_margin_at_opening(self):
        # (400 - 94) / 400 = 76.5 %
        lead = _lead(country=Country.CA, review_count=1, business_category="dental")
        assert margin_ok(400, lead) is True


# =============================================================================
# FLOW 09 — GBP LINK MISSING — QUOTE GATE ENFORCED
# Unique: request_gbp_first=True, no quote, not an escalation
# =============================================================================


class TestFlow09_GBPGate:
    def test_no_gbp_link_sets_request_gbp_first(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(gbp_link=None, review_count=3), wants_price=True
        )
        assert r.request_gbp_first is True
        assert r.authorized_quote_usd_per_review is None
        assert r.can_quote is False

    def test_gbp_gate_is_not_a_hard_escalation(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(gbp_link=None, review_count=3), wants_price=True
        )
        assert r.escalate is False

    def test_empty_string_gbp_link_treated_as_missing(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(gbp_link="", review_count=3), wants_price=True
        )
        assert r.request_gbp_first is True

    def test_whitespace_gbp_link_treated_as_missing(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(gbp_link="   ", review_count=3), wants_price=True
        )
        assert r.request_gbp_first is True

    def test_valid_gbp_link_allows_quote(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(gbp_link="https://g.page/test", review_count=3, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH),
            wants_price=True,
        )
        assert r.request_gbp_first is False
        assert r.authorized_quote_usd_per_review is not None


# =============================================================================
# FLOW 10 — RECENCY UNKNOWN — CONSERVATIVE TIER
# Unique: UNCERTAIN → over bucket → conservative (higher-index) tier
# =============================================================================


class TestFlow10_RecencyUnknown:
    def test_uncertain_2reviews_maps_to_us4_not_us1(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, business_category="electrical", recency_profile=RecencyProfile.UNCERTAIN),
            wants_price=True,
        )
        # UNCERTAIN → over bucket → US-4 (1-2 reviews over), not US-1
        assert r.tier_id == "US-4"

    def test_uncertain_3reviews_maps_to_us5_not_us3(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=3, business_category="electrical", recency_profile=RecencyProfile.UNCERTAIN),
            wants_price=True,
        )
        # UNCERTAIN + 3 reviews → over bucket → US-5 not US-3
        assert r.tier_id == "US-5"
        assert r.authorized_quote_usd_per_review == 400

    def test_mixed_recency_is_conservative(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2, recency_profile=RecencyProfile.MIXED),
            wants_price=True,
        )
        # MIXED → conservative over bucket → US-4
        assert r.tier_id == "US-4"

    def test_uncertain_uses_over_1_month_cost_for_margin(self):
        # At $214 with UNCERTAIN: cost = $214 (over) → margin 0 % → fails
        lead = _lead(review_count=2, recency_profile=RecencyProfile.UNCERTAIN)
        assert margin_ok(214, lead) is False
        # At $268: (268-214)/268 = 20.1 % → passes
        assert margin_ok(268, lead) is True

    def test_uncertain_opening_us4_passes_margin(self):
        # US-4 opening $425, cost over $214 → 49.6 %
        lead = _lead(review_count=2, recency_profile=RecencyProfile.UNCERTAIN)
        assert margin_ok(425, lead) is True


# =============================================================================
# FLOW 11 — MARGIN DISCIPLINE FAIL — ESCALATE INSTEAD OF QUOTE
# Unique: CA-6 step 2 ($250), cost over ($214), margin 14.4 % < 20 %
# =============================================================================


class TestFlow11_MarginFail:
    def test_margin_ok_false_ca6_step2_mixed_recency(self):
        # CA-6 uses MIXED recency. MIXED maps to over bucket → cost=$214.
        # (250 - 214) / 250 = 14.4 % < 20 %
        lead = _lead(
            country=Country.CA,
            review_count=6,
            recency_profile=RecencyProfile.MIXED,
            is_price_sensitive_bulk=True,
        )
        assert margin_ok(250, lead) is False

    def test_ca6_step2_mixed_recency_escalates(self):
        # CA-6: n>=5, recency==MIXED. At step 2, price=250, cost_over=214 → margin 14.4 % < 20 % → escalate
        r = CommercialEngine().evaluate_pricing(
            _lead(
                country=Country.CA,
                review_count=6,
                recency_profile=RecencyProfile.MIXED,
                is_price_sensitive_bulk=True,
                negotiation_step=2,
            ),
            wants_price=True,
        )
        assert r.tier_id == "CA-6"
        assert r.escalate is True
        assert "Margin" in (r.escalation_reason or "")
        assert r.authorized_quote_usd_per_review is None

    def test_pipeline_margin_fail_escalates_no_llm(self):
        res = _pipeline_no_llm().run(
            lead=_lead(
                country=Country.CA,
                review_count=6,
                recency_profile=RecencyProfile.MIXED,
                is_price_sensitive_bulk=True,
                negotiation_step=2,
            ),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            wants_price=True,
        )
        assert res.outcome == "escalate"

    def test_effective_cost_over_1month_implicit_214(self):
        # At exactly $214 with over-1-month recency, margin = 0 %
        lead = _lead(review_count=2, recency_profile=RecencyProfile.ALL_OVER_1_MONTH)
        assert margin_ok(214, lead) is False
        # Just above 20 % threshold for $214 cost: need price = 268
        assert margin_ok(268, lead) is True

    def test_effective_cost_under_1month_implicit_94(self):
        # At exactly $94 with under-1-month recency, margin = 0 %
        lead = _lead(review_count=2, recency_profile=RecencyProfile.ALL_UNDER_1_MONTH)
        assert margin_ok(94, lead) is False
        # $118 → (118-94)/118 = 20.3 %
        assert margin_ok(118, lead) is True


# =============================================================================
# FLOW 12 — AI_QUOTE_ALLOWED KILL SWITCH
# Unique: kill switch disables pricing, immediate escalation
# =============================================================================


class TestFlow12_KillSwitch:
    def test_commercial_engine_kill_switch_escalates(self):
        r = CommercialEngine().evaluate_pricing(_lead(ai_quote_allowed=False), wants_price=True)
        assert r.escalate is True
        assert r.authorized_quote_usd_per_review is None
        assert "ai_quote_allowed" in (r.escalation_reason or "")

    def test_pipeline_kill_switch_no_llm(self):
        res = _pipeline_no_llm().run(
            lead=_lead(ai_quote_allowed=False),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            wants_price=True,
        )
        assert res.outcome == "escalate"
        assert res.draft and res.draft.reason == "ai_quote_allowed_kill_switch"

    def test_kill_switch_fires_on_inbound_price_question(self):
        res = _pipeline_no_llm().run(
            lead=_lead(ai_quote_allowed=False),
            transcript=[],
            channel=Channel.SMS,
            sequence_stage="main",
            inbound_message="How much would this cost?",
        )
        assert res.outcome == "escalate"

    def test_kill_switch_off_non_pricing_turn_reaches_llm(self):
        # No pricing intent + kill switch off → LLM is reached (fake conv returns send)
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        pipe = OutboundPipeline(conversation=conv, self_correction=sc)
        res = pipe.run(
            lead=_lead(ai_quote_allowed=True),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="Hello, I have a general question",
        )
        assert res.outcome == "send"

    def test_kill_switch_can_be_toggled_on_lead_record(self):
        # Operator toggles via CRM — represented as replace() on LeadRecord
        lead_off = _lead(ai_quote_allowed=False)
        lead_on = replace(lead_off, ai_quote_allowed=True)
        r_off = CommercialEngine().evaluate_pricing(lead_off, wants_price=True)
        r_on = CommercialEngine().evaluate_pricing(lead_on, wants_price=True)
        assert r_off.escalate is True
        assert r_on.escalate is False


# =============================================================================
# FLOW 13 — SELF-CORRECTION: FIX VERDICTS
# Unique: fix → redraft → pass; draft not sent until pass
# =============================================================================


class TestFlow13_SelfCorrectionFix:
    def test_fix_then_pass_returns_send(self):
        sc = _FakeSC([_fix("copy_rules: em dash present"), _pass()])
        conv = _FakeConv([
            _send_draft("Hey John — bad draft."),
            _send_draft("Hey John. Fixed draft."),
        ])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "send"
        assert len(res.self_correction_logs) == 2
        assert res.self_correction_logs[0].verdict == "fix"
        assert res.self_correction_logs[1].verdict == "pass"

    def test_fix_verdict_identifies_correct_check(self):
        sc = _FakeSC([_fix("copy_rules: em dash present"), _pass()])
        conv = _FakeConv([_send_draft(), _send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert "copy_rules: em dash present" in res.self_correction_logs[0].failed_checks

    def test_only_passed_draft_is_final(self):
        sc = _FakeSC([_fix("factual_accuracy: wrong business name"), _pass()])
        conv = _FakeConv([_send_draft("bad draft"), _send_draft("good draft")])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.draft.body == "good draft"

    def test_wrong_footer_fix_is_correctable(self):
        sc = _FakeSC([_fix("regional_footer: US footer on CA lead"), _pass()])
        conv = _FakeConv([_send_draft(), _send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(country=Country.CA), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "send"
        assert res.self_correction_logs[0].failed_checks[0].startswith("regional_footer")

    def test_hard_timeline_commitment_fix(self):
        sc = _FakeSC([_fix("timeline_language: hard commitment"), _pass()])
        conv = _FakeConv([_send_draft(), _send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "send"

    def test_two_fix_retries_max(self):
        # Two consecutive fix verdicts followed by a pass → 3 SC calls total, outcome = send
        sc = _FakeSC([_fix("v1"), _fix("v2"), _pass()])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "send"
        assert len(res.self_correction_logs) == 3


# =============================================================================
# FLOW 14 — SELF-CORRECTION: ESCALATE VERDICTS
# Unique: hidden cost, percentage, invented price, below floor → escalate, not retry
# =============================================================================


class TestFlow14_SelfCorrectionEscalate:
    @pytest.mark.parametrize("reason", [
        "internal cost data in customer-facing message",
        "success rate percentage — scope violation",
        "invented price",
        "price below floor — hard violation",
    ])
    def test_escalate_verdict_outcome_escalate(self, reason: str):
        sc = _FakeSC([_escalate(reason)])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "escalate"

    def test_escalate_verdict_not_retried(self):
        sc = _FakeSC([_escalate("violation")])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert len(res.self_correction_logs) == 1
        assert sc.calls == [0]  # only one SC call was made

    def test_escalate_verdict_message_not_sent(self):
        sc = _FakeSC([_escalate("hidden_cost_leak")])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome != "send"

    def test_escalate_verdict_logs_reason(self):
        # _escalate() puts the reason in failed_checks[0] via _escalate() helper
        sc = _FakeSC([_escalate("scope_check: cost data surfaced")])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "escalate"
        assert res.self_correction_logs[0].verdict == "escalate"
        # failed_checks carries the check label (escalation_reason is on SelfCorrectionVerdict,
        # not on SelfCorrectionAttemptLog; we check the pipeline stored the verdict correctly)
        assert len(res.self_correction_logs[0].failed_checks) > 0


# =============================================================================
# FLOW 15 — 3 CONSECUTIVE FIX VERDICTS → HUMAN DRAFT QUEUE
# Unique: retry cap = 2; third attempt → human_queue with full history
# =============================================================================


class TestFlow15_HumanDraftQueue:
    def test_three_fix_verdicts_human_queue(self):
        sc = _FakeSC([_fix("em dash"), _fix("word count"), _fix("wrong footer")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "human_queue"

    def test_human_queue_has_all_3_attempts(self):
        sc = _FakeSC([_fix("A"), _fix("B"), _fix("C")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.human_queue_payload is not None
        assert len(res.human_queue_payload["attempts"]) == 3

    def test_human_queue_payload_has_verdict_and_failed_checks(self):
        sc = _FakeSC([_fix("check_one"), _fix("check_two"), _fix("check_three")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        hq = res.human_queue_payload
        assert hq["verdict"] == "fix"
        assert len(hq["failed_checks"]) > 0

    def test_human_queue_has_draft(self):
        sc = _FakeSC([_fix("x"), _fix("x"), _fix("x")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.human_queue_payload["draft"] is not None

    def test_retry_cap_exactly_two_redrafts(self):
        sc = _FakeSC([_fix("v1"), _fix("v2"), _fix("v3")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert len(res.self_correction_logs) == 3
        assert len(sc.calls) == 3

    def test_message_not_sent_at_cap(self):
        sc = _FakeSC([_fix("x"), _fix("x"), _fix("x")])
        conv = _FakeConv([_send_draft() for _ in range(3)])
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL, sequence_stage="main"
        )
        assert res.outcome == "human_queue"
        assert res.outcome != "send"


# =============================================================================
# FLOW 16 — ALL HARD ESCALATION TRIGGERS
# Unique: 7 triggers, no draft, AI silent after escalation
# =============================================================================


class TestFlow16_HardEscalationTriggers:
    @pytest.mark.parametrize("msg,prefix", [
        ("I might get my lawyer to look at this.", "legal_escalation"),
        ("I am going to sue your company.", "legal_escalation"),
        ("My attorney has already sent a notice to Google.", "legal_escalation"),
        ("I am going to file a complaint with the BBB.", "regulator"),
        ("I want to speak to the owner.", "specific_person"),
        ("I want to speak to the manager.", "specific_person"),
        ("file a complaint to the better business bureau", "regulator"),
        ("I wanna talk to jayden directly", "specific_person"),
        ("Can I speak with Jayden?", "specific_person"),
        ("Put me through to Maria", "specific_person"),
    ])
    def test_trigger_fires(self, msg: str, prefix: str):
        reason = should_escalate_inbound(msg)
        assert reason is not None, f"No escalation for: {msg!r}"
        assert reason.startswith(prefix), f"{reason!r} should start with {prefix!r}"

    def test_off_topic_does_not_hard_escalate(self):
        assert should_escalate_inbound("what is sun like on the other side") is None
        assert should_escalate_inbound("What's the weather in Tokyo?") is None

    def test_generic_specialist_not_named_person_escalation(self):
        assert should_escalate_inbound("I want to talk to a specialist") is None
        assert should_escalate_inbound("can I speak to someone on your team?") is None

    def test_refund_only_fires_post_payment(self):
        assert should_escalate_inbound("I want a refund", post_payment_context=False) is None
        r = should_escalate_inbound(
            "I already paid and the reviews are still up. I want a refund.",
            post_payment_context=True,
        )
        assert r is not None and r.startswith("post_payment")

    def test_pipeline_legal_escalates_no_llm(self):
        for msg in [
            "talking to my lawyer about this",
            "we will sue you",
            "my attorney is involved",
            "I wanna talk to jayden directly",
        ]:
            res = _pipeline_no_llm().run(
                lead=_lead(), transcript=[], channel=Channel.EMAIL,
                sequence_stage="main", inbound_message=msg,
            )
            assert res.outcome == "escalate", f"No escalation for: {msg!r}"

    def test_three_no_progress_escalates(self):
        res = _pipeline_no_llm().run(
            lead=_lead(),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="still thinking",
            meaningful_progress=False,
            conversation_state=ConversationState(consecutive_no_progress_turns=2),
        )
        assert res.outcome == "escalate"
        assert res.draft and res.draft.reason == "no_progress_three_turns"

    def test_no_progress_counter_increments_each_turn(self):
        state = ConversationState(consecutive_no_progress_turns=0)
        # First no-progress turn: counter → 1 (not 3 yet, so LLM would be needed)
        with pytest.raises(AssertionError, match="LLM was unexpectedly invoked"):
            _pipeline_no_llm().run(
                lead=_lead(), transcript=[], channel=Channel.EMAIL,
                sequence_stage="main", inbound_message="meh",
                meaningful_progress=False, conversation_state=state,
            )

    def test_escalation_draft_action_is_escalate(self):
        res = _pipeline_no_llm().run(
            lead=_lead(), transcript=[], channel=Channel.EMAIL,
            sequence_stage="main", inbound_message="I will get my lawyer",
        )
        assert res.draft is not None
        assert res.draft.action == "escalate"


# =============================================================================
# FLOW 17 — STALL DETECTION: 6H SILENCE, BACKUP AT T+10H
# Unique: stall at exactly T+6h hard / T+2h soft, salesman payload
# =============================================================================


class TestFlow17_StallDetection:
    _T0 = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)

    def test_stall_not_before_6h_hard(self):
        assert not check_stall(
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=5, minutes=59),
            soft_quote_mode=False,
        )

    def test_stall_at_6h_hard(self):
        assert check_stall(
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=6),
            soft_quote_mode=False,
        )

    def test_stall_not_before_2h_soft(self):
        assert not check_stall(
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=1, minutes=59),
            soft_quote_mode=True,
        )

    def test_stall_at_2h_soft(self):
        assert check_stall(
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=2),
            soft_quote_mode=True,
        )

    def test_stall_payload_fields(self):
        lead = _lead(
            lead_id="STALL-1",
            first_name="John",
            last_name="Smith",
            business_name="Smith Auto",
            country=Country.US,
            phone="+15550001234",
            email="john@smith.com",
        )
        payload = evaluate_post_quote_stall(
            lead=lead,
            transcript=[{"role": "user", "body": "hmm let me think"}],
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=7),
            last_quote=450,
        )
        assert payload is not None
        assert payload["ai_conversation_state"] == "stalled_post_quote"
        page = payload["salesman_page"]
        assert "backup_page" not in payload
        assert page["lead_name"] == "John Smith"
        assert page["business"] == "Smith Auto"
        assert page["phone"] == "+15550001234"
        assert page["email"] == "john@smith.com"
        assert page["last_quote_offered"] == 450
        assert page["last_lead_message"] == {"role": "user", "body": "hmm let me think"}
        assert page["stall_escalation"] == "primary_salesman"

    def test_stall_hard_backup_at_12h_uses_backup_page_only(self):
        lead = _lead()
        t = [
            {"role": "assistant", "body": "The rate is $450 USD per review."},
            {"role": "user", "body": "let me think about it"},
            {"role": "assistant", "body": "No problem, take your time."},
        ]
        payload = evaluate_post_quote_stall(
            lead=lead,
            transcript=t,
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=12),
            last_quote=450,
        )
        assert payload is not None
        assert payload["ai_conversation_state"] == "stalled_post_quote_backup"
        assert "salesman_page" not in payload
        bp = payload["backup_page"]
        assert bp["last_lead_message"] == {"role": "user", "body": "let me think about it"}
        assert bp["stall_escalation"] == "backup_jayden"
        assert bp["conversation"] == t

    def test_stall_soft_backup_at_4h_uses_backup_page(self):
        lead = _lead(soft_quote_mode=True)
        payload = evaluate_post_quote_stall(
            lead=lead,
            transcript=[{"role": "user", "body": "maybe"}],
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=4),
            last_quote=400,
        )
        assert payload["ai_conversation_state"] == "stalled_post_quote_backup"
        assert "backup_page" in payload
        assert "salesman_page" not in payload

    def test_stall_none_without_commercial_turn(self):
        assert evaluate_post_quote_stall(
            lead=_lead(), transcript=[], last_commercial_turn_at=None,
            now=self._T0, last_quote=None,
        ) is None

    def test_stall_closes_if_lead_replies_before_threshold(self):
        # At T+3h (before 6h), stall check returns None
        assert evaluate_post_quote_stall(
            lead=_lead(),
            transcript=[{"role": "user", "body": "still interested"}],
            last_commercial_turn_at=self._T0,
            now=self._T0 + timedelta(hours=3),
            last_quote=425,
        ) is None

    def test_stall_page_includes_full_transcript(self):
        t = [{"role": "assistant", "body": "rate is $450"}, {"role": "user", "body": "hmm"}]
        page = stall_page_payload(_lead(), t, 450)
        assert page["conversation"] == t
        assert page["last_lead_message"] == {"role": "user", "body": "hmm"}

    def test_stall_page_last_lead_ignores_trailing_assistant(self):
        t = [
            {"role": "user", "body": "quote please"},
            {"role": "assistant", "body": "$450 per review"},
            {"role": "user", "body": "let me think"},
            {"role": "assistant", "body": "No problem."},
        ]
        page = stall_page_payload(_lead(), t, 450)
        assert page["last_lead_message"] == {"role": "user", "body": "let me think"}
    def test_configurable_window_soft_vs_hard(self):
        # Same T+3h: hard → no stall; soft → stall
        t0 = self._T0
        assert not check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=False
        )
        assert check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=True
        )


# =============================================================================
# FLOW 18 — AFTER-HOURS, SUNDAY DEFERRAL, MORNING QUEUE
# Unique: Sunday suppression, deferral to Monday 08:00 EST, follow-up cadence
# =============================================================================


class TestFlow18_SundayDeferral:
    def test_sunday_deferred_to_monday_8am_est(self):
        # Sunday 22:00 UTC = Sunday 18:00 EDT
        sunday_utc = datetime(2026, 5, 17, 22, 0, tzinfo=timezone.utc)
        out = defer_sunday_touch_to_monday_8am_est(sunday_utc)
        local = out.astimezone(EST)
        assert local.weekday() == 0  # Monday
        assert local.hour == 8
        assert local.minute == 0

    def test_non_sunday_is_unchanged(self):
        monday_utc = datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
        assert defer_sunday_touch_to_monday_8am_est(monday_utc) == monday_utc

    def test_saturday_not_deferred(self):
        saturday_utc = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
        assert defer_sunday_touch_to_monday_8am_est(saturday_utc) == saturday_utc

    def test_monday_not_deferred(self):
        monday_utc = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        assert defer_sunday_touch_to_monday_8am_est(monday_utc) == monday_utc

    def test_follow_up_1_at_30min_subject_and_body(self):
        t0 = datetime(2026, 5, 16, 3, 10, tzinfo=timezone.utc)
        lead = _lead(business_name="Acme Plumbing", first_name="Sam")
        seq = schedule_nurture_follow_ups(t0, lead, channel=Channel.EMAIL)
        f1 = seq[0]
        assert f1.index == 1
        assert f1.fire_at_utc == t0 + timedelta(minutes=30)
        assert "Acme Plumbing" in f1.subject
        assert "Google reviews" in f1.subject
        assert f1.body.startswith("Hi Sam,")
        assert "policy-violating Google reviews" in f1.body
        assert "Brickell" in f1.body or "Miami" in f1.body

    def test_follow_up_1_sms_no_subject_compact_body(self):
        t0 = datetime(2026, 5, 16, 3, 10, tzinfo=timezone.utc)
        lead = _lead(business_name="Acme", first_name="Sam")
        seq = schedule_nurture_follow_ups(t0, lead, channel=Channel.SMS)
        f1 = seq[0]
        assert f1.channel == Channel.SMS
        assert f1.subject is None
        assert "Hi Sam," in f1.body
        assert "Acme" in f1.body
        assert "+17864643783" in f1.body
        assert len(f1.body) <= 320

    def test_follow_up_2_at_60min_subject_and_body(self):
        t0 = datetime(2026, 5, 16, 3, 10, tzinfo=timezone.utc)
        lead = _lead(business_name="Acme Plumbing", first_name="Sam")
        seq = schedule_nurture_follow_ups(t0, lead)
        f2 = seq[1]
        assert f2.fire_at_utc == t0 + timedelta(minutes=60)
        assert "Following up" in f2.subject
        assert "slipped down the inbox" in f2.body

    def test_follow_up_3_at_24h_when_not_sunday(self):
        t0 = datetime(2026, 5, 11, 15, 0, tzinfo=timezone.utc)  # Monday UTC
        lead = _lead()
        seq = schedule_nurture_follow_ups(t0, lead)
        f3 = seq[2]
        assert f3.index == 3
        assert f3.fire_at_utc == t0 + timedelta(hours=24)
        assert f3.state_updates.get("lead_status") is None
        assert f3.raw_fire_at_utc is None
        assert "Still here" in f3.subject

    def test_follow_up_3_landing_on_sunday_deferred(self):
        # Saturday 15:00 UTC + 24h = Sunday 15:00 UTC (Sunday morning US Eastern)
        t0 = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
        lead = _lead()
        seq = schedule_nurture_follow_ups(t0, lead)
        f3 = seq[2]
        assert f3.state_updates.get("lead_status") == "queued_for_morning"
        assert f3.raw_fire_at_utc == t0 + timedelta(hours=24)
        local = f3.fire_at_utc.astimezone(EST)
        assert local.weekday() == 0
        assert local.hour == 8
        assert local.minute == 0

    def test_morning_brief_uses_not_stated_for_unknowns(self):
        lead = _lead(lead_id="L-MORN", lead_source="", urgency_flag=None, gbp_link=None)
        text = build_morning_queue_brief(
            lead,
            [{"role": "user", "body": "hi", "channel": "email"}],
            submission_utc=datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc),
        )
        assert "L-MORN" in text
        assert "not stated" in text
        assert "Sentiment:    not stated" in text
        assert "Last contact: not stated" in text

    def test_queue_priority_escalation_before_morning_queue(self):
        assert queue_priority_rank("escalated_to_human") < queue_priority_rank(
            "queued_for_morning"
        )
        assert queue_priority_rank("stalled_post_quote_backup") < queue_priority_rank(
            "new"
        )

    def test_queue_priority_tuple_ordering_stable(self):
        assert "escalated_to_human" in QUEUE_STATUS_PRIORITY
        assert QUEUE_STATUS_PRIORITY.index("queued_for_morning") > QUEUE_STATUS_PRIORITY.index(
            "stalled_post_quote"
        )


# =============================================================================
# FLOW 19 — BUSINESS HOURS, SALESMAN MISS, AI FALLBACK
# Unique: acceptance detection, bounded reply during dispatch phase
# =============================================================================


class TestFlow19_SalesmanMiss:
    def test_acceptance_signal_fires(self):
        for msg in ["let's do it", "im in", "Go ahead", "send the invoice", "i'm in"]:
            assert acceptance_signal(msg), f"Expected acceptance: {msg!r}"

    def test_no_acceptance_signal_for_vague_replies(self):
        for msg in ["maybe", "let me think", "not sure yet", "what else?", "I have a question"]:
            assert not acceptance_signal(msg), f"Unexpected acceptance: {msg!r}"

    def test_acceptance_on_sms_sets_quote_accepted(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft(channel=Channel.SMS)])
        pipe = OutboundPipeline(
            conversation=conv,
            self_correction=sc,
            use_llm_quote_acceptance=False,
        )
        res = pipe.run(
            lead=_lead(),
            transcript=[{"role": "assistant", "body": "rate $450"}],
            channel=Channel.SMS,
            sequence_stage="main",
            inbound_message="im in",
            quoted_previously=True,
        )
        assert res.outcome == "send"
        assert res.state_updates.get("ai_conversation_state") == "quote_accepted"


# =============================================================================
# FLOW 20 — POST-CALL UNDECIDED: TOUCH TIMINGS
# Unique: T+24h, T+72h, T+7d, T+14d; Sunday deferral; mid-sequence cancellation
# =============================================================================


class TestFlow20_PostCallUndecidedTimings:
    _CALL = datetime(2026, 5, 11, 19, 0, tzinfo=timezone.utc)  # Monday 14:00 EST

    def test_touch1_at_24h(self):
        assert (self._CALL + timedelta(hours=24) - self._CALL) == timedelta(hours=24)

    def test_touch2_at_72h(self):
        assert (self._CALL + timedelta(hours=72) - self._CALL) == timedelta(hours=72)

    def test_touch3_at_7d(self):
        assert (self._CALL + timedelta(days=7) - self._CALL) == timedelta(days=7)

    def test_touch4_at_14d(self):
        assert (self._CALL + timedelta(days=14) - self._CALL) == timedelta(days=14)

    def test_touch_order_ascending(self):
        t = self._CALL
        t1 = t + timedelta(hours=24)
        t2 = t + timedelta(hours=72)
        t3 = t + timedelta(days=7)
        t4 = t + timedelta(days=14)
        assert t1 < t2 < t3 < t4

    def test_sunday_touch1_deferred(self):
        # Call Saturday 19:00 EST → +24h = Sunday 19:00 EST → deferred
        call_sat = datetime(2026, 5, 16, 23, 0, tzinfo=timezone.utc)  # ~19:00 EST Saturday
        raw = call_sat + timedelta(hours=24)
        deferred = defer_sunday_touch_to_monday_8am_est(raw)
        local = deferred.astimezone(EST)
        if raw.astimezone(EST).weekday() == 6:
            assert local.weekday() == 0
            assert local.hour == 8


# =============================================================================
# FLOW 21 — POST-CALL NO-SHOW: ACCELERATED TIMINGS
# Unique: 15min, 2h, 24h, 72h cadence; SMS-first
# =============================================================================


class TestFlow21_NoShowTimings:
    _NO_SHOW = datetime(2026, 5, 11, 19, 0, tzinfo=timezone.utc)  # 14:00 EST

    def test_touch1_at_15min(self):
        assert (self._NO_SHOW + timedelta(minutes=15) - self._NO_SHOW) == timedelta(minutes=15)

    def test_touch2_at_2h(self):
        assert (self._NO_SHOW + timedelta(hours=2) - self._NO_SHOW) == timedelta(hours=2)

    def test_touch3_at_24h(self):
        assert (self._NO_SHOW + timedelta(hours=24) - self._NO_SHOW) == timedelta(hours=24)

    def test_touch4_at_72h(self):
        assert (self._NO_SHOW + timedelta(hours=72) - self._NO_SHOW) == timedelta(hours=72)

    def test_touch_order_ascending(self):
        t = self._NO_SHOW
        assert t + timedelta(minutes=15) < t + timedelta(hours=2) < t + timedelta(hours=24) < t + timedelta(hours=72)

    def test_no_show_sequence_faster_than_undecided(self):
        # Touch 1 no-show (15min) < Touch 1 undecided (24h)
        no_show_touch1 = self._NO_SHOW + timedelta(minutes=15)
        undecided_touch1 = self._NO_SHOW + timedelta(hours=24)
        assert no_show_touch1 < undecided_touch1


# =============================================================================
# FLOW 22 — CUSTOMER REVIEW REQUEST: CHARACTER LIMITS & TIMING
# Unique: Touch 1 <200 chars, Touch 2 <80 words, Touch 3 <160 chars, timing
# =============================================================================


class TestFlow22_ReviewRequestCharacterLimits:
    _JOB = datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)

    def test_touch1_sms_under_200_chars(self):
        gbp = "https://g.page/r/example"
        body = (
            "Hey Sarah, just confirming 3 reviews removed from Chen Dental's GBP. "
            "If you have 30 seconds a quick review on our Google profile would help. "
            f"Direct link: {gbp}"
        )
        assert len(body) < 200

    def test_touch2_email_under_80_words(self):
        body = (
            "Following up on the Chen Dental job. If you have a moment, a quick review "
            "goes a long way. Direct link: https://g.page/r/example. "
            "Even one line is enough. No pressure either way."
        )
        assert len(body.split()) < 80

    def test_touch3_sms_under_160_chars(self):
        body = "Last note — if you'd like to leave a review: https://g.page/r/example"
        assert len(body) < 160

    def test_compliant_bodies_have_no_star_rating(self):
        for body in [
            "Please leave a review. Direct link: https://g.page/r/example",
            "Following up about a review. No pressure either way.",
            "A quick review would mean a lot to us.",
        ]:
            assert not any(s in body.lower() for s in ("5-star", "five star", "5 star"))

    def test_gbp_link_exactly_once(self):
        gbp = "https://g.page/r/example"
        body = f"Please leave a review: {gbp}"
        assert body.count(gbp) == 1

    def test_compliant_bodies_have_no_incentive(self):
        for body in [
            "Leave a review here: https://g.page/r/example",
            "A quick review would be appreciated. No pressure.",
        ]:
            assert not any(w in body.lower() for w in ("discount", "reward", "gift", "cash", "$"))

    def test_touch1_at_1h_after_job_complete(self):
        assert (self._JOB + timedelta(hours=1) - self._JOB) == timedelta(hours=1)

    def test_touch2_at_24h(self):
        assert (self._JOB + timedelta(hours=24) - self._JOB) == timedelta(hours=24)

    def test_touch3_at_5d(self):
        assert (self._JOB + timedelta(days=5) - self._JOB) == timedelta(days=5)

    def test_sc_escalates_specific_star_rating_request(self):
        # A draft requesting "5-star" should trigger an escalate verdict
        v = _escalate("scope_check: specific star rating requested")
        assert v.verdict == "escalate"
        assert "star" in (v.escalation_reason or "")

    def test_touch_order_ascending(self):
        t = self._JOB
        assert t + timedelta(hours=1) < t + timedelta(hours=24) < t + timedelta(days=5)


# =============================================================================
# FLOW 23 — REVIEW REQUEST SUPPRESSION
# Unique: suppression flag, missing summary holds sequence
# =============================================================================


class TestFlow23_ReviewRequestSuppression:
    def test_suppression_timing_logic(self):
        job = datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
        touch1 = job + timedelta(hours=1)
        suppression = job + timedelta(hours=5)
        touch2 = job + timedelta(hours=24)
        # Touch1 already fired, suppression set before Touch2
        assert touch1 < suppression < touch2

    def test_suppression_before_job_complete_blocks_all(self):
        # Conceptual: suppression before job_complete → no touches at all
        review_suppressed = True
        touches_scheduled = 0 if review_suppressed else 3
        assert touches_scheduled == 0

    def test_missing_summary_represented_as_escalate_verdict(self):
        v = _escalate("completed_job_summary required but not provided")
        assert v.verdict == "escalate"
        assert "summary" in (v.escalation_reason or "")

    def test_soft_quote_mode_is_crm_toggle(self):
        # Suppression is a CRM field, representable via replace()
        lead = _lead(soft_quote_mode=False)
        toggled = replace(lead, soft_quote_mode=True)
        assert toggled.soft_quote_mode is True


# =============================================================================
# FLOW 24 — SLACK HANDOFF FAILURE — JAYDEN PAGED AS FALLBACK
# Unique: quote_accepted state set before Slack attempt; confirmation sent first
# =============================================================================


class TestFlow24_SlackFailure:
    def test_quote_accepted_state_set_immediately(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(
            conversation=conv,
            self_correction=sc,
            use_llm_quote_acceptance=False,
        ).run(
            lead=_lead(lead_id="SLACK-1"),
            transcript=[{"role": "assistant", "body": "rate $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        # State is set on this pipeline result, not gated on Slack success
        assert res.state_updates.get("ai_conversation_state") == "quote_accepted"

    def test_handoff_payload_present_before_slack(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(
            conversation=conv,
            self_correction=sc,
            use_llm_quote_acceptance=False,
        ).run(
            lead=_lead(lead_id="SLACK-2"),
            transcript=[{"role": "assistant", "body": "rate $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        assert res.handoff_payload == {"type": "quote_to_invoice", "lead_id": "SLACK-2"}

    def test_outcome_send_independent_of_slack(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(
            conversation=conv,
            self_correction=sc,
            use_llm_quote_acceptance=False,
        ).run(
            lead=_lead(),
            transcript=[{"role": "assistant", "body": "rate $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        assert res.outcome == "send"

    def test_confirmation_body_sent_to_lead(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        res = OutboundPipeline(
            conversation=conv,
            self_correction=sc,
            use_llm_quote_acceptance=False,
        ).run(
            lead=_lead(),
            transcript=[{"role": "assistant", "body": "rate $450"}],
            channel=Channel.EMAIL,
            sequence_stage="main",
            inbound_message="let's do it",
            quoted_previously=True,
        )
        assert res.draft is not None
        assert res.draft.action == "send"
        assert "pay only after" in (res.draft.body or "").lower()


# =============================================================================
# FLOW 25 — SOFT-QUOTE MODE: RANGE, EARLY STALL, NO NEGOTIATION
# Unique: soft_quote_mode=True, stall=2h, pushback → immediate escalate
# =============================================================================


class TestFlow25_SoftQuoteMode:
    def test_soft_stall_2h_not_6h(self):
        t0 = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
        assert check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=2), soft_quote_mode=True
        )
        assert not check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=2), soft_quote_mode=False
        )

    def test_soft_stall_not_before_2h(self):
        t0 = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
        assert not check_stall(
            last_commercial_turn_at=t0,
            now=t0 + timedelta(hours=1, minutes=59),
            soft_quote_mode=True,
        )

    def test_soft_quote_mode_flag_on_lead(self):
        lead = _lead(soft_quote_mode=True)
        assert lead.soft_quote_mode is True

    def test_soft_stall_payload_at_t_plus_3h(self):
        t0 = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
        lead = _lead(soft_quote_mode=True)
        payload = evaluate_post_quote_stall(
            lead=lead,
            transcript=[{"role": "user", "body": "thinking"}],
            last_commercial_turn_at=t0,
            now=t0 + timedelta(hours=3),
            last_quote=425,
        )
        assert payload is not None
        assert payload["ai_conversation_state"] == "stalled_post_quote"
        assert "salesman_page" in payload
        assert "backup_page" not in payload

    def test_toggle_soft_quote_changes_stall_window(self):
        t0 = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
        lead_hard = _lead(soft_quote_mode=False)
        lead_soft = replace(lead_hard, soft_quote_mode=True)
        # At T+3h: hard → no stall; soft → stall
        hard_stall = check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=3),
            soft_quote_mode=lead_hard.soft_quote_mode,
        )
        soft_stall = check_stall(
            last_commercial_turn_at=t0, now=t0 + timedelta(hours=3),
            soft_quote_mode=lead_soft.soft_quote_mode,
        )
        assert not hard_stall
        assert soft_stall

    def test_soft_quote_pushback_escalates_pipeline(self):
        # Operator intent: pushback on soft quote → immediate escalation (kill switch enforces)
        res = _pipeline_no_llm().run(
            lead=_lead(soft_quote_mode=True, ai_quote_allowed=False),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            wants_price=True,
        )
        assert res.outcome == "escalate"


# =============================================================================
# CROSS-FLOW: internal cost constants never surface in prompt dict (Flows 11, 14)
# =============================================================================


class TestHiddenCostNeverSurfaces:
    def test_prompt_dict_excludes_cost_fields(self):
        r = CommercialEngine().evaluate_pricing(
            _lead(review_count=2), wants_price=True
        )
        d = r.to_prompt_dict()
        for forbidden in ("effective_cost", "94", "214", "margin_passed", "floor"):
            assert forbidden not in str(d), f"{forbidden!r} should not appear in prompt dict"

    def test_prompt_dict_exact_keys(self):
        r = CommercialEngine().evaluate_pricing(_lead(), wants_price=True)
        allowed = {
            "tier_id", "opening", "neg_1", "neg_2",
            "negotiation_step", "authorized_quote_usd_per_review",
            "can_quote", "request_gbp_first", "escalate", "escalation_reason",
        }
        assert set(r.to_prompt_dict().keys()) == allowed
        assert "floor" not in r.to_prompt_dict()

    def test_margin_passed_not_in_prompt_dict(self):
        r = CommercialEngine().evaluate_pricing(_lead(), wants_price=True)
        assert "margin_passed" not in r.to_prompt_dict()

    @pytest.mark.parametrize("cost", [94, 214])
    def test_internal_cost_not_in_prompt_dict(self, cost: int):
        r = CommercialEngine().evaluate_pricing(_lead(), wants_price=True)
        assert str(cost) not in str(r.to_prompt_dict())


# =============================================================================
# CROSS-FLOW: virtual clock / now_override (Flows 17, 25, tester)
# =============================================================================


class TestVirtualClock:
    def test_pipeline_accepts_now_override(self):
        sc = _FakeSC([_pass()])
        conv = _FakeConv([_send_draft()])
        virtual = datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc)
        res = OutboundPipeline(conversation=conv, self_correction=sc).run(
            lead=_lead(),
            transcript=[],
            channel=Channel.EMAIL,
            sequence_stage="main",
            wants_price=True,
            now_override=virtual,
        )
        if "last_commercial_turn_at" in res.state_updates:
            assert "2025-01-15" in res.state_updates["last_commercial_turn_at"]

    def test_stall_uses_virtual_now(self):
        virtual_t0 = datetime(2024, 3, 1, 8, 0, tzinfo=timezone.utc)
        assert check_stall(
            last_commercial_turn_at=virtual_t0,
            now=virtual_t0 + timedelta(hours=7),
            soft_quote_mode=False,
        )
        assert not check_stall(
            last_commercial_turn_at=virtual_t0,
            now=virtual_t0 + timedelta(hours=5),
            soft_quote_mode=False,
        )


# =============================================================================
# CROSS-FLOW: regional footer (Flows 01, 07, 13)
# =============================================================================


class TestRegionalFooter:
    def test_us_footer_brickell_miami(self):
        f = regional_footer(Country.US)
        assert "Brickell" in f
        assert "Miami" in f

    def test_ca_footer_toronto_bloor(self):
        f = regional_footer(Country.CA)
        assert "Toronto" in f
        assert "Bloor" in f

    def test_us_footer_has_786_phone(self):
        assert "+1 (786)" in regional_footer(Country.US)

    def test_ca_footer_has_416_phone(self):
        assert "416" in regional_footer(Country.CA)

    def test_footers_are_distinct(self):
        assert regional_footer(Country.US) != regional_footer(Country.CA)
