"""Deterministic tests for the spec v2 industry-based commercial engine.

Replaces the v7 US-1..US-6 / CA-1..CA-6 suite. The new engine:
  - maps GBPCategory + review-count volume bracket to a tier band (range + floor)
  - validates an adaptive (LLM-chosen) price is in band, with a T1 written-quote
    exception for image-or-recent ≤2-review leads
  - applies the negotiation step ladder (×1.0 / ×0.875 / ×0.766) clamped to floor
  - gates the phone-call threshold at $400 (except T1 exception up to $450)
"""

from __future__ import annotations

import pytest

from reviewarmour.commercial import (
    CommercialEngine,
    PHONE_CALL_THRESHOLD_USD,
    T1_WRITTEN_EXCEPTION_CEILING_USD,
    TIER_MATRIX,
    apply_negotiation_step,
    apply_pushback,
    get_tier_config,
    get_volume_band,
    phone_call_threshold_applies,
    pushback_already_recorded,
    record_negotiation_pushback,
)
from reviewarmour.models import (
    Country,
    GBPCategory,
    LeadRecord,
    PricingTier,
    RecencyProfile,
    VolumeBracket,
    volume_bracket_from_count,
)


def _lead(**kwargs) -> LeadRecord:
    defaults = dict(
        lead_id="L1",
        first_name="Alex",
        last_name="Patel",
        business_name="Acme Test",
        country=Country.US,
        phone="+15550001",
        email="a@example.com",
        gbp_link="https://g.page/test",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="dental",
        gbp_category=GBPCategory.DENTIST,
        reviews_image_content=[False, False],
        reviews_under_one_month=[False, False],
    )
    defaults.update(kwargs)
    return LeadRecord(**defaults)


# ---------------------------------------------------------------------------
# Tier matrix completeness
# ---------------------------------------------------------------------------


def test_all_gbp_categories_except_other_are_in_matrix() -> None:
    for cat in GBPCategory:
        if cat == GBPCategory.OTHER:
            continue
        assert cat in TIER_MATRIX, f"missing matrix entry for {cat}"


def test_tier_floors_match_spec() -> None:
    """Spec v2 Section 1: T1=$400, T2=$350, T3=$260, T4=$200."""
    floors = {
        PricingTier.T1: 400,
        PricingTier.T2: 350,
        PricingTier.T3: 260,
        PricingTier.T4: 200,
    }
    for cat, config in TIER_MATRIX.items():
        assert config.floor_usd == floors[config.tier], (
            f"{cat.value} floor wrong: {config.floor_usd}"
        )


def test_volume_bracket_thresholds() -> None:
    assert volume_bracket_from_count(1) == VolumeBracket.SMALL
    assert volume_bracket_from_count(5) == VolumeBracket.SMALL
    assert volume_bracket_from_count(6) == VolumeBracket.MEDIUM
    assert volume_bracket_from_count(15) == VolumeBracket.MEDIUM
    assert volume_bracket_from_count(16) == VolumeBracket.LARGE
    assert volume_bracket_from_count(30) == VolumeBracket.LARGE
    assert volume_bracket_from_count(31) == VolumeBracket.BULK


# ---------------------------------------------------------------------------
# Tier band lookup
# ---------------------------------------------------------------------------


def test_dentist_t1_small_range() -> None:
    config, band = get_volume_band(GBPCategory.DENTIST, 2)
    assert config.tier == PricingTier.T1
    assert band.bracket == VolumeBracket.SMALL
    assert band.low_usd == 480 and band.high_usd == 530


def test_plumber_t3_small_range() -> None:
    config, band = get_volume_band(GBPCategory.PLUMBER, 2)
    assert config.tier == PricingTier.T3
    assert band.low_usd == 330 and band.high_usd == 370


def test_nail_salon_t4_small_range() -> None:
    config, band = get_volume_band(GBPCategory.NAIL_SALON, 2)
    assert config.tier == PricingTier.T4
    assert band.low_usd == 210 and band.high_usd == 250


def test_other_falls_back_to_t3() -> None:
    config = get_tier_config(GBPCategory.OTHER)
    assert config.tier == PricingTier.T3


def test_unknown_category_falls_back_to_t3() -> None:
    config = get_tier_config(None)
    assert config.tier == PricingTier.T3


# ---------------------------------------------------------------------------
# Phone-call threshold gate (spec v2 Section 4)
# ---------------------------------------------------------------------------


def test_threshold_no_trigger_under_400() -> None:
    assert not phone_call_threshold_applies(
        400, tier=PricingTier.T3, review_count=2, all_reviews_image_or_recent=False
    )


def test_threshold_triggers_above_400_default() -> None:
    assert phone_call_threshold_applies(
        500, tier=PricingTier.T1, review_count=2, all_reviews_image_or_recent=False
    )


def test_t1_exception_2_reviews_all_image_or_recent() -> None:
    # Up to $450 is allowed in writing when conditions are met.
    assert not phone_call_threshold_applies(
        450, tier=PricingTier.T1, review_count=2, all_reviews_image_or_recent=True
    )


def test_t1_exception_does_not_apply_above_450() -> None:
    assert phone_call_threshold_applies(
        451, tier=PricingTier.T1, review_count=2, all_reviews_image_or_recent=True
    )


def test_t1_exception_does_not_apply_with_3_plus_reviews() -> None:
    assert phone_call_threshold_applies(
        450, tier=PricingTier.T1, review_count=3, all_reviews_image_or_recent=True
    )


def test_t1_exception_does_not_apply_when_not_all_image_or_recent() -> None:
    assert phone_call_threshold_applies(
        450, tier=PricingTier.T1, review_count=2, all_reviews_image_or_recent=False
    )


def test_t2_above_400_always_triggers() -> None:
    # T2 has no exception.
    assert phone_call_threshold_applies(
        420, tier=PricingTier.T2, review_count=2, all_reviews_image_or_recent=True
    )


# ---------------------------------------------------------------------------
# Negotiation step ladder
# ---------------------------------------------------------------------------


def test_step_0_is_full_price() -> None:
    assert apply_negotiation_step(500, 0, 400) == 500


def test_step_1_drops_about_12_5_percent() -> None:
    assert apply_negotiation_step(500, 1, 400) == round(500 * 0.875)  # 438


def test_step_2_compounds() -> None:
    assert apply_negotiation_step(500, 2, 400) == max(round(500 * 0.765625), 400)  # 400 (floor)


def test_step_clamps_to_floor() -> None:
    # Plumber at $330 step 2 = 252 < floor 260 → 260.
    assert apply_negotiation_step(330, 2, 260) == 260


# ---------------------------------------------------------------------------
# CommercialEngine.evaluate_pricing — written-quote path (T3/T4)
# ---------------------------------------------------------------------------


def test_t3_plumber_written_quote() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.PLUMBER, business_category="plumber")
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
    assert r.tier == PricingTier.T3
    assert r.authorized_quote_usd_per_review == 350
    assert r.can_quote is True
    assert r.phone_call_threshold_triggered is False
    assert r.commercial_turn is not None


def test_t4_nail_salon_floor_enforced() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.NAIL_SALON, business_category="nail", review_count=2)
    # Adaptive picks $210 (band low), then step 2 drops to ~161 → floor 200 wins.
    lead.negotiation_step = 2
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=210)
    assert r.tier == PricingTier.T4
    assert r.authorized_quote_usd_per_review == 200


# ---------------------------------------------------------------------------
# CommercialEngine.evaluate_pricing — phone-call route (T1/T2)
# ---------------------------------------------------------------------------


def test_t1_dentist_above_threshold_routes_to_phone() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.DENTIST, review_count=2)
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=500)
    assert r.phone_call_threshold_triggered is True
    assert r.authorized_quote_usd_per_review is None  # never quoted in writing
    assert r.can_quote is False
    assert r.salesman_recommended_range == (480, 530)
    assert r.salesman_recommended_opening_usd == 500


def test_t1_dentist_exception_writes_450() -> None:
    eng = CommercialEngine()
    lead = _lead(
        gbp_category=GBPCategory.DENTIST,
        review_count=2,
        reviews_image_content=[True, False],
        reviews_under_one_month=[True, True],
    )
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=450)
    assert r.phone_call_threshold_triggered is False
    assert r.authorized_quote_usd_per_review == 450
    assert r.can_quote is True


def test_t2_hvac_above_threshold_routes_to_phone() -> None:
    eng = CommercialEngine()
    lead = _lead(
        gbp_category=GBPCategory.HVAC_CONTRACTOR,
        business_category="hvac",
        review_count=2,
    )
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=420)
    assert r.tier == PricingTier.T2
    assert r.phone_call_threshold_triggered is True
    assert r.authorized_quote_usd_per_review is None


# ---------------------------------------------------------------------------
# Validation guards
# ---------------------------------------------------------------------------


def test_no_gbp_category_requests_category() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=None)
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.request_category_first is True
    assert r.can_quote is False


def test_no_gbp_link_requests_link() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_link=None)
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.request_gbp_first is True
    assert r.can_quote is False


def test_ai_quote_allowed_false_escalates() -> None:
    eng = CommercialEngine()
    lead = _lead(ai_quote_allowed=False)
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
    assert r.escalate is True
    assert "ai_quote_allowed" in r.escalation_reason


def test_below_floor_escalates() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.PLUMBER)
    r = eng.evaluate_pricing(
        lead,
        wants_price=True,
        adaptive_price_usd=350,
        lead_requested_price_below_floor=True,
    )
    assert r.escalate is True
    assert "floor" in r.escalation_reason.lower()


def test_negotiation_past_step_2_escalates() -> None:
    """Spec v2 + I2/I6 fix: pushback 3 (step > 2) escalates; step 2 still quotes."""
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.PLUMBER, negotiation_step=3)
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
    assert r.escalate is True
    assert "step 2" in r.escalation_reason.lower()


def test_step_2_still_quotes_not_escalates() -> None:
    """I2/I6 bug regression: step 2 must produce a discounted quote, not escalate."""
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.PLUMBER, negotiation_step=2)
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
    assert r.escalate is False
    assert r.authorized_quote_usd_per_review is not None
    assert r.authorized_quote_usd_per_review >= 260  # floor
    assert r.authorized_quote_usd_per_review <= 350  # ≤ adaptive


def test_adaptive_price_outside_band_escalates() -> None:
    eng = CommercialEngine()
    lead = _lead(gbp_category=GBPCategory.PLUMBER)
    # Plumber band is $330-$370; adaptive=$200 is out.
    r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=200)
    assert r.escalate is True
    assert "outside band" in r.escalation_reason.lower()


# ---------------------------------------------------------------------------
# Negotiation state machine (unchanged from v7)
# ---------------------------------------------------------------------------


def test_pushback_advances_step() -> None:
    lead = _lead()
    updated = apply_pushback(lead, "too expensive")
    assert updated.negotiation_step == 1


def test_pushback_idempotent_for_same_message() -> None:
    lead = _lead()
    record_negotiation_pushback(lead, "too expensive")
    assert lead.negotiation_step == 1
    # Same message → no advance
    record_negotiation_pushback(lead, "too expensive")
    assert lead.negotiation_step == 1


def test_pushback_advances_on_new_message() -> None:
    lead = _lead()
    record_negotiation_pushback(lead, "too expensive")
    record_negotiation_pushback(lead, "still too high")
    assert lead.negotiation_step == 2


def test_pushback_stops_at_max_step() -> None:
    lead = _lead(negotiation_step=2)
    advanced = record_negotiation_pushback(lead, "way too much")
    assert advanced is False
    assert lead.negotiation_step == 2


def test_pushback_already_recorded() -> None:
    lead = _lead()
    record_negotiation_pushback(lead, "no way")
    assert pushback_already_recorded(lead, "no way") is True
    assert pushback_already_recorded(lead, "different msg") is False
