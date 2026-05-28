"""Offline tests for timelineLanguage sanity in self-correction."""

from __future__ import annotations

from reviewarmour.prompt_templates import APPROVED_TIMELINE_PARAGRAPHS
from reviewarmour.self_correction import (
    SelfCorrectionVerdict,
    _sanitize_timeline_verdict,
    approved_timeline_paragraph_for_review,
    lead_demands_hard_calendar_date,
)


def test_sanitize_drops_spurious_timeline_failure_when_paragraph_present() -> None:
    body = (
        "Sam, the rate is $450 USD per review.\n\n"
        f"{APPROVED_TIMELINE_PARAGRAPHS['under_1_month']}\n\n"
        "Reply to move forward.\n\nJayden Faris / ReviewArmour"
    )
    v = SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=["timeline_language: paraphrased timeline window"],
        suggested_fixes=["use approved copy"],
        escalation_reason=None,
    )
    out = _sanitize_timeline_verdict(
        v,
        draft_body=body,
        approved_timeline_paragraph=APPROVED_TIMELINE_PARAGRAPHS["under_1_month"],
    )
    assert out.verdict == "pass"
    assert out.failed_checks == []


def test_sanitize_keeps_timeline_failure_when_paragraph_absent() -> None:
    v = SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=["timeline_language: missing approved copy"],
        suggested_fixes=[],
        escalation_reason=None,
    )
    out = _sanitize_timeline_verdict(
        v,
        draft_body="Usually about a month for removals.",
        approved_timeline_paragraph=APPROVED_TIMELINE_PARAGRAPHS["under_1_month"],
    )
    assert out.verdict == "fix"
    assert len(out.failed_checks) == 1


def test_sanitize_removes_only_timeline_among_other_failures() -> None:
    body = "Hi.\n\n" + APPROVED_TIMELINE_PARAGRAPHS["under_1_month"]
    v = SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=[
            "timeline_language: paraphrase",
            "copy_rules: email body exceeds word limit",
        ],
        suggested_fixes=[],
        escalation_reason=None,
    )
    out = _sanitize_timeline_verdict(
        v,
        draft_body=body,
        approved_timeline_paragraph=APPROVED_TIMELINE_PARAGRAPHS["under_1_month"],
    )
    assert out.verdict == "fix"
    assert out.failed_checks == ["copy_rules: email body exceeds word limit"]


def test_sanitize_accepts_hard_guarantee_paragraph_when_framing_is_hard_date() -> None:
    hg = APPROVED_TIMELINE_PARAGRAPHS["hard_guarantee_asked"]
    body = f"{hg}\n\nReply here.\n\nJayden Faris / ReviewArmour"
    v = SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=["timeline_language: wrong paragraph"],
        suggested_fixes=[],
        escalation_reason=None,
    )
    out = _sanitize_timeline_verdict(
        v, draft_body=body, approved_timeline_paragraph=hg
    )
    assert out.verdict == "pass"
    assert out.failed_checks == []


def test_lead_demands_hard_calendar_date_from_latest_turn() -> None:
    t = [
        {"role": "assistant", "body": "Price is $450"},
        {"role": "user", "body": "how long will it take?"},
        {"role": "assistant", "body": "two to four weeks..."},
        {"role": "lead", "body": "I need a hard date"},
    ]
    assert lead_demands_hard_calendar_date(t)
    para, key = approved_timeline_paragraph_for_review(t, "under_1_month")
    assert key == "hard_guarantee_asked"
    assert para == APPROVED_TIMELINE_PARAGRAPHS["hard_guarantee_asked"]


def test_lead_demands_hard_calendar_date_typo_specific() -> None:
    t = [{"role": "lead", "body": "i need a specifc date"}]
    assert lead_demands_hard_calendar_date(t)
    _, key = approved_timeline_paragraph_for_review(t, "under_1_month")
    assert key == "hard_guarantee_asked"


def test_lead_demands_hard_calendar_date_glued_thehard() -> None:
    t = [{"role": "lead", "body": "what isthehard date?"}]
    assert lead_demands_hard_calendar_date(t)


def test_approved_timeline_paragraph_recency_when_no_hard_date() -> None:
    t = [{"role": "user", "body": "how long will it take?"}]
    assert not lead_demands_hard_calendar_date(t)
    para, key = approved_timeline_paragraph_for_review(t, "under_1_month")
    assert key == "under_1_month"
    assert para == APPROVED_TIMELINE_PARAGRAPHS["under_1_month"]
