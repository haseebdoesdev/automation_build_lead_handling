"""Conversation module + outbound pipeline.

The conversation module asks Claude for a single outbound message. It never
invents prices: any pricing topic must come from the commercial reasoning
module's ``CommercialResult``. Every draft it produces is reviewed by the
self-correction module before being returned to the caller.

The pipeline is:

    [commercial reasoning if pricing involved]
        -> [conversation drafts]
        -> [self-correction reviews]
        -> [retry up to 2x if fix verdict]
        -> [return passed draft OR queue for human]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional

from reviewarmour.commercial import (
    CommercialEngine,
    CommercialResult,
    record_negotiation_pushback,
)
from reviewarmour.errors import ConfigError, LLMResponseError
from reviewarmour.models import (
    Channel,
    Country,
    LeadRecord,
    RecencyProfile,
    SelfCorrectionAttemptLog,
)
from reviewarmour.prompt_templates import (
    ADAPTIVE_PRICE_SELECTOR_SYSTEM,
    APPROVED_TIMELINE_PARAGRAPHS,
    COMMERCIAL_ENGINE_TURN_SYSTEM,
    CONVERSATION_SYSTEM,
    CUSTOMER_REVIEW_REQUEST_SYSTEM,
    POST_QUOTE_ACCEPTANCE_SYSTEM,
)
from reviewarmour.self_correction import (
    AnthropicMessagesClient,
    SelfCorrectionModule,
    SelfCorrectionVerdict,
    _call_claude_for_json,
    lead_demands_hard_calendar_date,
)
from reviewarmour.settings import FIRST_TOUCH_VARIATION, LLMRuntime

logger = logging.getLogger("reviewarmour.conversation")

# -----------------------------------------------------------------------------
# GBP URL extraction — pulls the first recognisable Maps / g.page URL from text.
# -----------------------------------------------------------------------------

_GBP_URL_RE = re.compile(
    r"https?://"
    r"(?:"
    r"(?:www\.)?google\.com/maps/[^\s\"<>)]*"
    r"|maps\.google\.com/[^\s\"<>)]*"
    r"|g\.page/[^\s\"<>)]*"
    r")",
    re.IGNORECASE,
)


def extract_gbp_url(text: str) -> Optional[str]:
    """Return the first Google Maps / g.page URL found in *text*, or None."""
    m = _GBP_URL_RE.search(text)
    return m.group(0) if m else None


# -----------------------------------------------------------------------------
# Hard escalation patterns (matched against the lead's inbound text).
# -----------------------------------------------------------------------------

LEGAL_ESCALATION = (
    "lawyer",
    "attorney",
    "lawsuit",
    "sue",
    "legal action",
    "defamation",
)
POST_PAY_ESCALATION = ("refund", "chargeback")
REGULATOR_ESCALATION = ("bbb", "better business", "ftc", "regulator", "complaint to google")

# Substrings matched against lowercased inbound text. Broad enough for natural
# pricing asks; triggers the commercial engine (not a human escalation).
PRICE_SHOPPING_ESCALATION_PHRASES = (
    "how much",
    "what is the price",
    "what's the price",
    "what would be the price",
    "what would be the cost",
    "what's the cost",
    "what is the cost",
    "send me a quote",
    "send a quote",
    "pricing",
    "the cost",
    "ballpark",
    "estimate",
    "cost",  # "what would it cost", "total cost" (after longer phrases above)
    "per review",
)

# After a quote exists in-thread, these indicate negotiation / price pushback — must re-run commercial.
_NEGOTIATION_PUSHBACK_PHRASES = (
    "lower",
    "lowering",
    "discount",
    "cheaper",
    "negotiate",
    "negotiation",
    "too expensive",
    "too much for",
    "price match",
    "match your",
    "match that",
    "budget",
    "flexibility",
    "flexible",
    "reduce the",
    "better price",
    "best price",
    "can you do",
    "could you do",
    "more low",
    "any room",
    "work with me",
    "meet me",
)

ACCEPTANCE_PHRASES = (
    "let's do it",
    "lets do it",
    "send the invoice",
    "im in",
    "i'm in",
    "go ahead",
    "lets go ahead",
    "let's go ahead",
    "sure this works",
    "sounds good",
    "works for me",
    "that works",
    "move forward",
    "book it",
)

# Single-token affirmations — only reliable when caller also verified a quote context.
_ACCEPT_ONE_WORD = frozenset({"yes", "yeah", "yep", "ok", "okay", "sure", "yup"})

_QUOTE_IN_BODY_RE = re.compile(
    r"\$\s*\d{2,6}\b|usd\s*per\s*review|per\s*review[^\n]{0,40}\$\s*\d",
    re.IGNORECASE,
)

SPECIFIC_PERSON_ESCALATION = ("speak to the owner", "speak to owner", "speak to the manager", "speak to manager")

# Talk/speak/chat "to <word>" where <word> is not a generic role — catches named contacts (e.g. Jayden).
_NAMED_PERSON_ROLE_TOKENS = frozenset(
    {
        "a",
        "an",
        "the",
        "you",
        "u",
        "your",
        "ur",
        "someone",
        "somebody",
        "anyone",
        "anybody",
        "specialist",
        "human",
        "person",
        "people",
        "team",
        "rep",
        "representative",
        "sales",
        "support",
        "manager",
        "owner",
        "customer",
        "service",
        "us",
        "me",
        "him",
        "her",
        "them",
        "google",
    }
)

_NAMED_PERSON_REQUEST_RES = (
    re.compile(
        r"\b(?:want|wanna|need)\s+(?:to\s+)?(?:talk|speak|chat)\s+(?:to|with)\s+"
        r"([a-z][a-z'’-]{1,})\b",
        re.I,
    ),
    re.compile(
        r"\b(?:talk|speak|chat)\s+(?:to|with)\s+([a-z][a-z'’-]{1,})\b",
        re.I,
    ),
    re.compile(
        r"\b(?:connect|reach)\s+(?:me\s+)?(?:with|to)\s+([a-z][a-z'’-]{1,})\b",
        re.I,
    ),
    re.compile(
        r"\bput\s+me\s+through\s+to\s+([a-z][a-z'’-]{1,})\b",
        re.I,
    ),
)


def _named_specific_person_escalation_reason(s: str) -> Optional[str]:
    """Detect requests for a specific named contact (not specialist / team / owner role-only)."""
    for rx in _NAMED_PERSON_REQUEST_RES:
        m = rx.search(s)
        if not m:
            continue
        token = m.group(1).lower().strip("'’").rstrip("s")
        if token in _NAMED_PERSON_ROLE_TOKENS:
            continue
        return f"specific_person:named_contact"
    return None


def transcript_suggests_recent_price_quote(transcript: list[dict[str, Any]]) -> bool:
    """True if the latest assistant turn looks like it contained a USD per-review quote."""
    for turn in reversed(transcript):
        if turn.get("role") != "assistant":
            continue
        body = turn.get("body") or ""
        if _QUOTE_IN_BODY_RE.search(body):
            return True
        low = body.lower()
        if "$" in body and "review" in low:
            return True
        break
    return False


def effective_quote_context(
    quoted_previously: bool,
    transcript: list[dict[str, Any]],
) -> bool:
    """Whether we should treat the thread as post-quote (CRM flag or last outbound quote)."""
    return quoted_previously or transcript_suggests_recent_price_quote(transcript)


def transcript_including_inbound(
    transcript: list[dict[str, Any]],
    inbound_message: Optional[str],
    channel: Channel,
) -> list[dict[str, Any]]:
    """Build the thread the drafter / self-correction should see for this turn.

    Callers often pass ``transcript`` ending before the current lead message and supply
    that text only via ``inbound_message``. Without re-attaching it, the model never
    sees questions like “how long will it take?”.
    """
    text = (inbound_message or "").strip()
    if not text:
        return list(transcript)
    last = transcript[-1] if transcript else None
    if last:
        role = str(last.get("role") or "").lower()
        if role in ("lead", "user") and str(last.get("body") or "").strip() == text:
            return list(transcript)
    return [
        *transcript,
        {"role": "lead", "body": text, "channel": channel.value},
    ]


# -----------------------------------------------------------------------------
# Regional footers (kept in code so self-correction can compare exact strings).
# -----------------------------------------------------------------------------

FOOTER_US = """Jayden Faris / ReviewArmour / +1 (786) 464-3783
1395 Brickell Avenue, Suite 800, Miami, FL 33131"""

FOOTER_CA = """Jayden Faris / ReviewArmour / +1 416-432-5439
2 Bloor St E Suite 3500, Toronto, Ontario, Canada M4W 1A8"""


def regional_footer(country: Country) -> str:
    return FOOTER_US if country == Country.US else FOOTER_CA


def recency_to_timeline_class(recency: RecencyProfile) -> str:
    if recency in (RecencyProfile.ALL_UNDER_1_MONTH, RecencyProfile.MOSTLY_UNDER_1_MONTH):
        return "under_1_month"
    return "mixed_or_over_1_month"


def lead_record_to_dict(lead: LeadRecord) -> dict[str, Any]:
    """Project the dataclass to a JSON-safe dict for Claude prompts."""
    return {
        "lead_id": lead.lead_id,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "business_name": lead.business_name,
        "country": lead.country.value,
        "phone": lead.phone,
        "email": lead.email,
        "gbp_link": lead.gbp_link,
        "review_count": lead.review_count,
        "recency_profile": lead.recency_profile.value,
        "business_category": lead.business_category,
        "is_price_sensitive_bulk": lead.is_price_sensitive_bulk,
        "negotiation_step": lead.negotiation_step,
        "ai_quote_allowed": lead.ai_quote_allowed,
        "soft_quote_mode": lead.soft_quote_mode,
        "lead_source": lead.lead_source,
        "urgency_flag": lead.urgency_flag,
    }


# -----------------------------------------------------------------------------
# Pipeline state types
# -----------------------------------------------------------------------------


@dataclass
class ConversationState:
    """Per-lead pipeline state. Persist this between turns in your CRM."""

    ai_conversation_state: str = "active"
    consecutive_no_progress_turns: int = 0
    last_commercial_turn_at: Optional[datetime] = None


@dataclass(frozen=True)
class CommercialTurnLLMResult:
    """Structured output from :meth:`ConversationModule.classify_commercial_engine_turn_llm`."""

    run_commercial_engine: bool
    negotiation_pushback: bool


@dataclass
class OutboundDraft:
    action: Literal["send", "escalate"]
    channel: Optional[Channel] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class PipelineResult:
    outcome: Literal["send", "escalate", "human_queue"]
    draft: Optional[OutboundDraft] = None
    commercial: Optional[CommercialResult] = None
    self_correction_logs: list[SelfCorrectionAttemptLog] = field(default_factory=list)
    human_queue_payload: Optional[dict[str, Any]] = None
    state_updates: dict[str, Any] = field(default_factory=dict)
    handoff_payload: Optional[dict[str, Any]] = None


# -----------------------------------------------------------------------------
# LLM-backed drafters
# -----------------------------------------------------------------------------


def _safe_gbp_inspection(raw: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a prompt-safe subset of the GBP inspection dict (strips large arrays)."""
    if not raw or raw.get("status") != "success":
        return None
    return {
        "inferred_recency_profile": raw.get("inferred_recency_profile"),
        "any_review_has_images": raw.get("any_review_has_images"),
        "review_count_inferred": raw.get("review_count_inferred"),
        "total_reviews_text": raw.get("total_reviews_text"),
        "business_name_extracted": raw.get("business_name_extracted"),
        "category_hints": raw.get("category_hints") or [],
    }


def _validate_outbound_draft_payload(data: dict[str, Any]) -> OutboundDraft:
    action = data.get("action")
    if action == "escalate":
        r = data.get("reason")
        if isinstance(r, str) and r.strip():
            return OutboundDraft(action="escalate", reason=r.strip())
        return OutboundDraft(action="escalate", reason="escalate")
    if action != "send":
        raise LLMResponseError(f"Invalid draft action {action!r}; expected 'send' or 'escalate'")
    channel_raw = data.get("channel")
    if channel_raw not in ("email", "sms"):
        raise LLMResponseError(f"Invalid draft channel {channel_raw!r}; expected 'email' or 'sms'")
    body = data.get("body")
    if not isinstance(body, str) or not body.strip():
        raise LLMResponseError("Draft body must be a non-empty string")
    subject = data.get("subject")
    if subject is not None and not isinstance(subject, str):
        raise LLMResponseError("Draft subject must be string or null")
    return OutboundDraft(
        action="send",
        channel=Channel(channel_raw),
        subject=subject,
        body=body,
    )


# -----------------------------------------------------------------------------
# Adaptive Price Selector (spec v2 Section 6)
# -----------------------------------------------------------------------------


@dataclass
class AdaptivePriceResult:
    """LLM-chosen price + reasoning for the engine to validate."""

    selected_price_usd: int
    lead_tone: str
    engagement: str
    reasoning_summary: str

    def to_adaptive_inputs(self) -> dict[str, Any]:
        return {
            "selected_price_usd": self.selected_price_usd,
            "lead_tone": self.lead_tone,
            "engagement": self.engagement,
            "reasoning_summary": self.reasoning_summary,
        }


class AdaptivePriceSelector:
    """Short Claude call that picks the per-review price within the authorized band.

    Output is validated by ``CommercialEngine.evaluate_pricing()``: if the LLM
    returns a price outside the band or below floor, the engine escalates and
    the pipeline can retry by re-prompting with the violation reason in
    ``operator_directive`` (handled by callers).
    """

    _VALID_TONES = ("cooperative", "price_sensitive", "urgent", "noncommittal")
    _VALID_ENGAGEMENT = ("high", "medium", "low")

    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        runtime: Optional[LLMRuntime] = None,
        system_prompt: str = ADAPTIVE_PRICE_SELECTOR_SYSTEM,
    ) -> None:
        if client is None:
            raise ConfigError("AdaptivePriceSelector requires an Anthropic client")
        self._client = client
        self._runtime = runtime or LLMRuntime()
        self._system = system_prompt

    def select(
        self,
        *,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
        tier: str,
        range_low_usd: int,
        range_high_usd: int,
        floor_usd: int,
        retry_reason: Optional[str] = None,
    ) -> AdaptivePriceResult:
        tail = transcript[-8:] if len(transcript) > 8 else transcript
        payload = {
            "tier": tier,
            "gbp_category": lead.gbp_category.value if lead.gbp_category else None,
            "volume_bracket": lead.volume_bracket().value,
            "review_count": lead.review_count,
            "range_low_usd": range_low_usd,
            "range_high_usd": range_high_usd,
            "floor_usd": floor_usd,
            "negotiation_step": lead.negotiation_step,
            "reviews_image_content": list(lead.reviews_image_content),
            "reviews_under_one_month": list(lead.reviews_under_one_month),
            "recency_profile": lead.recency_profile.value,
            "lead_tone_hint": lead.lead_tone.value if lead.lead_tone else None,
            "engagement_hint": (
                lead.engagement_level.value if lead.engagement_level else None
            ),
            "business_name": lead.business_name,
            "recent_transcript_tail": tail,
            "retry_reason": retry_reason,
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=self._system,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=512,
        )
        return self._validate(data, range_low_usd, range_high_usd, floor_usd)

    def _validate(
        self,
        data: dict[str, Any],
        range_low: int,
        range_high: int,
        floor: int,
    ) -> AdaptivePriceResult:
        price = data.get("selected_price_usd")
        if not isinstance(price, int) or isinstance(price, bool):
            try:
                price = int(price)
            except (TypeError, ValueError):
                raise LLMResponseError(
                    f"AdaptivePriceSelector returned non-integer price: {price!r}"
                )

        tone = str(data.get("lead_tone") or "cooperative").lower()
        if tone not in self._VALID_TONES:
            tone = "cooperative"
        engagement = str(data.get("engagement") or "medium").lower()
        if engagement not in self._VALID_ENGAGEMENT:
            engagement = "medium"

        reasoning = str(data.get("reasoning_summary") or "").strip()
        if len(reasoning) > 240:
            reasoning = reasoning[:237] + "..."

        return AdaptivePriceResult(
            selected_price_usd=price,
            lead_tone=tone,
            engagement=engagement,
            reasoning_summary=reasoning,
        )


class ConversationModule:
    """Drafts outbound copy via Claude. Never sends; never invents prices."""

    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        runtime: Optional[LLMRuntime] = None,
        system_prompt: str = CONVERSATION_SYSTEM,
        first_touch_variation: str = FIRST_TOUCH_VARIATION,
    ) -> None:
        if client is None:
            raise ConfigError("ConversationModule requires an Anthropic client")
        if first_touch_variation not in ("A", "B", "C"):
            raise ConfigError(
                f"first_touch_variation must be A/B/C; got {first_touch_variation!r}"
            )
        self._client = client
        self._runtime = runtime or LLMRuntime()
        self._system = system_prompt
        self._first_touch_variation = first_touch_variation

    def draft(
        self,
        *,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
        channel: Channel,
        sequence_stage: str,
        commercial_output: Optional[CommercialResult],
        operator_directive: Optional[str] = None,
        gbp_inspection: Optional[dict[str, Any]] = None,
    ) -> OutboundDraft:
        payload = {
            "lead_record": lead_record_to_dict(lead),
            "conversation_transcript": transcript,
            "channel": channel.value,
            "sequence_stage": sequence_stage,
            "first_touch_variation": self._first_touch_variation,
            "timeline_class": recency_to_timeline_class(lead.recency_profile),
            "approved_timeline_paragraphs": dict(APPROVED_TIMELINE_PARAGRAPHS),
            "commercial_output": commercial_output.to_prompt_dict() if commercial_output else None,
            "operator_directive": operator_directive,
            "soft_quote_mode": lead.soft_quote_mode,
            "gbp_inspection": _safe_gbp_inspection(gbp_inspection),
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=self._system,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=self._runtime.draft_max_tokens,
        )
        return _validate_outbound_draft_payload(data)

    def detect_quote_acceptance_llm(
        self,
        inbound_message: str,
        transcript: list[dict[str, Any]],
    ) -> bool:
        """Classify whether the lead is accepting the quoted USD rate (not e.g. timeline).

        Sees ``recent_transcript_tail`` from the thread; use when the pipeline has
        ``use_llm_quote_acceptance=True`` (primary path in production).
        """
        tail = transcript[-8:] if len(transcript) > 8 else transcript
        payload = {
            "lead_latest_message": inbound_message,
            "recent_transcript_tail": tail,
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=POST_QUOTE_ACCEPTANCE_SYSTEM,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=256,
        )
        return bool(data.get("accept"))

    def classify_commercial_engine_turn_llm(
        self,
        inbound_message: str,
        transcript: list[dict[str, Any]],
        *,
        quoted_previously_flag: bool,
    ) -> CommercialTurnLLMResult:
        """LLM classifies pricing/commercial need and negotiation pushback (for tier steps)."""
        tail = transcript[-10:] if len(transcript) > 10 else transcript
        payload = {
            "lead_latest_message": inbound_message,
            "recent_transcript_tail": tail,
            "crm_quoted_previously": quoted_previously_flag,
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=COMMERCIAL_ENGINE_TURN_SYSTEM,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=320,
        )
        return CommercialTurnLLMResult(
            run_commercial_engine=bool(data.get("run_commercial_engine")),
            negotiation_pushback=bool(data.get("negotiation_pushback")),
        )


class CustomerReviewRequestModule:
    """Drafts the post-removal Google review request to a customer (1/2/3 touches)."""

    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        runtime: Optional[LLMRuntime] = None,
    ) -> None:
        if client is None:
            raise ConfigError("CustomerReviewRequestModule requires an Anthropic client")
        self._client = client
        self._runtime = runtime or LLMRuntime()

    def draft(
        self,
        *,
        customer: dict[str, Any],
        touch_number: int,
        channel: Channel,
        gbp_review_link: str,
    ) -> OutboundDraft:
        if touch_number not in (1, 2, 3):
            raise ConfigError(f"touch_number must be 1, 2, or 3; got {touch_number}")
        payload = {
            "customer_record": customer,
            "touch_number": touch_number,
            "channel": channel.value,
            "gbp_review_link": gbp_review_link,
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=CUSTOMER_REVIEW_REQUEST_SYSTEM,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=self._runtime.review_max_tokens,
        )
        return _validate_outbound_draft_payload(data)


# -----------------------------------------------------------------------------
# Inbound classification (deterministic guards)
# -----------------------------------------------------------------------------


def _lower(text: str) -> str:
    return text.strip().lower()


def should_escalate_inbound(lead_message: str, *, post_payment_context: bool = False) -> Optional[str]:
    """Return a short escalation reason, or None if no hard trigger fires."""
    s = _lower(lead_message)
    for w in LEGAL_ESCALATION:
        if w in s:
            return f"legal_escalation:{w}"
    if post_payment_context:
        for w in POST_PAY_ESCALATION:
            if w in s:
                return f"post_payment:{w}"
        if "cancel" in s:
            return "post_payment:cancel"
    for w in REGULATOR_ESCALATION:
        if w in s:
            return f"regulator:{w}"
    for w in SPECIFIC_PERSON_ESCALATION:
        if w in s:
            return f"specific_person:{w}"
    npr = _named_specific_person_escalation_reason(s)
    if npr:
        return npr
    if "lawsuit" in s or "suing" in s:
        return "legal_escalation:lawsuit_related"
    return None


def is_price_question_escalation(lead_message: str) -> bool:
    """Detects common price/quote shopping phrases in inbound text.

    When present on an inbound turn, the pipeline treats this as a pricing turn
    (runs :class:`CommercialEngine` and drafts via the conversation module with
    authorized numbers only). This does **not** auto-escalate to a human.
    """
    s = _lower(lead_message)
    return any(p in s for p in PRICE_SHOPPING_ESCALATION_PHRASES)


def is_negotiation_pushback(lead_message: str) -> bool:
    """Lead is pushing on price after seeing a quote (subset — pair with transcript context)."""
    s = _lower(lead_message)
    return any(p in s for p in _NEGOTIATION_PUSHBACK_PHRASES)


def pricing_turn_requested(
    *,
    wants_price: bool,
    inbound_message: Optional[str],
    transcript: Optional[list[dict[str, Any]]] = None,
    quoted_previously: bool = False,
) -> bool:
    """True if this turn should run :class:`CommercialEngine` (initial quote or negotiation)."""
    if wants_price:
        return True
    if inbound_message and is_price_question_escalation(inbound_message):
        return True
    if (
        inbound_message
        and transcript is not None
        and effective_quote_context(quoted_previously, transcript)
        and is_negotiation_pushback(inbound_message)
    ):
        return True
    return False


_SUCCESS_RATE_TOPIC_RE = re.compile(
    r"(?:"
    r"\bsuccess\s+rate\b|"
    r"\bsuccess\s+percentage\b|"
    r"\bhit\s+rate\b|"
    r"\bwhat\s+percentage\b.*\b(reviews?\b|remov|pull)|"
    r"\bhow\s+often\b.*\b(remov|pull|success|work)|"
    r"\b(odds|chance|chances|likelihood)\b.*\b(remov|pull|down)\b|"
    r"\bwill\s+it\s+come\s+down\b|"
    r"\bwill\s+the\s+review\b.*\b(come\s+down|remov|pull)|"
    r"\bdoes\s+it\s+work\b|"
    r"\bget\s+(the\s+)?review\b.*\b(pulled|down|remov)"
    r")",
    re.I,
)

# If this matches, the lead is also asking about money — do not treat as success-only.
_PRICING_INTENT_IN_MESSAGE_RE = re.compile(
    r"(?:"
    r"\bhow\s+much\b|"
    r"\bwhat.+\b(cost|price)\b|"
    r"\bper\s+review\b|"
    r"\$\s*\d|"
    r"\busd\b.*\b(per|review)\b|"
    r"\bnegotiat|"
    r"\bdiscount\b|"
    r"\bcheaper\b|"
    r"\blower\s+the\s+price\b|"
    r"\binvoice\b|"
    r"\bquote\b|"
    r"\bfee\b|"
    r"\bfees\b"
    r")",
    re.I,
)


_WHAT_IS_ARE_RE = re.compile(r"\bwhat\s+(?:is|are)\b", re.I)


def inbound_asks_success_rate_topic(inbound_message: Optional[str]) -> bool:
    """True when the inbound is primarily about removal odds / success rate, not USD pricing.

    Bundled emails (several questions in one message) are **not** success-only: the pipeline
    must still run the commercial classifier so cost/negotiation turns are not skipped.
    """
    raw = (inbound_message or "").strip()
    if not raw:
        return False
    if _PRICING_INTENT_IN_MESSAGE_RE.search(raw):
        return False
    # Multiple distinct asks in one inbound (e.g. cost + success rate + hard date).
    if raw.count("?") >= 2:
        return False
    if len(_WHAT_IS_ARE_RE.findall(raw)) >= 2:
        return False
    if lead_demands_hard_calendar_date([{"role": "lead", "body": raw}]):
        return False
    return bool(_SUCCESS_RATE_TOPIC_RE.search(raw))


def soft_pricing_fallback_hint(lead_message: str) -> bool:
    """Broad vocabulary when strict phrase lists miss — paired with LLM for final say."""
    if inbound_asks_success_rate_topic(lead_message):
        return False
    s = _lower(lead_message)
    hints = (
        "price",
        "cost",
        "quote",
        "fee",
        "fees",
        "pay",
        "paid",
        "payment",
        "budget",
        "afford",
        "expensive",
        "cheap",
        "discount",
        "deal",
        "rate",
        "invoice",
        "usd",
        "$",
        "money",
        "charge",
        "billing",
        "negotiat",
        "lower",
        "flex",
        "match",
        "worth",
        "how much",
        "what would",
        "ballpark",
    )
    return any(h in s for h in hints)


def should_invoke_commercial_turn_classifier(
    inbound_message: str,
    transcript: Optional[list[dict[str, Any]]],
    quoted_previously: bool,
) -> bool:
    """Gate LLM commercial-turn classifier to avoid calls on obvious non-price replies."""
    if not (inbound_message or "").strip():
        return False
    if inbound_asks_success_rate_topic(inbound_message):
        return False
    t = transcript or []
    if effective_quote_context(quoted_previously, t):
        return True
    return soft_pricing_fallback_hint(inbound_message)


_AGREEMENT_PROCESS_Q_RE = re.compile(
    r"like\s+how\b|\bhow\s+(can|do)\s+we\b|\bwhen\s+(can|do)\s+we\b|"
    r"\bwhere\s+do\s+we\b|what.*\bprocess\b|\bcan\s+we\s+sign\b|\bdo\s+we\s+sign\b",
    re.I,
)


def inbound_asks_signing_or_agreement_process(inbound_message: Optional[str]) -> bool:
    """True when the lead asks how/when signing or paperwork works — not quote acceptance."""
    raw = (inbound_message or "").strip()
    if not raw or "?" not in raw:
        return False
    s = raw.lower()
    if not any(
        k in s for k in ("sign", "docusign", "agreement", "contract", "paperwork")
    ):
        return False
    return bool(_AGREEMENT_PROCESS_Q_RE.search(s))


def acceptance_signal(lead_message: str) -> bool:
    """Deterministic go-ahead detection. Pair with :func:`effective_quote_context`.

    Uses only the latest inbound string — no transcript. For phrases like \"go ahead\"
    that can affirm non-pricing content, :func:`OutboundPipeline.run` may clear this
    hit when the latest assistant turn did not include a USD/review quote, and defer
    to :meth:`ConversationModule.detect_quote_acceptance_llm` (which *does* see the
    thread) when enabled.
    """
    s = _lower(lead_message)
    if any(p in s for p in ACCEPTANCE_PHRASES):
        return True
    stripped = s.strip().strip("!.\"'").strip()
    if stripped in _ACCEPT_ONE_WORD:
        return True
    return False


_MEANINGFUL_ENGAGEMENT_CALL_RE = re.compile(
    r"\b("
    r"book\s+(a\s+)?call|"
    r"schedule\s+(a\s+)?call|"
    r"set\s+up\s+(a\s+)?call|"
    r"call\s+me|phone\s+me|ring\s+me|"
    r"hop\s+on\s+(a\s+)?call|"
    r"calendar\s+link|\bcalendly\b"
    r")\b",
    re.I,
)

_MEANINGFUL_TIMELINE_RE = re.compile(
    r"\b(how\s+long|how\s+soon|how\s+much\s+time|when\s+(will|would|can|should)|"
    r"timeframe|timeline|typical\s+window)\b",
    re.I,
)

_SERVICE_CONTEXT_RE = re.compile(
    r"\b("
    r"review|reviews|removal|remove\b|google|gbp|g\.page|maps|business\s+profile|"
    r"listing|negative\s+review|bad\s+review|\d\s*-?\s*star|"
    r"star\s+rating|pay.*after|your\s+service|this\s+service|policy[\s-]*violat"
    r")\b",
    re.I,
)

_MEANINGFUL_SOFT_INTEREST_RE = re.compile(
    r"\b("
    r"i'?m\s+interested|i\s+am\s+interested|sounds\s+(good|great)|"
    r"tell\s+me\s+more|more\s+info|more\s+information|"
    r"let'?s\s+talk|lets\s+talk|"
    r"what\s+else\s+can\s+you\s+tell|any\s+other\s+details"
    r")\b",
    re.I,
)

_METHOD_OR_PROCESS_RE = re.compile(
    r"\b("
    r"how\s+do\s+you|how\s+does\s+this|what\s+is\s+the\s+process|what'?s\s+the\s+process|"
    r"walk\s+me\s+through|how\s+does\s+it\s+work|how\s+did\s+you|"
    r"what\s+steps|step\s*by\s*step"
    r")\b",
    re.I,
)

_PAY_OR_WARRANTY_RE = re.compile(
    r"\b("
    r"warranty|guarantee|money\s*back|what\s+if\s+(it\s+)?(doesn'?t|does\s+not)|"
    r"pay\s+if|still\s+pay|what\s+happens\s+if"
    r")\b",
    re.I,
)


def inbound_indicates_meaningful_engagement(
    inbound_message: str,
    *,
    transcript: list[dict[str, Any]],
    quoted_previously: bool,
) -> bool:
    """True when the lead's message shows in-scope engagement (Section 8 / stall spec).

    Random or off-topic text (e.g. weather) returns False so consecutive no-progress
    turns can escalate after three redirect cycles.
    """
    s = (inbound_message or "").strip()
    if not s:
        return False
    low = _lower(s)

    if extract_gbp_url(s):
        return True
    if is_price_question_escalation(s) or is_negotiation_pushback(s):
        return True
    if soft_pricing_fallback_hint(s):
        return True
    if inbound_asks_success_rate_topic(s) or bool(_SUCCESS_RATE_TOPIC_RE.search(s)):
        return True
    if _MEANINGFUL_ENGAGEMENT_CALL_RE.search(s):
        return True
    if inbound_asks_signing_or_agreement_process(s):
        return True
    if re.search(r"\b(docusign|removal\s+brief)\b", low):
        return True
    if _MEANINGFUL_TIMELINE_RE.search(s) and _SERVICE_CONTEXT_RE.search(s):
        return True
    if _METHOD_OR_PROCESS_RE.search(s):
        return True
    if _PAY_OR_WARRANTY_RE.search(s):
        return True
    if _MEANINGFUL_SOFT_INTEREST_RE.search(s):
        return True
    if _SERVICE_CONTEXT_RE.search(s):
        return True
    if acceptance_signal(s) and effective_quote_context(quoted_previously, transcript):
        return True
    return False


def resolve_meaningful_progress(
    inbound_message: Optional[str],
    meaningful_progress: Optional[bool],
    *,
    transcript: Optional[list[dict[str, Any]]] = None,
    quoted_previously: bool = False,
) -> bool:
    """CRM override, else: heuristic in-scope engagement (not merely non-empty text)."""
    if meaningful_progress is not None:
        return bool(meaningful_progress)
    text = (inbound_message or "").strip()
    if not text:
        return False
    return inbound_indicates_meaningful_engagement(
        text,
        transcript=list(transcript or []),
        quoted_previously=quoted_previously,
    )


# -----------------------------------------------------------------------------
# Outbound pipeline
# -----------------------------------------------------------------------------


class OutboundPipeline:
    """Orchestrates: commercial -> draft -> self-correct -> redraft up to 2x.

    Quote acceptance: when ``use_llm_quote_acceptance`` is True (default), only the
    LLM classifier decides (it sees recent transcript). When False, a deterministic
    phrase list is used instead (for fast offline tests).
    """

    MAX_FIX_RETRIES = 2

    # Max number of times the engine re-prompts the adaptive selector on an
    # out-of-band / below-floor price before giving up and using band midpoint.
    MAX_ADAPTIVE_RETRIES = 2

    def __init__(
        self,
        *,
        conversation: ConversationModule,
        self_correction: SelfCorrectionModule,
        commercial_engine: Optional[CommercialEngine] = None,
        adaptive_price_selector: Optional[AdaptivePriceSelector] = None,
        now_fn: Callable[[], datetime] | None = None,
        use_llm_quote_acceptance: bool = True,
        use_llm_commercial_turn: bool = True,
        use_adaptive_price_selector: bool = True,
    ) -> None:
        """
        Args:
            adaptive_price_selector: Spec v2 — Claude call that picks the
                per-review price within the tier band. If None and
                ``use_adaptive_price_selector`` is True, one is constructed
                from the same client/runtime as ``conversation``.
            use_llm_quote_acceptance: If True, quote acceptance uses
                :meth:`ConversationModule.detect_quote_acceptance_llm` only.
            use_adaptive_price_selector: When False, the engine falls back to
                its deterministic band-midpoint price (faster for tests).
        """
        self._conversation = conversation
        self._sc = self_correction
        self._commercial = commercial_engine or CommercialEngine()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._use_llm_quote_acceptance = use_llm_quote_acceptance
        self._use_llm_commercial_turn = use_llm_commercial_turn
        self._use_adaptive_price_selector = use_adaptive_price_selector

        if adaptive_price_selector is not None:
            self._adaptive_selector: Optional[AdaptivePriceSelector] = adaptive_price_selector
        elif use_adaptive_price_selector:
            # Share the conversation module's Anthropic client + runtime.
            self._adaptive_selector = AdaptivePriceSelector(
                client=conversation._client,
                runtime=conversation._runtime,
            )
        else:
            self._adaptive_selector = None

    # ---- adaptive selector ----

    def _run_adaptive_selector_if_eligible(
        self,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
    ) -> tuple[Optional[int], dict[str, Any], str]:
        """Return (adaptive_price_usd, adaptive_inputs, reasoning_summary).

        Eligibility:
          - selector is enabled
          - lead.gbp_category is set (otherwise engine asks for category)
          - lead.ai_quote_allowed is True
          - soft-quote mode is off (band-based range supersedes adaptive)

        Retry policy: on out-of-band / below-floor / non-integer responses,
        re-prompt up to ``MAX_ADAPTIVE_RETRIES`` times with a ``retry_reason``.
        On exhaustion, return (None, {...}, "") and let the engine midpoint.
        """
        if self._adaptive_selector is None:
            return None, {}, ""
        if lead.gbp_category is None:
            return None, {}, ""
        if not lead.ai_quote_allowed:
            return None, {}, ""
        if lead.soft_quote_mode:
            return None, {}, ""

        # Resolve the band the engine will validate against. Mirror commercial.py.
        from reviewarmour.commercial import get_volume_band

        config, band = get_volume_band(lead.gbp_category, lead.review_count)

        retry_reason: Optional[str] = None
        for attempt in range(self.MAX_ADAPTIVE_RETRIES + 1):
            try:
                result = self._adaptive_selector.select(
                    lead=lead,
                    transcript=transcript,
                    tier=config.tier.value,
                    range_low_usd=band.low_usd,
                    range_high_usd=band.high_usd,
                    floor_usd=config.floor_usd,
                    retry_reason=retry_reason,
                )
            except Exception as e:
                logger.warning(
                    "AdaptivePriceSelector error for lead %s (attempt %d): %s",
                    lead.lead_id, attempt + 1, e,
                )
                return None, {"selector_error": str(e)}, ""

            price = result.selected_price_usd
            in_band = band.low_usd <= price <= band.high_usd
            above_floor = price >= config.floor_usd

            # T1 written-exception: also accept floor..$450 when conditions are met.
            from reviewarmour.commercial import T1_WRITTEN_EXCEPTION_CEILING_USD
            t1_exception_ok = (
                config.tier.value == "T1"
                and lead.review_count <= 2
                and lead.all_reviews_image_or_recent()
                and config.floor_usd <= price <= T1_WRITTEN_EXCEPTION_CEILING_USD
            )

            if (in_band or t1_exception_ok) and above_floor:
                logger.info(
                    "AdaptivePriceSelector: lead %s tier=%s band=$%d-$%d -> $%d (%s)",
                    lead.lead_id, config.tier.value, band.low_usd, band.high_usd,
                    price, result.lead_tone,
                )
                return price, result.to_adaptive_inputs(), result.reasoning_summary

            retry_reason = (
                f"Your previous response selected ${price} which is outside the "
                f"allowed band ${band.low_usd}-${band.high_usd} or below floor "
                f"${config.floor_usd}. Pick a new integer per-review price strictly "
                f"within ${band.low_usd}-${band.high_usd} (or, for T1 exception, "
                f"${config.floor_usd}-$450 only when review_count <= 2 and every "
                f"review is image-or-under-1-month)."
            )
            logger.info(
                "AdaptivePriceSelector retry %d for lead %s: %s",
                attempt + 1, lead.lead_id, retry_reason,
            )

        # All retries exhausted — return None so the engine midpoints.
        logger.warning(
            "AdaptivePriceSelector exhausted %d retries for lead %s; "
            "falling back to band midpoint",
            self.MAX_ADAPTIVE_RETRIES, lead.lead_id,
        )
        return None, {"selector_retries_exhausted": True}, ""

    # ---- public API ----

    def run(
        self,
        *,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
        channel: Channel,
        sequence_stage: str,
        inbound_message: Optional[str] = None,
        wants_price: bool = False,
        post_payment_context: bool = False,
        lead_requested_price_below_floor: bool = False,
        quoted_previously: bool = False,
        conversation_state: Optional[ConversationState] = None,
        meaningful_progress: Optional[bool] = None,
        now_override: Optional[datetime] = None,
        gbp_inspection: Optional[dict[str, Any]] = None,
    ) -> PipelineResult:
        cstate = conversation_state or ConversationState()
        logs: list[SelfCorrectionAttemptLog] = []
        now = now_override if now_override is not None else self._now()
        draft_transcript = transcript_including_inbound(transcript, inbound_message, channel)

        # 1. Inbound message guards — escalation first; quote acceptance before stall counting.
        if inbound_message is not None:
            es = should_escalate_inbound(inbound_message, post_payment_context=post_payment_context)
            if es:
                logger.info("Pipeline escalate: %s for lead %s", es, lead.lead_id)
                return PipelineResult(
                    outcome="escalate",
                    draft=OutboundDraft(action="escalate", reason=es),
                    state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
                )

            effective_quote = effective_quote_context(quoted_previously, transcript)

            accepted = False
            if effective_quote:
                if inbound_asks_signing_or_agreement_process(inbound_message):
                    logger.info(
                        "Inbound asks signing/agreement process; skipping quote acceptance "
                        "for lead %s",
                        lead.lead_id,
                    )
                    accepted = False
                elif (
                    acceptance_signal(inbound_message)
                    and not transcript_suggests_recent_price_quote(transcript)
                ):
                    logger.info(
                        "Acceptance phrase matched inbound but latest assistant turn "
                        "has no USD/review quote; ignoring quote acceptance for lead %s",
                        lead.lead_id,
                    )
                    accepted = False
                elif self._use_llm_quote_acceptance:
                    try:
                        accepted = self._conversation.detect_quote_acceptance_llm(
                            inbound_message, transcript
                        )
                    except Exception as e:
                        logger.warning(
                            "Quote acceptance LLM failed for lead %s: %s",
                            lead.lead_id,
                            e,
                        )
                else:
                    accepted = acceptance_signal(inbound_message)

            if effective_quote and accepted:
                return self._handle_acceptance(lead, transcript, channel, logs, now)

            mp = resolve_meaningful_progress(
                inbound_message,
                meaningful_progress,
                transcript=transcript,
                quoted_previously=quoted_previously,
            )
            no_progress_result = self._maybe_no_progress(cstate, mp)
            if no_progress_result is not None:
                return no_progress_result

            # Auto-capture GBP link from inbound text when the lead record has none.
            if not lead.has_gbp_link():
                found_url = extract_gbp_url(inbound_message)
                if found_url:
                    lead.gbp_link = found_url
                    logger.info(
                        "Auto-captured GBP link from inbound message for lead %s: %s",
                        lead.lead_id,
                        found_url,
                    )

        det_turn = pricing_turn_requested(
            wants_price=wants_price,
            inbound_message=inbound_message,
            transcript=transcript,
            quoted_previously=quoted_previously,
        )
        effective_wants_price = bool(wants_price) or det_turn

        skip_commercial_classify = bool(
            inbound_message and inbound_asks_success_rate_topic(inbound_message)
        )
        llm_turn = CommercialTurnLLMResult(False, False)
        if (
            inbound_message
            and self._use_llm_commercial_turn
            and not skip_commercial_classify
        ):
            try:
                llm_turn = self._conversation.classify_commercial_engine_turn_llm(
                    inbound_message,
                    transcript,
                    quoted_previously_flag=quoted_previously,
                )
            except Exception as e:
                logger.warning(
                    "Commercial turn classifier LLM failed for lead %s: %s",
                    lead.lead_id,
                    e,
                )
            effective_wants_price = (
                effective_wants_price or llm_turn.run_commercial_engine
            )

        if (
            inbound_message
            and effective_wants_price
            and effective_quote_context(quoted_previously, transcript)
        ):
            pushback = llm_turn.negotiation_pushback or is_negotiation_pushback(
                inbound_message
            )
            if pushback and lead.negotiation_step > 2:
                logger.info(
                    "Negotiation pushback past final step (step>2); escalating for lead %s",
                    lead.lead_id,
                )
                return PipelineResult(
                    outcome="escalate",
                    draft=OutboundDraft(
                        action="escalate",
                        reason="negotiation_past_final_step",
                    ),
                    state_updates={
                        "consecutive_no_progress_turns": cstate.consecutive_no_progress_turns,
                        "ai_conversation_state": "escalated_to_human",
                    },
                )
            if pushback and lead.negotiation_step < 2:
                if record_negotiation_pushback(
                    lead, inbound_message, now=now, max_step=2
                ):
                    logger.info(
                        "Negotiation pushback: bumped negotiation_step to %s for lead %s",
                        lead.negotiation_step,
                        lead.lead_id,
                    )
                else:
                    logger.info(
                        "Negotiation pushback already recorded for lead %s (step=%s)",
                        lead.lead_id,
                        lead.negotiation_step,
                    )

        # 2. Kill switch: ai_quote_allowed=false on a pricing turn always escalates here.
        if effective_wants_price and not lead.ai_quote_allowed:
            logger.info("Pipeline escalate: ai_quote_allowed=false for lead %s", lead.lead_id)
            return PipelineResult(
                outcome="escalate",
                draft=OutboundDraft(action="escalate", reason="ai_quote_allowed_kill_switch"),
                state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
            )

        # 3. Commercial reasoning, only on pricing turns (explicit flag or inbound asks for price).
        commercial: Optional[CommercialResult] = None
        if effective_wants_price:
            # Spec v2 Section 6: run the LLM adaptive selector first when the
            # lead has enough info for the engine to validate a band. The engine
            # falls back to band midpoint if the selector is disabled or returns
            # an out-of-band price across all retries.
            adaptive_price, adaptive_inputs, adaptive_summary = (
                self._run_adaptive_selector_if_eligible(lead, draft_transcript)
            )
            commercial = self._commercial.evaluate_pricing(
                lead,
                wants_price=True,
                adaptive_price_usd=adaptive_price,
                reasoning_summary=adaptive_summary,
                adaptive_inputs=adaptive_inputs,
                lead_requested_price_below_floor=lead_requested_price_below_floor,
                now=now,
            )
            if commercial.escalate and not commercial.request_gbp_first:
                logger.info(
                    "Pipeline escalate (commercial): %s for lead %s",
                    commercial.escalation_reason,
                    lead.lead_id,
                )
                return PipelineResult(
                    outcome="escalate",
                    commercial=commercial,
                    draft=OutboundDraft(
                        action="escalate",
                        reason=commercial.escalation_reason or "commercial_escalate",
                    ),
                    state_updates={
                        "consecutive_no_progress_turns": cstate.consecutive_no_progress_turns,
                        "ai_conversation_state": "escalated_to_human",
                    },
                )

        # 4. Draft + self-correct loop.
        operator_directive: Optional[str] = None
        attempt = 0
        final_draft: Optional[OutboundDraft] = None
        last_draft: Optional[OutboundDraft] = None
        last_verdict: Optional[SelfCorrectionVerdict] = None

        while attempt < self.MAX_FIX_RETRIES + 1:
            attempt += 1
            draft = self._conversation.draft(
                lead=lead,
                transcript=draft_transcript,
                channel=channel,
                sequence_stage=sequence_stage,
                commercial_output=commercial,
                operator_directive=operator_directive,
                gbp_inspection=gbp_inspection,
            )
            if (
                draft.action == "escalate"
                and commercial is None
                and not effective_wants_price
            ):
                logger.info(
                    "Drafter escalated with no commercial_result on non-pricing turn; "
                    "retrying once for lead %s",
                    lead.lead_id,
                )
                draft = self._conversation.draft(
                    lead=lead,
                    transcript=draft_transcript,
                    channel=channel,
                    sequence_stage=sequence_stage,
                    commercial_output=commercial,
                    operator_directive=(
                        "Regeneration: commercial_output is null because this is not a pricing-engine turn. "
                        "Return action send only (first-touch or follow-up per GBP rules, no USD quote). "
                        "Do not escalate for missing commercial_output."
                    ),
                    gbp_inspection=gbp_inspection,
                )
            last_draft = draft
            if draft.action == "escalate":
                logger.info(
                    "Pipeline escalate (drafter): %s for lead %s", draft.reason, lead.lead_id
                )
                return PipelineResult(
                    outcome="escalate",
                    draft=draft,
                    commercial=commercial,
                    self_correction_logs=logs,
                )

            verdict = self._sc.review(
                draft_subject=draft.subject,
                draft_body=draft.body or "",
                channel=(draft.channel or channel).value,
                lead_record=lead_record_to_dict(lead),
                transcript=draft_transcript,
                commercial_snapshot=commercial.to_prompt_dict() if commercial else None,
                timeline_class=recency_to_timeline_class(lead.recency_profile),
                soft_quote_mode=lead.soft_quote_mode,
                gbp_inspection=_safe_gbp_inspection(gbp_inspection),
            )
            last_verdict = verdict
            logs.append(
                SelfCorrectionAttemptLog(
                    attempt=attempt,
                    verdict=verdict.verdict,
                    failed_checks=verdict.failed_checks,
                    at=now,
                )
            )
            logger.info(
                "Self-correction attempt %d: verdict=%s checks=%s",
                attempt,
                verdict.verdict,
                verdict.failed_checks,
            )

            if verdict.verdict == "pass":
                final_draft = draft
                break
            if verdict.verdict == "escalate":
                return PipelineResult(
                    outcome="escalate",
                    draft=draft,
                    commercial=commercial,
                    self_correction_logs=logs,
                    state_updates={"escalation_reason": verdict.escalation_reason},
                )
            # fix verdict: if we still have retries left, redraft with directives
            if attempt <= self.MAX_FIX_RETRIES:
                operator_directive = (
                    "; ".join(verdict.suggested_fixes) or "Fix copy-rule violations"
                )
                continue
            # third attempt also failed -> human queue (per spec: max 2 redraft attempts)
            break

        if final_draft is None:
            assert last_draft is not None and last_verdict is not None
            return self._human_queue(last_draft, logs, last_verdict)

        # 5. Mark commercial turn for stall detection; bubble state updates up.
        state_updates: dict[str, Any] = {
            "consecutive_no_progress_turns": cstate.consecutive_no_progress_turns,
            "negotiation_step": lead.negotiation_step,
        }
        stall_hours = 2 if lead.soft_quote_mode else 6
        if commercial and commercial.commercial_turn:
            cstate.last_commercial_turn_at = commercial.commercial_turn.sent_at
            state_updates["last_commercial_turn_at"] = commercial.commercial_turn.sent_at.isoformat()
            state_updates["stall_threshold_hours"] = stall_hours

        return PipelineResult(
            outcome="send",
            draft=final_draft,
            commercial=commercial,
            self_correction_logs=logs,
            state_updates=state_updates,
        )

    # ---- internals ----

    def _maybe_no_progress(
        self, cstate: ConversationState, meaningful_progress: bool
    ) -> Optional[PipelineResult]:
        if not meaningful_progress:
            cstate.consecutive_no_progress_turns += 1
            if cstate.consecutive_no_progress_turns >= 3:
                return PipelineResult(
                    outcome="escalate",
                    draft=OutboundDraft(action="escalate", reason="no_progress_three_turns"),
                    state_updates={
                        "consecutive_no_progress_turns": cstate.consecutive_no_progress_turns
                    },
                )
        else:
            cstate.consecutive_no_progress_turns = 0
        return None

    def _handle_acceptance(
        self,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
        channel: Channel,
        logs: list[SelfCorrectionAttemptLog],
        now: datetime,
    ) -> PipelineResult:
        """Acceptance signal: hardcoded confirmation message per spec, still self-corrected."""
        body = (
            "Confirmed. Your specialist will send the removal brief and the "
            "DocuSign within the hour. You'll pay only after the reviews are down.\n"
            f"{regional_footer(lead.country)}"
        )
        subj = f"Confirmed for {lead.business_name}" if channel == Channel.EMAIL else None
        draft = OutboundDraft(action="send", channel=channel, subject=subj, body=body)
        verdict = self._sc.review(
            draft_subject=draft.subject,
            draft_body=draft.body or "",
            channel=channel.value,
            lead_record=lead_record_to_dict(lead),
            transcript=transcript,
            commercial_snapshot=None,
            timeline_class=recency_to_timeline_class(lead.recency_profile),
            soft_quote_mode=lead.soft_quote_mode,
        )
        logs.append(
            SelfCorrectionAttemptLog(
                attempt=1,
                verdict=verdict.verdict,
                failed_checks=verdict.failed_checks,
                at=now,
            )
        )
        if verdict.verdict != "pass":
            return self._human_queue(draft, logs, verdict)
        return PipelineResult(
            outcome="send",
            draft=draft,
            self_correction_logs=logs,
            state_updates={
                "ai_conversation_state": "quote_accepted",
                "consecutive_no_progress_turns": 0,
                "negotiation_step": lead.negotiation_step,
            },
            handoff_payload={"type": "quote_to_invoice", "lead_id": lead.lead_id},
        )

    def _human_queue(
        self,
        draft: OutboundDraft,
        logs: list[SelfCorrectionAttemptLog],
        verdict: SelfCorrectionVerdict,
    ) -> PipelineResult:
        logger.warning(
            "Human queue: draft did not pass self-correction in %d attempts (last verdict=%s)",
            len(logs),
            verdict.verdict,
        )
        return PipelineResult(
            outcome="human_queue",
            draft=draft,
            self_correction_logs=logs,
            human_queue_payload={
                "draft": {"subject": draft.subject, "body": draft.body},
                "verdict": verdict.verdict,
                "failed_checks": verdict.failed_checks,
                "escalation_reason": verdict.escalation_reason,
                "attempts": [log.to_dict() for log in logs],
            },
        )


# -----------------------------------------------------------------------------
# Stall detection (deterministic, called on a cron / scheduler)
# -----------------------------------------------------------------------------

_LEAD_TRANSCRIPT_ROLES = frozenset({"user", "lead", "customer"})


def _stall_primary_hours(*, soft_quote_mode: bool) -> int:
    return 2 if soft_quote_mode else 6


def _stall_backup_hours(*, soft_quote_mode: bool) -> int:
    """Second page (Jayden / backup operator): T+2× primary after commercial turn."""
    return 2 * _stall_primary_hours(soft_quote_mode=soft_quote_mode)


def _last_lead_transcript_turn(transcript: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Last turn authored by the lead (tester uses role ``user``; pipeline uses ``lead``)."""
    for turn in reversed(transcript):
        role = str(turn.get("role") or "").strip().lower()
        if role in _LEAD_TRANSCRIPT_ROLES:
            return turn
    return None


def post_quote_stall_phase(
    *,
    last_commercial_turn_at: Optional[datetime],
    now: datetime,
    soft_quote_mode: bool,
) -> Optional[str]:
    """``salesman`` = first stall window; ``backup`` = backup escalation (e.g. Jayden). None if no breach."""
    if last_commercial_turn_at is None:
        return None
    delta = now - last_commercial_turn_at
    primary = timedelta(hours=_stall_primary_hours(soft_quote_mode=soft_quote_mode))
    backup = timedelta(hours=_stall_backup_hours(soft_quote_mode=soft_quote_mode))
    if delta < primary:
        return None
    if delta < backup:
        return "salesman"
    return "backup"


def check_stall(
    *,
    last_commercial_turn_at: Optional[datetime],
    now: datetime,
    soft_quote_mode: bool,
) -> bool:
    """True once the primary stall window has passed (includes backup window)."""
    return (
        post_quote_stall_phase(
            last_commercial_turn_at=last_commercial_turn_at,
            now=now,
            soft_quote_mode=soft_quote_mode,
        )
        is not None
    )


def stall_page_payload(
    lead: LeadRecord,
    transcript: list[dict[str, Any]],
    last_quote: Optional[int],
    *,
    stall_escalation: str = "primary_salesman",
) -> dict[str, Any]:
    return {
        "lead_name": f"{lead.first_name} {lead.last_name}".strip(),
        "business": lead.business_name,
        "country": lead.country.value,
        "phone": lead.phone,
        "email": lead.email,
        "last_quote_offered": last_quote,
        "last_lead_message": _last_lead_transcript_turn(transcript),
        "conversation": transcript,
        "stall_escalation": stall_escalation,
    }


def evaluate_post_quote_stall(
    *,
    lead: LeadRecord,
    transcript: list[dict[str, Any]],
    last_commercial_turn_at: Optional[datetime],
    now: datetime,
    last_quote: Optional[int],
) -> Optional[dict[str, Any]]:
    """Return a stall payload: ``salesman_page`` at primary window, ``backup_page`` at backup window."""
    phase = post_quote_stall_phase(
        last_commercial_turn_at=last_commercial_turn_at,
        now=now,
        soft_quote_mode=lead.soft_quote_mode,
    )
    if phase is None:
        return None
    if phase == "salesman":
        return {
            "ai_conversation_state": "stalled_post_quote",
            "salesman_page": stall_page_payload(
                lead, transcript, last_quote, stall_escalation="primary_salesman"
            ),
        }
    return {
        "ai_conversation_state": "stalled_post_quote_backup",
        "backup_page": stall_page_payload(
            lead, transcript, last_quote, stall_escalation="backup_jayden"
        ),
    }
