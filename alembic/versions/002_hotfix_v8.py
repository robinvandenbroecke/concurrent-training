"""HOTFIX v8: Add T_legs persistence and session idempotency

Revision ID: 002_hotfix_v8
Revises: 001_initial
Create Date: 2026-02-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_hotfix_v8'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # HOTFIX Part 1: Add T_legs column to day_states
    op.add_column(
        'day_states',
        sa.Column('T_legs', sa.Float(), nullable=False, server_default='0.0')
    )
    
    # HOTFIX Part 2: Add content_hash to strength_sessions for idempotency
    op.add_column(
        'strength_sessions',
        sa.Column('content_hash', sa.String(64), nullable=True)
    )
    op.create_unique_constraint(
        'uq_strength_session_hash',
        'strength_sessions',
        ['athlete_id', 'content_hash']
    )
    
    # HOTFIX Part 2: Add content_hash to endurance_sessions for idempotency
    op.add_column(
        'endurance_sessions',
        sa.Column('content_hash', sa.String(64), nullable=True)
    )
    op.create_unique_constraint(
        'uq_endurance_session_hash',
        'endurance_sessions',
        ['athlete_id', 'content_hash']
    )


def downgrade():
    # Remove constraints first
    op.drop_constraint('uq_endurance_session_hash', 'endurance_sessions', type_='unique')
    op.drop_constraint('uq_strength_session_hash', 'strength_sessions', type_='unique')
    
    # Remove columns
    op.drop_column('endurance_sessions', 'content_hash')
    op.drop_column('strength_sessions', 'content_hash')
    op.drop_column('day_states', 'T_legs')
