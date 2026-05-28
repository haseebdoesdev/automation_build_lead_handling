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

    return out


def guess_category_from_business_name(name: str) -> Optional[str]:
    """Very light keyword hints for high-ticket / tier — not authoritative."""
    n = name.lower()
    if any(k in n for k in ("dental", "dentist", "orthodont", "smile ")):
        return "dental"
    if any(k in n for k in ("law", "legal", "attorney", "lawyer")):
        return "legal"
    if any(k in n for k in ("contractor", "roofing", "hvac", "plumb")):
        return "contractor"
    return None
