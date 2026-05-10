from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal, Optional

from reviewarmour.models import (
    CommercialTurnMarker,
    Country,
    LeadRecord,
    NegotiationTriggerLogEntry,
    RecencyProfile,
)

# Internal margin economics — never exposed in customer-facing prompts or copy.
_EFFECTIVE_COST_UNDER_1_MONTH_USD = 94
_EFFECTIVE_COST_OVER_1_MONTH_USD = 214
_MARGIN_FLOOR_RATIO = 0.20

HIGH_TICKET_CATEGORIES = frozenset(
    {
        "contractor",
        "dental",
        "legal",
        "premium auto",
        "law",
        "lawyer",
        "attorney",
        "dentist",
    }
)


def _normalize_category(cat: str) -> str:
    return " ".join(cat.strip().lower().split())


def _is_high_ticket(business_category: str) -> bool:
    n = _normalize_category(business_category)
    if n in HIGH_TICKET_CATEGORIES:
        return True
    for token in HIGH_TICKET_CATEGORIES:
        if token in n:
            return True
    return False


def _tier_recency_bucket_for_matrix(
    recency: RecencyProfile,
) -> Literal["under", "over"]:
    """Conservative: uncertain or any 'over' majority → over bucket."""
    if recency in (RecencyProfile.UNCERTAIN, RecencyProfile.ALL_OVER_1_MONTH, RecencyProfile.MOSTLY_OVER_1_MONTH):
        return "over"
    if recency in (RecencyProfile.ALL_UNDER_1_MONTH, RecencyProfile.MOSTLY_UNDER_1_MONTH):
        return "under"
    # True mix without majority: conservative
    return "over"


@dataclass(frozen=True)
class TierBand:
    tier_id: str
    opening: int
    neg_1: int
    neg_2: int
    floor: int


def _pick_tier(lead: LeadRecord) -> TierBand:
    country = lead.country
    n = lead.review_count
    recency = lead.recency_profile
    price_sensitive = lead.is_price_sensitive_bulk

    bulk_tier = (
        TierBand("US-6", 400, 375, 325, 250)
        if country == Country.US
        else TierBand("CA-6", 300, 275, 250, 200)
    )
    if n >= 5 and price_sensitive and recency == RecencyProfile.MIXED:
        return bulk_tier

    if n >= 3:
        bucket = _tier_recency_bucket_for_matrix(recency)
        if bucket == "under":
            return (
                TierBand("US-3", 425, 400, 375, 300)
                if country == Country.US
                else TierBand("CA-3", 325, 300, 275, 225)
            )
        return (
            TierBand("US-5", 400, 375, 350, 300)
            if country == Country.US
            else TierBand("CA-5", 300, 275, 250, 225)
        )

    # 1–2 reviews
    bucket = _tier_recency_bucket_for_matrix(recency)
    if n == 1 and bucket == "under" and _is_high_ticket(lead.business_category):
        return (
            TierBand("US-2", 500, 475, 450, 350)
            if country == Country.US
            else TierBand("CA-2", 400, 375, 325, 275)
        )

    if bucket == "under":
        return (
            TierBand("US-1", 450, 425, 400, 300)
            if country == Country.US
            else TierBand("CA-1", 375, 325, 275, 225)
        )

    return (
        TierBand("US-4", 425, 400, 375, 300)
        if country == Country.US
        else TierBand("CA-4", 325, 300, 275, 225)
    )


def _effective_cost_for_margin(lead: LeadRecord) -> int:
    bucket = _tier_recency_bucket_for_matrix(lead.recency_profile)
    if bucket == "under":
        return _EFFECTIVE_COST_UNDER_1_MONTH_USD
    return _EFFECTIVE_COST_OVER_1_MONTH_USD


def margin_ok(quote_usd: int, lead: LeadRecord) -> bool:
    if quote_usd <= 0:
        return False
    eff = _effective_cost_for_margin(lead)
    return (quote_usd - eff) / quote_usd >= _MARGIN_FLOOR_RATIO


def price_for_negotiation_step(band: TierBand, step: int) -> Optional[int]:
    if step <= 0:
        return band.opening
    if step == 1:
        return band.neg_1
    if step == 2:
        return band.neg_2
    return None


@dataclass
class CommercialResult:
    """Output from commercial reasoning — single source of truth for authorized numbers."""

    tier_id: str
    opening: int
    neg_1: int
    neg_2: int
    floor: int
    negotiation_step: int
    authorized_quote_usd_per_review: Optional[int]
    can_quote: bool
    request_gbp_first: bool
    escalate: bool
    escalation_reason: Optional[str]
    margin_passed: bool
    negotiation_triggers: list[dict]
    commercial_turn: Optional[CommercialTurnMarker] = None

    def to_prompt_dict(self) -> dict:
        """Safe for conversation model: no hidden cost internals."""
        return {
            "tier_id": self.tier_id,
            "opening": self.opening,
            "neg_1": self.neg_1,
            "neg_2": self.neg_2,
            "floor": self.floor,
            "negotiation_step": self.negotiation_step,
            "authorized_quote_usd_per_review": self.authorized_quote_usd_per_review,
            "can_quote": self.can_quote,
            "request_gbp_first": self.request_gbp_first,
            "escalate": self.escalate,
            "escalation_reason": self.escalation_reason,
        }


class CommercialEngine:
    """
    Deterministic pricing and negotiation state machine.
    No LLM. Caller merges negotiation_step / triggers back into LeadRecord between turns.
    """

    def evaluate_pricing(
        self,
        lead: LeadRecord,
        *,
        wants_price: bool,
        lead_requested_price_below_floor: bool = False,
        now: Optional[datetime] = None,
    ) -> CommercialResult:
        now = now or datetime.now(timezone.utc)
        triggers = [t.to_dict() for t in lead.negotiation_triggers]

        if not lead.ai_quote_allowed:
            return CommercialResult(
                tier_id="",
                opening=0,
                neg_1=0,
                neg_2=0,
                floor=0,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=True,
                escalation_reason="ai_quote_allowed is false",
                margin_passed=False,
                negotiation_triggers=triggers,
            )

        if lead_requested_price_below_floor:
            band = _pick_tier(lead)
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=True,
                escalation_reason="Lead pushing below floor",
                margin_passed=False,
                negotiation_triggers=triggers,
            )

        if wants_price and not lead.has_gbp_link():
            band = _pick_tier(lead)
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=True,
                escalate=False,
                escalation_reason=None,
                margin_passed=True,
                negotiation_triggers=triggers,
            )

        band = _pick_tier(lead)
        step = lead.negotiation_step
        if step > 2:
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=True,
                escalation_reason="Negotiation past step 2",
                margin_passed=True,
                negotiation_triggers=triggers,
            )

        if not wants_price:
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=False,
                escalation_reason=None,
                margin_passed=True,
                negotiation_triggers=triggers,
            )

        quote = price_for_negotiation_step(band, step)
        if quote is None:
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=True,
                escalation_reason="Invalid negotiation step",
                margin_passed=False,
                negotiation_triggers=triggers,
            )

        m_ok = margin_ok(quote, lead)
        if not m_ok:
            return CommercialResult(
                tier_id=band.tier_id,
                opening=band.opening,
                neg_1=band.neg_1,
                neg_2=band.neg_2,
                floor=band.floor,
                negotiation_step=step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                escalate=True,
                escalation_reason="Margin discipline: quote below 20 percent minimum margin",
                margin_passed=False,
                negotiation_triggers=triggers,
            )

        return CommercialResult(
            tier_id=band.tier_id,
            opening=band.opening,
            neg_1=band.neg_1,
            neg_2=band.neg_2,
            floor=band.floor,
            negotiation_step=step,
            authorized_quote_usd_per_review=quote,
            can_quote=wants_price,
            request_gbp_first=False,
            escalate=False,
            escalation_reason=None,
            margin_passed=True,
            negotiation_triggers=triggers,
            commercial_turn=CommercialTurnMarker(
                sent_at=now,
                last_quote_usd_per_review=quote if wants_price else None,
                negotiation_step=step,
            )
            if wants_price
            else None,
        )


def apply_pushback(lead: LeadRecord, trigger_message: str, *, now: Optional[datetime] = None) -> LeadRecord:
    """Increment negotiation step and append the lead's exact trigger message to the log."""
    now = now or datetime.now(timezone.utc)
    new_step = lead.negotiation_step + 1
    entry = NegotiationTriggerLogEntry(
        step_after=new_step,
        lead_message_exact=trigger_message,
        at=now,
    )
    return replace(
        lead,
        negotiation_step=new_step,
        negotiation_triggers=[*lead.negotiation_triggers, entry],
    )
