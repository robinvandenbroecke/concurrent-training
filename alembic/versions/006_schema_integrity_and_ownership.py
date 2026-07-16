"""Schema integrity and ownership foundation.

Revision ID: 006
Revises: 005
Create Date: 2026-07-16

The migration is deliberately data-preserving:
- existing athletes are assigned to the ``local`` owner namespace;
- existing workout plans receive the ``primary`` slot;
- historical inactive goals are retained;
- downgrades fail explicitly when new multi-slot or goal-history data cannot be
  represented by the old constraints without data loss.
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        item.get("name") == constraint_name
        for item in inspector.get_unique_constraints(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _drop_unique(table_name: str, constraint_name: str) -> None:
    if not _unique_constraint_exists(table_name, constraint_name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
    else:
        op.drop_constraint(constraint_name, table_name, type_="unique")


def _create_unique(table_name: str, constraint_name: str, columns: list[str]) -> None:
    if _unique_constraint_exists(table_name, constraint_name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(constraint_name, columns)
    else:
        op.create_unique_constraint(constraint_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Ownership namespace. This is intentionally not an authentication system;
    # it provides a stable data boundary for the next account/API-key sprint.
    if dialect == "sqlite":
        with op.batch_alter_table("athletes") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "owner_subject",
                    sa.String(length=255),
                    nullable=False,
                    server_default="local",
                )
            )
    else:
        op.add_column(
            "athletes",
            sa.Column(
                "owner_subject",
                sa.String(length=255),
                nullable=False,
                server_default="local",
            ),
        )
    if not _index_exists("athletes", "ix_athletes_owner_subject"):
        op.create_index(
            "ix_athletes_owner_subject", "athletes", ["owner_subject"], unique=False
        )

    # Allow more than one planned session per calendar day, while preserving
    # idempotency for the same logical slot.
    if dialect == "sqlite":
        with op.batch_alter_table("workout_plans") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "slot",
                    sa.String(length=50),
                    nullable=False,
                    server_default="primary",
                )
            )
    else:
        op.add_column(
            "workout_plans",
            sa.Column(
                "slot",
                sa.String(length=50),
                nullable=False,
                server_default="primary",
            ),
        )
    _drop_unique("workout_plans", "uq_athlete_workout_date")
    _create_unique(
        "workout_plans",
        "uq_athlete_workout_date_slot",
        ["athlete_id", "date", "slot"],
    )
    if not _index_exists("workout_plans", "ix_workout_plans_athlete_date"):
        op.create_index(
            "ix_workout_plans_athlete_date",
            "workout_plans",
            ["athlete_id", "date"],
            unique=False,
        )

    # The old (athlete_id, active) constraint also limited inactive history to
    # one row. Replace it with a partial unique index for active rows only.
    bind.execute(sa.text("UPDATE goals SET active = 0 WHERE active IS NULL"))
    _drop_unique("goals", "uq_athlete_active_goal")
    if dialect == "sqlite":
        with op.batch_alter_table("goals") as batch_op:
            batch_op.alter_column(
                "active",
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
    else:
        op.alter_column(
            "goals",
            "active",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        )
    if not _index_exists("goals", "uq_goals_one_active_per_athlete"):
        op.create_index(
            "uq_goals_one_active_per_athlete",
            "goals",
            ["athlete_id"],
            unique=True,
            postgresql_where=sa.text("active IS TRUE"),
            sqlite_where=sa.text("active = 1"),
        )
    if not _index_exists("goals", "ix_goals_athlete_created_at"):
        op.create_index(
            "ix_goals_athlete_created_at",
            "goals",
            ["athlete_id", "created_at"],
            unique=False,
        )


def _assert_downgrade_is_lossless() -> None:
    bind = op.get_bind()
    duplicate_plan = bind.execute(
        sa.text(
            """
            SELECT athlete_id, date, COUNT(*) AS n
            FROM workout_plans
            GROUP BY athlete_id, date
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_plan is not None:
        raise RuntimeError(
            "Cannot downgrade revision 006: multiple workout-plan slots exist "
            "for at least one athlete/date. Consolidate them before downgrade."
        )

    duplicate_goal_state = bind.execute(
        sa.text(
            """
            SELECT athlete_id, active, COUNT(*) AS n
            FROM goals
            GROUP BY athlete_id, active
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_goal_state is not None:
        raise RuntimeError(
            "Cannot downgrade revision 006: multiple goals share the same "
            "athlete/active state. Archival history would be lost."
        )


def downgrade() -> None:
    _assert_downgrade_is_lossless()
    dialect = op.get_bind().dialect.name

    if _index_exists("goals", "ix_goals_athlete_created_at"):
        op.drop_index("ix_goals_athlete_created_at", table_name="goals")
    if _index_exists("goals", "uq_goals_one_active_per_athlete"):
        op.drop_index("uq_goals_one_active_per_athlete", table_name="goals")
    _create_unique("goals", "uq_athlete_active_goal", ["athlete_id", "active"])

    if _index_exists("workout_plans", "ix_workout_plans_athlete_date"):
        op.drop_index("ix_workout_plans_athlete_date", table_name="workout_plans")
    _drop_unique("workout_plans", "uq_athlete_workout_date_slot")
    _create_unique(
        "workout_plans", "uq_athlete_workout_date", ["athlete_id", "date"]
    )
    if dialect == "sqlite":
        with op.batch_alter_table("workout_plans") as batch_op:
            batch_op.drop_column("slot")
    else:
        op.drop_column("workout_plans", "slot")

    if _index_exists("athletes", "ix_athletes_owner_subject"):
        op.drop_index("ix_athletes_owner_subject", table_name="athletes")
    if dialect == "sqlite":
        with op.batch_alter_table("athletes") as batch_op:
            batch_op.drop_column("owner_subject")
    else:
        op.drop_column("athletes", "owner_subject")
