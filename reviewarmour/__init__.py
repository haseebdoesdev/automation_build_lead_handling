"""ReviewArmour AI layer.

Three production modules:
  * commercial reasoning (deterministic, no LLM)
  * self-correction (Claude review of every outbound draft)
  * conversation drafting (Claude, gated by commercial + self-correction)
"""

from reviewarmour.commercial import CommercialEngine, CommercialResult, apply_pushback
from reviewarmour.conversation import (
    CommercialTurnLLMResult,
    ConversationModule,
    ConversationState,
    CustomerReviewRequestModule,
    OutboundDraft,
    OutboundPipeline,
    PipelineResult,
    acceptance_signal,
    check_stall,
    effective_quote_context,
    evaluate_post_quote_stall,
    inbound_indicates_meaningful_engagement,
    is_price_question_escalation,
    post_quote_stall_phase,
    pricing_turn_requested,
    regional_footer,
    resolve_meaningful_progress,
    should_escalate_inbound,
    should_invoke_commercial_turn_classifier,
    soft_pricing_fallback_hint,
    stall_page_payload,
    transcript_including_inbound,
    transcript_suggests_recent_price_quote,
)
from reviewarmour.errors import (
    CommercialPolicyError,
    ConfigError,
    LLMResponseError,
    LLMTransportError,
    ReviewArmourError,
)
from reviewarmour.models import (
    Channel,
    CommercialTurnMarker,
    Country,
    LeadRecord,
    NegotiationTriggerLogEntry,
    RecencyProfile,
    SelfCorrectionAttemptLog,
)
from reviewarmour.followup_cadence import (
    QUEUE_STATUS_PRIORITY,
    ScheduledNurtureFollowUp,
    build_morning_queue_brief,
    queue_priority_rank,
    schedule_nurture_follow_ups,
)
from reviewarmour.scheduling import defer_sunday_touch_to_monday_8am_est
from reviewarmour.self_correction import (
    SelfCorrectionModule,
    SelfCorrectionVerdict,
    extract_json_object,
    make_anthropic_client,
)
from reviewarmour.settings import LLMRuntime

__all__ = [
    "Channel",
    "CommercialEngine",
    "CommercialPolicyError",
    "CommercialResult",
    "CommercialTurnLLMResult",
    "CommercialTurnMarker",
    "ConfigError",
    "ConversationModule",
    "ConversationState",
    "Country",
    "acceptance_signal",
    "CustomerReviewRequestModule",
    "LLMResponseError",
    "LLMRuntime",
    "LLMTransportError",
    "LeadRecord",
    "NegotiationTriggerLogEntry",
    "OutboundDraft",
    "OutboundPipeline",
    "PipelineResult",
    "RecencyProfile",
    "ReviewArmourError",
    "SelfCorrectionAttemptLog",
    "SelfCorrectionModule",
    "SelfCorrectionVerdict",
    "apply_pushback",
    "check_stall",
    "QUEUE_STATUS_PRIORITY",
    "ScheduledNurtureFollowUp",
    "build_morning_queue_brief",
    "defer_sunday_touch_to_monday_8am_est",
    "queue_priority_rank",
    "schedule_nurture_follow_ups",
    "effective_quote_context",
    "evaluate_post_quote_stall",
    "extract_json_object",
    "inbound_indicates_meaningful_engagement",
    "is_price_question_escalation",
    "make_anthropic_client",
    "post_quote_stall_phase",
    "pricing_turn_requested",
    "regional_footer",
    "resolve_meaningful_progress",
    "should_escalate_inbound",
    "should_invoke_commercial_turn_classifier",
    "soft_pricing_fallback_hint",
    "stall_page_payload",
    "transcript_including_inbound",
    "transcript_suggests_recent_price_quote",
]
