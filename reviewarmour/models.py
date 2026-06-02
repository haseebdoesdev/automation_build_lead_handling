from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Country(str, Enum):
    US = "US"
    CA = "CA"


class RecencyProfile(str, Enum):
    """How review ages cluster for the lead. Uncertain defaults to conservative (over-1-month tiers)."""

    ALL_UNDER_1_MONTH = "all_under_1_month"
    ALL_OVER_1_MONTH = "all_over_1_month"
    MOSTLY_UNDER_1_MONTH = "mostly_under_1_month"
    MOSTLY_OVER_1_MONTH = "mostly_over_1_month"
    MIXED = "mixed"  # Clear mix of under/over; not all one way
    UNCERTAIN = "uncertain"  # Maps to conservative over-1-month treatment for tier pick


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"


class CallOutcome(str, Enum):
    WON = "won"
    LOST_HARD = "lost_hard"
    UNDECIDED = "undecided"
    CALLBACK_REQUESTED = "callback_requested"
    NO_SHOW = "no_show"
    UNREACHABLE = "unreachable"


class LeadStatus(str, Enum):
    CAPTURED = "captured"
    DISPATCHED_TO_SALESMAN = "dispatched_to_salesman"
    AI_ENGAGED = "ai_engaged"
    AI_ESCALATED = "ai_escalated"
    QUOTE_ACCEPTED = "quote_accepted"
    STALLED_POST_QUOTE = "stalled_post_quote"
    BOOKED_CALL = "booked_call"
    QUEUED_FOR_MORNING = "queued_for_morning"
    MORNING_CALLED = "morning_called"
    WON = "won"
    LOST = "lost"
    UNREACHABLE = "unreachable"
    CUSTOMER_REVIEW_PENDING = "customer_review_pending"
    CUSTOMER_REVIEW_COMPLETE = "customer_review_complete"


class RouteDecision(str, Enum):
    BUSINESS_HOURS_SALESMAN = "business_hours_salesman"
    AFTER_HOURS_AI = "after_hours_ai"
    MORNING_QUEUE = "morning_queue"
    AI_ESCALATED_TO_HUMAN = "ai_escalated_to_human"


class PricingTier(str, Enum):
    """Pricing tier for the industry-based matrix (spec v2 Section 1)."""

    T1 = "T1"  # Premium ($450-$550 range, $400 floor)
    T2 = "T2"  # Upper-Mid ($380-$480 range, $350 floor)
    T3 = "T3"  # Standard ($280-$380 range, $260 floor)
    T4 = "T4"  # Lower ($200-$280 range, $200 floor)


class GBPCategory(str, Enum):
    """Google Business Profile categories mapped to pricing tiers (spec v2 Section 3).

    OTHER is used when the lead's category is unknown or unmapped; it defaults to T3.
    """

    # Medical & Healthcare (T1 except Pharmacy=T2)
    PLASTIC_SURGEON = "plastic_surgeon"
    DENTIST = "dentist"
    MEDICAL_CLINIC = "medical_clinic"
    CHIROPRACTOR = "chiropractor"
    PHARMACY = "pharmacy"
    # Professional & Financial (T1/T2)
    LAW_FIRM = "law_firm"
    ACCOUNTING_FIRM = "accounting_firm"
    REAL_ESTATE_AGENCY = "real_estate_agency"
    INSURANCE_AGENCY = "insurance_agency"
    # Home & Field Services (T2/T3)
    HVAC_CONTRACTOR = "hvac_contractor"
    ROOFING_CONTRACTOR = "roofing_contractor"
    ELECTRICIAN = "electrician"
    PLUMBER = "plumber"
    MOVING_COMPANY = "moving_company"
    PAVING_CONTRACTOR = "paving_contractor"
    LANDSCAPER = "landscaper"
    # Automotive (T3/T4)
    CAR_DEALERSHIP = "car_dealership"
    AUTO_REPAIR = "auto_repair"
    AUTO_DETAILING = "auto_detailing"
    CAR_WASH = "car_wash"
    # Beauty, Wellness, Fitness (T2/T3/T4)
    MED_SPA = "med_spa"
    FITNESS_CENTER = "fitness_center"
    BEAUTY_SALON = "beauty_salon"
    NAIL_SALON = "nail_salon"
    # Hospitality & Food (T3/T4)
    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    COFFEE_SHOP = "coffee_shop"
    BAKERY = "bakery"
    # Retail (T3/T4)
    ELECTRONICS_STORE = "electronics_store"
    FURNITURE_STORE = "furniture_store"
    CLOTHING_STORE = "clothing_store"
    GROCERY_STORE = "grocery_store"
    # Fallback
    OTHER = "other"


class VolumeBracket(str, Enum):
    """Review-count brackets that drive volume discounting (spec v2 Section 2)."""

    SMALL = "1-5"
    MEDIUM = "6-15"
    LARGE = "16-30"
    BULK = "30+"


class LeadTone(str, Enum):
    """Adaptive reasoning tone signal from the transcript (spec v2 Section 6)."""

    COOPERATIVE = "cooperative"
    PRICE_SENSITIVE = "price_sensitive"
    URGENT = "urgent"
    NONCOMMITTAL = "noncommittal"


class EngagementLevel(str, Enum):
    """Adaptive reasoning engagement signal (spec v2 Section 6)."""

    HIGH = "high"  # detailed questions, fast replies, motivated
    MEDIUM = "medium"  # responsive but not deeply engaged
    LOW = "low"  # slow / noncommittal


def volume_bracket_from_count(review_count: int) -> VolumeBracket:
    """Map a raw review count to a volume bracket."""
    if review_count <= 5:
        return VolumeBracket.SMALL
    if review_count <= 15:
        return VolumeBracket.MEDIUM
    if review_count <= 30:
        return VolumeBracket.LARGE
    return VolumeBracket.BULK


@dataclass
class NegotiationTriggerLogEntry:
    step_after: int  # 1 or 2 (step index after this pushback)
    lead_message_exact: str
    at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_after": self.step_after,
            "lead_message_exact": self.lead_message_exact,
            "timestamp": self.at.isoformat(),
        }


@dataclass
class LeadRecord:
    """Inbound lead / CRM snapshot used across modules.

    Typical **form submit** gives: full name (split into first/last by CRM), business name,
    email, phone, ``country`` (US or CA — drives footer and pricing matrix), lead source,
    submission time (store outside this record). Optionally: approximate review count,
    urgency, free-text notes — map notes into fields your pipeline supports.

    Often **unknown until conversation or GBP review**: ``recency_profile`` (use
    ``UNCERTAIN`` until known — commercial tier picks conservatively), granular review count,
    ``business_category`` / high-ticket vertical unless inferred from business name,
    which specific reviews matter, image vs non-image. The conversation layer should ask for
    these; CRM updates ``LeadRecord`` as facts arrive.
    """

    lead_id: str
    first_name: str
    last_name: str
    business_name: str
    country: Country
    phone: str
    email: str
    gbp_link: Optional[str]
    review_count: int
    recency_profile: RecencyProfile
    business_category: str
    is_price_sensitive_bulk: bool = False
    negotiation_step: int = 0
    negotiation_triggers: list[NegotiationTriggerLogEntry] = field(default_factory=list)
    ai_quote_allowed: bool = True
    soft_quote_mode: bool = False
    lead_source: str = ""
    urgency_flag: Optional[str] = None
    # Spec v2: industry-based pricing fields
    gbp_category: Optional[GBPCategory] = None
    reviews_image_content: list[bool] = field(default_factory=list)
    reviews_under_one_month: list[bool] = field(default_factory=list)
    lead_tone: Optional[LeadTone] = None
    engagement_level: Optional[EngagementLevel] = None

    def has_gbp_link(self) -> bool:
        return bool(self.gbp_link and str(self.gbp_link).strip())

    def volume_bracket(self) -> VolumeBracket:
        return volume_bracket_from_count(self.review_count)

    def all_reviews_image_or_recent(self) -> bool:
        """T1 exception (spec v2 Section 4): true if every concerning review is
        either an image review or under 1 month old. Used for the $450 written-quote
        exception when review_count <= 2.
        """
        if not self.reviews_image_content and not self.reviews_under_one_month:
            return False
        n = max(len(self.reviews_image_content), len(self.reviews_under_one_month))
        for i in range(n):
            is_image = (
                self.reviews_image_content[i]
                if i < len(self.reviews_image_content)
                else False
            )
            is_recent = (
                self.reviews_under_one_month[i]
                if i < len(self.reviews_under_one_month)
                else False
            )
            if not (is_image or is_recent):
                return False
        return True

@dataclass(frozen=True)
class ScheduledPostCallTouch:
    """One scheduled post-call follow-up touch."""

    index: int
    fire_at_utc: datetime
    channels: list[Channel]
    subject: Optional[str]
    body: str
    sms_body: Optional[str] = None
    state_updates: dict[str, Any] = field(default_factory=dict)
    raw_fire_at_utc: Optional[datetime] = None


@dataclass
class CommercialTurnMarker:
    """Attached when an outbound message was a commercial turn (for stall detection)."""

    sent_at: datetime
    last_quote_usd_per_review: Optional[int]
    negotiation_step: int


@dataclass
class SelfCorrectionAttemptLog:
    attempt: int
    verdict: str
    failed_checks: list[str]
    at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "verdict": self.verdict,
            "failed_checks": list(self.failed_checks),
            "timestamp": self.at.isoformat(),
        }
