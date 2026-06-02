"""Spec v2 — additional deterministic coverage for new behaviors.

Covers:
  - Volume-bracket pricing (1-5, 6-15, 16-30, 30+)
  - SC pre-checks (phone-call threshold violation, ROI/CLV, hidden cost, floor breach)
  - GBP category mapping from free text / business names
  - T1 exception edge cases (≤2 reviews, image-or-recent)
  - Salesman briefing pricing context
"""

from __future__ import annotations

import pytest

from reviewarmour.commercial import (
    CommercialEngine,
    get_volume_band,
    phone_call_threshold_applies,
)
from reviewarmour.gbp.inference import (
    guess_category_from_business_name,
    map_text_to_gbp_category,
)
from reviewarmour.models import (
    Country,
    GBPCategory,
    LeadRecord,
    PricingTier,
    RecencyProfile,
    VolumeBracket,
)
from reviewarmour.self_correction import (
    SelfCorrectionVerdict,
    _draft_dollar_figures,
    _floor_breach_check,
    _hidden_cost_language_check,
    _phone_call_threshold_violation_check,
    _roi_clv_language_check,
)


def _pass() -> SelfCorrectionVerdict:
    return SelfCorrectionVerdict(
        verdict="pass", failed_checks=[], suggested_fixes=[], escalation_reason=None
    )


def _lead(**kwargs) -> LeadRecord:
    defaults = dict(
        lead_id="v2-1",
        first_name="Test",
        last_name="Lead",
        business_name="Acme Test",
        country=Country.US,
        phone="+15550001",
        email="t@b.com",
        gbp_link="https://maps.google.com/x",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="dental",
        gbp_category=GBPCategory.DENTIST,
        reviews_image_content=[False, False],
        reviews_under_one_month=[True, True],
    )
    defaults.update(kwargs)
    return LeadRecord(**defaults)


# ---------------------------------------------------------------------------
# Volume bracket pricing
# ---------------------------------------------------------------------------


class TestVolumeBrackets:
    """Spec v2 Section 2: discounts at 6-15, 16-30, 30+ brackets."""

    def test_dentist_small_bracket(self) -> None:
        config, band = get_volume_band(GBPCategory.DENTIST, 3)
        assert band.bracket == VolumeBracket.SMALL
        assert band.low_usd == 480 and band.high_usd == 530

    def test_dentist_medium_bracket(self) -> None:
        config, band = get_volume_band(GBPCategory.DENTIST, 8)
        assert band.bracket == VolumeBracket.MEDIUM
        assert band.low_usd == 430 and band.high_usd == 475

    def test_dentist_large_bracket(self) -> None:
        config, band = get_volume_band(GBPCategory.DENTIST, 20)
        assert band.bracket == VolumeBracket.LARGE
        assert band.low_usd == 385 and band.high_usd == 425

    def test_dentist_bulk_bracket(self) -> None:
        config, band = get_volume_band(GBPCategory.DENTIST, 40)
        assert band.bracket == VolumeBracket.BULK
        assert band.low_usd == 360 and band.high_usd == 400

    def test_plumber_medium_bracket(self) -> None:
        # Spec section 3: Plumber 6-15 = $295-$335
        config, band = get_volume_band(GBPCategory.PLUMBER, 8)
        assert band.low_usd == 295 and band.high_usd == 335


# ---------------------------------------------------------------------------
# T1 exception edge cases
# ---------------------------------------------------------------------------


class TestT1Exception:
    def test_one_review_all_image_writes_at_400(self) -> None:
        eng = CommercialEngine()
        lead = _lead(
            review_count=1,
            reviews_image_content=[True],
            reviews_under_one_month=[True],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=400)
        assert r.authorized_quote_usd_per_review == 400
        assert r.phone_call_threshold_triggered is False

    def test_2_reviews_one_text_one_image_only_partial_routes_to_phone(self) -> None:
        """If one review is text-only and over a month, exception fails."""
        eng = CommercialEngine()
        lead = _lead(
            review_count=2,
            reviews_image_content=[True, False],
            reviews_under_one_month=[True, False],
        )
        # Second review is neither image nor recent → T1 exception fails.
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=500)
        assert r.phone_call_threshold_triggered is True

    def test_3_reviews_does_not_qualify_for_exception(self) -> None:
        eng = CommercialEngine()
        lead = _lead(
            review_count=3,
            reviews_image_content=[True, True, True],
            reviews_under_one_month=[True, True, True],
        )
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=500)
        # 3 reviews > 2 → exception doesn't apply, routes to phone.
        assert r.phone_call_threshold_triggered is True


# ---------------------------------------------------------------------------
# SC pre-checks
# ---------------------------------------------------------------------------


class TestPhoneCallThresholdSCCheck:
    def test_no_dollar_in_phone_route_draft_passes(self) -> None:
        v = _phone_call_threshold_violation_check(
            _pass(),
            draft_body="Your specialist will walk you through pricing on a quick call.",
            commercial_snapshot={"phone_call_threshold_triggered": True},
        )
        assert v.verdict == "pass"

    def test_dollar_amount_in_phone_route_draft_fails(self) -> None:
        v = _phone_call_threshold_violation_check(
            _pass(),
            draft_body="The investment is $500 per review.",
            commercial_snapshot={"phone_call_threshold_triggered": True},
        )
        assert v.verdict == "fix"
        assert any("phone_call_threshold" in f for f in v.failed_checks)

    def test_no_violation_when_threshold_not_triggered(self) -> None:
        v = _phone_call_threshold_violation_check(
            _pass(),
            draft_body="We can do this at $350 per review.",
            commercial_snapshot={"phone_call_threshold_triggered": False},
        )
        assert v.verdict == "pass"


class TestROICLVCheck:
    def test_no_roi_passes(self) -> None:
        v = _roi_clv_language_check(_pass(), draft_body="We can help you with this.")
        assert v.verdict == "pass"

    def test_roi_mention_fails(self) -> None:
        v = _roi_clv_language_check(
            _pass(),
            draft_body="The ROI on this is significant for your business.",
        )
        assert v.verdict == "fix"

    def test_clv_mention_fails(self) -> None:
        v = _roi_clv_language_check(
            _pass(), draft_body="Each customer's lifetime value is substantial."
        )
        assert v.verdict == "fix"

    def test_return_on_investment_phrase_fails(self) -> None:
        v = _roi_clv_language_check(
            _pass(), draft_body="Consider the return on investment over a year."
        )
        assert v.verdict == "fix"


class TestHiddenCostCheck:
    def test_our_margin_escalates(self) -> None:
        v = _hidden_cost_language_check(
            _pass(), draft_body="Our margin on this is around 30%."
        )
        assert v.verdict == "escalate"
        assert v.escalation_reason == "hidden_cost_leak"

    def test_cost_to_remove_escalates(self) -> None:
        v = _hidden_cost_language_check(
            _pass(), draft_body="The cost to remove these reviews is high."
        )
        assert v.verdict == "escalate"

    def test_lead_cost_escalates(self) -> None:
        v = _hidden_cost_language_check(
            _pass(), draft_body="Our lead cost on this exceeds $80."
        )
        assert v.verdict == "escalate"

    def test_normal_pricing_text_passes(self) -> None:
        v = _hidden_cost_language_check(
            _pass(), draft_body="The investment is $400 per review."
        )
        assert v.verdict == "pass"


class TestFloorBreachCheck:
    def test_t1_floor_400_quote_390_escalates(self) -> None:
        v = _floor_breach_check(
            _pass(),
            draft_body="We can do this at $390 per review.",
            commercial_snapshot={"floor_usd": 400},
        )
        assert v.verdict == "escalate"

    def test_t3_floor_260_quote_350_passes(self) -> None:
        v = _floor_breach_check(
            _pass(),
            draft_body="We can do this at $350 per review.",
            commercial_snapshot={"floor_usd": 260},
        )
        assert v.verdict == "pass"

    def test_no_floor_in_snapshot_passes(self) -> None:
        v = _floor_breach_check(_pass(), draft_body="$200 per review", commercial_snapshot=None)
        assert v.verdict == "pass"


class TestDraftDollarFigures:
    def test_finds_dollar_sign_amount(self) -> None:
        assert "$500" in _draft_dollar_figures("Our quote is $500.")

    def test_finds_usd_suffix(self) -> None:
        assert any("450" in f for f in _draft_dollar_figures("450 USD per review."))

    def test_finds_per_review_format(self) -> None:
        figures = _draft_dollar_figures("That's 350 per review.")
        assert any("350" in f for f in figures)

    def test_no_match_in_plain_text(self) -> None:
        assert _draft_dollar_figures("Thanks for reaching out.") == []


# ---------------------------------------------------------------------------
# GBP category mapping
# ---------------------------------------------------------------------------


class TestCategoryMapping:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Family Dentistry", "dentist"),
            ("Bright Smile Dental", "dentist"),
            ("Acme Plumbing LLC", "plumber"),
            ("Smith & Co Law Firm", "law_firm"),
            ("Johnson HVAC Heating & Air", "hvac_contractor"),
            ("ABC Roofing Contractors", "roofing_contractor"),
            ("Sunset Hotel", "hotel"),
            ("Joe's Pizza Restaurant", "restaurant"),
            ("Glamour Nail Salon", "nail_salon"),
            ("Quick Auto Repair", "auto_repair"),
            ("Greenfield Med Spa", "med_spa"),
            ("State Farm Insurance", "insurance_agency"),
            ("Premier Real Estate Agency", "real_estate_agency"),
            ("Pacific Chiropractic", "chiropractor"),
            ("Top Notch Electric", "electrician"),
        ],
    )
    def test_business_name_maps(self, text: str, expected: str) -> None:
        assert guess_category_from_business_name(text) == expected

    def test_unknown_name_returns_none(self) -> None:
        assert guess_category_from_business_name("Random Widget Co") is None

    def test_enum_values_round_trip(self) -> None:
        for s in ("dentist", "plumber", "law_firm", "hotel"):
            assert GBPCategory(s).value == s
