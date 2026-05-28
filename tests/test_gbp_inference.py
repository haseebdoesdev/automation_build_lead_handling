"""Pure inference tests for GBP / Maps review metadata (no Playwright)."""

from reviewarmour.gbp.inference import (
    infer_recency_profile,
    inspection_dict_to_lead_field_updates,
    relative_review_age_days,
)
from reviewarmour.models import RecencyProfile


def test_relative_review_age_days_weeks():
    assert relative_review_age_days("3 weeks ago") == 21.0


def test_infer_recency_all_recent():
    rp = infer_recency_profile(["2 days ago", "1 week ago", "3 weeks ago"])
    assert rp == RecencyProfile.ALL_UNDER_1_MONTH


def test_infer_recency_mixed():
    rp = infer_recency_profile(
        ["2 days ago", "3 weeks ago", "2 months ago", "5 months ago"]
    )
    assert rp == RecencyProfile.MIXED


def test_inspection_to_lead_updates_empty_on_error():
    assert inspection_dict_to_lead_field_updates({"status": "error"}) == {}


def test_inspection_to_lead_updates_success():
    upd = inspection_dict_to_lead_field_updates(
        {
            "status": "success",
            "inferred_recency_profile": RecencyProfile.MOSTLY_OVER_1_MONTH.value,
            "review_count_inferred": 42,
            "any_review_has_images": True,
            "category_hints": ["dental"],
        }
    )
    assert upd["recency_profile"] == RecencyProfile.MOSTLY_OVER_1_MONTH.value
    assert upd["review_count"] == 42
    assert upd["notes_images_observed"] is True
    assert upd["business_category"] == "dental"
