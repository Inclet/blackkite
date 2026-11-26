"""Awards for price benchmarks and procurement plans (spec 2.6, 6, 8; M5).

* award gains: ref_key / entity_key (dedupe keys, unique together), title,
  amount + currency (the winning price), awarded_on, category + tags, url,
  opportunity_id (the tender in the catalogue), raw (values as listed),
  first_seen / last_seen / updated_at; indexes for category, entity and date.
  Rows from before this revision get ref_key from their tender ref (or their id)
  so the unique key holds.
* New procurement_plan_item: planned tenders not yet advertised.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-26 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024  # decision 30; fixed here so the migration never moves


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _tags() -> sa.Column:
    return sa.Column(
        "tags",
        postgresql.ARRAY(sa.String(length=100)),
        server_default=sa.text("'{}'::varchar[]"),
        nullable=False,
    )


def _jsonb(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    # --- award ------------------------------------------------------------------
    op.add_column("award", sa.Column("ref_key", sa.String(length=300), nullable=True))
    op.execute(
        "UPDATE award SET ref_key = coalesce(lower(tender_ref), 'id:' || id::text)"
    )
    op.alter_column("award", "ref_key", nullable=False)
    op.add_column("award", sa.Column("title", sa.Text(), nullable=True))
    op.add_column(
        "award",
        sa.Column("entity_key", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "award", sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=True)
    )
    op.add_column("award", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("award", sa.Column("awarded_on", sa.Date(), nullable=True))
    op.add_column(
        "award",
        sa.Column(
            "category", sa.String(length=100), server_default="other", nullable=False
        ),
    )
    op.add_column("award", _tags())
    op.add_column("award", sa.Column("url", sa.Text(), nullable=True))
    op.add_column("award", sa.Column("opportunity_id", sa.Uuid(), nullable=True))
    op.add_column("award", _jsonb("raw"))
    op.add_column("award", _ts("first_seen"))
    op.add_column("award", _ts("last_seen"))
    op.add_column("award", _ts("updated_at"))
    op.create_foreign_key(
        op.f("fk_award_opportunity_id_opportunity"),
        "award",
        "opportunity",
        ["opportunity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        op.f("uq_award_ref_key_entity_key"), "award", ["ref_key", "entity_key"]
    )
    op.create_check_constraint(
        op.f("ck_award_currency_iso"),
        "award",
        "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        op.f("ck_award_amount_not_negative"), "award", "amount IS NULL OR amount >= 0"
    )
    op.create_index(op.f("ix_award_opportunity_id"), "award", ["opportunity_id"])
    op.create_index("ix_award_category_currency", "award", ["category", "currency"])
    op.create_index("ix_award_entity_key", "award", ["entity_key"])
    op.create_index("ix_award_awarded_on", "award", ["awarded_on"])
    op.create_index("ix_award_tags", "award", ["tags"], postgresql_using="gin")

    # --- procurement_plan_item ----------------------------------------------------
    op.create_table(
        "procurement_plan_item",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_key", sa.Text(), nullable=False),
        sa.Column(
            "category", sa.String(length=100), server_default="other", nullable=False
        ),
        _tags(),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("estimated_amount", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("fiscal_year", sa.String(length=7), nullable=True),
        sa.Column("planned_quarter", sa.String(length=2), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_end", sa.Date(), nullable=True),
        sa.Column("tender_ref", sa.String(length=200), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        _jsonb("raw"),
        _ts("first_seen"),
        _ts("last_seen"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_procurement_plan_item_currency_iso"),
        ),
        sa.CheckConstraint(
            "estimated_amount IS NULL OR estimated_amount >= 0",
            name=op.f("ck_procurement_plan_item_estimated_amount_not_negative"),
        ),
        sa.CheckConstraint(
            "planned_quarter IS NULL OR planned_quarter IN ('Q1', 'Q2', 'Q3', 'Q4')",
            name=op.f("ck_procurement_plan_item_planned_quarter_valid"),
        ),
        sa.CheckConstraint(
            "(planned_start IS NULL) = (planned_end IS NULL) "
            "AND (planned_start IS NULL OR planned_start <= planned_end)",
            name=op.f("ck_procurement_plan_item_planned_period_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_procurement_plan_item_opportunity_id_opportunity"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_procurement_plan_item_source_id_source"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_plan_item")),
        sa.UniqueConstraint(
            "entity_key",
            "description_key",
            "fiscal_year",
            name=op.f(
                "uq_procurement_plan_item_entity_key_description_key_fiscal_year"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_procurement_plan_item_opportunity_id"),
        "procurement_plan_item",
        ["opportunity_id"],
    )
    op.create_index(
        op.f("ix_procurement_plan_item_source_id"),
        "procurement_plan_item",
        ["source_id"],
    )
    op.create_index(
        "ix_procurement_plan_item_category", "procurement_plan_item", ["category"]
    )
    op.create_index(
        "ix_procurement_plan_item_entity_key", "procurement_plan_item", ["entity_key"]
    )
    op.create_index(
        "ix_procurement_plan_item_planned_start_planned_end",
        "procurement_plan_item",
        ["planned_start", "planned_end"],
    )
    op.create_index(
        "ix_procurement_plan_item_tags",
        "procurement_plan_item",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("procurement_plan_item")

    op.drop_index("ix_award_tags", table_name="award")
    op.drop_index("ix_award_awarded_on", table_name="award")
    op.drop_index("ix_award_entity_key", table_name="award")
    op.drop_index("ix_award_category_currency", table_name="award")
    op.drop_index(op.f("ix_award_opportunity_id"), table_name="award")
    op.drop_constraint(op.f("ck_award_amount_not_negative"), "award", type_="check")
    op.drop_constraint(op.f("ck_award_currency_iso"), "award", type_="check")
    op.drop_constraint(op.f("uq_award_ref_key_entity_key"), "award", type_="unique")
    op.drop_constraint(
        op.f("fk_award_opportunity_id_opportunity"), "award", type_="foreignkey"
    )
    for column in (
        "updated_at",
        "last_seen",
        "first_seen",
        "raw",
        "opportunity_id",
        "url",
        "tags",
        "category",
        "awarded_on",
        "currency",
        "amount",
        "entity_key",
        "title",
        "ref_key",
    ):
        op.drop_column("award", column)
