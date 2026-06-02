"""Derive ``RecencyProfile`` and lead hints from scraped Maps review metadata.

No Playwright — pure Python for tests and CRM merges.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from reviewarmour.models import RecencyProfile


def relative_review_age_days(published_at: Optional[str]) -> Optional[float]:
    """Map Google's relative strings ('3 weeks ago', 'a month ago') to approximate days.

    Returns ``None`` if unparseable. Larger = older for sorting newest-first.
    """
    if not published_at:
        return None
    s = published_at.strip().lower()

    if "minute" in s or "hour" in s or "just now" in s:
        return 0.0
    if "yesterday" in s:
        return 1.0

    num = 1
    m = re.search(r"(\d+)", s)
    if m:
        num = int(m.group(1))
    elif "a " in s or "an " in s:
        num = 1

    if "day" in s:
        return float(num)
    if "week" in s:
        return float(num * 7)
    if "month" in s:
        return float(num * 30)
    if "year" in s:
        return float(num * 365)
    return None


def infer_recency_profile(
    review_dates: list[Optional[str]],
    *,
    under_month_threshold_days: float = 31.0,
) -> RecencyProfile:
    """Infer ``RecencyProfile`` from a sample of relative date strings.

    Conservative: many unknowns → ``UNCERTAIN``. Uses rough calendar buckets
    aligned with commercial tier logic (under vs over ~1 month).
    """
    days_list: list[float] = []
    for d in review_dates:
        dd = relative_review_age_days(d)
        if dd is not None:
            days_list.append(dd)

    if not days_list:
        return RecencyProfile.UNCERTAIN

    under = sum(1 for x in days_list if x <= under_month_threshold_days)
    over = sum(1 for x in days_list if x > under_month_threshold_days)
    n = len(days_list)

    if over == 0 and under == n:
        return RecencyProfile.ALL_UNDER_1_MONTH
    if under == 0 and over == n:
        return RecencyProfile.ALL_OVER_1_MONTH
    if under >= over * 2 and under >= 2:
        return RecencyProfile.MOSTLY_UNDER_1_MONTH
    if over >= under * 2 and over >= 2:
        return RecencyProfile.MOSTLY_OVER_1_MONTH
    if under > 0 and over > 0:
        return RecencyProfile.MIXED
    return RecencyProfile.UNCERTAIN


def inspection_dict_to_lead_field_updates(inspection: dict[str, Any]) -> dict[str, Any]:
    """Map ``inspect_maps_place`` result into ``LeadRecord`` / form keys.

    Only includes keys when inference is confident enough; CRM may override.
    Spec v2: also emits per-review image flags and a mapped GBPCategory.
    """
    out: dict[str, Any] = {}
    if inspection.get("status") != "success":
        return out

    rp = inspection.get("inferred_recency_profile")
    if rp:
        out["recency_profile"] = rp

    rc = inspection.get("review_count_inferred")
    if isinstance(rc, int) and rc > 0:
        out["review_count"] = rc

    if inspection.get("any_review_has_images") is True:
        out["notes_images_observed"] = True

    cats = inspection.get("category_hints")
    if isinstance(cats, list) and cats:
        out["business_category"] = str(cats[0])
        mapped = map_text_to_gbp_category(str(cats[0]))
        if mapped:
            out["gbp_category"] = mapped

    # Per-review flags for the adaptive reasoning layer.
    reviews = inspection.get("reviews") or []
    if reviews:
        out["reviews_image_content"] = [bool(r.get("has_images")) for r in reviews]
        # Best-effort: relative_review_age_days exists in this module
        recent_flags: list[bool] = []
        for r in reviews:
            days = relative_review_age_days(r.get("published_at"))
            recent_flags.append(days is not None and days <= 31)
        out["reviews_under_one_month"] = recent_flags

    return out


# Spec v2 Section 3 — keyword → GBPCategory enum-value map. Free-text Google
# Business categories and business-name hints fall through this table.
_CATEGORY_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    # Medical & Healthcare
    (("plastic surgeon", "cosmetic surgeon"), "plastic_surgeon"),
    (("dentist", "dental", "orthodont", "endodont", "periodont", "smile "), "dentist"),
    (("medical clinic", "urgent care", "walk-in clinic"), "medical_clinic"),
    (("chiropractor", "chiropractic"), "chiropractor"),
    (("pharmacy", "drugstore"), "pharmacy"),
    # Professional & Financial
    (("law firm", "lawyer", "attorney", "legal services", "personal injury"), "law_firm"),
    (("accountant", "accounting", "cpa", "tax preparation"), "accounting_firm"),
    (("real estate", "realtor", "realty"), "real_estate_agency"),
    (("insurance",), "insurance_agency"),
    # Home & Field Services
    (("hvac", "heating", "air conditioning", "furnace"), "hvac_contractor"),
    (("roof", "roofer", "roofing"), "roofing_contractor"),
    (("electric", "electrician"), "electrician"),
    (("plumb",), "plumber"),
    (("moving", "movers"), "moving_company"),
    (("paving", "asphalt", "driveway"), "paving_contractor"),
    (("landscap", "lawn care", "lawn service"), "landscaper"),
    # Automotive
    (("car dealership", "auto dealer", "dealership"), "car_dealership"),
    (("auto repair", "mechanic", "car repair", "auto service"), "auto_repair"),
    (("auto detail", "car detail"), "auto_detailing"),
    (("car wash",), "car_wash"),
    # Beauty / Wellness / Fitness
    (("med spa", "medical spa"), "med_spa"),
    (("gym", "fitness", "crossfit"), "fitness_center"),
    (("nail salon", "nail bar"), "nail_salon"),
    (("hair salon", "barber", "beauty salon", "hair stylist"), "beauty_salon"),
    # Hospitality & Food
    (("hotel", "motel", "inn", "resort"), "hotel"),
    (("restaurant", "diner", "bistro", "eatery"), "restaurant"),
    (("coffee", "cafe", "espresso"), "coffee_shop"),
    (("bakery",), "bakery"),
    # Retail
    (("electronics store", "computer store"), "electronics_store"),
    (("furniture",), "furniture_store"),
    (("clothing store", "apparel", "boutique"), "clothing_store"),
    (("grocery", "supermarket"), "grocery_store"),
]


def map_text_to_gbp_category(text: str) -> Optional[str]:
    """Map a free-text category or business-name hint to a GBPCategory enum value.

    Returns the enum value (str) or None if nothing matches. The result can be
    fed directly into ``GBPCategory(...)`` in the commercial engine. Unmapped
    leads default to T3 via the engine's fallback.
    """
    if not text:
        return None
    n = text.lower()
    for keywords, cat_value in _CATEGORY_KEYWORD_MAP:
        for k in keywords:
            if k in n:
                return cat_value
    return None


def guess_category_from_business_name(name: str) -> Optional[str]:
    """Map a business name to a GBPCategory enum value, or None.

    Expanded from v7's 3 categories (dental/legal/contractor) to ~30 per spec v2.
    """
    return map_text_to_gbp_category(name)
