"""Mutable session state for the GUI tester (one instance per browser client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from reviewarmour.conversation import ConversationState


@dataclass
class TesterSession:
    """Conversation + logging state for the harness."""

    transcript: list[dict[str, Any]] = field(default_factory=list)
    conversation_state: ConversationState = field(default_factory=ConversationState)
    activity: list[str] = field(default_factory=list)
    last_inbound_inspection: dict[str, Any] = field(default_factory=dict)
    last_pipeline_inspection: dict[str, Any] = field(default_factory=dict)
    last_pipeline_result_dict: Optional[dict[str, Any]] = None
    last_human_queue: Optional[dict[str, Any]] = None
    last_quote_usd: Optional[int] = None
    last_gbp_inspection: dict[str, Any] = field(default_factory=dict)
    #: Flow 18 nurture emails (T+30m / +60m / +24h) after first simulated send.
    nurture_follow_ups: list[Any] = field(default_factory=list)
    nurture_follow_up_fired: set[int] = field(default_factory=set)
    #: CRM-style status (e.g. ``queued_for_morning`` after Sunday-deferred F3).
    lead_status: Optional[str] = None
    #: Deterministic “wall clock” for pipeline / stall tests (UTC).
    virtual_now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def log(self, line: str) -> None:
        ts = self.virtual_now.isoformat()
        self.activity.append(f"[{ts}] {line}")

    def set_virtual_now(self, dt: datetime) -> None:
        self.virtual_now = dt.astimezone(timezone.utc)

    def advance_virtual_now(self, delta: timedelta) -> None:
        self.virtual_now = self.virtual_now + delta

    def reset(self) -> None:
        self.transcript.clear()
        self.conversation_state = ConversationState()
        self.activity.clear()
        self.last_inbound_inspection.clear()
        self.last_pipeline_inspection.clear()
        self.last_pipeline_result_dict = None
        self.last_human_queue = None
        self.last_quote_usd = None
        self.last_gbp_inspection.clear()
        self.nurture_follow_ups.clear()
        self.nurture_follow_up_fired.clear()
        self.lead_status = None
        self.virtual_now = datetime.now(timezone.utc)
        self.log("New conversation started.")

    def merge_state_updates(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        if "ai_conversation_state" in updates:
            self.conversation_state.ai_conversation_state = str(
                updates["ai_conversation_state"]
            )
        if "consecutive_no_progress_turns" in updates:
            self.conversation_state.consecutive_no_progress_turns = int(
                updates["consecutive_no_progress_turns"]
            )
        if "last_commercial_turn_at" in updates:
            raw = updates["last_commercial_turn_at"]
            if isinstance(raw, str):
                self.conversation_state.last_commercial_turn_at = datetime.fromisoformat(
                    raw.replace("Z", "+00:00")
                )
        if "lead_status" in updates:
            self.lead_status = str(updates["lead_status"])

def pipeline_result_to_dict(pr: Any) -> dict[str, Any]:
    """JSON-serializable snapshot for Human tab / export."""
    out: dict[str, Any] = {
        "outcome": pr.outcome,
        "draft": None,
        "commercial": None,
        "self_correction_logs": [],
        "human_queue_payload": pr.human_queue_payload,
        "state_updates": dict(pr.state_updates or {}),
        "handoff_payload": pr.handoff_payload,
    }
    if pr.draft:
        out["draft"] = {
            "action": pr.draft.action,
            "channel": pr.draft.channel.value if pr.draft.channel else None,
            "subject": pr.draft.subject,
            "body": pr.draft.body,
            "reason": pr.draft.reason,
        }
    if pr.commercial:
        c = pr.commercial
        out["commercial"] = {
            "tier_id": c.tier_id,
            "tier": c.tier.value if hasattr(c, "tier") and c.tier else None,
            "gbp_category": c.gbp_category.value if c.gbp_category else None,
            "volume_bracket": c.volume_bracket.value if c.volume_bracket else None,
            "range_low_usd": c.range_low_usd,
            "range_high_usd": c.range_high_usd,
            "floor_usd": c.floor_usd,
            "authorized_quote_usd_per_review": c.authorized_quote_usd_per_review,
            "negotiation_step": c.negotiation_step,
            "can_quote": c.can_quote,
            "escalate": c.escalate,
            "escalation_reason": c.escalation_reason,
            "request_gbp_first": c.request_gbp_first,
            "request_category_first": getattr(c, "request_category_first", False),
            "phone_call_threshold_triggered": getattr(c, "phone_call_threshold_triggered", False),
            "salesman_recommended_range": (
                list(c.salesman_recommended_range)
                if getattr(c, "salesman_recommended_range", None)
                else None
            ),
            "salesman_recommended_opening_usd": getattr(
                c, "salesman_recommended_opening_usd", None
            ),
            "reasoning_summary": getattr(c, "reasoning_summary", ""),
            "soft_quote_mode": getattr(c, "soft_quote_mode", False),
            "soft_quote_range": (
                list(c.soft_quote_range) if getattr(c, "soft_quote_range", None) else None
            ),
        }
    for log in pr.self_correction_logs:
        out["self_correction_logs"].append(log.to_dict())
    return out
