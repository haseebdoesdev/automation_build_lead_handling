from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.models_db import Lead, OperatorConfig

logger = logging.getLogger("reviewarmour.api.operator")

router = APIRouter()


class ConfigUpdate(BaseModel):
    key: str
    value: str


class JobCompletePayload(BaseModel):
    lead_id: str
    completed_job_summary: str


@router.get("/config")
async def list_config(session: AsyncSession = Depends(get_session)):
    """List all operator-configurable values."""
    result = await session.execute(select(OperatorConfig))
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}


@router.put("/config")
async def update_config(
    update: ConfigUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a single operator config value."""
    result = await session.execute(
        select(OperatorConfig).where(OperatorConfig.key == update.key)
    )
    existing = result.scalars().first()

    if existing:
        existing.value = update.value
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(OperatorConfig(key=update.key, value=update.value))

    await session.commit()
    logger.info("Config updated: %s = %s", update.key, update.value)
    return {"status": "updated", "key": update.key}


@router.post("/kill-switch/quote")
async def toggle_ai_quote(
    enabled: bool,
    session: AsyncSession = Depends(get_session),
):
    """AI-quote-allowed kill switch. One-click disable of all AI pricing."""
    result = await session.execute(
        select(OperatorConfig).where(OperatorConfig.key == "ai_quote_allowed")
    )
    existing = result.scalars().first()
    value = "true" if enabled else "false"

    if existing:
        existing.value = value
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(OperatorConfig(key="ai_quote_allowed", value=value))

    await session.commit()
    logger.info("AI quote kill switch: %s", "enabled" if enabled else "disabled")
    return {"ai_quote_allowed": enabled}


@router.post("/kill-switch/soft-quote")
async def toggle_soft_quote(
    enabled: bool,
    session: AsyncSession = Depends(get_session),
):
    """Soft-quote mode toggle."""
    result = await session.execute(
        select(OperatorConfig).where(OperatorConfig.key == "soft_quote_mode")
    )
    existing = result.scalars().first()
    value = "true" if enabled else "false"

    if existing:
        existing.value = value
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(OperatorConfig(key="soft_quote_mode", value=value))

    await session.commit()
    return {"soft_quote_mode": enabled}


@router.post("/job-complete")
async def mark_job_complete(
    payload: JobCompletePayload,
    session: AsyncSession = Depends(get_session),
):
    """Operator marks a customer's removal job as complete. Triggers review request sequence."""
    result = await session.execute(
        select(Lead).where(Lead.id == payload.lead_id)
    )
    lead = result.scalars().first()
    if not lead:
        return {"status": "lead_not_found"}

    now = datetime.now(timezone.utc)
    lead.job_completion_utc = now
    lead.completed_job_summary = payload.completed_job_summary
    lead.lead_status = "customer_review_pending"
    lead.updated_at = now

    await session.commit()

    from api.services.scheduler_service import schedule_review_request_touches

    await schedule_review_request_touches(str(lead.id), now, session)

    logger.info("Job complete for lead %s, review request sequence queued", payload.lead_id)
    return {"status": "job_complete", "lead_id": payload.lead_id}


@router.get("/dashboard/queue")
async def morning_queue(session: AsyncSession = Depends(get_session)):
    """Morning queue dashboard — non-terminal after-hours leads sorted by priority."""
    terminal = {"won", "lost", "unreachable", "customer_review_complete"}
    result = await session.execute(
        select(Lead)
        .where(Lead.lead_status.notin_(terminal))
        .where(
            Lead.route_decision.in_(
                ["after_hours_ai", "morning_queue", "ai_escalated_to_human"]
            )
        )
        .order_by(Lead.created_at.asc())
    )
    leads = result.scalars().all()

    from reviewarmour.followup_cadence import queue_priority_rank

    sorted_leads = sorted(leads, key=lambda l: queue_priority_rank(l.lead_status))

    return [
        {
            "lead_id": str(l.id),
            "name": f"{l.first_name} {l.last_name}",
            "business": l.business_name,
            "country": l.country,
            "status": l.lead_status,
            "urgency": l.urgency_flag,
            "phone": l.phone,
            "email": l.email,
            "submitted": l.submission_utc.isoformat() if l.submission_utc else None,
        }
        for l in sorted_leads
    ]


class GBPInspectPayload(BaseModel):
    lead_id: str
    gbp_url: str | None = None  # if omitted, uses lead.gbp_link from DB


@router.post("/inspect-gbp")
async def inspect_gbp(
    payload: GBPInspectPayload,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Trigger a GBP profile inspection for a lead.

    Runs the Patchright scraper, then updates the lead's recency_profile,
    review_count, and business_category in the database.
    Runs in background — returns immediately with the lead_id.
    """
    config = request.app.state.config

    result = await session.execute(select(Lead).where(Lead.id == payload.lead_id))
    lead = result.scalars().first()
    if not lead:
        return {"status": "lead_not_found"}

    url = payload.gbp_url or lead.gbp_link
    if not url:
        return {"status": "no_gbp_url", "lead_id": payload.lead_id}

    # Update the gbp_link on the lead if a new one was provided
    if payload.gbp_url and payload.gbp_url != lead.gbp_link:
        lead.gbp_link = payload.gbp_url
        lead.updated_at = datetime.now(timezone.utc)
        await session.commit()

    background_tasks.add_task(_run_gbp_inspection, payload.lead_id, url, config)

    return {"status": "inspection_queued", "lead_id": payload.lead_id, "url": url}


async def _run_gbp_inspection(lead_id: str, url: str, config) -> None:
    """Background task: run GBP scraper and update lead record."""
    import asyncio
    from functools import partial

    from sqlalchemy import select

    from api.database import async_session_factory
    from api.models_db import Lead
    from reviewarmour.gbp.scraper import inspect_maps_place
    from reviewarmour.gbp.inference import inspection_dict_to_lead_field_updates

    if async_session_factory is None:
        return

    logger.info("GBP inspection starting for lead %s: %s", lead_id, url[:80])

    try:
        # Run in executor so it doesn't block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                __import__("reviewarmour.gbp.scraper", fromlist=["run_inspect_gbp_sync"]).run_inspect_gbp_sync,
                url,
                headless=True,
                max_reviews=24,
                storage_state=config.gbp_auth_state,
            ),
        )
    except Exception as e:
        logger.error("GBP inspection failed for lead %s: %s", lead_id, e)
        return

    if result.get("status") != "success":
        logger.warning("GBP inspection non-success for lead %s: %s", lead_id, result.get("error"))
        return

    updates = inspection_dict_to_lead_field_updates(result)

    async with async_session_factory() as session:
        db_result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead = db_result.scalars().first()
        if not lead:
            return

        if "recency_profile" in updates:
            lead.recency_profile = updates["recency_profile"]
        if "review_count" in updates:
            lead.review_count = updates["review_count"]
        if "business_category" in updates and updates["business_category"]:
            lead.business_category = updates["business_category"]

        # Store phone/address/website if missing
        if result.get("phone") and not lead.phone:
            lead.phone = result["phone"]
        if result.get("website"):
            lead.free_text_notes = (lead.free_text_notes or "") + f"\nWebsite: {result['website']}"

        lead.updated_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(
        "GBP inspection complete for lead %s: recency=%s reviews=%s images=%s",
        lead_id,
        result.get("inferred_recency_profile"),
        result.get("review_count_inferred"),
        result.get("any_review_has_images"),
    )
