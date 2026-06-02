from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models_db import Lead, ScheduledTouch, StallEvent

logger = logging.getLogger("reviewarmour.api.scheduler")


async def schedule_post_call_touches(
    lead_id: str,
    outcome: str,
    call_ended_utc: datetime,
    callback_dt: datetime | None,
    session: AsyncSession,
) -> None:
    """Schedule post-call follow-up touches based on call outcome."""
    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead_row = result.scalars().first()
    if not lead_row:
        return

    from reviewarmour.followup_cadence import schedule_post_call_follow_ups
    from reviewarmour.models import CallOutcome

    from api.services.conversation_service import _build_lead_record

    lead_record = _build_lead_record(lead_row)
    touches = schedule_post_call_follow_ups(
        CallOutcome(outcome),
        call_ended_utc,
        lead_record,
        callback_datetime_utc=callback_dt,
    )

    touch_type = "post_call_accelerated" if outcome in ("no_show", "unreachable") else "post_call_standard"

    for touch in touches:
        channels = [c.value for c in touch.channels]
        session.add(
            ScheduledTouch(
                lead_id=lead_row.id,
                touch_type=touch_type,
                index=touch.index,
                fire_at_utc=touch.fire_at_utc,
                channels=channels,
                subject=touch.subject,
                body=touch.body,
                sms_body=touch.sms_body,
                status="pending",
            )
        )

    await session.commit()
    logger.info("Scheduled %d post-call touches for lead %s (%s)", len(touches), lead_id, touch_type)


async def schedule_review_request_touches(
    lead_id: str,
    job_complete_utc: datetime,
    session: AsyncSession,
) -> None:
    """Schedule the 3-touch customer review request sequence (Section 16)."""
    result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead_row = result.scalars().first()
    if not lead_row:
        return

    from reviewarmour.scheduling import defer_sunday_touch_to_monday_8am_est

    t1 = defer_sunday_touch_to_monday_8am_est(job_complete_utc + timedelta(hours=1))
    t2 = defer_sunday_touch_to_monday_8am_est(job_complete_utc + timedelta(hours=24))
    t3 = defer_sunday_touch_to_monday_8am_est(job_complete_utc + timedelta(days=5))

    gbp_review_link = lead_row.gbp_review_link or "{gbp_review_link}"
    summary = lead_row.completed_job_summary or "your review removal"
    name = lead_row.first_name

    # Touch 1: SMS
    sms_1 = (
        f"Hi {name}, {summary} is complete. "
        f"Would mean a lot if you left us a quick review: {gbp_review_link}"
    )
    session.add(ScheduledTouch(
        lead_id=lead_row.id, touch_type="review_request", index=1,
        fire_at_utc=t1, channels=["sms"], body=sms_1, status="pending",
    ))

    # Touch 2: Email
    email_2_subject = f"{lead_row.business_name} - Quick favor"
    email_2_body = (
        f"Hi {name},\n\n"
        f"Sent you a text earlier about leaving a review. If you have 30 seconds, "
        f"it would really help us out: {gbp_review_link}\n\n"
        f"Thanks for trusting us with {lead_row.business_name}.\n"
    )
    session.add(ScheduledTouch(
        lead_id=lead_row.id, touch_type="review_request", index=2,
        fire_at_utc=t2, channels=["email"], subject=email_2_subject,
        body=email_2_body, status="pending",
    ))

    # Touch 3: Final SMS
    sms_3 = (
        f"Hi {name}, last ask from us. If you have a moment: {gbp_review_link} "
        f"No pressure either way."
    )
    session.add(ScheduledTouch(
        lead_id=lead_row.id, touch_type="review_request", index=3,
        fire_at_utc=t3, channels=["sms"], body=sms_3, status="pending",
    ))

    await session.commit()
    logger.info("Scheduled 3 review request touches for lead %s", lead_id)


async def close_stall_on_reply(lead_id: str, session: AsyncSession) -> None:
    """Close active stall event when lead replies."""
    result = await session.execute(
        select(StallEvent)
        .where(StallEvent.lead_id == lead_id, StallEvent.resolved_at.is_(None))
    )
    stall = result.scalars().first()
    if stall:
        stall.resolved_at = datetime.now(timezone.utc)
        stall.resolution = "lead_replied"
        await session.commit()
        logger.info("Stall closed for lead %s: lead replied", lead_id)

    # Also update lead status back from stalled
    lead_result = await session.execute(select(Lead).where(Lead.id == lead_id))
    lead_row = lead_result.scalars().first()
    if lead_row and lead_row.lead_status == "stalled_post_quote":
        lead_row.lead_status = "ai_engaged"
        lead_row.updated_at = datetime.now(timezone.utc)
        await session.commit()
