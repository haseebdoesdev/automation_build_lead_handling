from __future__ import annotations

from datetime import datetime, timezone

import pytest

from reviewarmour.commercial import (
    CommercialEngine,
    apply_pushback,
    margin_ok,
    pushback_already_recorded,
    record_negotiation_pushback,
)
from reviewarmour.models import Country, LeadRecord, RecencyProfile


def _base_lead(**kwargs) -> LeadRecord:
    defaults = dict(
        lead_id="L1",
        first_name="Alex",
        last_name="Patel",
        business_name="Acme Dental",
        country=Country.US,
        phone="+15550001",
        email="a@example.com",
        gbp_link="https://g.page/test",
        review_count=1,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="dental",
    )
    defaults.update(kwargs)
    return LeadRecord(**defaults)


def test_us_one_review_dental_under_month_tier_us2_opening_500() -> None:
    eng = CommercialEngine()
    lead = _base_lead(review_count=1, business_category="dental")
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.tier_id == "US-2"
    assert r.authorized_quote_usd_per_review == 500
    assert r.negotiation_step == 0


def test_us_four_reviews_mostly_under_plumber_tier_us3_opening_425() -> None:
    eng = CommercialEngine()
    lead = _base_lead(
        review_count=4,
        business_category="plumber",
        recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
    )
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.tier_id == "US-3"
    assert r.authorized_quote_usd_per_review == 425


def test_ca_two_reviews_restaurant_tier_ca1_opening_375() -> None:
    eng = CommercialEngine()
    lead = _base_lead(
        country=Country.CA,
        review_count=2,
        business_category="restaurant",
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
    )
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.tier_id == "CA-1"
    assert r.authorized_quote_usd_per_review == 375


def test_pushback_once_goes_to_neg1_and_logs_trigger() -> None:
    eng = CommercialEngine()
    lead = _base_lead(review_count=2, business_category="retail")
    lead2 = apply_pushback(lead, "Still too expensive for us")
    assert lead2.negotiation_step == 1
    assert len(lead2.negotiation_triggers) == 1
    assert lead2.negotiation_triggers[0].lead_message_exact == "Still too expensive for us"
    assert lead2.negotiation_triggers[0].step_after == 1

    r = eng.evaluate_pricing(lead2, wants_price=True)
    assert r.tier_id == "US-1"
    assert r.authorized_quote_usd_per_review == 425


def test_pushback_twice_goes_to_neg2() -> None:
    eng = CommercialEngine()
    lead = _base_lead(review_count=2, business_category="retail")
    lead = apply_pushback(lead, "first pushback")
    lead = apply_pushback(lead, "second push — still too high")
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.authorized_quote_usd_per_review == 400


def test_pushback_already_recorded_matches_latest_trigger() -> None:
    lead = apply_pushback(_base_lead(), "Still too expensive for us")
    assert pushback_already_recorded(lead, "Still too expensive for us")
    assert not pushback_already_recorded(lead, "Different pushback text")


def test_record_negotiation_pushback_is_idempotent_for_same_message() -> None:
    lead = apply_pushback(_base_lead(), "first pushback")
    assert lead.negotiation_step == 1
    assert record_negotiation_pushback(lead, "first pushback") is False
    assert lead.negotiation_step == 1
    assert len(lead.negotiation_triggers) == 1


def test_record_negotiation_pushback_advances_on_new_message() -> None:
    lead = _base_lead(review_count=2, business_category="retail")
    assert record_negotiation_pushback(lead, "first pushback") is True
    assert lead.negotiation_step == 1
    assert record_negotiation_pushback(lead, "second pushback") is True
    assert lead.negotiation_step == 2


def test_below_floor_escalates_no_quote() -> None:
    eng = CommercialEngine()
    lead = _base_lead()
    r = eng.evaluate_pricing(lead, wants_price=True, lead_requested_price_below_floor=True)
    assert r.escalate
    assert r.authorized_quote_usd_per_review is None


def test_margin_discipline_fails_escalates() -> None:
    eng = CommercialEngine()
    lead = _base_lead(
        country=Country.CA,
        review_count=6,
        recency_profile=RecencyProfile.MIXED,
        is_price_sensitive_bulk=True,
        business_category="retail",
        negotiation_step=2,
    )
    assert lead.negotiation_step == 2
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.tier_id == "CA-6"
    assert not margin_ok(250, lead)
    assert r.escalate
    assert "Margin" in (r.escalation_reason or "")


def test_gbp_missing_requests_link_no_quote() -> None:
    eng = CommercialEngine()
    lead = _base_lead(gbp_link=None)
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.request_gbp_first
    assert not r.can_quote
    assert r.authorized_quote_usd_per_review is None
    assert not r.escalate


def test_ai_quote_allowed_false_escalates() -> None:
    eng = CommercialEngine()
    lead = _base_lead(ai_quote_allowed=False)
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.escalate
    assert r.authorized_quote_usd_per_review is None


def test_negotiation_past_step_two_escalates() -> None:
    eng = CommercialEngine()
    lead = _base_lead(review_count=2, business_category="retail", negotiation_step=3)
    r = eng.evaluate_pricing(lead, wants_price=True)
    assert r.escalate
    assert r.authorized_quote_usd_per_review is None


def test_bulk_tier_us6_when_mixed_and_five_plus_reviews() -> None:
    eng = CommercialEngine()
    us5 = _base_lead(
        review_count=5,
        recency_profile=RecencyProfile.MOSTLY_UNDER_1_MONTH,
        is_price_sensitive_bulk=True,
        business_category="retail",
    )
    assert eng.evaluate_pricing(us5, wants_price=True).tier_id == "US-3"

    us6 = _base_lead(
        review_count=5,
        recency_profile=RecencyProfile.MIXED,
        is_price_sensitive_bulk=True,
        business_category="retail",
    )
    assert eng.evaluate_pricing(us6, wants_price=True).tier_id == "US-6"

    us6_no_flag = _base_lead(
        review_count=5,
        recency_profile=RecencyProfile.MIXED,
        is_price_sensitive_bulk=False,
        business_category="retail",
    )
    assert eng.evaluate_pricing(us6_no_flag, wants_price=True).tier_id == "US-6"
