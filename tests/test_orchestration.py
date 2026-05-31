"""Deterministic orchestration tests.

These exercise pure-Python paths through the pipeline:
  * Hard inbound escalations (legal, post-payment, regulator).
  * Pricing intent → ``pricing_turn_requested`` / commercial path (no immediate escalate on "how much").
  * Acceptance signal detection (pattern match only; LLM still gates the send).
  * Stall detection windows (6h hard mode, 2h soft mode).
  * Sunday deferral.
  * No-progress 3-turn escalation.
  * JSON extraction and verdict schema validation.

No Anthropic calls. No fakes. Where a path would otherwise touch the LLM,
the test asserts on the early-return behavior of the pipeline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from reviewarmour.conversation import (
    ConversationState,
    OutboundDraft,
    OutboundPipeline,
    PipelineResult,
    acceptance_signal,
    check_stall,
    effective_quote_context,
    evaluate_post_quote_stall,
    inbound_indicates_meaningful_engagement,
    inbound_asks_signing_or_agreement_process,
    inbound_asks_success_rate_topic,
    is_price_question_escalation,
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
from reviewarmour.commercial import apply_pushback
from reviewarmour.errors import LLMResponseError
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.prompt_templates import APPROVED_TIMELINE_PARAGRAPHS
from reviewarmour.scheduling import defer_sunday_touch_to_monday_8am_est
from reviewarmour.self_correction import SelfCorrectionVerdict, extract_json_object
from reviewarmour.commercial import apply_pushback


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _us_lead(**overrides) -> LeadRecord:
    base = dict(
        lead_id="L1",
        first_name="Sam",
        last_name="Lee",
        business_name="Lee Plumbing",
        country=Country.US,
        phone="+15550001111",
        email="sam@example.com",
        gbp_link="https://g.page/lee-plumbing",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )
    base.update(overrides)
    return LeadRecord(**base)


class _NeverCalled:
    """Stand-in for the LLM modules. Any attribute access fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"LLM was unexpectedly invoked: .{name}")


def _pipeline_no_llm() -> OutboundPipeline:
    """Pipeline whose drafter/self-correction will raise if called.

    All tests in this module take inbound paths that escalate before any
    LLM call, so this is safe.
    """
    return OutboundPipeline(
        conversation=_NeverCalled(),  # type: ignore[arg-type]
        self_correction=_NeverCalled(),  # type: ignore[arg-type]
        use_llm_commercial_turn=False,
    )


def _pass_verdict() -> SelfCorrectionVerdict:
    return SelfCorrectionVerdict(
        verdict="pass",
        failed_checks=[],
        suggested_fixes=[],
        escalation_reason=None,
    )


def _pipeline_for_send() -> OutboundPipeline:
    class _SC:
        def review(self, **_kw: object) -> SelfCorrectionVerdict:
            return _pass_verdict()

    class _Conv:
        def draft(self, **_kw: object) -> OutboundDraft:
            return OutboundDraft(
                action="send",
                channel=Channel.EMAIL,
                subject="Re: pricing",
                body="The updated rate is $425 USD per review.",
            )

    return OutboundPipeline(
        conversation=_Conv(),  # type: ignore[arg-type]
        self_correction=_SC(),
        use_llm_quote_acceptance=False,
        use_llm_commercial_turn=False,
    )


# ---------------------------------------------------------------------------
# Inbound classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "How much would this run?",
        "send me a quote please",
        "what is the price per review?",
        "What's the price?",
        "Sure, what would be the cost?",
    ],
)
def test_price_question_detection(msg: str) -> None:
    assert is_price_question_escalation(msg) is True


@pytest.mark.parametrize(
    "msg, expect_prefix",
    [
        ("We are talking to our lawyer about this", "legal_escalation"),
        ("My attorney will follow up", "legal_escalation"),
        ("considering a lawsuit", "legal_escalation"),
        ("file a complaint to the BBB", "regulator"),
        ("I want to speak to the owner", "specific_person"),
    ],
)
def test_hard_escalation_triggers(msg: str, expect_prefix: str) -> None:
    reason = should_escalate_inbound(msg)
    assert reason is not None and reason.startswith(expect_prefix), reason


def test_post_payment_refund_only_when_in_post_pay_context() -> None:
    msg = "I want a refund"
    assert should_escalate_inbound(msg, post_payment_context=False) is None
    reason = should_escalate_inbound(msg, post_payment_context=True)
    assert reason is not None and reason.startswith("post_payment")


def test_acceptance_phrases() -> None:
    assert acceptance_signal("Let's do it.")
    assert acceptance_signal("im in")
    assert acceptance_signal("Go ahead and send the invoice")
    assert not acceptance_signal("I need more time")


def test_inbound_asks_signing_or_agreement_process() -> None:
    assert inbound_asks_signing_or_agreement_process(
        "like how can we sign an agreement?"
    )
    assert inbound_asks_signing_or_agreement_process("How do we sign?")
    assert inbound_asks_signing_or_agreement_process("When can we DocuSign?")
    assert not inbound_asks_signing_or_agreement_process("Let's do it.")
    assert not inbound_asks_signing_or_agreement_process(
        "yes at $450, send the agreement"
    )
    assert not inbound_asks_signing_or_agreement_process("How much is it?")


# ---------------------------------------------------------------------------
# Pipeline early-return paths (no LLM is called)
# ---------------------------------------------------------------------------


def test_pricing_turn_requested_from_inbound_and_flag() -> None:
    assert pricing_turn_requested(wants_price=False, inbound_message="How much per review?")
    assert pricing_turn_requested(wants_price=False, inbound_message="Sure, what would be the cost?")
    assert pricing_turn_requested(wants_price=False, inbound_message="send me a quote")
    assert pricing_turn_requested(wants_price=True, inbound_message=None)
    assert not pricing_turn_requested(wants_price=False, inbound_message="Hello there")
    assert not pricing_turn_requested(wants_price=False, inbound_message=None)


def test_pricing_turn_requested_negotiation_after_quote_in_transcript() -> None:
    t = [{"role": "assistant", "body": "For Park Family Dentistry, the rate is $500 USD per review."}]
    assert pricing_turn_requested(
        wants_price=False,
        inbound_message="could you lower it a bit",
        transcript=t,
        quoted_previously=False,
    )
    assert not pricing_turn_requested(
        wants_price=False,
        inbound_message="could you lower it a bit",
        transcript=[],
        quoted_previously=False,
    )


def test_pipeline_lawsuit_escalates_no_llm() -> None:
    pipe = _pipeline_no_llm()
    res = pipe.run(
        lead=_us_lead(),
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="Talking to my lawyer about this",
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.reason and res.draft.reason.startswith("legal_escalation")


def test_pipeline_three_no_progress_turns_escalates_no_llm() -> None:
    pipe = _pipeline_no_llm()
    state = ConversationState(consecutive_no_progress_turns=2)
    res = pipe.run(
        lead=_us_lead(),
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="still thinking",
        meaningful_progress=False,
        conversation_state=state,
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.reason == "no_progress_three_turns"


def test_pipeline_kill_switch_blocks_pricing_no_llm() -> None:
    pipe = _pipeline_no_llm()
    res = pipe.run(
        lead=_us_lead(ai_quote_allowed=False),
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        wants_price=True,
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.reason == "ai_quote_allowed_kill_switch"


def test_pipeline_below_floor_escalates_no_llm() -> None:
    pipe = _pipeline_no_llm()
    res = pipe.run(
        lead=_us_lead(),
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        wants_price=True,
        lead_requested_price_below_floor=True,
    )
    assert res.outcome == "escalate"
    assert res.commercial is not None and res.commercial.escalate is True
    assert res.state_updates.get("ai_conversation_state") == "escalated_to_human"


def test_pipeline_negotiation_pushback_at_step_2_escalates_no_llm() -> None:
    pipe = _pipeline_no_llm()
    lead = _us_lead(negotiation_step=2)
    t = [{"role": "assistant", "body": "Best I can do is $325 USD per review."}]
    res = pipe.run(
        lead=lead,
        transcript=t,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="can we go any lower",
        wants_price=False,
        quoted_previously=True,
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.reason == "negotiation_past_final_step"
    assert res.state_updates.get("ai_conversation_state") == "escalated_to_human"


def test_pipeline_records_single_pushback_step() -> None:
    pipe = _pipeline_for_send()
    lead = _us_lead(negotiation_step=0)
    t = [{"role": "assistant", "body": "The rate is $450 USD per review."}]
    res = pipe.run(
        lead=lead,
        transcript=t,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="That is still too expensive for us",
        wants_price=True,
        quoted_previously=True,
    )
    assert res.outcome == "send"
    assert lead.negotiation_step == 1
    assert len(lead.negotiation_triggers) == 1
    assert res.state_updates.get("negotiation_step") == 1
    assert res.commercial is not None
    assert res.commercial.authorized_quote_usd_per_review == 425


def test_pipeline_does_not_double_bump_crm_pre_applied_pushback() -> None:
    pipe = _pipeline_for_send()
    msg = "That is still too expensive for us"
    lead = apply_pushback(_us_lead(negotiation_step=0), msg)
    assert lead.negotiation_step == 1
    t = [{"role": "assistant", "body": "The rate is $450 USD per review."}]
    res = pipe.run(
        lead=lead,
        transcript=t,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message=msg,
        wants_price=True,
        quoted_previously=True,
    )
    assert res.outcome == "send"
    assert lead.negotiation_step == 1
    assert len(lead.negotiation_triggers) == 1
    assert res.state_updates.get("negotiation_step") == 1
    assert res.commercial is not None
    assert res.commercial.authorized_quote_usd_per_review == 425


def test_pipeline_does_not_double_bump_externally_set_step_without_triggers() -> None:
    """B4.2: negotiation_step=1 without apply_pushback must stay at step 1 pricing."""
    pipe = _pipeline_for_send()
    msg = "Can you do it for less?"
    lead = _us_lead(negotiation_step=1)
    assert len(lead.negotiation_triggers) == 0
    t = [
        {"role": "assistant", "body": "The rate is $450 USD per review."},
        {"role": "user", "body": msg},
    ]
    res = pipe.run(
        lead=lead,
        transcript=t,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message=msg,
        wants_price=True,
        quoted_previously=True,
    )
    assert res.outcome == "send"
    assert lead.negotiation_step == 1
    assert len(lead.negotiation_triggers) == 1
    assert res.commercial is not None
    assert res.commercial.authorized_quote_usd_per_review == 425


def test_bare_ok_after_non_quote_assistant_blocks_acceptance_llm() -> None:
    """E3: generic Ok after timeline text must not invoke acceptance classifier."""
    verdict = SelfCorrectionVerdict(
        verdict="pass",
        failed_checks=[],
        suggested_fixes=[],
        escalation_reason=None,
    )

    class _SC:
        def review(self, **_kw: object) -> SelfCorrectionVerdict:
            return verdict

    class _Conv:
        def detect_quote_acceptance_llm(self, *_a: object, **_k: object) -> bool:
            raise AssertionError("acceptance LLM must not run when guard blocks bare Ok")

        def draft(self, **_kw: object) -> OutboundDraft:
            return OutboundDraft(
                action="send",
                channel=Channel.EMAIL,
                subject="Re: timing",
                body="Following up on timing.",
            )

    pipe = OutboundPipeline(
        conversation=_Conv(),  # type: ignore[arg-type]
        self_correction=_SC(),
        use_llm_quote_acceptance=True,
        use_llm_commercial_turn=False,
    )
    hg = APPROVED_TIMELINE_PARAGRAPHS["under_1_month"]
    res = pipe.run(
        lead=_us_lead(),
        transcript=[
            {"role": "assistant", "body": "The rate is $450 USD per review."},
            {"role": "user", "body": "how long will it take?"},
            {"role": "assistant", "body": hg},
        ],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="Ok",
        quoted_previously=True,
    )
    assert res.state_updates.get("ai_conversation_state") != "quote_accepted"
    assert res.handoff_payload is None


# ---------------------------------------------------------------------------
# Stall detection
# ---------------------------------------------------------------------------


def test_stall_six_hours_hard_mode() -> None:
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    assert not check_stall(last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=False)
    assert check_stall(last_commercial_turn_at=t0, now=t0 + timedelta(hours=7), soft_quote_mode=False)


def test_stall_two_hours_soft_mode() -> None:
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    assert check_stall(last_commercial_turn_at=t0, now=t0 + timedelta(hours=3), soft_quote_mode=True)


def test_evaluate_post_quote_stall_payload() -> None:
    t0 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    payload = evaluate_post_quote_stall(
        lead=_us_lead(),
        transcript=[{"role": "lead", "body": "hmm"}],
        last_commercial_turn_at=t0,
        now=t0 + timedelta(hours=7),
        last_quote=425,
    )
    assert payload is not None
    assert payload["ai_conversation_state"] == "stalled_post_quote"
    page = payload["salesman_page"]
    assert page["last_quote_offered"] == 425
    assert page["business"] == "Lee Plumbing"
    assert "backup_page" not in payload


def test_stall_page_includes_last_lead_message() -> None:
    p = stall_page_payload(_us_lead(), [{"role": "lead", "body": "ok"}], 400)
    assert p["last_lead_message"] == {"role": "lead", "body": "ok"}
    assert p["stall_escalation"] == "primary_salesman"


def test_transcript_suggests_recent_price_quote_detects_usd() -> None:
    t = [
        {
            "role": "assistant",
            "body": "For Lee Plumbing Co, the rate is $450 USD per review.",
        }
    ]
    assert transcript_suggests_recent_price_quote(t)


def test_effective_quote_context_from_transcript_without_crm_flag() -> None:
    t = [{"role": "assistant", "body": "The rate is $450 USD per review."}]
    assert effective_quote_context(False, t)


def test_resolve_meaningful_progress_uses_engagement_heuristic() -> None:
    assert resolve_meaningful_progress("hello", None) is False
    assert resolve_meaningful_progress("the sky is grey", None) is False
    assert resolve_meaningful_progress("how much is it", None) is True
    assert resolve_meaningful_progress("what is the success rate", None) is True
    assert resolve_meaningful_progress("hello", True) is True
    assert resolve_meaningful_progress("hello", False) is False


def test_inbound_meaningful_engagement_examples() -> None:
    t: list = []
    assert not inbound_indicates_meaningful_engagement(
        "the sky is yellow", transcript=t, quoted_previously=False
    )
    assert inbound_indicates_meaningful_engagement(
        "https://g.page/demo", transcript=t, quoted_previously=False
    )
    assert inbound_indicates_meaningful_engagement(
        "how long until the review comes down", transcript=t, quoted_previously=False
    )
    assert inbound_indicates_meaningful_engagement(
        "I'd like to book a call", transcript=t, quoted_previously=False
    )


def test_off_topic_third_turn_escalates_without_llm() -> None:
    res = _pipeline_no_llm().run(
        lead=_us_lead(),
        transcript=[],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="the sky is green",
        conversation_state=ConversationState(consecutive_no_progress_turns=2),
        meaningful_progress=None,
    )
    assert res.outcome == "escalate"
    assert res.draft and res.draft.reason == "no_progress_three_turns"


def test_transcript_including_inbound_appends_synthetic_lead_turn() -> None:
    t = [{"role": "assistant", "body": "Hi there"}]
    out = transcript_including_inbound(
        t, "how long will it take?", Channel.EMAIL
    )
    assert len(out) == 2
    assert out[-1] == {
        "role": "lead",
        "body": "how long will it take?",
        "channel": "email",
    }


def test_transcript_including_inbound_skips_duplicate_tail() -> None:
    t = [{"role": "user", "body": "how long will it take?"}]
    out = transcript_including_inbound(
        t, "how long will it take?", Channel.EMAIL
    )
    assert out == t


def test_soft_pricing_fallback_hint_catches_loose_phrasing() -> None:
    assert soft_pricing_fallback_hint("what would that run me cost-wise")
    assert not soft_pricing_fallback_hint("Tuesday at 3 works")


def test_soft_pricing_hint_does_not_fire_on_success_rate_question() -> None:
    assert not soft_pricing_fallback_hint("what is the success rate")


def test_inbound_asks_success_rate_topic() -> None:
    assert inbound_asks_success_rate_topic("what is the success rate")
    assert inbound_asks_success_rate_topic("What's your success rate? ")
    assert inbound_asks_success_rate_topic("will the review come down?")
    assert not inbound_asks_success_rate_topic("what is the cost")
    assert not inbound_asks_success_rate_topic(
        "how much is it and what's your success rate"
    )
    assert not inbound_asks_success_rate_topic(
        "what is the cause? what is the success rate? what is the hard date?"
    )
    assert not inbound_asks_success_rate_topic(
        "what is the cost and what is the success rate?"
    )


def test_should_invoke_commercial_classifier_after_quote_or_soft_hint() -> None:
    t = [{"role": "assistant", "body": "$500 USD per review"}]
    assert should_invoke_commercial_turn_classifier("Sounds good", t, quoted_previously=False)
    assert should_invoke_commercial_turn_classifier(
        "Any room on the price?",
        [],
        quoted_previously=False,
    )
    assert not should_invoke_commercial_turn_classifier(
        "Thanks",
        [],
        quoted_previously=False,
    )
    assert not should_invoke_commercial_turn_classifier(
        "what is the success rate",
        t,
        quoted_previously=True,
    )


def test_acceptance_handoff_uses_transcript_price_without_quoted_previously_flag() -> None:
    """Post-quote acceptance is detected before stall counting; CRM quoted flag optional."""
    verdict = SelfCorrectionVerdict(
        verdict="pass",
        failed_checks=[],
        suggested_fixes=[],
        escalation_reason=None,
    )

    class _AccSC:
        def review(self, **_kw: object) -> SelfCorrectionVerdict:
            return verdict

    class _AccConv:
        def detect_quote_acceptance_llm(self, **_kw: object) -> bool:
            return False

    pipe = OutboundPipeline(
        conversation=_AccConv(),  # type: ignore[arg-type]
        self_correction=_AccSC(),
        use_llm_quote_acceptance=False,
    )
    transcript = [
        {
            "role": "assistant",
            "body": "For Lee Plumbing Co, the rate is $450 USD per review.",
        },
    ]
    res = pipe.run(
        lead=_us_lead(),
        transcript=transcript,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="sure this works, lets go ahead",
        quoted_previously=False,
        conversation_state=ConversationState(consecutive_no_progress_turns=2),
        meaningful_progress=False,
    )
    assert res.outcome == "send"
    assert res.handoff_payload and res.handoff_payload.get("type") == "quote_to_invoice"
    assert res.state_updates.get("ai_conversation_state") == "quote_accepted"
    assert res.state_updates.get("consecutive_no_progress_turns") == 0


def test_signing_process_question_never_calls_acceptance_llm() -> None:
    """How/when to sign is not quote acceptance; do not invoke the classifier."""
    verdict = SelfCorrectionVerdict(
        verdict="pass",
        failed_checks=[],
        suggested_fixes=[],
        escalation_reason=None,
    )

    class _SC:
        def review(self, **_kw: object) -> SelfCorrectionVerdict:
            return verdict

    class _Conv:
        def detect_quote_acceptance_llm(self, *_a: object, **_k: object) -> bool:
            raise AssertionError("acceptance LLM must not run for signing/process asks")

        def draft(self, **_kw: object) -> OutboundDraft:
            return OutboundDraft(
                action="send",
                channel=Channel.EMAIL,
                subject="Re: test",
                body="Here is how signing works.",
            )

    pipe = OutboundPipeline(
        conversation=_Conv(),  # type: ignore[arg-type]
        self_correction=_SC(),
        use_llm_quote_acceptance=True,
        use_llm_commercial_turn=False,
    )
    transcript = [
        {
            "role": "assistant",
            "body": "For Lee Plumbing Co, the rate is $450 USD per review.",
        },
    ]
    res = pipe.run(
        lead=_us_lead(),
        transcript=transcript,
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="like how can we sign an agreement?",
        quoted_previously=True,
    )
    assert res.outcome == "send"
    assert res.state_updates.get("ai_conversation_state") != "quote_accepted"


def test_success_rate_inbound_skips_commercial_turn_classifier() -> None:
    verdict = SelfCorrectionVerdict(
        verdict="pass",
        failed_checks=[],
        suggested_fixes=[],
        escalation_reason=None,
    )

    class _SC:
        def review(self, **_kw: object) -> SelfCorrectionVerdict:
            return verdict

    class _Conv:
        def classify_commercial_engine_turn_llm(self, *_a: object, **_k: object) -> None:
            raise AssertionError(
                "commercial classifier must not run for success-rate-only inbound"
            )

        def draft(self, **_kw: object) -> OutboundDraft:
            return OutboundDraft(
                action="send",
                channel=Channel.EMAIL,
                subject="Re: test",
                body="stub",
            )

    pipe = OutboundPipeline(
        conversation=_Conv(),  # type: ignore[arg-type]
        self_correction=_SC(),
        use_llm_quote_acceptance=False,
        use_llm_commercial_turn=True,
    )
    res = pipe.run(
        lead=_us_lead(),
        transcript=[
            {
                "role": "assistant",
                "body": "For Lee Plumbing Co, the rate is $450 USD per review.",
            },
        ],
        channel=Channel.EMAIL,
        sequence_stage="main",
        inbound_message="what is the success rate",
        quoted_previously=True,
    )
    assert res.outcome == "send"


# ---------------------------------------------------------------------------
# Footer + scheduling
# ---------------------------------------------------------------------------


def test_regional_footer_us_and_ca() -> None:
    us = regional_footer(Country.US)
    ca = regional_footer(Country.CA)
    assert "Miami" in us and "Brickell" in us
    assert "Toronto" in ca and "Bloor" in ca


def test_sunday_defers_to_monday_8am_est() -> None:
    sunday_utc = datetime(2026, 5, 10, 10, 30, tzinfo=timezone.utc)  # Sunday in NYC
    out = defer_sunday_touch_to_monday_8am_est(sunday_utc)
    local = out.astimezone(ZoneInfo("America/New_York"))
    assert local.weekday() == 0
    assert local.hour == 8


def test_non_sunday_unchanged() -> None:
    monday_utc = datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
    out = defer_sunday_touch_to_monday_8am_est(monday_utc)
    assert out == monday_utc


def test_escalate_draft_normalizes_missing_reason() -> None:
    """Model JSON may include reason: null; UI should not show [ESCALATE] None."""
    from reviewarmour.conversation import _validate_outbound_draft_payload

    d = _validate_outbound_draft_payload({"action": "escalate", "reason": None})
    assert d.reason == "escalate"
    d2 = _validate_outbound_draft_payload({"action": "escalate"})
    assert d2.reason == "escalate"
    d3 = _validate_outbound_draft_payload({"action": "escalate", "reason": "pricing dispute"})
    assert d3.reason == "pricing dispute"
    d4 = _validate_outbound_draft_payload({"action": "escalate", "reason": ""})
    assert d4.reason == "escalate"


def test_conversation_system_calls_out_success_rate_as_in_scope() -> None:
    from reviewarmour.prompt_templates import CONVERSATION_SYSTEM

    assert "Success rate / odds" in CONVERSATION_SYSTEM
    assert "do **not** escalate solely because they asked about success rate" in CONVERSATION_SYSTEM


def test_extract_json_object_strips_fence() -> None:
    raw = "```json\n{\"verdict\":\"pass\",\"failed_checks\":[],\"suggested_fixes\":[],\"escalation_reason\":null}\n```"
    d = extract_json_object(raw)
    assert d["verdict"] == "pass"


def test_extract_json_object_rejects_empty() -> None:
    with pytest.raises(LLMResponseError):
        extract_json_object("")


def test_extract_json_object_rejects_no_object() -> None:
    with pytest.raises(LLMResponseError):
        extract_json_object("no JSON here at all")


def test_verdict_schema_rejects_invalid_verdict() -> None:
    with pytest.raises(LLMResponseError):
        SelfCorrectionVerdict.from_dict(
            {"verdict": "approve", "failed_checks": [], "suggested_fixes": [], "escalation_reason": None}
        )


def test_verdict_schema_rejects_non_list_failed_checks() -> None:
    with pytest.raises(LLMResponseError):
        SelfCorrectionVerdict.from_dict(
            {"verdict": "fix", "failed_checks": "copy_rules", "suggested_fixes": [], "escalation_reason": None}
        )


def test_verdict_schema_accepts_valid_pass() -> None:
    v = SelfCorrectionVerdict.from_dict(
        {"verdict": "pass", "failed_checks": [], "suggested_fixes": [], "escalation_reason": None}
    )
    assert v.verdict == "pass"
    assert v.escalation_reason is None
