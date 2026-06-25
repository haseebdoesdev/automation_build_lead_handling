from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.config import AppConfig

logger = logging.getLogger("reviewarmour.api.conversation")


def _build_lead_record(lead_row) -> "reviewarmour.models.LeadRecord":
    """Convert a DB Lead row into a reviewarmour LeadRecord for the AI core."""
    from reviewarmour.models import (
        Country,
        GBPCategory,
        LeadRecord,
        RecencyProfile,
    )

    gbp_cat = None
    raw_cat = getattr(lead_row, "gbp_category", None)
    if raw_cat:
        try:
            gbp_cat = GBPCategory(raw_cat)
        except ValueError:
            gbp_cat = None

    image_flags = getattr(lead_row, "reviews_image_content", None) or []
    recent_flags = getattr(lead_row, "reviews_under_one_month", None) or []

    return LeadRecord(
        lead_id=str(lead_row.id),
        first_name=lead_row.first_name,
        last_name=lead_row.last_name,
        business_name=lead_row.business_name,
        country=Country(lead_row.country),
        phone=lead_row.phone,
        email=lead_row.email,
        gbp_link=lead_row.gbp_link,
        review_count=lead_row.review_count,
        recency_profile=RecencyProfile(lead_row.recency_profile or "uncertain"),
        business_category=lead_row.business_category or "",
        negotiation_step=lead_row.negotiation_step,
        ai_quote_allowed=lead_row.ai_quote_allowed,
        soft_quote_mode=lead_row.soft_quote_mode,
        gbp_category=gbp_cat,
        reviews_image_content=list(image_flags),
        reviews_under_one_month=list(recent_flags),
    )


def _build_transcript(messages: list) -> list[dict]:
    """Convert DB ConversationMessage rows into transcript dicts for the AI core."""
    transcript = []
    for m in sorted(messages, key=lambda x: x.sent_at):
        transcript.append(
            {
                "role": m.role,
                "channel": m.channel,
                "content": m.body,
                "subject": m.subject,
            }
        )
    return transcript


async def handle_ai_first_touch(lead_id: str, config: AppConfig) -> None:
    """After-hours first-touch: run AI pipeline, send email + SMS within 60 seconds."""
    from sqlalchemy import select

    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead
    from api.services.messaging_service import send_email, send_sms, send_whatsapp

    if async_session_factory is None:
        logger.error("Database not initialized")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead_row = result.scalars().first()
        if not lead_row:
            logger.error("Lead %s not found for first touch", lead_id)
            return

        lead_record = _build_lead_record(lead_row)
        transcript: list[dict] = []

        try:
            from reviewarmour.conversation import (
                ConversationModule,
                OutboundPipeline,
            )
            from reviewarmour.self_correction import (
                SelfCorrectionModule,
                make_anthropic_client,
            )
            from reviewarmour.settings import LLMRuntime

            client = make_anthropic_client(config.anthropic_api_key)
            runtime = LLMRuntime()
            conv_module = ConversationModule(client=client, runtime=runtime)
            sc_module = SelfCorrectionModule(client=client, runtime=runtime)
            pipeline = OutboundPipeline(
                conversation=conv_module,
                self_correction=sc_module,
            )

            from reviewarmour.models import Channel

            pipeline_result = await _run_pipeline_async(
                pipeline, lead_record, transcript, Channel.EMAIL, "first_touch"
            )

            if pipeline_result and pipeline_result.draft:
                draft = pipeline_result.draft

                # Send email
                email_result = await send_email(
                    lead_row.email,
                    draft.subject or f"{lead_row.business_name} - Google Reviews",
                    draft.body,
                    lead_row.country,
                    config,
                )
                session.add(
                    ConversationMessage(
                        lead_id=lead_row.id,
                        role="assistant",
                        channel="email",
                        subject=draft.subject,
                        body=draft.body,
                        external_id=email_result.get("message_id"),
                        delivery_status=email_result.get("status", "unknown"),
                    )
                )

                # Send SMS
                sms_body = draft.body[:310] if len(draft.body) > 310 else draft.body
                sms_result = await send_sms(
                    lead_row.phone, sms_body, lead_row.country, config
                )
                session.add(
                    ConversationMessage(
                        lead_id=lead_row.id,
                        role="assistant",
                        channel="sms",
                        body=sms_body,
                        external_id=sms_result.get("sid"),
                        delivery_status=sms_result.get("status", "unknown"),
                    )
                )

                # Send WhatsApp (if configured)
                if config.whatsapp_enabled:
                    wa_result = await send_whatsapp(
                        lead_row.phone, draft.body, lead_row.country, config
                    )
                    session.add(
                        ConversationMessage(
                            lead_id=lead_row.id,
                            role="assistant",
                            channel="whatsapp",
                            body=draft.body,
                            external_id=wa_result.get("sid"),
                            delivery_status=wa_result.get("status", "unknown"),
                        )
                    )

                lead_row.ai_conversation_state = "in_progress"
                lead_row.lead_status = "ai_engaged"
                lead_row.updated_at = datetime.now(timezone.utc)

                await session.commit()
                logger.info("First touch sent for lead %s", lead_id)
            else:
                lead_row.lead_status = "ai_escalated"
                lead_row.escalation_reason = "first_touch_draft_failed"
                lead_row.updated_at = datetime.now(timezone.utc)
                await session.commit()
                logger.warning("First touch draft failed for lead %s", lead_id)

        except Exception as e:
            logger.error("First touch error for lead %s: %s", lead_id, e)
            lead_row.lead_status = "ai_escalated"
            lead_row.escalation_reason = f"first_touch_exception: {e}"
            lead_row.updated_at = datetime.now(timezone.utc)
            await session.commit()


async def handle_inbound_reply(
    lead_id: str,
    message: str,
    channel: str,
    config: AppConfig,
) -> None:
    """Process an inbound lead reply through the AI pipeline."""
    from sqlalchemy import select

    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead
    from api.services.messaging_service import send_email, send_sms, send_whatsapp

    if async_session_factory is None:
        logger.error("Database not initialized")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead_row = result.scalars().first()
        if not lead_row:
            logger.error("Lead %s not found for reply", lead_id)
            return

        if lead_row.lead_status in ("ai_escalated", "won", "lost"):
            logger.info("Lead %s in terminal state %s, skipping AI", lead_id, lead_row.lead_status)
            return

        # Close any active stall if lead replied
        from api.services.scheduler_service import close_stall_on_reply

        await close_stall_on_reply(lead_id, session)

        lead_record = _build_lead_record(lead_row)

        msg_result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.lead_id == lead_id)
            .order_by(ConversationMessage.sent_at)
        )
        transcript = _build_transcript(msg_result.scalars().all())

        from reviewarmour.conversation import should_escalate_inbound

        if should_escalate_inbound(message):
            lead_row.lead_status = "ai_escalated"
            lead_row.escalation_reason = "hard_trigger_inbound"
            lead_row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("Lead %s escalated: hard trigger in reply", lead_id)
            return

        try:
            from reviewarmour.conversation import (
                ConversationModule,
                OutboundPipeline,
            )
            from reviewarmour.models import Channel
            from reviewarmour.self_correction import (
                SelfCorrectionModule,
                make_anthropic_client,
            )
            from reviewarmour.settings import LLMRuntime

            client = make_anthropic_client(config.anthropic_api_key)
            runtime = LLMRuntime()
            conv_module = ConversationModule(client=client, runtime=runtime)
            sc_module = SelfCorrectionModule(client=client, runtime=runtime)
            pipeline = OutboundPipeline(
                conversation=conv_module,
                self_correction=sc_module,
            )

            ch = {"sms": Channel.SMS, "whatsapp": Channel.WHATSAPP}.get(channel, Channel.EMAIL)

            pipeline_result = await _run_pipeline_async(
                pipeline, lead_record, transcript, ch, "reply",
                inbound_message=message,
            )

            if pipeline_result and pipeline_result.draft:
                draft = pipeline_result.draft

                if draft.action == "escalate":
                    lead_row.lead_status = "ai_escalated"
                    lead_row.escalation_reason = draft.reason or "pipeline_escalation"
                    lead_row.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    return

                # Check for quote acceptance before sending
                from reviewarmour.conversation import acceptance_signal

                is_acceptance = acceptance_signal(message)

                if channel == "sms":
                    sms_result = await send_sms(
                        lead_row.phone, draft.body, lead_row.country, config
                    )
                    session.add(
                        ConversationMessage(
                            lead_id=lead_row.id,
                            role="assistant",
                            channel="sms",
                            body=draft.body,
                            external_id=sms_result.get("sid"),
                            delivery_status=sms_result.get("status", "unknown"),
                        )
                    )
                elif channel == "whatsapp":
                    wa_result = await send_whatsapp(
                        lead_row.phone, draft.body, lead_row.country, config
                    )
                    session.add(
                        ConversationMessage(
                            lead_id=lead_row.id,
                            role="assistant",
                            channel="whatsapp",
                            body=draft.body,
                            external_id=wa_result.get("sid"),
                            delivery_status=wa_result.get("status", "unknown"),
                        )
                    )
                else:
                    email_result = await send_email(
                        lead_row.email,
                        draft.subject or f"Re: {lead_row.business_name}",
                        draft.body,
                        lead_row.country,
                        config,
                    )
                    session.add(
                        ConversationMessage(
                            lead_id=lead_row.id,
                            role="assistant",
                            channel="email",
                            subject=draft.subject,
                            body=draft.body,
                            external_id=email_result.get("message_id"),
                            delivery_status=email_result.get("status", "unknown"),
                        )
                    )

                # Sync negotiation state + adaptive-pricing context back to DB
                if hasattr(pipeline_result, "commercial_result") and pipeline_result.commercial_result:
                    cr = pipeline_result.commercial_result
                    lead_row.quoted_price_usd = cr.authorized_quote_usd_per_review
                    lead_row.negotiation_step = cr.negotiation_step
                    lead_row.quote_basis = {
                        "tier": cr.tier.value,
                        "gbp_category": cr.gbp_category.value if cr.gbp_category else None,
                        "volume_bracket": cr.volume_bracket.value,
                        "range_low": cr.range_low_usd,
                        "range_high": cr.range_high_usd,
                        "floor": cr.floor_usd,
                        "negotiation_step": cr.negotiation_step,
                        "reasoning_summary": cr.reasoning_summary,
                    }
                    # Spec v2 fields
                    lead_row.pricing_tier = cr.tier.value
                    if cr.gbp_category:
                        lead_row.gbp_category = cr.gbp_category.value
                    lead_row.volume_bracket = cr.volume_bracket.value
                    lead_row.phone_call_threshold_triggered = (
                        cr.phone_call_threshold_triggered
                    )
                    if cr.salesman_recommended_range:
                        lead_row.salesman_recommended_range = {
                            "low": cr.salesman_recommended_range[0],
                            "high": cr.salesman_recommended_range[1],
                            "opening": cr.salesman_recommended_opening_usd,
                        }
                    if cr.reasoning_summary:
                        lead_row.adaptive_reasoning_summary = cr.reasoning_summary

                # Quote acceptance → Slack handoff (Section 13)
                if is_acceptance and lead_row.quoted_price_usd:
                    lead_row.lead_status = "quote_accepted"
                    lead_row.ai_conversation_state = "qualified"
                    await session.commit()

                    from api.services.slack_service import send_invoice_handoff

                    handoff_data = {
                        "name": f"{lead_row.first_name} {lead_row.last_name}",
                        "business": lead_row.business_name,
                        "country": lead_row.country,
                        "email": lead_row.email,
                        "phone": lead_row.phone,
                        "gbp_link": lead_row.gbp_link or "N/A",
                        "review_count": lead_row.review_count,
                        "quote_usd": lead_row.quoted_price_usd,
                        "total_usd": lead_row.quoted_price_usd * max(lead_row.review_count, 1),
                    }
                    await send_invoice_handoff(handoff_data, config)
                    logger.info(
                        "Quote accepted for lead %s — Slack handoff fired", lead_id
                    )
                else:
                    lead_row.updated_at = datetime.now(timezone.utc)
                    await session.commit()

                # Pause any active follow-up sequences (lead replied mid-sequence)
                await _pause_active_sequences(lead_id, session)

                logger.info("Reply processed for lead %s via %s", lead_id, channel)

        except Exception as e:
            logger.error("Reply processing error for lead %s: %s", lead_id, e)
            lead_row.lead_status = "ai_escalated"
            lead_row.escalation_reason = f"reply_exception: {e}"
            lead_row.updated_at = datetime.now(timezone.utc)
            await session.commit()


async def _pause_active_sequences(lead_id: str, session) -> None:
    """Pause pending follow-up touches when lead replies mid-sequence."""
    from sqlalchemy import select, update

    from api.models_db import ScheduledTouch

    await session.execute(
        update(ScheduledTouch)
        .where(
            ScheduledTouch.lead_id == lead_id,
            ScheduledTouch.status == "pending",
        )
        .values(status="paused")
    )
    await session.commit()
    logger.info("Paused pending touches for lead %s (lead replied)", lead_id)


async def draft_follow_up_via_ai(
    lead_id: str,
    touch_type: str,
    touch_index: int,
    channel: str,
    config: AppConfig,
) -> dict | None:
    """Draft a follow-up message through the AI pipeline + SC review.

    Returns {"subject": ..., "body": ..., "sms_body": ...} or None on failure.
    The spec requires every follow-up to be AI-drafted and SC-reviewed.
    """
    from sqlalchemy import select

    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead

    if async_session_factory is None:
        return None

    async with async_session_factory() as session:
        result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead_row = result.scalars().first()
        if not lead_row:
            return None

        lead_record = _build_lead_record(lead_row)
        msg_result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.lead_id == lead_id)
            .order_by(ConversationMessage.sent_at)
        )
        transcript = _build_transcript(msg_result.scalars().all())

        try:
            from reviewarmour.conversation import ConversationModule, OutboundPipeline
            from reviewarmour.models import Channel as Ch
            from reviewarmour.self_correction import (
                SelfCorrectionModule,
                make_anthropic_client,
            )
            from reviewarmour.settings import LLMRuntime

            client = make_anthropic_client(config.anthropic_api_key)
            runtime = LLMRuntime()
            conv_module = ConversationModule(client=client, runtime=runtime)
            sc_module = SelfCorrectionModule(client=client, runtime=runtime)
            pipeline = OutboundPipeline(
                conversation=conv_module, self_correction=sc_module
            )

            ch = {"sms": Ch.SMS, "whatsapp": Ch.WHATSAPP}.get(channel, Ch.EMAIL)
            stage = f"{touch_type}_touch_{touch_index}"

            pipeline_result = await _run_pipeline_async(
                pipeline, lead_record, transcript, ch, stage
            )

            if pipeline_result and pipeline_result.draft and pipeline_result.draft.action == "send":
                draft = pipeline_result.draft
                return {
                    "subject": draft.subject,
                    "body": draft.body,
                    "sms_body": draft.body[:310] if len(draft.body) > 310 else draft.body,
                }
        except Exception as e:
            logger.error("AI draft failed for lead %s touch %s/%d: %s", lead_id, touch_type, touch_index, e)

    return None


async def _run_pipeline_async(pipeline, lead_record, transcript, channel, stage, **kwargs):
    """Run the synchronous pipeline in a thread to avoid blocking the event loop."""
    import asyncio
    from functools import partial

    func = partial(
        pipeline.run,
        lead=lead_record,
        transcript=transcript,
        channel=channel,
        sequence_stage=stage,
        **kwargs,
    )
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func)
