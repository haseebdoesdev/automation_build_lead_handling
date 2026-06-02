"""
Industry-based commercial reasoning engine (spec v2 Section 9 replacement).

The v7 country-based US-1..US-6 / CA-1..CA-6 matrix is replaced by an industry-based
tier system. ~30 GBP categories map to 4 tiers (T1 Premium / T2 Upper-Mid / T3 Standard
/ T4 Lower) with per-volume-bracket ranges and absolute floors.

This module deterministically:
  - picks the tier band from gbp_category + volume_bracket
  - validates an adaptive price (chosen by the LLM selector in conversation.py)
    against the band range and floor
  - applies the phone-call threshold ($400 / per-review, with one T1 image-recent
    exception up to $450)
  - logs negotiation triggers

The LLM-driven adaptive price selection itself lives in conversation.py. This
module is the single source of truth for "is this price authorized" and "should
we route to a phone call."
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

from reviewarmour.models import (
    CommercialTurnMarker,
    Country,
    EngagementLevel,
    GBPCategory,
    LeadRecord,
    LeadTone,
    NegotiationTriggerLogEntry,
    PricingTier,
    RecencyProfile,
    VolumeBracket,
    volume_bracket_from_count,
)

# Phone-call threshold (spec v2 Section 4). Quotes above this are routed to phone,
# except the T1 exception (≤2 reviews, all image-or-recent) which extends to $450.
PHONE_CALL_THRESHOLD_USD: int = 400
T1_WRITTEN_EXCEPTION_CEILING_USD: int = 450

# Negotiation discount ladder. Step 0 = full adaptive price; step 1 ≈ 12.5% off;
# step 2 ≈ 12.5% off step 1 (≈23.4% off full). Always clamped to floor.
NEGOTIATION_STEP_MULTIPLIERS: tuple[float, ...] = (1.0, 0.875, 0.765625)


# ---------------------------------------------------------------------------
# Tier matrix (spec v2 Section 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolumeBand:
    """One row of the tier matrix: a volume bracket and its per-review range."""

    bracket: VolumeBracket
    low_usd: int
    high_usd: int


@dataclass(frozen=True)
class TierConfig:
    tier: PricingTier
    floor_usd: int
    bands: dict[VolumeBracket, VolumeBand]


def _bands(small: tuple[int, int], medium: tuple[int, int], large: tuple[int, int], bulk: tuple[int, int]) -> dict[VolumeBracket, VolumeBand]:
    return {
        VolumeBracket.SMALL: VolumeBand(VolumeBracket.SMALL, small[0], small[1]),
        VolumeBracket.MEDIUM: VolumeBand(VolumeBracket.MEDIUM, medium[0], medium[1]),
        VolumeBracket.LARGE: VolumeBand(VolumeBracket.LARGE, large[0], large[1]),
        VolumeBracket.BULK: VolumeBand(VolumeBracket.BULK, bulk[0], bulk[1]),
    }


# Full matrix from spec v2 Section 3. Floors come from spec v2 Section 1.
TIER_MATRIX: dict[GBPCategory, TierConfig] = {
    # ---- Medical & Healthcare ----
    GBPCategory.PLASTIC_SURGEON: TierConfig(
        PricingTier.T1, 400,
        _bands((520, 550), (470, 495), (415, 440), (385, 410)),
    ),
    GBPCategory.DENTIST: TierConfig(
        PricingTier.T1, 400,
        _bands((480, 530), (430, 475), (385, 425), (360, 400)),
    ),
    GBPCategory.MEDICAL_CLINIC: TierConfig(
        PricingTier.T1, 400,
        _bands((470, 520), (420, 465), (375, 415), (350, 390)),
    ),
    GBPCategory.CHIROPRACTOR: TierConfig(
        PricingTier.T1, 400,
        _bands((450, 490), (405, 440), (360, 390), (340, 365)),
    ),
    GBPCategory.PHARMACY: TierConfig(
        PricingTier.T2, 350,
        _bands((380, 420), (340, 380), (305, 335), (280, 315)),
    ),
    # ---- Professional & Financial ----
    GBPCategory.LAW_FIRM: TierConfig(
        PricingTier.T1, 400,
        _bands((500, 550), (450, 495), (400, 440), (380, 415)),
    ),
    GBPCategory.ACCOUNTING_FIRM: TierConfig(
        PricingTier.T1, 400,
        _bands((460, 510), (415, 460), (370, 410), (345, 385)),
    ),
    GBPCategory.REAL_ESTATE_AGENCY: TierConfig(
        PricingTier.T2, 350,
        _bands((420, 480), (380, 430), (335, 385), (310, 360)),
    ),
    GBPCategory.INSURANCE_AGENCY: TierConfig(
        PricingTier.T2, 350,
        _bands((400, 450), (360, 405), (320, 360), (295, 335)),
    ),
    # ---- Home & Field Services ----
    GBPCategory.HVAC_CONTRACTOR: TierConfig(
        PricingTier.T2, 350,
        _bands((400, 450), (360, 405), (320, 360), (295, 335)),
    ),
    GBPCategory.ROOFING_CONTRACTOR: TierConfig(
        PricingTier.T2, 350,
        _bands((390, 440), (350, 395), (310, 350), (285, 330)),
    ),
    GBPCategory.ELECTRICIAN: TierConfig(
        PricingTier.T3, 260,
        _bands((340, 380), (305, 340), (270, 305), (250, 285)),
    ),
    GBPCategory.PLUMBER: TierConfig(
        PricingTier.T3, 260,
        _bands((330, 370), (295, 335), (265, 295), (245, 275)),
    ),
    GBPCategory.MOVING_COMPANY: TierConfig(
        PricingTier.T3, 260,
        _bands((310, 360), (280, 325), (250, 290), (230, 270)),
    ),
    GBPCategory.PAVING_CONTRACTOR: TierConfig(
        PricingTier.T3, 260,
        _bands((300, 350), (270, 315), (240, 280), (225, 260)),
    ),
    GBPCategory.LANDSCAPER: TierConfig(
        PricingTier.T3, 260,
        _bands((290, 340), (260, 305), (230, 270), (215, 255)),
    ),
    # ---- Automotive ----
    GBPCategory.CAR_DEALERSHIP: TierConfig(
        PricingTier.T3, 260,
        _bands((330, 380), (295, 340), (265, 305), (245, 285)),
    ),
    GBPCategory.AUTO_REPAIR: TierConfig(
        PricingTier.T4, 200,
        _bands((240, 280), (215, 250), (190, 225), (200, 200)),
    ),
    GBPCategory.AUTO_DETAILING: TierConfig(
        PricingTier.T4, 200,
        _bands((220, 260), (200, 235), (200, 200), (200, 200)),
    ),
    GBPCategory.CAR_WASH: TierConfig(
        PricingTier.T4, 200,
        _bands((200, 240), (200, 215), (200, 200), (200, 200)),
    ),
    # ---- Beauty, Wellness & Fitness ----
    GBPCategory.MED_SPA: TierConfig(
        PricingTier.T2, 350,
        _bands((400, 460), (360, 415), (320, 370), (295, 345)),
    ),
    GBPCategory.FITNESS_CENTER: TierConfig(
        PricingTier.T3, 260,
        _bands((300, 350), (270, 315), (240, 280), (225, 260)),
    ),
    GBPCategory.BEAUTY_SALON: TierConfig(
        PricingTier.T4, 200,
        _bands((240, 280), (215, 250), (195, 225), (200, 200)),
    ),
    GBPCategory.NAIL_SALON: TierConfig(
        PricingTier.T4, 200,
        _bands((210, 250), (200, 225), (200, 200), (200, 200)),
    ),
    # ---- Hospitality & Food ----
    GBPCategory.HOTEL: TierConfig(
        PricingTier.T3, 260,
        _bands((320, 370), (290, 335), (255, 295), (240, 275)),
    ),
    GBPCategory.RESTAURANT: TierConfig(
        PricingTier.T3, 260,
        _bands((270, 320), (245, 290), (215, 255), (200, 240)),
    ),
    GBPCategory.COFFEE_SHOP: TierConfig(
        PricingTier.T4, 200,
        _bands((220, 260), (200, 235), (200, 200), (200, 200)),
    ),
    GBPCategory.BAKERY: TierConfig(
        PricingTier.T4, 200,
        _bands((200, 240), (200, 215), (200, 200), (200, 200)),
    ),
    # ---- Retail ----
    GBPCategory.ELECTRONICS_STORE: TierConfig(
        PricingTier.T3, 260,
        _bands((260, 310), (235, 280), (210, 250), (200, 230)),
    ),
    GBPCategory.FURNITURE_STORE: TierConfig(
        PricingTier.T3, 260,
        _bands((250, 300), (225, 270), (200, 240), (200, 225)),
    ),
    GBPCategory.CLOTHING_STORE: TierConfig(
        PricingTier.T4, 200,
        _bands((220, 260), (200, 235), (200, 200), (200, 200)),
    ),
    GBPCategory.GROCERY_STORE: TierConfig(
        PricingTier.T4, 200,
        _bands((200, 240), (200, 215), (200, 200), (200, 200)),
    ),
}


# Default fallback when category is unknown / unmapped: T3 Standard middle.
_DEFAULT_FALLBACK = TierConfig(
    PricingTier.T3, 260,
    _bands((280, 380), (252, 342), (224, 304), (200, 285)),
)


def get_tier_config(category: Optional[GBPCategory]) -> TierConfig:
    """Return the tier config for a GBP category, or the T3 fallback if unmapped."""
    if category is None or category == GBPCategory.OTHER:
        return _DEFAULT_FALLBACK
    return TIER_MATRIX.get(category, _DEFAULT_FALLBACK)


def get_volume_band(category: Optional[GBPCategory], review_count: int) -> tuple[TierConfig, VolumeBand]:
    """Return (tier_config, volume_band) for a lead."""
    config = get_tier_config(category)
    bracket = volume_bracket_from_count(review_count)
    return config, config.bands[bracket]


# ---------------------------------------------------------------------------
# Recency bucketing (used to feed the adaptive selector — unchanged from v7)
# ---------------------------------------------------------------------------


def recency_bucket(recency: RecencyProfile) -> str:
    """Conservative: uncertain or any 'over' majority → over. Mixed → over."""
    if recency in (
        RecencyProfile.UNCERTAIN,
        RecencyProfile.ALL_OVER_1_MONTH,
        RecencyProfile.MOSTLY_OVER_1_MONTH,
    ):
        return "over"
    if recency in (RecencyProfile.ALL_UNDER_1_MONTH, RecencyProfile.MOSTLY_UNDER_1_MONTH):
        return "under"
    return "over"  # MIXED conservative


# ---------------------------------------------------------------------------
# Phone-call threshold (spec v2 Section 4)
# ---------------------------------------------------------------------------


def phone_call_threshold_applies(
    selected_price_usd: int,
    *,
    tier: PricingTier,
    review_count: int,
    all_reviews_image_or_recent: bool,
) -> bool:
    """Return True if this price must be routed to a phone call.

    Exception (spec v2 Section 4): T1, review_count ≤ 2, every review is either
    an image review or under 1 month old, and the price ≤ $450 — quote in writing.
    """
    if selected_price_usd <= PHONE_CALL_THRESHOLD_USD:
        return False

    is_t1_exception = (
        tier == PricingTier.T1
        and review_count <= 2
        and all_reviews_image_or_recent
        and selected_price_usd <= T1_WRITTEN_EXCEPTION_CEILING_USD
    )
    return not is_t1_exception


# ---------------------------------------------------------------------------
# Negotiation step → discounted price
# ---------------------------------------------------------------------------


def apply_negotiation_step(opening_price_usd: int, step: int, floor_usd: int) -> int:
    """Apply the negotiation step multiplier to the opening adaptive price.

    Step 0 = full price. Step 1 ≈ 12.5% off. Step 2 ≈ 12.5% off step 1.
    Always clamped to the tier floor.
    """
    if step < 0:
        step = 0
    if step >= len(NEGOTIATION_STEP_MULTIPLIERS):
        step = len(NEGOTIATION_STEP_MULTIPLIERS) - 1
    raw = round(opening_price_usd * NEGOTIATION_STEP_MULTIPLIERS[step])
    return max(raw, floor_usd)


# ---------------------------------------------------------------------------
# CommercialResult — what the engine returns to the conversation pipeline
# ---------------------------------------------------------------------------


@dataclass
class CommercialResult:
    """Output from commercial reasoning — single source of truth for authorized numbers."""

    tier: PricingTier
    tier_id: str  # legacy convenience = tier.value
    gbp_category: Optional[GBPCategory]
    volume_bracket: VolumeBracket
    range_low_usd: int
    range_high_usd: int
    floor_usd: int
    negotiation_step: int
    authorized_quote_usd_per_review: Optional[int]
    can_quote: bool
    request_gbp_first: bool
    request_category_first: bool
    escalate: bool
    escalation_reason: Optional[str]
    negotiation_triggers: list[dict]
    commercial_turn: Optional[CommercialTurnMarker] = None
    # Soft-quote mode (unchanged from v7 — uses the band as the range)
    soft_quote_mode: bool = False
    soft_quote_range: Optional[tuple[int, int]] = None
    # Spec v2: phone-call threshold + adaptive reasoning context
    phone_call_threshold_triggered: bool = False
    salesman_recommended_range: Optional[tuple[int, int]] = None
    salesman_recommended_opening_usd: Optional[int] = None
    reasoning_summary: str = ""
    adaptive_inputs: dict = field(default_factory=dict)

    def to_prompt_dict(self) -> dict:
        """Safe for the conversation model: no hidden cost internals."""
        d: dict = {
            "tier": self.tier.value,
            "tier_id": self.tier_id,
            "gbp_category": self.gbp_category.value if self.gbp_category else None,
            "volume_bracket": self.volume_bracket.value,
            "range_low": self.range_low_usd,
            "range_high": self.range_high_usd,
            "negotiation_step": self.negotiation_step,
            "authorized_quote_usd_per_review": self.authorized_quote_usd_per_review,
            "can_quote": self.can_quote,
            "request_gbp_first": self.request_gbp_first,
            "request_category_first": self.request_category_first,
            "escalate": self.escalate,
            "escalation_reason": self.escalation_reason,
            "phone_call_threshold_triggered": self.phone_call_threshold_triggered,
        }
        if self.soft_quote_mode and self.soft_quote_range:
            d["soft_quote_range"] = {
                "low": self.soft_quote_range[0],
                "high": self.soft_quote_range[1],
            }
        if self.phone_call_threshold_triggered and self.salesman_recommended_range:
            d["salesman_recommended_range"] = {
                "low": self.salesman_recommended_range[0],
                "high": self.salesman_recommended_range[1],
            }
        if self.reasoning_summary:
            d["reasoning_summary"] = self.reasoning_summary
        return d


# ---------------------------------------------------------------------------
# CommercialEngine
# ---------------------------------------------------------------------------


class CommercialEngine:
    """Deterministic pricing validator + phone-call threshold gate.

    Unlike v7 where the engine picked the price from a fixed table, in v2 the LLM
    adaptive selector chooses a price within the tier band's range, and this engine:
      - confirms the price is in [range_low, range_high] and >= floor
      - applies the negotiation step discount
      - decides whether to route to a phone call (above $400 unless T1 exception)
      - returns a CommercialResult the conversation prompt can safely consume.

    Callers that don't yet have an adaptive price can pass ``adaptive_price_usd=None``
    and the engine will mid-point the band as a deterministic fallback (used in
    tests and offline calculation).
    """

    def evaluate_pricing(
        self,
        lead: LeadRecord,
        *,
        wants_price: bool,
        adaptive_price_usd: Optional[int] = None,
        reasoning_summary: str = "",
        adaptive_inputs: Optional[dict] = None,
        lead_requested_price_below_floor: bool = False,
        now: Optional[datetime] = None,
    ) -> CommercialResult:
        now = now or datetime.now(timezone.utc)
        triggers = [t.to_dict() for t in lead.negotiation_triggers]
        adaptive_inputs = adaptive_inputs or {}

        # 0. ai_quote_allowed kill switch.
        if not lead.ai_quote_allowed:
            return _escalate_result(
                lead=lead,
                triggers=triggers,
                reason="ai_quote_allowed is false",
                adaptive_inputs=adaptive_inputs,
            )

        # 1. Confirmed GBP category required for any pricing.
        if lead.gbp_category is None:
            # Need to ask before quoting.
            config = _DEFAULT_FALLBACK
            band = config.bands[lead.volume_bracket()]
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=None,
                volume_bracket=lead.volume_bracket(),
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=not lead.has_gbp_link(),
                request_category_first=True,
                escalate=False,
                escalation_reason=None,
                negotiation_triggers=triggers,
                adaptive_inputs=adaptive_inputs,
            )

        config, band = get_volume_band(lead.gbp_category, lead.review_count)

        # 2. Soft-quote mode (spec v7 Section 17 — preserved; uses band as range).
        if lead.soft_quote_mode and wants_price:
            if not lead.has_gbp_link():
                return _gbp_request_result(
                    lead, config, band, triggers, adaptive_inputs, soft=True
                )
            if lead_requested_price_below_floor or lead.negotiation_step > 0:
                return CommercialResult(
                    tier=config.tier,
                    tier_id=config.tier.value,
                    gbp_category=lead.gbp_category,
                    volume_bracket=band.bracket,
                    range_low_usd=band.low_usd,
                    range_high_usd=band.high_usd,
                    floor_usd=config.floor_usd,
                    negotiation_step=lead.negotiation_step,
                    authorized_quote_usd_per_review=None,
                    can_quote=False,
                    request_gbp_first=False,
                    request_category_first=False,
                    escalate=True,
                    escalation_reason="Soft-quote mode: pushback escalates to salesman",
                    negotiation_triggers=triggers,
                    soft_quote_mode=True,
                    adaptive_inputs=adaptive_inputs,
                )
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=0,
                authorized_quote_usd_per_review=band.high_usd,
                can_quote=True,
                request_gbp_first=False,
                request_category_first=False,
                escalate=False,
                escalation_reason=None,
                negotiation_triggers=triggers,
                commercial_turn=CommercialTurnMarker(
                    sent_at=now,
                    last_quote_usd_per_review=band.high_usd,
                    negotiation_step=0,
                ),
                soft_quote_mode=True,
                soft_quote_range=(band.low_usd, band.high_usd),
                adaptive_inputs=adaptive_inputs,
            )

        # 3. Lead pushing below floor → escalate.
        if lead_requested_price_below_floor:
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                request_category_first=False,
                escalate=True,
                escalation_reason="Lead pushing below floor",
                negotiation_triggers=triggers,
                adaptive_inputs=adaptive_inputs,
            )

        # 4. wants_price=True without GBP link → ask.
        if wants_price and not lead.has_gbp_link():
            return _gbp_request_result(lead, config, band, triggers, adaptive_inputs)

        # 5. Past negotiation step 2 → escalate.
        if lead.negotiation_step > 2:
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                request_category_first=False,
                escalate=True,
                escalation_reason="Negotiation past step 2",
                negotiation_triggers=triggers,
                adaptive_inputs=adaptive_inputs,
            )

        # 6. wants_price=False → return context without a quote (no commercial turn).
        if not wants_price:
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                request_category_first=False,
                escalate=False,
                escalation_reason=None,
                negotiation_triggers=triggers,
                adaptive_inputs=adaptive_inputs,
            )

        # 7. Adaptive price selected by LLM (or band midpoint if None).
        if adaptive_price_usd is None:
            adaptive_price_usd = (band.low_usd + band.high_usd) // 2
            reasoning_summary = reasoning_summary or "Band midpoint (no adaptive input)"

        # 8. Validate adaptive price is in band — with a documented T1 exception
        # for the written-quote-under-$450 case (spec v2 Section 4 exception).
        in_band = band.low_usd <= adaptive_price_usd <= band.high_usd
        t1_written_exception_ok = (
            config.tier == PricingTier.T1
            and lead.review_count <= 2
            and lead.all_reviews_image_or_recent()
            and config.floor_usd <= adaptive_price_usd <= T1_WRITTEN_EXCEPTION_CEILING_USD
        )

        if not in_band and not t1_written_exception_ok:
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=lead.negotiation_step,
                authorized_quote_usd_per_review=None,
                can_quote=False,
                request_gbp_first=False,
                request_category_first=False,
                escalate=True,
                escalation_reason=(
                    f"Adaptive price ${adaptive_price_usd} outside band "
                    f"${band.low_usd}-${band.high_usd}"
                ),
                negotiation_triggers=triggers,
                reasoning_summary=reasoning_summary,
                adaptive_inputs=adaptive_inputs,
            )

        # 9. Apply negotiation step ladder, clamp to floor.
        step = lead.negotiation_step
        discounted_price = apply_negotiation_step(adaptive_price_usd, step, config.floor_usd)

        # 10. Phone-call threshold gate.
        threshold_triggered = phone_call_threshold_applies(
            discounted_price,
            tier=config.tier,
            review_count=lead.review_count,
            all_reviews_image_or_recent=lead.all_reviews_image_or_recent(),
        )

        if threshold_triggered:
            return CommercialResult(
                tier=config.tier,
                tier_id=config.tier.value,
                gbp_category=lead.gbp_category,
                volume_bracket=band.bracket,
                range_low_usd=band.low_usd,
                range_high_usd=band.high_usd,
                floor_usd=config.floor_usd,
                negotiation_step=step,
                authorized_quote_usd_per_review=None,  # never quoted in writing
                can_quote=False,
                request_gbp_first=False,
                request_category_first=False,
                escalate=False,
                escalation_reason=None,
                negotiation_triggers=triggers,
                phone_call_threshold_triggered=True,
                salesman_recommended_range=(band.low_usd, band.high_usd),
                salesman_recommended_opening_usd=discounted_price,
                reasoning_summary=reasoning_summary,
                adaptive_inputs=adaptive_inputs,
            )

        # 11. Standard written quote.
        return CommercialResult(
            tier=config.tier,
            tier_id=config.tier.value,
            gbp_category=lead.gbp_category,
            volume_bracket=band.bracket,
            range_low_usd=band.low_usd,
            range_high_usd=band.high_usd,
            floor_usd=config.floor_usd,
            negotiation_step=step,
            authorized_quote_usd_per_review=discounted_price,
            can_quote=True,
            request_gbp_first=False,
            request_category_first=False,
            escalate=False,
            escalation_reason=None,
            negotiation_triggers=triggers,
            commercial_turn=CommercialTurnMarker(
                sent_at=now,
                last_quote_usd_per_review=discounted_price,
                negotiation_step=step,
            ),
            reasoning_summary=reasoning_summary,
            adaptive_inputs=adaptive_inputs,
        )


# ---------------------------------------------------------------------------
# Internal result builders
# ---------------------------------------------------------------------------


def _escalate_result(
    *,
    lead: LeadRecord,
    triggers: list[dict],
    reason: str,
    adaptive_inputs: dict,
) -> CommercialResult:
    return CommercialResult(
        tier=PricingTier.T3,
        tier_id=PricingTier.T3.value,
        gbp_category=lead.gbp_category,
        volume_bracket=lead.volume_bracket(),
        range_low_usd=0,
        range_high_usd=0,
        floor_usd=0,
        negotiation_step=lead.negotiation_step,
        authorized_quote_usd_per_review=None,
        can_quote=False,
        request_gbp_first=False,
        request_category_first=False,
        escalate=True,
        escalation_reason=reason,
        negotiation_triggers=triggers,
        adaptive_inputs=adaptive_inputs,
    )


def _gbp_request_result(
    lead: LeadRecord,
    config: TierConfig,
    band: VolumeBand,
    triggers: list[dict],
    adaptive_inputs: dict,
    *,
    soft: bool = False,
) -> CommercialResult:
    return CommercialResult(
        tier=config.tier,
        tier_id=config.tier.value,
        gbp_category=lead.gbp_category,
        volume_bracket=band.bracket,
        range_low_usd=band.low_usd,
        range_high_usd=band.high_usd,
        floor_usd=config.floor_usd,
        negotiation_step=lead.negotiation_step,
        authorized_quote_usd_per_review=None,
        can_quote=False,
        request_gbp_first=True,
        request_category_first=False,
        escalate=False,
        escalation_reason=None,
        negotiation_triggers=triggers,
        soft_quote_mode=soft,
        adaptive_inputs=adaptive_inputs,
    )


# ---------------------------------------------------------------------------
# Negotiation state machine (unchanged from v7 — already correct after > 2 fix)
# ---------------------------------------------------------------------------


def pushback_already_recorded(lead: LeadRecord, trigger_message: str) -> bool:
    """True when *trigger_message* was already logged as the latest pushback."""
    if not lead.negotiation_triggers:
        return False
    last = lead.negotiation_triggers[-1]
    return last.lead_message_exact.strip() == (trigger_message or "").strip()


def apply_pushback(lead: LeadRecord, trigger_message: str, *, now: Optional[datetime] = None) -> LeadRecord:
    """Return a new lead with negotiation step +1 and the trigger appended to the log."""
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


def record_negotiation_pushback(
    lead: LeadRecord,
    trigger_message: str,
    *,
    now: Optional[datetime] = None,
    max_step: int = 2,
) -> bool:
    """Record one pushback in place. Returns True if step was incremented.

    Idempotent on identical messages; tolerant of externally-advanced steps.
    """
    if pushback_already_recorded(lead, trigger_message):
        return False
    if lead.negotiation_step >= max_step:
        return False

    now = now or datetime.now(timezone.utc)
    if lead.negotiation_step > len(lead.negotiation_triggers):
        entry = NegotiationTriggerLogEntry(
            step_after=lead.negotiation_step,
            lead_message_exact=trigger_message,
            at=now,
        )
        lead.negotiation_triggers = [*lead.negotiation_triggers, entry]
        return False

    updated = apply_pushback(lead, trigger_message, now=now)
    lead.negotiation_step = min(updated.negotiation_step, max_step)
    lead.negotiation_triggers = updated.negotiation_triggers
    return True
