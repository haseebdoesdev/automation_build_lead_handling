"""Spec v2 — B-series live integration tests (industry-based pricing).

Replaces the v7 B-series in test_live_flows.py. These hit the real Anthropic API
through the full production pipeline (ConversationModule + SelfCorrectionModule
+ AdaptivePriceSelector) and verify spec v2 behaviors end-to-end:

  - Industry-based tier matrix produces the right band per GBPCategory + volume
  - Adaptive selector picks a price within band, biased by recency / image /
    tone / engagement signals
  - Phone-call threshold ($400) routes T1/T2 leads to phone, with the T1
    exception (<=2 reviews, image-or-recent) writing at $400-$450
  - Negotiation step ladder (×1.0, ×0.875, ×0.766) clamped to floor
  - I2/I6 regression: step 2 still quotes a discounted price; step 3 escalates
  - SC pre-checks (phone-threshold violation, ROI/CLV ban, hidden-cost leak,
    floor breach) hold against live LLM drafts

Requires: ANTHROPIC_API_KEY in the environment.

Run: pytest tests/test_live_flows_v2.py -v --timeout=180
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest

from reviewarmour.commercial import CommercialEngine, get_volume_band
from reviewarmour.conversation import (
    AdaptivePriceSelector,
    ConversationModule,
    OutboundPipeline,
)
from reviewarmour.models import (
    Channel,
    Country,
    EngagementLevel,
    GBPCategory,
    LeadRecord,
    LeadTone,
    PricingTier,
    RecencyProfile,
    VolumeBracket,
)
from reviewarmour.self_correction import SelfCorrectionModule, make_anthropic_client
from reviewarmour.settings import LLMRuntime

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — live tests require API access",
)


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return make_anthropic_client()


@pytest.fixture(scope="module")
def runtime():
    return LLMRuntime()


@pytest.fixture(scope="module")
def conversation_module(client, runtime):
    return ConversationModule(client, runtime=runtime)


@pytest.fixture(scope="module")
def sc_module(client, runtime):
    return SelfCorrectionModule(client, runtime=runtime)


@pytest.fixture(scope="module")
def adaptive_selector(client, runtime):
    return AdaptivePriceSelector(client, runtime=runtime)


@pytest.fixture(scope="module")
def pipeline(conversation_module, sc_module, adaptive_selector):
    return OutboundPipeline(
        conversation=conversation_module,
        self_correction=sc_module,
        adaptive_price_selector=adaptive_selector,
        use_adaptive_price_selector=True,
    )


def _lead(**kw) -> LeadRecord:
    defaults = dict(
        lead_id="V2-LIVE",
        first_name="Test",
        last_name="Lead",
        business_name="Test Biz",
        country=Country.US,
        phone="+15550001111",
        email="test@example.com",
        gbp_link="https://maps.google.com/test",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
        gbp_category=GBPCategory.PLUMBER,
        reviews_image_content=[False, False],
        reviews_under_one_month=[True, True],
    )
    defaults.update(kw)
    return LeadRecord(**defaults)


def _body(result) -> str:
    return (result.draft.body or "") if result.draft else ""


def _dollar_figures(body: str) -> list[int]:
    """Pull integer USD per-review figures from a draft body."""
    out = []
    for m in re.findall(r"\$\s?(\d[\d,]*)", body):
        try:
            v = int(m.replace(",", ""))
            if 100 <= v <= 999:  # per-review range
                out.append(v)
        except ValueError:
            pass
    return out


# ===========================================================================
# B1 — Plastic Surgeon (T1 Premium): phone-call threshold triggers
# ===========================================================================


class TestB1_PlasticSurgeonPhoneRoute:
    """T1 Plastic Surgeon, 2 reviews → range $520-$550 → over $400 → phone route."""

    def test_band_lookup(self):
        config, band = get_volume_band(GBPCategory.PLASTIC_SURGEON, 2)
        assert config.tier == PricingTier.T1
        assert band.low_usd == 520 and band.high_usd == 550

    def test_engine_routes_to_phone_with_adaptive_500(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=GBPCategory.PLASTIC_SURGEON,
            business_name="Premier Plastic Surgery",
            business_category="plastic_surgeon",
            reviews_image_content=[False, False],
            reviews_under_one_month=[False, False],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=530)
        assert r.phone_call_threshold_triggered is True
        assert r.authorized_quote_usd_per_review is None
        assert r.salesman_recommended_range == (520, 550)


# ===========================================================================
# B2 — Plumber (T3 Standard): written quote
# ===========================================================================


class TestB2_PlumberWrittenQuote:
    """T3 Plumber, 3 reviews → range $330-$370 → under $400 → written quote."""

    def test_band_lookup(self):
        config, band = get_volume_band(GBPCategory.PLUMBER, 3)
        assert config.tier == PricingTier.T3
        assert band.low_usd == 330 and band.high_usd == 370

    def test_live_pipeline_quotes_in_writing(self, pipeline):
        lead = _lead(
            lead_id="B2-LIVE",
            business_name="Acme Plumbing Co",
            gbp_category=GBPCategory.PLUMBER,
            review_count=3,
            reviews_image_content=[False, False, False],
            reviews_under_one_month=[True, True, True],
        )
        result = pipeline.run(
            lead=lead,
            transcript=[
                {
                    "role": "lead",
                    "channel": "email",
                    "content": "What does it cost to remove these reviews?",
                },
            ],
            channel=Channel.EMAIL,
            sequence_stage="reply",
            inbound_message="What does it cost to remove these reviews?",
            wants_price=True,
        )
        assert result.outcome == "send", f"expected send, got {result.outcome}"
        assert result.commercial is not None
        assert result.commercial.tier == PricingTier.T3
        assert result.commercial.phone_call_threshold_triggered is False
        assert 330 <= result.commercial.authorized_quote_usd_per_review <= 370
        # Body should contain that exact authorized figure
        body = _body(result)
        figs = _dollar_figures(body)
        assert (
            result.commercial.authorized_quote_usd_per_review in figs
        ), f"authorized quote not in body figures {figs}: {body[:200]}"


# ===========================================================================
# B3 — CA Restaurant: USD primary, CAD parenthetical OK for over-1mo
# ===========================================================================


class TestB3_CanadianRestaurant:
    def test_band_lookup(self):
        config, band = get_volume_band(GBPCategory.RESTAURANT, 2)
        assert config.tier == PricingTier.T3
        # Restaurant small band: $270-$320
        assert band.low_usd == 270 and band.high_usd == 320

    def test_live_quote_is_usd_primary(self, pipeline):
        lead = _lead(
            lead_id="B3-LIVE",
            business_name="Maple Diner",
            country=Country.CA,
            phone="+14165550000",
            email="m@diner.ca",
            gbp_category=GBPCategory.RESTAURANT,
            business_category="restaurant",
            recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
            reviews_image_content=[False, False],
            reviews_under_one_month=[False, False],
        )
        result = pipeline.run(
            lead=lead,
            transcript=[
                {
                    "role": "lead",
                    "channel": "email",
                    "content": "Hi, what is the cost per review to remove these?",
                },
            ],
            channel=Channel.EMAIL,
            sequence_stage="reply",
            inbound_message="Hi, what is the cost per review to remove these?",
            wants_price=True,
        )
        # Whether send or human_queue, the engine must compute a CA tier band.
        assert result.commercial is not None
        assert result.commercial.tier == PricingTier.T3
        # If a draft was sent, USD must be primary.
        if result.outcome == "send":
            body = _body(result)
            assert "USD" in body or "$" in body
            assert not re.match(r"^\s*\$?\d+\s*CAD", body)


# ===========================================================================
# B4 — Negotiation step 1: ~12.5% off, still in band
# ===========================================================================


class TestB4_NegStep1:
    def test_step1_drops_about_12_5_percent(self):
        eng = CommercialEngine()
        lead = _lead(gbp_category=GBPCategory.PLUMBER, negotiation_step=1)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        # 350 * 0.875 = 306.25 → 306
        assert r.authorized_quote_usd_per_review == round(350 * 0.875)


# ===========================================================================
# B5 — Negotiation step 2: still quotes, clamped to floor
# ===========================================================================


class TestB5_NegStep2:
    def test_step2_clamps_to_floor(self):
        eng = CommercialEngine()
        lead = _lead(gbp_category=GBPCategory.PLUMBER, negotiation_step=2)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        # 350 * 0.766 = 268, floor 260 → 268
        assert r.authorized_quote_usd_per_review == round(350 * 0.765625)
        assert r.authorized_quote_usd_per_review >= 260


# ===========================================================================
# B6 — Negotiation step 3 (past final step): escalates (I2/I6 fix)
# ===========================================================================


class TestB6_NegStep3Escalates:
    def test_step3_escalates(self):
        eng = CommercialEngine()
        lead = _lead(gbp_category=GBPCategory.PLUMBER, negotiation_step=3)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        assert r.escalate is True
        assert "step 2" in r.escalation_reason.lower()


# ===========================================================================
# B7 — Self-correction catches invented price not from engine
# ===========================================================================


class TestB7_InventedPriceSCCatch:
    def test_invented_price_fails_floor_or_threshold_check(self, sc_module):
        # SC sees commercial_snapshot floor=$260 (T3 plumber). Draft says $99.
        verdict = sc_module.review(
            draft_subject=None,
            draft_body=(
                "Hi Joe, for Acme Plumbing the rate is $99 per review. "
                "Reply to proceed."
            ),
            channel="email",
            lead_record={
                "first_name": "Joe",
                "business_name": "Acme Plumbing",
                "country": "US",
            },
            transcript=[],
            commercial_snapshot={
                "tier": "T3",
                "floor_usd": 260,
                "authorized_quote_usd_per_review": 350,
                "phone_call_threshold_triggered": False,
            },
            timeline_class="under_1_month",
            soft_quote_mode=False,
        )
        # Either the deterministic floor-breach check escalates, or the LLM
        # flags pricing — both are acceptable signals.
        assert verdict.verdict in ("fix", "escalate"), (
            f"got pass on invented $99 quote: {verdict.failed_checks}"
        )


# ===========================================================================
# B8 — Missing GBP link → engine asks for it before quoting
# ===========================================================================


class TestB8_NoGBPRequestsLink:
    def test_no_gbp_link_requests_first(self):
        eng = CommercialEngine()
        lead = _lead(gbp_category=GBPCategory.PLUMBER, gbp_link=None)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.request_gbp_first is True
        assert r.can_quote is False


# ===========================================================================
# B9 — Hidden cost language ("our margin") → SC escalates
# ===========================================================================


class TestB9_HiddenCostEscalates:
    def test_our_margin_escalates(self, sc_module):
        verdict = sc_module.review(
            draft_subject=None,
            draft_body=(
                "Hi Joe, our margin on this is around 30 percent so the rate is "
                "$350 per review."
            ),
            channel="email",
            lead_record={
                "first_name": "Joe",
                "business_name": "Acme Plumbing",
                "country": "US",
            },
            transcript=[],
            commercial_snapshot={
                "tier": "T3",
                "floor_usd": 260,
                "authorized_quote_usd_per_review": 350,
            },
            timeline_class="under_1_month",
            soft_quote_mode=False,
        )
        assert verdict.verdict == "escalate"


# ===========================================================================
# B10 — T4 nail salon floor enforced at $200
# ===========================================================================


class TestB10_T4FloorEnforced:
    def test_t4_floor_200(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=GBPCategory.NAIL_SALON,
            business_category="nail",
            negotiation_step=2,
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=210)
        assert r.tier == PricingTier.T4
        # 210 * 0.766 = 161 < floor 200 → 200
        assert r.authorized_quote_usd_per_review == 200


# ===========================================================================
# B11 — Dentist with GBP link → T1 detected
# ===========================================================================


class TestB11_DentistT1:
    def test_t1_band(self):
        config, band = get_volume_band(GBPCategory.DENTIST, 2)
        assert config.tier == PricingTier.T1
        assert band.low_usd == 480 and band.high_usd == 530


# ===========================================================================
# B12 — Unknown category + ambiguous name → request_category_first
# ===========================================================================


class TestB12_AskBeforeQuoting:
    def test_no_category_returns_request_category(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=None,
            business_name="Generic Widget Co",
            business_category="",
        )
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.request_category_first is True


# ===========================================================================
# B13 — Image reviews under 1 month: adaptive selector biases low
# ===========================================================================


class TestB13_ImageRecentBiasLow:
    def test_adaptive_picks_lower_half_of_band(self, adaptive_selector):
        lead = _lead(
            gbp_category=GBPCategory.PLUMBER,
            review_count=2,
            recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
            reviews_image_content=[True, True],
            reviews_under_one_month=[True, True],
            lead_tone=LeadTone.COOPERATIVE,
            engagement_level=EngagementLevel.HIGH,
        )
        result = adaptive_selector.select(
            lead=lead, transcript=[],
            tier="T3", range_low_usd=330, range_high_usd=370, floor_usd=260,
        )
        # Image+recent should push toward lower end. Allow midpoint generously.
        midpoint = (330 + 370) // 2
        assert result.selected_price_usd <= midpoint + 5, (
            f"expected <= ${midpoint + 5} (lower bias), got ${result.selected_price_usd}"
        )


# ===========================================================================
# B14 — Text-only over 1 month: adaptive biases high
# ===========================================================================


class TestB14_OverMonthTextBiasHigh:
    def test_adaptive_picks_upper_half(self, adaptive_selector):
        lead = _lead(
            gbp_category=GBPCategory.PLUMBER,
            review_count=2,
            recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
            reviews_image_content=[False, False],
            reviews_under_one_month=[False, False],
            lead_tone=LeadTone.COOPERATIVE,
            engagement_level=EngagementLevel.HIGH,
        )
        result = adaptive_selector.select(
            lead=lead, transcript=[],
            tier="T3", range_low_usd=330, range_high_usd=370, floor_usd=260,
        )
        midpoint = (330 + 370) // 2
        assert result.selected_price_usd >= midpoint - 5, (
            f"expected >= ${midpoint - 5} (upper bias), got ${result.selected_price_usd}"
        )


# ===========================================================================
# B15 — Mixed reviews: adaptive picks defensible midpoint
# ===========================================================================


class TestB15_MixedMidpoint:
    def test_adaptive_picks_within_band(self, adaptive_selector):
        lead = _lead(
            gbp_category=GBPCategory.PLUMBER,
            review_count=2,
            recency_profile=RecencyProfile.MIXED,
            reviews_image_content=[True, False],
            reviews_under_one_month=[True, False],
        )
        result = adaptive_selector.select(
            lead=lead, transcript=[],
            tier="T3", range_low_usd=330, range_high_usd=370, floor_usd=260,
        )
        assert 330 <= result.selected_price_usd <= 370


# ===========================================================================
# B16 — 8 reviews → 6-15 bracket without announcing discount
# ===========================================================================


class TestB16_VolumeDiscountSilent:
    def test_8_review_dentist_uses_medium_band(self):
        config, band = get_volume_band(GBPCategory.DENTIST, 8)
        # Spec: 6-15 bracket for dentist = $430-$475
        assert band.bracket == VolumeBracket.MEDIUM
        assert band.low_usd == 430 and band.high_usd == 475

    def test_live_draft_does_not_announce_discount(self, pipeline):
        lead = _lead(
            lead_id="B16-LIVE",
            business_name="Family Dental Group",
            gbp_category=GBPCategory.DENTIST,
            review_count=8,
            reviews_image_content=[False] * 8,
            reviews_under_one_month=[True] * 8,
        )
        result = pipeline.run(
            lead=lead,
            transcript=[
                {"role": "lead", "channel": "email", "content": "How much per review?"},
            ],
            channel=Channel.EMAIL,
            sequence_stage="reply",
            inbound_message="How much per review?",
            wants_price=True,
        )
        # T1 8 reviews $430-$475 → above $400 → phone route
        # OR if engine quotes (after-hours T1 exception doesn't apply >=3), threshold triggers.
        if result.outcome == "send":
            body = _body(result).lower()
            # No "discount", "bulk", "volume off" framing
            for forbidden in ("discount", "bulk pricing", "volume off", "% off"):
                assert forbidden not in body, f"draft mentioned '{forbidden}': {body[:200]}"


# ===========================================================================
# B18 — ROI language in draft → SC fix
# ===========================================================================


class TestB18_ROISCRejects:
    def test_roi_phrase_caught(self, sc_module):
        verdict = sc_module.review(
            draft_subject=None,
            draft_body=(
                "Hi Sarah, removing these reviews delivers strong ROI for "
                "Bright Smile Dental. Rate is $450 per review."
            ),
            channel="email",
            lead_record={
                "first_name": "Sarah",
                "business_name": "Bright Smile Dental",
                "country": "US",
            },
            transcript=[],
            commercial_snapshot={
                "tier": "T1",
                "floor_usd": 400,
                "authorized_quote_usd_per_review": 450,
            },
            timeline_class="under_1_month",
            soft_quote_mode=False,
        )
        assert verdict.verdict in ("fix", "escalate")
        joined = " ".join(verdict.failed_checks).lower()
        assert "roi" in joined or "lifetime" in joined or "clv" in joined


# ===========================================================================
# B20 — Internal financial figures in draft → SC escalates
# ===========================================================================


class TestB20_InternalCostsEscalate:
    def test_internal_cost_figures_escalate(self, sc_module):
        verdict = sc_module.review(
            draft_subject=None,
            draft_body=(
                "Our cost to remove each review averages $94 so the rate is $350."
            ),
            channel="email",
            lead_record={
                "first_name": "Joe",
                "business_name": "Acme Plumbing",
                "country": "US",
            },
            transcript=[],
            commercial_snapshot={"tier": "T3", "floor_usd": 260},
            timeline_class="under_1_month",
            soft_quote_mode=False,
        )
        assert verdict.verdict == "escalate"


# ===========================================================================
# B21 — T1 phone-call threshold: draft contains no dollar figure
# ===========================================================================


class TestB21_T1PhoneRouteNoDollar:
    def test_live_t1_over_month_no_price_in_draft(self, pipeline):
        lead = _lead(
            lead_id="B21-LIVE",
            business_name="City Dental Clinic",
            gbp_category=GBPCategory.DENTIST,
            review_count=2,
            recency_profile=RecencyProfile.ALL_OVER_1_MONTH,
            reviews_image_content=[False, False],
            reviews_under_one_month=[False, False],
        )
        result = pipeline.run(
            lead=lead,
            transcript=[
                {"role": "lead", "channel": "email", "content": "What's the cost?"},
            ],
            channel=Channel.EMAIL,
            sequence_stage="reply",
            inbound_message="What's the cost?",
            wants_price=True,
        )
        # Engine routes to phone; pipeline should still produce a send draft
        # but with no dollar figure (phone pivot copy).
        assert result.commercial is not None
        assert result.commercial.phone_call_threshold_triggered is True
        assert result.commercial.salesman_recommended_range == (480, 530)
        if result.outcome == "send":
            body = _body(result)
            figs = _dollar_figures(body)
            assert figs == [], f"phone-routed draft must NOT contain $ figures: {figs} / {body[:200]}"


# ===========================================================================
# B22 — T1 exception: 2 image+recent reviews → write at $400-$450
# ===========================================================================


class TestB22_T1ExceptionWrites450:
    def test_engine_accepts_exception_price(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=GBPCategory.DENTIST,
            review_count=2,
            reviews_image_content=[True, True],
            reviews_under_one_month=[True, True],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=450)
        assert r.phone_call_threshold_triggered is False
        assert r.authorized_quote_usd_per_review == 450


# ===========================================================================
# B23 — T2 HVAC above threshold routes to phone
# ===========================================================================


class TestB23_T2HVACPhoneRoute:
    def test_t2_no_exception(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=GBPCategory.HVAC_CONTRACTOR,
            business_category="hvac",
            review_count=2,
            reviews_image_content=[True, True],
            reviews_under_one_month=[True, True],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=420)
        assert r.tier == PricingTier.T2
        # T2 has no exception even with image+recent — all above $400 → phone
        assert r.phone_call_threshold_triggered is True


# ===========================================================================
# B24 — T3 plumber under threshold writes quote
# ===========================================================================


class TestB24_T3WrittenQuote:
    def test_t3_under_threshold_writes(self):
        eng = CommercialEngine()
        lead = _lead(gbp_category=GBPCategory.PLUMBER)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        assert r.tier == PricingTier.T3
        assert r.phone_call_threshold_triggered is False
        assert r.can_quote is True
        assert r.authorized_quote_usd_per_review == 350


# ===========================================================================
# B25 — Adaptive output schema check
# ===========================================================================


class TestB25_AdaptiveOutputSchema:
    def test_live_selector_returns_required_fields(self, adaptive_selector):
        lead = _lead(
            gbp_category=GBPCategory.DENTIST,
            review_count=2,
            reviews_image_content=[True, True],
            reviews_under_one_month=[True, True],
        )
        result = adaptive_selector.select(
            lead=lead, transcript=[],
            tier="T1", range_low_usd=480, range_high_usd=530, floor_usd=400,
        )
        assert isinstance(result.selected_price_usd, int)
        assert result.lead_tone in (
            "cooperative", "price_sensitive", "urgent", "noncommittal",
        )
        assert result.engagement in ("high", "medium", "low")
        assert isinstance(result.reasoning_summary, str)
        assert len(result.reasoning_summary) > 0
        assert len(result.reasoning_summary) <= 240


# ===========================================================================
# B26 — Salesman briefing payload includes pricing context
# ===========================================================================


class TestB26_SalesmanBriefingPayload:
    def test_phone_routed_result_carries_briefing_fields(self):
        eng = CommercialEngine()
        lead = _lead(
            gbp_category=GBPCategory.PLASTIC_SURGEON,
            business_name="Premier Plastic Surgery",
            review_count=2,
            reviews_image_content=[False, False],
            reviews_under_one_month=[False, False],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=530)
        assert r.phone_call_threshold_triggered is True
        # Spec v2 Section 8: salesman briefing fields populated
        assert r.salesman_recommended_range == (520, 550)
        assert r.salesman_recommended_opening_usd == 530
        # Total deal value computable from opening × review count
        total = r.salesman_recommended_opening_usd * lead.review_count
        assert total == 1060


# ===========================================================================
# Phone-call threshold SC pre-check live integration
# ===========================================================================


class TestPhoneThresholdSCDeterministicGate:
    def test_dollar_in_phone_routed_draft_caught_by_sc(self, sc_module):
        """If the LLM mistakenly includes $X in a phone-routed draft, the
        deterministic SC pre-check catches it without depending on the LLM."""
        verdict = sc_module.review(
            draft_subject=None,
            draft_body=(
                "Hi Sarah, the rate for Bright Smile Dental is $500 per review. "
                "Your specialist will call you tomorrow."
            ),
            channel="email",
            lead_record={
                "first_name": "Sarah",
                "business_name": "Bright Smile Dental",
                "country": "US",
            },
            transcript=[],
            commercial_snapshot={
                "tier": "T1",
                "floor_usd": 400,
                "phone_call_threshold_triggered": True,
            },
            timeline_class="under_1_month",
            soft_quote_mode=False,
        )
        assert verdict.verdict in ("fix", "escalate")
        joined = " ".join(verdict.failed_checks).lower()
        assert "phone_call_threshold" in joined or "phone" in joined
