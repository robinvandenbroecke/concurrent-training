"""Start the hosted app with durable, private PostgreSQL storage.

Use ``python -m deployment.serve``. No credentials are logged or built into the
image. Free instances must never silently fall back to an ephemeral SQLite DB.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

SCHEMA = "ct_backend"


def deployment_config(environ: Mapping[str, str]) -> tuple[URL, int]:
    if environ.get("APP_ENV", "").lower() != "production":
        raise ValueError("Hosted startup requires APP_ENV=production")
    if len(environ.get("ADMIN_API_KEY", "").strip()) < 32:
        raise ValueError("Hosted startup requires a random ADMIN_API_KEY of at least 32 characters")
    raw_url = environ.get("DATABASE_URL", "")
    try:
        url = make_url(raw_url)
        valid_db = (
            url.get_backend_name() == "postgresql"
            and url.host and url.username and url.password and url.database
            and url.query.get("sslmode") in {"require", "verify-ca", "verify-full"}
        )
    except Exception:
        valid_db = False
    if not valid_db:
        raise ValueError("Set DATABASE_URL to a persistent PostgreSQL database with TLS")
    try:
        port = int(environ.get("PORT", "10000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("PORT must be an integer between 1 and 65535") from None
    # Never inherit a caller-supplied search path. This schema is not exposed by
    # the Supabase Data API. Timeout keeps readiness checks bounded.
    url = url.update_query_dict({
        "options": f"-csearch_path={SCHEMA} -cstatement_timeout=3000",
        "connect_timeout": "3",
    })
    return url, port


def prepare_database(url: URL) -> None:
    """Create the private schema, serialize migrations, then deny Data API roles.

    The database login must own this schema and its tables. This is a private
    backend database, not a browser-accessible account storage API.
    """
    from alembic import command
    from alembic.config import Config

    bootstrap = create_engine(url.difference_update_query(["options"]), pool_pre_ping=True)
    try:
        with bootstrap.connect() as conn:
            # Session-level lock: concurrent deploys must not run Alembic at the
            # same time. Session-mode pooling is required, not transaction mode.
            locked = conn.execute(text("select pg_try_advisory_lock(762014, 1)")).scalar()
            if not locked:
                raise RuntimeError("Another database migration is running; retry deployment")
            conn.commit()
            try:
                exists = conn.execute(text("select 1 from pg_namespace where nspname=:schema"), {"schema": SCHEMA}).scalar()
                if not exists:
                    conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
                conn.execute(text(f'REVOKE ALL ON SCHEMA "{SCHEMA}" FROM PUBLIC'))
                for role in ("anon", "authenticated"):
                    exists = conn.execute(text("select 1 from pg_roles where rolname=:role"), {"role": role}).scalar()
                    if exists:
                        conn.execute(text(f'REVOKE ALL ON SCHEMA "{SCHEMA}" FROM "{role}"'))
                conn.commit()
                command.upgrade(Config("alembic.ini"), "head")
                # Defense in depth. The owning backend login retains access;
                # no browser role receives row policies or schema privileges.
                tables = conn.execute(text("select tablename from pg_tables where schemaname=:schema"), {"schema": SCHEMA}).scalars().all()
                quote = conn.dialect.identifier_preparer.quote_identifier
                for table in tables:
                    conn.execute(text(f'ALTER TABLE "{SCHEMA}".{quote(table)} ENABLE ROW LEVEL SECURITY'))
                conn.commit()
            finally:
                conn.rollback()
                conn.execute(text("select pg_advisory_unlock(762014, 1)"))
                conn.commit()
    finally:
        bootstrap.dispose()


def main() -> None:
    url, port = deployment_config(os.environ)
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["AUTO_CREATE_TABLES"] = "false"
    os.environ["REQUIRE_API_KEY"] = "true"
    # Validate all existing production safeguards before touching the database.
    from app.config import settings  # noqa: F401

    prepare_database(url)
    import uvicorn

    uvicorn.run("app.hosted:build_app", factory=True, host="0.0.0.0", port=port, workers=1)


if __name__ == "__main__":
    main()
