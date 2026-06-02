"""Spec v2: industry-based pricing fields

Adds 7 columns for the industry-based pricing matrix and phone-call threshold:
  gbp_category, pricing_tier, volume_bracket, reviews_image_content,
  reviews_under_one_month, phone_call_threshold_triggered,
  salesman_recommended_range, adaptive_reasoning_summary

Drops 2 columns from the v7 hidden-cost margin model that are no longer
populated by the engine:
  lead_cost_estimated_usd, hidden_margin_estimate_usd

Revision ID: 0001_industry_pricing
Revises:
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_industry_pricing"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("gbp_category", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("pricing_tier", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("volume_bracket", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("reviews_image_content", JSONB, nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("reviews_under_one_month", JSONB, nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "phone_call_threshold_triggered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "leads",
        sa.Column("salesman_recommended_range", JSONB, nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("adaptive_reasoning_summary", sa.Text(), nullable=True),
    )

    # Best-effort backfill of pricing_tier from existing business_category strings.
    op.execute(
        """
        UPDATE leads SET pricing_tier = CASE
            WHEN lower(business_category) LIKE '%dental%' THEN 'T1'
            WHEN lower(business_category) LIKE '%dentist%' THEN 'T1'
            WHEN lower(business_category) LIKE '%law%' THEN 'T1'
            WHEN lower(business_category) LIKE '%attorney%' THEN 'T1'
            WHEN lower(business_category) LIKE '%lawyer%' THEN 'T1'
            WHEN lower(business_category) LIKE '%plastic surgeon%' THEN 'T1'
            WHEN lower(business_category) LIKE '%clinic%' THEN 'T1'
            WHEN lower(business_category) LIKE '%chiropractor%' THEN 'T1'
            WHEN lower(business_category) LIKE '%pharmacy%' THEN 'T2'
            WHEN lower(business_category) LIKE '%hvac%' THEN 'T2'
            WHEN lower(business_category) LIKE '%roofing%' THEN 'T2'
            WHEN lower(business_category) LIKE '%med spa%' THEN 'T2'
            WHEN lower(business_category) LIKE '%insurance%' THEN 'T2'
            WHEN lower(business_category) LIKE '%real estate%' THEN 'T2'
            WHEN lower(business_category) LIKE '%plumb%' THEN 'T3'
            WHEN lower(business_category) LIKE '%electric%' THEN 'T3'
            WHEN lower(business_category) LIKE '%paving%' THEN 'T3'
            WHEN lower(business_category) LIKE '%landscap%' THEN 'T3'
            WHEN lower(business_category) LIKE '%moving%' THEN 'T3'
            WHEN lower(business_category) LIKE '%hotel%' THEN 'T3'
            WHEN lower(business_category) LIKE '%restaurant%' THEN 'T3'
            WHEN lower(business_category) LIKE '%fitness%' THEN 'T3'
            WHEN lower(business_category) LIKE '%dealership%' THEN 'T3'
            WHEN lower(business_category) LIKE '%nail%' THEN 'T4'
            WHEN lower(business_category) LIKE '%salon%' THEN 'T4'
            WHEN lower(business_category) LIKE '%bakery%' THEN 'T4'
            WHEN lower(business_category) LIKE '%coffee%' THEN 'T4'
            WHEN lower(business_category) LIKE '%cafe%' THEN 'T4'
            WHEN lower(business_category) LIKE '%car wash%' THEN 'T4'
            WHEN lower(business_category) LIKE '%auto repair%' THEN 'T4'
            WHEN lower(business_category) LIKE '%detailing%' THEN 'T4'
            WHEN lower(business_category) LIKE '%grocery%' THEN 'T4'
            WHEN lower(business_category) LIKE '%clothing%' THEN 'T4'
            ELSE NULL
        END
        WHERE pricing_tier IS NULL AND business_category IS NOT NULL;
        """
    )

    # Drop v7 hidden-cost columns — floors are the only margin protection now.
    op.drop_column("leads", "lead_cost_estimated_usd")
    op.drop_column("leads", "hidden_margin_estimate_usd")


def downgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "hidden_margin_estimate_usd",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "lead_cost_estimated_usd",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )
    op.drop_column("leads", "adaptive_reasoning_summary")
    op.drop_column("leads", "salesman_recommended_range")
    op.drop_column("leads", "phone_call_threshold_triggered")
    op.drop_column("leads", "reviews_under_one_month")
    op.drop_column("leads", "reviews_image_content")
    op.drop_column("leads", "volume_bracket")
    op.drop_column("leads", "pricing_tier")
    op.drop_column("leads", "gbp_category")
