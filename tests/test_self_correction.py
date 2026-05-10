"""Self-correction behavior covered with scripted Claude responses (no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.self_correction import SelfCorrectionModule


class _TB:
    __slots__ = ("type", "text")

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class FakeMessagesAPI:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(content=[_TB(self._responses.pop(0))])


def _lead() -> LeadRecord:
    return LeadRecord(
        lead_id="L1",
        first_name="Sam",
        last_name="Lee",
        business_name="Lee Plumbing",
        country=Country.US,
        phone="+1",
        email="a@b.co",
        gbp_link="https://g.page/x",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )


@pytest.mark.parametrize(
    "verdict_json",
    [
        '{"verdict":"fix","failed_checks":["copy_rules: em dash"],"suggested_fixes":["replace em dash"],"escalation_reason":null}',
        '{"verdict":"fix","failed_checks":["copy_rules: exclamation"],"suggested_fixes":["remove exclamation"],"escalation_reason":null}',
        '{"verdict":"fix","failed_checks":["copy_rules: banned term"],"suggested_fixes":["use identified not flagged"],"escalation_reason":null}',
        '{"verdict":"fix","failed_checks":["factual_accuracy: business name"],"suggested_fixes":["use Lee Plumbing"],"escalation_reason":null}',
        '{"verdict":"fix","failed_checks":["timeline_language: commitment"],"suggested_fixes":["use approved window copy"],"escalation_reason":null}',
        '{"verdict":"fix","failed_checks":["regional_footer: mismatch"],"suggested_fixes":["use US footer"],"escalation_reason":null}',
    ],
)
def test_self_correction_fix_verdicts(verdict_json: str) -> None:
    sc = SelfCorrectionModule(FakeMessagesAPI([verdict_json]))
    lead = _lead()
    v = sc.review(
        draft_subject="Hi",
        draft_body="Test body",
        channel=Channel.EMAIL.value,
        lead_record={
            "first_name": lead.first_name,
            "business_name": lead.business_name,
            "country": lead.country.value,
        },
        transcript=[],
        commercial_snapshot={
            "tier_id": "US-1",
            "authorized_quote_usd_per_review": 450,
            "floor": 300,
            "negotiation_step": 0,
        },
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "fix"


@pytest.mark.parametrize(
    "verdict_json",
    [
        '{"verdict":"escalate","failed_checks":["success_rate: percentage"],"suggested_fixes":[],"escalation_reason":"numeric success claim"}',
        '{"verdict":"escalate","failed_checks":["pricing: below floor"],"suggested_fixes":[],"escalation_reason":"below floor"}',
        '{"verdict":"escalate","failed_checks":["hidden_cost_leak: 80"],"suggested_fixes":[],"escalation_reason":"cost leak"}',
        '{"verdict":"escalate","failed_checks":["hidden_cost_leak: 200"],"suggested_fixes":[],"escalation_reason":"cost leak"}',
    ],
)
def test_self_correction_escalate_verdicts(verdict_json: str) -> None:
    sc = SelfCorrectionModule(FakeMessagesAPI([verdict_json]))
    lead = _lead()
    v = sc.review(
        draft_subject=None,
        draft_body="x",
        channel=Channel.SMS.value,
        lead_record={"first_name": lead.first_name, "business_name": lead.business_name, "country": "US"},
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "escalate"


def test_self_correction_pass() -> None:
    payload = json.dumps(
        {
            "verdict": "pass",
            "failed_checks": [],
            "suggested_fixes": [],
            "escalation_reason": None,
        }
    )
    sc = SelfCorrectionModule(FakeMessagesAPI([payload]))
    lead = _lead()
    v = sc.review(
        draft_subject="s",
        draft_body="ok",
        channel="email",
        lead_record={"first_name": lead.first_name, "business_name": lead.business_name, "country": "US"},
        transcript=[],
        commercial_snapshot=None,
        timeline_class="under_1_month",
        soft_quote_mode=False,
    )
    assert v.verdict == "pass"
