from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional

from reviewarmour.commercial import CommercialEngine, CommercialResult
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile, SelfCorrectionAttemptLog
from reviewarmour.prompt_templates import CONVERSATION_SYSTEM, CUSTOMER_REVIEW_REQUEST_SYSTEM
from reviewarmour.self_correction import DEFAULT_MODEL, SelfCorrectionModule, SelfCorrectionVerdict, extract_json_object

# Hard escalation patterns (inbound lead message text, lowercase match).
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

PRICE_SHOPPING_ESCALATION_PHRASES = (
    "how much",
    "how much?",
    "what is the price",
    "what's the price",
    "send me a quote",
    "send a quote",
)

ACCEPTANCE_PHRASES = (
    "let's do it",
    "lets do it",
    "send the invoice",
    "im in",
    "i'm in",
    "go ahead",
)

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


@dataclass
class ConversationState:
    ai_conversation_state: str = "active"
    consecutive_no_progress_turns: int = 0
    last_commercial_turn_at: Optional[datetime] = None

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


class ConversationModule:
    """
    Drafts outbound copy via Claude; every draft is reviewed by SelfCorrectionModule.
    """

    def __init__(
        self,
        messages_client: Any,
        *,
        model: str = DEFAULT_MODEL,
        system_prompt: str = CONVERSATION_SYSTEM,
    ) -> None:
        self._client = messages_client
        self._model = model
        self._system = system_prompt

    def _complete_json(self, user_payload: dict[str, Any]) -> dict[str, Any]:
        msg = self._client.create(
            model=self._model,
            max_tokens=1800,
            system=self._system,
            messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += block.text
        return extract_json_object(text)

    def draft(
        self,
        *,
        lead: LeadRecord,
        transcript: list[dict[str, Any]],
        channel: Channel,
        sequence_stage: str,
        commercial_output: Optional[CommercialResult],
        operator_directive: Optional[str] = None,
    ) -> OutboundDraft:
        payload = {
            "lead_record": lead_record_to_dict(lead),
            "conversation_transcript": transcript,
            "channel": channel.value,
            "sequence_stage": sequence_stage,
            "commercial_output": commercial_output.to_prompt_dict() if commercial_output else None,
            "operator_directive": operator_directive,
            "soft_quote_mode": lead.soft_quote_mode,
        }
        data = self._complete_json(payload)
        if data.get("action") == "escalate":
            return OutboundDraft(action="escalate", reason=str(data.get("reason", "escalate")))
        return OutboundDraft(
            action="send",
            channel=Channel(data["channel"]),
            subject=data.get("subject"),
            body=str(data.get("body", "")),
        )


class CustomerReviewRequestModule:
    def __init__(self, messages_client: Any, *, model: str = DEFAULT_MODEL) -> None:
        self._client = messages_client
        self._model = model

    def draft(
        self,
        *,
        customer: dict[str, Any],
        touch_number: int,
        channel: Channel,
        gbp_review_link: str,
    ) -> OutboundDraft:
        payload = {
            "customer_record": customer,
            "touch_number": touch_number,
            "channel": channel.value,
            "gbp_review_link": gbp_review_link,
        }
        msg = self._client.create(
            model=self._model,
            max_tokens=1200,
            system=CUSTOMER_REVIEW_REQUEST_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += block.text
        data = extract_json_object(text)
        if data.get("action") == "escalate":
            return OutboundDraft(action="escalate", reason=str(data.get("reason", "escalate")))
        return OutboundDraft(
            action="send",
            channel=Channel(data["channel"]),
            subject=data.get("subject"),
            body=str(data.get("body", "")),
        )


def _lower(text: str) -> str:
    return text.strip().lower()


def should_escalate_inbound(lead_message: str, *, post_payment_context: bool = False) -> Optional[str]:
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
    if "lawsuit" in s or "suing" in s:
        return "legal_escalation:lawsuit_related"
    return None


def is_price_question_escalation(lead_message: str) -> bool:
    s = _lower(lead_message)
    return any(p in s for p in PRICE_SHOPPING_ESCALATION_PHRASES)


def acceptance_signal(lead_message: str) -> bool:
    s = _lower(lead_message)
    return any(p in s for p in ACCEPTANCE_PHRASES)


class OutboundPipeline:
    """
    commercial (if pricing) → draft → self-correct → up to 2 re-draft loops.
    """

    MAX_FIX_RETRIES = 2

    def __init__(
        self,
        *,
        conversation: ConversationModule,
        self_correction: SelfCorrectionModule,
        commercial_engine: Optional[CommercialEngine] = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._conversation = conversation
        self._sc = self_correction
        self._commercial = commercial_engine or CommercialEngine()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

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
        meaningful_progress: bool = True,
    ) -> PipelineResult:
        cstate = conversation_state or ConversationState()
        logs: list[SelfCorrectionAttemptLog] = []
        now = self._now()

        if inbound_message is not None:
            if not meaningful_progress:
                cstate.consecutive_no_progress_turns += 1
                if cstate.consecutive_no_progress_turns >= 3:
                    return PipelineResult(
                        outcome="escalate",
                        draft=OutboundDraft(action="escalate", reason="no_progress_three_turns"),
                        state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
                    )
            else:
                cstate.consecutive_no_progress_turns = 0

            if is_price_question_escalation(inbound_message):
                return PipelineResult(
                    outcome="escalate",
                    draft=OutboundDraft(action="escalate", reason="price_question_escalate_to_salesman"),
                    state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
                )
            es = should_escalate_inbound(inbound_message, post_payment_context=post_payment_context)
            if es:
                return PipelineResult(
                    outcome="escalate",
                    draft=OutboundDraft(action="escalate", reason=es),
                    state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
                )
            if acceptance_signal(inbound_message) and quoted_previously:
                body = (
                    "Confirmed. Your specialist will send the removal brief and the "
                    "DocuSign within the hour. You'll pay only after the reviews are down.\n"
                    f"{regional_footer(lead.country)}"
                )
                subj = None
                if channel == Channel.EMAIL:
                    subj = f"Confirmed for {lead.business_name}"
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
                    },
                    handoff_payload={"type": "quote_to_invoice", "lead_id": lead.lead_id},
                )

        commercial: Optional[CommercialResult] = None
        if wants_price:
            commercial = self._commercial.evaluate_pricing(
                lead,
                wants_price=True,
                lead_requested_price_below_floor=lead_requested_price_below_floor,
                now=now,
            )
            if commercial.escalate and not commercial.request_gbp_first:
                return PipelineResult(
                    outcome="escalate",
                    commercial=commercial,
                    draft=OutboundDraft(
                        action="escalate",
                        reason=commercial.escalation_reason or "commercial_escalate",
                    ),
                    state_updates={"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns},
                )

        operator_directive: Optional[str] = None
        attempt = 0
        final_draft: Optional[OutboundDraft] = None

        while attempt < self.MAX_FIX_RETRIES + 1:
            attempt += 1
            draft = self._conversation.draft(
                lead=lead,
                transcript=transcript,
                channel=channel,
                sequence_stage=sequence_stage,
                commercial_output=commercial,
                operator_directive=operator_directive,
            )
            if draft.action == "escalate":
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
                transcript=transcript,
                commercial_snapshot=commercial.to_prompt_dict() if commercial else None,
                timeline_class=recency_to_timeline_class(lead.recency_profile),
                soft_quote_mode=lead.soft_quote_mode,
            )
            logs.append(
                SelfCorrectionAttemptLog(
                    attempt=attempt,
                    verdict=verdict.verdict,
                    failed_checks=verdict.failed_checks,
                    at=now,
                )
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
            if verdict.verdict == "fix" and attempt <= self.MAX_FIX_RETRIES:
                operator_directive = "; ".join(verdict.suggested_fixes) or "Fix copy-rule violations"
                continue
            return self._human_queue(draft, logs, verdict)

        if final_draft is None:
            return PipelineResult(outcome="human_queue", self_correction_logs=logs, human_queue_payload={"history": logs})

        state_updates: dict[str, Any] = {"consecutive_no_progress_turns": cstate.consecutive_no_progress_turns}
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

    def _human_queue(
        self,
        draft: OutboundDraft,
        logs: list[SelfCorrectionAttemptLog],
        verdict: SelfCorrectionVerdict,
    ) -> PipelineResult:
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


def check_stall(
    *,
    last_commercial_turn_at: Optional[datetime],
    now: datetime,
    soft_quote_mode: bool,
) -> bool:
    if last_commercial_turn_at is None:
        return False
    hours = 2 if soft_quote_mode else 6
    return now - last_commercial_turn_at >= timedelta(hours=hours)


def stall_page_payload(lead: LeadRecord, transcript: list[dict[str, Any]], last_quote: Optional[int]) -> dict[str, Any]:
    return {
        "lead_name": f"{lead.first_name} {lead.last_name}".strip(),
        "business": lead.business_name,
        "country": lead.country.value,
        "phone": lead.phone,
        "email": lead.email,
        "last_quote_offered": last_quote,
        "last_lead_message": transcript[-1] if transcript else None,
        "conversation": transcript,
    }


def evaluate_post_quote_stall(
    *,
    lead: LeadRecord,
    transcript: list[dict[str, Any]],
    last_commercial_turn_at: Optional[datetime],
    now: datetime,
    last_quote: Optional[int],
) -> Optional[dict[str, Any]]:
    """
    If the lead has been silent past the stall threshold after a commercial turn, return
    state + paging payload for the assigned salesman. Otherwise None.
    """
    if not check_stall(
        last_commercial_turn_at=last_commercial_turn_at,
        now=now,
        soft_quote_mode=lead.soft_quote_mode,
    ):
        return None
    return {
        "ai_conversation_state": "stalled_post_quote",
        "salesman_page": stall_page_payload(lead, transcript, last_quote),
    }
