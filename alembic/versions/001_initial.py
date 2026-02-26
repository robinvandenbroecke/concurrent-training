"""Initial migration with all tables including performance_snapshots

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create athletes table
    op.create_table(
        'athletes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_athletes_id'), 'athletes', ['id'], unique=False)
    
    # Create strength_sessions table
    op.create_table(
        'strength_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('lift', sa.Enum('SQUAT', 'BENCH', 'DEADLIFT', 'PRESS', 'CLEAN', name='lift_type'), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tonnage', sa.Float(), default=0.0),
        sa.Column('avg_intensity', sa.Float(), default=0.0),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('rep_level_log', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strength_sessions_id'), 'strength_sessions', ['id'], unique=False)
    
    # Create endurance_sessions table
    op.create_table(
        'endurance_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('sport', sa.Enum('CYCLING', 'RUNNING', 'SWIMMING', name='endurance_sport'), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_minutes', sa.Float(), nullable=False),
        sa.Column('intensity_type', sa.String(20), nullable=True),
        sa.Column('u_E_Z2', sa.Float(), default=0.0),
        sa.Column('u_E_HIIT', sa.Float(), default=0.0),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_endurance_sessions_id'), 'endurance_sessions', ['id'], unique=False)
    
    # Create lift_profiles table
    op.create_table(
        'lift_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('lift', sa.Enum('SQUAT', 'BENCH', 'DEADLIFT', 'PRESS', 'CLEAN', name='lift_type'), nullable=False),
        sa.Column('a', sa.Float(), nullable=False, default=0.5),
        sa.Column('b', sa.Float(), nullable=False, default=0.003),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'lift', name='uq_athlete_lift')
    )
    op.create_index(op.f('ix_lift_profiles_id'), 'lift_profiles', ['id'], unique=False)
    
    # Create day_states table
    op.create_table(
        'day_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(10), nullable=False),
        sa.Column('D_sys', sa.Float(), default=0.0),
        sa.Column('R_mito', sa.Float(), default=0.0),
        sa.Column('E_fat', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'date', name='uq_athlete_date')
    )
    op.create_index(op.f('ix_day_states_id'), 'day_states', ['id'], unique=False)
    
    # Create lift_day_states table
    op.create_table(
        'lift_day_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('lift', sa.Enum('SQUAT', 'BENCH', 'DEADLIFT', 'PRESS', 'CLEAN', name='lift_type'), nullable=False),
        sa.Column('date', sa.String(10), nullable=False),
        sa.Column('D_l', sa.Float(), default=0.0),
        sa.Column('F_l', sa.Float(), default=1.0),
        sa.Column('C_l', sa.Float(), default=100.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'lift', 'date', name='uq_athlete_lift_date')
    )
    op.create_index(op.f('ix_lift_day_states_id'), 'lift_day_states', ['id'], unique=False)
    
    # Create system_parameters table
    op.create_table(
        'system_parameters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('params', sa.JSON(), default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_parameters_id'), 'system_parameters', ['id'], unique=False)
    
    # Create workout_plans table
    op.create_table(
        'workout_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(10), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False),
        sa.Column('plan_json', sa.JSON(), nullable=False),
        sa.Column('readiness_snapshot', sa.JSON(), default=dict),
        sa.Column('is_adapted', sa.Boolean(), default=False),
        sa.Column('original_plan_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.ForeignKeyConstraint(['original_plan_id'], ['workout_plans.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'date', name='uq_athlete_workout_date')
    )
    op.create_index(op.f('ix_workout_plans_id'), 'workout_plans', ['id'], unique=False)
    
    # Create performance_snapshots table (Sprint 6)
    op.create_table(
        'performance_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.String(10), nullable=False),
        sa.Column('days_analyzed', sa.Integer(), default=28),
        sa.Column('metrics_json', sa.JSON(), nullable=False),
        sa.Column('overall_signal', sa.String(30), default='maintain'),
        sa.Column('suggest_deload', sa.Boolean(), default=False),
        sa.Column('volume_adjustment_pct', sa.Float(), default=0.0),
        sa.Column('intensity_adjustment_pct', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'snapshot_date', name='uq_athlete_perf_date')
    )
    op.create_index(op.f('ix_performance_snapshots_id'), 'performance_snapshots', ['id'], unique=False)
    op.create_index(op.f('ix_performance_snapshots_athlete_id'), 'performance_snapshots', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_performance_snapshots_snapshot_date'), 'performance_snapshots', ['snapshot_date'], unique=False)

    # Create goals table (Sprint 7)
    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('goal_id', sa.String(50), nullable=False, unique=True),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('goal_type', sa.String(30), nullable=False),
        sa.Column('target_date', sa.String(10), nullable=False),
        sa.Column('priority', sa.String(20), default='balanced'),
        sa.Column('goal_json', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('current_phase', sa.String(20), default='base'),
        sa.Column('phase_start_date', sa.String(10), nullable=True),
        sa.Column('phase_end_date', sa.String(10), nullable=True),
        sa.Column('macrocycle_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('athlete_id', 'goal_id', name='uq_athlete_goal')
    )
    op.create_index(op.f('ix_goals_id'), 'goals', ['id'], unique=False)
    op.create_index(op.f('ix_goals_goal_id'), 'goals', ['goal_id'], unique=False)
    op.create_index(op.f('ix_goals_athlete_id'), 'goals', ['athlete_id'], unique=False)


def downgrade():
    op.drop_table('goals')
    op.drop_table('performance_snapshots')
    op.drop_table('workout_plans')
    op.drop_table('system_parameters')
    op.drop_table('lift_day_states')
    op.drop_table('day_states')
    op.drop_table('lift_profiles')
    op.drop_table('endurance_sessions')
    op.drop_table('strength_sessions')
    op.drop_table('athletes')
