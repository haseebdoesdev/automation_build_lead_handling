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

    def has_gbp_link(self) -> bool:
        return bool(self.gbp_link and str(self.gbp_link).strip())

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
