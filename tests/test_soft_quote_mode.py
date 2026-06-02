"""Tests for soft-quote mode (Section 17)."""

import pytest

from reviewarmour.commercial import CommercialEngine
from reviewarmour.models import Country, LeadRecord, RecencyProfile


@pytest.fixture
def engine():
    return CommercialEngine()


def _lead(soft_quote: bool = False, **kw) -> LeadRecord:
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
        soft_quote_mode=soft_quote,
    )
    defaults.update(kw)
    return LeadRecord(**defaults)


class TestSoftQuoteRange:
    """Soft-quote mode returns a range instead of a specific number."""

    def test_returns_range(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.soft_quote_mode is True
        assert r.soft_quote_range is not None
        low, high = r.soft_quote_range
        assert low < high
        assert high == r.opening

    def test_us1_range(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.tier_id == "US-1"
        assert r.soft_quote_range == (400, 450)  # neg_2=400, opening=450

    def test_ca1_range(self, engine):
        lead = _lead(soft_quote=True, country=Country.CA)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.tier_id == "CA-1"
        assert r.soft_quote_range == (275, 375)  # neg_2=275, opening=375

    def test_can_quote_true(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.can_quote is True
        assert r.authorized_quote_usd_per_review == r.opening


class TestSoftQuoteNoNegotiation:
    """Soft-quote mode: pushback escalates immediately, no negotiation."""

    def test_pushback_escalates(self, engine):
        lead = _lead(soft_quote=True, negotiation_step=1)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.escalate is True
        assert "pushback" in r.escalation_reason.lower() or "soft" in r.escalation_reason.lower()

    def test_below_floor_escalates(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=True, lead_requested_price_below_floor=True)
        assert r.escalate is True


class TestSoftQuoteGBPRequired:
    """Soft-quote mode still requires GBP link before quoting."""

    def test_no_gbp_requests_link(self, engine):
        lead = _lead(soft_quote=True, gbp_link=None)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.request_gbp_first is True
        assert r.can_quote is False


class TestSoftQuoteCommercialTurn:
    """Soft-quote mode creates a commercial turn marker for stall detection."""

    def test_commercial_turn_created(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.commercial_turn is not None

    def test_no_commercial_turn_when_not_quoting(self, engine):
        lead = _lead(soft_quote=True)
        r = engine.evaluate_pricing(lead, wants_price=False)
        # When soft_quote_mode is on but wants_price is False, falls through to normal path
        assert r.commercial_turn is None


class TestHardQuoteUnchanged:
    """Hard-quote mode (default) is not affected by soft-quote changes."""

    def test_us1_opening(self, engine):
        lead = _lead(soft_quote=False)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.authorized_quote_usd_per_review == 450
        assert r.soft_quote_mode is False
        assert r.soft_quote_range is None

    def test_negotiation_works(self, engine):
        lead = _lead(soft_quote=False, negotiation_step=1)
        r = engine.evaluate_pricing(lead, wants_price=True)
        assert r.authorized_quote_usd_per_review == 425  # neg_1
