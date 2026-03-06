"""add_strava_connection

Revision ID: 004
Revises: 003_v9_1_hardening
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003_v9_1_hardening'
branch_labels = None
depends_on = None


def upgrade():
    # Create strava_connections table
    op.create_table(
        'strava_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('strava_athlete_id', sa.String(length=50), nullable=False),
        sa.Column('strava_athlete_name', sa.String(length=255), nullable=True),
        sa.Column('access_token', sa.String(length=255), nullable=False),
        sa.Column('refresh_token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False),
        sa.Column('accepted_scopes', sa.String(length=255), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_error', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id'),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], )
    )
    op.create_index(op.f('ix_strava_connections_id'), 'strava_connections', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_strava_connections_id'), table_name='strava_connections')
    op.drop_table('strava_connections')
