"""Live self-correction tests against the real Anthropic API.

These run on every ``pytest`` invocation. They require ``ANTHROPIC_API_KEY``
in the environment and the ``anthropic`` Python package installed. There is
no mock fallback by design — the spec mandates a Claude review on every
outbound draft, and this test suite is what protects that contract.

Each test corresponds to one or more cases from the spec's
``SELF-CORRECTION`` test list.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

anthropic = pytest.importorskip("anthropic")

if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
    pytest.skip(
        "ANTHROPIC_API_KEY is required for production self-correction tests.",
        allow_module_level=True,
    )

from reviewarmour.conversation import lead_record_to_dict, regional_footer
from reviewarmour.models import Channel, Country, LeadRecord, RecencyProfile
from reviewarmour.self_correction import SelfCorrectionModule, make_anthropic_client


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return make_anthropic_client()


@pytest.fixture(scope="module")
def sc(client) -> SelfCorrectionModule:
    return SelfCorrectionModule(client)


@pytest.fixture
def us_lead() -> LeadRecord:
    return LeadRecord(
        lead_id="LIVE-US-1",
        first_name="Sam",
        last_name="Lee",
        business_name="Lee Plumbing",
        country=Country.US,
        phone="+15551110001",
        email="sam@example.com",
        gbp_link="https://g.page/lee-plumbing",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumber",
    )


@pytest.fixture
def ca_lead() -> LeadRecord:
    return LeadRecord(
        lead_id="LIVE-CA-1",
        first_name="Riya",
        last_name="Khan",
        business_name="Khan Bistro",
        country=Country.CA,
        phone="+14165550101",
        email="riya@example.com",
        gbp_link="https://g.page/khan-bistro",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="restaurant",
    )


def _review(
    sc: SelfCorrectionModule,
    *,
    lead: LeadRecord,
    body: str,
    subject: str | None = None,
    channel: Channel = Channel.EMAIL,
    commercial_snapshot=None,
    timeline_class: str = "under_1_month",
    transcript: list | None = None,
):
    return sc.review(
        draft_subject=subject,
        draft_body=body,
        channel=channel.value,
        lead_record=lead_record_to_dict(lead),
        transcript=transcript or [],
        commercial_snapshot=commercial_snapshot,
        timeline_class=timeline_class,
        soft_quote_mode=lead.soft_quote_mode,
    )


# ---------------------------------------------------------------------------
# PASS path
# ---------------------------------------------------------------------------


def test_clean_gbp_request_email_passes(sc, us_lead) -> None:
    lead = replace(us_lead, gbp_link=None)
    body = (
        f"Hey {lead.first_name},\n\n"
        f"Jayden from ReviewArmour. Before I can quote removal for {lead.business_name}, "
        "send me your Google Business Profile link.\n\n"
        f"{regional_footer(lead.country)}"
    )
    v = _review(
        sc,
        lead=lead,
        body=body,
        subject="Quick link needed",
        commercial_snapshot={
            "tier_id": "US-1",
            "authorized_quote_usd_per_review": None,
            "can_quote": False,
            "request_gbp_first": True,
            "floor": 300,
            "negotiation_step": 0,
        },
    )
    assert v.verdict == "pass", (v.verdict, v.failed_checks)


# ---------------------------------------------------------------------------
# FIX path (correctable copy/factual issues)
# ---------------------------------------------------------------------------


def test_exclamation_marks_yield_fix_or_escalate(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name}!\n\n"
        f"Quick question about {us_lead.business_name}. Can you send your GBP link!\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Quick question")
    assert v.verdict in ("fix", "escalate"), (v.verdict, v.failed_checks)
    assert v.failed_checks


def test_flagged_term_yields_fix(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        f"I flagged the reviews on {us_lead.business_name} that fit policy violation patterns.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Update")
    assert v.verdict in ("fix", "escalate"), (v.verdict, v.failed_checks)
    assert v.failed_checks


def test_wrong_business_name_yields_fix(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "I have your profile open for Acme Pizza right now.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Reviewing your profile")
    assert v.verdict in ("fix", "escalate"), (v.verdict, v.failed_checks)
    assert v.failed_checks


def test_hard_timeline_commitment_yields_fix(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "I guarantee these reviews will be removed by Friday at noon.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Timeline")
    assert v.verdict in ("fix", "escalate"), (v.verdict, v.failed_checks)
    assert v.failed_checks


def test_wrong_regional_footer_yields_fix(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        f"Following up on {us_lead.business_name}.\n\n"
        f"{regional_footer(Country.CA)}"  # CA footer on a US lead
    )
    v = _review(sc, lead=us_lead, body=body, subject="Following up")
    assert v.verdict in ("fix", "escalate"), (v.verdict, v.failed_checks)
    assert v.failed_checks


# ---------------------------------------------------------------------------
# ESCALATE path (always escalate, per spec verdict rules)
# ---------------------------------------------------------------------------


def test_specific_success_percentage_escalates(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "We have a 95% success rate on reviews like yours.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Success rate")
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)


def test_below_floor_quote_escalates(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "I can do this for $250 USD per review for you.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(
        sc,
        lead=us_lead,
        body=body,
        subject="Pricing",
        commercial_snapshot={
            "tier_id": "US-1",
            "authorized_quote_usd_per_review": 450,
            "floor": 300,
            "negotiation_step": 0,
            "can_quote": True,
            "request_gbp_first": False,
        },
    )
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)


def test_hidden_cost_80_escalates(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "Our cost to remove each review is $80, so we price accordingly.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Pricing")
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)


def test_hidden_cost_200_escalates(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "Older reviews have a $200 lead cost on our side.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Pricing")
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)


def test_legal_engagement_escalates(sc, us_lead) -> None:
    body = (
        f"Hey {us_lead.first_name},\n\n"
        "Happy to walk you through how to sue the reviewers under defamation law.\n\n"
        f"{regional_footer(us_lead.country)}"
    )
    v = _review(sc, lead=us_lead, body=body, subject="Legal next steps")
    assert v.verdict == "escalate", (v.verdict, v.failed_checks, v.escalation_reason)
