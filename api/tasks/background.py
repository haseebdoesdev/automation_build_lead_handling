from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.config import AppConfig

logger = logging.getLogger("reviewarmour.api.tasks")


async def fire_pending_touches(config: AppConfig) -> int:
    """Find and send all scheduled touches whose fire_at_utc has passed."""
    from api.database import async_session_factory
    from api.models_db import Lead, ScheduledTouch
    from api.services.messaging_service import send_email, send_sms

    if async_session_factory is None:
        return 0

    now = datetime.now(timezone.utc)
    fired = 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(ScheduledTouch)
            .where(ScheduledTouch.status == "pending")
            .where(ScheduledTouch.fire_at_utc <= now)
            .order_by(ScheduledTouch.fire_at_utc)
        )
        touches = result.scalars().all()

        for touch in touches:
            lead_result = await session.execute(
                select(Lead).where(Lead.id == touch.lead_id)
            )
            lead = lead_result.scalars().first()
            if not lead:
                touch.status = "cancelled"
                continue

            if lead.lead_status in ("won", "lost", "unreachable", "ai_escalated"):
                touch.status = "cancelled"
                continue

            channels = touch.channels or []

            # Attempt AI-drafted content for post-call and review request touches
            subject = touch.subject
            body = touch.body
            sms_text = touch.sms_body or touch.body

            if touch.touch_type in ("post_call_standard", "post_call_accelerated"):
                from api.services.conversation_service import draft_follow_up_via_ai

                primary_ch = "sms" if "sms" in channels and "email" not in channels else "email"
                ai_draft = await draft_follow_up_via_ai(
                    str(touch.lead_id), touch.touch_type, touch.index, primary_ch, config
                )
                if ai_draft:
                    subject = ai_draft.get("subject") or subject
                    body = ai_draft.get("body") or body
                    sms_text = ai_draft.get("sms_body") or sms_text

            if "email" in channels and body:
                await send_email(
                    lead.email,
                    subject or f"Re: {lead.business_name}",
                    body,
                    lead.country,
                    config,
                )

            if "sms" in channels:
                await send_sms(lead.phone, sms_text, lead.country, config)

            touch.status = "sent"
            touch.sent_at = now
            fired += 1

            if touch.touch_type == "review_request" and touch.index == 3:
                lead.lead_status = "customer_review_complete"
                lead.updated_at = now

        await session.commit()

    logger.info("Fired %d pending touches", fired)
    return fired


async def sweep_stalls(config: AppConfig) -> int:
    """Detect leads that have gone silent after a commercial turn."""
    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead, StallEvent
    from api.services.slack_service import send_stall_alert

    if async_session_factory is None:
        return 0

    now = datetime.now(timezone.utc)
    stall_window = timedelta(hours=config.stall_escalation_window_hours)
    detected = 0

    async with async_session_factory() as session:
        # Find leads with quotes but no recent reply
        result = await session.execute(
            select(Lead)
            .where(Lead.lead_status == "ai_engaged")
            .where(Lead.quoted_price_usd.isnot(None))
        )
        leads = result.scalars().all()

        for lead in leads:
            # Check if already stalled
            existing_stall = await session.execute(
                select(StallEvent)
                .where(StallEvent.lead_id == lead.id, StallEvent.resolved_at.is_(None))
            )
            if existing_stall.scalars().first():
                continue

            # Find last outbound message
            last_out = await session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.lead_id == lead.id,
                    ConversationMessage.role == "assistant",
                )
                .order_by(ConversationMessage.sent_at.desc())
            )
            last_outbound = last_out.scalars().first()
            if not last_outbound:
                continue

            # Find last inbound after last outbound
            last_in = await session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.lead_id == lead.id,
                    ConversationMessage.role == "lead",
                    ConversationMessage.sent_at > last_outbound.sent_at,
                )
            )
            if last_in.scalars().first():
                continue  # Lead replied, not stalled

            # Check if stall window has passed
            if now - last_outbound.sent_at < stall_window:
                continue

            # Stall detected
            lead.lead_status = "stalled_post_quote"
            lead.updated_at = now

            stall = StallEvent(
                lead_id=lead.id,
                commercial_turn_at=last_outbound.sent_at,
                stall_detected_at=now,
                salesman_paged_at=now,
            )
            session.add(stall)
            detected += 1

            lead_data = {
                "name": f"{lead.first_name} {lead.last_name}",
                "business": lead.business_name,
                "country": lead.country,
                "phone": lead.phone,
                "email": lead.email,
                "last_quote": lead.quoted_price_usd,
                "last_message": "See transcript",
                "silent_since": last_outbound.sent_at.isoformat(),
            }
            await send_stall_alert(lead_data, config)

        await session.commit()

    logger.info("Detected %d new stalls", detected)
    return detected


async def sweep_stall_backups(config: AppConfig) -> int:
    """Page Jayden as backup for stalls not actioned within 4 hours."""
    from api.database import async_session_factory
    from api.models_db import Lead, StallEvent
    from api.services.slack_service import send_stall_alert

    if async_session_factory is None:
        return 0

    now = datetime.now(timezone.utc)
    backup_window = timedelta(hours=4)
    paged = 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(StallEvent)
            .where(
                StallEvent.resolved_at.is_(None),
                StallEvent.backup_paged_at.is_(None),
                StallEvent.salesman_paged_at.isnot(None),
            )
        )
        stalls = result.scalars().all()

        for stall in stalls:
            if now - stall.salesman_paged_at < backup_window:
                continue

            lead_result = await session.execute(
                select(Lead).where(Lead.id == stall.lead_id)
            )
            lead = lead_result.scalars().first()
            if not lead:
                continue

            stall.backup_paged_at = now

            lead_data = {
                "name": f"{lead.first_name} {lead.last_name}",
                "business": lead.business_name,
                "country": lead.country,
                "phone": lead.phone,
                "email": lead.email,
                "last_quote": lead.quoted_price_usd,
                "last_message": "See transcript",
                "silent_since": stall.commercial_turn_at.isoformat(),
            }
            await send_stall_alert(lead_data, config, is_backup=True)
            paged += 1

        await session.commit()

    logger.info("Paged backup for %d stalls", paged)
    return paged


async def release_morning_queue(config: AppConfig) -> int:
    """At 08:00 EST, generate briefs for queued leads and notify the morning salesman."""
    from zoneinfo import ZoneInfo

    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead
    from api.services.slack_service import _post_slack

    if async_session_factory is None:
        return 0

    tz = ZoneInfo(config.operations_timezone)
    now_local = datetime.now(tz)

    if now_local.hour != config.morning_queue_release_hour:
        return 0

    now = datetime.now(timezone.utc)
    released = 0

    async with async_session_factory() as session:
        non_terminal = [
            "ai_engaged", "queued_for_morning", "ai_escalated",
            "stalled_post_quote",
        ]
        result = await session.execute(
            select(Lead)
            .where(Lead.lead_status.in_(non_terminal))
            .where(
                Lead.route_decision.in_(
                    ["after_hours_ai", "morning_queue", "ai_escalated_to_human"]
                )
            )
            .order_by(Lead.created_at.asc())
        )
        leads = result.scalars().all()

        if not leads:
            return 0

        from reviewarmour.followup_cadence import build_morning_queue_brief, queue_priority_rank
        from reviewarmour.models import (
            Channel,
            Country,
            LeadRecord,
            RecencyProfile,
        )

        sorted_leads = sorted(leads, key=lambda l: queue_priority_rank(l.lead_status))

        briefs: list[str] = []
        for lead in sorted_leads:
            msg_result = await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.lead_id == lead.id)
                .order_by(ConversationMessage.sent_at)
            )
            messages = msg_result.scalars().all()
            transcript = [
                {"role": m.role, "channel": m.channel, "content": m.body}
                for m in messages
            ]

            lead_record = LeadRecord(
                lead_id=str(lead.id),
                first_name=lead.first_name,
                last_name=lead.last_name,
                business_name=lead.business_name,
                country=Country(lead.country),
                phone=lead.phone,
                email=lead.email,
                gbp_link=lead.gbp_link,
                review_count=lead.review_count,
                recency_profile=RecencyProfile(lead.recency_profile or "uncertain"),
                business_category=lead.business_category or "",
                lead_source=lead.lead_source or "",
                urgency_flag=lead.urgency_flag,
            )

            brief = build_morning_queue_brief(
                lead_record, transcript, submission_utc=lead.submission_utc or now
            )
            briefs.append(brief)

            lead.lead_status = "queued_for_morning"
            lead.updated_at = now
            released += 1

        await session.commit()

        if briefs and config.slack_salesman_channel:
            header = f"*Morning Queue — {now_local.strftime('%A %B %d')}*\n{released} leads queued\n"
            full_text = header + "\n".join(briefs[:10])
            if len(full_text) > 3900:
                full_text = full_text[:3900] + "\n... (truncated, see dashboard)"
            await _post_slack(config.slack_salesman_channel, full_text, None, config)

    logger.info("Morning queue released: %d leads", released)
    return released


_last_morning_release_date: str = ""


async def run_background_loop(config: AppConfig) -> None:
    """Main background loop: fires touches, sweeps stalls, releases morning queue."""
    global _last_morning_release_date
    logger.info("Background task loop started")
    while True:
        try:
            await fire_pending_touches(config)
            await sweep_stalls(config)
            await sweep_stall_backups(config)

            from zoneinfo import ZoneInfo

            tz = ZoneInfo(config.operations_timezone)
            now_local = datetime.now(tz)
            today = now_local.strftime("%Y-%m-%d")
            if (
                now_local.hour == config.morning_queue_release_hour
                and _last_morning_release_date != today
            ):
                await release_morning_queue(config)
                _last_morning_release_date = today

        except Exception as e:
            logger.error("Background loop error: %s", e)
        await asyncio.sleep(60)
