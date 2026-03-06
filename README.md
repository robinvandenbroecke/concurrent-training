# Concurrent Training API

API service for managing concurrent strength and endurance training with fatigue modeling and autoregulation.

## Features

- **Fatigue Modeling**: Three-component model (local, system, metabolic) with rep-level tracking
- **Concurrent Training**: Explicit modeling of interference (HIIT → strength) and synergy (Z2 → recovery)
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

### 5. Demo Data

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

### Fatigue Components

1. **Local Availability (A_l)**: Per-lift, rep-level
   - Decreases with each rep
   - Recovers during rest
   - Tracked as x_l = ln(A_l)

2. **System Availability (A_sys)**: Global, rep-level
   - Spills over across all lifts
   - Recovers slower than local

3. **Metabolic Limitation (M)**: Metabolic cost
   - Accumulates with rep volume
   - Decays during rest
   - Reduces velocity via exp(-kM*M)

### Day-Level States

- **D_l**: Per-lift fatigue (decays over days)
- **F_l**: Fitness/adaptation (slow buildup)
- **C_l**: Capacity ceiling (e1RM-like)
- **D_sys**: System fatigue
- **R_mito**: Recovery capacity (built by Z2)
- **E_fat**: Endurance fatigue (from HIIT)

### Interference & Synergy

**Interference (HIIT → Strength)**:
- Running > Cycling > Swimming for legs impact
- Peak effect <24h before strength
- Adds to D_l and D_sys

**Synergy (Z2 → Recovery)**:
- Builds R_mito
- Faster fatigue decay: tau_eff = tau / (1 + beta*R_mito)
- Faster metabolic clearance

## Configuration

System parameters are configurable per athlete via `SystemParameters`:

```python
params = SystemParameters(
    alpha_l=0.05,      # Local fatigue rate
    alpha_sys=0.03,    # System fatigue rate
    tau_Dl=3.0,        # Days fatigue decay
    tau_mito=7.0,      # Days R_mito decay
    k_ES_squat=0.002,  # HIIT to squat interference
    # ... see app/domain/model.py for all params
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
