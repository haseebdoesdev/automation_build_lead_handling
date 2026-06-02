"""Soft-quote mode tests for the spec v2 industry-based engine.

Soft-quote mode (preserved from v7 Section 17) returns a band-based range,
disables negotiation, and escalates on any pushback.
"""

from __future__ import annotations

import pytest

from reviewarmour.commercial import CommercialEngine
from reviewarmour.models import (
    Country,
    GBPCategory,
    LeadRecord,
    PricingTier,
    RecencyProfile,
)


def _lead(soft_quote: bool = False, **kwargs) -> LeadRecord:
    defaults = dict(
        lead_id="sq-1",
        first_name="Test",
        last_name="Lead",
        business_name="Test Biz",
        country=Country.US,
        phone="+15550001111",
        email="test@biz.com",
        gbp_link="https://maps.google.com/test",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumbing",
        gbp_category=GBPCategory.PLUMBER,
        soft_quote_mode=soft_quote,
    )
    defaults.update(kwargs)
    return LeadRecord(**defaults)


class TestSoftQuoteRange:
    def test_returns_band_range(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.soft_quote_mode is True
        # Plumber T3 small band is $330-$370
        assert r.soft_quote_range == (330, 370)
        assert r.authorized_quote_usd_per_review == 370  # quoted = high end of range

    def test_can_quote_true_in_soft_mode(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.can_quote is True

    def test_t1_soft_quote_returns_t1_band(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True, gbp_category=GBPCategory.DENTIST)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.tier == PricingTier.T1
        assert r.soft_quote_range == (480, 530)


class TestSoftQuoteNoNegotiation:
    def test_pushback_escalates(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True, negotiation_step=1)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.escalate is True
        assert "pushback" in r.escalation_reason.lower() or "soft" in r.escalation_reason.lower()

    def test_below_floor_escalates(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True)
        r = eng.evaluate_pricing(
            lead, wants_price=True, lead_requested_price_below_floor=True
        )
        assert r.escalate is True


class TestSoftQuoteGBPRequired:
    def test_no_gbp_requests_link(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True, gbp_link=None)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.request_gbp_first is True
        assert r.can_quote is False


class TestSoftQuoteCommercialTurn:
    def test_commercial_turn_created_when_quoting(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True)
        r = eng.evaluate_pricing(lead, wants_price=True)
        assert r.commercial_turn is not None

    def test_no_commercial_turn_when_not_quoting(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=True)
        r = eng.evaluate_pricing(lead, wants_price=False)
        assert r.commercial_turn is None


class TestHardQuoteUnchanged:
    """Soft-quote toggle must not affect hard-quote behavior on the same data."""

    def test_hard_quote_uses_adaptive_price(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=False)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        assert r.soft_quote_mode is False
        assert r.soft_quote_range is None
        assert r.authorized_quote_usd_per_review == 350

    def test_hard_quote_negotiation_works(self) -> None:
        eng = CommercialEngine()
        lead = _lead(soft_quote=False, negotiation_step=1)
        r = eng.evaluate_pricing(lead, wants_price=True, adaptive_price_usd=350)
        # Step 1 ≈ 12.5% off → ~306
        assert r.authorized_quote_usd_per_review == round(350 * 0.875)
