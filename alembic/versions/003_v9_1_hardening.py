"""Sprint v9.1: PRODUCTION HARDENING - content_hash NOT NULL + backfill

Revision ID: 003_v9_1_hardening
Revises: 002_hotfix_v8
Create Date: 2026-02-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import hashlib
import json


# revision identifiers, used by Alembic.
revision = '003_v9_1_hardening'
down_revision = '002_hotfix_v8'
branch_labels = None
depends_on = None


def compute_strength_content_hash(athlete_id, start_time, lift, raw_data):
    """Backfill hash for existing strength sessions."""
    if raw_data and isinstance(raw_data, dict):
        sets = raw_data.get("sets", [])
        canonical_sets = []
        for s in sorted(sets, key=lambda x: (x.get("weight", 0), len(x.get("reps", [])))):
            canonical_sets.append({
                "lift": lift.lower() if lift else "unknown",
                "load_kg": round(s.get("weight", 0), 2),
                "reps": len(s.get("reps", [])),
                "velocities": [round(r.get("velocity", 0), 3) for r in s.get("reps", [])],
                "rest_sec": None,
            })
        canonical = {
            "athlete_id": athlete_id,
            "date": start_time[:10] if isinstance(start_time, str) else str(start_time)[:10],
            "sets": canonical_sets,
            "rpe": None,
        }
    else:
        # Fallback: deterministic hash from athlete_id + lift + timestamp
        canonical = {
            "athlete_id": athlete_id,
            "lift": lift,
            "timestamp": str(start_time),
            "fallback": True
        }
    
    json_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


def compute_endurance_content_hash(athlete_id, start_time, sport, duration_minutes, intensity_type):
    """Backfill hash for existing endurance sessions."""
    canonical = {
        "athlete_id": athlete_id,
        "date": start_time[:10] if isinstance(start_time, str) else str(start_time)[:10],
        "sport": sport.lower() if sport else "unknown",
        "duration_minutes": round(float(duration_minutes), 1) if duration_minutes else 0.0,
        "intensity_type": intensity_type or "unknown",
        "power_data": None,
    }
    json_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


def upgrade():
    # Get database connection
    conn = op.get_bind()
    
    # -------------------------------------------------------------------------
    # PART 1: Backfill NULL content_hash in strength_sessions
    # -------------------------------------------------------------------------
    result = conn.execute(text(
        "SELECT id, athlete_id, start_time, lift, raw_data FROM strength_sessions WHERE content_hash IS NULL"
    ))
    rows = result.fetchall()
    
    for row in rows:
        session_id, athlete_id, start_time, lift, raw_data = row
        content_hash = compute_strength_content_hash(athlete_id, start_time, lift, raw_data)
        
        conn.execute(
            text("UPDATE strength_sessions SET content_hash = :hash WHERE id = :id"),
            {"hash": content_hash, "id": session_id}
        )
    
    # -------------------------------------------------------------------------
    # PART 2: Backfill NULL content_hash in endurance_sessions
    # -------------------------------------------------------------------------
    result = conn.execute(text(
        "SELECT id, athlete_id, start_time, sport, duration_minutes, intensity_type FROM endurance_sessions WHERE content_hash IS NULL"
    ))
    rows = result.fetchall()
    
    for row in rows:
        session_id, athlete_id, start_time, sport, duration, intensity = row
        content_hash = compute_endurance_content_hash(athlete_id, start_time, sport, duration, intensity)
        
        conn.execute(
            text("UPDATE endurance_sessions SET content_hash = :hash WHERE id = :id"),
            {"hash": content_hash, "id": session_id}
        )
    
    # -------------------------------------------------------------------------
    # PART 3: Make content_hash NOT NULL
    # -------------------------------------------------------------------------
    # SQLite doesn't support ALTER COLUMN directly, use batch_alter_table
    with op.batch_alter_table('strength_sessions') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(64), nullable=False)
    
    with op.batch_alter_table('endurance_sessions') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(64), nullable=False)


def downgrade():
    # Revert NOT NULL constraints
    with op.batch_alter_table('endurance_sessions') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(64), nullable=True)
    
    with op.batch_alter_table('strength_sessions') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(64), nullable=True)
