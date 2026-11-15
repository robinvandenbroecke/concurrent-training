#!/bin/bash
# Local development start. The database file is kept between starts; delete it
# yourself if you really want an empty one.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "API docs: http://localhost:8000/docs"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
