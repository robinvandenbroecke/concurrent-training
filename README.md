# concurrent-training

Python project with database migrations, Docker services, and testing.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start services
docker compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Run tests
pytest -q
```

## Project Structure

```
concurrent-training/
├── alembic/              # Database migrations
├── app/                  # Main application code
├── tests/                # Test suite
├── docker-compose.yml    # Services (DB, Cache, etc.)
├── requirements.txt      # Python dependencies
└── README.md
```

## Development

- **Database**: PostgreSQL 15 (port 5432)
- **Cache**: Redis (port 6379)
- **Migrations**: Alembic
- **Testing**: Pytest

## Environment Variables

Copy `.env.example` to `.env` and adjust:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/concurrent_training
REDIS_URL=redis://localhost:6379/0
```
