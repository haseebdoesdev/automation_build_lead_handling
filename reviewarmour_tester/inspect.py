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
    """Flatten outcome into boolean flags for action bar.

    Spec v2: expose phone-call threshold, T1-exception path, gbp_category,
    pricing tier, and request_category_first flags so the UI shows whether
    the engine took the written-quote path vs phone-route vs ask-first.
    """
    c = result.commercial
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
        "had_commercial_result": c is not None,
        "commercial_escalated": bool(c and c.escalate),
        "authorized_quote_usd": c.authorized_quote_usd_per_review if c else None,
        # Spec v2 additions
        "tier": c.tier.value if (c and hasattr(c, "tier") and c.tier) else None,
        "gbp_category": (
            c.gbp_category.value if (c and c.gbp_category) else None
        ),
        "phone_call_threshold_triggered": bool(
            c and getattr(c, "phone_call_threshold_triggered", False)
        ),
        "salesman_recommended_opening_usd": (
            c.salesman_recommended_opening_usd if c else None
        ),
        "request_gbp_first": bool(c and c.request_gbp_first),
        "request_category_first": bool(
            c and getattr(c, "request_category_first", False)
        ),
        "soft_quote_mode": bool(c and getattr(c, "soft_quote_mode", False)),
        "soft_quote_range": (
            list(c.soft_quote_range)
            if (c and getattr(c, "soft_quote_range", None))
            else None
        ),
        "adaptive_reasoning_summary": (
            c.reasoning_summary if (c and getattr(c, "reasoning_summary", "")) else ""
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
    c = result.commercial
    if c:
        if hasattr(c, "tier") and c.tier:
            parts.append(f"tier={c.tier.value}")
        if c.authorized_quote_usd_per_review:
            parts.append(f"authorized_quote=${c.authorized_quote_usd_per_review}")
        if getattr(c, "phone_call_threshold_triggered", False):
            parts.append(
                f"phone_route (recommend=${c.salesman_recommended_opening_usd})"
            )
        if c.request_gbp_first:
            parts.append("request_gbp_first")
        if getattr(c, "request_category_first", False):
            parts.append("request_category_first")
    return " | ".join(parts)
