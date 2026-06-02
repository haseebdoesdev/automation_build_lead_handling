from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_source: Mapped[str] = mapped_column(String(50), default="website_form")
    landing_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    business_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    country: Mapped[str] = mapped_column(
        Enum("US", "CA", name="country_enum", create_type=True)
    )
    gbp_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    recency_profile: Mapped[str] = mapped_column(String(30), default="uncertain")
    business_category: Mapped[str] = mapped_column(String(100), default="")
    urgency_flag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    free_text_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Routing
    route_decision: Mapped[str] = mapped_column(String(40), default="after_hours_ai")
    assigned_salesman: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lead_status: Mapped[str] = mapped_column(String(40), default="captured")

    # Commercial (spec v2 — industry-based)
    quoted_price_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    negotiation_step: Mapped[int] = mapped_column(Integer, default=0)
    negotiation_triggers: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Spec v2: industry-based pricing fields
    gbp_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pricing_tier: Mapped[str | None] = mapped_column(String(5), nullable=True)
    volume_bracket: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reviews_image_content: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reviews_under_one_month: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    phone_call_threshold_triggered: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    salesman_recommended_range: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    adaptive_reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI state
    ai_conversation_state: Mapped[str] = mapped_column(
        String(40), default="not_started"
    )
    ai_quote_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    soft_quote_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Call/booking
    booked_call_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    call_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Post-job
    job_completion_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_job_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    gbp_review_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    quotes: Mapped[list[Quote]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    sc_logs: Mapped[list[SelfCorrectionLog]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    scheduled_touches: Mapped[list[ScheduledTouch]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    dispatch_events: Mapped[list[SalesmanDispatch]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    stall_events: Mapped[list[StallEvent]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_leads_status", "lead_status"),
        Index("ix_leads_email", "email"),
        Index("ix_leads_phone", "phone"),
        Index("ix_leads_created", "created_at"),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20))  # "assistant", "lead", "system"
    channel: Mapped[str] = mapped_column(String(10))  # "email", "sms"
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    external_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # Twilio SID or SES message ID

    lead: Mapped[Lead] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_msg_lead_sent", "lead_id", "sent_at"),
    )


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    price_usd_per_review: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(10))
    negotiation_step: Mapped[int] = mapped_column(Integer, default=0)
    computed_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[dict] = mapped_column(JSONB)
    lead_trigger_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    lead: Mapped[Lead] = relationship(back_populates="quotes")


class SelfCorrectionLog(Base):
    __tablename__ = "self_correction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    attempt: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(20))
    failed_checks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    suggested_fixes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    draft_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    lead: Mapped[Lead] = relationship(back_populates="sc_logs")


class ScheduledTouch(Base):
    __tablename__ = "scheduled_touches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    touch_type: Mapped[str] = mapped_column(
        String(30)
    )  # "nurture", "post_call_standard", "post_call_accelerated", "review_request"
    index: Mapped[int] = mapped_column(Integer)
    fire_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channels: Mapped[list] = mapped_column(JSONB)  # ["email"], ["sms"], ["email","sms"]
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    sms_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # "pending", "sent", "cancelled", "paused"
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    lead: Mapped[Lead] = relationship(back_populates="scheduled_touches")

    __table_args__ = (
        Index("ix_touch_fire", "fire_at_utc", "status"),
        Index("ix_touch_lead", "lead_id"),
    )


class SalesmanDispatch(Base):
    __tablename__ = "salesman_dispatches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    salesman_name: Mapped[str] = mapped_column(String(100))
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    ack_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    missed: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatch_number: Mapped[int] = mapped_column(Integer, default=1)

    lead: Mapped[Lead] = relationship(back_populates="dispatch_events")


class StallEvent(Base):
    __tablename__ = "stall_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_id
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE")
    )
    commercial_turn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stall_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    salesman_paged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backup_paged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # "lead_replied", "salesman_called", "backup_called"

    lead: Mapped[Lead] = relationship(back_populates="stall_events")

    __table_args__ = (
        Index("ix_stall_lead", "lead_id"),
    )


class OperatorConfig(Base):
    __tablename__ = "operator_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
