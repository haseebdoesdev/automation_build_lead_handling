"""Label inbound text and PipelineResult for the tester UI (mirrors reviewarmour rules)."""

from __future__ import annotations

from typing import Any

from reviewarmour.conversation import (
    PipelineResult,
    acceptance_signal,
    is_price_question_escalation,
    resolve_meaningful_progress,
    should_escalate_inbound,
)


def inspect_inbound(
    text: str,
    *,
    post_payment_context: bool,
    transcript: list | None = None,
    quoted_previously: bool = False,
) -> dict[str, Any]:
    """Return flags + raw escalate reason for UI badges."""
    s = (text or "").strip()
    esc = should_escalate_inbound(s, post_payment_context=post_payment_context)
    t: list = list(transcript or [])
    auto_meaningful = (
        bool(s)
        and resolve_meaningful_progress(
            s, None, transcript=t, quoted_previously=quoted_previously
        )
    )
    return {
        "inbound_asks_for_price": is_price_question_escalation(s),
        "acceptance_signal": acceptance_signal(s),
        "meaningful_engagement_auto": auto_meaningful,
        "escalate_match": esc is not None,
        "escalate_reason": esc,
        "legal_keywords": _matches_substrings(
            s.lower(),
            ("lawyer", "attorney", "lawsuit", "sue", "legal action", "defamation"),
        ),
        "post_pay_keywords": _matches_substrings(s.lower(), ("refund", "chargeback"))
        or ("cancel" in s.lower() and post_payment_context),
        "regulator_keywords": _matches_substrings(
            s.lower(),
            ("bbb", "better business", "ftc", "regulator", "complaint to google"),
        ),
        "owner_manager_keywords": _matches_substrings(
            s.lower(),
            ("speak to the owner", "speak to owner", "speak to the manager", "speak to manager"),
        ),
    }


def _matches_substrings(hay: str, needles: tuple[str, ...]) -> bool:
    return any(n in hay for n in needles)


def inspect_pipeline_result(result: PipelineResult) -> dict[str, Any]:
    """Flatten outcome into boolean flags for action bar."""
    out = {
        "outcome_send": result.outcome == "send",
        "outcome_escalate": result.outcome == "escalate",
        "outcome_human_queue": result.outcome == "human_queue",
        "handoff_quote_to_invoice": bool(
            result.handoff_payload and result.handoff_payload.get("type") == "quote_to_invoice"
        ),
        "state_quote_accepted": result.state_updates.get("ai_conversation_state") == "quote_accepted",
        "commercial_turn_timestamp_set": "last_commercial_turn_at" in result.state_updates,
        "stall_threshold_hours": result.state_updates.get("stall_threshold_hours"),
        "escalation_reason_in_updates": "escalation_reason" in result.state_updates,
        "draft_escalate_from_model": bool(
            result.draft and result.draft.action == "escalate"
        ),
        "had_commercial_result": result.commercial is not None,
        "commercial_escalated": bool(result.commercial and result.commercial.escalate),
        "authorized_quote_usd": (
            result.commercial.authorized_quote_usd_per_review
            if result.commercial
            else None
        ),
        "self_correction_attempts": len(result.self_correction_logs),
        "last_sc_verdicts": [log.verdict for log in result.self_correction_logs],
    }
    return out


def describe_result(result: PipelineResult) -> str:
    """Human-readable one-liner for activity log."""
    parts = [f"outcome={result.outcome}"]
    if result.draft:
        parts.append(f"draft.action={result.draft.action}")
        if result.draft.reason:
            parts.append(f"reason={result.draft.reason}")
    if result.handoff_payload:
        parts.append(f"handoff={result.handoff_payload}")
    if result.human_queue_payload:
        parts.append("human_queue_payload=present")
    if result.state_updates:
        parts.append(f"state_updates={result.state_updates}")
    if result.commercial and result.commercial.authorized_quote_usd_per_review:
        parts.append(f"authorized_quote={result.commercial.authorized_quote_usd_per_review}")
    return " | ".join(parts)
