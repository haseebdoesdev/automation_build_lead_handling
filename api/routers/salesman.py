from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_session
from api.models_db import Lead, SalesmanDispatch

logger = logging.getLogger("reviewarmour.api.salesman")

router = APIRouter()


class AckPayload(BaseModel):
    lead_id: str
    salesman_name: str


class CallOutcomePayload(BaseModel):
    lead_id: str
    salesman_name: str
    outcome: str  # won, lost_hard, undecided, callback_requested, no_show, unreachable
    callback_datetime_utc: str | None = None
    notes: str | None = None


@router.post("/ack")
async def acknowledge_dispatch(
    payload: AckPayload,
    session: AsyncSession = Depends(get_session),
):
    """Salesman acknowledges a lead dispatch."""
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(SalesmanDispatch)
        .where(
            SalesmanDispatch.lead_id == payload.lead_id,
            SalesmanDispatch.salesman_name == payload.salesman_name,
            SalesmanDispatch.ack_at.is_(None),
            SalesmanDispatch.missed == False,
        )
        .order_by(SalesmanDispatch.dispatched_at.desc())
    )
    dispatch = result.scalars().first()

    if not dispatch:
        return {"status": "no_pending_dispatch"}

    dispatch.ack_at = now

    lead_result = await session.execute(
        select(Lead).where(Lead.id == dispatch.lead_id)
    )
    lead = lead_result.scalars().first()
    if lead:
        lead.lead_status = "dispatched_to_salesman"
        lead.updated_at = now

    await session.commit()

    logger.info(
        "Salesman %s acked lead %s", payload.salesman_name, payload.lead_id
    )
    return {"status": "acknowledged", "lead_id": payload.lead_id}


@router.post("/call-outcome")
async def log_call_outcome(
    payload: CallOutcomePayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Log the outcome of a salesman call and trigger appropriate follow-up."""
    config = request.app.state.config
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(Lead).where(Lead.id == payload.lead_id)
    )
    lead = result.scalars().first()

    if not lead:
        return {"status": "lead_not_found"}

    lead.call_outcome = payload.outcome
    lead.updated_at = now

    status_map = {
        "won": "won",
        "lost_hard": "lost",
        "undecided": "ai_engaged",
        "callback_requested": "booked_call",
        "no_show": "ai_engaged",
        "unreachable": "ai_engaged",
    }
    lead.lead_status = status_map.get(payload.outcome, lead.lead_status)

    if payload.outcome == "callback_requested" and payload.callback_datetime_utc:
        lead.booked_call_datetime = datetime.fromisoformat(
            payload.callback_datetime_utc
        )

    await session.commit()

    # Schedule post-call follow-ups for non-terminal outcomes
    if payload.outcome not in ("won", "lost_hard"):
        from api.services.scheduler_service import schedule_post_call_touches

        callback_dt = None
        if payload.callback_datetime_utc:
            callback_dt = datetime.fromisoformat(payload.callback_datetime_utc)

        await schedule_post_call_touches(
            str(lead.id), payload.outcome, now, callback_dt, session
        )

    logger.info(
        "Call outcome for lead %s: %s by %s",
        payload.lead_id, payload.outcome, payload.salesman_name,
    )
    return {"status": "logged", "lead_id": payload.lead_id, "outcome": payload.outcome}
