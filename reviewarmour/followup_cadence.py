"""
Nurture follow-up scheduling (Flow 18): T+30m, T+60m, T+24h from an anchor time.

Copy is chosen by ``channel`` (email vs SMS): email uses Re: subjects and full footer;
SMS uses no subject and compact sign-off (under length limits in templates).

Follow-up 3 deferred from Sunday (America/New_York) to Monday 08:00 EST; deferred
touches set ``lead_status`` to ``queued_for_morning`` for morning batch / brief.

Morning queue briefs are formatted deterministically from ``LeadRecord`` + transcript
with no LLM; unknown fields use the literal ``not stated``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from reviewarmour.models import (
    CallOutcome,
    Channel,
    Country,
    LeadRecord,
    ScheduledPostCallTouch,
)
from reviewarmour.scheduling import EST, defer_sunday_touch_to_monday_8am_est

_FOLLOWUP_1_SUBJECT = "Re: {business_name} - Google reviews"
_FOLLOWUP_1_BODY = (
    "Hi {first_name},\n\n"
    "Checking whether you saw my last note on policy-violating Google reviews for "
    "{business_name}. Reply here when you have a moment and we can go over next steps.\n\n"
    "{footer}"
)

_FOLLOWUP_2_SUBJECT = "Re: {business_name} - Following up"
_FOLLOWUP_2_BODY = (
    "Hi {first_name},\n\n"
    "Bumping this in case it slipped down the inbox. If you want to talk through "
    "options for {business_name}, reply here.\n\n"
    "{footer}"
)

_FOLLOWUP_3_SUBJECT = "Re: {business_name} - Still here if you need us"
_FOLLOWUP_3_BODY = (
    "Hi {first_name},\n\n"
    "Last note from me on the review removal side for {business_name}. If the timing "
    "is not right, no pressure. If you want to move forward, reply here or ask for a quick "
    "call with a specialist.\n\n"
    "{footer}"
)

FOOTER_US = (
    "Jayden Faris / ReviewArmour / +1 (786) 464-3783\n"
    "1395 Brickell Avenue, Suite 800, Miami, FL 33131"
)
FOOTER_CA = (
    "Jayden Faris / ReviewArmour / +1 416-432-5439\n"
    "2 Bloor St E Suite 3500, Toronto, Ontario, Canada M4W 1A8"
)

_SMS_FOOTER_US = "Jayden/ReviewArmour +17864643783"
_SMS_FOOTER_CA = "Jayden/ReviewArmour +14164325439"

_SMS_FOLLOWUP_1_BODY = (
    "Hi {first_name}, checking you saw my note on Google reviews for {business_name}. "
    "Reply when you can. {footer}"
)
_SMS_FOLLOWUP_2_BODY = (
    "Hi {first_name}, bumping this for {business_name}. Reply if you want options. {footer}"
)
_SMS_FOLLOWUP_3_BODY = (
    "Hi {first_name}, last note on review removal for {business_name}. "
    "Reply if timing works. {footer}"
)


def _regional_footer(country: Country) -> str:
    return FOOTER_US if country == Country.US else FOOTER_CA


def _sms_footer(country: Country) -> str:
    return _SMS_FOOTER_US if country == Country.US else _SMS_FOOTER_CA


def _format_followup_text(template: str, lead: LeadRecord) -> str:
    return template.format(
        first_name=lead.first_name,
        last_name=lead.last_name,
        business_name=lead.business_name,
        footer=_regional_footer(lead.country),
    )


def _format_sms_followup(template: str, lead: LeadRecord) -> str:
    return template.format(
        first_name=lead.first_name,
        business_name=lead.business_name,
        footer=_sms_footer(lead.country),
    )


def _same_utc_instant(a: datetime, b: datetime) -> bool:
    return a.astimezone(timezone.utc).replace(microsecond=0) == b.astimezone(
        timezone.utc
    ).replace(microsecond=0)


# Highest urgency first (lower rank = process sooner).
QUEUE_STATUS_PRIORITY: tuple[str, ...] = (
    "escalated_to_human",
    "stalled_post_quote_backup",
    "stalled_post_quote",
    "quote_accepted",
    "quoted_pending_acceptance",
    "active_nurture",
    "queued_for_morning",
    "new",
)


def queue_priority_rank(lead_status: Optional[str]) -> int:
    """Sort key: lower is higher priority. Unknown statuses sort last."""
    if not lead_status:
        return len(QUEUE_STATUS_PRIORITY) + 10
    try:
        return QUEUE_STATUS_PRIORITY.index(lead_status)
    except ValueError:
        return len(QUEUE_STATUS_PRIORITY) + 5


@dataclass(frozen=True)
class ScheduledNurtureFollowUp:
    """One scheduled nurture touch after first outbound (anchor = first send time, UTC)."""

    index: int
    fire_at_utc: datetime
    channel: Channel
    subject: Optional[str]
    body: str
    state_updates: dict[str, Any] = field(default_factory=dict)
    raw_fire_at_utc: Optional[datetime] = None  # set for F3 when Sunday-deferred


def schedule_nurture_follow_ups(
    anchor_first_outbound_utc: datetime,
    lead: LeadRecord,
    *,
    channel: Channel = Channel.EMAIL,
) -> list[ScheduledNurtureFollowUp]:
    """
    Build follow-up 1 (T+30m), 2 (T+60m), 3 (T+24h) from the first outbound timestamp.

    If follow-up 3's raw time falls on Sunday in America/New_York, it is moved to
    Monday 08:00 EST and ``state_updates`` include ``lead_status=queued_for_morning``.
    """
    if anchor_first_outbound_utc.tzinfo is None:
        anchor = anchor_first_outbound_utc.replace(tzinfo=timezone.utc)
    else:
        anchor = anchor_first_outbound_utc

    t1 = anchor + timedelta(minutes=30)
    t2 = anchor + timedelta(minutes=60)
    raw_t3 = anchor + timedelta(hours=24)
    eff_t3 = defer_sunday_touch_to_monday_8am_est(raw_t3)

    if channel == Channel.SMS:
        bu1 = _format_sms_followup(_SMS_FOLLOWUP_1_BODY, lead)
        bu2 = _format_sms_followup(_SMS_FOLLOWUP_2_BODY, lead)
        bu3 = _format_sms_followup(_SMS_FOLLOWUP_3_BODY, lead)
        su1 = su2 = su3 = None
    else:
        su1 = _format_followup_text(_FOLLOWUP_1_SUBJECT, lead)
        bu1 = _format_followup_text(_FOLLOWUP_1_BODY, lead)
        su2 = _format_followup_text(_FOLLOWUP_2_SUBJECT, lead)
        bu2 = _format_followup_text(_FOLLOWUP_2_BODY, lead)
        su3 = _format_followup_text(_FOLLOWUP_3_SUBJECT, lead)
        bu3 = _format_followup_text(_FOLLOWUP_3_BODY, lead)

    if _same_utc_instant(eff_t3, raw_t3):
        f3_updates = {}
        raw_for_meta = None
    else:
        f3_updates = {
            "lead_status": "queued_for_morning",
            "follow_up_3_deferred_from_utc": raw_t3.isoformat(),
            "follow_up_3_reason": "sunday_blackout_est",
        }
        raw_for_meta = raw_t3

    return [
        ScheduledNurtureFollowUp(
            1, t1, channel, su1, bu1, {}, None
        ),
        ScheduledNurtureFollowUp(
            2, t2, channel, su2, bu2, {}, None
        ),
        ScheduledNurtureFollowUp(
            3, eff_t3, channel, su3, bu3, f3_updates, raw_for_meta
        ),
    ]


def _touchpoint_counts(transcript: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Total touches (non-system), n_email, n_sms (WhatsApp counted alongside SMS)."""
    n_email = n_sms = 0
    n = 0
    for row in transcript:
        role = str(row.get("role") or "").lower()
        if role == "system":
            continue
        n += 1
        ch = str(row.get("channel") or "").lower()
        if ch == Channel.EMAIL.value:
            n_email += 1
        elif ch in (Channel.SMS.value, Channel.WHATSAPP.value):
            n_sms += 1
    return n, n_email, n_sms


def _n_lead_replies(transcript: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in transcript
        if str(row.get("role") or "").lower() in ("lead", "user")
    )


# ---------------------------------------------------------------------------
# Post-call follow-up templates (Section 15)
# ---------------------------------------------------------------------------

# Standard sequence (undecided) — email templates
_PC_STD_1_SUBJECT = "Re: {business_name} - Great speaking with you"
_PC_STD_1_BODY = (
    "Hi {first_name},\n\n"
    "Good speaking earlier about Google review removal for {business_name}. "
    "If you are ready to move forward, reply here and we will get started right away.\n\n"
    "{footer}"
)
_PC_STD_2_SUBJECT = "Re: {business_name} - Quick observation"
_PC_STD_2_BODY = (
    "Hi {first_name},\n\n"
    "One thing worth noting: the sooner policy-violating reviews are addressed for "
    "{business_name}, the less they weigh on your overall rating. Happy to walk through "
    "next steps when you are ready.\n\n"
    "{footer}"
)
_PC_STD_3_SUBJECT = "Re: {business_name} - Business impact"
_PC_STD_3_BODY = (
    "Hi {first_name},\n\n"
    "Every week those reviews stay up, {business_name} loses potential customers who check "
    "Google before calling. If the timing works, reply here and we will handle the rest.\n\n"
    "{footer}"
)
_PC_STD_4_SUBJECT = "Re: {business_name} - Closing the loop"
_PC_STD_4_BODY = (
    "Hi {first_name},\n\n"
    "Last note from me on Google review removal for {business_name}. If you want to revisit "
    "this later, you know where to find us. Otherwise I will close your file on our end.\n\n"
    "{footer}"
)

# Standard sequence — SMS templates
_PC_STD_SMS_1 = (
    "Hi {first_name}, good call earlier re {business_name} reviews. "
    "Reply when ready to move forward. {footer}"
)
_PC_STD_SMS_2 = (
    "Hi {first_name}, quick note on {business_name}: sooner those reviews come down, "
    "the better for your rating. Reply if ready. {footer}"
)
_PC_STD_SMS_3 = (
    "Hi {first_name}, every week those reviews stay up costs {business_name} customers. "
    "Reply here to get started. {footer}"
)
_PC_STD_SMS_4 = (
    "Hi {first_name}, last note on review removal for {business_name}. "
    "Reply if you want to revisit. {footer}"
)

# Accelerated sequence (no_show / unreachable) — SMS templates
_PC_ACC_SMS_1 = (
    "Hi {first_name}, just missed you for the {business_name} call. "
    "Reply with a good time and we will ring you right back. {footer}"
)
_PC_ACC_SMS_2 = (
    "Hi {first_name}, tried reaching you earlier re {business_name} reviews. "
    "Reply here or pick a slot and we will call at your convenience. {footer}"
)
_PC_ACC_EMAIL_2_SUBJECT = "Re: {business_name} - Missed you earlier"
_PC_ACC_EMAIL_2_BODY = (
    "Hi {first_name},\n\n"
    "Tried reaching you earlier about Google review removal for {business_name}. "
    "Reply here or let me know a good time for a quick call.\n\n"
    "{footer}"
)
_PC_ACC_SMS_3 = (
    "Hi {first_name}, following up on {business_name} reviews. "
    "Free for a quick call this week? Reply with a time. {footer}"
)
_PC_ACC_EMAIL_3_SUBJECT = "Re: {business_name} - Can we reschedule?"
_PC_ACC_EMAIL_3_BODY = (
    "Hi {first_name},\n\n"
    "Still hoping to connect about {business_name}. "
    "Reply with a time that works and I will have a specialist call you.\n\n"
    "{footer}"
)
_PC_ACC_SMS_4 = (
    "Hi {first_name}, final note on review removal for {business_name}. "
    "Reply if timing works better now. {footer}"
)
_PC_ACC_EMAIL_4_SUBJECT = "Re: {business_name} - Last note"
_PC_ACC_EMAIL_4_BODY = (
    "Hi {first_name},\n\n"
    "Last outreach on Google review removal for {business_name}. If the timing is not right, "
    "no pressure. Reply any time to pick this back up.\n\n"
    "{footer}"
)


def _defer_and_track(
    raw_utc: datetime,
) -> tuple[datetime, dict[str, Any], Optional[datetime]]:
    eff = defer_sunday_touch_to_monday_8am_est(raw_utc)
    if _same_utc_instant(eff, raw_utc):
        return eff, {}, None
    return (
        eff,
        {
            "lead_status": "queued_for_morning",
            "deferred_from_utc": raw_utc.isoformat(),
            "defer_reason": "sunday_blackout_est",
        },
        raw_utc,
    )


def schedule_post_call_standard(
    call_ended_utc: datetime,
    lead: LeadRecord,
) -> list[ScheduledPostCallTouch]:
    """Standard sequence for ``undecided``: T+24h, T+72h, T+7d, T+14d.

    Touch 1 is multi-channel (email + SMS). Touches 2-4 are single-channel email.
    Sunday-due touches defer to Monday 08:00 EST.
    """
    if call_ended_utc.tzinfo is None:
        anchor = call_ended_utc.replace(tzinfo=timezone.utc)
    else:
        anchor = call_ended_utc

    raw_times = [
        anchor + timedelta(hours=24),
        anchor + timedelta(hours=72),
        anchor + timedelta(days=7),
        anchor + timedelta(days=14),
    ]

    email_templates = [
        (_PC_STD_1_SUBJECT, _PC_STD_1_BODY),
        (_PC_STD_2_SUBJECT, _PC_STD_2_BODY),
        (_PC_STD_3_SUBJECT, _PC_STD_3_BODY),
        (_PC_STD_4_SUBJECT, _PC_STD_4_BODY),
    ]
    sms_templates = [_PC_STD_SMS_1, _PC_STD_SMS_2, _PC_STD_SMS_3, _PC_STD_SMS_4]

    touches: list[ScheduledPostCallTouch] = []
    for i, raw_t in enumerate(raw_times):
        eff_t, updates, raw_meta = _defer_and_track(raw_t)
        subj = _format_followup_text(email_templates[i][0], lead)
        body = _format_followup_text(email_templates[i][1], lead)
        sms = _format_sms_followup(sms_templates[i], lead)

        channels = [Channel.EMAIL, Channel.SMS] if i == 0 else [Channel.EMAIL]

        touches.append(
            ScheduledPostCallTouch(
                index=i + 1,
                fire_at_utc=eff_t,
                channels=channels,
                subject=subj,
                body=body,
                sms_body=sms if Channel.SMS in channels else None,
                state_updates=updates,
                raw_fire_at_utc=raw_meta,
            )
        )
    return touches


def schedule_post_call_accelerated(
    call_ended_utc: datetime,
    lead: LeadRecord,
) -> list[ScheduledPostCallTouch]:
    """Accelerated sequence for ``no_show`` / ``unreachable``: T+15m, T+2h, T+24h, T+72h.

    Touch 1 is SMS-only. Touch 2+ are multi-channel (SMS + email).
    Sunday-due touches defer to Monday 08:00 EST.
    """
    if call_ended_utc.tzinfo is None:
        anchor = call_ended_utc.replace(tzinfo=timezone.utc)
    else:
        anchor = call_ended_utc

    raw_times = [
        anchor + timedelta(minutes=15),
        anchor + timedelta(hours=2),
        anchor + timedelta(hours=24),
        anchor + timedelta(hours=72),
    ]

    sms_templates = [_PC_ACC_SMS_1, _PC_ACC_SMS_2, _PC_ACC_SMS_3, _PC_ACC_SMS_4]
    email_templates = [
        (None, None),
        (_PC_ACC_EMAIL_2_SUBJECT, _PC_ACC_EMAIL_2_BODY),
        (_PC_ACC_EMAIL_3_SUBJECT, _PC_ACC_EMAIL_3_BODY),
        (_PC_ACC_EMAIL_4_SUBJECT, _PC_ACC_EMAIL_4_BODY),
    ]

    touches: list[ScheduledPostCallTouch] = []
    for i, raw_t in enumerate(raw_times):
        eff_t, updates, raw_meta = _defer_and_track(raw_t)
        sms = _format_sms_followup(sms_templates[i], lead)

        if i == 0:
            channels = [Channel.SMS]
            subj = None
            body = sms
            sms_body = sms
        else:
            channels = [Channel.SMS, Channel.EMAIL]
            subj = _format_followup_text(email_templates[i][0], lead)
            body = _format_followup_text(email_templates[i][1], lead)
            sms_body = sms

        touches.append(
            ScheduledPostCallTouch(
                index=i + 1,
                fire_at_utc=eff_t,
                channels=channels,
                subject=subj,
                body=body,
                sms_body=sms_body,
                state_updates=updates,
                raw_fire_at_utc=raw_meta,
            )
        )
    return touches


def schedule_post_call_follow_ups(
    call_outcome: CallOutcome,
    call_ended_utc: datetime,
    lead: LeadRecord,
    *,
    callback_datetime_utc: Optional[datetime] = None,
) -> list[ScheduledPostCallTouch]:
    """Route to the correct sequence based on call outcome.

    Returns an empty list for ``won`` and ``lost_hard`` (no follow-up needed).
    For ``callback_requested``, returns the standard sequence starting from the
    callback time instead of call-ended time.
    """
    if call_outcome in (CallOutcome.WON, CallOutcome.LOST_HARD):
        return []

    if call_outcome == CallOutcome.CALLBACK_REQUESTED:
        anchor = callback_datetime_utc or call_ended_utc
        return schedule_post_call_standard(anchor, lead)

    if call_outcome in (CallOutcome.NO_SHOW, CallOutcome.UNREACHABLE):
        return schedule_post_call_accelerated(call_ended_utc, lead)

    return schedule_post_call_standard(call_ended_utc, lead)


def build_morning_queue_brief(
    lead: LeadRecord,
    transcript: list[dict[str, Any]],
    *,
    submission_utc: datetime,
) -> str:
    """
    Deterministic morning-queue brief. Any fact not in ``lead`` or ``transcript`` is
    the literal ``not stated`` (no LLM, no invented detail).

    ``submission_utc`` should be when the lead hit the system (UTC), shown in local
    operations timezone in the header.
    """
    if submission_utc.tzinfo is None:
        sub = submission_utc.replace(tzinfo=timezone.utc)
    else:
        sub = submission_utc
    local = sub.astimezone(EST)
    submission_local = local.strftime("%Y-%m-%d %H:%M %Z")
    tz_offset = local.strftime("%z")
    if tz_offset and len(tz_offset) >= 5:
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"
    gbp = lead.gbp_link.strip() if lead.gbp_link else "not stated"
    src = lead.lead_source.strip() if lead.lead_source else "not stated"
    urg = lead.urgency_flag.strip() if lead.urgency_flag else "not stated"

    n_touch, n_email, n_sms = _touchpoint_counts(transcript)
    n_reply = _n_lead_replies(transcript)

    # Transcript rows typically have no timestamp in harness; do not invent.
    last_contact = "not stated"

    return f"""================================================================
ReviewArmour Morning Queue Brief - Lead {lead.lead_id}
Submitted: {submission_local} ({tz_offset})
================================================================
LEAD
  Name:     {lead.first_name} {lead.last_name}
  Business: {lead.business_name}
  Country:  {lead.country.value}
  Phone:    {lead.phone}
  Email:    {lead.email}
  GBP Link: {gbp}
  Source:   {src}
  Urgency:  {urg}

CONVERSATION SUMMARY
  Touchpoints:  {n_touch} ({n_email} email / {n_sms} SMS)
  Lead replies: {n_reply}
  Sentiment:    not stated
  Last contact: {last_contact}

EXTRACTED FACTS
  Review count discussed:  not stated
  Specific reviews named:  not stated
  Image reviews mentioned: not stated
  Objections raised:       not stated

OPENING LINES (pick one — generic, record-only; no transcript facts)
  1. Check whether {lead.first_name} wants next steps on Google review removal for {lead.business_name}.
  2. Ask if a quick call would help for {lead.business_name}.
  3. Offer to walk through pricing or timing for {lead.business_name} when they are ready.
================================================================
"""
