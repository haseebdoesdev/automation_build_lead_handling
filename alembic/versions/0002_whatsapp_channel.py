"""Widen conversation_messages.channel for whatsapp support

Revision ID: 0002_whatsapp_channel
Revises: 0001_industry_pricing
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_whatsapp_channel"
down_revision = "0001_industry_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "conversation_messages",
        "channel",
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "conversation_messages",
        "channel",
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
