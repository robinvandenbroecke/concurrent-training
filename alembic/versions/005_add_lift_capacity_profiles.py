"""005_add_lift_capacity_profiles.py

Sprint E3: Add lift capacity anchor + breakthrough system.

Revision ID: 005
Revises: 004
Create Date: 2026-03-06 21:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create lift_capacity_profiles table
    op.create_table(
        'lift_capacity_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('lift', sa.Enum('SQUAT', 'BENCH', 'DEADLIFT', 'PRESS', 'POWER_CLEAN', 'CLEAN', 'OTHER', name='lift_type'), nullable=False),
        sa.Column('input_type', sa.String(length=20), nullable=False),
        sa.Column('input_load_kg', sa.Float(), nullable=True),
        sa.Column('input_reps', sa.Integer(), nullable=True),
        sa.Column('input_rpe', sa.Float(), nullable=True),
        sa.Column('anchor_capacity', sa.Float(), nullable=False),
        sa.Column('model_capacity', sa.Float(), nullable=False),
        sa.Column('confidence', sa.String(length=20), nullable=False),
        sa.Column('provisional_breakthrough_count', sa.Integer(), nullable=True),
        sa.Column('last_provisional_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_confirmed_breakthrough_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_signal_value', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'lift', name='uq_athlete_lift_capacity'),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ondelete='CASCADE')
    )
    
    # Create index for efficient lookup
    op.create_index(
        'ix_lift_capacity_profiles_athlete_lift',
        'lift_capacity_profiles',
        ['athlete_id', 'lift'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_lift_capacity_profiles_athlete_lift', table_name='lift_capacity_profiles')
    op.drop_table('lift_capacity_profiles')
