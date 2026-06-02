"""Tests for post-call follow-up sequences (Section 15)."""

from datetime import datetime, timedelta, timezone

import pytest

from reviewarmour.followup_cadence import (
    schedule_post_call_accelerated,
    schedule_post_call_follow_ups,
    schedule_post_call_standard,
)
from reviewarmour.models import (
    CallOutcome,
    Channel,
    Country,
    LeadRecord,
    RecencyProfile,
)


@pytest.fixture
def us_lead():
    return LeadRecord(
        lead_id="test-pc-1",
        first_name="John",
        last_name="Smith",
        business_name="Acme Plumbing",
        country=Country.US,
        phone="+15551234567",
        email="john@acme.com",
        gbp_link="https://maps.google.com/acme",
        review_count=2,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="plumbing",
    )


@pytest.fixture
def ca_lead():
    return LeadRecord(
        lead_id="test-pc-2",
        first_name="Jane",
        last_name="Doe",
        business_name="Jane Dental",
        country=Country.CA,
        phone="+14161234567",
        email="jane@dental.ca",
        gbp_link=None,
        review_count=1,
        recency_profile=RecencyProfile.ALL_UNDER_1_MONTH,
        business_category="dental",
    )


class TestStandardSequence:
    """G2: Outcome 'undecided' → standard sequence at T+24h, T+72h, T+7d, T+14d."""

    def test_four_touches(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        assert len(touches) == 4

    def test_timing(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        assert touches[0].fire_at_utc == now + timedelta(hours=24)
        assert touches[1].fire_at_utc == now + timedelta(hours=72)
        assert touches[2].fire_at_utc == now + timedelta(days=7)
        assert touches[3].fire_at_utc == now + timedelta(days=14)

    def test_touch_1_multi_channel(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        assert Channel.EMAIL in touches[0].channels
        assert Channel.SMS in touches[0].channels
        assert touches[0].sms_body is not None

    def test_touches_2_to_4_email_only(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        for t in touches[1:]:
            assert touches[1].channels == [Channel.EMAIL]
            assert t.sms_body is None

    def test_us_footer_in_body(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        assert "Miami" in touches[0].body

    def test_ca_footer_in_body(self, ca_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, ca_lead)
        assert "Toronto" in touches[0].body

    def test_first_name_in_body(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        for t in touches:
            assert "John" in t.body

    def test_business_name_in_body(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(now, us_lead)
        for t in touches:
            assert "Acme Plumbing" in t.body


class TestAcceleratedSequence:
    """G4: Outcome 'no_show' → accelerated sequence at T+15m, T+2h, T+24h, T+72h."""

    def test_four_touches(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_accelerated(now, us_lead)
        assert len(touches) == 4

    def test_timing(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_accelerated(now, us_lead)
        assert touches[0].fire_at_utc == now + timedelta(minutes=15)
        assert touches[1].fire_at_utc == now + timedelta(hours=2)
        assert touches[2].fire_at_utc == now + timedelta(hours=24)
        assert touches[3].fire_at_utc == now + timedelta(hours=72)

    def test_touch_1_sms_only(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_accelerated(now, us_lead)
        assert touches[0].channels == [Channel.SMS]

    def test_touches_2_to_4_multi_channel(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_accelerated(now, us_lead)
        for t in touches[1:]:
            assert Channel.SMS in t.channels
            assert Channel.EMAIL in t.channels

    def test_just_missed_you_framing(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_accelerated(now, us_lead)
        assert "just missed you" in touches[0].body.lower() or "missed you" in touches[0].sms_body.lower()


class TestCallOutcomeRouting:
    """Route to correct sequence based on CallOutcome."""

    def test_won_returns_empty(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        assert schedule_post_call_follow_ups(CallOutcome.WON, now, us_lead) == []

    def test_lost_hard_returns_empty(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        assert schedule_post_call_follow_ups(CallOutcome.LOST_HARD, now, us_lead) == []

    def test_undecided_returns_standard(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_follow_ups(CallOutcome.UNDECIDED, now, us_lead)
        assert len(touches) == 4
        assert touches[0].fire_at_utc == now + timedelta(hours=24)

    def test_no_show_returns_accelerated(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_follow_ups(CallOutcome.NO_SHOW, now, us_lead)
        assert len(touches) == 4
        assert touches[0].fire_at_utc == now + timedelta(minutes=15)

    def test_unreachable_returns_accelerated(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_follow_ups(CallOutcome.UNREACHABLE, now, us_lead)
        assert len(touches) == 4
        assert touches[0].fire_at_utc == now + timedelta(minutes=15)

    def test_callback_requested_anchors_at_callback_time(self, us_lead):
        now = datetime(2026, 6, 2, 14, 0, 0, tzinfo=timezone.utc)
        cb = now + timedelta(hours=48)
        touches = schedule_post_call_follow_ups(
            CallOutcome.CALLBACK_REQUESTED, now, us_lead, callback_datetime_utc=cb
        )
        assert len(touches) == 4
        assert touches[0].fire_at_utc == cb + timedelta(hours=24)


class TestSundayDeferral:
    """G5: T+24h touch landing on Sunday auto-defers to Monday 08:00 EST."""

    def test_sunday_deferred_to_monday(self, us_lead):
        # Saturday 14:00 UTC -> T+24h = Sunday 14:00 UTC (Sunday 10:00 ET)
        sat = datetime(2026, 5, 30, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(sat, us_lead)
        t1 = touches[0]
        assert t1.raw_fire_at_utc is not None  # Was deferred
        assert t1.state_updates.get("lead_status") == "queued_for_morning"
        assert t1.fire_at_utc.weekday() == 0  # Monday

    def test_non_sunday_not_deferred(self, us_lead):
        # Monday 14:00 UTC -> T+24h = Tuesday 14:00 UTC
        mon = datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone.utc)
        touches = schedule_post_call_standard(mon, us_lead)
        t1 = touches[0]
        assert t1.raw_fire_at_utc is None
        assert t1.state_updates == {}
