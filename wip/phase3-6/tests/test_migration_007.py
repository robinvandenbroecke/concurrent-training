"""Revision 007 in isolation. The full chain is PostgreSQL-only (earlier
revisions alter constraints) and runs in the PostgreSQL CI job, not here."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app import models


def test_revision_007_is_additive_reversible_and_matches_the_models():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "007_provider_connections.py"
    spec = importlib.util.spec_from_file_location("rev007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "006"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("create table athletes (id integer primary key, name text)")
        connection.exec_driver_sql("insert into athletes values (1, 'kept')")
        import alembic
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            inspector = inspect(connection)
            for model in (models.ProviderConnection, models.ProviderOAuthState):
                migrated = {c["name"] for c in inspector.get_columns(model.__tablename__)}
                assert migrated == {c.name for c in model.__table__.columns}
            module.downgrade()
        tables = set(inspect(connection).get_table_names())
        assert tables == {"athletes"}
        assert connection.exec_driver_sql("select name from athletes").scalar() == "kept"
