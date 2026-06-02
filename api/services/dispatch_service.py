from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from api.config import AppConfig

logger = logging.getLogger("reviewarmour.api.dispatch")


async def dispatch_to_salesman(lead_id: str, config: AppConfig) -> None:
    """Dispatch a lead to the on-duty salesman with ack tracking (Section 12)."""
    from sqlalchemy import select

    from api.database import async_session_factory
    from api.models_db import ConversationMessage, Lead, SalesmanDispatch
    from api.services.messaging_service import send_email, send_sms
    from api.services.slack_service import send_salesman_dispatch

    if async_session_factory is None:
        logger.error("Database not initialized")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead_row = result.scalars().first()
        if not lead_row:
            logger.error("Lead %s not found for dispatch", lead_id)
            return

        # Send acknowledgement to lead (within 60s SLA)
        ack_subject = f"{lead_row.business_name} - We received your inquiry"
        ack_body = (
            f"Hi {lead_row.first_name},\n\n"
            f"Thanks for reaching out about Google review removal for "
            f"{lead_row.business_name}. A specialist is reviewing your profile "
            f"now and will be in touch shortly.\n\n"
        )
        from reviewarmour.followup_cadence import _regional_footer

        from reviewarmour.models import Country

        footer = _regional_footer(Country(lead_row.country))
        ack_body += footer

        await send_email(
            lead_row.email, ack_subject, ack_body, lead_row.country, config
        )
        session.add(
            ConversationMessage(
                lead_id=lead_row.id,
                role="assistant",
                channel="email",
                subject=ack_subject,
                body=ack_body,
            )
        )

        sms_ack = (
            f"Hi {lead_row.first_name}, thanks for reaching out about "
            f"{lead_row.business_name} reviews. A specialist is calling you shortly."
        )
        await send_sms(lead_row.phone, sms_ack, lead_row.country, config)
        session.add(
            ConversationMessage(
                lead_id=lead_row.id,
                role="assistant",
                channel="sms",
                body=sms_ack,
            )
        )

        # Dispatch to salesman with rotation
        salesmen = config.salesmen_on_duty
        max_dispatches = min(len(salesmen), 2)  # 2-miss fallback

        for dispatch_num in range(1, max_dispatches + 1):
            salesman_idx = (dispatch_num - 1) % len(salesmen)
            salesman_name = salesmen[salesman_idx]

            lead_data = {
                "name": f"{lead_row.first_name} {lead_row.last_name}",
                "business": lead_row.business_name,
                "phone": lead_row.phone,
                "email": lead_row.email,
                "country": lead_row.country,
                "gbp_link": lead_row.gbp_link or "N/A",
                "urgency": lead_row.urgency_flag or "N/A",
                "source": lead_row.lead_source,
            }

            dispatch = SalesmanDispatch(
                lead_id=lead_row.id,
                salesman_name=salesman_name,
                dispatch_number=dispatch_num,
            )
            session.add(dispatch)
            await session.commit()

            # TODO: resolve salesman phone from config/DB
            salesman_phone = config.jayden_phone
            await send_salesman_dispatch(lead_data, salesman_phone, config)

            lead_row.assigned_salesman = salesman_name
            lead_row.lead_status = "dispatched_to_salesman"
            lead_row.updated_at = datetime.now(timezone.utc)
            await session.commit()

            # Wait for ack window
            await asyncio.sleep(config.salesman_ack_window_minutes * 60)

            # Check if acked
            await session.refresh(dispatch)
            if dispatch.ack_at is not None:
                logger.info(
                    "Salesman %s acked lead %s", salesman_name, lead_id
                )
                return

            # Mark as missed
            dispatch.missed = True
            await session.commit()
            logger.warning(
                "Salesman %s missed lead %s (dispatch %d)",
                salesman_name, lead_id, dispatch_num,
            )

        # All dispatches missed — fall back to AI, page Jayden
        logger.warning(
            "All dispatches missed for lead %s. Falling back to AI.", lead_id
        )
        lead_row.route_decision = "after_hours_ai"
        lead_row.lead_status = "ai_engaged"
        lead_row.updated_at = datetime.now(timezone.utc)
        await session.commit()

        from api.services.messaging_service import send_sms as sms_send

        await sms_send(
            config.jayden_phone,
            f"URGENT: All salesmen missed lead {lead_row.first_name} "
            f"({lead_row.business_name}). AI fallback active. Check CRM.",
            "US",
            config,
        )

        from api.services.conversation_service import handle_ai_first_touch

        await handle_ai_first_touch(lead_id, config)
