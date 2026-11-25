"""Save/dismiss state per (user, opportunity); scores per profile (decision 19).

user_opportunity keeps one row per (user, opportunity): state, dismiss_reason,
note. Scores move to user_opportunity_score, one row per (user, opportunity,
profile), with the composite FK that keeps the profile inside the same user.

Upgrade: every old row's score moves to user_opportunity_score. Old rows for the
same (user, opportunity) collapse to one: the most-progressed state wins
(done > acting > saved > dismissed > unseen), the latest updated_at breaking ties,
and the kept row's dismiss_reason goes with it. Distinct notes are joined so none
is lost, oldest first (by the earliest updated_at that carried each), then by text.

Downgrade: each score row becomes an old-style row carrying the user's state and
note. State rows with no score row cannot be expressed (profile_id was required)
and are dropped.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24 15:39:35.807368
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The one row kept per (user, opportunity) when state rows collapse.
_KEEP = """
    SELECT DISTINCT ON (user_id, opportunity_id) id, user_id, opportunity_id
    FROM user_opportunity
    ORDER BY user_id, opportunity_id,
             CASE state WHEN 'done' THEN 4 WHEN 'acting' THEN 3 WHEN 'saved' THEN 2
                        WHEN 'dismissed' THEN 1 ELSE 0 END DESC,
             updated_at DESC, id
"""


def upgrade() -> None:
    op.create_table(
        "user_opportunity_score",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column(
            "score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100",
            name=op.f("ck_user_opportunity_score_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_user_opportunity_score_opportunity_id_opportunity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "user_id"],
            ["profile.id", "profile.user_id"],
            name="fk_user_opportunity_score_profile_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_user_opportunity_score_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_opportunity_score")),
        sa.UniqueConstraint(
            "user_id",
            "opportunity_id",
            "profile_id",
            name=op.f("uq_user_opportunity_score_user_id_opportunity_id_profile_id"),
        ),
    )
    op.create_index(
        op.f("ix_user_opportunity_score_opportunity_id"),
        "user_opportunity_score",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_opportunity_score_profile_id"),
        "user_opportunity_score",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_opportunity_score_user_id"),
        "user_opportunity_score",
        ["user_id"],
        unique=False,
    )
    op.execute("""
        INSERT INTO user_opportunity_score
            (user_id, opportunity_id, profile_id, score, score_breakdown, score_reason,
             created_at, updated_at)
        SELECT user_id, opportunity_id, profile_id, score, score_breakdown, score_reason,
               created_at, updated_at
        FROM user_opportunity
    """)
    op.execute(
        """
        WITH distinct_notes AS (
            SELECT user_id, opportunity_id, note, min(updated_at) AS first_at
            FROM user_opportunity WHERE note IS NOT NULL
            GROUP BY user_id, opportunity_id, note
        ), notes AS (
            SELECT user_id, opportunity_id,
                   string_agg(note, E'\\n\\n' ORDER BY first_at, note) AS note
            FROM distinct_notes
            GROUP BY user_id, opportunity_id
        ), keep AS ("""
        + _KEEP
        + """)
        UPDATE user_opportunity uo SET note = notes.note
        FROM keep JOIN notes USING (user_id, opportunity_id)
        WHERE uo.id = keep.id
    """
    )
    op.execute(
        """
        DELETE FROM user_opportunity uo
        WHERE uo.id NOT IN (SELECT id FROM ("""
        + _KEEP
        + """) keep)
    """
    )
    op.drop_index(op.f("ix_user_opportunity_profile_id"), table_name="user_opportunity")
    op.drop_constraint(
        op.f("uq_user_opportunity_user_id_opportunity_id_profile_id"),
        "user_opportunity",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_user_opportunity_user_id_opportunity_id"),
        "user_opportunity",
        ["user_id", "opportunity_id"],
    )
    op.drop_constraint(
        op.f("fk_user_opportunity_profile_owner"),
        "user_opportunity",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_user_opportunity_score_range"), "user_opportunity", type_="check"
    )
    op.drop_column("user_opportunity", "score_reason")
    op.drop_column("user_opportunity", "score")
    op.drop_column("user_opportunity", "profile_id")
    op.drop_column("user_opportunity", "score_breakdown")


def downgrade() -> None:
    op.add_column(
        "user_opportunity",
        sa.Column(
            "score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column("user_opportunity", sa.Column("profile_id", sa.Uuid(), nullable=True))
    op.add_column(
        "user_opportunity", sa.Column("score", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "user_opportunity", sa.Column("score_reason", sa.Text(), nullable=True)
    )
    op.drop_constraint(
        op.f("uq_user_opportunity_user_id_opportunity_id"),
        "user_opportunity",
        type_="unique",
    )
    op.execute("""
        INSERT INTO user_opportunity
            (user_id, opportunity_id, profile_id, score, score_breakdown, score_reason,
             state, dismiss_reason, note, created_at, updated_at)
        SELECT s.user_id, s.opportunity_id, s.profile_id, s.score, s.score_breakdown,
               s.score_reason, COALESCE(uo.state, 'unseen'), uo.dismiss_reason, uo.note,
               s.created_at, GREATEST(s.updated_at, uo.updated_at)
        FROM user_opportunity_score s
        LEFT JOIN user_opportunity uo
          ON uo.user_id = s.user_id AND uo.opportunity_id = s.opportunity_id
         AND uo.profile_id IS NULL
    """)
    op.execute("DELETE FROM user_opportunity WHERE profile_id IS NULL")
    op.alter_column(
        "user_opportunity", "profile_id", existing_type=sa.Uuid(), nullable=False
    )
    op.create_check_constraint(
        op.f("ck_user_opportunity_score_range"),
        "user_opportunity",
        "score IS NULL OR score BETWEEN 0 AND 100",
    )
    op.create_foreign_key(
        "fk_user_opportunity_profile_owner",
        "user_opportunity",
        "profile",
        ["profile_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_user_opportunity_user_id_opportunity_id_profile_id"),
        "user_opportunity",
        ["user_id", "opportunity_id", "profile_id"],
    )
    op.create_index(
        op.f("ix_user_opportunity_profile_id"),
        "user_opportunity",
        ["profile_id"],
        unique=False,
    )
    op.drop_index(
        op.f("ix_user_opportunity_score_user_id"), table_name="user_opportunity_score"
    )
    op.drop_index(
        op.f("ix_user_opportunity_score_profile_id"),
        table_name="user_opportunity_score",
    )
    op.drop_index(
        op.f("ix_user_opportunity_score_opportunity_id"),
        table_name="user_opportunity_score",
    )
    op.drop_table("user_opportunity_score")
