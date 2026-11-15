"""Per-user Garmin/Wahoo connections (additive; no existing table is changed).

Revision ID: 007
Revises: 006
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False, server_default="oauth"),
        sa.Column("status", sa.String(16), nullable=False, server_default="connected"),
        sa.Column("provider_user_id", sa.String(128), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(255), nullable=True),
        sa.Column("cursor", sa.String(64), nullable=True),
        sa.Column("sync_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_connection_user"),
    )
    op.create_index("ix_provider_connections_user_id", "provider_connections", ["user_id"])
    op.create_index("ix_provider_connections_provider_user_id", "provider_connections", ["provider_user_id"])
    op.create_table(
        "provider_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("verifier_enc", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # Dropping these tables deletes stored provider links (tokens). Training
    # sessions live in the user's own account storage and are not affected.
    op.drop_table("provider_oauth_states")
    op.drop_index("ix_provider_connections_provider_user_id", table_name="provider_connections")
    op.drop_index("ix_provider_connections_user_id", table_name="provider_connections")
    op.drop_table("provider_connections")
