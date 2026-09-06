# Concurrent Training API

> **September 2026 audit:** this is an experimental private backend and technical web console, not a released Android app or validated physiological model. Start with the [full audit](docs/audit_2026_09.md), [research protocol](docs/research_protocol.md), [Android/web roadmap](docs/product_roadmap.md), and [verification record](docs/verification.md). The newest work is stacked above open PRs #1 and #2. Historical sprint claims and calibration artifacts below are not evidence of real-world model validity.

API service for managing concurrent strength and endurance training with fatigue modeling and autoregulation.

## Features

- **Fatigue Modeling**: Three-component model (local, system, metabolic) with rep-level tracking
- **Concurrent Training**: Experimental coupling terms for endurance exposure and strength load; causal and physiological interpretation unvalidated
- **Autoregulation**: Live suggestions for load, rest, and exercise selection based on fatigue state
- **Readiness Scoring**: Per-lift and endurance readiness with explanations
- **Trend Analysis**: JSON endpoints for dashboard integration

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│   Services   │────▶│    Domain   │
│   Layer     │     │   (ingest,   │     │   (fatigue  │
│             │     │   update,    │     │   equations)│
└─────────────┘     │   autoreg)   │     └─────────────┘
                    └──────────────┘            │
                           │                    │
                    ┌──────────────┐            │
                    │  PostgreSQL  │◀───────────┘
                    │   (state)    │
                    └──────────────┘
```

## Quick Start (Ubuntu VPS)

### 1. Clone and Setup

```bash
git clone https://github.com/robinvandenbroecke/concurrent-training.git
cd concurrent-training

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Services

```bash
# Start PostgreSQL and Redis
docker compose up -d

# Run database migrations
alembic upgrade head

# Or let SQLAlchemy create tables automatically (dev mode)
```

### 3. Run Application

```bash
# Development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. Test Setup

```bash
# Run all tests
pytest -q

# Run with coverage
pytest --cov=app --cov-report=html
```

### 5. Validation

```bash
# Run full validation (synthetic data)
python run_validation.py --source synthetic --athletes 10 --days 90

# Run validation on real database
python run_validation.py --source db --athlete-id 1 --days 90

# Replay stored sessions
python run_replay.py
```

Artifacts are written to `artifacts/latest/validation_report.json`.

### 6. Demo Data

```bash
# Initialize database
python -m app.cli init

# Create demo athlete with sample sessions
python -m app.cli demo

# View readiness
python -m app.cli readiness --athlete-id 1
```

## API Endpoints

### Athletes
```bash
POST /athletes
{"name": "Test Athlete"}
```

### Strength Sessions
```bash
POST /sessions/strength
{
  "athlete_id": 1,
  "lift": "squat",
  "start_time": "2024-01-15T10:00:00",
  "sets": [
    {
      "weight": 100,
      "target_reps": 5,
      "reps": [
        {"weight": 100, "velocity": 0.45, "rep_num": 1, "rest_before": 180},
        {"weight": 100, "velocity": 0.42, "rep_num": 2, "rest_before": 3}
      ]
    }
  ]
}
```

### Endurance Sessions
```bash
POST /sessions/endurance
{
  "athlete_id": 1,
  "sport": "running",
  "start_time": "2024-01-15T08:00:00",
  "duration_minutes": 45,
  "intensity_type": "z2"
}
```

### Autoregulation
```bash
POST /strength/autoregulate
{
  "athlete_id": 1,
  "lift": "squat",
  "current_weight": 100,
  "target_v_low": 0.35,
  "target_v_high": 0.45,
  "vl_max": 20,
  "planned_reps": 5,
  "current_reps_done": 0
}

Response:
{
  "continue_set": true,
  "load_change": 0.025,
  "rest_suggestion": null,
  "exercise_switch": null,
  "predicted_velocity": 0.42,
  "current_vl": 8.5,
  "messages": ["Velocity high with low VL, increase load 2.5%"]
}
```

### Readiness
```bash
GET /readiness/today?athlete_id=1

Response:
{
  "athlete_id": 1,
  "date": "2024-01-15",
  "overall": 78.5,
  "per_lift": {
    "squat": 65.2,
    "bench": 85.3,
    "deadlift": 72.1,
    "press": 88.5,
    "power_clean": 75.0
  },
  "endurance": 82.3,
  "explanations": [
    "squat has highest fatigue (0.45)",
    "Recovery capacity enhanced (0.65)"
  ]
}
```

### Trends (for Dashboards)
```bash
GET /trends/lift?athlete_id=1&lift=squat&days=30
GET /trends/endurance?athlete_id=1&days=30
```

## Conceptual Model

The current architecture is implemented by six hardened engines (not the deprecated `ConcurrentTrainingModel`). Production ingestion flows through `EngineOrchestrator`, which coordinates `rep_engine → day_engine → performance_engine`.

### Rep-Level Engine (`rep_engine`)

State is tracked in **log-availability** space for numerical stability:
- `x_l = ln(A_l)` — local availability (per-lift)
- `x_sys = ln(A_sys)` — system availability (global)
- `x_M = ln(A_M)` — metabolic availability (formerly dimensionless M)

**Velocity prediction** (single equation):
```
v_pred = v_ref * exp(x_l + x_sys + x_M)
```

**Fatigue driver**: `y_phi = min(y, 1.0)` where `y = v_ref / v_obs`. The `min` prevents the anti-fatigue artefact when observed velocity is higher than expected.

**Catastrophe term**: when velocity loss exceeds ~40 %, an additional nonlinear penalty accelerates the drop in `x_l` and `x_sys`, matching the empirical "rep-grinding" region.

**Central driver**: the central/systemic component now includes a density factor (reps per minute / average rest) and an optional `set_end_rpe` term. This separates local muscular fatigue from global/neural fatigue and improves identifiability.

### Day-Level Engine (`day_engine`)

**Capacity (`C_l`) with saturation**: `C_l` updates include a `(1 - C_l / C_max_l)` term so that progress slows as the athlete approaches their genetic/training-age ceiling. Floor `C_min` prevents collapse to zero.

**Bounded recovery capacity (`R_mito`)**: `R_mito` is kept in `[0, 1]`. It is raised by Z2 volume (HIIT and strength history also modulate it through overload penalties and cross-signals), decays with `tau_mito ≈ 45` days, and bounded to avoid runaway values.

**Explicit interference**: all HIIT → strength interference terms are explicit functions of sport mode, timing, and intensity. There are no placeholder constants.

**Structural/connective tissue (`T_legs`)**: a slow-recovering state (`tau_T_legs ≈ 21` days) guards heavy lower-body work. When `T_legs` exceeds its guardrail threshold, readiness for squat/deadlift is reduced independently of muscular fatigue.

### Other Engines

- **Coach engine** (`coach_engine`) — generates prescriptions, adaptations, and next-set adjustments.
- **Program engine** (`program_engine`) — microcycle templates, deload logic, missed-session replanning.
- **Performance engine** (`performance_engine`) — trend detection, EWMA smoothing, e1RM estimation, progress/stagnation/regression classification.
- **Goal engine** (`goal_engine`) — macrocycle phasing, target dates, priority-aware scheduling.

### Architecture Diagram (Current)

```
┌─────────────────┐
│  FastAPI / CLI  │
└────────┬────────┘
         │
┌────────▼────────┐     ┌──────────────────────────────┐
│ EngineOrchestrator│───▶│ rep_engine  (per-rep VBT)   │
│ (single source)  │     ├──────────────────────────────┤
└────────┬────────┘     │ day_engine  (daily state)    │
         │              ├──────────────────────────────┤
         │              │ performance_engine (trends)  │
         │              ├──────────────────────────────┤
         │              │ coach_engine  (prescriptions)│
         │              ├──────────────────────────────┤
         │              │ program_engine (planning)    │
         │              ├──────────────────────────────┤
         │              │ goal_engine   (macrocycles)  │
         │              └──────────────────────────────┘
    ┌────▼────┐
    │  PostgreSQL │
    └─────────┘
```

## Configuration

System parameters are configurable per athlete via `DayEngineParams` and `RepEngineParams`:

```python
from app.domain.rep_engine import RepEngineParams
from app.domain.day_engine import DayEngineParams

rep_params = RepEngineParams(
    alpha_l=0.05,    # Local fatigue rate
    alpha_sys=0.03,  # System fatigue rate
)

day_params = DayEngineParams(
    tau_Dl={'squat': 4.0, 'bench': 2.5},  # Per-lift fatigue decay (days)
    tau_mito=45.0,   # R_mito decay (days)
    C_max=200.0,     # Capacity ceiling (saturation)
)
```

## Development

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Run migrations
alembic upgrade head

# Downgrade
alembic downgrade -1
```

### Testing

```bash
# Run specific test
pytest tests/test_domain.py::TestLiftProfile -v

# Run with pdb on failure
pytest --pdb

# Performance test
pytest --benchmark-only
```

### Docker Commands

```bash
# View logs
docker compose logs -f db

# Reset database
docker compose down -v
docker compose up -d

# Backup
docker exec concurrent-training-db pg_dump -U postgres concurrent_training > backup.sql
```

## API Documentation

When running, view interactive docs at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Production Deployment

### Systemd Service

Create `/etc/systemd/system/concurrent-training.service`:

```ini
[Unit]
Description=Concurrent Training API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/concurrent-training
Environment="PATH=/home/ubuntu/concurrent-training/.venv/bin"
Environment="DATABASE_URL=postgresql://postgres:postgres@localhost:5432/concurrent_training"
ExecStart=/home/ubuntu/concurrent-training/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable concurrent-training
sudo systemctl start concurrent-training
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## Strava Integration

Sync activities from Strava automatically into endurance sessions.

### Setup

#### 1. Create Strava Developer App

1. Go to https://www.strava.com/settings/api
2. Create a new application:
   - **Application Name**: Your App Name
   - **Category**: Training
   - **Website**: Your domain
   - **Authorization Callback Domain**: `yourdomain.com` (or `localhost` for dev)
3. Note down:
   - **Client ID**
   - **Client Secret**

#### 2. Configure Environment Variables

```bash
# Add to .env file or export
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_REDIRECT_URI=http://localhost:8000/integrations/strava/callback
STRAVA_SCOPES=read,activity:read_all
APP_BASE_URL=http://localhost:8000
```

For production:
```bash
STRAVA_REDIRECT_URI=https://api.yourdomain.com/integrations/strava/callback
APP_BASE_URL=https://api.yourdomain.com
```

#### 3. Run Migration

```bash
alembic upgrade head
```

This creates the `strava_connections` table for storing OAuth tokens.

### Usage

#### Connect Strava Account

1. Visit the status page:
   ```
   http://localhost:8000/integrations/strava?athlete_id=1
   ```

2. Click **"Connect with Strava"**

3. Authorize the application on Strava

4. You'll be redirected back to the status page showing:
   - Connection status
   - Strava athlete name
   - Token expiry
   - Last sync timestamp

#### Sync Activities

**Via Web UI:**
- Click **"Sync Last 30 Days"** button on the status page

**Via API:**
```bash
# Sync last 30 days
curl -X POST "http://localhost:8000/integrations/strava/sync?athlete_id=1&days_back=30"

# Response:
# {
#   "status": "success",
#   "athlete_id": 1,
#   "imported": 15,
#   "skipped": 3,
#   "errors": [],
#   "total_fetched": 18,
#   "synced_at": "2024-01-15T12:00:00"
# }
```

#### Disconnect

**Via Web UI:**
- Click **"Disconnect"** button on the status page

**Via API:**
```bash
curl -X POST "http://localhost:8000/integrations/strava/disconnect?athlete_id=1"
```

### Activity Mapping

Strava activities are mapped to `EnduranceSession` records:

| Strava Type | EnduranceSport | Intensity Detection |
|-------------|----------------|---------------------|
| Ride, VirtualRide, EBikeRide | CYCLING | HIIT if name contains 'interval/workout' or avg_watts > 200 |
| Run, VirtualRun | RUNNING | HIIT if name contains 'interval/sprint' |
| Swim | SWIMMING | Defaults to z2 |

**Idempotency**: Duplicate activities are prevented using content hashes based on Strava activity ID.

**Token Refresh**: Access tokens are automatically refreshed when they expire (within 1 hour of expiry).

### Local Development Example

```bash
# 1. Set env vars
export STRAVA_CLIENT_ID=12345
export STRAVA_CLIENT_SECRET=your_secret
export STRAVA_REDIRECT_URI=http://localhost:8000/integrations/strava/callback

# 2. Run the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Open browser
curl http://localhost:8000/integrations/strava?athlete_id=1
```

## License

MIT

