from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.models_db import ConversationMessage, Lead
from api.services.conversation_service import handle_ai_first_touch, handle_inbound_reply
from api.services.dispatch_service import dispatch_to_salesman
from api.services.router_service import decide_route

logger = logging.getLogger("reviewarmour.api.inbound")

router = APIRouter()


class FormSubmission(BaseModel):
    full_name: str
    business_name: str
    email: EmailStr
    phone: str
    country: str = Field(pattern="^(US|CA)$")
    gbp_link: str | None = None
    review_count_mentioned: int | None = None
    urgency_flag: str | None = None
    free_text_notes: str | None = None
    lead_source: str = "website_form"
    landing_page_url: str | None = None


class TwilioSmsWebhook(BaseModel):
    From: str = Field(alias="From")
    To: str = Field(alias="To")
    Body: str = Field(alias="Body")
    MessageSid: str | None = Field(default=None, alias="MessageSid")


class SesEmailNotification(BaseModel):
    from_email: str
    subject: str | None = None
    body: str
    message_id: str | None = None


@router.post("/form")
async def receive_form_submission(
    form: FormSubmission,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Inbound form submission webhook. Creates lead, routes, triggers first touch."""
    config = request.app.state.config
    received_at = datetime.now(timezone.utc)

    name_parts = form.full_name.strip().split(maxsplit=1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    lead = Lead(
        id=uuid.uuid4(),
        lead_source=form.lead_source,
        landing_page_url=form.landing_page_url,
        submission_utc=received_at,
        first_name=first_name,
        last_name=last_name,
        business_name=form.business_name,
        email=form.email,
        phone=form.phone,
        country=form.country,
        gbp_link=form.gbp_link,
        review_count=form.review_count_mentioned or 0,
        urgency_flag=form.urgency_flag,
        free_text_notes=form.free_text_notes,
        lead_status="captured",
        lead_cost_estimated_usd=config.default_lead_cost_usd,
        ai_quote_allowed=config.ai_quote_allowed,
        soft_quote_mode=config.soft_quote_mode,
    )

    route = decide_route(config)
    lead.route_decision = route.value

    session.add(lead)
    await session.commit()
    await session.refresh(lead)

    if route.value == "business_hours_salesman":
        background_tasks.add_task(
            dispatch_to_salesman, str(lead.id), config
        )
    else:
        background_tasks.add_task(
            handle_ai_first_touch, str(lead.id), config
        )

    logger.info(
        "Lead %s created: %s (%s) -> %s",
        lead.id, form.business_name, form.country, route.value,
    )

    return {
        "lead_id": str(lead.id),
        "route_decision": route.value,
        "received_at": received_at.isoformat(),
    }


@router.post("/sms")
async def receive_sms_reply(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Twilio SMS reply webhook. Matches phone to lead, runs AI pipeline."""
    config = request.app.state.config
    form_data = await request.form()
    from_phone = form_data.get("From", "")
    body = form_data.get("Body", "")
    message_sid = form_data.get("MessageSid", "")

    from sqlalchemy import select

    result = await session.execute(
        select(Lead).where(Lead.phone == from_phone).order_by(Lead.created_at.desc())
    )
    lead = result.scalars().first()

    if not lead:
        logger.warning("SMS from unknown phone: %s", from_phone)
        return {"status": "unknown_sender"}

    msg = ConversationMessage(
        lead_id=lead.id,
        role="lead",
        channel="sms",
        body=body,
        external_id=message_sid,
    )
    session.add(msg)
    await session.commit()

    background_tasks.add_task(
        handle_inbound_reply, str(lead.id), body, "sms", config
    )

    return {"status": "received", "lead_id": str(lead.id)}


@router.post("/email")
async def receive_email_reply(
    notification: SesEmailNotification,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """SES inbound email webhook (via SNS). Matches email to lead, runs AI pipeline."""
    config = request.app.state.config

    from sqlalchemy import select

    result = await session.execute(
        select(Lead)
        .where(Lead.email == notification.from_email)
        .order_by(Lead.created_at.desc())
    )
    lead = result.scalars().first()

    if not lead:
        logger.warning("Email from unknown address: %s", notification.from_email)
        return {"status": "unknown_sender"}

    msg = ConversationMessage(
        lead_id=lead.id,
        role="lead",
        channel="email",
        subject=notification.subject,
        body=notification.body,
        external_id=notification.message_id,
    )
    session.add(msg)
    await session.commit()

    background_tasks.add_task(
        handle_inbound_reply,
        str(lead.id),
        notification.body,
        "email",
        config,
    )

    return {"status": "received", "lead_id": str(lead.id)}
